import os.path
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
from utils.logger import setup_logging, get_logger
from dialogs import (SendCMDDialog, SendCMD2Dialog, SendFilesDialog, GetFilesDialog, CopyFilesDialog,
                     SetServerDialog, ResourceMonitorDialog1, ResourceMonitorDialog2,
                     WeakNetDialog1, WeakNetControlDialog, HelpDialog, sc_class2str)


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

        # 创建菜单栏选项与弹出的编辑窗口关系
        self.send_cmd_action.triggered.connect(self.cmd1_dialog)  # 发送cmd的编辑框
        self.send_cmd2_action.triggered.connect(self.cmd2_dialog)  # 发送cmd并接收回显的编辑框
        self.send_file_action.triggered.connect(self.send_file_dialog)  # 发送文件的编辑框
        self.get_file_action.triggered.connect(self.get_file_dialog)  # 获取文件的编辑框
        self.copy_local_action.triggered.connect(self.copy_file_dialog)  # 复制本地文件编辑框
        self.resource_monitor_action.triggered.connect(self.resource_monitor_dialog)  # 资源监控编辑框
        self.weak_net_action.triggered.connect(self.weak_net_dialog)  # 弱网编辑框
        self.get_sc_from_cfg_action.triggered.connect(self.load_sc_config)  # 从配置文件获取快捷按钮

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
        self.save_cmd_pushButton.clicked.connect(self.save_cmd)
        self.del_cmd_pushButton.clicked.connect(self.del_cmd)
        self.send_cmd_pushButton.clicked.connect(self.send_cmd)
        self.cmd_comboBox.activated.connect(self.select_cmd)
        # 输入框的按键监听
        self.cmd_plainTextEdit.keyPressEvent = self.keyPressEvent

        # 配置文件的默认路径
        self.default_config_path = self.get_default_path() + '/' + 'config.json'

        # 初始化日志系统（必须在 update_run_info 之前）
        self._log_emitter = setup_logging(
            log_dir=self.get_default_path(),
            enable_file_logging=False,  # 默认关闭，由勾选框控制
            enable_qt_bridge=False,
        )
        self.logger = get_logger("MainWindow")

        # 先连接状态变化信号，然后设置初始状态（从配置文件读取）
        self.log_file_checkBox.stateChanged.connect(self._on_log_file_checkbox_changed)

        # 从配置文件读取初始状态（如果有）
        initial_log_enabled = False
        # 日志级别配置：字典，键为级别名，值为bool
        self._log_level_config = {
            'DEBUG': False,
            'INFO': True,
            'WARNING': True,
            'ERROR': True,
        }
        if os.path.exists(self.default_config_path):
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    import json
                    cfg_data = json.load(f)
                    if '日志配置' in cfg_data:
                        initial_log_enabled = cfg_data['日志配置'].get('文件日志', False)
                        # 读取日志级别配置（如果有）
                        for level in self._log_level_config:
                            if level in cfg_data['日志配置']:
                                self._log_level_config[level] = cfg_data['日志配置'][level]
            except Exception:
                pass

        # 设置勾选框初始状态（会触发 stateChanged，自动初始化文件日志开关）
        self.log_file_checkBox.setChecked(initial_log_enabled)

        self.showMaximized()

        # 创建默认分组
        self.add_group_tab("默认分组")

        # 如果有默认配置文件，则获取
        if os.path.exists(self.default_config_path):
            self.update_run_info('存在默认配置文件，开始添加服务器和快捷按钮')
            self.load_server_config(self.default_config_path)
            self.load_sc_config(self.default_config_path)
        # 主界面服务器选择下拉表
        self.server_comboBox.setCurrentIndex(-1)
        self.update_server_combobox()
        self.update_run_info("OneClick 启动成功")

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑快捷按钮')
            else:
                self.update_run_info('取消创建快捷按钮')

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
                self.update_run_info(f'{button_type} {button_text}快捷按钮编辑成功')
            else:
                button_type = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令类型"]
                button_text = self.sc_buttons[f"button_{self.btn_count}"]["config"]["指令名称"]
                self.update_run_info(f'<{button_text}>快捷按钮创建成功')
        else:
            if button_id:
                self.update_run_info('取消编辑弱网快捷按钮')
            else:
                self.update_run_info('取消创建弱网快捷按钮')

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
            self.sc_buttons[button_id]['config']['指令']
        )

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中，一定要先移动再绑信号槽，不然会绑定到主线程
        worker.moveToThread(thread)

        # 绑定worker信号槽
        log_wrapper = self._make_log_wrapper(button_name)
        worker.log_signal.connect(log_wrapper)
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
        worker = qthread_worker.OneClickWorker(send_cmd_and_receive_echo)
        worker.kwargs = {
            "cmd" : self.sc_buttons[button_id]['config']['指令'],
            "echo_signal": worker.echo_signal
        }

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定信号槽
        log_wrapper = self._make_log_wrapper(button_name)
        worker.log_signal.connect(log_wrapper)
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

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        local_path = self.sc_buttons[button_id]['config']['本地路径']
        remote_path = self.sc_buttons[button_id]['config']['服务器路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']
        work_dir = self.sc_buttons[button_id]['config']['文件暂存路径']

        def execute_send_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            s_result = ssh_tool.send_files(local_path, remote_path, mtime, filename, work_dir)

            ssh_tool.disconnect()

            return s_result

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
        worker = qthread_worker.OneClickWorker(execute_send_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        log_wrapper = self._make_log_wrapper(button_name)
        worker.log_signal.connect(log_wrapper)
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

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        # 将本地路径的"当前路径/时间IP(例:20251024031415-1.1.1.1)/"修改为当前时间当前路径
        if self.sc_buttons[button_id]['config']['本地路径'] == "当前路径/时间IP(例:20251024031415-1.1.1.1)/":
            current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            local_path = self.get_default_path() + '/' + current_time + '-' + self.sc_buttons[button_id]['config'][
                'IP']
            os.mkdir(local_path)
        else:
            local_path = self.sc_buttons[button_id]['config']['本地路径']

        remote_path = self.sc_buttons[button_id]['config']['服务器路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']
        work_dir = self.sc_buttons[button_id]['config']['文件暂存路径']

        def execute_get_files():
            c_result = ssh_tool.connect()
            if not c_result:
                return False

            g_result = ssh_tool.get_files(remote_path, local_path, mtime, filename, work_dir)

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
        worker = qthread_worker.OneClickWorker(execute_get_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        log_wrapper = self._make_log_wrapper(button_name)
        worker.log_signal.connect(log_wrapper)
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
        """打包复制文件或文件夹"""
        if button_id not in self.sc_buttons:
            return
        button_name = self.sc_buttons[button_id]['config']['指令名称']
        # 检查是否正在执行
        if self.sc_buttons[button_id]['button'].property('executing'):
            self.update_run_info(f'<{button_name}> 正在执行中，请先停止', 'WARNING')
            return
        self.update_run_info(f'<{button_name}> 开始执行')
        self.set_button_executing(button_id, True)

        # 初始化WindowsTools
        win_tool = windows_tools.WindowsTools()

        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200
        }

        # 将复制到的"当前路径/当前时间(例:20251024031415)/"修改为当前路径/当前时间
        if self.sc_buttons[button_id]['config']['复制到'] == "当前路径/当前时间(例:20251024031415)/":
            current_time = datetime.datetime.now().strftime("%Y_%m%d_%H%M%S")
            target_path = self.get_default_path() + '/' + current_time
            os.mkdir(target_path)
        else:
            target_path = self.sc_buttons[button_id]['config']['复制到']

        resource_path = self.sc_buttons[button_id]['config']['源路径']
        mtime = mtime_dic.get(self.sc_buttons[button_id]['config']['修改时间'])
        filename = self.sc_buttons[button_id]['config']['文件名包含']

        def execute_copy_files():
            cp_result = win_tool.copy_files(resource_path, target_path, mtime, filename)
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
        worker = qthread_worker.OneClickWorker(execute_copy_files)

        # 初始化线程
        thread = QThread()

        # 将worker移动到线程中
        worker.moveToThread(thread)

        # 绑定worker信号槽
        log_wrapper = self._make_log_wrapper(button_name)
        worker.log_signal.connect(log_wrapper)
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

    def _on_log_file_checkbox_changed(self, state):
        """日志勾选框状态变化：控制文件日志开关"""
        import logging.handlers
        enable = (state == QtCore.Qt.Checked)
        root_logger = logging.getLogger()

        # 先移除所有已存在的文件 handler
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.close()
                root_logger.removeHandler(handler)

        if enable:
            # 添加文件 handler
            log_dir = self.get_default_path()
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                filename=os.path.join(log_dir, "OneClick.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
            file_handler.setFormatter(fmt)
            
            # 添加过滤器：只写入配置中开启的日志级别
            def log_filter(record):
                level_name = record.levelname
                # 映射日志级别名称
                level_map = {
                    'DEBUG': 'DEBUG',
                    'INFO': 'INFO',
                    'WARNING': 'WARNING',
                    'ERROR': 'ERROR',
                    'CRITICAL': 'ERROR',
                }
                config_key = level_map.get(level_name, level_name)
                # 检查该级别是否开启（默认不输出，避免配置丢失导致日志错乱）
                return self._log_level_config.get(config_key, False)
            
            file_handler.addFilter(log_filter)
            root_logger.addHandler(file_handler)
            self.update_run_info("文件日志已开启")
        else:
            self.update_run_info("文件日志已关闭")

    def _make_log_wrapper(self, button_name):
        """创建带按钮名称前缀的日志包装函数"""
        def wrapper(text, level='INFO'):
            # 如果已经有前缀了就不加了（避免重复）
            if text.startswith(f'<{button_name}> '):
                self.update_run_info(text, level)
            else:
                self.update_run_info(f'<{button_name}> {text}', level)
        return wrapper

    def update_run_info(self, text, level='INFO'):
        """同步显示到UI（带颜色），同时发给logger写文件

        Args:
            text: 要显示的文本
            level: 日志级别，可选值 INFO / WARNING / ERROR
        """
        # 根据级别设置颜色
        color_map = {
            'INFO': '#000000',
            'WARNING': '#FF8C00',
            'ERROR': '#FF0000',
        }
        color = color_map.get(level.upper(), '#000000')

        # HTML 转义：防止 < > & 等特殊字符被解析成标签
        html_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # 1. 加时间戳后显示到UI（带颜色）
        formatted_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html = f'<span style="color: {color}">{formatted_datetime} {html_text}</span>'
        self.run_info_browser.append(html)

        # 2. 滚动条置底
        self.run_info_browser.verticalScrollBar().setValue(
            self.run_info_browser.verticalScrollBar().maximum()
        )
        self.run_info_browser.horizontalScrollBar().setValue(
            self.run_info_browser.horizontalScrollBar().minimum()
        )

        # 3. 发给logger（如果开启了文件日志，会写入文件）
        if hasattr(self, 'logger'):
            level_upper = level.upper()
            if level_upper == 'WARNING':
                self.logger.warning(text)
            elif level_upper == 'ERROR':
                self.logger.error(text)
            else:
                self.logger.info(text)

    def update_linux_print(self, text, insert=False):
        if insert:
            # 获取当前文本控件的光标
            cursor = self.linux_print_browser.textCursor()
            # 将光标移动到文档末尾
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            # 应用移动后的光标
            self.linux_print_browser.setTextCursor(cursor)
            self.linux_print_browser.insertPlainText(text)
        else:
            # 将输出添加到linux_print_browser
            self.linux_print_browser.append(text)
        # 滚动到底部
        self.linux_print_browser.verticalScrollBar().setValue(
            self.linux_print_browser.verticalScrollBar().maximum()
        )
        # 水平滚动条到头部
        self.linux_print_browser.horizontalScrollBar().setValue(
            self.linux_print_browser.horizontalScrollBar().minimum()
        )

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
            }
            sc_ty = self.sc_buttons[button_id]['config']['指令类型']
            dialog_func = ty_dialog.get(sc_ty)  # 假设指令类型是发送命令，dialog_func就是self.cmd1_dialog
            if dialog_func:
                dialog_func(button_id)  # 以编辑模式打开窗口，传入button_id
            else:
                self.update_run_info(f"编辑按钮出错：未知指令类型{sc_ty}", 'ERROR')

    # ==================== 分组批量操作 ====================

    # 批量执行时跳过的类型
    SKIP_BATCH_TYPES = {'发送命令并接收回显', '资源监控', '弱网'}

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
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            # 关键：禁用系统原生对话框，强制使用Qt风格
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            # 设置为保存模式
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            # 设置默认文件名和文件类型
            dialog.setDefaultSuffix("json")  # 自动补充.json后缀
            dialog.selectFile("自定义配置")  # 默认文件名
            dialog.setNameFilter("JSON Files (*.json)")
            # 显示对话框并处理结果
            if dialog.exec_():
                # 获取选中的完整路径
                file_path = dialog.selectedFiles()[0]
                # 确保后缀正确
                if not file_path.endswith('.json'):
                    file_path += '.json'
            else:
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
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            #  使用Qt自带的对话框,保持风格一致
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

            # 设置文件过滤器，只显示JSON文件
            # 格式："描述 (*.扩展名)"，多个类型用;;分隔
            dialog.setNameFilter("JSON Files (*.json)")

            # 可以设置默认文件后缀，当用户输入无后缀的文件名时自动添加
            dialog.setDefaultSuffix("json")

            # 显示对话框并检查用户是否点击了打开按钮
            if dialog.exec_():
                # 如果用户选择了文件，返回文件路径
                file_path = dialog.selectedFiles()[0]
            else:
                self.update_run_info('批量添加快捷按钮 取消')
                return
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
                    self.cmd_comboBox.addItem(cmd, cmd)
                self.update_run_info(f"批量添加指令 成功，来自{file_path}")
                self.cmd_comboBox.setCurrentIndex(-1)
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
            dialog = QFileDialog()
            dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
            # 使用Qt自带的对话框,保持风格一致
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

            # 设置文件过滤器，只显示JSON文件
            # 格式："描述 (*.扩展名)"，多个类型用;;分隔
            dialog.setNameFilter("JSON Files (*.json)")

            # 可以设置默认文件后缀，当用户输入无后缀的文件名时自动添加
            dialog.setDefaultSuffix("json")

            # 显示对话框并检查用户是否点击了打开按钮
            if dialog.exec_():
                # 如果用户选择了文件，返回文件路径
                file_path = dialog.selectedFiles()[0]
            else:
                self.update_run_info('批量添加服务器 取消')
                return
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

            # 封装指令发送和回显接收方法
            def current_ssh(echo_signal):
                c_result = ssh_tool.connect()
                if not c_result:
                    return False
                worker.info_signal.emit(('断开',True))
                g_result = ssh_tool.get_output_continue(timeout=float('inf'), echo_signal=echo_signal)
                return g_result

            def on_worker_finished():
                update_connect_button(('连接',True))
                self.server_comboBox.setEnabled(True)
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

            # 绑定信号槽
            worker.log_signal.connect(self.update_run_info)
            worker.echo_signal.connect(lambda text: self.update_linux_print(text, insert=True))
            worker.info_signal.connect(update_connect_button)
            worker.finished.connect(on_worker_finished)

            # 绑定线程信号槽
            thread.started.connect(worker.run_task)
            thread.finished.connect(on_thread_finished)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    "tool": ssh_tool,
                    "send_count": 0,
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

            # 绑定信号槽
            worker.log_signal.connect(self.update_run_info)
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

    def send_cmd(self):
        if self.connect_pushButton.text() == '断开':
            self.current_ssh['send_count'] += 1
            cmd = self.cmd_plainTextEdit.toPlainText()

            worker = qthread_worker.OneClickWorker(self.current_ssh['tool'].send_command_interactive, cmd)
            thread = QThread()
            worker.moveToThread(thread)

            worker.log_signal.connect(self.update_run_info)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(thread.quit)

            thread.started.connect(worker.run_task)
            thread.finished.connect(thread.deleteLater)

            # 保存worker和线程信息
            self.current_ssh.update(
                {
                    f"task_send_{self.current_ssh['send_count']}": (thread, worker)
                }
            )
            thread.start()
        else:
            self.update_run_info('请先建立ssh连接', 'WARNING')
        self.cmd_plainTextEdit.clear()

    def save_cmd(self):
        cmd = self.cmd_plainTextEdit.toPlainText()
        if cmd == '':
            self.update_run_info('请输入指令内容', 'WARNING')
        else:
            self.cmd_comboBox.addItem(cmd)
            self.commands.append(cmd)
            self.update_run_info(f'保存指令成功{cmd}')

    def del_cmd(self):
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Icon.Question)
        confirm_dialog.setWindowTitle("确认")
        confirm_dialog.setText("是否要删除指令")
        confirm_dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm_dialog.setDefaultButton(QMessageBox.StandardButton.No)
        result = confirm_dialog.exec_()
        current_index = self.cmd_comboBox.currentIndex()
        if current_index == -1:
            return
        current_text = self.cmd_comboBox.currentText()
        if result == QMessageBox.StandardButton.Yes:
            self.cmd_comboBox.removeItem(current_index)
            self.commands.remove(current_text)
            self.update_run_info(f'删除指令成功{current_text}')
        else:
            self.update_run_info(f'删除指令取消{current_text}')

    def select_cmd(self):
        cmd = self.cmd_comboBox.currentText()
        self.cmd_plainTextEdit.setPlainText(cmd)

    def keyPressEvent(self, event):
        # 处理 Ctrl+C 中断（插入 ^C 符号）
        if (event.key() == QtCore.Qt.Key.Key_C and
                event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier):
            event.accept()
            self.cmd_plainTextEdit.insertPlainText("^C")
            self.send_cmd()
            return

        # 处理回车键逻辑
        is_enter = event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
        if is_enter:
            if not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                # 单纯 Enter：发送
                event.accept()
                self.send_cmd()
                return
            # Shift+Enter：走默认换行逻辑，不拦截

        # 其他按键（包括 Shift+Enter）走默认逻辑
        QtWidgets.QPlainTextEdit.keyPressEvent(self.cmd_plainTextEdit, event)

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
