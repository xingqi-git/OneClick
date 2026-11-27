import time
import os
import re
import socket
import codecs
import stat
import tarfile
import tempfile
from collections import namedtuple
from utils.windows_tools import WindowsTools
from utils.logger import get_logger

logger = get_logger("ssh")

# 远程文件条目（fs_listdir 统一返回结构，字段与 paramiko SFTPAttributes 对齐）
RemoteEntry = namedtuple('RemoteEntry', ['filename', 'st_mode', 'st_size', 'st_mtime',
                                         'owner', 'permission'])


class TransferAborted(Exception):
    """用户主动中止传输（策略层捕获时必须原样上抛，不得触发协议降级）"""
    pass


def _sh_quote(s):
    """shell 单引号包裹，安全包含空格/特殊字符的路径"""
    return "'" + str(s).replace("'", "'\\''") + "'"


class SSHTools(object):
    def __init__(self):
        self.ip = None
        self.port = 22
        self.username = "root"
        self.password = "123456"
        self.ssh = None
        self.channel = None

        self.sudo_ok = False
        self.transfer_stat = 0
        self._last_progress = -1
        self.transport = None
        # 连接期探测一次、本连接内不再变化的结果缓存：
        # _sftp_ok   = 传输协议能力（SFTP 优先 / SCP+exec 降级）
        # sudo_ok    = 提权能力（非 root 时能否 sudo），下载/目录操作按此分叉
        self._sftp_ok = False      # True=后续文件操作优先走 SFTP
        self._sftp_client = None   # SFTP 可用时保持打开的客户端

        self.win_tool = WindowsTools()

    def resolve_work_dir(self, work_dir):
        """校验并规范化服务器临时文件路径（唯一收口点）。

        合法：Linux 绝对路径（'/' 开头，不含反斜杠/盘符），原样返回。
        非法（典型：误填 Windows 路径 'C:\\Users\\...'）：不抛异常，
        回退到登录用户家目录，否则拼接 mkdir 时会被当成相对路径，
        在远端家目录下造出 'C:\\Users\\...' 这样的怪目录。
        空值同样回退家目录。root 的家目录推导统一走 config_schema.derive_home。
        """
        from utils.config_schema import derive_home
        default = derive_home(self.username) or "/home"
        if not work_dir or not isinstance(work_dir, str):
            return default
        path = work_dir.strip()
        # 必须绝对路径；禁止反斜杠（Windows 路径特征）和盘符 C: / D:
        if not path.startswith('/') or '\\' in path or re.match(r'^[A-Za-z]:', path):
            logger.warning(
                "临时文件路径不是合法的 Linux 绝对路径('%s')，回退到 %s",
                work_dir, default)
            return default
        return path.rstrip('/') or '/'

    def connect(self, timeout=10):
        import paramiko
        from scp import SCPClient
        self._paramiko = paramiko
        self._SCPClient = SCPClient
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # allow_agent/look_for_keys 显式关闭：本工具只用密码认证。
            # paramiko 默认会探测 Windows 的 \\.\pipe\openssh-ssh-agent，
            # 部分电脑该管道存在但打开时报 [Errno 22] Invalid argument，
            # 且 paramiko 2.10.4 不捕获该错误，会导致密码认证根本走不到
            self.ssh.connect(self.ip, self.port, self.username, self.password,
                             timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                             allow_agent=False, look_for_keys=False)

            # 打开一个通道用于传输数据
            self.channel = self.ssh.invoke_shell(term='xterm-256color')
            self.channel.resize_pty(width=120, height=40)
            self.channel.settimeout(10)  # 防止卡住
            # 非阻塞通道，在线程里时仍然可以发送数据
            self.channel.setblocking(0)
            logger.info("ssh连接成功")
            self.transport = self.ssh.get_transport()
            self.transport.set_keepalive(5)

            # ---- 传输协议嗅探（连接期一次）：SFTP 优先，不可用则全程走 SCP/exec ----
            # 结果缓存在本连接实例上，后续所有文件操作直接按已知协议执行，零嗅探
            self._sftp_client = None
            self._sftp_ok = False
            try:
                # 嗅探加短超时：防止部分网络环境对 sftp 请求黑洞式挂起
                sock = self.transport.sock
                old_timeout = sock.gettimeout() if sock else None
                if sock is not None:
                    sock.settimeout(5)
                try:
                    self._sftp_client = self.ssh.open_sftp()
                    self._sftp_ok = True
                    logger.info("传输协议嗅探: SFTP 可用")
                finally:
                    if sock is not None and old_timeout is not None:
                        sock.settimeout(old_timeout)
            except Exception as e:
                self._sftp_client = None
                self._sftp_ok = False
                logger.info("传输协议嗅探: SFTP 不可用(%s)，走 SCP", e)

            # ---- sudo 能力探测（连接期一次）：非 root 时验证能否 sudo，结果缓存 ----
            if self.username == 'root':
                self.sudo_ok = True
            else:
                try:
                    stdin, stdout, stderr = self.ssh.exec_command(
                        f"echo {self.password} | sudo -S true")
                    stdout.read()
                    sudo_err = stderr.read().decode('utf-8', 'replace').strip()
                    code = stdout.channel.recv_exit_status()
                    if code == 0:
                        self.sudo_ok = True
                        logger.info("sudo 探测: 当前用户有 sudo 权限")
                    elif code == 127:
                        logger.info("sudo 探测: 服务器无 sudo 命令")
                    else:
                        reason = sudo_err.splitlines()[-1] if sudo_err else f"退出码 {code}"
                        logger.info("sudo 探测: 当前用户无 sudo 权限(%s)", reason)
                except Exception as e:
                    logger.info("sudo 探测异常，按无 sudo 处理: %s", e)

            return True
        except Exception as e:
            logger.error(f"ssh连接失败: {e}")
            return False

    def disconnect(self):
        if self._sftp_client is not None:
            try:
                self._sftp_client.close()
            except Exception:
                pass
            self._sftp_client = None
        self._sftp_ok = False
        if not self.is_connected():
            self.transfer_stat = 0
            self.win_tool.transfer_stat = 0
            logger.info('ssh断开成功')
            return True
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.transfer_stat = 0
        self.win_tool.transfer_stat = 0
        logger.info('ssh断开成功')
        return True

    def is_connected(self):
        """检查SSH连接是否存活
        先快速判断 transport 状态，不存活直接返回 False；
        存活时再用轻量命令探活，避免每次都阻塞。
        """
        if not (self.ssh and self.transport and self.transport.is_active()):
            return False
        # transport 看起来活着，再用一个极轻量命令确认
        try:
            transport = self.ssh.get_transport()
            if transport is None or not transport.is_active():
                return False
            # 用 send_ignore 探活，比 exec_command 轻量得多，不会新建 channel
            transport.send_ignore()
            return True
        except Exception:
            return False

        # return self.channel is not None and self.channel.active and self.ssh is not None

    def purify_output(self, output='', only=True) -> str:
        """将结果格式化，如果only传入True自动剔除首行的命令和最后一行的[root@localhost ~]#"""
        # 1. 移除ANSI转义序列（颜色、格式控制码）
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        output = ansi_escape.sub('', output)
        if not only:
            return output
        # 2. 统一换行符
        output = output.replace('\r\n', '\n').replace('\r', '\n')

        # 剔除第一行（发命令的行）和最后一行（linux身份标识行）
        first_n = output.find('\n')
        if first_n == -1:  # 如果没有换行符，返回空字符串或原字符串
            return ""

        # 截取第一个换行符之后的内容
        after_first = output[first_n + 1:]

        # 找到剩余内容中最后一个换行符的位置
        last_n = after_first.rfind('\n')
        if last_n == -1:  # 如果只剩一个换行符，返回空字符串
            return ""

        # 截取到最后一个换行符之前的内容
        result = after_first[:last_n]
        return result

    def send_command(self, cmd):
        if self.is_connected():
            self.ssh.exec_command(cmd)
            logger.info(f"指令发送成功：{cmd}")
            return True
        else:
            logger.warning("未连接到服务器，请先连接")
            return False

    def send_command_interactive(self, cmd):
        """使用channel发送指令，用于交互式的指令，需要持续接收回显的命令，如top free等"""
        if self.is_connected():
            try:
                if cmd == 'top':
                    self.channel.send(f"{cmd} -b\n")
                elif cmd == '^C':
                    self.channel.send(f"{chr(3)}\n")
                else:
                    self.channel.send(f"{cmd}\n")
                # 按下停止指令时，cmd传递过来的时chr(3)
                if cmd == chr(3):
                    logger.info(f"已发送中止请求ctrl+c，请稍等...")
                else:
                    logger.info(f"指令发送成功：{cmd}")
                    return True
            except Exception as e:
                logger.error(f"指令发送失败：{e}")
                return False
        else:
            logger.warning("未连接到服务器，请先连接")
            return False

    def send_get_output_once(self, cmd, only=True):
        """用于发送一次命令，并接受该次命令的回显，返回回显"""
        if not self.is_connected():
            return False
        self.channel.send('\n')
        time.sleep(0.1)
        # 清空空换行带来的多余输出
        while self.channel.recv_ready():
            self.channel.recv(4096)
            time.sleep(0.05)

        self.channel.send(f'{cmd}\n')
        timeout_count = 0
        out = ""
        while True:
            if self.channel.recv_ready():
                receive_count = 0
                while True:
                    if self.channel.recv_ready():
                        out += self.channel.recv(4096).decode().strip()
                        receive_count = 0
                        time.sleep(0.05)
                    else:
                        receive_count += 1
                        if receive_count > 4:  # 已经开始收数据了，0.2s没新数据直接返回
                            timeout_count = 50
                            break
            else:
                timeout_count += 1
                # 无数据超时退出
                if timeout_count > 50:
                    break
            time.sleep(0.1)
        out = self.purify_output(out, only)
        return out

    def get_output_continue(self, echo_signal=None, timeout=3, raw=False):
        """用于持续接收类似与top这样的命令的回显
        raw=True 时不做任何纯化，直接发原始字节字符串给 echo_signal（给终端模拟器用）
        """
        if not self.is_connected():
            logger.warning("未连接到服务器，请先连接。")
            return False
        try:
            CHECK_INTERVAL = 0.5  # 阻塞读超时=空闲期健康检查周期
            idle = 0.0            # 连续无数据累计时长
            logger.debug("回显接收循环开始: raw=%s, timeout=%s", raw, timeout)
            # 阻塞式读取：数据到达即刻返回（按键回显零等待，替代旧的
            # sleep(0.1)+recv_ready 轮询，旧方案平均引入 50ms、最坏 100ms 延迟）
            self.channel.settimeout(CHECK_INTERVAL)
            # 增量 UTF-8 解码器：TCP 段可能在多字节字符中间截断，
            # 逐包独立 decode 会产生替换符乱码；增量解码保留残缺尾部到下一包
            utf8_decoder = codecs.getincrementaldecoder('utf-8')('replace')
            while True:
                if self.channel is None:
                    logger.debug("channel 已置空，回显接收循环退出")
                    break
                # 用 transport.is_active() 快速判断，避免每次循环都 exec_command 阻塞
                if not (self.transport and self.transport.is_active()):
                    logger.debug("transport 失效/断开，回显接收循环退出")
                    break
                # 通道级断开检测：服务器空闲超时踢人、shell 退出会直接关闭通道。
                # 不能只靠 recv_ready——纯 EOF 不带数据时 recv_ready 永远是 False，
                # 而 timeout=inf 又让超时分支失效，会导致死循环、连接状态永不更新
                if self.channel.closed or not self.channel.active:
                    logger.info("通道已被关闭（服务器空闲超时/主动断开），回显接收循环退出")
                    break
                try:
                    try:
                        output_bytes = self.channel.recv(65536)  # 阻塞至多 CHECK_INTERVAL 秒
                    except socket.timeout:
                        # 空闲期：无数据，做周期性健康检查
                        output_bytes = b''
                    if output_bytes:
                        # 数据到达：把缓冲区一次抽干再合并上屏，
                        # 大突发（cat 大文件等）不被 4KB/0.1s 的旧节流拖慢
                        chunks = [output_bytes]
                        while self.channel.recv_ready():
                            chunks.append(self.channel.recv(65536))
                        payload = b''.join(chunks)
                        if not payload:
                            logger.debug("收到 EOF，回显接收循环退出")
                            break
                        if raw:
                            # 原始模式：直接发字符串（带 \r\n 和 ANSI），给 pyte 处理
                            output = utf8_decoder.decode(payload)
                            if echo_signal is not None:
                                echo_signal.emit(output)
                        else:
                            output = payload.decode().strip()
                            output = self.purify_output(output, False)

                            if echo_signal is not None:
                                echo_signal.emit(output)

                        idle = 0.0  # 有数据，重置空闲计时
                    else:
                        # 无数据可读但对端已发 EOF：纯 EOF 场景在这里退出，
                        # 有缓冲数据时先读完（recv_ready 为 True）再走到这
                        if self.channel.eof_received:
                            logger.info("收到通道 EOF（服务器空闲超时/主动断开），回显接收循环退出")
                            break
                        idle += CHECK_INTERVAL
                        # 无数据超时退出（保留历史行为：实际等待 timeout×3 秒）
                        if timeout is not None and idle > timeout * 3:
                            logger.info(f"超时({timeout}秒)无内容，回显退出")
                            break
                except EOFError:
                    # 对端关闭写方向且缓冲已空：阻塞 recv 直接抛 EOFError
                    logger.info("收到通道 EOF（服务器空闲超时/主动断开），回显接收循环退出")
                    break
                except (AttributeError, OSError) as e:
                    # 断开操作把 channel 设为 None 时，直接退出
                    logger.debug("接收中 channel 失效，回显接收循环退出: %s", e)
                    break
            logger.debug("回显接收循环结束")
            return True
        except Exception as e:
            logger.error(f"执行命令时出错: {e}")
            return False

    def get_pathtree_info(self, remote_path, path_only=False, recursive=False, tree_list=None):
        """
        获取远程路径的文件/目录信息（不依赖sudo_ok，全程使用sudo指令）
        参数：
            remote_path: 远程路径
            path_only: 是否只获取路径信息
            recursive: 是否递归获取子目录
            tree_list: 用于递归存储路径信息的列表
        返回：
            包含路径信息的列表，每个元素是字典：
                {'path': 完整路径, 'name': 文件名/目录名, 'mtime': 修改时间, 'is_dir': 是否是目录}
        """
        if not self.is_connected():
            return []
        if tree_list is None:
            tree_list = []
        # 路径标准化
        remote_path = remote_path.replace('\\', '/').rstrip('/')

        # 构造sudo命令（通过标准输入传递密码）
        def exec_sudo_cmd(cmd):
            if self.username != 'root':
                full_cmd = f"echo {self.password} | sudo -S {cmd}"
            else:
                full_cmd = f"{cmd}"
            stdin, stdout, stderr = self.ssh.exec_command(full_cmd)
            stdout_content = stdout.read().decode('utf-8').strip()
            stderr_content = stderr.read().decode('utf-8').strip()

            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                logger.error(f"执行sudo命令失败 [{cmd}]: {stderr_content}")
                return None

            # --- 清洗 ---
            lines = stdout_content.rstrip('\n').split('\n')
            # 从后往前检查，移除所有已知的sudo干扰行
            sudo_noise = {"验证成功", "Authentication successful", "Sorry, try again"}
            while lines and lines[-1].strip() in sudo_noise:
                lines.pop()

            # 重新拼接回干净的输出
            cleaned_output = '\n'.join(lines).strip()
            return cleaned_output if cleaned_output else None

        # 1. 获取当前路径的基础信息（stat命令）
        stat_cmd = f'stat -c "%F %Y" "{remote_path}"'
        stat_output = exec_sudo_cmd(stat_cmd)
        if stat_output is None:
            # 执行失败：密码错、无权限、命令错误
            logger.error(f"获取路径信息失败：命令执行失败")
            return []

        if not stat_output:
            # stat执行成功，但输出为空 = 路径不存在
            logger.warning(f"路径不存在：{remote_path}")
            return []
        # 把输出按空格切开，例如：
        # ['directory', '1739999999']
        stat_parts = stat_output.split(" ")
        if len(stat_parts) < 2:
            return []

        # 解析基础信息
        path_dict = {}
        path_dict['path'] = remote_path
        path_dict['name'] = os.path.basename(remote_path)
        path_dict['mtime'] = stat_parts[-1]
        path_dict['is_dir'] = True if 'directory' in stat_parts[0] or '目录' in stat_parts[0] else False

        tree_list.append(path_dict)

        # 2. 如果是目录，处理子项
        if path_dict['is_dir']:
            # 获取目录下的子项列表
            ls_cmd = f'ls -1 "{remote_path}"'
            ls_output = exec_sudo_cmd(ls_cmd)
            if ls_output:
                children = ls_output.split("\n")
                for child_name in children:
                    if not child_name:
                        continue
                    child_path = f"{remote_path}/{child_name}"

                    # 如果只需要路径信息，则不再获取子项的stat信息
                    if path_only:
                        child_dict = {
                            'path': child_path,
                            'name': child_name,
                            'mtime': 'unknown',
                            'is_dir': 'unknown'
                        }
                        if recursive:
                            if self.transfer_stat == 0:
                                return []
                            self.get_pathtree_info(child_path, path_only=True, recursive=True, tree_list=tree_list)
                        else:
                            tree_list.append(child_dict)
                            continue

                    # 获取子项的stat信息
                    child_stat_cmd = f'stat -c "%F %Y" "{child_path}"'
                    child_stat_output = exec_sudo_cmd(child_stat_cmd)
                    if child_stat_output is None:
                        continue

                    if not child_stat_output:
                        continue

                    child_stat_parts = child_stat_output.split(" ")
                    if len(child_stat_parts) < 2:
                        continue

                    child_dict = {
                        'path': child_path,
                        'name': child_name,
                        'mtime': child_stat_parts[-1],
                        'is_dir': True if 'directory' in child_stat_parts[0] else False
                    }

                    # 递归处理子目录（如果需要）
                    if recursive:
                        if self.transfer_stat == 0:
                            return []
                        self.get_pathtree_info(child_path, path_only=False, recursive=True, tree_list=tree_list)
                    else:
                        tree_list.append(child_dict)

        return tree_list

    def _match_filename(self, name, include_keywords, include_logic, exclude_keywords, exclude_logic):
        """
        判断文件名是否符合包含/不包含筛选条件
        - include_keywords: 包含关键词列表
        - include_logic: '和' 或 '或'
        - exclude_keywords: 不包含关键词列表
        - exclude_logic: '和' 或 '或'
        - 包含组 和 不包含组 之间是"与"关系
        """
        # 包含判断
        if include_keywords:
            if include_logic == '和':
                include_ok = all(kw in name for kw in include_keywords)
            else:  # 或
                include_ok = any(kw in name for kw in include_keywords)
        else:
            include_ok = True

        # 不包含判断
        if exclude_keywords:
            if exclude_logic == '和':
                # 所有关键词都不包含才算通过
                exclude_ok = all(kw not in name for kw in exclude_keywords)
            else:  # 或
                # 任意一个关键词不包含就算通过？不对，应该是"任意一个包含就排除"
                # "名称不包含 A 或 B" = 不含A 或者 不含B = 几乎总是成立，没意义
                # 更合理的理解：不包含组的逻辑是"命中排除规则"的条件
                # 逻辑'和' = 所有关键词都包含才排除；逻辑'或' = 任意一个包含就排除
                # 然后 exclude_ok = 不命中排除规则
                if exclude_logic == '和':
                    # 所有关键词都包含 → 命中排除 → 不通过
                    hit_exclude = all(kw in name for kw in exclude_keywords)
                else:  # 或
                    hit_exclude = any(kw in name for kw in exclude_keywords)
                exclude_ok = not hit_exclude
        else:
            exclude_ok = True

        return include_ok and exclude_ok

    def _filter_source_path(self, source_path, mtime_seconds, include_keywords, include_logic,
                            exclude_keywords, exclude_logic, time_now):
        """
        对单个源路径进行筛选，返回 (dir_list, file_list)
        规则：
        - 如果源路径是文件，不参与筛选，直接加入 file_list
        - 如果源路径是文件夹，文件夹本身不参与筛选（总是加入 dir_list），
          其下的子目录和子文件才参与筛选
        """
        dir_list = []
        file_list = []

        source_path = source_path.replace('\\', '/').rstrip('/')
        if not os.path.exists(source_path):
            return dir_list, file_list

        if os.path.isfile(source_path):
            # 源路径是文件，不筛选，直接传
            file_list.append(source_path)
            return dir_list, file_list

        # 源路径是文件夹，文件夹本身直接加入目录列表
        dir_list.append(source_path)

        # 遍历子目录和子文件，应用筛选
        for root, dirs, files in os.walk(source_path):
            if self.transfer_stat == 0:
                return dir_list, file_list
            for name in dirs + files:
                full_path = os.path.join(root, name).replace('\\', '/')
                is_dir = os.path.isdir(full_path)
                # 修改时间筛选
                try:
                    mtime_val = os.path.getmtime(full_path)
                except OSError:
                    continue
                interval = time_now - mtime_val
                if interval > mtime_seconds:
                    continue
                # 文件名筛选
                if not self._match_filename(name, include_keywords, include_logic,
                                            exclude_keywords, exclude_logic):
                    continue
                if is_dir:
                    dir_list.append(full_path)
                else:
                    file_list.append(full_path)

        return dir_list, file_list

    # ===================== 统一传输策略层 =====================
    # 连接期嗅探协议（SFTP 优先 / SCP+exec 降级，见 connect），缓存于连接实例；
    # 所有文件操作通过本层入口执行，内部按已知协议分派，运行期通道级失败自动
    # 永久降级（文件级错误如"不存在/无权限"不降级），外部调用方零感知。

    def _sftp_failed(self, e):
        """判断 SFTP 异常是否为通道级失败（需要降级）：
        - 带 errno 的 IOError 是文件级错误（不存在/无权限），不降级
        - 用户中止（TransferAborted）在入口处已单独拦截，不会走到这里
        - 其余（SSHException/EOFError/Socket closed 等）视为通道失败 → 降级
        """
        if isinstance(e, IOError) and getattr(e, 'errno', None) is not None:
            return False
        return True

    def _mark_sftp_down(self):
        """永久降级本连接的传输协议：后续操作全部走 SCP/exec，不再尝试 SFTP"""
        self._sftp_ok = False
        if self._sftp_client is not None:
            try:
                self._sftp_client.close()
            except Exception:
                pass
            self._sftp_client = None
        logger.debug("本连接传输协议已降级为 SCP/exec")

    def _exec_read(self, cmd):
        """exec 通道执行命令，返回 (exit_status, stdout文本)"""
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        out = stdout.read().decode('utf-8', 'replace')
        stderr.read()
        try:
            rc = stdout.channel.recv_exit_status()
        except Exception:
            rc = -1
        return rc, out

    def put_file(self, local_path, remote_path, progress=None):
        """统一单文件上传入口。
        progress(name, size, sent)：可选回调，与 SCPClient 的 progress 签名一致。
        """
        if self._sftp_ok:
            try:
                self._sftp_client.put(
                    local_path, remote_path,
                    callback=lambda sent, total: progress(
                        os.path.basename(local_path), total, sent) if progress else None)
                return
            except TransferAborted:
                raise
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 上传失败(%s)，降级为 SCP 重试本次上传", e)
                self._mark_sftp_down()
        with self._SCPClient(self.transport,
                             progress=(lambda n, s, se: progress(n, s, se)) if progress else None) as client:
            self._last_progress = -1
            client.put(local_path, remote_path)

    def get_file(self, remote_path, local_path, progress=None):
        """统一单文件下载入口。progress(name, size, sent) 可选回调。"""
        if self._sftp_ok:
            try:
                self._sftp_client.get(
                    remote_path, local_path,
                    callback=lambda sent, total: progress(
                        os.path.basename(remote_path), total, sent) if progress else None)
                return
            except TransferAborted:
                raise
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 下载失败(%s)，降级为 SCP 重试本次下载", e)
                self._mark_sftp_down()
        with self._SCPClient(self.transport,
                             progress=(lambda n, s, se: progress(n, s, se)) if progress else None) as client:
            self._last_progress = -1
            client.get(remote_path, local_path)

    def get_dir(self, remote_dir, local_dir, progress=None):
        """统一递归下载入口：远端目录整体下载到 local_dir 下（以其原目录名落盘，
        与 SCPClient.get(recursive=True) 行为一致）。
        progress(name, size, sent)：逐文件的字节级回调，可选。
        """
        if self._sftp_ok:
            try:
                local_target = os.path.join(
                    local_dir, os.path.basename(remote_dir.rstrip('/')))
                self._sftp_get_recursive(remote_dir, local_target, progress)
                return
            except TransferAborted:
                raise
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 递归下载失败(%s)，降级为 SCP 重试", e)
                self._mark_sftp_down()
        with self._SCPClient(self.transport,
                             progress=(lambda n, s, se: progress(n, s, se)) if progress else None) as client:
            self._last_progress = -1
            client.get(remote_dir, local_dir, recursive=True)

    def _sftp_get_recursive(self, remote_dir, local_target, progress):
        """SFTP 后端的递归下载"""
        os.makedirs(local_target, exist_ok=True)
        entries = self._sftp_client.listdir_attr(remote_dir)
        for attr in entries:
            rpath = remote_dir.rstrip('/') + '/' + attr.filename
            lpath = os.path.join(local_target, attr.filename)
            if stat.S_ISDIR(attr.st_mode):
                self._sftp_get_recursive(rpath, lpath, progress)
            else:
                callback = None
                if progress:
                    callback = (lambda sent, total, _n=attr.filename, _s=attr.st_size:
                                progress(_n, _s, sent))
                self._sftp_client.get(rpath, lpath, callback=callback)

    # ---- 远程文件系统操作（文件浏览器目录管理用） ----

    def fs_listdir(self, path):
        """列目录：返回条目列表，条目含 filename/st_mode/st_size/st_mtime/owner/permission"""
        if self._sftp_ok:
            try:
                return self._build_entries_from_attrs(
                    self._sftp_client.listdir_attr(path))
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 列目录失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        return self._exec_listdir(path)

    def _build_entries_from_attrs(self, attrs):
        """SFTPAttributes 列表 → RemoteEntry 列表。
        权限串由 st_mode 计算；拥有者名由 uid 经一次 exec 批量解析（失败回退数字 uid）。"""
        owner_map = {}
        uids = sorted({a.st_uid for a in attrs if getattr(a, 'st_uid', None) is not None})
        if uids:
            try:
                cmd = ';'.join(f"id -un {u} 2>/dev/null || echo {u}" for u in uids)
                rc, out = self._exec_read(cmd)
                for u, line in zip(uids, out.strip().split('\n')):
                    name = line.strip()
                    if name:
                        owner_map[u] = name
            except Exception:
                pass  # 解析失败统一回退数字 uid
        entries = []
        for a in attrs:
            try:
                perm = stat.filemode(a.st_mode or 0)
            except Exception:
                perm = ''
            owner = owner_map.get(getattr(a, 'st_uid', None), str(getattr(a, 'st_uid', '')))
            entries.append(RemoteEntry(a.filename, a.st_mode, a.st_size or 0,
                                       a.st_mtime or 0.0, owner, perm))
        return entries

    def _exec_listdir(self, path):
        """exec 后端列目录：find -printf 一次输出 类型/大小/时间戳/拥有者/权限/文件名"""
        rc, out = self._exec_read(
            f"find {_sh_quote(path)} -maxdepth 1 -mindepth 1 "
            f"-printf '%y\\t%s\\t%T@\\t%u\\t%M\\t%f\\n'")
        entries = []
        for line in out.split('\n'):
            parts = line.split('\t', 5)
            if len(parts) != 6:
                continue
            ftype, size, mtime, owner, perm, name = parts
            mode = stat.S_IFDIR if ftype == 'd' else stat.S_IFREG
            try:
                size_v = int(size)
            except ValueError:
                size_v = 0
            try:
                mtime_v = float(mtime)
            except ValueError:
                mtime_v = 0.0
            entries.append(RemoteEntry(name, mode, size_v, mtime_v, owner, perm))
        if rc != 0 and not entries:
            raise IOError(f"无法读取目录内容: {path}")
        return entries

    def fs_normalize(self, path):
        """路径规范化（绝对路径展开，与 SFTP normalize 对齐）"""
        if self._sftp_ok:
            try:
                return self._sftp_client.normalize(path)
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 规范化路径失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"cd {_sh_quote(path)} >/dev/null 2>&1 && pwd")
        if rc == 0 and out.strip():
            return out.strip().split('\n')[-1]
        return path

    def fs_home(self):
        """当前用户远程家目录"""
        if self._sftp_ok:
            try:
                return self._sftp_client.normalize('.')
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 获取家目录失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read("echo $HOME")
        return out.strip() or '/'

    def fs_exists(self, path):
        """远程路径是否存在"""
        if self._sftp_ok:
            try:
                self._sftp_client.stat(path)
                return True
            except IOError as e:
                if getattr(e, 'errno', None) is not None:
                    return False  # 文件不存在等文件级错误
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP stat失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP stat失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"test -e {_sh_quote(path)} && echo Y || echo N")
        return out.strip() == 'Y'

    def fs_rename(self, old_path, new_path):
        if self._sftp_ok:
            try:
                self._sftp_client.rename(old_path, new_path)
                return
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 重命名失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(
            f"mv -f {_sh_quote(old_path)} {_sh_quote(new_path)} && echo OK")
        if rc != 0 or 'OK' not in out:
            raise IOError(f"重命名失败: {old_path} -> {new_path}")

    def fs_remove(self, path):
        if self._sftp_ok:
            try:
                self._sftp_client.remove(path)
                return
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 删除失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"rm -f {_sh_quote(path)} && echo OK")
        if rc != 0 or 'OK' not in out:
            raise IOError(f"删除失败: {path}")

    def fs_mkdir(self, path):
        if self._sftp_ok:
            try:
                self._sftp_client.mkdir(path)
                return
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 新建目录失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"mkdir {_sh_quote(path)} && echo OK")
        if rc != 0 or 'OK' not in out:
            raise IOError(f"新建目录失败: {path}")

    def fs_touch(self, path):
        if self._sftp_ok:
            try:
                with self._sftp_client.open(path, 'w'):
                    pass
                return
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 新建文件失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"touch {_sh_quote(path)} && echo OK")
        if rc != 0 or 'OK' not in out:
            raise IOError(f"新建文件失败: {path}")

    def fs_dir_size(self, path):
        """递归计算远程目录总大小（字节）。元数据不提供目录总大小，
        需要远端整树遍历（du），代价大——仅供右键"计算大小"按需调用。"""
        rc, out = self._exec_read(f"du -sb {_sh_quote(path)} 2>/dev/null")
        line = out.strip().split('\n')[0] if out.strip() else ''
        if '\t' in line and line.split('\t')[0].isdigit():
            return int(line.split('\t')[0])
        raise IOError(f"无法计算大小: {path}")

    def fs_rmtree(self, path):
        """递归删除远程目录（含全部隐藏文件）"""
        if self._sftp_ok:
            try:
                self._sftp_rmtree(path)
                return
            except Exception as e:
                if not self._sftp_failed(e):
                    raise
                logger.warning("SFTP 递归删除失败(%s)，降级为 exec", e)
                self._mark_sftp_down()
        rc, out = self._exec_read(f"rm -rf {_sh_quote(path)} && echo OK")
        if rc != 0 or 'OK' not in out:
            raise IOError(f"递归删除失败: {path}")

    def _sftp_rmtree(self, remote_dir):
        """SFTP 后端递归删除"""
        contents = self._sftp_client.listdir_attr(remote_dir)
        for attr in contents:
            child = remote_dir.rstrip('/') + '/' + attr.filename
            if stat.S_ISDIR(attr.st_mode):
                self._sftp_rmtree(child)
            else:
                self._sftp_client.remove(child)
        self._sftp_client.rmdir(remote_dir)

    def upload_single_file(self, local_path, remote_path):
        """
        轻量单文件上传（双击打开的远程文件保存后回传覆盖）
        走统一传输策略层（SFTP 优先 / SCP 降级），协议由连接期嗅探决定。
        注意：要求登录用户对远端文件有写权限（不做 sudo 中转）
        """
        if not self.is_connected():
            logger.error("upload_single_file: SSH 未连接")
            return False
        # 呈现层路径统一正斜杠（正斜杠路径 Windows API 全兼容）
        local_path = str(local_path).replace('\\', '/')
        try:
            self.put_file(local_path, remote_path)
            logger.info(f"单文件回传成功 [{local_path} -> {remote_path}]")
            return True
        except Exception as e:
            logger.error(f"单文件回传失败 [{local_path} -> {remote_path}]: {e}")
            return False

    def send_files(self, source_items, remote_path, work_dir=None, progress_cb=None):
        """
        SSH上传文件（支持多源路径，每条独立筛选）
        流程：本地筛选 -> 复制到临时目录 -> 打包 -> SCP上传 -> 服务器端解包 -> 移动到目标目录 -> 清理临时文件
        参数：
            source_items: 源路径列表，每项为 dict：
                {
                    '路径': '本地路径',
                    '修改时间': '全部'/'最近30分钟'/'最近1小时'/'最近2小时',
                    '名称包含': {'关键词': [], '逻辑': '和'/'或'},
                    '名称不包含': {'关键词': [], '逻辑': '和'/'或'}
                }
            remote_path: 远程目标路径，只能是文件夹
            work_dir: 服务器端临时目录所在路径，默认为 /home/{username}
            progress_cb: 可选的进度回调函数 progress_cb(phase, current, total, extra)
                phase: 'find' | 'upload' | 'move'
                find: current=0, total=文件数, extra=描述
                upload: current=已传字节, total=总字节, extra=cur_name|cur_size|cur_sent|file_idx|total_files
                move: current=已移动文件数, total=总文件数, extra=描述
        返回：
            成功返回True，失败返回False
        中断支持：
            self.transfer_stat = 0 时立即中止传输并清理临时文件
        """
        if not self.is_connected():
            logger.warning("未连接到服务器，请先连接")
            return False

        remote_path = remote_path.replace('\\', '/').rstrip('/')

        # 修改时间映射（秒）
        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200,
            "最近1天": 86400,
            "最近1月": 2592000,
            "最近1年": 31536000
        }

        # 校验所有源路径是否存在
        for item in source_items:
            path = item['路径'].replace('\\', '/').rstrip('/')
            if not os.path.exists(path):
                logger.error(f"上传失败，本地路径不存在: {path}")
                return False

        # 检查远程目标路径
        if self.username != 'root':
            check_remote_cmd = f"echo {self.password} | sudo -S bash -c 'test -d \"{remote_path}\" && echo exists || echo not exists'"
        else:
            check_remote_cmd = f"bash -c 'test -d \"{remote_path}\" && echo exists || echo not exists'"
        stdin, stdout, stderr = self.ssh.exec_command(check_remote_cmd)
        dir_check_result = stdout.read().decode('utf-8').strip()
        stderr.read()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0 or 'not exists' in dir_check_result:
            logger.error(f"上传失败，远程目标路径不存在或不是文件夹: {remote_path}")
            return False

        # 标记传输状态为进行中
        self.transfer_stat = 1

        logger.debug("开始查找符合条件的文件...")
        time_now = time.time()
        # 生成毫秒级本地时间戳，用于临时目录命名，避免重名
        local_timestamp_ms = f"{int(time_now * 1000)}"

        # 多源路径合并后的文件/目录列表，每项带源路径信息用于计算相对路径
        all_file_list = []  # [(full_path, source_root)]
        all_dir_list = []   # [(full_path, source_root)]

        for item in source_items:
            src_path = item['路径'].replace('\\', '/').rstrip('/')
            mtime_str = item.get('修改时间', '全部')
            mtime_sec = mtime_dic.get(mtime_str, float('inf'))
            inc = item.get('名称包含', {})
            inc_kw = inc.get('关键词', []) if isinstance(inc, dict) else ([inc] if inc else [])
            inc_logic = inc.get('逻辑', '或') if isinstance(inc, dict) else '或'
            exc = item.get('名称不包含', {})
            exc_kw = exc.get('关键词', []) if isinstance(exc, dict) else []
            exc_logic = exc.get('逻辑', '和') if isinstance(exc, dict) else '和'

            dirs, files = self._filter_source_path(
                src_path, mtime_sec, inc_kw, inc_logic, exc_kw, exc_logic, time_now
            )
            for d in dirs:
                all_dir_list.append((d, src_path))
            for f in files:
                all_file_list.append((f, src_path))

            if self.transfer_stat == 0:
                logger.warning('上传被中止！')
                return False

        # 没有符合条件的项，直接返回
        if not all_dir_list and not all_file_list:
            logger.info(f"上传完成，未上传任何文件，待上传路径无符合条件的项")
            self.transfer_stat = 0
            return True

        logger.debug(f"找到{len(all_dir_list)}个目录, {len(all_file_list)}个文件")
        if progress_cb:
            progress_cb('find', 0, len(all_file_list), f'找到{len(all_file_list)}个文件')

        # 计算总大小（用于总进度）
        total_size = 0
        for f_path, _ in all_file_list:
            try:
                total_size += os.path.getsize(f_path)
            except OSError:
                pass

        # 构造服务器临时目录
        # 校验/规范化临时根目录：非法（如 Windows 路径）回退家目录，
        # 保证拼出的一定是绝对路径，不会在远端造出相对路径怪目录
        base_dir = self.resolve_work_dir(work_dir)
        temp_remote_dir = f"{base_dir}/OneClick_temp{local_timestamp_ms}"

        # 收集所有需要创建的目录
        all_dirs = set()
        for d, src_root in all_dir_list:
            # 相对路径 = 去掉源路径父目录后的部分
            src_parent = os.path.dirname(src_root)
            rel_path = d.replace(src_parent, '', 1).lstrip('/')
            dst_dir = f"{temp_remote_dir}/{rel_path}"
            all_dirs.add(dst_dir)

        for f, src_root in all_file_list:
            src_parent = os.path.dirname(src_root)
            rel_path = f.replace(src_parent, '', 1).lstrip('/')
            dst_dir = os.path.dirname(f"{temp_remote_dir}/{rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序，优化 mkdir -p 调用
        sorted_dirs = sorted(all_dirs, key=lambda x: len(x), reverse=True)
        created_dirs = set()

        logger.debug("开始创建服务器临时目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                logger.warning('上传被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                self.transfer_stat = 0
                return False

            need_create = True
            for created in created_dirs:
                if created.startswith(dst_dir + '/'):
                    need_create = False
                    break

            if need_create:
                if self.username != 'root':
                    mkdir_cmd = f"echo {self.password} | sudo -S mkdir -p \"{dst_dir}\""
                else:
                    mkdir_cmd = f"mkdir -p \"{dst_dir}\""
                stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
                stdout.read()
                mkdir_err = stderr.read().decode('utf-8').strip()
                exit_status = stdout.channel.recv_exit_status()
                if exit_status != 0:
                    logger.error(f"创建目录失败: {mkdir_err}")
                    # 清理本次已创建的部分临时目录，避免残留 OneClick_temp* 目录
                    try:
                        rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                        stdout.read()
                        stderr.read()
                    except Exception:
                        pass
                    return False
                created_dirs.add(dst_dir)

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_dir}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        # 所有目录创建完成，开始上传文件
        file_count = len(all_file_list)
        logger.debug(f"开始上传文件到服务器临时目录，共{file_count}个文件")

        up_count = 0
        failed_files = []
        _upload_state = {'accumulated': 0, 'cur_index': 0, 'last_name': '', 'last_cb_pct': -1}

        def _scp_upload_progress(name, size, sent):
            """SCP上传进度回调，维护累计字节数并调用progress_cb（节流）"""
            if progress_cb is None:
                return
            name_str = name.decode() if isinstance(name, bytes) else name
            file_changed = False
            if name_str != _upload_state['last_name']:
                if _upload_state['last_name']:
                    try:
                        prev_size = os.path.getsize(all_file_list[_upload_state['cur_index']][0])
                        _upload_state['accumulated'] += prev_size
                    except (OSError, IndexError):
                        pass
                _upload_state['cur_index'] = up_count - 1
                _upload_state['last_name'] = name_str
                file_changed = True
            total_sent = _upload_state['accumulated'] + sent
            cur_pct = int(total_sent * 100 / total_size) if total_size > 0 else 0
            if file_changed or cur_pct != _upload_state['last_cb_pct']:
                _upload_state['last_cb_pct'] = cur_pct
                extra = f"{name_str}|{size}|{sent}|{up_count}|{file_count}"
                progress_cb('upload', total_sent, total_size, extra)

        for f_path, src_root in all_file_list:
            if self.transfer_stat == 0:
                logger.warning('上传被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                self.transfer_stat = 0
                return False

            up_count += 1
            src_parent = os.path.dirname(src_root)
            rel_path = f_path.replace(src_parent, '', 1).lstrip('/')
            dst_path = f"{temp_remote_dir}/{rel_path}"

            try:
                file_size = os.path.getsize(f_path)
                if file_size < 100 * 1024 * 1024:
                    if progress_cb and file_count <= 10:
                        self.put_file(f_path, dst_path,
                                      progress=lambda n, s, se, fp=f_path: _scp_upload_progress(os.path.basename(fp), s, se))
                    else:
                        self.put_file(f_path, dst_path)
                    if progress_cb and file_count > 10:
                        _upload_state['accumulated'] += file_size
                        extra = f"{os.path.basename(f_path)}|{file_size}|{file_size}|{up_count}|{file_count}"
                        progress_cb('upload', _upload_state['accumulated'], total_size, extra)
                else:
                    logger.debug(f"大文件上传: {file_size} 字节")
                    if self.transfer_stat == 0:
                        logger.warning("上传被中止")
                        rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                        stdout.read()
                        stderr.read()
                        self.transfer_stat = 0
                        return False
                    self._last_progress = -1
                    self.put_file(f_path, dst_path,
                                  progress=lambda n, s, se, fp=f_path: _scp_upload_progress(os.path.basename(fp), s, se))
                logger.debug(f"已上传到临时目录 {up_count}/{file_count}: {f_path} -> {dst_path}")
            except Exception as e:
                err_msg = str(e)
                real_failed = True
                if "No response from server" in err_msg:
                    try:
                        check_cmd = f"test -f '{dst_path}' && echo EXISTS"
                        _, check_stdout, _ = self.ssh.exec_command(check_cmd)
                        check_result = check_stdout.read().decode('utf-8').strip()
                        if check_result == 'EXISTS':
                            real_failed = False
                    except Exception:
                        pass
                if real_failed:
                    logger.error(f"上传到临时目录失败 {up_count}/{file_count}: {f_path} -> {dst_path},原因: {e}")
                    failed_files.append({"文件": f_path, "原因": err_msg})

        # 打印上传失败汇总
        if failed_files:
            fail_lines = [f"上传失败{len(failed_files)}个文件："]
            for idx, f_item in enumerate(failed_files, 1):
                fail_lines.append(f"  {idx}. {f_item['文件']} - {f_item['原因']}")
            logger.info("\n".join(fail_lines))

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_dir}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        # 移动文件到目标目录：一次性 cp -a，更快
        logger.debug("上传完成，开始移动文件到目标目录...")
        if progress_cb:
            progress_cb('move', 0, 0, '移动文件到目标目录...')

        if self.username != 'root':
            mv_cmd = f"echo {self.password} | sudo -S cp -a \"{temp_remote_dir}/.\" \"{remote_path}/\""
        else:
            mv_cmd = f"cp -a \"{temp_remote_dir}/.\" \"{remote_path}/\""

        stdin, stdout, stderr = self.ssh.exec_command(mv_cmd)
        stdout.read()
        mv_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            logger.error(f"移动文件失败: {mv_err}")
            rm_cmd = f"rm -rf \"{temp_remote_dir}\""
            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
            stdout.read()
            stderr.read()
            self.transfer_stat = 0
            return False

        # 清理临时目录
        rm_cmd = f"rm -rf \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
        stdout.read()
        stderr.read()
        logger.debug("临时目录已删除")

        logger.debug(f"上传完毕！文件已保存到: {remote_path}")
        self.transfer_stat = 0
        return True

    def _filter_remote_source(self, remote_path, mtime_seconds, include_keywords, include_logic,
                              exclude_keywords, exclude_logic, server_now, sudo_prefix):
        """
        对单个远程源路径进行筛选，返回 (dir_list, file_list)
        规则：
        - 如果源路径是文件，不参与筛选，直接加入 file_list
        - 如果源路径是文件夹，文件夹本身不参与筛选（总是加入 dir_list），
          其下的子目录和子文件才参与筛选
        - 服务器端先用 find + mmin + 第一个关键词粗筛，Python端再精细过滤名称
        """
        dir_list = []
        file_list = []

        remote_path = remote_path.replace('\\', '/').rstrip('/')

        # 判断源路径类型
        if self.username != 'root':
            check_cmd = f"{sudo_prefix}bash -c 'test -f \"{remote_path}\" && echo file || (test -d \"{remote_path}\" && echo dir || echo none)'"
        else:
            check_cmd = f"bash -c 'test -f \"{remote_path}\" && echo file || (test -d \"{remote_path}\" && echo dir || echo none)'"
        stdin, stdout, stderr = self.ssh.exec_command(check_cmd)
        check_result = stdout.read().decode('utf-8').strip()
        stderr.read()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0 or check_result == 'none':
            return dir_list, file_list

        if check_result == 'file':
            # 源路径是文件，不筛选，直接传
            file_list.append(remote_path)
            return dir_list, file_list

        # 源路径是文件夹，文件夹本身直接加入目录列表
        dir_list.append(remote_path)

        # 计算mmin（分钟）
        mtime_minutes = int(mtime_seconds / 60) if mtime_seconds != float('inf') else 0

        # 粗筛策略：
        # - 包含逻辑为"和"时，可以用第一个关键词做 find -name 粗筛（因为"和"要求全有，
        #   第一个关键词不满足的一定不匹配）
        # - 包含逻辑为"或"时，不能用单个关键词粗筛，否则会漏掉含其他关键词的文件
        if include_keywords and include_logic == '和':
            first_kw = include_keywords[0]
        else:
            first_kw = ''

        # 构造find命令（只按时间 + 第一个关键词粗筛）
        if mtime_seconds == float('inf') and not first_kw:
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -not -path "{remote_path}"'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f'
        elif mtime_seconds == float('inf'):
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -not -path "{remote_path}" -name "*{first_kw}*"'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -name "*{first_kw}*"'
        elif not first_kw:
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -not -path "{remote_path}" -mmin -{mtime_minutes}'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -mmin -{mtime_minutes}'
        else:
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -not -path "{remote_path}" -name "*{first_kw}*" -mmin -{mtime_minutes}'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -name "*{first_kw}*" -mmin -{mtime_minutes}'

        # 执行目录查找
        stdin, stdout, stderr = self.ssh.exec_command(dir_find_cmd)
        dir_result = stdout.read().decode('utf-8').strip()
        dir_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            logger.error(f"查找目录失败: {dir_err}")
            return dir_list, file_list

        # 执行文件查找
        stdin, stdout, stderr = self.ssh.exec_command(file_find_cmd)
        file_result = stdout.read().decode('utf-8').strip()
        file_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            logger.error(f"查找文件失败: {file_err}")
            return dir_list, file_list

        # Python端精细过滤名称（多关键词和/或逻辑）
        if dir_result:
            for line in dir_result.split('\n'):
                if self.transfer_stat == 0:
                    return dir_list, file_list
                line = line.strip()
                if not line or not line.startswith('/'):
                    continue
                name = os.path.basename(line)
                if self._match_filename(name, include_keywords, include_logic,
                                        exclude_keywords, exclude_logic):
                    dir_list.append(line)

        if file_result:
            for line in file_result.split('\n'):
                if self.transfer_stat == 0:
                    return dir_list, file_list
                line = line.strip()
                if not line or not line.startswith('/'):
                    continue
                name = os.path.basename(line)
                if self._match_filename(name, include_keywords, include_logic,
                                        exclude_keywords, exclude_logic):
                    file_list.append(line)

        return dir_list, file_list

    @staticmethod
    def _sanitize_member_name(name):
        """tar 成员名逐段清洗 Windows 非法字符（服务器文件名可能含 : * ? 等，NTFS 落盘会失败）"""
        parts = name.split('/')
        return '/'.join(re.sub(r'[<>:"|?*\\]', '-', p) for p in parts)

    def _extract_tar_local(self, tar_path, dest_dir, progress_cb=None):
        """解包本地 tar 到目的路径。
        - 成员名逐段清洗 Windows 非法字符后落盘
        - 已存在同名内容按覆盖语义处理（与历史行为一致）
        - 个别成员解包失败不中断整体，结束时汇总日志
        """
        with tarfile.open(tar_path, 'r') as tf:
            members = tf.getmembers()
            total = len(members)
            failed = []
            for i, m in enumerate(members):
                if self.transfer_stat == 0:
                    raise TransferAborted("解包被中止")
                m.name = self._sanitize_member_name(m.name)
                try:
                    tf.extract(m, dest_dir)
                except Exception as e:
                    failed.append(f"{m.name}: {e}")
                    continue
                if progress_cb:
                    progress_cb('extract', i + 1, total, m.name)
            if failed:
                logger.error(f"解包失败{len(failed)}个条目:\n  " + "\n  ".join(failed))

    def get_files(self, source_items, local_path, work_dir=None, progress_cb=None, pack=False, archive_name=''):
        """
        SSH下载文件（支持多源路径，每条独立筛选）
        流程：服务器端find筛选 -> 跨源重名消歧 -> 服务器端tar打包 -> 单文件下载
             -> 勾选打包：包即产物落到目的路径；未勾选：本地解包到目的路径后删除中转包
        性能优化：使用find命令在服务器端完成时间粗筛，Python端完成名称精细过滤；
        打包后单文件传输（tar不压缩，速度与磁盘拷贝同量级）
        参数：
            source_items: 源路径列表，每项为 dict：
                {
                    '路径': '远程路径',
                    '修改时间': '全部'/'最近30分钟'/'最近1小时'/'最近2小时',
                    '名称包含': {'关键词': [], '逻辑': '和'/'或'},
                    '名称不包含': {'关键词': [], '逻辑': '和'/'或'}
                }
            local_path: 本地目标路径，只能是文件夹
            work_dir: 服务器端临时文件所在路径，默认为 /home/{username}
            progress_cb: 可选的进度回调函数 progress_cb(phase, current, total, extra)
                phase: 'find' | 'pack' | 'download' | 'extract'
                current/total: 进度数值
                extra: 附加信息字符串
            pack: True 时保留打包产物到目的路径（archive_name 为最终文件名）；
                  False 时下载后自动解包到目的路径（历史行为）
            archive_name: pack=True 时的包文件名（调用方已渲染占位符并校验合法字符）
        返回：
            成功返回True，失败返回False
        中断支持：
            self.transfer_stat = 0 时立即中止传输并清理临时文件
        """
        if not self.is_connected():
            logger.warning("未连接到服务器，请先连接")
            return False

        local_path = local_path.replace('\\', '/').rstrip('/')

        if not os.path.exists(local_path) or not os.path.isdir(local_path):
            logger.error(f"下载失败，本地路径不存在或不是文件夹: {local_path}")
            return False

        if pack and not str(archive_name or '').strip():
            logger.error("打包下载失败：包文件名为空")
            return False

        # 修改时间映射（秒）
        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200,
            "最近1天": 86400,
            "最近1月": 2592000,
            "最近1年": 31536000
        }

        # 构造sudo前缀（连接期已探测 sudo 能力）：
        # - 有 sudo：全程提权，可读任意路径（历史行为）
        # - 无 sudo：全程不提权，能下多少下多少；find/tar 对无权限内容报错但
        #   继续处理其余条目，最终在 tar_errors 中逐项报告（部分成功语义）
        if self.username != 'root' and self.sudo_ok:
            sudo_prefix = f"echo {self.password} | sudo -S "
        else:
            if self.username != 'root':
                logger.info("当前用户无sudo权限，仅下载有读取权限的文件")
            sudo_prefix = ""

        # 校验所有源路径是否存在
        for item in source_items:
            path = item['路径'].replace('\\', '/').rstrip('/')
            check_cmd = f"{sudo_prefix}bash -c 'test -e \"{path}\" && echo exists || echo not exists'"
            stdin, stdout, stderr = self.ssh.exec_command(check_cmd)
            check_result = stdout.read().decode('utf-8').strip()
            stderr.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0 or 'not exists' in check_result:
                logger.error(f"下载失败，远程路径不存在: {path}")
                return False

        # 标记传输状态为进行中
        self.transfer_stat = 1

        # 获取服务器当前时间戳
        time_cmd = "date +%s"
        stdin, stdout, stderr = self.ssh.exec_command(time_cmd)
        server_now = stdout.read().decode('utf-8').strip()
        stderr.read()

        # 生成毫秒级本地时间戳，用于临时文件命名，避免重名
        local_timestamp_ms = f"{int(time.time() * 1000)}"

        # 服务器端打包文件与条目列表文件的所在目录（校验/规范化，非法路径回退家目录）
        base_dir = self.resolve_work_dir(work_dir)
        remote_tar_path = f"{base_dir}/OneClick_temp{local_timestamp_ms}.tar"

        logger.debug("开始查找符合条件的文件...")

        # 多源路径合并后的文件/目录列表，每项带源根路径与源序号，
        # 源根用于计算相对路径，源序号用于跨源重名消歧
        all_file_list = []  # [(full_path, source_root, source_idx)]
        all_dir_list = []   # [(full_path, source_root, source_idx)]
        # 无筛选条件且源路径是目录的项，直接整目录打包，不走 find + 逐文件筛选
        direct_copy_dirs = []  # [(src_path, source_root, source_idx)]

        for src_idx, item in enumerate(source_items):
            src_path = item['路径'].replace('\\', '/').rstrip('/')
            mtime_str = item.get('修改时间', '全部')
            mtime_sec = mtime_dic.get(mtime_str, float('inf'))
            inc = item.get('名称包含', {})
            inc_kw = inc.get('关键词', []) if isinstance(inc, dict) else ([inc] if inc else [])
            inc_logic = inc.get('逻辑', '或') if isinstance(inc, dict) else '或'
            exc = item.get('名称不包含', {})
            exc_kw = exc.get('关键词', []) if isinstance(exc, dict) else []
            exc_logic = exc.get('逻辑', '和') if isinstance(exc, dict) else '和'

            # 判断：源路径是目录 且 完全没有筛选条件 → 整目录直接打包
            has_no_filter = (
                mtime_sec == float('inf')
                and not inc_kw
                and not exc_kw
            )
            if has_no_filter:
                # 检查源路径是否为目录
                check_cmd = f"{sudo_prefix}bash -c 'test -d \"{src_path}\" && echo dir || echo not_dir'"
                stdin, stdout, stderr = self.ssh.exec_command(check_cmd)
                check_result = stdout.read().decode('utf-8').strip()
                stderr.read()
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0 and check_result == 'dir':
                    direct_copy_dirs.append((src_path, src_path, src_idx))
                    continue

            dirs, files = self._filter_remote_source(
                src_path, mtime_sec, inc_kw, inc_logic, exc_kw, exc_logic, server_now, sudo_prefix
            )
            for d in dirs:
                all_dir_list.append((d, src_path, src_idx))
            for f in files:
                all_file_list.append((f, src_path, src_idx))

            if self.transfer_stat == 0:
                logger.warning('下载被中止！')
                return False

        # 没有符合条件的项，直接返回
        if not all_dir_list and not all_file_list and not direct_copy_dirs:
            logger.info("下载完成，未下载任何文件，待下载路径无符合条件的项")
            self.transfer_stat = 0
            return True

        # 统计直接复制目录的文件总数
        direct_copy_file_count = 0
        for dir_path, _, _src_idx in direct_copy_dirs:
            count_cmd = f"{sudo_prefix}find \"{dir_path}\" -type f | wc -l"
            stdin, stdout, stderr = self.ssh.exec_command(count_cmd)
            count_out = stdout.read().decode('utf-8').strip()
            stderr.read()
            if count_out.isdigit():
                direct_copy_file_count += int(count_out)

        logger.debug(f"找到{len(all_dir_list)}个目录, {len(all_file_list)}个文件, {len(direct_copy_dirs)}个直接复制目录")
        if progress_cb:
            total_files = len(all_file_list) + direct_copy_file_count
            if not all_file_list and direct_copy_dirs:
                progress_cb('find', 0, total_files, f'找到{len(direct_copy_dirs)}个目录（共{total_files}个文件）')
            elif all_file_list and direct_copy_dirs:
                progress_cb('find', 0, total_files, f'找到{total_files}个文件 + {len(direct_copy_dirs)}个目录')
            else:
                progress_cb('find', 0, total_files, f'找到{total_files}个文件')

        # ---- 组装打包条目：相对路径 + 跨源重名消歧 ----
        # 每条源以自己的父目录为基准计算相对路径（与历史落盘结构一致）。
        # 不同源路径算出相同相对路径时（如 /root/abc 与 /home/abc 都算出 'abc'），
        # 后到的源加 "{源序号}_" 前缀消歧，避免打包落盘时静默覆盖/嵌套错乱
        grouped_entries = {}  # 源父目录 -> [相对条目, ...]（按出现顺序）
        rel_owner = {}        # 相对条目 -> 首个占用的源序号

        def _claim_rel(src_parent, rel, src_idx):
            owner = rel_owner.get(rel)
            if owner is not None:
                if owner == src_idx:
                    return  # 同源重复条目，去重
                orig = rel
                rel = f"{src_idx + 1}_{rel}"
                # 极端情况：消歧后的名字仍被占用，继续追加序号直到唯一
                while rel in rel_owner:
                    rel = f"{src_idx + 1}_{rel}"
                logger.warning(f"源{owner + 1}与源{src_idx + 1}的目标相对路径重名'{orig}'，"
                               f"源{src_idx + 1}已改名为'{rel}'")
            rel_owner[rel] = src_idx
            grouped_entries.setdefault(src_parent, []).append(rel)

        for dir_path, src_root, src_idx in all_dir_list:
            if dir_path == src_root:
                # 源目录本身是结构壳（_filter_remote_source 无条件放入），
                # 绝不能进 tar -T 列表——tar 对目录条目会递归归档整个目录，
                # 导致筛选失效全量打包；壳层由文件/子目录条目的相对路径自动带出
                continue
            src_parent = os.path.dirname(src_root)
            _claim_rel(src_parent, dir_path.replace(src_parent, '', 1).lstrip('/'), src_idx)
        for file_path, src_root, src_idx in all_file_list:
            src_parent = os.path.dirname(src_root)
            _claim_rel(src_parent, file_path.replace(src_parent, '', 1).lstrip('/'), src_idx)
        for dir_path, src_root, src_idx in direct_copy_dirs:
            src_parent = os.path.dirname(src_root)
            _claim_rel(src_parent, dir_path.replace(src_parent, '', 1).lstrip('/'), src_idx)

        if not grouped_entries:
            logger.info("下载完成，未下载任何文件，待下载路径无符合条件的项")
            self.transfer_stat = 0
            return True

        # ---- 写条目列表文件（本地生成，经统一传输入口上传，避免超长命令行）----
        local_list_paths = []
        remote_list_paths = []
        try:
            for g, (src_parent, rels) in enumerate(grouped_entries.items()):
                remote_list = f"{base_dir}/OneClick_temp{local_timestamp_ms}_g{g}.list"
                fd, local_list = tempfile.mkstemp(prefix='oneclick_tar_list_')
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fp:
                    fp.write('\n'.join(rels) + '\n')
                local_list_paths.append(local_list)
                remote_list_paths.append(remote_list)
                self.put_file(local_list, remote_list)
                os.remove(local_list)
                local_list_paths.pop()
        except Exception as e:
            logger.error(f"上传打包条目列表失败: {e}")
            for p in local_list_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            self.transfer_stat = 0
            return False

        def _cleanup_remote_artifacts():
            """清理远端包与列表文件（普通用户经 sudo，root 直连直接删）"""
            quoted = ' '.join(f'"{p}"' for p in [remote_tar_path] + remote_list_paths)
            try:
                stdin, stdout, stderr = self.ssh.exec_command(f"{sudo_prefix}rm -f {quoted}")
                stdout.read()
                stderr.read()
            except Exception:
                pass

        # ---- 服务器端打包（tar 不压缩，速度与磁盘拷贝同量级）----
        if progress_cb:
            progress_cb('pack', 0, 0, '服务器端打包中...')
        tar_errors = []
        for g, (src_parent, rels) in enumerate(grouped_entries.items()):
            if self.transfer_stat == 0:
                logger.warning('下载被中止！')
                _cleanup_remote_artifacts()
                self.transfer_stat = 0
                return False
            # 首组建包，后续组追加（追加要求包未压缩）
            # 注意：items() 的第二个值是 rels 列表，列表文件路径取 remote_list_paths[g]
            remote_list = remote_list_paths[g]
            mode = '-cf' if g == 0 else '-rf'
            tar_cmd = (f"{sudo_prefix}bash -c 'cd \"{src_parent}\" && tar {mode} "
                       f"\"{remote_tar_path}\" -T \"{remote_list}\"'")
            stdin, stdout, stderr = self.ssh.exec_command(tar_cmd)
            tar_err = stderr.read().decode('utf-8', 'replace').strip()
            stdout.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                tar_errors.append(f"源目录 {src_parent}: {tar_err or f'退出码 {exit_status}'}")

        # sudo 打包时包属主为 root，放开读权限供下载会话读取
        # （无 sudo 时包以登录用户身份生成，本身可读，无需 chmod）
        if sudo_prefix:
            stdin, stdout, stderr = self.ssh.exec_command(f"{sudo_prefix}chmod 644 \"{remote_tar_path}\"")
            stdout.read()
            stderr.read()

        # 包大小：存在性校验 + 下载进度总量
        stdin, stdout, stderr = self.ssh.exec_command(
            f'du -sb "{remote_tar_path}" 2>/dev/null | awk \'{{print $1}}\'')
        output = stdout.read().decode('utf-8').strip()
        stderr.read()
        tar_size = int(output) if output.isdigit() else 0
        if tar_size <= 0:
            detail = "\n  ".join(tar_errors) if tar_errors else "打包命令未产出有效包文件"
            logger.error(f"服务器端打包失败:\n  {detail}")
            # 诊断：打印列表内容与源目录实况（列表此时还在远端，清理前取回），
            # 定位"列表条目与磁盘实际条目对不上"类问题
            for g, (src_parent, rels) in enumerate(grouped_entries.items()):
                remote_list = remote_list_paths[g]
                try:
                    stdin, stdout, stderr = self.ssh.exec_command(
                        f"echo '--- 列表内容 {remote_list} ---'; cat \"{remote_list}\" 2>&1; "
                        f"echo '--- 源目录实况 {src_parent} ---'; ls -la \"{src_parent}\" 2>&1")
                    diag = stdout.read().decode('utf-8', 'replace').strip()
                    stderr.read()
                    logger.error(f"打包诊断[组{g}]:\n{diag}")
                except Exception:
                    pass
            _cleanup_remote_artifacts()
            self.transfer_stat = 0
            return False
        if tar_errors:
            # 个别源打包失败但包已生成：列出明细继续下载其余内容（与历史逐文件容错语义一致）
            logger.error("以下源路径打包出错（已跳过）:\n  " + "\n  ".join(tar_errors))
        if progress_cb:
            progress_cb('pack', 1, 1, f'打包完成 ({tar_size / 1048576:.1f}MB)')
        logger.debug(f"打包完成，大小: {tar_size / 1048576:.2f} M")

        # ---- 单文件下载 ----
        tar_basename = os.path.basename(remote_tar_path)
        if pack:
            local_target = os.path.join(local_path, archive_name)
        else:
            local_target = os.path.join(local_path, tar_basename)

        try:
            if self.transfer_stat == 0:
                raise TransferAborted("下载被中止")

            def _dl_progress(name, size, sent):
                if self.transfer_stat == 0:
                    raise TransferAborted("下载被中止")
                self._print_progress(sent, tar_size)
                if progress_cb:
                    progress_cb('download', sent, tar_size, '')

            self.get_file(remote_tar_path, local_target,
                          progress=_dl_progress if progress_cb else None)
            if progress_cb:
                progress_cb('download', tar_size, tar_size, '')
        except TransferAborted:
            logger.warning('下载被中止！')
            _cleanup_remote_artifacts()
            try:
                if os.path.exists(local_target):
                    os.remove(local_target)
            except OSError:
                pass
            self.transfer_stat = 0
            return False
        except Exception as e:
            logger.error(f"\n下载失败: {e}")
            _cleanup_remote_artifacts()
            try:
                if os.path.exists(local_target):
                    os.remove(local_target)
            except OSError:
                pass
            self.transfer_stat = 0
            return False

        # ---- 本地处理：落包 or 解包 ----
        # 呈现层路径统一正斜杠（正斜杠路径 Windows API 全兼容，不影响后续 os 操作）
        local_target = str(local_target).replace('\\', '/')
        if pack:
            logger.info(f"打包下载完成: {local_target}")
        else:
            try:
                self._extract_tar_local(local_target, local_path, progress_cb)
            except TransferAborted:
                logger.warning('解包被中止！')
                try:
                    os.remove(local_target)
                except OSError:
                    pass
                self.transfer_stat = 0
                return False
            except Exception as e:
                logger.error(f"解包失败: {e}")
                try:
                    os.remove(local_target)
                except OSError:
                    pass
                self.transfer_stat = 0
                return False
            # 解包完成，删除中转包
            try:
                os.remove(local_target)
            except OSError:
                pass

        # ---- 清理远端临时文件 ----
        _cleanup_remote_artifacts()
        logger.debug("远程临时文件已删除")

        logger.debug(f"下载完毕！文件已保存到: {local_path}")
        self.transfer_stat = 0
        return True

    def _print_progress(self, sent, total):
        """
        打印SCP传输进度条
        参数：
            sent: 已传输字节数
            total: 总字节数
        异常：
            当self.transfer_stat为0时抛出异常，用于中断传输
        """
        if self.transfer_stat == 0:
            raise TransferAborted("传输被中止")
        if total <= 0:
            return
        # 计算当前进度（0~10）
        progress = int((sent / total) * 10)
        # 只有当进度值发生变化时才打印
        if progress != self._last_progress:
            self._last_progress = progress
            bar = '-' * progress + ' ' * (10 - progress)
            if '-' not in bar:
                return
            logger.debug(f"传输进度: |{bar}|")

    def mkdir(self, path):
        if not self.is_connected():
            logger.warning("未连接到服务器，请先连接")
            return False
        if self.username != 'root':
            mkdir_cmd = f"echo {self.password} | sudo -S mkdir -p \"{path}\""
        else:
            mkdir_cmd = f'mkdir -p \"{path}\"'
        stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
        mkdir_out = stdout.read().decode('utf-8').strip()
        mkdir_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            logger.error(f"创建目标目录失败 {path}，原因: {mkdir_err}")
            return False
        return True

