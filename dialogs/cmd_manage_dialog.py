"""指令管理对话框
"""
from PyQt5 import QtWidgets, QtCore


class CmdManageDialog(QtWidgets.QDialog):
    """指令管理对话框：添加、编辑、删除、插入到终端
    每条指令包含名称和内容两部分，表格中显示名称和内容第一行。
    """

    insert_cmd_signal = QtCore.pyqtSignal(str)  # 插入命令内容到终端

    COL_NAME = 0
    COL_CONTENT = 1

    def __init__(self, commands=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("指令管理")
        self.resize(700, 500)

        # 左侧：指令表格（两列：名称、内容预览）
        self.cmd_table = QtWidgets.QTableWidget(0, 2)
        self.cmd_table.setHorizontalHeaderLabels(["名称", "内容"])
        self.cmd_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.cmd_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.cmd_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.cmd_table.verticalHeader().setVisible(False)
        self.cmd_table.horizontalHeader().setStretchLastSection(True)
        self.cmd_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Interactive
        )
        self.cmd_table.setColumnWidth(0, 180)
        self.cmd_table.setObjectName("cmd_table")

        # 右侧按钮
        self.add_button = QtWidgets.QPushButton("添加")
        self.edit_button = QtWidgets.QPushButton("编辑")
        self.del_button = QtWidgets.QPushButton("删除")
        self.insert_button = QtWidgets.QPushButton("插入到终端")
        self.insert_button.setDefault(True)

        btn_layout = QtWidgets.QVBoxLayout()
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.edit_button)
        btn_layout.addWidget(self.del_button)
        btn_layout.addStretch()
        btn_layout.addWidget(self.insert_button)

        # 主布局
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(self.cmd_table, 1)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        # 加载初始指令（支持老格式字符串和新格式 dict）
        if commands:
            for cmd in commands:
                self._add_cmd_to_table(cmd)

        # 信号
        self.add_button.clicked.connect(self._on_add)
        self.edit_button.clicked.connect(self._on_edit)
        self.del_button.clicked.connect(self._on_delete)
        self.insert_button.clicked.connect(self._on_insert)
        self.cmd_table.cellDoubleClicked.connect(self._on_insert)

    def _add_cmd_to_table(self, cmd):
        """把一条指令加到表格里。cmd 可以是 str（旧格式）或 dict（新格式）"""
        if isinstance(cmd, dict):
            name = cmd.get('name', '')
            content = cmd.get('content', '')
        else:
            # 旧格式：纯字符串
            content = str(cmd)
            name = self._make_default_name(content)

        row = self.cmd_table.rowCount()
        self.cmd_table.insertRow(row)

        name_item = QtWidgets.QTableWidgetItem(name)
        # 完整内容存在名称列的 UserRole
        name_item.setData(QtCore.Qt.ItemDataRole.UserRole, content)
        name_item.setToolTip(content)
        self.cmd_table.setItem(row, self.COL_NAME, name_item)

        # 内容列：显示第一行预览
        first_line = self._content_preview(content)
        content_item = QtWidgets.QTableWidgetItem(first_line)
        content_item.setToolTip(content)
        self.cmd_table.setItem(row, self.COL_CONTENT, content_item)

    @staticmethod
    def _content_preview(content):
        """内容预览：取第一行，过长截断"""
        if not content:
            return ''
        first_line = content.splitlines()[0].strip()
        if not first_line:
            first_line = content.strip()[:60]
        if len(first_line) > 80:
            first_line = first_line[:80] + '...'
        return first_line

    @staticmethod
    def _make_default_name(content):
        """从命令内容生成默认名称（取第一行，过长截断）"""
        if not content:
            return '(空)'
        first_line = content.splitlines()[0].strip()
        if not first_line:
            first_line = content.strip()[:20]
        if len(first_line) > 40:
            first_line = first_line[:40] + '...'
        return first_line

    def _current_row(self):
        """获取当前选中的行号（单行操作时用）"""
        items = self.cmd_table.selectedItems()
        if not items:
            return -1
        return items[0].row()

    def _selected_rows(self):
        """获取所有选中的行号（去重、升序）"""
        rows = set()
        for item in self.cmd_table.selectedItems():
            rows.add(item.row())
        return sorted(rows, reverse=True)  # 倒序，方便从下往上删

    def _get_row_content(self, row):
        """获取某一行的完整内容"""
        item = self.cmd_table.item(row, self.COL_NAME)
        if not item:
            return ''
        return item.data(QtCore.Qt.ItemDataRole.UserRole) or ''

    def _on_add(self):
        """添加指令"""
        dlg = _CmdEditDialog(parent=self)
        if dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            name, content = dlg.get_result()
            if not content.strip():
                return
            if not name.strip():
                name = self._make_default_name(content)
            self._add_cmd_to_table({'name': name, 'content': content})

    def _on_edit(self):
        """编辑选中的指令"""
        row = self._current_row()
        if row < 0:
            return
        old_name = self.cmd_table.item(row, self.COL_NAME).text()
        old_content = self._get_row_content(row)
        dlg = _CmdEditDialog(name=old_name, content=old_content, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            name, content = dlg.get_result()
            if not content.strip():
                return
            if not name.strip():
                name = self._make_default_name(content)
            # 更新名称列
            name_item = self.cmd_table.item(row, self.COL_NAME)
            name_item.setText(name)
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, content)
            name_item.setToolTip(content)
            # 更新内容列
            content_item = self.cmd_table.item(row, self.COL_CONTENT)
            content_item.setText(self._content_preview(content))
            content_item.setToolTip(content)

    def _on_delete(self):
        """删除选中的指令"""
        rows = self._selected_rows()
        if not rows:
            return
        count = len(rows)
        reply = QtWidgets.QMessageBox.question(
            self, "确认", f"确定要删除选中的 {count} 条指令吗？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            for row in rows:
                self.cmd_table.removeRow(row)

    def _on_insert(self, *args):
        """插入到终端（发送信号然后关闭）"""
        row = self._current_row()
        if row < 0:
            return
        content = self._get_row_content(row)
        if content:
            self.insert_cmd_signal.emit(content)
            self.accept()

    def get_all_commands(self):
        """获取所有指令（新格式：[{name, content}, ...]）"""
        result = []
        for i in range(self.cmd_table.rowCount()):
            name = self.cmd_table.item(i, self.COL_NAME).text()
            content = self._get_row_content(i)
            result.append({'name': name, 'content': content})
        return result


class _CmdEditDialog(QtWidgets.QDialog):
    """添加/编辑指令的子对话框：名称 + 内容"""

    def __init__(self, name='', content='', parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑指令" if name else "添加指令")
        self.resize(500, 400)

        # 名称
        name_label = QtWidgets.QLabel("名称：")
        self.name_edit = QtWidgets.QLineEdit(name)
        self.name_edit.setPlaceholderText("留空则自动用命令内容生成")

        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit, 1)

        # 内容
        content_label = QtWidgets.QLabel("指令内容：")
        self.content_edit = QtWidgets.QPlainTextEdit(content)
        self.content_edit.setPlaceholderText("输入要执行的命令，可以是多行")

        # 按钮
        self.ok_button = QtWidgets.QPushButton("确定")
        self.cancel_button = QtWidgets.QPushButton("取消")
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_button)
        btn_layout.addWidget(self.cancel_button)

        # 主布局
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(name_layout)
        main_layout.addWidget(content_label)
        main_layout.addWidget(self.content_edit, 1)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def get_result(self):
        """返回 (name, content)"""
        return self.name_edit.text().strip(), self.content_edit.toPlainText()
