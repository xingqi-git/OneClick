# -*- coding: utf-8 -*-
"""
日志模块
基于 Python 标准 logging + QueueHandler，线程安全，支持文件持久化和 UI 桥接

用法:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("连接服务器 %s", ip)
    logger.error("执行失败", exc_info=True)

主程序启动时初始化（可选，需要 UI 桥接时调用）:
    from utils.logger import setup_logging
    log_emitter = setup_logging()
    log_emitter.log_signal.connect(main_window.append_log)
"""

import contextvars
import logging
import logging.handlers
import os
import queue
import sys

# 自定义进度级别（介于 INFO=20 和 WARNING=30 之间）
# 文件(DEBUG+)全量记录，控制台过滤掉，UI 走单独的 progress_signal
PROGRESS = 21
logging.addLevelName(PROGRESS, "PROGRESS")

# 当前操作上下文（在 Worker 线程内设置）：(操作名/按钮名, 唯一执行ID)
_op_context = contextvars.ContextVar('op_context', default=('', ''))


class operation_context:
    """操作上下文管理器：让该线程内产生的日志自动带上操作名和执行ID

    用法（OneClickWorker.run_task 内）:
        with operation_context('文件下载', 'fb_download_1695...'):
            func(...)
    """
    def __init__(self, name='', op_id=''):
        self.name = name
        self.op_id = op_id
        self._token = None

    def __enter__(self):
        self._token = _op_context.set((self.name, self.op_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _op_context.reset(self._token)
        return False


def log_progress(logger, phase, current, total, extra=''):
    """记录一条进度日志

    - 日志文件：人类可读的全量记录（PROGRESS 级别）
    - 运行信息面板：通过 progress_signal 结构化下发，由 UI 更新同一行
    """
    if logger.isEnabledFor(PROGRESS):
        human_msg = f"[{phase}] {current}/{total} {extra}".rstrip()
        logger.log(
            PROGRESS, human_msg,
            extra={'progress': (phase, str(current), str(total), str(extra))}
        )

# 颜色映射（供 UI 根据级别渲染颜色）
LOG_COLORS = {
    logging.DEBUG:    "#808080",   # 灰色
    logging.INFO:     "#000000",   # 黑色
    logging.WARNING:  "#FF8C00",   # 深橙色
    logging.ERROR:    "#FF0000",   # 红色
    logging.CRITICAL: "#8B0000",   # 深红色
}

LOG_LEVEL_NAMES = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO",
    logging.WARNING:  "WARNING",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "CRITICAL",
}

# 全局队列和 listener（由 setup_logging 初始化）
_log_queue = None
_log_listener = None
_qt_emitter = None
_file_handler = None
_console_handler = None
_qt_handler = None
_log_dir = None
_max_bytes = None


class QtLogEmitter:
    """
    Qt 日志发射器（不强制依赖 PyQt5，按需导入）
    主线程通过连接 log_signal 接收日志，自动在 UI 中展示
    """
    _qt_available = None

    @classmethod
    def _check_qt(cls):
        if cls._qt_available is None:
            try:
                from PyQt5.QtCore import QObject, pyqtSignal
                cls._qt_available = True
            except ImportError:
                cls._qt_available = False
        return cls._qt_available

    def __init__(self):
        if not self._check_qt():
            raise RuntimeError("PyQt5 未安装，无法创建 QtLogEmitter")
        from PyQt5.QtCore import QObject, pyqtSignal

        class _Emitter(QObject):
            log_signal = pyqtSignal(str, str, int, str)       # (消息, 颜色, 级别, 操作名)
            progress_signal = pyqtSignal(str, str, str, str, str, str)
            # (操作名, 执行ID, phase, current, total, extra)

        self._emitter = _Emitter()
        self.log_signal = self._emitter.log_signal
        self.progress_signal = self._emitter.progress_signal

    def emit(self, record: logging.LogRecord):
        """将 LogRecord 转换为信号发射（UI 简化格式：只显示消息，时间由 UI 自己加）"""
        color = LOG_COLORS.get(record.levelno, "#000000")
        op_name = getattr(record, 'op_name', '') or ''
        self.log_signal.emit(record.getMessage(), color, record.levelno, op_name)

    def emit_progress(self, record: logging.LogRecord):
        """发射结构化进度信号"""
        phase, current, total, extra = record.progress
        self.progress_signal.emit(
            getattr(record, 'op_name', '') or '',
            getattr(record, 'op_id', '') or '',
            phase, current, total, extra
        )


class QueueHandler(logging.handlers.QueueHandler):
    """线程安全的日志队列 Handler，直接包装标准库实现"""
    pass


class _OpContextFilter(logging.Filter):
    """在【日志产生线程】执行：把当前操作上下文注入 record

    必须挂在 QueueHandler 上（producer 侧），不能挂在 listener 侧的 handler 上，
    因为操作上下文是线程局部的。
    """
    def filter(self, record):
        op_name, op_id = _op_context.get()
        record.op_name = op_name
        record.op_id = op_id
        return True


class _SuppressProgressFilter(logging.Filter):
    """控制台不打印高频进度（文件全量、UI 单独通道）"""
    def filter(self, record):
        return record.levelno != PROGRESS


class _QtBridgeHandler(logging.Handler):
    """
    内部 Handler：将日志记录交给 QtLogEmitter 发射
    只在主线程的 QueueListener 中被调用，因此是线程安全的
    """
    def __init__(self, emitter: QtLogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord):
        try:
            if hasattr(record, 'progress'):
                self.emitter.emit_progress(record)
            else:
                self.emitter.emit(record)
        except Exception:
            self.handleError(record)


def setup_logging(
    log_dir: str = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    enable_file_logging: bool = True,
    enable_qt_bridge: bool = True,
):
    """
    初始化日志系统。主程序启动时调用一次。

    Args:
        log_dir: 日志文件保存目录，默认当前目录下的 logs/
        max_bytes: 单个日志文件最大字节数（默认 10MB）
        backup_count: 保留的备份文件数量（默认 5 个）
        console_level: 控制台输出级别（默认 INFO）
        file_level: 文件输出级别（默认 DEBUG）
        enable_file_logging: 是否启用文件日志持久化（默认 True）
        enable_qt_bridge: 是否启用 Qt 信号桥接（默认 True）

    Returns:
        QtLogEmitter 实例（供主界面连接信号），如果 enable_qt_bridge=False 则返回 None
    """
    global _log_queue, _log_listener, _qt_emitter

    if _log_listener is not None:
        return _qt_emitter

    # 创建队列
    _log_queue = queue.Queue(-1)

    # 根 logger 配置
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 移除已有的 handler，避免重复
    for h in root.handlers[:]:
        root.removeHandler(h)

    # 干掉第三方库的噪音（paramiko transport DEBUG 包分析全丢）
    logging.getLogger('paramiko').setLevel(logging.WARNING)
    logging.getLogger('paramiko.transport').setLevel(logging.WARNING)

    # 1) QueueHandler：工作线程写入队列（filter 在产生线程执行，注入操作上下文）
    queue_handler = QueueHandler(_log_queue)
    queue_handler.setLevel(logging.DEBUG)
    queue_handler.addFilter(_OpContextFilter())
    root.addHandler(queue_handler)

    # 2) 准备 listener 的 handlers（在主线程中执行）
    listener_handlers = []

    # 控制台输出
    console_fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_fmt)
    console_handler.addFilter(_SuppressProgressFilter())
    listener_handlers.append(console_handler)
    global _console_handler
    _console_handler = console_handler

    # 文件输出（按大小轮转，可选）
    if enable_file_logging:
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        global _log_dir, _max_bytes
        _log_dir = log_dir
        _max_bytes = max_bytes

        file_fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "OneClick.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(file_fmt)
        listener_handlers.append(file_handler)
        global _file_handler
        _file_handler = file_handler

    # Qt 桥接（可选，UI 只看 INFO+）
    if enable_qt_bridge:
        try:
            _qt_emitter = QtLogEmitter()
            qt_handler = _QtBridgeHandler(_qt_emitter)
            qt_handler.setLevel(logging.INFO)  # UI 只看 INFO 及以上，DEBUG 不刷屏
            listener_handlers.append(qt_handler)
            global _qt_handler
            _qt_handler = qt_handler
        except Exception:
            pass

    # 启动 QueueListener（在独立线程中从队列消费日志）
    _log_listener = logging.handlers.QueueListener(
        _log_queue, *listener_handlers, respect_handler_level=True
    )
    _log_listener.start()

    return _qt_emitter


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger。
    如果 setup_logging() 未被调用，logger 仍可用，只是走默认的 StreamHandler。
    """
    return logging.getLogger(name)


def get_emitter():
    """获取全局 QtLogEmitter（setup_logging 后可用），供对话框订阅 progress_signal"""
    return _qt_emitter


def subscribe_progress(op_id, callback):
    """订阅指定操作的进度信号，返回退订函数

    Qt 信号跨线程自动排队，callback 在 GUI 主线程执行。
    只有 op_id 完全匹配的进度才会触发回调。
    """
    if _qt_emitter is None:
        return lambda: None

    def _handler(_op_name, _op_id, phase, current, total, extra):
        if _op_id == op_id:
            callback(phase, current, total, extra)

    _qt_emitter.progress_signal.connect(_handler)

    def _unsubscribe():
        try:
            _qt_emitter.progress_signal.disconnect(_handler)
        except Exception:
            pass

    return _unsubscribe


def shutdown_logging():
    """
    关闭日志系统。程序退出前调用，确保所有日志都写入完毕。
    支持重新初始化（setup_logging 可再次调用）。
    """
    global _log_listener, _log_queue, _qt_emitter, _file_handler
    if _log_listener is not None:
        _log_listener.stop()
        _log_listener = None
    _log_queue = None
    _qt_emitter = None
    _file_handler = None
    # 清理 root logger 的 handler，避免重复
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    logging.shutdown()


def set_file_logging(enabled: bool):
    """运行时开关文件日志（动态生效，无需重启）"""
    if _file_handler is None:
        return False
    if enabled:
        _file_handler.setLevel(logging.DEBUG)
    else:
        # 禁用：设成一个不可能的级别（CRITICAL 以上）
        _file_handler.setLevel(logging.CRITICAL + 1)
    return True


def set_file_log_level(level: int):
    """运行时调整文件日志级别（DEBUG/INFO/WARNING/ERROR）"""
    if _file_handler is None:
        return False
    _file_handler.setLevel(level)
    return True


def is_file_logging_enabled() -> bool:
    """查询文件日志是否开启"""
    if _file_handler is None:
        return False
    return _file_handler.level <= logging.CRITICAL


def set_panel_level(level: int):
    """运行时调整运行信息面板（UI）的日志级别"""
    if _qt_handler is None:
        return False
    _qt_handler.setLevel(level)
    return True


def get_panel_level() -> int:
    """查询面板日志级别"""
    if _qt_handler is None:
        return logging.INFO
    return _qt_handler.level


def set_console_level(level: int):
    """运行时调整控制台日志级别"""
    if _console_handler is None:
        return False
    _console_handler.setLevel(level)
    return True


def set_file_backup_count(count: int):
    """运行时调整日志文件保留个数（重建 file handler）"""
    global _file_handler, _log_listener
    if _file_handler is None or _log_dir is None:
        return False
    count = max(1, int(count))
    old_level = _file_handler.level
    old_formatter = _file_handler.formatter
    old_filename = _file_handler.baseFilename
    try:
        new_handler = logging.handlers.RotatingFileHandler(
            filename=old_filename,
            maxBytes=_max_bytes if _max_bytes else 10 * 1024 * 1024,
            backupCount=count,
            encoding="utf-8",
        )
        new_handler.setLevel(old_level)
        new_handler.setFormatter(old_formatter)

        # 在 listener 中替换 handler：先停 listener，替换后重启
        if _log_listener is not None:
            _log_listener.stop()
            handlers = list(_log_listener.handlers)
            for i, h in enumerate(handlers):
                if h is _file_handler:
                    handlers[i] = new_handler
                    break
            _file_handler.close()
            _file_handler = new_handler
            _log_listener.handlers = handlers
            _log_listener.start()
        return True
    except Exception:
        return False


def get_file_backup_count() -> int:
    """查询日志文件保留个数"""
    if _file_handler is None:
        return 5
    return getattr(_file_handler, 'backupCount', 5)
