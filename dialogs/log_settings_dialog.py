# -*- coding: utf-8 -*-
"""
日志设置对话框
"""
from PyQt5 import QtCore, QtWidgets


class LogSettingsDialog(QtWidgets.QDialog):
    """日志设置对话框：文件日志开关、文件日志级别、面板日志级别、文件保留个数"""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("日志设置")
        self.setMinimumWidth(380)
        self.setModal(True)

        # 默认配置
        self.config = config or {}
        self._file_enabled = self.config.get('文件日志', True)
        self._file_level = self.config.get('文件日志级别', 'INFO')
        self._panel_level = self.config.get('面板日志级别', 'INFO')
        self._backup_count = self.config.get('文件保留个数', 5)

        self._init_ui()
        self._apply_values()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---- 文件日志开关 ----
        self.file_enable_check = QtWidgets.QCheckBox("启用文件日志")
        self.file_enable_check.toggled.connect(self._on_file_enable_toggled)
        layout.addWidget(self.file_enable_check)

        # ---- 文件日志级别 ----
        file_group = QtWidgets.QGroupBox("文件日志级别")
        file_layout = QtWidgets.QVBoxLayout(file_group)
        file_layout.setSpacing(6)
        self.file_level_btns = {}
        for level, desc in [
            ('DEBUG', 'DEBUG — 最详细（含调试信息）'),
            ('INFO', 'INFO — 默认（日常运行）'),
            ('WARNING', 'WARNING — 仅警告和错误'),
            ('ERROR', 'ERROR — 仅错误'),
        ]:
            rb = QtWidgets.QRadioButton(desc)
            self.file_level_btns[level] = rb
            file_layout.addWidget(rb)
        layout.addWidget(file_group)

        # ---- 面板日志级别 ----
        panel_group = QtWidgets.QGroupBox("运行信息面板级别")
        panel_layout = QtWidgets.QVBoxLayout(panel_group)
        panel_layout.setSpacing(6)
        self.panel_level_btns = {}
        for level, desc in [
            ('INFO', 'INFO — 全部（操作 + 警告 + 错误）'),
            ('WARNING', 'WARNING — 仅警告和错误'),
            ('ERROR', 'ERROR — 仅错误'),
        ]:
            rb = QtWidgets.QRadioButton(desc)
            self.panel_level_btns[level] = rb
            panel_layout.addWidget(rb)
        layout.addWidget(panel_group)

        # ---- 文件保留个数 ----
        backup_layout = QtWidgets.QHBoxLayout()
        backup_layout.addWidget(QtWidgets.QLabel("日志文件保留个数："))
        self.backup_spin = QtWidgets.QSpinBox()
        self.backup_spin.setRange(1, 100)
        self.backup_spin.setSuffix(" 个")
        backup_layout.addWidget(self.backup_spin)
        backup_layout.addStretch()
        layout.addLayout(backup_layout)

        layout.addStretch()

        # ---- 按钮 ----
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.ok_btn = QtWidgets.QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _apply_values(self):
        """把当前配置应用到界面"""
        self.file_enable_check.setChecked(self._file_enabled)
        # 文件级别
        level = self._file_level if self._file_level in self.file_level_btns else 'INFO'
        self.file_level_btns[level].setChecked(True)
        # 面板级别
        p_level = self._panel_level if self._panel_level in self.panel_level_btns else 'INFO'
        self.panel_level_btns[p_level].setChecked(True)
        # 保留个数
        self.backup_spin.setValue(int(self._backup_count))
        # 同步禁用状态
        self._on_file_enable_toggled(self._file_enabled)

    def _on_file_enable_toggled(self, checked):
        """文件日志开关变化时，级别和保留个数控件同步禁用状态"""
        for rb in self.file_level_btns.values():
            rb.setEnabled(checked)
        self.backup_spin.setEnabled(checked)

    def get_config(self):
        """获取用户选择的配置字典"""
        file_level = 'INFO'
        for level, rb in self.file_level_btns.items():
            if rb.isChecked():
                file_level = level
                break
        panel_level = 'INFO'
        for level, rb in self.panel_level_btns.items():
            if rb.isChecked():
                panel_level = level
                break
        return {
            '文件日志': self.file_enable_check.isChecked(),
            '文件日志级别': file_level,
            '面板日志级别': panel_level,
            '文件保留个数': self.backup_spin.value(),
        }
