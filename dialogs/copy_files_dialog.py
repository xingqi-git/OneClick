from PyQt5 import QtCore
from PyQt5.QtWidgets import (QDialog, QFileDialog, QDialogButtonBox, QSizePolicy,
                             QListWidget, QListWidgetItem, QHBoxLayout, QPushButton,
                             QVBoxLayout, QWidget, QLabel, QLineEdit, QButtonGroup,
                             QRadioButton)
from UI import copy_local_files_dlg
from .base_dialog import sc_class2str


class CopyFilesDialog(QDialog, copy_local_files_dlg.Ui_Dialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 保存对话框的所有配置项
        self.sc_cfg = {}
        self._loading = False

        # 源路径列表数据
        self.source_items = []
        self._ignore_filter_change = False

        # 改造UI
        self._rebuild_source_and_target()
        self._rebuild_filter_frame()

        # 快捷按钮名称标签加粗
        font_bold = self.label_11.font()
        font_bold.setBold(True)
        self.label_11.setFont(font_bold)

        self.target_path_pushButton.clicked.connect(self.select_target_path)
        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)

        self.time_dic = {}
        for index in range(self.time_comboBox.count()):
            text = self.time_comboBox.itemText(index)
            self.time_dic[text] = index

        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：')

        # 筛选条件变化 → 同步到当前选中条目
        self.time_comboBox.currentIndexChanged.connect(self._on_filter_changed)
        self.include_lineEdit.textChanged.connect(self._on_filter_changed)
        self.exclude_lineEdit.textChanged.connect(self._on_filter_changed)
        self.include_logic_group.buttonClicked.connect(self._on_filter_changed)
        self.exclude_logic_group.buttonClicked.connect(self._on_filter_changed)

        # 默认列表为空
        self.source_list.setCurrentRow(-1)

    def _rebuild_source_and_target(self):
        """
        重建源路径/目的路径区域：
        - 源路径从一行按钮改成列表 + 添加/删除
        - 目的路径保留按钮
        - 都放到 gridLayout_2 中
        """
        # 移除原来的源路径行
        self.gridLayout_2.removeWidget(self.label_7)
        self.gridLayout_2.removeWidget(self.source_path_pushButton)
        self.label_7.setParent(None)
        self.label_7.deleteLater()
        self.source_path_pushButton.setParent(None)
        self.source_path_pushButton.deleteLater()

        # 源路径标题加粗
        self.source_title_label = QLabel("源路径")
        font = self.source_title_label.font()
        font.setBold(True)
        self.source_title_label.setFont(font)

        # 源路径列表
        self.source_list = QListWidget()
        self.source_list.setObjectName("source_list")
        self.source_list.setMinimumHeight(80)
        self.source_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 添加/删除按钮
        self.add_source_btn = QPushButton("添加")
        self.del_source_btn = QPushButton("删除")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_source_btn)
        btn_layout.addWidget(self.del_source_btn)
        btn_layout.addStretch()

        # 源路径整体容器
        source_container = QWidget()
        vbox = QVBoxLayout(source_container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(self.source_title_label)
        vbox.addWidget(self.source_list)
        vbox.addLayout(btn_layout)

        # 源路径放到 gridLayout_2 第0行，跨2列
        self.gridLayout_2.addWidget(source_container, 0, 0, 1, 2)

        # 把目的路径从 gridLayout_2 中拿出来，后面放到筛选条件下面
        self.gridLayout_2.removeWidget(self.label_10)
        self.gridLayout_2.removeWidget(self.target_path_pushButton)

        # 目的路径标签加粗
        font_bold = self.label_10.font()
        font_bold.setBold(True)
        self.label_10.setFont(font_bold)

        # 连接信号
        self.add_source_btn.clicked.connect(self._on_add_source)
        self.del_source_btn.clicked.connect(self._on_del_source)
        self.source_list.currentRowChanged.connect(self._on_source_selected)
        self.source_list.itemDoubleClicked.connect(self._on_source_double_clicked)

    def _rebuild_filter_frame(self):
        """重建筛选条件 frame：修改时间 + 名称包含 + 名称不包含"""
        # 筛选条件标题加粗，放到第0行跨2列
        font = self.label_13.font()
        font.setBold(True)
        self.label_13.setFont(font)
        self.gridLayout.removeWidget(self.label_13)
        self.gridLayout.addWidget(self.label_13, 0, 0, 1, 2)

        # 修改时间行（label_8 在第1行第0列，time_comboBox 移到第1行第1列）
        self.gridLayout.removeWidget(self.label_8)
        self.gridLayout.removeWidget(self.time_comboBox)
        self.gridLayout.addWidget(self.label_8, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.time_comboBox, 1, 1, 1, 1)

        # 移除原来的名称包含相关控件
        self.gridLayout.removeWidget(self.label_9)
        self.gridLayout.removeWidget(self.filename_lineEdit)
        self.label_9.setParent(None)
        self.label_9.deleteLater()
        self.filename_lineEdit.setParent(None)
        self.filename_lineEdit.deleteLater()

        # ---- 名称包含行 ----
        self.label_include = QLabel("名称包含")
        self.include_lineEdit = QLineEdit()
        self.include_lineEdit.setPlaceholderText("多个关键词用 / 分隔")

        self.include_radio_and = QRadioButton("和")
        self.include_radio_or = QRadioButton("或")
        self.include_radio_or.setChecked(True)
        self.include_logic_group = QButtonGroup(self)
        self.include_logic_group.addButton(self.include_radio_and)
        self.include_logic_group.addButton(self.include_radio_or)

        include_row_widget = QWidget()
        include_row_layout = QHBoxLayout(include_row_widget)
        include_row_layout.setContentsMargins(0, 0, 0, 0)
        include_row_layout.setSpacing(8)
        include_row_layout.addWidget(self.include_lineEdit, 1)
        include_logic_label = QLabel("逻辑：")
        include_row_layout.addWidget(include_logic_label)
        include_row_layout.addWidget(self.include_radio_and)
        include_row_layout.addWidget(self.include_radio_or)

        self.gridLayout.addWidget(self.label_include, 2, 0, 1, 1)
        self.gridLayout.addWidget(include_row_widget, 2, 1, 1, 1)

        # ---- 名称不包含行 ----
        self.label_exclude = QLabel("名称不包含")
        self.exclude_lineEdit = QLineEdit()
        self.exclude_lineEdit.setPlaceholderText("多个关键词用 / 分隔")

        self.exclude_radio_and = QRadioButton("和")
        self.exclude_radio_or = QRadioButton("或")
        self.exclude_radio_and.setChecked(True)
        self.exclude_logic_group = QButtonGroup(self)
        self.exclude_logic_group.addButton(self.exclude_radio_and)
        self.exclude_logic_group.addButton(self.exclude_radio_or)

        exclude_row_widget = QWidget()
        exclude_row_layout = QHBoxLayout(exclude_row_widget)
        exclude_row_layout.setContentsMargins(0, 0, 0, 0)
        exclude_row_layout.setSpacing(8)
        exclude_row_layout.addWidget(self.exclude_lineEdit, 1)
        exclude_logic_label = QLabel("逻辑：")
        exclude_row_layout.addWidget(exclude_logic_label)
        exclude_row_layout.addWidget(self.exclude_radio_and)
        exclude_row_layout.addWidget(self.exclude_radio_or)

        self.gridLayout.addWidget(self.label_exclude, 3, 0, 1, 1)
        self.gridLayout.addWidget(exclude_row_widget, 3, 1, 1, 1)

        # 内边距与其他窗口保持一致
        self.gridLayout.setContentsMargins(8, 8, 8, 8)
        self.gridLayout.setVerticalSpacing(6)

        # frame 不垂直拉伸
        self.frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.frame.setMinimumHeight(0)

        # 目的路径放到筛选条件 frame 下面
        target_widget = QWidget()
        target_layout = QHBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(6)
        # 左侧标签（和其他label对齐，占一定宽度比例）
        self.label_10.setMinimumWidth(80)
        target_layout.addWidget(self.label_10)
        target_layout.addWidget(self.target_path_pushButton, 1)

        # 找到 frame 在 verticalLayout 中的位置，把目的路径插到 frame 下面
        frame_index = self.verticalLayout.indexOf(self.frame)
        self.verticalLayout.insertWidget(frame_index + 1, target_widget)

    def _refresh_filter_title(self, row):
        if row < 0:
            self.label_13.setText("源路径筛选条件")
        else:
            self.label_13.setText(f"第{row + 1}号源路径筛选条件")

    def _update_item_display(self, row):
        if row < 0 or row >= len(self.source_items):
            return
        item = self.source_list.item(row)
        path = self.source_items[row]['路径']
        display = f"{row + 1}. {path}" if path else f"{row + 1}. (未设置路径，请双击编辑)"
        item.setText(display)
        item.setToolTip(path)

    def _refresh_all_item_numbers(self):
        for i in range(len(self.source_items)):
            self._update_item_display(i)

    def _add_source_item(self, path, modify_time="全部", include=None, exclude=None):
        if include is None:
            include = {"关键词": [], "逻辑": "或"}
        if exclude is None:
            exclude = {"关键词": [], "逻辑": "和"}
        item_data = {
            '路径': path,
            '修改时间': modify_time,
            '名称包含': include,
            '名称不包含': exclude
        }
        self.source_items.append(item_data)
        item = QListWidgetItem("")
        self.source_list.addItem(item)
        row = len(self.source_items) - 1
        self._update_item_display(row)
        return row

    def _on_add_source(self):
        """添加按钮：选择本地文件/文件夹"""
        path = self._select_path_dialog()
        if path:
            row = self._add_source_item(path)
            self.source_list.setCurrentRow(row)

    def _on_del_source(self):
        row = self.source_list.currentRow()
        if row < 0:
            return
        if len(self.source_items) <= 1:
            return
        self.source_items.pop(row)
        self.source_list.takeItem(row)
        self._refresh_all_item_numbers()
        if row >= len(self.source_items):
            row = len(self.source_items) - 1
        self.source_list.setCurrentRow(row)

    def _on_source_selected(self, row):
        if row < 0 or row >= len(self.source_items):
            return
        self._ignore_filter_change = True
        item = self.source_items[row]
        if item['修改时间'] in self.time_dic:
            self.time_comboBox.setCurrentIndex(self.time_dic[item['修改时间']])
        else:
            self.time_comboBox.setCurrentIndex(0)

        inc = item.get('名称包含', {"关键词": [], "逻辑": "或"})
        self.include_lineEdit.setText("/".join(inc.get('关键词', [])) if isinstance(inc, dict) else (inc if inc else ""))
        if isinstance(inc, dict):
            if inc.get('逻辑') == '和':
                self.include_radio_and.setChecked(True)
            else:
                self.include_radio_or.setChecked(True)
        else:
            self.include_radio_or.setChecked(True)

        exc = item.get('名称不包含', {"关键词": [], "逻辑": "和"})
        self.exclude_lineEdit.setText("/".join(exc.get('关键词', [])) if isinstance(exc, dict) else "")
        if isinstance(exc, dict):
            if exc.get('逻辑') == '和':
                self.exclude_radio_and.setChecked(True)
            else:
                self.exclude_radio_or.setChecked(True)
        else:
            self.exclude_radio_and.setChecked(True)

        self._refresh_filter_title(row)
        self._ignore_filter_change = False

    def _on_filter_changed(self):
        if self._ignore_filter_change:
            return
        row = self.source_list.currentRow()
        if row < 0 or row >= len(self.source_items):
            return

        inc_text = self.include_lineEdit.text().strip()
        inc_keywords = [k.strip() for k in inc_text.split("/") if k.strip()]
        inc_logic = "和" if self.include_radio_and.isChecked() else "或"
        self.source_items[row]['名称包含'] = {"关键词": inc_keywords, "逻辑": inc_logic}

        exc_text = self.exclude_lineEdit.text().strip()
        exc_keywords = [k.strip() for k in exc_text.split("/") if k.strip()]
        exc_logic = "和" if self.exclude_radio_and.isChecked() else "或"
        self.source_items[row]['名称不包含'] = {"关键词": exc_keywords, "逻辑": exc_logic}

        self.source_items[row]['修改时间'] = self.time_comboBox.currentText()

    def _on_source_double_clicked(self, item):
        """双击条目：重新选择路径"""
        row = self.source_list.row(item)
        if row < 0:
            return
        path = self._select_path_dialog()
        if path:
            self.source_items[row]['路径'] = path
            self._update_item_display(row)

    def _select_path_dialog(self):
        """弹出文件/文件夹选择对话框，返回选择的路径或空字符串"""
        dialog = QFileDialog(self)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        button_box = dialog.findChild(QDialogButtonBox)
        if button_box:
            buttons = button_box.buttons()
            for button in buttons:
                role = button_box.buttonRole(button)
                if role == QDialogButtonBox.ButtonRole.RejectRole:
                    button.setText("选择当前文件夹路径")

        if dialog.exec_():
            file_paths = dialog.selectedFiles()
            if file_paths:
                return file_paths[0]
        else:
            current_dir = dialog.directory().absolutePath()
            return current_dir
        return ""

    def create_sc(self):
        # 每次点生成快捷方式按钮时，都先初始化所有输入框的样式
        self.source_list.setStyleSheet("")
        self.target_path_pushButton.setStyleSheet("")
        self.sc_name_lineEdit.setStyleSheet("")

        # 校验快捷按钮名称
        if not self.sc_name_lineEdit.text().strip():
            self.sc_name_lineEdit.setStyleSheet("QLineEdit { border: 2px solid red; }")
            return

        # 校验目的路径
        if not self.target_path_pushButton.text().strip() or self.target_path_pushButton.text() == '请选择':
            self.target_path_pushButton.setStyleSheet("QPushButton { border: 2px solid red; }")
            return

        # 校验源路径列表
        valid_items = [item for item in self.source_items if item['路径']]
        if not valid_items:
            self.source_list.setStyleSheet("QListWidget { border: 2px solid red; }")
            self.parent.update_run_info("请至少添加一个源路径", "WARNING")
            return

        # 保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['源路径列表'] = valid_items[:]
        self.sc_cfg['目的路径'] = self.target_path_pushButton.text()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()

        if self.parent:
            if hasattr(self, 'button_id'):
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        self.accept()

    def edit_sc(self, button_id):
        self.button_id = button_id
        self._loading = True
        sc_data = self.parent.sc_buttons[button_id]['config']

        # 目的路径
        if '目的路径' in sc_data:
            self.target_path_pushButton.setText(sc_data['目的路径'])
            self.target_path_pushButton.setToolTip(sc_data['目的路径'])
        elif '复制到' in sc_data:
            self.target_path_pushButton.setText(sc_data['复制到'])
            self.target_path_pushButton.setToolTip(sc_data['复制到'])
        self.target_path_pushButton.setToolTipDuration(10000)

        self.sc_name_lineEdit.setText(sc_data['指令名称'])

        # 回显源路径列表（兼容旧版配置）
        self.source_items = []
        self.source_list.clear()
        if '源路径列表' in sc_data:
            for item in sc_data['源路径列表']:
                include = item.get('名称包含', {"关键词": [], "逻辑": "或"})
                exclude = item.get('名称不包含', {"关键词": [], "逻辑": "和"})
                if '文件名包含' in item and isinstance(item['文件名包含'], str):
                    include = item['文件名包含']
                self._add_source_item(
                    item.get('路径', ''),
                    item.get('修改时间', '全部'),
                    include,
                    exclude
                )
        elif '源路径' in sc_data:
            # 兼容旧版单条配置
            modify_time = sc_data.get('修改时间', '全部')
            include = sc_data.get('文件名包含', '')
            self._add_source_item(sc_data['源路径'], modify_time, include)

        if self.source_list.count() > 0:
            self.source_list.setCurrentRow(0)

        self._loading = False

    def reset(self):
        self.source_items = []
        self.source_list.clear()
        self.target_path_pushButton.setText('当前路径/当前时间(例:20251024_031415)/')
        self.time_comboBox.setCurrentIndex(0)
        self.include_lineEdit.clear()
        self.exclude_lineEdit.clear()
        self.include_radio_or.setChecked(True)
        self.exclude_radio_and.setChecked(True)
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：')

    def select_source_path(self):
        """旧方法，保留以兼容（现在通过列表的添加按钮操作）"""
        pass

    def select_target_path(self):
        dialog = QFileDialog(self)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if dialog.exec_():
            file_paths = dialog.selectedFiles()
            if file_paths:
                self.target_path_pushButton.setText(file_paths[0])
                self.target_path_pushButton.setToolTip(file_paths[0])
                self.target_path_pushButton.setToolTipDuration(10000)
                return
