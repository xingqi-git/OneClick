# 技术决策记录

## 2026-11 获取文件打包：默认包名纠偏为 .tar（内容不压缩，禁止 .tar.gz 名不副实）
- 服务器端 tar -cf 无压缩（见下条），但旧默认包名 `当前时间_IP.tar.gz` 会让解压工具按 gzip 解纯 tar 而报错。
- 默认值改 `当前时间_IP.tar`（config_schema/get_files_dialog placeholder/create_sc fallback）；渲染精确串匹配**同时接受新旧两个默认串**，统一落为 `{时间}-{IP}.tar`——老配置存着旧串无需迁移自动纠偏；edit_sc 回显把两个默认串都显示为空走 placeholder。

## 2026-11 sudo 能力连接期探测 + 传输按权限分层（sudo_ok 体系）
- **连接期探测**：`SSHTools.connect()` 末尾执行 `echo 密码 | sudo -S true` 一次（root 直连直接 sudo_ok=True），退出码 0=有权限 / 127=无 sudo 命令 / 其他=无 sudoers 权限，结果缓存 `self.sudo_ok`，与 `_sftp_ok` 成对的连接期状态；本连接内不重探。
- **快捷按钮 get_files 分叉**：非 root 且 sudo_ok 才拼 sudo 前缀；无 sudo 全程不提权，靠 find 保留部分结果 + tar_errors 明细实现"能下多少下多少"的部分成功语义；chmod 644 仅在 sudo 路径执行。放弃"先不用 sudo 失败再补"方案：find 无权限时静默返回部分结果，无法可靠判定是否需要 sudo。
- **文件浏览器直传 + sudo 兜底**：`_fb_download` 改两段式管线——第一段逐项直传（文件 `get_file` 平铺、文件夹 `get_dir` 整体递归，无服务器临时文件，类型来自浏览器行数据 `is_dir`）；单项失败收集残留清理，收尾（主线程）询问"是否用 sudo 重试"，选是对失败项走 get_files sudo 链路（第二段 worker）。直传阶段必须 `transfer_stat=1` 且给 get_file/get_dir 传中止检查回调（SFTP 分支的 _print_progress 不生效）。`download_requested` 信号改为携带 `(路径, is_dir)` 元组。**直传进度**走既有 log_progress→运行信息面板同行刷新管线：字节级回调合并中止检查，phase='download'、extra=`名称|大小|已传|序号|总数` 5 段，`_format_progress` 按 op_id 前缀 `fb_download` 渲染"文件i/N: 名 pct% (MB)"（无总体百分比——直传不预查远端大小）；双击打开走简单格式 `pct% (MB)`。get_file/get_dir 两后端（SFTP/SCP）回调签名统一为 `(name, size, sent)`。
- **双击打开对齐**：`_fb_open_file` 改 get_file 直传 OneClick_Temp，失败同样询问 sudo → get_files 单源兜底；编辑会话登记/打开方式收尾不变。
- **死代码清理**：`self.sudo` 属性（6 处赋值零读取）与死方法 `get_root_priority()`（全项目无调用）删除；fs_stat 注释同步。
- 冒烟通过：sudo/无 sudo 两路径命令构造、无 sudo tar 失败容错（tar_errors 继续下载 / 无包返回 False+清理）、transfer_stat 中止。真机实测待用户回报。

## 2026-11 统一传输策略层（SFTP 优先 / SCP+exec 降级）——取代旧"一律 SCP"约定
- 背景：大量现场网络策略掐 SFTP 子系统；但通用软件还面对反向场景（chroot sftp-only 账户只放行 SFTP、限制 exec），exec-only 方案同样会挂 → 双后端才是"通用"。
- 设计（用户定版）：`SSHTools.connect()` 连接期嗅探一次（open_sftp + 5 秒 sock 超时防黑洞挂起），结果缓存实例（`_sftp_ok`/`_sftp_client`），本连接内零重嗅探。
- 统一入口全部在 ssh_tools.py：`put_file`/`get_file`/`get_dir`（传输，SFTP 后端 + SCPClient 降级）+ `fs_listdir/fs_normalize/fs_home/fs_exists/fs_rename/fs_remove/fs_mkdir/fs_touch/fs_rmtree`（目录管理，SFTP 后端 + exec 命令降级）。
- 运行期自愈：SFTP 通道级失败（SSHException/EOFError/无 errno OSError）→ `_mark_sftp_down` 永久降级 + 本次 SCP/exec 重试；文件级错误（IOError 带 errno：不存在/无权限）原样上抛不降级；用户中止（`TransferAborted`，`_print_progress` 抛出）原样上抛不降级。**注意 fs 操作发生在 transfer_stat==0 时，中止判定绝不能用 transfer_stat 区分**。
- exec 列目录用 `find -maxdepth 1 -printf '%y\t%s\t%T@\t%f\n'`（一次拿全类型/大小/时间戳，空格文件名安全；换行符文件名不支持——已接受的取舍）。
- 接入点：send_files/get_files 内部传输、文件浏览器全部目录操作、upload_single_file（编辑回传）、资源监控 2 处脚本上传、绘图更新数据。外部散装 `open_sftp`/`SCPClient` 已清零，仅 ssh_tools.py 持有。死代码 `clean_empty_dir` 已删。

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
