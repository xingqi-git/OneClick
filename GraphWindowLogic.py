from UI import GraphMainWindow
import os
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QTreeWidgetItem
import pandas as pd

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt
from utils.graph_data_tools import Worker

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


class GraphWindow(QMainWindow, GraphMainWindow.Ui_MainWindow):
    def __init__(self, data_path, parent=None, server_config=None):
        super().__init__(parent)
        self.setupUi(self)

        self.data_path = data_path
        self.original_data_path = data_path
        self.server_config = server_config
        self.data_dic = {}  # {进程名: DataFrame}
        self.loaded_processes = set()
        self.file_map = {}  # {进程名: [文件名, ...]}
        self.indicator_map = {}  # {进程名: [指标名, ...]}
        self.pid_map = {}  # {进程名: [pid1, pid2, ...]} 该进程包含的PID列表
        self.process_tree_items = {}
        self._updating_tree = False

        # 选中状态
        self.selected_indicators = {}  # {proc_name: {ind_name, ...}}
        self.selected_pids = {}  # {proc_name: {pid, ...}}
        self.loaded_pids = {}  # {proc_name: {pid, ...}}  已经加载了哪些PID
        self.fig_objects = {}  # {action_name: fig_info}  保存绘图对象，用于动态更新

        self.threads = {}
        self.workers = {}
        self.action_tab_map = {}  # {action_name: tab_index}

        self.current_time_start = None
        self.current_time_end = None
        self.global_min_time = None
        self.global_max_time = None

        self._build_ui()
        self._scan_files()
        self._build_tree()
        self.showMaximized()

    def _build_ui(self):
        self.menuBar().hide()

        # 顶部工具栏（两行，固定高度）
        top_bar = QtWidgets.QWidget(self.centralwidget)
        top_bar.setMaximumHeight(70)
        top_layout = QtWidgets.QVBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)
        top_layout.setSpacing(2)

        # 第一行：数据源 + 操作按钮
        row1 = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel()
        self.path_label.setStyleSheet("color: #666;")
        self.path_label.setText(f"数据源：{self.data_path}")
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row1.addWidget(self.path_label)
        row1.addSpacing(12)

        self.load_folder_btn = QtWidgets.QPushButton("切换数据源")
        self.load_folder_btn.clicked.connect(self.on_load_other_folder)
        row1.addWidget(self.load_folder_btn)

        self.update_btn = QtWidgets.QPushButton("更新数据")
        self.update_btn.clicked.connect(self.on_update_data)
        row1.addWidget(self.update_btn)
        if self.server_config is None:
            self.update_btn.hide()

        row1.addStretch()
        top_layout.addLayout(row1)

        # 第二行：时间筛选
        row2 = QtWidgets.QHBoxLayout()
        self.start_label = QtWidgets.QLabel("开始：")
        self.start_dateTimeEdit = QtWidgets.QDateTimeEdit()
        self.start_dateTimeEdit.setCalendarPopup(True)
        self.start_dateTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_dateTimeEdit.setEnabled(False)

        self.end_label = QtWidgets.QLabel("结束：")
        self.end_dateTimeEdit = QtWidgets.QDateTimeEdit()
        self.end_dateTimeEdit.setCalendarPopup(True)
        self.end_dateTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_dateTimeEdit.setEnabled(False)

        self.apply_filter_btn = QtWidgets.QPushButton("应用筛选")
        self.apply_filter_btn.clicked.connect(self.apply_time_filter)
        self.apply_filter_btn.setEnabled(False)
        self.reset_filter_btn = QtWidgets.QPushButton("重置")
        self.reset_filter_btn.clicked.connect(self.reset_time_filter)
        self.reset_filter_btn.setEnabled(False)

        row2.addWidget(self.start_label)
        row2.addWidget(self.start_dateTimeEdit)
        row2.addSpacing(6)
        row2.addWidget(self.end_label)
        row2.addWidget(self.end_dateTimeEdit)
        row2.addSpacing(6)
        row2.addWidget(self.apply_filter_btn)
        row2.addWidget(self.reset_filter_btn)
        row2.addStretch()

        top_layout.addLayout(row2)

        self._filter_widgets = [
            self.start_label, self.start_dateTimeEdit,
            self.end_label, self.end_dateTimeEdit,
            self.apply_filter_btn, self.reset_filter_btn
        ]

        # 左侧树 + 右侧标签页
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        tree_label = QtWidgets.QLabel("进程 / 指标")
        tree_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(tree_label)

        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.itemChanged.connect(self.on_tree_item_changed)
        left_layout.addWidget(self.tree_widget)

        splitter.addWidget(left_widget)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)
        splitter.addWidget(self.tab_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 800])

        central_layout = QtWidgets.QVBoxLayout(self.centralwidget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(top_bar)
        central_layout.addWidget(splitter)
        self.centralwidget.setLayout(central_layout)

    def _scan_files(self):
        """扫描数据文件夹，归并进程，读取表头和PID列表"""
        self.file_map = {}
        self.indicator_map = {}
        self.pid_map = {}

        if not os.path.isdir(self.data_path):
            return

        try:
            all_files = [f for f in os.listdir(self.data_path) if f.endswith('.log')]
        except Exception:
            return

        for filename in all_files:
            if filename == 'system.log':
                proc_name = '系统'
                pid = ''
            else:
                name_no_ext = filename[:-4]
                last_underscore = name_no_ext.rfind('_')
                if last_underscore > 0:
                    suffix = name_no_ext[last_underscore + 1:]
                    if suffix.isdigit():
                        proc_name = name_no_ext[:last_underscore]
                        pid = suffix
                    else:
                        proc_name = name_no_ext
                        pid = ''
                else:
                    proc_name = name_no_ext
                    pid = ''

            if proc_name not in self.file_map:
                self.file_map[proc_name] = []
                self.pid_map[proc_name] = []
            self.file_map[proc_name].append(filename)
            if pid and pid not in self.pid_map[proc_name]:
                self.pid_map[proc_name].append(pid)

        # 读每个进程第一个文件的表头，并校验格式
        valid_procs = []
        for proc_name, files in self.file_map.items():
            files_sorted = sorted(files, key=len, reverse=True)
            first_file = files_sorted[0]
            filepath = os.path.join(self.data_path, first_file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    header_line = f.readline()
                    if not header_line:
                        continue
                    import re
                    keys = [k.replace('\ufeff', '').strip() for k in header_line.split(',')]
                    # 格式校验：表头第一列必须是"系统时间"，否则跳过（非监控数据文件）
                    if not keys or keys[0] != '系统时间':
                        continue
                    indicators = [k for k in keys if '时间' not in k]
                    self.indicator_map[proc_name] = indicators
                    valid_procs.append(proc_name)
            except Exception:
                continue

        # 只保留格式校验通过的进程
        self.file_map = {p: self.file_map[p] for p in valid_procs}
        self.pid_map = {p: self.pid_map[p] for p in valid_procs if p in self.pid_map}

        # PID 排序
        for proc_name in self.pid_map:
            try:
                self.pid_map[proc_name].sort(key=lambda x: int(x))
            except ValueError:
                self.pid_map[proc_name].sort()

    def _build_tree(self):
        """构建树形结构：
        系统类：系统 → 指标（直接勾选画图）
        进程类：进程 → 指标 + 单PID列表（指标+PID组合出图）
        """
        self._updating_tree = True
        self.tree_widget.clear()
        self.process_tree_items = {}

        if not self.file_map:
            item = QTreeWidgetItem(["暂无监控数据"])
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.tree_widget.addTopLevelItem(item)
            self._updating_tree = False
            return

        proc_names = list(self.file_map.keys())
        if '系统' in proc_names:
            proc_names.remove('系统')
            proc_names.sort()
            proc_names.insert(0, '系统')
        else:
            proc_names.sort()

        for proc_name in proc_names:
            indicators = self.indicator_map.get(proc_name, [])
            if not indicators:
                continue

            proc_item = QTreeWidgetItem([proc_name])
            proc_item.setFlags(proc_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            proc_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            proc_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('process', proc_name))

            pids = self.pid_map.get(proc_name, [])
            is_system_or_single = (proc_name == '系统' or len(pids) == 0)

            # 指标节点（系统类直接是指标，进程类也是指标但和PID组合出图）
            for ind_name in indicators:
                child = QTreeWidgetItem([ind_name])
                child.setFlags(child.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('indicator', proc_name, ind_name))
                proc_item.addChild(child)

            # 进程类：加一个"单PID"分组
            if not is_system_or_single and pids:
                pid_group_item = QTreeWidgetItem([f"单PID（{len(pids)}个）"])
                pid_group_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('pid_group', proc_name))
                # 分组节点可勾选，勾选=全选子PID
                pid_group_item.setFlags(
                    pid_group_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                )
                pid_group_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

                for pid in pids:
                    pid_item = QTreeWidgetItem([f"{proc_name}_{pid}"])
                    pid_item.setFlags(pid_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    pid_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                    pid_item.setData(0, QtCore.Qt.ItemDataRole.UserRole,
                                     ('pid', proc_name, pid))
                    pid_group_item.addChild(pid_item)

                proc_item.addChild(pid_group_item)

            self.tree_widget.addTopLevelItem(proc_item)
            self.process_tree_items[proc_name] = proc_item
            # 默认展开第一级
            self.tree_widget.expandItem(proc_item)

        self._updating_tree = False

    def on_tree_item_changed(self, item, column):
        if column != 0:
            return
        if self._updating_tree:
            return
        self._updating_tree = True

        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            self._updating_tree = False
            return

        node_type = data[0]

        if node_type == 'process':
            # 进程节点勾选：同步所有指标子节点的勾选状态 + 更新 selected_indicators
            proc_name = data[1]
            state = item.checkState(0)
            checked = state == QtCore.Qt.CheckState.Checked
            if proc_name not in self.selected_indicators:
                self.selected_indicators[proc_name] = set()

            for i in range(item.childCount()):
                child = item.child(i)
                child_data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not child_data:
                    continue
                if child_data[0] == 'indicator':
                    child.setCheckState(0, state)
                    ind_name = child_data[2]
                    if checked:
                        self.selected_indicators[proc_name].add(ind_name)
                    else:
                        self.selected_indicators[proc_name].discard(ind_name)
            # 触发变更处理
            self._handle_selection_change(proc_name)

        elif node_type == 'indicator':
            # 指标节点勾选/取消
            proc_name = data[1]
            ind_name = data[2]
            checked = item.checkState(0) == QtCore.Qt.CheckState.Checked

            if proc_name not in self.selected_indicators:
                self.selected_indicators[proc_name] = set()
            if checked:
                self.selected_indicators[proc_name].add(ind_name)
            else:
                self.selected_indicators[proc_name].discard(ind_name)

            # 更新父节点状态
            self._update_process_check_state(item.parent())
            # 处理绘图变化
            self._handle_selection_change(proc_name)

        elif node_type == 'pid_group':
            # PID分组节点勾选：同步所有子PID
            proc_name = data[1]
            state = item.checkState(0)
            for i in range(item.childCount()):
                child = item.child(i)
                child_data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if child_data and child_data[0] == 'pid':
                    child.setCheckState(0, state)
                    pid = child_data[2]
                    if proc_name not in self.selected_pids:
                        self.selected_pids[proc_name] = set()
                    if state == QtCore.Qt.CheckState.Checked:
                        self.selected_pids[proc_name].add(pid)
                    else:
                        self.selected_pids[proc_name].discard(pid)
            self._handle_selection_change(proc_name)

        elif node_type == 'pid':
            # PID节点勾选/取消
            proc_name = data[1]
            pid = data[2]
            checked = item.checkState(0) == QtCore.Qt.CheckState.Checked

            if proc_name not in self.selected_pids:
                self.selected_pids[proc_name] = set()
            if checked:
                self.selected_pids[proc_name].add(pid)
            else:
                self.selected_pids[proc_name].discard(pid)

            # 更新PID分组节点状态（全选/半选/未选）
            pid_group = item.parent()
            if pid_group:
                self._update_pid_group_state(pid_group)

            # 处理绘图变化
            self._handle_selection_change(proc_name)

        self._updating_tree = False

    def _update_process_check_state(self, proc_item):
        """根据指标子节点状态更新进程节点的勾选状态"""
        if proc_item is None:
            return
        data = proc_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data or data[0] != 'process':
            return

        checked_count = 0
        total = 0
        for i in range(proc_item.childCount()):
            child = proc_item.child(i)
            child_data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not child_data or child_data[0] != 'indicator':
                continue
            total += 1
            if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                checked_count += 1

        if total == 0:
            return

        if checked_count == 0:
            proc_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        elif checked_count == total:
            proc_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        else:
            proc_item.setCheckState(0, QtCore.Qt.CheckState.PartiallyChecked)

    def _update_pid_group_state(self, pid_group_item):
        """根据子PID的勾选状态更新PID分组节点（全选/半选/未选）"""
        if pid_group_item is None:
            return
        checked_count = 0
        total = pid_group_item.childCount()
        if total == 0:
            return
        for i in range(total):
            child = pid_group_item.child(i)
            if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                checked_count += 1
        if checked_count == 0:
            pid_group_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        elif checked_count == total:
            pid_group_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        else:
            pid_group_item.setCheckState(0, QtCore.Qt.CheckState.PartiallyChecked)

    def _handle_selection_change(self, proc_name):
        """指标或PID选择变化时，更新对应的图表"""
        indicators = self.selected_indicators.get(proc_name, set())
        pids = self.selected_pids.get(proc_name, set())
        is_system_or_single = (proc_name == '系统' or len(self.pid_map.get(proc_name, [])) == 0)

        # 系统类或单PID进程：有指标选中就加载（一次加载全部）
        if is_system_or_single:
            if indicators and proc_name not in self.loaded_processes:
                self._load_process_data(proc_name,
                                        on_finished=lambda ok: self._redraw_proc_charts(proc_name) if ok else None)
            else:
                self._redraw_proc_charts(proc_name)
            return

        # 多PID进程类：按需加载选中的PID
        if not indicators:
            # 没选中指标，直接重绘（关图）
            self._redraw_proc_charts(proc_name)
            return

        # 有指标，计算需要新加载的PID
        if proc_name not in self.loaded_pids:
            self.loaded_pids[proc_name] = set()
        new_pids = pids - self.loaded_pids[proc_name]

        if new_pids:
            # 有新PID需要加载
            self._load_pid_data(proc_name, new_pids,
                                on_finished=lambda ok: self._redraw_proc_charts(proc_name) if ok else None)
        else:
            # 所有选中的PID都加载过了，直接重绘
            self._redraw_proc_charts(proc_name)

    def _redraw_proc_charts(self, proc_name):
        """重绘某个进程的所有图表（根据当前选中的指标+PID）"""
        indicators = self.selected_indicators.get(proc_name, set())
        pids = self.selected_pids.get(proc_name, set())
        is_system_or_single = (proc_name == '系统' or len(self.pid_map.get(proc_name, [])) == 0)

        # 系统类或单PID进程：直接画图
        if is_system_or_single:
            for ind_name in list(indicators):
                action_name = f"{proc_name}-{ind_name}"
                if action_name not in self.action_tab_map:
                    self._draw_indicator(action_name)
            # 取消的关图
            all_inds = self.indicator_map.get(proc_name, [])
            for ind_name in all_inds:
                action_name = f"{proc_name}-{ind_name}"
                if ind_name not in indicators and action_name in self.action_tab_map:
                    self.remove_plot_tab(action_name)
            return

        # 多PID进程类：指标 + 选中PID 组合出图
        for ind_name in list(indicators):
            action_name = f"{proc_name}-{ind_name}"
            if action_name not in self.action_tab_map:
                # 新图：从头画（可以是空图）
                self._draw_indicator(action_name, pids=pids)
            else:
                # 已有图：在原图上动态增删曲线
                self._update_plot_pids(action_name, pids)

        # 取消了的指标，关图
        all_inds = self.indicator_map.get(proc_name, [])
        for ind_name in all_inds:
            action_name = f"{proc_name}-{ind_name}"
            if ind_name not in indicators and action_name in self.action_tab_map:
                self.remove_plot_tab(action_name)

    def _load_process_data(self, proc_name, on_finished=None):
        """加载指定进程的所有文件数据（系统类或单PID进程用）"""
        files = self.file_map.get(proc_name, [])
        if not files:
            if on_finished:
                on_finished(False)
            return

        file_paths = [os.path.join(self.data_path, f) for f in files]
        load_key = f'load_{proc_name}'
        if load_key in self.threads:
            return  # 已经在加载了

        worker = Worker(file_paths)
        thread = QtCore.QThread()
        self.workers[load_key] = worker
        self.threads[load_key] = thread
        worker.moveToThread(thread)

        def on_finished_wrap(data=None):
            if isinstance(data, tuple) and len(data) >= 2 and data[0] == '错误':
                QtWidgets.QMessageBox.warning(self, "提示", f"加载{proc_name}数据失败：{data[1]}")
                if on_finished:
                    on_finished(False)
            else:
                # data 是 {proc_name: DataFrame} 字典
                for key, val in data.items():
                    self.data_dic[key] = val
                self.loaded_processes.add(proc_name)
                # 记录已加载的PID
                if proc_name not in self.loaded_pids:
                    self.loaded_pids[proc_name] = set()
                df = self.data_dic.get(proc_name)
                if df is not None and '_pid' in df.columns:
                    self.loaded_pids[proc_name] = set(df['_pid'].unique())
                self._update_global_time_range()
                for w in self._filter_widgets:
                    w.setEnabled(True)
                if on_finished:
                    on_finished(True)

            worker.deleteLater()
            thread.quit()
            self.threads.pop(load_key, None)
            self.workers.pop(load_key, None)

        worker.finished.connect(on_finished_wrap)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.data_process)
        thread.start()

    def _load_pid_data(self, proc_name, pids, on_finished=None):
        """增量加载指定进程的指定PID文件，合并到已有数据中"""
        all_files = self.file_map.get(proc_name, [])
        # 找出这些 PID 对应的文件
        files_to_load = []
        for f in all_files:
            if not f.endswith('.log'):
                continue
            name_no_ext = f[:-4]
            last_underscore = name_no_ext.rfind('_')
            if last_underscore > 0:
                pid = name_no_ext[last_underscore + 1:]
                if pid.isdigit() and pid in pids:
                    files_to_load.append(f)
            else:
                # 汇总文件（没有数字后缀），如果还没加载过进程也一起加载
                # 但这里是增量加载 PID，汇总文件不需要重复加载
                pass

        if not files_to_load:
            if on_finished:
                on_finished(False)
            return

        file_paths = [os.path.join(self.data_path, f) for f in files_to_load]
        load_key = f'load_{proc_name}_pid_{"_".join(sorted(pids))}'
        if load_key in self.threads:
            return

        worker = Worker(file_paths)
        thread = QtCore.QThread()
        self.workers[load_key] = worker
        self.threads[load_key] = thread
        worker.moveToThread(thread)

        def on_finished_wrap(data=None):
            if isinstance(data, tuple) and len(data) >= 2 and data[0] == '错误':
                QtWidgets.QMessageBox.warning(self, "提示", f"加载{proc_name}数据失败：{data[1]}")
                if on_finished:
                    on_finished(False)
            else:
                # data 是 {proc_name: DataFrame} 字典（新加载的）
                new_df = None
                for key, val in data.items():
                    new_df = val
                    break

                if new_df is not None:
                    # 合并到已有数据
                    if proc_name in self.data_dic and self.data_dic[proc_name] is not None:
                        old_df = self.data_dic[proc_name]
                        combined = pd.concat([old_df, new_df], ignore_index=True)
                        time_col = None
                        for c in combined.columns:
                            if '时间' in c:
                                time_col = c
                                break
                        if time_col:
                            combined = combined.sort_values(time_col).reset_index(drop=True)
                        self.data_dic[proc_name] = combined
                    else:
                        self.data_dic[proc_name] = new_df
                        self.loaded_processes.add(proc_name)

                    # 记录已加载的PID
                    if proc_name not in self.loaded_pids:
                        self.loaded_pids[proc_name] = set()
                    if '_pid' in new_df.columns:
                        self.loaded_pids[proc_name].update(new_df['_pid'].unique())

                self._update_global_time_range()
                for w in self._filter_widgets:
                    w.setEnabled(True)
                if on_finished:
                    on_finished(True)

            worker.deleteLater()
            thread.quit()
            self.threads.pop(load_key, None)
            self.workers.pop(load_key, None)

        worker.finished.connect(on_finished_wrap)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.data_process)
        thread.start()

    def _draw_indicator(self, action_name, pids=None):
        """绘图（从 self.data_dic 读数据，主线程直接画）
        pids: set/list，只画这些 PID；None 表示画全部（系统类或单PID进程用None）
        """
        if action_name in self.action_tab_map:
            return

        from utils.graph_data_tools import make_plot_figure

        filter_pids = set(str(p) for p in pids) if pids is not None else None
        result = make_plot_figure(self.data_dic, action_name,
                                  self.current_time_start, self.current_time_end,
                                  filter_pids)

        if isinstance(result, tuple):
            QtWidgets.QMessageBox.information(self, result[0], result[1])
            # 出错，取消勾选
            self._sync_check_from_action(action_name, False)
            return

        fig = result
        ax = fig.axes[0] if fig.axes else None
        canvas = FigureCanvas(fig)
        toolbar = NavigationToolbar(canvas, self.centralwidget)
        tab_content = QtWidgets.QWidget()
        tab_layout = QtWidgets.QVBoxLayout(tab_content)
        tab_layout.addWidget(toolbar)
        tab_layout.addWidget(canvas)
        tab_content.setLayout(tab_layout)
        tab_index = self.tab_widget.addTab(tab_content, action_name)
        self.action_tab_map[action_name] = tab_index
        self.tab_widget.setCurrentIndex(tab_index)

        # 保存图信息用于后续动态更新
        lines = {}  # {pid: line}
        if ax is not None:
            for line in ax.get_lines():
                label = line.get_label()
                # label 格式是 proc_pid
                parts = label.rsplit('_', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    lines[parts[1]] = line
                else:
                    lines[label] = line

        self.fig_objects[action_name] = {
            'fig': fig,
            'ax': ax,
            'canvas': canvas,
            'lines': lines,
            'color_idx': len(lines),
        }

    def _update_plot_pids(self, action_name, new_pids):
        """在原图上动态增删PID曲线，不重建图
        action_name: 指标图名
        new_pids: 新的选中PID集合
        """
        if action_name not in self.fig_objects:
            return
        info = self.fig_objects[action_name]
        ax = info['ax']
        canvas = info['canvas']
        lines = info['lines']

        new_pid_set = set(str(p) for p in new_pids)
        current_pid_set = set(lines.keys())

        # 需要删除的PID
        pids_to_remove = current_pid_set - new_pid_set
        for pid in pids_to_remove:
            line = lines.pop(pid, None)
            if line is not None:
                line.remove()

        # 需要新增的PID
        pids_to_add = new_pid_set - current_pid_set

        if not pids_to_add and not pids_to_remove:
            return

        # 新增的在主线程直接从 data_dic 取数据画线
        # 数据量不大（已降采样），直接画不会卡
        parts = action_name.rsplit('-', 1)
        if len(parts) != 2:
            return
        proc_name = parts[0]
        ind_name = parts[1]

        df = self.data_dic.get(proc_name)
        if df is None or len(df) == 0 or ind_name not in df.columns:
            return

        time_col = None
        for c in df.columns:
            if '时间' in c:
                time_col = c
                break
        if time_col is None:
            return

        import matplotlib.cm as cm
        colors = cm.tab10.colors

        # 移除空图提示文字（如果存在）
        if not current_pid_set and pids_to_add:
            for text in list(ax.texts):
                if text.get_text() == "请在左侧勾选要查看的 PID":
                    text.remove()

        for pid in sorted(pids_to_add):
            if '_pid' in df.columns:
                group = df[df['_pid'] == pid]
            else:
                group = df
            if len(group) == 0:
                continue
            ts = group[time_col]
            vs = group[ind_name]

            # 时间过滤
            if self.current_time_start:
                mask = ts >= pd.Timestamp(self.current_time_start)
                ts = ts[mask]
                vs = vs[mask]
            if self.current_time_end:
                mask = ts <= pd.Timestamp(self.current_time_end)
                ts = ts[mask]
                vs = vs[mask]

            if len(ts) == 0:
                continue

            # 降采样
            max_points = 5000
            if len(ts) > max_points:
                step = max(1, len(ts) // max_points)
                ts = ts.iloc[::step]
                vs = vs.iloc[::step]

            label = f"{proc_name}_{pid}"
            color = colors[info['color_idx'] % len(colors)]
            info['color_idx'] += 1
            line, = ax.plot(ts.values, vs.values, label=label, color=color)
            line.set_picker(True)
            line.set_pickradius(10)
            lines[pid] = line

        # 更新图例
        if lines:
            # 如果是从空变有，重新建图例；否则更新图例
            line_list = list(lines.values())
            if len(line_list) <= 20:
                legend = ax.legend()
            else:
                legend = ax.legend(ncol=min(4, len(line_list)//10 + 1), fontsize=7)
            legend.set_draggable(True)
            for leg_line, leg_text in zip(legend.get_lines(), legend.get_texts()):
                leg_line.set_picker(True)
                leg_text.set_picker(True)
        else:
            # 全部删光了，显示提示
            ax.text(0.5, 0.5, "请在左侧勾选要查看的 PID",
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=14, color='#999')
            if ax.get_legend():
                ax.get_legend().remove()

        # 自动调整坐标轴范围
        ax.relim()
        ax.autoscale_view()
        canvas.draw_idle()

    def _sync_check_from_action(self, action_name, checked):
        """根据 action_name 同步树节点勾选状态 + 更新 selected_indicators"""
        parts = action_name.rsplit('-', 1)
        if len(parts) != 2:
            return
        proc_name = parts[0]
        ind_name = parts[1]

        # 更新选中状态
        if proc_name not in self.selected_indicators:
            self.selected_indicators[proc_name] = set()
        if checked:
            self.selected_indicators[proc_name].add(ind_name)
        else:
            self.selected_indicators[proc_name].discard(ind_name)

        self._updating_tree = True

        def find_and_set(item):
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not data:
                for i in range(item.childCount()):
                    if find_and_set(item.child(i)):
                        return True
                return False
            node_type = data[0]
            if node_type == 'indicator' and data[1] == proc_name and data[2] == ind_name:
                item.setCheckState(0, QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
                if item.parent():
                    self._update_process_check_state(item.parent())
                return True
            for i in range(item.childCount()):
                if find_and_set(item.child(i)):
                    return True
            return False

        for i in range(self.tree_widget.topLevelItemCount()):
            if find_and_set(self.tree_widget.topLevelItem(i)):
                break
        self._updating_tree = False

    def remove_plot_tab(self, action_name):
        if action_name not in self.action_tab_map:
            return
        tab_index = self.action_tab_map[action_name]
        self.tab_widget.removeTab(tab_index)
        del self.action_tab_map[action_name]
        # 清理图对象
        if action_name in self.fig_objects:
            info = self.fig_objects.pop(action_name)
            import matplotlib.pyplot as plt
            try:
                plt.close(info['fig'])
            except Exception:
                pass
        new_map = {}
        for name, idx in self.action_tab_map.items():
            new_map[name] = idx - 1 if idx > tab_index else idx
        self.action_tab_map = new_map

    def on_tab_close_requested(self, tab_index):
        action_name = None
        for name, idx in self.action_tab_map.items():
            if idx == tab_index:
                action_name = name
                break
        if action_name is not None:
            self.remove_plot_tab(action_name)
            self._sync_check_from_action(action_name, False)

    def _update_global_time_range(self):
        """计算所有已加载数据的最早/最晚时间"""
        min_time = None
        max_time = None
        for key, df in self.data_dic.items():
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
            ts = df[time_col]
            if len(ts) == 0:
                continue
            t_min = ts.min()
            t_max = ts.max()
            if min_time is None or t_min < min_time:
                min_time = t_min
            if max_time is None or t_max > max_time:
                max_time = t_max

        if min_time is not None and max_time is not None:
            self.global_min_time = min_time
            self.global_max_time = max_time
            if isinstance(min_time, pd.Timestamp):
                qt_min = QtCore.QDateTime(min_time.year, min_time.month, min_time.day,
                                           min_time.hour, min_time.minute, min_time.second)
                qt_max = QtCore.QDateTime(max_time.year, max_time.month, max_time.day,
                                           max_time.hour, max_time.minute, max_time.second)
            else:
                qt_min = QtCore.QDateTime(min_time)
                qt_max = QtCore.QDateTime(max_time)
            self.start_dateTimeEdit.setDateTime(qt_min)
            self.end_dateTimeEdit.setDateTime(qt_max)
            self.current_time_start = min_time.strftime('%Y-%m-%d %H:%M:%S')
            self.current_time_end = max_time.strftime('%Y-%m-%d %H:%M:%S')

    def apply_time_filter(self):
        start_dt = self.start_dateTimeEdit.dateTime().toPyDateTime()
        end_dt = self.end_dateTimeEdit.dateTime().toPyDateTime()
        if start_dt > end_dt:
            QtWidgets.QMessageBox.warning(self, "提示", "开始时间不能晚于结束时间")
            return
        self.current_time_start = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        self.current_time_end = end_dt.strftime('%Y-%m-%d %H:%M:%S')

        actions_to_redraw = list(self.action_tab_map.keys())
        if not actions_to_redraw:
            return
        for action_name in list(actions_to_redraw):
            self.remove_plot_tab(action_name)
        for action_name in actions_to_redraw:
            self._draw_indicator(action_name)

    def reset_time_filter(self):
        if self.global_min_time and self.global_max_time:
            if isinstance(self.global_min_time, pd.Timestamp):
                qt_min = QtCore.QDateTime(self.global_min_time.year, self.global_min_time.month,
                                           self.global_min_time.day, self.global_min_time.hour,
                                           self.global_min_time.minute, self.global_min_time.second)
                qt_max = QtCore.QDateTime(self.global_max_time.year, self.global_max_time.month,
                                           self.global_max_time.day, self.global_max_time.hour,
                                           self.global_max_time.minute, self.global_max_time.second)
            else:
                qt_min = QtCore.QDateTime(self.global_min_time)
                qt_max = QtCore.QDateTime(self.global_max_time)
            self.start_dateTimeEdit.setDateTime(qt_min)
            self.end_dateTimeEdit.setDateTime(qt_max)
            self.current_time_start = self.global_min_time.strftime('%Y-%m-%d %H:%M:%S')
            self.current_time_end = self.global_max_time.strftime('%Y-%m-%d %H:%M:%S')
            if self.action_tab_map:
                self.apply_time_filter()

    def on_load_other_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择监控数据文件夹", self.data_path)
        if not folder:
            return
        self._switch_data_source(folder)

    def _switch_data_source(self, new_path):
        for action_name in list(self.action_tab_map.keys()):
            self.remove_plot_tab(action_name)
        for key in list(self.threads.keys()):
            try:
                self.threads[key].requestInterruption()
            except Exception:
                pass

        self.data_path = new_path
        self.path_label.setText(f"数据源：{new_path}")
        self.data_dic = {}
        self.loaded_processes = set()
        self.current_time_start = None
        self.current_time_end = None
        self.global_min_time = None
        self.global_max_time = None
        for w in self._filter_widgets:
            w.setEnabled(False)

        self._scan_files()
        self._build_tree()

    def on_update_data(self):
        if self.server_config is None:
            return

        if os.path.normpath(self.data_path) != os.path.normpath(self.original_data_path):
            QtWidgets.QMessageBox.information(
                self, "提示",
                "当前数据源不是服务器的监控目录，无法更新数据。\n"
                "如需更新，请先切换回原始数据源。"
            )
            return

        if not self._is_ssh_connected():
            QtWidgets.QMessageBox.information(self, "提示", "服务器未连接，无法更新数据")
            return

        from utils import ssh_tools
        from utils import qthread_worker

        cfg = self.server_config
        ip = cfg.get('IP')
        port = cfg.get('端口')
        username = cfg.get('用户名')
        password = cfg.get('密码')
        work_dir = cfg.get('文件暂存路径')
        user_path = f"{work_dir}/OneClick/Monitor"

        ssh_client = ssh_tools.SSHTools()
        ssh_client.ip = ip
        ssh_client.port = port
        ssh_client.username = username
        ssh_client.password = password

        progress_dialog = QtWidgets.QProgressDialog("正在检查更新...", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("更新数据")
        progress_dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setAutoClose(True)
        progress_dialog.setAutoReset(True)
        progress_dialog.show()

        def do_update():
            connect_result = ssh_client.connect()
            if not connect_result:
                return (False, "连接服务器失败")
            try:
                local_files = {}
                if os.path.isdir(self.data_path):
                    for f in os.listdir(self.data_path):
                        if f.endswith('.log'):
                            fp = os.path.join(self.data_path, f)
                            try:
                                local_files[f] = os.path.getsize(fp)
                            except OSError:
                                pass

                stdin, stdout, stderr = ssh_client.ssh.exec_command(
                    f"ls -l {user_path}/*.log 2>/dev/null | awk '{{print $NF, $5}}'"
                )
                server_files = {}
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        fname = os.path.basename(parts[0])
                        try:
                            fsize = int(parts[1])
                            server_files[fname] = fsize
                        except ValueError:
                            pass
                stderr.read()

                to_download = []
                for fname, ssize in server_files.items():
                    lsize = local_files.get(fname)
                    if lsize is None or lsize != ssize:
                        to_download.append(fname)

                if not to_download:
                    ssh_client.disconnect()
                    return (True, "已是最新，无需更新")

                os.makedirs(self.data_path, exist_ok=True)

                total = len(to_download)
                for idx, fname in enumerate(to_download):
                    remote_file = f"{user_path}/{fname}"
                    local_file = os.path.join(self.data_path, fname)
                    try:
                        worker_obj.info_signal.emit(('download', idx, total, fname))
                    except Exception:
                        pass
                    try:
                        sftp = ssh_client.ssh.open_sftp()
                        sftp.get(remote_file, local_file)
                        sftp.close()
                    except Exception as e:
                        ssh_client.disconnect()
                        return (False, f"下载{fname}失败：{e}")

                ssh_client.disconnect()
                return (True, f"已更新 {len(to_download)} 个文件")

            except Exception as e:
                try:
                    ssh_client.disconnect()
                except Exception:
                    pass
                return (False, f"{e}")

        worker_obj = qthread_worker.OneClickWorker(do_update)
        thread_obj = QtCore.QThread()
        worker_obj.moveToThread(thread_obj)

        def on_info(data):
            if isinstance(data, tuple) and len(data) >= 1 and data[0] == 'download':
                _, idx, total, fname = data
                def _update():
                    progress_dialog.setRange(0, total)
                    progress_dialog.setValue(idx)
                    progress_dialog.setLabelText(f"下载中... {idx + 1}/{total}\n{fname}")
                QtCore.QTimer.singleShot(0, _update)

        def on_finished(result):
            def _update():
                progress_dialog.close()
                success, msg = result
                if success:
                    self._refresh_after_update()
                    QtWidgets.QMessageBox.information(self, "提示", msg)
                else:
                    QtWidgets.QMessageBox.warning(self, "提示", msg)
                thread_obj.quit()
            QtCore.QTimer.singleShot(0, _update)

        worker_obj.info_signal.connect(on_info)
        worker_obj.finished.connect(on_finished)
        worker_obj.finished.connect(worker_obj.deleteLater)
        thread_obj.finished.connect(thread_obj.deleteLater)
        thread_obj.started.connect(worker_obj.run_task)

        self._update_worker = worker_obj
        self._update_thread = thread_obj
        thread_obj.start()

    def _refresh_after_update(self):
        # 先保存当前选中状态
        saved_indicators = dict(self.selected_indicators)
        saved_pids = dict(self.selected_pids)
        saved_tabs = list(self.action_tab_map.keys())

        self.data_dic = {}
        self.loaded_processes = set()
        self.global_min_time = None
        self.global_max_time = None

        self._scan_files()
        self._build_tree()

        # 恢复选中状态
        self.selected_indicators = saved_indicators
        self.selected_pids = saved_pids

        # 重新加载之前打开的进程数据
        procs_to_load = set()
        for action_name in saved_tabs:
            parts = action_name.rsplit('-', 1)
            if len(parts) == 2:
                procs_to_load.add(parts[0])
        for proc_name in procs_to_load:
            if proc_name in self.file_map:
                self._load_process_data(proc_name,
                                        on_finished=lambda ok, p=proc_name: self._redraw_proc_charts(p) if ok else None)

        # 恢复树节点勾选状态
        self._updating_tree = True
        for proc_name, inds in saved_indicators.items():
            proc_item = self.process_tree_items.get(proc_name)
            if not proc_item:
                continue
            for i in range(proc_item.childCount()):
                child = proc_item.child(i)
                child_data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not child_data or child_data[0] != 'indicator':
                    continue
                if child_data[2] in inds:
                    child.setCheckState(0, QtCore.Qt.CheckState.Checked)
            self._update_process_check_state(proc_item)

            # 恢复 PID 勾选
            pids = saved_pids.get(proc_name, set())
            if not pids:
                continue
            # 找到 PID 分组节点
            for i in range(proc_item.childCount()):
                child = proc_item.child(i)
                child_data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not child_data or child_data[0] != 'pid_group':
                    continue
                for j in range(child.childCount()):
                    pid_item = child.child(j)
                    pid_data = pid_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if pid_data and pid_data[0] == 'pid' and pid_data[2] in pids:
                        pid_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        self._updating_tree = False

    def _is_ssh_connected(self):
        if self.parent() and hasattr(self.parent(), 'ssh_stutas_label'):
            return self.parent().ssh_stutas_label.text() == '已连接'
        return True


if __name__ == '__main__':
    pass
