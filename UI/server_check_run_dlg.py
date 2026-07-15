
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.setWindowModality(QtCore.Qt.NonModal)
        Dialog.resize(1000, 600)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        
        # 标题
        self.label_title = QtWidgets.QLabel(Dialog)
        self.label_title.setObjectName("label_title")
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.label_title.setFont(font)
        self.verticalLayout_2.addWidget(self.label_title)
        
        # 表格
        self.scrollArea = QtWidgets.QScrollArea(Dialog)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 980, 450))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.gridLayout_table = QtWidgets.QVBoxLayout(self.scrollAreaWidgetContents)
        self.gridLayout_table.setObjectName("gridLayout_table")
        self.tableWidget = QtWidgets.QTableWidget(self.scrollAreaWidgetContents)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.tableWidget.setAlternatingRowColors(True)
        self.gridLayout_table.addWidget(self.tableWidget)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout_2.addWidget(self.scrollArea)
        
        # 底部按钮
        self.horizontalLayout_bottom = QtWidgets.QHBoxLayout()
        self.horizontalLayout_bottom.setObjectName("horizontalLayout_bottom")
        self.start_pushButton = QtWidgets.QPushButton(Dialog)
        self.start_pushButton.setObjectName("start_pushButton")
        self.horizontalLayout_bottom.addWidget(self.start_pushButton)
        self.stop_pushButton = QtWidgets.QPushButton(Dialog)
        self.stop_pushButton.setObjectName("stop_pushButton")
        self.horizontalLayout_bottom.addWidget(self.stop_pushButton)
        self.close_pushButton = QtWidgets.QPushButton(Dialog)
        self.close_pushButton.setObjectName("close_pushButton")
        self.horizontalLayout_bottom.addWidget(self.close_pushButton)
        self.verticalLayout_2.addLayout(self.horizontalLayout_bottom)

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "服务器检查面板"))
        self.label_title.setText(_translate("Dialog", "服务器检查"))
        self.start_pushButton.setText(_translate("Dialog", "开始检查"))
        self.stop_pushButton.setText(_translate("Dialog", "停止检查"))
        self.close_pushButton.setText(_translate("Dialog", "关闭"))
