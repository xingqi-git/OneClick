from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QMessageBox, QHeaderView, QAbstractItemView, QTableWidgetItem
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
        self.del_pushButton.clicked.connect(self.del_item)
        self.clear_pushButton.clicked.connect(self.clear_table)
        self.save_pushButton.clicked.connect(self.save_table)
        self.close_pushButton.clicked.connect(self.close)

    def add_item(self):
        row_count = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_count)

    def del_item(self):
        # 获取所有选中的行索引（去重并倒序，避免删除时索引错乱）
        selected_rows = sorted(set(index.row() for index in self.tableWidget.selectedIndexes()), reverse=True)
        # 遍历删除选中行
        for row in selected_rows:
            self.tableWidget.removeRow(row)

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

    def save_table(self):
        # 获取表格总行数
        row_count = self.tableWidget.rowCount()
        # 获取表格总列数
        col_count = self.tableWidget.columnCount()

        self.parent.servers_cfg.clear()
        # 遍历每行获取数据
        for row in range(row_count):
            row_data = {}
            for col in range(col_count):
                item = self.tableWidget.item(row, col)
                if item:
                    row_data[self.tableWidget.horizontalHeaderItem(col).text()] = item.text()
                else:
                    row_data[self.tableWidget.horizontalHeaderItem(col).text()] = ""
            self.parent.servers_cfg.append(row_data)
        self.parent.update_server_combobox()
        self.accept()
