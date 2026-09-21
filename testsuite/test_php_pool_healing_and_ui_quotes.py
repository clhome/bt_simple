# -*- coding: utf-8 -*-
"""
PHP 插件 No pool defined 启动失败根治与前端多页面翻译代码裸露自动化回归测试套件
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


class TestPhpPoolHealingAndUiQuotes(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='yf_php_test_')
        self.ver = '80'
        self.ver_dir = os.path.join(self.test_dir, self.ver)
        self.etc_dir = os.path.join(self.ver_dir, 'etc')
        self.pool_dir = os.path.join(self.etc_dir, 'php-fpm.d')
        os.makedirs(self.pool_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_php_fpm_replace_include_self_healing(self):
        """测试 1: phpFpmReplace 对缺少/注释/相对路径 include 的全方位自愈能力"""
        import plugins.php.index as php_mod
        orig_getServerDir = php_mod.getServerDir
        php_mod.getServerDir = lambda: self.test_dir

        try:
            fpm_conf = os.path.join(self.etc_dir, 'php-fpm.conf')
            expected_inc = f"{self.test_dir.replace('\\', '/')}/{self.ver}/etc/php-fpm.d/*.conf"

            # 场景 A: 包含被分号注释的 include
            bad_content_commented = (
                "[global]\n"
                "pid = run/php-fpm.pid\n"
                "error_log = log/php-fpm.log\n"
                ";include=etc/php-fpm.d/*.conf\n"
                "php_value[auto_prepend_file] = /www/server/php/app_start.php\n"
            )
            with open(fpm_conf, 'w', encoding='utf-8') as f:
                f.write(bad_content_commented)

            php_mod.phpFpmReplace(self.ver)

            with open(fpm_conf, 'r', encoding='utf-8') as f:
                healed = f.read()

            self.assertNotIn(';include', healed, "被注释的 include 必须被取消注释自愈")
            self.assertIn(f"include = {expected_inc}", healed, "include 必须被校准为规范绝对路径")
            self.assertNotIn('php_value', healed, "非法全局 php_value 必须被清除")

            # 场景 B: 包含相对路径的未注释 include
            bad_content_relative = (
                "[global]\n"
                "pid = run/php-fpm.pid\n"
                "error_log = log/php-fpm.log\n"
                "include = etc/php-fpm.d/*.conf\n"
            )
            with open(fpm_conf, 'w', encoding='utf-8') as f:
                f.write(bad_content_relative)

            php_mod.phpFpmReplace(self.ver)

            with open(fpm_conf, 'r', encoding='utf-8') as f:
                healed_b = f.read()
            self.assertIn(f"include = {expected_inc}", healed_b, "相对路径 include 必须被校准为绝对路径")

            # 场景 C: 完全没有 include
            bad_content_no_include = (
                "[global]\n"
                "pid = run/php-fpm.pid\n"
                "error_log = log/php-fpm.log\n"
            )
            with open(fpm_conf, 'w', encoding='utf-8') as f:
                f.write(bad_content_no_include)

            php_mod.phpFpmReplace(self.ver)

            with open(fpm_conf, 'r', encoding='utf-8') as f:
                healed_c = f.read()
            self.assertIn(f"include = {expected_inc}", healed_c, "缺少 include 必须被自动追加补齐")

        finally:
            php_mod.getServerDir = orig_getServerDir

    def test_02_php_fpm_pool_replace_www_healing(self):
        """测试 2: phpFpmPoolReplace 对缺失/空文件/缺少池节区的 www.conf 自愈能力"""
        import plugins.php.index as php_mod
        orig_getServerDir = php_mod.getServerDir
        php_mod.getServerDir = lambda: self.test_dir

        try:
            www_conf = os.path.join(self.pool_dir, 'www.conf')

            # 场景 A: www.conf 不存在
            if os.path.exists(www_conf):
                os.remove(www_conf)
            php_mod.phpFpmPoolReplace(self.ver, 'www')
            self.assertTrue(os.path.exists(www_conf), "www.conf 必须被自动生成")
            with open(www_conf, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('[www]', content, "自动生成的 www.conf 必须包含 [www] 池段")
            self.assertIn('pm = ', content, "必须包含 pm 进程模式")

            # 场景 B: www.conf 为 0 字节损坏文件
            with open(www_conf, 'w', encoding='utf-8') as f:
                f.write('')
            php_mod.phpFpmPoolReplace(self.ver, 'www')
            with open(www_conf, 'r', encoding='utf-8') as f:
                healed_empty = f.read()
            self.assertIn('[www]', healed_empty, "0 字节损坏文件必须被安全自愈重建")

            # 场景 C: www.conf 内容缺少 [www] 标识
            with open(www_conf, 'w', encoding='utf-8') as f:
                f.write('# invalid broken pool without section\n')
            php_mod.phpFpmPoolReplace(self.ver, 'www')
            with open(www_conf, 'r', encoding='utf-8') as f:
                healed_nosect = f.read()
            self.assertIn('[www]', healed_nosect, "无池节区文件必须被自愈重建")

        finally:
            php_mod.getServerDir = orig_getServerDir

    def test_03_js_template_quotes_integrity(self):
        """测试 3: 词法级精准扫描三款插件 js/php.js 中双引号/单引号模板内部 pt(...) 代码裸露"""
        js_files = [
            os.path.join(ROOT_DIR, 'plugins', 'php', 'js', 'php.js'),
            os.path.join(ROOT_DIR, 'plugins', 'php-apt', 'js', 'php.js'),
            os.path.join(ROOT_DIR, 'plugins', 'php-yum', 'js', 'php.js')
        ]

        def scan_js_for_leaks(content):
            pos = 0
            n = len(content)
            findings = []
            while pos < n:
                ch = content[pos]
                # 单行注释
                if ch == '/' and pos + 1 < n and content[pos + 1] == '/':
                    pos = content.find('\n', pos)
                    if pos == -1:
                        break
                    continue
                # 多行注释
                if ch == '/' and pos + 1 < n and content[pos + 1] == '*':
                    end = content.find('*/', pos + 2)
                    pos = n if end == -1 else end + 2
                    continue
                # 双引号字符串
                if ch == '"':
                    start_pos = pos
                    pos += 1
                    chars = []
                    while pos < n:
                        c = content[pos]
                        if c == '\\':
                            if pos + 1 < n:
                                chars.append(content[pos:pos+2])
                                pos += 2
                                continue
                        elif c == '"':
                            pos += 1
                            break
                        chars.append(c)
                        pos += 1
                    s = ''.join(chars)
                    if ("' + pt(" in s) or (") + '" in s):
                        line_no = content[:start_pos].count('\n') + 1
                        findings.append((line_no, "DOUBLE_QUOTE_LEAK", s[:80]))
                    continue
                # 单引号字符串
                if ch == "'":
                    start_pos = pos
                    pos += 1
                    chars = []
                    while pos < n:
                        c = content[pos]
                        if c == '\\':
                            if pos + 1 < n:
                                chars.append(content[pos:pos+2])
                                pos += 2
                                continue
                        elif c == "'":
                            pos += 1
                            break
                        chars.append(c)
                        pos += 1
                    s = ''.join(chars)
                    if ('" + pt(' in s) or (') + "' in s):
                        line_no = content[:start_pos].count('\n') + 1
                        findings.append((line_no, "SINGLE_QUOTE_LEAK", s[:80]))
                    continue
                pos += 1
            return findings

        broken_findings = []
        for js_path in js_files:
            rel_name = os.path.relpath(js_path, ROOT_DIR)
            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()
            leaks = scan_js_for_leaks(content)
            for line_no, leak_type, snippet in leaks:
                broken_findings.append(f"{rel_name}:L{line_no} [{leak_type}]: {snippet}")

        self.assertEqual(len(broken_findings), 0, f"发现前端模板引号混淆/代码裸露:\n" + "\n".join(broken_findings))

    def test_04_i18n_common_and_note_translations(self):
        """测试 4: 校验 6 国语言包中“常用功能”精炼为 Common 与 public.note 覆盖"""
        # 1. 验证三款 PHP 插件的常用功能在各语言下精炼
        for plugin in ['php', 'php-apt', 'php-yum']:
            en_path = os.path.join(ROOT_DIR, 'plugins', plugin, 'lang', 'en.json')
            with open(en_path, 'r', encoding='utf-8') as f:
                en_dict = json.load(f)
            self.assertEqual(en_dict.get('常用功能'), 'Common', f"{plugin} 的英文 常用功能 必须精炼为 Common 消除截断")

            fr_path = os.path.join(ROOT_DIR, 'plugins', plugin, 'lang', 'fr.json')
            with open(fr_path, 'r', encoding='utf-8') as f:
                fr_dict = json.load(f)
            self.assertEqual(fr_dict.get('常用功能'), 'Commun', f"{plugin} 的法文 常用功能 必须精炼为 Commun")

            it_path = os.path.join(ROOT_DIR, 'plugins', plugin, 'lang', 'it.json')
            with open(it_path, 'r', encoding='utf-8') as f:
                it_dict = json.load(f)
            self.assertEqual(it_dict.get('常用功能'), 'Comune', f"{plugin} 的意文 常用功能 必须精炼为 Comune")

        # 2. 验证 public.json 中 note 键 100% 覆盖
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        for lang in langs:
            pub_path = os.path.join(ROOT_DIR, 'web', 'static', 'language', lang, 'public.json')
            self.assertTrue(os.path.exists(pub_path), f"{pub_path} 必须存在")
            with open(pub_path, 'r', encoding='utf-8') as f:
                pub_dict = json.load(f)
            self.assertIn('note', pub_dict, f"{lang}/public.json 必须包含 note 键以消除中英混杂")
            self.assertTrue(len(pub_dict['note']) > 0, f"{lang}/public.json 的 note 不能为空")


if __name__ == '__main__':
    unittest.main()
