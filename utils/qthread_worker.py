import sys
from io import StringIO
import threading
from PyQt5.QtCore import pyqtSignal, QObject, QTimer


# ---------------------- 自定义输出流：实时捕获print ----------------------
class ThreadLocalStreamRouter:
    """
    一个全局的路由器，用来替代 sys.stdout。
    它会根据当前线程，把 print 内容分发到不同的地方。
    """
    def __init__(self, default_stdout):
        self._local = threading.local()  # 线程局部存储
        self._default_stdout = default_stdout  # 保存原始的 stdout（用于控制台输出）

    def register_worker(self, stream):
        """在线程中调用：注册当前线程的输出流"""
        self._local.stream = stream

    def unregister_worker(self):
        """在线程中调用：注销当前线程的输出流"""
        if hasattr(self._local, 'stream'):
            del self._local.stream

    def write(self, text):
        """核心分发逻辑"""
        # 如果当前线程注册了自定义 stream，就写进去
        if hasattr(self._local, 'stream'):
            self._local.stream.write(text)
        else:
            # 否则写回默认的控制台（或者不做任何事）
            self._default_stdout.write(text)

    def flush(self):
        """必须实现 flush，否则有些缓冲内容不会及时显示"""
        if hasattr(self._local, 'stream'):
            self._local.stream.flush()
        else:
            self._default_stdout.flush()

# 在程序启动时，把 sys.stdout 替换成重定向路由器
# 注意：一定要保存原始的 sys.stdout
_router = ThreadLocalStreamRouter(sys.stdout)
sys.stdout = _router

class Stream(StringIO):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal  # 绑定传递信息的信号

    def write(self, text):
        """重写write方法，每次print都会调用该方法"""
        super().write(text)
        # 过滤空行（避免print()空输出），并发送非空内容
        if text.strip():
            self.signal.emit(text.strip())

class OneClickWorker(QObject):
    finished = pyqtSignal(object)  # 用于传递结果
    log_signal = pyqtSignal(str)   # 用于传递打印信息
    echo_signal = pyqtSignal(str)  # 命令回显专用信号，可传递给func
    info_signal = pyqtSignal(object)  # 用于提示框

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func  # 保存旧函数的引用
        self.args = args  # 保存旧函数的参数
        self.kwargs = kwargs
        # self.timer = QTimer(self)

    def run_task(self):
        # 创建当前线程专属的 Stream
        stream = Stream(self.log_signal)

        # 将这个 stream 注册到全局路由器
        # 告诉路由器：“当前线程的 print 归我管”
        _router.register_worker(stream)

        try:
            # 在这里调用你的旧函数
            result = self.func(*self.args, **self.kwargs)
            # 发送结果
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(f"{self.func.__name__}出错了: {str(e)}")
        finally:
            # 注销当前线程
            # 告诉路由器：“当前线程结束了，还给默认控制台吧”
            _router.unregister_worker()

if __name__ == "__main__":
    pass
