from PyQt5 import QtCore
from PyQt5.QtWidgets import (
    QDialog, QMessageBox, QHeaderView, QAbstractItemView, QTableWidgetItem,
    QPushButton,
)
from UI import edit_servers_dlg


class SetServerDialog(QDialog, edit_servers_dlg.Ui_Dialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 设置表格行列数
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setRowCount(len(self.parent.servers_cfg))

        # 设置表格水平表头和垂直表头
        self.tableWidget.setHorizontalHeaderLabels(['服务器名称', 'IP', '端口', '用户名', '密码'])

        # 设置列宽
        self.tableWidget.setColumnWidth(0, 130)
        self.tableWidget.setColumnWidth(1, 130)
        self.tableWidget.setColumnWidth(2, 40)
        self.tableWidget.setColumnWidth(3, 100)
        self.tableWidget.setColumnWidth(4, 130)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        # 设置表格整行选中
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 设置内容
        i = 0
        for server in self.parent.servers_cfg:
            self.tableWidget.setItem(i, 0, QTableWidgetItem(server['服务器名称']))
            self.tableWidget.setItem(i, 1, QTableWidgetItem(server['IP']))
            self.tableWidget.setItem(i, 2, QTableWidgetItem(server['端口']))
            self.tableWidget.setItem(i, 3, QTableWidgetItem(server['用户名']))
            self.tableWidget.setItem(i, 4, QTableWidgetItem(server['密码']))
            i += 1

        # 关联按钮逻辑
        self.add_pushButton.clicked.connect(self.add_item)
        self.copy_pushButton.clicked.connect(self.copy_item)
        self.del_pushButton.clicked.connect(self.del_item)
        self.clear_pushButton.clicked.connect(self.clear_table)
        self.close_pushButton.clicked.connect(self.close)

        # 排序按钮：动态插入到"清空"与弹簧之间（不改 pyuic5 生成的 UI 文件）
        self.up_pushButton = QPushButton("上移", self)
        self.down_pushButton = QPushButton("下移", self)
        # 此时布局顺序：增加0 复制1 删除2 清空3 弹簧4 保存5 关闭6
        self.horizontalLayout.insertWidget(4, self.up_pushButton)
        self.horizontalLayout.insertWidget(5, self.down_pushButton)
        self.up_pushButton.clicked.connect(self.move_up)
        self.down_pushButton.clicked.connect(self.move_down)

        # 移除手动保存按钮（表格编辑改为自动落盘）
        self.save_pushButton.setParent(None)
        self.save_pushButton.deleteLater()

        # 自动落盘：表格编辑（单元格修改/增删/移动）经 600ms 防抖后
        # 同步到主窗口服务器列表并写配置文件；初始填充在连接信号之前，不会误触发
        self._auto_save_timer = QtCore.QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(600)
        self._auto_save_timer.timeout.connect(self._sync_to_parent)
        self.tableWidget.cellChanged.connect(self._schedule_auto_save)

    def _schedule_auto_save(self):
        """表格有编辑时调用：重置防抖定时器，600ms 无新编辑后自动落盘"""
        self._auto_save_timer.start()

    def _sync_to_parent(self):
        """把表格内容同步到主窗口服务器列表并落盘"""
        col_count = self.tableWidget.columnCount()
        self.parent.servers_cfg.clear()
        for row in range(self.tableWidget.rowCount()):
            row_data = {}
            for col in range(col_count):
                item = self.tableWidget.item(row, col)
                header = self.tableWidget.horizontalHeaderItem(col).text()
                row_data[header] = item.text() if item else ""
            self.parent.servers_cfg.append(row_data)
        self.parent.update_server_combobox()
        self.parent._save_config_auto()

    def closeEvent(self, event):
        # 关闭前冲刷防抖中未落盘的编辑
        if self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
            self._sync_to_parent()
        event.accept()

    def add_item(self):
        row_count = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_count)
        # 端口默认填入 22
        self.tableWidget.setItem(row_count, 2, QTableWidgetItem('22'))

    def copy_item(self):
        """复制选中的行到表最下面"""
        row_count = self.tableWidget.rowCount()
        # 表内没有内容，等同于添加
        if row_count == 0:
            self.add_item()
            return

        # 获取选中的行索引（去重并排序）
        selected_rows = sorted(set(index.row() for index in self.tableWidget.selectedIndexes()))
        # 没有选中任何行，复制最下面一行
        if not selected_rows:
            selected_rows = [row_count - 1]

        # 复制每一行到表最下面
        for src_row in selected_rows:
            new_row = self.tableWidget.rowCount()
            self.tableWidget.insertRow(new_row)
            for col in range(self.tableWidget.columnCount()):
                src_item = self.tableWidget.item(src_row, col)
                if src_item:
                    self.tableWidget.setItem(new_row, col, QTableWidgetItem(src_item.text()))

    def del_item(self):
        # 获取所有选中的行索引（去重并倒序，避免删除时索引错乱）
        selected_rows = sorted(set(index.row() for index in self.tableWidget.selectedIndexes()), reverse=True)
        # 遍历删除选中行
        for row in selected_rows:
            self.tableWidget.removeRow(row)
        self._schedule_auto_save()  # removeRow 不触发 cellChanged，手动调度

    def _current_row(self):
        """当前选中行：优先 currentRow，其次选中区域的首行；无选中返回 -1"""
        row = self.tableWidget.currentRow()
        if row >= 0:
            return row
        rows = sorted(set(i.row() for i in self.tableWidget.selectedIndexes()))
        return rows[0] if rows else -1

    def _swap_rows(self, r1, r2):
        """整行交换所有单元格内容"""
        for col in range(self.tableWidget.columnCount()):
            item1 = self.tableWidget.takeItem(r1, col)
            item2 = self.tableWidget.takeItem(r2, col)
            if item2 is not None:
                self.tableWidget.setItem(r1, col, item2)
            if item1 is not None:
                self.tableWidget.setItem(r2, col, item1)

    def move_up(self):
        row = self._current_row()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)
        self.tableWidget.selectRow(row - 1)

    def move_down(self):
        row = self._current_row()
        if row < 0 or row >= self.tableWidget.rowCount() - 1:
            return
        self._swap_rows(row, row + 1)
        self.tableWidget.selectRow(row + 1)

    def clear_table(self):
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Icon.Question)
        confirm_dialog.setWindowTitle("确认")
        confirm_dialog.setText("是否要清空列表")
        confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = confirm_dialog.exec_()
        if result == QMessageBox.StandardButton.Yes:
            self.tableWidget.setRowCount(0)
            self._schedule_auto_save()  # removeRow 不触发 cellChanged，手动调度
