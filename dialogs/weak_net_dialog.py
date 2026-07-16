import os
import time
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtWidgets import QDialog, QMessageBox, QTableWidgetItem
from UI import weak_net_control_dlg
from utils import ssh_tools, qthread_worker
from .base_dialog import SendCMDDialog, sc_class2str
import sip


# ===================================== 弱网脚本内容 =====================================
# 延迟用的 shell 脚本，和其他脚本类似，都是传输到服务器执行
WEAK_NET_SH = '''#!/bin/bash

# 参数解析
NIC="$1"
LOOP_COUNT="$2"
LOG_FILE="$3"
shift 3
# 剩余参数是规则列表：每个规则9个参数，用空格分隔
# 备份所有规则参数，便于循环中重复使用
ALL_RULES="$*"

# 追加写入启动标记（不覆盖原有日志）
echo "[$(date "+%Y-%m-%d %H:%M:%S")] ======== 弱网脚本启动 ========" >> "$LOG_FILE"

log() {
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $*" >> "$LOG_FILE"
}

cleanup() {
    tc qdisc del dev "$NIC" root 2>/dev/null || true
    log "弱网脚本已终止，tc规则已清除"
    exit 0
}
trap cleanup SIGINT SIGTERM

log "弱网脚本启动"
log "网卡: $NIC"
log "循环次数: $LOOP_COUNT"
log "规则列表:"

# 解析并打印所有规则（每个规则9个参数）
rule_idx=1
temp_args="$*"
set -- $temp_args
while [ $# -gt 0 ]; do
    delay="$1"
    jitter="$2"
    loss="$3"
    corrupt="$4"
    duplicate="$5"
    reorder="$6"
    reorder_gap="$7"
    rate="$8"
    duration="$9"
    shift 9
    
    log "  [规则$rule_idx] 延迟:${delay}ms 抖动:${jitter}ms 丢包:${loss}% 损坏:${corrupt}% 重复:${duplicate}% 重排:${reorder}% 重排间隔:${reorder_gap} 带宽:${rate}kbit 持续:${duration}s"
    rule_idx=$((rule_idx + 1))
done

loop_num=1
while true; do
    if [ "$LOOP_COUNT" != "0" ] && [ $loop_num -gt $LOOP_COUNT ]; then
        break
    fi
    log "第 $loop_num/$LOOP_COUNT 次循环开始"
    
    # 恢复参数并依次执行每条规则
    set -- $ALL_RULES
    rule_idx=1
    while [ $# -gt 0 ]; do
        delay="$1"
        jitter="$2"
        loss="$3"
        corrupt="$4"
        duplicate="$5"
        reorder="$6"
        reorder_gap="$7"
        rate="$8"
        duration="$9"
        shift 9
        
        # 先清除
        tc qdisc del dev "$NIC" root 2>/dev/null || true
        
        # 检查是否全0（仅清除）
        has_param=0
        if [ "$delay" != "0" ] || [ "$jitter" != "0" ] || [ "$loss" != "0" ] || [ "$corrupt" != "0" ] || [ "$duplicate" != "0" ] || [ "$reorder" != "0" ] || [ "$reorder_gap" != "0" ] || [ "$rate" != "0" ]; then
            has_param=1
        fi
        
        if [ $has_param -eq 1 ]; then
            # 构建 netem 参数
            netem_args=""
            if [ "$delay" != "0" ]; then
                netem_args="$netem_args delay ${delay}ms"
                if [ "$jitter" != "0" ]; then
                    netem_args="$netem_args ${jitter}ms"
                fi
            fi
            if [ "$loss" != "0" ]; then
                netem_args="$netem_args loss ${loss}%"
            fi
            if [ "$corrupt" != "0" ]; then
                netem_args="$netem_args corrupt ${corrupt}%"
            fi
            if [ "$duplicate" != "0" ]; then
                netem_args="$netem_args duplicate ${duplicate}%"
            fi
            if [ "$reorder" != "0" ]; then
                netem_args="$netem_args reorder ${reorder}%"
                if [ "$reorder_gap" != "0" ]; then
                    netem_args="$netem_args gap $reorder_gap"
                fi
            fi
            
            if [ "$rate" != "0" ]; then
                # 有带宽限制，用 htb + netem
                tc qdisc add dev "$NIC" root handle 1: htb default 1
                tc class add dev "$NIC" parent 1: classid 1:1 htb rate ${rate}kbit
                if [ -n "$netem_args" ]; then
                    tc qdisc add dev "$NIC" parent 1:1 handle 10: netem $netem_args
                fi
            else
                # 只有 netem
                if [ -n "$netem_args" ]; then
                    tc qdisc add dev "$NIC" root netem $netem_args
                fi
            fi
            log "  应用规则${rule_idx}: tc qdisc add ..."
        else
            log "  规则${rule_idx}: 仅清除弱网规则"
        fi
        
        sleep $duration
        log "  规则${rule_idx}结束（持续${duration}s）"
        
        rule_idx=$((rule_idx + 1))
    done
    
    loop_num=$((loop_num + 1))
done

log "所有循环已完成，清除tc规则"
cleanup
'''


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
        self.sc_cfg['文件暂存路径'] = self.work_dir_lineEdit.text().strip() if self.work_dir_lineEdit.text().strip() else ''

        if self.parent:
            if hasattr(self, 'button_id'):
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        self.accept()

    def edit_sc(self, button_id):
        self.button_id = button_id
        self._loading = True
        sc_data = self.parent.sc_buttons[button_id]['config']
        self.linux_ip_lineEdit.setText(sc_data['IP'])
        self.sshport_lineEdit.setText(sc_data['端口'])
        self.username_lineEdit.setText(sc_data['用户名'])
        self.passwd_lineEdit.setText(sc_data['密码'])
        self.sc_name_lineEdit.setText(sc_data['指令名称'])
        if '文件暂存路径' in sc_data:
            self.work_dir_lineEdit.setText(sc_data['文件暂存路径'])
        self._loading = False


class WeakNetControlDialog(QDialog, weak_net_control_dlg.Ui_Dialog):
    """弱网控制面板 - 100% 照抄资源监控架构"""
    def __init__(self, button_id, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

        self.button_id = button_id
        self.parent = parent
        self.stop_flag = False
        self.work_thread_id = None
        self.lookup_thread_id = None
        self._operation_running = False  # 操作进行中，防止状态检查线程更新按钮
        self._can_close = True  # 用于阻止关闭窗口
        self.last_log_size = 0  # 记录上次读取的日志大小，用于增量读取

        # 从配置恢复
        cfg = self.parent.sc_buttons[self.button_id]['config']
        self.button_name = cfg.get('指令名称', '弱网')
        rule_list = cfg.get('规则列表', [])
        
        # 运行次数输入验证（失去光标后验证，只允许0和正整数，非法自动改为默认0）
        def validate_loop_count():
            text = self.loop_lineEdit.text().strip()
            if not text.isdigit() or int(text) < 0:
                self.loop_lineEdit.setText('0')
        self.loop_lineEdit.editingFinished.connect(validate_loop_count)
        
        self.loop_lineEdit.setText(cfg.get('循环次数', '0'))
        validate_loop_count()  # 初始化时验证一次
        self.saved_nic = cfg.get('网卡', '')  # 保存配置的网卡，用于后续恢复
        self.work_dir = cfg.get('文件暂存路径', '')
        if not self.work_dir:
            self.work_dir = f"/home/{cfg.get('用户名', 'root')}"

        # 【关键】如果有保存的网卡，先添加到下拉框并选中，让界面打开就显示
        if self.saved_nic:
            self.nic_comboBox.addItem(self.saved_nic)
            self.nic_comboBox.setCurrentIndex(0)
        
        self.weak_net_data_path = os.path.join(self.parent.get_default_path(), cfg['IP'], "WeakNet").replace('\\', '/')
        self.remote_log_path = f"{self.work_dir}/OneClick/WeakNet/OneClickWeakNet.log"

        # 先恢复配置中的规则到表格，再设置输入限制
        self.restore_rules_from_config(rule_list)
        self.setup_table_validators()

        # 【关键】必须在表格填充后再保存原始配置快照！！！
        self._original_rules = self._get_table_rules()
        self._original_loop = cfg.get('循环次数', '0')
        self._original_nic = self.saved_nic

        # 信号连接
        self.add_rule_pushButton.clicked.connect(self.add_rule_to_queue)
        self.del_rule_pushButton.clicked.connect(self.del_rule_from_queue)
        self.move_up_pushButton.clicked.connect(self.move_rule_up)
        self.move_down_pushButton.clicked.connect(self.move_rule_down)
        self.start_pushButton.clicked.connect(self.start_weak_net)
        self.stop_pushButton.clicked.connect(self.stop_weak_net)
        self.save_cfg_pushButton.clicked.connect(self.save_config_only)
        self.clear_local_log_pushButton.clicked.connect(self.clear_server_logs)

        # 关闭事件
        self.closeEvent = self.on_close_event

        # 启动状态检查线程
        self.start_status_check()

    def setup_table_validators(self):
        """为表格单元格设置数字输入限制"""
        self.rule_tableWidget.cellChanged.connect(self.on_cell_changed)

    def on_cell_changed(self, row, col):
        """单元格内容变化时的处理，限制只能输入数字"""
        item = self.rule_tableWidget.item(row, col)
        if not item:
            return
        text = item.text().strip()
        if not text:
            item.setText('0')
            return
        # 检查是否为数字
        try:
            int(text)
        except ValueError:
            item.setText('0')

    def restore_rules_from_config(self, rule_list):
        """从配置恢复规则到表格"""
        self.rule_tableWidget.setRowCount(0)
        for rule in rule_list:
            self._add_rule_row(
                delay=rule.get('延迟', '0'),
                jitter=rule.get('抖动', '0'),
                loss=rule.get('丢包率', '0'),
                corrupt=rule.get('损坏率', '0'),
                duplicate=rule.get('重复率', '0'),
                reorder=rule.get('重排率', '0'),
                reorder_gap=rule.get('重排间隔', '0'),
                rate=rule.get('带宽', '0'),
                duration=rule.get('持续时长', '0')
            )

    def _add_rule_row(self, delay='0', jitter='0', loss='0', corrupt='0',
                      duplicate='0', reorder='0', reorder_gap='0', rate='0', duration='0'):
        """添加一行规则到表格"""
        row = self.rule_tableWidget.rowCount()
        self.rule_tableWidget.insertRow(row)

        # 设置单元格内容
        self.rule_tableWidget.setItem(row, 0, QTableWidgetItem(delay))
        self.rule_tableWidget.setItem(row, 1, QTableWidgetItem(jitter))
        self.rule_tableWidget.setItem(row, 2, QTableWidgetItem(loss))
        self.rule_tableWidget.setItem(row, 3, QTableWidgetItem(corrupt))
        self.rule_tableWidget.setItem(row, 4, QTableWidgetItem(duplicate))
        self.rule_tableWidget.setItem(row, 5, QTableWidgetItem(reorder))
        self.rule_tableWidget.setItem(row, 6, QTableWidgetItem(reorder_gap))
        self.rule_tableWidget.setItem(row, 7, QTableWidgetItem(rate))
        self.rule_tableWidget.setItem(row, 8, QTableWidgetItem(duration))

        # 设置对齐方式
        for col in range(9):
            item = self.rule_tableWidget.item(row, col)
            if item:
                item.setTextAlignment(QtCore.Qt.AlignCenter)

    def add_rule_to_queue(self):
        """添加一行空规则"""
        self._add_rule_row()

    def del_rule_from_queue(self):
        """删除选中的行"""
        rows = sorted(set(item.row() for item in self.rule_tableWidget.selectedItems()), reverse=True)
        for row in rows:
            self.rule_tableWidget.removeRow(row)

    def move_rule_up(self):
        """选中行上移"""
        current_row = self.rule_tableWidget.currentRow()
        if current_row <= 0:
            return
        for col in range(self.rule_tableWidget.columnCount()):
            item1 = self.rule_tableWidget.takeItem(current_row, col)
            item2 = self.rule_tableWidget.takeItem(current_row - 1, col)
            self.rule_tableWidget.setItem(current_row, col, item2 if item2 else QTableWidgetItem('0'))
            self.rule_tableWidget.setItem(current_row - 1, col, item1 if item1 else QTableWidgetItem('0'))
        self.rule_tableWidget.selectRow(current_row - 1)

    def move_rule_down(self):
        """选中行下移"""
        current_row = self.rule_tableWidget.currentRow()
        if current_row < 0 or current_row >= self.rule_tableWidget.rowCount() - 1:
            return
        for col in range(self.rule_tableWidget.columnCount()):
            item1 = self.rule_tableWidget.takeItem(current_row, col)
            item2 = self.rule_tableWidget.takeItem(current_row + 1, col)
            self.rule_tableWidget.setItem(current_row, col, item2 if item2 else QTableWidgetItem('0'))
            self.rule_tableWidget.setItem(current_row + 1, col, item1 if item1 else QTableWidgetItem('0'))
        self.rule_tableWidget.selectRow(current_row + 1)

    def _get_table_rules(self):
        """从表格获取所有规则"""
        rules = []
        for row in range(self.rule_tableWidget.rowCount()):
            def get_text(r, c):
                item = self.rule_tableWidget.item(r, c)
                text = item.text().strip() if item else '0'
                return text if text else '0'
            rule = {
                '延迟': get_text(row, 0),
                '抖动': get_text(row, 1),
                '丢包率': get_text(row, 2),
                '损坏率': get_text(row, 3),
                '重复率': get_text(row, 4),
                '重排率': get_text(row, 5),
                '重排间隔': get_text(row, 6),
                '带宽': get_text(row, 7),
                '带宽单位': 'kbit',
                '持续时长': get_text(row, 8),
            }
            rules.append(rule)
        return rules

    def start_status_check(self):
        """和资源监控一样：一个线程处理 SSH 状态、脚本状态、网卡刷新、日志显示"""
        self.update_status(('连接中...', '未知'))

        cfg = self.parent.sc_buttons[self.button_id]['config']
        ip = cfg['IP']
        port = cfg['端口']
        username = cfg['用户名']
        password = cfg['密码']

        # 一个 SSH 连接，用于所有状态检查
        ssh_client = ssh_tools.SSHTools()
        ssh_client.ip = ip
        ssh_client.port = port
        ssh_client.username = username
        ssh_client.password = password

        def do_status_check():
            while True:
                if self.stop_flag:
                    return
                time.sleep(1)
                # 检查是否有连接
                if not ssh_client.is_connected():
                    result = ssh_client.connect()
                    if not result:
                        worker.info_signal.emit(("连接中...", "未知", None, ""))
                        continue
                try:
                    # ============ 1. 检查脚本状态 ============
                    cmd = "ps | grep OneClickWeakNet | grep -v grep | wc -l"
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(cmd)
                    if stderr.read():
                        script_status = "未知"
                    else:
                        monitor_count = stdout.read().decode('utf-8').strip()
                        if not monitor_count:
                            script_status = "未知"
                        elif monitor_count[-1] == "0":
                            script_status = "已停止"
                        else:
                            script_status = "运行中"

                    # ============ 2. 刷新网卡 ============
                    stdin, stdout, stderr = ssh_client.ssh.exec_command(
                        "ls /sys/class/net/ | grep -v '^lo$'"
                    )
                    nic_output = stdout.read().decode('utf-8').strip()
                    nics = None
                    if nic_output:
                        nics = nic_output.split('\n')
                        nics = [n.strip() for n in nics if n.strip()]

                    # ============ 3. 读取运行日志（取最近10000行，控制流量） ============
                    log_content = ""
                    try:
                        stdin, stdout, stderr = ssh_client.ssh.exec_command(f"tail -n 10000 {self.remote_log_path} 2>/dev/null")
                        log_content = stdout.read().decode('utf-8').strip()
                    except Exception:
                        pass  # 日志读取失败不影响

                    # 发送信号更新 UI
                    worker.info_signal.emit(("已连接", script_status, nics, log_content))
                except Exception as e:
                    worker.log_signal.emit(f'状态检查失败: {e}')
                    worker.info_signal.emit(("连接中...", "未知", None, ""))
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
        worker.info_signal.connect(self.update_status)
        worker.log_signal.connect(self._log)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def save_config_only(self):
        """仅保存配置，不启动弱网"""
        cfg = self.parent.sc_buttons[self.button_id]['config']
        cfg['规则列表'] = self._get_table_rules()
        cfg['循环次数'] = self.loop_lineEdit.text()
        cfg['网卡'] = self.nic_comboBox.currentText()
        self.saved_nic = cfg['网卡']  # 更新内存中的保存网卡
        self.parent.save_config()
        # 更新原始配置基准，避免关闭时重复提示
        self._original_rules = self._get_table_rules()
        self._original_loop = self.loop_lineEdit.text()
        self._original_nic = self.saved_nic
        AutoCloseMessageBox("提示", "配置已保存", 2000, self).exec_()
        self._log("配置已保存")

    def update_status(self, status):
        """更新状态：(ssh_status, script_status, nics_list, log_content)"""
        if sip.isdeleted(self):
            return

        ssh_status, script_status = status[0], status[1]
        self.ssh_stutas_label.setText(ssh_status)
        self.script_stutas_label.setText(script_status)

        # 如果有网卡列表，并且不在操作中，更新下拉框
        if len(status) > 2 and status[2] is not None and not self._operation_running:
            nics = status[2]
            current_nic = self.nic_comboBox.currentText()
            self.nic_comboBox.clear()
            for nic in nics:
                self.nic_comboBox.addItem(nic)
            # 优先恢复保存的网卡，如果没有当前选择则恢复配置的网卡
            nic_to_restore = current_nic if current_nic else self.saved_nic
            if nic_to_restore:
                idx = self.nic_comboBox.findText(nic_to_restore)
                if idx >= 0:
                    self.nic_comboBox.setCurrentIndex(idx)

        # 日志完整重新显示（方案A）
        if len(status) > 3 and status[3]:
            self.log_textBrowser.setPlainText(status[3])
            # 自动滚动到底部
            scrollbar = self.log_textBrowser.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        elif len(status) > 3:
            # 日志为空时清空显示
            self.log_textBrowser.clear()

        # 有操作运行时不更新按钮状态，等操作完成后再更新
        if not self._operation_running:
            # 停止按钮可用性控制：只有运行中时可用
            is_running = (script_status == '运行中')
            self.stop_pushButton.setEnabled(is_running)
            # 清除日志按钮：运行中时禁用
            self.clear_local_log_pushButton.setEnabled(not is_running)

    def set_all_buttons_enable(self, enable=True):
        """设置所有按钮状态 - 和资源监控一样的逻辑"""
        self.start_pushButton.setEnabled(enable)
        self.save_cfg_pushButton.setEnabled(enable)
        self.add_rule_pushButton.setEnabled(enable)
        self.del_rule_pushButton.setEnabled(enable)
        self.move_up_pushButton.setEnabled(enable)
        self.move_down_pushButton.setEnabled(enable)
        if enable:
            # 启用按钮时，根据当前显示的状态设置按钮
            script_status = self.script_stutas_label.text()
            is_running = (script_status == '运行中')
            self.stop_pushButton.setEnabled(is_running)
            # 清除日志按钮：运行中时禁用
            self.clear_local_log_pushButton.setEnabled(not is_running)
        else:
            # 禁用所有按钮时都禁用
            self.stop_pushButton.setEnabled(False)
            self.clear_local_log_pushButton.setEnabled(False)
        self._can_close = enable

    def start_weak_net(self):
        """开始弱网 - 和资源监控完全一样的逻辑"""
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)

        # 状态检查
        ssh_status = self.ssh_stutas_label.text()
        script_status = self.script_stutas_label.text()
        
        # 连接中，未知：提示请等待服务器连接，自动关闭
        if ssh_status == '连接中...' and script_status == '未知':
            AutoCloseMessageBox("提示", "请等待服务器连接", 2000, self).exec_()
            return
        # 已连接，未知：提示请等待获取脚本状态，自动关闭
        if ssh_status == '已连接' and script_status == '未知':
            AutoCloseMessageBox("提示", "请等待获取脚本状态", 2000, self).exec_()
            return
        if ssh_status != '已连接':
            AutoCloseMessageBox("提示", "服务器尚未连接", 2000, self).exec_()
            return
        if script_status == '运行中':
            AutoCloseMessageBox("提示", "存在运行中的弱网脚本，请先停止", 2000, self).exec_()
            return

        # 检查规则
        rule_queue = self._get_table_rules()
        if not rule_queue:
            AutoCloseMessageBox("提示", "请先添加规则", 2000, self).exec_()
            return
        for idx, rule in enumerate(rule_queue, 1):
            duration = rule.get('持续时长', '0').strip()
            if not duration or duration == '0':
                AutoCloseMessageBox("提示", f"第{idx}行持续时长必须大于0", 2000, self).exec_()
                return

        nic = self.nic_comboBox.currentText()
        if not nic:
            AutoCloseMessageBox("提示", "请先选择网卡", 2000, self).exec_()
            return

        try:
            loop_val = self.loop_lineEdit.text().strip()
            loop_count = int(loop_val) if loop_val else 0
        except ValueError:
            AutoCloseMessageBox("提示", "循环次数必须是正整数", 2000, self).exec_()
            self.set_all_buttons_enable(True)
            self._operation_running = False
            return

        cfg = self.parent.sc_buttons[self.button_id]['config']

        # 新建 SSH 连接，用完即断
        start_ssh = ssh_tools.SSHTools()
        start_ssh.ip = cfg['IP']
        start_ssh.port = cfg['端口']
        start_ssh.username = cfg['用户名']
        start_ssh.password = cfg['密码']

        # 从配置中获取文件暂存路径
        work_dir = cfg['文件暂存路径']
        user_path = f"{work_dir}/OneClick/WeakNet"
        script_path = f"{user_path}/OneClickWeakNet.sh"

        # 构建脚本参数：nic loop_count log_path 规则参数...
        script_args = f"{nic} {loop_count} {self.remote_log_path}"
        for rule in rule_queue:
            script_args += f" {rule.get('延迟', '0')} {rule.get('抖动', '0')} {rule.get('丢包率', '0')} {rule.get('损坏率', '0')} {rule.get('重复率', '0')} {rule.get('重排率', '0')} {rule.get('重排间隔', '0')} {rule.get('带宽', '0')} {rule.get('持续时长', '0')}"

        def do_start():
            try:
                os.makedirs(f"{self.weak_net_data_path}", mode=0o777, exist_ok=True)
                local_script = f"{self.weak_net_data_path}/OneClickWeakNet.sh"
                with open(local_script, "w", encoding="utf-8", newline='\n') as f:
                    f.write(WEAK_NET_SH)

                # 连接 SSH
                if not start_ssh.connect():
                    worker.info_signal.emit(("提示", "连接服务器失败"))
                    return False

                # 创建远程目录
                start_ssh.ssh.exec_command(f"mkdir -p {user_path}")

                # 上传脚本
                send_result = start_ssh.send_files(local_script, f"{user_path}", float('inf'), '', work_dir)
                if not send_result:
                    worker.info_signal.emit(("提示", "上传脚本失败"))
                    start_ssh.disconnect()
                    return False

                # 给执行权限
                start_ssh.ssh.exec_command(f"chmod +x {script_path}")

                # 检测 nohup，兼容嵌入式
                stdin, stdout, stderr = start_ssh.ssh.exec_command("which nohup 2>/dev/null")
                has_nohup = bool(stdout.read().decode().strip())

                # 用完整路径直接执行（和资源监控一样），避免 cd 导致的问题
                if has_nohup:
                    monitor_cmd = f"nohup {script_path} {script_args} >/dev/null 2>&1 & echo $!"
                else:
                    monitor_cmd = f"{script_path} {script_args} >/dev/null 2>&1 & echo $!"

                stdin, stdout, stderr = start_ssh.ssh.exec_command(monitor_cmd)
                pid = stdout.read().decode().strip()
                err = stderr.read().decode().strip()

                start_ssh.disconnect()

                if err:
                    worker.info_signal.emit(("提示", f"执行指令失败{err}"))
                    return False
                if pid.isdigit():
                    return True
                else:
                    return False
            except Exception as e:
                worker.info_signal.emit(("提示", f"执行指令失败: {e}"))
                try:
                    start_ssh.disconnect()
                except:
                    pass
                return False

        def on_finished(result):
            if result:
                AutoCloseMessageBox("提示", "弱网已经开始，关闭软件不会停止弱网", 2000, self, 'start_weak_net').exec_()
                self._log("弱网脚本已启动")
                # 保存配置
                cfg['规则列表'] = self._get_table_rules()
                cfg['循环次数'] = self.loop_lineEdit.text()
                cfg['网卡'] = self.nic_comboBox.currentText()
                self.saved_nic = cfg['网卡']  # 更新内存中的保存网卡
                self.parent.save_config()
                # 更新原始配置基准，避免关闭时重复提示
                self._original_rules = self._get_table_rules()
                self._original_loop = self.loop_lineEdit.text()
                self._original_nic = self.saved_nic
                # 重置日志位置，下次读取会读取完整新日志
                self.last_log_size = 0
                self.log_textBrowser.clear()
            else:
                # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                self._operation_running = False
                self.set_all_buttons_enable()
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
        """停止弱网 - 和资源监控完全一样的逻辑"""
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)

        script_status = self.script_stutas_label.text()
        if script_status == '未知':
            AutoCloseMessageBox("提示", "请等待获取脚本状态", 2000, self).exec_()
            return
        if script_status == '已停止':
            AutoCloseMessageBox("提示", "没有运行中的弱网脚本", 2000, self).exec_()
            return

        cfg = self.parent.sc_buttons[self.button_id]['config']
        nic = self.nic_comboBox.currentText()

        # 新建 SSH 连接
        stop_ssh = ssh_tools.SSHTools()
        stop_ssh.ip = cfg['IP']
        stop_ssh.port = cfg['端口']
        stop_ssh.username = cfg['用户名']
        stop_ssh.password = cfg['密码']

        def do_stop():
            try:
                if not stop_ssh.connect():
                    worker.info_signal.emit(("提示", "连接服务器失败"))
                    return False

                # 查找并 kill 所有进程
                find_pid_cmd = "ps | grep OneClickWeakNet | grep -v grep | awk '{print $1}'"
                stdin, stdout, stderr = stop_ssh.ssh.exec_command(find_pid_cmd)
                pids = stdout.read().decode().strip().split()
                for pid in pids:
                    if pid.isdigit():
                        stop_ssh.ssh.exec_command(f"kill -9 {pid}")

                # 清除 tc 规则
                if nic:
                    stop_ssh.ssh.exec_command(f"tc qdisc del dev {nic} root 2>/dev/null || true")

                # 手动写停止日志
                stop_ssh.ssh.exec_command(
                    f'echo "[$(date "+%Y-%m-%d %H:%M:%S")] 弱网脚本已终止，tc规则已清除" >> {self.remote_log_path}'
                )

                stop_ssh.disconnect()
                return True
            except Exception as e:
                worker.info_signal.emit(("提示", f"停止失败: {e}"))
                try:
                    stop_ssh.disconnect()
                except:
                    pass
                return False

        def on_finished(result):
            if result:
                AutoCloseMessageBox("提示", "弱网已停止", 2000, self, 'stop_weak_net').exec_()
                self._log("弱网已停止")
            else:
                # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                self._operation_running = False
                self.set_all_buttons_enable()
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

    def clear_server_logs(self):
        """清除服务器日志 - 和资源监控一样：新建 SSH 连接，用完即断"""
        self._operation_running = True  # 开始操作，禁止状态检查线程更新按钮
        self.set_all_buttons_enable(False)

        script_status = self.script_stutas_label.text()
        if script_status == '运行中':
            AutoCloseMessageBox("提示", "弱网脚本正在运行，请先停止后再删除记录", 2000, self).exec_()
            return
        if script_status == '未知':
            AutoCloseMessageBox("提示", "脚本状态未知，请等待状态获取完成后再操作", 2000, self).exec_()
            return

        cfg = self.parent.sc_buttons[self.button_id]['config']

        clear_ssh = ssh_tools.SSHTools()
        clear_ssh.ip = cfg['IP']
        clear_ssh.port = cfg['端口']
        clear_ssh.username = cfg['用户名']
        clear_ssh.password = cfg['密码']

        work_dir = cfg['文件暂存路径']
        user_path = f"{work_dir}/OneClick/WeakNet"
        clean_cmd = f"rm -rf {user_path}"

        def do_clear():
            try:
                if not clear_ssh.connect():
                    worker.info_signal.emit(("提示", "连接服务器失败"))
                    return False
                # 删除远程日志目录
                stdin, stdout, stderr = clear_ssh.ssh.exec_command(clean_cmd)
                err = stderr.read().decode().strip()
                clear_ssh.disconnect()
                if err:
                    return False
                return True
            except Exception as e:
                worker.info_signal.emit(("提示", f"删除失败: {e}"))
                try:
                    clear_ssh.disconnect()
                except:
                    pass
                return False

        def on_finished(result):
            if result:
                self.log_textBrowser.clear()
                self.last_log_size = 0
                AutoCloseMessageBox("提示", "服务器日志已清除", 2000, self).exec_()
                self._log("服务器日志已清除")
            else:
                # 失败情况（普通提示框已由 worker.info_signal 弹出），手动启用按钮
                self._operation_running = False
                self.set_all_buttons_enable()
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
        worker.info_signal.connect(self.message_info_box)
        worker.log_signal.connect(self._log)
        worker.finished.connect(on_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def _log(self, msg):
        """带按钮名称前缀的日志输出"""
        if msg.startswith(f'<{self.button_name}>'):
            self.parent.update_run_info(msg)
        else:
            self.parent.update_run_info(f'<{self.button_name}> {msg}')

    def message_info_box(self, data):
        QMessageBox.information(self, data[0], data[1], QMessageBox.StandardButton.Ok)

    def is_config_changed(self):
        """检查配置是否被修改"""
        # 检查规则是否变化
        current_rules = self._get_table_rules()
        rules_changed = (current_rules != self._original_rules)
        # 检查循环次数是否变化
        loop_changed = (self.loop_lineEdit.text() != self._original_loop)
        # 检查网卡是否变化
        nic_changed = (self.nic_comboBox.currentText() != self._original_nic)
        return rules_changed or loop_changed or nic_changed

    def save_current_config(self):
        """保存当前配置（不提示）"""
        cfg = self.parent.sc_buttons[self.button_id]['config']
        cfg['规则列表'] = self._get_table_rules()
        cfg['循环次数'] = self.loop_lineEdit.text()
        cfg['网卡'] = self.nic_comboBox.currentText()
        self.saved_nic = cfg['网卡']
        self.parent.save_config()

    def on_close_event(self, event):
        if not self._can_close:
            event.ignore()  # 忽略关闭事件
            self.message_info_box(("提示", "操作中，请稍后"))
            return

        # 检查配置是否修改
        if self.is_config_changed():
            reply = QMessageBox.question(
                self, "提示",
                "配置已修改，是否保存修改并退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_current_config()
                self._log("配置已保存")
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            # No 的话直接继续退出

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
                                  'start_weak_net'=开始弱网完成
                                  'stop_weak_net'=停止弱网完成
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
            
            # 根据操作类型直接设置按钮状态
            if self._after_close_action == 'start_weak_net':
                # 开始弱网完成
                self._parent_dialog.start_pushButton.setEnabled(True)
                self._parent_dialog.stop_pushButton.setEnabled(True)
                self._parent_dialog.save_cfg_pushButton.setEnabled(True)
                self._parent_dialog.add_rule_pushButton.setEnabled(True)
                self._parent_dialog.del_rule_pushButton.setEnabled(True)
                self._parent_dialog.move_up_pushButton.setEnabled(True)
                self._parent_dialog.move_down_pushButton.setEnabled(True)
                # 运行中禁用清除日志按钮
                self._parent_dialog.clear_local_log_pushButton.setEnabled(False)
                self._parent_dialog._can_close = True  # 关键：允许关闭窗口
            elif self._after_close_action == 'stop_weak_net':
                # 停止弱网完成
                self._parent_dialog.start_pushButton.setEnabled(True)
                self._parent_dialog.stop_pushButton.setEnabled(False)
                self._parent_dialog.save_cfg_pushButton.setEnabled(True)
                self._parent_dialog.add_rule_pushButton.setEnabled(True)
                self._parent_dialog.del_rule_pushButton.setEnabled(True)
                self._parent_dialog.move_up_pushButton.setEnabled(True)
                self._parent_dialog.move_down_pushButton.setEnabled(True)
                # 停止后可以清除日志
                self._parent_dialog.clear_local_log_pushButton.setEnabled(True)
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
