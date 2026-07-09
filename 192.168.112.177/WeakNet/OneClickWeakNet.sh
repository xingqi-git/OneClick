#!/bin/bash
set -euo pipefail
NIC="docker0"
LOOP=99999999
LOGFILE="/home/root/OneClick/WeakNet/OneClickWeakNet.log"

log() {
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $*" >> "$LOGFILE"
}

# 清空旧日志
> "$LOGFILE"

cleanup() {
    tc qdisc del dev "$NIC" root 2>/dev/null || true
    log "弱网脚本已终止，tc规则已清除"
    exit 0
}
trap cleanup SIGINT SIGTERM

log "弱网脚本启动"
log "网卡: docker0"
log "循环次数: 99999999"
log "规则队列:"
log "  [规则1] 持续: 1s | 间隔: s"
log "  [规则2] 持续: 10s | 间隔: s"

for i in $(seq 1 $LOOP); do
    log "第 $i/$LOOP 次循环开始"
    tc qdisc del dev "$NIC" root 2>/dev/null || true
    log "  规则1无tc参数，仅清除规则"
    sleep 1
    log "  规则1弱网结束（持续1s），进入间隔s"
    tc qdisc del dev "$NIC" root 2>/dev/null || true
    log "  规则2无tc参数，仅清除规则"
    sleep 10
    log "  规则2弱网结束（持续10s），进入间隔s"
done

log "所有循环已完成，清除tc规则"
cleanup