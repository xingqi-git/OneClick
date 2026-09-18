from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QFrame, QGridLayout, QLabel
from UI import send_cmd_dlg
from utils.logger import get_logger


def wrap_server_info_in_frame(dialog, grid_layout, server_row_count):
    """
    将 grid_layout 中前 server_row_count 行的服务器信息控件，
    移动到一个带边框的 QFrame 中，并将 QFrame 插入到 grid_layout 第0行。
    """
    # 创建带边框的 QFrame，样式与筛选条件框一致
    frame = QFrame(dialog)
    frame.setFrameShape(QFrame.Box)
    frame.setFrameShadow(QFrame.Sunken)
    frame.setLineWidth(1)

    # QFrame 内部的网格布局
    frame_layout = QGridLayout(frame)
    frame_layout.setContentsMargins(8, 8, 8, 8)
    frame_layout.setHorizontalSpacing(6)
    frame_layout.setVerticalSpacing(6)
    frame_layout.setColumnStretch(0, 1)
    frame_layout.setColumnStretch(1, 4)

    # 添加标题
    title_label = QLabel("服务器信息", frame)
    title_font = title_label.font()
    title_font.setBold(True)
    title_label.setFont(title_font)
    frame_layout.addWidget(title_label, 0, 0, 1, 2)

    # 收集前 server_row_count 行的控件
    widgets = []
    for row in range(server_row_count):
        for col in range(2):
            item = grid_layout.itemAtPosition(row, col)
            if item is not None:
                w = item.widget()
                if w is not None:
                    widgets.append((row, col, w))

    # 从原布局移除
    for row, col, w in widgets:
        grid_layout.removeWidget(w)

    # 将控件加入 frame_layout（第0行是标题，所以行号 +1）
    for row, col, w in widgets:
        frame_layout.addWidget(w, row + 1, col, 1, 1)

    # 将 frame 插入到 grid_layout 第0行，跨2列
    grid_layout.addWidget(frame, 0, 0, 1, 2)

    return frame


sc_class2str = {
    'SendCMDDialog': "发送命令",
    'SendCMD2Dialog': "发送命令并接收回显",
    'SendFilesDialog': "发送文件",
    'GetFilesDialog': "获取文件",
    'CopyFilesDialog': "复制本地文件",
    'ResourceMonitorDialog1': "资源监控",
    'WeakNetDialog1': "弱网",
    'ServerCheckDialog': "服务器检查"
}


class SendCMDDialog(QDialog, send_cmd_dlg.Ui_Dialog):
    """初始化对象时，需要传入主窗口，因为按下生成快捷方式的按钮后需要主窗口调用添加快捷按钮的方法"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent
        self.logger = get_logger("SendCMDDialog")

        # 保存对话框的所有配置项
        self.sc_cfg = {}
        self._loading = False  # 编辑模式加载标志，防止 textChanged 覆盖名称

        # 将服务器信息行用边框包裹起来
        # 前6行：选择服务器、IP、端口、用户名、密码、临时文件路径
        wrap_server_info_in_frame(self, self.gridLayout, 6)

        # "指令内容"和"快捷按钮名称"加粗
        bold_labels = [self.label_7, self.label_8]
        for lbl in bold_labels:
            f = lbl.font()
            f.setBold(True)
            lbl.setFont(f)

        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        # 将服务器列表加载到下拉选择框
        for server in self.parent.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)
        self.server_comboBox.activated.connect(self.select_server)

        # IP输入框变化时，自动生成快捷按钮名称
        self.linux_ip_lineEdit.textChanged.connect(self._on_ip_changed)

        # 文件暂存路径：用户名变化时自动联动更新
        if hasattr(self, 'username_lineEdit') and hasattr(self, 'work_dir_lineEdit'):
            self.username_lineEdit.textChanged.connect(self._on_username_changed)
            # 初始化时设置默认值（如果已有用户名则自动填入）
            if self.username_lineEdit.text():
                self.work_dir_lineEdit.setText(f"/home/{self.username_lineEdit.text()}")

        # 仅发送命令和发送命令并接收回显不需要显示临时文件路径输入框
        if self.__class__.__name__ in ('SendCMDDialog', 'SendCMD2Dialog'):
            self.label_workdir.setVisible(False)
            self.work_dir_lineEdit.setVisible(False)

    def _on_ip_changed(self, ip):
        """手动填写IP时，自动生成快捷按钮名称"""
        if getattr(self, '_loading', False):
            return
        # 如果是通过下拉框选择的服务器，不自动填
        if self.server_comboBox.currentIndex() != -1:
            return
        # 手动填写IP，用 IP 替代服务器名称
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
            self.sc_name_lineEdit
        ]
        # 每次点生成快捷方式按钮时，都先初始话所有输入框的样式
        self.cmd_TextEdit.setStyleSheet("")
        for t in text_list:
            t.setStyleSheet("")

        # 如果有输入框为空，则高亮显示
        for t in text_list:
            if not t.text().strip():
                t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                self.parent.update_run_info(f"{t.objectName()}不能为空", "WARNING")
                return
        if not self.cmd_TextEdit.toPlainText().strip():
            self.cmd_TextEdit.setStyleSheet("QPlainTextEdit { border: 2px solid red; }")
            self.parent.update_run_info("请输入指令内容", "WARNING")
            return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['指令'] = self.cmd_TextEdit.toPlainText()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()
        # 保存文件暂存路径
        if hasattr(self, 'work_dir_lineEdit'):
            self.sc_cfg['文件暂存路径'] = self.work_dir_lineEdit.text().strip()
        else:
            self.sc_cfg['文件暂存路径'] = f"/home/{self.username_lineEdit.text()}"

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
        self.cmd_TextEdit.setPlainText(sc_data['指令'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        # 回显文件暂存路径
        if '文件暂存路径' in sc_data and hasattr(self, 'work_dir_lineEdit'):
            self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])
        self._loading = False  # 加载完成

    def reset(self):
        self.server_comboBox.setCurrentIndex(-1)
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.cmd_TextEdit.clear()
        self.sc_name_lineEdit.clear()
        if hasattr(self, 'work_dir_lineEdit'):
            self.work_dir_lineEdit.clear()

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
        # 选择服务器时，同步更新文件暂存路径
        if hasattr(self, 'work_dir_lineEdit'):
            self.work_dir_lineEdit.setText(f"/home/{self.server_comboBox.currentData()['用户名']}")
