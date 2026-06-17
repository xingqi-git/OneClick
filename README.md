# OneClick - 一键式服务器运维管理工具

一个基于 PyQt5 开发的图形化 SSH 服务器运维管理工具，支持多服务器管理、命令批量执行、文件传输、资源监控等功能。

## 项目简介

OneClick 是一款专为 Windows 平台设计的服务器运维管理工具，旨在简化日常服务器运维操作。通过图形化界面，用户可以方便地管理多台 Linux 服务器，执行命令、传输文件、监控资源使用情况等。

## 主要功能

### 1. 服务器管理
- 多服务器配置管理（IP、端口、用户名、密码）
- SSH 连接与断开
- 自动获取 root 权限（支持 sudo 切换）

### 2. 命令执行
- 发送命令到远程服务器
- 实时接收命令执行回显
- 命令历史记录与快速选择
- 快捷按钮配置（一键执行常用命令）

### 3. 文件传输
- 发送本地文件到远程服务器
- 从远程服务器获取文件到本地
- 本地文件批量复制

### 4. 资源监控
- 远程服务器资源监控（CPU、内存、磁盘等）
- 本地进程资源监控
- 实时数据采集与日志记录
- 图形化数据展示（matplotlib 图表）

### 5. 弱网模拟
- 基于 Linux tc（Traffic Control）的网络模拟
- 支持延迟、丢包、带宽限制、损坏、重复、重排等规则
- 多规则队列循环执行，支持持续时长与间隔时长
- 运行日志自动记录，可随时查看历史运行记录
- 脚本后台执行，不影响其他操作

### 6. 配置管理
- 服务器配置导入/导出
- 快捷按钮配置保存
- 支持多配置文件（JSON格式）

## 技术栈

- **GUI 框架**: PyQt5 5.15.2
- **SSH 协议**: paramiko 2.10.4
- **文件传输**: scp 0.14.4
- **数据可视化**: matplotlib 3.4.3
- **系统监控**: psutil 5.9.0
- **打包工具**: pyinstaller 4.10
- **加密**: cryptography 3.4.8, bcrypt 3.2.2
- **Windows API**: pywin32 306

## 环境要求

- Python 3.8+
- Windows 7 / Windows 10 / Windows Server
- 支持 pyinstaller 4.10（打包验证通过

## 安装与运行

### 方式一：直接运行 Python 脚本

```bash
# 安装依赖
pip install -r requirements.txt

# 运行程序
python OneClick.py
```

### 方式二：打包为 EXE 可执行文件

```bash
# 打包命令（使用 UPX 压缩）
pyinstaller -F -w OneClick.py --upx-dir "path/to/upx"

# 或不使用 UPX 压缩
pyinstaller -F -w OneClick.py
```

打包参数说明：
- `-F` / `--onefile`: 将所有文件打包成一个单独的可执行文件
- `-w` / `--windowed`: 打包成不带控制台窗口的程序
- `--upx-dir`: 指定 UPX 压缩工具所在目录

## 项目结构

```
OneClick/
├── OneClick.py              # 程序入口
├── MainWindowLogic.py       # 主窗口逻辑
├── GraphWindowLogic.py      # 图表窗口逻辑
├── OneClick.spec            # PyInstaller 配置文件
├── config.json            # 默认配置文件
├── requirements.txt       # Python 依赖
├── UI/                    # UI 文件目录
│   ├── MainWindow.py      # 主窗口 UI
│   ├── GraphMainWindow.py # 图表窗口 UI
│   ├── send_cmd_dlg.py     # 发送命令对话框
│   ├── send_files_dlg.py   # 发送文件对话框
│   ├── get_files_dlg.py    # 获取文件对话框
│   ├── copy_local_files_dlg.py  # 复制本地文件对话框
│   ├── edit_servers_dlg.py      # 编辑服务器对话框
│   ├── resource_monitor_dlg.py    # 资源监控对话框
│   └── weak_net_control_dlg.py    # 弱网控制对话框
├── utils/                 # 工具模块
│   ├── ssh_tools.py       # SSH 工具类
│   ├── windows_tools.py    # Windows 工具类
│   ├── qthread_worker.py    # QThread 工作线程
│   └── graph_data_tools.py  # 图表数据处理
└── local/OneClick/         # 本地数据目录
    ├── OneClickMonitor.ps1  # PowerShell 监控脚本
    └── *.log                  # 日志文件
```

## 使用说明

### 1. 添加服务器

点击菜单 `服务器管理` -> `编辑服务器列表`，添加服务器配置信息。

### 2. 连接服务器

在主界面选择服务器，点击 `连接` 按钮建立 SSH 连接。

### 3. 创建快捷按钮

通过菜单创建各种类型的快捷按钮，实现一键操作。

### 4. 资源监控

选择 `快捷按钮类型选择 `资源监控`，配置需要监控的进程和采样频率。

### 5. 弱网模拟

选择 `快捷按钮类型选择 `弱网`，配置服务器信息后生成快捷按钮。点击按钮进入弱网控制面板：

1. 选择目标网卡（自动获取服务器网卡列表）
2. 编辑规则：设置延迟、丢包率、带宽限制等参数，以及持续时长和间隔时长
3. 将规则添加到队列，可调整顺序或删除
4. 设置循环次数（0 表示无限循环）
5. 点击 `开始弱网` 执行，脚本将在服务器后台运行
6. 点击 `查看运行日志` 可查看实时进度和历史记录
7. 点击 `停止弱网` 终止脚本并清除 tc 规则

**注意**：弱网设置可能导致 SSH 连接中断，请确保已配置好停止条件或保留其他可用连接通道。

### 6. 查看监控图表

监控数据会自动保存到 local/OneClick/ 目录下的 .log 文件中，可通过图表功能查看历史数据。

## UI 文件更新

如需修改 UI 界面，使用 Qt Designer 编辑 .ui 文件后执行以下命令更新：

```bash
# 更新主窗口
python -m PyQt5.uic.pyuic ./UI/MainWindow.ui -o ./UI/MainWindow.py

# 更新其他对话框
python -m PyQt5.uic.pyuic ./UI/send_cmd_dlg.ui -o ./UI/send_cmd_dlg.py
python -m PyQt5.uic.pyuic ./UI/send_files_dlg.ui -o ./UI/send_files_dlg.py
python -m PyQt5.uic.pyuic ./UI/get_files_dlg.ui -o ./UI/get_files_dlg.py
python -m PyQt5.uic.pyuic ./UI/copy_local_files_dlg.ui -o ./UI/copy_local_files_dlg.py
python -m PyQt5.uic.pyuic ./UI/edit_servers_dlg.ui -o ./UI/edit_servers_dlg.py
python -m PyQt5.uic.pyuic ./UI/resource_monitor_dlg.ui -o ./UI/resource_monitor_dlg.py
python -m PyQt5.uic.pyuic ./UI/weak_net_control_dlg.ui -o ./UI/weak_net_control_dlg.py
python -m PyQt5.uic.pyuic ./UI/GraphMainWindow.ui -o ./UI/GraphMainWindow.py
```

## 开发说明

- 项目使用面向对象设计，各对话框类继承自对应的 UI 类
- 所有耗时操作均在独立线程中执行，避免界面卡顿
- SSH 连接使用 keepalive 保持连接活跃
- 支持非 root 用户可自动尝试 sudo 切换到 root 权限

## 许可证

本项目仅供内部使用。

## 注意事项

1. 请妥善保管服务器密码，配置文件包含敏感信息
2. 建议使用非 root 用户进行日常操作
3. 监控数据日志文件会随时间增长，请注意定期清理
4. 弱网功能仅在 Linux 服务器上有效，需要 root 权限或 sudo 权限
5. 使用弱网功能前请确保了解当前网络环境，避免误操作导致连接中断
