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
        proc_cpu=$(awk -v p="$proc_cpu_diff" -v s="$sys_cpu_diff" \ 'BEGIN{printf "%.1f", (p/s)*100}')
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
'''
