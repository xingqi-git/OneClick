# 踩坑记录（错误现象 → 根因 → 修法）

## Python 闭包 UnboundLocalError（资源监控上传脚本失败）
- 现象：开始监控报 `local variable 'user_path' referenced before assignment`。
- 根因：嵌套闭包内**赋值**某变量会使其成为闭包局部变量，若闭包内先读后写即崩；外层函数的同名赋值帮不上忙（不同作用域）。
- 修法：`resolve_work_dir` 等收口赋值放在闭包开头或外层赋值源头，闭包内只读不写。排查工具：AST 扫描"函数内赋值过的名字在赋值前被读取"。

## pyqtSignal 参数个数不匹配 → 线程崩溃
- 现象：`OneClickWorker.log_signal[str, str] signal has 2 argument(s) but 1 provided`，状态轮询线程整个死掉。
- 根因：`log_signal = pyqtSignal(str, str)`（消息, 级别），emit 只传 1 个参数在 emit 处抛 TypeError，且发生在 except 块内穿透出去。
- 修法：emit 一律两个参数（resource_monitor_dialog、weak_net_dialog 已修）。全项目仅两处，已清零。

## Windows 路径拼进 Linux 命令 → 远端怪目录/怪文件
- 现象：服务器家目录出现 `C:\Users\xxx\Desktop\...` 命名的目录及 OneClick_temp* 残留。
- 根因：work_dir 未校验，Windows 路径不以 `/` 开头被 `mkdir -p` 当相对路径，在当前目录创建；`:` 和 `\` 在 Linux 是合法文件名字符。
- 修法：全链路 resolve_work_dir 收口（详见 decisions.md）。资源监控四条链路（启动/轮询/清除/下载）+ 弱网三条链路均已覆盖。

## 补默认值漏掉空字符串
- 现象：config.json 里 `"端口": ""` 没被自动补 22。
- 根因：只把 None 当缺失。
- 修法：config_schema 中 None、空串、纯空白一律视为缺失。

## 冒烟测试预期错误 ≠ 代码 bug
- 例：断言 `SSHTools().resolve_work_dir(r'C:\x') == '/home'` 失败——实际 `__init__` 默认 username='root'，回退 `/home/root` 才是设计行为。先读源码确认默认值再写预期。

## offscreen 平台几何失真
- QT_QPA_PLATFORM=offscreen 下 QTabBar 返回全零几何、findChildren 可能崩；涉及几何/渲染的验证必须真实 Windows 平台（`setAttribute(Qt.WA_DontShowOnScreen, True)` + widget.render(QPixmap) 截图）。

## 本地复现不了、测试机才出现的问题
- 例：分组标签栏箭头压标签（本地源码 OK）。疑因：测试机 DPI 缩放 + 分组栏独有的 setStyleSheet（QStyleSheetStyle 几何随主题变化）。教训：环境差异类 bug 先找"该组件独有因素"再改代码，拿不到截图不盲改。

## 环境备忘
- 打包：`pyinstaller OneClick.spec --clean`；venv 解释器 `d:/github/OneClick/.venv/Scripts/python.exe`；PowerShell 5 不支持 `&&`，用 `;` 或 `$LASTEXITCODE`。
- GUI 程序（PyQt）会占住终端：AI 只跑非阻塞检查（py_compile/冒烟/AST），界面验证由用户手动 `run.bat`。
