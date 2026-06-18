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

import logging
import logging.handlers
import queue
import sys

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
            log_signal = pyqtSignal(str, str, int)  # (时间, 模块名, 级别, 消息)

        self._emitter = _Emitter()
        self.log_signal = self._emitter.log_signal

    def emit(self, record: logging.LogRecord):
        """将 LogRecord 转换为信号发射（UI 简化格式：只显示时间 + 消息）"""
        color = LOG_COLORS.get(record.levelno, "#000000")
        # 只提取时:分:秒
        time_str = logging.Formatter("%(asctime)s", datefmt="%H:%M:%S").format(record)
        msg = f"[{time_str}] {record.getMessage()}"
        self.log_signal.emit(msg, color, record.levelno)


class QueueHandler(logging.handlers.QueueHandler):
    """线程安全的日志队列 Handler，直接包装标准库实现"""
    pass


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

    # 1) QueueHandler：工作线程写入队列
    queue_handler = QueueHandler(_log_queue)
    queue_handler.setLevel(logging.DEBUG)
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
    listener_handlers.append(console_handler)

    # 文件输出（按大小轮转，可选）
    if enable_file_logging:
        if log_dir is None:
            import os
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)

        file_fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
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

    # Qt 桥接（可选）
    if enable_qt_bridge:
        try:
            _qt_emitter = QtLogEmitter()
            qt_handler = _QtBridgeHandler(_qt_emitter)
            qt_handler.setLevel(logging.DEBUG)
            qt_handler.setFormatter(file_fmt)
            listener_handlers.append(qt_handler)
        except Exception:
            pass

    # 启动 QueueListener（在独立线程中从队列消费日志）
    _log_listener = logging.handlers.QueueListener(
        _log_queue, *listener_handlers, respect_handler_level=True
    )
    _log_listener.start()

    logging.info("日志系统初始化完成")
    return _qt_emitter


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger。
    如果 setup_logging() 未被调用，logger 仍可用，只是走默认的 StreamHandler。
    """
    return logging.getLogger(name)


def shutdown_logging():
    """
    关闭日志系统。程序退出前调用，确保所有日志都写入完毕。
    支持重新初始化（setup_logging 可再次调用）。
    """
    global _log_listener, _log_queue, _qt_emitter
    if _log_listener is not None:
        _log_listener.stop()
        _log_listener = None
    _log_queue = None
    _qt_emitter = None
    # 清理 root logger 的 handler，避免重复
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    logging.shutdown()
