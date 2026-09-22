# -*- coding: utf-8 -*-
import os
import re
import json
import unittest
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MYSQL_LANG_DIR = os.path.join(PROJECT_ROOT, "plugins", "mysql", "lang")
MARIADB_LANG_DIR = os.path.join(PROJECT_ROOT, "plugins", "mariadb", "lang")
MYSQL_JS_PATH = os.path.join(PROJECT_ROOT, "plugins", "mysql", "js", "mysql.js")
MARIADB_JS_PATH = os.path.join(PROJECT_ROOT, "plugins", "mariadb", "js", "mariadb.js")

EXPECTED_KEYS = [
    "数据权限",
    "全部 (A) - 读写及修改表结构",
    "读写 (RW) - 仅增删改查数据",
    "只读 (RO) - 仅查询数据",
    "全部权限(A): 允许数据读写与创建/修改/删除表结构",
    "读写权限(RW): 仅允许数据增删改查，禁止修改表结构",
    "只读权限(RO): 仅允许数据查询，禁止任何写入",
    "【全部 (A)】拥有数据库全部权限，允许增删改查数据及创建/修改/删除表结构（默认推荐）。",
    "【读写 (RW)】仅允许对现有表数据进行增删改查，禁止创建、删除或修改表结构（防误删表）。",
    "【只读 (RO)】仅允许执行查询操作，禁止任何数据写入与表结构修改（适合只读从库与报表）。"
]

LANGUAGES = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
WESTERN_LANGS = ["en", "de", "fr", "it"]

class TestMysqlMariadbRwI18nAndLayout(unittest.TestCase):

    def test_01_mysql_and_mariadb_lang_files_completeness(self):
        """验证 MySQL 和 MariaDB 的全部 6 国语言包中 10 个数据权限词条完整且有效"""
        chinese_char_pattern = re.compile(r'[\u4e00-\u9fa5]')

        for plugin_name, lang_dir in [("MySQL", MYSQL_LANG_DIR), ("MariaDB", MARIADB_LANG_DIR)]:
            for lang in LANGUAGES:
                file_path = os.path.join(lang_dir, f"{lang}.json")
                self.assertTrue(os.path.exists(file_path), f"[{plugin_name}] Missing lang file: {file_path}")

                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for key in EXPECTED_KEYS:
                    self.assertIn(key, data, f"[{plugin_name} - {lang}] Key '{key}' not found in {lang}.json")
                    val = data[key]
                    self.assertTrue(bool(val and val.strip()), f"[{plugin_name} - {lang}] Key '{key}' has empty translation")

                    # 西欧语言包中绝不能残留汉字
                    if lang in WESTERN_LANGS:
                        has_chinese = bool(chinese_char_pattern.search(val))
                        self.assertFalse(has_chinese, f"[{plugin_name} - {lang}] Key '{key}' contains untranslated Chinese: {val}")

    def test_02_frontend_js_pt_calls(self):
        """验证 mysql.js 和 mariadb.js 中数据权限相关词条均被 pt() 正确包裹"""
        for js_name, js_path in [("mysql.js", MYSQL_JS_PATH), ("mariadb.js", MARIADB_JS_PATH)]:
            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            for key in EXPECTED_KEYS:
                # 检查是否存在 pt('key') 或 pt("key")
                pt_single = f"pt('{key}')"
                pt_double = f'pt("{key}")'
                self.assertTrue(pt_single in content or pt_double in content,
                                f"[{js_name}] Text '{key}' is not properly wrapped with pt(...)")

    def test_03_frontend_js_badges_and_table_layout(self):
        """验证 mysql.js 和 mariadb.js 中的防折行容器与 flex 布局"""
        for js_name, js_path in [("mysql.js", MYSQL_JS_PATH), ("mariadb.js", MARIADB_JS_PATH)]:
            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证徽章容器 nowrap
            self.assertIn("white-space:nowrap", content, f"[{js_name}] Missing white-space:nowrap in badges")
            self.assertIn("inline-flex", content, f"[{js_name}] Missing inline-flex in badges")
            self.assertIn("flex-shrink:0", content, f"[{js_name}] Missing flex-shrink:0 in badges")

            # 验证数据库名单元格 flex 布局与 text-overflow:ellipsis
            self.assertIn("display:flex", content, f"[{js_name}] Missing display:flex in table row")
            self.assertIn("text-overflow:ellipsis", content, f"[{js_name}] Missing text-overflow:ellipsis for long db name")
            self.assertIn("flex-wrap:nowrap", content, f"[{js_name}] Missing flex-wrap:nowrap in table row")

            # 验证表头 min-width 和 nowrap
            self.assertIn("min-width:130px", content, f"[{js_name}] Missing min-width:130px in thead db name")

    def test_04_node_syntax_check(self):
        """使用 Node.js 编译检查 JS 语法正确性"""
        for js_path in [MYSQL_JS_PATH, MARIADB_JS_PATH]:
            cmd = ["node", "-c", js_path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"JS Syntax Error in {js_path}: {res.stderr}")

    def test_05_mock_render_i18n_output(self):
        """通过模拟渲染验证在英文环境下的 title 文本输出为纯正英文"""
        with open(os.path.join(MYSQL_LANG_DIR, "en.json"), "r", encoding="utf-8") as f:
            en_dict = json.load(f)

        def pt(k):
            return en_dict.get(k, k)

        # 模拟前端计算 title
        rwTitle_all = pt('全部权限(A): 允许数据读写与创建/修改/删除表结构')
        rwTitle_rw = pt('读写权限(RW): 仅允许数据增删改查，禁止修改表结构')
        rwTitle_r = pt('只读权限(RO): 仅允许数据查询，禁止任何写入')

        self.assertEqual(rwTitle_all, "ALL (A): Allows read/write and create/alter/drop schema")
        self.assertEqual(rwTitle_rw, "Read/Write (RW): Allows DML only, schema alterations forbidden")
        self.assertEqual(rwTitle_r, "Read-Only (RO): Query only, all writes forbidden")

        # 模拟下拉选项
        opt_all = pt('全部 (A) - 读写及修改表结构')
        self.assertEqual(opt_all, "ALL (A) - Read, write and alter schema")


if __name__ == "__main__":
    unittest.main()
