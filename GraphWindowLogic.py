from UI import GraphMainWindow
import os
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QMessageBox, QMainWindow

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt
from utils.graph_data_tools import Worker

plt.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体：黑体（Windows）
plt.rcParams['axes.unicode_minus'] = False    # 解决负号显示为方块的问题

class GraphWindow(QMainWindow, GraphMainWindow.Ui_MainWindow):
    def __init__(self, data_path, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.data_path = data_path
        self.data_dic = {} # 存储所有数据
        # 创建窗口的工作线程
        self.threads = {} # data_load: sys_fig:
        self.workers = {}

        # 创建标签页控件（用于显示多个绘图窗口）
        self.tab_widget = QtWidgets.QTabWidget(self.centralwidget)
        self.tab_widget.setObjectName("tab_widget")
        # 设置中心窗口的布局，将标签页放入
        central_layout = QtWidgets.QVBoxLayout(self.centralwidget)
        central_layout.addWidget(self.tab_widget)
        self.centralwidget.setLayout(central_layout)
        # 存储菜单项与标签页的映射（键：菜单项名称，值：标签页索引）
        self.action_tab_map = {}

        # 查找数据文件夹下的所有文件，返回文件名
        self.data_file_names = self.find_data_files()

        if self.data_file_names != []:
            # 加载数据
            self.start_loading()
        self.showMaximized()

    def find_data_files(self):
        # 查找数据源文件
        try:
            data_file_names = os.listdir(self.data_path)  # 检测到的可用数据源文件名
        except Exception as e:
            self.info_message(f"未找到监控数据{e}")
            return []

        filtered_names = [f for f in data_file_names if f.endswith('.log')]
        if len(filtered_names) == 0:
            self.info_message("监控数据文件夹无.log文件")
            return []
        else:
            return filtered_names

    def update_menubar(self):
        # 生成菜单栏内的选项
        class KeepOpenMenu(QtWidgets.QMenu):
            """使用该类创建菜单，防止选择某一项时菜单关闭"""
            def mouseReleaseEvent(self, event):
                action = self.actionAt(event.pos())
                if action and action.isCheckable():
                    action.toggle() # 手动切换勾选状态
                    # 手动发射triggered信号
                    action.triggered.emit(action.isChecked())
                    return
                super().mouseReleaseEvent(event)

        added_list = []
        service_names = list(self.data_dic.keys())
        if "系统" in service_names:
            service_names.remove("系统")
        # 将进程列表按名称长度由长到短排序，doubao.log,doubao_789.log优先处理长的
        service_names.sort(key=len, reverse=True)

        # 头部插入系统
        service_names.insert(0, "系统")

        # 获取系统二级菜单项
        sys_items = list(self.data_dic.get("系统", {}).keys())
        # 去除掉含有“时间”的项目
        sys_items = [item for item in sys_items if "时间" not in item]

        proc_name = next((k for k in self.data_dic if k != "系统"), None)
        if proc_name is not None:
            proc_items = list(self.data_dic[proc_name].keys())
            proc_items = [item for item in proc_items if "时间" not in item]
        else:
            proc_items = []

        for menu in service_names: # [系统,top_123.log,top_443.log,nms_567.log,top.log]
            if menu in added_list:
                continue
            # 因为一个进程名只生成一个菜单栏，所以判断proc_full_name是否已经在了，比如先处理了top_123，进程取了top,其他top开头的不需要处理了
            # 或者有的进程自带下划线pdt_gui_123已经处理了，pdt_gui就不再处理了
            if '_' in menu:
                # 找到最后一个下划线的位置
                last_underscore_index = menu.rfind('_')
                # 截取到最后一个下划线之前的部分
                menu_name = menu[:last_underscore_index]
                # 没有下划线则返回原值
            else:
                menu_name = menu

            if menu_name in added_list:
                continue
            added_list.append(menu_name)

            first_menu = KeepOpenMenu(f"{menu_name}", self)

            # 给一级菜单添加二级选项 绑定触发信号
            if menu_name == "系统":
                for item in sys_items:
                    action = QtWidgets.QAction(item, self, checkable=True)
                    action.triggered.connect(lambda checked, name=f"系统-{item}": self.on_menu_action_triggered(checked, name))
                    first_menu.addAction(action)
            else:
                for item in proc_items:
                    action = QtWidgets.QAction(item, self, checkable=True)
                    action.triggered.connect(lambda checked, name=f"{menu_name}-{item}": self.on_menu_action_triggered(checked, name))
                    first_menu.addAction(action)
            self.menu.addMenu(first_menu)

    def create_progress_dialog(self):
        # 创建进度条
        progress_dialog = QtWidgets.QProgressDialog(self)
        progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress_dialog.setRange(0, 100)
        progress_dialog.setCancelButtonText("取消")
        progress_dialog.setValue(0)
        # 禁用所有自动行为，完全手动控制
        progress_dialog.setMinimumDuration(0)  # 禁用自动弹出
        progress_dialog.setAutoReset(False)  # 禁止自动重置进度
        progress_dialog.setAutoClose(False)  # 禁止自动关闭窗口
        progress_dialog.hide()  # 强制初始隐藏
        return progress_dialog

    def info_message(self, message):
        """显示信息对话框"""
        QtWidgets.QMessageBox.information(self, "提示", message)

    def start_loading(self):
        """开始加载数据"""
        self.menu.setEnabled(False)

        # 创建工作对象
        data_file_paths = []
        for n in self.data_file_names:
            data_file_paths.append(self.data_path + "/" + n)
        worker = Worker(data_file_paths)
        self.workers['数据读取'] = worker

        # 创建并启动工作线程
        thread = QtCore.QThread()
        self.threads['数据读取'] = thread

        # 将工作对象放到线程
        worker.moveToThread(thread)

        # 显示进度对话框
        progress_dialog = self.create_progress_dialog()
        progress_dialog.setWindowTitle("数据读取")
        progress_dialog.show()

        def on_data_canceled():
            progress_dialog.close()
            worker.deleteLater()
            thread.quit()
            self.threads.pop('数据读取')
            self.workers.pop('数据读取')


        def on_data_finished(data=None):
            """数据加载完毕后"""
            self.menu.setEnabled(True)
            progress_dialog.setLabelText("读取完成，请在菜单栏选择数据绘图")
            progress_dialog.setCancelButtonText("确定")
            # 完成后断开取消信号，点按钮也不会触发取消逻辑，只会关闭对话框
            progress_dialog.canceled.disconnect()
            progress_dialog.canceled.connect(progress_dialog.close)
            progress_dialog.setValue(100)  # 确保进度条到100%
            self.data_dic = data
            worker.deleteLater()
            thread.quit()
            self.threads.pop('数据读取')
            self.workers.pop('数据读取')

        # 设置信号连接
        worker.progress.connect(progress_dialog.setValue)
        worker.message.connect(progress_dialog.setLabelText)
        worker.canceled.connect(on_data_canceled)
        worker.finished.connect(on_data_finished)

        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.update_menubar)
        thread.started.connect(worker.data_process)

        # 点击取消按钮时，请求线程中断
        progress_dialog.canceled.connect(thread.requestInterruption)

        thread.start()

    def on_menu_action_triggered(self, checked, action_name):
        """
        菜单选项勾选/取消勾选的处理函数
        :param checked: 是否勾选（True/False）
        :param action_name: 菜单项名称（如"系统-内存"、"top-CPU"）
        """
        if checked:
            # self.data_dic={"系统"：{"系统时间":[],"已用内存":[],"CPU使用率%":[]...},"top_123"：{}}
            data_for_fig = [self.data_dic, action_name]
            # 勾选状态：创建绘图工作对象和线程
            worker = Worker(data_for_fig)
            thread = QtCore.QThread()
            self.workers[action_name] = worker
            self.threads[action_name] = thread

            # 将工作对象放到线程
            worker.moveToThread(thread)

            # 显示进度对话框
            progress_dialog = self.create_progress_dialog()
            progress_dialog.setWindowTitle(f"绘图<{action_name}>")
            progress_dialog.show()

            action = self.sender()

            def on_fig_canceled():
                progress_dialog.close()
                action.setChecked(False)
                worker.deleteLater()
                thread.quit()
                self.threads.pop(action_name)
                self.workers.pop(action_name)

            def on_fig_finished(data):
                """绘图完成后"""
                if isinstance(data, tuple):
                    QMessageBox.information(self, data[0], data[1])
                    progress_dialog.setLabelText(f"{action_name}绘图出错！")
                    progress_dialog.setCancelButtonText("确定")
                    # 完成后断开取消信号，点按钮也不会触发取消逻辑，只会关闭对话框
                    progress_dialog.canceled.disconnect()
                    progress_dialog.canceled.connect(progress_dialog.close)
                    progress_dialog.setValue(100)  # 确保进度条到100%
                    action.setChecked(False)
                    worker.deleteLater()
                    thread.quit()
                    self.threads.pop(action_name)
                    self.workers.pop(action_name)
                    return
                progress_dialog.setLabelText(f"{action_name}正在渲染图表...")
                # 封装matplotlib画布到PyQt控件
                # 创建画布控件（嵌入PyQt）
                canvas = FigureCanvas(data)

                # 创建绘图工具栏（支持缩放、平移、保存等操作）
                toolbar = NavigationToolbar(canvas, self.centralwidget)

                # 创建标签页控件并布局
                tab_content = QtWidgets.QWidget()
                tab_layout = QtWidgets.QVBoxLayout(tab_content)
                tab_layout.addWidget(toolbar)  # 添加工具栏（缩放功能）
                tab_layout.addWidget(canvas)  # 添加绘图画布
                tab_content.setLayout(tab_layout)

                # 添加标签页到主标签控件，并记录映射关系
                tab_index = self.tab_widget.addTab(tab_content, action_name)
                self.action_tab_map[action_name] = tab_index

                progress_dialog.setLabelText(f"{action_name}绘图完成！")
                progress_dialog.setCancelButtonText("确定")
                # 完成后断开取消信号，点按钮也不会触发取消逻辑，只会关闭对话框
                progress_dialog.canceled.disconnect()
                progress_dialog.canceled.connect(progress_dialog.close)
                progress_dialog.setValue(100)  # 确保进度条到100%
                worker.deleteLater()
                thread.quit()
                self.threads.pop(action_name)
                self.workers.pop(action_name)

            # 设置信号连接
            worker.progress.connect(progress_dialog.setValue)
            worker.message.connect(progress_dialog.setLabelText)
            worker.canceled.connect(on_fig_canceled)

            worker.finished.connect(on_fig_finished)

            thread.finished.connect(thread.deleteLater)
            thread.started.connect(worker.create_plot_tab)

            # 点击取消按钮时，请求线程中断
            progress_dialog.canceled.connect(thread.requestInterruption)

            thread.start()
        else:
            # 取消勾选：删除对应的绘图标签页
            self.remove_plot_tab(action_name)

    def remove_plot_tab(self, action_name):
        """
        根据菜单项名称删除对应的绘图标签页
        :param action_name: 菜单项名称（如"系统-内存"、"top-CPU"）
        """
        # 1. 检查映射关系是否存在
        if action_name not in self.action_tab_map:
            return

        # 2. 获取标签页索引并删除
        tab_index = self.action_tab_map[action_name]
        self.tab_widget.removeTab(tab_index)

        # 3. 删除映射关系，并修正剩余标签页的索引（避免索引错乱）
        del self.action_tab_map[action_name]
        # 重新更新映射表中的索引
        new_action_tab_map = {}
        for name, idx in self.action_tab_map.items():
            if idx > tab_index:
                new_action_tab_map[name] = idx - 1
            else:
                new_action_tab_map[name] = idx
        self.action_tab_map = new_action_tab_map

if __name__ == '__main__':
    pass
