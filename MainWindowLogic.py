import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtWidgets import (QDialog, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
                             QMenu, QMessageBox, QMainWindow, QTabBar, QToolButton,
                             QTabWidget, QCheckBox, QScrollArea, QInputDialog, QLineEdit)

from UI import MainWindow
from utils import ssh_tools, windows_tools, qthread_worker
import json
import datetime
from utils.logger import log_progress
from dialogs import (SendCMDDialog, SendCMD2Dialog, SendFilesDialog, GetFilesDialog, CopyFilesDialog,
                     SetServerDialog, ResourceMonitorDialog1, ResourceMonitorDialog2,
                     WeakNetDialog1, WeakNetControlDialog, HelpDialog, ServerCheckDialog,
                     ServerCheckRunDialog, CmdManageDialog, NotepadDialog, NotepadEditWindow)

class ScrollSafeTabBar(QTabBar):
    """标签过多时，左右滚动箭头压住最后一个标签的修复。

    Qt 的 QTabBar 在标签溢出时会把滚动按钮直接叠在最后半个标签上，
    标签文字/关闭按钮被箭头遮住。这里在绘制完标签后用底色覆盖箭头占位区，
    使溢出的标签被干净裁边，箭头落在空白条上。
    """

    def _scroller_width(self):
        """当前可见滚动按钮的总宽度（没有溢出时为 0）"""
        total = 0
        for btn in self.findChildren(QToolButton):
            if btn.isVisible():
                total += btn.width()
        return total

    def paintEvent(self, event):
        super().paintEvent(event)
        gutter = self._scroller_width()
        if gutter <= 0:
            return
        painter = QtGui.QPainter(self)
        painter.fillRect(self.width() - gutter, 0, gutter, self.height(),
                         self.palette().color(QtGui.QPalette.Window))


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

        # 窗口标题只显示软件名（任务栏同此）；版本号在"关于"对话框中展示
        self.setWindowTitle("OneClick")

        # 设置窗口图标（任务栏和标题栏显示）
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

        # 菜单分类分隔线：命令类 | 文件传输类 | 监控检查类（记事本在末尾自成一类）
        self.menu.insertSeparator(self.send_file_action)       # 命令类 / 文件传输类
        self.menu.insertSeparator(self.resource_monitor_action)  # 文件传输类 / 监控检查类

        # 记事本菜单项（加在菜单末尾；UI 中其前已有一条分隔线，使其自成一类）
        self.notepad_action = QAction("记事本", self)
        self.menu.addAction(self.notepad_action)
        self.notepad_action.triggered.connect(self.notepad_dialog)

        self.edit_server_action.triggered.connect(self.server_cfg_dialog)  # 服务器列表的编辑框

        self.help_action.triggered.connect(self.show_help_dialog)  # 显示帮助文档

        # 关于菜单项：版本号只在关于对话框中展示，窗口标题/任务栏只显示软件名
        from PyQt5.QtWidgets import QAction
        self.about_action = QAction("关于", self)
        self.menu_4.addAction(self.about_action)
        self.about_action.triggered.connect(self.show_about_dialog)

        # 创建按钮逻辑
        self.stop_pushButton.clicked.connect(self.stop_sc)
        self.clean_pushButton.clicked.connect(self.clean_linux_print)

        # ---- 替换 scrollArea_2 为 QTabWidget（分组标签页） ----
        self.group_tabWidget = QTabWidget(self.centralwidget)
        # 先换标签栏，避免标签溢出时滚动箭头压住标签（须在信号接线之前）
        self.group_tabWidget.setTabBar(ScrollSafeTabBar(self.group_tabWidget))
        self.group_tabWidget.setTabsClosable(True)
        self.group_tabWidget.setMovable(True)  # 允许拖拽排序
        self.group_tabWidget.tabCloseRequested.connect(self.on_tab_close_requested)
        self.group_tabWidget.tabBarDoubleClicked.connect(self.on_tab_bar_double_clicked)
        self.group_tabWidget.tabBar().tabMoved.connect(self.on_tab_moved)
        # 标签栏右键菜单
        self.group_tabWidget.tabBar().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_tabWidget.tabBar().customContextMenuRequested.connect(self.on_tab_bar_context_menu)
        # 左上角"+"新建分组按钮（用容器包装，按钮靠右贴紧标签）
        self.add_group_btn = QPushButton("+", self.centralwidget)
        self.add_group_btn.setFixedSize(24, 24)
        self.add_group_btn.setToolTip("新建分组")
        self.add_group_btn.clicked.connect(self.add_new_group)
        add_btn_container = QWidget(self.centralwidget)
        add_btn_layout = QHBoxLayout(add_btn_container)
        add_btn_layout.setContentsMargins(0, 0, 0, 0)
        add_btn_layout.addStretch()
        add_btn_layout.addWidget(self.add_group_btn)
        self.group_tabWidget.setCornerWidget(add_btn_container, QtCore.Qt.Corner.TopLeftCorner)
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
        self._notepad_windows = {}  # button_id -> NotepadEditWindow（已打开的笔记窗口，去重用）

        # 将运行中的指令线程存入字典
        self.sc_threads = {}
        self.thread_count = 0

        # 用于存放服务器配置信息的列表
        self.servers_cfg = []  # [{"服务器名称": ,"IP": ,"端口": ,"用户名": ,"密码": },...]

        # 多终端连接管理：conn_id -> 连接信息
        # conn = {id, config, tool, terminal, page, combo, btn, thread, worker, state, closing}
        #   page : 标签页容器（内含本标签独立的服务器下拉框 + 连接/断开按钮 + 终端）
        #   state: 'idle'(未发起连接) / 'connecting' / 'connected' / 'disconnected'
        self.connections = {}
        self.active_conn_id = None
        self._conn_seq = 0
        self._closing_workers = []  # 关闭标签时后台断开的 (thread, worker)，防GC

        # 双击打开的远程文件编辑会话：本地临时路径 -> 会话信息
        # {local_path: {'conn_id', 'remote_path', 'base_mtime', 'base_size',
        #               'last_mtime', 'last_size', 'synced', 'uploading'}}
        # base_*: 上次已回传（或已判定失败不再重试）的 mtime/size 基线
        # last_*: 上次轮询看到的 mtime/size，用于防抖（连续两轮一致才回传）
        self._edit_sessions = {}
        self._edit_watch_timer = QtCore.QTimer(self)
        self._edit_watch_timer.setInterval(2000)  # 2秒轮询一次本地临时文件
        self._edit_watch_timer.timeout.connect(self._poll_edit_sessions)

        # 发送指令、保存指令、删除指令按钮逻辑
        self.commands = []  # 新格式：[{'name': 'xxx', 'content': 'xxx'}, ...]
        # 配置文件的默认路径
        self.default_config_path = self.get_default_path() + '/' + 'config.json'

        # 日志系统：OneClick.py 入口已统一初始化好，这里直接连接 Qt 信号
        # setup_logging() 内部有防重复调用保护，这里再调一次只是为了拿到 emitter
        from utils.logger import (
            setup_logging, get_logger, set_file_logging, set_file_log_level,
            log_progress, set_panel_level,
            set_file_backup_count,
        )
        import logging as _logging
        self._log_emitter = setup_logging()  # OneClick.py 已初始化，返回已有的 emitter
        self.logger = get_logger("MainWindow")

        # 连接 Qt 日志信号（所有模块的 logger.info() 都会自动到这里）
        if self._log_emitter is not None:
            self._log_emitter.log_signal.connect(self._on_qt_log_message)
            self._log_emitter.progress_signal.connect(self._on_qt_progress)

        # 日志配置：读取默认配置文件并应用
        self._log_config = {
            '文件日志': True,
            '文件日志级别': 'INFO',
            '面板日志级别': 'INFO',
            '文件保留个数': 5,
        }
        _level_map = {'DEBUG': _logging.DEBUG, 'INFO': _logging.INFO,
                      'WARNING': _logging.WARNING, 'ERROR': _logging.ERROR}
        if os.path.exists(self.default_config_path):
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    cfg_data = json.load(f)
                    if '日志配置' in cfg_data:
                        log_cfg = cfg_data['日志配置']
                        if '文件日志' in log_cfg:
                            self._log_config['文件日志'] = log_cfg['文件日志']
                        if '文件日志级别' in log_cfg:
                            self._log_config['文件日志级别'] = log_cfg['文件日志级别']
                        if '面板日志级别' in log_cfg:
                            self._log_config['面板日志级别'] = log_cfg['面板日志级别']
                        if '文件保留个数' in log_cfg:
                            self._log_config['文件保留个数'] = log_cfg['文件保留个数']
            except Exception:
                pass

        # 应用配置到 logger
        set_file_logging(self._log_config['文件日志'])
        set_file_log_level(_level_map.get(self._log_config['文件日志级别'], _logging.INFO))
        set_panel_level(_level_map.get(self._log_config['面板日志级别'], _logging.INFO))
        set_file_backup_count(self._log_config['文件保留个数'])

        # 选项菜单（动态插入到"帮助"之前）
        self.settings_menu = QtWidgets.QMenu("选项", self)
        self.open_program_dir_action = self.settings_menu.addAction("打开程序目录")
        self.open_program_dir_action.triggered.connect(self.open_program_dir)
        self.settings_menu.addSeparator()
        self.log_settings_action = self.settings_menu.addAction("日志设置")
        self.log_settings_action.triggered.connect(self.open_log_settings)
        self.settings_menu.addSeparator()
        self.import_append_action = self.settings_menu.addAction("导入配置（追加）")
        self.import_append_action.triggered.connect(lambda: self.import_config_dialog(append=True))
        self.import_overwrite_action = self.settings_menu.addAction("导入配置（覆盖）")
        self.import_overwrite_action.triggered.connect(lambda: self.import_config_dialog(append=False))
        self.settings_menu.addSeparator()
        self.export_action = self.settings_menu.addAction("导出配置")
        self.export_action.triggered.connect(self.export_config_dialog)
        # 找到 menubar 中"帮助"菜单的位置，插在它前面
        menubar = self.menuBar()
        actions = menubar.actions()
        for act in actions:
            if act.text() == "帮助":
                menubar.insertMenu(act, self.settings_menu)
                break
        else:
            menubar.addMenu(self.settings_menu)

        # ---- 三列布局改造：按钮区 | 文件区 | 终端区 ----
        # 用 QSplitter 水平分割，可拖动调整宽度
        from widgets.terminal_widget import TerminalEdit
        from widgets.file_browser_widget import FileBrowserWidget

        # 终端标签页：每个 SSH 连接一个标签，各标签独立一个 TerminalEdit
        self.terminal_tabs = QtWidgets.QTabWidget(self.centralwidget)
        # 同上：标签溢出时滚动箭头不压标签
        self.terminal_tabs.setTabBar(ScrollSafeTabBar(self.terminal_tabs))
        self.terminal_tabs.setTabsClosable(True)   # 标签带关闭按钮
        self.terminal_tabs.setMovable(True)        # 标签可拖动排序
        self.terminal_tabs.setDocumentMode(True)
        # 左上角"+"新建终端标签（样式与左侧分组标签页的"+"保持一致）
        self.new_terminal_btn = QtWidgets.QPushButton("+", self.terminal_tabs)
        self.new_terminal_btn.setFixedSize(24, 24)
        self.new_terminal_btn.setToolTip("新建终端")
        add_term_btn_container = QtWidgets.QWidget(self.terminal_tabs)
        add_term_btn_layout = QtWidgets.QHBoxLayout(add_term_btn_container)
        add_term_btn_layout.setContentsMargins(0, 0, 0, 0)
        add_term_btn_layout.addStretch()
        add_term_btn_layout.addWidget(self.new_terminal_btn)
        self.terminal_tabs.setCornerWidget(add_term_btn_container, QtCore.Qt.Corner.TopLeftCorner)
        self.file_browser = FileBrowserWidget(self.centralwidget)

        # 1. 左侧容器：仅快捷按钮区（运行信息区已移至底部通栏）
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
        left_layout.addWidget(self.left_top_widget)

        # 运行信息区（原 verticalLayout_3）从左栏取出，提升为底部通栏独立部件
        self.gridLayout_2.removeItem(self.verticalLayout_3)
        self.run_info_widget = QtWidgets.QWidget(self.centralwidget)
        run_info_layout = QtWidgets.QVBoxLayout(self.run_info_widget)
        run_info_layout.setContentsMargins(0, 0, 0, 0)
        run_info_layout.setSpacing(0)
        run_info_layout.addLayout(self.verticalLayout_3)
        # 压低运行信息文本框的默认最小高度，使底部通栏的 14:1 初始比例真正生效
        self.run_info_browser.setMinimumHeight(40)

        # 2. 右侧容器：终端区（上）+ 服务器选择行（下）
        self.right_column_widget = QtWidgets.QWidget(self.centralwidget)
        right_layout = QtWidgets.QVBoxLayout(self.right_column_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # 终端标题行（原 horizontalLayout_2）从 verticalLayout_2 取出
        self.verticalLayout_2.removeItem(self.horizontalLayout_2)
        right_layout.addLayout(self.horizontalLayout_2)
        right_layout.addWidget(self.terminal_tabs, 1)

        # 3. 主 splitter：左 | 中 | 右
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.centralwidget)
        self.main_splitter.addWidget(self.left_container)
        self.main_splitter.addWidget(self.file_browser)
        self.main_splitter.addWidget(self.right_column_widget)
        self.main_splitter.setStretchFactor(0, 1)  # 按钮区
        self.main_splitter.setStretchFactor(1, 1)  # 文件区
        self.main_splitter.setStretchFactor(2, 3)  # 终端区

        # 4. 外层垂直 splitter：上=三栏主区，下=运行信息通栏（10:1，可拖动）
        # 先移除 verticalLayout_2（已空）
        self.gridLayout_2.removeItem(self.verticalLayout_2)
        self.outer_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.centralwidget)
        self.outer_splitter.addWidget(self.main_splitter)
        self.outer_splitter.addWidget(self.run_info_widget)
        self.outer_splitter.setStretchFactor(0, 14)  # 三栏主区
        self.outer_splitter.setStretchFactor(1, 1)   # 运行信息
        # 外层 splitter 填满 gridLayout_2
        self.gridLayout_2.addWidget(self.outer_splitter, 0, 0, 2, 2)

        # "服务器回显" 标签改为 "终端"
        self.linux_print_label.setText("终端")

        # ---- 统一四个区域标题样式：加粗 + 统一高度 ----
        title_style = "font-weight: bold; font-size: 13px; padding: 4px 0;"
        for lbl in (self.label, self.run_info_label, self.linux_print_label):
            lbl.setStyleSheet(title_style)
        # 远程文件标题也统一样式
        self.file_browser.set_title_style(title_style)

        # 终端标签页信号：关闭标签、切换激活标签
        self.terminal_tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.terminal_tabs.currentChanged.connect(self._on_active_tab_changed)
        # 双击"已断开"的标签页可重连（tabBar 没有双击信号，用事件过滤器）
        self.terminal_tabs.tabBar().installEventFilter(self)
        # "+"按钮：新建一个空白终端标签（服务器选择和连接在标签页内部完成）
        self.new_terminal_btn.clicked.connect(lambda: self._new_terminal_tab())

        # 文件浏览器信号
        self.file_browser.upload_requested.connect(self._fb_upload)
        self.file_browser.download_requested.connect(self._fb_download)
        self.file_browser.open_file_requested.connect(self._fb_open_file)  # 双击远程文件→下载打开
        self.file_browser.open_with_requested.connect(self._fb_open_with)  # 右键"打开方式..."→选择程序打开

        # 指令管理按钮：放在终端标题行"清屏"按钮旁（指令是全局的，不属于任何标签）
        self.cmd_manage_button = QtWidgets.QPushButton("指令管理", self.centralwidget)
        self.cmd_manage_button.setObjectName("cmd_manage_button")
        self.cmd_manage_button.clicked.connect(self.open_cmd_manage_dialog)
        self.cmd_manage_button.setMinimumWidth(120)
        self.cmd_manage_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        # 插到"清屏"按钮前面（清屏是标题行最后一个控件）
        self.horizontalLayout_2.insertWidget(
            self.horizontalLayout_2.count() - 1, self.cmd_manage_button)

        # 如果有默认配置文件，则获取
        if os.path.exists(self.default_config_path):
            self.update_run_info('存在默认配置文件，开始添加服务器和快捷按钮')
            self._loading_config = True
            try:
                self.load_server_config(self.default_config_path)
                self.load_sc_config(self.default_config_path)
            finally:
                self._loading_config = False

        # 如果没有任何分组，则创建默认分组
        if not self._groups:
            self.add_group_tab("默认分组")
        # 重建所有终端标签页的服务器下拉框；若终端区还没有标签，建一个空白标签
        self.update_server_combobox()
        if self.terminal_tabs.count() == 0:
            self._new_terminal_tab()
        self.update_run_info("OneClick 启动成功")

        # 延迟设置 splitter 初始比例：等窗口最大化、真实尺寸确定后再设
        QtCore.QTimer.singleShot(50, self._init_splitter_sizes)

    def _init_splitter_sizes(self):
        """窗口显示后设置 splitter 初始分配比例"""
        # 外层垂直 splitter：三栏主区 14/15，运行信息通栏 1/15
        total_h = self.outer_splitter.height()
        info_h = max(total_h // 15, 1)
        self.outer_splitter.setSizes([total_h - info_h, info_h])

        # 主水平 splitter：快捷按钮 : 远程文件 : 终端 = 1 : 1 : 3（比例保持不变）
        total_w = self.main_splitter.width()
        w1 = total_w // 5
        self.main_splitter.setSizes([w1, w1, total_w - w1 * 2])

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
            self._save_config_auto()
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
        '记事本':           ('#3F51B5', '#303F9F'),   # 靛蓝色
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
        self._save_config_auto()
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
            self._save_config_auto()

    def on_tab_moved(self, from_index, to_index):
        """标签页拖拽移动后，同步更新 _group_order 和各分组的 tab_index"""
        # 按当前标签页顺序重建 _group_order
        new_order = []
        for i in range(self.group_tabWidget.count()):
            gname = self.group_tabWidget.tabText(i)
            new_order.append(gname)
            if gname in self._groups:
                self._groups[gname]['tab_index'] = i
        self._group_order = new_order
        self._save_config_auto()

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
        self._save_config_auto()

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
            '记事本': self.open_notepad,
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
        self._save_config_auto()

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
        self._save_config_auto()

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
        """发送指令并回显打印到界面（自动新建一个终端标签页显示回显，结束不自动关）"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 自动新建一个回显专用标签页显示回显（结束后保留，由用户手动关闭）。
        # 该标签隐藏服务器下拉框和连接按钮：回显未结束时不能再于此标签连终端，
        # 否则同一终端区既跑回显又跑交互终端，输出会彻底混在一起
        conn = self._new_terminal_tab(title=button_name, echo_only=True)
        btn_cfg = self.sc_buttons[button_id]['config']

        # 初始化SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = btn_cfg['IP']
            ssh_tool.port = btn_cfg['端口']
            ssh_tool.username = btn_cfg['用户名']
            ssh_tool.password = btn_cfg['密码']
        except Exception as e:
            self.update_run_info(f'<{button_name}> 执行失败:{e}', 'ERROR')
            self.set_button_executing(button_id, False)
            return

        # 封装指令发送和回显接收方法
        def send_cmd_and_receive_echo(cmd, echo_signal):
            # 标签已被用户关闭则放弃执行（不再白白建连接）
            if conn['id'] not in self.connections:
                return False
            c_result = ssh_tool.connect()
            if not c_result:
                return False
            # 连接期间标签被关闭：不再发送指令，直接断开
            if conn['id'] not in self.connections:
                ssh_tool.disconnect()
                return False
            ssh_tool.send_command_interactive(cmd)
            g_result = ssh_tool.get_output_continue(echo_signal=echo_signal)
            ssh_tool.disconnect()
            return g_result

        def on_worker_finished(result, c=conn):
            if c['id'] not in self.connections:
                # 回显标签被用户关闭，会话随标签终止
                self.update_run_info(f'<{button_name}> 已终止（回显标签被关闭）', 'WARNING')
            elif result:
                self.update_run_info(f'<{button_name}> 执行成功')
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
            self.set_button_executing(button_id, False)
            # 回显标签保留，由用户手动关闭
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

        # 回显路由到自动新建的标签页（若标签被用户提前关闭则丢弃）
        def route_echo(text, c=conn):
            if c['id'] in self.connections:
                c['terminal'].append_output(text)

        # 绑定信号槽
        worker.echo_signal.connect(route_echo)
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
        # 记录回显标签与会话的关联：关闭该标签时终止对应回显会话
        conn['sc_thread'] = thread_name

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
        work_dir = sc_cfg.get('临时文件路径', '')

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
        work_dir = sc_cfg.get('临时文件路径', '')

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

    def open_notepad(self, button_id):
        """点击记事本按钮：打开该篇笔记的编辑窗口（已打开则提到最前，不重复开窗）"""
        if button_id not in self.sc_buttons:
            return
        existing = self._notepad_windows.get(button_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        win = NotepadEditWindow(button_id, self)
        self._notepad_windows[button_id] = win
        win.show()

    def _on_notepad_closed(self, button_id):
        self._notepad_windows.pop(button_id, None)

    def notepad_dialog(self, button_id=None):
        """主窗口侧：新建记事本 / 右键编辑记事本名称（模态配置框，只填名称）"""
        np_dlg = NotepadDialog(parent=self)
        if button_id:
            np_dlg.edit_sc(button_id)
        if np_dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if button_id:
                button_text = self.sc_buttons[button_id]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}> 记事本名称编辑成功')
            else:
                if f"button_{self.btn_count}" in self.sc_buttons:
                    button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                    self.update_run_info(f'<{button_text}> 记事本创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑记事本名称')
            else:
                self.update_run_info('取消创建记事本')

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

    # ---------- 多终端连接管理 ----------

    def _active_conn(self):
        """当前激活标签对应的连接（无则 None）"""
        return self.connections.get(self.active_conn_id)

    def _conn_by_index(self, index):
        """按标签页索引找连接（标签页的 widget 是 page 容器）"""
        widget = self.terminal_tabs.widget(index)
        for conn in self.connections.values():
            if conn['page'] is widget:
                return conn
        return None

    def _select_server_combo(self, combo, target):
        """让指定下拉框指向 target 配置对应的服务器（严格匹配防同名误中）"""
        idx = -1
        if target is not None:
            for i, srv in enumerate(self.servers_cfg):
                if (srv.get('服务器名称') == target.get('服务器名称')
                        and srv.get('IP') == target.get('IP')
                        and srv.get('端口') == target.get('端口')
                        and srv.get('用户名') == target.get('用户名')):
                    idx = i
                    break
        combo.setCurrentIndex(idx)

    def _fill_conn_combo(self, conn):
        """重建某个标签页的服务器下拉框（服务器列表变化时调用）"""
        combo = conn['combo']
        # 记住当前选择，重建后恢复
        old_sel = combo.currentData()
        combo.clear()
        for server in self.servers_cfg:
            combo.addItem(server['服务器名称'], server)
        if conn['state'] in ('connected', 'connecting'):
            # 已绑定的标签：下拉指向自己的服务器
            self._select_server_combo(combo, conn['config'])
        else:
            # 未连接的标签：尽量保持用户刚才选中的服务器
            self._select_server_combo(combo, old_sel)

    def _sync_conn_widgets(self, conn):
        """同步某个标签页自己的 连接/断开按钮 和 服务器下拉框 状态"""
        if conn.get('echo_only'):
            return  # 回显专用标签：连接条已隐藏，无需同步
        btn = conn['btn']
        combo = conn['combo']
        state = conn['state']
        if state == 'connected':
            btn.setText('断开')
            btn.setEnabled(True)
            combo.setEnabled(False)   # 已连接：服务器已绑定，不允许改选
        elif state == 'connecting':
            btn.setText('连接中...')
            btn.setEnabled(False)
            combo.setEnabled(False)
        else:
            # idle / disconnected：可选服务器再连接
            btn.setText('重连' if state == 'disconnected' else '连接')
            btn.setEnabled(True)
            combo.setEnabled(True)

    def _sync_active_side_ui(self):
        """同步随激活标签变化的区域：文件浏览器"""
        conn = self._active_conn()
        if (hasattr(self, 'file_browser') and conn is not None
                and conn['state'] == 'connected' and conn.get('tool') is not None):
            self.file_browser.set_ssh_tool(conn['tool'])
        elif hasattr(self, 'file_browser'):
            self.file_browser.set_ssh_tool(None)

    def _set_conn_state(self, conn, state):
        """更新连接状态、标签页标题和标签内按钮/下拉框"""
        conn['state'] = state
        index = self.terminal_tabs.indexOf(conn['page'])
        if index >= 0:
            name = conn['config'].get('服务器名称', '?')
            if state == 'connected':
                self.terminal_tabs.setTabText(index, name)
            elif state == 'connecting':
                self.terminal_tabs.setTabText(index, f"{name}（连接中）")
            elif state == 'disconnected':
                self.terminal_tabs.setTabText(index, f"{name}（已断开）")
            # idle 不改标题（保持"新终端"或快捷按钮指定的名字）
        self._sync_conn_widgets(conn)
        if conn['id'] == self.active_conn_id:
            self._sync_active_side_ui()

    def _on_active_tab_changed(self, index):
        """切换激活标签：文件浏览器跟随该标签的连接"""
        conn = self._conn_by_index(index)
        self.active_conn_id = conn['id'] if conn is not None else None
        self._sync_active_side_ui()

    def _on_tab_close_requested(self, index):
        conn = self._conn_by_index(index)
        if conn is not None:
            self._remove_connection(conn)
        # 最后一个标签也被关掉时自动补一个空白标签：
        # 标签区清空后 QTabWidget 的角部"+"会随标签栏一起消失，
        # 不补一个就再也没有入口能打开终端了
        if self.terminal_tabs.count() == 0:
            self._new_terminal_tab()

    def eventFilter(self, obj, event):
        # 双击"已断开"的标签页标题 → 重连该标签（tabBar 没有双击信号，用事件过滤器）
        if (obj is self.terminal_tabs.tabBar()
                and event.type() == QtCore.QEvent.Type.MouseButtonDblClick):
            index = self.terminal_tabs.tabBar().tabAt(event.pos())
            if index >= 0:
                conn = self._conn_by_index(index)
                if conn is not None and conn['state'] == 'disconnected':
                    self._reconnect_conn(conn)
                return True
        return super().eventFilter(obj, event)

    def _send_to_conn(self, conn, text):
        """终端按键：发送给该连接的 channel"""
        if conn['state'] != 'connected':
            return
        try:
            channel = conn['tool'].channel
            if channel and channel.active:
                # 前后各留一条：若崩溃发生在 channel.send 内部（C 扩展层），
                # 只有第一条能落盘，据此可精确定位崩溃点
                self.logger.debug("终端发送按键: %r", text)
                channel.send(text)
                self.logger.debug("终端按键发送完成: %r", text)
        except Exception as e:
            self.logger.exception("终端按键发送异常: %r", text)
            self.update_run_info(f'发送按键失败: {e}', 'ERROR')

    def _paste_to_conn(self, conn, text):
        """终端粘贴：发送给该连接的 channel"""
        if conn['state'] != 'connected':
            return
        try:
            channel = conn['tool'].channel
            if channel and channel.active:
                self.logger.debug("终端粘贴发送: %d 字符", len(text))
                # 分块发送避免一次发太多
                chunk_size = 4096
                for i in range(0, len(text), chunk_size):
                    channel.send(text[i:i+chunk_size])
        except Exception as e:
            self.logger.exception("终端粘贴发送异常: %d 字符", len(text))
            self.update_run_info(f'粘贴发送失败: {e}', 'ERROR')

    def _resize_conn_pty(self, conn, cols, rows):
        """终端尺寸变化：通知该连接的远端调整 pty"""
        if conn['state'] != 'connected':
            return
        try:
            channel = conn['tool'].channel
            if channel and channel.active:
                self.logger.debug("终端尺寸变化: %dx%d", cols, rows)
                channel.resize_pty(width=cols, height=rows)
        except Exception as e:
            self.logger.exception("调整终端尺寸异常: %dx%d", cols, rows)
            self.update_run_info(f'调整终端大小失败: {e}', 'ERROR')

    def _spawn_disconnect(self, tool):
        """后台线程执行 disconnect，不阻塞 UI（用于断开/关标签）"""
        worker = qthread_worker.OneClickWorker(tool.disconnect)
        thread = QThread()
        worker.moveToThread(thread)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run_task)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _purge():
            try:
                self._closing_workers.remove((thread, worker))
            except ValueError:
                pass
        thread.finished.connect(_purge)
        self._closing_workers.append((thread, worker))
        thread.start()

    def _new_terminal_tab(self, title=None, echo_only=False):
        """新建一个终端标签页（idle 状态，未发起连接）。
        标签页内含本标签独立的服务器下拉框、连接/断开按钮和终端显示区。
        title: 标签标题（默认"新终端"）；快捷按钮回显标签会传入按钮名。
        echo_only: True 表示回显专用标签——隐藏服务器下拉框和连接按钮，
        不允许在回显未结束时于同一标签再连其他终端，避免相互干扰。
        """
        from widgets.terminal_widget import TerminalEdit

        self._conn_seq += 1
        conn = {
            'id': self._conn_seq,
            'config': {},   # 连接建立时从本标签下拉框取配置快照
            'tool': None,
            'thread': None,
            'worker': None,
            'state': 'idle',
            'closing': False,
            'echo_only': echo_only,
        }

        # 标签页容器：上=服务器下拉+连接按钮，下=终端
        page = QtWidgets.QWidget(self.terminal_tabs)
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        # 顶部条包进独立容器：回显标签可整体隐藏
        top_widget = QtWidgets.QWidget(page)
        top_bar = QtWidgets.QHBoxLayout(top_widget)
        top_bar.setContentsMargins(4, 3, 4, 3)
        top_bar.setSpacing(4)
        combo = QtWidgets.QComboBox(page)
        combo.setMinimumWidth(220)
        combo.setToolTip("选择要连接的服务器")
        btn = QtWidgets.QPushButton('连接', page)
        btn.setFixedWidth(90)
        top_bar.addWidget(combo)
        top_bar.addWidget(btn)
        top_bar.addStretch()
        page_layout.addWidget(top_widget)
        terminal = TerminalEdit(page)
        page_layout.addWidget(terminal, 1)

        if echo_only:
            # 回显专用标签：整体隐藏顶部连接条（双保险：同时禁用两个控件）
            top_widget.hide()
            btn.setEnabled(False)
            combo.setEnabled(False)

        conn['page'] = page
        conn['combo'] = combo
        conn['btn'] = btn
        conn['terminal'] = terminal

        self.connections[conn['id']] = conn
        self.terminal_tabs.addTab(page, title if title else "新终端")
        # 新建标签后激活它（用户点"+"或按回显按钮就是为了立即使用/查看）
        self.terminal_tabs.setCurrentWidget(page)
        self._fill_conn_combo(conn)
        self._sync_conn_widgets(conn)

        # 本标签的连接/断开按钮（默认参数捕获 conn，防晚绑定）
        btn.clicked.connect(lambda _checked, c=conn: self._on_conn_button_clicked(c))
        # 终端按键/粘贴/尺寸信号只路由到该连接（只连接一次，重连不重复）
        terminal.key_sent.connect(lambda t, c=conn: self._send_to_conn(c, t))
        terminal.paste_sent.connect(lambda t, c=conn: self._paste_to_conn(c, t))
        terminal.resize_requested.connect(
            lambda cols, rows, c=conn: self._resize_conn_pty(c, cols, rows))
        return conn

    def _on_conn_button_clicked(self, conn):
        """标签页内的 连接/断开/重连 按钮"""
        if conn.get('echo_only'):
            return  # 回显专用标签没有连接功能
        state = conn['state']
        if state == 'connected':
            self._disconnect_conn(conn)
        elif state in ('idle', 'disconnected'):
            self._connect_conn(conn)
        # connecting 状态按钮已禁用，不会触发

    def _connect_conn(self, conn):
        """用本标签下拉框选中的服务器发起连接（首次连接和重连共用）"""
        if conn.get('echo_only'):
            # 防御：回显标签不允许连接（正常情况下按钮已隐藏禁用）
            self.update_run_info('回显标签不支持连接服务器', 'WARNING')
            return
        conn['closing'] = False
        idx = conn['combo'].currentIndex()
        if idx == -1:
            self.update_run_info('请先选择服务器', 'WARNING')
            return
        config = conn['combo'].currentData()
        if not config:
            self.update_run_info('服务器配置为空', 'WARNING')
            return
        conn['config'] = dict(config)  # 配置快照：编辑列表改名不影响已开标签
        name = conn['config'].get('服务器名称', '?')

        # 每个连接独立的 SSHTools
        ssh_tool = ssh_tools.SSHTools()
        try:
            ssh_tool.ip = conn['config']['IP']
            ssh_tool.port = conn['config']['端口']
            ssh_tool.username = conn['config']['用户名']
            ssh_tool.password = conn['config']['密码']
        except Exception as e:
            self.update_run_info(f'请检查服务器ssh连接配置{e}', 'ERROR')
            self._set_conn_state(conn, 'disconnected')
            return
        conn['tool'] = ssh_tool

        # 激活该标签（首次 addTab 已自动激活，这里保证重连时也切过来）
        self.terminal_tabs.setCurrentWidget(conn['page'])
        self._set_conn_state(conn, 'connecting')

        def current_ssh(echo_signal):
            c_result = ssh_tool.connect()
            if not c_result:
                return False
            worker.info_signal.emit(('断开', True))
            self.logger.info("[%s] 终端接收线程启动（持续读取服务器回显）", name)
            g_result = ssh_tool.get_output_continue(
                timeout=float('inf'), echo_signal=echo_signal, raw=True)
            self.logger.info("[%s] 终端接收线程退出: result=%s", name, g_result)
            return g_result

        def on_conn_established(data):
            """data = ('断开', True)：连接建立，进入终端模式"""
            if conn['closing'] or conn['tool'] is not ssh_tool:
                # 标签已关闭或连接已被替换：立即断开让接收循环退出
                try:
                    ssh_tool.disconnect()
                except Exception:
                    pass
                return
            self._set_conn_state(conn, 'connected')
            terminal = conn['terminal']
            terminal.set_terminal_mode(True)
            # 同步 pty 尺寸到终端控件实际尺寸
            cols = getattr(terminal, '_cols', 120)
            rows = getattr(terminal, '_rows', 40)
            try:
                if ssh_tool.channel:
                    ssh_tool.channel.resize_pty(width=cols, height=rows)
            except Exception:
                pass
            self.update_run_info(f'已连接 {name}')

        def on_worker_finished(_result):
            if conn['closing']:
                thread.quit()
                return
            self._set_conn_state(conn, 'disconnected')
            conn['terminal'].set_terminal_mode(False)
            self.update_run_info(f'{name} 连接已断开（点击标签页内"重连"或双击标签页可重连）')
            thread.quit()

        def on_thread_finished():
            worker.deleteLater()
            thread.deleteLater()
            if conn.get('thread') is thread:
                conn['thread'] = None
                conn['worker'] = None

        worker = qthread_worker.OneClickWorker(current_ssh)
        worker.kwargs = {"echo_signal": worker.echo_signal}
        thread = QThread()
        worker.moveToThread(thread)
        conn['thread'] = thread
        conn['worker'] = worker
        # 回显直连该标签终端；按键/粘贴/尺寸也只路由到该连接
        worker.echo_signal.connect(conn['terminal'].append_output)
        worker.info_signal.connect(on_conn_established)
        worker.finished.connect(on_worker_finished)
        thread.started.connect(worker.run_task)
        thread.finished.connect(on_thread_finished)
        thread.start()

    def _disconnect_conn(self, conn):
        """断开连接（后台执行，接收线程随后自动退出并更新标签状态）"""
        if conn['state'] != 'connected' or conn['tool'] is None:
            return
        # 防重复点击；断开后 on_worker_finished 会把状态置为已断开
        conn['btn'].setText('连接中...')
        conn['btn'].setEnabled(False)
        self._spawn_disconnect(conn['tool'])

    def _reconnect_conn(self, conn):
        """重连：复用标签和终端（保留已显示内容）"""
        if conn['state'] == 'connecting':
            return
        self._connect_conn(conn)

    def _remove_connection(self, conn):
        """关闭标签：立即移除标签页，连接后台断开"""
        conn['closing'] = True  # 过期回调不再动 UI
        index = self.terminal_tabs.indexOf(conn['page'])
        if index >= 0:
            self.terminal_tabs.removeTab(index)
        self.connections.pop(conn['id'], None)
        if self.active_conn_id == conn['id']:
            self.active_conn_id = None
            self._sync_active_side_ui()

        tool = conn.get('tool')
        if tool is not None:
            # 已连接：后台断开（channel 关闭后接收线程自然退出）
            # 连接中：connect 完成后 on_conn_established 会看到 closing 自行断开
            try:
                if tool.is_connected():
                    self._spawn_disconnect(tool)
            except Exception:
                pass

        # 回显专用标签："发送并接收回显"的会话是独立的 SSH 连接（不属于 conn['tool']），
        # 不主动断开的话会话会在后台继续跑、按钮一直灰着。关标签即断开它的 SSH，
        # worker 的回显循环检测到断开后自行退出，按钮恢复、线程清理走原有流程
        thread_name = conn.get('sc_thread')
        if thread_name and thread_name in self.sc_threads:
            echo_tool = self.sc_threads[thread_name].get('tool')
            if echo_tool is not None:
                try:
                    if echo_tool.is_connected():
                        self._spawn_disconnect(echo_tool)
                except Exception:
                    pass

    def _disconnect_all(self):
        """退出程序前断开所有终端连接（尽力而为）"""
        for conn in list(self.connections.values()):
            try:
                if conn.get('tool') is not None:
                    conn['tool'].disconnect()
            except Exception:
                pass
        self.connections.clear()

    # ---------- 文件浏览器：上传/下载 ----------

    def _fb_upload(self, remote_dir, local_paths):
        """文件浏览器：上传本地文件/文件夹到远程目录"""
        conn = self._active_conn()
        if (conn is None or conn.get('tool') is None or
                not conn['tool'].is_connected()):
            self.update_run_info('请先连接服务器', 'WARNING')
            return

        if not local_paths:
            return

        import time, os

        ssh_tool = conn['tool']
        button_name = '文件上传'
        exec_id = f"fb_upload_{int(time.time()*1000)}"
        self.update_run_info(f'<{button_name}> 开始执行')
        self.logger.info("文件浏览器上传开始: %s -> %s（%d 项）", local_paths, remote_dir, len(local_paths))

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
            self.logger.info("文件浏览器上传结束: result=%s", result)
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
                self.file_browser.status_label.setText("上传完成")
                if hasattr(self, 'file_browser') and self.file_browser.is_connected():
                    self.file_browser.refresh()
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
                self.file_browser.status_label.setText("上传失败")
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
        conn = self._active_conn()
        if (conn is None or conn.get('tool') is None or
                not conn['tool'].is_connected()):
            self.update_run_info('请先连接服务器', 'WARNING')
            return

        if not remote_paths:
            return

        import time, os

        ssh_tool = conn['tool']
        button_name = '文件下载'
        exec_id = f"fb_download_{int(time.time()*1000)}"
        self.update_run_info(f'<{button_name}> 开始执行')
        self.logger.info("文件浏览器下载开始: %s -> %s（%d 项）", remote_paths, local_dir, len(remote_paths))

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
            self.logger.info("文件浏览器下载结束: result=%s", result)
            if result:
                self.update_run_info(f'<{button_name}> 执行成功')
                self.file_browser.status_label.setText("下载完成")
            else:
                self.update_run_info(f'<{button_name}> 执行失败', 'ERROR')
                self.file_browser.status_label.setText("下载失败")
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

    # ──────────────────── 文件浏览器：双击远程文件 → 下载本地打开 + 编辑回传 ────────────────────

    def _fb_open_file(self, remote_path, choose_app=False):
        """
        双击远程文件：下载到 OneClick_Temp/时间戳子目录/（文件保持原始
        文件名），弹 Windows 现代"打开方式"选择框用本地程序打开。
        同时登记编辑会话：本地编辑保存后自动回传覆盖远端文件。
        choose_app=True 时始终弹出打开方式选择框（右键菜单"打开方式..."）
        """
        conn = self._active_conn()
        if (conn is None or conn.get('tool') is None or
                not conn['tool'].is_connected()):
            self.update_run_info('请先连接服务器', 'WARNING')
            return

        import time as _time

        # ── 计算 OneClick_Temp 路径（exe 同目录）──
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.abspath(__file__))
        temp_base = os.path.join(exe_dir, 'OneClick_Temp')
        # 每次打开一个时间戳工作子目录隔离冲突，文件保持原始文件名；同秒冲突追加序号
        temp_dir = self._timestamp_work_dir(temp_base)
        os.makedirs(temp_dir, exist_ok=True)

        ssh_tool = conn['tool']
        conn_id = conn['id']
        fname = os.path.basename(remote_path)
        button_name = '打开远程文件'
        exec_id = f"fb_open_{int(_time.time()*1000)}"
        self.update_run_info(f'<{button_name}> 下载中: {fname}')

        # ── 用已封装的 get_files 链路下载（以原始文件名落入时间戳子目录）──
        source_items = [{
            '路径': remote_path,
            '修改时间': '全部',
            '名称包含': {'关键词': [], '逻辑': '或'},
            '名称不包含': {'关键词': [], '逻辑': '和'}
        }]

        def progress_cb(phase, current, total, extra=''):
            log_progress(self.logger, phase, current, total, extra)

        def execute_download():
            return ssh_tool.get_files(source_items, temp_dir, progress_cb=progress_cb)

        def on_worker_finished(result, _conn_id=conn_id, _remote=remote_path,
                               _choose=choose_app, _work_dir=temp_dir):
            import shutil as _shutil

            def _drop_work_dir():
                # 下载未成功：该时间戳子目录无人使用，直接清掉避免空目录堆积
                _shutil.rmtree(_work_dir, ignore_errors=True)

            try:
                if _conn_id not in self.connections:
                    self.update_run_info(f'<{button_name}> 标签已关闭，不再打开', 'WARNING')
                    _drop_work_dir()
                    return
                if not result:
                    self.update_run_info(f'<{button_name}> 下载失败', 'ERROR')
                    _drop_work_dir()
                    return
                local_path = os.path.join(_work_dir, os.path.basename(_remote))
                if not os.path.exists(local_path):
                    self.update_run_info(f'<{button_name}> 完成但文件未找到', 'WARNING')
                    _drop_work_dir()
                    return
                self._register_edit_session(local_path, _conn_id, _remote)
                if self._shell_open_local(local_path, _choose):
                    self.update_run_info(
                        f'<{button_name}> 已弹出"打开方式"选择: {os.path.basename(local_path)}'
                        f'（选中程序即打开；本地保存后将自动回传 {_remote}）')
                else:
                    self.update_run_info(
                        f'<{button_name}> 选择框拉起失败: {os.path.basename(local_path)}'
                        f'（可右键该文件选"打开方式..."重试）；'
                        f'本地手动打开编辑保存后仍会自动回传', 'WARNING')
            finally:
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

    def _fb_open_with(self, remote_path):
        """文件浏览器右键"打开方式..."：下载后强制弹出打开方式选择框"""
        self._fb_open_file(remote_path, choose_app=True)

    def _timestamp_work_dir(self, temp_base):
        """生成时间戳工作子目录路径：OneClick_Temp/YYYYmmdd_HHMMSS（同秒冲突追加序号）；
        只计算路径不创建，由调用方 makedirs"""
        import datetime
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        candidate = os.path.join(temp_base, ts)
        i = 1
        while os.path.exists(candidate):
            candidate = os.path.join(temp_base, f'{ts}_{i}')
            i += 1
        return candidate

    def _shell_open_local(self, local_path, choose_app=False):
        """
        双击/右键打开本地文件：弹 Windows 现代版"你要如何打开这个文件?"
        选择框（与 资源管理器右键 → 打开方式 → 选择其他应用 同款界面，
        由系统 OpenWith.exe 承载，带"始终使用此应用"勾选）。
        实现：ShellExecuteEx + SEE_MASK_INVOKEIDLIST + 'openas' 动词，
        走 IContextMenu 通道（本机实测：裸 ShellExecuteW 'openas' 对无
        UserChoice 的扩展返回 31 静默失败，必须带 INVOKEIDLIST 掩码）。
        异步：选择框弹出后本函数即返回，用户选中程序后系统自行打开文件。
        choose_app 参数保留以兼容右键入口（现双击/右键行为一致）。
        返回 True=选择框已拉起；False=拉起失败
        """
        try:
            import ctypes

            SEE_MASK_INVOKEIDLIST = 0x0000000C

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ('cbSize', ctypes.c_uint),
                    ('fMask', ctypes.c_uint),
                    ('hwnd', ctypes.c_void_p),
                    ('lpVerb', ctypes.c_wchar_p),
                    ('lpFile', ctypes.c_wchar_p),
                    ('lpParameters', ctypes.c_wchar_p),
                    ('lpDirectory', ctypes.c_wchar_p),
                    ('nShow', ctypes.c_int),
                    ('hInstApp', ctypes.c_void_p),
                    ('lpIDList', ctypes.c_void_p),
                    ('lpClass', ctypes.c_wchar_p),
                    ('hkeyClass', ctypes.c_void_p),
                    ('dwHotKey', ctypes.c_uint),
                    ('hIcon', ctypes.c_void_p),
                    ('hProcess', ctypes.c_void_p),
                ]

            shell32 = ctypes.WinDLL('shell32')
            info = SHELLEXECUTEINFOW()
            info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
            info.fMask = SEE_MASK_INVOKEIDLIST
            info.lpVerb = 'openas'
            info.lpFile = local_path
            info.nShow = 1  # SW_SHOWNORMAL
            if shell32.ShellExecuteExW(ctypes.byref(info)):
                return True
            self.logger.info('ShellExecuteExW openas 失败: %s', local_path)
            return False
        except Exception as e:
            self.update_run_info(f'打开本地文件失败: {e}', 'ERROR')
            return False

    def _register_edit_session(self, local_path, conn_id, remote_path):
        """登记编辑会话并启动轮询：本地保存（mtime+size 变化且稳定）后自动回传"""
        st = os.stat(local_path)
        self._edit_sessions[local_path] = {
            'conn_id': conn_id,
            'remote_path': remote_path,
            'base_mtime': st.st_mtime,   # 上次已回传（或已判定失败不再重试）的基线
            'base_size': st.st_size,
            'last_mtime': st.st_mtime,  # 上次轮询看到的值，防抖参照
            'last_size': st.st_size,
            'synced': True,
            'uploading': False,
        }
        self.logger.info("编辑会话登记: %s -> %s", local_path, remote_path)
        if not self._edit_watch_timer.isActive():
            self._edit_watch_timer.start()

    def _poll_edit_sessions(self):
        """每2秒轮询编辑会话的本地临时文件：mtime+size 变化且连续两轮一致 → 回传"""
        if not self._edit_sessions:
            self._edit_watch_timer.stop()
            return
        for local_path in list(self._edit_sessions.keys()):
            s = self._edit_sessions[local_path]
            if s.get('uploading'):
                continue
            try:
                st = os.stat(local_path)
            except OSError:
                # 本地临时文件被删（清理/用户手动删）→ 会话结束
                del self._edit_sessions[local_path]
                self.update_run_info(
                    f"<文件回传> 编辑会话结束（临时文件已删除）: {os.path.basename(local_path)}",
                    'WARNING')
                continue
            mtime, size = st.st_mtime, st.st_size
            if (mtime, size) == (s['base_mtime'], s['base_size']):
                continue
            if (mtime, size) == (s['last_mtime'], s['last_size']):
                # 连续两轮一致：保存动作已稳定 → 回传
                self._upload_edit_session(local_path)
            else:
                s['last_mtime'], s['last_size'] = mtime, size

    def _upload_edit_session(self, local_path):
        """把本地修改回传覆盖远端文件（QThread 后台执行，不卡 UI）"""
        s = self._edit_sessions.get(local_path)
        if s is None or s.get('uploading'):
            return
        remote_path = s['remote_path']
        fname = os.path.basename(remote_path)
        conn = self.connections.get(s['conn_id'])
        if (conn is None or conn.get('tool') is None or
                not conn['tool'].is_connected()):
            # 连接已断开：只提示不重试；推进基线到当前修改，等用户再次保存才触发下一次回传
            s['synced'] = False
            try:
                st = os.stat(local_path)
                s['base_mtime'], s['base_size'] = st.st_mtime, st.st_size
                s['last_mtime'], s['last_size'] = st.st_mtime, st.st_size
            except OSError:
                pass
            self.update_run_info(
                f'<文件回传> {fname} 保存未同步到服务器（连接已断开），'
                f'重新保存可再次回传', 'ERROR')
            return

        # 上传前把基线锁定为本轮快照：上传期间再有保存属于新版本，
        # 成功后轮询会检测到并自动再传，不丢更新
        try:
            st0 = os.stat(local_path)
        except OSError:
            return
        s['base_mtime'], s['base_size'] = st0.st_mtime, st0.st_size
        s['last_mtime'], s['last_size'] = st0.st_mtime, st0.st_size
        s['uploading'] = True
        ssh_tool = conn['tool']
        conn_id = s['conn_id']
        self.update_run_info(f'<文件回传> {fname} 回传中…')

        import time as _time
        exec_id = f"fb_edit_{int(_time.time()*1000)}"
        button_name = '文件回传'

        def execute_upload():
            return ssh_tool.upload_single_file(local_path, remote_path)

        def on_worker_finished(result, _s=s, _remote=remote_path, _conn_id=conn_id):
            try:
                if result:
                    _s['synced'] = True
                    self.update_run_info(
                        f'<{button_name}> {os.path.basename(_remote)} 已同步覆盖服务器文件')
                    # 来源连接是当前激活连接时刷新文件浏览器，立即可见远端新状态
                    ac = self._active_conn()
                    if (ac is not None and ac['id'] == _conn_id
                            and self.file_browser.is_connected()):
                        self.file_browser.refresh()
                else:
                    # 回传失败：不重试（基线已锁定为快照），标记未同步，等用户再次保存触发
                    _s['synced'] = False
                    self.update_run_info(
                        f'<{button_name}> {os.path.basename(_remote)} 回传失败，'
                        f'保存未同步到服务器，重新保存可再次回传', 'ERROR')
            finally:
                _s['uploading'] = False
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
        self._save_config_auto()

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
        self._save_config_auto()

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
                '记事本': self.notepad_dialog,
            }
            sc_ty = self.sc_buttons[button_id]['config']['指令类型']
            dialog_func = ty_dialog.get(sc_ty)  # 假设指令类型是发送命令，dialog_func就是self.cmd1_dialog
            if dialog_func:
                dialog_func(button_id)  # 以编辑模式打开窗口，传入button_id
            else:
                self.update_run_info(f"编辑按钮出错：未知指令类型{sc_ty}", 'ERROR')

    # ==================== 分组批量操作 ====================

    # 批量执行时跳过的类型
    SKIP_BATCH_TYPES = {'发送命令并接收回显', '资源监控', '弱网', '服务器检查', '记事本'}

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
            self._save_config_auto()

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
        # 清屏：清空当前激活标签的终端
        conn = self._active_conn()
        if conn is not None:
            conn['terminal'].clear_terminal()
            self.update_run_info("终端已清空")
        else:
            self.update_run_info('当前没有打开的终端标签')

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

    def open_program_dir(self):
        """用系统文件管理器打开程序所在目录（打包后为 exe 目录，开发时为脚本目录）"""
        import subprocess
        if getattr(sys, 'frozen', False):
            target_dir = os.path.dirname(sys.executable)
        else:
            target_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            if sys.platform.startswith('win'):
                # 尾部补 os.sep 强制"目录"语义：无扩展名路径经 ShellExecute 会优先
                # 尝试补全 .exe，若目录旁恰好存在同名 exe（如 dist\ 下同时有
                # OneClick.exe 单文件版与 OneClick\ 文件夹版）会被误启动
                os.startfile(target_dir + os.sep)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', target_dir])
            else:
                subprocess.Popen(['xdg-open', target_dir])
        except Exception as e:
            self.update_run_info(f'打开程序目录失败: {e}', 'ERROR')

    def open_log_settings(self):
        """打开日志设置对话框"""
        from dialogs.log_settings_dialog import LogSettingsDialog
        from utils.logger import set_file_logging, set_file_log_level, set_panel_level, set_file_backup_count
        import logging as _logging
        _level_map = {'DEBUG': _logging.DEBUG, 'INFO': _logging.INFO,
                      'WARNING': _logging.WARNING, 'ERROR': _logging.ERROR}
        dlg = LogSettingsDialog(self, self._log_config)
        if dlg.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            new_cfg = dlg.get_config()
            self._log_config = new_cfg
            # 应用到 logger
            set_file_logging(new_cfg['文件日志'])
            set_file_log_level(_level_map.get(new_cfg['文件日志级别'], _logging.INFO))
            set_panel_level(_level_map.get(new_cfg['面板日志级别'], _logging.INFO))
            set_file_backup_count(new_cfg['文件保留个数'])
            # 保存到默认配置文件
            self._save_log_config_to_file()
            self.update_run_info("日志设置已更新")

    def _save_log_config_to_file(self):
        """把当前日志配置写入默认配置文件（保留其他配置不变）"""
        if os.path.exists(self.default_config_path):
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    cfg_data = json.load(f)
            except Exception:
                cfg_data = {}
        else:
            cfg_data = {}
        cfg_data['日志配置'] = self._log_config.copy()
        try:
            with open(self.default_config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg_data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def _save_config_auto(self):
        """自动保存配置到默认配置文件，失败只记日志不弹框"""
        if getattr(self, '_loading_config', False):
            return
        try:
            self.save_config_to(self.default_config_path)
        except Exception as e:
            self.logger.warning(f"自动保存配置失败: {e}")

    def save_config(self):
        """菜单-保存（保留兼容，自动保存后基本用不到）"""
        self.save_config_to(self.default_config_path)

    def export_config_dialog(self):
        """导出配置：弹出保存对话框，另存为 JSON 文件"""
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出配置",
            "OneClick配置",
            "JSON Files (*.json)"
        )
        if not file_path:
            self.update_run_info("导出配置 取消")
            return
        if not file_path.endswith('.json'):
            file_path += '.json'
        self.save_config_to(file_path)

    def import_config_dialog(self, append=True):
        """
        导入配置
        append=True:  追加模式（分组重名跳过，按钮/服务器/指令一律追加）
        append=False: 覆盖模式（全部清空后导入）
        """
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        files, _ = QFileDialog.getOpenFileName(
            self,
            "导入配置（追加）" if append else "导入配置（覆盖）",
            "",
            "JSON Files (*.json)"
        )
        if not files:
            self.update_run_info("导入配置 取消")
            return
        file_path = files
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("配置文件格式错误：不是字典类型")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            self.update_run_info(f"导入配置失败: {str(e)}", 'WARNING')
            QMessageBox.warning(self, "导入失败", f"配置文件解析失败:\n{e}")
            return

        # 覆盖模式：确认后清空现有数据
        if not append:
            reply = QMessageBox.question(
                self, "确认覆盖",
                "覆盖模式将清空所有现有按钮、分组、服务器和指令，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.update_run_info("导入配置 取消")
                return
            # 清空所有数据
            self._clear_all_config()

        # 设置加载标志，避免过程中反复保存
        self._loading_config = True
        try:
            # ---- 收集数据 ----
            sc_buttons_list = []
            group_set = set()
            servers = []
            commands = []
            for key in data:
                if '快捷按钮' in key:
                    btn_cfg = data[key]
                    gname = btn_cfg.get('分组', '默认分组')
                    pos = btn_cfg.get('位置', 99999)
                    sc_buttons_list.append((gname, pos, btn_cfg))
                    group_set.add(gname)
                elif '服务器' in key:
                    servers.append(data[key])
                elif key == '指令':
                    commands = data[key] if isinstance(data[key], list) else []

            # ---- 分组处理 ----
            group_order_cfg = data.get('分组顺序', [])
            if isinstance(group_order_cfg, list) and group_order_cfg:
                ordered = [g for g in group_order_cfg if g in group_set]
                remaining = sorted([g for g in group_set if g not in group_order_cfg])
                ordered_groups = ordered + remaining
            else:
                ordered_groups = sorted(group_set)

            if not append:
                # 覆盖模式：按导入的分组顺序重建
                for gname in ordered_groups:
                    self._ensure_group(gname)
            else:
                # 追加模式：已有的分组跳过，新的追加到末尾
                for gname in ordered_groups:
                    self._ensure_group(gname)

            # ---- 按钮处理 ----
            group_order_map = {g: i for i, g in enumerate(ordered_groups)}
            sc_buttons_list.sort(key=lambda x: (group_order_map.get(x[0], 99999), x[1]))
            btn_added = 0
            for gname, pos, btn_cfg in sc_buttons_list:
                clean_cfg = btn_cfg.copy()
                if '位置' in clean_cfg:
                    del clean_cfg['位置']
                self.add_button(clean_cfg)
                btn_added += 1

            # ---- 服务器处理 ----
            srv_added = 0
            for srv in servers:
                self.servers_cfg.append(srv)
                srv_added += 1
            if srv_added > 0:
                self.update_server_combobox()

            # ---- 指令处理 ----
            cmd_added = 0
            for cmd in commands:
                normalized = self._normalize_command(cmd)
                if not normalized['content']:
                    continue
                if not self._cmd_content_exists(normalized['content']):
                    self.commands.append(normalized)
                    cmd_added += 1

            # 同步到 UI（指令列表在打开管理对话框时会刷新）
            mode_name = "追加" if append else "覆盖"
            self.update_run_info(
                f"导入配置（{mode_name}）成功，来自{file_path}\n"
                f"  分组：{len(group_set)} 个，按钮：{btn_added} 个，"
                f"服务器：{srv_added} 个，指令：{cmd_added} 条"
            )

            # 选中第一个分组
            if self.group_tabWidget.count() > 0:
                self.group_tabWidget.setCurrentIndex(0)
        finally:
            self._loading_config = False
            # 导入完成后保存一次
            self._save_config_auto()

    def _clear_all_config(self):
        """清空所有配置（按钮、分组、服务器、指令），用于覆盖导入"""
        # 清空按钮和分组
        self.sc_buttons.clear()
        self._groups.clear()
        self._group_order.clear()
        # 清空所有标签页（从后往前删，避免索引问题）
        while self.group_tabWidget.count() > 0:
            self.group_tabWidget.removeTab(self.group_tabWidget.count() - 1)
        # 清空服务器
        self.servers_cfg.clear()
        self.update_server_combobox()
        # 清空指令
        self.commands.clear()

    def save_config_to(self, path):
        """保存配置到指定路径"""
        file_path = path
        if not file_path.endswith('.json'):
            file_path += '.json'
        # 获取所有配置
        cfg_dic = {}
        server_count = 1
        button_count = 1
        for server in self.servers_cfg:
            cfg_dic[f'服务器{server_count}'] = server
            server_count += 1
        # 保存分组顺序
        cfg_dic['分组顺序'] = self._group_order.copy()
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
        # 保存日志配置（用当前内存中的配置）
        cfg_dic['日志配置'] = self._log_config.copy()

        # 写入到json文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cfg_dic, f, ensure_ascii=False, indent=4)
            self.update_run_info(f"已保存配置到{os.path.abspath(file_path)}")
        except Exception as e:
            self.update_run_info(f"保存配置失败: {str(e)}", 'WARNING')

    def load_sc_config(self, path):
        """启动时从默认配置文件加载快捷按钮、分组、指令"""
        file_path = path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 解析内容
                data = json.loads(content)
                # 确保是字典类型
                if not isinstance(data, dict):
                    raise ValueError("配置文件格式错误：不是字典类型")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            self.update_run_info(f"配置文件解析失败: {str(e)}，使用空配置", 'WARNING')
            return
        # 先收集所有快捷按钮配置，按分组和位置排序
        sc_buttons_list = []
        group_set = set()
        for key in data:
            if '快捷按钮' in key:
                button_config = data[key]
                group_name = button_config.get('分组', '默认分组')
                position = button_config.get('位置', 99999)
                sc_buttons_list.append((group_name, position, button_config))
                group_set.add(group_name)

        # 读取分组顺序（如果配置中有，则按此顺序创建分组；否则按分组名字典序）
        group_order_cfg = data.get('分组顺序', [])
        if isinstance(group_order_cfg, list) and group_order_cfg:
            # 配置中有的分组按配置顺序，没在配置里的分组追加到后面
            ordered_groups = [g for g in group_order_cfg if g in group_set]
            remaining = sorted([g for g in group_set if g not in group_order_cfg])
            ordered_groups.extend(remaining)
        else:
            ordered_groups = sorted(group_set)

        # 先按顺序创建所有分组（确保分组顺序正确）
        for gname in ordered_groups:
            self._ensure_group(gname)

        # 按分组顺序 + 组内位置排序
        group_order_map = {gname: idx for idx, gname in enumerate(ordered_groups)}
        sc_buttons_list.sort(key=lambda x: (group_order_map.get(x[0], 99999), x[1]))
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
                for cmd in data[key]:
                    self.commands.append(self._normalize_command(cmd))
                self.update_run_info(f"批量添加指令 成功，来自{file_path}")
            elif key == '日志配置':  # 跳过，日志配置在启动时单独加载
                pass
            elif key == '分组顺序':
                pass  # 分组排序，上面已处理
            else:
                self.update_run_info(f'{key}无法识别的数据类型', 'WARNING')
        self.update_run_info(f"批量添加快捷按钮 成功，来自{file_path}")
        # 加载完成后默认选中第一个分组
        if self.group_tabWidget.count() > 0:
            self.group_tabWidget.setCurrentIndex(0)

    def load_server_config(self, path):
        """启动时从默认配置文件加载服务器列表"""
        file_path = path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 解析内容
                data = json.loads(content)
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

    def update_server_combobox(self):
        # 服务器列表变化：重建每个终端标签页自己的服务器下拉框
        for conn in self.connections.values():
            self._fill_conn_combo(conn)

    @staticmethod
    def _normalize_command(cmd):
        """把一条指令统一成 {'name': ..., 'content': ...} 格式。
        支持旧格式纯字符串 -> 新格式dict的向下兼容转换。"""
        if isinstance(cmd, dict):
            name = str(cmd.get('name', '')).strip()
            content = str(cmd.get('content', '')).strip()
            if not name:
                # 名称为空，用内容第一行自动生成
                first_line = content.splitlines()[0].strip() if content else ''
                if not first_line:
                    first_line = content.strip()[:20]
                if len(first_line) > 40:
                    first_line = first_line[:40] + '...'
                name = first_line or '(空)'
            return {'name': name, 'content': content}
        else:
            # 旧格式：纯字符串
            content = str(cmd).strip()
            first_line = content.splitlines()[0].strip() if content else ''
            if not first_line:
                first_line = content[:20]
            if len(first_line) > 40:
                first_line = first_line[:40] + '...'
            name = first_line or '(空)'
            return {'name': name, 'content': content}

    def _cmd_content_exists(self, content):
        """判断某条指令内容是否已经存在（按content去重）"""
        for cmd in self.commands:
            if isinstance(cmd, dict):
                if cmd.get('content', '') == content:
                    return True
            else:
                if str(cmd) == content:
                    return True
        return False

    def open_cmd_manage_dialog(self):
        """打开指令管理对话框"""
        old_commands = self.commands.copy()
        dlg = CmdManageDialog(commands=self.commands, parent=self)
        dlg.insert_cmd_signal.connect(self._insert_cmd_to_terminal)
        dlg.exec_()
        # 对话框关闭后，同步指令列表
        self.commands = dlg.get_all_commands()
        if self.commands != old_commands:
            self._save_config_auto()

    def _insert_cmd_to_terminal(self, cmd):
        """插入指令到终端（直接发送给服务器，不自动回车）"""
        conn = self._active_conn()
        if conn is None or conn['state'] != 'connected':
            self.update_run_info('请先建立SSH连接', 'WARNING')
            return
        try:
            channel = conn['tool'].channel
            if channel and channel.active:
                channel.send(cmd)
        except Exception as e:
            self.update_run_info(f'发送指令失败: {e}', 'ERROR')

    def closeEvent(self, event):
        """
        重写窗口关闭事件：检测运行中的按钮/未同步的编辑文件，提示用户确认；
        退出时清理 OneClick_Temp
        """
        running_count = len(self.sc_threads)
        # 双击打开编辑的文件：保存了但回传失败/连接断开，退出清临时目录会丢修改
        # 多次打开同名文件时按文件名去重显示
        unsynced_names = []
        for p, s in self._edit_sessions.items():
            if not s.get('synced'):
                name = os.path.basename(p)
                if name not in unsynced_names:
                    unsynced_names.append(name)
        if running_count > 0 or unsynced_names:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("确认退出")
            if running_count > 0 and unsynced_names:
                msg_box.setText(f"有 {running_count} 个后台任务正在运行，"
                                f"且有 {len(unsynced_names)} 个文件的修改未同步到服务器")
                msg_box.setInformativeText(
                    f"未同步文件: {'、'.join(unsynced_names[:5])}"
                    f"{'等' if len(unsynced_names) > 5 else ''}\n"
                    "直接退出会强制中断任务，并丢失这些文件的本地修改。")
            elif running_count > 0:
                msg_box.setText(f"有 {running_count} 个快捷按钮正在运行，是否直接退出？")
                msg_box.setInformativeText("直接退出会强制中断正在执行的操作。")
            else:
                msg_box.setText(f"有 {len(unsynced_names)} 个文件的修改未同步到服务器，是否直接退出？")
                msg_box.setInformativeText(
                    f"未同步文件: {'、'.join(unsynced_names[:5])}"
                    f"{'等' if len(unsynced_names) > 5 else ''}\n"
                    "直接退出会丢失这些文件的本地修改。")
            msg_box.setIcon(QMessageBox.Icon.Warning)
            btn_exit = msg_box.addButton("直接退出", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_cancel)
            msg_box.exec_()
            if msg_box.clickedButton() == btn_exit:
                # 自动保存 + 停止编辑轮询 + 断开所有终端连接 + 清理临时目录 + 退出
                self._edit_watch_timer.stop()
                self._save_config_auto()
                self._disconnect_all()
                self._cleanup_oneclick_temp()
                event.accept()
            else:
                event.ignore()
        else:
            # 没有运行中的任务，自动保存 + 断开所有终端连接 + 清理临时目录 + 退出
            self._edit_watch_timer.stop()
            self._save_config_auto()
            self._disconnect_all()
            self._cleanup_oneclick_temp()
            event.accept()

    def _cleanup_oneclick_temp(self):
        """清理 exe 同目录下的 OneClick_Temp（双击远程文件下载的临时目录）"""
        try:
            import shutil
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
            else:
                exe_dir = os.path.dirname(os.path.abspath(__file__))
            temp_dir = os.path.join(exe_dir, 'OneClick_Temp')
            if os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass  # 清理失败不影响退出

    def show_help_dialog(self):
        """显示帮助文档对话框"""
        help_dialog = HelpDialog(self)
        help_dialog.exec_()

    def show_about_dialog(self):
        """关于对话框：展示软件名称与版本号（版本号不再放窗口标题）"""
        from version import __version__
        QtWidgets.QMessageBox.about(
            self, "关于 OneClick",
            f"<h3>OneClick</h3><p>版本 v{__version__}</p>")


if __name__ == '__main__':
    pass
