from PyQt5 import QtCore
from PyQt5.QtWidgets import (QDialog, QFileDialog, QDialogButtonBox, QListWidget,
                             QListWidgetItem, QHBoxLayout, QPushButton, QVBoxLayout,
                             QWidget, QSizePolicy, QLabel, QLineEdit, QButtonGroup,
                             QRadioButton)
from UI import send_files_dlg
from .base_dialog import sc_class2str, wrap_server_info_in_frame


class SendFilesDialog(QDialog, send_files_dlg.Ui_Dialog):
    """初始化对象时，需要传入主窗口，因为按下生成快捷方式按钮后需要主窗口调用添加快捷按钮的方法"""

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
        self._ignore_filter_change = False  # 加载条目时暂时屏蔽筛选条件变更

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

        # 创建时间下拉菜单的选项字典，因为编辑按钮时传入的是str，需要将str对应为下拉的索引
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

        # 默认不添加条目，列表为空
        self.source_list.setCurrentRow(-1)

        # 调整 tab 顺序：按视觉从上到下、从左到右
        self._set_tab_order()

    def _set_tab_order(self):
        """设置 tab 顺序，确保按视觉从上到下、从左到右"""
        # 服务器信息区域
        self.setTabOrder(self.server_comboBox, self.linux_ip_lineEdit)
        self.setTabOrder(self.linux_ip_lineEdit, self.sshport_lineEdit)
        self.setTabOrder(self.sshport_lineEdit, self.username_lineEdit)
        self.setTabOrder(self.username_lineEdit, self.passwd_lineEdit)
        self.setTabOrder(self.passwd_lineEdit, self.work_dir_lineEdit)
        # 源路径列表 + 按钮
        self.setTabOrder(self.work_dir_lineEdit, self.source_list)
        self.setTabOrder(self.source_list, self.add_file_btn)
        self.setTabOrder(self.add_file_btn, self.add_dir_btn)
        self.setTabOrder(self.add_dir_btn, self.del_source_btn)
        # 筛选条件区域
        self.setTabOrder(self.del_source_btn, self.time_comboBox)
        self.setTabOrder(self.time_comboBox, self.include_lineEdit)
        self.setTabOrder(self.include_lineEdit, self.include_radio_and)
        self.setTabOrder(self.include_radio_and, self.include_radio_or)
        self.setTabOrder(self.include_radio_or, self.exclude_lineEdit)
        self.setTabOrder(self.exclude_lineEdit, self.exclude_radio_and)
        self.setTabOrder(self.exclude_radio_and, self.exclude_radio_or)
        # 目的路径 → 快捷按钮名称 → 底部按钮
        self.setTabOrder(self.exclude_radio_or, self.server_path_lineEdit)
        self.setTabOrder(self.server_path_lineEdit, self.sc_name_lineEdit)
        self.setTabOrder(self.sc_name_lineEdit, self.save_pushButton)
        self.setTabOrder(self.save_pushButton, self.reset_pushButton)
        self.setTabOrder(self.reset_pushButton, self.close_pushButton)

    def _build_source_list_ui(self):
        """将原来的源路径行改造成带标题的列表 + 添加/删除按钮"""
        # 从 gridLayout 中移除原来的源路径控件
        self.gridLayout.removeWidget(self.label_7)
        self.gridLayout.removeWidget(self.local_path_pushButton)
        self.label_7.setParent(None)
        self.label_7.deleteLater()
        self.local_path_pushButton.setParent(None)
        self.local_path_pushButton.deleteLater()

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
        self.add_file_btn = QPushButton("添加文件")
        self.add_file_btn.setObjectName("add_file_btn")
        self.add_dir_btn = QPushButton("添加文件夹")
        self.add_dir_btn.setObjectName("add_dir_btn")
        self.del_source_btn = QPushButton("删除")
        self.del_source_btn.setObjectName("del_source_btn")

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_file_btn)
        btn_layout.addWidget(self.add_dir_btn)
        btn_layout.addWidget(self.del_source_btn)
        btn_layout.addStretch()

        # 整体容器（标题 + 列表 + 按钮）
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(self.source_title_label)
        vbox.addWidget(self.source_list)
        vbox.addLayout(btn_layout)

        # 插入到 gridLayout 第1行（frame 下面），跨2列
        self.gridLayout.addWidget(container, 1, 0, 1, 2)

        # 连接信号
        self.add_file_btn.clicked.connect(self._on_add_file)
        self.add_dir_btn.clicked.connect(self._on_add_dir)
        self.del_source_btn.clicked.connect(self._on_del_source)
        self.source_list.currentRowChanged.connect(self._on_source_selected)
        self.source_list.itemDoubleClicked.connect(self._on_source_double_clicked)

    def _rebuild_filter_frame(self):
        """
        重建筛选条件 frame 的内容：
        把"文件名包含"那一行替换成两行：
        - 名称包含：标签 + 输入框（用/分隔） + 逻辑：和/或
        - 名称不包含：标签 + 输入框（用/分隔） + 逻辑：和/或
        """
        # 从 frame 里的 gridLayout_2 中移除原来的"文件名包含"行控件
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

        # 逻辑切换（和输入框同一行）
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

        # 放入 gridLayout_2 第2行：标签(0列) + 输入框(1列左) + 逻辑(1列右)
        # 用一个容器把输入框和逻辑放在一起
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
        self.exclude_radio_and.setChecked(True)  # 不包含默认"和"
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

        # 设置列宽比例，和原来一致
        self.gridLayout_2.setColumnStretch(0, 1)
        self.gridLayout_2.setColumnStretch(1, 4)
        # 内边距与服务器信息边框保持一致
        self.gridLayout_2.setContentsMargins(8, 8, 8, 8)
        self.gridLayout_2.setVerticalSpacing(6)

    def _move_filter_frame_into_grid(self):
        """
        将筛选条件 frame 从 verticalLayout 移到 gridLayout 中，
        放在源路径列表下面、目的路径上面。
        """
        # 从 verticalLayout 中移除 frame
        self.verticalLayout.removeWidget(self.frame)

        # 放到 gridLayout 第2行（源路径列表下面），跨2列
        self.gridLayout.addWidget(self.frame, 2, 0, 1, 2)

    def _refresh_filter_title(self, row):
        """更新筛选条件标题，显示当前是第几号"""
        if row < 0:
            self.label_12.setText("源路径筛选条件")
        else:
            self.label_12.setText(f"第{row + 1}号源路径筛选条件")

    def _update_item_display(self, row):
        """更新列表中某一行的显示文本（带序号）"""
        if row < 0 or row >= len(self.source_items):
            return
        item = self.source_list.item(row)
        path = self.source_items[row]['路径']
        display = f"{row + 1}. {path}" if path else f"{row + 1}. (未设置路径，请双击编辑)"
        item.setText(display)
        item.setToolTip(path)

    def _refresh_all_item_numbers(self):
        """重新刷新所有条目的序号（删除后调用）"""
        for i in range(len(self.source_items)):
            self._update_item_display(i)

    def _add_source_item(self, path, modify_time="全部", include=None, exclude=None):
        """添加一条源路径条目"""
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

    def _on_add_file(self):
        """添加文件按钮：打开原生文件选择对话框"""
        from PyQt5.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, "选择源文件", "", "")
        for path in paths:
            row = self._add_source_item(path)
            self.source_list.setCurrentRow(row)

    def _on_add_dir(self):
        """添加文件夹按钮：打开原生文件夹选择对话框"""
        from PyQt5.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if path:
            row = self._add_source_item(path)
            self.source_list.setCurrentRow(row)

    def _on_del_source(self):
        """删除当前选中条目"""
        row = self.source_list.currentRow()
        if row < 0:
            return
        if len(self.source_items) <= 1:
            # 至少保留一条
            return
        self.source_items.pop(row)
        self.source_list.takeItem(row)
        # 删除后刷新所有序号
        self._refresh_all_item_numbers()
        if row >= len(self.source_items):
            row = len(self.source_items) - 1
        self.source_list.setCurrentRow(row)

    def _on_source_selected(self, row):
        """选中条目变化：加载该条目的筛选条件到编辑区"""
        if row < 0 or row >= len(self.source_items):
            return
        self._ignore_filter_change = True
        item = self.source_items[row]
        if item['修改时间'] in self.time_dic:
            self.time_comboBox.setCurrentIndex(self.time_dic[item['修改时间']])
        else:
            self.time_comboBox.setCurrentIndex(0)

        # 名称包含
        inc = item.get('名称包含', {"关键词": [], "逻辑": "或"})
        self.include_lineEdit.setText("/".join(inc.get('关键词', [])) if isinstance(inc, dict) else (inc if inc else ""))
        if isinstance(inc, dict):
            if inc.get('逻辑') == '和':
                self.include_radio_and.setChecked(True)
            else:
                self.include_radio_or.setChecked(True)
        else:
            self.include_radio_or.setChecked(True)

        # 名称不包含
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
        """筛选条件编辑区变化：写回当前选中条目"""
        if self._ignore_filter_change:
            return
        row = self.source_list.currentRow()
        if row < 0 or row >= len(self.source_items):
            return

        # 读取包含
        inc_text = self.include_lineEdit.text().strip()
        inc_keywords = [k.strip() for k in inc_text.split("/") if k.strip()]
        inc_logic = "和" if self.include_radio_and.isChecked() else "或"
        self.source_items[row]['名称包含'] = {"关键词": inc_keywords, "逻辑": inc_logic}

        # 读取不包含
        exc_text = self.exclude_lineEdit.text().strip()
        exc_keywords = [k.strip() for k in exc_text.split("/") if k.strip()]
        exc_logic = "和" if self.exclude_radio_and.isChecked() else "或"
        self.source_items[row]['名称不包含'] = {"关键词": exc_keywords, "逻辑": exc_logic}

        # 修改时间
        self.source_items[row]['修改时间'] = self.time_comboBox.currentText()

    def _on_source_double_clicked(self, item):
        """双击条目：重新选择路径（按原路径类型弹对应对话框）"""
        import os
        from PyQt5.QtWidgets import QFileDialog
        row = self.source_list.row(item)
        if row < 0:
            return
        old_path = self.source_items[row]['路径']
        default_dir = os.path.dirname(old_path)
        if os.path.isdir(old_path):
            path = QFileDialog.getExistingDirectory(self, "选择源文件夹", default_dir)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "选择源文件", default_dir, "")
            path = file_path
        if path:
            self.source_items[row]['路径'] = path
            self._update_item_display(row)

    def _on_ip_changed(self, ip):
        """手动填写IP时，自动生成快捷按钮名称"""
        if getattr(self, '_loading', False):
            return
        if self.server_comboBox.currentIndex() != -1:
            return
        if ip.strip():
            self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：{ip}')
        else:
            self.sc_name_lineEdit.clear()

    def _on_username_changed(self, username):
        """用户名变化时自动更新文件暂存路径"""
        if username:
            self.work_dir_lineEdit.setText(f"/home/{username}")

    def create_sc(self):
        text_list = [
            self.linux_ip_lineEdit,
            self.username_lineEdit,
            self.passwd_lineEdit,
            self.sshport_lineEdit,
            self.server_path_lineEdit,
            self.sc_name_lineEdit
        ]
        # 每次点生成快捷方式按钮时，都先初始化所有输入框的样式
        self.source_list.setStyleSheet("")
        for t in text_list:
            t.setStyleSheet("")

        # 如果有输入框为空，则高亮显示
        for t in text_list:
            if not t.text().strip():
                t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                return

        # 校验源路径列表
        valid_items = [item for item in self.source_items if item['路径']]
        if not valid_items:
            self.source_list.setStyleSheet("QListWidget { border: 2px solid red; }")
            self.parent.update_run_info("请至少添加一个源路径", "WARNING")
            return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['源路径列表'] = valid_items[:]
        self.sc_cfg['服务器路径'] = self.server_path_lineEdit.text()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()
        self.sc_cfg['文件暂存路径'] = self.work_dir_lineEdit.text().strip()

        # 将快捷方式的配置内容传递给主窗口，区分编辑模式还是添加模式
        if self.parent:
            if hasattr(self, 'button_id'):
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        # 关闭对话框
        self.accept()

    def edit_sc(self, button_id):
        self.button_id = button_id  # 变为自己的属性，用于按下保存按钮时父窗口调用编辑按钮函数
        self._loading = True  # 加载中，防止 textChanged 覆盖名称
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.server_path_lineEdit.setText(sc_data['服务器路径'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        # 回显文件暂存路径
        if '文件暂存路径' in sc_data:
            self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])

        # 回显源路径列表（兼容旧版配置）
        self.source_items = []
        self.source_list.clear()
        if '源路径列表' in sc_data:
            for item in sc_data['源路径列表']:
                include = item.get('名称包含', {"关键词": [], "逻辑": "或"})
                exclude = item.get('名称不包含', {"关键词": [], "逻辑": "和"})
                # 兼容旧版：列表里可能还是"文件名包含"字符串
                if '文件名包含' in item and isinstance(item['文件名包含'], str):
                    include = item['文件名包含']
                self._add_source_item(
                    item.get('路径', ''),
                    item.get('修改时间', '全部'),
                    include,
                    exclude
                )
        elif '本地路径' in sc_data:
            # 兼容旧版单条配置
            modify_time = sc_data.get('修改时间', '全部')
            include = sc_data.get('文件名包含', '')
            self._add_source_item(sc_data['本地路径'], modify_time, include)

        if self.source_list.count() > 0:
            self.source_list.setCurrentRow(0)

        self._loading = False  # 加载完成

    def reset(self):
        self.server_comboBox.clear()
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.work_dir_lineEdit.clear()
        self.server_path_lineEdit.clear()
        self.sc_name_lineEdit.clear()
        # 重置源路径列表
        self.source_items = []
        self.source_list.clear()
        self.time_comboBox.setCurrentIndex(0)
        self.include_lineEdit.clear()
        self.exclude_lineEdit.clear()
        self.include_radio_or.setChecked(True)
        self.exclude_radio_and.setChecked(True)
        # 重置后列表为空，不添加条目

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
        # 选择服务器时，同步更新文件暂存路径
        self.work_dir_lineEdit.setText(f"/home/{self.server_comboBox.currentData()['用户名']}")
