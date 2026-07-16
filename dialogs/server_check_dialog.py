
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QDialog, QTableWidgetItem, QComboBox, 
                             QCheckBox, QSpinBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QDialogButtonBox, QMessageBox, QAbstractItemView, QHeaderView)
from UI import server_check_dlg
from dialogs import sc_class2str


class ServerSelectDialog(QDialog):
    """服务器选择对话框"""
    def __init__(self, servers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择服务器")
        self.resize(300, 400)
        
        layout = QVBoxLayout()
        
        # 说明标签
        info_label = QLabel("可多选，按住Ctrl或Shift选择")
        layout.addWidget(info_label)
        
        # 服务器列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for server in servers:
            self.list_widget.addItem(server['服务器名称'])
        layout.addWidget(self.list_widget)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def get_selected_servers(self):
        """获取选中的服务器列表"""
        selected_items = self.list_widget.selectedItems()
        return [item.text() for item in selected_items]


class ServerCheckDialog(QDialog, server_check_dlg.Ui_Dialog):
    """服务器检查配置对话框"""

    DEFAULT_CHECK_ITEMS = ["连通", "SSH登录", "Root SSH权限", "系统时间", "防火墙", "命令回显1"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.parent = parent

        self.sc_cfg = {}
        self._loading = False
        
        # 设置默认按钮名称
        self.sc_name_lineEdit.setText("服务器检查：")
        
        # 连接按钮
        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        self.add_server_pushButton.clicked.connect(self.show_add_server_dialog)
        self.add_row_pushButton.clicked.connect(self.add_command_echo_row)
        self.del_selected_pushButton.clicked.connect(self.delete_selected)

        # 初始化表格
        self.init_table()

    def init_table(self):
        """初始化表格"""
        # 设置行和列
        self.tableWidget.setRowCount(len(self.DEFAULT_CHECK_ITEMS))
        self.tableWidget.setColumnCount(0)  # 初始0列
        
        # 设置垂直表头（检查项）
        self.tableWidget.setVerticalHeaderLabels(self.DEFAULT_CHECK_ITEMS)
        
        # 设置选择模式 - 允许选择多行多列
        self.tableWidget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectItems)
        
        # 设置表格属性
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.horizontalHeader().setCascadingSectionResizes(False)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tableWidget.verticalHeader().setCascadingSectionResizes(False)
        
        # 设置表格行高自动适应内容
        self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # 设置表格显示内部网格线
        self.tableWidget.setShowGrid(True)
        self.tableWidget.setAlternatingRowColors(True)
        
        # 设置表格样式，更美观
        self.tableWidget.setStyleSheet("""
            QTableWidget {
                border: 2px solid #cccccc;
                gridline-color: #e0e0e0;
                background-color: white;
                selection-background-color: #cce5ff;
                selection-color: #000000;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #cce5ff;
            }
            QHeaderView::section {
                background-color: #6c757d;
                color: white;
                padding: 8px;
                border: 1px solid #5a6268;
                font-weight: bold;
            }
            QHeaderView::section:checked {
                background-color: #5a6268;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #6c757d;
                border: 1px solid #5a6268;
            }
        """)
        
        # 设置表头点击选中整列/整行
        self.tableWidget.horizontalHeader().setSectionsClickable(True)
        self.tableWidget.horizontalHeader().setHighlightSections(True)
        self.tableWidget.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.tableWidget.verticalHeader().setSectionsClickable(True)
        self.tableWidget.verticalHeader().setHighlightSections(True)
        self.tableWidget.verticalHeader().sectionClicked.connect(self.on_header_clicked)

    def on_header_clicked(self, index):
        """表头点击事件处理"""
        # 点击水平表头选中整列
        sender = self.sender()
        if sender == self.tableWidget.horizontalHeader():
            self.tableWidget.clearSelection()
            self.tableWidget.selectColumn(index)
        # 点击垂直表头选中整行
        elif sender == self.tableWidget.verticalHeader():
            self.tableWidget.clearSelection()
            self.tableWidget.selectRow(index)

    def show_add_server_dialog(self):
        """显示添加服务器对话框"""
        if not self.parent or not self.parent.servers_cfg:
            QMessageBox.warning(self, "提示", "请先添加服务器配置")
            return
        
        # 获取当前表格中已经有的服务器
        existing_servers = set()
        for col in range(self.tableWidget.columnCount()):
            header_item = self.tableWidget.horizontalHeaderItem(col)
            if header_item:
                existing_servers.add(header_item.text())
        
        # 过滤掉已经存在的服务器
        available_servers = []
        for server in self.parent.servers_cfg:
            if server['服务器名称'] not in existing_servers:
                available_servers.append(server)
        
        if not available_servers:
            QMessageBox.warning(self, "提示", "没有可用的服务器可添加")
            return
        
        dialog = ServerSelectDialog(available_servers, self)
        if dialog.exec_() == QDialog.DialogCode.Accepted:
            selected_servers = dialog.get_selected_servers()
            for server_name in selected_servers:
                self.add_server_column(server_name)

    def add_server_column(self, server_name):
        """添加服务器列"""
        col_count = self.tableWidget.columnCount()
        self.tableWidget.insertColumn(col_count)
        
        # 设置表格列头
        self.tableWidget.setHorizontalHeaderItem(col_count, QTableWidgetItem(server_name))
        
        # 为新列的每一行添加控件
        for row in range(self.tableWidget.rowCount()):
            self.create_check_widget(row, col_count)

    def create_check_widget(self, row, col):
        """为指定单元格创建检查控件"""
        item_name = self.tableWidget.verticalHeaderItem(row).text()
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 检查复选框
        check_box = QCheckBox("检查")
        check_box.setChecked(True)
        layout.addWidget(check_box)

        # 根据检查项添加对应的控件
        if item_name in ["连通", "SSH登录", "Root SSH权限", "防火墙"]:
            combo = QComboBox()
            combo.addItem("是")
            combo.addItem("否")
            combo.setCurrentIndex(0)
            layout.addWidget(combo)
        elif item_name == "系统时间":
            hlayout = QHBoxLayout()
            hlayout.setSpacing(4)
            hlayout.addWidget(QLabel("误差±"))
            spin = QSpinBox()
            spin.setMinimum(1)
            spin.setMaximum(60)
            spin.setValue(5)
            hlayout.addWidget(spin)
            hlayout.addWidget(QLabel("分钟"))
            hlayout.addStretch()
            layout.addLayout(hlayout)
            
            sync_check = QCheckBox("自动同步时间")
            sync_check.setChecked(False)
            layout.addWidget(sync_check)
        elif item_name.startswith("命令回显"):
            # 输入命令
            cmd_line = QLineEdit()
            cmd_line.setPlaceholderText("输入命令")
            layout.addWidget(cmd_line)
            # 期望类型
            type_combo = QComboBox()
            type_combo.addItem("包含")
            type_combo.addItem("不包含")
            layout.addWidget(type_combo)
            # 期望内容
            content_line = QLineEdit()
            content_line.setPlaceholderText("期望内容")
            layout.addWidget(content_line)

        widget.setLayout(layout)
        self.tableWidget.setCellWidget(row, col, widget)

    def add_command_echo_row(self):
        """添加命令回显行"""
        # 找到最小的可用命令回显序号
        used_numbers = set()
        for row in range(self.tableWidget.rowCount()):
            item_name = self.tableWidget.verticalHeaderItem(row).text()
            if item_name.startswith("命令回显"):
                try:
                    num = int(item_name.replace("命令回显", ""))
                    used_numbers.add(num)
                except ValueError:
                    pass
        
        # 找到最小的可用数字
        new_row_num = 1
        while new_row_num in used_numbers:
            new_row_num += 1
        
        # 添加新行
        row_idx = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_idx)
        self.tableWidget.setVerticalHeaderItem(row_idx, QTableWidgetItem(f"命令回显{new_row_num}"))
        
        # 为新行的每一列添加控件
        for col in range(self.tableWidget.columnCount()):
            self.create_check_widget(row_idx, col)

    def delete_selected(self):
        """删除选中的行或列"""
        selected_indexes = self.tableWidget.selectedIndexes()
        
        if not selected_indexes:
            QMessageBox.warning(self, "提示", "请通过点击表头选中完整的一行或者一列")
            return
        
        # 收集选中的行和列
        selected_rows = set()
        selected_columns = set()
        
        for index in selected_indexes:
            selected_rows.add(index.row())
            selected_columns.add(index.column())
        
        # 检查是否是完整的整行选择（所有列的这一行都被选中）
        is_full_row_selection = len(selected_rows) == 1 and len(selected_indexes) == self.tableWidget.columnCount()
        # 检查是否是完整的整列选择（所有行的这一列都被选中）
        is_full_col_selection = len(selected_columns) == 1 and len(selected_indexes) == self.tableWidget.rowCount()
        
        if not is_full_row_selection and not is_full_col_selection:
            QMessageBox.warning(self, "提示", "请通过点击表头选中完整的一行或者一列")
            return
        
        if is_full_col_selection:
            # 删除列
            col = next(iter(selected_columns))
            self.tableWidget.removeColumn(col)
        elif is_full_row_selection:
            # 删除行
            row = next(iter(selected_rows))
            # 前5行不可删除
            if row < 5:
                QMessageBox.warning(self, "提示", "前5行不可删除")
                return
            
            self.tableWidget.removeRow(row)

    def create_sc(self):
        """创建快捷按钮"""
        if not self.sc_name_lineEdit.text().strip():
            self.sc_name_lineEdit.setStyleSheet("QLineEdit { border: 2px solid red; }")
            return
        
        if self.tableWidget.columnCount() == 0:
            QMessageBox.warning(self, "提示", "请至少添加一个服务器列")
            return

        # 构建配置数据
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()
        
        # 收集服务器检查配置
        server_configs = {}
        for col in range(self.tableWidget.columnCount()):
            server_name = self.tableWidget.horizontalHeaderItem(col).text()
            server_configs[server_name] = {}
            
            for row in range(self.tableWidget.rowCount()):
                check_item = self.tableWidget.verticalHeaderItem(row).text()
                widget = self.tableWidget.cellWidget(row, col)
                if widget:
                    # 获取控件中的值
                    config = self.get_widget_config(widget, check_item)
                    server_configs[server_name][check_item] = config
        
        self.sc_cfg['服务器检查配置'] = server_configs

        if self.parent:
            if hasattr(self, 'button_id'):
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        self.accept()
    
    def get_widget_config(self, widget, check_item):
        """从控件中获取配置"""
        config = {}
        
        # 获取复选框状态
        check_box = widget.findChild(QCheckBox)
        if check_box:
            config['检查'] = check_box.isChecked()
        
        # 根据检查项类型获取其他控件的值
        if check_item in ["连通", "SSH登录", "Root SSH权限", "防火墙"]:
            combo = widget.findChild(QComboBox)
            if combo:
                config['期望结果'] = combo.currentText()
        elif check_item == "系统时间":
            spin = widget.findChild(QSpinBox)
            if spin:
                config['允许误差'] = spin.value()
            check_boxes = widget.findChildren(QCheckBox)
            for cb in check_boxes:
                if cb.text() == "自动同步时间":
                    config['自动同步'] = cb.isChecked()
                    break
        elif check_item.startswith("命令回显"):
            line_edits = widget.findChildren(QLineEdit)
            combo = widget.findChild(QComboBox)
            if len(line_edits) >= 2:
                config['命令'] = line_edits[0].text()
                config['期望内容'] = line_edits[1].text()
            if combo:
                config['期望类型'] = combo.currentText()
        
        return config

    def reset(self):
        """重置"""
        self.sc_name_lineEdit.clear()
        self.sc_name_lineEdit.setText("服务器检查：")
        # 不要用clear()，会清除表头
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(0)
        self.sc_cfg = {}
        self.init_table()
    
    def edit_sc(self, button_id):
        """编辑模式"""
        self.button_id = button_id
        if button_id in self.parent.sc_buttons:
            config = self.parent.sc_buttons[button_id]['config']
            
            # 重置表格
            self.reset()
            
            # 填入按钮名称
            self.sc_name_lineEdit.setText(config.get('指令名称', ''))
            
            # 加载服务器检查配置
            if '服务器检查配置' in config:
                server_configs = config['服务器检查配置']
                
                # 1. 先收集所有需要的检查项 - 只从配置里收集，不要强制加默认项
                all_check_items = set()
                for checks in server_configs.values():
                    all_check_items.update(checks.keys())
                
                # 2. 先把默认的非命令回显项加进去（如果配置里有的话）
                default_core_items = [item for item in self.DEFAULT_CHECK_ITEMS 
                                     if item in all_check_items and not item.startswith("命令回显")]
                
                # 3. 如果配置里没有任何核心检查项，就加默认的
                if not default_core_items:
                    default_core_items = [item for item in self.DEFAULT_CHECK_ITEMS 
                                         if not item.startswith("命令回显")]
                
                # 4. 收集命令回显项
                command_items = sorted([item for item in all_check_items if item.startswith("命令回显")], 
                                      key=lambda x: int(x.replace("命令回显", "")))
                
                final_check_items = default_core_items + command_items
                
                # 5. 如果最终没有检查项（不太可能），就用默认的
                if not final_check_items:
                    final_check_items = self.DEFAULT_CHECK_ITEMS
                
                # 6. 重建表格行
                self.tableWidget.setRowCount(len(final_check_items))
                self.tableWidget.setVerticalHeaderLabels(final_check_items)
                
                # 7. 添加服务器列并填充数据
                for server_name, checks in server_configs.items():
                    self.add_server_column(server_name)
                    
                    # 填充数据
                    for row in range(self.tableWidget.rowCount()):
                        check_item = self.tableWidget.verticalHeaderItem(row).text()
                        if check_item in checks:
                            col = self.tableWidget.columnCount() - 1
                            widget = self.tableWidget.cellWidget(row, col)
                            if widget:
                                self.set_widget_config(widget, checks[check_item])
    
    def set_widget_config(self, widget, config):
        """设置控件配置"""
        # 设置复选框
        check_box = widget.findChild(QCheckBox)
        if check_box and '检查' in config:
            check_box.setChecked(config['检查'])
        
        # 设置其他控件
        if '期望结果' in config:
            combo = widget.findChild(QComboBox)
            if combo:
                index = combo.findText(config['期望结果'])
                if index >= 0:
                    combo.setCurrentIndex(index)
        if '允许误差' in config:
            spin = widget.findChild(QSpinBox)
            if spin:
                spin.setValue(config['允许误差'])
        if '自动同步' in config:
            check_boxes = widget.findChildren(QCheckBox)
            for cb in check_boxes:
                if cb.text() == "自动同步时间":
                    cb.setChecked(config['自动同步'])
                    break
        if '命令' in config or '期望内容' in config or '期望类型' in config:
            line_edits = widget.findChildren(QLineEdit)
            combo = widget.findChild(QComboBox)
            if len(line_edits) >= 2:
                if '命令' in config:
                    line_edits[0].setText(config['命令'])
                if '期望内容' in config:
                    line_edits[1].setText(config['期望内容'])
            if combo and '期望类型' in config:
                index = combo.findText(config['期望类型'])
                if index >= 0:
                    combo.setCurrentIndex(index)

