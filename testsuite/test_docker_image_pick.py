# coding: utf-8
import os
import sys
import time
import json
import shutil
import unittest
import importlib

# 将根目录和 web/core 添加入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'web'))
sys.path.insert(0, os.path.join(BASE_DIR, 'plugins', 'docker'))

import core.yf as yf

# 导入插件的 index.py
docker_index = importlib.import_module("plugins.docker.index")

class TestDockerImagePick(unittest.TestCase):

    def setUp(self):
        # 准备临时的测试 backup/docker 目录
        self.father_dir = yf.getFatherDir()
        self.test_bk_dir = os.path.join(self.father_dir, 'backup', 'docker')
        os.makedirs(self.test_bk_dir, exist_ok=True)

        # 记录原有文件，测试后恢复
        self.original_files = os.listdir(self.test_bk_dir)
        self.created_test_items = []

    def tearDown(self):
        # 清理测试期间创建的文件
        for item in self.created_test_items:
            path = os.path.join(self.test_bk_dir, item)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_01_filter_and_sort_in_list(self):
        """测试 dockerImagePickList 是否能精准过滤非镜像文件并按时间倒序排列"""
        # 1. 制造非镜像文件（完全对齐用户截图中的文件名）
        garbage_files = [
            "__copy__1 (1).json",
            "2.sh",
            "3.md",
            "1 (1).txt",
            "1.py",
            ".hidden.tar"
        ]
        for g_file in garbage_files:
            p = os.path.join(self.test_bk_dir, g_file)
            with open(p, 'w', encoding='utf-8') as f:
                f.write("dummy content")
            self.created_test_items.append(g_file)

        # 2. 制造一个子目录（即使扩展名伪装成 .tar，也应该被过滤）
        fake_dir = "fake_folder.tar"
        os.makedirs(os.path.join(self.test_bk_dir, fake_dir), exist_ok=True)
        self.created_test_items.append(fake_dir)

        # 3. 制造合法镜像归档包，并人工设置不同的修改时间
        now = time.time()
        valid_archives = [
            ("arch_old.tar", now - 300),
            ("arch_mid.tar.gz", now - 150),
            ("arch_new.tgz", now)
        ]
        for fname, mtime in valid_archives:
            p = os.path.join(self.test_bk_dir, fname)
            with open(p, 'wb') as f:
                f.write(b"tar fake binary content")
            os.utime(p, (mtime, mtime))
            self.created_test_items.append(fname)

        # 4. 调用接口
        res_json = docker_index.dockerImagePickList()
        res = json.loads(res_json)

        self.assertTrue(res['status'])
        ret_data = res['data']
        ret_names = [item['name'] for item in ret_data]

        # 5. 校验过滤结果：所有杂项文件和目录严禁出现
        for g_file in garbage_files:
            self.assertNotIn(g_file, ret_names, f"杂项文件 {g_file} 未被过滤！")
        self.assertNotIn(fake_dir, ret_names, f"子目录 {fake_dir} 未被过滤！")

        # 6. 校验合法镜像包都存在
        for fname, _ in valid_archives:
            self.assertIn(fname, ret_names, f"合法镜像包 {fname} 未能正确列出！")

        # 7. 校验时间倒序（最新的在前）
        expected_order = ["arch_new.tgz", "arch_mid.tar.gz", "arch_old.tar"]
        self.assertEqual(ret_names[:3], expected_order, "列表未按修改时间倒序排列！")
        print(">> test_01_filter_and_sort_in_list 通过: 杂质文件与目录100%过滤，排序正确")

    def test_02_load_validation_and_no_silent_failure(self):
        """测试 dockerImagePickLoad 拒绝非镜像文件，彻底杜绝假成功"""
        # 创建一个非镜像文件
        bad_file = "test_script.sh"
        bad_path = os.path.join(self.test_bk_dir, bad_file).replace('\\', '/')
        with open(bad_path, 'w', encoding='utf-8') as f:
            f.write("#!/bin/bash\necho hello")
        self.created_test_items.append(bad_file)

        # 模拟调用导入
        # 设置全局 args
        def mock_get_args():
            return {'file': bad_path}
        
        orig_get_args = docker_index.getArgs
        try:
            docker_index.getArgs = mock_get_args
            res_json = docker_index.dockerImagePickLoad()
            res = json.loads(res_json)
            # 必须返回 False，严禁返回 True
            self.assertFalse(res['status'], "非镜像文件导入必须失败，不能出现假成功！")
            self.assertIn("不支持的文件格式", res['msg'])
            print(">> test_02_load_validation_and_no_silent_failure 通过: 非镜像文件被正确拦截")
        finally:
            docker_index.getArgs = orig_get_args

    def test_03_load_path_traversal_defense(self):
        """测试 dockerImagePickLoad 针对路径穿越攻击的防护"""
        def mock_get_args():
            return {'file': '../../../../etc/passwd'}

        orig_get_args = docker_index.getArgs
        try:
            docker_index.getArgs = mock_get_args
            res_json = docker_index.dockerImagePickLoad()
            res = json.loads(res_json)
            self.assertFalse(res['status'])
            self.assertTrue("非法的镜像文件路径" in res['msg'] or "校验失败" in res['msg'])
            print(">> test_03_load_path_traversal_defense 通过: 路径遍历被安全拦截")
        finally:
            docker_index.getArgs = orig_get_args

    def test_04_save_arguments_and_multi_image_quoting(self):
        """测试 dockerImagePickSave 空参数拦截与多镜像参数拆分转义"""
        # 1. 测试空参数
        docker_index.getArgs = lambda: {'images': '   '}
        res_empty = json.loads(docker_index.dockerImagePickSave())
        self.assertFalse(res_empty['status'])
        self.assertIn("至少选择一个", res_empty['msg'])

        # 2. 测试多镜像参数拼接
        # 截获 yf.execShell 验证执行的命令
        captured_cmd = []
        def mock_exec_shell(cmd):
            captured_cmd.append(cmd)
            # 模拟创建生成的空文件以走通流程，测试完删除
            # 这里只需检查 cmd 即可
            return ("", "Error: fake test stop")

        orig_exec = yf.execShell
        try:
            yf.execShell = mock_exec_shell
            docker_index.getArgs = lambda: {'images': 'nginx:latest redis:alpine ubuntu:22.04'}
            docker_index.dockerImagePickSave()

            self.assertTrue(len(captured_cmd) > 0)
            actual_cmd = captured_cmd[0]
            # 验证多镜像命令不是单引号包住全部，而是每个镜像分别独立转义
            self.assertIn("docker image save ", actual_cmd)
            # 应该包含分别的镜像名
            self.assertIn("nginx:latest", actual_cmd)
            self.assertIn("redis:alpine", actual_cmd)
            self.assertIn("ubuntu:22.04", actual_cmd)
            # 绝不能是 'nginx:latest redis:alpine ubuntu:22.04' 整体
            self.assertNotIn("'nginx:latest redis:alpine ubuntu:22.04'", actual_cmd)
            print(">> test_04_save_arguments_and_multi_image_quoting 通过: 多镜像独立安全转义拼装正常")
        finally:
            yf.execShell = orig_exec

if __name__ == '__main__':
    unittest.main()
