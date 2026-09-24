# -*- coding: utf-8 -*-
"""
远程文件浏览器控件（方案B：单栏远程文件列表）
- 地址栏 + 工具栏（上级、刷新、上传、下载）
- QTreeWidget 显示文件列表
- 双击文件夹进入
- 右键菜单：重命名、删除、下载、新建文件/文件夹
- 所有操作通过外部传入的 ssh_tool 执行
"""
import os
import stat
import datetime
from PyQt5 import QtWidgets, QtCore, QtGui


class FileBrowserWidget(QtWidgets.QWidget):
    """远程 SFTP 文件浏览器"""

    upload_requested = QtCore.pyqtSignal(str, list)  # (远程目标目录, 本地文件列表)
    download_requested = QtCore.pyqtSignal(list, str)  # (远程文件列表, 本地目标目录)
    status_changed = QtCore.pyqtSignal(str)  # 状态变化提示

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sftp = None        # paramiko SFTPClient，外部设置
        self._ssh_tool = None    # SSHTools 实例，外部设置
        self._current_path = '/' # 当前远程路径
        self._connected = False

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
        self.tree = QtWidgets.QTreeWidget(self)
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
            # 默认进入用户主目录
            try:
                home = self._sftp.normalize('.')
                self._current_path = home
            except Exception:
                self._current_path = '/'
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

        act_rename = None
        act_delete = None
        act_download = None

        if has_selection:
            # 有选中项：文件/文件夹操作
            if len(selected) == 1:
                act_rename = menu.addAction("重命名")
            act_delete = menu.addAction(f"删除 ({len(selected)}项)")
            act_download = menu.addAction(f"下载 ({len(selected)}项)")
            menu.addSeparator()

        # 空白处：新建
        act_new_file = menu.addAction("新建文件")
        act_new_dir = menu.addAction("新建文件夹")

        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))

        if action is None:
            return

        if act_rename is not None and action == act_rename:
            self._rename_item(selected[0])
        elif act_delete is not None and action == act_delete:
            self._delete_items(selected)
        elif act_download is not None and action == act_download:
            self._on_download_clicked()
        elif action == act_new_file:
            self._new_file()
        elif action == act_new_dir:
            self._new_directory()

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
