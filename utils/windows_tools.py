import os
import time
import shutil


class WindowsTools(object):
    def __init__(self):
        self.transfer_stat = 0

    def filter_files(self, local_path, mtime=float('inf'), filename=''):

        local_path = local_path.replace('\\', '/').rstrip('/')

        if not os.path.exists(local_path):
            print(f"筛选失败，本地路径不存在: {local_path}")
            return False

        self.transfer_stat = 1

        print("开始查找符合条件的文件...")
        time_now = time.time()
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
                print('筛选被中止！')
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
            print(f"筛选完成，无符合条件的项")
            self.transfer_stat = 0
            return True

        print(f"找到{len(dir_list)}个目录, {len(file_list)}个文件")
        return dir_list, file_list

    def copy_files(self, source_path, target_path, mtime=float('inf'), filename=''):
        source_path = source_path.replace('\\', '/').rstrip('/')
        target_path = target_path.replace('\\', '/').rstrip('/')
        if not os.path.exists(source_path):
            print(f"复制失败，源路径不存在: {source_path}")
            return False

        if not os.path.exists(target_path):
            print(f"复制失败，目的路径不存在: {target_path}")
            return False

        dir_list, file_list = self.filter_files(source_path, mtime, filename)
        # 没有符合条件的项，直接返回
        if not dir_list and not file_list:
            print(f"复制完成，未复制任何文件，无符合条件的项")
            self.transfer_stat = 0
            return True

        # 收集所有需要创建的目录：dir_list + file_list中所有文件的父目录，保证空目录也能被创建
        all_dirs = set()
        for d in dir_list:
            rel_path = d.replace(os.path.dirname(source_path), '', 1).lstrip('/')
            dst_dir = f"{target_path}/{rel_path}"
            all_dirs.add(dst_dir)

        for f in file_list:
            rel_path = f.replace(os.path.dirname(source_path), '', 1).lstrip('/')
            dst_dir = os.path.dirname(f"{target_path}/{rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序，这样创建了最长路径后，短路径如果是父路径就可以跳过
        sorted_dirs = sorted(all_dirs, key=lambda x: len(x), reverse=True)
        created_dirs = set()

        print(f"开始创建目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                print('复制被中止！')
                shutil.rmtree(target_path, ignore_errors=True)
                return False

            # 检查当前目录是否是某个已创建目录的父路径，如果是就跳过
            need_create = True
            for created in created_dirs:
                if created.startswith(dst_dir + '/'):
                    need_create = False
                    break

            if need_create:
                os.makedirs(dst_dir, exist_ok=True)
                created_dirs.add(dst_dir)

        # 所有目录创建完成，直接复制文件，不用再创建目录
        file_count = len(file_list)
        print(f"开始复制文件到本地目的目录，共{file_count}个文件")

        cp_count = 0
        for f_path in file_list:
            if self.transfer_stat == 0:
                print('上传被中止！')
                shutil.rmtree(target_path, ignore_errors=True)
                return False

            cp_count += 1
            rel_path = f_path.replace(os.path.dirname(source_path), '', 1).lstrip('/')
            dst_path = f"{target_path}/{rel_path}"

            try:
                # copy2保留文件元数据（修改时间、权限等）
                shutil.copy2(f_path, dst_path)
                print(f"已复制到临时目录 {cp_count}/{file_count}: {f_path} -> {dst_path}")
            except Exception as e:
                print(f"复制到临时目录失败 {cp_count}/{file_count}: {f_path} -> {dst_path},原因: {e}")
        self.transfer_stat = 0
        return True

    def clean_empty_dir(self, path, f_name=''):
        """将windows目录中的空文件夹删除，如果文件夹的名字包含f_name则不删除"""
        path = path.replace('\\', '/')
        path = path.rstrip('/')
        try:
            dir_list = os.listdir(path)
        except Exception as e:
            return
        if len(dir_list) == 0:
            if f_name == '':
                os.rmdir(path)
                # 删除之后重新检查上一级目录
                self.clean_empty_dir(path.rsplit('/', 1)[0], f_name)
            else:
                if not f_name in path.rsplit('/', 1)[1]:
                    os.rmdir(path)
                    # 删除之后重新检查上一级目录
                    self.clean_empty_dir(path.rsplit('/', 1)[0], f_name)
                else:
                    return
        else:
            for item in dir_list:
                self.clean_empty_dir(path + '/' + item, f_name)

if __name__ == '__main__':
    pass
