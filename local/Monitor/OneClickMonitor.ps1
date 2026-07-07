<#
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
