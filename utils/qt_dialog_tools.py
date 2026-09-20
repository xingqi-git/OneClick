# -*- coding: utf-8 -*-
"""
Qt 对话框通用工具
- 统一的 QFileDialog 侧边栏路径
- 统一的文件/文件夹选择对话框（文件+文件夹二合一）
"""
from PyQt5 import QtCore
from PyQt5.QtWidgets import QFileDialog, QDialogButtonBox
from PyQt5.QtCore import QUrl, QStandardPaths


def add_sidebar_urls(dialog):
    """Qt 非原生对话框在 Windows 上的默认侧边栏已经包含：
    - 所有盘符（如"系统 (C:)"、"数据 (D:)"，等价于"此电脑"的内容）
    - Desktop/Downloads/Documents/Pictures/Music/Videos 等常用路径
    - 用户主目录
    不需要额外设置，保留 Qt 默认即可。此函数保留空实现仅为兼容调用。"""
    pass


def select_path_dialog(parent, title="选择", allow_multi=False, default_dir=""):
    """
    弹出文件/文件夹二选一对话框。
    - 选文件：点"选择"按钮，返回选中的文件路径列表
    - 选文件夹：点"当前文件夹"按钮，返回 [当前浏览的文件夹路径]

    参数：
        parent: 父窗口
        title: 对话框标题
        allow_multi: 是否允许选择多个文件（仅对选文件有效）
        default_dir: 默认打开的目录

    返回：
        成功返回路径列表（list[str]），取消返回空列表
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)

    if allow_multi:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    else:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

    # 使用 Qt 自带对话框（才能改按钮文字 + 加侧边栏）
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    if default_dir:
        dialog.setDirectory(default_dir)

    # 侧边栏
    add_sidebar_urls(dialog)

    # 修改按钮文字：AcceptRole="选择"，RejectRole="当前文件夹"
    # 不再 addButton 破坏对齐，取消统一用对话框右上角的 X 按钮
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box:
        dialog._fb_set_choice = lambda choice: setattr(dialog, '_fb_choice', choice)
        for button in button_box.buttons():
            role = button_box.buttonRole(button)
            if role == QDialogButtonBox.ButtonRole.AcceptRole:
                button.setText("选择")
            elif role == QDialogButtonBox.ButtonRole.RejectRole:
                # 原来的取消按钮改成"当前文件夹"
                button.setText("当前文件夹")
                button.clicked.disconnect()
                button.clicked.connect(
                    lambda: (dialog.accept(), dialog._fb_set_choice('dir'))
                )

    dialog._fb_choice = 'select'  # 默认
    if dialog.exec_() == QFileDialog.DialogCode.Accepted:
        if getattr(dialog, '_fb_choice', 'select') == 'dir':
            # 点了"当前文件夹" → 返回当前浏览的文件夹
            current_dir = dialog.directory().absolutePath()
            return [current_dir] if current_dir else []
        else:
            # 点了"选择" → 返回选中的文件
            files = dialog.selectedFiles()
            return files if files else []
    else:
        # 点了取消或 X → 返回空
        return []


def save_file_dialog(parent, title="另存为", default_name="", suffix="", file_filter="", default_dir=""):
    """
    弹出保存文件对话框（带丰富侧边栏）。

    返回：保存路径（str），取消返回空字符串
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

    if default_dir:
        dialog.setDirectory(default_dir)
    if default_name:
        dialog.selectFile(default_name)
    if suffix:
        dialog.setDefaultSuffix(suffix)
    if file_filter:
        dialog.setNameFilter(file_filter)

    add_sidebar_urls(dialog)

    # 修改确定按钮文字
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box:
        for button in button_box.buttons():
            role = button_box.buttonRole(button)
            if role == QDialogButtonBox.ButtonRole.AcceptRole:
                button.setText("保存")

    if dialog.exec_():
        files = dialog.selectedFiles()
        if files:
            path = files[0]
            if suffix and not path.endswith('.' + suffix):
                path += '.' + suffix
            return path
    return ""


def open_file_dialog(parent, title="打开", file_filter="", allow_multi=False, default_dir=""):
    """
    弹出打开文件对话框（带丰富侧边栏）。

    返回：路径列表（list[str]），取消返回空列表
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    if default_dir:
        dialog.setDirectory(default_dir)
    if file_filter:
        dialog.setNameFilter(file_filter)

    if allow_multi:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    else:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

    add_sidebar_urls(dialog)

    # 修改确定按钮文字
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box:
        for button in button_box.buttons():
            role = button_box.buttonRole(button)
            if role == QDialogButtonBox.ButtonRole.AcceptRole:
                button.setText("选择")

    if dialog.exec_():
        return dialog.selectedFiles()
    return []


def select_dir_dialog(parent, title="选择文件夹", default_dir=""):
    """
    弹出选择文件夹对话框（带丰富侧边栏）。

    返回：文件夹路径（str），取消返回空字符串
    """
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.Directory)

    if default_dir:
        dialog.setDirectory(default_dir)

    add_sidebar_urls(dialog)

    # 修改确定按钮文字
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box:
        for button in button_box.buttons():
            role = button_box.buttonRole(button)
            if role == QDialogButtonBox.ButtonRole.AcceptRole:
                button.setText("选择")

    if dialog.exec_():
        files = dialog.selectedFiles()
        if files:
            return files[0]
    return ""
