import os
import time
import shutil

from utils.logger import get_logger

logger = get_logger("windows")


class WindowsTools(object):
    def __init__(self):
        self.transfer_stat = 0

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
                # 任意一个包含就排除
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

    def copy_files(self, source_items, target_path, progress_cb=None):
        """
        复制本地文件（支持多源路径，每条独立筛选）
        参数：
            source_items: 源路径列表，每项为 dict：
                {
                    '路径': '源路径',
                    '修改时间': '全部'/'最近30分钟'/'最近1小时'/'最近2小时'/'最近1天'/'最近1月'/'最近1年',
                    '名称包含': {'关键词': [], '逻辑': '和'/'或'},
                    '名称不包含': {'关键词': [], '逻辑': '和'/'或'}
                }
            target_path: 目的路径
            progress_cb: 进度回调 (phase, cur, total, extra)
        """
        mtime_dic = {
            "全部": float('inf'),
            "最近30分钟": 1800,
            "最近1小时": 3600,
            "最近2小时": 7200,
            "最近1天": 86400,
            "最近1月": 2592000,
            "最近1年": 31536000
        }

        target_path = target_path.replace('\\', '/').rstrip('/')
        if not os.path.exists(target_path):
            logger.error(f"复制失败，目的路径不存在: {target_path}")
            return False

        self.transfer_stat = 1
        time_now = time.time()

        # 逐条源路径筛选，收集所有目录和文件
        all_dir_list = []
        all_file_list = []
        source_roots = {}  # file/dir path -> source root (用于计算相对路径)

        for item in source_items:
            if self.transfer_stat == 0:
                logger.warning('复制被中止！')
                return False

            src_path = item['路径']
            mtime_str = item.get('修改时间', '全部')
            mtime_seconds = mtime_dic.get(mtime_str, float('inf'))
            include_info = item.get('名称包含', {}) or {}
            include_keywords = include_info.get('关键词', []) or []
            include_logic = include_info.get('逻辑', '或') or '或'
            exclude_info = item.get('名称不包含', {}) or {}
            exclude_keywords = exclude_info.get('关键词', []) or []
            exclude_logic = exclude_info.get('逻辑', '和') or '和'

            dir_list, file_list = self._filter_source_path(
                src_path, mtime_seconds, include_keywords, include_logic,
                exclude_keywords, exclude_logic, time_now
            )

            src_root = src_path if os.path.isdir(src_path) else os.path.dirname(src_path)
            for d in dir_list:
                all_dir_list.append(d)
                source_roots[d] = src_root
            for f in file_list:
                all_file_list.append(f)
                source_roots[f] = src_root

        # 没有符合条件的项，直接返回
        if not all_dir_list and not all_file_list:
            logger.info(f"复制完成，未复制任何文件，无符合条件的项")
            self.transfer_stat = 0
            if progress_cb:
                progress_cb('find', 0, 0, '找到0个文件')
            return True

        logger.debug(f"找到{len(all_dir_list)}个目录, {len(all_file_list)}个文件")
        if progress_cb:
            total_files = len(all_file_list)
            progress_cb('find', 0, total_files, f'找到{total_files}个文件')

        # 收集所有需要创建的目录
        all_dirs = set()
        for d in all_dir_list:
            src_root = source_roots.get(d, os.path.dirname(d))
            rel_path = d.replace(src_root, '', 1).lstrip('/')
            dst_dir = f"{target_path}/{rel_path}"
            all_dirs.add(dst_dir)

        for f in all_file_list:
            src_root = source_roots.get(f, os.path.dirname(f))
            rel_path = f.replace(src_root, '', 1).lstrip('/')
            dst_dir = os.path.dirname(f"{target_path}/{rel_path}")
            all_dirs.add(dst_dir)

        # 按路径长度从长到短排序，这样创建了最长路径后，短路径如果是父路径就可以跳过
        sorted_dirs = sorted(all_dirs, key=lambda x: len(x), reverse=True)
        created_dirs = set()

        logger.debug(f"开始创建目录")
        for dst_dir in sorted_dirs:
            if self.transfer_stat == 0:
                logger.warning('复制被中止！')
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
        file_count = len(all_file_list)
        logger.debug(f"开始复制文件到目的目录，共{file_count}个文件")

        failed_files = []
        cp_count = 0
        total_size = 0
        copied_size = 0
        file_sizes = {}

        # 先计算总大小
        for f_path in all_file_list:
            try:
                sz = os.path.getsize(f_path)
                file_sizes[f_path] = sz
                total_size += sz
            except OSError:
                file_sizes[f_path] = 0

        for f_path in all_file_list:
            if self.transfer_stat == 0:
                logger.warning('复制被中止！')
                return False

            cp_count += 1
            src_root = source_roots.get(f_path, os.path.dirname(f_path))
            rel_path = f_path.replace(src_root, '', 1).lstrip('/')
            dst_path = f"{target_path}/{rel_path}"

            try:
                # copy2保留文件元数据（修改时间、权限等）
                shutil.copy2(f_path, dst_path)
                f_size = file_sizes.get(f_path, 0)
                copied_size += f_size
                f_name = os.path.basename(f_path)
                size_mb = f_size / (1024 * 1024) if f_size > 0 else 0
                total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                if progress_cb and total_size > 0:
                    total_pct = int(copied_size / total_size * 100)
                    progress_cb('copy', total_pct, file_count,
                                f'总进度{total_pct}% (共{total_mb:.1f}MB)  文件{cp_count}/{file_count}: {f_name} 100% ({size_mb:.1f}MB)')
                logger.debug(f"已复制 {cp_count}/{file_count}: {f_path} -> {dst_path}")
            except Exception as e:
                failed_files.append((f_path, str(e)))
                logger.error(f"复制失败 {cp_count}/{file_count}: {f_path} -> {dst_path},原因: {e}")

        # 打印失败汇总
        if failed_files:
            logger.error(f"复制失败{len(failed_files)}个文件：")
            for i, (f, reason) in enumerate(failed_files, 1):
                logger.error(f"  {i}. {f} - {reason}")

        # 最后补一次100%进度
        if progress_cb and total_size > 0 and cp_count > 0:
            total_mb = total_size / (1024 * 1024)
            last_name = os.path.basename(all_file_list[-1])
            progress_cb('copy', 100, file_count,
                        f'总进度100% (共{total_mb:.1f}MB)  文件{file_count}/{file_count}: {last_name} 100%')

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
