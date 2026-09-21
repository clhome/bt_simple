# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）首页提醒修改即时刷新与全局配置缓存优化专项自动化测试套件
验证:
1. 核心修改文件 UTF-8 无 BOM 与 LF 换行符规范
2. web/utils/config.py 中 clearGlobalVarCache() 导出与缓存清空机制
3. getGlobalVar() 在 30 秒 TTL 内的读缓存性能机制（零额外数据库开销）
4. 修改 home_notice 后立即调用 clearGlobalVarCache() 实现 0 延迟即时刷新
5. web/admin/setting/setting.py 中 set_home_notice 等接口正确接入 clearGlobalVarCache()
"""
import unittest
import os
import sys
import ast
import time
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

CONFIG_PY = os.path.join(WEB_DIR, 'utils', 'config.py')
SETTING_PY = os.path.join(WEB_DIR, 'admin', 'setting', 'setting.py')


class TestHomeNoticeCache(unittest.TestCase):

    def test_01_encoding_and_lf_newline(self):
        """验证核心修改文件统一使用 UTF-8 无 BOM 与 LF 换行符"""
        for filepath in [CONFIG_PY, SETTING_PY]:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"{filepath} 包含非法 UTF-8 BOM 头")
            self.assertNotIn(b'\r\n', content, f"{filepath} 包含非法 CRLF 换行符，必须使用 LF")

    def test_02_clear_global_var_cache_function_exists(self):
        """验证 web/utils/config.py 正确定义并导出了 clearGlobalVarCache 方法"""
        import utils.config as utils_config
        self.assertTrue(hasattr(utils_config, 'clearGlobalVarCache'), "utils.config 缺少 clearGlobalVarCache 函数")
        self.assertTrue(callable(utils_config.clearGlobalVarCache), "clearGlobalVarCache 应当为可调用函数")

        # 模拟填充缓存后执行清除
        utils_config._global_var_cache = {'dummy': 'test'}
        utils_config._global_var_cache_time = time.time()
        utils_config.clearGlobalVarCache()

        self.assertIsNone(utils_config._global_var_cache, "clearGlobalVarCache 后 _global_var_cache 必须重置为 None")
        self.assertEqual(utils_config._global_var_cache_time, 0, "clearGlobalVarCache 后 _global_var_cache_time 必须为 0")

    def test_03_ttl_cache_preserves_performance(self):
        """验证日常读操作在 30 秒 TTL 内命中内存缓存，避免重复数据库查询以保证系统性能"""
        import utils.config as utils_config
        utils_config.clearGlobalVarCache()

        mock_data = {'title': '测试面板', 'home_notice': '原始内容'}
        utils_config._global_var_cache = mock_data.copy()
        base_time = 1000000.0
        utils_config._global_var_cache_time = base_time

        # 模拟在第 10 秒（< 30s TTL）调用 getGlobalVar()
        with patch('time.time', return_value=base_time + 10.0):
            # mock thisdb 确保如果调用 thisdb 则抛出异常
            with patch('utils.config.thisdb', MagicMock(side_effect=RuntimeError("命中缓存时不应调用 thisdb"))):
                res = utils_config.getGlobalVar()
                self.assertEqual(res['home_notice'], '原始内容')
                self.assertEqual(res['title'], '测试面板')

    def test_04_instant_invalidation_after_notice_update(self):
        """验证修改 home_notice 并触发 clearGlobalVarCache 后，下一次读取立即获取新数据（0延迟）"""
        import utils.config as utils_config
        utils_config.clearGlobalVarCache()

        # 步骤 1: 用户在 00:00 打开页面，生成旧缓存
        t0 = 2000000.0
        with patch('time.time', return_value=t0):
            with patch('utils.config.thisdb.getOption', side_effect=lambda k, default='': '旧提醒' if k == 'home_notice' else 'def'):
                with patch('utils.config.thisdb.getOptionByJson', return_value={}):
                    with patch('utils.config.thisdb.getSitesCount', return_value=0):
                        with patch('utils.config.yf.getLocalIp', return_value='127.0.0.1'):
                            with patch('utils.config.yf.getHostPort', return_value='7200'):
                                with patch('utils.config.yf.M', MagicMock()):
                                    with patch('utils.config.get_menu_config', return_value=[]):
                                        res1 = utils_config.getGlobalVar()
                                        self.assertEqual(res1['home_notice'], '旧提醒')

        # 步骤 2: 在第 5 秒，用户修改了提醒为“新提醒123”并保存
        t_modify = t0 + 5.0
        # 若未清缓存，第 6 秒访问仍会返回旧提醒（即重现用户原本遇到的 Bug）
        with patch('time.time', return_value=t_modify + 1.0):
            stale_res = utils_config.getGlobalVar()
            self.assertEqual(stale_res['home_notice'], '旧提醒', "在未主动失效时应命中 30 秒缓存")

        # 步骤 3: 触发 clearGlobalVarCache()（修复后的行为）
        utils_config.clearGlobalVarCache()

        # 步骤 4: 数据库已经更新为“新提醒123”，第 6 秒用户切回首页读取
        with patch('time.time', return_value=t_modify + 1.0):
            with patch('utils.config.thisdb.getOption', side_effect=lambda k, default='': '新提醒123' if k == 'home_notice' else 'def'):
                with patch('utils.config.thisdb.getOptionByJson', return_value={}):
                    with patch('utils.config.thisdb.getSitesCount', return_value=0):
                        with patch('utils.config.yf.getLocalIp', return_value='127.0.0.1'):
                            with patch('utils.config.yf.getHostPort', return_value='7200'):
                                with patch('utils.config.yf.M', MagicMock()):
                                    with patch('utils.config.get_menu_config', return_value=[]):
                                        fresh_res = utils_config.getGlobalVar()
                                        self.assertEqual(fresh_res['home_notice'], '新提醒123', "主动失效后必须立刻获取最新修改的内容")

    def test_05_setting_py_ast_calls_clear_global_var_cache(self):
        """通过 AST 静态分析，验证 setting.py 的各主要配置更新函数均调用了 clearGlobalVarCache"""
        with open(SETTING_PY, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=SETTING_PY)

        checked_functions = [
            'set_home_notice',
            'set_webname',
            'set_ip',
            'set_backup_dir',
            'set_www_dir',
            'set_status_code',
            'set_cdn_status',
            'set_gpu_detect',
            'save_menu_config',
        ]

        found_functions = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in checked_functions:
                # 检查该函数体内是否包含 clearGlobalVarCache 调用
                calls = []
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Call):
                        if isinstance(subnode.func, ast.Attribute) and subnode.func.attr == 'clearGlobalVarCache':
                            calls.append(subnode.func.attr)
                        elif isinstance(subnode.func, ast.Name) and subnode.func.id == 'clearGlobalVarCache':
                            calls.append(subnode.func.id)
                found_functions[node.name] = len(calls) > 0

        for fn in checked_functions:
            self.assertIn(fn, found_functions, f"setting.py 中未找到函数 {fn}")
            self.assertTrue(found_functions[fn], f"函数 {fn} 内必须调用 clearGlobalVarCache()")


if __name__ == '__main__':
    unittest.main()
