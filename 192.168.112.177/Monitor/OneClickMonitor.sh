#!/bin/bash

# ---------------------- 脚本使用方式 ----------------------
# ./OneClickMonitor.sh                                              # 默认运行（5 秒采样，无指定进程，保存到当前路径下，仅包含系统日志system.log）
# ./OneClickMonitor.sh -f 10 -o /home                               # 10秒采样，日志保存到/home路径下
# ./OneClickMonitor.sh -f 3 -p nginx java -o /home                  # 监控nginx和java，3秒采样，日志保存到/home路径下，包括系统日志system.log，进程日志nginx_234.log/java_867.log
# ./OneClickMonitor.sh -h                                           # 查看帮助
# nohup ./OneClickMonitor.sh &                                      # 后台执行

set -euo pipefail

# ---------------------- 配置参数（可通过命令行覆盖，优先级更高） ----------------------
SAMPLE_FREQ=5                          # 默认采样频率：5秒
OUTPUT_DIR="./"                        # 默认输出文件夹：当前目录
SYS_LOG_NAME="system.log"              # 系统日志文件名
SYS_LOG_FILE=""                        # 系统日志完整路径（后续拼接文件夹+文件名）
TARGET_PROCS=()                        # 默认不监控指定进程，为空数组（明确初始化）
MAX_DURATION=0                         # 最大运行时长（秒），0=无限

# ---------------------- 命令行参数解析 ----------------------
usage() {
    echo "用法：$0 [选项]"
    echo "选项："
    echo "  -f, --freq <秒数>        采样频率，默认5秒"
    echo "  -o, --output <文件夹路径>   输出文件夹路径，默认当前目录（./）"
    echo "  -p, --proc <进程名>     指定监控的进程名（可多个，空格分隔），进程日志自动命名为<进程名>_<PID>.log"
    echo "  -d, --duration <秒数>    最大运行时长（秒），0=无限运行，默认0"
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
        -d|--duration)
            MAX_DURATION="$2"
            shift 2
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
    echo "系统时间,进程RSS(MB),堆内存VmData(MB),进程CPU(%),进程FD数,进程Socket数"
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

    # 进程内存（VmRSS和VmData，转换为MB保留2位小数）
    local proc_mem=$(cat /proc/$pid/status 2>/dev/null | awk '/VmRSS/ {print $2}')
    proc_mem=$(awk -v mem="$proc_mem" 'BEGIN{printf "%.2f", mem / 1024}')
    proc_mem=${proc_mem:-0.00}

    local proc_data=$(cat /proc/$pid/status 2>/dev/null | awk '/VmData/ {print $2}')
    proc_data=$(awk -v mem="$proc_data" 'BEGIN{printf "%.2f", mem / 1024}')
    proc_data=${proc_data:-0.00}

    # 进程CPU使用率（%，保留2位小数）
    local proc_stat1=$(cat /proc/$pid/stat 2>/dev/null | awk '{print $14 "," $15}')
    local sys_stat1=$(cat /proc/stat 2>/dev/null | awk '/^cpu / {printf "%d", $2+$3+$4+$5+$6+$7+$8}')
    sleep 0.1
    local proc_stat2=$(cat /proc/$pid/stat 2>/dev/null | awk '{print $14 "," $15}')
    local sys_stat2=$(cat /proc/stat 2>/dev/null | awk '/^cpu / {printf "%d", $2+$3+$4+$5+$6+$7+$8}')

    local utime1=$(echo "$proc_stat1" | cut -d',' -f1)
    utime1=${utime1:-0}
    local stime1=$(echo "$proc_stat1" | cut -d',' -f2)
    stime1=${stime1:-0}
    local utime2=$(echo "$proc_stat2" | cut -d',' -f1)
    utime2=${utime2:-0}
    local stime2=$(echo "$proc_stat2" | cut -d',' -f2)
    stime2=${stime2:-0}
    
    local proc_cpu=0.00
    proc_cpu=$(awk -v u1="$utime1" -v s1="$stime1" -v u2="$utime2" -v s2="$stime2" -v ss1="$sys_stat1" -v ss2="$sys_stat2" \
        'BEGIN{
            p_diff = (u2 + s2) - (u1 + s1);
            s_diff = ss2 - ss1;
            if (s_diff > 0) {
                printf "%.1f", (p_diff / s_diff) * 100;
            } else {
                print "0.00";
            }
        }')

    # 进程文件描述符数
    local proc_fds=$(ls /proc/$pid/fd 2>/dev/null | wc -l)
    proc_fds=${proc_fds:-0}

    # 进程Socket描述符数
    local proc_socks=$(ls -l /proc/$pid/fd 2>/dev/null | grep -c 'socket:\[')
    proc_socks=${proc_socks:-0}

    # 拼接指标行
    echo "$sys_time,$proc_mem,$proc_data,$proc_cpu,$proc_fds,$proc_socks"
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
    # 运行日志文件路径
    local RUN_LOG="$OUTPUT_DIR/OneClickMonitor.log"

    # 写入启动标记（和弱网统一格式）
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] ======== 资源监控脚本启动 ========" | tee -a "$RUN_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 采样频率：${SAMPLE_FREQ}秒" | tee -a "$RUN_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 系统数据日志：${SYS_LOG_FILE}" | tee -a "$RUN_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 运行日志：${RUN_LOG}" | tee -a "$RUN_LOG"
    if [[ ${#TARGET_PROCS[@]} -gt 0 ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 监控进程列表：${TARGET_PROCS[*]}" | tee -a "$RUN_LOG"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 进程日志规则：每个PID对应独立日志文件，路径为 $OUTPUT_DIR/<进程名>_<PID>.log" | tee -a "$RUN_LOG"
    fi
    if [[ $MAX_DURATION -gt 0 ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 最大运行时长：${MAX_DURATION}秒" | tee -a "$RUN_LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 最大运行时长：无限" | tee -a "$RUN_LOG"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 按 Ctrl+C 停止监控" | tee -a "$RUN_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 特性：无进程时不创建日志，PID消失则停止写入对应日志，新增PID自动创建日志" | tee -a "$RUN_LOG"

    # 记录开始时间
    local start_time=$(date +%s)

    while true; do
        # 初始化/检查系统日志表头
        update_log_header

        # 采集并写入系统数据（原有逻辑完全保留）
        local sys_data=$(collect_sys_metrics)
        echo "$sys_data" >> "$SYS_LOG_FILE"
        local sys_time=$(echo "$sys_data" | cut -d',' -f1)
        echo "[$sys_time] 已写入系统数据到 $SYS_LOG_FILE" | tee -a "$RUN_LOG"

        # 处理进程监控（重写后的逻辑）
        if [[ ${#TARGET_PROCS[@]} -gt 0 ]]; then
            for proc in "${TARGET_PROCS[@]}"; do
                # 获取当前进程的有效PID列表
                local current_pids=($(get_proc_current_pids "$proc"))

                # 无有效PID时跳过
                if [[ ${#current_pids[@]} -eq 0 ]]; then
                    echo "[$sys_time] 进程 $proc 无有效PID，跳过进程日志写入" | tee -a "$RUN_LOG"
                    continue
                fi

                # 遍历每个PID处理日志
                for pid in "${current_pids[@]}"; do
                    local proc_log_file="$OUTPUT_DIR/${proc}_${pid}.log"

                    # 日志文件不存在则创建并写入表头
                    if [[ ! -f "$proc_log_file" ]]; then
                        local pid_header=$(generate_single_pid_header "$proc" "$pid")
                        echo "$pid_header" > "$proc_log_file"
                        echo "[$sys_time] 进程 $proc (PID:$pid) 日志已创建：$proc_log_file" | tee -a "$RUN_LOG"
                    fi

                    # 采集并写入该PID的指标
                    local pid_metrics=$(collect_single_pid_metrics "$proc" "$pid" "$sys_time")
                    # 仅当指标非空时写入（PID有效才会有数据）
                    if [[ -n "$pid_metrics" ]]; then
                        echo "$pid_metrics" >> "$proc_log_file"
                        echo "[$sys_time] 已写入进程 $proc (PID:$pid) 数据到 $proc_log_file" | tee -a "$RUN_LOG"
                    fi
                done
            done
        fi

        # 检查是否超过最大运行时长
        if [[ $MAX_DURATION -gt 0 ]]; then
            local current_time=$(date +%s)
            local elapsed=$((current_time - start_time))
            local remaining=$((MAX_DURATION - elapsed))
            echo "[$sys_time] 已运行 ${elapsed} 秒，剩余 ${remaining} 秒" | tee -a "$RUN_LOG"
            if [[ $elapsed -ge $MAX_DURATION ]]; then
                echo "[$sys_time] 达到最大运行时长 ${MAX_DURATION} 秒，监控停止" | tee -a "$RUN_LOG"
                break
            fi
        fi

        # 等待采样间隔
        sleep "$SAMPLE_FREQ"
    done
}

# ---------------------- 启动脚本 ----------------------
trap 'echo -e "\n监控已停止"; exit 0' SIGINT
main_monitor
