#!/bin/bash

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
