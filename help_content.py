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
            background: linear-gradient(to right, #e8f4fc, transparent);
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
        <li>主界面左上角下拉框选择服务器，点 <code>连接</code></li>
        <li>连接成功后即可在终端里操作，支持中文、Tab 补全、鼠标选中复制</li>
    </ol>

    <h3>第 3 步：添加快捷按钮（可选）</h3>
    <p>把常用操作做成一键按钮，省去重复敲命令：</p>
    <ol>
        <li>点击菜单栏 <code>添加快捷按钮</code>，选择按钮类型</li>
        <li>填写配置，点 <code>生成快捷按钮</code></li>
        <li>点击按钮即可一键执行</li>
    </ol>

    <div class="tip">
        <strong>提示：</strong>快捷按钮支持分组管理，点分组栏的 <code>+</code> 新建分组，双击分组名重命名。
    </div>

    <h2>二、功能介绍</h2>

    <table>
        <tr>
            <th style="width:25%">功能</th>
            <th>说明</th>
        </tr>
        <tr>
            <td><strong>SSH 终端</strong></td>
            <td>多标签终端，支持指令管理、快捷按钮、中文显示</td>
        </tr>
        <tr>
            <td><strong>发送命令</strong></td>
            <td>向服务器发送预设的 Shell 命令</td>
        </tr>
        <tr>
            <td><strong>发送/获取文件</strong></td>
            <td>本地与服务器之间传输文件（SCP）</td>
        </tr>
        <tr>
            <td><strong>资源监控</strong></td>
            <td>监控指定进程的 CPU、内存、磁盘、网络等，图表展示</td>
        </tr>
        <tr>
            <td><strong>弱网模拟</strong></td>
            <td>基于 Linux tc 的网络模拟，支持延迟、丢包、带宽等，可多规则循环</td>
        </tr>
        <tr>
            <td><strong>服务器检查</strong></td>
            <td>批量检查多台服务器健康状态（连通性、时间、防火墙等）</td>
        </tr>
        <tr>
            <td><strong>复制本地文件</strong></td>
            <td>本地文件批量复制、转储</td>
        </tr>
    </table>

    <h2>三、数据目录</h2>

    <p>所有运行产生的数据都在 <strong>exe 同目录</strong> 下：</p>

    <table>
        <tr>
            <th style="width:30%">目录/文件</th>
            <th>说明</th>
        </tr>
        <tr>
            <td><code>config/</code></td>
            <td>配置文件（服务器列表、快捷按钮、软件设置等）</td>
        </tr>
        <tr>
            <td><code>logs/</code></td>
            <td>运行日志，出问题时可查看</td>
        </tr>
        <tr>
            <td><code>&lt;服务器IP&gt;/</code></td>
            <td>各服务器的资源监控数据（按 IP 分目录，Monitor 子目录下）</td>
        </tr>
        <tr>
            <td><code>_internal/</code></td>
            <td>程序内部依赖（dll、pyd 等），不要修改或删除</td>
        </tr>
    </table>

    <h2>四、常见问题</h2>

    <h3>SSH 连不上？</h3>
    <ul>
        <li>确认 IP、端口、用户名、密码是否正确</li>
        <li>确认服务器开启了 SSH 服务，防火墙放行了对应端口</li>
        <li>本地能 ping 通服务器吗</li>
    </ul>

    <h3>监控数据在哪？</h3>
    <p>远程监控数据在服务器的 <code>{暂存路径}/OneClick/Monitor/</code> 目录下；点控制面板的 <code>下载数据</code> 可下载到本地 <code>&lt;IP&gt;/Monitor/</code> 目录。</p>

    <h3>弱网功能用不了？</h3>
    <ul>
        <li>仅限 Linux 服务器（需要 tc 命令）</li>
        <li>需要 root 或 sudo 权限</li>
        <li>服务器需安装 iproute2 工具包</li>
    </ul>

    <div class="warn">
        <strong>注意：</strong>弱网模拟可能导致当前 SSH 连接中断，建议设置较短的持续时长，或保留其他连接通道。
    </div>

    <h3>怎么备份配置？</h3>
    <p>菜单栏 <code>文件</code> → <code>另存为</code>，即可导出当前所有配置（服务器列表 + 快捷按钮）。</p>

    <div class="footer">
        OneClick | 一键式服务器运维管理工具
    </div>
</body>
</html>'''
