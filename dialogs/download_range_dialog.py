"""
下载数据时间范围选择对话框
"""

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QDialog, QMessageBox


class DownloadRangeDialog(QDialog):
    """下载数据时间范围选择对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载监控数据")
        self.setModal(True)
        self.resize(420, 280)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 下载方式
        mode_group = QtWidgets.QGroupBox("下载方式")
        mode_layout = QtWidgets.QVBoxLayout(mode_group)

        self.radio_all = QtWidgets.QRadioButton("全部下载（下载所有监控数据）")
        self.radio_all.setChecked(True)
        self.radio_range = QtWidgets.QRadioButton("按时间范围下载")

        mode_layout.addWidget(self.radio_all)
        mode_layout.addWidget(self.radio_range)

        # 时间范围
        time_group = QtWidgets.QGroupBox("时间范围")
        time_layout = QtWidgets.QGridLayout(time_group)

        self.start_label = QtWidgets.QLabel("开始时间：")
        self.start_edit = QtWidgets.QDateTimeEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        self.end_label = QtWidgets.QLabel("结束时间：")
        self.end_edit = QtWidgets.QDateTimeEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        # 默认时间：今天 00:00 到 当前时间
        now = QtCore.QDateTime.currentDateTime()
        today_start = QtCore.QDateTime(now.date(), QtCore.QTime(0, 0, 0))
        self.start_edit.setDateTime(today_start)
        self.end_edit.setDateTime(now)

        time_layout.addWidget(self.start_label, 0, 0)
        time_layout.addWidget(self.start_edit, 0, 1)
        time_layout.addWidget(self.end_label, 1, 0)
        time_layout.addWidget(self.end_edit, 1, 1)

        # 提示标签
        self.hint_label = QtWidgets.QLabel("提示：按时间范围下载时，将先下载完整数据，然后在本地裁剪到指定范围")
        self.hint_label.setStyleSheet("color: #999; font-size: 12px;")
        self.hint_label.setWordWrap(True)

        # 按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QtWidgets.QPushButton("确定")
        self.btn_cancel = QtWidgets.QPushButton("取消")
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)

        layout.addWidget(mode_group)
        layout.addWidget(time_group)
        layout.addWidget(self.hint_label)
        layout.addStretch()
        layout.addLayout(btn_layout)

        self._update_time_widgets_enabled()

    def _connect_signals(self):
        self.radio_all.toggled.connect(self._update_time_widgets_enabled)
        self.radio_range.toggled.connect(self._update_time_widgets_enabled)
        self.btn_ok.clicked.connect(self._on_ok_clicked)
        self.btn_cancel.clicked.connect(self.reject)

    def _update_time_widgets_enabled(self):
        enabled = self.radio_range.isChecked()
        self.start_edit.setEnabled(enabled)
        self.end_edit.setEnabled(enabled)
        self.start_label.setEnabled(enabled)
        self.end_label.setEnabled(enabled)

    def _on_ok_clicked(self):
        if self.radio_range.isChecked():
            start = self.start_edit.dateTime().toPyDateTime()
            end = self.end_edit.dateTime().toPyDateTime()
            if start > end:
                QMessageBox.warning(self, "提示", "开始时间不能晚于结束时间")
                return

        self.accept()

    def get_download_mode(self):
        """返回 'all' 或 'range'"""
        return 'all' if self.radio_all.isChecked() else 'range'

    def get_time_range(self):
        """返回 (start_datetime, end_datetime)，全部下载模式返回 (None, None)"""
        if self.radio_all.isChecked():
            return None, None
        start = self.start_edit.dateTime().toPyDateTime()
        end = self.end_edit.dateTime().toPyDateTime()
        return start, end
