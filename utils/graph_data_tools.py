from PyQt5 import QtCore
import os
import datetime
import matplotlib.pyplot as plt
from matplotlib.dates import AutoDateLocator, DateFormatter  # 导入时间轴工具

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
        """数据处理主函数"""
        try:
            self.canceled_flag = False
            # 处理每个文件
            file_count = len(self.data) # 所有log数据文件的路径
            for i, log_file in enumerate(self.data):
                # 处理单个文件,更新进度
                filename = os.path.basename(log_file)
                self.message.emit(f"当前正在处理第 {i+1}/{file_count} 个文件: {filename}")
                self.process_log_file(log_file)

            # 步骤3：完成
            if self.canceled_flag:
                self.canceled.emit()
            else:
                self.finished.emit(self.data_dic)
        except Exception as e:
            import traceback
            error_msg = f"数据处理失败：{str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.finished.emit(("错误", f"数据处理失败：{str(e)}"))

    def process_log_file(self, filepath):
        """处理单个日志文件"""
        filename = os.path.basename(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) <= 1:
                self.message.emit(f"{filename}文件无有效数据")
                return
            last_emitted_progress = 0

            # 清理字符串中的NUL字符和不可见字符
            import re
            def clean_invalid_chars(s: str) -> str:
                """
                清理字符串中的无效字符：
                - 移除 UTF-8 BOM (\ufeff)
                - 移除所有 ASCII 控制字符（\x00-\x1F、\x7F）
                - 移除多余空白、首尾空白
                """
                if not isinstance(s, str):
                    return ""
                # 1. 去掉 BOM 头
                s = s.replace('\ufeff', '')
                # 2. 去掉所有不可打印的控制字符
                s = re.sub(r'[\x00-\x1F\x7F]', '', s)
                # 3. 清理空白（换行、制表符、多个空格 → 单个空格）
                s = re.sub(r'\s+', ' ', s).strip()
                return s

            # 读取文件的第一行，用逗号分割作为keys[]
            keys = clean_invalid_chars(lines[0]).split(',')
            # 如果第一行的keys第一个没有"时间"，则跳过
            if len(keys) > 0 and "时间" not in keys[0]:
                self.message.emit(f"{filename}文件数据错误")
                return

            if filename=="system.log":
                key = "系统"
            elif filename.endswith(".log"):
                key = filename[:-4]
            else:
                return
            # 初始化数据结构data_dic={"系统"：{"时间":[],"内存":[],"CPU":[]...},"top_123"：{}}
            if key not in self.data_dic:
                self.data_dic[key] = {}
                for k in keys:
                    self.data_dic[key][k] = []
            # 从第二行开始读取数据
            for i in range(1, len(lines)):
                # 线程对象访问防护
                thread_obj = self.thread()
                if thread_obj is not None and thread_obj.isInterruptionRequested():
                    self.canceled_flag = True
                    break

                # 先清理整行的NUL和不可见字符，再去空
                line = clean_invalid_chars(lines[i])
                if not line:
                    continue

                # 分割后对每个值单独清理
                values = [clean_invalid_chars(v) for v in line.split(',')]

                # 如果values长度不对，则跳过
                if len(values) != len(keys):
                    continue

                for idx in range(len(keys)):
                    try:
                        # 尝试取值并去除空格
                        val = values[idx].strip()
                        # 空字符串则赋值为'0'
                        val = val if val else '0'
                    except IndexError:
                        # 索引不存在则直接赋值为'0'
                        val = '0'
                    # 追加到字典对应字段
                    self.data_dic[key][keys[idx]].append(val)

                progress = int(100 * i / (len(lines) - 1))
                # 只有当进度增加了至少 1% 时才 emit，防止 UI 卡顿
                if progress > last_emitted_progress:
                    self.progress.emit(progress)
                    last_emitted_progress = progress

    def create_plot_tab(self):
        """
        根据菜单项名称创建绘图标签页
        :param action_name: 菜单项名称（如"系统-内存"、"top-CPU"）
        """
        try:
            self.canceled_flag = False
            self.message.emit("正在绘图，请稍后...")
            # 解析菜单项名称，获取数据分类和指标 self.data = [self.data_dic, action_name]
            # 用rsplit从右往左只分割1次，兼容进程名中包含'-'的情况(如0-1_405-进程RSS)
            parts = self.data[1].rsplit('-', 1)
            if len(parts) < 2:
                error = ("参数错误", f"菜单项【{self.data[1]}】格式错误，应为'分类-指标'")
                self.finished.emit((error[0], error[1]))
                return
            data_category = parts[0]  # 数据分类 (系统/top)
            data_indicator = parts[1]  # 监控指标（内存/CPU/文件描述符等）

            # self.data[0]的key = 系统,top_123,top_587,top等
            has_matched = any(key == data_category or key.startswith(data_category) for key in self.data[0])

            if not has_matched:
                error = ("数据缺失",f"{self.data[1]}未找到【{data_category}】的相关监控数据")
                self.finished.emit((error[0], error[1]))
                return
            # 创建matplotlib绘图组件
            fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)

            # 使用matplotlib内置的tab10调色板
            colors = plt.cm.tab10.colors
            # 初始化索引，用于循环分配颜色
            color_idx = 0

            lines = []  # 存储折线对象
            for key in self.data[0]:
                if key == data_category or key.startswith(data_category):
                    # 获取时间列表 - 使用 .get() 防止 KeyError
                    time_str_list = self.data[0][key].get("系统时间", [])
                    if not time_str_list:
                        continue

                    # 获取指标数值列表
                    value_raw_list = self.data[0][key].get(data_indicator, [])
                    if not value_raw_list:
                        continue

                    data_total = len(value_raw_list) + len(time_str_list)
                    data_count = 0
                    last_emitted_progress = 0
                    time_list = []
                    value_list = []
                    try:
                        for t in time_str_list:
                            # 线程对象访问防护
                            thread_obj = self.thread()
                            if thread_obj is not None and thread_obj.isInterruptionRequested():
                                self.canceled_flag = True
                                self.canceled.emit()
                                return
                            # 将时间字符串解析为datetime对象（匹配时间格式：%Y-%m-%d %H:%M:%S）
                            time_list.append(datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S'))
                            # 进度更新逻辑
                            data_count += 1
                            current_progress = int(100 * data_count / data_total)
                            # 只有当进度增加了至少 1% 时才 emit，防止 UI 卡顿
                            if current_progress > last_emitted_progress:
                                self.progress.emit(current_progress)
                                last_emitted_progress = current_progress
                    except ValueError as e:
                        error = ("错误", f"{self.data[1]}时间格式解析失败：{e}")
                        self.finished.emit((error[0], error[1]))
                        return

                    # 数据格式转换（字符串→数值，方便绘图）
                    try:
                        for v in value_raw_list:
                            thread_obj = self.thread()
                            if thread_obj is not None and thread_obj.isInterruptionRequested():
                                self.canceled_flag = True
                                self.canceled.emit()
                                return
                            value_list.append(float(v))
                            # 进度更新逻辑
                            data_count += 1
                            current_progress = int(100 * data_count / data_total)
                            # 只有当进度增加了至少 1% 时才 emit，防止 UI 卡顿
                            if current_progress > last_emitted_progress:
                                self.progress.emit(current_progress)
                                last_emitted_progress = current_progress
                    except ValueError:
                        error = ("数据错误", f"【{self.data[1]}】的监控数据格式错误，无法转换为数值")
                        self.finished.emit((error[0], error[1]))
                        return

                    # 校验数据有效性
                    if not time_list or len(value_list) == 0:
                        error = ("数据缺失", f"【{self.data[1]}】无可用的监控数据")
                        self.finished.emit((error[0], error[1]))
                        return

                    # 分配颜色 + 保存折线对象
                    line = ax.plot(time_list, value_list, label=f"{key}:{data_indicator}",
                                   color=colors[color_idx % len(colors)])[0]
                    lines.append(line)
                    color_idx += 1

                    # 给折线本身开启拾取功能
                    line.set_picker(True)  # 让折线可被鼠标点击拾取
                    line.set_pickradius(10)  # 扩大折线点击判定范围（10像素，避免点不准）

            # 检查是否成功绘制了至少一条曲线
            if not lines:
                error = ("数据缺失", f"【{self.data[1]}】没有可用的监控数据")
                self.finished.emit((error[0], error[1]))
                return

            # AutoDateLocator：自动根据X轴宽度调整时间间隔（窗口大→显示多刻度，窗口小→显示少刻度）
            ax.xaxis.set_major_locator(AutoDateLocator())
            # DateFormatter：设置时间显示格式（可根据需要调整，比如简化为'%m-%d %H:%M'）
            ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))
            # 旋转x轴时间标签，避免重叠
            plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)  # ha='right'让标签右对齐，更整齐

            # 设置图表标题和坐标轴标签
            ax.set_title(self.data[1], fontsize=12, fontweight='bold')
            ax.set_xlabel("系统时间", fontsize=10)
            ax.set_ylabel(data_indicator, fontsize=10)

            # 图例点击逻辑
            legend = ax.legend()  # 显式创建图例
            legend.set_draggable(True)  # 可拖拽
            # 同时给图例的"线条"和"文字"开启拾取功能
            for leg_line, leg_text in zip(legend.get_lines(), legend.get_texts()):
                leg_line.set_picker(True)  # 图例线条可点击
                leg_text.set_picker(True)  # 图例文字可点击

            # 双击图形区域切换图例显隐
            def on_double_click(event):
                if event.dblclick:
                    if event.inaxes == ax:  # 在图形区域内
                        legend.set_visible(not legend.get_visible())
                        fig.canvas.draw()

            fig.canvas.mpl_connect('button_press_event', on_double_click)

            # 兼容"图例线条/图例文字/折线"的点击事件
            def on_pick(event):
                try:
                    clicked_artist = event.artist
                    # 区分点击对象：是文字（图例名称）还是线条（图例线条/图表折线）
                    if hasattr(clicked_artist, 'get_text'):
                        # 点击的是图例文字：取文字内容作为label
                        target_label = clicked_artist.get_text()
                    else:
                        # 点击的是线条（图例线条/图表折线）：取线条label
                        target_label = clicked_artist.get_label()

                    # 找到匹配label的折线
                    line = next(l for l in lines if l.get_label() == target_label)
                    # 切换折线显隐
                    line.set_visible(not line.get_visible())

                    # 同步更新"图例线条+文字"的样式（视觉反馈）
                    for leg_line, leg_text in zip(legend.get_lines(), legend.get_texts()):
                        if leg_text.get_text() == target_label:
                            # 显隐状态同步：隐藏时变浅，显示时恢复
                            alpha = 1.0 if line.get_visible() else 0.2
                            leg_line.set_alpha(alpha)
                            leg_text.set_alpha(alpha)
                            break

                    fig.canvas.draw()  # 刷新图表
                except StopIteration:
                    pass  # 容错：匹配不到时跳过

            # 绑定事件
            fig.canvas.mpl_connect('pick_event', on_pick)
            self.finished.emit(fig)
        except Exception as e:
            # 顶层异常捕获，防止崩溃
            import traceback
            error_msg = f"绘图失败：{str(e)}\n{traceback.format_exc()}"
            print(error_msg)  # 调试用
            self.finished.emit(("错误", f"绘图过程中发生异常：{str(e)}"))

if __name__ == "__main__":
    pass
