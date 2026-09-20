# -*- coding: utf-8 -*-
"""
模块延迟加载管理器
- 后台线程预加载重型模块
- 未加载完成时触发操作，自动等待并显示加载提示
"""
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker, Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar


# 模块加载状态
STATUS_NONE = 'none'       # 未加载
STATUS_LOADING = 'loading' # 加载中
STATUS_READY = 'ready'     # 加载完成


# 模块分组定义（加载顺序按列表顺序）
# 每个元素：(模块名, 加载函数)
# 加载函数在子线程中执行，负责 import 和初始化
MODULE_GROUPS = [
    ('paramiko', None),   # SSH 连接相关
    ('pyte', None),       # 终端相关
    ('matplotlib', None), # 绘图相关
    ('pandas', None),     # 数据处理相关
]


class _LoadingDialog(QDialog):
    """加载中提示对话框"""
    
    def __init__(self, module_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle('加载中')
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(300, 100)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(f'正在加载 {module_label}...', self)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)  # 不确定进度
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)


class ModuleLoader:
    """
    模块加载管理器（单例）
    """
    _instance = None
    
    def __init__(self):
        self._mutex = QMutex()
        self._status = {}     # 模块名 -> 状态
        self._modules = {}    # 模块名 -> 模块对象（如果需要直接获取模块的话）
        self._waiting_cbs = {} # 模块名 -> [callback, ...]
        self._thread = None
        self._started = False
        self._main_window = None  # 用于做加载对话框的 parent
        
        # 初始化状态
        for name, _ in MODULE_GROUPS:
            self._status[name] = STATUS_NONE
            self._waiting_cbs[name] = []
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ModuleLoader()
        return cls._instance
    
    def set_main_window(self, main_window):
        """设置主窗口，用于加载对话框的 parent"""
        self._main_window = main_window
    
    def start_preload(self):
        """启动后台预加载线程"""
        if self._started:
            return
        self._started = True
        
        self._thread = _PreloadThread()
        self._thread.module_loading.connect(self._on_module_loading)
        self._thread.module_loaded.connect(self._on_module_loaded)
        self._thread.all_finished.connect(self._on_all_finished)
        self._thread.start()
    
    def _on_module_loading(self, name):
        """某个模块开始加载"""
        with QMutexLocker(self._mutex):
            self._status[name] = STATUS_LOADING
    
    def _on_module_loaded(self, name):
        """某个模块加载完成"""
        cbs = []
        with QMutexLocker(self._mutex):
            self._status[name] = STATUS_READY
            cbs = self._waiting_cbs.get(name, [])
            self._waiting_cbs[name] = []
        
        # 在主线程执行回调
        for cb in cbs:
            try:
                cb()
            except Exception:
                import traceback
                traceback.print_exc()
    
    def _on_all_finished(self):
        """所有模块加载完成"""
        pass
    
    def get_status(self, name):
        """获取模块状态"""
        with QMutexLocker(self._mutex):
            return self._status.get(name, STATUS_NONE)
    
    def is_ready(self, name):
        """模块是否已加载完成"""
        return self.get_status(name) == STATUS_READY
    
    def ensure(self, module_name, callback, label=None):
        """
        确保模块加载完成后执行 callback。
        - 已加载：直接执行
        - 加载中/未加载：显示等待对话框，加载完后执行
        """
        if self.is_ready(module_name):
            callback()
            return
        
        # 如果还没开始加载，手动触发该模块的加载
        if self.get_status(module_name) == STATUS_NONE:
            # 预加载线程可能还没到这个模块，或者根本没启动预加载
            # 这里直接等预加载线程按顺序来即可，不用额外操作
            pass
        
        # 注册回调
        with QMutexLocker(self._mutex):
            self._waiting_cbs[module_name].append(callback)
        
        # 显示加载对话框（用 QTimer 在下一事件循环显示，避免立即阻塞）
        display_label = label or module_name
        QTimer.singleShot(0, lambda: self._show_loading_dialog(module_name, display_label))
    
    def ensure_sync(self, module_name, label=None):
        """
        同步等待模块加载完成（阻塞式，显示对话框）。
        不推荐使用，优先用 ensure(callback)。
        """
        if self.is_ready(module_name):
            return
        
        display_label = label or module_name
        dlg = _LoadingDialog(display_label, self._main_window)
        
        # 连接信号：加载完成就关闭对话框
        def _on_done():
            dlg.accept()
        
        with QMutexLocker(self._mutex):
            self._waiting_cbs[module_name].append(_on_done)
        
        dlg.exec_()
    
    def _show_loading_dialog(self, module_name, label):
        """显示加载中对话框，加载完成后自动关闭"""
        if self.is_ready(module_name):
            return
        
        dlg = _LoadingDialog(label, self._main_window)
        
        def _on_done():
            dlg.accept()
        
        with QMutexLocker(self._mutex):
            self._waiting_cbs[module_name].append(_on_done)
        
        dlg.exec_()
    
    def ensure_all(self, module_names, callback, label=None):
        """
        确保多个模块都加载完成后执行 callback。
        """
        remaining = list(module_names)
        display_label = label or ', '.join(module_names)
        
        def _check_next():
            if not remaining:
                callback()
                return
            next_mod = remaining.pop(0)
            self.ensure(next_mod, _check_next, display_label)
        
        _check_next()


class _PreloadThread(QThread):
    """后台预加载线程"""
    
    module_loading = pyqtSignal(str)   # 开始加载某模块
    module_loaded = pyqtSignal(str)    # 某模块加载完成
    all_finished = pyqtSignal()        # 全部完成
    
    def run(self):
        for name, _ in MODULE_GROUPS:
            self.module_loading.emit(name)
            try:
                self._load_module(name)
            except Exception:
                import traceback
                traceback.print_exc()
            self.module_loaded.emit(name)
        
        self.all_finished.emit()
    
    def _load_module(self, name):
        """加载指定模块"""
        if name == 'paramiko':
            import paramiko  # noqa: F401
            # 顺带预加载常用的子模块
            from paramiko import SSHClient, AutoAddPolicy, SFTPClient  # noqa: F401
        
        elif name == 'pyte':
            import pyte  # noqa: F401
            from pyte import HistoryScreen, ByteStream, modes  # noqa: F401
            import wcwidth  # noqa: F401
        
        elif name == 'matplotlib':
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.figure import Figure  # noqa: F401
            from matplotlib.backends.backend_qt5agg import (  # noqa: F401
                FigureCanvasQTAgg as FigureCanvas,
                NavigationToolbar2QT as NavigationToolbar,
            )
            import matplotlib.cm  # noqa: F401
        
        elif name == 'pandas':
            import pandas  # noqa: F401
            import numpy  # noqa: F401
