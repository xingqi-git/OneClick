import os.path
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QDialog, QPushButton, QWidget, QVBoxLayout, QMenu, QFileDialog, QMessageBox, QMainWindow

from UI import MainWindow
from utils import ssh_tools, windows_tools, qthread_worker
import json
import datetime
from utils.logger import setup_logging, get_logger
from dialogs import (SendCMDDialog, SendCMD2Dialog, SendFilesDialog, GetFilesDialog, CopyFilesDialog,
                     SetServerDialog, ResourceMonitorDialog1, ResourceMonitorDialog2,
                     WeakNetDialog1, WeakNetControlDialog, HelpDialog, sc_class2str)


class MainWindowLogic(QMainWindow, MainWindow.Ui_MainWindow):
    """继承两个父类，QMainWindow用于作为参数传入MainWindow.Ui_MainWindow"""
    def __init__(self, parent=None):
        super().__init__(parent) # 调用父类QMainWindow，实例化了self为QMainWindow
        self.setupUi(self) # 现在self是个窗口，self直接调用，相当于MainWindow.Ui_MainWindow的setupUi

        # 创建菜单栏选项与弹出的编辑窗口关系
        self.send_cmd_action.triggered.connect(self.cmd1_dialog)  # 发送cmd的编辑框
        self.send_cmd2_action.triggered.connect(self.cmd2_dialog)  # 发送cmd并接收回显的编辑框
        self.send_file_action.triggered.connect(self.send_file_dialog)  # 发送文件的编辑框
        self.get_file_action.triggered.connect(self.get_file_dialog)  # 获取文件的编辑框
        self.copy_local_action.triggered.connect(self.copy_file_dialog)  # 复制本地文件编辑框
        self.resource_monitor_action.triggered.connect(self.resource_monitor_dialog)  # 资源监控编辑框
        self.weak_net_action.triggered.connect(self.weak_net_dialog)  # 弱网编辑框
        self.get_sc_from_cfg_action.triggered.connect(self.load_sc_config)  # 从配置文件获取快捷按钮

        self.edit_server_action.triggered.connect(self.server_cfg_dialog)  # 服务器列表的编辑框
        self.get_server_from_cfg_action.triggered.connect(self.load_server_config)  # 从配置文件获取服务器

        self.save_action.triggered.connect(self.save_config)  # 保存配置到当前配置文件
        self.save_to_action_2.triggered.connect(self.save_config_to)  # 另存为配置到文件夹
        self.help_action.triggered.connect(self.show_help_dialog)  # 显示帮助文档
        # 创建按钮逻辑
        self.stop_pushButton.clicked.connect(self.stop_sc)
        self.clean_pushButton.clicked.connect(self.clean_linux_print)

        # 创建一个容器用于放置动态生成的快捷方式
        self.button_container = QWidget()
        self.button_layout = QVBoxLayout(self.button_container)
        self.scrollArea_2.setWidget(self.button_container)  # 快捷方式多时支持滚动条

        # 将所有快捷方式存储到字典里,由于button_id唯一，因此用字典
        self.sc_buttons = {}  # 存储发送命令按钮对象{'button_id1': {'button': new_button(按钮对象),'config': config_data},...}
        self.btn_count = 0  # 用于快捷方式唯一ID

        # 将运行中的指令线程存入字典
        self.sc_threads = {}
        self.thread_count = 0
        self.timer = None

        # 用于存放服务器配置信息的列表
        self.servers_cfg = []  # [{"服务器名称": ,"IP": ,"端口": ,"用户名": ,"密码": },...]

        # 连接ssh按钮逻辑
        self.connect_pushButton.clicked.connect(self.connect_server)
        self.current_ssh = {}  # 'config':{"服务器名称": ,"IP": ...},'ssh':,'receive_thread':,

        # 发送指令、保存指令、删除指令按钮逻辑
        self.commands = []
        self.save_cmd_pushButton.clicked.connect(self.save_cmd)
        self.del_cmd_pushButton.clicked.connect(self.del_cmd)
        self.send_cmd_pushButton.clicked.connect(self.send_cmd)
        self.cmd_comboBox.activated.connect(self.select_cmd)
        # 输入框的按键监听
        self.cmd_plainTextEdit.keyPressEvent = self.keyPressEvent

        # 配置文件的默认路径
        self.default_config_path = self.get_default_path() + '/' + 'config.json'

        # 初始化日志系统（必须在 update_run_info 之前）
        self._log_emitter = setup_logging(
            log_dir=self.get_default_path(),
            enable_file_logging=False,  # 默认关闭，由勾选框控制
            enable_qt_bridge=False,
        )
        self.logger = get_logger("MainWindow")

        # 先连接状态变化信号，然后设置初始状态（从配置文件读取）
        self.log_file_checkBox.stateChanged.connect(self._on_log_file_checkbox_changed)

        # 从配置文件读取初始状态（如果有）
        initial_log_enabled = False
        # 日志级别配置：字典，键为级别名，值为bool
        self._log_level_config = {
            'DEBUG': False,
            'INFO': True,
            'WARNING': True,
            'ERROR': True,
        }
        if os.path.exists(self.default_config_path):
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    import json
                    cfg_data = json.load(f)
                    if '日志配置' in cfg_data:
                        initial_log_enabled = cfg_data['日志配置'].get('文件日志', False)
                        # 读取日志级别配置（如果有）
                        for level in self._log_level_config:
                            if level in cfg_data['日志配置']:
                                self._log_level_config[level] = cfg_data['日志配置'][level]
            except Exception:
                pass

        # 设置勾选框初始状态（会触发 stateChanged，自动初始化文件日志开关）
        self.log_file_checkBox.setChecked(initial_log_enabled)

        self.showMaximized()
        
        # 如果有默认配置文件，则获取
        if os.path.exists(self.default_config_path):
            self.update_run_info('存在默认配置文件，开始添加服务器和快捷按钮')
            self.load_server_config(self.default_config_path)
            self.load_sc_config(self.default_config_path)
        # 主界面服务器选择下拉表
        self.server_comboBox.setCurrentIndex(-1)
        self.update_server_combobox()
        self.update_run_info("OneClick 启动成功")

    def cmd1_dialog(self, button_id=None):
        """创建发送指令的窗口实例"""
        s_cmd_dlg = SendCMDDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_cmd_dlg.setWindowTitle('编辑<发送命令>配置')
            s_cmd_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下’生成快捷按钮‘按钮时调用accpted()，主窗口打印日志
        if s_cmd_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def cmd2_dialog(self, button_id=None):
        """创建发送指令的窗口实例"""
        s_cmd_dlg = SendCMD2Dialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_cmd_dlg.setWindowTitle('编辑<发送指令并接收回显>配置')
            s_cmd_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_cmd_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def send_file_dialog(self, button_id=None):
        s_file_dlg = SendFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_file_dlg.setWindowTitle('编辑<发送文件>配置')
            s_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def get_file_dialog(self, button_id=None):
        dialog = QDialog()
        g_file_dlg = GetFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            g_file_dlg.setWindowTitle('编辑<获取文件>配置')
            g_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if g_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def copy_file_dialog(self, button_id=None):
        copy_file_dlg = CopyFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            copy_file_dlg.setWindowTitle('编辑<复制本地文件>配置')
            copy_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if copy_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def resource_monitor_dialog(self, button_id=None):
        """创建资源监控的窗口实例"""
        r_monitor_dlg = ResourceMonitorDialog1(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            r_monitor_dlg.setWindowTitle('编辑<资源监控>配置')
            r_monitor_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下'生成快捷按钮'按钮时调用accpted()，主窗口打印日志
        if r_monitor_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

    def weak_net_dialog(self, button_id=None):
        """创建弱网的窗口实例"""
        w_net_dlg = WeakNetDialog1(parent=self)
        if button_id:
            w_net_dlg.setWindowTitle('编辑<弱网>配置')
            w_net_dlg.edit_sc(button_id)
        if w_net_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_type}>|<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑弱网快捷按钮')
            else:
                self.update_run_info('取消创建弱网快捷按钮')

    def server_cfg_dialog(self):
        s_cfg_dlg = SetServerDialog(parent=self)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_cfg_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            self.update_run_info('服务器列表编辑 成功')
        else:
            self.update_run_info('服务器列表编辑 取消')

    def add_button(self, config_data):
        """根据配置数据(dialog会将配置好的数据传递给主窗口)创建新按钮"""
        # 获取脚本名称作为按钮文本
        if '指令名称' in config_data:
            button_text = config_data['指令名称']
        else:
            button_text = f'新按钮{self.btn_count}'

        # 创建新按钮
        self.btn_count += 1
        button_id = f"button_{self.btn_count}"  # 唯一ID
        new_button = QPushButton(button_text)
        new_button.setObjectName(button_id)

        # 设置按钮样式
        new_button.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-size: 14px;
                margin: 5px;
                border-radius: 5px;
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                color: #3a8ee6;
                border-color: #3a8ee6;
                background-color: #ecf5ff;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #999999;
            }
        """)
        # 根据传入的快捷类型选择按钮点击连接的事件，并传入button_id参数
        if config_data['指令类型'] == '发送命令':
            new_button.clicked.connect(lambda _, para=button_id: self.click_send_cmd(para))
        elif config_data['指令类型'] == '发送命令并接收回显':
            new_button.clicked.connect(lambda _, para=button_id: self.click_send_cmd_print(para))
        elif config_data['指令类型'] == '发送文件':
            new_button.clicked.connect(lambda _, para=button_id: self.click_send_files(para))
        elif config_data['指令类型'] == '获取文件':
            new_button.clicked.connect(lambda _, para=button_id: self.click_get_files(para))
        elif config_data['指令类型'] == '复制本地文件':
            new_button.clicked.connect(lambda _, para=button_id: self.click_copy_files(para))
        elif config_data['指令类型'] == '资源监控':
            new_button.clicked.connect(lambda _, para=button_id: self.resource_monitor(para))
        elif config_data['指令类型'] == '弱网':
            new_button.clicked.connect(lambda _, para=button_id: self.weak_net(para))
        else:
            self.update_run_info(f'添加快捷按钮{button_text}失败:错误的指令类型', 'ERROR')
            return
        # 在按钮上添加右键菜单，pos参数为鼠标坐标，系统自动获取
        new_button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        new_button.customContextMenuRequested.connect(
            lambda pos, btn_id=button_id: self.show_button_context_menu(pos, btn_id))

        # 添加到主窗口
        self.button_layout.addWidget(new_button)

        # 将新建的快捷按钮添加到快捷按钮字典
        self.sc_buttons[button_id] = {'button': new_button, 'config': config_data}

    def edit_button(self, config_data, button_id):
        self.sc_buttons[button_id]['config'].update(config_data)  # 更新按钮字典内容
        btn = self.sc_buttons[button_id]['button']  # 按钮对象
        btn.setText(config_data['指令名称'])  # 修改按钮名称

    def click_send_cmd(self, button_id):
        """发送指令"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'<{button_name}>开始执行')
        self.sc_buttons[button_id]['button'].setEnabled(False)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}>执行失败:{e}', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            return

        def execute_send_cmd_flow(cmd):
            """执行发送指令流程连接→发送→断开"""
            # 连接SSH
            connect_result = ssh_tool.connect()
            if not connect_result:
                return False

            # 发送指令
            send_result = ssh_tool.send_command(cmd)

            # 断开连接
            disconnect_result = ssh_tool.disconnect()

            if not send_result:
                return False
            if not disconnect_result:
                return False
            return True

        def on_worker_finished(result):
            """worker结束处理界面"""
            if result:
                self.update_run_info(f'<{button_name}>执行成功')
            else:
                self.update_run_info(f'<{button_name}>执行失败', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            thread.quit()

        def on_thread_finished():
            """线程结束清理资源"""
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            execute_send_cmd_flow, # 封装完整流程
            self.sc_buttons[button_id]['config']['指令']
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中，一定要先移动再绑信号槽，不然会绑定到主线程
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.log_signal.connect(self.update_run_info)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker
        }

        thread.start()

    def click_send_cmd_print(self, button_id):
        """发送指令并回显打印到界面"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'<{button_name}>开始执行')
        self.sc_buttons[button_id]['button'].setEnabled(False)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<<{button_name}>>执行失败:{e}', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            return

        # 封装指令发送和回显接收方法
        def send_cmd_and_receive_echo(cmd, echo_signal):
            c_result = ssh_tool.connect()
            if not c_result:
                return False
            ssh_tool.send_command_interactive(cmd)
            g_result = ssh_tool.get_output_continue(echo_signal=echo_signal)
            ssh_tool.disconnect()
            return g_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            # 不要在worker里deleteLater自己，会被放到worker的线程中执行
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(send_cmd_and_receive_echo)
        worker.kwargs = {
            "cmd" : self.sc_buttons[button_id]['config']['指令'],
            "echo_signal": worker.echo_signal
        }

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定信号槽
        worker.log_signal.connect(self.update_run_info)
        worker.echo_signal.connect(self.update_linux_print)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存worker和线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker
        }

        thread.start()

    def click_send_files(self, button_id):
        """发送文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'<<{button_name}>>开始执行')
        self.sc_buttons[button_id]['button'].setEnabled(False)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<<{button_name}>>执行失败:{e}', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            return

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        local_path = self.sc_buttons[button_id]['config']['本地路径']
        remote_path = self.sc_buttons[button_id]['config']['服务器路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']
        work_dir = self.sc_buttons[button_id]['config']['文件暂存路径']

        def execute_send_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            s_result = ssh_tool.send_files(local_path, remote_path, mtime, filename, work_dir)

            ssh_tool.disconnect()

            return s_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(execute_send_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.log_signal.connect(self.update_run_info)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker
        }

        thread.start()

    def click_get_files(self, button_id):
        """下载文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'<<{button_name}>>开始执行')
        self.sc_buttons[button_id]['button'].setEnabled(False)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<<{button_name}>>执行失败:{e}', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            return

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        # 将本地路径的"当前路径/时间IP(例:20251024031415-1.1.1.1)/"修改为当前时间当前路径
        if self.sc_buttons[button_id]['config']['本地路径'] == "当前路径/时间IP(例:20251024031415-1.1.1.1)/":
            current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            local_path = self.get_default_path() + '/' + current_time + '-' + self.sc_buttons[button_id]['config'][
                'IP']
            os.mkdir(local_path)
        else:
            local_path = self.sc_buttons[button_id]['config']['本地路径']

        remote_path = self.sc_buttons[button_id]['config']['服务器路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']
        work_dir = self.sc_buttons[button_id]['config']['文件暂存路径']

        def execute_get_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            g_result = ssh_tool.get_files(remote_path, local_path, mtime, filename, work_dir)

            ssh_tool.disconnect()

            return g_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(execute_get_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.log_signal.connect(self.update_run_info)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker
        }

        thread.start()

    def click_copy_files(self, button_id):
        """打包复制文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'<<{button_name}>>开始执行')
        self.sc_buttons[button_id]['button'].setEnabled(False)

        # 初始化WindowsTools
        win_tool = windows_tools.WindowsTools()

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        # 将复制到的"当前路径/当前时间(例:20251024031415)/"修改为当前路径/当前时间
        if self.sc_buttons[button_id]['config']['复制到'] == "当前路径/当前时间(例:20251024031415)/":
            current_time = datetime.datetime.now().strftime("%Y_%m%d_%H%M%S")
            target_path = self.get_default_path() + '/' + current_time
            os.mkdir(target_path)
        else:
            target_path = self.sc_buttons[button_id]['config']['复制到']

        resource_path = self.sc_buttons[button_id]['config']['源路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']

        def execute_copy_files():
            cp_result = win_tool.copy_files(resource_path, target_path, mtime, filename)
            return cp_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败', 'ERROR')
            self.sc_buttons[button_id]['button'].setEnabled(True)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(execute_copy_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.log_signal.connect(self.update_run_info)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": win_tool,
            "thread": thread,
            "worker": worker
        }

        thread.start()

    def resource_monitor(self, button_id):
        """按下快捷键时调用，打开资源监控配置的窗口，按传入的button_id参数来获取服务器IP等内容"""
        if button_id in self.sc_buttons:
            self.sc_buttons[button_id]['button'].setEnabled(False)
            # 打开资源监控的子窗口，需要将buttonid传入
            monitor_set_dlg = ResourceMonitorDialog2(button_id, self)
            if self.sc_buttons[button_id]['config']['IP'] == '':
                monitor_set_dlg.setWindowTitle('本机<资源监控>控制面板')
            else:
                monitor_set_dlg.setWindowTitle(f"{self.sc_buttons[button_id]['config']['IP']}<资源监控>控制面板")
            # 显示弹出窗口
            result = monitor_set_dlg.exec_()
            # 关闭窗口时主界面按钮恢复
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                self.sc_buttons[button_id]['button'].setEnabled(True)

    def weak_net(self, button_id):
        """按下快捷键时调用，打开弱网控制面板"""
        if button_id in self.sc_buttons:
            self.sc_buttons[button_id]['button'].setEnabled(False)
            weak_net_dlg = WeakNetControlDialog(button_id, self)
            ip = self.sc_buttons[button_id]['config']['IP']
            if ip == '':
                weak_net_dlg.setWindowTitle('本机<弱网>控制面板')
            else:
                weak_net_dlg.setWindowTitle(f"{ip}<弱网>控制面板")
            result = weak_net_dlg.exec_()
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                self.sc_buttons[button_id]['button'].setEnabled(True)

    def _on_log_file_checkbox_changed(self, state):
        """日志勾选框状态变化：控制文件日志开关"""
        import logging.handlers
        enable = (state == QtCore.Qt.Checked)
        root_logger = logging.getLogger()

        # 先移除所有已存在的文件 handler
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.close()
                root_logger.removeHandler(handler)

        if enable:
            # 添加文件 handler
            log_dir = self.get_default_path()
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                filename=os.path.join(log_dir, "OneClick.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
            file_handler.setFormatter(fmt)
            
            # 添加过滤器：只写入配置中开启的日志级别
            def log_filter(record):
                level_name = record.levelname
                # 映射日志级别名称
                level_map = {
                    'DEBUG': 'DEBUG',
                    'INFO': 'INFO',
                    'WARNING': 'WARNING',
                    'ERROR': 'ERROR',
                    'CRITICAL': 'ERROR',
                }
                config_key = level_map.get(level_name, level_name)
                # 检查该级别是否开启（默认不输出，避免配置丢失导致日志错乱）
                return self._log_level_config.get(config_key, False)
            
            file_handler.addFilter(log_filter)
            root_logger.addHandler(file_handler)
            self.update_run_info("文件日志已开启")
        else:
            self.update_run_info("文件日志已关闭")

    def update_run_info(self, text, level='INFO'):
        """同步显示到UI（带颜色），同时发给logger写文件

        Args:
            text: 要显示的文本
            level: 日志级别，可选值 INFO / WARNING / ERROR
        """
        # 根据级别设置颜色
        color_map = {
            'INFO': '#000000',
            'WARNING': '#FF8C00',
            'ERROR': '#FF0000',
        }
        color = color_map.get(level.upper(), '#000000')

        # HTML 转义：防止 < > & 等特殊字符被解析成标签
        html_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # 1. 加时间戳后显示到UI（带颜色）
        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html = f'<span style="color: {color}">{formatted_datetime} {html_text}</span>'
        self.run_info_browser.append(html)

        # 2. 滚动条置底
        self.run_info_browser.verticalScrollBar().setValue(
            self.run_info_browser.verticalScrollBar().maximum()
        )
        self.run_info_browser.horizontalScrollBar().setValue(
            self.run_info_browser.horizontalScrollBar().minimum()
        )

        # 3. 发给logger（如果开启了文件日志，会写入文件）
        if hasattr(self, 'logger'):
            level_upper = level.upper()
            if level_upper == 'WARNING':
                self.logger.warning(text)
            elif level_upper == 'ERROR':
                self.logger.error(text)
            else:
                self.logger.info(text)

    def update_linux_print(self, text, insert=False):
        if insert:
            # 获取当前文本控件的光标
            cursor = self.linux_print_browser.textCursor()
            # 将光标移动到文档末尾
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            # 应用移动后的光标
            self.linux_print_browser.setTextCursor(cursor)
            self.linux_print_browser.insertPlainText(text)
        else:
            # 将输出添加到linux_print_browser
            self.linux_print_browser.append(text)
        # 滚动到底部
        self.linux_print_browser.verticalScrollBar().setValue(
            self.linux_print_browser.verticalScrollBar().maximum()
        )
        # 水平滚动条到头部
        self.linux_print_browser.horizontalScrollBar().setValue(
            self.linux_print_browser.horizontalScrollBar().minimum()
        )

    def show_button_context_menu(self, pos, button_id):
        menu = QMenu()
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")

        action = menu.exec(self.sc_buttons[button_id]['button'].mapToGlobal(pos))

        # 处理菜单选择
        if action == delete_action:
            self.delete_button(button_id)
        elif action == edit_action:
            self.edit_button_dialog(button_id)

    def delete_button(self, button_id):
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Icon.Question)
        confirm_dialog.setWindowTitle("确认")
        confirm_dialog.setText("是否要删除快捷按钮")
        confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = confirm_dialog.exec_()
        if result == QMessageBox.StandardButton.Yes:
            if button_id in self.sc_buttons:
                btn = self.sc_buttons[button_id]['button']
                sc_ty = self.sc_buttons[button_id]['config']['指令类型']
                btn_text = self.sc_buttons[button_id]['config']['指令名称']
                self.update_run_info(f"删除<{sc_ty}>|<{btn_text}>快捷按钮成功")
                btn.deleteLater()
                del self.sc_buttons[button_id]  # 只调用这个无法删除已经实例化并在界面显示的按钮，所以需要提前btn.deleteLater()
                # button_id为唯一标识，删除button后也不要减少数量
        else:
            self.update_run_info(f"删除按钮操作取消")

    def edit_button_dialog(self, button_id):
        if button_id in self.sc_buttons:
            ty_dialog = {
                '发送命令': self.cmd1_dialog,
                '发送命令并接收回显': self.cmd2_dialog,
                '发送文件': self.send_file_dialog,
                '获取文件': self.get_file_dialog,
                '复制本地文件': self.copy_file_dialog,
                '资源监控': self.resource_monitor_dialog,
                '弱网': self.weak_net_dialog,
            }
            sc_ty = self.sc_buttons[button_id]['config']['指令类型']
            dialog_func = ty_dialog.get(sc_ty)  # 假设指令类型是发送命令，dialog_func就是self.cmd1_dialog
            if dialog_func:
                dialog_func(button_id)  # 以编辑模式打开窗口，传入button_id
            else:
                self.update_run_info(f"编辑按钮出错：未知指令类型{sc_ty}", 'ERROR')

    def stop_sc(self):
        """耗时的指令手动中止方法"""
        # 首先防止重复按下中止键
        self.stop_pushButton.setEnabled(False)  # 禁用停止按钮
        # 检查是否有正在执行的线程
        if len(self.sc_threads) == 0:
            self.update_run_info('没有正在执行的指令', 'WARNING')
            self.stop_pushButton.setEnabled(True)
            return
        # 如果有，检查线程字典self.sc_threads，将所有线程结束
        for thread in self.sc_threads:
            # 检查是否有tool
            if 'tool' in self.sc_threads[thread]:
                # 检查tool是否是ssh_tools.SSHTools类型
                if type(self.sc_threads[thread]['tool']) == ssh_tools.SSHTools:
                    # 检查是否有连接，如果有连接，发送中止信号，设置传输位=0
                    if self.sc_threads[thread]['tool'].is_connected():
                        self.sc_threads[thread]['tool'].send_command_interactive(chr(3))
                        self.sc_threads[thread]['tool'].transfer_stat = 0
                        self.sc_threads[thread]['tool'].win_tool.transfer_stat = 0
                elif type(self.sc_threads[thread]['tool']) == windows_tools.WindowsTools:
                    self.sc_threads[thread]['tool'].transfer_stat = 0
            else:
                continue
        self.update_run_info('已发送中止请求，请等待')
        self.stop_pushButton.setEnabled(True)

    def clean_linux_print(self):
        self.linux_print_browser.clear()
        self.update_run_info(f"服务器回显区已清空")

    def get_default_path(self):
        # 获取可执行文件（.exe）本身所在的路径，不包含自己的名称
        if getattr(sys, 'frozen', False):
            # 打包后的环境：sys.executable指向.exe文件
            executable_path = sys.executable
        else:
            # 未打包的环境：使用原来的__file__
            executable_path = os.path.realpath(__file__)
        # 获取可执行文件所在的目录
        current_path = os.path.dirname(executable_path)
        # 格式化路径全部左斜
        current_path = current_path.replace('\\', '/')
        return current_path

    def save_config(self):
        """菜单-保存"""
        self.save_config_to(self.default_config_path)

    def save_config_to(self, path):
        """保存功能调用，如果点击菜单-另存为按钮来调用时，传入的是False，弹出对话框"""
        if not path:
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            # 关键：禁用系统原生对话框，强制使用Qt风格
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            # 设置为保存模式
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            # 设置默认文件名和文件类型
            dialog.setDefaultSuffix("json")  # 自动补充.json后缀
            dialog.selectFile("自定义配置")  # 默认文件名
            dialog.setNameFilter("JSON Files (*.json)")
            # 显示对话框并处理结果
            if dialog.exec_():
                # 获取选中的完整路径
                file_path = dialog.selectedFiles()[0]
                # 确保后缀正确
                if not file_path.endswith('.json'):
                    file_path += '.json'
            else:
                self.update_run_info(f"另存为配置 取消")
                return
        else:
            file_path = path
        # 获取所有配置
        cfg_dic = {}
        server_count = 1
        button_count = 1
        for server in self.servers_cfg:
            cfg_dic[f'服务器{server_count}'] = server
            server_count += 1
        for button in self.sc_buttons:
            cfg_dic[f'快捷按钮{button_count}'] = self.sc_buttons[button]['config']
            button_count += 1
        if len(self.commands) != 0:
            cfg_dic['指令'] = self.commands
        # 保存日志配置
        # 如果配置文件已存在，读取原有的日志级别配置并保留
        existing_log_cfg = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    old_cfg = json.load(f)
                    if '日志配置' in old_cfg:
                        existing_log_cfg = old_cfg['日志配置']
            except Exception:
                pass
        
        # 构建新的日志配置
        new_log_cfg = {
            '文件日志': self.log_file_checkBox.isChecked()
        }
        # 如果已有级别配置，保留；否则设置默认值（DEBUG=False，其他=True）
        if 'DEBUG' in existing_log_cfg:
            new_log_cfg['DEBUG'] = existing_log_cfg['DEBUG']
            new_log_cfg['INFO'] = existing_log_cfg.get('INFO', True)
            new_log_cfg['WARNING'] = existing_log_cfg.get('WARNING', True)
            new_log_cfg['ERROR'] = existing_log_cfg.get('ERROR', True)
        else:
            new_log_cfg['DEBUG'] = False
            new_log_cfg['INFO'] = True
            new_log_cfg['WARNING'] = True
            new_log_cfg['ERROR'] = True
        
        cfg_dic['日志配置'] = new_log_cfg

        # 写入到json文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cfg_dic, f, ensure_ascii=False, indent=4)
            self.update_run_info(f"已保存配置到{os.path.abspath(file_path)}")

    def load_sc_config(self, path):
        """启动时如果有默认配置会调用，传入默认配置路径，手动点的时候传入的是False，弹出对话框"""
        if not path:
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            #  使用Qt自带的对话框,保持风格一致
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

            # 设置文件过滤器，只显示JSON文件
            # 格式："描述 (*.扩展名)"，多个类型用;;分隔
            dialog.setNameFilter("JSON Files (*.json)")

            # 可以设置默认文件后缀，当用户输入无后缀的文件名时自动添加
            dialog.setDefaultSuffix("json")

            # 显示对话框并检查用户是否点击了打开按钮
            if dialog.exec_():
                # 如果用户选择了文件，返回文件路径
                file_path = dialog.selectedFiles()[0]
            else:
                self.update_run_info('批量添加快捷按钮 取消')
                return
        else:
            file_path = path
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 将内容中的\替换为/
            processed_content = content.replace("\\", "/")
            # 解析处理后的内容
            data = json.loads(processed_content)
        for key in data:
            if '服务器' in key:
                continue
            elif '快捷按钮' in key:
                self.add_button(data[key])
            elif '指令' in key:
                for cmd in data[key]:  # data[key]=['top','pwd']
                    self.commands.append(cmd)
                    self.cmd_comboBox.addItem(cmd, cmd)
                self.update_run_info(f"批量添加指令 成功，来自{file_path}")
                self.cmd_comboBox.setCurrentIndex(-1)
            elif key == '日志配置':
                log_cfg = data[key]
                if log_cfg.get('文件日志', False):
                    self.log_file_checkBox.setChecked(True)
                else:
                    self.log_file_checkBox.setChecked(False)
                # 读取日志级别配置（如果有）
                for level in self._log_level_config:
                    if level in log_cfg:
                        self._log_level_config[level] = log_cfg[level]
            else:
                self.update_run_info(f'{key}无法识别的数据类型', 'WARNING')
        self.update_run_info(f"批量添加快捷按钮 成功，来自{file_path}")

    def load_server_config(self, path):
        """启动时如果有默认配置会调用，传入默认配置路径，手动点的时候传入的是False，弹出对话框"""
        if not path:  # 手动点的情况
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            # 使用Qt自带的对话框,保持风格一致
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

            # 设置文件过滤器，只显示JSON文件
            # 格式："描述 (*.扩展名)"，多个类型用;;分隔
            dialog.setNameFilter("JSON Files (*.json)")

            # 可以设置默认文件后缀，当用户输入无后缀的文件名时自动添加
            dialog.setDefaultSuffix("json")

            # 显示对话框并检查用户是否点击了打开按钮
            if dialog.exec_():
                # 如果用户选择了文件，返回文件路径
                file_path = dialog.selectedFiles()[0]
            else:
                self.update_run_info('批量添加服务器 取消')
                return
        else:
            file_path = path
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 将内容中的\替换为/
            processed_content = content.replace("\\", "/")
            # 解析处理后的内容
            data = json.loads(processed_content)
        for key in data:
            if '服务器' in key:
                self.servers_cfg.append(data[key])
            else:
                continue
        self.update_run_info(f"批量添加服务器 成功，来自{file_path}")

    def is_config_changed(self, path):
        if not os.path.exists(path):
            file_cfg = {}

        # 读取文件中的配置
        try:
            with open(path, 'r', encoding='utf-8') as f:
                file_cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            file_cfg = {}

        # 生成当前界面中的配置
        current_cfg = {}
        server_count = 1
        button_count = 1
        for server in self.servers_cfg:
            current_cfg[f'服务器{server_count}'] = server
            server_count += 1
        for button in self.sc_buttons:
            current_cfg[f'快捷按钮{button_count}'] = self.sc_buttons[button]['config']
            button_count += 1
        if len(self.commands) != 0:
            current_cfg['指令'] = self.commands
        # 加入日志配置状态
        # 如果文件中已有日志级别配置，保留；否则用内存中的配置
        current_log_cfg = {
            '文件日志': self.log_file_checkBox.isChecked()
        }
        if '日志配置' in file_cfg and 'DEBUG' in file_cfg['日志配置']:
            # 保留文件中的日志级别配置
            current_log_cfg['DEBUG'] = file_cfg['日志配置']['DEBUG']
            current_log_cfg['INFO'] = file_cfg['日志配置'].get('INFO', True)
            current_log_cfg['WARNING'] = file_cfg['日志配置'].get('WARNING', True)
            current_log_cfg['ERROR'] = file_cfg['日志配置'].get('ERROR', True)
        else:
            # 用内存中的配置（首次保存）
            current_log_cfg['DEBUG'] = self._log_level_config['DEBUG']
            current_log_cfg['INFO'] = self._log_level_config['INFO']
            current_log_cfg['WARNING'] = self._log_level_config['WARNING']
            current_log_cfg['ERROR'] = self._log_level_config['ERROR']
        current_cfg['日志配置'] = current_log_cfg

        # 直接比较两个字典是否完全相等
        return current_cfg != file_cfg

    def update_server_combobox(self):
        self.server_comboBox.clear()
        for server in self.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)

    def connect_server(self):
        if self.connect_pushButton.text() == '连接':
            if self.server_comboBox.currentIndex() == -1:
                self.update_run_info(f'请先选择服务器', 'WARNING')
                return
            self.connect_pushButton.setEnabled(False)
            self.server_comboBox.setEnabled(False)
            self.current_ssh['config'] = self.server_comboBox.currentData()

            # 创建一个ssh连接对象，给对象初始化属性
            ssh_tool = ssh_tools.SSHTools()
            # 初始化属性
            try:
                ssh_tool.ip = self.current_ssh['config']['IP']
                ssh_tool.port = self.current_ssh['config']['端口']
                ssh_tool.username = self.current_ssh['config']['用户名']
                ssh_tool.password = self.current_ssh['config']['密码']
            except Exception as e:
                self.update_run_info(f'请检查服务器ssh连接配置{e}', 'ERROR')
                self.connect_pushButton.setEnabled(True)
                self.server_comboBox.setEnabled(True)
                return

            def update_connect_button(data):
                """data[0]=text, data[1]=True"""
                self.connect_pushButton.setText(data[0])
                self.connect_pushButton.setEnabled(data[1])

            # 封装指令发送和回显接收方法
            def current_ssh(echo_signal):
                c_result = ssh_tool.connect()
                if not c_result:
                    return False
                worker.info_signal.emit(('断开',True))
                g_result = ssh_tool.get_output_continue(timeout=float('inf'), echo_signal=echo_signal)
                return g_result

            def on_worker_finished():
                update_connect_button(('连接',True))
                self.server_comboBox.setEnabled(True)
                # 不要在worker里deleteLater自己，会被放到worker的线程中执行
                thread.quit()

            def on_thread_finished():
                worker.deleteLater()
                thread.deleteLater()
                self.current_ssh.clear()

            # 初始化worker
            worker = qthread_worker.OneClickWorker(current_ssh)
            worker.kwargs = {
                "echo_signal": worker.echo_signal
                }

            # 初始化线程
            thread = QThread()

            # 将worker移动到线程中
            worker.moveToThread(thread)

            # 绑定信号槽
            worker.log_signal.connect(self.update_run_info)
            worker.echo_signal.connect(lambda text: self.update_linux_print(text, insert=True))
            worker.info_signal.connect(update_connect_button)
            worker.finished.connect(on_worker_finished)

            # 绑定线程信号槽
            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    "tool": ssh_tool,
                    "send_count": 0,
                    "task_connect": (thread, worker)
                }
            )

            thread.start()

        else:
            if not self.current_ssh['tool'].is_connected():
                self.connect_pushButton.setText('连接')
                self.connect_pushButton.setEnabled(True)
                self.server_comboBox.setEnabled(True)
                return
            # 初始化worker
            worker = qthread_worker.OneClickWorker(self.current_ssh['tool'].disconnect)

            # 初始化线程
            thread = QThread()

            # 将worker移动到线程中
            worker.moveToThread(thread)

            # 绑定信号槽
            worker.log_signal.connect(self.update_run_info)
            worker.finished.connect(thread.quit)

            # 绑定线程信号槽
            thread.started.connect(worker.run_task)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    "task_disconnect": (thread, worker)
                }
            )
            thread.start()

    def send_cmd(self):
        if self.connect_pushButton.text() == '断开':
            self.current_ssh['send_count'] += 1
            cmd = self.cmd_plainTextEdit.toPlainText()

            worker = qthread_worker.OneClickWorker(self.current_ssh['tool'].send_command_interactive, cmd)
            thread = QThread()
            worker.moveToThread(thread)

            worker.log_signal.connect(self.update_run_info)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(thread.quit)

            thread.started.connect(worker.run_task)
            thread.finished.connect(thread.deleteLater)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    f"task_send_{self.current_ssh['send_count']}": (thread, worker)
                }
            )
            thread.start()
        else:
            self.update_run_info('请先建立ssh连接', 'WARNING')
        self.cmd_plainTextEdit.clear()

    def save_cmd(self):
        cmd = self.cmd_plainTextEdit.toPlainText()
        if cmd == '':
            self.update_run_info('请输入指令内容', 'WARNING')
        else:
            self.cmd_comboBox.addItem(cmd)
            self.commands.append(cmd)
            self.update_run_info(f'保存指令成功{cmd}')

    def del_cmd(self):
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Icon.Question)
        confirm_dialog.setWindowTitle("确认")
        confirm_dialog.setText("是否要删除指令")
        confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = confirm_dialog.exec_()
        current_index = self.cmd_comboBox.currentIndex()
        if current_index == -1:
            return
        current_text = self.cmd_comboBox.currentText()
        if result == QMessageBox.StandardButton.Yes:
            self.cmd_comboBox.removeItem(current_index)
            self.commands.remove(current_text)
            self.update_run_info(f'删除指令成功{current_text}')
        else:
            self.update_run_info(f'删除指令取消{current_text}')

    def select_cmd(self):
        cmd = self.cmd_comboBox.currentText()
        self.cmd_plainTextEdit.setPlainText(cmd)

    def keyPressEvent(self, event):
        # 处理 Ctrl+C 中断（插入 ^C 符号）
        if (event.key() == QtCore.Qt.Key.Key_C and
                event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier):
            event.accept()
            self.cmd_plainTextEdit.insertPlainText("^C")
            self.send_cmd()
            return

        # 处理回车键逻辑
        is_enter = event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
        if is_enter:
            if not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                # 单纯 Enter：发送
                event.accept()
                self.send_cmd()
                return
            # Shift+Enter：走默认换行逻辑，不拦截

        # 其他按键（包括 Shift+Enter）走默认逻辑
        QtWidgets.QPlainTextEdit.keyPressEvent(self.cmd_plainTextEdit, event)

    def closeEvent(self, event):
        """
        重写窗口关闭事件，弹出三按钮确认框
        """
        if self.is_config_changed(self.default_config_path):
            # 创建消息框实例
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("保存确认")
            msg_box.setText("当前配置未保存，是否保存更改后退出？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 添加三个按钮 (保存 / 不保存 / 取消)
            btn_save = msg_box.addButton("保存并退出", QMessageBox.ButtonRole.ActionRole)
            btn_discard = msg_box.addButton("不保存退出", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

            # 设置默认选中按钮（可选，比如默认选中"取消"比较安全）
            msg_box.setDefaultButton(btn_cancel)

            # 弹出对话框并等待用户点击
            msg_box.exec_()

            # 判断用户点击了哪个按钮
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == btn_save:
                # --- 点击了"保存" ---
                self.save_config()
                event.accept()
            elif clicked_btn == btn_discard:
                # --- 点击了"不保存" ---
                event.accept()
            else:
                # --- 点击了"取消" 或 关闭了对话框 ---
                event.ignore()
        else:
            # 配置没变动，直接退出
            event.accept()

    def show_help_dialog(self):
        """显示帮助文档对话框"""
        help_dialog = HelpDialog(self)
        help_dialog.exec_()


if __name__ == '__main__':
    pass
