r"""
    启动qtdesigner
    .\.venv\Lib\site-packages\qt5_applications\Qt\bin\designer.exe
    更新UI命令
    python -m PyQt5.uic.pyuic ./UI/MainWindow.ui -o ./UI/MainWindow.py
    python -m PyQt5.uic.pyuic ./UI/send_cmd_dlg.ui -o ./UI/send_cmd_dlg.py
    python -m PyQt5.uic.pyuic ./UI/send_files_dlg.ui -o ./UI/send_files_dlg.py
    python -m PyQt5.uic.pyuic ./UI/get_files_dlg.ui -o ./UI/get_files_dlg.py
    python -m PyQt5.uic.pyuic ./UI/copy_local_files_dlg.ui -o ./UI/copy_local_files_dlg.py
    python -m PyQt5.uic.pyuic ./UI/edit_servers_dlg.ui -o ./UI/edit_servers_dlg.py
    python -m PyQt5.uic.pyuic ./UI/resource_monitor_dlg.ui -o ./UI/resource_monitor_dlg.py
    python -m PyQt5.uic.pyuic ./UI/GraphMainWindow.ui -o ./UI/GraphMainWindow.py

    打包命令：pyinstaller -F -w OneClick.py -i app.ico --add-data "app.ico"
    参数说明：
    -F 或 --onefile：将所有文件打包成一个单独的可执行文件
    -w 或 --windowed、--noconsole：打包成不带控制台窗口的程序
    -i 或 --icon：指定程序的图标.ico
    --upx-dir 打包压缩，参数指定 UPX 所在目录--upx-dir "path/to/upx" my_script.py
    --noupx 不适用upx
"""



from MainWindowLogic import MainWindowLogic
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
import sys
import os


def resource_path(relative_path):
    """获取资源文件路径，兼容源码运行和 PyInstaller 打包（-F 单文件模式）"""
    if getattr(sys, 'frozen', False):
        # 打包后：优先找 exe 同目录的文件（方便用户手动替换），其次找打包进 exe 的资源
        p = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(p):
            return p
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


if __name__ == '__main__':
    def run():
        # Windows 任务栏需要设置 AppUserModelID，否则可能显示默认图标且不与窗口图标关联
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('OneClick.V2.0')
        except Exception:
            pass

        app = QApplication(sys.argv)
        app.setApplicationName("OneClick")
        app.setApplicationVersion("V2.0")

        # 设置应用程序图标（任务栏显示）
        icon_path = resource_path("app.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        # global_font = QFont()  # 获取系统默认字体的配置
        # global_font.setKerning(False)  # 关Kerning，解决roo等o中间有空格的显示问题
        # app.setFont(global_font)  # 应用到所有控件

        window = MainWindowLogic()
        window.show()
        sys.exit(app.exec_())

    run()
