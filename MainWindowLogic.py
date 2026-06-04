import os.path
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QDialog, QPushButton, QWidget, QVBoxLayout, QMenu, QFileDialog, QMessageBox, \
    QDialogButtonBox, QAbstractItemView, QHeaderView, QTableWidgetItem, QMainWindow

from UI import MainWindow, send_cmd_dlg, send_files_dlg, get_files_dlg, copy_local_files_dlg, edit_servers_dlg, resource_monitor_dlg
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
    'ResourceMonitorDialog1': "资源监控"
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
        self.get_sc_from_cfg_action.triggered.connect(self.load_sc_config)  # 从配置文件获取快捷按钮

        self.edit_server_action.triggered.connect(self.server_cfg_dialog)  # 服务器列表的编辑框
        self.get_server_from_cfg_action.triggered.connect(self.load_server_config)  # 从配置文件获取服务器

        self.save_action.triggered.connect(self.save_config)  # 保存配置到当前配置文件
        self.save_to_action_2.triggered.connect(self.save_config_to)  # 另存为配置到文件夹
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
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下’生成快捷按钮‘按钮时调用accpted()，主窗口打印日志
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
        self.monitor_sh = r"""#!/bin/bash

        # ---------------------- 脚本使用方式 ----------------------
        # ./OneClickMonitor.sh                                              # 默认运行（5 秒采样，无指定进程，保存到当前路径下，仅包含系统日志system.log）
        # ./OneClickMonitor.sh -f 10 -o /home                               # 10秒采样，日志保存到/home路径下
        # ./OneClickMonitor.sh -f 3 -p nginx java -o /home                  # 监控nginx和java，3秒采样，日志保存到/home路径下，包括系统日志system.log，进程日志nginx_234.log/java_867.log
        # ./OneClickMonitor.sh -h                                           # 查看帮助
        # nohup ./OneClickMonitor.sh &                                      # 后台执行

        set -euo pipefail

        # ---------------------- 配置参数（可通过命令行覆盖，优先级更高） ----------------------
        SAMPLE_FREQ=5                          # 默认采样频率：5秒/次
        OUTPUT_DIR="./"                        # 默认输出文件夹：当前目录
        SYS_LOG_NAME="system.log"              # 系统日志文件名
        SYS_LOG_FILE=""                        # 系统日志完整路径（后续拼接文件夹+文件名）
        TARGET_PROCS=()                        # 默认不监控指定进程，为空数组（明确初始化）

        # ---------------------- 命令行参数解析 ----------------------
        usage() {
            echo "用法：$0 [选项]"
            echo "选项："
            echo "  -f, --freq <秒数>        采样频率，默认5秒"
            echo "  -o, --output <文件夹路径>   输出文件夹路径，默认当前目录（./）"
            echo "  -p, --proc <进程名>     指定监控的进程名（可多个，空格分隔），进程日志自动命名为<进程名>_<PID>.log"
            echo "  -h, --help              显示帮助信息"
            exit 1
        }

        while [[ $# -gt 0 ]]; do
            case "$1" in
                -f|--freq)
                    SAMPLE_FREQ="$2"
                    shift 2
                    ;;
                -o|--output)
                    OUTPUT_DIR="$2"
                    shift 2
                    ;;
                -p|--proc)
                    shift
                    while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                        TARGET_PROCS+=("$1")
                        shift
                    done
                    ;;
                -h|--help)
                    usage
                    ;;
                *)
                    echo "错误：无效参数 $1"
                    usage
                    ;;
            esac
        done

        # ---------------------- 输出文件夹校验与创建 ----------------------
        # 处理文件夹路径末尾是否有/的兼容问题, 部分系统可能没有安装realpath
        #OUTPUT_DIR=$(cd "$(dirname "$OUTPUT_DIR")" &>/dev/null && pwd)/$(basename "$OUTPUT_DIR") # 规范化路径
        #if [[ ! -d "$OUTPUT_DIR" ]]; then
        #    mkdir -p "$OUTPUT_DIR"
        #    echo "输出文件夹不存在，已自动创建：$OUTPUT_DIR"
        #fi

        # 拼接系统日志完整路径
        SYS_LOG_FILE="$OUTPUT_DIR/$SYS_LOG_NAME"

        # ---------------------- 生成系统日志表头（固定不变） ----------------------
        generate_sys_header() {
            echo "系统时间,已用内存(MB),CPU使用率(%),磁盘读(KB/s),磁盘写(KB/s),文件描述符,Socket描述符,进程数"
        }

        # ---------------------- 获取单个进程的当前有效PID列表 ----------------------
        get_proc_current_pids() {
            local proc_name="$1"
            local current_pids=()
            # 查找精确匹配进程名的PID，过滤无效PID（/proc不存在的）
            local pids=$(pgrep -x "$proc_name" 2>/dev/null)
            for pid in $pids; do
                if [[ -d "/proc/$pid" ]]; then
                    current_pids+=("$pid")
                fi
            done
            echo "${current_pids[*]:-}"
        }

        # ---------------------- 生成单个PID的进程日志表头 ----------------------
        generate_single_pid_header() {
            echo "系统时间,已用内存(MB),CPU使用率(%),文件描述符,Socket描述符"
        }

        # ---------------------- 采集单个PID的进程指标 ----------------------
        collect_single_pid_metrics() {
            local proc_name="$1"
            local pid="$2"
            local sys_time="$3"  # 与系统日志同步的时间

            # PID无效时直接返回空（不会写入）
            if [[ ! -d "/proc/$pid" ]]; then
                echo ""
                return
            fi

            # 进程内存（VmRSS，转换为MB保留2位小数）
            local proc_mem=$(cat /proc/$pid/status 2>/dev/null | awk '/VmRSS/ {print $2}')
            proc_mem=$(awk -v mem="$proc_mem" 'BEGIN{printf "%.2f", mem / 1024}')
            proc_mem=${proc_mem:-0.00}

            # 进程CPU使用率（%，保留2位小数）
            local proc_stat1=$(cat /proc/$pid/stat 2>/dev/null | awk '{print $14 "," $15}')
            local sys_stat1=$(cat /proc/stat 2>/dev/null | awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8}')
            sleep 0.1
            local proc_stat2=$(cat /proc/$pid/stat 2>/dev/null | awk '{print $14 "," $15}')
            local sys_stat2=$(cat /proc/stat 2>/dev/null | awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8}')

            local utime1=$(echo "$proc_stat1" | cut -d',' -f1)
            utime1=${utime1:-0}
            local stime1=$(echo "$proc_stat1" | cut -d',' -f2)
            stime1=${stime1:-0}
            local utime2=$(echo "$proc_stat2" | cut -d',' -f1)
            utime2=${utime2:-0}
            local stime2=$(echo "$proc_stat2" | cut -d',' -f2)
            stime2=${stime2:-0}
            local proc_cpu_diff=$((utime2 + stime2 - utime1 - stime1))
            local sys_cpu_diff=$((sys_stat2 - sys_stat1))

            local proc_cpu=0.00
            if [[ $sys_cpu_diff -gt 0 ]]; then
                proc_cpu=$(awk -v p="$proc_cpu_diff" -v s="$sys_cpu_diff" \ 'BEGIN{printf "%.2f", (p/s)*100}')
            fi

            # 进程文件描述符数
            local proc_fds=$(ls /proc/$pid/fd 2>/dev/null | wc -l)
            proc_fds=${proc_fds:-0}

            # 进程Socket描述符数
            local proc_socks=$(ls -l /proc/$pid/fd 2>/dev/null | grep -c 'socket:\[')
            proc_socks=${proc_socks:-0}

            # 拼接指标行
            echo "$sys_time,$proc_mem,$proc_cpu,$proc_fds,$proc_socks"
        }

        # ---------------------- 更新日志表头（仅处理系统日志） ----------------------
        update_log_header() {
            # 系统日志初始化（仅首次）
            if [[ ! -f "$SYS_LOG_FILE" ]]; then
                local sys_header=$(generate_sys_header)
                echo "$sys_header" > "$SYS_LOG_FILE"
                echo "系统日志文件已初始化：$SYS_LOG_FILE，表头：$sys_header"
            fi
        }

        # ---------------------- 系统级指标采集函数 ----------------------
        collect_sys_metrics() {
            local sys_time=$(date "+%Y-%m-%d %H:%M:%S")
            local used_mem=$(free -m | awk '/Mem|内存/ {print $3}')
            local cpu_usage=$(vmstat 1 2 | tail -1 | awk '{print 100 - $15}')
            local io_stats=$(vmstat 1 2 | tail -1 | awk '{print $9 "," $10}')
            local disk_read=$(echo "$io_stats" | cut -d',' -f1)
            local disk_write=$(echo "$io_stats" | cut -d',' -f2)
            local total_fds=$(cat /proc/sys/fs/file-nr | awk '{print $1}')
            local total_socks=$(cat /proc/net/sockstat | awk '/sockets/ {print $3}')
            local total_procs=$(ls -l /proc/ | grep -c "^d.*[0-9]$")

            echo "$sys_time,$used_mem,$cpu_usage,$disk_read,$disk_write,$total_fds,$total_socks,$total_procs"
        }

        # ---------------------- 主监控循环 ----------------------
        main_monitor() {
            echo "开始系统监控，采样频率：${SAMPLE_FREQ}秒"
            echo "系统日志：${SYS_LOG_FILE}"
            if [[ ${#TARGET_PROCS[@]} -gt 0 ]]; then
                echo "监控进程列表：${TARGET_PROCS[*]}"
                echo "进程日志规则：每个PID对应独立日志文件，路径为 $OUTPUT_DIR/<进程名>_<PID>.log"
            fi
            echo "按 Ctrl+C 停止监控"
            echo "特性：无进程时不创建日志，PID消失则停止写入对应日志，新增PID自动创建日志"

            while true; do
                # 初始化/检查系统日志表头
                update_log_header

                # 采集并写入系统数据（原有逻辑完全保留）
                local sys_data=$(collect_sys_metrics)
                echo "$sys_data" >> "$SYS_LOG_FILE"
                local sys_time=$(echo "$sys_data" | cut -d',' -f1)
                echo "[$sys_time] 已写入系统数据到 $SYS_LOG_FILE"

                # 处理进程监控（重写后的逻辑）
                if [[ ${#TARGET_PROCS[@]} -gt 0 ]]; then
                    for proc in "${TARGET_PROCS[@]}"; do
                        # 获取当前进程的有效PID列表
                        local current_pids=($(get_proc_current_pids "$proc"))

                        # 无有效PID时跳过
                        if [[ ${#current_pids[@]} -eq 0 ]]; then
                            echo "[$sys_time] 进程 $proc 无有效PID，跳过进程日志写入"
                            continue
                        fi

                        # 遍历每个PID处理日志
                        for pid in "${current_pids[@]}"; do
                            local proc_log_file="$OUTPUT_DIR/${proc}_${pid}.log"

                            # 日志文件不存在则创建并写入表头
                            if [[ ! -f "$proc_log_file" ]]; then
                                local pid_header=$(generate_single_pid_header "$proc" "$pid")
                                echo "$pid_header" > "$proc_log_file"
                                echo "[$sys_time] 进程 $proc (PID:$pid) 日志已创建：$proc_log_file"
                            fi

                            # 采集并写入该PID的指标
                            local pid_metrics=$(collect_single_pid_metrics "$proc" "$pid" "$sys_time")
                            # 仅当指标非空时写入（PID有效才会有数据）
                            if [[ -n "$pid_metrics" ]]; then
                                echo "$pid_metrics" >> "$proc_log_file"
                                echo "[$sys_time] 已写入进程 $proc (PID:$pid) 数据到 $proc_log_file"
                            fi
                        done
                    done
                fi

                # 等待采样间隔
                sleep "$SAMPLE_FREQ"
            done
        }

        # ---------------------- 启动脚本 ----------------------
        trap 'echo -e "\n监控已停止"; exit 0' SIGINT
        main_monitor
        """
        self.monitor_ps1 = """<#
        .SYNOPSIS
        Windows系统/进程监控（优化版）
        .DESCRIPTION
        - CPU统计：基于实际采集间隔计算（无硬编码sleep）
        - 兼容：PS2.0+
        - 优化：减少WMI调用、移除强制sleep，精准匹配-f指定的间隔
        #>
        param (
            [Alias("f")]
            [int]$freq = 5,                   # 输出间隔（秒，默认5），-f 1则1秒输出一次
            [Alias("o")]
            [string]$output = $PSScriptRoot,  # 输出目录
            [Alias("p")]
            [string[]]$proc,                  # 监控进程名
            [Alias("h")]
            [switch]$help
        )

        # 帮助信息
        if ($help) {
            Write-Host "用法：.\OneClickMonitor.ps1 [选项]"
            Write-Host "  -f <秒数>    输出间隔（默认5秒，-f 1则1秒输出一次）"
            Write-Host "  -o <路径>    输出目录（默认脚本所在目录）"
            Write-Host "  -p <进程名>  监控进程（多个空格分隔）"
            Write-Host "  -h           显示帮助"
            exit 0
        }

        # 全局配置（缓存静态数据，减少开销）
        $SYS_LOG_NAME = "system.log"
        $OUTPUT_DIR = [System.IO.Path]::GetFullPath($output)
        
        $cpuProcs = Get-CimInstance -ClassName Win32_Processor
        $LOGICAL_CORES = ($cpuProcs | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
        # 如果求和为0（罕见情况），则取第一个值
        if ($LOGICAL_CORES -eq 0 -or $null -eq $LOGICAL_CORES) {
            $LOGICAL_CORES = $cpuProcs[0].NumberOfLogicalProcessors
        }
        
        $script:diskReadLast = $null
        $script:diskWriteLast = $null
        $script:procCpuTimeCache = @{}  # 缓存进程上一次的CPU时间：Key=PID, Value=CPU时间戳
        $script:osCache = $null  # 变量缓存OS对象
        $script:perfFixed = $false # 记录是否已经执行过 lodctr /r

        # 创建输出目录
        if (-not (Test-Path $OUTPUT_DIR -PathType Container)) {
            New-Item -Path $OUTPUT_DIR -ItemType Directory -Force | Out-Null
        }
        $SYS_LOG_FILE = Join-Path $OUTPUT_DIR $SYS_LOG_NAME

        # 生成系统日志表头
        function Generate-SysHeader {
            return "系统时间,已用内存(MB),CPU使用率(%),磁盘读(KB/s),磁盘写(KB/s)"
        }

        # 生成进程日志表头
        function Generate-ProcessHeader {
            return "系统时间,已用内存(MB),CPU使用率(%),句柄数"
        }

        # 汇总进程的表头函数（无PID）
        function Generate-ProcessSummaryHeader {
            return "系统时间,已用内存(MB),CPU使用率(%),句柄数"
        }

        # 获取进程有效PID（仅存活进程）
        function Get-LivePids {
            param([string]$ProcName)
            $pids = @()
            Get-Process -Name $ProcName -ErrorAction SilentlyContinue | Where-Object {!$_.HasExited} | ForEach-Object {
                $pids += $_.Id
            }
            return $pids
        }

        # 采集系统指标（优化：减少不必要的计算）
        function Collect-SysMetrics {
            $sysTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

            # 1. 内存（MB）- 缓存OS对象减少调用
            $script:osCache = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue

            $totalMemMB = [math]::Round($script:osCache.TotalVisibleMemorySize / 1024, 0)
            $freeMemMB = [math]::Round($script:osCache.FreePhysicalMemory / 1024, 0)
            $usedMemMB = [math]::Round($totalMemMB - $freeMemMB, 0)

            # 2. CPU整体使用率（优化：改用Get-CimInstance，比Get-WmiObject快）
            $cpuLoad = Get-CimInstance -ClassName Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average
            $cpuUsage = if ($cpuLoad -ne $null) { [math]::Round($cpuLoad, 1) } else { 0 }

            # 3. 磁盘读写速率（KB/s - 优化：计算基于实际间隔）
        	$diskReadKB = 0
        	$diskWriteKB = 0
        	try {
        		# 用WMI获取格式化后的磁盘性能数据（_Total代表所有磁盘）
        		$diskPerf = Get-WmiObject -Class Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'" -ErrorAction Stop
        		# DiskReadBytesPerSec/WriteBytesPerSec 直接是每秒字节数，转KB
        		$diskReadKB = [math]::Round($diskPerf.DiskReadBytesPerSec / 1024, 0)
        		$diskWriteKB = [math]::Round($diskPerf.DiskWriteBytesPerSec / 1024, 0)
        	} catch {
        		# 异常时置0，不影响整体脚本
        		$diskReadKB = 0
        		$diskWriteKB = 0
        	}

            return @{
                Data = "$sysTime,$usedMemMB,$cpuUsage,$diskReadKB,$diskWriteKB"
                Time = $sysTime
                Timestamp = (Get-Date).ToFileTime()  # 用于计算间隔
            }
        }

        # 采集进程指标（核心优化：去掉硬编码sleep，基于缓存计算CPU）
        function Collect-ProcessMetrics {
            param([string]$ProcName, [array]$ProcessIDs, [string]$SysTime, [long]$CurrentTimestamp)
            $processDataList = @()

            foreach ($ProcID in $ProcessIDs) {
                $process = Get-Process -Id $ProcID -ErrorAction SilentlyContinue
                if (-not $process -or $process.HasExited) {
                    # 清理失效缓存
                    if ($script:procCpuTimeCache.ContainsKey($ProcID)) {
                        $script:procCpuTimeCache.Remove($ProcID)
                    }
                    continue
                }

                # 内存（MB）+ 句柄数（实时获取）
        		# 替换内存计算行的所有内容，直接用这一段
        		$wmiProc = Get-WmiObject -Class Win32_PerfFormattedData_PerfProc_Process -Filter "IDProcess='$ProcID'" -ErrorAction SilentlyContinue
                
                if (-not $wmiProc -or $null -eq $wmiProc.WorkingSetPrivate) {
                    Write-Host "警告: 进程 $ProcID (${ProcName}) 内存数据获取失败，跳过本次采集"
                    # 尝试修复性能计数器（仅一次）
                    if (-not $script:perfFixed) {
                        Write-Host "尝试执行 lodctr /r 重建性能计数器..."
                        try {
                            # 注意：需要管理员权限，否则可能失败
                            & "$env:windir/system32/lodctr.exe" /r 2>&1 | Out-Null
                            Write-Host "已执行 lodctr /r，请稍后重试监控"
                        } catch {
                            Write-Host "执行 lodctr /r 失败: $($_.Exception.Message)"
                        }
                        $script:perfFixed = $true
                    }
                    continue
                }
                
                # WorkingSetPrivate 是任务管理器“专用(KB)”的官方属性（单位：KB）
                $memMB = [math]::Round($wmiProc.WorkingSetPrivate / 1024 / 1024, 0)
                #$memMB = [math]::Round($process.WorkingSet64 / 1024 / 1024, 0)
                
                $handle = $process.HandleCount

                # CPU使用率计算（核心优化：基于缓存的上次CPU时间 + 实际间隔）
                $cpuTimeNow = $process.UserProcessorTime + $process.PrivilegedProcessorTime
                $procCpu = 0
                if ($script:procCpuTimeCache.ContainsKey($ProcID)) {
                    $lastData = $script:procCpuTimeCache[$ProcID]
                    $lastCpuTime = $lastData.CpuTime
                    $lastTimestamp = $lastData.Timestamp

                    # 计算实际间隔（秒）
                    $intervalSec = [math]::Max(0.001, ($CurrentTimestamp - $lastTimestamp) / 10000000)
                    # CPU时间差（秒）
                    $cpuDiffSec = ($cpuTimeNow - $lastCpuTime).TotalSeconds
                    # 计算CPU使用率（核心公式）
                    $procCpu = [math]::Round(($cpuDiffSec / $intervalSec) / $LOGICAL_CORES * 100, 0)
                    $procCpu = [math]::Max(0, [math]::Min(100, $procCpu))
                }

                # 更新缓存
                $script:procCpuTimeCache[$ProcID] = @{
                    CpuTime = $cpuTimeNow
                    Timestamp = $CurrentTimestamp
                }

                # 组装进程数据
                $processDataList += @{
                    PID  = $ProcID
                    Data = "$SysTime,$memMB,$procCpu,$handle"
                    Log  = Join-Path $OUTPUT_DIR "${ProcName}_${ProcID}.log"
                }
            }

            return $processDataList
        }

        # 主监控逻辑（优化：精准控制循环间隔）
        function Main-Monitor {
            # 初始化系统日志表头
            if (-not (Test-Path $SYS_LOG_FILE)) {
                Generate-SysHeader | Out-File -FilePath $SYS_LOG_FILE -Encoding utf8
            }

            Write-Host "监控启动：精准间隔${freq}秒 | 按Ctrl+C停止"
            while ($true) {
                $loopStart = Get-Date  # 记录本轮循环开始时间
                $currentTimestamp = $loopStart.ToFileTime()

                # 1. 采集系统数据并写入
                $sysResult = Collect-SysMetrics
                $sysResult.Data | Out-File -FilePath $SYS_LOG_FILE -Encoding utf8 -Append
                Write-Host "[$($sysResult.Time)] 系统数据已写入：$SYS_LOG_FILE"

                # 2. 采集进程数据 proc="doubao,pycharm64"
                if ($proc -and $proc.Count -gt 0) {
					# 拆分,分隔的字符串为数组
					$pList = $proc -split ',' | Where-Object { ![string]::IsNullOrWhiteSpace($_) }
					# 遍历拆分后的每个进程名
					foreach ($singleP in $pList) {
						$singleP = $singleP.Trim() # 去除首尾空格
						$pids = Get-LivePids -ProcName $singleP
						if ($pids.Count -eq 0) {
							Write-Host "[$($sysResult.Time)] 进程$singleP无有效PID，跳过"
							continue
						}
						# 采集进程数据
						$procDataList = Collect-ProcessMetrics -ProcName $singleP -ProcessIDs $pids -SysTime $sysResult.Time -CurrentTimestamp $currentTimestamp

						# 批量写入进程日志
						foreach ($procData in $procDataList) {
							$procLog = $procData.Log
							# 初始化进程日志表头（首次写入时）
							if (-not (Test-Path $procLog)) {
								Generate-ProcessHeader -ProcName $singleP -ProcessPID $procData.PID | Out-File -FilePath $procLog -Encoding utf8
							}
							$procData.Data | Out-File -FilePath $procLog -Encoding utf8 -Append
							Write-Host "[$($sysResult.Time)] 进程$singleP(PID:$($procData.PID))数据已写入：$procLog"
						}
						# 汇总当前进程名的所有子进程数据
						$totalMemMB = 0    # 内存总和
						$totalCpu = 0      # CPU总和
						$totalHandle = 0   # 句柄总和

						# 遍历单个进程数据，累加求和
						foreach ($procData in $procDataList) {
							# 拆分单个进程的Data，提取数值（格式：时间,内存,CPU,句柄）
							$dataParts = $procData.Data -split ','
							if ($dataParts.Count -eq 4) {
								$totalMemMB += [int]$dataParts[1]    # 累加内存
								$totalCpu += [int]$dataParts[2]      # 累加CPU
								$totalHandle += [int]$dataParts[3]   # 累加句柄
							}
						}

						# 写入汇总日志
						$summaryLog = Join-Path $OUTPUT_DIR "${singleP}.log"
						# 初始化汇总表头（首次写入时）
						if (-not (Test-Path $summaryLog)) {
							Generate-ProcessSummaryHeader -ProcName $singleP | Out-File -FilePath $summaryLog -Encoding utf8
						}
						# 组装汇总数据行
						$summaryData = "$($sysResult.Time),$totalMemMB,$totalCpu,$totalHandle"
						# 写入汇总日志
						$summaryData | Out-File -FilePath $summaryLog -Encoding utf8 -Append
						# 输出汇总日志提示
						Write-Host "[$($sysResult.Time)] 进程$p汇总数据已写入：$summaryLog"
					}
                }

                # 3. 精准计算等待时间（确保总间隔严格等于freq）
                $loopElapsed = (Get-Date) - $loopStart
                $waitTime = [math]::Max(0, $freq - $loopElapsed.TotalSeconds)
                if ($waitTime -gt 0) {
                    Start-Sleep -Seconds $waitTime
                }
            }
        }

        # 启动监控（捕获Ctrl+C）
        try {
            Main-Monitor
        }
        catch {
            Write-Host "监控异常：$($_.Exception.Message)"
            exit 1
        }
                
        """

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
                os.makedirs(self.monitor_data_path + "/OneClick", mode=0o777, exist_ok=True)
                ps1_path = self.monitor_data_path + "/OneClick/OneClickMonitor.ps1"

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
                user_path = f"/home/{username}/OneClick"
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
                    # 生成本地IP/OneClick文件夹
                    os.makedirs(self.monitor_data_path + "/OneClick", mode=0o777, exist_ok=True)
                    monitor_sh_path = self.monitor_data_path + "/OneClick/OneClickMonitor.sh"

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
                    shutil.rmtree(self.monitor_data_path)
                    self.message_info_box(("提示", f"本机监控数据已删除{self.monitor_data_path}"))
                    self.parent.update_run_info(f"本机监控数据已删除{self.monitor_data_path}")
                except FileNotFoundError:
                    # 捕获“文件夹不存在”的异常，不做任何操作
                    self.message_info_box(("提示", f"没有本机监控数据，无需删除{self.monitor_data_path}"))
                except Exception as e:
                    # 捕获其他未知异常
                    self.message_info_box(("提示", f"出错：文件夹 {self.monitor_data_path} ：{str(e)}"))
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
                    shutil.rmtree(self.monitor_data_path)
                    self.message_info_box(("提示", f"本机监控数据已删除{self.monitor_data_path}"))
                    self.parent.update_run_info(f"本机监控数据已删除{self.monitor_data_path}")
                except FileNotFoundError:
                    # 捕获“文件夹不存在”的异常，不做任何操作
                    self.message_info_box(("提示", f"没有本机监控数据，无需删除{self.monitor_data_path}"))
                except Exception as e:
                    # 捕获其他未知异常
                    self.message_info_box(("提示", f"删除出错：文件夹 {self.monitor_data_path} ：{str(e)}"))

                if self.ssh_stutas_label.text() != '已连接':
                    self.message_info_box(("提示", f"未连接服务器，服务器数据未删除"))
                    self.set_all_buttons_enable()
                    return

                user_path = f"/home/{username}/OneClick"

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
        user_path = f"/home/{username}/OneClick"

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
                self.message_info_box(("提示", f"监控数据已下载到{self.monitor_data_path}"))
                self.parent.update_run_info(f"监控数据已下载到{self.monitor_data_path}")
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
        data_path = self.monitor_data_path + '/OneClick'
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


if __name__ == '__main__':
    pass
