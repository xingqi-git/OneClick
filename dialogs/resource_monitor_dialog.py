import os
import sys
import time
import subprocess
import psutil
import shutil
import GraphWindowLogic
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtWidgets import QDialog, QMessageBox
from UI import resource_monitor_dlg
from utils import ssh_tools, qthread_worker
from .base_dialog import SendCMDDialog, sc_class2str


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
        # 保存文件暂存路径，本机情况下为空
        if self.server_comboBox.currentData() == '本机':
            self.sc_cfg['文件暂存路径'] = ""
        else:
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
        if sc_data['IP'] == '':
            item_count = self.server_comboBox.count()
            self.server_comboBox.setCurrentIndex(item_count - 1)
            self.sshport_lineEdit.clear()
            self.work_dir_lineEdit.clear()
            self.linux_ip_lineEdit.setEnabled(False)
            self.username_lineEdit.setEnabled(False)
            self.passwd_lineEdit.setEnabled(False)
            self.sshport_lineEdit.setEnabled(False)
            self.work_dir_lineEdit.setEnabled(False)
        else:
            self.linux_ip_lineEdit.setText(sc_data['IP'])
            self.sshport_lineEdit.setText(sc_data['端口'])
            self.username_lineEdit.setText(sc_data['用户名'])
            self.passwd_lineEdit.setText(sc_data['密码'])
            # 回显文件暂存路径
            if '文件暂存路径' in sc_data:
                self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])
            self.linux_ip_lineEdit.setEnabled(True)
            self.username_lineEdit.setEnabled(True)
            self.passwd_lineEdit.setEnabled(True)
            self.sshport_lineEdit.setEnabled(True)
            self.work_dir_lineEdit.setEnabled(True)
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        self._loading = False  # 加载完成

    def reset(self):
        self.server_comboBox.setCurrentIndex(-1)
        self.linux_ip_lineEdit.clear()
        self.username_lineEdit.clear()
        self.passwd_lineEdit.clear()
        self.sshport_lineEdit.clear()
        self.work_dir_lineEdit.clear()
        self.sc_name_lineEdit.clear()
        self.linux_ip_lineEdit.setEnabled(True)
        self.username_lineEdit.setEnabled(True)
        self.passwd_lineEdit.setEnabled(True)
        self.sshport_lineEdit.setEnabled(True)
        self.work_dir_lineEdit.setEnabled(True)

    def select_server(self, index):
        if self.server_comboBox.currentData() == '本机':
            self.linux_ip_lineEdit.clear()
            self.username_lineEdit.clear()
            self.passwd_lineEdit.clear()
            self.sshport_lineEdit.clear()
            self.work_dir_lineEdit.clear()
            self.sc_name_lineEdit.setText(f'{sc_class2str[self.__class__.__name__]}：' + self.server_comboBox.currentText())
            self.linux_ip_lineEdit.setEnabled(False)
            self.username_lineEdit.setEnabled(False)
            self.passwd_lineEdit.setEnabled(False)
            self.sshport_lineEdit.setEnabled(False)
            self.work_dir_lineEdit.setEnabled(False)
        else:
            super().select_server(index)
            self.linux_ip_lineEdit.setEnabled(True)
            self.username_lineEdit.setEnabled(True)
            self.passwd_lineEdit.setEnabled(True)
            self.sshport_lineEdit.setEnabled(True)
            self.work_dir_lineEdit.setEnabled(True)


class ResourceMonitorDialog2(QDialog, resource_monitor_dlg.Ui_Dialog):
    def __init__(self, button_id, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # 设置窗口标志
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.button_id = button_id
        self.parent = parent
        self.g_windows = []  # 保存所有图表窗口的引用
        from monitor_scripts import MONITOR_SH, MONITOR_SH_2, MONITOR_PS1
        self.monitor_sh_normal = MONITOR_SH
        self.monitor_sh_embedded = MONITOR_SH_2
        self.monitor_ps1 = MONITOR_PS1

        # （脚本内容已移到 monitor_scripts.py 中）

        # 按钮逻辑和窗口默认值
        self.process_input_plainTextEdit.setPlainText(self.parent.sc_buttons[button_id]['config']['进程'])
        self.freq_lineEdit.setText(self.parent.sc_buttons[button_id]['config']['采样频率'])
        # 回显嵌入式勾选状态
        self.embedded_checkBox.setChecked(self.parent.sc_buttons[button_id]['config'].get('嵌入式', False))
        # 本机监控时禁用嵌入式勾选框
        if self.parent.sc_buttons[button_id]['config']['IP'] == '':
            self.embedded_checkBox.setEnabled(False)
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

    @property
    def monitor_sh(self):
        """根据嵌入式勾选状态返回对应的监控脚本"""
        if self.embedded_checkBox.isChecked():
            return self.monitor_sh_embedded
        return self.monitor_sh_normal

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
                    worker.info_signal.emit(("连接中...", "未知"))
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
            monitor_status = self.monitor_stutas_label.text()
            # 未知：提示请等待获取监控状态，自动关闭
            if monitor_status == '未知':
                AutoCloseMessageBox("提示", "请等待获取监控状态", 2000, self).exec_()
                self.set_all_buttons_enable()
                return
            # 监控中：提示存在运行中的监控，请先结束，自动关闭
            if monitor_status == '监控中':
                AutoCloseMessageBox("提示", "存在运行中的监控，请先结束", 2000, self).exec_()
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
                            AutoCloseMessageBox("提示", "监控已经开始，关闭软件不会停止监控", 2000, self).exec_()
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
            ssh_status = self.ssh_stutas_label.text()
            monitor_status = self.monitor_stutas_label.text()
            
            # 连接中，未知：提示请等待服务器连接，自动关闭
            if ssh_status == '连接中...' and monitor_status == '未知':
                AutoCloseMessageBox("提示", "请等待服务器连接", 2000, self).exec_()
                self.set_all_buttons_enable()
                return
            # 已连接，未知：提示请等待获取监控状态，自动关闭
            if ssh_status == '已连接' and monitor_status == '未知':
                AutoCloseMessageBox("提示", "请等待获取监控状态", 2000, self).exec_()
                self.set_all_buttons_enable()
                return
            if ssh_status != '已连接':
                AutoCloseMessageBox("提示", "服务器尚未连接", 2000, self).exec_()
                self.set_all_buttons_enable()
                return
            if self.monitor_stutas_label.text() == '监控中':
                AutoCloseMessageBox("提示", "存在运行中的监控，请先结束", 2000, self).exec_()
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
                # 从配置中获取文件暂存路径
                work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
                user_path = f"{work_dir}/OneClick/Monitor"
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
                    AutoCloseMessageBox("提示", "监控已经开始，关闭软件不会停止监控", 2000, self).exec_()
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

                # 从配置中获取文件暂存路径
                work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
                user_path = f"{work_dir}/OneClick/Monitor"

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
        # 从配置中获取文件暂存路径
        work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
        user_path = f"{work_dir}/OneClick/Monitor"

        # 本地保存路径
        def do_download_data():
            connect_result = ssh_client.connect()
            if not connect_result:
                worker.info_signal.emit(("提示", f"下载数据失败，原因：连接服务器失败"))
                return False
            try:
                # 如果本地没有ip文件夹，则创建
                os.makedirs(self.monitor_data_path, mode=0o777, exist_ok=True)
                get_result = ssh_client.get_files(user_path, self.monitor_data_path, float('inf'), '', work_dir)
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
                break

    def on_close_event(self, event):
        if not self._can_close:
            event.ignore()  # 忽略关闭事件
            self.message_info_box(("提示", "操作中，请稍后"))
            return

        # 保存数据，下次打开自动填入
        self.parent.sc_buttons[self.button_id]['config']['进程'] = self.process_input_plainTextEdit.toPlainText()
        self.parent.sc_buttons[self.button_id]['config']['采样频率'] = self.freq_lineEdit.text()
        self.parent.sc_buttons[self.button_id]['config']['嵌入式'] = self.embedded_checkBox.isChecked()

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


class AutoCloseMessageBox(QMessageBox):
    """自动关闭的消息框，带读秒倒计时"""
    def __init__(self, title, text, timeout=2000, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(text)
        self.setStandardButtons(QMessageBox.Ok)
        self.setDefaultButton(QMessageBox.Ok)
        
        self.timeout = timeout
        self.remaining = timeout // 1000
        
        # 初始就设置为2秒
        self.button(QMessageBox.Ok).setText(f"确认({self.remaining}秒)")
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)
        
        QTimer.singleShot(timeout, self.accept)
    
    def update_countdown(self):
        self.remaining -= 1
        if self.remaining > 0:
            self.button(QMessageBox.Ok).setText(f"确认({self.remaining}秒)")
        else:
            self.timer.stop()
