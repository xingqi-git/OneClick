import os
import sys
import subprocess
import platform
import time
from datetime import datetime
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, QObject, Qt
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidgetItem, QHeaderView, QMessageBox, QCheckBox,
                             QComboBox, QSpinBox, QLineEdit, QAbstractItemView)
from UI import server_check_run_dlg
from utils import qthread_worker
import paramiko
import socket


class ServerCheckRunDialog(QDialog, server_check_run_dlg.Ui_Dialog):
    """服务器检查运行时对话框（照搬资源监控的闭包 + OneClickWorker 模式）"""

    def __init__(self, button_id, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.button_id = button_id
        self.parent = parent

        self.check_config = self.parent.sc_buttons[button_id]['config']
        self.server_configs = self.check_config.get('服务器检查配置', {})
        self.servers_list = self.parent.servers_cfg
        self.server_info_dict = {s['服务器名称']: s for s in self.servers_list}

        self.check_items = self._build_check_items_list()
        self.button_name = self.check_config.get('指令名称', '未命名')

        # 照搬资源监控模式
        self.is_running = False
        self.stop_flag = False  # 普通 bool，worker 闭包直接捕获
        self.worker = None
        self.thread = None
        self.finished_count = 0

        self.setup_ui()
        self.setup_connections()
        self.update_button_states()

    def _build_check_items_list(self):
        """动态构建检查项列表"""
        items = ["连通", "SSH登录", "Root SSH权限", "系统时间", "防火墙"]
        used_numbers = set()
        for checks in self.server_configs.values():
            for item in checks:
                if item.startswith("命令回显"):
                    try:
                        used_numbers.add(int(item.replace("命令回显", "")))
                    except ValueError:
                        pass
        for num in sorted(used_numbers):
            items.append(f"命令回显{num}")
        return items

    def setup_ui(self):
        """初始化 UI"""
        self.tableWidget.setRowCount(len(self.check_items))
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setVerticalHeaderLabels(self.check_items)

        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.horizontalHeader().setCascadingSectionResizes(False)
        self.tableWidget.verticalHeader().setCascadingSectionResizes(False)
        self.tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tableWidget.setShowGrid(True)
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setSelectionMode(QAbstractItemView.NoSelection)
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectItems)

        self.tableWidget.setStyleSheet("""
            QTableWidget {
                border: 2px solid #cccccc;
                gridline-color: #e0e0e0;
                background-color: white;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
            }
            QHeaderView::section {
                background-color: #6c757d;
                color: white;
                padding: 8px;
                border: 1px solid #5a6268;
                font-weight: bold;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #6c757d;
                border: 1px solid #5a6268;
            }
        """)

        self.load_servers()

    def load_servers(self):
        for server_name in self.server_configs:
            self.add_server_column(server_name)

    def add_server_column(self, server_name):
        col = self.tableWidget.columnCount()
        self.tableWidget.insertColumn(col)
        self.tableWidget.setHorizontalHeaderItem(col, QTableWidgetItem(server_name))

        for row in range(self.tableWidget.rowCount()):
            check_item = self.tableWidget.verticalHeaderItem(row).text()
            if check_item in self.server_configs[server_name]:
                widget = self.create_result_widget(check_item, server_name)
                self.tableWidget.setCellWidget(row, col, widget)

    def create_result_widget(self, check_item, server_name):
        """创建结果显示控件（只读）"""
        config = self.server_configs[server_name][check_item]
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        status_label = QLabel("⏳ 等待检查")
        status_label.setAlignment(QtCore.Qt.AlignCenter)
        status_label.setProperty("result_status", True)
        layout.addWidget(status_label)

        check_box = QCheckBox("检查")
        check_box.setChecked(config.get('检查', True))
        check_box.setEnabled(False)
        layout.addWidget(check_box)

        if check_item in ["连通", "SSH登录", "Root SSH权限", "防火墙"]:
            combo = QComboBox()
            combo.addItem("是")
            combo.addItem("否")
            expected = config.get('期望结果', '是')
            combo.setCurrentIndex(0 if expected == '是' else 1)
            combo.setEnabled(False)
            layout.addWidget(combo)
        elif check_item == "系统时间":
            hlayout = QHBoxLayout()
            hlayout.setSpacing(4)
            hlayout.addWidget(QLabel("误差±"))
            spin = QSpinBox()
            spin.setMinimum(1)
            spin.setMaximum(60)
            spin.setValue(config.get('允许误差', 5))
            spin.setEnabled(False)
            hlayout.addWidget(spin)
            hlayout.addWidget(QLabel("分钟"))
            hlayout.addStretch()
            layout.addLayout(hlayout)
            
            sync_check = QCheckBox("自动同步时间")
            sync_check.setChecked(config.get('自动同步', False))
            sync_check.setEnabled(False)
            layout.addWidget(sync_check)
        elif check_item.startswith("命令回显"):
            cmd_line = QLineEdit()
            cmd_line.setText(config.get('命令', ''))
            cmd_line.setPlaceholderText("输入命令")
            cmd_line.setEnabled(False)
            layout.addWidget(cmd_line)

            type_combo = QComboBox()
            type_combo.addItem("包含")
            type_combo.addItem("不包含")
            expect_type = config.get('期望类型', '包含')
            type_combo.setCurrentIndex(0 if expect_type == '包含' else 1)
            type_combo.setEnabled(False)
            layout.addWidget(type_combo)

            content_line = QLineEdit()
            content_line.setText(config.get('期望内容', ''))
            content_line.setPlaceholderText("期望内容")
            content_line.setEnabled(False)
            layout.addWidget(content_line)

        widget.setLayout(layout)
        return widget

    def setup_connections(self):
        self.start_pushButton.clicked.connect(self.start_check)
        self.stop_pushButton.clicked.connect(self.stop_check_confirm)
        self.close_pushButton.clicked.connect(self.close_event)

    def update_button_states(self):
        self.start_pushButton.setEnabled(not self.is_running)
        self.stop_pushButton.setEnabled(self.is_running)

    def start_check(self):
        """开始检查（照搬资源监控：闭包 + OneClickWorker 模式）"""
        # 先清理旧的线程和worker
        if hasattr(self, 'thread') and self.thread:
            if self.thread.isRunning():
                self.stop_flag = True
                self.thread.quit()
                if not self.thread.wait(3000):  # 等待最多3秒
                    self.thread.terminate()
                    self.thread.wait()
        self.worker = None
        self.thread = None
        
        self.is_running = True
        self.stop_flag = False
        self.finished_count = 0
        self.update_button_states()

        btn = self.parent.sc_buttons[self.button_id]['button']
        btn.setProperty('executing', True)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

        # 重置所有状态
        for col in range(self.tableWidget.columnCount()):
            for row in range(self.tableWidget.rowCount()):
                self.update_cell_status(row, col, "⏳ 等待检查", None)

        # ============================================================
        # 关键：照搬资源监控的闭包模式！直接捕获 self
        # ============================================================
        def do_check_all_servers():
            """在 worker 线程中执行的检查函数（闭包直接捕获 self）"""
            server_names = list(self.server_configs.keys())
            total = len(server_names)

            for col_idx, server_name in enumerate(server_names):
                # 每次循环先检查是否停止
                if self.stop_flag:
                    return

                self._log(f"开始检查 {server_name}")
                self._check_single_server(server_name, col_idx)

                if self.stop_flag:
                    return

                self._log(f"{server_name} 检查完成")
                self.finished_count += 1

                # 检查是否全部完成
                if self.finished_count >= total and not self.stop_flag:
                    # 全部完成，发送信号
                    self.worker.info_signal.emit(("ALL_DONE",))

        def on_thread_finished():
            try:
                self.thread.deleteLater()
            except:
                pass

        def on_info_signal_received(data):
            """处理 worker 发回的信号"""
            if data[0] == "STATUS":
                # ("STATUS", row, col, status, success)
                _, row, col, status, success = data
                self.update_cell_status(row, col, status, success)
            elif data[0] == "ALL_DONE":
                self.on_all_checks_finished()

        # 创建 worker 和线程，完全照搬资源监控
        self.worker = qthread_worker.OneClickWorker(do_check_all_servers)
        self.thread = QThread()

        self.worker.moveToThread(self.thread)
        self.worker.info_signal.connect(on_info_signal_received)
        self.worker.log_signal.connect(lambda msg, level: self._log(msg, level))
        self.worker.finished.connect(self.worker.deleteLater)

        self.thread.started.connect(self.worker.run_task)
        self.thread.finished.connect(on_thread_finished)
        self.thread.start()

    def _check_single_server(self, server_name, col_idx):
        """检查单个服务器（在 worker 线程执行，通过 info_signal 更新 UI）"""
        server_info = self.server_info_dict.get(server_name, {})
        server_ip = server_info.get('IP', '')
        server_port = int(server_info.get('端口', 22))
        server_user = server_info.get('用户名', '')
        server_pass = server_info.get('密码', '')

        checks_config = self.server_configs.get(server_name, {})
        ping_success = False
        ssh_success = False
        ssh_client = None  # 局部变量，线程退出自动销毁

        for row_idx, check_item in enumerate(self.check_items):
            if self.stop_flag:
                return

            if check_item not in checks_config:
                continue

            check_config = checks_config[check_item]
            if not check_config.get('检查', True):
                continue

            # 先更新为检查中
            self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "⏳ 检查中...", None))

            # ================ 1. 连通检查 ================
            if check_item == "连通":
                if not server_ip:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "⚠️ 无IP", False))
                    continue

                ping_success = self._do_ping(server_ip)
                expected = check_config.get('期望结果', '是')

                if (ping_success and expected == '是') or (not ping_success and expected == '否'):
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "✔️ 通过", True))
                else:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "❌ 不通过", False))

                if not ping_success:
                    self._mark_rest_failed(col_idx, row_idx + 1, "❌ 网络不可达")
                    break

            # ================ 2. SSH 登录检查 ================
            elif check_item == "SSH登录":
                if not server_ip or not server_user or not server_pass:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "⚠️ 配置不完整", False))
                    self._mark_rest_failed(col_idx, row_idx + 1, "❌ SSH未配置")
                    break

                ssh_success, ssh_client = self._do_ssh_login(server_ip, server_port,
                                                              server_user, server_pass)
                expected = check_config.get('期望结果', '是')

                if (ssh_success and expected == '是') or (not ssh_success and expected == '否'):
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "✔️ 通过", True))
                else:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "❌ 不通过", False))

                if not ssh_success:
                    self._mark_rest_failed(col_idx, row_idx + 1, "❌ SSH不可用")
                    break

            # ================ 3. Root SSH 权限检查 ================
            elif check_item == "Root SSH权限":
                allowed, detail = self._check_root_ssh_permission(ssh_client, server_user, server_pass)
                expected = check_config.get('期望结果', '是')

                if (allowed and expected == '是') or (not allowed and expected == '否'):
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"✔️ {detail}", True))
                else:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"❌ {detail}", False))

            # ================ 4. 系统时间检查 ================
            elif check_item == "系统时间":
                allow_minutes = int(check_config.get('允许误差', 5))
                auto_sync = check_config.get('自动同步', False)
                
                ok, diff = self._check_system_time(ssh_client)
                is_ok = (diff <= allow_minutes)
                
                if not is_ok and auto_sync:
                    # 尝试同步时间
                    sync_success = self._sync_server_time(ssh_client, server_user, server_pass)
                    
                    if sync_success:
                        # 同步成功，等待一下让时间生效，再重新检查（只检查不显示）
                        time.sleep(0.5)
                        ok, new_diff = self._check_system_time(ssh_client)
                        self.worker.info_signal.emit(
                            ("STATUS", row_idx, col_idx, f"✔️ 原偏差{diff:.1f}分,已同步", True)
                        )
                    else:
                        # 同步失败
                        self.worker.info_signal.emit(
                            ("STATUS", row_idx, col_idx, f"❌ 偏差{diff:.1f}分,同步失败", False)
                        )
                else:
                    if is_ok:
                        self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"✔️ 偏差{diff:.1f}分", True))
                    else:
                        self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"❌ 偏差{diff:.1f}分", False))

            # ================ 5. 防火墙检查 ================
            elif check_item == "防火墙":
                fw_active, detail = self._check_firewall(ssh_client)
                expected = check_config.get('期望结果', '是')

                if (fw_active and expected == '是') or (not fw_active and expected == '否'):
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"✔️ {detail}", True))
                else:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, f"❌ {detail}", False))

            # ================ 6. 命令回显检查 ================
            elif check_item.startswith("命令回显"):
                cmd = check_config.get('命令', '')
                expect_type = check_config.get('期望类型', '包含')
                expect_content = check_config.get('期望内容', '')

                match, _ = self._check_cmd_echo(ssh_client, cmd, expect_type, expect_content)
                if match:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "✔️ 匹配", True))
                else:
                    self.worker.info_signal.emit(("STATUS", row_idx, col_idx, "❌ 不匹配", False))

        # 检查完关闭 SSH
        if ssh_client:
            try:
                ssh_client.close()
            except:
                pass

    def _mark_rest_failed(self, col_idx, start_row, reason):
        """标记剩余检查项失败"""
        for row_idx in range(start_row, len(self.check_items)):
            self.worker.info_signal.emit(("STATUS", row_idx, col_idx, reason, False))

    # ============================================================
    # 以下是具体检查实现
    # ============================================================

    def _do_ping(self, host):
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-w', '2', host]
            result = subprocess.call(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result == 0
        except Exception:
            return False

    def _do_ssh_login(self, host, port, username, password):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=host, port=port, username=username, password=password, timeout=5)
            return True, ssh
        except Exception:
            return False, None

    def _check_root_ssh_permission(self, ssh_client, username, password):
        if not ssh_client:
            return False, "连接不可用"
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                "grep -i '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null", timeout=3)
            output = stdout.read().decode('utf-8', errors='ignore').strip()

            if not output:
                stdin, stdout, stderr = ssh_client.exec_command(
                    "cat /etc/ssh/sshd_config 2>/dev/null | grep -v '^#' | grep -i PermitRootLogin", timeout=3)
                output = stdout.read().decode('utf-8', errors='ignore').strip()

            if not output:
                return True, "默认允许"

            value = output.split(None, 1)[-1].strip().lower()

            if value == 'yes':
                return True, "完全允许"
            elif value == 'no':
                return False, "完全禁止"
            elif value == 'prohibit-password':
                return True, "仅密钥登录"
            elif value == 'forced-commands-only':
                return True, "仅强制命令"
            else:
                return True, f"配置: {value}"
        except Exception:
            return False, "检查出错"

    def _sync_server_time(self, ssh_client, server_user, server_pass):
        """同步服务器时间到本地时间"""
        try:
            # 获取本地时间，格式化为 "YYYY-MM-DD HH:MM:SS"
            local_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 构建date命令，直接设置时间
            date_cmd = f"date -s '{local_time_str}'"
            
            # 先尝试直接执行
            stdin, stdout, stderr = ssh_client.exec_command(date_cmd, timeout=5)
            err = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if not err:
                # 同步成功，还要尝试更新硬件时钟
                try:
                    hwclock_cmd = "hwclock -w"
                    ssh_client.exec_command(hwclock_cmd, timeout=3)
                except:
                    pass
                return True
            
            # 如果直接执行失败，尝试用sudo
            if server_pass:
                # 用sudo执行
                sudo_cmd = f"echo {server_pass} | sudo -S {date_cmd}"
                stdin, stdout, stderr = ssh_client.exec_command(sudo_cmd, timeout=5)
                output = stdout.read().decode('utf-8', errors='ignore')
                err = stderr.read().decode('utf-8', errors='ignore').strip()
                
                # 检查是否成功
                if "password" not in err.lower() and len(err) < 100:
                    # 尝试更新硬件时钟
                    try:
                        hwclock_cmd = f"echo {server_pass} | sudo -S hwclock -w"
                        ssh_client.exec_command(hwclock_cmd, timeout=3)
                    except:
                        pass
                    return True
            
            return False
        except Exception:
            return False

    def _check_system_time(self, ssh_client):
        if not ssh_client:
            return False, 9999
        try:
            # 获取服务器当前时间戳（本地时区）
            stdin, stdout, stderr = ssh_client.exec_command("date +%s", timeout=3)
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            if not output.isdigit():
                return False, 9999

            # 比较本地时间戳和服务器时间戳
            server_timestamp = int(output)
            local_timestamp = int(datetime.now().timestamp())
            diff_seconds = abs(server_timestamp - local_timestamp)
            diff_minutes = diff_seconds / 60.0
            return True, diff_minutes
        except Exception:
            return False, 9999

    def _check_firewall(self, ssh_client):
        if not ssh_client:
            return False, "连接不可用"
        try:
            # 1. firewalld
            stdin, stdout, stderr = ssh_client.exec_command(
                "systemctl is-active firewalld 2>/dev/null", timeout=3)
            result = stdout.read().decode('utf-8', errors='ignore').strip()
            if result == 'active':
                return True, "firewalld运行中"
            if result == 'inactive':
                return False, "firewalld未运行"

            # 2. ufw
            stdin, stdout, stderr = ssh_client.exec_command(
                "ufw status 2>/dev/null | grep -i 'status'", timeout=3)
            result = stdout.read().decode('utf-8', errors='ignore').strip()
            if 'active' in result.lower():
                return True, "ufw运行中"
            if 'inactive' in result.lower():
                return False, "ufw未运行"

            # 3. SELinux
            stdin, stdout, stderr = ssh_client.exec_command(
                "getenforce 2>/dev/null", timeout=3)
            result = stdout.read().decode('utf-8', errors='ignore').strip()
            if result == 'Enforcing':
                return True, "SELinux强制模式"
            if result == 'Permissive':
                return False, "SELinux宽容模式"

            return False, "未检测到防火墙"
        except Exception:
            return False, "检查出错"

    def _check_cmd_echo(self, ssh_client, cmd, expect_type, expect_content):
        if not ssh_client or not cmd.strip():
            return False, ""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=5)
            output = stdout.read().decode('utf-8', errors='ignore')
            output += stderr.read().decode('utf-8', errors='ignore')

            if expect_type == "包含":
                return expect_content in output, output
            else:
                return expect_content not in output, output
        except Exception:
            return False, ""

    # ============================================================
    # UI 更新
    # ============================================================

    def stop_check_confirm(self):
        reply = QMessageBox.question(
            self, "确认", "确定要停止所有检查吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_flag = True
            self.is_running = False
            self.update_button_states()
            
            # 停止后清理线程和worker
            if hasattr(self, 'thread') and self.thread:
                if self.thread.isRunning():
                    self.thread.quit()
                    if not self.thread.wait(3000):
                        self.thread.terminate()
                        self.thread.wait()
            self.worker = None
            self.thread = None

    def on_all_checks_finished(self):
        self.is_running = False
        self.update_button_states()

        btn = self.parent.sc_buttons[self.button_id]['button']
        btn.setProperty('executing', False)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

        QMessageBox.information(self, "完成", "所有服务器检查完成！")
        self._log("全部完成")
        
        # 检查完成后清理线程和worker
        if hasattr(self, 'thread') and self.thread:
            self.thread.quit()
            self.thread.wait(1000)
        self.worker = None
        self.thread = None

    def update_cell_status(self, row, col, status, success=None):
        try:
            widget = self.tableWidget.cellWidget(row, col)
            if not widget:
                return
            for label in widget.findChildren(QLabel):
                if label.property("result_status"):
                    label.setText(status)
                    if success is True:
                        label.setStyleSheet("color: green;")
                    elif success is False:
                        label.setStyleSheet("color: red;")
                    else:
                        label.setStyleSheet("color: #6c757d;")
                    break
        except Exception:
            pass

    def close_event(self):
        """点击关闭按钮"""
        if self.is_running and self.thread and self.thread.isRunning():
            # 正在检查中，提示确认
            reply = QMessageBox.question(
                self, "确认",
                "正在检查中，确定要停止并关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.stop_flag = True
        self.is_running = False
        if self.thread and self.thread.isRunning():
            self.thread.quit()
        self.close()

    def closeEvent(self, event):
        """点击窗口右上角X关闭"""
        if self.is_running and self.thread and self.thread.isRunning():
            # 正在检查中，提示确认
            reply = QMessageBox.question(
                self, "确认",
                "正在检查中，确定要停止并关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.stop_flag = True
        self.is_running = False
        if self.thread and self.thread.isRunning():
            self.thread.quit()
        event.accept()

    def _log(self, text, level="INFO"):
        try:
            self.parent.update_run_info(f"<{self.button_name}> {text}", level)
        except Exception:
            pass
