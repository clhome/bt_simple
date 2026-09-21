# coding: utf-8
import os
import sys
import unittest
import shutil
import tempfile
import json
from unittest.mock import patch, MagicMock

# 确保 web 与根目录加入 sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(WORKSPACE_DIR, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

plugins_redis_dir = os.path.join(WORKSPACE_DIR, 'plugins', 'redis')
if plugins_redis_dir not in sys.path:
    sys.path.insert(0, plugins_redis_dir)

import core.yf as yf
import plugins.redis.index as redis_index


class TestRedisUpgradeSelfHealing(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='redis_test_healing_')
        self.test_server_dir = os.path.join(self.test_dir, 'server', 'redis')
        self.test_plugin_dir = os.path.join(self.test_dir, 'plugins', 'redis')
        os.makedirs(self.test_server_dir, exist_ok=True)
        os.makedirs(self.test_plugin_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_status_pid_self_healing(self):
        """测试 1: 验证 status() 在 PID 丢失或失效时，能通过真实进程探活并自愈写回 PID 文件"""
        test_pid_file = os.path.join(self.test_server_dir, 'redis.pid')
        fake_live_pid = 77665

        with patch.object(redis_index, 'getPidFile', return_value=test_pid_file), \
             patch.object(redis_index, 'getRedisPid', return_value=fake_live_pid), \
             patch.object(redis_index, 'checkPluginUpgrade', return_value=None), \
             patch.object(yf, 'checkPid', side_effect=lambda pid: pid == fake_live_pid):

            # 场景 A: PID 文件不存在，但真实进程存活
            self.assertFalse(os.path.exists(test_pid_file))
            st = redis_index.status()
            self.assertEqual(st, 'start', "真实进程存活时，status() 必须准确返回 start")
            self.assertTrue(os.path.exists(test_pid_file), "status() 必须自动自愈创建 pid 文件")
            self.assertEqual(yf.readFile(test_pid_file).strip(), str(fake_live_pid), "自愈写回的 PID 必须与存活进程一致")

            # 场景 B: PID 文件被写成了无效的死 PID，但真实进程存活
            yf.writeFile(test_pid_file, '11223')
            st2 = redis_index.status()
            self.assertEqual(st2, 'start')
            self.assertEqual(yf.readFile(test_pid_file).strip(), str(fake_live_pid), "死 PID 必须被自动自愈替换为真实 PID")

    def test_02_status_stops_when_no_process(self):
        """测试 2: 当无存活进程且 systemd 状态非 active 时，准确判定为 stop"""
        test_pid_file = os.path.join(self.test_server_dir, 'redis.pid')
        with patch.object(redis_index, 'getPidFile', return_value=test_pid_file), \
             patch.object(redis_index, 'getRedisPid', return_value=None), \
             patch.object(redis_index, 'checkPluginUpgrade', return_value=None), \
             patch.object(yf, 'getOs', return_value='linux'), \
             patch.object(yf, 'execShell', return_value=('inactive', '')):
            st = redis_index.status()
            self.assertEqual(st, 'stop', "没有任何存活进程时必须返回 stop")

    def test_03_redis_conf_zero_touch_protection(self):
        """测试 3: 验证已有 redis.conf 存在时零触碰防御机制，绝对不覆盖用户原有密码与配置"""
        conf_file = os.path.join(self.test_server_dir, 'redis.conf')
        init_pl = os.path.join(self.test_server_dir, 'init.pl')
        custom_pwd = 'MyCustomSuperPassword123'
        user_conf_content = f"port 6388\nrequirepass {custom_pwd}\ndaemonize yes\n"
        yf.writeFile(conf_file, user_conf_content)

        # 此时 init.pl 尚不存在（模拟老版本升级场景）
        self.assertFalse(os.path.exists(init_pl))

        with patch.object(redis_index, 'getServerDir', return_value=self.test_server_dir), \
             patch.object(redis_index, 'getConf', return_value=conf_file), \
             patch.object(redis_index, 'getInitDTpl', return_value=os.path.join(WORKSPACE_DIR, 'plugins', 'redis', 'init.d', 'redis.tpl')), \
             patch.object(redis_index, 'getConfTpl', return_value=os.path.join(WORKSPACE_DIR, 'plugins', 'redis', 'config', 'redis.conf')), \
             patch.object(yf, 'systemdCfgDir', return_value='/tmp'):

            # 触发 initDreplace
            redis_index.initDreplace()

            # 验证 1: init.pl 被自愈补齐
            self.assertTrue(os.path.exists(init_pl), "已有配置自愈后必须补齐 init.pl 标记")

            # 验证 2: redis.conf 中的原有密码与端口 100% 完整保留，绝对未被模板覆盖
            current_conf = yf.readFile(conf_file)
            self.assertIn(custom_pwd, current_conf, "已有密码绝对不能被重置覆盖！")
            self.assertIn('port 6388', current_conf, "已有端口必须完整保留！")

    def test_04_systemd_service_tpl_no_pkill_and_has_pidfile(self):
        """测试 4: 验证 redis.service.tpl 模板已包含 PIDFile 且已彻底移除暴力 pkill -9"""
        tpl_path = os.path.join(WORKSPACE_DIR, 'plugins', 'redis', 'init.d', 'redis.service.tpl')
        self.assertTrue(os.path.exists(tpl_path))
        content = yf.readFile(tpl_path)

        # 必须包含 PIDFile
        self.assertIn('PIDFile=', content, "systemd 配置必须声明 PIDFile 以免 forking 模式超时失败")
        # 必须废除暴力强杀
        self.assertNotIn('pkill -9', content, "必须彻底移除破坏性 pkill -9 指令")
        # 必须包含 LimitNOFILE
        self.assertIn('LimitNOFILE=', content, "必须配置 LimitNOFILE 以支撑高并发")

    def test_05_check_plugin_upgrade_single_execution(self):
        """测试 5: 验证大版本升级检测单次自愈流水线（1.x -> 2.0 仅执行一次自愈）"""
        test_version_file = os.path.join(self.test_plugin_dir, 'plugin_version.pl')

        with patch.object(redis_index, 'getPluginVersionFile', return_value=test_version_file), \
             patch.object(redis_index, 'getServerDir', return_value=self.test_server_dir), \
             patch.object(redis_index, 'upgradeSelfHealing') as mock_healing:

            mock_healing.return_value = yf.returnJson(True, 'Self healing ok')

            # 1. 模拟 1.x 老版本环境（文件不存在，默认 1.0）
            self.assertEqual(redis_index.getInstalledPluginVersion(), '1.0')

            # 2. 第一次调用：必须触发自愈
            res1 = redis_index.checkPluginUpgrade()
            self.assertTrue(res1['status'])
            self.assertEqual(res1['target_version'], '2.0')
            mock_healing.assert_called_once()
            self.assertEqual(redis_index.getInstalledPluginVersion(), '2.0', "执行成功后版本必须更新为 2.0")

            # 3. 第二次调用：直接放行（0 损耗），不再调用自愈
            mock_healing.reset_mock()
            res2 = redis_index.checkPluginUpgrade()
            self.assertTrue(res2['status'])
            self.assertEqual(res2['msg'], 'Already up to date')
            mock_healing.assert_not_called()

    def test_06_start_closed_loop_and_error_capture(self):
        """测试 6: 验证 start() 闭环检测与假成功拦截：服务未拉起时必须截获错误日志并返回真实失败"""
        fake_log = os.path.join(self.test_server_dir, 'data', 'redis.log')
        os.makedirs(os.path.dirname(fake_log), exist_ok=True)
        yf.writeFile(fake_log, "1234:M 17 Sep 2026 # Bad directive or wrong number of arguments\n1234:M 17 Sep 2026 # Fatal error, can't open config file\n")

        with patch.object(redis_index, 'status', return_value='stop'), \
             patch.object(redis_index, 'redisOp', return_value='ok'), \
             patch.object(redis_index, 'runLog', return_value=fake_log), \
             patch.object(redis_index, 'checkPluginUpgrade', return_value=None), \
             patch.object(yf, 'getOs', return_value='linux'), \
             patch.object(yf, 'execShell', return_value=('', '')):

            res = redis_index.start()
            # 必须拒绝返回 ok，且必须包含日志错误信息
            self.assertNotEqual(res, 'ok', "进程未存活时 start() 绝对不能返回假成功 ok！")
            self.assertIn('启动失败', res)
            self.assertIn('Fatal error', res)


if __name__ == '__main__':
    unittest.main()
