# -*- coding: utf-8 -*-
"""快捷按钮配置的统一规范化工具（单一真相源）。

所有按钮配置在进入内存前（add_button / edit_button）都经过
normalize_button_config 处理：
1. 旧键名迁移：按 RENAMES 把旧键的值搬到新键（仅当新键缺失时）；
2. 缺失补默认：以该指令类型的 schema 为准，缺失的键补默认值；
3. 只保留识别到的键：schema 之外的未知键一律丢弃；
4. 无法识别指令类型的损坏配置原样返回，不丢数据。

以后键名变更时，只需在 RENAMES 加一条映射、在 TYPE_SCHEMAS
更新规范键，老配置加载时即自动迁移，无需逐个编辑按钮。
"""

import copy

from utils.logger import get_logger

logger = get_logger("config_schema")

# SSH 类按钮（发送命令/发送文件/获取文件/资源监控/弱网）共有的键
_SSH_KEYS = {
    'IP': '',
    '用户名': '',
    '密码': '',
    '端口': '22',
}

# 每种指令类型的规范键 → 默认值。键集合即"允许保留的键"，
# 不在此列的键加载时会被丢弃
TYPE_SCHEMAS = {
    '发送命令': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '指令': '',
        '临时文件路径': '',
    },
    '发送命令并接收回显': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '指令': '',
        '临时文件路径': '',
    },
    '发送文件': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '临时文件路径': '',
        '源路径列表': [],
        '服务器路径': '',
    },
    '获取文件': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '临时文件路径': '',
        '源路径列表': [],
        '目的路径': '',
    },
    '复制本地文件': {
        '指令类型': '',
        '指令名称': '',
        '源路径列表': [],
        '目的路径': '',
    },
    '资源监控': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '临时文件路径': '',
        '进程': '',
        '采样频率': '',
        '监控时长': '',
        '监控时长单位': '天',
        '嵌入式': False,
    },
    '弱网': {
        **_SSH_KEYS,
        '指令类型': '',
        '指令名称': '',
        '临时文件路径': '',
        '规则列表': [],
        '循环次数': '0',
        '网卡': '',
    },
    '服务器检查': {
        '指令类型': '',
        '指令名称': '',
        '服务器检查配置': {},
    },
    '记事本': {
        '指令类型': '',
        '指令名称': '',
        '内容': '',
        '窗口宽度': 480,
        '窗口高度': 360,
    },
}

# 旧键 → 新键 迁移映射（全局 + 按类型）
RENAMES_GLOBAL = {
    '文件暂存路径': '临时文件路径',
}
RENAMES_BY_TYPE = {
    '发送文件': {'目的路径': '服务器路径'},
    '获取文件': {'本地路径': '目的路径'},
    '复制本地文件': {'复制到': '目的路径'},
}

# 框架层注入键（分组/位置由主窗口管理），规范化时原样保留
FRAMEWORK_KEYS = ('分组', '位置')

# 点击时必须齐备的键（不可推导、瞎猜会出事的键）。
# SSH 类连接三要素 IP/用户名/密码缺一不可（连接时禁用了 agent/密钥认证，
# 空密码必然认证失败），缺失时不执行，提示用户编辑补全；
# 纯本地类型（复制本地文件/服务器检查/记事本）无必填键
REQUIRED_KEYS = {
    cmd_type: ('IP', '用户名', '密码')
    for cmd_type in ('发送命令', '发送命令并接收回显', '发送文件', '获取文件', '资源监控', '弱网')
}


def normalize_button_config(config):
    """规范化单个快捷按钮的配置字典，返回新字典。

    - 指令类型无法识别时原样返回（不裁剪、不丢数据，仅记日志）；
    - 先迁移旧键名，再按 schema 补默认并剔除未知键；
    - 框架键（分组/位置）原样保留。
    """
    if not isinstance(config, dict):
        return config
    cmd_type = config.get('指令类型', '')
    schema = TYPE_SCHEMAS.get(cmd_type)
    if schema is None:
        logger.warning("快捷按钮配置的指令类型'%s'无法识别，跳过规范化", cmd_type)
        return config

    cfg = dict(config)
    renames = dict(RENAMES_GLOBAL)
    renames.update(RENAMES_BY_TYPE.get(cmd_type, {}))
    for old_key, new_key in renames.items():
        if old_key in cfg:
            if new_key not in cfg:
                cfg[new_key] = cfg[old_key]
            cfg.pop(old_key, None)

    result = {}
    for key, default in schema.items():
        value = cfg.get(key)
        # None / 空字符串 / 纯空白都视为缺失，补默认值
        # （配置文件里常存 "" 而非 null，如手改后端口留空）
        if value is None or (isinstance(value, str) and not value.strip()):
            result[key] = copy.deepcopy(default)
        else:
            result[key] = value
    for key in FRAMEWORK_KEYS:
        if key in cfg:
            result[key] = cfg[key]

    # 可推导键自适应：临时文件路径缺失/为空时按用户名推导家目录
    # （用户名也没有则留空，运行时由 resolve_work_dir 回退 /home）
    if '临时文件路径' in result and not str(result['临时文件路径'] or '').strip():
        username = str(result.get('用户名') or '').strip()
        if username:
            result['临时文件路径'] = f"/home/{username}"
    return result


def find_missing_required(config):
    """返回配置中缺失的必填键列表（点击时拦截用）；全部齐备返回空列表。"""
    if not isinstance(config, dict):
        return []
    cmd_type = config.get('指令类型', '')
    if cmd_type not in TYPE_SCHEMAS:
        return []
    return [key for key in REQUIRED_KEYS.get(cmd_type, ())
            if not str(config.get(key) or '').strip()]
