
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.setWindowModality(QtCore.Qt.NonModal)
        Dialog.resize(1000, 600)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        
        # 配置区域标题
        self.label_config = QtWidgets.QLabel(Dialog)
        self.label_config.setObjectName("label_config")
        self.verticalLayout_2.addWidget(self.label_config)
        
        # 工具栏（添加列、添加行、删除行、删除列）
        self.horizontalLayout_toolbar = QtWidgets.QHBoxLayout()
        self.horizontalLayout_toolbar.setObjectName("horizontalLayout_toolbar")
        self.add_col_pushButton = QtWidgets.QPushButton(Dialog)
        self.add_col_pushButton.setObjectName("add_col_pushButton")
        self.horizontalLayout_toolbar.addWidget(self.add_col_pushButton)
        self.del_col_pushButton = QtWidgets.QPushButton(Dialog)
        self.del_col_pushButton.setObjectName("del_col_pushButton")
        self.horizontalLayout_toolbar.addWidget(self.del_col_pushButton)
        spacer1 = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_toolbar.addItem(spacer1)
        self.add_row_pushButton = QtWidgets.QPushButton(Dialog)
        self.add_row_pushButton.setObjectName("add_row_pushButton")
        self.horizontalLayout_toolbar.addWidget(self.add_row_pushButton)
        self.del_row_pushButton = QtWidgets.QPushButton(Dialog)
        self.del_row_pushButton.setObjectName("del_row_pushButton")
        self.horizontalLayout_toolbar.addWidget(self.del_row_pushButton)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_toolbar.addItem(spacerItem)
        self.verticalLayout_2.addLayout(self.horizontalLayout_toolbar)
        
        # 表格
        self.scrollArea = QtWidgets.QScrollArea(Dialog)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 980, 400))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.gridLayout_table = QtWidgets.QVBoxLayout(self.scrollAreaWidgetContents)
        self.gridLayout_table.setObjectName("gridLayout_table")
        self.tableWidget = QtWidgets.QTableWidget(self.scrollAreaWidgetContents)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.tableWidget.setAlternatingRowColors(False)
        self.gridLayout_table.addWidget(self.tableWidget)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout_2.addWidget(self.scrollArea)
        
        # 快捷按钮名称（放到保存和重置上面）
        self.horizontalLayout_name = QtWidgets.QHBoxLayout()
        self.horizontalLayout_name.setObjectName("horizontalLayout_name")
        self.label_8 = QtWidgets.QLabel(Dialog)
        self.label_8.setObjectName("label_8")
        self.horizontalLayout_name.addWidget(self.label_8)
        self.sc_name_lineEdit = QtWidgets.QLineEdit(Dialog)
        self.sc_name_lineEdit.setText("")
        self.sc_name_lineEdit.setObjectName("sc_name_lineEdit")
        self.horizontalLayout_name.addWidget(self.sc_name_lineEdit)
        self.horizontalLayout_name.setStretch(0, 1)
        self.horizontalLayout_name.setStretch(1, 4)
        self.verticalLayout_2.addLayout(self.horizontalLayout_name)
        
        # 底部按钮
        self.horizontalLayout_bottom = QtWidgets.QHBoxLayout()
        self.horizontalLayout_bottom.setObjectName("horizontalLayout_bottom")
        self.save_pushButton = QtWidgets.QPushButton(Dialog)
        self.save_pushButton.setObjectName("save_pushButton")
        self.horizontalLayout_bottom.addWidget(self.save_pushButton)
        self.reset_pushButton = QtWidgets.QPushButton(Dialog)
        self.reset_pushButton.setObjectName("reset_pushButton")
        self.horizontalLayout_bottom.addWidget(self.reset_pushButton)
        self.close_pushButton = QtWidgets.QPushButton(Dialog)
        self.close_pushButton.setObjectName("close_pushButton")
        self.horizontalLayout_bottom.addWidget(self.close_pushButton)
        self.verticalLayout_2.addLayout(self.horizontalLayout_bottom)

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "添加<服务器检查>配置"))
        self.label_config.setText(_translate("Dialog", "服务器检查配置"))
        self.add_col_pushButton.setText(_translate("Dialog", "添加服务器列"))
        self.del_col_pushButton.setText(_translate("Dialog", "删除选中列"))
        self.add_row_pushButton.setText(_translate("Dialog", "添加命令回显行"))
        self.del_row_pushButton.setText(_translate("Dialog", "删除命令回显行"))
        self.label_8.setText(_translate("Dialog", "快捷按钮名称"))
        self.save_pushButton.setText(_translate("Dialog", "生成快捷按钮"))
        self.reset_pushButton.setText(_translate("Dialog", "重置"))
        self.close_pushButton.setText(_translate("Dialog", "关闭"))

