import sys
import os
import unittest
import json
import tempfile
import shutil
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import utils.config as uc


class MenuHardeningTest(unittest.TestCase):
    """菜单配置与安全性加固测试"""

    def setUp(self):
        self.orig_cache = uc._menu_cache
        uc._menu_cache = None

    def tearDown(self):
        uc._menu_cache = self.orig_cache

    def test_filter_blocks_unsafe_url_protocols(self):
        """测试 _filter_menu_items 过滤包含 javascript: 等危险伪协议的条目"""
        items = [
            {"id": "memuA", "name": "首页", "class": "menu_home", "url": "javascript:alert(1)", "show": True},
            {"id": "memuAsite", "name": "网站", "class": "menu_web", "url": "data:text/html,<script>alert(1)</script>", "show": True},
            {"id": "memuAfiles", "name": "文件", "class": "menu_folder", "url": "vbscript:msgbox(1)", "show": True},
            {"id": "memuAsetting", "name": "面板设置", "class": "menu_set", "url": "/setting/index", "show": True}
        ]
        res = uc._filter_menu_items(items)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "memuAsetting")
        self.assertEqual(res[0]["url"], "/setting/index")

    def test_get_menu_config_fallback_on_corrupted_or_isolated_entry(self):
        """测试当 menu.json 被污染为单项脏数据(如 id='x', name='n')时自动回退默认菜单"""
        tmp_dir = tempfile.mkdtemp()
        try:
            fake_menu_file = os.path.join(tmp_dir, 'menu.json')
            # 模拟污染现场: 只有单个 id='x', name='n'
            dirty_data = [{"id": "x", "name": "n", "class": "c", "url": "/", "show": True}]
            with open(fake_menu_file, 'w', encoding='utf-8') as f:
                json.dump(dirty_data, f)

            with patch('os.path.exists', return_value=True), \
                 patch('core.yf.readFile', return_value=json.dumps(dirty_data)):
                uc._menu_cache = None
                menus = uc.get_menu_config()
                # 必须兜底回退到 9 个默认菜单
                self.assertEqual(len(menus), 9)
                menu_ids = [m['id'] for m in menus]
                self.assertIn('memuA', menu_ids)
                self.assertIn('memuAsite', menu_ids)
                self.assertIn('memuAsetting', menu_ids)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_reset_menu_config(self):
        """测试 reset_menu_config 重置为标准 9 项默认菜单"""
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch('core.yf.writeFile') as mock_write, \
                 patch('utils.config.clearGlobalVarCache') as mock_clear:
                uc._menu_cache = [{'id': 'dirty'}]
                res = uc.reset_menu_config()
                self.assertEqual(len(res), 9)
                mock_write.assert_called_once()
                mock_clear.assert_called_once()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


    def test_save_menu_config_logic_rejects_missing_core_items(self):
        """测试 save_menu_config 拒绝缺失核心菜单的请求"""
        # 1. 只有单个恶意项 [{"id": "x", ...}] -> 被拒
        bad_menus = [{"id": "x", "name": "n", "class": "c", "url": "/", "show": True}]
        valid = uc._filter_menu_items(bad_menus)
        default_ids = set(uc.DEFAULT_MENU_IDS)
        submitted_ids = set(item.get('id') for item in valid)
        self.assertFalse(default_ids.issubset(submitted_ids))

        # 2. 只有 8 个核心菜单(缺失 setting) -> 被拒
        missing_one = [dict(m) for m in uc.DEFAULT_MENU if m['id'] != 'memuAsetting']
        valid_missing = uc._filter_menu_items(missing_one)
        submitted_missing = set(item.get('id') for item in valid_missing)
        self.assertFalse(default_ids.issubset(submitted_missing))

        # 3. 完整的 9 个核心菜单(顺序被打乱或部分 show: False) -> 允许
        reordered = list(reversed([dict(m) for m in uc.DEFAULT_MENU]))
        reordered[0]['show'] = False
        valid_good = uc._filter_menu_items(reordered)
        submitted_good = set(item.get('id') for item in valid_good)
        self.assertTrue(default_ids.issubset(submitted_good))
        self.assertEqual(len(valid_good), len(reordered))


if __name__ == '__main__':
    unittest.main()
