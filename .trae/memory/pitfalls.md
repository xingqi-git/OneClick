# 踩坑记录（错误现象 → 根因 → 修法）

## 筛选下载全量打包：源目录壳条目进了 tar -T 列表（2026-11-26 真机）
- 现象：源路径 /var/log + 名称包含 dnf，实际整个 /var/log 全下载。
- 根因：_filter_remote_source 无条件把源目录本身放进 dir_list（历史行为，旧 cp 流程里壳只提供目录结构、不参与复制，从不暴露）；新 tar -T 打包把壳条目一并塞进列表，tar 对目录条目会**递归归档整个目录**，覆盖了文件条目筛选 → 全量打包。
- 修法：组装打包列表时跳过"dir_path == 源根"的壳条目；壳层由文件/子目录条目的相对路径自动带出，落盘结构不变。筛选命中的**子目录**仍整目录进包（与旧 cp -a 行为一致）。
- 教训：tar -T 列表里任何目录条目都会递归打包，"结构壳"类占位条目绝不能进列表；mock fake 的 exec_command 三元组数据必须放第二位（stdout 位），放第一位（stdin 位）会让精筛静默拿到空数据、测试假阴性。
- 真机佐证：修复前解压时"包内有重名文件"告警，正是壳条目递归归档+文件条目重复归档（同一文件在包内多份）的副产品；修复后条目唯一告警消失，确认修复覆盖全部症状。

## 改"条件匹配+赋值"成对逻辑时漏改赋值行（2026-11-26 真机）
- 现象：默认包名改为 .tar 后，真机产物仍是 .tar.gz。
- 根因：click_get_files 里只把匹配条件扩成新旧两串元组，`archive_name = f"...tar.gz"` 赋值行没同步改——条件与赋值是一对，改条件必须同步检查赋值体。
- 教训：修改 if/else 分支时，分支体内引用旧常量的行必须逐行过一遍；冒烟断言要覆盖**渲染产物本身**而非只覆盖配置读取。

## 下载到 100% 必报 info() missing msg（2026-11-26 真机）
- 现象：资源监控下载数据，SFTP 下载失败报 `info() missing 1 required positional argument: 'msg'` → 误降级 SCP → SCP 到 100% 同样报错 → 下载失败。
- 根因：`_print_progress` 里旧控制台进度条的"完成时换行"残留 `logger.info()`（零参数调用），进度到 100% 档位必抛 TypeError；SFTP 分支把它当通道故障误触发降级。
- 修法：删除换行调用。教训：控制台交互式输出残留迁到日志面板时必须清理；TypeError 无 errno 会被传输层误判为通道级失败，写回调链代码时注意异常类型的影响面。

## tar -T 收到 "['Monitor']" 字符串 → 服务器端打包全量失败（2026-11-26 真机）
- 现象：资源监控/快捷按钮下载数据，服务器端打包报 `tar: [Monitor]：无法 stat: 没有那个文件或目录`，所有用户必现（与权限无关），root 一样挂。
- 根因：打包循环 `for g, (src_parent, remote_list) in grouped_entries.items()`——items() 的 value 是 **rels 列表**不是列表文件路径，`-T` 参数变成 Python list 的 repr 字符串 `['Monitor']`。列表文件路径在平行列表 `remote_list_paths[g]` 里。
- 修法：解包变量改名 rels，循环内 `remote_list = remote_list_paths[g]`；诊断循环同步修。
- **教训：mock 冒烟必须校验命令语义**（如 -T 参数须在已上传文件集合里），只断言退出码会放过参数错位；"list 的 repr 当路径"这类 bug 编译期零告警。

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

## 终端颜色渲染失效（只有粗细深浅，无彩色）
- 现象：终端里 `ls --color=always` 目录/文件只有亮暗差别，没有红蓝绿彩色。
- 根因：本项目 pyte 版本的 `Char.fg/bg` 只存三种**字符串**——`"default"`、基础 8 色色名（`"red"`/`"brown"` 及 `"bright*"` 变体）、256 色与真彩色统一存为不带 `#` 的 `"rrggbb"` 六位十六进制串；而 `_resolve_fg/_resolve_bg` 只处理了 `default`/int/tuple 三种形态（int/tuple 在该版本是死分支），色名和 rrggbb 串全部掉进兜底灰色，只剩粗体生效。
- 修法：`_resolve_color` 统一解析：色名查标准 16 色表（粗体+基础色提升为亮色变体，对齐主流终端），6 位十六进制串加 `#` 前缀，其余兜底。教训：接入第三方库前先查该版本字段的**实际取值形态**，不要按想象中的 API 写分支。

## 现场网络策略阻断 SFTP 子系统（Channel closed）
- 现象：某现场电脑 2026-11-23 09:05 起，绘图窗口「更新数据」100% 失败 `Channel closed`，且跨 3 台服务器（243/246/250）同时出现；失败文件名各不相同=各自列表字母序第一个（下载循环失败即中止）。
- 根因：网络新上的安全设备只放行 exec 和 scp、掐掉 sftp 子系统通道；同连接上 exec_command 正常、SCP（下载数据/get_files）正常、open_sftp 秒挂。诊断方法：按服务器 IP 关联日志找"分水岭时刻"、对比同一时段 sftp 与 scp 两条路径表现。
- 修法：更新数据改走 SCP 单文件下载。教训：项目传输约定是 SCP（send_files/get_files 一律 SCP），散装小操作不要随手用 open_sftp，先对齐约定。
- 通用排查思路：`Channel closed` 类错误先分清是服务器问题还是客户端网络问题——多台服务器同时刻开始失败 = 客户端网络侧变化。

## Windows 非法文件名（冒号）写本地失败
- 服务器端合法文件名含 `:`（如 `u40:3-flush-252:0_2450854.log`）下载到 NTFS 报 `[Errno 22] Invalid argument`。Linux 合法、Windows 非法的字符冲突，未修（罕见场景）。

## 环境备忘
- 打包：`pyinstaller OneClick.spec --clean`；venv 解释器 `d:/github/OneClick/.venv/Scripts/python.exe`；PowerShell 5 不支持 `&&`，用 `;` 或 `$LASTEXITCODE`。
- GUI 程序（PyQt）会占住终端：AI 只跑非阻塞检查（py_compile/冒烟/AST），界面验证由用户手动 `run.bat`。
