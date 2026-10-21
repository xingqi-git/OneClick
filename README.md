# OneClick - 一键式远程终端工具

一个基于 PyQt5 的远程服务器运维工具，集成 SSH 终端、文件传输、资源监控、弱网模拟、服务器检查等功能。

## 功能介绍

- **SSH 终端**：多标签终端，支持自定义快捷按钮、指令管理、中文显示
- **文件传输**：批量上传/下载文件，支持 SCP
- **资源监控**：远程 Linux / Windows 服务器 CPU、内存、磁盘、网络、进程监控，图形化展示（matplotlib）
- **弱网模拟**：基于 Linux tc 的网络模拟，支持延迟、丢包、带宽限制等，可多规则循环
- **服务器检查**：批量检查服务器健康状态（连通性、系统时间、防火墙等）
- **快捷命令**：自定义快捷按钮，一键发送常用命令

## 快速使用

### 运行

直接双击 `OneClick.exe` 启动。

### 数据目录说明

所有运行时产生的数据都在 **exe 同目录**下：

```
OneClick/
├── OneClick.exe        # 主程序
├── config/             # 配置文件（服务器列表、快捷按钮、软件设置等）
├── logs/               # 运行日志
├── <服务器IP>/         # 各服务器的资源监控数据（按IP分目录）
└── ...
```

- **配置文件**：`config/` 目录下，修改配置后重启生效
- **日志文件**：`logs/` 目录下，出问题时可以查看
- **监控数据**：以服务器 IP 命名的目录下，`Monitor/` 子目录存放各进程的 `.log` 数据文件

### 源码运行

```bash
pip install -r requirements.txt
python OneClick.py
```

## 项目结构

```
OneClick/
├── OneClick.py              # 程序入口
├── MainWindowLogic.py       # 主窗口逻辑
├── GraphWindowLogic.py      # 资源监控图表窗口逻辑
├── monitor_scripts.py       # 监控脚本（Linux Bash / Windows PS / ash）
├── help_content.py          # 帮助文档内容
├── OneClick.spec            # PyInstaller 打包配置
├── requirements.txt         # Python 依赖
├── app.ico                  # 程序图标
│
├── UI/                      # UI 定义文件
│   ├── MainWindow.py
│   ├── GraphMainWindow.py
│   └── ...
│
├── dialogs/                 # 对话框
│   ├── cmd_manage_dialog.py    # 指令管理
│   ├── send_cmd2_dialog.py     # 发送命令
│   ├── send_files_dialog.py    # 发送文件
│   ├── get_files_dialog.py     # 获取文件
│   ├── resource_monitor_dialog.py  # 资源监控
│   ├── weak_net_dialog.py      # 弱网控制
│   ├── server_check_dialog.py  # 服务器检查
│   └── ...
│
├── widgets/                 # 自定义控件
│   ├── terminal_widget.py      # 终端控件（pyte + QPainter 自绘）
│   └── file_browser_widget.py  # 文件浏览控件
│
└── utils/                   # 工具模块
    ├── ssh_tools.py            # SSH/SCP 封装
    ├── graph_data_tools.py     # 图表数据处理
    ├── qthread_worker.py       # 多线程工作类
    ├── logger.py               # 日志
    ├── module_loader.py        # 模块预加载
    ├── log_cleaner.py          # 日志清理
    └── ...
```
