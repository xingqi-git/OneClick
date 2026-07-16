import paramiko
import time
import os
import re
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
        self.transport = None

        self.win_tool = WindowsTools()

    def connect(self):
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.ip, self.port, self.username, self.password)

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

    def send_files(self, local_path, remote_path, mtime=float('inf'), filename='', work_dir=None):
        """
        SSH上传文件
        流程：本地筛选 -> 复制到临时目录 -> 打包 -> SCP上传 -> 服务器端解包 -> 移动到目标目录 -> 清理临时文件
        参数：
            local_path: 本地源路径，可以是文件或文件夹
            work_dir: 服务器端临时目录所在路径，默认为 /home/{username}
            remote_path: 远程目标路径，只能是文件夹
            mtime: 筛选修改时间（秒），只上传在此时间内修改的文件，默认无限大即不限制
            filename: 筛选文件名包含该字符串，默认空字符串即不限制
        返回：
            成功返回True，失败返回False
        中断支持：
            self.transfer_stat = 0 时立即中止传输并清理临时文件
        """
        if not self.is_connected():
            print("未连接到服务器，请先连接")
            return False

        local_path = local_path.replace('\\', '/').rstrip('/')
        remote_path = remote_path.replace('\\', '/').rstrip('/')

        if not os.path.exists(local_path):
            print(f"上传失败，本地路径不存在: {local_path}")
            return False

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
        dir_list = []
        file_list = []

        name = os.path.basename(local_path)
        mtime_val = os.path.getmtime(local_path)
        interval = time_now - mtime_val
        if interval <= mtime and filename in name:
            if os.path.isfile(local_path):
                file_list.append(local_path)
            else:
                dir_list.append(local_path)
        # 源路径是目录，用os.walk遍历，分别收集目录和文件
        for root, dirs, files in os.walk(local_path):
            if self.transfer_stat == 0:
                print('上传被中止！')
                return False
            for name in dirs + files:
                full_path = os.path.join(root, name).replace('\\', '/')
                is_dir = os.path.isdir(full_path)
                mtime_val = os.path.getmtime(full_path)
                interval = time_now - mtime_val
                if interval <= mtime and filename in name:
                    if is_dir:
                        dir_list.append(full_path)
                    else:
                        file_list.append(full_path)

        # 没有符合条件的项，直接返回
        if not dir_list and not file_list:
            print(f"上传完成，未上传任何文件，待上传路径无符合条件的项")
            self.transfer_stat = 0
            return True

        print(f"找到{len(dir_list)}个目录, {len(file_list)}个文件")

        # 提取源路径的基础名，用于保持原目录结构
        local_base = os.path.basename(local_path)
        # 构造服务器临时目录
        base_dir = work_dir if work_dir else f"/home/{self.username}"
        temp_remote_dir = f"{base_dir}/OneClick_temp{local_timestamp_ms}"

        # 收集所有需要创建的目录：dir_list + file_list中所有文件的父目录，保证空目录也能被创建
        all_dirs = set()
        for d in dir_list:
            rel_path = d.replace(os.path.dirname(local_path), '', 1).lstrip('/')
            dst_dir = f"{temp_remote_dir}/{rel_path}"
            all_dirs.add(dst_dir)

        for f in file_list:
            rel_path = f.replace(os.path.dirname(local_path), '', 1).lstrip('/')
            dst_dir = os.path.dirname(f"{temp_remote_dir}/{rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序，这样创建了最长路径后，短路径如果是父路径就可以跳过
        sorted_dirs = sorted(all_dirs, key=lambda x: len(x), reverse=True)
        created_dirs = set()

        print("开始创建服务器临时目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                print('上传被中止！')
                # 清理已创建的临时目录
                rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                self.transfer_stat = 0
                return False

            # 检查当前目录是否是某个已创建目录的父路径，如果是就跳过
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

        # 所有目录创建完成，直接复制文件，不用再创建目录
        file_count = len(file_list)
        print(f"开始上传文件到服务器临时目录，共{file_count}个文件")

        up_count = 0
        for f_path in file_list:
            if self.transfer_stat == 0:
                print('上传被中止！')
                # 清理可能上传了一半的文件
                rm_cmd = f"rm -rf \"{temp_remote_dir}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                self.transfer_stat = 0
                return False

            up_count += 1
            rel_path = f_path.replace(os.path.dirname(local_path), '', 1).lstrip('/')
            dst_path = f"{temp_remote_dir}/{rel_path}"

            try:
                file_size = os.path.getsize(f_path)
                if file_size < 100 * 1024 * 1024:
                    # 不打印进度上传
                    with SCPClient(self.transport) as client:
                        self._last_progress = -1
                        client.put(f_path, dst_path)
                else:
                    print(f"大文件上传: {file_size} 字节")
                    with SCPClient(self.transport, progress=lambda name, size, sent: self._print_progress(sent, file_size)) as client:
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
                print(f"上传到临时目录失败 {up_count}/{file_count}: {f_path} -> {dst_path},原因: {e}")

        # 设置临时目录权限为777
        if self.username != 'root':
            chmod_cmd = f"echo {self.password} | sudo -S chmod -R 777 \"{temp_remote_dir}\""
        else:
            chmod_cmd = f"chmod -R 777 \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(chmod_cmd)
        stdout.read()
        stderr.read()

        print("上传完成，开始移动文件到目标目录...")

        target_path = f"{remote_path}/{local_base}"
        if self.username != 'root':
            # -a 保留文件权限并且递归复制
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

        rm_cmd = f"rm -rf \"{temp_remote_dir}\""
        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
        stdout.read()
        stderr.read()
        print("临时目录已删除")

        print(f"上传完毕！文件已保存到: {target_path}")
        self.transfer_stat = 0
        return True

    def get_files(self, remote_path, local_path, mtime=float('inf'), filename='', work_dir=None):
        """
        SSH下载文件
        流程：服务器端find筛选 -> 复制到临时目录 -> SCP下载 -> 清理临时文件
        性能优化：使用find命令直接在服务器端完成筛选和信息获取，仅需1次exec_command调用
        参数：
            remote_path: 远程源路径，可以是文件或文件夹
            work_dir: 服务器端临时目录所在路径，默认为 /home/{username}
            local_path: 本地目标路径，只能是文件夹
            mtime: 筛选修改时间（秒），只下载在此时间内修改的文件，默认无限大即不限制
            filename: 筛选文件名包含该字符串，默认空字符串即不限制
        返回：
            成功返回True，失败返回False
        中断支持：
            self.transfer_stat = 0 时立即中止传输并清理临时文件
        """
        if not self.is_connected():
            print("未连接到服务器，请先连接")
            return False

        remote_path = remote_path.replace('\\', '/').rstrip('/')
        local_path = local_path.replace('\\', '/').rstrip('/')

        if not os.path.exists(local_path) or not os.path.isdir(local_path):
            print(f"下载失败，本地路径不存在或不是文件夹: {local_path}")
            return False

        if self.username != 'root':
            check_remote_cmd = f"echo {self.password} | sudo -S bash -c 'test -e \"{remote_path}\" && echo exists || echo not exists'"
        else:
            check_remote_cmd = f"bash -c 'test -e \"{remote_path}\" && echo exists || echo not exists'"
        stdin, stdout, stderr = self.ssh.exec_command(check_remote_cmd)
        dir_check_result = stdout.read().decode('utf-8').strip()
        stderr.read()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0 or 'not exists' in dir_check_result:
            print(f"下载失败，远程路径不存在: {remote_path}")
            return False

        # 标记传输状态为进行中
        self.transfer_stat = 1

        # 获取服务器当前时间戳，用于筛选条件
        time_cmd = "date +%s"
        stdin, stdout, stderr = self.ssh.exec_command(time_cmd)
        server_now = stdout.read().decode('utf-8').strip()
        stderr.read()
        
        # 获取本地当前时间戳（精确到毫秒），用于生成唯一临时目录名，避免冲突
        # 使用本地时间避免部分Linux服务器不支持%N参数的问题，同时保证毫秒级精度
        local_timestamp_ms = f"{int(time.time() * 1000)}"

        # 构造远程临时目录路径，放在当前用户home下避免权限问题
        # 构造服务器临时目录
        base_dir = work_dir if work_dir else f"/home/{self.username}"
        temp_remote_path = f"{base_dir}/OneClick_temp{local_timestamp_ms}"
        # 提取远程源路径的基础名并清洗Windows不支持的字符
        remote_base = os.path.basename(remote_path)
        remote_base = re.sub(r'[<>:"/\\|?*]', '-', remote_base)


        print("开始查找符合条件的文件...")
        # 将修改时间阈值从秒转换为分钟，适配find命令的-mmin参数
        mtime_minutes = int(mtime / 60) if mtime != float('inf') else 0

        dir_list = []
        file_list = []

        # 构造sudo前缀，非root用户执行需要权限的命令时自动输入密码
        if self.username != 'root':
            sudo_prefix = f"echo {self.password} | sudo -S "
        else:
            sudo_prefix = ""

        # 根据筛选条件构造find命令，分四种情况：无筛选、仅文件名筛选、仅时间筛选、双重筛选
        if mtime == float('inf') and filename == '':
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f'
        elif mtime == float('inf'):
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -name "*{filename}*"'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -name "*{filename}*"'
        elif filename == '':
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -mmin -{mtime_minutes}'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -mmin -{mtime_minutes}'
        else:
            dir_find_cmd = f'{sudo_prefix}find "{remote_path}" -type d -name "*{filename}*" -mmin -{mtime_minutes}'
            file_find_cmd = f'{sudo_prefix}find "{remote_path}" -type f -name "*{filename}*" -mmin -{mtime_minutes}'

        # 执行查找目录的命令，检查执行状态，失败则终止下载
        stdin, stdout, stderr = self.ssh.exec_command(dir_find_cmd)
        dir_result = stdout.read().decode('utf-8').strip()
        dir_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"查找目录失败: {dir_err}")
            self.transfer_stat = 0
            return False

        # 执行查找文件的命令，检查执行状态，失败则终止下载
        stdin, stdout, stderr = self.ssh.exec_command(file_find_cmd)
        file_result = stdout.read().decode('utf-8').strip()
        file_err = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"查找文件失败: {file_err}")
            self.transfer_stat = 0
            return False

        # 解析目录查找结果，存入dir_list
        if dir_result:
            for line in dir_result.split('\n'):
                if line.strip() and line.startswith('/'):
                    dir_list.append(line.strip())

        # 解析文件查找结果，存入file_list
        if file_result:
            for line in file_result.split('\n'):
                if line.strip() and line.startswith('/'):
                    file_list.append(line.strip())

        # 如果没有找到任何符合条件的目录和文件，清理临时目录后返回
        if not dir_list and not file_list:
            print(f"下载完成，未下载任何文件，待下载路径无符合条件的项")
            rm_cmd = f"rm -rf \"{temp_remote_path}\""
            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
            stdout.read()
            stderr.read()
            self.transfer_stat = 0
            return True

        print(f"找到{len(dir_list)}个目录, {len(file_list)}个文件")

        # 清洗完整路径：所有目录名和文件名中的Windows不支持字符都替换为 -
        def sanitize_path_for_windows(path):
            parts = path.split('/')
            sanitized_parts = [re.sub(r'[<>:"/\\|?*]', '-', part) for part in parts]
            return '/'.join(sanitized_parts)

        # 收集所有需要创建的目录：dir_list + file_list中所有文件的父目录，保证空目录也能被创建
        all_dirs = set()
        for d in dir_list:
            rel_path = d.replace(os.path.dirname(remote_path), '', 1).lstrip('/')
            if rel_path == '':
                continue
            # 清洗路径中的所有目录名
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_dir = f"{temp_remote_path}/{sanitized_rel_path}"
            all_dirs.add(dst_dir)

        for f in file_list:
            rel_path = f.replace(os.path.dirname(remote_path), '', 1).lstrip('/')
            # 清洗完整路径
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_dir = os.path.dirname(f"{temp_remote_path}/{sanitized_rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序，这样创建了最长路径后，短路径如果是父路径就可以跳过
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

            # 检查当前目录是否是某个已创建目录的父路径，如果是就跳过
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

        # 所有目录创建完成，直接复制文件，不用再创建目录
        file_count = len(file_list)
        print(f"开始复制文件到远程临时目录，共{file_count}个文件")

        cp_count = 0
        for file_path in file_list:
            if self.transfer_stat == 0:
                print('下载被中止！')
                rm_cmd = f"rm -rf \"{temp_remote_path}\""
                stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
                stdout.read()
                stderr.read()
                return False

            cp_count += 1
            rel_path = file_path.replace(os.path.dirname(remote_path), '', 1).lstrip('/')
            # 复制前清洗完整路径，避免Windows下载时因特殊字符失败
            sanitized_rel_path = sanitize_path_for_windows(rel_path)
            dst_path = f"{temp_remote_path}/{sanitized_rel_path}"

            if self.username != 'root':
                # -p保留权限、时间复制，但不递归
                cp_cmd = f"echo {self.password} | sudo -S cp -p \"{file_path}\" \"{dst_path}\""
            else:
                cp_cmd = f"cp -p \"{file_path}\" \"{dst_path}\""

            stdin, stdout, stderr = self.ssh.exec_command(cp_cmd)
            cp_err = stderr.read().decode('utf-8').strip()
            stdout.read()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"复制到临时目录失败 {cp_count}/{file_count}: {file_path} -> {dst_path},原因: {cp_err}")
            else:
                print(f"已复制到临时目录 {cp_count}/{file_count}: {file_path} -> {dst_path}")

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

        dst_path = f"{temp_remote_path}/{remote_base}"

        # 多层fallback计算远程文件/目录大小，兼容嵌入式Linux系统
        dst_size = 0
        # 方案1: 尝试用du -sb（标准Linux）
        stdin, stdout, stderr = self.ssh.exec_command(f'du -sb "{dst_path}" 2>/dev/null | awk \'{{print $1}}\'')
        output = stdout.read().decode('utf-8').strip()
        stderr.read()
        if output.isdigit():
            dst_size = int(output)
        else:
            # 方案2: BusyBox du -s，按1024字节/块估算
            stdin, stdout, stderr = self.ssh.exec_command(f'du -s "{dst_path}" 2>/dev/null')
            du_output = stdout.read().decode('utf-8').strip()
            stderr.read()
            output = du_output.split()[0] if du_output else ''
            if output.isdigit():
                dst_size = int(output) * 1024  # 估算每块1024字节
            else:
                # 方案3: 用find + wc -c逐个统计文件大小
                stdin, stdout, stderr = self.ssh.exec_command(f'find "{dst_path}" -type f -exec wc -c {{}} \\; 2>/dev/null | awk \'{{sum+=$1}} END {{print sum}}\'')
                output = stdout.read().decode('utf-8').strip()
                stderr.read()
                if output.isdigit():
                    dst_size = int(output)
        
        if dst_size > 0:
            print(f"开始下载，大小: {dst_size/1048576:.2f} M")
        else:
            print(f"开始下载（无法获取大小）")

        try:
            with SCPClient(self.transport, progress=lambda name, size, sent: self._print_progress(sent, dst_size)) as client:
                if self.transfer_stat == 0:
                    raise Exception("下载被中止")
                self._last_progress = -1
                client.get(dst_path, local_path, recursive=True)
        except Exception as e:
            print(f"\n下载失败: {e}")
            # 清理可能下载了一半的文件
            local_tar = f"{local_path}/{remote_base}"
            if os.path.exists(local_tar):
                os.remove(local_tar)
            rm_cmd = f"rm -rf \"{temp_remote_path}\""
            stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
            stdout.read()
            stderr.read()
            self.transfer_stat = 0
            return False

        rm_cmd = f"rm -rf \"{temp_remote_path}\""
        stdin, stdout, stderr = self.ssh.exec_command(rm_cmd)
        stdout.read()
        stderr.read()
        print("远程临时目录已删除")
        print(f"下载完毕！文件已保存到: {local_path}/{remote_base}")
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

    def compress_file(self, source_path):
        if self.is_connected():
            source_path = source_path.replace('\\', '/')
            source_path = source_path.rstrip('/')
            # 构建压缩命令，使用tar创建gz压缩包
            # -czf 表示创建压缩文件、使用gzip压缩、指定文件名
            # 建立sftp通道协议
            try:
                sftp = self.ssh.open_sftp()
            except Exception as e:
                print(f"sftp出错：{e}")
                return
            # 首先判断远端路径是否存在，不存在直接返回
            try:
                sftp.stat(source_path)
            except FileNotFoundError:
                print("远端路径不存在，请检查")
                return
            target_tar = source_path
            command = f"tar -zcvPf {target_tar}.tar.gz -C {source_path[::-1].replace('/', ' ', 1)[::-1]}"
            self.send_command(command)
            print(f'压缩完成{source_path} -> {target_tar}.tar.gz')
        else:
            print("未连接到服务器，请先连接")

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

if __name__ == '__main__':
    pass
