"""指令管理对话框
"""
from PyQt5 import QtWidgets, QtCore


class CmdManageDialog(QtWidgets.QDialog):
    """指令管理对话框：添加、编辑、删除、插入到终端"""

    insert_cmd_signal = QtCore.pyqtSignal(str)  # 插入命令到终端

    def __init__(self, commands=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("指令管理")
        self.resize(550, 500)

        # 指令列表
        self.cmd_list = QtWidgets.QListWidget()
        self.cmd_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.cmd_list.setObjectName("cmd_list")

        # 右侧按钮
        self.add_button = QtWidgets.QPushButton("添加")
        self.edit_button = QtWidgets.QPushButton("编辑")
        self.del_button = QtWidgets.QPushButton("删除")
        self.insert_button = QtWidgets.QPushButton("插入到终端")
        self.insert_button.setDefault(True)

        # 右侧按钮布局
        btn_layout = QtWidgets.QVBoxLayout()
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.edit_button)
        btn_layout.addWidget(self.del_button)
        btn_layout.addStretch()
        btn_layout.addWidget(self.insert_button)

        # 主布局
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(self.cmd_list, 1)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

        # 加载初始指令
        if commands:
            for cmd in commands:
                self.cmd_list.addItem(cmd)

        # 信号
        self.add_button.clicked.connect(self._on_add)
        self.edit_button.clicked.connect(self._on_edit)
        self.del_button.clicked.connect(self._on_delete)
        self.insert_button.clicked.connect(self._on_insert)
        self.cmd_list.itemDoubleClicked.connect(self._on_insert)
        self.cmd_list.itemDoubleClicked.connect(lambda _: self.accept())

    def _on_add(self):
        """添加指令"""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, "添加指令", "请输入指令内容：")
        if ok and text.strip():
            self.cmd_list.addItem(text.strip())

    def _on_edit(self):
        """编辑选中的指令"""
        current = self.cmd_list.currentItem()
        if not current:
            return
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, "编辑指令", "请修改指令内容：", current.text())
        if ok and text.strip():
            current.setText(text.strip())

    def _on_delete(self):
        """删除选中的指令"""
        items = self.cmd_list.selectedItems()
        if not items:
            return
        count = len(items)
        reply = QtWidgets.QMessageBox.question(
            self, "确认", f"确定要删除选中的 {count} 条指令吗？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            for item in items:
                self.cmd_list.takeItem(self.cmd_list.row(item))

    def _on_insert(self):
        """插入到终端（发送信号然后关闭）"""
        current = self.cmd_list.currentItem()
        if current:
            self.insert_cmd_signal.emit(current.text())
            self.accept()

    def get_all_commands(self):
        """获取所有指令（按列表顺序）"""
        result = []
        for i in range(self.cmd_list.count()):
            result.append(self.cmd_list.item(i).text())
        return result
