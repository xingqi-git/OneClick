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
        # 获取按钮名称，用于日志前缀
        self.button_name = self.parent.sc_buttons[button_id]['config'].get('指令名称', '资源监控')
        self.g_windows = []  # 保存所有图表窗口的引用
        self.last_log_size = 0  # 用于记录上次读取日志的位置
        from monitor_scripts import MONITOR_SH, MONITOR_SH_2, MONITOR_PS1
        self.monitor_sh_normal = MONITOR_SH
        self.monitor_sh_embedded = MONITOR_SH_2
        self.monitor_ps1 = MONITOR_PS1

        # （脚本内容已移到 monitor_scripts.py 中）

        # 按钮逻辑和窗口默认值
        self.process_input_plainTextEdit.setPlainText(self.parent.sc_buttons[button_id]['config']['进程'])
        
        # 采样频率输入验证（失去光标后验证，只允许正整数，非法自动改为默认5）
        def validate_freq():
            text = self.freq_lineEdit.text().strip()
            if not text.isdigit() or int(text) <= 0:
                self.freq_lineEdit.setText('5')
        self.freq_lineEdit.editingFinished.connect(validate_freq)
        
        # 采样频率回显
        freq_value = self.parent.sc_buttons[button_id]['config']['采样频率']
        self.freq_lineEdit.setText(freq_value)
        validate_freq()  # 初始化时验证一次
        
        # 监控时长回显
        duration_value = self.parent.sc_buttons[button_id]['config'].get('监控时长', '')
        duration_unit = self.parent.sc_buttons[button_id]['config'].get('监控时长单位', '天')
        
        # 监控时长输入验证（失去光标后验证，只允许0和正整数，非法自动改为默认0）
        def validate_duration():
            text = self.duration_lineEdit.text().strip()
            if not text.isdigit() or int(text) < 0:
                self.duration_lineEdit.setText('0')
        self.duration_lineEdit.editingFinished.connect(validate_duration)
        
        self.duration_lineEdit.setText(duration_value)
        validate_duration()  # 初始化时验证一次
        # 设置单位下拉框
        unit_index_map = {'秒': 0, '分钟': 1, '小时': 2, '天': 3}
        self.duration_comboBox.setCurrentIndex(unit_index_map.get(duration_unit, 3))
        
        # 根据是本机监控还是服务器监控，更新UI显示的监控内容
        if self.parent.sc_buttons[button_id]['config']['IP'] == '':
            # 本机监控
            self.sys_plainTextEdit.setPlainText("已用内存(MB)\nCPU使用率(%)\n磁盘读(KB/s)\n磁盘写(KB/s)")
            self.process_plainTextEdit.setPlainText("已用内存(MB)\nCPU使用率(%)\n句柄数")
            # 本机监控时隐藏嵌入式勾选框
            self.embedded_checkBox.setVisible(False)
            if hasattr(self, 'embedded_label'):
                self.embedded_label.setVisible(False)
        else:
            # 服务器监控
            self.sys_plainTextEdit.setPlainText("已用内存(MB)\nCPU使用率(%)\n磁盘读(KB/s)\n磁盘写(KB/s)\n文件描述符\nSocket描述符\n进程数")
            self.process_plainTextEdit.setPlainText("进程RSS(MB)\n堆内存VmData(MB)\n进程CPU(%)\n进程FD数\n进程Socket数")
        
        # 回显嵌入式勾选状态
        self.embedded_checkBox.setChecked(self.parent.sc_buttons[button_id]['config'].get('嵌入式', False))
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
        self._operation_running = False  # 标记是否正在执行操作，有操作时不更新按钮状态

        # 用于保存数据的根目录名称 本机或IP
        if self.parent.sc_buttons[button_id]['config']['IP'] == '':
            self.data_dir_name = 'local'
            self.download_pushButton.setVisible(False)  # 本机监控不显示下载按钮
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
        self.update_status(('本机', '未知', ''))

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
                
                # ============ 1. 判断脚本状态 ============
                if not pids:
                    script_status = "无监控"
                else:
                    script_status = "监控中"

                # ============ 2. 读取运行日志（取最近10000行，控制内存） ============
                log_content = ""
                local_log_path = os.path.join(self.monitor_data_path, "Monitor", "OneClickMonitor.log")
                try:
                    if os.path.exists(local_log_path):
                        with open(local_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            # 只取最后10000行
                            if len(lines) > 10000:
                                lines = lines[-10000:]
                            log_content = ''.join(lines).strip()
                except Exception:
                    pass  # 日志读取失败不影响
                
                # 发送信号更新 UI
                worker.info_signal.emit(('本机', script_status, log_content))

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
        worker.info_signal.connect(self.update_status)
        worker.finished.connect(worker.deleteLater)

        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def on_ssh_button_click(self):
        self.update_status(('连接中...', '未知', ''))

        ip = self.parent.sc_buttons[self.button_id]['config']['IP']
        port = self.parent.sc_buttons[self.button_id]['config']['端口']
        username = self.parent.sc_buttons[self.button_id]['config']['用户名']
        password = self.parent.sc_buttons[self.button_id]['config']['密码']
        work_dir = self.parent.sc_buttons[self.button_id]['config'].get('文件暂存路径', '')

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
                        worker.info_signal.emit(("连接中...", "未知", ""))
                        continue
                try:
                    # 检查是否有监控 - 用基础ps命令，兼容嵌入式BusyBox
                    cmd = "ps | grep OneClickMonitor | grep -v grep | wc -l"
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(cmd)
                    if stderr.read():
                        worker.info_signal.emit(("已连接", "未知", ""))
                        continue
                    monitor_count = stdout.read().decode('utf-8').strip()
                    if not monitor_count:
                        worker.info_signal.emit(("已连接", "未知", ""))
                        continue
                    
                    # ============ 1. 判断脚本状态 ============
                    if monitor_count[-1] == "0":
                        script_status = "无监控"
                    else:
                        script_status = "监控中"

                    # ============ 2. 读取运行日志（取最近10000行，控制流量） ============
                    log_content = ""
                    if work_dir:
                        try:
                            remote_log_path = f"{work_dir}/OneClick/Monitor/OneClickMonitor.log"
                            stdin, stdout, stderr = ssh_client.ssh.exec_command(f"tail -n 10000 {remote_log_path} 2>/dev/null")
                            log_content = stdout.read().decode('utf-8').strip()
                        except Exception:
                            pass  # 日志读取失败不影响
                    
                    # 发送信号更新 UI
                    worker.info_signal.emit(("已连接", script_status, log_content))
                except Exception as e:
                    worker.log_signal.emit(f'检查监控状态失败: {e}')
                    worker.info_signal.emit(("连接中...", "未知", ""))
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
        worker.log_signal.connect(self._log)
        worker.finished.connect(worker.deleteLater)

        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def start_monitor(self):
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)
        # 如果是本机监控，需要创建本地监控脚本并执行
        if self.data_dir_name == 'local':
            monitor_status = self.monitor_stutas_label.text()
            # 未知：提示请等待获取监控状态，自动关闭
            if monitor_status == '未知':
                AutoCloseMessageBox("提示", "请等待获取监控状态", 2000, self).exec_()
                return
            # 监控中：提示存在运行中的监控，请先结束，自动关闭
            if monitor_status == '监控中':
                AutoCloseMessageBox("提示", "存在运行中的监控，请先结束", 2000, self).exec_()
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

                # 添加时长参数
                duration_text = self.duration_lineEdit.text().strip()
                if duration_text:
                    try:
                        duration = int(duration_text)
                        duration_unit = self.duration_comboBox.currentText()
                        # 转换为秒
                        if duration_unit == '分钟':
                            duration = duration * 60
                        elif duration_unit == '小时':
                            duration = duration * 3600
                        elif duration_unit == '天':
                            duration = duration * 86400
                        cmd.append('-d')
                        cmd.append(str(duration))
                    except ValueError:
                        worker.info_signal.emit(("提示", "监控时长必须是正整数"))
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
                            AutoCloseMessageBox("提示", "监控已经开始，关闭软件不会停止监控", 2000, self, 'start_monitor').exec_()
                            self._log("本机监控已经开始")
                            # 重置日志位置，下次读取会读取完整新日志
                            self.last_log_size = 0
                            self.log_textBrowser.clear()
                        else:
                            # 失败：普通提示框，需要手动启用按钮
                            self.message_info_box(("提示", f"监控脚本启动失败{result.returncode}"))
                            self._operation_running = False
                            self.set_all_buttons_enable()
                    except Exception as e:
                        # 失败：普通提示框，需要手动启用按钮
                        self.message_info_box(("提示", f"监控脚本启动失败{result}-{e}"))
                        self._operation_running = False
                        self.set_all_buttons_enable()
                # 成功的情况由 AutoCloseMessageBox.accept() 启用按钮
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
            worker.log_signal.connect(self._log)
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
                return
            # 已连接，未知：提示请等待获取监控状态，自动关闭
            if ssh_status == '已连接' and monitor_status == '未知':
                AutoCloseMessageBox("提示", "请等待获取监控状态", 2000, self).exec_()
                return
            if ssh_status != '已连接':
                AutoCloseMessageBox("提示", "服务器尚未连接", 2000, self).exec_()
                return
            if self.monitor_stutas_label.text() == '监控中':
                AutoCloseMessageBox("提示", "存在运行中的监控，请先结束", 2000, self).exec_()
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
                
                # 检查是否设置了监控时长
                duration_text = self.duration_lineEdit.text().strip()
                if duration_text:
                    try:
                        duration = int(duration_text)
                        duration_unit = self.duration_comboBox.currentText()
                        # 转换为秒
                        if duration_unit == '秒':
                            pass
                        elif duration_unit == '分钟':
                            duration = duration * 60
                        elif duration_unit == '小时':
                            duration = duration * 3600
                        elif duration_unit == '天':
                            duration = duration * 86400
                        monitor_cmd += f" -d {duration}"
                    except Exception as e:
                        self.message_info_box(("提示", f"监控时长必须是正整数{e}"))
                        self.set_all_buttons_enable()
                        return
            except Exception as e:
                self.message_info_box(("提示", f"请检查指令内容{e}"))
                self.set_all_buttons_enable()
                return
            # 基础命令（nohup会在执行时检测是否存在，兼容嵌入式系统
            monitor_cmd_bash = monitor_cmd

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
                    send_result = ssh_client.send_files(monitor_sh_path, f"{user_path}", float('inf'), '', work_dir)
                    if not send_result:
                        worker.info_signal.emit(("提示", "上传脚本失败"))
                        return False
                except Exception as e:
                    worker.info_signal.emit(("提示", f"上传脚本失败{e}"))
                    ssh_client.disconnect()
                    return False

                # 执行指令 - 先检测nohup是否存在，兼容嵌入式系统
                try:
                    # 先检测nohup
                    stdin, stdout, stderr = ssh_client.ssh.exec_command("which nohup 2>/dev/null")
                    nohup_path = stdout.read().decode().strip()
                    stderr.read().decode()
                    
                    # 构建最终执行命令
                    if nohup_path:
                        run_cmd = f"nohup {monitor_cmd_bash} >/dev/null 2>&1 & echo $!"
                    else:
                        # 嵌入式系统无nohup，直接后台运行
                        run_cmd = f"{monitor_cmd_bash} >/dev/null 2>&1 & echo $!"
                    
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(run_cmd)
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
                    AutoCloseMessageBox("提示", "监控已经开始，关闭软件不会停止监控", 2000, self, 'start_monitor').exec_()
                    self._log(f"{ip}监控开始")
                    # 重置日志位置，下次读取会读取完整新日志
                    self.last_log_size = 0
                    self.log_textBrowser.clear()
                else:
                    # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                    self._operation_running = False
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
            worker.log_signal.connect(self._log)
            worker.finished.connect(on_ssh_worker_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_ssh_thread_finished)
            thread.start()

    def stop_monitor(self):
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)
        if self.data_dir_name == 'local':
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
                
                # 写入停止日志
                local_log_path = os.path.join(self.monitor_data_path, "Monitor", "OneClickMonitor.log")
                try:
                    from datetime import datetime
                    stop_msg = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] 资源监控脚本已终止\n'
                    with open(local_log_path, 'a', encoding='utf-8') as f:
                        f.write(stop_msg)
                except Exception:
                    pass  # 写日志失败不影响停止功能
                
                return True

            def on_worker_finished(result):
                if result:
                    AutoCloseMessageBox("提示", "本机监控已经停止", 2000, self, 'stop_monitor').exec_()
                    self._log("本机监控停止")
                else:
                    # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                    self._operation_running = False
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
            worker.log_signal.connect(self._log)
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

            def do_stop_monitor():
                connect_result = ssh_client.connect()
                if not connect_result:
                    worker.info_signal.emit(("提示", f"停止监控失败，原因：连接服务器失败"))
                    return False
                try:
                    # 用基础命令查找PID，兼容嵌入式（避免pkill -f不支持）
                    find_pid_cmd = "ps | grep OneClickMonitor | grep -v grep | awk '{print $1}'"
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(find_pid_cmd)
                    pids = stdout.read().decode().strip().split()
                    err = stderr.read().decode().strip()
                    
                    # 遍历kill所有PID
                    for pid in pids:
                        if pid.isdigit():
                            ssh_client.ssh.exec_command(f"kill -9 {pid}")
                    
                    # 写入停止日志
                    work_dir = self.parent.sc_buttons[self.button_id]['config'].get('文件暂存路径', '')
                    if work_dir:
                        remote_log_path = f"{work_dir}/OneClick/Monitor/OneClickMonitor.log"
                        ssh_client.ssh.exec_command(
                            f'echo "[$(date "+%Y-%m-%d %H:%M:%S")] 资源监控脚本已终止" >> {remote_log_path}'
                        )
                    
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
                    AutoCloseMessageBox("提示", f"{ip}监控已经停止", 2000, self, 'stop_monitor').exec_()
                    self._log(f"{ip}监控已经停止")
                else:
                    # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                    self._operation_running = False
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
            worker.log_signal.connect(self._log)
            worker.info_signal.connect(self.message_info_box)
            worker.finished.connect(on_stop_monitor_finished)
            worker.finished.connect(worker.deleteLater)

            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)
            thread.start()

    def clean_data(self):
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)
        
        # 本机监控直接清除本地数据
        if self.data_dir_name == 'local':
            dialog = QMessageBox()
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("确认")
            dialog.setText("是否要清空本机所有历史监控数据，清空后无法恢复？")
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            result = dialog.exec_()
            
            if result == QMessageBox.StandardButton.Yes:
                try:
                    local_monitor_path = self.monitor_data_path + "/Monitor"
                    shutil.rmtree(local_monitor_path)
                    self._log(f"本机监控数据已删除{local_monitor_path}")
                    AutoCloseMessageBox("提示", "本机监控数据已清除", 2000, self).exec_()
                except FileNotFoundError:
                    AutoCloseMessageBox("提示", "没有本机监控数据，无需删除", 2000, self).exec_()
                except Exception as e:
                    AutoCloseMessageBox("提示", f"删除本地数据出错：{str(e)}", 2000, self).exec_()
            else:
                # 用户取消，手动启用按钮
                self._operation_running = False
                self.set_all_buttons_enable()
            return
        
        ssh_status = self.ssh_stutas_label.text()
        monitor_status = self.monitor_stutas_label.text()
        is_connected = (ssh_status == '已连接')
        
        if not is_connected or monitor_status in ('未知', '监控中'):
            # 未连接、监控状态未知、监控中：仅清除本地
            dialog = QMessageBox()
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("确认")
            if is_connected and monitor_status == '监控中':
                dialog.setText("监控中，仅可以清除本地数据，是否继续？")
            elif is_connected:
                dialog.setText("监控状态未知，仅可以清除本地数据，是否继续？")
            else:
                dialog.setText("未连接服务器，是否仅清除本地监控数据？")
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            result = dialog.exec_()
            
            if result == QMessageBox.StandardButton.Yes:
                try:
                    local_monitor_path = self.monitor_data_path + "/Monitor"
                    shutil.rmtree(local_monitor_path)
                    self._log(f"本机监控数据已删除{local_monitor_path}")
                    AutoCloseMessageBox("提示", "本地监控数据已清除", 2000, self).exec_()
                except FileNotFoundError:
                    AutoCloseMessageBox("提示", "没有本机监控数据，无需删除", 2000, self).exec_()
                except Exception as e:
                    AutoCloseMessageBox("提示", f"删除本地数据出错：{str(e)}", 2000, self).exec_()
            else:
                # 用户取消，手动启用按钮
                self._operation_running = False
                self.set_all_buttons_enable()
        else:
            # 已连接且监控状态已知（无监控）：四选项对话框
            dialog = QMessageBox()
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("选择清除范围")
            dialog.setText("请选择要清除的监控数据范围")
            btn_local = dialog.addButton("仅清除本地", QMessageBox.ButtonRole.ActionRole)
            btn_server = dialog.addButton("仅清除服务器", QMessageBox.ButtonRole.ActionRole)
            btn_all = dialog.addButton("全部清除", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(btn_cancel)
            result = dialog.exec_()
            
            clicked_btn = dialog.clickedButton()
            if clicked_btn == btn_cancel or clicked_btn is None:
                self._operation_running = False
                self.set_all_buttons_enable()
                return
            
            # 确定清除范围
            clean_local = (clicked_btn == btn_local) or (clicked_btn == btn_all)
            clean_server = (clicked_btn == btn_server) or (clicked_btn == btn_all)
            
            # 清除本地数据
            if clean_local:
                try:
                    local_monitor_path = self.monitor_data_path + "/Monitor"
                    shutil.rmtree(local_monitor_path)
                    self._log(f"本机监控数据已删除{local_monitor_path}")
                except FileNotFoundError:
                    pass
                except Exception as e:
                    AutoCloseMessageBox("提示", f"删除本地数据出错：{str(e)}", 2000, self).exec_()
                    return
            
            # 清除服务器数据
            if clean_server:
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
                    AutoCloseMessageBox("提示", f"请检查服务器配置{e}", 2000, self).exec_()
                    return
                
                work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
                user_path = f"{work_dir}/OneClick/Monitor"
                clean_cmd = f"rm -rf {user_path}"
                
                def do_clean_cmd():
                    connect_result = ssh_client.connect()
                    if not connect_result:
                        return False
                    try:
                        stdin, stdout, stderr = ssh_client.ssh.exec_command(clean_cmd)
                        err = stderr.read().decode().strip()
                        ssh_client.disconnect()
                        if err:
                            return False
                        return True
                    except Exception as e:
                        ssh_client.disconnect()
                        return False
                
                def on_clean_cmd_finished(result):
                    if clean_local and clean_server:
                        AutoCloseMessageBox("提示", "本地和服务器监控数据已清除", 2000, self).exec_()
                    elif clean_local:
                        AutoCloseMessageBox("提示", "本地监控数据已清除", 2000, self).exec_()
                    elif clean_server:
                        if result:
                            AutoCloseMessageBox("提示", f"{ip}服务器监控数据已清除", 2000, self).exec_()
                            self._log(f"{ip}监控数据已清空")
                        else:
                            AutoCloseMessageBox("提示", "清除服务器数据失败", 2000, self).exec_()
                    # 所有情况都由 AutoCloseMessageBox.accept() 启用按钮
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
                worker.log_signal.connect(self._log)
                worker.finished.connect(on_clean_cmd_finished)
                worker.finished.connect(worker.deleteLater)
                thread.started.connect(worker.run_task)
                thread.finished.connect(on_thread_finished)
                thread.start()
            else:
                # 只清除了本地，直接提示完成
                AutoCloseMessageBox("提示", "本地监控数据已清除", 2000, self).exec_()
                # 由 AutoCloseMessageBox.accept() 启用按钮

    def download_data(self):
        """
        从服务器下载监控数据，如果没有，弹窗提示
        如果有，下载
        :return:
        """
        ssh_status = self.ssh_stutas_label.text()
        if ssh_status != '已连接':
            AutoCloseMessageBox("提示", "请等待服务器连接", 2000, self).exec_()
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

        self._operation_running = True
        self.set_all_buttons_enable(False)
        # 从配置中获取文件暂存路径
        work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
        user_path = f"{work_dir}/OneClick/Monitor"

        # 本地保存路径
        def do_download_data():
            connect_result = ssh_client.connect()
            if not connect_result:
                return (False, "连接服务器失败")
            try:
                # 如果本地没有ip文件夹，则创建
                os.makedirs(self.monitor_data_path, mode=0o777, exist_ok=True)
                get_result = ssh_client.get_files(user_path, self.monitor_data_path, float('inf'), '', work_dir)
                ssh_client.disconnect()
                if not get_result:
                    return (False, "获取数据失败")
            except Exception as e:
                ssh_client.disconnect()
                return (False, f"{e}")
            return (True, "")

        def on_download_data_finished(result):
            success, err_msg = result
            if success:
                AutoCloseMessageBox("提示", f"监控数据已下载到{self.monitor_data_path}/Monitor", 2000, self).exec_()
                self._log(f"监控数据已下载到{self.monitor_data_path}/Monitor")
            else:
                # 失败显示提示
                AutoCloseMessageBox("提示", f"下载数据失败，原因：{err_msg}", 2000, self).exec_()
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

        worker.log_signal.connect(self._log)
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
        self.watch_pushButton.setEnabled(enable)
        # 下载按钮只在服务器监控时显示，本机时隐藏
        if self.data_dir_name != 'local':
            self.download_pushButton.setEnabled(enable)
        if enable:
            # 启用按钮时，根据当前显示的状态设置按钮
            ssh_status = self.ssh_stutas_label.text()
            monitor_status = self.monitor_stutas_label.text()
            is_monitoring = (monitor_status == '监控中')
            is_local = (ssh_status == '本机')
            monitor_unknown = (monitor_status == '未知')
            
            self.stop_pushButton.setEnabled(is_monitoring)
            # 清除按钮：本机+未知 或 本机+监控中 时禁用，其他情况都可用
            # 本机监控中不能删（正在写入），服务器监控中可以删本地
            if is_local and (monitor_unknown or is_monitoring):
                self.clean_pushButton.setEnabled(False)
            else:
                self.clean_pushButton.setEnabled(True)
        else:
            # 禁用所有按钮时都禁用
            self.stop_pushButton.setEnabled(False)
            self.clean_pushButton.setEnabled(False)
        self._can_close = enable

    def update_status(self, data):
        """
        更新状态
        :param data: 状态列表, 0: ssh状态, 1: 监控状态, 2: 日志内容(完整内容)
        :return:
        """
        self.ssh_stutas_label.setText(data[0])
        self.monitor_stutas_label.setText(data[1])
        
        # 日志完整重新显示（方案A）
        if len(data) > 2 and data[2]:
            self.log_textBrowser.setPlainText(data[2])
            # 自动滚动到底部
            scrollbar = self.log_textBrowser.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        elif len(data) > 2:
            # 日志为空时清空显示
            self.log_textBrowser.clear()
        
        # 有操作运行时不更新按钮状态，等操作完成后再更新
        if not getattr(self, '_operation_running', False):
            # 停止按钮可用性控制：只有监控中时可用
            is_monitoring = (data[1] == '监控中')
            self.stop_pushButton.setEnabled(is_monitoring)
            # 清除按钮：本机+未知 或 本机+监控中 时禁用，其他情况都可用
            # 本机监控中不能删（正在写入），服务器监控中可以删本地
            is_local = (data[0] == '本机')
            monitor_unknown = (data[1] == '未知')
            if is_local and (monitor_unknown or is_monitoring):
                self.clean_pushButton.setEnabled(False)
            else:
                self.clean_pushButton.setEnabled(True)

    def _has_monitor_data(self):
        """检查是否有监控数据（.log文件）"""
        data_path = self.monitor_data_path + '/Monitor'
        if not os.path.exists(data_path):
            return False
        # 检查是否有 .log 文件
        try:
            files = os.listdir(data_path)
            return any(f.lower().endswith('.log') for f in files)
        except:
            return False

    def _show_graph_window(self):
        """显示绘图窗口"""
        data_path = self.monitor_data_path + '/Monitor'
        g_window = GraphWindowLogic.GraphWindow(data_path, self)
        g_window.destroyed.connect(
            lambda obj: self.remove_window_from_list(obj)
        )
        self.g_windows.append(g_window)
        g_window.show()

    def _log(self, text, level='INFO'):
        """带按钮名称前缀的日志输出"""
        if text.startswith(f'<{self.button_name}>'):
            self.parent.update_run_info(text, level)
        else:
            self.parent.update_run_info(f'<{self.button_name}> {text}', level)

    def _show_local_data_graph(self):
        """展示本地数据（检查是否有数据，无数据则提示，有数据直接打开）"""
        if not self._has_monitor_data():
            AutoCloseMessageBox("提示", "没有检测到监控数据", 2000, self).exec_()
            return
        self._show_graph_window()

    def display_resource(self):
        if self.data_dir_name == 'local':
            # 本机监控
            self._show_local_data_graph()
        else:
            ssh_status = self.ssh_stutas_label.text()
            if ssh_status != '已连接':
                # 连接中，未知：直接展示本地数据
                self._show_local_data_graph()
            else:
                # 已连接：二选一对话框
                dialog = QMessageBox()
                dialog.setIcon(QMessageBox.Icon.Question)
                dialog.setWindowTitle("选择展示方式")
                dialog.setText("请选择展示方式")
                btn_local = dialog.addButton("本地数据绘图", QMessageBox.ButtonRole.ActionRole)
                btn_download = dialog.addButton("下载最新数据绘图", QMessageBox.ButtonRole.ActionRole)
                btn_cancel = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                dialog.exec_()

                clicked_btn = dialog.clickedButton()
                if clicked_btn == btn_local:
                    self._show_local_data_graph()
                elif clicked_btn == btn_download:
                    # 先下载最新数据再展示
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

                    self._operation_running = True
                    self.set_all_buttons_enable(False)
                    work_dir = self.parent.sc_buttons[self.button_id]['config']['文件暂存路径']
                    user_path = f"{work_dir}/OneClick/Monitor"

                    def do_download():
                        connect_result = ssh_client.connect()
                        if not connect_result:
                            return False
                        try:
                            os.makedirs(self.monitor_data_path, mode=0o777, exist_ok=True)
                            get_result = ssh_client.get_files(user_path, self.monitor_data_path, float('inf'), '', work_dir)
                            ssh_client.disconnect()
                            if not get_result:
                                return False
                        except Exception as e:
                            ssh_client.disconnect()
                            return False
                        return True

                    def on_download_finished(success):
                        # 下载完成后直接调用展示本地数据逻辑（不提示成功/失败）
                        self._operation_running = False
                        self.set_all_buttons_enable()
                        self._show_local_data_graph()
                        thread.quit()

                    def on_thread_finished():
                        thread.deleteLater()
                        self.parent.sc_threads.pop(self.work_thread_id)
                        self.work_thread_id = None

                    worker = qthread_worker.OneClickWorker(do_download)
                    thread = QThread()

                    self.parent.thread_count += 1
                    self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
                    self.parent.sc_threads[self.work_thread_id] = {
                        'worker': worker,
                        'thread': thread
                    }

                    worker.moveToThread(thread)
                    worker.log_signal.connect(self._log)
                    worker.finished.connect(on_download_finished)
                    worker.finished.connect(worker.deleteLater)
                    thread.started.connect(worker.run_task)
                    thread.finished.connect(on_thread_finished)
                    thread.start()

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

        # 保存数据到配置文件，下次打开自动填入
        self.parent.sc_buttons[self.button_id]['config']['进程'] = self.process_input_plainTextEdit.toPlainText()
        self.parent.sc_buttons[self.button_id]['config']['采样频率'] = self.freq_lineEdit.text()
        self.parent.sc_buttons[self.button_id]['config']['监控时长'] = self.duration_lineEdit.text()
        self.parent.sc_buttons[self.button_id]['config']['监控时长单位'] = self.duration_comboBox.currentText()
        self.parent.sc_buttons[self.button_id]['config']['嵌入式'] = self.embedded_checkBox.isChecked()
        self.parent.save_config()

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
    def __init__(self, title, text, timeout=2000, parent=None, after_close_action=None):
        """
        :param after_close_action: 关闭后的动作，None=默认调用set_all_buttons_enable()
                                  'start_monitor'=开始监控完成（清除按钮禁用，停止按钮可用）
                                  'stop_monitor'=停止监控完成
        """
        super().__init__(parent)
        self._parent_dialog = parent
        self._after_close_action = after_close_action
        self.setWindowTitle(title)
        self.setText(text)
        self.setStandardButtons(QMessageBox.Ok)
        self.setDefaultButton(QMessageBox.Ok)
        
        self.timeout = timeout
        self.remaining = timeout // 1000
        self._closed = False
        
        # 初始就设置为2秒
        self.button(QMessageBox.Ok).setText(f"确认({self.remaining}秒)")
        
        # 显示前设置标志，阻止状态检查线程更新按钮
        if self._parent_dialog and hasattr(self._parent_dialog, '_operation_running'):
            self._parent_dialog._operation_running = True
        
        # 绑定确定按钮点击事件（这是最可靠的方式）
        self.button(QMessageBox.Ok).clicked.connect(self._on_close)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)
        
        QTimer.singleShot(timeout, self._on_close)
    
    def _on_close(self):
        """无论手动点击还是超时，都走这个逻辑"""
        if self._closed:
            return
        self._closed = True
        
        self.timer.stop()
        if self._parent_dialog and hasattr(self._parent_dialog, '_operation_running'):
            self._parent_dialog._operation_running = False
            
            # 根据操作类型直接设置按钮状态，不读取标签（标签可能还没被状态线程更新）
            if self._after_close_action == 'start_monitor':
                # 开始监控完成
                is_local = (self._parent_dialog.data_dir_name == 'local')
                self._parent_dialog.start_pushButton.setEnabled(True)
                self._parent_dialog.stop_pushButton.setEnabled(True)
                self._parent_dialog.watch_pushButton.setEnabled(True)
                # 本机监控不显示下载按钮
                if not is_local:
                    self._parent_dialog.download_pushButton.setEnabled(True)
                # 本机监控中禁用清除按钮，服务器监控中可以清除本地
                self._parent_dialog.clean_pushButton.setEnabled(not is_local)
                self._parent_dialog._can_close = True  # 关键：允许关闭窗口
            elif self._after_close_action == 'stop_monitor':
                # 停止监控完成：清除按钮可用，停止按钮禁用
                is_local = (self._parent_dialog.data_dir_name == 'local')
                self._parent_dialog.start_pushButton.setEnabled(True)
                self._parent_dialog.stop_pushButton.setEnabled(False)
                self._parent_dialog.clean_pushButton.setEnabled(True)
                self._parent_dialog.watch_pushButton.setEnabled(True)
                # 本机监控不显示下载按钮
                if not is_local:
                    self._parent_dialog.download_pushButton.setEnabled(True)
                self._parent_dialog._can_close = True  # 关键：允许关闭窗口
            else:
                # 默认情况，根据当前状态自动设置
                self._parent_dialog.set_all_buttons_enable()
        self.accept()
    
    def update_countdown(self):
        self.remaining -= 1
        if self.remaining > 0:
            self.button(QMessageBox.Ok).setText(f"确认({self.remaining}秒)")
        else:
            self.timer.stop()
