import paramiko
import time
import os
import re
import shutil
from utils.windows_tools import WindowsTools
from scp import SCPClient


class SSHTools(object):
    def __init__(self):
        self.ip = None
        self.port = 22
        self.username = "root"
        self.password = "123456"
        self.ssh = None
        self.channel = None

        self.sudo = False
        self.transfer_stat = 0
        self._last_progress = -1
        self._download_progress_cb = None
        self.transport = None

        self.win_tool = WindowsTools()

    def connect(self, timeout=10):
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.ip, self.port, self.username, self.password,
                             timeout=timeout, banner_timeout=timeout, auth_timeout=timeout)

            # 打开一个通道用于传输数据
            self.channel = self.ssh.invoke_shell()
            self.channel.resize_pty(width=500, height=1000)
            self.channel.settimeout(10)  # 防止卡住
            # 非阻塞通道，在线程里时仍然可以发送数据
            self.channel.setblocking(0)
            if self.username == "root":
                self.sudo = True
            print("ssh连接成功")
            self.transport = self.ssh.get_transport()
            self.transport.set_keepalive(5)
            return True
        except Exception as e:
            print(f"ssh连接失败: {e}")
            return False

    def get_root_priority(self):
        if not self.is_connected():
            return False
        if self.username != 'root':
            print(f"当前非root用户登录，尝试使用{self.username}密码切换到root权限")
            try:
                # 发送sudo -i命令
                # 读取输出，判断是否需要输入sudo密码（通常提示"Password:"或"密码："）
                output = self.send_get_output_once("sudo -i", False)
                if "Password" in output or "password" in output or "密码" in output:
                    # 输入当前用户密码
                    # 验证是否切换成功（root提示符通常是#，普通用户是$）
                    self.send_command_interactive(self.password)
                    whoami_output = self.send_get_output_once("whoami", False)
                    if "root" in whoami_output:
                        print("非root用户已切换root权限")
                        self.sudo = True
                        return True
                    else:
                        print(f"root切换失败")
                        return False
                else:
                    print(f"不支持sudo -i，切换root权限失败{output}")
                    return False
            except Exception as e:
                print(f"切换root权限失败{e}")
                return False
        else:
            self.sudo = True
            print("当前已是root用户，拥有root权限")
            return True

    def disconnect(self):
        if not self.is_connected():
            self.sudo = False
            self.transfer_stat = 0
            self.win_tool.transfer_stat = 0
            print('ssh断开成功')
            return True
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.sudo = False
        self.transfer_stat = 0
        self.win_tool.transfer_stat = 0
        print('ssh断开成功')
        return True

    def is_connected(self):
        if not (self.ssh and self.transport and self.transport.is_active()):
            return False
        try:
            # 尝试执行一个极简单的命令来探测连接
            stdin, stdout, stderr = self.ssh.exec_command("echo -n", timeout=2)
            stdout.read()  # 必须读取输出，确保命令执行完毕
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
            print(f"指令发送成功：{cmd}")
            return True
        else:
            print("未连接到服务器，请先连接")
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
                    print(f"已发送中止请求ctrl+c，请稍等...")
                else:
                    print(f"指令发送成功：{cmd}")
                    return True
            except Exception as e:
                print(f"指令发送失败：{e}")
                return False
        else:
            print("未连接到服务器，请先连接")
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

    def get_output_continue(self, echo_signal=None, timeout=3):
        """用于持续接收类似与top这样的命令的回显"""
        if not self.is_connected():
            print("未连接到服务器，请先连接。")
            return False
        try:
            timeout_count = 0
            while True:
                time.sleep(0.1)
                if self.channel is None:
                    break
                if not self.is_connected():
                    break
                try:
                    if self.channel.recv_ready():
                        output = self.channel.recv(4096).decode().strip()
                        output = self.purify_output(output, False)

                        if echo_signal is not None:
                            echo_signal.emit(output)

                        timeout_count = 0  # 重置超时计数器
                    else:
                        timeout_count += 1
                        # 无数据超时退出
                        if timeout_count > timeout * 30:
                            print(f"超时({timeout}秒)无内容，回显退出")
                            break
                except (AttributeError, EOFError):
                    # 断开操作把 channel 设为 None 时，直接退出
                    break
            return True
        except Exception as e:
            print(f"执行命令时出错: {e}")
            return False

    def get_path_mode(self, path):
        """获取路径的权限，755、777，如果是root用户登录，直接用sftp获取权限，否则用channel"""
        if not self.is_connected():
            return False
        else:
            if not self.sudo:
                self.get_root_priority()
            if self.sudo:
                try:
                    if self.username == 'root':
                        sftp = self.ssh.open_sftp()
                        path_attr = sftp.stat(path)
                        permission = oct(path_attr.st_mode & 0o777)[2:]
                        return permission
                    else:
                        output = self.send_get_output_once(f'stat -c %a {path}')
                        return output
                except Exception as e:
                    print(f"获取路径的用户权限失败{e}")
                    return False
            else:
                return False

    def get_pathtree_info(self, remote_path, path_only=False, recursive=False, tree_list=None):
        """
        获取远程路径的文件/目录信息（不依赖self.sudo，全程使用sudo指令）
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
                print(f"执行sudo命令失败 [{cmd}]: {stderr_content}")
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
            print(f"获取路径信息失败：命令执行失败")
            return []

        if not stat_output:
            # stat执行成功，但输出为空 = 路径不存在
            print(f"路径不存在：{remote_path}")
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
            print("未连接到服务器，请先连接")
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
                print(f"上传失败，本地路径不存在: {path}")
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
            print(f"上传失败，远程目标路径不存在或不是文件夹: {remote_path}")
            return False

        # 标记传输状态为进行中
        self.transfer_stat = 1

        print("开始查找符合条件的文件...")
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
                print('上传被中止！')
                return False

        # 没有符合条件的项，直接返回
        if not all_dir_list and not all_file_list:
            print(f"上传完成，未上传任何文件，待上传路径无符合条件的项")
            self.transfer_stat = 0
            return True

        print(f"找到{len(all_dir_list)}个目录, {len(all_file_list)}个文件")
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
        base_dir = work_dir if work_dir else f"/home/{self.username}"
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

        print("开始创建服务器临时目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                print('上传被中止！')
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
                    print(f"创建目录失败: {mkdir_err}")
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
        print(f"开始上传文件到服务器临时目录，共{file_count}个文件")

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
                print('上传被中止！')
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
                        with SCPClient(self.transport, progress=lambda n, s, se, fp=f_path: _scp_upload_progress(os.path.basename(fp), s, se)) as client:
                            self._last_progress = -1
                            client.put(f_path, dst_path)
                    else:
                        with SCPClient(self.transport) as client:
                            self._last_progress = -1
                            client.put(f_path, dst_path)
                    if progress_cb and file_count > 10:
                        _upload_state['accumulated'] += file_size
                        extra = f"{os.path.basename(f_path)}|{file_size}|{file_size}|{up_count}|{file_count}"
                        progress_cb('upload', _upload_state['accumulated'], total_size, extra)
                else:
                    print(f"大文件上传: {file_size} 字节")
                    with SCPClient(self.transport, progress=lambda n, s, se, fp=f_path: _scp_upload_progress(os.path.basename(fp), s, se)) as client:
                        if self.transfer_stat == 0:
                            print("上传被中止")
                            rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                            stdout.read()
                            stderr.read()
                            self.transfer_stat = 0
                            return False
                        self._last_progress = -1
                        client.put(f_path, dst_path)
                print(f"已上传到临时目录 {up_count}/{file_count}: {f_path} -> {dst_path}")
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
                    print(f"上传到临时目录失败 {up_count}/{file_count}: {f_path} -> {dst_path},原因: {e}")
                    failed_files.append({"文件": f_path, "原因": err_msg})

        # 打印上传失败汇总
        if failed_files:
            fail_lines = [f"上传失败{len(failed_files)}个文件："]
            for idx, f_item in enumerate(failed_files, 1):
                fail_lines.append(f"  {idx}. {f_item['文件']} - {f_item['原因']}")
            print("\n".join(fail_lines))

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_dir}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        # 移动文件到目标目录：一次性 cp -a，更快
        print("上传完成，开始移动文件到目标目录...")
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
            print(f"移动文件失败: {mv_err}")
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
        print("临时目录已删除")

        print(f"上传完毕！文件已保存到: {remote_path}")
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
            print(f"查找目录失败: {dir_err}")
            return dir_list, file_list

        # 执行文件查找
        stdin, stdout, stderr = self.ssh.exec_command(file_find_cmd)
        file_result = stdout.read().decode('utf-8').strip()
        file_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"查找文件失败: {file_err}")
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

    def get_files(self, source_items, local_path, work_dir=None, progress_cb=None):
        """
        SSH下载文件（支持多源路径，每条独立筛选）
        流程：服务器端find筛选 -> 复制到临时目录 -> SCP下载 -> 清理临时文件
        性能优化：使用find命令在服务器端完成时间粗筛，Python端完成名称精细过滤
        参数：
            source_items: 源路径列表，每项为 dict：
                {
                    '路径': '远程路径',
                    '修改时间': '全部'/'最近30分钟'/'最近1小时'/'最近2小时',
                    '名称包含': {'关键词': [], '逻辑': '和'/'或'},
                    '名称不包含': {'关键词': [], '逻辑': '和'/'或'}
                }
            local_path: 本地目标路径，只能是文件夹
            work_dir: 服务器端临时目录所在路径，默认为 /home/{username}
            progress_cb: 可选的进度回调函数 progress_cb(phase, current, total, extra)
                phase: 'find' | 'copy' | 'download'
                current/total: 进度数值
                extra: 附加信息字符串
        返回：
            成功返回True，失败返回False
        中断支持：
            self.transfer_stat = 0 时立即中止传输并清理临时文件
        """
        if not self.is_connected():
            print("未连接到服务器，请先连接")
            return False

        local_path = local_path.replace('\\', '/').rstrip('/')

        if not os.path.exists(local_path) or not os.path.isdir(local_path):
            print(f"下载失败，本地路径不存在或不是文件夹: {local_path}")
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

        # 构造sudo前缀
        if self.username != 'root':
            sudo_prefix = f"echo {self.password} | sudo -S "
        else:
            sudo_prefix = ""

        # 校验所有源路径是否存在
        for item in source_items:
            path = item['路径'].replace('\\', '/').rstrip('/')
            if self.username != 'root':
                check_cmd = f"{sudo_prefix}bash -c 'test -e \"{path}\" && echo exists || echo not exists'"
            else:
                check_cmd = f"bash -c 'test -e \"{path}\" && echo exists || echo not exists'"
            stdin, stdout, stderr = self.ssh.exec_command(check_cmd)
            check_result = stdout.read().decode('utf-8').strip()
            stderr.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0 or 'not exists' in check_result:
                print(f"下载失败，远程路径不存在: {path}")
                return False

        # 标记传输状态为进行中
        self.transfer_stat = 1

        # 获取服务器当前时间戳
        time_cmd = "date +%s"
        stdin, stdout, stderr = self.ssh.exec_command(time_cmd)
        server_now = stdout.read().decode('utf-8').strip()
        stderr.read()

        # 生成毫秒级本地时间戳，用于临时目录命名，避免重名
        local_timestamp_ms = f"{int(time.time() * 1000)}"

        # 构造服务器临时目录
        base_dir = work_dir if work_dir else f"/home/{self.username}"
        temp_remote_path = f"{base_dir}/OneClick_temp{local_timestamp_ms}"

        print("开始查找符合条件的文件...")

        # 多源路径合并后的文件/目录列表，每项带源路径信息用于计算相对路径
        all_file_list = []  # [(full_path, source_root)]
        all_dir_list = []   # [(full_path, source_root)]
        # 无筛选条件且源路径是目录的项，直接 cp -a 复制，不走 find + 逐文件复制
        direct_copy_dirs = []  # [(src_path, source_root)]

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

            # 判断：源路径是目录 且 完全没有筛选条件 → 直接 cp -a
            has_no_filter = (
                mtime_sec == float('inf')
                and not inc_kw
                and not exc_kw
            )
            if has_no_filter:
                # 检查源路径是否为目录
                if self.username != 'root':
                    check_cmd = f"{sudo_prefix}bash -c 'test -d \"{src_path}\" && echo dir || echo not_dir'"
                else:
                    check_cmd = f"bash -c 'test -d \"{src_path}\" && echo dir || echo not_dir'"
                stdin, stdout, stderr = self.ssh.exec_command(check_cmd)
                check_result = stdout.read().decode('utf-8').strip()
                stderr.read()
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0 and check_result == 'dir':
                    direct_copy_dirs.append((src_path, src_path))
                    continue

            dirs, files = self._filter_remote_source(
                src_path, mtime_sec, inc_kw, inc_logic, exc_kw, exc_logic, server_now, sudo_prefix
            )
            for d in dirs:
                all_dir_list.append((d, src_path))
            for f in files:
                all_file_list.append((f, src_path))

            if self.transfer_stat == 0:
                print('下载被中止！')
                return False

        # 没有符合条件的项，直接返回
        if not all_dir_list and not all_file_list and not direct_copy_dirs:
            print(f"下载完成，未下载任何文件，待下载路径无符合条件的项")
            self.transfer_stat = 0
            return True

        # 统计直接复制目录的文件总数
        direct_copy_file_count = 0
        for dir_path, _ in direct_copy_dirs:
            if self.username != 'root':
                count_cmd = f"echo {self.password} | sudo -S find \"{dir_path}\" -type f | wc -l"
            else:
                count_cmd = f"find \"{dir_path}\" -type f | wc -l"
            stdin, stdout, stderr = self.ssh.exec_command(count_cmd)
            count_out = stdout.read().decode('utf-8').strip()
            stderr.read()
            if count_out.isdigit():
                direct_copy_file_count += int(count_out)

        print(f"找到{len(all_dir_list)}个目录, {len(all_file_list)}个文件, {len(direct_copy_dirs)}个直接复制目录")
        if progress_cb:
            total_files = len(all_file_list) + direct_copy_file_count
            if not all_file_list and direct_copy_dirs:
                progress_cb('find', 0, total_files, f'找到{len(direct_copy_dirs)}个目录（共{total_files}个文件）')
            elif all_file_list and direct_copy_dirs:
                progress_cb('find', 0, total_files, f'找到{total_files}个文件 + {len(direct_copy_dirs)}个目录')
            else:
                progress_cb('find', 0, total_files, f'找到{total_files}个文件')

        # 清洗完整路径：所有目录名和文件名中的Windows不支持字符都替换为 -
        def sanitize_path_for_windows(path):
            parts = path.split('/')
            sanitized_parts = [re.sub(r'[<>:"/\\|?*]', '-', part) for part in parts]
            return '/'.join(sanitized_parts)

        # 收集所有需要创建的目录
        all_dirs = set()
        for d, src_root in all_dir_list:
            src_parent = os.path.dirname(src_root)
            rel_path = d.replace(src_parent, '', 1).lstrip('/')
            if rel_path == '':
                continue
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_dir = f"{temp_remote_path}/{sanitized_rel_path}"
            all_dirs.add(dst_dir)

        for f, src_root in all_file_list:
            src_parent = os.path.dirname(src_root)
            rel_path = f.replace(src_parent, '', 1).lstrip('/')
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_dir = os.path.dirname(f"{temp_remote_path}/{sanitized_rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序
        sorted_dirs = sorted(all_dirs, key=lambda x: len(x), reverse=True)
        created_dirs = set()

        print("开始创建目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                print('下载被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_path}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
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
                stderr.read()
                created_dirs.add(dst_dir)

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_path}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_path}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        # 复制文件到临时目录
        file_count = len(all_file_list)
        print(f"开始复制文件到远程临时目录，共{file_count}个文件, {len(direct_copy_dirs)}个直接复制目录")

        # 先创建临时目录根目录（直接复制目录需要）
        if self.username != 'root':
            mkdir_cmd = f"echo {self.password} | sudo -S mkdir -p \"{temp_remote_path}\""
        else:
            mkdir_cmd = f"mkdir -p \"{temp_remote_path}\""
        stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
        stdout.read()
        stderr.read()

        # 先处理直接复制的目录（cp -a 整个目录）
        for dir_path, src_root in direct_copy_dirs:
            if self.transfer_stat == 0:
                print('下载被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_path}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                return False

            src_parent = os.path.dirname(src_root)
            rel_path = dir_path.replace(src_parent, '', 1).lstrip('/')
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_path = f"{temp_remote_path}/{sanitized_rel_path}"

            # 确保目标父目录存在
            dst_parent = os.path.dirname(dst_path)
            if dst_parent and dst_parent != temp_remote_path:
                if self.username != 'root':
                    mkdir_cmd = f"echo {self.password} | sudo -S mkdir -p \"{dst_parent}\""
                else:
                    mkdir_cmd = f"mkdir -p \"{dst_parent}\""
                stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
                stdout.read()
                stderr.read()

            if self.username != 'root':
                cp_cmd = f"echo {self.password} | sudo -S cp -a \"{dir_path}\" \"{dst_path}\""
            else:
                cp_cmd = f"cp -a \"{dir_path}\" \"{dst_path}\""

            stdin, stdout, stderr = self.ssh.exec_command(cp_cmd)
            cp_err = stderr.read().decode('utf-8').strip()
            stdout.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"直接复制目录失败: {dir_path} -> {dst_path},原因: {cp_err}")
            else:
                print(f"复制目录完成: {dir_path} -> {dst_path}")
                if progress_cb:
                    progress_cb('copy', 0, 0, f'复制目录{os.path.basename(dir_path)}完成')

        # 再处理逐文件复制
        cp_count = 0
        failed_files = []
        for file_path, src_root in all_file_list:
            if self.transfer_stat == 0:
                print('下载被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_path}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                return False

            cp_count += 1
            src_parent = os.path.dirname(src_root)
            rel_path = file_path.replace(src_parent, '', 1).lstrip('/')
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_path = f"{temp_remote_path}/{sanitized_rel_path}"

            if self.username != 'root':
                cp_cmd = f"echo {self.password} | sudo -S cp -p \"{file_path}\" \"{dst_path}\""
            else:
                cp_cmd = f"cp -p \"{file_path}\" \"{dst_path}\""

            stdin, stdout, stderr = self.ssh.exec_command(cp_cmd)
            cp_err = stderr.read().decode('utf-8').strip()
            stdout.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"复制到临时目录失败 {cp_count}/{file_count}: {file_path} -> {dst_path},原因: {cp_err}")
                failed_files.append({"文件": file_path, "原因": cp_err})
            else:
                print(f"已复制到临时目录 {cp_count}/{file_count}: {file_path} -> {dst_path}")
                if progress_cb:
                    progress_cb('copy', cp_count, file_count, os.path.basename(file_path))

        # 打印复制失败汇总
        if failed_files:
            fail_lines = [f"复制失败{len(failed_files)}个文件："]
            for idx, f_item in enumerate(failed_files, 1):
                fail_lines.append(f"  {idx}. {f_item['文件']} - {f_item['原因']}")
            print("\n".join(fail_lines))

        if self.transfer_stat == 0:
            print('下载被中止！')
            rm_cmd = f"rm -rf \"{temp_remote_path}\""
            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
            stdout.read()
            stderr.read()
            return False

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_path}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_path}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        # 多层fallback计算远程文件/目录大小
        dst_size = 0
        stdin, stdout, stderr = self.ssh.exec_command(f'du -sb "{temp_remote_path}" 2>/dev/null | awk \'{{print $1}}\'')
        output = stdout.read().decode('utf-8').strip()
        stderr.read()
        if output.isdigit():
            dst_size = int(output)
        else:
            stdin, stdout, stderr = self.ssh.exec_command(f'du -s "{temp_remote_path}" 2>/dev/null')
            du_output = stdout.read().decode('utf-8').strip()
            stderr.read()
            output = du_output.split()[0] if du_output else ''
            if output.isdigit():
                dst_size = int(output) * 1024
            else:
                stdin, stdout, stderr = self.ssh.exec_command(f'find "{temp_remote_path}" -type f -exec wc -c {{}} \\; 2>/dev/null | awk \'{{sum+=$1}} END {{print sum}}\'')
                output = stdout.read().decode('utf-8').strip()
                stderr.read()
                if output.isdigit():
                    dst_size = int(output)

        if dst_size > 0:
            print(f"开始下载，大小: {dst_size/1048576:.2f} M")
        else:
            print(f"开始下载（无法获取大小）")

        try:
            # 直接复制目录的文件数 + 逐文件复制的文件数
            _real_total_files = len(all_file_list) + direct_copy_file_count
            _download_state = {
                'accumulated': 0,
                'last_name': '',
                'last_size': 0,
                'file_index': 0,
                'total_files': _real_total_files,
                'last_cb_pct': -1,
            }

            if progress_cb:
                def _dl_progress(total_sent, total_size, cur_name, cur_size, cur_sent, file_idx, total_files):
                    progress_cb('download', total_sent, total_size,
                                f"{cur_name}|{cur_size}|{cur_sent}|{file_idx}|{total_files}")
                self._download_progress_cb = _dl_progress
            else:
                self._download_progress_cb = None

            def _scp_progress(name, size, sent):
                file_changed = False
                if _download_state['last_name'] and name != _download_state['last_name']:
                    _download_state['accumulated'] += _download_state['last_size']
                    _download_state['file_index'] += 1
                    file_changed = True
                _download_state['last_name'] = name
                _download_state['last_size'] = size

                total_sent = _download_state['accumulated'] + sent
                self._print_progress(total_sent, dst_size)
                if hasattr(self, '_download_progress_cb') and self._download_progress_cb:
                    cur_pct = int(total_sent * 100 / dst_size) if dst_size > 0 else 0
                    if file_changed or cur_pct != _download_state['last_cb_pct']:
                        _download_state['last_cb_pct'] = cur_pct
                        self._download_progress_cb(total_sent, dst_size, name, size, sent,
                                                   _download_state['file_index'], _download_state['total_files'])

            with SCPClient(self.transport, progress=_scp_progress) as client:
                if self.transfer_stat == 0:
                    raise Exception("下载被中止")
                self._last_progress = -1
                client.get(temp_remote_path, local_path, recursive=True)

            # 补一次 100% 进度回调
            if progress_cb and dst_size > 0:
                last_name = _download_state['last_name']
                last_size = _download_state['last_size']
                last_idx = _download_state['file_index']
                last_total = _download_state['total_files']
                progress_cb('download', dst_size, dst_size,
                            f"{last_name}|{last_size}|{last_size}|{last_idx}|{last_total}")
        except Exception as e:
            print(f"\n下载失败: {e}")
            rm_cmd = f"rm -rf \"{temp_remote_path}\""
            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
            stdout.read()
            stderr.read()
            self.transfer_stat = 0
            self._download_progress_cb = None
            return False

        rm_cmd = f"rm -rf \"{temp_remote_path}\""
        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
        stdout.read()
        stderr.read()
        print("远程临时目录已删除")

        # 将本地下载的 temp 目录内容移动到 local_path，去掉多余的一层 temp 目录名
        temp_basename = os.path.basename(temp_remote_path)
        local_temp_dir = f"{local_path}/{temp_basename}"
        if os.path.exists(local_temp_dir):
            for item in os.listdir(local_temp_dir):
                src_item = os.path.join(local_temp_dir, item)
                dst_item = os.path.join(local_path, item)
                # 目标存在则先删除（覆盖）
                if os.path.exists(dst_item):
                    if os.path.isdir(dst_item):
                        shutil.rmtree(dst_item)
                    else:
                        os.remove(dst_item)
                shutil.move(src_item, dst_item)
            # 删除空的 temp 目录
            os.rmdir(local_temp_dir)

        print(f"下载完毕！文件已保存到: {local_path}")
        self.transfer_stat = 0
        self._download_progress_cb = None
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
            raise Exception("传输被中止")
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
            print(f"传输进度: |{bar}|")

            # 传输完成时换行，避免后续输出覆盖
            if progress == 10:
                print()

    def clean_empty_dir(self, sftp, path, f_name=''):
        """将linux目录中的空文件夹删除，如果文件夹的名字包含f_name则不删除，注意需要传入一个已经open的sftp"""
        try:
            dir_list = sftp.listdir(path)
        except Exception as e:
            return
        if len(dir_list) == 0:
            if f_name == '':
                try:
                    sftp.rmdir(path)
                except Exception as e:
                    return
                # 删除之后重新检查上一级目录
                self.clean_empty_dir(sftp, path.rsplit('/', 1)[0], f_name)
            else:
                if not f_name in path.rsplit('/', 1)[1]:
                    sftp.rmdir(path)
                    # 删除之后重新检查上一级目录
                    self.clean_empty_dir(sftp, path.rsplit('/', 1)[0], f_name)
                else:
                    return
        else:
            for item in dir_list:
                self.clean_empty_dir(sftp, path + '/' + item)

    def mkdir(self, path):
        if not self.is_connected():
            print("未连接到服务器，请先连接")
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
            print(f"创建目标目录失败 {path}，原因: {mkdir_err}")
            return False
        return True

