# -*- coding: utf-8 -*-
"""
帮助文档内容
把 HTML 内容作为字符串嵌入，避免打包时的路径问题
"""

HELP_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OneClick 使用帮助</title>
    <style>
        body {
            font-family: "Microsoft YaHei", "SimHei", sans-serif;
            line-height: 1.7;
            color: #333;
            max-width: 850px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
            margin-top: 0;
        }
        h2 {
            color: #2980b9;
            border-left: 4px solid #3498db;
            padding-left: 12px;
            margin-top: 28px;
            background-color: #e8f4fc;
            padding-top: 5px;
            padding-bottom: 5px;
        }
        h3 {
            color: #16a085;
            margin-top: 20px;
            margin-bottom: 8px;
        }
        code {
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", monospace;
            color: #e74c3c;
        }
        .tip {
            background-color: #e8f8f5;
            border-left: 4px solid #1abc9c;
            padding: 10px 15px;
            margin: 12px 0;
            border-radius: 4px;
        }
        .warn {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px 15px;
            margin: 12px 0;
            border-radius: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            background-color: white;
            font-size: 14px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 10px;
            text-align: left;
        }
        th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }
        tr:nth-child(even) {
            background-color: #f2f7fc;
        }
        ol, ul {
            padding-left: 22px;
        }
        li {
            margin-bottom: 4px;
        }
        .footer {
            text-align: center;
            margin-top: 35px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <h1>OneClick 使用说明</h1>

    <h2>一、快速上手</h2>

    <h3>第 1 步：添加服务器</h3>
    <ol>
        <li>点击菜单栏 <code>服务器配置</code> → <code>编辑服务器列表</code></li>
        <li>点 <code>添加</code>，填写服务器名称、IP、端口、用户名、密码</li>
        <li>点 <code>确定</code> 保存</li>
    </ol>

    <h3>第 2 步：连接终端</h3>
    <ol>
        <li>在主界面右侧终端区，点 <code>+</code> 新建一个终端标签</li>
        <li>在标签内的下拉框选择服务器，点 <code>连接</code></li>
        <li>连接成功后即可在终端里操作，支持中文、Tab 补全、鼠标选中复制</li>
    </ol>
    <div class="tip">
        <strong>提示：</strong>终端是多标签设计，每个标签独立连接一台服务器，互不影响；标签可关闭，也可拖动排序。
    </div>

    <h3>第 3 步：添加快捷按钮（可选）</h3>
    <p>把常用操作做成一键按钮，省去重复配置：</p>
    <ol>
        <li>点击菜单栏 <code>添加快捷按钮</code>，选择按钮类型</li>
        <li>填写配置，点 <code>生成快捷按钮</code></li>
        <li>单击按钮即可一键执行；右键按钮可复制、编辑、删除或停止</li>
    </ol>

    <h2>二、主界面布局</h2>

    <p>主界面分三列，列宽可拖动调整：</p>
    <table>
        <tr>
            <th style="width:25%">区域</th>
            <th>说明</th>
        </tr>
        <tr>
            <td><strong>快捷按钮区</strong></td>
            <td>按分组管理快捷按钮，分组用标签页切换</td>
        </tr>
        <tr>
            <td><strong>文件浏览器</strong></td>
            <td>浏览已连接服务器的远程文件，支持上传下载</td>
        </tr>
        <tr>
            <td><strong>终端区</strong></td>
            <td>多标签 SSH 终端，每个标签独立连接</td>
        </tr>
    </table>

    <h3>分组管理</h3>
    <ul>
        <li>点标签栏左侧的 <code>+</code> 新建分组；双击分组名重命名</li>
        <li>分组标签可拖动排序，右键标签可新建、重命名、删除分组</li>
        <li>每个分组内有 <code>全选</code>、<code>执行选中</code>、<code>停止选中</code>、<code>删除选中</code> 按钮</li>
        <li>底部 <code>开始所有</code>、<code>结束所有</code> 控制所有分组的按钮</li>
    </ul>

    <h3>快捷按钮</h3>
    <ul>
        <li>单击执行；执行中再操作会提示，可右键 <code>停止</code> 中断</li>
        <li>右键菜单：复制、编辑、删除、停止</li>
        <li>按钮可在同分组内拖动排序，也可拖到其他分组</li>
        <li>勾选多个按钮后用分组工具栏批量执行</li>
    </ul>

    <h3>文件浏览器</h3>
    <ul>
        <li>双击文件夹进入，双击文件直接下载并用本地软件打开</li>
        <li>右键菜单：重命名、删除、下载、新建文件/文件夹</li>
        <li>把本地文件/文件夹拖入 = 上传；把远程文件拖出 = 下载</li>
    </ul>

    <h3>终端</h3>
    <ul>
        <li>点 <code>+</code> 新建终端标签，标签内自带服务器下拉框和连接/断开按钮</li>
        <li>支持中文显示、Tab 补全、鼠标选中复制</li>
        <li>点 <code>指令管理</code> 可维护常用指令；点 <code>清屏</code> 清空当前回显</li>
    </ul>

    <h2>三、快捷按钮类型</h2>

    <table>
        <tr>
            <th style="width:25%">类型</th>
            <th>说明</th>
        </tr>
        <tr>
            <td><strong>发送命令</strong></td>
            <td>连接服务器执行预设 Shell 命令，执行完自动断开，结果以弹窗提示</td>
        </tr>
        <tr>
            <td><strong>发送命令并接收回显</strong></td>
            <td>执行命令并实时接收回显，自动新建一个终端标签显示输出</td>
        </tr>
        <tr>
            <td><strong>发送文件</strong></td>
            <td>把本地文件/文件夹上传到服务器（SCP）</td>
        </tr>
        <tr>
            <td><strong>获取文件</strong></td>
            <td>把服务器上的文件/文件夹下载到本地（SCP）</td>
        </tr>
        <tr>
            <td><strong>复制本地文件</strong></td>
            <td>按筛选条件（修改时间、名称包含）批量复制本地文件，可按时间戳目录转储</td>
        </tr>
        <tr>
            <td><strong>资源监控</strong></td>
            <td>在服务器上部署监控脚本，采集系统与进程指标，支持绘图分析</td>
        </tr>
        <tr>
            <td><strong>弱网</strong></td>
            <td>基于 Linux tc 的网络质量模拟（延迟、丢包、限速等）</td>
        </tr>
        <tr>
            <td><strong>服务器检查</strong></td>
            <td>批量检查多台服务器的健康状态</td>
        </tr>
        <tr>
            <td><strong>记事本</strong></td>
            <td>点击打开独立笔记窗口，随手记录，内容与窗口大小自动记住，窗口可置顶</td>
        </tr>
    </table>

    <h2>四、资源监控与绘图</h2>

    <h3>监控配置</h3>
    <ul>
        <li><code>采样频率</code>：多少秒采一次样；<code>监控时长</code>：0 表示无限持续</li>
        <li><code>进程名称</code>：要监控的进程名，可多个（空格分隔），同一进程的每个 PID 记录到独立日志</li>
        <li>系统监控内容：已用内存、CPU 使用率、磁盘读写、文件描述符、Socket 描述符、进程数</li>
        <li>进程监控内容：内存（VmRSS/VmSize 等）、CPU 使用率、FD 数、Socket 数</li>
        <li>目标机是嵌入式系统（ash）时勾选对应选项</li>
    </ul>

    <h3>控制面板</h3>
    <ul>
        <li><code>开始监控</code> / <code>停止监控</code>：控制服务器上的监控脚本</li>
        <li><code>清除数据</code>：清理本地或服务器上的监控数据</li>
        <li><code>下载数据</code>：把服务器上的监控数据下载到本地</li>
        <li><code>监控绘图</code>：打开绘图窗口分析数据（本地数据即可，不要求监控在运行）</li>
    </ul>

    <h3>绘图窗口</h3>
    <ul>
        <li>左侧树勾选要看的 <code>进程 / 指标</code>，每个指标一个图签页；多 PID 进程可展开 <code>PID</code> 分组勾选具体 PID，勾选分组节点即全选；勾选某项指标后自动切换到对应图签页并选中该节点</li>
        <li>顶部 <code>切换数据源</code>：打开其他目录的数据；<code>更新数据</code>：从服务器拉取最新数据（监控运行中才有意义）</li>
        <li>时间筛选：设置开始/结束时间后点 <code>应用筛选</code>，点 <code>重置</code> 恢复全部</li>
        <li>点击图例项或曲线本体：切换该曲线显隐，隐藏的图例项变淡；双击子图区域：显示/隐藏图例；图例可拖拽</li>
        <li>每次切换曲线显隐后，坐标轴自动适应到当前可见数据的范围（手动缩放会被取消）</li>
        <li>工具栏 <code>Home</code> 按钮恢复到可见数据的全景；其余按钮为缩放、平移、保存图片等标准功能，保存图片的默认文件名即当前图签页名</li>
    </ul>

    <h2>五、弱网模拟</h2>

    <ul>
        <li>仅支持 Linux 服务器（基于 tc 命令），需 root/sudo 权限</li>
        <li>单条规则可配：延迟、抖动、丢包率、损坏率、重复率、重排率、重排间隔、带宽、持续时长</li>
        <li>可添加多条规则按顺序循环执行，<code>循环次数</code> 0 表示无限循环</li>
        <li>规则支持上移/下移调整顺序，<code>保存配置</code> 可复用</li>
    </ul>

    <div class="warn">
        <strong>注意：</strong>弱网规则可能影响当前 SSH 连接本身，建议保留其他连接通道，或设置有限的持续时长。
    </div>

    <h2>六、服务器检查</h2>

    <ul>
        <li>内置检查项：连通、SSH 登录、Root SSH 权限、系统时间（可勾选自动同步时间）、防火墙</li>
        <li><code>添加命令回显行</code>：自定义要执行并检查回显的命令，可加多条</li>
        <li><code>添加服务器</code>：把多台服务器加入检查列表，一次批量出结果</li>
    </ul>

    <h2>七、配置与数据目录</h2>

    <p>所有运行产生的数据都在 <strong>程序所在目录</strong> 下：</p>

    <table>
        <tr>
            <th style="width:30%">目录/文件</th>
            <th>说明</th>
        </tr>
        <tr>
            <td><code>config.json</code></td>
            <td>配置文件（服务器列表、快捷按钮、分组、日志设置等）</td>
        </tr>
        <tr>
            <td><code>logs/</code></td>
            <td>运行日志与崩溃日志，出问题时可查看</td>
        </tr>
        <tr>
            <td><code>&lt;服务器IP&gt;/Monitor/</code></td>
            <td>从该服务器下载的监控数据；监控本机时为 <code>local/Monitor/</code></td>
        </tr>
        <tr>
            <td><code>_internal/</code></td>
            <td>程序内部依赖（dll、pyd 等），不要修改或删除（仅文件夹版存在）</td>
        </tr>
    </table>

    <h3>备份与恢复配置</h3>
    <ul>
        <li>备份：菜单 <code>选项</code> → <code>导出配置</code></li>
        <li>恢复：<code>选项</code> → <code>导入配置（追加）</code>（合入现有配置）或 <code>导入配置（覆盖）</code>（替换现有配置）</li>
        <li>另有 <code>打开程序目录</code>、<code>日志设置</code>（日志开关、级别、保留个数）</li>
    </ul>

    <h2>八、常见问题</h2>

    <h3>SSH 连不上？</h3>
    <ul>
        <li>确认 IP、端口、用户名、密码正确</li>
        <li>确认服务器开启了 SSH 服务，防火墙放行了对应端口</li>
        <li>确认本地能 ping 通服务器</li>
    </ul>

    <h3>监控数据在哪？</h3>
    <p>远程监控数据在服务器的 <code>临时文件路径/OneClick/Monitor/</code> 下；点控制面板的 <code>下载数据</code> 下载到本地 <code>&lt;服务器IP&gt;/Monitor/</code> 目录。临时文件路径必须是 Linux 绝对路径（<code>/</code> 开头），留空或填错时自动使用登录用户的家目录。</p>

    <h3>绘图窗口看不到某条曲线？</h3>
    <p>每次切换曲线显隐后坐标轴都会自动适应到可见数据范围，若仍看不到，点工具栏 <code>Home</code> 恢复全景，或检查左侧树里该 PID/指标是否已勾选。</p>

    <h3>弱网功能用不了？</h3>
    <ul>
        <li>仅限 Linux 服务器，需要 root 或 sudo 权限</li>
        <li>服务器需安装 iproute2 工具包（tc 命令）</li>
    </ul>

    <h3>怎么备份配置？</h3>
    <p>菜单 <code>选项</code> → <code>导出配置</code>，把服务器列表和快捷按钮导出为文件。</p>

    <h3>版本号在哪看？</h3>
    <p>菜单 <code>帮助</code> → <code>关于</code>。</p>

    <div class="footer">
        OneClick | 一键式服务器运维管理工具
    </div>
</body>
</html>'''
