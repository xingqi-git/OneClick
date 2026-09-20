from PyQt5 import QtCore
from PyQt5.QtWidgets import (QDialog, QFileDialog, QListWidget,
                             QListWidgetItem, QHBoxLayout, QPushButton, QVBoxLayout,
                             QWidget, QSizePolicy, QLabel, QLineEdit, QButtonGroup,
                             QRadioButton, QInputDialog)
from UI import get_files_dlg
from .base_dialog import sc_class2str, wrap_server_info_in_frame


class GetFilesDialog(QDialog, get_files_dlg.Ui_Dialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 保存对话框的所有配置项
        self.sc_cfg = {}
        self._loading = False  # 编辑模式加载标志，防止 textChanged 覆盖名称

        # 将服务器信息行用边框包裹起来
        # 前6行：选择服务器、IP、端口、用户名、密码、临时文件路径
        wrap_server_info_in_frame(self, self.gridLayout, 6)

        # 筛选条件标题加粗
        font = self.label_12.font()
        font.setBold(True)
        self.label_12.setFont(font)

        # 目的路径和快捷按钮名称加粗
        font_bold = self.label_10.font()
        font_bold.setBold(True)
        self.label_10.setFont(font_bold)
        self.label_11.setFont(font_bold)

        # 源路径列表数据：[{路径, 修改时间, 名称包含, 名称不包含}, ...]
        self.source_items = []
        self._ignore_filter_change = False

        # 改造UI
        self._build_source_list_ui()
        self._rebuild_filter_frame()
        self._move_filter_frame_into_grid()

        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        for server in self.parent.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)
        self.server_comboBox.activated.connect(self.select_server)

        # IP输入框变化时，自动生成快捷按钮名称
        self.linux_ip_lineEdit.textChanged.connect(self._on_ip_changed)

        # 创建时间下拉菜单的选项字典
        self.time_dic = {}
        for index in range(self.time_comboBox.count()):
            text = self.time_comboBox.itemText(index)
            self.time_dic[text] = index

        # 文件暂存路径：用户名变化时自动联动更新
        self.username_lineEdit.textChanged.connect(self._on_username_changed)
        if self.username_lineEdit.text():
            self.work_dir_lineEdit.setText(f"/home/{self.username_lineEdit.text()}")

        # 筛选条件变化 → 同步到当前选中条目
        self.time_comboBox.currentIndexChanged.connect(self._on_filter_changed)
        self.include_lineEdit.textChanged.connect(self._on_filter_changed)
        self.exclude_lineEdit.textChanged.connect(self._on_filter_changed)
        self.include_logic_group.buttonClicked.connect(self._on_filter_changed)
        self.exclude_logic_group.buttonClicked.connect(self._on_filter_changed)

        # 默认列表为空
        self.source_list.setCurrentRow(-1)

    def _build_source_list_ui(self):
        """将原来的源路径行改造成带标题的列表 + 添加/删除按钮
        同时把目的路径行也先拿出来，后面统一摆放顺序
        """
        # 保存目的路径控件引用
        self.target_label = self.label_10
        self.target_button = self.local_path_pushButton

        # 从 gridLayout 中移除源路径行和目的路径行
        self.gridLayout.removeWidget(self.label_7)
        self.gridLayout.removeWidget(self.server_path_lineEdit)
        self.gridLayout.removeWidget(self.label_10)
        self.gridLayout.removeWidget(self.local_path_pushButton)
        self.label_7.setParent(None)
        self.label_7.deleteLater()
        self.server_path_lineEdit.setParent(None)
        self.server_path_lineEdit.deleteLater()
        # 目的路径控件不移除父对象，只是从布局中拿出来，后面还要放回去

        # 标题
        self.source_title_label = QLabel("源路径")
        title_font = self.source_title_label.font()
        title_font.setBold(True)
        self.source_title_label.setFont(title_font)

        # 创建列表控件
        self.source_list = QListWidget()
        self.source_list.setObjectName("source_list")
        self.source_list.setMinimumHeight(80)
        self.source_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 创建按钮
        self.add_source_btn = QPushButton("添加")
        self.add_source_btn.setObjectName("add_source_btn")
        self.del_source_btn = QPushButton("删除")
        self.del_source_btn.setObjectName("del_source_btn")

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_source_btn)
        btn_layout.addWidget(self.del_source_btn)
        btn_layout.addStretch()

        # 整体容器
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(self.source_title_label)
        vbox.addWidget(self.source_list)
        vbox.addLayout(btn_layout)

        # 插入到 gridLayout 第1行（frame 下面），跨2列
        self.gridLayout.addWidget(container, 1, 0, 1, 2)

        # 目的路径放第3行（筛选条件 frame 下面）
        self.gridLayout.addWidget(self.target_label, 3, 0, 1, 1)
        self.gridLayout.addWidget(self.target_button, 3, 1, 1, 1)

        # 连接信号
        self.add_source_btn.clicked.connect(self._on_add_source)
        self.del_source_btn.clicked.connect(self._on_del_source)
        self.source_list.currentRowChanged.connect(self._on_source_selected)
        self.source_list.itemDoubleClicked.connect(self._on_source_double_clicked)
        self.target_button.clicked.connect(self.select_path)

    def _rebuild_filter_frame(self):
        """重建筛选条件 frame：修改时间 + 名称包含 + 名称不包含"""
        # 移除原来的"名称包含"行控件
        self.gridLayout_2.removeWidget(self.label_9)
        self.gridLayout_2.removeWidget(self.filename_lineEdit)
        self.label_9.setParent(None)
        self.label_9.deleteLater()
        self.filename_lineEdit.setParent(None)
        self.filename_lineEdit.deleteLater()

        # ---- 名称包含行 ----
        self.label_include = QLabel("名称包含")
        self.include_lineEdit = QLineEdit()
        self.include_lineEdit.setPlaceholderText("多个关键词用 / 分隔")

        include_logic_widget = QWidget()
        include_logic_layout = QHBoxLayout(include_logic_widget)
        include_logic_layout.setContentsMargins(0, 0, 0, 0)
        include_logic_layout.setSpacing(6)
        include_logic_label = QLabel("逻辑：")
        self.include_radio_and = QRadioButton("和")
        self.include_radio_or = QRadioButton("或")
        self.include_radio_or.setChecked(True)
        self.include_logic_group = QButtonGroup(self)
        self.include_logic_group.addButton(self.include_radio_and)
        self.include_logic_group.addButton(self.include_radio_or)
        include_logic_layout.addWidget(include_logic_label)
        include_logic_layout.addWidget(self.include_radio_and)
        include_logic_layout.addWidget(self.include_radio_or)

        include_row_widget = QWidget()
        include_row_layout = QHBoxLayout(include_row_widget)
        include_row_layout.setContentsMargins(0, 0, 0, 0)
        include_row_layout.setSpacing(8)
        include_row_layout.addWidget(self.include_lineEdit, 1)
        include_row_layout.addWidget(include_logic_widget)

        self.gridLayout_2.addWidget(self.label_include, 2, 0, 1, 1)
        self.gridLayout_2.addWidget(include_row_widget, 2, 1, 1, 1)

        # ---- 名称不包含行 ----
        self.label_exclude = QLabel("名称不包含")
        self.exclude_lineEdit = QLineEdit()
        self.exclude_lineEdit.setPlaceholderText("多个关键词用 / 分隔")

        exclude_logic_widget = QWidget()
        exclude_logic_layout = QHBoxLayout(exclude_logic_widget)
        exclude_logic_layout.setContentsMargins(0, 0, 0, 0)
        exclude_logic_layout.setSpacing(6)
        exclude_logic_label = QLabel("逻辑：")
        self.exclude_radio_and = QRadioButton("和")
        self.exclude_radio_or = QRadioButton("或")
        self.exclude_radio_and.setChecked(True)
        self.exclude_logic_group = QButtonGroup(self)
        self.exclude_logic_group.addButton(self.exclude_radio_and)
        self.exclude_logic_group.addButton(self.exclude_radio_or)
        exclude_logic_layout.addWidget(exclude_logic_label)
        exclude_logic_layout.addWidget(self.exclude_radio_and)
        exclude_logic_layout.addWidget(self.exclude_radio_or)

        exclude_row_widget = QWidget()
        exclude_row_layout = QHBoxLayout(exclude_row_widget)
        exclude_row_layout.setContentsMargins(0, 0, 0, 0)
        exclude_row_layout.setSpacing(8)
        exclude_row_layout.addWidget(self.exclude_lineEdit, 1)
        exclude_row_layout.addWidget(exclude_logic_widget)

        self.gridLayout_2.addWidget(self.label_exclude, 3, 0, 1, 1)
        self.gridLayout_2.addWidget(exclude_row_widget, 3, 1, 1, 1)

        # 内边距与服务器信息边框保持一致
        self.gridLayout_2.setContentsMargins(8, 8, 8, 8)
        self.gridLayout_2.setVerticalSpacing(6)

    def _move_filter_frame_into_grid(self):
        """将筛选条件 frame 移到 gridLayout 中，放在源路径列表下面、目的路径上面"""
        self.verticalLayout.removeWidget(self.frame)
        self.gridLayout.addWidget(self.frame, 2, 0, 1, 2)

    def _refresh_filter_title(self, row):
        if row < 0:
            self.label_12.setText("源路径筛选条件")
        else:
            self.label_12.setText(f"第{row + 1}号源路径筛选条件")

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
        """添加按钮：获取文件的源路径是服务器路径，用输入对话框输入"""
        text, ok = QInputDialog.getText(self, "添加源路径", "请输入服务器路径：")
        if ok and text.strip():
            row = self._add_source_item(text.strip())
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
        """双击条目：编辑路径"""
        row = self.source_list.row(item)
        if row < 0:
            return
        old_path = self.source_items[row]['路径']
        text, ok = QInputDialog.getText(self, "编辑源路径", "请输入服务器路径：", text=old_path)
        if ok and text.strip():
            self.source_items[row]['路径'] = text.strip()
            self._update_item_display(row)

    def _on_ip_changed(self, ip):
        if getattr(self, '_loading', False):
            return
        if self.server_comboBox.currentIndex() != -1:
            return
        if ip.strip():
            self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：{ip}')
        else:
            self.sc_name_lineEdit.clear()

    def _on_username_changed(self, username):
        if username:
            self.work_dir_lineEdit.setText(f"/home/{username}")

    def create_sc(self):
        text_list = [
            self.linux_ip_lineEdit,
            self.username_lineEdit,
            self.passwd_lineEdit,
            self.sshport_lineEdit,
            self.local_path_pushButton,
            self.sc_name_lineEdit
        ]
        # 注意：local_path_pushButton 是目的路径（本地保存路径），text 不能为空
        # 校验 text_list 中除 button 外的 lineEdit，button 单独判断
        self.source_list.setStyleSheet("")
        self.local_path_pushButton.setStyleSheet("")
        line_edits = [
            self.linux_ip_lineEdit,
            self.username_lineEdit,
            self.passwd_lineEdit,
            self.sshport_lineEdit,
            self.sc_name_lineEdit
        ]
        for t in line_edits:
            t.setStyleSheet("")

        for t in line_edits:
            if not t.text().strip():
                t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                return

        # 目的路径（本地路径按钮）校验
        if not self.local_path_pushButton.text().strip() or self.local_path_pushButton.text() == '请选择':
            self.local_path_pushButton.setStyleSheet("QPushButton { border: 2px solid red; }")
            return

        # 校验源路径列表
        valid_items = [item for item in self.source_items if item['路径']]
        if not valid_items:
            self.source_list.setStyleSheet("QListWidget { border: 2px solid red; }")
            self.parent.update_run_info("请至少添加一个源路径", "WARNING")
            return

        # 保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['源路径列表'] = valid_items[:]
        self.sc_cfg['目的路径'] = self.local_path_pushButton.text()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()
        self.sc_cfg['文件暂存路径'] = self.work_dir_lineEdit.text().strip()

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
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])

        # 目的路径（本地路径）
        if '目的路径' in sc_data:
            self.local_path_pushButton.setText(sc_data['目的路径'])
            self.local_path_pushButton.setToolTip(sc_data['目的路径'])
        elif '本地路径' in sc_data:
            self.local_path_pushButton.setText(sc_data['本地路径'])
            self.local_path_pushButton.setToolTip(sc_data['本地路径'])
        self.local_path_pushButton.setToolTipDuration(10000)

        if '文件暂存路径' in sc_data:
            self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])

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
        elif '服务器路径' in sc_data:
            # 兼容旧版单条配置
            modify_time = sc_data.get('修改时间', '全部')
            include = sc_data.get('文件名包含', '')
            self._add_source_item(sc_data['服务器路径'], modify_time, include)

        if self.source_list.count() > 0:
            self.source_list.setCurrentRow(0)

        self._loading = False

    def reset(self):
        self.server_comboBox.clear()
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.work_dir_lineEdit.clear()
        self.local_path_pushButton.setText("当前路径/时间IP(例:20251024_031415-1.1.1.1)/")
        self.sc_name_lineEdit.clear()
        self.source_items = []
        self.source_list.clear()
        self.time_comboBox.setCurrentIndex(0)
        self.include_lineEdit.clear()
        self.exclude_lineEdit.clear()
        self.include_radio_or.setChecked(True)
        self.exclude_radio_and.setChecked(True)

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
        self.work_dir_lineEdit.setText(f"/home/{self.server_comboBox.currentData()['用户名']}")

    # 保留原来的选择路径方法（选择本地目的路径）
    def select_path(self):
        """获取文件时本地路径只能选择文件夹"""
        from utils.qt_dialog_tools import select_dir_dialog
        path = select_dir_dialog(self, title="选择目的路径")
        if path:
            self.local_path_pushButton.setText(path)
            self.local_path_pushButton.setToolTip(path)
            self.local_path_pushButton.setToolTipDuration(10000)
