from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox


class HelpDialog(QDialog):
    """帮助文档对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.resize(900, 700)
        # 去掉窗口标题栏的问号按钮
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        from PyQt5.QtWidgets import QTextBrowser
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)

        # 直接使用嵌入的帮助文档内容
        from help_content import HELP_HTML
        self.text_browser.setHtml(HELP_HTML)

        layout.addWidget(self.text_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
