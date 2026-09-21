import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtWidgets import (QDialog, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
                             QMenu, QFileDialog, QMessageBox, QMainWindow,
                             QTabWidget, QCheckBox, QScrollArea, QInputDialog, QLineEdit)

from UI import MainWindow
from utils import ssh_tools, windows_tools, qthread_worker
import json
import datetime
from utils.logger import setup_logging, get_logger, log_progress
from dialogs import (SendCMDDialog, SendCMD2Dialog, SendFilesDialog, GetFilesDialog, CopyFilesDialog,
                     SetServerDialog, ResourceMonitorDialog1, ResourceMonitorDialog2,
                     WeakNetDialog1, WeakNetControlDialog, HelpDialog, ServerCheckDialog,
                     ServerCheckRunDialog, CmdManageDialog)
from widgets.terminal_widget import TerminalEdit


class DraggableButton(QPushButton):
    """可拖动的按钮类，支持长按拖动改变位置"""
    dragStarted = QtCore.pyqtSignal()  # 拖动开始信号
    dragMoved = QtCore.pyqtSignal(QtCore.QPoint)  # 拖动中信号，传入全局位置
    dragEnded = QtCore.pyqtSignal()  # 拖动结束信号

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._isDragging = False
        self._dragStartPos = QtCore.QPoint()
        self._longPressTimer = QTimer(self)
        self._longPressTimer.setInterval(300)  # 300ms长按触发
        self._longPressTimer.setSingleShot(True)
        self._longPressTimer.timeout.connect(self._startDrag)
        self._dragIndicator = None  # 拖动时的指示器

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragStartPos = event.pos()
            self._longPressTimer.start()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._isDragging:
            # 拖动中，发送位置信号
            self.dragMoved.emit(self.mapToGlobal(event.pos()))
        else:
            # 如果移动超过一定距离，取消长按检测
            if (event.pos() - self._dragStartPos).manhattanLength() > 10:
                self._longPressTimer.stop()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._longPressTimer.stop()
        if self._isDragging:
            self._isDragging = False
            self.dragEnded.emit()
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _startDrag(self):
        """开始拖动"""
        self._isDragging = True
        self.dragStarted.emit()
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)


class MainWindowLogic(QMainWindow, MainWindow.Ui_MainWindow):
    """继承两个父类，QMainWindow用于作为参数传入MainWindow.Ui_MainWindow"""
    def __init__(self, parent=None):
        super().__init__(parent) # 调用父类QMainWindow，实例化了self为QMainWindow
        self.setupUi(self) # 现在self是个窗口，self直接调用，相当于MainWindow.Ui_MainWindow的setupUi

        # 设置窗口图标（任务栏和标题栏显示）
        import os
        import sys
        from PyQt5.QtGui import QIcon
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后：优先 exe 同目录，其次打包进 exe 的资源
            icon_path = os.path.join(os.path.dirname(sys.executable), "app.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(sys._MEIPASS, "app.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 启动模块后台预加载（不阻塞主界面显示）
        from utils.module_loader import ModuleLoader
        ModuleLoader.instance().set_main_window(self)
        ModuleLoader.instance().start_preload()

        # 创建菜单栏选项与弹出的编辑窗口关系
        self.send_cmd_action.triggered.connect(self.cmd1_dialog)  # 发送cmd的编辑框
        self.send_cmd2_action.triggered.connect(self.cmd2_dialog)  # 发送cmd并接收回显的编辑框
        self.send_file_action.triggered.connect(self.send_file_dialog)  # 发送文件的编辑框
        self.get_file_action.triggered.connect(self.get_file_dialog)  # 获取文件的编辑框
        self.copy_local_action.triggered.connect(self.copy_file_dialog)  # 复制本地文件编辑框
        self.resource_monitor_action.triggered.connect(self.resource_monitor_dialog)  # 资源监控编辑框
        self.weak_net_action.triggered.connect(self.weak_net_dialog)  # 弱网编辑框
        self.get_sc_from_cfg_action.triggered.connect(self.load_sc_config)  # 从配置文件获取快捷按钮
        
        # 添加服务器检查菜单项，放到弱网下面
        from PyQt5.QtWidgets import QAction
        self.server_check_action = QAction("服务器检查", self)
        # 找到弱网action在菜单中的位置，然后插入在它后面
        actions = self.menu.actions()
        weak_net_idx = -1
        for i, action in enumerate(actions):
            if action == self.weak_net_action:
                weak_net_idx = i
                break
        if weak_net_idx != -1:
            self.menu.insertAction(actions[weak_net_idx + 1], self.server_check_action)
        else:
            self.menu.addAction(self.server_check_action)
        self.server_check_action.triggered.connect(self.server_check_dialog)

        self.edit_server_action.triggered.connect(self.server_cfg_dialog)  # 服务器列表的编辑框
        self.get_server_from_cfg_action.triggered.connect(self.load_server_config)  # 从配置文件获取服务器

        self.save_action.triggered.connect(self.save_config)  # 保存配置到当前配置文件
        self.save_to_action_2.triggered.connect(self.save_config_to)  # 另存为配置到文件夹
        self.help_action.triggered.connect(self.show_help_dialog)  # 显示帮助文档
        # 创建按钮逻辑
        self.stop_pushButton.clicked.connect(self.stop_sc)
        self.clean_pushButton.clicked.connect(self.clean_linux_print)

        # ---- 替换 scrollArea_2 为 QTabWidget（分组标签页） ----
        self.group_tabWidget = QTabWidget(self.centralwidget)
        self.group_tabWidget.setTabsClosable(True)
        self.group_tabWidget.tabCloseRequested.connect(self.on_tab_close_requested)
        self.group_tabWidget.tabBarDoubleClicked.connect(self.on_tab_bar_double_clicked)
        # 标签栏右键菜单
        self.group_tabWidget.tabBar().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_tabWidget.tabBar().customContextMenuRequested.connect(self.on_tab_bar_context_menu)
        # 左上角"+"新建分组按钮（标签页最前面），紧贴标签无间隙
        self.add_group_btn = QPushButton("+", self.centralwidget)
        self.add_group_btn.setFixedSize(24, 24)
        self.add_group_btn.setToolTip("新建分组")
        self.add_group_btn.clicked.connect(self.add_new_group)
        self.group_tabWidget.setCornerWidget(self.add_group_btn, QtCore.Qt.Corner.TopLeftCorner)
        # 消除corner widget与tab之间的间隙
        self.group_tabWidget.tabBar().setStyleSheet("QTabBar { qproperty-usesScrollButtons: 1; }")
        # 替换布局中的 scrollArea_2
        idx_scroll = self.verticalLayout.indexOf(self.scrollArea_2)
        self.verticalLayout.removeWidget(self.scrollArea_2)
        self.scrollArea_2.deleteLater()
        self.verticalLayout.insertWidget(idx_scroll, self.group_tabWidget)

        # ---- 在"结束所有"按钮旁边添加"开始所有"按钮，大小保持一致 ----
        self.execute_all_btn = QPushButton("开始所有", self.centralwidget)
        self.execute_all_btn.clicked.connect(self.execute_all_buttons)
        # 统一两个按钮的大小：取两个按钮sizeHint的最大值作为固定宽度
        from PyQt5.QtWidgets import QSizePolicy
        w1 = self.stop_pushButton.fontMetrics().boundingRect("结束所有").width() + 20
        w2 = self.execute_all_btn.fontMetrics().boundingRect("开始所有").width() + 20
        fixed_w = max(w1, w2, 80)
        self.stop_pushButton.setFixedWidth(fixed_w)
        self.execute_all_btn.setFixedWidth(fixed_w)
        self.stop_pushButton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.execute_all_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # horizontalLayout 中 stop_pushButton 在 index 2，在它前面插入
        self.horizontalLayout.insertWidget(2, self.execute_all_btn)

        # ---- 分组管理 ----
        # _groups: {'分组名': {'tab_index':, 'buttons': [button_id,...], 'scroll_area':, 'button_container':, 'button_layout':, 'select_all_btn':, 'execute_selected_btn':, 'stop_group_btn':}}
        self._groups = {}
        self._group_order = []  # 分组顺序

        # 拖动相关的变量
        self._drag_button = None        # 当前正在拖动的按钮(DraggableButton)
        self._drag_container = None     # 拖动按钮的容器(QWidget)
        self._drag_indicator = None     # 拖动位置指示线
        self._drag_group_name = None    # 拖动所在的分组名

        # 将所有快捷方式存储到字典里,由于button_id唯一，因此用字典
        self.sc_buttons = {}  # {'button_id': {'widget':容器, 'button':DraggableButton, 'checkbox':QCheckBox, 'config':config, 'group':分组名}}
        self.btn_count = 0

        # 将运行中的指令线程存入字典
        self.sc_threads = {}
        self.thread_count = 0
        self.timer = None

        # 用于存放服务器配置信息的列表
        self.servers_cfg = []  # [{"服务器名称": ,"IP": ,"端口": ,"用户名": ,"密码": },...]

        # 连接ssh按钮逻辑
        self.connect_pushButton.clicked.connect(self.connect_server)
        self.current_ssh = {}  # 'config':{"服务器名称": ,"IP": ...},'ssh':,'receive_thread':,

        # 发送指令、保存指令、删除指令按钮逻辑
        self.commands = []
        # 配置文件的默认路径
        self.default_config_path = self.get_default_path() + '/' + 'config.json'

        # 日志系统：OneClick.py 入口已统一初始化好，这里直接连接 Qt 信号
        # setup_logging() 内部有防重复调用保护，这里再调一次只是为了拿到 emitter
        from utils.logger import setup_logging, get_logger, set_file_logging, set_file_log_level, is_file_logging_enabled, log_progress
        import logging as _logging
        self._log_emitter = setup_logging()  # OneClick.py 已初始化，返回已有的 emitter
        self.logger = get_logger("MainWindow")

        # 连接 Qt 日志信号（所有模块的 logger.info() 都会自动到这里）
        if self._log_emitter is not None:
            self._log_emitter.log_signal.connect(self._on_qt_log_message)
            self._log_emitter.progress_signal.connect(self._on_qt_progress)

        # 从配置文件读取初始状态
        self._log_level_config = {
            'DEBUG': _logging.DEBUG,
            'INFO': _logging.INFO,
            'WARNING': _logging.WARNING,
            'ERROR': _logging.ERROR,
        }
        initial_log_enabled = is_file_logging_enabled()
        if os.path.exists(self.default_config_path):
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    import json
                    cfg_data = json.load(f)
                    if '日志配置' in cfg_data:
                        initial_log_enabled = cfg_data['日志配置'].get('文件日志', True)
                        # 读取日志级别配置（整数：DEBUG=10, INFO=20, ...）
                        for level_name in self._log_level_config:
                            if level_name in cfg_data['日志配置']:
                                self._log_level_config[level_name] = cfg_data['日志配置'][level_name]
            except Exception:
                pass

        # 应用配置到 logger
        set_file_logging(initial_log_enabled)
        # 找到配置中最小的级别（比如只开 INFO+WARNING+ERROR 那就是 INFO=20）
        active_levels = [v for v in self._log_level_config.values() if isinstance(v, int)]
        if active_levels:
            set_file_log_level(min(active_levels))

        # 勾选框：现在只做开关日志的触发
        self.log_file_checkBox.stateChanged.connect(set_file_logging)
        self.log_file_checkBox.setChecked(initial_log_enabled)

        # ---- 三列布局改造：按钮区 | 文件区 | 终端区 ----
        # 用 QSplitter 水平分割，可拖动调整宽度
        from widgets.terminal_widget import TerminalEdit
        from widgets.file_browser_widget import FileBrowserWidget

        self.terminal_widget = TerminalEdit(self.centralwidget)
        self.file_browser = FileBrowserWidget(self.centralwidget)

        # 1. 左侧容器：快捷按钮（上）+ 运行信息（下），垂直 splitter
        self.left_container = QtWidgets.QWidget(self.centralwidget)
        left_layout = QtWidgets.QVBoxLayout(self.left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 把按钮区（原 verticalLayout）包进一个 QWidget
        self.gridLayout_2.removeItem(self.verticalLayout)
        self.left_top_widget = QtWidgets.QWidget(self.left_container)
        top_layout = QtWidgets.QVBoxLayout(self.left_top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addLayout(self.verticalLayout)

        # 把运行信息区（原 verticalLayout_3）包进一个 QWidget
        self.gridLayout_2.removeItem(self.verticalLayout_3)
        self.left_bottom_widget = QtWidgets.QWidget(self.left_container)
        bottom_layout = QtWidgets.QVBoxLayout(self.left_bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        bottom_layout.addLayout(self.verticalLayout_3)

        # 垂直 splitter 让两个区可拖动
        self.left_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.left_container)
        self.left_splitter.addWidget(self.left_top_widget)
        self.left_splitter.addWidget(self.left_bottom_widget)
        self.left_splitter.setStretchFactor(0, 4)
        self.left_splitter.setStretchFactor(1, 1)
        left_layout.addWidget(self.left_splitter)

        # 2. 右侧容器：终端区（上）+ 服务器选择行（下）
        self.right_column_widget = QtWidgets.QWidget(self.centralwidget)
        right_layout = QtWidgets.QVBoxLayout(self.right_column_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # 终端标题行（原 horizontalLayout_2）从 verticalLayout_2 取出
        self.verticalLayout_2.removeItem(self.horizontalLayout_2)
        # 旧回显区销毁
        self.verticalLayout_2.removeWidget(self.linux_print_browser)
        self.linux_print_browser.deleteLater()
        right_layout.addLayout(self.horizontalLayout_2)
        right_layout.addWidget(self.terminal_widget, 1)
        self.linux_print_browser = self.terminal_widget

        # 底部服务器选择行从 gridLayout_2 取出，放到右侧容器底部
        self.gridLayout_2.removeItem(self.gridLayout)
        right_layout.addLayout(self.gridLayout)

        # 3. 主 splitter：左 | 中 | 右
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.centralwidget)
        self.main_splitter.addWidget(self.left_container)
        self.main_splitter.addWidget(self.file_browser)
        self.main_splitter.addWidget(self.right_column_widget)
        self.main_splitter.setStretchFactor(0, 2)  # 按钮区
        self.main_splitter.setStretchFactor(1, 2)  # 文件区
        self.main_splitter.setStretchFactor(2, 3)  # 终端区

        # 4. 把 gridLayout_2 清空，只留主 splitter
        # 先移除 verticalLayout_2（已空）
        self.gridLayout_2.removeItem(self.verticalLayout_2)
        # 主 splitter 填满 gridLayout_2
        self.gridLayout_2.addWidget(self.main_splitter, 0, 0, 2, 2)

        # "服务器回显" 标签改为 "终端"
        self.linux_print_label.setText("终端")

        # ---- 统一四个区域标题样式：加粗 + 统一高度 ----
        title_style = "font-weight: bold; font-size: 13px; padding: 4px 0;"
        for lbl in (self.label, self.run_info_label, self.linux_print_label):
            lbl.setStyleSheet(title_style)
        # 远程文件标题也统一样式
        self.file_browser.set_title_style(title_style)

        # 终端按键发送信号
        self.terminal_widget.key_sent.connect(self._on_terminal_key)
        self.terminal_widget.paste_sent.connect(self._on_terminal_paste)

        # 文件浏览器信号
        self.file_browser.upload_requested.connect(self._fb_upload)
        self.file_browser.download_requested.connect(self._fb_download)

        # 指令管理按钮，放到连接按钮后面（第0行第3列）
        self.cmd_manage_button = QtWidgets.QPushButton("指令管理", self.centralwidget)
        self.cmd_manage_button.setObjectName("cmd_manage_button")
        self.cmd_manage_button.clicked.connect(self.open_cmd_manage_dialog)
        # 与连接按钮保持一致的高度和宽度
        self.cmd_manage_button.setMinimumWidth(120)
        self.connect_pushButton.setMinimumWidth(120)
        self.cmd_manage_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.connect_pushButton.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.gridLayout.addWidget(self.cmd_manage_button, 0, 3, 1, 1)

        # 如果有默认配置文件，则获取
        if os.path.exists(self.default_config_path):
            self.update_run_info('存在默认配置文件，开始添加服务器和快捷按钮')
            self.load_server_config(self.default_config_path)
            self.load_sc_config(self.default_config_path)

        # 如果没有任何分组，则创建默认分组
        if not self._groups:
            self.add_group_tab("默认分组")
        # 主界面服务器选择下拉表
        self.server_comboBox.setCurrentIndex(-1)
        self.update_server_combobox()
        self.update_run_info("OneClick 启动成功")

        # 延迟设置 splitter 初始比例：等窗口最大化、真实尺寸确定后再设
        QtCore.QTimer.singleShot(50, self._init_splitter_sizes)

    def _init_splitter_sizes(self):
        """窗口显示后设置 splitter 初始分配比例"""
        # 左侧垂直 splitter：按钮区 4/5，运行信息 1/5
        total_h = self.left_splitter.height()
        self.left_splitter.setSizes([int(total_h * 0.8), int(total_h * 0.2)])

    def cmd1_dialog(self, button_id=None):
        """创建发送指令的窗口实例"""
        s_cmd_dlg = SendCMDDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_cmd_dlg.setWindowTitle('编辑<发送命令>配置')
            s_cmd_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下’生成快捷按钮‘按钮时调用accpted()，主窗口打印日志
        if s_cmd_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑发送命令快捷按钮')
            else:
                self.update_run_info('取消创建发送命令快捷按钮')

    def cmd2_dialog(self, button_id=None):
        """创建发送指令的窗口实例"""
        s_cmd_dlg = SendCMD2Dialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_cmd_dlg.setWindowTitle('编辑<发送指令并接收回显>配置')
            s_cmd_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_cmd_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑发送命令并接收回显快捷按钮')
            else:
                self.update_run_info('取消创建发送命令并接收回显快捷按钮')

    def send_file_dialog(self, button_id=None):
        s_file_dlg = SendFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            s_file_dlg.setWindowTitle('编辑<发送文件>配置')
            s_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑发送文件快捷按钮')
            else:
                self.update_run_info('取消创建发送文件快捷按钮')

    def get_file_dialog(self, button_id=None):
        dialog = QDialog()
        g_file_dlg = GetFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            g_file_dlg.setWindowTitle('编辑<获取文件>配置')
            g_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if g_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑获取文件快捷按钮')
            else:
                self.update_run_info('取消创建获取文件快捷按钮')

    def copy_file_dialog(self, button_id=None):
        copy_file_dlg = CopyFilesDialog(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            copy_file_dlg.setWindowTitle('编辑<复制本地文件>配置')
            copy_file_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if copy_file_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑复制本地文件快捷按钮')
            else:
                self.update_run_info('取消创建复制本地文件快捷按钮')

    def resource_monitor_dialog(self, button_id=None):
        """创建资源监控的窗口实例"""
        r_monitor_dlg = ResourceMonitorDialog1(parent=self)
        if button_id:  # 以编辑模式打开时会传入button_id，以创建模式打开时不传参数，会自动传入False
            r_monitor_dlg.setWindowTitle('编辑<资源监控>配置')
            r_monitor_dlg.edit_sc(button_id)
        # 显示弹出窗口（模态显示，阻止操作主窗口）,按下'生成快捷按钮'按钮时调用accpted()，主窗口打印日志
        if r_monitor_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑资源监控快捷按钮')
            else:
                self.update_run_info('取消创建资源监控快捷按钮')

    def weak_net_dialog(self, button_id=None):
        """创建弱网的窗口实例"""
        w_net_dlg = WeakNetDialog1(parent=self)
        if button_id:
            w_net_dlg.setWindowTitle('编辑<弱网>配置')
            w_net_dlg.edit_sc(button_id)
        if w_net_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑弱网快捷按钮')
            else:
                self.update_run_info('取消创建弱网快捷按钮')

    def server_check_dialog(self, button_id=None):
        sc_dlg = ServerCheckDialog(parent=self)
        if button_id:
            sc_dlg.setWindowTitle('编辑<服务器检查>配置')
            sc_dlg.edit_sc(button_id)
        if sc_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_type = self.sc_buttons[button_id]["config"]["指令类型"]
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 快捷按钮编辑成功')
            else:
                if f"button_{self.btn_count}" in self.sc_buttons:
                    button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                    self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑服务器检查快捷按钮')
            else:
                self.update_run_info('取消创建服务器检查快捷按钮')

    def server_cfg_dialog(self):
        s_cfg_dlg = SetServerDialog(parent=self)
        # 显示弹出窗口（模态显示，阻止操作主窗口）
        if s_cfg_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            self.update_run_info('服务器列表编辑 成功')
        else:
            self.update_run_info('服务器列表编辑 取消')

    # ---- 按钮类型颜色映射（不含红色） ----
    BUTTON_COLOR_MAP = {
        '发送命令':         ('#4CAF50', '#45a049'),   # 绿色
        '发送命令并接收回显': ('#2196F3', '#1976D2'),   # 蓝色
        '发送文件':         ('#FF9800', '#F57C00'),   # 橙色
        '获取文件':         ('#9C27B0', '#7B1FA2'),   # 紫色
        '复制本地文件':     ('#607D8B', '#455A64'),   # 蓝灰色
        '资源监控':         ('#009688', '#00796B'),   # 青色
        '弱网':             ('#795548', '#5D4037'),   # 棕色
        '服务器检查':       ('#E91E63', '#C2185B'),   # 粉色
    }

    def get_button_style(self, cmd_type):
        """根据指令类型获取按钮样式"""
        bg, hover = self.BUTTON_COLOR_MAP.get(cmd_type, ('#4CAF50', '#45a049'))
        return f"""
            QPushButton {{
                padding: 10px;
                font-size: 14px;
                margin: 2px;
                border-radius: 5px;
                background-color: {bg};
                color: white;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {hover};
            }}
            QPushButton[executing="true"] {{
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #999999;
            }}
            QPushButton[executing="true"]:hover {{
                background-color: #cccccc;
            }}
        """

    def set_button_executing(self, button_id, is_executing):
        """设置按钮执行状态，不真正禁用按钮，只通过样式模拟"""
        if button_id in self.sc_buttons:
            button = self.sc_buttons[button_id]['button']
            button.setProperty('executing', is_executing)
            button.style().unpolish(button)
            button.style().polish(button)

    # ==================== 分组（标签页）管理 ====================

    def add_group_tab(self, group_name):
        """创建一个分组标签页，包含工具栏和按钮滚动区"""
        if group_name in self._groups:
            self.update_run_info(f'分组<{group_name}>已存在', 'WARNING')
            return
        # 创建标签页内容
        tab_page = QWidget()
        tab_layout = QVBoxLayout(tab_page)
        tab_layout.setContentsMargins(2, 2, 2, 2)
        tab_layout.setSpacing(2)

        # 工具栏：全选 / 执行选中 / 停止选中 / 删除选中
        toolbar = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedHeight(28)
        execute_selected_btn = QPushButton("执行选中")
        execute_selected_btn.setFixedHeight(28)
        stop_group_btn = QPushButton("停止选中")
        stop_group_btn.setFixedHeight(28)
        delete_selected_btn = QPushButton("删除选中")
        delete_selected_btn.setFixedHeight(28)
        toolbar.addWidget(select_all_btn)
        toolbar.addWidget(execute_selected_btn)
        toolbar.addWidget(stop_group_btn)
        toolbar.addWidget(delete_selected_btn)
        toolbar.addStretch()
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        tab_layout.addWidget(toolbar_widget)

        # 滚动区 + 按钮容器
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        button_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        button_layout.setSpacing(0)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()  # 底部拉伸
        scroll_area.setWidget(button_container)
        tab_layout.addWidget(scroll_area)

        # 添加到 TabWidget
        tab_index = self.group_tabWidget.addTab(tab_page, group_name)
        self.group_tabWidget.setCurrentIndex(tab_index)

        # 绑定工具栏按钮
        select_all_btn.clicked.connect(lambda _, g=group_name: self.select_all_in_group(g))
        execute_selected_btn.clicked.connect(lambda _, g=group_name: self.execute_selected_in_group(g))
        stop_group_btn.clicked.connect(lambda _, g=group_name: self.stop_all_in_group(g))
        delete_selected_btn.clicked.connect(lambda _, g=group_name: self.delete_selected_in_group(g))

        # 保存分组信息
        self._groups[group_name] = {
            'tab_index': tab_index,
            'buttons': [],
            'scroll_area': scroll_area,
            'button_container': button_container,
            'button_layout': button_layout,
            'select_all_btn': select_all_btn,
            'execute_selected_btn': execute_selected_btn,
            'stop_group_btn': stop_group_btn,
            'delete_selected_btn': delete_selected_btn,
            'tab_page': tab_page,
        }
        self._group_order.append(group_name)
        return group_name

    def add_new_group(self):
        """点击"+"按钮，新建分组"""
        name, ok = QInputDialog.getText(self, "新建分组", "请输入分组名称：", QLineEdit.Normal, f"分组{len(self._groups)+1}")
        if ok and name.strip():
            name = name.strip()
            if name in self._groups:
                self.update_run_info(f'分组<{name}>已存在', 'WARNING')
                return
            self.add_group_tab(name)
            self.update_run_info(f'新建分组<{name}>成功')

    def on_tab_bar_double_clicked(self, index):
        """双击标签重命名"""
        if index < 0:
            return
        old_name = self.group_tabWidget.tabText(index)
        new_name, ok = QInputDialog.getText(self, "重命名分组", "请输入新的分组名称：", QLineEdit.Normal, old_name)
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name == old_name:
                return
            if new_name in self._groups:
                self.update_run_info(f'分组<{new_name}>已存在', 'WARNING')
                return
            # 更新分组信息
            group_info = self._groups.pop(old_name)
            group_info['tab_index'] = index
            self._groups[new_name] = group_info
            self._group_order[self._group_order.index(old_name)] = new_name
            self.group_tabWidget.setTabText(index, new_name)
            # 更新该分组下所有按钮的 group 字段
            for bid in group_info['buttons']:
                self.sc_buttons[bid]['group'] = new_name
            self.update_run_info(f'分组<{old_name}>重命名为<{new_name}>')

    def on_tab_close_requested(self, index):
        """关闭标签页（删除分组）"""
        if index < 0:
            return
        group_name = self.group_tabWidget.tabText(index)
        # 至少保留一个分组
        if len(self._groups) <= 1:
            self.update_run_info('至少保留一个分组', 'WARNING')
            return
        # 确认对话框
        confirm = QMessageBox()
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setWindowTitle("确认")
        confirm.setText(f"删除分组<{group_name}>将同时删除该分组下所有按钮，是否继续？")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        if confirm.exec_() != QMessageBox.StandardButton.Yes:
            return
        # 删除该分组下所有按钮
        group_info = self._groups[group_name]
        buttons_to_delete = list(group_info['buttons'])
        for bid in buttons_to_delete:
            self._delete_button_internal(bid)
        # 删除标签页
        self.group_tabWidget.removeTab(index)
        # 更新 _groups 中的 tab_index
        del self._groups[group_name]
        self._group_order.remove(group_name)
        for gname, ginfo in self._groups.items():
            ginfo['tab_index'] = self.group_tabWidget.indexOf(ginfo['tab_page'])
        self.update_run_info(f'删除分组<{group_name}>成功')

    def on_tab_bar_context_menu(self, pos):
        """标签栏右键菜单"""
        index = self.group_tabWidget.tabBar().tabAt(pos)
        menu = QMenu()
        new_action = menu.addAction("新建分组")
        rename_action = menu.addAction("重命名") if index >= 0 else None
        delete_action = menu.addAction("删除分组") if index >= 0 else None
        action = menu.exec_(self.group_tabWidget.tabBar().mapToGlobal(pos))
        if action == new_action:
            self.add_new_group()
        elif rename_action and action == rename_action:
            self.on_tab_bar_double_clicked(index)
        elif delete_action and action == delete_action:
            self.on_tab_close_requested(index)

    def _ensure_group(self, group_name):
        """确保分组存在，不存在则创建"""
        if group_name not in self._groups:
            self.add_group_tab(group_name)
        return group_name

    # ==================== 按钮创建 ====================

    def add_button(self, config_data):
        """根据配置数据创建新按钮（带复选框+按钮，添加到对应分组）"""
        if '指令名称' in config_data:
            button_text = config_data['指令名称']
        else:
            button_text = f'新按钮{self.btn_count}'

        # 确定分组：优先用config中的分组，没有则用当前选中的标签页
        if '分组' in config_data and config_data['分组']:
            group_name = config_data['分组']
        else:
            # 获取当前选中的标签页对应的分组名
            current_idx = self.group_tabWidget.currentIndex()
            if current_idx >= 0:
                group_name = self.group_tabWidget.tabText(current_idx)
            else:
                group_name = '默认分组'
        self._ensure_group(group_name)
        group_info = self._groups[group_name]

        # 创建唯一ID
        self.btn_count += 1
        button_id = f"button_{self.btn_count}"

        # 创建容器（复选框 + 按钮）
        container = QWidget(group_info['button_container'])
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(2)

        # 复选框：左边留出间距
        h_layout.addSpacing(15)
        checkbox = QCheckBox(container)
        checkbox.setFixedWidth(20)

        # 按钮主体
        new_button = DraggableButton(button_text, container)
        new_button.setObjectName(button_id)
        cmd_type = config_data['指令类型']
        new_button.setStyleSheet(self.get_button_style(cmd_type))
        new_button.setProperty('executing', False)

        h_layout.addWidget(checkbox)
        h_layout.addWidget(new_button)

        # 连接按钮点击事件
        click_map = {
            '发送命令': self.click_send_cmd,
            '发送命令并接收回显': self.click_send_cmd_print,
            '发送文件': self.click_send_files,
            '获取文件': self.click_get_files,
            '复制本地文件': self.click_copy_files,
            '资源监控': self.resource_monitor,
            '弱网': self.weak_net,
            '服务器检查': self.server_check_exec,
        }
        handler = click_map.get(cmd_type)
        if handler is None:
            self.update_run_info(f'添加快捷按钮{button_text}失败:错误的指令类型', 'ERROR')
            return
        new_button.clicked.connect(lambda _, para=button_id: handler(para))

        # 右键菜单
        new_button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        new_button.customContextMenuRequested.connect(
            lambda pos, btn_id=button_id: self.show_button_context_menu(pos, btn_id))

        # 拖动信号
        new_button.dragStarted.connect(lambda: self._on_drag_started(new_button, button_id, container))
        new_button.dragMoved.connect(self._on_drag_moved)
        new_button.dragEnded.connect(self._on_drag_ended)

        # 添加到分组的按钮布局（在 stretch 之前）
        btn_layout = group_info['button_layout']
        insert_index = btn_layout.count() - 1 if btn_layout.count() > 0 else 0
        btn_layout.insertWidget(insert_index, container)

        # 保存按钮信息
        self.sc_buttons[button_id] = {
            'widget': container,
            'button': new_button,
            'checkbox': checkbox,
            'config': config_data,
            'group': group_name,
        }
        group_info['buttons'].append(button_id)
        config_data['位置'] = len(group_info['buttons'])

    def edit_button(self, config_data, button_id):
        self.sc_buttons[button_id]['config'].update(config_data)  # 更新按钮字典内容
        btn = self.sc_buttons[button_id]['button']  # 按钮对象
        btn.setText(config_data['指令名称'])  # 修改按钮名称
        # 更新按钮样式（类型可能变了）
        cmd_type = config_data.get('指令类型', '')
        if cmd_type:
            btn.setStyleSheet(self.get_button_style(cmd_type))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_drag_started(self, button, button_id, container):
        """拖动开始"""
        self._drag_button = button
        self._drag_container = container
        self._drag_group_name = self.sc_buttons[button_id]['group']
        group_info = self._groups[self._drag_group_name]
        # 创建拖动指示线（在当前分组的容器中）
        if self._drag_indicator is None:
            self._drag_indicator = QWidget(group_info['button_container'])
            self._drag_indicator.setFixedHeight(3)
            self._drag_indicator.setStyleSheet("background-color: #2196F3;")
        else:
            self._drag_indicator.setParent(group_info['button_container'])
        # 改变按钮样式表示正在拖动
        cmd_type = self.sc_buttons[button_id]['config']['指令类型']
        bg, _ = self.BUTTON_COLOR_MAP.get(cmd_type, ('#4CAF50', '#45a049'))
        button.setStyleSheet(f"""
            QPushButton {{
                padding: 10px;
                font-size: 14px;
                margin: 2px;
                border-radius: 5px;
                background-color: rgba({int(bg[1:3], 16)}, {int(bg[3:5], 16)}, {int(bg[5:7], 16)}, 0.5);
                color: rgba(255, 255, 255, 0.7);
                border: 2px solid #2196F3;
            }}
        """)

    def _on_drag_moved(self, global_pos):
        """拖动过程中更新位置"""
        if self._drag_button is None or self._drag_group_name is None:
            return
        group_info = self._groups[self._drag_group_name]
        local_pos = group_info['button_container'].mapFromGlobal(global_pos)
        insert_index = self._get_insert_index(local_pos)
        self._update_drag_indicator(insert_index)

    def _get_insert_index(self, pos):
        """根据鼠标位置获取应该插入的索引"""
        group_info = self._groups[self._drag_group_name]
        button_count = len(group_info['buttons'])
        for i in range(button_count):
            item = group_info['button_layout'].itemAt(i)
            if item.widget():
                btn_rect = item.widget().geometry()
                if pos.y() < btn_rect.center().y():
                    return i
        return button_count

    def _update_drag_indicator(self, index):
        """更新拖动指示线的位置"""
        if self._drag_indicator is None or self._drag_group_name is None:
            return
        group_info = self._groups[self._drag_group_name]
        layout = group_info['button_layout']
        container = group_info['button_container']
        if index >= layout.count():
            last_item = layout.itemAt(layout.count() - 1)
            if last_item and last_item.widget():
                y = last_item.widget().y() + last_item.widget().height()
            else:
                y = 0
            self._drag_indicator.setGeometry(0, y, container.width(), 3)
        else:
            item = layout.itemAt(index)
            if item and item.widget():
                y = item.widget().y() - 2
                self._drag_indicator.setGeometry(0, y, container.width(), 3)
        self._drag_indicator.show()
        self._drag_indicator.raise_()

    def _on_drag_ended(self):
        """拖动结束"""
        if self._drag_button is None:
            return
        # 恢复按钮样式
        button_id = self._drag_button.objectName()
        cmd_type = self.sc_buttons[button_id]['config']['指令类型']
        self._drag_button.setStyleSheet(self.get_button_style(cmd_type))
        self._drag_button.style().unpolish(self._drag_button)
        self._drag_button.style().polish(self._drag_button)
        # 隐藏指示线
        if self._drag_indicator:
            self._drag_indicator.hide()
        # 获取最终插入位置
        group_info = self._groups[self._drag_group_name]
        insert_index = self._get_insert_index(
            group_info['button_container'].mapFromGlobal(QtGui.QCursor.pos()))
        # 获取被拖动容器的当前索引
        current_index = group_info['button_layout'].indexOf(self._drag_container)
        if current_index != -1 and current_index != insert_index:
            self._reorder_buttons(current_index, insert_index)
        self._drag_button = None
        self._drag_container = None
        self._drag_group_name = None

    def _reorder_buttons(self, from_index, to_index):
        """重新排列按钮（在分组内）"""
        group_info = self._groups[self._drag_group_name]
        layout = group_info['button_layout']
        # 从布局中移除容器
        container = layout.itemAt(from_index).widget()
        layout.removeWidget(container)
        # 插入到新位置
        max_index = layout.count() - 1  # 减去 stretch
        if to_index > max_index:
            to_index = max_index
        if to_index > from_index:
            to_index -= 1
        layout.insertWidget(to_index, container)
        # 更新分组的 buttons 列表
        button_id = self._drag_button.objectName()
        if button_id in group_info['buttons']:
            group_info['buttons'].remove(button_id)
        group_info['buttons'].insert(to_index, button_id)
        # 更新位置字段
        for idx, bid in enumerate(group_info['buttons']):
            self.sc_buttons[bid]['config']['位置'] = idx + 1
        self.update_run_info(f'按钮<{self._drag_button.text()}>已移动到第{to_index + 1}个位置')

    def click_send_cmd(self, button_id):
        """发送指令"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}> 执行失败:{e}', 'ERROR')
            self.set_button_executing(button_id, False)
            return

        def execute_send_cmd_flow(cmd):
            """执行发送指令流程连接→发送→断开"""
            # 连接SSH
            connect_result = ssh_tool.connect()
            if not connect_result:
                return False

            # 发送指令
            send_result = ssh_tool.send_command(cmd)

            # 断开连接
            disconnect_result = ssh_tool.disconnect()

            if not send_result:
                return False
            if not disconnect_result:
                return False
            return True

        def on_worker_finished(result):
            """worker结束处理界面"""
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            thread.quit()

        def on_thread_finished():
            """线程结束清理资源"""
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            execute_send_cmd_flow, # 封装完整流程
            self.sc_buttons[button_id]['config']['指令'],
            op_name=button_name
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中，一定要先移动再绑信号槽，不然会绑定到主线程
        worker.moveToThread(thread)

        # 绑定worker信号槽（业务日志通过 logger + 操作上下文自动进入运行信息面板）
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker,
            "button_id": button_id
        }

        thread.start()

    def click_send_cmd_print(self, button_id):
        """发送指令并回显打印到界面"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}> 执行失败:{e}', 'ERROR')
            self.set_button_executing(button_id, False)
            return

        # 封装指令发送和回显接收方法
        def send_cmd_and_receive_echo(cmd, echo_signal):
            c_result = ssh_tool.connect()
            if not c_result:
                return False
            ssh_tool.send_command_interactive(cmd)
            g_result = ssh_tool.get_output_continue(echo_signal=echo_signal)
            ssh_tool.disconnect()
            return g_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            # 不要在worker里deleteLater自己，会被放到worker的线程中执行
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            send_cmd_and_receive_echo, op_name=button_name
        )
        worker.kwargs = {
            "cmd" : self.sc_buttons[button_id]['config']['指令'],
            "echo_signal": worker.echo_signal
        }

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定信号槽
        worker.echo_signal.connect(self.update_linux_print)
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存worker和线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker,
            "button_id": button_id
        }

        thread.start()

    def click_send_files(self, button_id):
        """发送文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 每次执行生成唯一进度ID，确保新进度不会覆盖上一次的行
        import time
        exec_id = f"{button_id}_{int(time.time()*1000)}"

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}> 执行失败:{e}', 'ERROR')
            self.set_button_executing(button_id, False)
            return

        # 读取源路径列表（兼容旧版单条配置）
        sc_cfg = self.sc_buttons[button_id]['config']
        remote_path = sc_cfg['服务器路径'] if '服务器路径' in sc_cfg else sc_cfg.get('目的路径', '')
        work_dir = sc_cfg['文件暂存路径'] if '文件暂存路径' in sc_cfg else ''

        if '源路径列表' in sc_cfg:
            source_items = sc_cfg['源路径列表']
        else:
            # 兼容旧版单条配置
            source_items = [{
                '路径': sc_cfg.get('本地路径', ''),
                '修改时间': sc_cfg.get('修改时间', '全部'),
                '名称包含': {'关键词': [sc_cfg.get('文件名包含', '')] if sc_cfg.get('文件名包含') else [], '逻辑': '或'},
                '名称不包含': {'关键词': [], '逻辑': '和'}
            }]

        def execute_send_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            def send_progress_cb(phase, current, total, extra=''):
                log_progress(self.logger, phase, current, total, extra)

            s_result = ssh_tool.send_files(source_items, remote_path, work_dir=work_dir if work_dir else None, progress_cb=send_progress_cb)

            ssh_tool.disconnect()

            return s_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            thread.quit()

        def on_progress(info):
            if len(info) < 4:
                return
            phase = info[1]
            current = info[2]
            total = info[3]
            extra = info[4] if len(info) > 4 else ''
            msg = None
            if phase == 'find':
                msg = f'<{button_name}> 查找中... 找到{total}个文件'
            elif phase == 'upload':
                if total > 0:
                    pct = int(current * 100 / total)
                    total_mb = total / 1048576
                    # extra格式：cur_name|cur_size|cur_sent|file_idx|total_files
                    parts = extra.split('|') if extra else []
                    if len(parts) >= 5:
                        file_idx = int(parts[3]) if parts[3].isdigit() else 0
                        total_files = int(parts[4]) if parts[4].isdigit() else 0
                        cur_name = os.path.basename(parts[0])
                        cur_size = int(parts[1]) if parts[1].isdigit() else 0
                        cur_sent = int(parts[2]) if parts[2].isdigit() else 0
                        cur_pct = int(cur_sent * 100 / cur_size) if cur_size > 0 else 0
                        cur_mb = cur_size / 1048576
                        msg = (f'<{button_name}> 上传中... 总进度{pct}% (共{total_mb:.1f}MB)  '
                               f'文件{file_idx}/{total_files}: {cur_name} {cur_pct}% ({cur_mb:.1f}MB)')
                    else:
                        msg = f'<{button_name}> 上传中... {pct}% (共{total_mb:.1f}MB)'
            elif phase == 'move':
                if total > 0 and isinstance(current, (int, float)):
                    pct = int(current * 100 / total)
                    msg = f'<{button_name}> 移动中... {pct}% ({current}/{total}) {extra}'
                else:
                    msg = f'<{button_name}> 移动中... {extra}'
            if msg:
                self.update_run_info_progress(button_id, msg)

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker（携带操作上下文：线程内 ssh_tools 日志自动带按钮名前缀，
        # 进度通过 logger 的 progress_signal 统一进入运行信息面板）
        worker = qthread_worker.OneClickWorker(
            execute_send_files, op_name=button_name, op_id=exec_id
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        if hasattr(worker, 'info_signal'):
            worker.info_signal.connect(on_progress)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker,
            "button_id": button_id
        }

        thread.start()

    def click_get_files(self, button_id):
        """下载文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 每次执行生成唯一进度ID，确保新进度不会覆盖上一次的行
        import time
        exec_id = f"{button_id}_{int(time.time()*1000)}"

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = self.sc_buttons[button_id]['config']['IP']
            ssh_tool.port = self.sc_buttons[button_id]['config']['端口']
            ssh_tool.username = self.sc_buttons[button_id]['config']['用户名']
            ssh_tool.password = self.sc_buttons[button_id]['config']['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}> 执行失败:{e}', 'ERROR')
            self.set_button_executing(button_id, False)
            return

        sc_cfg = self.sc_buttons[button_id]['config']
        work_dir = sc_cfg['文件暂存路径'] if '文件暂存路径' in sc_cfg else ''

        # 读取源路径列表（兼容旧版单条配置）
        if '源路径列表' in sc_cfg:
            source_items = sc_cfg['源路径列表']
        else:
            # 兼容旧版单条配置
            source_items = [{
                '路径': sc_cfg.get('服务器路径', ''),
                '修改时间': sc_cfg.get('修改时间', '全部'),
                '名称包含': {'关键词': [sc_cfg.get('文件名包含', '')] if sc_cfg.get('文件名包含') else [], '逻辑': '或'},
                '名称不包含': {'关键词': [], '逻辑': '和'}
            }]

        # 目的路径
        local_path = sc_cfg['目的路径']

        # 将本地路径的"当前路径/时间IP(例:20251024_031415-1.1.1.1)/"修改为当前时间当前路径
        if local_path == "当前路径/时间IP(例:20251024_031415-1.1.1.1)/":
            current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = self.get_default_path() + '/' + current_time + '-' + sc_cfg['IP']
            os.mkdir(local_path)

        def execute_get_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            def get_progress_cb(phase, current, total, extra=''):
                log_progress(self.logger, phase, current, total, extra)

            g_result = ssh_tool.get_files(source_items, local_path, work_dir=work_dir if work_dir else None, progress_cb=get_progress_cb)

            ssh_tool.disconnect()

            return g_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            execute_get_files, op_name=button_name, op_id=exec_id
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": ssh_tool,
            "thread": thread,
            "worker": worker,
            "button_id": button_id
        }

        thread.start()

    def click_copy_files(self, button_id):
        """复制本地文件（支持多源路径、名称包含/不包含筛选）"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 生成唯一执行ID，避免多次执行的进度行互相覆盖
        import time
        exec_id = f"{button_id}_{int(time.time() * 1000)}"

        # 初始化WindowsTools
        win_tool = windows_tools.WindowsTools()

        sc_cfg = self.sc_buttons[button_id]['config']

        # 目的路径：优先读"目的路径"，兼容旧版"复制到"
        target_path = sc_cfg.get('目的路径', sc_cfg.get('复制到', ''))

        # 将"当前路径/当前时间(例:20251024_031415)/"修改为当前路径/当前时间
        if target_path == "当前路径/当前时间(例:20251024_031415)/":
            current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.get_default_path() + '/' + current_time
            os.mkdir(target_path)

        # 读取源路径列表
        source_items = sc_cfg.get('源路径列表', [])
        if not source_items:
            self.update_run_info(f'<{button_name}> 请至少添加一个源路径', 'WARNING')
            self.set_button_executing(button_id, False)
            return

        def execute_copy_files():
            def copy_progress_cb(phase, current, total, extra=''):
                log_progress(self.logger, phase, current, total, extra)

            cp_result = win_tool.copy_files(source_items, target_path, progress_cb=copy_progress_cb)
            return cp_result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            thread.quit()

        def on_thread_finished():
            thread.deleteLater()
            self.sc_threads.pop(thread_name)

        # 初始化worker
        worker = qthread_worker.OneClickWorker(
            execute_copy_files, op_name=button_name, op_id=exec_id
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)

        # 绑定线程信号槽
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)

        # 保存线程信息
        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        self.sc_threads[thread_name] = {
            "tool": win_tool,
            "thread": thread,
            "worker": worker,
            "button_id": button_id
        }

        thread.start()

    def resource_monitor(self, button_id):
        """按下快捷键时调用，打开资源监控配置的窗口，按传入的button_id参数来获取服务器IP等内容"""
        if button_id in self.sc_buttons:
            self.set_button_executing(button_id, True)
            # 打开资源监控的子窗口，需要将buttonid传入
            monitor_set_dlg = ResourceMonitorDialog2(button_id, self)
            if self.sc_buttons[button_id]['config']['IP'] == '':
                monitor_set_dlg.setWindowTitle('本机<资源监控>控制面板')
            else:
                monitor_set_dlg.setWindowTitle(f"{self.sc_buttons[button_id]['config']['IP']}<资源监控>控制面板")
            # 显示弹出窗口
            result = monitor_set_dlg.exec_()
            # 关闭窗口时主界面按钮恢复
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                self.set_button_executing(button_id, False)

    def weak_net(self, button_id):
        """按下快捷键时调用，打开弱网控制面板"""
        if button_id in self.sc_buttons:
            self.set_button_executing(button_id, True)
            weak_net_dlg = WeakNetControlDialog(button_id, self)
            ip = self.sc_buttons[button_id]['config']['IP']
            if ip == '':
                weak_net_dlg.setWindowTitle('本机<弱网>控制面板')
            else:
                weak_net_dlg.setWindowTitle(f"{ip}<弱网>控制面板")
            result = weak_net_dlg.exec_()
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                self.set_button_executing(button_id, False)

    def server_check_exec(self, button_id):
        """服务器检查按钮执行函数"""
        if button_id in self.sc_buttons:
            self.set_button_executing(button_id, True)
            check_dlg = ServerCheckRunDialog(button_id, self)
            check_dlg.setWindowTitle('服务器检查面板')
            result = check_dlg.exec_()
            if result != QtWidgets.QDialog.DialogCode.Accepted:
                self.set_button_executing(button_id, False)

    def _on_qt_log_message(self, msg: str, color: str, levelno: int, op_name: str = ''):
        """Qt 普通日志信号回调：logger.info/warning/error → 运行信息面板

        - DEBUG 级别的内部细节不进 UI（已在 QtHandler 的 INFO 级别过滤，双保险）
        - 带操作上下文（按钮名）时自动加 <按钮名> 前缀
        """
        import logging
        if levelno < logging.INFO:
            return
        level = logging.getLevelName(levelno)

        if op_name and not msg.startswith(f'<{op_name}>'):
            msg = f'<{op_name}> {msg}'
        self.update_run_info(msg, level)

    def _on_qt_progress(self, op_name, op_id, phase, current, total, extra):
        """Qt 进度信号回调：log_progress() → 更新运行信息同一行

        统一处理所有流程（发送/获取/复制文件、文件浏览器上传下载、对话框上传下载）。
        """
        msg = self._format_progress(op_name, phase, current, total, extra, op_id)
        if msg:
            progress_key = f"{op_id}_{phase}" if op_id else phase
            level = 'ERROR' if phase == 'error' else 'INFO'
            self.update_run_info_progress(progress_key, msg, level)

    @staticmethod
    def _format_progress(op_name, phase, current, total, extra, op_id=''):
        """把进度四元组格式化成运行信息展示文本（复刻原各流程 wrapper 的格式）"""
        prefix = f'<{op_name}> ' if op_name else ''

        def to_int(v, default=0):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        cur = to_int(current)
        tot = to_int(total)
        extra_parts = (extra or '').split('|') if extra else []

        if phase == 'find':
            return f'{prefix}查找中... 找到{tot}个文件'

        if phase == 'upload':
            # 文件浏览器上传：简洁格式；快捷按钮发送文件：详细格式（extra 5段）
            if op_id.startswith('fb_upload') or len(extra_parts) < 5:
                if tot > 0:
                    return f'{prefix}上传中... {cur}/{tot} ({int(cur * 100 / tot)}%)'
                return f'{prefix}上传中... {cur}/{tot}'
            pct = int(cur * 100 / tot) if tot else 0
            total_mb = tot / 1048576
            file_idx = to_int(extra_parts[3])
            total_files = to_int(extra_parts[4])
            cur_name = os.path.basename(extra_parts[0])
            cur_size = to_int(extra_parts[1])
            cur_sent = to_int(extra_parts[2])
            cur_pct = int(cur_sent * 100 / cur_size) if cur_size > 0 else 0
            cur_mb = cur_size / 1048576
            return (f'{prefix}上传中... 总进度{pct}% (共{total_mb:.1f}MB)  '
                    f'文件{file_idx}/{total_files}: {cur_name} {cur_pct}% ({cur_mb:.1f}MB)')

        if phase == 'move':
            if op_id.startswith('fb_upload'):
                return f'{prefix}移动中... {cur}/{tot}'
            if tot > 0:
                pct = int(cur * 100 / tot)
                return f'{prefix}移动中... {pct}% ({cur}/{tot}) {extra}'
            return f'{prefix}移动中... {extra}'

        if phase == 'copy':
            # 本地文件复制(windows_tools)：extra 直接是展示文本
            if extra and '总进度' in extra:
                return f'{prefix}复制中... {extra}'
            # 远程下载前的临时目录复制：extra 是远程路径
            if extra:
                cur_name = extra.split('/')[-1] if '/' in extra else extra
                if tot > 0:
                    return f'{prefix}复制中... {cur}/{tot} ({int(cur * 100 / tot)}%)  {cur_name}'
            if tot > 0:
                return f'{prefix}复制中... {cur}% ({cur}/{tot})'
            return None

        if phase == 'download':
            if tot > 0:
                pct = int(cur * 100 / tot)
                total_mb = tot / 1048576
                if len(extra_parts) >= 5:
                    file_idx = to_int(extra_parts[3])
                    total_files = to_int(extra_parts[4])
                    cur_name = os.path.basename(extra_parts[0])
                    cur_size = to_int(extra_parts[1])
                    cur_sent = to_int(extra_parts[2])
                    cur_pct = int(cur_sent * 100 / cur_size) if cur_size > 0 else 0
                    cur_mb = cur_size / 1048576
                    total_display = total_files if total_files > 0 else '未知'
                    return (f'{prefix}下载中... 总进度{pct}% ({total_mb:.1f}MB) '
                            f'文件{file_idx + 1}/{total_display}: {cur_name} {cur_pct}% ({cur_mb:.1f}MB)')
                return f'{prefix}下载中... {pct}% ({total_mb:.1f}MB)'
            return None

        if phase in ('done', 'error'):
            text = '|'.join(extra_parts)
            if phase == 'error':
                return f'{prefix}错误: {text}'
            return f'{prefix}{text}'

        return None

    def _make_log_wrapper(self, button_name):
        """创建带按钮名称前缀的日志包装函数（仅用于直接发射 worker.log_signal 的场景）"""
        def wrapper(text, level='INFO'):
            if text.startswith(f'<{button_name}> '):
                self.update_run_info(text, level)
            else:
                self.update_run_info(f'<{button_name}> {text}', level)
        return wrapper

    def update_run_info(self, text, level='INFO'):
        """显示到运行信息面板（纯 UI 渲染，不转发 logger）

        logger 方向：各模块直接调 logger.info() 会自动走到这里，
                    因为 QtLogEmitter 已经连好了信号。
        """
        # 根据级别设置颜色
        color_map = {
            'INFO': '#000000',
            'WARNING': '#FF8C00',
            'ERROR': '#FF0000',
            'DEBUG': '#808080',
        }
        color = color_map.get(level.upper(), '#000000')

        # HTML 转义：防止 < > & 等特殊字符被解析成标签
        html_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # 加时间戳后显示到UI（带颜色）
        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html = f'<span style="color: {color}">{formatted_datetime} {html_text}</span>'
        self.run_info_browser.append(html)

        # 滚动条置底
        self.run_info_browser.verticalScrollBar().setValue(
            self.run_info_browser.verticalScrollBar().maximum()
        )
        self.run_info_browser.horizontalScrollBar().setValue(
            self.run_info_browser.horizontalScrollBar().minimum()
        )

    def update_run_info_progress(self, progress_key, text, level='INFO'):
        """更新运行信息中指定的进度行（用于进度等实时刷新的内容，不刷屏）

        Args:
            progress_key: 进度的唯一标识（如button_id），多个并行任务互不干扰
            text: 要显示的文本
            level: 日志级别
        """
        color_map = {
            'INFO': '#000000',
            'WARNING': '#FF8C00',
            'ERROR': '#FF0000',
        }
        color = color_map.get(level.upper(), '#000000')
        html_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html = f'<span style="color: {color}">{formatted_datetime} {html_text}</span>'

        if not hasattr(self, '_progress_blocks'):
            self._progress_blocks = {}

        doc = self.run_info_browser.document()
        cursor = self.run_info_browser.textCursor()

        if progress_key in self._progress_blocks:
            # 已有进度块：定位到那个块，替换内容
            block_pos = self._progress_blocks[progress_key]
            block = doc.findBlock(block_pos)
            if block.isValid():
                cursor.setPosition(block.position())
                cursor.movePosition(cursor.MoveOperation.EndOfBlock, cursor.MoveMode.KeepAnchor)
                cursor.insertHtml(html)
            else:
                # 块失效了（比如被外部清掉了），重新追加
                self.run_info_browser.append(html)
                new_block = doc.lastBlock()
                self._progress_blocks[progress_key] = new_block.position()
        else:
            # 新进度：追加一行，并记录块位置
            self.run_info_browser.append(html)
            new_block = doc.lastBlock()
            self._progress_blocks[progress_key] = new_block.position()

        # 滚动条置底
        self.run_info_browser.verticalScrollBar().setValue(
            self.run_info_browser.verticalScrollBar().maximum()
        )

    def update_linux_print(self, text, insert=False):
        # 更新终端显示（服务器回显）
        if hasattr(self, 'terminal_widget'):
            self.terminal_widget.append_output(text)
        else:
            if insert:
                cursor = self.linux_print_browser.textCursor()
                cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
                self.linux_print_browser.setTextCursor(cursor)
                self.linux_print_browser.insertPlainText(text)
            else:
                self.linux_print_browser.append(text)
            self.linux_print_browser.verticalScrollBar().setValue(
                self.linux_print_browser.verticalScrollBar().maximum()
            )
            self.linux_print_browser.horizontalScrollBar().setValue(
                self.linux_print_browser.horizontalScrollBar().minimum()
            )

    def _start_terminal_mode(self):
        """进入终端模式：开启可编辑，准备接收服务器回显"""
        if hasattr(self, 'terminal_widget'):
            self.terminal_widget.set_terminal_mode(True)
            self.update_run_info('进入终端模式')
        # 联动文件浏览器
        if hasattr(self, 'file_browser') and 'tool' in self.current_ssh:
            self.file_browser.set_ssh_tool(self.current_ssh['tool'])

    def _stop_terminal_mode(self):
        """退出终端模式：回到只读"""
        if hasattr(self, 'terminal_widget'):
            self.terminal_widget.set_terminal_mode(False)

    def _on_terminal_output(self, text):
        """接收到服务器回显，追加到终端"""
        self.update_linux_print(text, insert=True)

    def _on_terminal_key(self, key_text):
        """终端按键：发送给服务器"""
        if (self.connect_pushButton.text() == '断开' and
                'tool' in self.current_ssh and self.current_ssh['tool']):
            try:
                channel = self.current_ssh['tool'].channel
                if channel and channel.active:
                    channel.send(key_text)
            except Exception as e:
                self.update_run_info(f'发送按键失败: {e}', 'ERROR')

    def _on_terminal_paste(self, text):
        """终端粘贴：发送给服务器"""
        if (self.connect_pushButton.text() == '断开' and
                'tool' in self.current_ssh and self.current_ssh['tool']):
            try:
                channel = self.current_ssh['tool'].channel
                if channel and channel.active:
                    # 分块发送避免一次发太多
                    chunk_size = 4096
                    for i in range(0, len(text), chunk_size):
                        channel.send(text[i:i+chunk_size])
            except Exception as e:
                self.update_run_info(f'粘贴发送失败: {e}', 'ERROR')

    # ---------- 文件浏览器：上传/下载 ----------

    def _fb_upload(self, remote_dir, local_paths):
        """文件浏览器：上传本地文件/文件夹到远程目录"""
        if ('tool' not in self.current_ssh or
                not self.current_ssh['tool'] or
                not self.current_ssh['tool'].is_connected()):
            self.update_run_info('请先连接服务器', 'WARNING')
            return

        if not local_paths:
            return

        import time, os

        ssh_tool = self.current_ssh['tool']
        button_name = '文件上传'
        exec_id = f"fb_upload_{int(time.time()*1000)}"
        self.update_run_info(f'<{button_name}> 开始执行')

        # 构造 source_items（文件浏览器上传不做筛选，直接传）
        source_items = []
        for p in local_paths:
            source_items.append({
                '路径': p,
                '修改时间': '全部',
                '名称包含': {'关键词': [], '逻辑': '或'},
                '名称不包含': {'关键词': [], '逻辑': '和'}
            })

        def progress_cb(phase, current, total, extra=''):
            log_progress(self.logger, phase, current, total, extra)

        def execute_upload():
            result = ssh_tool.send_files(source_items, remote_dir, progress_cb=progress_cb)
            return result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
                if hasattr(self, 'file_browser') and self.file_browser.is_connected():
                    self.file_browser.refresh()
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            thread.quit()

        worker = qthread_worker.OneClickWorker(
            execute_upload, op_name=button_name, op_id=exec_id
        )

        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        thread = QThread()
        worker.moveToThread(thread)

        def on_thread_finished():
            if thread_name in self.sc_threads:
                del self.sc_threads[thread_name]

        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.sc_threads[thread_name] = {"thread": thread, "worker": worker}
        thread.start()

    def _fb_download(self, remote_paths, local_dir):
        """文件浏览器：下载远程文件/文件夹到本地"""
        if ('tool' not in self.current_ssh or
                not self.current_ssh['tool'] or
                not self.current_ssh['tool'].is_connected()):
            self.update_run_info('请先连接服务器', 'WARNING')
            return

        if not remote_paths:
            return

        import time, os

        ssh_tool = self.current_ssh['tool']
        button_name = '文件下载'
        exec_id = f"fb_download_{int(time.time()*1000)}"
        self.update_run_info(f'<{button_name}> 开始执行')

        # 构造 source_items（文件浏览器下载不做筛选，直接下）
        source_items = []
        for p in remote_paths:
            source_items.append({
                '路径': p,
                '修改时间': '全部',
                '名称包含': {'关键词': [], '逻辑': '或'},
                '名称不包含': {'关键词': [], '逻辑': '和'}
            })

        def progress_cb(phase, current, total, extra=''):
            log_progress(self.logger, phase, current, total, extra)

        def execute_download():
            result = ssh_tool.get_files(source_items, local_dir, progress_cb=progress_cb)
            return result

        def on_worker_finished(result):
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            thread.quit()

        worker = qthread_worker.OneClickWorker(
            execute_download, op_name=button_name, op_id=exec_id
        )

        self.thread_count += 1
        thread_name = f'sc_thread_{self.thread_count}'
        thread = QThread()
        worker.moveToThread(thread)

        def on_thread_finished():
            if thread_name in self.sc_threads:
                del self.sc_threads[thread_name]

        worker.finished.connect(on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.sc_threads[thread_name] = {"thread": thread, "worker": worker}
        thread.start()

    def show_button_context_menu(self, pos, button_id):
        menu = QMenu()
        is_executing = self.sc_buttons[button_id]['button'].property('executing')
        edit_action = None
        delete_action = None
        move_action = None
        if is_executing:
            copy_action = menu.addAction("复制")
            stop_action = menu.addAction("停止")
        else:
            copy_action = menu.addAction("复制")
            edit_action = menu.addAction("编辑")
            delete_action = menu.addAction("删除")
            stop_action = menu.addAction("停止")
            # 移动分组子菜单
            move_menu = menu.addMenu("移动到分组")
            current_group = self.sc_buttons[button_id]['group']
            for gname in self._group_order:
                if gname != current_group:
                    move_menu.addAction(gname)
            move_action = move_menu

        action = menu.exec(self.sc_buttons[button_id]['button'].mapToGlobal(pos))

        if action == copy_action:
            self.copy_button(button_id)
        elif edit_action is not None and action == edit_action:
            self.edit_button_dialog(button_id)
        elif delete_action is not None and action == delete_action:
            self.delete_button(button_id)
        elif action == stop_action:
            self.stop_single_button(button_id)
        elif move_action is not None and action is not None and action.text() in self._groups:
            self.move_button_to_group(button_id, action.text())

    def move_button_to_group(self, button_id, target_group):
        """移动按钮到另一个分组"""
        if button_id not in self.sc_buttons or target_group not in self._groups:
            return
        old_group = self.sc_buttons[button_id]['group']
        if old_group == target_group:
            return
        # 从旧分组移除
        old_group_info = self._groups[old_group]
        if button_id in old_group_info['buttons']:
            old_group_info['buttons'].remove(button_id)
        old_group_info['button_layout'].removeWidget(self.sc_buttons[button_id]['widget'])
        # 更新旧分组位置字段
        for idx, bid in enumerate(old_group_info['buttons']):
            self.sc_buttons[bid]['config']['位置'] = idx + 1
        # 添加到新分组
        new_group_info = self._groups[target_group]
        btn_layout = new_group_info['button_layout']
        insert_index = btn_layout.count() - 1 if btn_layout.count() > 0 else 0
        btn_layout.insertWidget(insert_index, self.sc_buttons[button_id]['widget'])
        new_group_info['buttons'].append(button_id)
        self.sc_buttons[button_id]['group'] = target_group
        self.sc_buttons[button_id]['config']['分组'] = target_group
        self.sc_buttons[button_id]['config']['位置'] = len(new_group_info['buttons'])
        self.sc_buttons[button_id]['widget'].setParent(new_group_info['button_container'])
        btn_name = self.sc_buttons[button_id]['config']['指令名称']
        self.update_run_info(f'按钮<{btn_name}>已移动到分组<{target_group}>')

    def copy_button(self, button_id):
        """复制按钮"""
        if button_id not in self.sc_buttons:
            return
        original_config = self.sc_buttons[button_id]['config'].copy()
        original_config['指令名称'] = original_config['指令名称'] + '_副本'
        # 保持同一分组
        original_config['分组'] = self.sc_buttons[button_id]['group']
        self.add_button(original_config)
        btn_text = original_config['指令名称']
        self.update_run_info(f"复制删除<{btn_text}>快捷按钮成功")

    def stop_single_button(self, button_id):
        """停止单个按钮的线程"""
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        stopped_count = 0
        thread_names_to_stop = []
        for thread_name, thread_info in self.sc_threads.items():
            if 'button_id' in thread_info and thread_info['button_id'] == button_id:
                thread_names_to_stop.append(thread_name)

        if not thread_names_to_stop:
            self.update_run_info(f'<{button_name}> 没有正在执行的指令', 'WARNING')
            return

        for thread_name in thread_names_to_stop:
            thread_info = self.sc_threads[thread_name]
            if 'tool' in thread_info:
                if type(thread_info['tool']) == ssh_tools.SSHTools:
                    if thread_info['tool'].is_connected():
                        thread_info['tool'].send_command_interactive(chr(3))
                        thread_info['tool'].transfer_stat = 0
                        thread_info['tool'].win_tool.transfer_stat = 0
                elif type(thread_info['tool']) == windows_tools.WindowsTools:
                    thread_info['tool'].transfer_stat = 0
            stopped_count += 1

        if stopped_count > 0:
            self.update_run_info(f'<{button_name}> 已发送中止请求，请等待')

    def _delete_button_internal(self, button_id):
        """内部删除按钮（不弹确认框），供删除分组调用"""
        if button_id not in self.sc_buttons:
            return
        btn_info = self.sc_buttons[button_id]
        group_name = btn_info['group']
        sc_ty = btn_info['config']['指令类型']
        btn_text = btn_info['config']['指令名称']
        # 从分组移除
        group_info = self._groups[group_name]
        if button_id in group_info['buttons']:
            group_info['buttons'].remove(button_id)
        # 更新位置字段
        for idx, bid in enumerate(group_info['buttons']):
            self.sc_buttons[bid]['config']['位置'] = idx + 1
        # 删除界面控件
        btn_info['widget'].deleteLater()
        del self.sc_buttons[button_id]
        self.update_run_info(f"删除<{btn_text}>快捷按钮成功")

    def delete_button(self, button_id):
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Icon.Question)
        confirm_dialog.setWindowTitle("确认")
        confirm_dialog.setText("是否要删除快捷按钮")
        confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = confirm_dialog.exec_()
        if result == QMessageBox.StandardButton.Yes:
            self._delete_button_internal(button_id)
        else:
            self.update_run_info(f"删除按钮操作取消")

    def edit_button_dialog(self, button_id):
        if button_id in self.sc_buttons:
            ty_dialog = {
                '发送命令': self.cmd1_dialog,
                '发送命令并接收回显': self.cmd2_dialog,
                '发送文件': self.send_file_dialog,
                '获取文件': self.get_file_dialog,
                '复制本地文件': self.copy_file_dialog,
                '资源监控': self.resource_monitor_dialog,
                '弱网': self.weak_net_dialog,
                '服务器检查': self.server_check_dialog,
            }
            sc_ty = self.sc_buttons[button_id]['config']['指令类型']
            dialog_func = ty_dialog.get(sc_ty)  # 假设指令类型是发送命令，dialog_func就是self.cmd1_dialog
            if dialog_func:
                dialog_func(button_id)  # 以编辑模式打开窗口，传入button_id
            else:
                self.update_run_info(f"编辑按钮出错：未知指令类型{sc_ty}", 'ERROR')

    # ==================== 分组批量操作 ====================

    # 批量执行时跳过的类型
    SKIP_BATCH_TYPES = {'发送命令并接收回显', '资源监控', '弱网', '服务器检查'}

    def select_all_in_group(self, group_name):
        """切换分组内所有按钮的勾选状态"""
        if group_name not in self._groups:
            return
        group_info = self._groups[group_name]
        buttons = group_info['buttons']
        if not buttons:
            return
        # 检查当前是否全部勾选
        all_checked = all(self.sc_buttons[bid]['checkbox'].isChecked() for bid in buttons)
        # 切换状态
        for bid in buttons:
            self.sc_buttons[bid]['checkbox'].setChecked(not all_checked)

    def execute_selected_in_group(self, group_name):
        """执行分组内所有勾选的按钮"""
        if group_name not in self._groups:
            return
        group_info = self._groups[group_name]
        to_execute = [bid for bid in group_info['buttons']
                      if self.sc_buttons[bid]['checkbox'].isChecked()]
        if not to_execute:
            self.update_run_info(f'分组<{group_name}>没有勾选的按钮', 'WARNING')
            return
        # 过滤掉不适合批量执行的类型
        skipped = []
        executable = []
        for bid in to_execute:
            cmd_type = self.sc_buttons[bid]['config']['指令类型']
            if cmd_type in self.SKIP_BATCH_TYPES:
                skipped.append(bid)
            elif self.sc_buttons[bid]['button'].property('executing'):
                skipped.append(bid)  # 正在执行的也跳过
            else:
                executable.append(bid)
        if skipped:
            for bid in skipped:
                btn_name = self.sc_buttons[bid]['config']['指令名称']
                self.update_run_info(f'跳过<{btn_name}>（不支持批量或正在执行）', 'WARNING')
        if not executable:
            self.update_run_info(f'分组<{group_name}>没有可批量执行的按钮', 'WARNING')
            return
        self.update_run_info(f'分组<{group_name}>开始批量执行{len(executable)}个按钮')
        # 间隔1秒逐个启动
        for i, bid in enumerate(executable):
            if i > 0:
                QTimer.singleShot(1000 * i, lambda b=bid: self._execute_button(b))
            else:
                self._execute_button(bid)

    def _execute_button(self, button_id):
        """执行单个按钮（根据类型调用对应的处理函数）"""
        if button_id not in self.sc_buttons:
            return
        cmd_type = self.sc_buttons[button_id]['config']['指令类型']
        handler_map = {
            '发送命令': self.click_send_cmd,
            '发送文件': self.click_send_files,
            '获取文件': self.click_get_files,
            '复制本地文件': self.click_copy_files,
        }
        handler = handler_map.get(cmd_type)
        if handler:
            handler(button_id)

    def stop_all_in_group(self, group_name):
        """停止分组内所有正在执行的按钮"""
        if group_name not in self._groups:
            return
        group_info = self._groups[group_name]
        button_ids = set(group_info['buttons'])
        stopped_count = 0
        for thread_name, thread_info in self.sc_threads.items():
            if 'button_id' in thread_info and thread_info['button_id'] in button_ids:
                if 'tool' in thread_info:
                    if type(thread_info['tool']) == ssh_tools.SSHTools:
                        if thread_info['tool'].is_connected():
                            thread_info['tool'].send_command_interactive(chr(3))
                            thread_info['tool'].transfer_stat = 0
                            thread_info['tool'].win_tool.transfer_stat = 0
                    elif type(thread_info['tool']) == windows_tools.WindowsTools:
                        thread_info['tool'].transfer_stat = 0
                stopped_count += 1
        if stopped_count > 0:
            self.update_run_info(f'分组<{group_name}>已发送{stopped_count}个中止请求，请等待')
        else:
            self.update_run_info(f'分组<{group_name}>没有正在执行的指令', 'WARNING')

    def delete_selected_in_group(self, group_name):
        """删除分组内所有勾选的按钮（跳过正在执行的）"""
        if group_name not in self._groups:
            return
        group_info = self._groups[group_name]
        to_delete = [bid for bid in group_info['buttons']
                     if self.sc_buttons[bid]['checkbox'].isChecked()]
        if not to_delete:
            self.update_run_info(f'分组<{group_name}>没有勾选的按钮', 'WARNING')
            return
        # 确认对话框
        confirm = QMessageBox()
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setWindowTitle("确认")
        confirm.setText(f"是否删除分组<{group_name}>中勾选的{len(to_delete)}个按钮？")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        if confirm.exec_() != QMessageBox.StandardButton.Yes:
            self.update_run_info('删除选中按钮操作取消')
            return
        # 分离可删除和需跳过的
        skipped = []
        deletable = []
        for bid in to_delete:
            if self.sc_buttons[bid]['button'].property('executing'):
                skipped.append(bid)
            else:
                deletable.append(bid)
        if skipped:
            for bid in skipped:
                btn_name = self.sc_buttons[bid]['config']['指令名称']
                self.update_run_info(f'跳过<{btn_name}>（正在执行中）', 'WARNING')
        for bid in deletable:
            self._delete_button_internal(bid)
        if deletable:
            self.update_run_info(f'分组<{group_name}>已删除{len(deletable)}个按钮')

    def execute_all_buttons(self):
        """全部执行所有标签页的所有按钮（跳过不支持批量执行的类型）"""
        all_executable = []
        for gname in self._group_order:
            for bid in self._groups[gname]['buttons']:
                cmd_type = self.sc_buttons[bid]['config']['指令类型']
                if cmd_type not in self.SKIP_BATCH_TYPES:
                    if not self.sc_buttons[bid]['button'].property('executing'):
                        all_executable.append(bid)
        if not all_executable:
            self.update_run_info('没有可批量执行的按钮', 'WARNING')
            return
        self.update_run_info(f'开始批量执行所有标签页的{len(all_executable)}个按钮')
        for i, bid in enumerate(all_executable):
            if i > 0:
                QTimer.singleShot(1000 * i, lambda b=bid: self._execute_button(b))
            else:
                self._execute_button(bid)

    def stop_sc(self):
        """耗时的指令手动中止方法"""
        # 首先防止重复按下中止键
        self.stop_pushButton.setEnabled(False)  # 禁用停止按钮
        # 检查是否有正在执行的线程
        if len(self.sc_threads) == 0:
            self.update_run_info('没有正在执行的指令', 'WARNING')
            self.stop_pushButton.setEnabled(True)
            return
        # 如果有，检查线程字典self.sc_threads，将所有线程结束
        for thread in self.sc_threads:
            # 检查是否有tool
            if 'tool' in self.sc_threads[thread]:
                # 检查tool是否是ssh_tools.SSHTools类型
                if type(self.sc_threads[thread]['tool']) == ssh_tools.SSHTools:
                    # 检查是否有连接，如果有连接，发送中止信号，设置传输位=0
                    if self.sc_threads[thread]['tool'].is_connected():
                        self.sc_threads[thread]['tool'].send_command_interactive(chr(3))
                        self.sc_threads[thread]['tool'].transfer_stat = 0
                        self.sc_threads[thread]['tool'].win_tool.transfer_stat = 0
                elif type(self.sc_threads[thread]['tool']) == windows_tools.WindowsTools:
                    self.sc_threads[thread]['tool'].transfer_stat = 0
            else:
                continue
        self.update_run_info('已发送中止请求，请等待')
        self.stop_pushButton.setEnabled(True)

    def clean_linux_print(self):
        # 清屏：终端模式下清空终端，否则清空服务器回显区
        if hasattr(self, 'terminal_widget'):
            self.terminal_widget.clear_terminal()
            self.update_run_info("终端已清空")
        else:
            self.linux_print_browser.clear()
            self.update_run_info(f"服务器回显区已清空")

    def get_default_path(self):
        # 获取可执行文件（.exe）本身所在的路径，不包含自己的名称
        if getattr(sys, 'frozen', False):
            # 打包后的环境：sys.executable指向.exe文件
            executable_path = sys.executable
        else:
            # 未打包的环境：使用原来的__file__
            executable_path = os.path.realpath(__file__)
        # 获取可执行文件所在的目录
        current_path = os.path.dirname(executable_path)
        # 格式化路径全部左斜
        current_path = current_path.replace('\\', '/')
        return current_path

    def save_config(self):
        """菜单-保存"""
        self.save_config_to(self.default_config_path)

    def save_config_to(self, path):
        """保存功能调用，如果点击菜单-另存为按钮来调用时，传入的是False，弹出对话框"""
        if not path:
            from utils.qt_dialog_tools import save_file_dialog
            file_path = save_file_dialog(
                self,
                title="另存为配置",
                default_name="自定义配置",
                suffix="json",
                file_filter="JSON Files (*.json)"
            )
            if not file_path:
                self.update_run_info(f"另存为配置 取消")
                return
        else:
            file_path = path
        # 获取所有配置
        cfg_dic = {}
        server_count = 1
        button_count = 1
        for server in self.servers_cfg:
            cfg_dic[f'服务器{server_count}'] = server
            server_count += 1
        # 按分组顺序保存按钮配置，每个按钮配置中包含"位置"和"分组"字段
        for gname in self._group_order:
            for i, button_id in enumerate(self._groups[gname]['buttons']):
                button_config = self.sc_buttons[button_id]['config'].copy()
                button_config['位置'] = i + 1
                button_config['分组'] = gname
                cfg_dic[f'快捷按钮{button_count}'] = button_config
                button_count += 1
        if len(self.commands) != 0:
            cfg_dic['指令'] = self.commands
        # 保存日志配置
        # 如果配置文件已存在，读取原有的日志级别配置并保留
        existing_log_cfg = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    old_cfg = json.load(f)
                    if '日志配置' in old_cfg:
                        existing_log_cfg = old_cfg['日志配置']
            except Exception:
                pass
        
        # 构建新的日志配置
        new_log_cfg = {
            '文件日志': self.log_file_checkBox.isChecked()
        }
        # 如果已有级别配置，保留；否则设置默认值（DEBUG=False，其他=True）
        if 'DEBUG' in existing_log_cfg:
            new_log_cfg['DEBUG'] = existing_log_cfg['DEBUG']
            new_log_cfg['INFO'] = existing_log_cfg.get('INFO', True)
            new_log_cfg['WARNING'] = existing_log_cfg.get('WARNING', True)
            new_log_cfg['ERROR'] = existing_log_cfg.get('ERROR', True)
        else:
            new_log_cfg['DEBUG'] = False
            new_log_cfg['INFO'] = True
            new_log_cfg['WARNING'] = True
            new_log_cfg['ERROR'] = True
        
        cfg_dic['日志配置'] = new_log_cfg

        # 写入到json文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cfg_dic, f, ensure_ascii=False, indent=4)
            self.update_run_info(f"已保存配置到{os.path.abspath(file_path)}")
        except Exception as e:
            self.update_run_info(f"保存配置失败: {str(e)}", 'WARNING')

    def load_sc_config(self, path):
        """启动时如果有默认配置会调用，传入默认配置路径，手动点的时候传入的是False，弹出对话框"""
        if not path:
            from utils.qt_dialog_tools import open_file_dialog
            files = open_file_dialog(
                self,
                title="加载快捷按钮配置",
                file_filter="JSON Files (*.json)"
            )
            if not files:
                self.update_run_info('批量添加快捷按钮 取消')
                return
            file_path = files[0]
        else:
            file_path = path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 将内容中的\替换为/
                processed_content = content.replace("\\", "/")
                # 解析处理后的内容
                data = json.loads(processed_content)
                # 确保是字典类型
                if not isinstance(data, dict):
                    raise ValueError("配置文件格式错误：不是字典类型")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            self.update_run_info(f"配置文件解析失败: {str(e)}，使用空配置", 'WARNING')
            return
        # 先收集所有快捷按钮配置，按分组和位置排序
        sc_buttons_list = []
        for key in data:
            if '快捷按钮' in key:
                button_config = data[key]
                group_name = button_config.get('分组', '默认分组')
                position = button_config.get('位置', 99999)
                sc_buttons_list.append((group_name, position, button_config))

        # 先按分组名排序（保证分组创建顺序），再按位置排序
        sc_buttons_list.sort(key=lambda x: (x[0], x[1]))
        for group_name, position, button_config in sc_buttons_list:
            button_config_clean = button_config.copy()
            if '位置' in button_config_clean:
                del button_config_clean['位置']
            self.add_button(button_config_clean)
        
        for key in data:
            if '服务器' in key:
                continue
            elif '快捷按钮' in key:
                pass  # 已经处理过了
            elif '指令' in key:
                for cmd in data[key]:  # data[key]=['top','pwd']
                    self.commands.append(cmd)
                self.update_run_info(f"批量添加指令 成功，来自{file_path}")
            elif key == '日志配置':
                log_cfg = data[key]
                if log_cfg.get('文件日志', False):
                    self.log_file_checkBox.setChecked(True)
                else:
                    self.log_file_checkBox.setChecked(False)
                # 读取日志级别配置（如果有）
                for level in self._log_level_config:
                    if level in log_cfg:
                        self._log_level_config[level] = log_cfg[level]
            elif key == '按钮顺序':  # 旧版本的key，忽略
                pass
            else:
                self.update_run_info(f'{key}无法识别的数据类型', 'WARNING')
        self.update_run_info(f"批量添加快捷按钮 成功，来自{file_path}")
        # 加载完成后默认选中第一个分组
        if self.group_tabWidget.count() > 0:
            self.group_tabWidget.setCurrentIndex(0)

    def load_server_config(self, path):
        """启动时如果有默认配置会调用，传入默认配置路径，手动点的时候传入的是False，弹出对话框"""
        if not path:  # 手动点的情况
            from utils.qt_dialog_tools import open_file_dialog
            files = open_file_dialog(
                self,
                title="加载服务器配置",
                file_filter="JSON Files (*.json)"
            )
            if not files:
                self.update_run_info('批量添加服务器 取消')
                return
            file_path = files[0]
        else:
            file_path = path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 将内容中的\替换为/
                processed_content = content.replace("\\", "/")
                # 解析处理后的内容
                data = json.loads(processed_content)
                # 确保是字典类型
                if not isinstance(data, dict):
                    raise ValueError("配置文件格式错误：不是字典类型")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            self.update_run_info(f"配置文件解析失败: {str(e)}，使用空配置", 'WARNING')
            return
        for key in data:
            if '服务器' in key:
                self.servers_cfg.append(data[key])
            else:
                continue
        self.update_run_info(f"批量添加服务器 成功，来自{file_path}")

    def is_config_changed(self, path):
        if not os.path.exists(path):
            file_cfg = {}

        # 读取文件中的配置
        try:
            with open(path, 'r', encoding='utf-8') as f:
                file_cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            file_cfg = {}

        # 生成当前界面中的配置
        current_cfg = {}
        server_count = 1
        button_count = 1
        for server in self.servers_cfg:
            current_cfg[f'服务器{server_count}'] = server
            server_count += 1
        # 按分组顺序生成按钮配置
        for gname in self._group_order:
            for i, button_id in enumerate(self._groups[gname]['buttons']):
                btn_cfg = self.sc_buttons[button_id]['config'].copy()
                btn_cfg['位置'] = i + 1
                btn_cfg['分组'] = gname
                current_cfg[f'快捷按钮{button_count}'] = btn_cfg
                button_count += 1
        if len(self.commands) != 0:
            current_cfg['指令'] = self.commands
        # 加入日志配置状态
        # 如果文件中已有日志级别配置，保留；否则用内存中的配置
        current_log_cfg = {
            '文件日志': self.log_file_checkBox.isChecked()
        }
        if '日志配置' in file_cfg and 'DEBUG' in file_cfg['日志配置']:
            # 保留文件中的日志级别配置
            current_log_cfg['DEBUG'] = file_cfg['日志配置']['DEBUG']
            current_log_cfg['INFO'] = file_cfg['日志配置'].get('INFO', True)
            current_log_cfg['WARNING'] = file_cfg['日志配置'].get('WARNING', True)
            current_log_cfg['ERROR'] = file_cfg['日志配置'].get('ERROR', True)
        else:
            # 用内存中的配置（首次保存）
            current_log_cfg['DEBUG'] = self._log_level_config['DEBUG']
            current_log_cfg['INFO'] = self._log_level_config['INFO']
            current_log_cfg['WARNING'] = self._log_level_config['WARNING']
            current_log_cfg['ERROR'] = self._log_level_config['ERROR']
        current_cfg['日志配置'] = current_log_cfg

        # 直接比较两个字典是否完全相等
        return current_cfg != file_cfg

    def update_server_combobox(self):
        self.server_comboBox.clear()
        for server in self.servers_cfg:
            self.server_comboBox.addItem(server['服务器名称'], server)
        self.server_comboBox.setCurrentIndex(-1)

    def connect_server(self):
        if self.connect_pushButton.text() == '连接':
            if self.server_comboBox.currentIndex() == -1:
                self.update_run_info(f'请先选择服务器', 'WARNING')
                return
            self.connect_pushButton.setEnabled(False)
            self.server_comboBox.setEnabled(False)
            self.current_ssh['config'] = self.server_comboBox.currentData()

            # 创建一个ssh连接对象，给对象初始化属性
            ssh_tool = ssh_tools.SSHTools()
            # 初始化属性
            try:
                ssh_tool.ip = self.current_ssh['config']['IP']
                ssh_tool.port = self.current_ssh['config']['端口']
                ssh_tool.username = self.current_ssh['config']['用户名']
                ssh_tool.password = self.current_ssh['config']['密码']
            except Exception as e:
                self.update_run_info(f'请检查服务器ssh连接配置{e}', 'ERROR')
                self.connect_pushButton.setEnabled(True)
                self.server_comboBox.setEnabled(True)
                return

            def update_connect_button(data):
                """data[0]=text, data[1]=True"""
                self.connect_pushButton.setText(data[0])
                self.connect_pushButton.setEnabled(data[1])
                # 连接成功后切换终端模式
                if data[0] == '断开':
                    self._start_terminal_mode()

            # 封装指令发送和回显接收方法
            def current_ssh(echo_signal):
                c_result = ssh_tool.connect()
                if not c_result:
                    return False
                worker.info_signal.emit(('断开',True))
                g_result = ssh_tool.get_output_continue(timeout=float('inf'), echo_signal=echo_signal, raw=True)
                return g_result

            def on_worker_finished():
                update_connect_button(('连接',True))
                self.server_comboBox.setEnabled(True)
                # 退出终端模式
                self._stop_terminal_mode()
                self.update_run_info('退出终端模式')
                # 关闭文件浏览器
                if hasattr(self, 'file_browser'):
                    self.file_browser.set_ssh_tool(None)
                # 不要在worker里deleteLater自己，会被放到worker的线程中执行
                thread.quit()

            def on_thread_finished():
                worker.deleteLater()
                thread.deleteLater()
                self.current_ssh.clear()

            # 初始化worker
            worker = qthread_worker.OneClickWorker(current_ssh)
            worker.kwargs = {
                "echo_signal": worker.echo_signal
                }

            # 初始化线程
            thread = QThread()

            # 将worker移动到线程中
            worker.moveToThread(thread)

            # 绑定信号槽（连接过程日志通过 logger 自动进入运行信息面板）
            worker.echo_signal.connect(self._on_terminal_output)
            worker.info_signal.connect(update_connect_button)
            worker.finished.connect(on_worker_finished)

            # 绑定线程信号槽
            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    "tool": ssh_tool,
                    "task_connect": (thread, worker)
                }
            )

            thread.start()

        else:
            if not self.current_ssh['tool'].is_connected():
                self.connect_pushButton.setText('连接')
                self.connect_pushButton.setEnabled(True)
                self.server_comboBox.setEnabled(True)
                return
            # 初始化worker
            worker = qthread_worker.OneClickWorker(self.current_ssh['tool'].disconnect)

            # 初始化线程
            thread = QThread()

            # 将worker移动到线程中
            worker.moveToThread(thread)

            # 绑定信号槽（断连日志通过 logger 自动进入运行信息面板）
            worker.finished.connect(thread.quit)

            # 绑定线程信号槽
            thread.started.connect(worker.run_task)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    "task_disconnect": (thread, worker)
                }
            )
            thread.start()

    def open_cmd_manage_dialog(self):
        """打开指令管理对话框"""
        dlg = CmdManageDialog(commands=self.commands, parent=self)
        dlg.insert_cmd_signal.connect(self._insert_cmd_to_terminal)
        dlg.exec_()
        # 对话框关闭后，同步指令列表
        self.commands = dlg.get_all_commands()

    def _insert_cmd_to_terminal(self, cmd):
        """插入指令到终端（直接发送给服务器，不自动回车）"""
        if not (self.connect_pushButton.text() == '断开' and
                'tool' in self.current_ssh and self.current_ssh['tool']):
            self.update_run_info('请先建立SSH连接', 'WARNING')
            return
        try:
            channel = self.current_ssh['tool'].channel
            if channel and channel.active:
                channel.send(cmd)
        except Exception as e:
            self.update_run_info(f'发送指令失败: {e}', 'ERROR')

    def closeEvent(self, event):
        """
        重写窗口关闭事件，弹出三按钮确认框
        """
        if self.is_config_changed(self.default_config_path):
            # 创建消息框实例
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("保存确认")
            msg_box.setText("当前配置未保存，是否保存更改后退出？")
            msg_box.setIcon(QMessageBox.Icon.Question)

            # 添加三个按钮 (保存 / 不保存 / 取消)
            btn_save = msg_box.addButton("保存并退出", QMessageBox.ButtonRole.ActionRole)
            btn_discard = msg_box.addButton("不保存退出", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

            # 设置默认选中按钮（可选，比如默认选中"取消"比较安全）
            msg_box.setDefaultButton(btn_cancel)

            # 弹出对话框并等待用户点击
            msg_box.exec_()

            # 判断用户点击了哪个按钮
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == btn_save:
                # --- 点击了"保存" ---
                self.save_config()
                event.accept()
            elif clicked_btn == btn_discard:
                # --- 点击了"不保存" ---
                event.accept()
            else:
                # --- 点击了"取消" 或 关闭了对话框 ---
                event.ignore()
        else:
            # 配置没变动，直接退出
            event.accept()

    def show_help_dialog(self):
        """显示帮助文档对话框"""
        help_dialog = HelpDialog(self)
        help_dialog.exec_()


if __name__ == '__main__':
    pass
