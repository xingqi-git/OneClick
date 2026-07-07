from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QFileDialog, QDialogButtonBox
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

        self.source_path_pushButton.clicked.connect(self.select_source_path)
        self.target_path_pushButton.clicked.connect(self.select_target_path)
        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        self.time_dic = {}
        for index in range(self.time_comboBox.count()):
            text = self.time_comboBox.itemText(index)
            self.time_dic[text] = index

        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：')

    def create_sc(self):
        # 每次点生成快捷方式按钮时，都先初始话所有输入框的样式
        self.source_path_pushButton.setStyleSheet("")
        self.target_path_pushButton.setStyleSheet("")
        self.sc_name_lineEdit.setStyleSheet("")
        # 如果有输入框为空，则高亮显示
        if self.source_path_pushButton.text() == '请选择':
            self.source_path_pushButton.setStyleSheet("QPushButton { border: 2px solid red; }")
            return
        if not self.sc_name_lineEdit.text().strip():
            self.sc_name_lineEdit.setStyleSheet("QLineEdit { border: 2px solid red; }")
            return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['源路径'] = self.source_path_pushButton.text()
        self.sc_cfg['修改时间'] = self.time_comboBox.currentText()
        self.sc_cfg['文件名包含'] = self.filename_lineEdit.text()
        self.sc_cfg['复制到'] = self.target_path_pushButton.text()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()

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
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.source_path_pushButton.setText(sc_data['源路径'])
        # 设置鼠标悬浮显示
        self.source_path_pushButton.setToolTip(sc_data['源路径'])
        self.source_path_pushButton.setToolTipDuration(10000)
        self.time_comboBox.setCurrentIndex(self.time_dic[sc_data['修改时间']])
        self.filename_lineEdit.setText(sc_data['文件名包含'])
        self.target_path_pushButton.setText(sc_data['复制到'])
        # 设置鼠标悬浮显示
        self.target_path_pushButton.setToolTip(sc_data['复制到'])
        self.target_path_pushButton.setToolTipDuration(10000)
        self.sc_name_lineEdit.setText(sc_data['指令名称'])

    def reset(self):
        self.source_path_pushButton.setText('请选择')
        self.time_comboBox.setCurrentIndex(0)
        self.filename_lineEdit.clear()
        self.target_path_pushButton.setText('当前路径/当前时间(例:20251024031415)/')
        self.sc_name_lineEdit.clear()

    def select_source_path(self):
        dialog = QFileDialog(self)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)  # 只允许选择已存在的文件

        # 使用Qt自带的对话框,可以修改按钮名称，实现既可以选择文件又可以选择文件夹（修改取消按钮为选择文件夹）
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # 在对话框显示前修改按钮
        button_box = dialog.findChild(QDialogButtonBox)
        if button_box:
            buttons = button_box.buttons()
            for button in buttons:
                role = button_box.buttonRole(button)
                if role == QDialogButtonBox.ButtonRole.RejectRole:
                    button.setText("选择当前文件夹路径")
        # 显示对话框并检查用户是否点击了打开按钮
        if dialog.exec_():
            # 如果用户选择了文件，返回文件路径
            file_paths = dialog.selectedFiles()
            if file_paths:
                self.source_path_pushButton.setText(file_paths[0])
                self.source_path_pushButton.setToolTip(file_paths[0])
                self.source_path_pushButton.setToolTipDuration(10000)
                return
        # 如果用户未选择任何文件，返回当前文件夹路径
        current_dir = dialog.directory().absolutePath()
        self.source_path_pushButton.setText(current_dir)
        self.source_path_pushButton.setToolTip(current_dir)
        self.source_path_pushButton.setToolTipDuration(10000)

    def select_target_path(self):
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
                self.target_path_pushButton.setText(file_paths[0])
                self.target_path_pushButton.setToolTip(file_paths[0])
                self.target_path_pushButton.setToolTipDuration(10000)
                return
