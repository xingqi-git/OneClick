# -*- coding: utf-8 -*-
"""
远程文件浏览器控件（方案B：单栏远程文件列表）
- 地址栏 + 工具栏（上级、刷新、上传、下载）
- QTreeWidget 显示文件列表
- 双击文件夹进入，双击文件→下载到本地 OneClick_Temp→本地软件打开
- 右键菜单：重命名、删除、下载、新建文件/文件夹
- 拖入上传（批量本地文件/文件夹→当前远程目录）
- 拖出下载（选中远程文件/文件夹→弹框选位置→批量下载）
- 所有操作通过外部传入的 ssh_tool 执行
"""
import os
import stat
import weakref
import datetime
import subprocess
from urllib.parse import unquote
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QUrl, QEvent


def _detect_explorer_folder(hwnd):
    """
    通过 PowerShell Shell.Application 拿资源管理器窗口的 LocationURL → 转本地路径。
    hwnd: int，资源管理器窗口句柄
    返回：本地绝对路径字符串，失败返回 None
    """
    try:
        ps = (
            "$hwnd = {hwnd}; "
            "$shell = New-Object -ComObject Shell.Application; "
            "foreach ($w in $shell.Windows()) {{ "
            "  try {{ if ([int]$w.HWND -eq $hwnd) {{ Write-Output $w.LocationURL; break }} }} catch {{}} "
            "}}"
        ).format(hwnd=int(hwnd))
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        url = result.stdout.strip()
        if not url or not url.startswith('file:///'):
            return None
        # file:///C:/Users/xingq/Downloads → C:\Users\xingq\Downloads
        path = unquote(url[8:])  # 去掉 file:///
        path = path.replace('/', '\\')
        return path
    except Exception:
        return None


class _RemoteTreeWidget(QtWidgets.QTreeWidget):
    """
    远程文件列表专用 QTreeWidget 子类：
    - 完全自己接管拖拽状态机（不进 Qt 默认 startDrag）
    - 通过父级 FileBrowserWidget 显示手动拖拽的半透明浮窗
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_pos = None
        self._started = False
        self._mouse_pressed = False
        self._items_at_press = []

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press_pos = event.globalPos()
            self._started = False
            self._mouse_pressed = True
            self._items_at_press = []
            fb = self.parent()
            if fb is not None and hasattr(fb, 'tree') and fb.tree is self and hasattr(fb, '_full_path'):
                for item in self.selectedItems():
                    name = item.data(0, QtCore.Qt.UserRole)
                    self._items_at_press.append(fb._full_path(name))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 拖拽开始后完全阻断 QTreeWidget 默认行为（防止移动鼠标时触发多选）
        if self._press_pos is not None and self._mouse_pressed and len(self._items_at_press) > 0:
            if event.buttons() & QtCore.Qt.LeftButton:
                if not self._started and (event.globalPos() - self._press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    self._started = True
                    self.parent()._start_manual_drag_out(self._items_at_press)
                # 不调 super()，阻断 Qt 默认的 hover-select 行为
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press_pos = None
            self._started = False
            self._mouse_pressed = False
            if self.parent() is not None and hasattr(self.parent(), '_end_manual_drag_out'):
                self.parent()._end_manual_drag_out()
        super().mouseReleaseEvent(event)


class _DragOverlayWidget(QtWidgets.QWidget):

    def __init__(self, items_at_press, app_window=None):
        super().__init__(None)  # 独立窗口（无 parent），才能跨窗口显示
        self._items_at_press = items_at_press
        self._app_window = app_window

        # 取第一个文件名做显示文本（多项显示 "name, name(2)"）
        names = [os.path.basename(p.rstrip('/')) for p in items_at_press]
        if len(names) == 1:
            self._text = names[0]
        else:
            self._text = f"{names[0]} +{len(names)-1}"

        self._forbidden = True  # 当前是否显示禁止图标

        # 半透明样式
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)  # 让 ctypes 能"穿透"浮窗拿到下面的真实窗口
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool |
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._text_label = QtWidgets.QLabel(self._text, self)
        self._text_label.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,180);
                color: #fff;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self._text_label)

        self._forbidden_label = QtWidgets.QLabel("⛔", self)
        self._forbidden_label.setStyleSheet("""
            QLabel {
                background: transparent;
                padding: 2px;
                font-size: 16px;
            }
        """)
        layout.addWidget(self._forbidden_label)

        self.adjustSize()

    def update_forbidden(self):
        """根据当前鼠标位置是否在软件窗口内，切换禁止图标"""
        if self._app_window is None:
            return
        cursor_pos = QtGui.QCursor.pos()
        win_rect = self._app_window.geometry()
        inside = win_rect.contains(cursor_pos)
        if inside and not self._forbidden:
            self._forbidden = True
            self._forbidden_label.show()
            self.adjustSize()
        elif not inside and self._forbidden:
            self._forbidden = False
            self._forbidden_label.hide()
            self.adjustSize()

    def follow_cursor(self):
        """每 20ms 跟随一次鼠标位置"""
        cursor_pos = QtGui.QCursor.pos()
        self.move(cursor_pos.x() + 16, cursor_pos.y() + 16)
        self.update_forbidden()


class FileBrowserWidget(QtWidgets.QWidget):
    """远程 SFTP 文件浏览器"""

    upload_requested = QtCore.pyqtSignal(str, list)       # (远程目标目录, 本地文件/文件夹列表)
    download_requested = QtCore.pyqtSignal(list, str)     # (远程完整路径列表, 本地目标目录)
    open_file_requested = QtCore.pyqtSignal(str)          # (远程完整文件路径) 双击远程文件→本地打开
    open_with_requested = QtCore.pyqtSignal(str)          # (远程完整文件路径) 右键"打开方式..."→选择程序打开
    status_changed = QtCore.pyqtSignal(str)               # 状态变化提示

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sftp = None        # paramiko SFTPClient，外部设置
        self._ssh_tool = None    # SSHTools 实例，外部设置
        self._current_path = '/' # 当前远程路径
        self._connected = False
        # 每个连接（终端标签）各自记住浏览到的目录，切回该标签时恢复。
        # 弱引用 key：连接关闭、标签删除后条目随对象一起消失，不占内存
        self._path_by_tool = weakref.WeakKeyDictionary()
        # 手动拖出状态
        self._drag_overlay = None   # 当前显示的拖出浮窗
        self._drag_timer = None     # 跟随鼠标的 QTimer
        self._drag_paths = []       # 当前拖拽的远程路径列表

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ---- 标题行 ----
        title_row = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("远程文件", self)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        # ---- 地址栏 + 工具栏 ----
        tool_row = QtWidgets.QHBoxLayout()
        tool_row.setSpacing(3)

        self.up_btn = QtWidgets.QPushButton("↑", self)
        self.up_btn.setFixedWidth(30)
        self.up_btn.setToolTip("上级目录")
        self.up_btn.clicked.connect(self.go_up)
        tool_row.addWidget(self.up_btn)

        self.path_edit = QtWidgets.QLineEdit(self)
        self.path_edit.setPlaceholderText("远程路径")
        self.path_edit.returnPressed.connect(self.go_to_path)
        tool_row.addWidget(self.path_edit, 1)

        self.refresh_btn = QtWidgets.QPushButton("刷新", self)
        self.refresh_btn.setFixedWidth(50)
        self.refresh_btn.clicked.connect(self.refresh)
        tool_row.addWidget(self.refresh_btn)

        self.upload_file_btn = QtWidgets.QPushButton("传文件", self)
        self.upload_file_btn.setFixedWidth(55)
        self.upload_file_btn.setToolTip("上传文件到当前目录")
        self.upload_file_btn.clicked.connect(self._on_upload_file_clicked)
        tool_row.addWidget(self.upload_file_btn)

        self.upload_dir_btn = QtWidgets.QPushButton("传文件夹", self)
        self.upload_dir_btn.setFixedWidth(65)
        self.upload_dir_btn.setToolTip("上传文件夹到当前目录")
        self.upload_dir_btn.clicked.connect(self._on_upload_dir_clicked)
        tool_row.addWidget(self.upload_dir_btn)

        self.download_btn = QtWidgets.QPushButton("下载", self)
        self.download_btn.setFixedWidth(50)
        self.download_btn.setToolTip("下载选中的文件/文件夹")
        self.download_btn.clicked.connect(self._on_download_clicked)
        tool_row.addWidget(self.download_btn)

        layout.addLayout(tool_row)

        # ---- 文件列表 ----
        self.tree = _RemoteTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["名称", "大小", "修改时间"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 120)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        # 右键菜单
        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        # 拖拽：允许拖入（本地文件→远程上传）
        self.tree.setAcceptDrops(True)
        # 拖出下载：完全自己接管（mouseMove/mouseRelease），不启用 Qt 默认拖出
        # DropOnly = 只接受拖入，不支持 Qt 默认拖出
        self.tree.setDragEnabled(False)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        # 拖入上传：安装事件过滤器处理 DragEnter/Drop
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree, 1)

        # ---- 底部状态栏 ----
        self.status_label = QtWidgets.QLabel("未连接", self)
        self.status_label.setStyleSheet("color: #888; padding: 2px 0;")
        layout.addWidget(self.status_label)

        self._set_buttons_enabled(False)

    # -------- 外部接口 --------

    def set_ssh_tool(self, ssh_tool):
        """设置已连接的 SSHTools 实例"""
        self._ssh_tool = ssh_tool
        if ssh_tool is not None and ssh_tool.is_connected():
            try:
                self._sftp = ssh_tool.ssh.open_sftp()
            except Exception as e:
                self.status_label.setText(f"打开SFTP失败: {e}")
                self._sftp = None
                self._connected = False
                return
            self._connected = True
            # 默认进入用户主目录；该连接此前浏览过目录则恢复它自己的目录
            # （多终端标签各自记住自己的位置，切换标签时互不干扰）
            try:
                home = self._sftp.normalize('.')
            except Exception:
                home = '/'
            try:
                saved = self._path_by_tool.get(ssh_tool)
            except TypeError:
                saved = None
            if saved and saved != home:
                # 先落到主目录兜底：恢复失败（目录被删/无权限）时浏览器仍可用
                self._current_path = home
                self.path_edit.setText(home)
                self._set_buttons_enabled(True)
                self._load_path(saved)
            else:
                self._current_path = home
                self.path_edit.setText(self._current_path)
                self._set_buttons_enabled(True)
                self.refresh()
            self.status_label.setText("已连接")
            self.status_changed.emit("已连接")
        else:
            self._connected = False
            if self._sftp is not None:
                try:
                    self._sftp.close()
                except Exception:
                    pass
                self._sftp = None
            self.tree.clear()
            self.path_edit.clear()
            self._set_buttons_enabled(False)
            self.status_label.setText("未连接")
            self.status_changed.emit("未连接")

    def is_connected(self):
        return self._connected and self._sftp is not None

    def set_title_style(self, style_sheet):
        """设置标题标签样式（与主界面其他标题统一）"""
        self.title_label.setStyleSheet(style_sheet)

    def current_path(self):
        return self._current_path

    # -------- 导航 --------

    def go_up(self):
        if not self.is_connected():
            return
        if self._current_path == '/' or self._current_path == '':
            return
        parent = os.path.dirname(self._current_path.rstrip('/'))
        if not parent:
            parent = '/'
        self._load_path(parent)

    def go_to_path(self):
        if not self.is_connected():
            return
        path = self.path_edit.text().strip()
        if not path:
            return
        self._load_path(path)

    def refresh(self):
        if not self.is_connected():
            return
        self._load_path(self._current_path)

    def _load_path(self, path):
        """加载指定远程路径"""
        if not self.is_connected():
            return
        try:
            items = self._sftp.listdir_attr(path)
        except Exception as e:
            self.status_label.setText(f"无法访问: {e}")
            return

        # 规范化路径
        try:
            normalized = self._sftp.normalize(path)
            self._current_path = normalized
            self.path_edit.setText(normalized)
        except Exception:
            self._current_path = path

        # 记住该连接浏览到的目录（切换终端标签后再切回来时恢复）
        if self._ssh_tool is not None:
            try:
                self._path_by_tool[self._ssh_tool] = self._current_path
            except TypeError:
                pass

        self.tree.clear()

        # 先排目录、再排文件；各自按名称排序
        dirs = []
        files = []
        for attr in items:
            if attr.filename.startswith('.'):
                # 跳过隐藏文件，列表太乱
                continue
            if stat.S_ISDIR(attr.st_mode):
                dirs.append(attr)
            else:
                files.append(attr)

        dirs.sort(key=lambda a: a.filename.lower())
        files.sort(key=lambda a: a.filename.lower())

        for attr in dirs:
            item = self._make_item(attr, is_dir=True)
            self.tree.addTopLevelItem(item)

        for attr in files:
            item = self._make_item(attr, is_dir=False)
            self.tree.addTopLevelItem(item)

        self.status_label.setText(f"{len(dirs)} 个目录，{len(files)} 个文件")

    def _make_item(self, attr, is_dir):
        name = attr.filename
        if is_dir:
            display_name = name + '/'
        else:
            display_name = name

        # 大小
        if is_dir:
            size_str = ''
        else:
            size_str = self._format_size(attr.st_size)

        # 修改时间
        try:
            mtime = datetime.datetime.fromtimestamp(attr.st_mtime)
            time_str = mtime.strftime('%Y-%m-%d %H:%M')
        except Exception:
            time_str = ''

        item = QtWidgets.QTreeWidgetItem([display_name, size_str, time_str])
        item.setData(0, QtCore.Qt.UserRole, name)
        item.setData(0, QtCore.Qt.UserRole + 1, is_dir)

        # 图标
        icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_DirIcon if is_dir else QtWidgets.QStyle.SP_FileIcon)
        item.setIcon(0, icon)

        if is_dir:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)

        return item

    def _format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} K"
        elif size < 1024 * 1024 * 1024:
            return f"{size/1024/1024:.1f} M"
        else:
            return f"{size/1024/1024/1024:.1f} G"

    def _full_path(self, name):
        """拼接当前目录 + 文件名"""
        if self._current_path == '/':
            return '/' + name
        return self._current_path.rstrip('/') + '/' + name

    # -------- 右键菜单 --------

    def _show_context_menu(self, pos):
        """在鼠标位置弹出右键菜单"""
        if not self.is_connected():
            return

        item = self.tree.itemAt(pos)
        selected = self.tree.selectedItems()
        has_selection = len(selected) > 0

        menu = QtWidgets.QMenu(self)

        act_open_with = None
        act_rename = None
        act_delete = None
        act_download = None

        if has_selection:
            # 有选中项：文件/文件夹操作
            if len(selected) == 1 and not selected[0].data(0, QtCore.Qt.UserRole + 1):
                # 单选且是文件：允许选择打开方式
                act_open_with = menu.addAction("打开方式...")
            if len(selected) == 1:
                act_rename = menu.addAction("重命名")
            act_delete = menu.addAction(f"删除 ({len(selected)}项)")
            act_download = menu.addAction(f"下载 ({len(selected)}项)")
            menu.addSeparator()

        # 空白处：新建 + 刷新
        act_new_file = menu.addAction("新建文件")
        act_new_dir = menu.addAction("新建文件夹")
        menu.addSeparator()
        act_refresh = menu.addAction("刷新")

        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))

        if action is None:
            return

        if act_open_with is not None and action == act_open_with:
            self.open_with_requested.emit(
                self._full_path(selected[0].data(0, QtCore.Qt.UserRole)))
        elif act_rename is not None and action == act_rename:
            self._rename_item(selected[0])
        elif act_delete is not None and action == act_delete:
            self._delete_items(selected)
        elif act_download is not None and action == act_download:
            self._on_download_clicked()
        elif action == act_new_file:
            self._new_file()
        elif action == act_new_dir:
            self._new_directory()
        elif action == act_refresh:
            self.refresh()

    # -------- 右键操作实现 --------

    def _rename_item(self, item):
        """重命名文件/文件夹"""
        old_name = item.data(0, QtCore.Qt.UserRole)
        old_path = self._full_path(old_name)
        is_dir = item.data(0, QtCore.Qt.UserRole + 1)

        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "重命名", "新名称:", text=old_name)
        if not ok or not new_name.strip() or new_name == old_name:
            return
        new_name = new_name.strip()
        new_path = self._full_path(new_name)

        try:
            self._sftp.rename(old_path, new_path)
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "重命名失败", str(e))

    def _delete_items(self, items):
        """删除文件/文件夹（多选）"""
        # 收集路径，去掉末尾的 "/"
        targets = []
        for item in items:
            name = item.data(0, QtCore.Qt.UserRole)
            is_dir = item.data(0, QtCore.Qt.UserRole + 1)
            full = self._full_path(name)
            targets.append((full, is_dir))

        names_preview = ', '.join(t[0].split('/')[-1] for t in targets[:5])
        if len(targets) > 5:
            names_preview += f' 等{len(targets)}项'

        reply = QtWidgets.QMessageBox.warning(
            self, "确认删除",
            f"确定要删除以下内容吗？\n\n{names_preview}\n\n此操作不可恢复！",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)

        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        errors = []
        for full_path, is_dir in targets:
            try:
                if is_dir:
                    self._sftp_rmtree(full_path)
                else:
                    self._sftp.remove(full_path)
            except Exception as e:
                errors.append(f"{full_path}: {e}")

        self.refresh()

        if errors:
            QtWidgets.QMessageBox.warning(
                self, "部分删除失败",
                "以下项目删除失败：\n\n" + '\n'.join(errors))

    def _sftp_rmtree(self, remote_dir):
        """递归删除远程目录（SFTP 没提供，自己实现）"""
        # 先列出目录内容
        try:
            contents = self._sftp.listdir_attr(remote_dir)
        except Exception:
            return  # 目录不存在或无权限，跳过

        for attr in contents:
            if attr.filename.startswith('.'):
                continue
            child_path = remote_dir.rstrip('/') + '/' + attr.filename
            if stat.S_ISDIR(attr.st_mode):
                self._sftp_rmtree(child_path)
            else:
                self._sftp.remove(child_path)

        self._sftp.rmdir(remote_dir)

    def _new_file(self):
        """在当前目录新建空文件"""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建文件", "文件名:")
        if not ok or not name.strip():
            return
        name = name.strip()
        full_path = self._full_path(name)

        # 检查是否已存在
        try:
            self._sftp.stat(full_path)
            QtWidgets.QMessageBox.warning(self, "已存在", f"文件 '{name}' 已存在")
            return
        except IOError:
            pass  # 不存在，继续

        try:
            # SFTP.open 相当于 touch
            with self._sftp.open(full_path, 'w'):
                pass
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "创建失败", str(e))

    def _new_directory(self):
        """在当前目录新建文件夹"""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建文件夹", "文件夹名:")
        if not ok or not name.strip():
            return
        name = name.strip()
        full_path = self._full_path(name)

        # 检查是否已存在
        try:
            self._sftp.stat(full_path)
            QtWidgets.QMessageBox.warning(self, "已存在", f"文件夹 '{name}' 已存在")
            return
        except IOError:
            pass

        try:
            self._sftp.mkdir(full_path)
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "创建失败", str(e))

    # -------- 交互 --------

    def _on_item_double_clicked(self, item, column):
        if not self.is_connected():
            return
        name = item.data(0, QtCore.Qt.UserRole)
        is_dir = item.data(0, QtCore.Qt.UserRole + 1)
        if is_dir:
            new_path = self._full_path(name)
            self._load_path(new_path)
        else:
            # 双击远程文件 → 下载到 OneClick_Temp 并本地打开
            full = self._full_path(name)
            self.open_file_requested.emit(full)

    # -------- 事件过滤器：拖入上传 + 拖出下载 --------

    def eventFilter(self, obj, event):
        """拦截 tree 上的拖入事件（DragEnter/DragMove/Drop）"""
        if obj is not self.tree:
            return super().eventFilter(obj, event)

        evt_type = event.type()

        # ---- 拖入（本地文件/文件夹 → 远程上传）----
        if evt_type == QEvent.DragEnter or evt_type == QEvent.DragMove:
            if self._connected and event.mimeData().hasUrls():
                # 有本地文件可拖入，且已连接 → 接受
                event.acceptProposedAction()
                return True
            return False

        if evt_type == QEvent.Drop:
            if self._connected and event.mimeData().hasUrls():
                local_paths = []
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if path:
                        local_paths.append(path)
                if local_paths:
                    self.upload_requested.emit(self._current_path, local_paths)
                    self.status_label.setText(f"已接收 {len(local_paths)} 项，开始上传…")
                return True
            return False

        return super().eventFilter(obj, event)

    # -------- 拖出下载：纯手动拖拽（无 QDrag / 无后台下载） --------

    def _start_manual_drag_out(self, remote_paths):
        """超过拖拽阈值时调用：显示跟随鼠标的半透明浮窗，启动 QTimer 跟随"""
        self._drag_paths = remote_paths
        # app_window = self.window() 获取顶层主窗口，供浮窗判断"在窗口内/外"
        self._drag_overlay = _DragOverlayWidget(remote_paths, app_window=self.window())
        self._drag_overlay.show()
        self._drag_overlay.follow_cursor()

        # QTimer 每 20ms 更新浮窗位置和禁止图标状态
        self._drag_timer = QtCore.QTimer(self)
        self._drag_timer.setInterval(20)
        self._drag_timer.timeout.connect(self._drag_overlay.follow_cursor)
        self._drag_timer.start()

    def _end_manual_drag_out(self):
        """鼠标松开时调用：停 QTimer、隐藏浮窗、检测鼠标下的真实目录 → 下载或取消"""
        # 停计时器
        if self._drag_timer is not None:
            self._drag_timer.stop()
            self._drag_timer.deleteLater()
            self._drag_timer = None

        local_dir = None

        if self._drag_overlay is not None:
            app_win = self._drag_overlay._app_window
            mouse_outside = (app_win is not None and
                             not app_win.geometry().contains(QtGui.QCursor.pos()))
            self._drag_overlay.hide()
            self._drag_overlay.deleteLater()
            self._drag_overlay = None

            if mouse_outside and self._drag_paths:
                # 在软件窗口外松手 → 检测鼠标下的真实 Windows 目录
                local_dir = self._detect_folder_under_cursor()
                if local_dir is None:
                    # 检测失败 → 弹框让用户选
                    from PyQt5.QtWidgets import QFileDialog
                    local_dir = QFileDialog.getExistingDirectory(self, "选择下载到的文件夹")
                    if not local_dir:
                        local_dir = None  # 用户取消

        if local_dir and self._drag_paths:
            self.download_requested.emit(self._drag_paths, local_dir)
            self.status_label.setText(f"开始下载到 {local_dir}…")

        self._drag_paths = []

    # ---- Windows 路径检测（ctypes + PowerShell） ----

    @staticmethod
    def _detect_folder_under_cursor():
        """
        检测鼠标下的真实 Windows 目录。
        返回本地绝对路径，失败返回 None。
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32

            # 1. 取鼠标坐标
            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))

            # 2. WindowFromPoint（POINT 按值传，不是 byref）
            hwnd = user32.WindowFromPoint(pt)
            if not hwnd:
                return None

            # 3. 爬升到顶层窗口（GA_ROOT = 2）
            GA_ROOT = 2
            root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                hwnd = root_hwnd

            # 4. GetClassNameW
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            cls = buf.value

            # 5a. 桌面（Progman）或隐藏桌面（WorkerW）
            CSIDL_DESKTOP = 0
            if cls in ('Progman', 'WorkerW'):
                buf_path = ctypes.create_unicode_buffer(260)
                if shell32.SHGetFolderPathW(0, CSIDL_DESKTOP, 0, 0, buf_path) == 0:
                    return buf_path.value
                return None

            # 5b. 资源管理器（CabinetWClass）→ PowerShell Shell.Application 拿路径
            if cls == 'CabinetWClass':
                return _detect_explorer_folder(hwnd)

            return None
        except Exception:
            return None

    def _on_upload_file_clicked(self):
        """上传文件到当前目录"""
        if not self.is_connected():
            QtWidgets.QMessageBox.information(self, "提示", "请先连接服务器")
            return

        from PyQt5.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要上传的文件", "", "")
        if not paths:
            return
        self.upload_requested.emit(self._current_path, paths)

    def _on_upload_dir_clicked(self):
        """上传文件夹到当前目录"""
        if not self.is_connected():
            QtWidgets.QMessageBox.information(self, "提示", "请先连接服务器")
            return

        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择要上传的文件夹")
        if not folder:
            return
        self.upload_requested.emit(self._current_path, [folder])

    def _on_download_clicked(self):
        """下载选中的文件/文件夹"""
        if not self.is_connected():
            QtWidgets.QMessageBox.information(self, "提示", "请先连接服务器")
            return

        selected = self.tree.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要下载的文件")
            return

        from PyQt5.QtWidgets import QFileDialog
        local_dir = QFileDialog.getExistingDirectory(self, "选择保存到的本地文件夹")
        if not local_dir:
            return

        remote_paths = []
        for item in selected:
            name = item.data(0, QtCore.Qt.UserRole)
            remote_paths.append(self._full_path(name))

        self.download_requested.emit(remote_paths, local_dir)

    def _set_buttons_enabled(self, enabled):
        self.up_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.upload_file_btn.setEnabled(enabled)
        self.upload_dir_btn.setEnabled(enabled)
        self.download_btn.setEnabled(enabled)
        self.path_edit.setEnabled(enabled)
        self.tree.setEnabled(enabled)
