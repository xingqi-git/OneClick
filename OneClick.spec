# -*- mode: python ; coding: utf-8 -*-
"""
OneClick PyInstaller 打包配置（体积优化版）
效果与原始命令等价，在此基础上排除未用模块减小体积。

使用方法：
    .venv\Scripts\pyinstaller.exe OneClick.spec --clean

原始命令参考：
    pyinstaller -F -w OneClick.py -i app.ico --add-data "app.ico;."

优化项：
1. 排除 QtQml/QtQuick/QtLocation 等未用 Qt 模块（节省几 MB）
2. 排除 tkinter（项目完全不用）
3. 排除 IPython/pytest 等开发工具
4. UPX 压缩（环境已自动启用）
"""

import os

block_cipher = None

# 排除确定不用的模块
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
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
