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
            line-height: 1.6;
            color: #333;
            max-width: 900px;
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
            margin-top: 30px;
            background: linear-gradient(to right, #e8f4fc, transparent);
            padding-top: 5px;
            padding-bottom: 5px;
        }
        h3 {
            color: #16a085;
            margin-top: 20px;
        }
        .env-box {
            background-color: #e8f8f5;
            border: 1px solid #1abc9c;
            border-radius: 6px;
            padding: 15px;
            margin: 15px 0;
        }
        .env-title {
            font-weight: bold;
            color: #16a085;
            font-size: 16px;
            margin-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            background-color: white;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 10px;
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
        .feature-card {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .feature-title {
            font-weight: bold;
            color: #e74c3c;
            font-size: 16px;
            margin-bottom: 10px;
        }
        .step-list {
            counter-reset: step;
            list-style: none;
            padding-left: 0;
        }
        .step-list li {
            counter-increment: step;
            padding: 12px 0 12px 50px;
            position: relative;
            margin-bottom: 10px;
            background-color: white;
            border-radius: 6px;
            border: 1px solid #eee;
        }
        .step-list li::before {
            content: counter(step);
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            width: 30px;
            height: 30px;
            background-color: #3498db;
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            font-weight: bold;
        }
        .tip-box {
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 6px;
            padding: 12px 15px;
            margin: 15px 0;
        }
        .tip-title {
            font-weight: bold;
            color: #856404;
        }
        .warning-box {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            border-radius: 6px;
            padding: 12px 15px;
            margin: 15px 0;
        }
        .warning-title {
            font-weight: bold;
            color: #721c24;
        }
        .highlight {
            background-color: #ffff00;
            padding: 2px 5px;
            border-radius: 3px;
        }
        code {
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", monospace;
            color: #e74c3c;
        }
        .footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <h1>🛠️ OneClick 一键式服务器运维管理工具</h1>

    <h2>📋 一、运行环境要求</h2>

    <div class="env-box">
        <div class="env-title">💻 客户端运行环境（Windows）</div>
        <table>
            <tr>
                <th>操作系统</th>
                <th>版本要求</th>
                <th>备注</th>
            </tr>
            <tr>
                <td>Windows 7</td>
                <td>需安装 SP1 及配套补丁</td>
                <td>详见压缩包中的安装说明</td>
            </tr>
            <tr>
                <td>Windows Server</td>
                <td>2008 R2 及以上</td>
                <td>推荐 2012/2016/2019</td>
            </tr>
            <tr>
                <td>Windows 10</td>
                <td>所有版本</td>
                <td>推荐使用</td>
            </tr>
            <tr>
                <td>Windows 11</td>
                <td>所有版本</td>
                <td>完全兼容</td>
            </tr>
        </table>
    </div>

    <div class="env-box">
        <div class="env-title">🖥️ 服务端支持系统（Linux）</div>
        <p>本工具兼容大部分主流 Linux 发行版，包括但不限于：</p>
        <table>
            <tr>
                <th>发行版</th>
                <th>支持版本</th>
                <th>说明</th>
            </tr>
            <tr>
                <td>CentOS</td>
                <td>6.x / 7.x / 8.x</td>
                <td>完全支持</td>
            </tr>
            <tr>
                <td>Red Hat Enterprise Linux (RHEL)</td>
                <td>6.x / 7.x / 8.x / 9.x</td>
                <td>完全支持</td>
            </tr>
            <tr>
                <td>统信 UOS</td>
                <td>桌面版 / 服务器版</td>
                <td>国产系统</td>
            </tr>
            <tr>
                <td>银河麒麟 Kylin</td>
                <td>桌面版 / 服务器版</td>
                <td>国产系统</td>
            </tr>
            <tr>
                <td>欧拉 openEuler</td>
                <td>20.03 / 22.03</td>
                <td>国产系统</td>
            </tr>
            <tr>
                <td>Ubuntu</td>
                <td>16.04 及以上</td>
                <td>完全支持</td>
            </tr>
            <tr>
                <td>Debian</td>
                <td>9.x 及以上</td>
                <td>完全支持</td>
            </tr>
        </table>
        <p><strong>服务端要求：</strong>开启 SSH 服务，端口默认为 22</p>
    </div>

    <h2>✨ 二、功能介绍</h2>

    <div class="feature-card">
        <div class="feature-title">📡 1. 服务器管理</div>
        <ul>
            <li><strong>多服务器配置：</strong>支持添加、编辑、删除多台服务器配置信息</li>
            <li><strong>快速连接：</strong>下拉选择服务器，一键建立 SSH 连接</li>
            <li><strong>配置导入导出：</strong>支持服务器配置的批量导入和导出</li>
            <li><strong>自动权限提升：</strong>非 root 用户可自动尝试 sudo 切换到 root 权限</li>
        </ul>
    </div>

    <div class="feature-card">
        <div class="feature-title">⚡ 2. 命令执行</div>
        <ul>
            <li><strong>发送命令：</strong>向远程服务器发送 Shell 命令并执行</li>
            <li><strong>实时回显：</strong>实时接收并显示命令执行输出结果</li>
            <li><strong>命令历史：</strong>自动保存执行过的命令，支持快速选择</li>
            <li><strong>快捷按钮：</strong>将常用命令保存为快捷按钮，一键执行</li>
            <li><strong>停止执行：</strong>支持随时中止正在执行的命令</li>
        </ul>
    </div>

    <div class="feature-card">
        <div class="feature-title">📁 3. 文件传输</div>
        <ul>
            <li><strong>发送文件：</strong>将本地文件上传到远程服务器指定目录</li>
            <li><strong>获取文件：</strong>从远程服务器下载文件到本地</li>
            <li><strong>本地复制：</strong>本地文件批量复制功能</li>
            <li><strong>进度显示：</strong>实时显示文件传输进度</li>
        </ul>
    </div>

    <div class="feature-card">
        <div class="feature-title">📊 4. 资源监控</div>
        <ul>
            <li><strong>系统资源监控：</strong>监控 CPU、内存、磁盘、网络等系统资源</li>
            <li><strong>进程监控：</strong>指定进程名称，监控其资源占用情况</li>
            <li><strong>数据采集：</strong>可配置采样频率，自动保存监控数据到日志</li>
            <li><strong>图表展示：</strong>支持历史数据可视化，生成趋势图表</li>
            <li><strong>本地监控：</strong>支持监控本机 Windows 进程资源</li>
        </ul>
    </div>

    <div class="feature-card">
        <div class="feature-title">🌐 5. 弱网模拟</div>
        <ul>
            <li><strong>基于 tc：</strong>使用 Linux Traffic Control 进行网络模拟</li>
            <li><strong>多种规则：</strong>支持延迟、丢包、带宽限制、损坏、重复、重排等</li>
            <li><strong>规则队列：</strong>多规则循环执行，支持持续时长与间隔时长</li>
            <li><strong>后台运行：</strong>脚本在服务器后台执行，不影响其他操作</li>
            <li><strong>运行日志：</strong>自动记录运行进度，支持随时查看历史记录</li>
        </ul>
    </div>

    <div class="feature-card">
        <div class="feature-title">✅ 6. 服务器检查</div>
        <ul>
            <li><strong>多服务器批量检查：</strong>支持同时检查多台服务器的健康状态</li>
            <li><strong>丰富检查项：</strong>连通性、SSH 登录、Root 权限、系统时间、防火墙、自定义命令</li>
            <li><strong>实时结果更新：</strong>逐项显示检查结果，绿色 ✔️ 通过 / 红色 ❌ 不通过</li>
            <li><strong>智能依赖：</strong>前面检查失败，后续依赖项自动标记跳过</li>
            <li><strong>运行控制：</strong>可随时停止检查，关闭窗口时有确认提示</li>
        </ul>
    </div>

    <h2>🚀 三、快速上手</h2>

    <div class="feature-card">
        <div class="feature-title">📌 功能概述</div>
        <p>本工具主要包含两大核心功能模块：</p>
        <table>
            <tr>
                <th style="width:50%">模块一：主界面远程终端</th>
                <th style="width:50%">模块二：快捷按钮自动化</th>
            </tr>
            <tr>
                <td>类似 MobaXterm / SecureCRT 的远程 SSH 工具</td>
                <td>一键执行预配置操作，提升运维效率</td>
            </tr>
            <tr>
                <td>• 手动连接服务器</td>
                <td>• 发送预设指令</td>
            </tr>
            <tr>
                <td>• 实时命令交互</td>
                <td>• 自动收发文件</td>
            </tr>
            <tr>
                <td>• 查看实时回显</td>
                <td>• 本地文件一键转储</td>
            </tr>
            <tr>
                <td>• 命令历史记录</td>
                <td>• 本机/远程资源监控</td>
            </tr>
        </table>
    </div>

    <h3>第一步：添加服务器配置</h3>
    <ol class="step-list">
        <li>点击菜单栏 <code>服务器配置</code> → <code>编辑服务器列表</code></li>
        <li>在弹出的对话框中点击 <code>添加</code> 按钮</li>
        <li>填写服务器信息：服务器名称、IP地址、端口、用户名、密码</li>
        <li>点击 <code>确定</code> 保存配置</li>
        <li>可通过 <code>从配置文件批量添加</code> 导入服务器配置</li>
    </ol>

    <div class="tip-box">
        <div class="tip-title">💡 提示</div>
        <p>配置文件为 JSON 格式，可手动编辑或从其他机器导出导入。</p>
    </div>

    <h3>模块一：远程终端功能（手动操作）</h3>
    <p>连接服务器后，可像使用 MobaXterm / SecureCRT 一样进行手动命令交互：</p>

    <h4>1. 连接服务器</h4>
    <ol class="step-list">
        <li>在主界面 <code>服务器</code> 下拉列表中选择要连接的服务器</li>
        <li>点击 <code>连接</code> 按钮建立 SSH 连接</li>
        <li>连接成功后，运行信息区会显示连接状态</li>
        <li>如使用非 root 用户，工具会自动尝试获取 root 权限</li>
    </ol>

    <div class="warning-box">
        <div class="warning-title">⚠️ 注意</div>
        <p>请确保网络通畅，远程服务器已开启 SSH 服务，防火墙已开放对应端口。</p>
    </div>

    <h4>2. 执行命令</h4>
    <ol class="step-list">
        <li>在命令输入框中输入要执行的 Shell 命令</li>
        <li>按 <code>Enter</code> 键或点击 <code>发送命令</code> 按钮执行</li>
        <li>按 <code>Shift + Enter</code> 可换行输入多行命令</li>
        <li>按 <code>Ctrl + C</code> 可中止当前执行的命令</li>
        <li>命令执行结果会实时显示在"服务器回显"区域</li>
    </ol>

    <h4>3. 保存常用命令</h4>
    <ol class="step-list">
        <li>输入命令后，点击 <code>保存</code> 按钮将命令保存到历史</li>
        <li>下次可直接从命令下拉列表中选择，无需重复输入</li>
        <li>点击 <code>删除</code> 按钮可移除不需要的历史命令</li>
    </ol>

    <h4>4. 其他主界面功能</h4>
    <ul>
        <li><strong>停止按钮：</strong>立即结束所有正在执行的后台任务和线程</li>
        <li><strong>清空按钮：</strong>清空 Linux 回显区域的内容</li>
        <li><strong>开始所有：</strong>批量执行所有分组标签页中可批量执行的按钮</li>
        <li><strong>文件日志：</strong>勾选后运行信息会同时写入 <code>OneClick.log</code> 文件</li>
    </ul>

    <h3>模块二：快捷按钮功能（自动化操作）</h3>
    <p>将常用操作配置为快捷按钮，实现一键执行，大幅提升运维效率：</p>

    <h4>1. 分组管理</h4>
    <p>快捷按钮按分组标签页组织，支持以下操作：</p>
    <ul>
        <li><strong>新建分组：</strong>点击 <code>+</code> 按钮或右键菜单新建分组</li>
        <li><strong>重命名分组：</strong>双击分组标签页名称进行修改</li>
        <li><strong>删除分组：</strong>右键点击分组标签页选择删除（至少保留一个分组）</li>
        <li><strong>移动按钮到分组：</strong>右键点击按钮选择目标分组</li>
    </ul>

    <h4>2. 创建快捷按钮</h4>
    <ol class="step-list">
        <li>点击菜单栏 <code>添加快捷按钮</code>，选择需要的按钮类型</li>
        <li>在弹出的配置对话框中填写相关参数</li>
        <li>点击 <code>生成快捷按钮</code>，按钮将出现在当前分组标签页中</li>
        <li>点击按钮即可一键执行预配置的操作</li>
    </ol>

    <h4>3. 按钮操作</h4>
    <ul>
        <li><strong>左键单击：</strong>执行按钮对应的操作</li>
        <li><strong>长按拖动：</strong>在同分组内调整按钮排列顺序</li>
        <li><strong>右键菜单：</strong>复制、编辑、删除、停止、移动到分组</li>
        <li><strong>复选框：</strong>勾选后可通过分组工具栏进行批量操作</li>
    </ul>

    <h4>4. 批量操作（分组工具栏）</h4>
    <ul>
        <li><strong>全选：</strong>切换该分组下所有按钮的勾选状态</li>
        <li><strong>执行选中：</strong>批量执行勾选的按钮（跳过交互式类型）</li>
        <li><strong>停止选中：</strong>发送中止信号给选中按钮的正在执行任务</li>
        <li><strong>删除选中：</strong>删除勾选的按钮（正在执行的会被跳过）</li>
    </ul>

    <h4>5. 快捷按钮类型说明</h4>
    <table>
        <tr>
            <th>按钮类型</th>
            <th>功能说明</th>
            <th>适用场景</th>
        </tr>
        <tr>
            <td><strong>发送命令</strong></td>
            <td>向远程服务器发送预设的 Shell 命令</td>
            <td>启停服务、执行脚本等</td>
        </tr>
        <tr>
            <td><strong>发送命令并接收回显</strong></td>
            <td>发送命令并捕获完整输出结果</td>
            <td>需要查看详细执行日志</td>
        </tr>
        <tr>
            <td><strong>发送文件</strong></td>
            <td>将本地文件自动上传到远程服务器指定目录</td>
            <td>配置文件分发、程序部署</td>
        </tr>
        <tr>
            <td><strong>获取文件</strong></td>
            <td>从远程服务器自动下载文件到本地</td>
            <td>日志收集、配置备份</td>
        </tr>
        <tr>
            <td><strong>复制本地文件</strong></td>
            <td>本地文件批量复制、一键转储</td>
            <td>本机文件分发、数据迁移</td>
        </tr>
        <tr>
            <td><strong>资源监控</strong></td>
            <td>进程资源实时监控（支持本机/远程服务器）</td>
            <td>性能监控、故障排查</td>
        </tr>
        <tr>
            <td><strong>弱网</strong></td>
            <td>基于 tc 的网络模拟，支持延迟/丢包/带宽等规则</td>
            <td>网络稳定性测试、故障注入</td>
        </tr>
        <tr>
            <td><strong>服务器检查</strong></td>
            <td>多服务器健康状态批量检查，支持 6 种内置检查项 + 自定义命令回显</td>
            <td>环境巡检、上线前验证、定期健康检查</td>
        </tr>
    </table>

    <h4>3. 资源监控功能详解</h4>
    <div class="tip-box">
        <div class="tip-title">📊 两种监控模式</div>
        <ul>
            <li><strong>监控本机：</strong>IP 留空，监控本地 Windows 系统的指定进程资源（CPU、内存、句柄数等）</li>
            <li><strong>监控远程服务器：</strong>填写服务器信息，通过 SSH 监控 Linux 服务器上的指定进程</li>
        </ul>
    </div>

    <ol class="step-list">
        <li>创建"资源监控"类型快捷按钮</li>
        <li>配置要监控的进程名称（如：doubao、java、mysql 等）</li>
        <li>设置采样频率（单位：秒），建议 5-60 秒</li>
        <li>点击按钮打开监控控制面板</li>
        <li>点击<code>开始监控</code>启动监控，脚本将在后台运行</li>
        <li>点击<code>停止监控</code>终止监控进程</li>
        <li>点击<code>查看数据</code>打开图表窗口查看历史数据</li>
        <li>点击<code>下载数据</code>从远程服务器下载最新监控数据到本地（仅远程模式）</li>
        <li>点击<code>清除数据</code>可选择清除本地、服务器或全部监控数据</li>
    </ol>

    <div class="tip-box">
        <div class="tip-title">💡 监控数据存储</div>
        <p>本机监控数据保存在 <code>local/OneClick/</code> 目录下，远程监控数据保存在服务器的 <code>{文件暂存路径}/OneClick/Monitor/</code> 目录下。</p>
    </div>

    <h4>4. 弱网模拟功能详解</h4>
    <div class="warning-box">
        <div class="warning-title">⚠️ 重要提醒</div>
        <p>弱网设置可能导致 SSH 连接中断，请确保已配置好停止条件或保留其他可用连接通道。</p>
    </div>

    <ol class="step-list">
        <li>创建"弱网"类型快捷按钮，配置服务器信息（包括文件暂存路径，用于存放脚本和日志）</li>
        <li>点击按钮进入弱网控制面板，选择目标网卡（自动获取服务器网卡列表，也可手动刷新）</li>
        <li>编辑规则：设置延迟、丢包率、带宽限制、损坏率、重复率、重排率等参数</li>
        <li>设置每条规则的<strong>持续时长</strong>（规则生效时间）和<strong>间隔时长</strong>（恢复正常网络的时间）</li>
        <li>将规则添加到队列，可调整顺序或删除不需要的规则</li>
        <li>设置循环次数（0 表示无限循环）</li>
        <li>点击<code>开始弱网</code>执行，脚本将在服务器后台运行</li>
        <li>点击<code>查看运行日志</code>可查看实时进度和历史运行记录（日志会自动下载到本地）</li>
        <li>点击<code>停止弱网</code>立即终止脚本并清除所有 tc 规则</li>
    </ol>

    <div class="tip-box">
        <div class="tip-title">💡 规则参数说明</div>
        <ul>
            <li><strong>延迟：</strong>增加网络延迟，单位毫秒（如 100ms）</li>
            <li><strong>抖动：</strong>延迟的波动范围，需配合延迟使用</li>
            <li><strong>丢包率：</strong>随机丢弃数据包的百分比（如 5%）</li>
            <li><strong>损坏率：</strong>随机损坏数据包的百分比</li>
            <li><strong>重复率：</strong>重复发送数据包的百分比</li>
            <li><strong>重排率：</strong>乱序发送数据包的百分比</li>
            <li><strong>带宽：</strong>限制网络带宽（如 1mbit、100kbit）</li>
        </ul>
    </div>

    <h3>5. 服务器检查功能详解</h3>
    <p>服务器检查功能用于批量验证多台服务器的健康状态，支持多种内置检查项和自定义命令回显检查。</p>

    <div class="tip-box">
        <div class="tip-title">💡 检查项说明</div>
        <table>
            <tr>
                <th style="width:25%">检查项</th>
                <th style="width:25%">配置参数</th>
                <th>说明</th>
            </tr>
            <tr>
                <td><strong>连通</strong></td>
                <td>检查复选框 + 期望结果（是/否）</td>
                <td>通过 ping 命令检测服务器网络是否可达</td>
            </tr>
            <tr>
                <td><strong>SSH登录</strong></td>
                <td>检查复选框 + 期望结果（是/否）</td>
                <td>验证 SSH 服务是否正常响应并可登录</td>
            </tr>
            <tr>
                <td><strong>Root SSH权限</strong></td>
                <td>检查复选框 + 期望结果（是/否）</td>
                <td>检查 sshd_config 中 PermitRootLogin 配置值</td>
            </tr>
            <tr>
                <td><strong>系统时间</strong></td>
                <td>检查复选框 + 允许误差（分钟）</td>
                <td>比较服务器 UTC 时间与本地 UTC 时间偏差</td>
            </tr>
            <tr>
                <td><strong>防火墙</strong></td>
                <td>检查复选框 + 期望结果（是/否）</td>
                <td>检测 firewalld/ufw/SELinux 等防火墙状态</td>
            </tr>
            <tr>
                <td><strong>命令回显N</strong></td>
                <td>命令内容 + 期望类型（包含/不包含） + 期望内容</td>
                <td>执行自定义命令，匹配输出是否符合预期</td>
            </tr>
        </table>
    </div>

    <h4>服务器检查配置步骤</h4>
    <ol class="step-list">
        <li>点击菜单栏 <code>添加快捷按钮 -> 服务器检查</code></li>
        <li>在配置对话框中点击 <code>添加服务器列</code>，选择要检查的服务器（可多选）</li>
        <li>在表格中为每台服务器勾选需要执行的检查项</li>
        <li>为各项检查配置期望结果（如系统时间的最大允许误差）</li>
        <li>添加自定义命令回显检查项（可选）：点击表格左侧的添加按钮</li>
        <li>填写按钮名称后点击 <code>生成快捷按钮</code></li>
        <li>点击生成的快捷按钮进入检查面板，将自动开始执行所有检查</li>
        <li>检查结果会逐项实时更新（绿色 ✔️ 通过，红色 ❌ 不通过，⏸️ 跳过）</li>
        <li>可点击 <code>停止检查</code> 中止，或 <code>关闭</code> 窗口（正在运行时有确认提示）</li>
    </ol>

    <h2>❓ 四、常见问题</h2>

    <h3>Q1: SSH 连接失败怎么办？</h3>
    <p>A: 请检查以下几点：</p>
    <ul>
        <li>确认服务器 IP 地址和端口是否正确</li>
        <li>确认用户名和密码是否正确</li>
        <li>确认本地网络可以访问服务器（ping 测试）</li>
        <li>确认服务器已开启 SSH 服务</li>
        <li>确认服务器防火墙已开放 SSH 端口</li>
    </ul>

    <h3>Q2: sudo 切换 root 失败？</h3>
    <p>A: 请确认：</p>
    <ul>
        <li>该用户是否在 sudoers 列表中</li>
        <li>密码是否正确</li>
        <li>服务器是否允许 sudo -i 命令</li>
    </ul>

    <h3>Q3: 文件传输速度慢？</h3>
    <p>A: 文件传输速度受网络带宽影响，大文件建议压缩后传输。</p>

    <h3>Q4: 监控数据保存在哪里？</h3>
    <p>A: 本机监控数据保存在程序运行目录下的 <code>local/OneClick/</code> 文件夹中。远程监控数据保存在服务器的 <code>{文件暂存路径}/OneClick/Monitor/</code> 目录下，可通过控制面板的<code>下载数据</code>按钮下载到本地。</p>

    <h3>Q5: 如何备份配置？</h3>
    <p>A: 点击菜单栏 <code>文件</code> → <code>另存为</code>，选择保存位置即可备份当前配置。配置文件包含服务器列表和所有快捷按钮设置。</p>

    <h3>Q6: 弱网功能无法使用？</h3>
    <p>A: 弱网功能基于 Linux tc 命令，仅限远程 Linux 服务器使用，且需要 root 权限或 sudo 权限。请确认：</p>
    <ul>
        <li>目标服务器为 Linux 系统（CentOS、Ubuntu、RHEL 等）</li>
        <li>当前用户为 root，或在 sudoers 列表中</li>
        <li>服务器已安装 iproute2 / tc 工具</li>
        <li>网卡名称正确（如 eth0、ens33 等）</li>
    </ul>

    <h3>Q7: 弱网开始后 SSH 连接断了怎么办？</h3>
    <p>A: 弱网设置（特别是高延迟、丢包、带宽限制）可能导致当前 SSH 连接卡顿或中断。建议：</p>
    <ul>
        <li>使用另一台机器或带外管理（如 IPMI、KVM）连接服务器</li>
        <li>设置较短的持续时长和间隔时长，确保有规律的网络恢复窗口</li>
        <li>提前配置好停止条件，脚本会在到达持续时长后自动恢复正常网络</li>
        <li>也可通过其他网络路径连接服务器执行 <code>tc qdisc del dev {网卡} root</code> 手动清除规则</li>
    </ul>

    <h3>Q8: 弱网日志保存在哪里？</h3>
    <p>A: 服务器上的日志保存在 <code>{文件暂存路径}/OneClick/WeakNet/OneClickWeakNet.log</code>。点击"查看运行日志"时会自动下载到本地 <code>local/{IP}/WeakNet/</code> 目录下。</p>

    <h3>Q9: Windows 7 无法运行？</h3>
    <p>A: Windows 7 需要安装 <span class="highlight">SP1 服务包</span> 和相关系统补丁后才能正常运行。</p>

    <div class="footer">
        <p>OneClick V2.0 | 一键式服务器运维管理工具</p>
        <p>如有问题，请联系技术支持</p>
    </div>
</body>
</html>'''
