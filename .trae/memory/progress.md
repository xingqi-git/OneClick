# 当前进度与待办

## 已完成（2026-11 近期）
- 界面简化一轮（用户推动）：四区域标题控件从源头删除（UI/MainWindow.py 为唯一源无 .ui）；清屏/指令管理挪入终端标签页连接条（清屏按标签各自清）；全局"结束所有/开始所有"按钮及 stop_sc/execute_all_buttons 删除，批量操作收敛为分组工具栏 全选/执行选中/停止选中 一套；get_files 修复三连（tar -T 参数错位、默认包名 .tar.gz 名不副实、源目录壳条目进打包列表致筛选失效+重复条目）；_print_progress 100% 档 logger.info() 零参调用残留导致所有下载到 100% 即失败；root 家目录推导 /home/root→/root（derive_home 单一真相源收口 10 处）；呈现层路径统一正斜杠 11 处；文件浏览器列标题三态排序；多数修改**待真机回归**
- sudo 能力连接期探测 + 传输按权限分层：connect() 探测缓存 sudo_ok；get_files 非 root 无 sudo 时全程不提权（部分成功语义）；文件浏览器下载改直传（get_file/get_dir）+ 失败询问 sudo 兜底；双击打开对齐；死代码 self.sudo/get_root_priority 清理。冒烟通过，**待用户真机实测**（无 sudo 用户下载、浏览器直传/兜底弹窗、中止）
- 终端回显接收循环改阻塞式读取（ssh_tools.get_output_continue）：原 sleep(0.1)+recv_ready 轮询平均引入 50ms 按键延迟、吞吐上限 40KB/s；现 channel.settimeout(0.5) 阻塞 recv + 抽干缓冲 + 增量 UTF-8 解码（修跨包乱码），空闲期 0.5s 做健康检查，超时语义保留历史 3 倍行为
- 弱网控制窗口 + 服务器列表编辑窗口改为自动落盘（600ms 防抖，启动/停止/关闭前冲刷）：删除手动保存按钮/关闭时三问/_original_* 快照，启动与停止前冲刷防抖；服务器列表 del/clear 行需手动调度（removeRow 不触发 cellChanged），主窗口 server_cfg_dialog 不再依赖 accept 返回码
- 弱网 sudo 提权（方案A+C）：脚本内 sudo tc + 凭据缓存，启动前三连探测（sudo 存在/密码/tc 存在）失败给明确原因，停止命令同步提权；脚本第4参数传密码（单引号包裹）
- 更新数据（GraphWindowLogic do_update）SFTP 改 SCP 单文件下载：某现场网络策略阻断 sftp 子系统，详见 pitfalls.md
- 快捷按钮配置通用键名迁移 + 三档自适应 + 必填键点击拦截（config_schema.py / MainWindowLogic）
- 临时文件路径全链路收口：resolve_work_dir（ssh_tools）+ 前端五对话框校验 + 资源监控四条链路 + 弱网三条链路 + 停止监控写日志/轮询 tail
- log_signal 双参数 emit 修复（资源监控/弱网状态轮询线程崩溃）
- ScrollSafeTabBar 标签栏滚动箭头修复 + 分组栏样式表清除（对齐终端栏）
- 绘图保存默认文件名=标签名、节点树勾选联动、记事本窗口尺寸持久化、spec 四段版本号清理
- 项目根目录 run.bat 一键运行（venv 完整路径）
- .trae/memory/ 项目记忆体系建立（本目录，随 git 跨电脑同步）

## 待办
- [ ] 用户测试机验证分组标签栏箭头（需用户自行打包后测）
- [ ] 服务器手动清理残留：`rm -rf "/home/osadmin/C:\Users\..."` 怪目录（用户自行决定）
- [ ] （可选）弱网对话框外层死变量 user_path/script_path/clean_cmd 清理（无功能风险）
- [ ] （可选）传输启动时自动清理陈旧 OneClick_temp* 残留（曾建议，用户未要求）

## 用户偏好备忘
- Windows 本地开发、远程 Linux 服务器打包工作流；打包精简、UPX 压缩。
- 打包发版（pyinstaller OneClick.spec --clean）由用户手动操作，AI 不代劳、不主动提醒。
- 排查类问题常要求"先只分析不改代码"，方案需经确认再动手。
- 使用 Trae IDE 模式为主，手动点运行验证 GUI 效果，改动要能看到 diff。
