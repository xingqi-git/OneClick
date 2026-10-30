r"""
    打包命令（推荐，体积优化版）：
    pyinstaller OneClick.spec --clean

    原始命令（直接打，不做排除）：
    pyinstaller -F -w OneClick.py -i app.ico --add-data "app.ico;."

    参数说明：
    -F 或 --onefile：将所有文件打包成一个单独的可执行文件
    -w 或 --windowed、--noconsole：打包成不带控制台窗口的程序
    -i 或 --icon：指定程序的图标.ico
    --upx-dir 打包压缩，参数指定 UPX 所在目录--upx-dir "path/to/upx" my_script.py
    --noupx 不使用upx

    OneClick.spec 中已配置排除未用的 Qt 模块（Qml/Quick/Multimedia/WebEngine 等）
    以及 tkinter、IPython 等，可在原基础上进一步减小体积。
"""



from MainWindowLogic import MainWindowLogic
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer
import sys
import os


def resource_path(relative_path):
    """获取资源文件路径，兼容源码运行和 PyInstaller 打包（-F 单文件模式）"""
    if getattr(sys, 'frozen', False):
        # 打包后：优先找 exe 同目录的文件（方便用户手动替换），其次找打包进 exe 的资源
        p = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(p):
            return p
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


if __name__ == '__main__':
    def run():
        # Windows 任务栏需要设置 AppUserModelID，否则可能显示默认图标且不与窗口图标关联
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('OneClick.V2.4')
        except Exception:
            pass

        # 日志系统：最早初始化，确保后续所有日志都能走对路径
        import logging
        from utils.logger import setup_logging
        if getattr(sys, 'frozen', False):
            _base_dir = os.path.dirname(sys.executable)
        else:
            _base_dir = os.path.dirname(os.path.abspath(__file__))
        setup_logging(log_dir=os.path.join(_base_dir, "logs"))

        # ─────────── 崩溃捕获机制：任何崩溃都要留下痕迹 ───────────
        # 背景：windowed 打包无控制台，崩溃时默认零痕迹，事后无法定位。
        # 三层捕获，结果统一写入 logs/crash.log（独立于主日志，主日志系统崩溃时可能已死）：
        #   1. faulthandler —— C 层原生崩溃（段错误/访问冲突等），崩溃瞬间直接写文件
        #   2. sys.excepthook / threading.excepthook —— 未处理的 Python 异常
        #   3. qInstallMessageHandler —— Qt 层警告/致命消息（如 QThread destroyed while running）
        import time as _time
        import traceback
        import faulthandler

        crash_dir = os.path.join(_base_dir, "logs")
        crash_log_path = os.path.join(crash_dir, "crash.log")

        def _write_crash_file(text):
            """同步直写崩溃文件（不走日志队列，崩溃瞬间也能落盘）"""
            try:
                os.makedirs(crash_dir, exist_ok=True)
                with open(crash_log_path, "a", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass

        # 1) faulthandler：原生崩溃发生时 Python 已无法执行任何代码，
        #    必须提前打开文件句柄，由底层信号处理器直接写入（含所有线程的调用栈）
        try:
            if os.path.exists(crash_log_path) and os.path.getsize(crash_log_path) > 512 * 1024:
                os.replace(crash_log_path, crash_log_path + ".old")
        except OSError:
            pass
        try:
            _crash_file = open(crash_log_path, "a", encoding="utf-8")
            _crash_file.write(
                f"\n===== OneClick 启动 {_time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"pid={os.getpid()} frozen={bool(getattr(sys, 'frozen', False))} =====\n")
            _crash_file.flush()
            faulthandler.enable(file=_crash_file, all_threads=True)
            globals()['_crash_file_handle'] = _crash_file  # 保持引用，防止句柄被回收关闭
        except Exception as e:
            _write_crash_file(f"faulthandler 初始化失败: {e}\n")

        # 2) 未处理的 Python 异常（windowed 模式下默认完全不可见）
        #    注：PyQt5 对槽函数里的未处理异常，只有安装了自定义 excepthook 才会
        #    调用钩子而不是直接 qFatal 终止进程——装上钩子后这类错误可被记录且进程存活
        def _excepthook(exc_type, exc_value, exc_tb):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_tb)
                return
            tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _write_crash_file(
                f"\n===== 未处理Python异常 {_time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
                f"{tb_text}\n")
            try:
                logging.getLogger("crash").critical("未处理的Python异常:\n%s", tb_text)
            except Exception:
                pass

        sys.excepthook = _excepthook

        def _thread_excepthook(args):
            tb_text = "".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback))
            _write_crash_file(
                f"\n===== 线程未处理异常 [{getattr(args.thread, 'name', '?')}] "
                f"{_time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{tb_text}\n")
            try:
                logging.getLogger("crash").critical(
                    "线程[%s]未处理异常:\n%s", getattr(args.thread, 'name', '?'), tb_text)
            except Exception:
                pass

        import threading
        threading.excepthook = _thread_excepthook

        # 3) Qt 消息钩子：捕获 Qt 层的警告/严重/致命消息（默认同样不可见）
        from PyQt5 import QtCore as _QtCore

        def _qt_message_handler(msg_type, context, message):
            # 防递归：处理过程中再产生的 Qt 消息直接丢弃
            if getattr(_qt_message_handler, "_in_progress", False):
                return
            _qt_message_handler._in_progress = True
            try:
                where = ""
                try:
                    if context.file:
                        where = (f" ({os.path.basename(context.file)}:"
                                 f"{context.line} {context.function or ''})")
                except Exception:
                    pass
                if msg_type == _QtCore.QtFatalMsg:
                    # Qt 致命错误：钩子返回后进程会 abort，同步落盘，faulthandler 会再补全线程堆栈
                    _write_crash_file(
                        f"\n===== Qt致命错误 {_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(进程即将abort) =====\n{message}{where}\n")
                    logging.getLogger("crash").critical("Qt致命错误%s: %s", where, message)
                elif msg_type == _QtCore.QtCriticalMsg:
                    logging.getLogger("qt").critical("Qt严重%s: %s", where, message)
                elif msg_type == _QtCore.QtWarningMsg:
                    logging.getLogger("qt").warning("Qt警告%s: %s", where, message)
                # QtDebugMsg/QtInfoMsg 噪音大且诊断价值低，不记录
            except Exception:
                pass
            finally:
                _qt_message_handler._in_progress = False

        _QtCore.qInstallMessageHandler(_qt_message_handler)

        app = QApplication(sys.argv)
        app.setApplicationName("OneClick")
        app.setApplicationVersion("V2.4")

        # 设置应用程序图标（任务栏显示）
        icon_path = resource_path("app.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        # global_font = QFont()  # 获取系统默认字体的配置
        # global_font.setKerning(False)  # 关Kerning，解决roo等o中间有空格的显示问题
        # app.setFont(global_font)  # 应用到所有控件

        window = MainWindowLogic()
        # 延迟到事件循环空闲后再最大化，避免 QSplitter 尺寸计算冲突
        QTimer.singleShot(0, window.showMaximized)
        sys.exit(app.exec_())

    run()
