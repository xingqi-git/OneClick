# -*- coding: utf-8 -*-
"""
监控脚本内容
把长脚本字符串从MainWindowLogic.py中分离出来
"""

# Linux Shell 监控脚本
MONITOR_SH = r'''#!/bin/bash

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
# 返回格式：PID:真实进程名，多个结果用空格分隔
get_proc_current_pids() {
    local proc_name="$1"
    local current_pids=()
    local pids=""
    
    # 方案1：先用pgrep匹配进程名（不含-f，只匹配comm字段，更精确）
    pids=$(pgrep "$proc_name" 2>/dev/null)
    
    # 方案2：如果方案1无结果，再用-f匹配完整命令行（但排除监控脚本自身）
    if [[ -z "$pids" ]]; then
        pids=$(pgrep -f "$proc_name" 2>/dev/null)
    fi
    
    for pid in $pids; do
        if [[ -d "/proc/$pid" ]]; then
            # 从/proc/$pid/comm获取真实进程名
            local real_proc_name=$(cat "/proc/$pid/comm" 2>/dev/null | tr -d '\n')
            if [[ -z "$real_proc_name" ]]; then
                real_proc_name=$(cat "/proc/$pid/status" 2>/dev/null | awk '/^Name:/ {print $2}')
            fi
            # 如果仍无法获取，使用用户输入的进程名作为后备
            [[ -z "$real_proc_name" ]] && real_proc_name="$proc_name"
            
            # 排除监控脚本自身的进程（避免自监控）
            if [[ "$real_proc_name" != *"OneClickMonitor"* ]]; then
                current_pids+=("${pid}:${real_proc_name}")
            fi
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
                for pid_entry in "${current_pids[@]}"; do
                    # 拆分PID和真实进程名
                    local pid="${pid_entry%%:*}"
                    local real_proc_name="${pid_entry#*:}"
                    # 只取进程名中/后面的部分，避免路径异常（如kworker/u:3取u:3）
                    local safe_proc_name="${real_proc_name##*/}"
                    
                    local proc_log_file="$OUTPUT_DIR/${safe_proc_name}_${pid}.log"

                    # 日志文件不存在则创建并写入表头
                    if [[ ! -f "$proc_log_file" ]]; then
                        local pid_header=$(generate_single_pid_header "$real_proc_name" "$pid")
                        echo "$pid_header" > "$proc_log_file"
                        echo "[$sys_time] 进程 $real_proc_name (PID:$pid) 日志已创建：$proc_log_file" | tee -a "$RUN_LOG"
                    fi

                    # 采集并写入该PID的指标
                    local pid_metrics=$(collect_single_pid_metrics "$real_proc_name" "$pid" "$sys_time")
                    # 仅当指标非空时写入（PID有效才会有数据）
                    if [[ -n "$pid_metrics" ]]; then
                        echo "$pid_metrics" >> "$proc_log_file"
                        echo "[$sys_time] 已写入进程 $real_proc_name (PID:$pid) 数据到 $proc_log_file" | tee -a "$RUN_LOG"
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
'''


# Windows PowerShell 监控脚本
MONITOR_PS1 = '''<#
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
    [Alias("d")]
    [int]$duration = 0,               # 最大运行时长（秒，0=无限）
    [Alias("h")]
    [switch]$help
)

# 帮助信息
if ($help) {
    Write-Host "用法：.\OneClickMonitor.ps1 [选项]"
    Write-Host "  -f <秒数>    输出间隔（默认5秒，-f 1则1秒输出一次）"
    Write-Host "  -o <路径>    输出目录（默认脚本所在目录）"
    Write-Host "  -p <进程名>  监控进程（多个空格分隔）"
    Write-Host "  -d <秒数>    最大运行时长（秒，0=无限）"
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

# 获取进程有效PID（仅存活进程，模糊匹配：进程名包含指定字符串即可）
function Get-LivePids {
    param([string]$ProcName)
    $pids = @()
    Get-Process -ErrorAction SilentlyContinue | Where-Object {!$_.HasExited -and $_.ProcessName -like "*$ProcName*"} | ForEach-Object {
        $pids += $_.Id
    }
    return $pids
}

# 采集系统指标（优化：减少不必要的计算）
function Collect-SysMetrics {
    $sysTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # 1. 内存（MB）- 缓存OS对象减少调用
    $script:osCache = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue

    $totalMemMB = [math]::Round($script:osCache.TotalVisibleMemorySize / 1024, 2)
    $freeMemMB = [math]::Round($script:osCache.FreePhysicalMemory / 1024, 2)
    $usedMemMB = [math]::Round($totalMemMB - $freeMemMB, 2)

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

        # 获取真实进程名
        $realProcName = $process.ProcessName
        # 只取进程名中/后面的部分，避免路径异常（如kworker/u:3取u:3）
        $safeProcName = if ($realProcName -contains '/') { $realProcName -split '/' | Select-Object -Last 1 } else { $realProcName }

        # 内存（MB）+ 句柄数（实时获取）
        # 替换内存计算行的所有内容，直接用这一段
        $wmiProc = Get-WmiObject -Class Win32_PerfFormattedData_PerfProc_Process -Filter "IDProcess='$ProcID'" -ErrorAction SilentlyContinue

        if (-not $wmiProc -or $null -eq $wmiProc.WorkingSetPrivate) {
            Write-Host "警告: 进程 $ProcID (${realProcName}) 内存数据获取失败，跳过本次采集"
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

        # WorkingSetPrivate 是任务管理器"专用(KB)"的官方属性（单位：KB）
        $memMB = [math]::Round($wmiProc.WorkingSetPrivate / 1024 / 1024, 2)
        #$memMB = [math]::Round($process.WorkingSet64 / 1024 / 1024, 2)

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
            $procCpu = [math]::Round(($cpuDiffSec / $intervalSec) / $LOGICAL_CORES * 100, 1)
            $procCpu = [math]::Max(0, [math]::Min(100, $procCpu))
        }

        # 更新缓存
        $script:procCpuTimeCache[$ProcID] = @{
            CpuTime = $cpuTimeNow
            Timestamp = $CurrentTimestamp
        }

        # 组装进程数据（使用安全进程名命名日志，避免/导致路径问题）
        $processDataList += @{
            PID         = $ProcID
            RealProcName = $realProcName
            Data        = "$SysTime,$memMB,$procCpu,$handle"
            Log         = Join-Path $OUTPUT_DIR "${safeProcName}_${ProcID}.log"
        }
    }

    return $processDataList
}

# 主监控逻辑（优化：精准控制循环间隔）
function Main-Monitor {
    # 运行日志文件路径
    $RUN_LOG = Join-Path $OUTPUT_DIR "OneClickMonitor.log"

    # 自定义Write-Log函数，同时输出到终端和日志文件
    function Write-Log {
        param([string]$Message)
        $logMsg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
        Write-Host $logMsg
        $logMsg | Out-File -FilePath $RUN_LOG -Encoding utf8 -Append
    }

    # 初始化系统日志表头
    if (-not (Test-Path $SYS_LOG_FILE)) {
        Generate-SysHeader | Out-File -FilePath $SYS_LOG_FILE -Encoding utf8
    }

    # 记录开始时间
    $startTime = Get-Date
    # 写入启动标记（和弱网统一格式）
    Write-Log "======== 资源监控脚本启动 ========"
    Write-Log "采样频率：${freq}秒"
    if ($duration -gt 0) {
        Write-Log "最大运行时长：${duration}秒"
    } else {
        Write-Log "最大运行时长：无限"
    }
    Write-Log "系统数据日志：$SYS_LOG_FILE"
    Write-Log "运行日志：$RUN_LOG"
    Write-Log "按 Ctrl+C 停止监控"
    while ($true) {
        $loopStart = Get-Date  # 记录本轮循环开始时间
        $currentTimestamp = $loopStart.ToFileTime()

        # 1. 采集系统数据并写入
        $sysResult = Collect-SysMetrics
        $sysResult.Data | Out-File -FilePath $SYS_LOG_FILE -Encoding utf8 -Append
        Write-Log "系统数据已写入：$SYS_LOG_FILE"

        # 2. 采集进程数据 proc="doubao,pycharm64"
        if ($proc -and $proc.Count -gt 0) {
            # 拆分,分隔的字符串为数组
            $pList = $proc -split ',' | Where-Object { ![string]::IsNullOrWhiteSpace($_) }
            # 遍历拆分后的每个进程名
            foreach ($singleP in $pList) {
                $singleP = $singleP.Trim() # 去除首尾空格
                $pids = Get-LivePids -ProcName $singleP
                if ($pids.Count -eq 0) {
                    Write-Log "进程$singleP无有效PID，跳过"
                    continue
                }
                # 采集进程数据
                $procDataList = Collect-ProcessMetrics -ProcName $singleP -ProcessIDs $pids -SysTime $sysResult.Time -CurrentTimestamp $currentTimestamp

                # 批量写入进程日志（使用真实进程名）
                foreach ($procData in $procDataList) {
                    $procLog = $procData.Log
                    $realProcName = $procData.RealProcName
                    # 初始化进程日志表头（首次写入时）
                    if (-not (Test-Path $procLog)) {
                        Generate-ProcessHeader -ProcName $realProcName -ProcessPID $procData.PID | Out-File -FilePath $procLog -Encoding utf8
                    }
                    $procData.Data | Out-File -FilePath $procLog -Encoding utf8 -Append
                    Write-Log "进程$realProcName(PID:$($procData.PID))数据已写入：$procLog"
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
                        $totalMemMB += [double ]$dataParts[1]    # 累加内存
                        $totalCpu += [double]$dataParts[2]      # 累加CPU
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
                $summaryData = "$($sysResult.Time),$($totalMemMB.ToString('0.00')),$($totalCpu.ToString('0.0')),$totalHandle"
                # 写入汇总日志
                $summaryData | Out-File -FilePath $summaryLog -Encoding utf8 -Append
                # 输出汇总日志提示
                Write-Log "进程$p汇总数据已写入：$summaryLog"
            }
        }

        # 3. 检查是否超过最大运行时长
        if ($duration -gt 0) {
            $elapsed = (Get-Date) - $startTime
            $elapsedSec = [math]::Floor($elapsed.TotalSeconds)
            $remainingSec = $duration - $elapsedSec
            Write-Log "已运行 ${elapsedSec} 秒，剩余 ${remainingSec} 秒"
            if ($elapsed.TotalSeconds -ge $duration) {
                Write-Log "达到最大运行时长 ${duration} 秒，监控停止"
                break
            }
        }

        # 4. 精准计算等待时间（确保总间隔严格等于freq）
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
'''



# Linux Shell 监控脚本-原生linux监控脚本，不依赖任何外部工具
MONITOR_SH_2 = r'''#!/bin/sh
# ---------------------- 脚本使用方式 ----------------------
# ./OneClickMonitor.sh                                              # 默认运行（5 秒采样，无指定进程，保存到当前路径下，仅包含系统日志system.log）
# ./OneClickMonitor.sh -f 10 -o /home                               # 10秒采样，日志保存到/home路径下
# ./OneClickMonitor.sh -p nginx java -o /home                  # 监控nginx和java，3秒采样，日志保存到/home路径下
# ./OneClickMonitor.sh -h                                           # 查看帮助
# nohup ./OneClickMonitor.sh &                                      # 后台执行

# 嵌入式ash：仅开启未定义变量检查，ash不支持set -u严格容错，注释规避报错
# set -u

# ---------------------- 配置参数 ----------------------
SAMPLE_FREQ=5
OUTPUT_DIR="./"
SYS_LOG_NAME="system.log"
SYS_LOG_FILE=""
# ash不支持数组，改用空格分隔字符串存储进程列表
TARGET_PROCS=""
MAX_DURATION=0                         # 最大运行时长（秒），0=无限

# ---------------------- 帮助文档 ----------------------
usage() {
    echo "用法：$0 [选项]"
    echo "选项："
    echo "  -f, --freq <秒数>        采样频率，默认5秒"
    echo "  -o, --output <文件夹>    输出目录，默认当前目录"
    echo "  -p, --proc <进程名>      多进程空格分隔，如 -p nginx java"
    echo "  -d, --duration <秒数>    最大运行时长（秒），0=无限运行，默认0"
    echo "  -h, --help               显示帮助"
    exit 1
}

# ---------------------- 参数解析（ash兼容，移除[[ ]]，改用[ ]） ----------------------
while [ $# -gt 0 ]; do
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
            # 拼接进程字符串替代数组
            while [ $# -gt 0 ] && ! echo "$1" | grep '^-' >/dev/null; do
                TARGET_PROCS="$TARGET_PROCS $1"
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

# 创建输出目录
mkdir -p "$OUTPUT_DIR"
echo "日志输出目录：$OUTPUT_DIR"
SYS_LOG_FILE="$OUTPUT_DIR/$SYS_LOG_NAME"

# ---------------------- 表头 ----------------------
generate_sys_header() {
    echo "系统时间,内存使用MB,整机CPU%,磁盘读KB/s,磁盘写KB/s,全局FD,全局Socket,运行进程总数"
}
generate_single_pid_header() {
    echo "系统时间,进程RSS(MB),堆内存VmData(MB),进程CPU(%),进程FD数,进程Socket数"
}

# ---------------------- 获取PID（模糊匹配）----------------------
# 返回格式：PID:真实进程名，多个结果用空格分隔
get_proc_current_pids() {
    local proc_name="$1"
    local pids=""
    
    # 方案1：先用pgrep匹配进程名（不含-f，只匹配comm字段，更精确）
    pids=$(pgrep "$proc_name" 2>/dev/null)
    
    # 方案2：如果方案1无结果，再用-f匹配完整命令行
    if [ -z "$pids" ]; then
        pids=$(pgrep -f "$proc_name" 2>/dev/null)
    fi
    
    if [ -n "$pids" ]; then
        for pid in $pids; do
            if [ -d "/proc/$pid" ]; then
                # 从/proc/$pid/comm获取真实进程名
                local real_proc_name
                read -r real_proc_name < "/proc/$pid/comm" 2>/dev/null
                # 尝试从status获取作为后备
                if [ -z "$real_proc_name" ] && [ -f "/proc/$pid/status" ]; then
                    real_proc_name=$(grep '^Name:' "/proc/$pid/status" 2>/dev/null | awk '{print $2}')
                fi
                # 如果仍无法获取，使用用户输入的进程名作为后备
                [ -z "$real_proc_name" ] && real_proc_name="$proc_name"
                
                # 排除监控脚本自身的进程（避免自监控）
                case "$real_proc_name" in
                    *OneClickMonitor*) ;;
                    *) echo "${pid}:${real_proc_name}" ;;
                esac
            fi
        done
        return
    fi
    
    # pgrep失效时降级遍历/proc（模糊匹配：进程名包含指定字符串即可）
    for pid in /proc/[0-9]*; do
        local p="${pid#/proc/}"
        local comm="/proc/$p/comm"
        [ -f "$comm" ] || continue
        local real_name
        read -r real_name < "$comm" 2>/dev/null
        # 嵌入式grep可能不支持-q，用>/dev/null替代
        if echo "$real_name" | grep "$proc_name" >/dev/null 2>&1; then
            # 排除监控脚本自身的进程
            case "$real_name" in
                *OneClickMonitor*) ;;
                *) echo "${p}:${real_name}" ;;
            esac
        fi
    done
}

# ---------------------- 单进程指标采集 ----------------------
collect_single_pid_metrics() {
    local proc_name="$1"
    local pid="$2"
    local sys_time="$3"
    [ ! -d "/proc/$pid" ] && return

    # 内存 - 改用grep + cut，兼容性更好
    local mem_kb=0
    local data_kb=0
    if [ -f "/proc/$pid/status" ]; then
        mem_line=$(grep "VmRSS" "/proc/$pid/status" 2>/dev/null)
        if [ -n "$mem_line" ]; then
            mem_kb=$(echo "$mem_line" | awk '{print $2}')
        fi
        data_line=$(grep "VmData" "/proc/$pid/status" 2>/dev/null)
        if [ -n "$data_line" ]; then
            data_kb=$(echo "$data_line" | awk '{print $2}')
        fi
    fi
    local mem_mb=$(echo "$mem_kb" | awk '{printf "%.2f", $1/1024}')
    local data_mb=$(echo "$data_kb" | awk '{printf "%.2f", $1/1024}')

    # CPU - 简化，嵌入式只用awk内完成所有计算，减少子shell问题
    local cpu_pct="0.00"

    local fd_num=0
    # 不用管道问题，直接计数
    if [ -d "/proc/$pid/fd" ]; then
        for f in "/proc/$pid/fd/"*; do
            [ -e "$f" ] && fd_num=$((fd_num + 1))
        done
    fi
    local sock_num=0
    # 不用grep -c，用循环+case匹配
    if [ -d "/proc/$pid/fd" ]; then
        for f in "/proc/$pid/fd/"*; do
            link=$(readlink "$f" 2>/dev/null)
            case "$link" in
                *socket:*) sock_num=$((sock_num + 1)) ;;
            esac
        done
    fi

    # 用printf严格控制输出，避免任何额外字符
    printf "%s,%.2f,%.2f,%s,%d,%d\n" "$sys_time" "$mem_mb" "$data_mb" "$cpu_pct" "$fd_num" "$sock_num"
}

# ---------------------- 系统指标采集 ----------------------
collect_sys_metrics() {
    local now=$(date "+%Y-%m-%d %H:%M:%S")

    # 内存 - 简化获取方式
    local mem_used=0
    if command -v free >/dev/null 2>&1; then
        mem_used=$(free -m 2>/dev/null | grep Mem | awk '{print $3}')
    fi
    [ -z "$mem_used" ] && mem_used=0

    # CPU - 简化，减少子shell嵌套
    local cpu_used="0.0"

    # 磁盘IO - 不用变量传递，直接在awk内处理
    local rd=0 wr=0
    if [ -f "/proc/diskstats" ]; then
        rd=$(awk '{r+=$6}END{print r}' /proc/diskstats 2>/dev/null)
        wr=$(awk '{w+=$10}END{print w}' /proc/diskstats 2>/dev/null)
    fi
    [ -z "$rd" ] && rd=0
    [ -z "$wr" ] && wr=0

    # 全局FD - 直接赋值
    local total_fd=0
    if [ -f "/proc/sys/fs/file-nr" ]; then
        total_fd=$(cat /proc/sys/fs/file-nr 2>/dev/null | awk '{print $1}')
    fi
    [ -z "$total_fd" ] && total_fd=0

    # Socket总数 - 简化
    local total_sock=0
    if [ -f "/proc/net/sockstat" ]; then
        total_sock=$(cat /proc/net/sockstat 2>/dev/null | grep sock | awk '{for(i=1;i<=NF;i++) if($i~/^[0-9]+$/) {print $i;exit}}')
    fi
    [ -z "$total_sock" ] && total_sock=0

    # 进程数 - 直接循环计数
    local proc_cnt=0
    for p in /proc/[0-9]*; do
        [ -d "$p" ] && proc_cnt=$((proc_cnt + 1))
    done

    # 用printf严格控制输出，确保8个字段，格式统一
    printf "%s,%d,%s,%d,%d,%d,%d,%d\n" "$now" "$mem_used" "$cpu_used" "$rd" "$wr" "$total_fd" "$total_sock" "$proc_cnt"
}

# 初始化系统日志表头
update_log_header() {
    [ ! -f "$SYS_LOG_FILE" ] && generate_sys_header > "$SYS_LOG_FILE"
}

# ---------------------- 主循环 ----------------------
main_monitor() {
    # 运行日志文件路径
    local RUN_LOG="$OUTPUT_DIR/OneClickMonitor.log"
    local now=$(date '+%Y-%m-%d %H:%M:%S')

    # 写入启动标记（和弱网统一格式）
    echo "[$now] ======== 资源监控脚本启动 ========" | tee -a "$RUN_LOG"
    echo "[$now] 采样频率：${SAMPLE_FREQ}秒" | tee -a "$RUN_LOG"
    echo "[$now] 系统数据日志：$SYS_LOG_FILE" | tee -a "$RUN_LOG"
    echo "[$now] 运行日志：$RUN_LOG" | tee -a "$RUN_LOG"
    if [ -n "$TARGET_PROCS" ]; then
        echo "[$now] 监控进程：$TARGET_PROCS" | tee -a "$RUN_LOG"
    fi
    if [ "$MAX_DURATION" -gt 0 ]; then
        echo "[$now] 最大运行时长：${MAX_DURATION}秒" | tee -a "$RUN_LOG"
    else
        echo "[$now] 最大运行时长：无限" | tee -a "$RUN_LOG"
    fi
    echo "[$now] 按 Ctrl+C 停止监控" | tee -a "$RUN_LOG"

    # 记录开始时间
    local start_time=$(date +%s)

    while true; do
        update_log_header
        # 采集系统指标，失败不中断循环
        local sys_line
        sys_line=$(collect_sys_metrics 2>/dev/null)
        if [ -n "$sys_line" ]; then
            echo "$sys_line" >> "$SYS_LOG_FILE"
            local cur_time=$(echo "$sys_line" | cut -d',' -f1)
            echo "[$cur_time] 写入系统指标" | tee -a "$RUN_LOG"

            # ash无数组，直接遍历空格分隔的进程字符串
            for proc in $TARGET_PROCS; do
                echo "[$cur_time] 开始查找进程：$proc" | tee -a "$RUN_LOG"
                pid_entries=$(get_proc_current_pids "$proc")
                echo "[$cur_time] 查找结果：$pid_entries" | tee -a "$RUN_LOG"
                if [ -z "$pid_entries" ]; then
                    echo "[$cur_time] $proc 无运行PID，跳过" | tee -a "$RUN_LOG"
                    continue
                fi
                for pid_entry in $pid_entries; do
                    # 拆分PID和真实进程名（ash不支持%%和#参数扩展，使用cut）
                    pid=$(echo "$pid_entry" | cut -d':' -f1)
                    real_proc_name=$(echo "$pid_entry" | cut -d':' -f2-)
                    # 只取进程名中/后面的部分，避免路径异常（如kworker/u:3取u:3）
                    # ash不支持##参数扩展，用awk处理
                    safe_proc_name=$(echo "$real_proc_name" | awk -F/ '{print $NF}')
                    
                    log_path="${OUTPUT_DIR}/${safe_proc_name}_${pid}.log"
                    if [ ! -f "$log_path" ]; then
                        generate_single_pid_header > "$log_path"
                        echo "[$cur_time] 进程 $real_proc_name (PID:$pid) 日志已创建：$log_path" | tee -a "$RUN_LOG"
                    fi
                    data=$(collect_single_pid_metrics "$real_proc_name" "$pid" "$cur_time" 2>/dev/null)
                    if [ -n "$data" ]; then
                        echo "$data" >> "$log_path"
                        echo "[$cur_time] 已写入进程 $real_proc_name (PID:$pid) 数据" | tee -a "$RUN_LOG"
                    else
                        echo "[$cur_time] 进程 $real_proc_name (PID:$pid) 数据采集失败，跳过" | tee -a "$RUN_LOG"
                    fi
                done
            done
        fi

        # 检查是否超过最大运行时长
        if [ "$MAX_DURATION" -gt 0 ]; then
            local current_time=$(date +%s)
            local elapsed=$((current_time - start_time))
            local remaining=$((MAX_DURATION - elapsed))
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已运行 ${elapsed} 秒，剩余 ${remaining} 秒" | tee -a "$RUN_LOG"
            if [ $elapsed -ge $MAX_DURATION ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] 达到最大运行时长 ${MAX_DURATION} 秒，监控停止" | tee -a "$RUN_LOG"
                break
            fi
        fi

        sleep "${SAMPLE_FREQ}"
    done
}

# 优雅退出捕获
trap 'echo -e "\n\n监控程序正常退出，日志存放目录：$OUTPUT_DIR"; exit 0' SIGINT SIGTERM
main_monitor
'''
