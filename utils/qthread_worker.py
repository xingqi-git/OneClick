import sys
from io import StringIO
import threading
from PyQt5.QtCore import pyqtSignal, QObject


# ---------------------- 线程局部 stdout 路由器 ----------------------
class ThreadLocalStreamRouter:
    """
    替代 sys.stdout 的全局路由器。
    根据当前线程，把 print 内容分发到不同的流（或默认控制台）。
    未注册 stream 的线程不受影响（如 paramiko 内部线程）。
    """
    def __init__(self, default_stdout):
        self._local = threading.local()
        self._default_stdout = default_stdout

    def register_worker(self, stream):
        """注册当前线程的输出流"""
        self._local.stream = stream

    def unregister_worker(self):
        """注销当前线程的输出流"""
        if hasattr(self._local, 'stream'):
            del self._local.stream

    def write(self, text):
        if hasattr(self._local, 'stream'):
            self._local.stream.write(text)
        else:
            self._default_stdout.write(text)

    def flush(self):
        if hasattr(self._local, 'stream'):
            self._local.stream.flush()
        else:
            self._default_stdout.flush()


# 替换 sys.stdout（仅影响 print）
_router = ThreadLocalStreamRouter(sys.stdout)
sys.stdout = _router


# ---------------------- 自定义输出流：把 print 转发到 Qt 信号 ----------------------
class Stream(StringIO):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def write(self, text):
        super().write(text)
        # 过滤空行，发送非空内容（统一作为 INFO 级别）
        if text.strip():
            self.signal.emit(text.strip(), 'INFO')


class OneClickWorker(QObject):
    finished = pyqtSignal(object)  # 用于传递结果
    log_signal = pyqtSignal(str, str)  # 用于传递日志信息 (消息, 级别)
    echo_signal = pyqtSignal(str)  # 命令回显专用信号
    info_signal = pyqtSignal(object)  # 用于提示框

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run_task(self):
        # 注册当前线程的 print 捕获流
        stream = Stream(self.log_signal)
        _router.register_worker(stream)

        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(f"{self.func.__name__}出错了: {str(e)}")
        finally:
            _router.unregister_worker()


if __name__ == "__main__":
    pass
