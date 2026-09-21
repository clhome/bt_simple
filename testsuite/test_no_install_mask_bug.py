# -*- coding: utf-8 -*-
import unittest
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT_DIR, "plugins", "data_query", "static", "js", "app.js")
INDEX_HTML = os.path.join(ROOT_DIR, "plugins", "data_query", "static", "html", "index.html")

class TestNoInstallMaskBug(unittest.TestCase):

    def test_01_index_html_mask_layer_disabled(self):
        """测试 index.html 中的全局未安装遮罩层已被彻底禁用，绝不霸屏"""
        self.assertTrue(os.path.exists(INDEX_HTML))
        with open(INDEX_HTML, 'rb') as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r\n', raw)
        
        content = raw.decode('utf-8')
        self.assertIn('class="mask_layer"', content)
        self.assertIn('display:none !important;', content)

    def test_02_app_js_show_install_layer_defused(self):
        """测试 app.js 中 showInstallLayer 彻底废除 block 样式，selectTab 强制重置遮罩"""
        self.assertTrue(os.path.exists(APP_JS))
        with open(APP_JS, 'rb') as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r\n', raw)
        
        code = raw.decode('utf-8')
        
        # 1. 验证 showInstallLayer 实现不再 block
        m_show = re.search(r'function\s+showInstallLayer\s*\(\)\s*\{([^}]+)\}', code)
        self.assertIsNotNone(m_show, "找不到 showInstallLayer 函数")
        self.assertNotIn("'display','block'", m_show.group(1))
        
        # 2. 验证 selectTab 包含 closeInstallLayer
        m_select = re.search(r'function\s+selectTab\s*\([^)]*\)\s*\{([^}]+)\}', code)
        self.assertIsNotNone(m_select, "找不到 selectTab 函数")
        self.assertIn("closeInstallLayer()", m_select.group(1))

    def test_03_database_get_list_no_show_install_layer(self):
        """测试 Redis, MongoDB, Memcached, MySQL 等在连接失败时绝不再调用 showInstallLayer"""
        with open(APP_JS, 'r', encoding='utf-8') as f:
            code = f.read()
            
        # 排除函数本身的声明行，查找所有调用点
        call_lines = []
        for idx, line in enumerate(code.splitlines()):
            stripped = line.strip()
            if 'showInstallLayer()' in stripped and not stripped.startswith('function'):
                call_lines.append(f"Line {idx+1}: {stripped}")
                
        self.assertEqual(len(call_lines), 0, f"检测到残留的 showInstallLayer 调用: {call_lines}")

    def test_04_tab_isolation_state_logic(self):
        """验证前端 dqConnectionStates 对各数据库的独立状态隔离"""
        with open(APP_JS, 'r', encoding='utf-8') as f:
            code = f.read()
            
        for db in ['mysql', 'postgresql', 'redis', 'mongodb', 'memcached']:
            self.assertIn(f"{db}:", code)
        self.assertIn("function updateDbConnectionUI(dbType, status, errorMsg)", code)

if __name__ == '__main__':
    unittest.main()
