from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QFileDialog
from UI import get_files_dlg
from .base_dialog import sc_class2str


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

        self.local_path_pushButton.clicked.connect(self.select_path)
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
        self.local_path_pushButton.setStyleSheet("")
        for t in text_list:
            t.setStyleSheet("")

        # 如果有输入框为空，则高亮显示
        for t in text_list:
            if not t.text().strip():
                t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                return
        if self.local_path_pushButton.text() == '请选择':
            self.local_path_pushButton.setStyleSheet("QPushButton { border: 2px solid red; }")
            return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['本地路径'] = self.local_path_pushButton.text()
        self.sc_cfg['修改时间'] = self.time_comboBox.currentText()
        self.sc_cfg['文件名包含'] = self.filename_lineEdit.text()
        self.sc_cfg['服务器路径'] = self.server_path_lineEdit.text()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()
        self.sc_cfg['文件暂存路径'] = self.work_dir_lineEdit.text().strip()

        # 将快捷方式的配置内容传递给主窗口
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
        self.local_path_pushButton.setText(sc_data['本地路径'])
        self.local_path_pushButton.setToolTip(sc_data['本地路径'])
        self.local_path_pushButton.setToolTipDuration(10000)
        self.time_comboBox.setCurrentIndex(self.time_dic[sc_data['修改时间']])
        self.filename_lineEdit.setText(sc_data['文件名包含'])
        self.server_path_lineEdit.setText(sc_data['服务器路径'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        # 回显文件暂存路径
        if '文件暂存路径' in sc_data:
            self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])
        self._loading = False  # 加载完成

    def reset(self):
        self.server_comboBox.clear()
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.work_dir_lineEdit.clear()
        self.local_path_pushButton.setText("当前路径/时间IP(例:20251024031415-1.1.1.1)/")
        self.time_comboBox.setCurrentIndex(0)
        self.filename_lineEdit.clear()
        self.server_path_lineEdit.clear()
        self.sc_name_lineEdit.clear()

    def select_path(self):
        """获取文件时本地路径只能选择文件夹"""
        dialog = QFileDialog(self)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        dialog.setFileMode(QFileDialog.FileMode.Directory)  # 选择目录

        # 使用Qt自带的对话框,可以修改按钮名称，实现既可以选择文件又可以选择文件夹（修改取消按钮为选择文件夹）
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        # 显示对话框并检查用户是否点击了打开按钮
        if dialog.exec_():
            # 如果用户选择了文件，返回文件路径
            file_paths = dialog.selectedFiles()
            if file_paths:
                self.local_path_pushButton.setText(file_paths[0])
                self.local_path_pushButton.setToolTip(file_paths[0])
                self.local_path_pushButton.setToolTipDuration(10000)
                return

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
        # 选择服务器时，同步更新文件暂存路径
        self.work_dir_lineEdit.setText(f"/home/{self.server_comboBox.currentData()['用户名']}")
