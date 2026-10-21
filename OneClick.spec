# -*- mode: python ; coding: utf-8 -*-
"""
OneClick PyInstaller 打包配置（PyInstaller 6.x，体积深度优化版）
同时生成单文件版和文件夹版，想用哪个发哪个。

使用方法：
    .venv\Scripts\pyinstaller.exe OneClick.spec --clean

产物：
    dist/OneClick.exe          单文件版
    dist/OneClick/             文件夹版（顶层只有 OneClick.exe，依赖都在 _internal/）

体积优化（按收益排序）：
1. 排除 OpenGL 软件渲染 fallback（opengl32sw.dll ~15MB）
2. 排除 QtQml/QtQuick/QtNetwork/QtDBus/QtSvg 等冗余 Qt 模块（matplotlib hook 带进来的）
3. 清理 matplotlib 示例数据、多余字体、多余样式表
4. 清理 Qt 翻译文件（只留中文）
5. 排除 tkinter、IPython、pytest 等无关模块
6. UPX 压缩
"""

import os

block_cipher = None

# ── 排除确定不用的 Python 模块 ──────────────────────
excludes = [
    # Qt QML / Quick 系列（项目纯 QtWidgets，不用 QML）
    'PyQt5.QtQml',
    'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets',
    'PyQt5.QtQuick3D',
    'PyQt5.QtQuickControls2',
    'PyQt5.QtQuickTemplates2',
    'PyQt5.QtQuickShapes',
    'PyQt5.QtQuickParticles',
    'PyQt5.QtQuickLocalStorage',
    'PyQt5.QtQuickWindow',
    'PyQt5.QtQml.Models',
    'PyQt5.QtQml.WorkerScript',

    # Qt Location / Positioning（地图定位，不用）
    'PyQt5.QtLocation',
    'PyQt5.QtPositioning',

    # Qt Multimedia（多媒体，不用）
    'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets',

    # Qt WebEngine（浏览器引擎，不用，大块头）
    'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebChannel',
    'PyQt5.QtWebSockets',

    # Qt 其他未用模块
    'PyQt5.QtSql',
    'PyQt5.QtXml',
    'PyQt5.QtXmlPatterns',
    'PyQt5.QtSensors',
    'PyQt5.QtSerialPort',
    'PyQt5.QtBluetooth',
    'PyQt5.QtNfc',
    'PyQt5.QtTextToSpeech',
    'PyQt5.QtRemoteObjects',
    'PyQt5.QtHelp',
    'PyQt5.QtDesigner',
    'PyQt5.QtTest',
    'PyQt5.QtWinExtras',

    # tkinter（完全不用）
    'tkinter',
    'Tkinter',
    '_tkinter',

    # 开发工具（运行时不需要）
    'IPython',
    'pytest',
    'nose',
    'unittest',
    'doctest',

    # pywin32 系列（项目不用，hook 误带）
    'win32com',
    'pythoncom',
    'pywintypes',
    'win32api',
    'win32con',
    'win32gui',
]

a = Analysis(
    ['OneClick.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app.ico', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ══════════════════════════════════════════════════════
# 体积优化：手动过滤冗余二进制和数据文件
# ══════════════════════════════════════════════════════

# ── 过滤冗余 DLL（matplotlib hook 或 PyQt5 hook 带进来的） ──
_DLL_BLACKLIST = {
    # OpenGL / D3D 相关（纯 QtWidgets + Agg 后端不需要）
    'opengl32sw.dll',
    'libGLESv2.dll',
    'libEGL.dll',
    'd3dcompiler_47.dll',
    'Qt5OpenGL.dll',

    # Qml / Quick（excludes 已经排除 Python 模块，但 DLL 可能被依赖带进来）
    'Qt5Qml.dll',
    'Qt5QmlModels.dll',
    'Qt5Quick.dll',
    'Qt5QuickWidgets.dll',
    'Qt5QuickControls2.dll',
    'Qt5QuickTemplates2.dll',
    'Qt5QuickShapes.dll',
    'Qt5QuickParticles.dll',
    'Qt5Quick3D.dll',
    'Qt5QmlWorkerScript.dll',
    'Qt5QmlLocalStorage.dll',

    # Network / DBus / Svg（项目纯本地 + QtWidgets，不需要）
    'Qt5Network.dll',
    'Qt5DBus.dll',
    'Qt5Svg.dll',

    # WebEngine / WebChannel（大块头）
    'Qt5WebEngineCore.dll',
    'Qt5WebEngineWidgets.dll',
    'Qt5WebChannel.dll',
    'Qt5WebSockets.dll',

    # Location / Positioning
    'Qt5Location.dll',
    'Qt5Positioning.dll',

    # Multimedia
    'Qt5Multimedia.dll',
    'Qt5MultimediaWidgets.dll',

    # Sql / Xml / Sensors / SerialPort / Bluetooth / Nfc 等
    'Qt5Sql.dll',
    'Qt5Xml.dll',
    'Qt5XmlPatterns.dll',
    'Qt5Sensors.dll',
    'Qt5SerialPort.dll',
    'Qt5Bluetooth.dll',
    'Qt5Nfc.dll',
    'Qt5TextToSpeech.dll',
    'Qt5RemoteObjects.dll',
    'Qt5Help.dll',
    'Qt5Designer.dll',
    'Qt5Test.dll',
    'Qt5WinExtras.dll',

    # QtCharts / QtDataVisualization（图表类，matplotlib 够用了）
    'Qt5Charts.dll',
    'Qt5DataVisualization.dll',

    # Qt3D 系列
    'Qt53DCore.dll',
    'Qt53DRender.dll',
    'Qt53DInput.dll',
    'Qt5DLogic.dll',
    'Qt53DAnimation.dll',
    'Qt53DExtras.dll',
}


def _is_dll_blacklisted(dest_path):
    """判断 DLL 是否在黑名单中（只比较文件名，不区分大小写）"""
    name = os.path.basename(dest_path).lower()
    return name in {n.lower() for n in _DLL_BLACKLIST}


a.binaries = [b for b in a.binaries if not _is_dll_blacklisted(b[0])]

# ── 过滤 Qt 翻译文件（只留中文） ──
# 翻译文件路径类似 PyQt5/Qt/translations/qt_xx.qm
_KEEP_QM_PREFIXES = ('qt_zh', 'qtbase_zh', 'qtmultimedia_zh')


def _is_keep_qm(dest_path):
    """判断 .qm 翻译文件是否保留（只留中文相关）"""
    if not dest_path.endswith('.qm'):
        return True  # 不是翻译文件，不拦
    if 'translations' not in dest_path.replace('\\', '/'):
        return True
    fname = os.path.basename(dest_path)
    return any(fname.startswith(p) for p in _KEEP_QM_PREFIXES)


a.datas = [d for d in a.datas if _is_keep_qm(d[0])]

# ── 过滤 matplotlib 冗余数据 ──
# 示例数据、多余字体、多余样式表
_SKIP_MPL_PATHS = (
    'mpl-data/sample_data/',
    'mpl-data/images/filesave.pdf',
    'mpl-data/images/filesave.xpm',
    'mpl-data/stylelib/dark_background.mplstyle',      # 保留默认就够
    'mpl-data/stylelib/fivethirtyeight.mplstyle',
    'mpl-data/stylelib/ggplot.mplstyle',
    'mpl-data/stylelib/grayscale.mplstyle',
    'mpl-data/stylelib/seaborn-v0_8',
    'mpl-data/stylelib/Solarize_Light2.mplstyle',
    'mpl-data/stylelib/bmh.mplstyle',
    'mpl-data/stylelib/classic.mplstyle',
    'mpl-data/stylelib/fast.mplstyle',
    'mpl-data/stylelib/Pastel1.mplstyle',
    'mpl-data/stylelib/Pastel2.mplstyle',
    'mpl-data/stylelib/Paired.mplstyle',
    'mpl-data/stylelib/Accent.mplstyle',
    'mpl-data/stylelib/Dark2.mplstyle',
    'mpl-data/stylelib/Set1.mplstyle',
    'mpl-data/stylelib/Set2.mplstyle',
    'mpl-data/stylelib/Set3.mplstyle',
    'mpl-data/stylelib/tab10.mplstyle',
    'mpl-data/stylelib/tab20.mplstyle',
    'mpl-data/stylelib/tab20b.mplstyle',
    'mpl-data/stylelib/tab20c.mplstyle',
)


def _is_keep_mpl_data(dest_path):
    """判断 matplotlib 数据文件是否保留"""
    p = dest_path.replace('\\', '/')
    if 'mpl-data/' not in p:
        return True  # 不是 mpl 数据，不拦
    return not any(skip in p for skip in _SKIP_MPL_PATHS)


a.datas = [d for d in a.datas if _is_keep_mpl_data(d[0])]

# ── 过滤 Qt 插件中冗余的图片格式、平台插件 ──
_KEEP_IMAGE_FORMATS = ('qico', 'qjpeg', 'qgif', 'qpng')
_KEEP_PLATFORMS = ('qwindows',)
_KEEP_STYLES = ('qwindowsvistastyle',)  # 留着 Vista 风格也无妨，不大


def _is_keep_plugin(dest_path):
    """判断 Qt 插件是否保留"""
    p = dest_path.replace('\\', '/')
    if 'plugins/imageformats/' in p:
        fname = os.path.basename(p).lower()
        return any(fname.startswith(k) for k in _KEEP_IMAGE_FORMATS)
    if 'plugins/platforms/' in p:
        fname = os.path.basename(p).lower()
        return any(fname.startswith(k) for k in _KEEP_PLATFORMS)
    if 'plugins/generic/' in p:
        # 触摸等通用插件，Windows 桌面不用
        return False
    if 'plugins/platformthemes/' in p:
        # Linux 的桌面主题插件，Windows 不用
        return False
    return True


a.datas = [d for d in a.datas if _is_keep_plugin(d[0])]

# binaries 里的插件 DLL 也要过滤（有些 plugin 会进 binaries）
a.binaries = [b for b in a.binaries if _is_keep_plugin(b[0])]


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── 单文件版 ──────────────────────────────────────────
exe_single = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OneClick',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)

# ── 文件夹版 ──────────────────────────────────────────
exe_dir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OneClick',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
    contents_directory='_internal',
)

collect = COLLECT(
    exe_dir,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OneClick',
)
