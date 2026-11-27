# 项目约定

## 删除 UI 元素必须删创建源头，禁止"先建后删"与 hide 兜底（2026-11-27 用户明确要求）
- 用户要求去掉某 UI 元素时，删除其**创建代码本身**（UI/MainWindow.py 的控件创建/addWidget/retranslateUi setText，无 .ui 源文件、该 py 即唯一源），禁止 ①运行时 removeWidget+deleteLater 打补丁 ②hide()/setVisible(False) 留死控件。
- 项目用 git 管理版本，删错可回退，不允许以"怕删错"为由留任何形式的隐藏/回退代码。

## 路径呈现统一正斜杠（2026-11-26 用户明确要求）
- 所有呈现给用户的路径（日志面板、运行信息、状态栏）一律正斜杠 `/`，无论 Windows 还是 Linux——输出前 `.replace('\\', '/')`。反斜杠只允许存在于文件系统操作内部，不得出现在用户可见文本里。
- 注意：Python 3.8 的 f-string 表达式内不能写反斜杠字面量，转换放在输出前的普通代码行；Windows API 对正斜杠路径完全兼容，转换不影响后续 os 操作。

## UI 文案与日志禁止暴露实现思考（2026-11-26 用户明确要求）
- 界面文案（placeholder/提示语）只说"是什么"，不解释"为什么/怎么实现的"——例：打包不压缩是实现细节，不得写进输入框 placeholder。
- 日志同理：砍掉括号内的解释性补充（"（文件操作优先 SFTP）""（后续操作不再尝试 SFTP）"这类）；同一事件不连发多条重叠日志，状态型提示降 debug。
- 写完文案自查一句：用户需要这条信息做什么操作/判断？答不上来就删。

## 语言与文案
- 注释、日志文案、用户提示一律中文；技术标识符/路径/命令保留英文原样。

## 对话框一致性
- 配置对话框有两套平行实现：SendCMDDialog 继承系（发送命令/接收回显/资源监控/弱网）与独立的 SendFilesDialog/GetFilesDialog。修改通用行为（如 reset、服务器下拉、校验）时必须两套都检查对齐，reset 统一 `setCurrentIndex(-1)` 保留服务器列表，禁止 `clear()`。

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
