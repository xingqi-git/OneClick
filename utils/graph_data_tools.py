from PyQt5 import QtCore
import os
import datetime
import matplotlib.pyplot as plt
from matplotlib.dates import AutoDateLocator, DateFormatter
import pandas as pd
import numpy as np


def make_plot_figure(data_dic, action_name, time_start=None, time_end=None, filter_pids=None):
    """
    纯函数：根据数据生成 matplotlib 图表（直接调用，不经过线程）
    返回 fig 对象 或 (title, msg) 错误元组
    """
    try:
        # 用 rsplit 从右往左只分割1次，兼容进程名中包含'-'的情况
        parts = action_name.rsplit('-', 1)
        if len(parts) < 2:
            return ("参数错误", f"菜单项【{action_name}】格式错误")
        data_category = parts[0]
        data_indicator = parts[1]

        # 解析时间范围
        t_start = pd.Timestamp(time_start) if time_start else None
        t_end = pd.Timestamp(time_end) if time_end else None

        series_to_plot = []  # [(label, time_series, value_series)]

        for key, df in data_dic.items():
            if df is None or len(df) == 0:
                continue

            # 找时间列
            time_col = None
            for c in df.columns:
                if '时间' in c:
                    time_col = c
                    break
            if time_col is None:
                continue

            if data_indicator not in df.columns:
                continue

            if data_category == '系统':
                if key == '系统':
                    label = '系统'
                    series_to_plot.append((label, df[time_col], df[data_indicator]))
            else:
                # 进程类：key 就是基础进程名（如 "sshd"）
                if key != data_category:
                    continue

                # 没有 _pid 列（单文件的进程），直接画
                if '_pid' not in df.columns:
                    series_to_plot.append((key, df[time_col], df[data_indicator]))
                    continue

                # 指定了 filter_pids 且为空集合 → 直接跳过，不做 groupby
                if filter_pids is not None and len(filter_pids) == 0:
                    continue

                # 有 filter_pids → 先筛选再分组，更快
                if filter_pids is not None:
                    filtered_df = df[df['_pid'].astype(str).isin(filter_pids)]
                    if len(filtered_df) == 0:
                        continue
                    groupby_df = filtered_df
                else:
                    groupby_df = df

                for pid_val, group in groupby_df.groupby('_pid'):
                    label = f"{key}_{pid_val}" if pid_val else key
                    series_to_plot.append((label, group[time_col], group[data_indicator]))

        # 时间过滤
        if t_start is not None or t_end is not None:
            filtered = []
            for label, ts, vs in series_to_plot:
                mask = pd.Series(True, index=ts.index)
                if t_start is not None:
                    mask &= ts >= t_start
                if t_end is not None:
                    mask &= ts <= t_end
                if mask.any():
                    filtered.append((label, ts[mask], vs[mask]))
            series_to_plot = filtered

        # 降采样（点数太多时）
        max_points = 5000  # 最多画 5000 个点
        total_points = sum(len(vs) for _, _, vs in series_to_plot)
        if total_points > max_points * len(series_to_plot):
            resampled = []
            for label, ts, vs in series_to_plot:
                if len(ts) > max_points:
                    step = max(1, len(ts) // max_points)
                    resampled.append((label, ts.iloc[::step], vs.iloc[::step]))
                else:
                    resampled.append((label, ts, vs))
            series_to_plot = resampled

        # 创建图表（空图也创建，保证有坐标轴/标题）
        fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
        colors = plt.cm.tab10.colors
        color_idx = 0
        lines = []

        # X轴时间格式（即使没有线也设置）
        ax.xaxis.set_major_locator(AutoDateLocator())
        ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)

        ax.set_title(action_name, fontsize=12, fontweight='bold')
        ax.set_xlabel("系统时间", fontsize=10)
        ax.set_ylabel(data_indicator, fontsize=10)

        for label, ts, vs in series_to_plot:
            line = ax.plot(ts.values, vs.values, label=label,
                           color=colors[color_idx % len(colors)])[0]
            lines.append(line)
            color_idx += 1
            line.set_picker(True)
            line.set_pickradius(10)

        # 图例：有线就显示，空图显示提示文字
        if lines:
            if len(lines) <= 20:
                legend = ax.legend()
            else:
                legend = ax.legend(ncol=min(4, len(lines)//10 + 1), fontsize=7)
        else:
            # 空图提示
            ax.text(0.5, 0.5, "请在左侧勾选要查看的 PID",
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=14, color='#999')
            legend = None

        if legend is not None:
            legend.set_draggable(True)
            for leg_line, leg_text in zip(legend.get_lines(), legend.get_texts()):
                leg_line.set_picker(True)
                leg_text.set_picker(True)

            # 双击切换图例显隐
            def on_double_click(event):
                if event.dblclick and event.inaxes == ax:
                    legend.set_visible(not legend.get_visible())
                    fig.canvas.draw()
            fig.canvas.mpl_connect('button_press_event', on_double_click)

            # 拾取事件（点击图例/折线切换显隐）
            def on_pick(event):
                try:
                    clicked_artist = event.artist
                    if hasattr(clicked_artist, 'get_text'):
                        target_label = clicked_artist.get_text()
                    else:
                        target_label = clicked_artist.get_label()
                    line = next(l for l in lines if l.get_label() == target_label)
                    line.set_visible(not line.get_visible())
                    for leg_line, leg_text in zip(legend.get_lines(), legend.get_texts()):
                        if leg_text.get_text() == target_label:
                            alpha = 1.0 if line.get_visible() else 0.2
                            leg_line.set_alpha(alpha)
                            leg_text.set_alpha(alpha)
                            break
                    fig.canvas.draw()
                except StopIteration:
                    pass
            fig.canvas.mpl_connect('pick_event', on_pick)

        return fig
    except Exception as e:
        import traceback
        error_msg = f"绘图失败：{str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return ("错误", f"绘图过程中发生异常：{str(e)}")


class Worker(QtCore.QObject):
    """工作对象，包含耗时函数"""
    progress = QtCore.pyqtSignal(int)
    message = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(object)
    canceled = QtCore.pyqtSignal()

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.data_dic = {}
        self.canceled_flag = False

    def data_process(self):
        """数据处理主函数 - 用 pandas 加载 CSV 文件并按进程名合并"""
        try:
            self.canceled_flag = False
            file_paths = self.data  # 所有log数据文件的路径
            file_count = len(file_paths)
            self.message.emit(f"开始加载 {file_count} 个文件...")

            # 按进程基础名分组（sshd_1001, sshd_1002 -> 都属于 sshd 组）
            # 每个进程组的数据合并到一个 DataFrame
            proc_groups = {}  # {proc_base_name: [file_path, ...]}
            for fpath in file_paths:
                fname = os.path.basename(fpath)
                if fname == 'system.log':
                    proc_name = '系统'
                elif fname.endswith('.log'):
                    name_no_ext = fname[:-4]
                    last_underscore = name_no_ext.rfind('_')
                    if last_underscore > 0:
                        suffix = name_no_ext[last_underscore + 1:]
                        if suffix.isdigit():
                            proc_name = name_no_ext[:last_underscore]
                        else:
                            proc_name = name_no_ext
                    else:
                        proc_name = name_no_ext
                else:
                    continue
                if proc_name not in proc_groups:
                    proc_groups[proc_name] = []
                proc_groups[proc_name].append(fpath)

            total_groups = len(proc_groups)
            for idx, (proc_name, paths) in enumerate(proc_groups.items()):
                if self._is_canceled():
                    break

                self.message.emit(f"正在加载 {proc_name} ({idx+1}/{total_groups})...")
                try:
                    df = self._load_and_merge_files(paths, proc_name)
                    if df is not None and len(df) > 0:
                        self.data_dic[proc_name] = df
                    self.progress.emit(int(100 * (idx + 1) / total_groups))
                except Exception as e:
                    self.message.emit(f"加载 {proc_name} 失败: {e}")

            if self.canceled_flag:
                self.canceled.emit()
            else:
                self.finished.emit(self.data_dic)
        except Exception as e:
            import traceback
            error_msg = f"数据处理失败：{str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.finished.emit(("错误", f"数据处理失败：{str(e)}"))

    def _load_and_merge_files(self, file_paths, proc_name):
        """加载多个文件并合并为一个 DataFrame"""
        dfs = []
        time_col = None
        for fpath in file_paths:
            if self._is_canceled():
                return None
            try:
                # 用 pandas 读 CSV，C 引擎，让 pandas 自动推断类型
                df = pd.read_csv(
                    fpath,
                    encoding='utf-8-sig',  # 自动处理 BOM
                    engine='c',
                    on_bad_lines='skip',  # 跳过坏行
                )
                if len(df) == 0:
                    continue

                # 清理列名（去除不可见字符、空格）
                df.columns = [c.strip() for c in df.columns]

                # 找时间列
                if time_col is None:
                    for c in df.columns:
                        if '时间' in c:
                            time_col = c
                            break

                # 给每个文件的数据加一个 PID 标识（如果是单PID文件）
                fname = os.path.basename(fpath)
                if fname != 'system.log' and fname.endswith('.log'):
                    name_no_ext = fname[:-4]
                    last_underscore = name_no_ext.rfind('_')
                    if last_underscore > 0 and name_no_ext[last_underscore+1:].isdigit():
                        pid = name_no_ext[last_underscore+1:]
                        df['_pid'] = pid
                    else:
                        df['_pid'] = ''  # 汇总文件，pid 为空
                else:
                    df['_pid'] = ''

                dfs.append(df)
            except Exception as e:
                print(f"读取文件 {fpath} 失败: {e}")
                continue

        if not dfs:
            return None

        # 合并所有 DataFrame
        merged = pd.concat(dfs, ignore_index=True)

        # 时间列转 datetime
        if time_col and time_col in merged.columns:
            merged[time_col] = pd.to_datetime(merged[time_col], errors='coerce')
            # 去掉时间为空的行
            merged = merged.dropna(subset=[time_col])
            # 按时间排序
            merged = merged.sort_values(time_col).reset_index(drop=True)

        # 确保数值列是数值类型（自动推断失败时兜底）
        skip_cols = set()
        if time_col:
            skip_cols.add(time_col)
        skip_cols.add('_pid')

        for col in merged.columns:
            if col in skip_cols:
                continue
            if not pd.api.types.is_numeric_dtype(merged[col]):
                merged[col] = pd.to_numeric(merged[col], errors='coerce').fillna(0)

        return merged

    def _is_canceled(self):
        thread_obj = self.thread()
        if thread_obj is not None and thread_obj.isInterruptionRequested():
            self.canceled_flag = True
            return True
        return False

    def create_plot_tab(self):
        """
        根据指标名创建绘图标签页（调用纯函数 make_plot_figure）
        self.data = [data_dic, action_name, time_start, time_end, pids(可选)]
        """
        try:
            self.canceled_flag = False
            self.message.emit("正在绘图，请稍后...")

            data_dic = self.data[0]
            action_name = self.data[1]
            time_start = self.data[2] if len(self.data) > 2 else None
            time_end = self.data[3] if len(self.data) > 3 else None
            filter_pids = self.data[4] if len(self.data) > 4 else None

            result = make_plot_figure(data_dic, action_name, time_start, time_end, filter_pids)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(("错误", f"绘图过程中发生异常：{str(e)}"))

    def extract_pid_series(self):
        """
        提取单个PID单个指标的曲线数据（用于原图动态增删曲线）
        self.data = [data_dic, proc_name, ind_name, pid, time_start, time_end]
        返回 (label, x_list, y_list)，数据不存在返回 None
        """
        try:
            data_dic = self.data[0]
            proc_name = self.data[1]
            ind_name = self.data[2]
            pid = str(self.data[3])
            time_start = self.data[4] if len(self.data) > 4 else None
            time_end = self.data[5] if len(self.data) > 5 else None

            df = data_dic.get(proc_name)
            if df is None or len(df) == 0 or ind_name not in df.columns:
                self.finished.emit(None)
                return

            time_col = None
            for c in df.columns:
                if '时间' in c:
                    time_col = c
                    break
            if time_col is None:
                self.finished.emit(None)
                return

            if '_pid' in df.columns:
                group = df[df['_pid'] == pid]
            else:
                group = df
            if len(group) == 0:
                self.finished.emit(None)
                return

            ts = group[time_col]
            vs = group[ind_name]

            # 时间过滤
            t_start = pd.Timestamp(time_start) if time_start else None
            t_end = pd.Timestamp(time_end) if time_end else None
            if t_start is not None or t_end is not None:
                mask = pd.Series(True, index=ts.index)
                if t_start is not None:
                    mask &= ts >= t_start
                if t_end is not None:
                    mask &= ts <= t_end
                ts = ts[mask]
                vs = vs[mask]

            if len(ts) == 0:
                self.finished.emit(None)
                return

            # 降采样
            max_points = 5000
            if len(ts) > max_points:
                step = max(1, len(ts) // max_points)
                ts = ts.iloc[::step]
                vs = vs.iloc[::step]

            label = f"{proc_name}_{pid}" if '_pid' in df.columns else proc_name
            self.finished.emit((label, list(ts.values), list(vs.values)))
        except Exception as e:
            print(f"提取PID曲线失败: {e}")
            self.finished.emit(None)
