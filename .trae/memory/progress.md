# 当前进度与待办

## 已完成（2026-11 近期）
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
