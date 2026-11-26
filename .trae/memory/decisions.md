# 技术决策记录

## 2026-11 快捷按钮配置：通用键名迁移机制（config_schema.py）
- 配置键名「文件暂存路径」统一改为「临时文件路径」。**不做新旧键兼容读取**：缺新键即默认值，保存只写新键（用户明确要求）。
- 改键名等配置结构变更，只改 `utils/config_schema.py` 的 `RENAMES`（旧→新映射）+ `TYPE_SCHEMAS`（各类型规范键+默认值），加载/导入经 `add_button`、编辑保存经 `edit_button` 统一收口规范化。未来再改任何键名只需加一条 RENAMES。

## 2026-11 配置缺失键三档自适应
1. 可推导：`临时文件路径` 缺失/空 → 按 `用户名` 推导 `/home/{用户名}`；
2. 公认默认：`端口` 缺失/空 → `'22'`；
3. 必填不猜：IP/用户名/密码缺失不造数据，点击时 `_check_required_then_run`（MainWindowLogic）拦截并提示右键编辑补全。方案讨论后用户选定 B（点击时拦截）。

## work_dir（临时文件路径）校验双保险
- 运行时收口：`SSHTools.resolve_work_dir`（utils/ssh_tools.py）——非 `/` 开头/含反斜杠/盘符的路径一律回退 `/home/{用户名}`，不抛异常。send_files/get_files 及资源监控、弱网的脚本/日志/清理路径全部经它。
- 前端校验：`validate_work_dir`（dialogs/base_dialog.py）——非空必须 Linux 绝对路径，不合法红框；base/resource/send/get/weak_net 五个对话框保存时接入。

## SSH 连接参数
- paramiko connect 统一加 `allow_agent=False, look_for_keys=False`（ssh_tools.py 与 server_check_run_dialog.py 两处连接点），规避 Windows ssh-agent 管道残留导致的 `[Errno 22] Invalid argument: \\.\pipe\openssh-ssh-agent`。

## 标签栏滚动箭头压标签修复（ScrollSafeTabBar）
- MainWindowLogic 的 ScrollSafeTabBar：绘制完后用底色覆盖左右滚动按钮占位区，标签干净截断。
- 分组/终端两处 QTabWidget 均换用；分组栏**不要 setStyleSheet**（会让 QTabBar 走 QStyleSheetStyle 渲染路径，几何随系统主题/DPI 变化，曾在测试机复现箭头压标签），corner「+」容器父对象设为 tabWidget 与终端栏一致。

## 其他
- 绘图窗口「更新数据」的单文件下载改走 SCP（GraphWindowLogic do_update），与主传输约定一致；不加 sftp/scp 降级（用户明确要求，全项目无降级机制）。背景：2026-11-23 起某现场网络策略阻断 sftp 子系统（exec/SCP 正常），导致 sftp 版更新数据全挂，详见 pitfalls.md。
- 版本号固定 Windows 四段式 `2.5.0.0`（version.py），spec 直接 split 转元组，格式错立即报错。
- 绘图保存默认文件名 = 标签页名（GraphWindowLogic `_NamedCanvas.get_default_filename`）；节点树勾选复选框自动切标签+选节点。
- 记事本窗口尺寸持久化（键：窗口宽度/窗口高度，默认 480×360，resizeEvent 400ms 防抖）。
