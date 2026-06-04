r"""
    启动qtdesigner
    C:\Users\huang\Documents\PycharmData\venvs\.oneclick\Lib\site-packages\qt6_applications\Qt\bin\designer.exe
    D:\Users\xingq.FHC-DOMAIN\Documents\MyProjects\venvs\.oneclick\Lib\site-packages\qt6_applications\Qt\bin\designer.exe
    更新UI命令
    pyuic6 ./UI/MainWindow.ui -o ./UI/MainWindow.py
    pyuic6 ./UI/send_cmd_dlg.ui -o ./UI/send_cmd_dlg.py
    pyuic6 ./UI/send_files_dlg.ui -o ./UI/send_files_dlg.py
    pyuic6 ./UI/get_files_dlg.ui -o ./UI/get_files_dlg.py
    pyuic6 ./UI/copy_local_files_dlg.ui -o ./UI/copy_local_files_dlg.py
    pyuic6 ./UI/edit_servers_dlg.ui -o ./UI/edit_servers_dlg.py
    pyuic6 ./UI/resource_monitor_dlg.ui -o ./UI/resource_monitor_dlg.py
    pyuic6 ./UI/GraphMainWindow.ui -o ./UI/GraphMainWindow.py

    打包命令：pyinstaller -F -w OneClick.py --upx-dir "../upx"
    pyinstaller -F -w OneClick.py --upx-dir "D:\WPS云盘\Projects\upx"
    参数说明：
    -F 或 --onefile：将所有文件打包成一个单独的可执行文件
    -w 或 --windowed、--noconsole：打包成不带控制台窗口的程序
    -i 或 --icon：指定程序的图标.ico
    --upx-dir 打包压缩，参数指定 UPX 所在目录--upx-dir "path/to/upx" my_script.py
    --noupx 不适用upx
"""



from MainWindowLogic import MainWindowLogic
from PyQt5.QtWidgets import QApplication
# from PyQt5.QtGui import QFont
import sys

if __name__ == '__main__':
    def run():
        app = QApplication(sys.argv)

        # global_font = QFont()  # 获取系统默认字体的配置
        # global_font.setKerning(False)  # 关Kerning，解决roo等o中间有空格的显示问题
        # app.setFont(global_font)  # 应用到所有控件

        window = MainWindowLogic()
        window.show()
        sys.exit(app.exec_())

    run()
