"""
日志清理工具
- 按时间范围清理 .log 监控数据文件
- 策略：首尾行快速判断 -> 整文件删除 / 二分定位行号 -> 命令行裁剪
"""

import os
import datetime


TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# 排除的文件（不是监控数据文件）
EXCLUDE_FILES = {'OneClickMonitor.log'}


def parse_time(t_str):
    """解析时间字符串，失败返回 None"""
    try:
        return datetime.datetime.strptime(t_str.strip(), TIME_FORMAT)
    except (ValueError, AttributeError):
        return None


def get_log_time_range(filepath):
    """
    读取日志文件的首行数据和末行数据的时间（第1行是表头，从第2行开始）
    返回 (首行时间, 末行时间)，都可能为 None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # 读表头（第1行）和首条数据（第2行）
            first_data_time = None
            header = f.readline()  # 跳过表头
            second_line = f.readline()
            if second_line:
                first_col = second_line.split(',')[0].strip()
                first_data_time = parse_time(first_col)

            # 读最后一行数据（从文件末尾往前找）
            last_data_time = None
            try:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size <= 100:
                    # 文件很小，直接重开读
                    f.seek(0)
                    lines = f.readlines()
                    if len(lines) >= 2:
                        last_col = lines[-1].split(',')[0].strip()
                        last_data_time = parse_time(last_col)
                else:
                    # 从末尾向前读 2KB，找最后一个换行
                    read_size = min(2048, file_size)
                    f.seek(file_size - read_size)
                    tail = f.read(read_size)
                    lines = tail.splitlines()
                    # 找到最后一个非空行
                    for line in reversed(lines):
                        line = line.strip()
                        if line:
                            last_col = line.split(',')[0].strip()
                            last_data_time = parse_time(last_col)
                            if last_data_time:
                                break
            except Exception:
                pass

            return first_data_time, last_data_time
    except (FileNotFoundError, PermissionError, OSError):
        return None, None


def binary_search_delete_range(filepath, start_time, end_time):
    """
    二分法定位需要删除的行号范围（数据行号，从 2 开始，第 1 行是表头）
    返回 (delete_start_line, delete_end_line)
    - delete_start_line: 第一条落在 [start_time, end_time] 区间内的数据行号
    - delete_end_line: 最后一条落在区间内的数据行号 + 1（即第一个 > end_time 的行号）
    如果没有数据在区间内，返回 (None, None)
    """
    first_time, last_time = get_log_time_range(filepath)
    if first_time is None or last_time is None:
        return None, None

    # 完全不重叠
    if last_time < start_time or first_time > end_time:
        return None, None

    # 先建立行偏移表（所有数据行，即从第2行开始的所有行的起始字节位置）
    line_offsets = []  # line_offsets[i] 对应第 i+2 行（数据行）的起始字节偏移
    try:
        with open(filepath, 'rb') as f:
            # 跳过第 1 行（表头）
            f.readline()
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    break
                line_offsets.append(pos)
    except OSError:
        return None, None

    if not line_offsets:
        return None, None

    total = len(line_offsets)

    def get_time_at(idx):
        """读取第 idx 条数据行的时间（idx 从 0 开始）"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                f.seek(line_offsets[idx])
                line = f.readline()
                if line:
                    return parse_time(line.split(',')[0])
        except Exception:
            return None
        return None

    # 找第一个 >= start_time 的位置
    left = 0
    right = total
    while left < right:
        mid = (left + right) // 2
        t = get_time_at(mid)
        if t is None:
            # 解析失败，保守认为在区间内
            left = mid + 1
        elif t < start_time:
            left = mid + 1
        else:
            right = mid
    first_in_range = left  # 数据行索引

    # 找第一个 > end_time 的位置
    left = 0
    right = total
    while left < right:
        mid = (left + right) // 2
        t = get_time_at(mid)
        if t is None:
            left = mid + 1
        elif t <= end_time:
            left = mid + 1
        else:
            right = mid
    first_after_range = left  # 数据行索引

    if first_in_range >= first_after_range:
        # 没有落在区间内的数据
        return None, None

    # 转成行号（第 1 行是表头，数据行从第 2 行开始，索引0对应行号2）
    delete_start_line = first_in_range + 2
    delete_end_line = first_after_range + 2  # [start, end) 中的 end，即第一个不用删的行号

    return delete_start_line, delete_end_line


def trim_local_log_by_lines(filepath, keep_before_line, keep_from_line):
    """
    本地文件按行号裁剪：保留 [1, keep_before_line) 和 [keep_from_line, 末尾] 的行
    即删除 [keep_before_line, keep_from_line - 1] 区间的行
    行号从 1 开始，第 1 行是表头，永远保留

    使用纯 Python 逐行读写 + 临时文件原子替换，避免 PowerShell 的路径/编码问题
    """
    import shutil

    tmp_path = filepath + '.tmp'
    data_line_count = 0  # 统计数据行数（不含表头）

    try:
        with open(filepath, 'r', encoding='utf-8', newline='') as src, \
             open(tmp_path, 'w', encoding='utf-8', newline='') as dst:

            line_num = 0
            for line in src:
                line_num += 1
                # 第 1 行（表头）直接写
                if line_num == 1:
                    dst.write(line)
                    continue
                # 在删除区间内的行，跳过
                if keep_before_line <= line_num < keep_from_line:
                    continue
                # 其余行写入
                dst.write(line)
                data_line_count += 1

        # 裁剪后没有数据行（只有表头），删除整个文件
        if data_line_count <= 0:
            try:
                os.remove(tmp_path)
                os.remove(filepath)
            except OSError as e:
                return False, str(e)
            return True, ""

        # 原子替换
        try:
            shutil.move(tmp_path, filepath)
        except OSError as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return False, str(e)
        return True, ""

    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False, str(e)


def clean_local_logs(dir_path, start_time, end_time, progress_cb=None):
    """
    清理本地目录下指定时间范围内的监控数据（删除区间内的数据）
    :param dir_path: Monitor 目录路径
    :param start_time: datetime，区间开始（包含）
    :param end_time: datetime，区间结束（包含）
    :param progress_cb: 进度回调函数 callback(file_count, total_count)
    :return: (deleted_files, trimmed_files, errors)
    """
    deleted_files = 0
    trimmed_files = 0
    errors = []

    if not os.path.isdir(dir_path):
        return deleted_files, trimmed_files, errors

    # 收集所有 .log 文件
    log_files = []
    for name in os.listdir(dir_path):
        if not name.endswith('.log'):
            continue
        if name in EXCLUDE_FILES:
            continue
        full_path = os.path.join(dir_path, name)
        if os.path.isfile(full_path):
            log_files.append(full_path)

    total = len(log_files)
    for idx, filepath in enumerate(log_files):
        if progress_cb:
            try:
                progress_cb(idx + 1, total)
            except Exception:
                pass

        first_time, last_time = get_log_time_range(filepath)
        if first_time is None or last_time is None:
            continue

        # 完全在区间之前或之后，跳过
        if last_time < start_time or first_time > end_time:
            continue

        # 完全在区间内，直接删文件
        if first_time >= start_time and last_time <= end_time:
            try:
                os.remove(filepath)
                deleted_files += 1
            except OSError as e:
                errors.append(f"{os.path.basename(filepath)}: {e}")
            continue

        # 部分重叠，行级裁剪
        del_start, del_end = binary_search_delete_range(filepath, start_time, end_time)
        if del_start is None:
            continue

        # del_start 是第一条要删的行号，del_end 是第一条不用删的行号
        # 保留：[1, del_start) （即表头 + del_start之前的数据）
        # 保留：[del_end, 末尾] （即 del_end 及之后的数据）
        keep_before_line = del_start  # 保留到这行之前
        keep_from_line = del_end     # 从这行开始保留

        ok, err = trim_local_log_by_lines(filepath, keep_before_line, keep_from_line)
        if ok:
            trimmed_files += 1
        else:
            errors.append(f"{os.path.basename(filepath)}: {err if err else '裁剪失败'}")

    # 清理空目录（可选）
    try:
        remaining = [f for f in os.listdir(dir_path) if f not in EXCLUDE_FILES]
        if not remaining:
            os.rmdir(dir_path)
    except OSError:
        pass

    if progress_cb:
        try:
            progress_cb(total, total)
        except Exception:
            pass

    return deleted_files, trimmed_files, errors


def build_remote_linux_clean_cmd(remote_dir, start_str, end_str):
    """
    构造 Linux 远程清理的 shell 命令（bash 脚本，按时间字符串比较，不用解析日期）
    因为时间格式是 ISO 风格 (YYYY-MM-DD HH:MM:SS)，字符串比较与时间比较一致
    """
    script = f'''
dir="{remote_dir}"
start_ts="{start_str}"
end_ts="{end_str}"
deleted=0
trimmed=0

if [ ! -d "$dir" ]; then
    echo "DIR_NOT_FOUND"
    exit 0
fi

# 先统计总文件数（排除 OneClickMonitor.log）
total=0
for f in "$dir"/*.log; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    case "$base" in
        OneClickMonitor.log) ;;
        *) total=$((total + 1)) ;;
    esac
done
echo "TOTAL:$total"

index=0
for f in "$dir"/*.log; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    case "$base" in
        OneClickMonitor.log) continue ;;
    esac
    index=$((index + 1))
    echo "PROGRESS:$index/$total"

    # 取首行数据时间（第2行，跳过表头）
    first_time=$(sed -n '2p' "$f" | cut -d',' -f1)
    # 取末行时间
    last_time=$(tail -n1 "$f" | cut -d',' -f1)

    [ -z "$first_time" ] && continue
    [ -z "$last_time" ] && continue

    # 完全在区间之前或之后，跳过
    if [[ "$last_time" < "$start_ts" ]] || [[ "$first_time" > "$end_ts" ]]; then
        continue
    fi

    # 完全在区间内，删除整个文件
    if [[ "$first_time" > "$start_ts" || "$first_time" == "$start_ts" ]] && [[ "$last_time" < "$end_ts" || "$last_time" == "$end_ts" ]]; then
        rm -f "$f"
        deleted=$((deleted + 1))
        continue
    fi

    # 部分重叠，用 awk 按时间裁剪（保留表头 + 不在区间内的数据行）
    tmp="$f.tmp"
    awk -F',' -v s="$start_ts" -v e="$end_ts" '
        NR == 1 {{ print; next }}
        $1 < s || $1 > e {{ print }}
    ' "$f" > "$tmp"

    # 检查裁剪后是否还有数据行
    line_count=$(wc -l < "$tmp")
    if [ "$line_count" -le 1 ]; then
        rm -f "$tmp" "$f"
        deleted=$((deleted + 1))
    else
        mv -f "$tmp" "$f"
        trimmed=$((trimmed + 1))
    fi
done

echo "RESULT:deleted=$deleted:trimmed=$trimmed"
'''
    return script


def write_remote_linux_clean_script(remote_dir, start_str, end_str, local_path):
    """
    生成 Linux 远程清理脚本到本地文件，方便上传到服务器执行
    :param remote_dir: 服务器上的 Monitor 目录路径
    :param start_str: 起始时间字符串
    :param end_str: 结束时间字符串
    :param local_path: 本地保存路径
    """
    script = build_remote_linux_clean_cmd(remote_dir, start_str, end_str)
    with open(local_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(script)


def build_remote_linux_filter_cmd(remote_dir, out_dir, start_str, end_str):
    """
    构造 Linux 远程按时间范围筛选的 bash 脚本（保留区间内的数据，不动原文件）
    流程：
      1. 创建输出目录
      2. 遍历原目录每个 log 文件
      3. 首尾行快速判断：完全在区间内→复制；完全在区间外→跳过；部分重叠→awk裁剪后复制
      4. 输出进度信息
    因为时间格式是 ISO 风格 (YYYY-MM-DD HH:MM:SS)，字符串比较与时间比较一致
    """
    script = f'''
src_dir="{remote_dir}"
out_dir="{out_dir}"
start_ts="{start_str}"
end_ts="{end_str}"
copied=0
trimmed=0
skipped=0

if [ ! -d "$src_dir" ]; then
    echo "DIR_NOT_FOUND"
    exit 0
fi

mkdir -p "$out_dir"

# 先统计总文件数（排除 OneClickMonitor.log）
total=0
for f in "$src_dir"/*.log; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    case "$base" in
        OneClickMonitor.log) ;;
        *) total=$((total + 1)) ;;
    esac
done
echo "TOTAL:$total"

if [ "$total" -eq 0 ]; then
    echo "RESULT:copied=0:trimmed=0:skipped=0"
    exit 0
fi

index=0
for f in "$src_dir"/*.log; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    case "$base" in
        OneClickMonitor.log) continue ;;
    esac
    index=$((index + 1))
    echo "PROGRESS:$index/$total"

    # 取首行数据时间（第2行，跳过表头）
    first_time=$(sed -n '2p' "$f" | cut -d',' -f1)
    # 取末行时间
    last_time=$(tail -n1 "$f" | cut -d',' -f1)

    [ -z "$first_time" ] && continue
    [ -z "$last_time" ] && continue

    # 完全在区间之前或之后，跳过
    if [[ "$last_time" < "$start_ts" ]] || [[ "$first_time" > "$end_ts" ]]; then
        skipped=$((skipped + 1))
        continue
    fi

    # 完全在区间内，直接复制
    if [[ "$first_time" > "$start_ts" || "$first_time" == "$start_ts" ]] && [[ "$last_time" < "$end_ts" || "$last_time" == "$end_ts" ]]; then
        cp "$f" "$out_dir/"
        copied=$((copied + 1))
        continue
    fi

    # 部分重叠，用 awk 按时间裁剪（保留表头 + 区间内的数据行），输出到 out_dir
    out_f="$out_dir/$base"
    awk -F',' -v s="$start_ts" -v e="$end_ts" '
        NR == 1 {{ print; next }}
        $1 >= s && $1 <= e {{ print }}
    ' "$f" > "$out_f"

    # 检查裁剪后是否还有数据行
    line_count=$(wc -l < "$out_f")
    if [ "$line_count" -le 1 ]; then
        rm -f "$out_f"
        skipped=$((skipped + 1))
    else
        trimmed=$((trimmed + 1))
    fi
done

echo "RESULT:copied=$copied:trimmed=$trimmed:skipped=$skipped"
'''
    return script


def write_remote_linux_filter_script(remote_dir, out_dir, start_str, end_str, local_path):
    """
    生成 Linux 远程按时间范围筛选脚本到本地文件，方便上传到服务器执行
    :param remote_dir: 服务器上的 Monitor 目录路径（源）
    :param out_dir: 服务器上的输出目录路径（筛选后的数据放这里）
    :param start_str: 起始时间字符串
    :param end_str: 结束时间字符串
    :param local_path: 本地保存路径
    """
    script = build_remote_linux_filter_cmd(remote_dir, out_dir, start_str, end_str)
    with open(local_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(script)
