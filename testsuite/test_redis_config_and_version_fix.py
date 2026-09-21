# coding:utf-8

import os
import sys
import unittest
import tempfile
import shutil
import json
import re

# 注入面板路径
test_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(test_dir)
web_dir = os.path.join(project_dir, 'web')
plugins_dir = os.path.join(project_dir, 'plugins')
redis_dir = os.path.join(plugins_dir, 'redis')

if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if redis_dir not in sys.path:
    sys.path.insert(0, redis_dir)

import core.yf as yf
import plugins.redis.index as redis_plugin


class TestRedisConfigAndVersionFix(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_redis_cfg_')
        self.orig_server_dir = redis_plugin.getServerDir()
        self.orig_plugin_dir = redis_plugin.getPluginDir()

        # 构造沙箱 serverDir
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)
        os.makedirs(os.path.join(self.sandbox_server, 'bin'), exist_ok=True)

        redis_plugin.getServerDir = lambda: self.sandbox_server

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_getArgs_json_no_version(self):
        """测试单版本调用 (sys.argv[2] 为 JSON 参数字典)，杜绝 '参数:(file)没有!'"""
        sample_args = json.dumps({'file': 'test_simple.conf', 'port': '6379'})
        saved_argv = sys.argv
        try:
            # 模拟 web/utils/plugin.py: [python, index.py, read_config_tpl, args]
            sys.argv = ['index.py', 'read_config_tpl', sample_args]
            args = redis_plugin.getArgs()
            self.assertEqual(args.get('file'), 'test_simple.conf')
            self.assertEqual(args.get('port'), '6379')

            check_res = redis_plugin.checkArgs(args, ['file'])
            self.assertTrue(check_res[0], "单版本传参检查 file 参数必须通过")
        finally:
            sys.argv = saved_argv

    def test_02_getArgs_json_with_version(self):
        """测试多版本调用 (sys.argv[2]=version, sys.argv[3]=JSON args)"""
        sample_args = json.dumps({'file': 'test_cluster.conf', 'bind': '127.0.0.1'})
        saved_argv = sys.argv
        try:
            sys.argv = ['index.py', 'read_config_tpl', '7.0.15', sample_args]
            args = redis_plugin.getArgs()
            self.assertEqual(args.get('file'), 'test_cluster.conf')
            self.assertEqual(args.get('bind'), '127.0.0.1')
        finally:
            sys.argv = saved_argv

    def test_03_getArgs_key_value_pairs(self):
        """测试 CLI 键值对传参 (k=v 格式与带版本格式)"""
        saved_argv = sys.argv
        try:
            sys.argv = ['index.py', 'submit_redis_conf', 'bind=127.0.0.1', 'port=6380']
            args = redis_plugin.getArgs()
            self.assertEqual(args.get('bind'), '127.0.0.1')
            self.assertEqual(args.get('port'), '6380')

            sys.argv = ['index.py', 'submit_redis_conf', '7.0.15', 'bind=0.0.0.0', 'port=6381']
            args2 = redis_plugin.getArgs()
            self.assertEqual(args2.get('bind'), '0.0.0.0')
            self.assertEqual(args2.get('port'), '6381')
        finally:
            sys.argv = saved_argv

    def test_04_getRedisConfInfo_robust_parsing(self):
        """测试性能调整读取：支持行首缩进、IPv6、带引号的复杂密码、行尾注释及 mb 去除"""
        conf_content = """
# Redis 示例配置文件
  bind 127.0.0.1 -::1
port 6379 # 监听端口
timeout 300
maxclients 10000
databases 16
requirepass "Secret@Pass#2026!"
maxmemory 4096mb
"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, conf_content)

        info = redis_plugin.getRedisConfInfo()
        info_dict = {item['name']: item['value'] for item in info}

        self.assertEqual(info_dict.get('bind'), '127.0.0.1 -::1', "bind 应正确解析包含 IPv6 -::1")
        self.assertEqual(info_dict.get('port'), '6379', "port 应去除行尾注释")
        self.assertEqual(info_dict.get('timeout'), '300')
        self.assertEqual(info_dict.get('maxclients'), '10000')
        self.assertEqual(info_dict.get('databases'), '16')
        self.assertEqual(info_dict.get('requirepass'), 'Secret@Pass#2026!', "密码应正确剥离两端引号并保留特殊符号")
        self.assertEqual(info_dict.get('maxmemory'), '4096', "maxmemory 应自动剥离 mb 后缀")

    def test_05_submitRedisConf_update_and_append(self):
        """测试保存配置：更新现有配置、安全字符密码、新配置项追加"""
        init_conf = """
bind 127.0.0.1
port 6379
#requirepass ""
"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, init_conf)

        # 模拟 reload 为 no-op
        redis_plugin.reload = lambda: 'ok'

        saved_argv = sys.argv
        try:
            update_payload = json.dumps({
                'bind': '127.0.0.1 -::1',
                'port': '6380',
                'timeout': '120',
                'maxclients': '20000',
                'databases': '32',
                'requirepass': 'MySecurePass_2026@#',
                'maxmemory': '2048'
            })
            sys.argv = ['index.py', 'submit_redis_conf', update_payload]
            res_str = redis_plugin.submitRedisConf()
            res = json.loads(res_str)
            self.assertTrue(res.get('status'), f"submitRedisConf 应该执行成功: {res_str}")

            # 验证写入后的配置
            new_info = redis_plugin.getRedisConfInfo()
            new_dict = {item['name']: item['value'] for item in new_info}

            self.assertEqual(new_dict.get('bind'), '127.0.0.1 -::1')
            self.assertEqual(new_dict.get('port'), '6380')
            self.assertEqual(new_dict.get('timeout'), '120')
            self.assertEqual(new_dict.get('maxclients'), '20000')
            self.assertEqual(new_dict.get('databases'), '32')
            self.assertEqual(new_dict.get('requirepass'), 'MySecurePass_2026@#')
            self.assertEqual(new_dict.get('maxmemory'), '2048')

            # 测试清空密码
            clear_pass_payload = json.dumps({'requirepass': ''})
            sys.argv = ['index.py', 'submit_redis_conf', clear_pass_payload]
            redis_plugin.submitRedisConf()
            after_clear_info = redis_plugin.getRedisConfInfo()
            after_clear_dict = {item['name']: item['value'] for item in after_clear_info}
            self.assertEqual(after_clear_dict.get('requirepass'), '', "清空密码后读取应为空")
        finally:
            sys.argv = saved_argv

    def test_06_detectAndFixConf_fallback(self):
        """测试配置多源自愈：当 redis.conf 缺失时从模板自愈初始化"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        if os.path.exists(conf_path):
            os.remove(conf_path)

        res_conf = redis_plugin.detectAndFixConf()
        self.assertTrue(os.path.exists(res_conf), "自愈后配置文件必须存在")
        self.assertGreater(os.path.getsize(res_conf), 50, "自愈后的配置文件必须具备有效初始内容")

    def test_07_detectAndFixVersion(self):
        """测试版本自愈探测：若已持久化直接读取，缺失时能安全自愈探测并写回 version.pl"""
        version_pl = os.path.join(self.sandbox_server, 'version.pl')
        if os.path.exists(version_pl):
            os.remove(version_pl)

        # 模拟探测函数返回一个版本并写回
        ver = redis_plugin.detectAndFixVersion()
        self.assertTrue(len(ver) > 0, "应能探测或兜底拿到版本号")
        self.assertTrue(os.path.exists(version_pl), "探测成功后应自动持久化写入 version.pl")
        self.assertEqual(yf.readFile(version_pl).strip(), ver)


if __name__ == '__main__':
    unittest.main()
