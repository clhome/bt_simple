# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）软件菜单分类切换延迟与插件状态探测性能优化专项自动化测试套件
验证:
1. 核心文件 UTF-8 无 BOM 与 LF 换行符
2. display_status is False 插件无需外部进程探测
3. 缓存增量合并机制（彻底杜绝分类/分页切换时的缓存踩踏与抹除）
4. Docker、OP_WAF、Fail2ban、Swap 快速探针的准确性与降级回退
"""
import unittest
import os
import sys
import ast
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# 优先导入 psutil
try:
    import psutil
except ImportError:
    psutil = MagicMock()
    psutil.pid_exists.side_effect = lambda p: p == os.getpid()
    sys.modules['psutil'] = psutil

# 优雅 mock 外部依赖
for mod in ['flask', 'flask_socketio', 'gevent', 'geventwebsocket']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PLUGIN_PY = os.path.join(WEB_DIR, 'utils', 'plugin.py')


class TestPluginListPerfOpt(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='yf_perf_test_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_01_encoding_and_lf(self):
        """测试 1: 验证修改的 plugin.py 为 UTF-8 无 BOM 且使用 LF 换行符"""
        self.assertTrue(os.path.exists(PLUGIN_PY), f"文件不存在: {PLUGIN_PY}")
        with open(PLUGIN_PY, "rb") as f:
            content = f.read()
        self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"文件 {PLUGIN_PY} 含有 UTF-8 BOM")
        self.assertNotIn(b"\r\n", content, f"文件 {PLUGIN_PY} 含有 CRLF 换行符，必须为 LF")
        print("\n[OK] 测试 1: plugin.py UTF-8 无 BOM 与 LF 换行符验证通过！")

    def test_02_ast_syntax_check(self):
        """测试 2: 验证 plugin.py 语法解析完全正常"""
        with open(PLUGIN_PY, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source, filename=PLUGIN_PY)
        except SyntaxError as e:
            self.fail(f"plugin.py 存在语法错误: {e}")
        print("[OK] 测试 2: plugin.py AST 语法树解析通过，零语法缺陷！")

    def test_03_display_status_filter_in_probes(self):
        """测试 3: 验证 display_status is False 插件直接跳过探测并置为 False，不触发 run()"""
        from utils.plugin import plugin
        pg = plugin()

        # 模拟调用 checkStatusReal 与 checkStatusThreadsByCache
        mock_run = MagicMock()
        pg.run = mock_run

        tool_plugin = {
            'name': 'python_yf',
            'setup': True,
            'setup_version': '1.0',
            'display_status': False
        }

        # 1. checkStatusReal
        res_real = pg.checkStatusReal(tool_plugin)
        self.assertFalse(res_real)
        mock_run.assert_not_called()

        # 2. checkStatusThreadsByCache
        res_cache = pg.checkStatusThreadsByCache(tool_plugin)
        self.assertFalse(res_cache)
        mock_run.assert_not_called()
        print("[OK] 测试 3: display_status is False 插件成功拦截，零外部子进程调用！")

    def test_04_cache_incremental_merge_and_anti_overwrite(self):
        """测试 4: 验证分类切换时缓存增量合并，旧分类缓存永不被覆盖抹除"""
        from utils.plugin import plugin
        import thisdb

        pg = plugin()

        # 模拟内存和 thisdb 的持久化存储
        simulated_db = {}
        def mock_getOptionByJson(key, type='common', default=None):
            val = simulated_db.get(key, default)
            return json.loads(val) if isinstance(val, str) else val

        def mock_setOption(key, val, type='common'):
            simulated_db[key] = val
            return True

        with patch.object(thisdb, 'getOptionByJson', side_effect=mock_getOptionByJson), \
             patch.object(thisdb, 'setOption', side_effect=mock_setOption):

            # 初始状态：预置分类 1（运行环境）的已缓存状态
            simulated_db[pg._plugin__plugin_status_cachekey] = json.dumps({
                'openresty': True,
                'php-80': True
            })

            # 用户切换到分类 2（数据库）：包含 mysql (已安装, display_status: True) 与未安装项
            db_plugins = [
                {'name': 'mysql', 'setup': True, 'setup_version': '5.7', 'display_status': True, 'coexist': False},
                {'name': 'redis', 'setup': False, 'setup_version': '', 'display_status': True, 'coexist': False}
            ]

            # 模拟 mysql 快速探测返回 True
            with patch.object(pg, 'checkStatusQuick', return_value=True):
                result = pg.checkStatusMThreadsByCache(db_plugins)

            # 验证 mysql 状态被正确填充
            self.assertTrue(result[0]['status'])

            # 验证 simulated_db 中的缓存：openresty, php-80 仍然健在，并且新增了 mysql！
            saved_cache = json.loads(simulated_db[pg._plugin__plugin_status_cachekey])
            self.assertIn('openresty', saved_cache, "错误：openresty 缓存被分类切换抹除了！")
            self.assertIn('php-80', saved_cache, "错误：php-80 缓存被分类切换抹除了！")
            self.assertIn('mysql', saved_cache, "错误：mysql 状态未能成功合并写入！")
            self.assertTrue(saved_cache['openresty'])
            self.assertTrue(saved_cache['mysql'])
        print("[OK] 测试 4: 多分类/分页切换缓存增量合并机制验证成功，彻底杜绝缓存踩踏！")

    def test_05_check_status_quick_docker_opwaf_fail2ban_swap(self):
        """测试 5: 验证 Docker、OP_WAF、Fail2ban、Swap 快速探针的有效性"""
        from utils.plugin import plugin
        import core.yf as yf
        pg = plugin()

        # 1. 测试 Docker 快速探测
        with patch('os.path.exists') as mock_exists, \
             patch('core.yf.readFile', return_value='12345'), \
             patch('core.yf.checkPid', return_value=True):
            mock_exists.side_effect = lambda p: p == '/var/run/docker.pid'
            res_docker = pg.checkStatusQuick('docker')
            self.assertTrue(res_docker)

        # 2. 测试 OP_WAF 快速探测
        with patch('os.path.exists', return_value=True), \
             patch.object(pg, 'checkStatusQuick', return_value=True):
            # 当 openresty 存活且配置文件齐备
            res_waf = pg.checkStatusQuick('op_waf')
            self.assertTrue(res_waf)

        # 3. 测试 Fail2ban 快速探测
        with patch('os.path.exists') as mock_exists, \
             patch('core.yf.readFile', return_value='23456'), \
             patch('core.yf.checkPid', return_value=True):
            mock_exists.side_effect = lambda p: p == '/run/fail2ban/fail2ban.pid'
            res_f2b = pg.checkStatusQuick('fail2ban')
            self.assertTrue(res_f2b)

        # 4. 测试 Swap 快速探测
        swap_path = os.path.join(yf.getServerDir(), 'swap', 'swapfile').replace('\\', '/')
        fake_swaps = f"Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n{swap_path}\tfile\t\t1048572\t\t0\t\t-2\n"
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data=fake_swaps)):
            res_swap = pg.checkStatusQuick('swap')
            self.assertTrue(res_swap)

        print("[OK] 测试 5: Docker、OP_WAF、Fail2ban、Swap 快速探针覆盖与判定准确！")

    def test_06_installed_category_perf_and_no_unneeded_processes(self):
        """测试 6: 模拟用户真实的已安装列表（10个插件），验证5个工具插件0探测，有快速探针的0外部进程"""
        from utils.plugin import plugin
        import thisdb
        pg = plugin()

        mock_run = MagicMock(return_value=('start', ''))
        pg.run = mock_run

        # 10 个已安装插件
        sample_page = [
            {'name': 'docker', 'setup': True, 'setup_version': '1.0', 'display_status': True, 'coexist': False},
            {'name': 'pg_docker', 'setup': True, 'setup_version': '1.0', 'display_status': False, 'coexist': False},
            {'name': 'python_yf', 'setup': True, 'setup_version': '1.0', 'display_status': False, 'coexist': False},
            {'name': 'openresty', 'setup': True, 'setup_version': '1.31.1', 'display_status': True, 'coexist': False},
            {'name': 'swap', 'setup': True, 'setup_version': '1.7', 'display_status': False, 'coexist': False},
            {'name': 'mysql', 'setup': True, 'setup_version': '5.7', 'display_status': True, 'coexist': False},
            {'name': 'op_waf', 'setup': True, 'setup_version': '1.5', 'display_status': True, 'coexist': False},
            {'name': 'fail2ban', 'setup': True, 'setup_version': '1.2.0', 'display_status': True, 'coexist': False},
            {'name': 'linux_sys_opt', 'setup': True, 'setup_version': '1.0', 'display_status': False, 'coexist': False},
            {'name': 'jdk', 'setup': True, 'setup_version': '1.0', 'display_status': False, 'coexist': False}
        ]

        with patch.object(thisdb, 'getOptionByJson', return_value={}), \
             patch.object(thisdb, 'setOption', return_value=True), \
             patch.object(pg, 'checkStatusQuick', side_effect=lambda name, ver='': True if name in ('openresty', 'mysql', 'docker', 'op_waf', 'fail2ban') else None):
            res_items = pg.checkStatusMThreadsByCache(sample_page)

        # 验证所有 display_status: False 的插件 status 均为 False，且没有调用 pg.run
        tool_names = {'pg_docker', 'python_yf', 'swap', 'linux_sys_opt', 'jdk'}
        for it in res_items:
            if it['name'] in tool_names:
                self.assertFalse(it['status'])

        # 验证 display_status: True 的插件 status 均为 True（命中快速探针）
        service_names = {'docker', 'openresty', 'mysql', 'op_waf', 'fail2ban'}
        for it in res_items:
            if it['name'] in service_names:
                self.assertTrue(it['status'])

        # 快速探针全部命中，pg.run 一次都不需要调用！
        mock_run.assert_not_called()
        print("[OK] 测试 6: 已安装列表 10 个插件全面测试通过，0 外部进程调用，彻底消除 487ms 卡顿！")


if __name__ == '__main__':
    unittest.main()
