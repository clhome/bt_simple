# coding:utf-8
import os
import sys
import unittest
import shutil
import time

# 设置运行环境
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)
web_dir = os.path.join(root_dir, 'web')
sys.path.insert(0, web_dir)
sys.path.insert(0, os.path.join(web_dir, 'core'))

import core.yf as yf
import utils.file as file_util
import utils.task as task_util
import panel_task

class TestP1DeepReliabilityPerf(unittest.TestCase):

    def setUp(self):
        self.test_tmp = os.path.join(root_dir, 'tmp', 'test_p1_rel')
        os.makedirs(self.test_tmp, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_tmp):
            shutil.rmtree(self.test_tmp, ignore_errors=True)

    def test_01_atomic_write_file(self):
        """验证全局 writeFile 原子写入与抗截断保护"""
        target_file = os.path.join(self.test_tmp, 'important_config.json')
        initial_content = '{"server": "running", "status": 1}'
        
        # 1. 初始写入
        res = yf.writeFile(target_file, initial_content)
        self.assertTrue(res)
        self.assertEqual(yf.readFile(target_file), initial_content)

        # 2. 模拟原子更新成功
        updated_content = '{"server": "running", "status": 2, "updated": true}'
        res = yf.writeFile(target_file, updated_content)
        self.assertTrue(res)
        self.assertEqual(yf.readFile(target_file), updated_content)

        # 3. 验证目录下无残留的临时文件
        files = os.listdir(self.test_tmp)
        tmp_files = [f for f in files if '.tmp.' in f]
        self.assertEqual(len(tmp_files), 0, "原子写入后不应遗留临时文件")

    def test_02_os_scandir_get_dir_list(self):
        """验证基于 os.scandir 的大目录加载性能与排序准确性"""
        # 创建 20 个测试文件
        for i in range(20):
            fname = os.path.join(self.test_tmp, f"test_item_{i:02d}.txt")
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(f"content {i}")

        # 创建 3 个子目录
        for d in ['dir_alpha', 'dir_beta', 'dir_gamma']:
            os.makedirs(os.path.join(self.test_tmp, d), exist_ok=True)

        # 1. 测试分页读取第一页 (size=10)
        page1 = file_util.getDirList(self.test_tmp, page=1, size=10, order='fname asc')
        self.assertEqual(page1['count'], 23)  # 20 个文件 + 3 个目录
        self.assertEqual(len(page1['dir']) + len(page1['files']), 10)

        # 2. 测试搜索过滤
        search_res = file_util.getDirList(self.test_tmp, page=1, size=10, search='alpha')
        self.assertEqual(search_res['count'], 1)
        self.assertEqual(len(search_res['dir']), 1)
        self.assertEqual(search_res['dir'][0].split(';')[0], 'dir_alpha')

        # 3. 测试 sortFileList 排序一致性
        flist = yf.sortFileList(self.test_tmp, ftype='fname', sort='asc')
        self.assertEqual(len(flist), 23)
        self.assertTrue(flist[0] <= flist[1])

    def test_03_download_protocol_security(self):
        """验证远程下载接口严格拦截 file:// 等非安全协议"""
        # 1. 尝试使用 file:// 协议读取本地文件
        res = panel_task.downloadFile('file:///etc/shadow', os.path.join(self.test_tmp, 'leak.txt'))
        self.assertFalse(res, "必须拦截 file:// 协议下载")
        self.assertFalse(os.path.exists(os.path.join(self.test_tmp, 'leak.txt')))

        # 2. 尝试使用 gopher://
        res2 = panel_task.downloadFile('gopher://127.0.0.1:6379/_INFO', os.path.join(self.test_tmp, 'gopher.txt'))
        self.assertFalse(res2, "必须拦截 gopher:// 协议")

    def test_04_task_pid_management(self):
        """验证任务取消优先按子进程 PID 机制精确处理"""
        cur_task_pid_file = os.path.join(yf.getPanelDir(), 'tmp', 'panel_task_sub.pid')
        try:
            # 模拟正在运行任务 999，PID 88888
            os.makedirs(os.path.dirname(cur_task_pid_file), exist_ok=True)
            with open(cur_task_pid_file, 'w', encoding='utf-8') as f:
                f.write("999:88888")

            # 模拟取消非当前运行的任务 (例如 888)
            task_util.removeTask('888')
            # pid 文件应该仍在，因为运行中的是 999
            self.assertTrue(os.path.exists(cur_task_pid_file))

            # 模拟取消当前运行任务 999
            task_util.removeTask('999')
            # 验证 pid 文件已被处理清理
            self.assertFalse(os.path.exists(cur_task_pid_file))
        finally:
            if os.path.exists(cur_task_pid_file):
                try:
                    os.remove(cur_task_pid_file)
                except:
                    pass

if __name__ == '__main__':
    unittest.main()
