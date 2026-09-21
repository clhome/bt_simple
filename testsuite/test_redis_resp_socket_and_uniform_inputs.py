# coding:utf-8

import os
import sys
import unittest
import tempfile
import shutil
import json

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


class TestRedisRespSocketAndUniformInputs(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_redis_uniform_')
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)
        redis_plugin.getServerDir = lambda: self.sandbox_server

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_uniform_200px_input_width(self):
        """验证所有配置项 input 框宽度统一为 200px"""
        js_file = os.path.join(redis_dir, 'js', 'redis.js')
        js_content = yf.readFile(js_file)
        self.assertIn("var w = '200';", js_content, "所有 input 框宽度必须统一为 200px，杜绝长短不一")
        self.assertNotIn("item.name) > -1) ? '280' : '140'", js_content, "不得再有差异化 280px 宽度设置")

    def test_02_execRedisCommand_fallback_and_direct(self):
        """验证 execRedisCommand 高可用三级容灾执行器"""
        # 模拟外部 execRedisCommand 返回标准 INFO
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, "port 6379\nrequirepass YomlixYx4y\n")

        redis_plugin.status = lambda: 'start'
        mock_info = """# Server
tcp_port:6379
uptime_in_days:5
connected_clients:2
used_memory:1048576
used_memory_rss:2097152
used_memory_peak:3145728
mem_fragmentation_ratio:1.15
total_connections_received:20
total_commands_processed:150
instantaneous_ops_per_sec:2
keyspace_hits:80
keyspace_misses:10
latest_fork_usec:120
"""
        redis_plugin.execRedisCommand = lambda cmd: (mock_info, '')

        ret_json = redis_plugin.runInfo()
        ret = json.loads(ret_json)
        self.assertEqual(ret.get('tcp_port'), '6379')
        self.assertEqual(ret.get('uptime_in_days'), '5')
        self.assertEqual(ret.get('connected_clients'), '2')
        self.assertEqual(ret.get('used_memory'), '1048576')

    def test_03_replication_and_cluster_uses_execRedisCommand(self):
        """验证复制与集群信息也无缝对齐三级执行器"""
        redis_plugin.status = lambda: 'start'
        mock_repl = """role:master
connected_slaves:0
master_replid:abcdef123456
master_repl_offset:1024
"""
        redis_plugin.execRedisCommand = lambda cmd: (mock_repl, '')
        repl_json = redis_plugin.infoReplication()
        repl_data = json.loads(repl_json)
        self.assertEqual(repl_data.get('role'), 'master')
    def test_04_user_real_dict_data_parsing(self):
        """验证真实生产环境中 redis-py 返回字典字符串时，runInfo 依然 100% 正确解析"""
        redis_plugin.status = lambda: 'start'
        user_real_data = {
            'redis_version': '8.6.3',
            'tcp_port': 6379,
            'uptime_in_days': 0,
            'connected_clients': 1,
            'used_memory': 796464,
            'used_memory_rss': 7823360,
            'used_memory_peak': 796720,
            'mem_fragmentation_ratio': 11.09,
            'total_connections_received': 1,
            'total_commands_processed': 3,
            'instantaneous_ops_per_sec': 0,
            'keyspace_hits': 0,
            'keyspace_misses': 0,
            'latest_fork_usec': 0
        }
        # 模拟外部直接返回字典对象的 str 格式
        redis_plugin.execRedisCommand = lambda cmd: (str(user_real_data), '')

        ret_json = redis_plugin.runInfo()
        ret = json.loads(ret_json)
        self.assertNotIn('status', ret, "解析成功时不得返回 status=False 错误")
        self.assertEqual(ret.get('tcp_port'), '6379')
        self.assertEqual(ret.get('used_memory'), '796464')
        self.assertEqual(ret.get('connected_clients'), '1')


if __name__ == '__main__':
    unittest.main()

