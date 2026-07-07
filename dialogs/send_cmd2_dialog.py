from .base_dialog import SendCMDDialog


class SendCMD2Dialog(SendCMDDialog):
    """继承SendCMDDialog，仅需要修改窗口的标题"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加<发送命令并接收回显>配置")
