import os.path
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QDialog, QPushButton, QWidget, QVBoxLayout, QMenu, QFileDialog, QMessageBox, \
    QDialogButtonBox, QAbstractItemView, QHeaderView, QTableWidgetItem, QMainWindow

from UI import MainWindow, send_cmd_dlg, send_files_dlg, get_files_dlg, copy_local_files_dlg, edit_servers_dlg, resource_monitor_dlg, weak_net_control_dlg
from utils import ssh_tools, windows_tools, qthread_worker
import GraphWindowLogic
import json
import datetime
import shutil
import subprocess
import psutil
import time

sc_class2str = {
    'SendCMDDialog': "发送命令",
    'SendCMD2Dialog': "发送命令并接收回显",
    'SendFilesDialog': "发送文件",
    'GetFilesDialog': "获取文件",
    'CopyFilesDialog': "复制本地文件",
    'ResourceMonitorDialog1': "资源监控",
    'WeakNetDialog1': "弱网"
}


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

        # 如果有默认配置文件，则获取
        if os.path.exists(self.default_config_path):
            self.update_run_info('存在默认配置文件，开始添加服务器和快捷按钮')
            self.load_server_config(self.default_config_path)
            self.load_sc_config(self.default_config_path)
        # 主界面服务器选择下拉表
        self.server_comboBox.setCurrentIndex(-1)
        self.update_server_combobox()
        self.showMaximized()

    def cmd1_dialog(self, button_id=None):
        """创建发送指令的窗口实例"""
        s_cmd_dlg = SendCMDDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_cmd_dlg.setWindowTitle('编辑<发送命令>配置')
            s_cmd_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下’生成快捷按钮‘按钮时调用accpted()，主窗口打印日志
        if s_cmd_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                self.update_run_info('<发送命令>快捷按钮编辑成功')
            else:
                self.update_run_info('<发送命令>快捷按钮创建成功')
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
                self.update_run_info('<发送指令并接收回显>快捷按钮编辑成功')
            else:
                self.update_run_info('<发送指令并接收回显>快捷按钮创建成功')
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
                self.update_run_info('<发送文件>快捷按钮编辑成功')
            else:
                self.update_run_info('<发送文件>快捷按钮创建成功')
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
                self.update_run_info('<获取文件>快捷按钮编辑成功')
            else:
                self.update_run_info('<获取文件>快捷按钮创建成功')
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
                self.update_run_info('<复制本地文件>快捷按钮编辑成功')
            else:
                self.update_run_info('<复制本地文件>快捷按钮创建成功')
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
                self.update_run_info('<资源监控>快捷按钮编辑成功')
            else:
                self.update_run_info('<资源监控>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')
        pass

    def weak_net_dialog(self, button_id=None):
        """创建弱网的窗口实例"""
        w_net_dlg = WeakNetDialog1(parent=self)
        if button_id:
            w_net_dlg.setWindowTitle('编辑<弱网>配置')
            w_net_dlg.edit_sc(button_id)
        if w_net_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                self.update_run_info('<弱网>快捷按钮编辑成功')
            else:
                self.update_run_info('<弱网>快捷按钮创建成功')
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
            self.update_run_info(f'添加快捷按钮{button_text}失败:错误的指令类型')
            return
        # 在按钮上添加右键菜单，pos参数为鼠标坐标，系统自动获取
        new_button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        new_button.customContextMenuRequested.connect(
            lambda pos, btn_id=button_id: self.show_button_context_menu(pos, btn_id))

        # 添加到主窗口
        self.button_layout.addWidget(new_button)

        # 将新建的快捷按钮添加到快捷按钮字典
        self.sc_buttons[button_id] = {'button': new_button, 'config': config_data}
        self.btn_count += 1
        self.update_run_info(f'添加快捷按钮{button_text}成功')

    def edit_button(self, config_data, button_id):
        self.sc_buttons[button_id]['config'].update(config_data)  # 更新按钮字典内容
        btn = self.sc_buttons[button_id]['button']  # 按钮对象
        btn.setText(config_data['指令名称'])  # 修改按钮名称

    def click_send_cmd(self, button_id):
        """发送指令"""
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
            self.update_run_info(f'<<{button_name}>>执行失败:{e}')
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
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败')
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
            self.update_run_info(f'<<{button_name}>>执行失败:{e}')
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
                self.update_run_info(f'<<{button_name}>>执行失败')
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
            self.update_run_info(f'<<{button_name}>>执行失败:{e}')
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

        def execute_send_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            s_result = ssh_tool.send_files(local_path, remote_path, mtime, filename)

            ssh_tool.disconnect()

            return s_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败')
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
            self.update_run_info(f'<<{button_name}>>执行失败:{e}')
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

        def execute_get_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            g_result = ssh_tool.get_files(remote_path, local_path, mtime, filename)

            ssh_tool.disconnect()

            return g_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<<{button_name}>>执行成功')
            else:
                self.update_run_info(f'<<{button_name}>>执行失败')
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
                self.update_run_info(f'<<{button_name}>>执行失败')
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

    def update_run_info(self, text):
        # 将输出添加到run_info_browser, 并打印时间戳
        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.run_info_browser.append(formatted_datetime + ' ' + text)

        # 延迟执行滚动条操作（等待UI初始化完成）
        def scroll_to_target():
            # 垂直滚动条到底部
            self.run_info_browser.verticalScrollBar().setValue(
                self.run_info_browser.verticalScrollBar().maximum()
            )
            # 水平滚动条到头部
            self.run_info_browser.horizontalScrollBar().setValue(
                self.run_info_browser.horizontalScrollBar().minimum()
            )

        # 0毫秒延迟 = 等待当前事件循环结束后执行
        QtCore.QTimer.singleShot(0, scroll_to_target)

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
                self.update_run_info(f"删除{btn.text()}成功")
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
                self.update_run_info('编辑按钮出错：未知指令类型')

    def stop_sc(self):
        """耗时的指令手动中止方法"""
        # 首先防止重复按下中止键
        self.stop_pushButton.setEnabled(False)  # 禁用停止按钮
        # 检查是否有正在执行的线程
        if len(self.sc_threads) == 0:
            self.update_run_info('没有正在执行的指令')
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
                        self.sc_threads[thread]['tool'].transfer_status = 0
                        self.sc_threads[thread]['tool'].win_tool.transfer_stat = 0
                elif type(self.sc_threads[thread]['tool']) == windows_tools.WindowsTools:
                    self.sc_threads[thread]['tool'].transfer_stat = 0
            else:
                continue
        self.update_run_info('已发送中止请求，请等待')
        self.stop_pushButton.setEnabled(True)

    def clean_linux_print(self):
        self.linux_print_browser.clear()
        self.update_run_info('服务器回显区已清空')

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
                self.update_run_info('另存为配置 取消')
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
            else:
                self.update_run_info(f'{key}无法识别的数据类型')
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
            elif '快捷按钮' in key:
                continue
            elif '指令' in key:
                continue
            else:
                self.update_run_info(f'{key}无法识别的数据类型')
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
                self.update_run_info(f'请先选择服务器')
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
                self.update_run_info(f'请检查服务器ssh连接配置{e}')
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
            self.update_run_info('请先建立ssh连接')
        self.cmd_plainTextEdit.clear()

    def save_cmd(self):
        cmd = self.cmd_plainTextEdit.toPlainText()
        if cmd == '':
            self.update_run_info('请输入指令内容')
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


class SendCMDDialog(QDialog, send_cmd_dlg.Ui_Dialog):
    """初始化对象时，需要传入主窗口，因为按下生成快捷方式的按钮后需要主窗口调用添加快捷按钮的方法"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 保存对话框的所有配置项
        self.sc_cfg = {}

        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        # 将服务器列表加载到下拉选择框
        for server in self.parent.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)
        self.server_comboBox.activated.connect(self.select_server)

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
                return
        if not self.cmd_TextEdit.toPlainText().strip():
            self.cmd_TextEdit.setStyleSheet("QPlainTextEdit { border: 2px solid red; }")
            return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['指令'] = self.cmd_TextEdit.toPlainText()
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()

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
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.cmd_TextEdit.setPlainText(sc_data['指令'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])

    def reset(self):
        self.server_comboBox.setCurrentIndex(-1)
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.cmd_TextEdit.clear()
        self.sc_name_lineEdit.clear()

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())


class SendCMD2Dialog(SendCMDDialog):
    """继承SendCMDDialog，仅需要修改窗口的标题"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加<发送命令并接收回显>配置")


class SendFilesDialog(QDialog, send_files_dlg.Ui_Dialog):
    """初始化对象时，需要传入主窗口，因为按下生成快捷按钮按钮后需要主窗口调用添加快捷按钮的方法"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 保存对话框的所有配置项
        self.sc_cfg = {}

        self.local_path_pushButton.clicked.connect(self.select_path)
        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        for server in self.parent.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)
        self.server_comboBox.activated.connect(self.select_server)
        # 创建时间下拉菜单的选项字典，因为编辑按钮时传入的是str，需要将str对应为下拉的索引
        self.time_dic = {}
        for index in range(self.time_comboBox.count()):
            text = self.time_comboBox.itemText(index)
            self.time_dic[text] = index

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

    def reset(self):
        self.server_comboBox.clear()
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.local_path_pushButton.setText('请选择')
        self.time_comboBox.setCurrentIndex(0)
        self.filename_lineEdit.clear()
        self.server_path_lineEdit.clear()
        self.sc_name_lineEdit.clear()

    def select_path(self):
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
                self.local_path_pushButton.setText(file_paths[0])
                self.local_path_pushButton.setToolTip(file_paths[0])
                self.local_path_pushButton.setToolTipDuration(10000)
                return
        # 如果用户未选择任何文件，返回当前文件夹路径
        current_dir = dialog.directory().absolutePath()
        self.local_path_pushButton.setText(current_dir)
        self.local_path_pushButton.setToolTip(current_dir)
        self.local_path_pushButton.setToolTipDuration(10000)

    def select_server(self, index):
        self.linux_ip_lineEdit.setText(self.server_comboBox.currentData()['IP'])
        self.sshport_lineEdit.setText(self.server_comboBox.currentData()['端口'])
        self.username_lineEdit.setText(self.server_comboBox.currentData()['用户名'])
        self.passwd_lineEdit.setText(self.server_comboBox.currentData()['密码'])
        self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())


class GetFilesDialog(QDialog, get_files_dlg.Ui_Dialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.parent = parent

        # 保存对话框的所有配置项
        self.sc_cfg = {}

        self.local_path_pushButton.clicked.connect(self.select_path)
        self.save_pushButton.clicked.connect(self.create_sc)
        self.reset_pushButton.clicked.connect(self.reset)
        self.close_pushButton.clicked.connect(self.close)
        for server in self.parent.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)
        self.server_comboBox.activated.connect(self.select_server)
        # 创建时间下拉菜单的选项字典，因为编辑按钮时传入的是str，需要将str对应为下拉的索引
        self.time_dic = {}
        for index in range(self.time_comboBox.count()):
            text = self.time_comboBox.itemText(index)
            self.time_dic[text] = index

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

    def reset(self):
        self.server_comboBox.clear()
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
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


class ResourceMonitorDialog1(SendCMDDialog):
    """继承SendCMDDialog，需要修改窗口的标题，删除指令内容，调整窗口大小"""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("添加<资源监控>配置")
        self.resize(420, 230)
        # 移除指令输入框
        self.label_7.setParent(None)
        self.label_7.deleteLater()
        self.cmd_TextEdit.setParent(None)
        self.cmd_TextEdit.deleteLater()

        # 在服务器列表增加一个本机的选项
        self.server_comboBox.addItem('本机', '本机')
        self.server_comboBox.setCurrentIndex(-1)

    def create_sc(self):
        text_list = [
            self.linux_ip_lineEdit,
            self.username_lineEdit,
            self.passwd_lineEdit,
            self.sshport_lineEdit,
            self.sc_name_lineEdit
        ]
        # 每次点生成快捷方式按钮时，都先初始话所有输入框的样式
        for t in text_list:
            t.setStyleSheet("")

        # 如果选择了本机，只校验sc_name_lineEdit
        if self.server_comboBox.currentData() == '本机':
            if not self.sc_name_lineEdit.text().strip():
                self.sc_name_lineEdit.setStyleSheet("QLineEdit { border: 2px solid red; }")
                return
        # 如果选择了服务器，校验所有字段
        else:
            # 如果有输入框为空，则高亮显示
            for t in text_list:
                if not t.text().strip():
                    t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                    return

        # 将输入框内容保存到字典
        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['进程'] = ""
        self.sc_cfg['采样频率'] = ""
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()

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
        sc_data = self.parent.sc_buttons[button_id]['config']
        if sc_data['IP'] == '':
            item_count = self.server_comboBox.count()
            self.server_comboBox.setCurrentIndex(item_count - 1)
            self.sshport_lineEdit.clear()
            self.linux_ip_lineEdit.setEnabled(False)
            self.username_lineEdit.setEnabled(False)
            self.passwd_lineEdit.setEnabled(False)
            self.sshport_lineEdit.setEnabled(False)
        else:
            self.linux_ip_lineEdit.setText(sc_data['IP'])
            self.sshport_lineEdit.setText(sc_data['端口'])
            self.username_lineEdit.setText(sc_data['用户名'])
            self.passwd_lineEdit.setText(sc_data['密码'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])

    def reset(self):
        self.server_comboBox.setCurrentIndex(-1)
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.sc_name_lineEdit.clear()
        self.linux_ip_lineEdit.setEnabled(True)
        self.username_lineEdit.setEnabled(True)
        self.passwd_lineEdit.setEnabled(True)
        self.sshport_lineEdit.setEnabled(True)

    def select_server(self, index):
        if self.server_comboBox.currentData() == '本机':
            self.linux_ip_lineEdit.clear()
            self.username_lineEdit.clear()
            self.passwd_lineEdit.clear()
            self.sshport_lineEdit.clear()
            self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
            self.linux_ip_lineEdit.setEnabled(False)
            self.username_lineEdit.setEnabled(False)
            self.passwd_lineEdit.setEnabled(False)
            self.sshport_lineEdit.setEnabled(False)
        else:
            super().select_server(index)
            self.linux_ip_lineEdit.setEnabled(True)
            self.username_lineEdit.setEnabled(True)
            self.passwd_lineEdit.setEnabled(True)
            self.sshport_lineEdit.setEnabled(True)


class ResourceMonitorDialog2(QDialog, resource_monitor_dlg.Ui_Dialog):
    def __init__(self, button_id, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.button_id = button_id
        self.parent = parent
        self.g_windows = []  # 保存所有图表窗口的引用
        from monitor_scripts import MONITOR_SH, MONITOR_PS1
        self.monitor_sh = MONITOR_SH
        self.monitor_ps1 = MONITOR_PS1

        # （脚本内容已移到 monitor_scripts.py 中）
        # （脚本内容已移到 monitor_scripts.py 中）

        # 按钮逻辑和窗口默认值
        self.process_input_plainTextEdit.setPlainText(self.parent.sc_buttons[button_id]['config']['进程'])
        self.freq_lineEdit.setText(self.parent.sc_buttons[button_id]['config']['采样频率'])
        self.start_pushButton.clicked.connect(self.start_monitor)
        self.stop_pushButton.clicked.connect(self.stop_monitor)
        self.clean_pushButton.clicked.connect(self.clean_data)
        self.watch_pushButton.clicked.connect(self.display_resource)
        self.download_pushButton.clicked.connect(self.download_data)

        self.work_thread_id = None # 用于发送指令、文件等
        self.lookup_thread_id = None # 用于实时检查ssh连接状态和监控状态

        self.closeEvent = self.on_close_event
        self._can_close = True  # 用于阻止关闭窗口
        self.stop_flag = False  # 用于停止定时获取监控状态

        # 用于保存数据的根目录名称 本机或IP
        if self.parent.sc_buttons[button_id]['config']['IP'] == '':
            self.data_dir_name = 'local'
            self.on_local_button_click()
        else:
            self.data_dir_name = self.parent.sc_buttons[button_id]['config']['IP']
            self.on_ssh_button_click()

        self.monitor_data_path = os.path.join(self.parent.get_default_path(), f"{self.data_dir_name}").replace('\\','/')

    def on_local_button_click(self):
        self.update_status(('本机', '未知'))

        script_name = "OneClickMonitor.ps1"

        def get_powershell_pids(s_name):
            while True:
                if self.stop_flag:
                    return
                time.sleep(1)
                pids = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        name = proc.info['name']
                        if name and name.lower() in ('powershell.exe', 'pwsh.exe'):
                            cmdline = proc.info['cmdline']
                            if cmdline and any(s_name in arg for arg in cmdline):
                                # 排除自身调用的那个命令
                                if not any('-Command' in arg for arg in cmdline):
                                    pids.append(str(proc.info['pid']))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if not pids:
                    worker.info_signal.emit(f'无监控')
                else:
                    worker.info_signal.emit('监控中')

        def on_thread_finished():
            thread.deleteLater()
            self.parent.sc_threads.pop(self.lookup_thread_id)
            self.lookup_thread_id = None

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            get_powershell_pids,
            script_name
        )

        # 初始化线程
        thread = QThread()

        # 保存线程和worker
        self.parent.thread_count += 1
        self.lookup_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.lookup_thread_id] = {
            'worker': worker,
            'thread': thread
        }

        # worker移动到线程
        worker.moveToThread(thread)

        # 连接信号和槽
        worker.log_signal.connect(lambda :None)
        worker.info_signal.connect(self.monitor_stutas_label.setText)
        worker.finished.connect(worker.deleteLater)

        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def on_ssh_button_click(self):
        self.update_status(('连接中...', '未知'))

        ip = self.parent.sc_buttons[self.button_id]['config']['IP']
        port = self.parent.sc_buttons[self.button_id]['config']['端口']
        username = self.parent.sc_buttons[self.button_id]['config']['用户名']
        password = self.parent.sc_buttons[self.button_id]['config']['密码']

        ssh_client = ssh_tools.SSHTools()
        ssh_client.ip = ip
        ssh_client.port = port
        ssh_client.username = username
        ssh_client.password = password

        def do_ssh_monitor_check():
            while True:
                if self.stop_flag:
                    return
                time.sleep(1)
                # 检查是否有连接
                if not ssh_client.is_connected():
                    result = ssh_client.connect()
                    if not result:
                        worker.info_signal.emit(("连接中...", "未知"))
                        continue
                try:
                    # 检查是否有监控
                    cmd = "ps -ef | grep OneClickMonitor.sh | grep -v grep | wc -l"
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(cmd)
                    if stderr.read():
                        worker.info_signal.emit(("已连接", "未知"))
                    monitor_count = stdout.read().decode('utf-8').strip()
                    if not monitor_count:
                        worker.info_signal.emit(("已连接", "未知"))
                    if monitor_count[-1] == "0":
                        worker.info_signal.emit(("已连接", "无监控"))
                    else:
                        worker.info_signal.emit(("已连接", "监控中"))
                except Exception as e:
                    worker.log_signal.emit(f'检查监控状态失败: {e}')
                    continue

        def on_thread_finished():
            thread.deleteLater()
            self.parent.sc_threads.pop(self.lookup_thread_id)
            self.lookup_thread_id = None


        # worker用于定时检查ssh连接状态
        worker = qthread_worker.OneClickWorker(do_ssh_monitor_check)

        thread = QThread()

        self.parent.thread_count += 1
        self.lookup_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.lookup_thread_id] = {
            'worker': worker,
            'thread': thread
        }

        worker.moveToThread(thread)

        worker.info_signal.connect(self.update_status)
        worker.log_signal.connect(self.parent.update_run_info)
        worker.finished.connect(worker.deleteLater)

        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def start_monitor(self):
        self.set_all_buttons_enable(False)
        # 如果是本机监控，需要创建本地监控脚本并执行
        if self.data_dir_name == 'local':
            if self.monitor_stutas_label.text() == '监控中':
                self.message_info_box(("提示", "请先结束正在运行的监控！"))
                self.set_all_buttons_enable()
                return

            def do_local_worker():
                # 生成本地脚本的地址
                os.makedirs(self.monitor_data_path + "/Monitor", mode=0o777, exist_ok=True)
                ps1_path = self.monitor_data_path + "/Monitor/OneClickMonitor.ps1"

                # 构建脚本执行的指令
                cmd = [
                    "powershell",
                    "-ExecutionPolicy", "Bypass",
                    "-File", ps1_path
                ]

                # 构建进程列表（去重、过滤空值）
                proc_input = self.process_input_plainTextEdit.toPlainText().strip()
                procs = proc_input.replace('/', ',')
                # 添加进程参数
                if procs:
                    cmd.append('-p')
                    cmd.append(procs)

                # 添加频率参数
                freq_text = self.freq_lineEdit.text().strip()
                if freq_text:
                    try:
                        freq = int(freq_text)
                        cmd.append('-f')
                        cmd.append(str(freq))
                    except ValueError:
                        worker.info_signal.emit(("提示", "采样频率必须是正整数"))
                        return False

                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW  # 隐藏控制台窗口
                # 将脚本内容写入
                with open(ps1_path, "w", encoding="utf-8-sig", newline='\r\n') as f:
                    f.write(self.monitor_ps1)
                #  后台执行脚本：
                # - Popen：异步执行，不阻塞主进程
                # - stdout/stderr=DEVNULL：重定向所有输出到空设备，无任何打印
                # - creationflags=CREATE_NO_WINDOW：Windows下隐藏PowerShell窗口（可选）
                # ["powershell", "-Command", ps_command],
                result = subprocess.Popen(
                    cmd,
                    shell=False,
                    stdout=subprocess.DEVNULL,  # 屏蔽标准输出
                    stderr=subprocess.DEVNULL,  # 屏蔽错误输出
                    creationflags=creation_flags,  # 隐藏窗口（Windows）
                    encoding='utf-8'  # 兼容字符编码（虽重定向但保留，避免潜在报错）
                )
                return result

            # 创建发送脚本执行指令的线程
            def on_local_worker_finished(result):
                if result:
                    try:
                        if result.poll() is None:
                            self.message_info_box(("提示", "监控已经开始，关闭软件不会停止监控"))
                            self.parent.update_run_info("本机监控已经开始")
                        else:
                            self.message_info_box(("提示", f"监控脚本启动失败{result.returncode}"))
                    except Exception as e:
                        self.message_info_box(("提示", f"监控脚本启动失败{result}-{e}"))
                self.set_all_buttons_enable()
                thread.quit()
            def on_local_thread_finished():
                thread.deleteLater()
                self.parent.sc_threads.pop(self.work_thread_id)
                self.work_thread_id = None

            # 创建worker
            worker = qthread_worker.OneClickWorker(do_local_worker)

            # 创建线程
            thread = QThread()

            # 保存线程和worker
            self.parent.thread_count += 1
            self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
            self.parent.sc_threads[self.work_thread_id] = {
                'worker': worker,
                'thread': thread
            }

            worker.moveToThread(thread)

            # 连接信号和槽
            # worker.log_signal.connect(lambda: None)
            worker.log_signal.connect(self.parent.update_run_info)
            worker.info_signal.connect(self.message_info_box)
            worker.finished.connect(on_local_worker_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_local_thread_finished)
            thread.start()

        # 如果是服务器监控，需要创建本地监控脚本，上传到服务器执行，并删除本地脚本
        else:
            if self.ssh_stutas_label.text() != '已连接':
                self.message_info_box(("提示", "服务器尚未连接"))
                self.set_all_buttons_enable()
                return
            if self.monitor_stutas_label.text() == '监控中':
                self.message_info_box(("提示", "请先结束正在运行的监控！"))
                self.set_all_buttons_enable()
                return

            try:
                ip = self.parent.sc_buttons[self.button_id]['config']['IP']
                port = self.parent.sc_buttons[self.button_id]['config']['端口']
                username = self.parent.sc_buttons[self.button_id]['config']['用户名']
                password = self.parent.sc_buttons[self.button_id]['config']['密码']

                ssh_client = ssh_tools.SSHTools()
                ssh_client.ip = ip
                ssh_client.port = port
                ssh_client.username = username
                ssh_client.password = password
            except Exception as e:
                self.message_info_box(("提示", f"请检查服务器配置{e}"))
                self.set_all_buttons_enable()
                return

            # 构建并检查指令的内容
            try:
                user_path = f"/home/{username}/OneClick/Monitor"
                script_path = f"{user_path}/OneClickMonitor.sh"
                monitor_cmd = f"{script_path} -o {user_path}"

                # 检查是否有进程需要监控
                if self.process_input_plainTextEdit.toPlainText().strip():
                    monitor_cmd = monitor_cmd + " -p"
                    process_list = self.process_input_plainTextEdit.toPlainText().split('/')
                    for p in process_list:
                        if p.strip():
                            monitor_cmd += f" {p.strip()}"

                # 检查是否设置了采样频率
                if self.freq_lineEdit.text().strip():
                    try:
                        freq = int(self.freq_lineEdit.text().strip())
                        monitor_cmd += f" -f {freq}"
                    except Exception as e:
                        self.message_info_box(("提示", f"采样频率必须是正整数{e}"))
                        self.set_all_buttons_enable()
                        return
            except Exception as e:
                self.message_info_box(("提示", f"请检查指令内容{e}"))
                self.set_all_buttons_enable()
                return
            #  >/dev/null 2>&1：将 stdout/stderr 全部重定向到空设备（丢弃nohup提示和脚本输出）
            #  echo $!：输出后台进程的PID到stdout
            monitor_cmd = f"nohup {monitor_cmd} >/dev/null 2>&1 & echo $!"

            def do_ssh_monitor_worker():
                try:
                    # 生成本地IP/Monitor文件夹
                    os.makedirs(self.monitor_data_path + "/Monitor", mode=0o777, exist_ok=True)
                    monitor_sh_path = self.monitor_data_path + "/Monitor/OneClickMonitor.sh"

                    # 在本地创建脚本
                    with open(monitor_sh_path, "w", encoding="utf-8", newline='\n') as f:
                        f.write(self.monitor_sh)
                    ssh_result = ssh_client.connect()
                    if not ssh_result:
                        worker.info_signal.emit(("提示", "连接服务器失败"))
                        return False
                    # 在服务器创建脚本和监控文件所在文件夹/home/root/OneClick
                    mkdir_temp_cmd = f"mkdir -p \"{user_path}\""
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(mkdir_temp_cmd)
                    stdout.read()
                    stderr.read()
                    # 上传脚本
                    send_result = ssh_client.send_files(monitor_sh_path, f"{user_path}")
                    if not send_result:
                        worker.info_signal.emit(("提示", "上传脚本失败"))
                        return False
                except Exception as e:
                    worker.info_signal.emit(("提示", f"上传脚本失败{e}"))
                    ssh_client.disconnect()
                    return False

                # 执行指令
                try:
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(monitor_cmd)
                    pid = stdout.read().decode().strip()
                    err = stderr.read().decode().strip()
                    ssh_client.disconnect()
                    if err:
                        worker.info_signal.emit(("提示", f"执行指令失败{err}"))
                        return False
                    if pid.isdigit():
                        return True
                    else:
                        return False
                except Exception as e:
                    worker.info_signal.emit(("提示", f"执行指令失败{e}"))
                    ssh_client.disconnect()
                    return False

            def on_ssh_worker_finished(result):
                if result:
                    self.message_info_box(("提示", "监控已经开始，关闭软件不会停止监控"))
                    self.parent.update_run_info(f"{ip}监控开始")
                self.set_all_buttons_enable()
                thread.quit()

            def on_ssh_thread_finished():
                thread.deleteLater()
                self.parent.sc_threads.pop(self.work_thread_id)
                self.work_thread_id = None

            worker = qthread_worker.OneClickWorker(do_ssh_monitor_worker)
            thread = QThread()

            # 保存线程和worker
            self.parent.thread_count += 1
            self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
            self.parent.sc_threads[self.work_thread_id] = {
                'worker': worker,
                'thread': thread
            }

            worker.moveToThread(thread)

            worker.info_signal.connect(self.message_info_box)
            worker.log_signal.connect(self.parent.update_run_info)
            worker.finished.connect(on_ssh_worker_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_ssh_thread_finished)
            thread.start()

    def stop_monitor(self):
        self.set_all_buttons_enable(False)
        if self.data_dir_name == 'local':
            if self.monitor_stutas_label.text() != '监控中':
                self.message_info_box(("提示", "没有正在运行的监控！"))
                self.set_all_buttons_enable()
                return

            def do_stop_monitor():
                script_name = "OneClickMonitor.ps1"
                pids = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        name = proc.info['name']
                        if name and name.lower() in ('powershell.exe', 'pwsh.exe'):
                            cmdline = proc.info['cmdline']
                            if cmdline and any(script_name in arg for arg in cmdline):
                                # 排除自身调用的那个命令
                                if not any('-Command' in arg for arg in cmdline):
                                    pids.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if not pids:
                    worker.info_signal.emit(("提示", "没有正在运行的监控！"))
                    return False
                    # 终止所有匹配的进程
                for pid in pids:
                    try:
                        proc = psutil.Process(pid)
                        # 先尝试优雅终止
                        proc.terminate()
                        # 等待最多 3 秒，让进程有机会清理
                        gone, alive = psutil.wait_procs([proc], timeout=3)
                        if alive:
                            # 超时则强制杀死
                            for p in alive:
                                p.kill()
                    except psutil.AccessDenied:
                        worker.info_signal.emit(("错误", f"权限不足，无法终止进程 {pid}，请尝试以管理员身份运行"))
                        return False
                    except Exception as e:
                        worker.info_signal.emit(("错误", f"终止进程 {pid} 时出错: {e}"))
                        return False
                return True

            def on_worker_finished(result):
                if result:
                    self.message_info_box(("提示", "本机监控已经停止"))
                    self.parent.update_run_info("本机监控停止")
                self.set_all_buttons_enable()
                thread.quit()
            def on_thread_finished():
                thread.deleteLater()
                self.parent.sc_threads.pop(self.work_thread_id)
                self.work_thread_id = None

            worker = qthread_worker.OneClickWorker(do_stop_monitor)
            thread = QThread()

            # 保存线程和worker
            self.parent.thread_count += 1
            self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
            self.parent.sc_threads[self.work_thread_id] = {
                'worker': worker,
                'thread': thread
            }

            worker.moveToThread(thread)

            # worker.log_signal.connect(lambda : None) # 屏蔽日志输出
            worker.log_signal.connect(self.parent.update_run_info)
            worker.info_signal.connect(self.message_info_box)
            worker.finished.connect(on_worker_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)
            thread.start()

        else:
            if self.ssh_stutas_label.text() != '已连接':
                self.message_info_box(("提示", "服务器尚未连接"))
                self.set_all_buttons_enable()
                return
            if self.monitor_stutas_label.text() != '监控中':
                self.message_info_box(("提示", "没有正在运行的监控！"))
                self.set_all_buttons_enable()
                return

            try:
                ip = self.parent.sc_buttons[self.button_id]['config']['IP']
                port = self.parent.sc_buttons[self.button_id]['config']['端口']
                username = self.parent.sc_buttons[self.button_id]['config']['用户名']
                password = self.parent.sc_buttons[self.button_id]['config']['密码']

                ssh_client = ssh_tools.SSHTools()
                ssh_client.ip = ip
                ssh_client.port = port
                ssh_client.username = username
                ssh_client.password = password
            except Exception as e:
                self.message_info_box(("提示", f"请检查服务器配置{e}"))
                self.set_all_buttons_enable()
                return

            stop_cmd = "pkill -9 -f OneClickMonitor.sh"

            def do_stop_monitor():
                connect_result = ssh_client.connect()
                if not connect_result:
                    worker.info_signal.emit(("提示", f"停止监控失败，原因：连接服务器失败"))
                    return False
                try:
                    stdin,stdout, stderr = ssh_client.ssh.exec_command(stop_cmd)
                    err = stderr.read().decode().strip()
                    ssh_client.disconnect()
                    if err:
                        worker.info_signal.emit(("提示", f"停止监控失败{err}"))
                        return False
                    return True
                except Exception as e:
                    worker.info_signal.emit(("提示", f"停止监控失败{e}"))
                    ssh_client.disconnect()
                    return False

            def on_stop_monitor_finished(result):
                if result:
                    self.message_info_box(("提示", f"{ip}监控已经停止"))
                    self.parent.update_run_info(f"{ip}监控已经停止")
                self.set_all_buttons_enable()
                thread.quit()

            def on_thread_finished():
                thread.deleteLater()
                self.parent.sc_threads.pop(self.work_thread_id)
                self.work_thread_id = None

            worker = qthread_worker.OneClickWorker(do_stop_monitor)
            thread = QThread()

            # 保存线程和worker
            self.parent.thread_count += 1
            self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
            self.parent.sc_threads[self.work_thread_id] = {
                'worker': worker,
                'thread': thread
            }

            worker.moveToThread(thread)

            # worker.log_signal.connect(lambda : None) # 屏蔽日志输出
            worker.log_signal.connect(self.parent.update_run_info)
            worker.info_signal.connect(self.message_info_box)
            worker.finished.connect(on_stop_monitor_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)
            thread.start()

    def clean_data(self):
        self.set_all_buttons_enable(False)
        # 存在监控时不允许删数据，否则删除后新的监控数据找不到存储路径
        if self.monitor_stutas_label.text() == '监控中':
            self.message_info_box(("提示", "请先结束正在运行的监控！"))
            self.set_all_buttons_enable()
            return

        if self.data_dir_name == 'local':
            confirm_dialog = QMessageBox()
            confirm_dialog.setIcon(QMessageBox.Icon.Question)
            confirm_dialog.setWindowTitle("确认")
            confirm_dialog.setText("是否要清空本机(local路径)所有历史监控数据，清空后无法恢复")
            confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
            result = confirm_dialog.exec_()
            if result == QMessageBox.StandardButton.Yes:
                try:
                    # 尝试递归删除文件夹及所有内容
                    local_monitor_path = self.monitor_data_path + "/Monitor"
                    shutil.rmtree(local_monitor_path)
                    self.message_info_box(("提示", f"本机监控数据已删除{local_monitor_path}"))
                    self.parent.update_run_info(f"本机监控数据已删除{local_monitor_path}")
                except FileNotFoundError:
                    # 捕获"文件夹不存在"的异常，不做任何操作
                    self.message_info_box(("提示", f"没有本机监控数据，无需删除{local_monitor_path}"))
                except Exception as e:
                    # 捕获其他未知异常
                    self.message_info_box(("提示", f"出错：文件夹 {local_monitor_path} ：{str(e)}"))
                finally:
                    self.set_all_buttons_enable()
            else:
                self.set_all_buttons_enable()

        else:
            confirm_dialog = QMessageBox()
            confirm_dialog.setIcon(QMessageBox.Icon.Question)
            confirm_dialog.setWindowTitle("确认")
            confirm_dialog.setText("是否要清空服务器和本地所有历史监控数据，清空后无法恢复")
            confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
            result = confirm_dialog.exec_()
            if result == QMessageBox.StandardButton.Yes:
                try:
                    ip = self.parent.sc_buttons[self.button_id]['config']['IP']
                    port = self.parent.sc_buttons[self.button_id]['config']['端口']
                    username = self.parent.sc_buttons[self.button_id]['config']['用户名']
                    password = self.parent.sc_buttons[self.button_id]['config']['密码']

                    ssh_client = ssh_tools.SSHTools()
                    ssh_client.ip = ip
                    ssh_client.port = port
                    ssh_client.username = username
                    ssh_client.password = password
                except Exception as e:
                    self.message_info_box(("提示", f"请检查服务器配置{e}"))
                    self.set_all_buttons_enable()
                    return
                # 清除本地
                try:
                    # 尝试递归删除文件夹及所有内容
                    local_monitor_path = self.monitor_data_path + "/Monitor"
                    shutil.rmtree(local_monitor_path)
                    self.message_info_box(("提示", f"本机监控数据已删除{local_monitor_path}"))
                    self.parent.update_run_info(f"本机监控数据已删除{local_monitor_path}")
                except FileNotFoundError:
                    # 捕获"文件夹不存在"的异常，不做任何操作
                    self.message_info_box(("提示", f"没有本机监控数据，无需删除{local_monitor_path}"))
                except Exception as e:
                    # 捕获其他未知异常
                    self.message_info_box(("提示", f"删除出错：文件夹 {local_monitor_path} ：{str(e)}"))

                if self.ssh_stutas_label.text() != '已连接':
                    self.message_info_box(("提示", f"未连接服务器，服务器数据未删除"))
                    self.set_all_buttons_enable()
                    return

                user_path = f"/home/{username}/OneClick/Monitor"

                clean_cmd = f"rm -rf {user_path}"

                def do_clean_cmd():
                    connect_result = ssh_client.connect()
                    if not connect_result:
                        worker.info_signal.emit(("提示", f"清空服务器数据失败，原因：连接服务器失败"))
                        return False
                    try:
                        stdin,stdout, stderr = ssh_client.ssh.exec_command(clean_cmd)
                        err = stderr.read().decode().strip()
                        ssh_client.disconnect()
                        if err:
                            worker.info_signal.emit(("提示", f"清空服务器数据失败{err}"))
                            return False
                        return True
                    except Exception as e:
                        worker.info_signal.emit(("提示", f"清空服务器数据失败{e}"))
                        ssh_client.disconnect()
                        return False

                def on_clean_cmd_finished(result):
                    if result:
                        self.message_info_box(("提示", f"{ip}监控数据已清空"))
                        self.parent.update_run_info(f"{ip}监控数据已清空")
                    self.set_all_buttons_enable()
                    thread.quit()

                def on_thread_finished():
                    thread.deleteLater()
                    self.parent.sc_threads.pop(self.work_thread_id)
                    self.work_thread_id = None

                worker = qthread_worker.OneClickWorker(do_clean_cmd)
                thread = QThread()

                self.parent.thread_count += 1
                self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
                self.parent.sc_threads[self.work_thread_id] = {
                    'worker': worker,
                    'thread': thread
                }

                worker.moveToThread(thread)

                # worker.log_signal.connect(lambda : None) # 屏蔽日志输出
                worker.log_signal.connect(self.parent.update_run_info)
                worker.info_signal.connect(self.message_info_box)
                worker.finished.connect(on_clean_cmd_finished)
                worker.finished.connect(worker.deleteLater)

                thread.started.connect(worker.run_task)
                thread.finished.connect(on_thread_finished)
                thread.start()
            else:
                self.set_all_buttons_enable()

    def download_data(self):
        """
        从服务器下载监控数据，如果没有，弹窗提示
        如果有，下载
        :return:
        """
        if self.data_dir_name == 'local':
            self.message_info_box(("提示", "本机监控无需下载，保存在当前路径local下，可直接查看"))
            return
        if self.ssh_stutas_label.text() != '已连接':
            self.message_info_box(("提示", "服务器尚未连接"))
            return

        try:
            ip = self.parent.sc_buttons[self.button_id]['config']['IP']
            port = self.parent.sc_buttons[self.button_id]['config']['端口']
            username = self.parent.sc_buttons[self.button_id]['config']['用户名']
            password = self.parent.sc_buttons[self.button_id]['config']['密码']

            ssh_client = ssh_tools.SSHTools()
            ssh_client.ip = ip
            ssh_client.port = port
            ssh_client.username = username
            ssh_client.password = password
        except Exception as e:
            self.message_info_box(("提示", f"请检查服务器配置{e}"))
            return

        self.set_all_buttons_enable(False)
        # 服务器监控数据的位置
        user_path = f"/home/{username}/OneClick/Monitor"

        # 本地保存路径
        def do_download_data():
            connect_result = ssh_client.connect()
            if not connect_result:
                worker.info_signal.emit(("提示", f"下载数据失败，原因：连接服务器失败"))
                return False
            try:
                # 如果本地没有ip文件夹，则创建
                os.makedirs(self.monitor_data_path, mode=0o777, exist_ok=True)
                get_result = ssh_client.get_files(user_path, self.monitor_data_path)
                ssh_client.disconnect()
                if not get_result:
                    worker.info_signal.emit(("提示", f"下载数据失败，原因：获取数据失败"))
                    return False
            except Exception as e:
                worker.info_signal.emit(("提示", f"下载数据失败，原因：{e}"))
                ssh_client.disconnect()
                return False
            return True

        def on_download_data_finished(result):
            if result:
                self.message_info_box(("提示", f"监控数据已下载到{self.monitor_data_path}/Monitor"))
                self.parent.update_run_info(f"监控数据已下载到{self.monitor_data_path}/Monitor")
            self.set_all_buttons_enable()
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_download_data)
        thread = QThread()

        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {
            'worker': worker,
            'thread': thread
        }

        worker.moveToThread(thread)

        worker.log_signal.connect(self.parent.update_run_info)
        worker.info_signal.connect(self.message_info_box)
        worker.finished.connect(on_download_data_finished)
        worker.finished.connect(worker.deleteLater)

        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def message_info_box(self, data):
        """
        弹窗提示
        :param data: data[0] 标题, data[1] 内容
        :return:
        """
        QMessageBox.information(self, data[0], data[1], QMessageBox.StandardButton.Ok)

    def set_all_buttons_enable(self, enable=True):
        self.start_pushButton.setEnabled(enable)
        self.stop_pushButton.setEnabled(enable)
        self.clean_pushButton.setEnabled(enable)
        self.watch_pushButton.setEnabled(enable)
        self.download_pushButton.setEnabled(enable)
        self._can_close = enable

    def update_status(self, data):
        """
        更新状态
        :param data: 状态列表, 0: ssh状态, 1: 监控状态
        :return:
        """
        self.ssh_stutas_label.setText(data[0])
        self.monitor_stutas_label.setText(data[1])

    def display_resource(self):
        if self.data_dir_name != 'local':
            self.message_info_box(("提示", "仅处理已下载的监控数据"))
        data_path = self.monitor_data_path + '/Monitor'
        g_window = GraphWindowLogic.GraphWindow(data_path, self)

        g_window.destroyed.connect(
            lambda obj: self.remove_window_from_list(obj)
        )
        # 关键：保持对窗口的引用，防止被垃圾回收
        self.g_windows.append(g_window)

        g_window.show()

    def remove_window_from_list(self, window):
        """从列表中移除已关闭的窗口"""
        # 注意：这里的window参数是已经销毁的对象，不能直接比较
        # 我们需要找到并移除对应的引用
        for i, w in enumerate(self.g_windows):
            if w is window:
                self.g_windows.pop(i)
                # print(f"移除了一个窗口引用，还剩 {len(self.g_windows)} 个")
                break

    def on_close_event(self, event):
        if not self._can_close:
            event.ignore()  # 忽略关闭事件
            self.message_info_box(("提示", "操作中，请稍后"))
            return

        # 保存数据，下次打开自动填入
        self.parent.sc_buttons[self.button_id]['config']['进程'] = self.process_input_plainTextEdit.toPlainText()
        self.parent.sc_buttons[self.button_id]['config']['采样频率'] = self.freq_lineEdit.text()

        # 安全结束监控线程
        if self.work_thread_id is not None and self.work_thread_id in self.parent.sc_threads:
            # 仅当字典里确实还有这个线程对象时才操作
            thread_data = self.parent.sc_threads[self.work_thread_id]
            # 退出线程
            thread_data['thread'].quit()

        # 安全结束查询线程
        if self.lookup_thread_id is not None and self.lookup_thread_id in self.parent.sc_threads:
            thread_data = self.parent.sc_threads[self.lookup_thread_id]
            # 停止循环，触发finished信号清理worker
            self.stop_flag = True
            # 退出线程
            thread_data['thread'].quit()

        event.accept()


class WeakNetDialog1(SendCMDDialog):
    """继承SendCMDDialog，移除指令内容，用于配置弱网按钮的服务器信息"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加<弱网>配置")
        self.resize(420, 230)
        # 移除指令输入框
        self.label_7.setParent(None)
        self.label_7.deleteLater()
        self.cmd_TextEdit.setParent(None)
        self.cmd_TextEdit.deleteLater()

    def create_sc(self):
        text_list = [
            self.linux_ip_lineEdit,
            self.username_lineEdit,
            self.passwd_lineEdit,
            self.sshport_lineEdit,
            self.sc_name_lineEdit
        ]
        for t in text_list:
            t.setStyleSheet("")
        for t in text_list:
            if not t.text().strip():
                t.setStyleSheet("QLineEdit { border: 2px solid red; }")
                return

        self.sc_cfg['指令类型'] = sc_class2str[self.__class__.__name__]
        self.sc_cfg['IP'] = self.linux_ip_lineEdit.text()
        self.sc_cfg['用户名'] = self.username_lineEdit.text()
        self.sc_cfg['密码'] = self.passwd_lineEdit.text()
        self.sc_cfg['端口'] = self.sshport_lineEdit.text()
        self.sc_cfg['规则列表'] = []
        self.sc_cfg['循环次数'] = '0'
        self.sc_cfg['指令名称'] = self.sc_name_lineEdit.text()

        if self.parent:
            if hasattr(self, 'button_id'):
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        self.accept()

    def edit_sc(self, button_id):
        self.button_id = button_id
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])


class WeakNetControlDialog(QDialog, weak_net_control_dlg.Ui_Dialog):
    """弱网控制面板"""
    def __init__(self, button_id, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.button_id = button_id
        self.parent = parent
        self.rule_queue = []
        self.ssh_client = ssh_tools.SSHTools()
        self.stop_flag = False
        self.work_thread_id = None
        self.lookup_thread_id = None
        self.script_running = False
        self.current_nic = ''

        # 从配置恢复
        cfg = self.parent.sc_buttons[button_id]['config']
        self.rule_queue = list(cfg.get('规则列表', []))
        self.loop_lineEdit.setText(cfg.get('循环次数', '0'))

        self.init_ssh_from_config()
        self.refresh_rule_table()

        # 信号连接
        self.refresh_nic_pushButton.clicked.connect(self.refresh_nics)
        self.add_rule_pushButton.clicked.connect(self.add_rule_to_queue)
        self.del_rule_pushButton.clicked.connect(self.del_rule_from_queue)
        self.move_up_pushButton.clicked.connect(self.move_rule_up)
        self.move_down_pushButton.clicked.connect(self.move_rule_down)
        self.start_pushButton.clicked.connect(self.start_weak_net)
        self.stop_pushButton.clicked.connect(self.stop_weak_net)
        self.show_tc_pushButton.clicked.connect(self.show_weaknet_log)

        self.closeEvent = self.on_close_event
        self._can_close = True

        self.update_status(('连接中...', '未知'))
        self.start_status_check()

    def init_ssh_from_config(self):
        cfg = self.parent.sc_buttons[self.button_id]['config']
        try:
            self.ssh_client.ip = cfg['IP']
            self.ssh_client.port = cfg['端口']
            self.ssh_client.username = cfg['用户名']
            self.ssh_client.password = cfg['密码']
        except Exception as e:
            self.update_status(('配置错误', '未知'))

    def start_status_check(self):
        ip = self.parent.sc_buttons[self.button_id]['config']['IP']

        def do_status_check():
            while True:
                if self.stop_flag:
                    return
                time.sleep(2)
                if not self.ssh_client.is_connected():
                    result = self.ssh_client.connect()
                    if not result:
                        worker.info_signal.emit(('连接中...', '未知'))
                        continue
                try:
                    # 获取网卡列表（首次或网卡下拉为空时）
                    if self.nic_comboBox.count() == 0:
                        stdin, stdout, stderr = self.ssh_client.ssh.exec_command(
                            "ls /sys/class/net/ | grep -v '^lo$'"
                        )
                        nics = stdout.read().decode('utf-8').strip().split('\n')
                        nics = [n.strip() for n in nics if n.strip()]
                        worker.log_signal.emit(f'网卡列表: {nics}')
                        if nics:
                            worker.info_signal.emit(('已连接', None, nics))
                    else:
                        # 仅检查脚本状态
                        cmd = "ps -ef | grep OneClickWeakNet.sh | grep -v grep | wc -l"
                        stdin, stdout, stderr = self.ssh_client.ssh.exec_command(cmd)
                        count = stdout.read().decode('utf-8').strip()
                        is_running = count and count[-1] != '0'
                        worker.info_signal.emit(('已连接', '运行中' if is_running else '已停止', None))
                except Exception as e:
                    worker.log_signal.emit(f'状态检查失败: {e}')
                    continue

        def on_info(data):
            ssh_status = data[0]
            script_status = data[1] if len(data) > 1 else None
            nics = data[2] if len(data) > 2 else None
            self.ssh_stutas_label.setText(ssh_status)
            if script_status:
                self.script_stutas_label.setText(script_status)
            if nics:
                current = self.nic_comboBox.currentText()
                self.nic_comboBox.clear()
                for nic in nics:
                    self.nic_comboBox.addItem(nic)
                if current:
                    idx = self.nic_comboBox.findText(current)
                    if idx >= 0:
                        self.nic_comboBox.setCurrentIndex(idx)
            # 同步脚本运行状态标记
            if script_status == '运行中' and not self.script_running:
                self.script_running = True
            elif script_status == '已停止' and self.script_running:
                self.script_running = False

        def on_thread_finished():
            thread.deleteLater()
            if self.lookup_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.lookup_thread_id)
            self.lookup_thread_id = None

        worker = qthread_worker.OneClickWorker(do_status_check)
        thread = QThread()
        self.parent.thread_count += 1
        self.lookup_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.lookup_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.log_signal.connect(self.parent.update_run_info)
        worker.info_signal.connect(on_info)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def refresh_nics(self):
        if not self.ssh_client.is_connected():
            self.message_info_box(("提示", "SSH未连接"))
            return
        try:
            stdin, stdout, stderr = self.ssh_client.ssh.exec_command(
                "ls /sys/class/net/ | grep -v '^lo$'"
            )
            nics = stdout.read().decode('utf-8').strip().split('\n')
            nics = [n.strip() for n in nics if n.strip()]
            current = self.nic_comboBox.currentText()
            self.nic_comboBox.clear()
            for nic in nics:
                self.nic_comboBox.addItem(nic)
            if current:
                idx = self.nic_comboBox.findText(current)
                if idx >= 0:
                    self.nic_comboBox.setCurrentIndex(idx)
            self.parent.update_run_info(f"网卡列表刷新: {nics}")
        except Exception as e:
            self.message_info_box(("错误", f"获取网卡失败: {e}"))

    def show_weaknet_log(self):
        if not self.ssh_client.is_connected():
            self.message_info_box(("提示", "SSH未连接"))
            return
        cfg = self.parent.sc_buttons[self.button_id]['config']
        ip_name = cfg['IP'] if cfg['IP'] else 'local'
        local_dir = os.path.join(self.parent.get_default_path(), ip_name, "WeakNet").replace('\\', '/')
        local_log = local_dir + "/OneClickWeakNet.log"
        remote_log = f"/home/{self.ssh_client.username}/OneClick/WeakNet/OneClickWeakNet.log"

        try:
            os.makedirs(local_dir, mode=0o777, exist_ok=True)
            self.ssh_client.get_files(remote_log, local_dir)
        except Exception as e:
            self.parent.update_run_info(f"下载日志失败: {e}")

        try:
            if os.path.exists(local_log):
                with open(local_log, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    self.tc_rule_textBrowser.setPlainText(content)
                else:
                    self.tc_rule_textBrowser.setPlainText("日志文件为空")
            else:
                self.tc_rule_textBrowser.setPlainText("暂无运行日志（尚未运行过弱网脚本）")
        except Exception as e:
            self.tc_rule_textBrowser.setPlainText(f"读取日志失败: {e}")

    def add_rule_to_queue(self):
        rule = {
            '延迟': self.delay_lineEdit.text().strip(),
            '抖动': self.jitter_lineEdit.text().strip(),
            '丢包率': self.loss_lineEdit.text().strip(),
            '损坏率': self.corrupt_lineEdit.text().strip(),
            '重复率': self.duplicate_lineEdit.text().strip(),
            '重排率': self.reorder_lineEdit.text().strip(),
            '带宽': self.rate_lineEdit.text().strip(),
            '带宽单位': self.rate_unit_comboBox.currentText(),
            '持续时长': self.duration_lineEdit.text().strip(),
            '间隔时长': self.interval_lineEdit.text().strip(),
        }
        if not rule['持续时长']:
            self.message_info_box(("提示", "持续时长不能为空"))
            return
        try:
            int(rule['持续时长'])
        except ValueError:
            self.message_info_box(("提示", "持续时长必须是整数"))
            return
        if rule['间隔时长']:
            try:
                int(rule['间隔时长'])
            except ValueError:
                self.message_info_box(("提示", "间隔时长必须是整数"))
                return
        self.rule_queue.append(rule)
        self.refresh_rule_table()

    def del_rule_from_queue(self):
        row = self.rule_tableWidget.currentRow()
        if row < 0 or row >= len(self.rule_queue):
            return
        self.rule_queue.pop(row)
        self.refresh_rule_table()

    def move_rule_up(self):
        row = self.rule_tableWidget.currentRow()
        if row <= 0:
            return
        self.rule_queue[row], self.rule_queue[row - 1] = self.rule_queue[row - 1], self.rule_queue[row]
        self.refresh_rule_table()
        self.rule_tableWidget.selectRow(row - 1)

    def move_rule_down(self):
        row = self.rule_tableWidget.currentRow()
        if row < 0 or row >= len(self.rule_queue) - 1:
            return
        self.rule_queue[row], self.rule_queue[row + 1] = self.rule_queue[row + 1], self.rule_queue[row]
        self.refresh_rule_table()
        self.rule_tableWidget.selectRow(row + 1)

    def refresh_rule_table(self):
        self.rule_tableWidget.setRowCount(len(self.rule_queue))
        for i, rule in enumerate(self.rule_queue):
            delay = rule.get('延迟', '')
            loss = rule.get('丢包率', '')
            rate = rule.get('带宽', '')
            if rate:
                rate += rule.get('带宽单位', 'kbit')
            duration = rule.get('持续时长', '')
            interval = rule.get('间隔时长', '')
            self.rule_tableWidget.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.rule_tableWidget.setItem(i, 1, QTableWidgetItem(delay + 'ms' if delay else '-'))
            self.rule_tableWidget.setItem(i, 2, QTableWidgetItem(loss + '%' if loss else '-'))
            self.rule_tableWidget.setItem(i, 3, QTableWidgetItem(rate if rate else '-'))
            self.rule_tableWidget.setItem(i, 4, QTableWidgetItem(duration + 's'))
            self.rule_tableWidget.setItem(i, 5, QTableWidgetItem(interval + 's' if interval else '0s'))

    def build_tc_add_cmd(self, nic, rule):
        netem_parts = []
        delay = rule.get('延迟', '').strip()
        jitter = rule.get('抖动', '').strip()
        loss = rule.get('丢包率', '').strip()
        corrupt = rule.get('损坏率', '').strip()
        duplicate = rule.get('重复率', '').strip()
        reorder = rule.get('重排率', '').strip()
        rate = rule.get('带宽', '').strip()
        rate_unit = rule.get('带宽单位', 'kbit')

        if delay and delay != '0':
            part = f"delay {delay}ms"
            if jitter and jitter != '0':
                part += f" {jitter}ms"
            netem_parts.append(part)
        if loss and loss != '0':
            netem_parts.append(f"loss {loss}%")
        if corrupt and corrupt != '0':
            netem_parts.append(f"corrupt {corrupt}%")
        if duplicate and duplicate != '0':
            netem_parts.append(f"duplicate {duplicate}%")
        if reorder and reorder != '0':
            netem_parts.append(f"reorder {reorder}%")

        has_netem = len(netem_parts) > 0
        has_rate = bool(rate) and rate != '0'
        rate_str = f"{rate}{rate_unit}" if has_rate else ""

        if has_rate and has_netem:
            return (
                f"tc qdisc add dev {nic} root handle 1: htb default 1 && "
                f"tc class add dev {nic} parent 1: classid 1:1 htb rate {rate_str} && "
                f"tc qdisc add dev {nic} parent 1:1 handle 10: netem {' '.join(netem_parts)}"
            )
        elif has_rate:
            return f"tc qdisc add dev {nic} root tbf rate {rate_str} burst 32kbit latency 400ms"
        elif has_netem:
            return f"tc qdisc add dev {nic} root netem {' '.join(netem_parts)}"
        return None

    def generate_script(self, nic, loop_count):
        log_file = f"/home/{self.ssh_client.username}/OneClick/WeakNet/OneClickWeakNet.log"
        lines = [
            '#!/bin/bash',
            'set -euo pipefail',
            f'NIC="{nic}"',
            f'LOOP={loop_count}',
            f'LOGFILE="{log_file}"',
            '',
            'log() {',
            '    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $*" >> "$LOGFILE"',
            '}',
            '',
            '# 清空旧日志',
            '> "$LOGFILE"',
            '',
            'cleanup() {',
            '    tc qdisc del dev "$NIC" root 2>/dev/null || true',
            '    log "弱网脚本已终止，tc规则已清除"',
            '    exit 0',
            '}',
            'trap cleanup SIGINT SIGTERM',
            '',
            'log "弱网脚本启动"',
            f'log "网卡: {nic}"',
            f'log "循环次数: {loop_count}"',
            'log "规则队列:"',
        ]
        for idx, rule in enumerate(self.rule_queue, 1):
            parts = []
            if rule.get('延迟'):
                parts.append(f"延迟: {rule['延迟']}ms")
            if rule.get('抖动'):
                parts.append(f"抖动: {rule['抖动']}ms")
            if rule.get('丢包率'):
                parts.append(f"丢包率: {rule['丢包率']}%")
            if rule.get('损坏率'):
                parts.append(f"损坏率: {rule['损坏率']}%")
            if rule.get('重复率'):
                parts.append(f"重复率: {rule['重复率']}%")
            if rule.get('重排率'):
                parts.append(f"重排率: {rule['重排率']}%")
            if rule.get('带宽'):
                parts.append(f"带宽: {rule['带宽']}{rule.get('带宽单位', 'kbit')}")
            parts.append(f"持续: {rule.get('持续时长', '10')}s")
            parts.append(f"间隔: {rule.get('间隔时长', '0')}s")
            lines.append(f'log "  [规则{idx}] {" | ".join(parts)}"')
        lines.append('')
        lines.append('for i in $(seq 1 $LOOP); do')
        lines.append('    log "第 $i/$LOOP 次循环开始"')
        for idx, rule in enumerate(self.rule_queue, 1):
            tc_cmd = self.build_tc_add_cmd(nic, rule)
            duration = rule.get('持续时长', '10')
            interval = rule.get('间隔时长', '0')
            lines.append(f'    tc qdisc del dev "$NIC" root 2>/dev/null || true')
            if tc_cmd:
                lines.append(f'    {tc_cmd}')
                lines.append(f'    log "  应用规则{idx}: {tc_cmd}"')
            else:
                lines.append(f'    log "  规则{idx}无tc参数，仅清除规则"')
            lines.append(f'    sleep {duration}')
            lines.append(f'    log "  规则{idx}弱网结束（持续{duration}s），进入间隔{interval}s"')
            if interval and interval != '0':
                lines.append(f'    tc qdisc del dev "$NIC" root 2>/dev/null || true')
                lines.append(f'    sleep {interval}')
                lines.append(f'    log "  间隔结束（{interval}s）"')
        lines.append('done')
        lines.append('')
        lines.append('log "所有循环已完成，清除tc规则"')
        lines.append('cleanup')
        return '\n'.join(lines)

    def start_weak_net(self):
        if self.script_running:
            self.message_info_box(("提示", "弱网脚本正在运行，请先停止"))
            return
        if not self.rule_queue:
            self.message_info_box(("提示", "请先添加规则到队列"))
            return
        nic = self.nic_comboBox.currentText()
        if not nic:
            self.message_info_box(("提示", "请先选择网卡"))
            return

        reply = QMessageBox.warning(
            self, "警告",
            "弱网设置可能导致SSH连接中断！\n"
            "请确保已配置好停止条件（持续时长/间隔时长），\n"
            "或在另一终端准备好恢复命令。\n\n"
            "确定要开始弱网吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            loop_val = self.loop_lineEdit.text().strip()
            loop_count = int(loop_val) if loop_val else 0
            if loop_count <= 0:
                loop_count = 99999999
        except ValueError:
            self.message_info_box(("提示", "循环次数必须是整数"))
            return

        script_content = self.generate_script(nic, loop_count)
        cfg = self.parent.sc_buttons[self.button_id]['config']
        username = cfg['用户名']
        ip_name = cfg['IP'] if cfg['IP'] else 'local'
        local_dir = os.path.join(self.parent.get_default_path(), ip_name, "WeakNet").replace('\\', '/')
        user_path = f"/home/{username}/OneClick/WeakNet"
        script_path = f"{user_path}/OneClickWeakNet.sh"
        monitor_cmd = f"nohup bash {script_path} >/dev/null 2>&1 & echo $!"

        def do_start():
            try:
                os.makedirs(local_dir, mode=0o777, exist_ok=True)
                local_path = local_dir + "/OneClickWeakNet.sh"
                with open(local_path, "w", encoding="utf-8", newline='\n') as f:
                    f.write(script_content)
                ssh_result = self.ssh_client.connect()
                if not ssh_result:
                    worker.info_signal.emit(("提示", "连接服务器失败"))
                    return False
                mkdir_cmd = f"mkdir -p \"{user_path}\""
                stdin, stdout, stderr = self.ssh_client.ssh.exec_command(mkdir_cmd)
                stdout.read(); stderr.read()
                send_result = self.ssh_client.send_files(local_path, f"{user_path}/")
                if not send_result:
                    worker.info_signal.emit(("提示", "上传脚本失败"))
                    return False
            except Exception as e:
                worker.info_signal.emit(("提示", f"准备脚本失败: {e}"))
                self.ssh_client.disconnect()
                return False

            try:
                stdin, stdout, stderr = self.ssh_client.ssh.exec_command(monitor_cmd)
                pid = stdout.read().decode().strip()
                err = stderr.read().decode().strip()
                self.ssh_client.disconnect()
                if err:
                    worker.info_signal.emit(("提示", f"执行指令失败: {err}"))
                    return False
                if pid.isdigit():
                    return True
                return False
            except Exception as e:
                worker.info_signal.emit(("提示", f"执行指令失败: {e}"))
                self.ssh_client.disconnect()
                return False

        def on_finished(result):
            if result:
                self.message_info_box(("提示", "弱网脚本已启动"))
                self.parent.update_run_info(f"{cfg['IP']}弱网脚本已启动")
                self.script_running = True
            else:
                self.parent.update_run_info(f"{cfg['IP']}弱网脚本启动失败")
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            if self.work_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_start)
        thread = QThread()
        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.info_signal.connect(self.message_info_box)
        worker.log_signal.connect(self.parent.update_run_info)
        worker.finished.connect(on_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def stop_weak_net(self):
        if not self.script_running:
            self.message_info_box(("提示", "弱网脚本未在运行"))
            return
        stop_cmd = "pkill -f OneClickWeakNet.sh"

        def do_stop():
            connect_result = self.ssh_client.connect()
            if not connect_result:
                worker.info_signal.emit(("提示", "停止失败，连接服务器失败"))
                return False
            try:
                self.ssh_client.ssh.exec_command(stop_cmd)
                time.sleep(1)
                self.ssh_client.disconnect()
                return True
            except Exception as e:
                worker.info_signal.emit(("提示", f"停止失败: {e}"))
                self.ssh_client.disconnect()
                return False

        def on_finished(result):
            if result:
                self.message_info_box(("提示", "弱网已停止"))
                self.parent.update_run_info("弱网已停止")
                self.script_running = False
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            if self.work_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_stop)
        thread = QThread()
        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.info_signal.connect(self.message_info_box)
        worker.log_signal.connect(self.parent.update_run_info)
        worker.finished.connect(on_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def set_ui_editable(self, editable):
        pass

    def update_status(self, data):
        self.ssh_stutas_label.setText(data[0])
        if len(data) > 1:
            self.script_stutas_label.setText(data[1])

    def message_info_box(self, data):
        QMessageBox.information(self, data[0], data[1], QMessageBox.StandardButton.Ok)

    def on_close_event(self, event):
        if not self._can_close:
            event.ignore()
            self.message_info_box(("提示", "操作中，请稍后"))
            return
        # 保存配置
        self.parent.sc_buttons[self.button_id]['config']['规则列表'] = list(self.rule_queue)
        self.parent.sc_buttons[self.button_id]['config']['循环次数'] = self.loop_lineEdit.text()
        # 结束线程
        self.stop_flag = True
        if self.lookup_thread_id and self.lookup_thread_id in self.parent.sc_threads:
            self.parent.sc_threads[self.lookup_thread_id]['thread'].quit()
        if self.work_thread_id and self.work_thread_id in self.parent.sc_threads:
            self.parent.sc_threads[self.work_thread_id]['thread'].quit()
        event.accept()


class HelpDialog(QDialog):
    """帮助文档对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.resize(900, 700)
        # 去掉窗口标题栏的问号按钮
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        
        from PyQt5.QtWidgets import QTextBrowser
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        
        # 直接使用嵌入的帮助文档内容
        from help_content import HELP_HTML
        self.text_browser.setHtml(HELP_HTML)
        
        layout.addWidget(self.text_browser)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


if __name__ == '__main__':
    pass