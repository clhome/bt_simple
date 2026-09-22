# coding:utf-8

import os
import sys
import json
import glob
import unittest
import tempfile
import shutil

test_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(test_dir)
web_dir = os.path.join(project_dir, 'web')
plugins_dir = os.path.join(project_dir, 'plugins')
redis_dir = os.path.join(plugins_dir, 'redis')

for p in [project_dir, web_dir, redis_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf
import plugins.redis.index as redis_plugin


class TestRedisRunLogFix(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_redis_log_')
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)
        self._orig_runLog = redis_plugin.runLog
        self._orig_getConf = redis_plugin.getConf
        self._orig_status = redis_plugin.status
        self._orig_getServerDir = redis_plugin.getServerDir
        self._orig_yf_getServerDir = redis_plugin.yf.getServerDir

        redis_plugin.getServerDir = lambda: self.sandbox_server
        redis_plugin.yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')
        redis_plugin.status = lambda: 'start'

    def tearDown(self):
        redis_plugin.runLog = self._orig_runLog
        redis_plugin.getConf = self._orig_getConf
        redis_plugin.status = self._orig_status
        redis_plugin.getServerDir = self._orig_getServerDir
        redis_plugin.yf.getServerDir = self._orig_yf_getServerDir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_restart_preserves_logs_instead_of_clearing(self):
        """验证 restart() 绝不清空日志文件，而是安全保留并追加"""
        log_file = os.path.join(self.sandbox_server, 'data', 'redis.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        initial_log = "[2026-09-17 12:00:00] Initial Redis user record.\n"
        yf.writeFile(log_file, initial_log)

        redis_plugin.runLog = lambda: log_file
        redis_plugin.redisOp = lambda op: 'ok'
        redis_plugin.status = lambda: 'start'

        res = redis_plugin.restart()
        self.assertEqual(res, 'ok')

        current_content = yf.readFile(log_file)
        self.assertIn("Initial Redis user record", current_content, "restart() 严禁粗暴清空用户日志")
        self.assertIn("服务重启成功", current_content, "必须追加重启事件记录")

    def test_02_runLog_cleans_server_path_placeholder(self):
        """验证 runLog() 能够清洗 {$SERVER_PATH} 占位符并自愈配置"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, "logfile {$SERVER_PATH}/redis/data/redis.log\n")

        redis_plugin.getConf = lambda: conf_path
        detected_log = redis_plugin.runLog()

        self.assertNotIn('{$SERVER_PATH}', detected_log, "日志路径严禁残留 {$SERVER_PATH} 占位符")
        self.assertTrue(os.path.isabs(detected_log), "返回的必须是系统有效绝对路径")
        self.assertTrue(os.path.exists(detected_log), "日志文件必须真实存在")
        self.assertGreater(os.path.getsize(detected_log), 0, "日志文件严禁为0字节空文件")

    def test_03_getRunLog_never_returns_empty(self):
        """验证 getRunLog() 无论环境如何，绝不返回空内容，必须有健康诊断与日志信息"""
        log_file = os.path.join(self.sandbox_server, 'data', 'redis.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        # 故意创建 0 字节空文件，测试自愈机制
        yf.writeFile(log_file, "")

        redis_plugin.runLog = lambda: log_file
        redis_plugin.status = lambda: 'start'

        res_json = redis_plugin.getRunLog()
        res = json.loads(res_json)
        self.assertTrue(res.get('status'), "getRunLog 必须成功响应")
        data = res.get('data', {})
        self.assertEqual(data.get('path'), log_file)
        log_text = data.get('data', '')
        self.assertTrue(len(log_text.strip()) > 20, "日志内容严禁为空白")
        self.assertIn("Redis", log_text)

    def test_04_clearRunLog_works_correctly(self):
        """验证 clearRunLog() 能安全清空并保留清空审计记录"""
        log_file = os.path.join(self.sandbox_server, 'data', 'redis.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        yf.writeFile(log_file, "Line 1\nLine 2\nLine 3\n")

        redis_plugin.runLog = lambda: log_file
        res_json = redis_plugin.clearRunLog()
        res = json.loads(res_json)
        self.assertTrue(res.get('status'))

        content = yf.readFile(log_file)
        self.assertNotIn("Line 1", content)
        self.assertIn("清空", content)

    def test_05_frontend_redisRunLog_and_index_html(self):
        """验证前端 index.html 与 redis.js 正确集成 redisRunLog"""
        html_file = os.path.join(redis_dir, 'index.html')
        html_content = yf.readFile(html_file)
        self.assertIn("redisRunLog()", html_content, "index.html 运行日志菜单必须调用 redisRunLog()")

        js_file = os.path.join(redis_dir, 'js', 'redis.js')
        js_content = yf.readFile(js_file)
        self.assertIn("function redisRunLog()", js_content, "redis.js 中必须实现 redisRunLog")
        self.assertIn("get_run_log", js_content, "redisRunLog 必须调用 get_run_log API")
        self.assertIn("clear_run_log", js_content, "redisRunLog 必须调用 clear_run_log API")
        self.assertIn("刷新日志", js_content, "界面必须包含刷新日志功能")

    def test_06_lang_files_contain_log_keys(self):
        """验证 6 国多语言字典中均完整包含运行日志相关的词条"""
        # 只列源码里真实存在的 pt() 实参（plugins/redis/js/redis.js 的日志面板）。
        # 旧的「当前暂无新增运行日志」已不再由前端渲染：空态文案改由后端写进日志正文
        # （plugins/redis/index.py 的 `运行提示: 当前暂无异常或生命周期事件记录。`），
        # 在 6 个语言包里都没有对应键，是死键，别再断言它。
        required_keys = [
            "日志文件", "刷新日志", "清空日志", "说明", "正在获取运行日志..."
        ]
        lang_files = glob.glob(os.path.join(redis_dir, 'lang', '*.json'))
        self.assertGreaterEqual(len(lang_files), 6, "必须存在至少 6 个语言包")

        for lf in lang_files:
            with open(lf, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in required_keys:
                self.assertIn(k, data, f"语言文件 {os.path.basename(lf)} 缺失词条: {k}")


if __name__ == '__main__':
    unittest.main()
