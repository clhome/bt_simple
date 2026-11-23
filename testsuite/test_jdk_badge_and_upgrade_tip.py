# coding: utf-8
"""JDK 徽章汇总优化与升级版本悬浮发布时间提示测试。

验证范围：
1. _format_release_date 解析多种日期格式为 YYYY-MM-DD；
2. _normalize_jdk_items 过滤条目并完整保留 release_date；
3. get_online_jdks 包含 release_date 字段；
4. get_jdk_list 在存在可升级版本时输出 upgrade_release_date 与 latest_version；
5. index.html 中所有 pt 国际化键在 6 国语言包中 100% 存在且对称；
6. 文件编码合规性（UTF-8 无 BOM、换行符 LF）。
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)
if ROOT not in sys.path:
    sys.path.append(ROOT)

import plugins.jdk.index as jdk_mod

LANG_DIR = os.path.join(ROOT, 'plugins', 'jdk', 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']


class TestJdkBadgeAndUpgradeTip(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_jdk_test_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        self.javadir = os.path.join(self.server, 'jdk')
        self.plug = os.path.join(self.tmp, 'plugins', 'jdk')
        os.makedirs(self.javadir)
        os.makedirs(self.plug)

        self._orig_java_dir = jdk_mod.jdk_main._java_dir
        self._orig_plugin_path = jdk_mod.jdk_main._plugin_path
        self._orig_config_file = jdk_mod.jdk_main._config_file

        jdk_mod.jdk_main._java_dir = self.javadir
        jdk_mod.jdk_main._plugin_path = self.plug
        jdk_mod.jdk_main._config_file = os.path.join(self.plug, 'data.json')

    def tearDown(self):
        jdk_mod.jdk_main._java_dir = self._orig_java_dir
        jdk_mod.jdk_main._plugin_path = self._orig_plugin_path
        jdk_mod.jdk_main._config_file = self._orig_config_file

    def test_format_release_date(self):
        """测试 _format_release_date 对各种日期字符串的解析"""
        self.assertEqual(jdk_mod._format_release_date('18 Nov 2026 21:07:43 +0000'), '2026-11-18')
        self.assertEqual(jdk_mod._format_release_date('20 Jan 2026'), '2026-01-20')
        self.assertEqual(jdk_mod._format_release_date('2026-02-15'), '2026-02-15')
        self.assertEqual(jdk_mod._format_release_date(''), '')
        self.assertEqual(jdk_mod._format_release_date(None), '')

    def test_normalize_jdk_items_preserves_date(self):
        """测试 _normalize_jdk_items 能正确保留 release_date 字段"""
        raw = [
            {
                "version": "jdk-21",
                "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.13.1_1.tar.gz",
                "release_date": "2026-11-18"
            },
            {
                "version": "jdk-invalid",
                "url": "http://evil.com/bad.tar.gz",
                "release_date": "2026-01-01"
            }
        ]
        norm = jdk_mod._normalize_jdk_items(raw)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0]['version'], 'jdk-21')
        self.assertEqual(norm[0]['release_date'], '2026-11-18')

    def test_get_online_jdks_contains_release_date(self):
        """测试 get_online_jdks 读取缓存或默认清单均包含 release_date"""
        main = jdk_mod.jdk_main()
        # 写入模拟缓存
        fake_cache = [
            {"version": "jdk-21", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.13.1_1.tar.gz", "release_date": "2026-11-18"},
            {"version": "jdk-25", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/25/jdk/x64/linux/OpenJDK25U-jdk_x64_linux_hotspot_25.0.5.1_1.tar.gz", "release_date": "2026-01-20"}
        ]
        with open(os.path.join(self.plug, 'versions.json'), 'w', encoding='utf-8') as f:
            json.dump(fake_cache, f)

        res = main.get_online_jdks()
        self.assertTrue(len(res) >= 2)
        v21 = next((x for x in res if x['version'] == 'jdk-21'), None)
        self.assertIsNotNone(v21)
        self.assertEqual(v21.get('release_date'), '2026-11-18')

    def test_get_jdk_list_upgrade_release_date(self):
        """测试已安装 JDK 有更新版本时返回 upgrade_release_date 与 latest_version"""
        main = jdk_mod.jdk_main()
        fake_cache = [
            {"version": "jdk-21", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.13.1_1.tar.gz", "release_date": "2026-11-18"},
            {"version": "jdk-25", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/25/jdk/x64/linux/OpenJDK25U-jdk_x64_linux_hotspot_25.0.5.1_1.tar.gz", "release_date": "2026-01-20"}
        ]
        with open(os.path.join(self.plug, 'versions.json'), 'w', encoding='utf-8') as f:
            json.dump(fake_cache, f)

        # 模拟安装 jdk-21 的旧版本
        jdk21_bin = os.path.join(self.javadir, 'jdk-21', 'bin')
        os.makedirs(jdk21_bin)
        java_exe = os.path.join(jdk21_bin, 'java')
        with open(java_exe, 'w') as f:
            f.write('#!/bin/sh\nexit 0\n')

        # mock _get_jdk_version_info
        orig_getinfo = jdk_mod._get_jdk_version_info
        try:
            jdk_mod._get_jdk_version_info = lambda p, f: ('21.0.12.1', 'openjdk 21.0.12.1')
            json_str = main.get_jdk_list()
            data = json.loads(json_str)
            self.assertTrue(data.get('status'))
            res = data.get('msg', {}).get('list', [])
            item21 = next((x for x in res if x['name'] == 'jdk-21'), None)
            self.assertIsNotNone(item21)
            self.assertTrue(item21.get('can_upgrade'))
            self.assertEqual(item21.get('latest_version'), '21.0.13.1')
            self.assertEqual(item21.get('upgrade_release_date'), '2026-11-18')
        finally:
            jdk_mod._get_jdk_version_info = orig_getinfo

    def test_i18n_keys_symmetry_and_completeness(self):
        """测试 6 国语言包键集合 100% 包含 index.html 中引用的所有 pt 键"""
        html_file = os.path.join(ROOT, 'plugins', 'jdk', 'index.html')
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()

        pt_keys = set(re.findall(r"pt\(\s*'([^']+)'\s*\)", html))
        self.assertTrue(len(pt_keys) > 0)

        for lang in LANGS:
            lang_file = os.path.join(LANG_DIR, f"{lang}.json")
            self.assertTrue(os.path.exists(lang_file), f"Language file missing: {lang_file}")
            with open(lang_file, 'r', encoding='utf-8') as f:
                d = json.load(f)

            missing = [k for k in pt_keys if k not in d]
            self.assertEqual(missing, [], f"Language {lang} is missing keys: {missing}")

    def test_file_encoding_and_line_endings(self):
        """验证修改的源文件均为 UTF-8 编码且不含 CRLF (\\r\\n) 换行符"""
        checked_files = [
            os.path.join(ROOT, 'plugins', 'jdk', 'index.py'),
            os.path.join(ROOT, 'plugins', 'jdk', 'index.html'),
        ]
        for lang in LANGS:
            checked_files.append(os.path.join(LANG_DIR, f"{lang}.json"))

        for fp in checked_files:
            with open(fp, 'rb') as f:
                raw_bytes = f.read()
            # 严禁带 BOM
            self.assertFalse(raw_bytes.startswith(b'\xef\xbb\xbf'), f"BOM detected in {fp}")
            # 严禁含 CRLF
            self.assertNotIn(b'\r\n', raw_bytes, f"CRLF (\\r\\n) detected in {fp}")
            # 必须为合法 UTF-8
            raw_bytes.decode('utf-8')


if __name__ == '__main__':
    unittest.main()
