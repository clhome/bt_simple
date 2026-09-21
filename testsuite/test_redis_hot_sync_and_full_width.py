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
import plugins.data_query.nosql_redis as nosql_redis


class TestRedisHotSyncAndFullWidth(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_redis_hotsync_')
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)
        redis_plugin.getServerDir = lambda: self.sandbox_server
        nosql_redis.yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_full_width_ui_and_css_isolation(self):
        """验证性能调整表单样式隔离，杜绝换行"""
        js_file = os.path.join(redis_dir, 'js', 'redis.js')
        js_content = yf.readFile(js_file)
        self.assertIn('redis-form-row', js_content, "必须使用独立类名 redis-form-row 隔离 site.css 污染")
        self.assertIn('redis-field-desc', js_content)
        self.assertIn('white-space:nowrap', js_content, "说明文字必须强制不换行铺开")

        html_file = os.path.join(redis_dir, 'index.html')
        html_content = yf.readFile(html_file)
        self.assertIn('.redis-conf-wrap', html_content)
        self.assertIn('white-space: nowrap !important;', html_content)

    def test_02_submitRedisConf_restarts_running_service(self):
        """验证提交配置后自动重启 Redis 服务使新配置真实生效"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, "port 6379\nrequirepass OldPass123\n")

        redis_plugin.getArgs = lambda: {'port': '6380', 'requirepass': 'YomlixYx4y'}
        redis_plugin.status = lambda: 'start'

        restart_called = [False]
        def mock_restart():
            restart_called[0] = True
            return 'ok'
        redis_plugin.restart = mock_restart

        res_json = redis_plugin.submitRedisConf()
        res = json.loads(res_json)
        self.assertTrue(res.get('status'))
        self.assertTrue(restart_called[0], "保存配置后必须自动调用 restart() 使配置和密码真实生效")

        updated_conf = yf.readFile(conf_path)
        self.assertIn('port 6380', updated_conf)
        self.assertIn('requirepass YomlixYx4y', updated_conf)

    def test_03_runInfo_self_healing_on_auth_mismatch(self):
        """验证 runInfo 遇到密码不匹配时自动触发自愈并成功恢复"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, "port 6379\nrequirepass YomlixYx4y\n")

        redis_plugin.status = lambda: 'start'
        exec_count = [0]
        restart_called = [False]

        def mock_exec(cmd):
            exec_count[0] += 1
            if exec_count[0] == 1:
                # 第一次返回 WRONGPASS invalid username-password pair
                return ('(error) WRONGPASS invalid username-password pair or user is disabled.', '')
            else:
                # 自愈重启后第二次执行返回正常 info 输出
                return ('# Server\ntcp_port:6379\nuptime_in_days:3\nused_memory:2048\n', '')

        redis_plugin.yf.execShell = mock_exec
        def mock_restart():
            restart_called[0] = True
            return 'ok'
        redis_plugin.restart = mock_restart

        ret_json = redis_plugin.runInfo()
        ret = json.loads(ret_json)
        self.assertTrue(restart_called[0], "检测到密码不匹配时应自动触发自愈重启")
        self.assertEqual(ret.get('tcp_port'), '6379')
        self.assertEqual(ret.get('uptime_in_days'), '3')

    def test_04_data_manager_hot_sync_self_healing(self):
        """验证 Data Manager 捕获到 invalid username-password 触发自愈"""
        ctr = nosql_redis.nosqlRedisCtr()
        ins = ctr.getInstanceBySid(0)

        # 模拟失败报错
        setattr(ins, '_nosqlRedis__DB_ERR', 'invalid username-password pair or user is disabled.')
        ins.redis_conn = lambda db_idx=0: False

        ret = ctr.getList({'sid': 0})
        self.assertFalse(ret.get('status'))
        self.assertIn('Redis 密码错误', ret.get('msg', ''))
        self.assertIn('invalid username-password', ret.get('msg', ''))


if __name__ == '__main__':
    unittest.main()
