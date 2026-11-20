# 项目约定

## 语言与文案
- 注释、日志文案、用户提示一律中文；技术标识符/路径/命令保留英文原样。

## 配置键读写
- 快捷按钮配置读取统一 `config.get('键名', 默认)`，禁止裸索引 `cfg['键名']`（normalize_button_config 保证键存在，但防御手动粘贴的毒数据）。
- 保存只写当前规范键；键名变更走 utils/config_schema.py 的 RENAMES。
- 敏感信息（密码等）不写入任何会进 git 的文件（config.json 已被 .gitignore 忽略）。

## 修改流程
1. 改代码 → `py_compile` 编译检查（用 venv 解释器）；
2. 可离线验证的逻辑写 offscreen 冒烟脚本（Temp 目录，验证完删除）；
3. GUI 效果由用户手动验证：项目根目录 `run.bat`（内含 venv 完整路径，任何终端可用）。

## 验证原则
- 涉及几何/渲染的验证用真实 Windows 平台渲染截图，offscreen 不可信。
- 静态分析（AST 扫描闭包读前赋值等）作为全项目兜底检查手段。
- 先确认问题存在/根因，经用户确认方案后再改代码；用户明确说"先只检查不要改"时严格遵守。

## 项目结构速查
- 主入口 OneClick.py；主窗口逻辑 MainWindowLogic.py；绘图 GraphWindowLogic.py。
- dialogs/ 各功能对话框（base_dialog.py 含共享校验/工具函数）；utils/ssh_tools.py（SSH 封装+resolve_work_dir）；utils/config_schema.py（配置规范化）。
- UI/ 为 Qt Designer 生成的界面代码；config.json 运行时配置（gitignore）。
