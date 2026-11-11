# -*- coding: utf-8 -*-
"""记事本快捷按钮
- NotepadDialog：新建/改名配置对话框（只填笔记名称），与 SSH 无关
- NotepadEditWindow：非模态笔记编辑窗口，内容防抖自动保存到该按钮 config 并落盘 config.json
"""
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QCheckBox

from utils.logger import get_logger
from .base_dialog import sc_class2str


class NotepadDialog(QDialog):
    """新建记事本 / 编辑记事本名称（右键"编辑"只改名称）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.logger = get_logger("NotepadDialog")
        self.sc_cfg = {}

        self.setWindowTitle("添加<记事本>")
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.resize(360, 130)

        layout = QVBoxLayout(self)

        # 名称行
        name_row = QHBoxLayout()
        name_label = QLabel("笔记名称：")
        self.name_lineEdit = QLineEdit()
        self.name_lineEdit.setPlaceholderText("例如：随手记")
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_lineEdit)
        layout.addLayout(name_row)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_pushButton = QPushButton("生成快捷按钮")
        self.close_pushButton = QPushButton("关闭")
        btn_row.addWidget(self.save_pushButton)
        btn_row.addWidget(self.close_pushButton)
        layout.addLayout(btn_row)

        self.save_pushButton.clicked.connect(self.create_sc)
        self.close_pushButton.clicked.connect(self.close)

    def create_sc(self):
        name = self.name_lineEdit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "提示", "请填写笔记名称")
            return
        self.sc_cfg = {
            '指令类型': sc_class2str[self.__class__.__name__],  # "记事本"
            '指令名称': name,
            '内容': '',
        }
        if hasattr(self, 'button_id'):
            # 编辑模式只改名：保留原正文，避免整体替换 config 时丢失内容
            old_cfg = self.parent.sc_buttons[self.button_id]['config']
            self.sc_cfg['内容'] = old_cfg.get('内容', '')
        if self.parent:
            if hasattr(self, 'button_id'):
                # 编辑模式：只改名称，保留原内容
                self.parent.edit_button(self.sc_cfg, self.button_id)
            else:
                self.parent.add_button(self.sc_cfg)
        self.accept()

    def edit_sc(self, button_id):
        """右键编辑：回填名称（正文不在此改）"""
        self.button_id = button_id
        cfg = self.parent.sc_buttons[button_id]['config']
        self.setWindowTitle("编辑<记事本>名称")
        self.name_lineEdit.setText(cfg.get('指令名称', ''))
        self.save_pushButton.setText("保存")


class NotepadEditWindow(QWidget):
    """非模态笔记编辑窗口：内容防抖自动写回按钮 config 并落盘"""

    def __init__(self, button_id, parent=None):
        super().__init__()
        self.main_window = parent
        self.button_id = button_id

        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Window)

        cfg = self.main_window.sc_buttons[button_id]['config']
        self.setWindowTitle(f"记事本 - {cfg.get('指令名称', '')}")

        # 尺寸防抖落盘（拖动调整时避免频繁写 config.json）
        self._size_timer = QtCore.QTimer(self)
        self._size_timer.setSingleShot(True)
        self._size_timer.setInterval(400)
        self._size_timer.timeout.connect(self._save_window_size)

        # 恢复上次窗口尺寸（默认 480×360），并限制在当前屏幕可用区域内，
        # 避免上次在大屏上保存的尺寸把小屏下的窗口撑出屏幕
        width, height = 480, 360
        try:
            width = int(cfg.get('窗口宽度', width))
            height = int(cfg.get('窗口高度', height))
        except (TypeError, ValueError):
            width, height = 480, 360
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            width = max(320, min(width, avail.width()))
            height = max(200, min(height, avail.height()))
        self.resize(width, height)

        layout = QVBoxLayout(self)

        # 顶栏：置顶勾选
        top_row = QHBoxLayout()
        self.always_on_top_checkBox = QCheckBox("窗口置顶")
        self.always_on_top_checkBox.toggled.connect(self._on_toggle_on_top)
        top_row.addWidget(self.always_on_top_checkBox)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 编辑区
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(cfg.get('内容', ''))
        layout.addWidget(self.editor)

        # 防抖自动保存：文本变更后 1 秒落盘
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_now)
        self.editor.textChanged.connect(self._save_timer.start)

    def _on_toggle_on_top(self, checked):
        flags = self.windowFlags()
        if checked:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # setWindowFlags 后需重新 show

    def resizeEvent(self, event):
        """尺寸变化后防抖保存（拖动过程中不立即写盘）"""
        super().resizeEvent(event)
        self._size_timer.start()

    def _update_size_cfg(self):
        """把当前窗口尺寸写入按钮配置（只改内存，不落盘）"""
        if self.button_id not in self.main_window.sc_buttons:
            return  # 按钮已删除
        cfg = self.main_window.sc_buttons[self.button_id]['config']
        cfg['窗口宽度'] = self.width()
        cfg['窗口高度'] = self.height()

    def _save_window_size(self):
        """尺寸防抖到点：写入配置并落盘"""
        self._update_size_cfg()
        self.main_window._save_config_auto()

    def _save_now(self):
        if self.button_id not in self.main_window.sc_buttons:
            return  # 按钮已删除
        text = self.editor.toPlainText()
        self.main_window.sc_buttons[self.button_id]['config']['内容'] = text
        self.main_window._save_config_auto()

    def closeEvent(self, event):
        self._size_timer.stop()
        self._update_size_cfg()  # 关窗前立即记下最终尺寸（防抖可能还没到点）
        self._save_timer.stop()
        self._save_now()  # 关窗兜底保存
        # 通知主窗口移除引用
        if hasattr(self.main_window, '_on_notepad_closed'):
            self.main_window._on_notepad_closed(self.button_id)
        event.accept()
