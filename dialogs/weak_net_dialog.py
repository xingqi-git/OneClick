import os
import time
from PyQt5 import QtCore
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QDialog, QMessageBox, QTableWidgetItem
from UI import weak_net_control_dlg
from utils import ssh_tools, qthread_worker
from .base_dialog import SendCMDDialog, sc_class2str


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
        self._loading = True  # 加载中，防止 textChanged 覆盖名称
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        self._loading = False  # 加载完成


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
        self.button_name = cfg.get('指令名称', '弱网')
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
        self.clear_log_pushButton.clicked.connect(self.clear_weaknet_logs)

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
                time.sleep(1)
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
                        worker.log_signal.emit(f'网卡列表: {nics}', 'INFO')
                        # 同时检查脚本状态，避免"已连接，未知"停留太久
                        cmd = "ps -ef | grep OneClickWeakNet.sh | grep -v grep | wc -l"
                        stdin, stdout, stderr = self.ssh_client.ssh.exec_command(cmd)
                        count = stdout.read().decode('utf-8').strip()
                        is_running = count and count[-1] != '0'
                        if not nics:
                            worker.info_signal.emit(('已连接', '无可用网卡', None))
                        else:
                            worker.info_signal.emit(('已连接', '运行中' if is_running else '已停止', nics))
                    else:
                        # 仅检查脚本状态
                        cmd = "ps -ef | grep OneClickWeakNet.sh | grep -v grep | wc -l"
                        stdin, stdout, stderr = self.ssh_client.ssh.exec_command(cmd)
                        count = stdout.read().decode('utf-8').strip()
                        is_running = count and count[-1] != '0'
                        worker.info_signal.emit(('已连接', '运行中' if is_running else '已停止', None))
                except Exception as e:
                    worker.log_signal.emit(f'状态检查失败: {e}', 'ERROR')
                    continue

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
        worker.log_signal.connect(self._log)
        worker.info_signal.connect(self.update_status)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def refresh_nics(self):
        if not self.ssh_client.is_connected():
            self.message_info_box(("提示", "SSH未连接"))
            return
        self.set_all_buttons_enable(False)  # 禁用所有按钮
        current_nic = self.nic_comboBox.currentText()

        def do_refresh():
            try:
                stdin, stdout, stderr = self.ssh_client.ssh.exec_command(
                    "ls /sys/class/net/ | grep -v '^lo$'"
                )
                nics = stdout.read().decode('utf-8').strip().split('\n')
                nics = [n.strip() for n in nics if n.strip()]
                return (True, nics)
            except Exception as e:
                return (False, str(e))

        def on_finished(result):
            success, data = result
            if success:
                nics = data
                self.nic_comboBox.clear()
                for nic in nics:
                    self.nic_comboBox.addItem(nic)
                if current_nic:
                    idx = self.nic_comboBox.findText(current_nic)
                    if idx >= 0:
                        self.nic_comboBox.setCurrentIndex(idx)
                self._log(f"网卡列表刷新: {nics}")
            else:
                self.message_info_box(("错误", f"获取网卡失败: {data}"))
            self.set_all_buttons_enable(True)  # 恢复所有按钮
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            if self.work_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_refresh)
        thread = QThread()
        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def show_weaknet_log(self):
        if not self.ssh_client.is_connected():
            self.message_info_box(("提示", "SSH未连接"))
            return
        self.set_all_buttons_enable(False)  # 禁用所有按钮
        cfg = self.parent.sc_buttons[self.button_id]['config']
        # 从配置中获取文件暂存路径
        work_dir = cfg.get('文件暂存路径', f"/home/{cfg.get('用户名', 'root')}")
        ip_name = cfg['IP'] if cfg['IP'] else 'local'
        local_dir = os.path.join(self.parent.get_default_path(), ip_name, "WeakNet").replace('\\', '/')
        local_log = local_dir + "/OneClickWeakNet.log"
        remote_log = f"{work_dir}/OneClick/WeakNet/OneClickWeakNet.log"

        def do_download():
            try:
                os.makedirs(local_dir, mode=0o777, exist_ok=True)
                self.ssh_client.get_files(remote_log, local_dir, float('inf'), '', work_dir)
            except Exception as e:
                self._log(f"下载日志失败: {e}")
            # 读取并显示日志（在主线程执行，所以通过 worker 回调传回来）
            content_result = ""
            try:
                if os.path.exists(local_log):
                    with open(local_log, 'r', encoding='utf-8') as f:
                        content_result = f.read().strip()
                    if not content_result:
                        content_result = "日志文件为空"
                else:
                    content_result = "暂无运行日志（尚未运行过弱网脚本）"
            except Exception as e:
                content_result = f"读取日志失败: {e}"
            return content_result

        def on_finished(result):
            self.tc_rule_textBrowser.setPlainText(result)
            self.set_all_buttons_enable(True)  # 恢复所有按钮
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            if self.work_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_download)
        thread = QThread()
        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def clear_weaknet_logs(self):
        """清空弱网记录（删除远程服务器上的WeakNet文件夹）"""
        # 检查状态
        ssh_status = self.ssh_stutas_label.text()
        script_status = self.script_stutas_label.text()

        if ssh_status == '未连接':
            self.message_info_box(("提示", "SSH未连接，无法删除弱网记录"))
            return
        if script_status == '运行中':
            self.message_info_box(("提示", "弱网脚本正在运行，请先停止后再删除记录"))
            return
        if script_status == '未知':
            self.message_info_box(("提示", "脚本状态未知，请等待状态获取完成后再操作"))
            return

        # 确认删除
        reply = QMessageBox.question(
            self, '确认删除',
            '确定要删除服务器上的弱网记录吗？此操作不可恢复。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.set_all_buttons_enable(False)

        def do_clear():
            try:
                cfg = self.parent.sc_buttons[self.button_id]['config']
                work_dir = cfg.get('文件暂存路径', f"/home/{cfg.get('用户名', 'root')}")
                remote_dir = f"{work_dir}/OneClick/WeakNet"
                # 删除远程目录
                self.ssh_client.ssh.exec_command(f"rm -rf {remote_dir}")
                return True, "弱网记录已删除"
            except Exception as e:
                return False, str(e)

        def on_finished(result):
            success, msg = result
            if success:
                self._log(msg)
                self.tc_rule_textBrowser.setPlainText("弱网记录已清空")
            else:
                self._log(f"删除弱网记录失败: {msg}")
            self.set_all_buttons_enable(True)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            if self.work_thread_id in self.parent.sc_threads:
                self.parent.sc_threads.pop(self.work_thread_id)
            self.work_thread_id = None

        worker = qthread_worker.OneClickWorker(do_clear)
        thread = QThread()
        self.parent.thread_count += 1
        self.work_thread_id = f'sc_thread_{self.parent.thread_count}'
        self.parent.sc_threads[self.work_thread_id] = {'worker': worker, 'thread': thread}

        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

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

    def generate_script(self, nic, loop_count, work_dir):
        log_file = f"{work_dir}/OneClick/WeakNet/OneClickWeakNet.log"
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

        self.set_all_buttons_enable(False)  # 禁用所有按钮，防止重复点击

        try:
            loop_val = self.loop_lineEdit.text().strip()
            loop_count = int(loop_val) if loop_val else 0
            if loop_count <= 0:
                loop_count = 99999999
        except ValueError:
            self.message_info_box(("提示", "循环次数必须是整数"))
            self.set_all_buttons_enable(True)  # 恢复所有按钮
            return

        cfg = self.parent.sc_buttons[self.button_id]['config']
        # 从配置中获取文件暂存路径
        work_dir = cfg.get('文件暂存路径', f"/home/{cfg.get('用户名', 'root')}")
        username = cfg['用户名']
        ip_name = cfg['IP'] if cfg['IP'] else 'local'
        local_dir = os.path.join(self.parent.get_default_path(), ip_name, "WeakNet").replace('\\', '/')

        script_content = self.generate_script(nic, loop_count, work_dir)
        user_path = f"{work_dir}/OneClick/WeakNet"
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
                send_result = self.ssh_client.send_files(local_path, f"{user_path}/", float('inf'), '', work_dir)
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
                self._log(f"{cfg['IP']}弱网脚本已启动")
                self.script_running = True
                self.script_stutas_label.setText("运行中")
                self.current_nic = nic  # 保存当前网卡，用于停止时清除规则
            else:
                self._log(f"{cfg['IP']}弱网脚本启动失败")
            self.set_all_buttons_enable(True)  # 恢复所有按钮
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
        worker.log_signal.connect(self._log)
        worker.finished.connect(on_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def stop_weak_net(self):
        if not self.script_running:
            self.message_info_box(("提示", "弱网脚本未在运行"))
            return
        self.set_all_buttons_enable(False)  # 禁用所有按钮，防止重复点击
        cfg = self.parent.sc_buttons[self.button_id]['config']
        work_dir = cfg.get('文件暂存路径', f"/home/{cfg.get('用户名', 'root')}")
        stop_cmd = "pkill -9 -f OneClickWeakNet.sh"
        clear_tc_cmd = f"tc qdisc del dev {self.current_nic} root 2>/dev/null || true"
        # 手动写停止日志（SIGKILL 不会触发 trap，所以补上）
        log_cmd = f'echo "[$(date "+%Y-%m-%d %H:%M:%S")] 弱网脚本已终止，tc规则已清除" >> "{work_dir}/OneClick/WeakNet/OneClickWeakNet.log"'

        def do_stop():
            connect_result = self.ssh_client.connect()
            if not connect_result:
                worker.info_signal.emit(("提示", "停止失败，连接服务器失败"))
                return False
            try:
                self.ssh_client.ssh.exec_command(stop_cmd)
                self.ssh_client.ssh.exec_command(clear_tc_cmd)  # 手动清除 tc 规则
                self.ssh_client.ssh.exec_command(log_cmd)  # 手动写停止日志
                time.sleep(0.5)
                self.ssh_client.disconnect()
                return True
            except Exception as e:
                worker.info_signal.emit(("提示", f"停止失败: {e}"))
                self.ssh_client.disconnect()
                return False

        def on_finished(result):
            if result:
                self.message_info_box(("提示", "弱网已停止"))
                self._log("弱网已停止")
                self.script_running = False
                self.script_stutas_label.setText("已停止")
            self.set_all_buttons_enable(True)  # 恢复所有按钮
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
        worker.log_signal.connect(self._log)
        worker.finished.connect(on_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def set_ui_editable(self, editable):
        pass

    def update_status(self, data):
        self.ssh_stutas_label.setText(data[0])
        if len(data) > 1 and data[1]:
            self.script_stutas_label.setText(data[1])
        # 同步脚本运行状态标记（每次状态更新都同步，不依赖网卡）
        if len(data) > 1 and data[1]:
            if data[1] == '运行中' and not self.script_running:
                self.script_running = True
            elif data[1] == '已停止' and self.script_running:
                self.script_running = False
        if len(data) > 2 and data[2]:
            # 更新网卡列表
            current = self.nic_comboBox.currentText()
            self.nic_comboBox.clear()
            for nic in data[2]:
                self.nic_comboBox.addItem(nic)
            if current:
                idx = self.nic_comboBox.findText(current)
                if idx >= 0:
                    self.nic_comboBox.setCurrentIndex(idx)

    def set_all_buttons_enable(self, enable=True):
        """启用/禁用所有操作按钮"""
        self.refresh_nic_pushButton.setEnabled(enable)
        self.add_rule_pushButton.setEnabled(enable)
        self.del_rule_pushButton.setEnabled(enable)
        self.move_up_pushButton.setEnabled(enable)
        self.move_down_pushButton.setEnabled(enable)
        self.show_tc_pushButton.setEnabled(enable)
        self.clear_log_pushButton.setEnabled(enable)
        self.start_pushButton.setEnabled(enable)
        self.stop_pushButton.setEnabled(enable)

    def _log(self, text, level='INFO'):
        """带按钮名称前缀的日志输出"""
        if text.startswith(f'<{self.button_name}>'):
            self.parent.update_run_info(text, level)
        else:
            self.parent.update_run_info(f'<{self.button_name}> {text}', level)

    def message_info_box(self, data):
        """提示框，2秒后自动关闭，带倒计时按钮（无进度条）"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(data[0])
        msg.setText(data[1])
        ok_btn = msg.addButton("确定(2秒)", QMessageBox.ButtonRole.AcceptRole)
        def update_button(remaining):
            try:
                ok_btn.setText(f"确定({remaining}秒)")
            except RuntimeError:
                pass  # 对象已被删除，忽略
        QtCore.QTimer.singleShot(1000, lambda: update_button(1))
        # 定时器也保护一下
        def safe_close():
            try:
                msg.close()
            except RuntimeError:
                pass
        QtCore.QTimer.singleShot(2000, safe_close)
        msg.exec_()

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
