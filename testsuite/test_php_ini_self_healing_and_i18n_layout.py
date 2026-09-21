# -*- coding: utf-8 -*-
"""
PHP 配置文件空白与禁用函数自愈、性能排版与会话表格多语言适配自动化测试套件
"""
import os
import sys
import json
import re
import shutil
import tempfile
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'web'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'web', 'utils'))


class TestPhpIniSelfHealingAndI18nLayout(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='yf_php_ini_test_')
        self.ver = '80'
        self.ver_dir = os.path.join(self.test_dir, self.ver)
        self.etc_dir = os.path.join(self.ver_dir, 'etc')
        os.makedirs(self.etc_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_php_ini_recursion_and_empty_file_self_healing(self):
        """测试 1: php 源码版 makePhpIni 与 getConf 无递归且能自愈缺失/0字节损坏文件"""
        import plugins.php.index as php_mod
        orig_getServerDir = php_mod.getServerDir
        php_mod.getServerDir = lambda: self.test_dir.replace('\\', '/')

        try:
            ini_file = os.path.join(self.etc_dir, 'php.ini')

            # 场景 A: php.ini 完全不存在，调用 getConf 必须安全生成且不发生递归崩溃
            if os.path.exists(ini_file):
                os.remove(ini_file)
            ret_path = php_mod.getConf(self.ver)
            self.assertEqual(ret_path, ini_file.replace('\\', '/'))
            self.assertTrue(os.path.exists(ini_file), "getConf 必须自动生成 php.ini")
            self.assertGreater(os.path.getsize(ini_file), 100, "生成的 php.ini 大小必须大于 100 字节")
            with open(ini_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('[PHP]', content, "自动生成的 php.ini 必须包含 [PHP] 段")
            self.assertIn('disable_functions', content, "必须包含 disable_functions")

            # 场景 B: php.ini 为 0 字节空文件，调用 getConf 必须自动自愈重建
            with open(ini_file, 'w', encoding='utf-8') as f:
                f.write('')
            self.assertEqual(os.path.getsize(ini_file), 0)
            php_mod.getConf(self.ver)
            self.assertGreater(os.path.getsize(ini_file), 100, "0 字节损坏文件必须被自动修复")

            # 场景 C: php.ini 存在但无 disable_functions，调用 getDisableFunc 必须自动补齐
            with open(ini_file, 'w', encoding='utf-8') as f:
                f.write("[PHP]\nengine = On\nshort_open_tag = On\nupload_max_filesize = 50M\n")
            res = json.loads(php_mod.getDisableFunc(self.ver))
            self.assertIn('disable_functions', res)
            self.assertIn('exec', res['disable_functions'], "getDisableFunc 必须返回完整的默认安全禁用函数")
            with open(ini_file, 'r', encoding='utf-8') as f:
                healed_content = f.read()
            self.assertIn('disable_functions', healed_content, "物理文件必须被自愈写入 disable_functions")

        finally:
            php_mod.getServerDir = orig_getServerDir

    def test_02_php_apt_and_yum_get_conf_and_disable_func_healing(self):
        """测试 2: php-apt 与 php-yum 的 getConf 与 getDisableFunc 缺损自愈验证"""
        import importlib
        # 测试 php-apt
        apt_mod = importlib.import_module('plugins.php-apt.index')
        orig_apt_sdir = apt_mod.getServerDir
        apt_mod.getServerDir = lambda: self.test_dir.replace('\\', '/')
        try:
            apt_ini = os.path.join(self.test_dir, '8.0', 'fpm', 'php.ini')
            apt_mod.getConf('8.0')
            self.assertTrue(os.path.exists(apt_ini), "php-apt getConf 必须能自愈生成 php.ini")
            res_apt = json.loads(apt_mod.getDisableFunc('8.0'))
            self.assertIn('exec', res_apt['disable_functions'])
        finally:
            apt_mod.getServerDir = orig_apt_sdir

        # 测试 php-yum
        yum_mod = importlib.import_module('plugins.php-yum.index')
        orig_yum_sdir = yum_mod.getServerDir
        yum_mod.getServerDir = lambda: self.test_dir.replace('\\', '/')
        try:
            yum_ini = os.path.join(self.test_dir, 'php80', 'php.ini')
            yum_mod.getConf('80')
            self.assertTrue(os.path.exists(yum_ini), "php-yum getConf 必须能自愈生成 php.ini")
            res_yum = json.loads(yum_mod.getDisableFunc('80'))
            self.assertIn('exec', res_yum['disable_functions'])
        finally:
            yum_mod.getServerDir = orig_yum_sdir

    def test_03_performance_and_session_layout_styles(self):
        """测试 3: 校验三款插件前端 index.html 与 js 中性能调整与 Session 排版自适应样式"""
        plugins = ['php', 'php-apt', 'php-yum']
        for p in plugins:
            html_file = os.path.join(ROOT_DIR, 'plugins', p, 'index.html')
            with open(html_file, 'r', encoding='utf-8') as f:
                html = f.read()

            # 校验性能调整 .bingfa .line .span_tit 拓宽到 175px 消除截断
            self.assertIn('.bingfa .line .span_tit', html, f"{p} 必须包含 bingfa span_tit 自适应样式")
            self.assertIn('width: 175px !important;', html, f"{p} 的 span_tit 宽度必须为 175px")
            self.assertIn('min-width: 150px !important;', html, f"{p} 的 select 宽度必须自适应 min-width 150px")

            # 校验 Session 清理表格自适应样式
            self.assertIn('.session_clear_list', html, f"{p} 必须包含 session_clear_list 样式")
            self.assertIn('max-width: 480px !important;', html, f"{p} 表格最大宽度需舒展至 480px")
            self.assertIn('width: 280px !important;', html, f"{p} 表格第一列需拓宽至 280px 消除文字折行重叠")

            # 校验 js/php.js 中 select 移除了内联 style='width:100px;' 且 placeholder 带 pt 包裹
            js_file = os.path.join(ROOT_DIR, 'plugins', p, 'js', 'php.js')
            with open(js_file, 'r', encoding='utf-8') as f:
                js_content = f.read()
            self.assertNotIn("<select class='bt-input-text' name='limit' style='width:100px;'>", js_content,
                             f"{p} 的并发方案 select 不应写死 100px 宽度")
            self.assertIn("pt('如果没有密码留空')", js_content,
                             f"{p} 的密码 placeholder 必须包含 pt('如果没有密码留空')")

    def test_04_public_json_configuration_terms_coverage(self):
        """测试 4: 校验 6 国语言包中 public.json 配置文件提示词条 100% 覆盖"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = ['tip_use_ctrl_to_1', 'this_is_1', 'main_configuration_file_if', 'save_4']

        for lang in langs:
            p = os.path.join(ROOT_DIR, 'web', 'static', 'language', lang, 'public.json')
            self.assertTrue(os.path.exists(p), f"{p} 文件必须存在")
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
            for k in required_keys:
                self.assertIn(k, d, f"{lang}/public.json 必须包含 {k} 词条")
                self.assertTrue(len(d[k].strip()) > 0, f"{lang}/public.json 的 {k} 不能为空")


if __name__ == '__main__':
    unittest.main()
