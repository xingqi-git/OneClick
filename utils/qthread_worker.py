from PyQt5.QtCore import pyqtSignal, QObject
from utils.logger import operation_context


class OneClickWorker(QObject):
    finished = pyqtSignal(object)  # 用于传递结果
    log_signal = pyqtSignal(str, str)  # 对话框等场景直接发射的UI日志 (消息, 级别)
    echo_signal = pyqtSignal(str)  # 命令回显专用信号
    info_signal = pyqtSignal(object)  # 用于提示框

    def __init__(self, func, *args, op_name='', op_id='', **kwargs):
        """
        Args:
            func: 工作函数
            op_name: 操作名（如"文件下载"），执行期间线程内所有日志自动此前缀显示到UI
            op_id: 本次执行的唯一ID（进度行更新去重用）
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.op_name = op_name
        self.op_id = op_id

    def run_task(self):
        # 设置当前线程的操作上下文：该线程内 logger 产生的日志会自动带上操作名/执行ID
        with operation_context(self.op_name, self.op_id):
            try:
                result = self.func(*self.args, **self.kwargs)
                self.finished.emit(result)
            except Exception as e:
                self.finished.emit(f"{self.func.__name__}出错了: {str(e)}")
