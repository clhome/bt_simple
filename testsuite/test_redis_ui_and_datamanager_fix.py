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
data_query_dir = os.path.join(plugins_dir, 'data_query')

for p in [project_dir, web_dir, redis_dir, data_query_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf
import plugins.redis.index as redis_plugin
import plugins.data_query.nosql_redis as nosql_redis


class TestRedisUIAndDataManagerFix(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_redis_ui_')
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)
        os.makedirs(os.path.join(self.sandbox_server, 'bin'), exist_ok=True)
        os.makedirs(os.path.join(self.sandbox_server, 'data'), exist_ok=True)

        redis_plugin.getServerDir = lambda: self.sandbox_server
        nosql_redis.yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_getRedisCmd_with_complex_pass_and_port(self):
        """测试 getRedisCmd 与 getPort 对复杂密码（含引号、#）和端口注释的准确解析"""
        conf_content = """
bind 127.0.0.1 -::1
port 6380 # 自定义端口
requirepass "My@Complex#Pass!2026"
"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, conf_content)

        port = redis_plugin.getPort()
        self.assertEqual(port, '6380', "端口应正确剥离行尾注释")

        cmd = redis_plugin.getRedisCmd()
        self.assertIn('-p 6380', cmd)
        self.assertIn('-a "My@Complex#Pass!2026"', cmd, "密码应完整提取并保留特殊字符与安全包裹")
        self.assertIn('--no-auth-warning', cmd)

    def test_02_runInfo_parsing_and_noauth_capture(self):
        """测试 runInfo 数据解析与 NOAUTH 捕获，杜绝 undefined"""
        # 1. 模拟 Redis 正常输出 info
        mock_info_output = """
# Server
redis_version:7.0.15
tcp_port:6379
uptime_in_days:12
connected_clients:5
used_memory:1048576
used_memory_rss:2097152
used_memory_peak:3145728
mem_fragmentation_ratio:1.25
total_connections_received:100
total_commands_processed:5000
instantaneous_ops_per_sec:10
keyspace_hits:800
keyspace_misses:200
latest_fork_usec:150
"""
        redis_plugin.status = lambda: 'start'
        redis_plugin.yf.execShell = lambda cmd: (mock_info_output, '')

        res_json = redis_plugin.runInfo()
        res = json.loads(res_json)
        self.assertEqual(res.get('tcp_port'), '6379')
        self.assertEqual(res.get('uptime_in_days'), '12')
        self.assertEqual(res.get('connected_clients'), '5')
        self.assertEqual(res.get('keyspace_hits'), '800')

        # 2. 模拟密码未认证拦截
        redis_plugin.yf.execShell = lambda cmd: ('(error) NOAUTH Authentication required.', '')
        res_noauth_json = redis_plugin.runInfo()
        res_noauth = json.loads(res_noauth_json)
        self.assertFalse(res_noauth.get('status'), "未认证时应明确返回 status: False")
        self.assertIn('requirepass', res_noauth.get('msg', ''))

    def test_03_runLog_dynamic_detection_and_empty_self_healing(self):
        """测试 runLog 动态解析 logfile 与空日志自动自愈"""
        custom_log = os.path.join(self.sandbox_server, 'data', 'custom_redis.log')
        conf_content = f"""
logfile "{custom_log}"
"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, conf_content)

        detected_log = redis_plugin.runLog()
        self.assertEqual(os.path.abspath(detected_log), os.path.abspath(custom_log))
        self.assertTrue(os.path.exists(detected_log), "自愈机制应保证日志文件真实存在")
        self.assertGreater(os.path.getsize(detected_log), 0, "空日志应自愈生成初始化记录")

    def test_04_data_query_host_and_pass_sanitization(self):
        """测试 Data Manager 过滤 IPv6 -::1 并剥离双引号密码"""
        conf_content = """
bind 127.0.0.1 -::1
port 6379
requirepass "YomlixYx2026!"
"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, conf_content)

        # 实例化 nosqlRedisCtr
        ctr = nosql_redis.nosqlRedisCtr()
        ins = ctr.getInstanceBySid(0)

        # 检查内部解析的 Host 和 Password
        opts = ins.get_options(sid=0)
        self.assertEqual(opts.get('port'), 6379)
        self.assertEqual(opts.get('requirepass'), 'YomlixYx2026!', "密码中的外层双引号必须被剥离")

        # 验证 setSid 规范化 Host
        ins.setSid(0)
        self.assertEqual(getattr(ins, '_nosqlRedis__DB_HOST'), '127.0.0.1', "IPv6 -::1 必须被规范为 127.0.0.1")
        self.assertEqual(getattr(ins, '_nosqlRedis__DB_PASS'), 'YomlixYx2026!')

    def test_05_data_query_error_diagnostics(self):
        """测试 Data Manager 连接失败时提供详尽诊断信息（驱动缺失、连接被拒绝、密码错误）"""
        ctr = nosql_redis.nosqlRedisCtr()
        ins = ctr.getInstanceBySid(0)

        # 1. 模拟驱动缺失场景
        ins.redis_conn = lambda db_idx=0: False
        setattr(ins, '_nosqlRedis__DB_ERR', "Python 环境缺少 redis 扩展模块: No module named 'redis'")
        ret_driver = ctr.getList({'sid': 0})
        self.assertFalse(ret_driver.get('status'))
        self.assertIn('未安装 redis 驱动模块', ret_driver.get('msg', ''))
        self.assertTrue(ret_driver.get('data', {}).get('driver_missing'))

        # 2. 模拟连接被拒绝场景
        setattr(ins, '_nosqlRedis__DB_ERR', 'Connection refused by peer')
        ret_refused = ctr.getList({'sid': 0})
        self.assertFalse(ret_refused.get('status'))
        self.assertIn('连接被拒绝', ret_refused.get('msg', ''))

        # 3. 模拟密码错误场景
        setattr(ins, '_nosqlRedis__DB_ERR', 'WRONGPASS invalid username-password pair')
        ret_pass = ctr.getList({'sid': 0})
        self.assertFalse(ret_pass.get('status'))
        self.assertIn('密码错误', ret_pass.get('msg', ''))


if __name__ == '__main__':
    unittest.main()
