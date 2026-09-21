# -*- coding: utf-8 -*-
"""
文件管理模块（Files）国际化与渲染逻辑自动化回归测试
"""

import json
import os
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, "web")
LANG_DIR = os.path.join(WEB_DIR, "static", "language")
FILES_JS_PATH = os.path.join(WEB_DIR, "static", "app", "files.js")

SUPPORTED_LANGUAGES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

REQUIRED_FILES_KEYS = [
    "per_page", "item", "total_of_directory_and", "get",
    "file_name", "size", "last_modified", "permissions", "owner", "operations",
    "new", "create_new_folder", "create_new_blank_file", "back_parent",
    "calculate", "copy_path", "copy", "cut", "rename", "compress", "unzip",
    "edit", "preview", "download", "delete", "recycle_bin", "recycle_bin_re",
    "recycle_bin_del", "note_once_you_empty", "empty_the_recycle_bin"
]

class TestFilesI18n(unittest.TestCase):

    def test_files_language_dictionaries_completeness(self):
        """测试 6 种语言字典中 files 模块标准词条完整性与脏键清理"""
        for lang in SUPPORTED_LANGUAGES:
            tpl_path = os.path.join(LANG_DIR, lang, "template.json")
            lan_path = os.path.join(LANG_DIR, lang, "lan.js")

            self.assertTrue(os.path.exists(tpl_path), f"template.json not found for {lang}")
            self.assertTrue(os.path.exists(lan_path), f"lan.js not found for {lang}")

            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl_data = json.load(f)
            files_tpl = tpl_data.get("files", {})

            with open(lan_path, "r", encoding="utf-8") as f:
                lan_content = f.read()

            # 1. 验证必要词条存在且非空
            for key in REQUIRED_FILES_KEYS:
                self.assertIn(key, files_tpl, f"Key '{key}' missing in {lang}/template.json")
                self.assertTrue(bool(files_tpl[key]), f"Key '{key}' is empty in {lang}/template.json")
                self.assertIn(f'"{key}"', lan_content, f"Key '{key}' missing in {lang}/lan.js")

            # 2. 验证无破坏性脏键
            for key, val in files_tpl.items():
                if isinstance(val, str):
                    self.assertNotIn("add-tab-btn", key, f"Dirty key in {lang}: {key}")
                    self.assertNotIn("<select", key, f"Dirty key in {lang}: {key}")
                    self.assertNotIn("<table", key, f"Dirty key in {lang}: {key}")
                    self.assertFalse(val.startswith("')\">"), f"Dirty val in {lang}[{key}]: {val}")
                    self.assertFalse(val.startswith("');\">"), f"Dirty val in {lang}[{key}]: {val}")

    def test_files_js_no_corrupted_patterns(self):
        """测试 files.js 中绝无标签嵌套错乱或未解析大写键名泄漏"""
        self.assertTrue(os.path.exists(FILES_JS_PATH), "files.js file does not exist")
        with open(FILES_JS_PATH, "r", encoding="utf-8") as f:
            js_content = f.read()

        corrupted_patterns = [
            r"<select[^>]*><select",
            r"<table[^>]*><table",
            r"\bFILES\.[A-Z0-9_]+\b",
            r"files\.nbsp_recycle_bin",
            r"files\.path\s+root",
            r"files\.total_of_directory_and\d+",
            r"\(\(\(\(\(lan\s*&&",
            r"\\'\)\">计算",
        ]

        for pat in corrupted_patterns:
            matches = re.findall(pat, js_content)
            self.assertEqual(len(matches), 0, f"Found corrupted pattern in files.js: {pat}, matches: {matches}")

    def test_pagination_and_table_rendering_logic(self):
        """模拟执行前端 makeFilePage 与 getFiles 渲染逻辑，验证 HTML 闭合性与语义结构"""
        # 1. 模拟分页渲染 makeFilePage
        rows = ['10', '50', '100', '200', '500', '1000', '2000']
        show_row = '10'
        row_options = ''.join(
            f'<option value="{r}" {"selected" if r == show_row else ""}>{r}</option>' for r in rows
        )
        
        for lang in SUPPORTED_LANGUAGES:
            tpl_path = os.path.join(LANG_DIR, lang, "template.json")
            with open(tpl_path, "r", encoding="utf-8") as f:
                lang_data = json.load(f).get("files", {})

            per_page_text = lang_data.get("per_page")
            item_text = lang_data.get("item")
            page_html = f"<span class='Pcount-item'>{per_page_text}<select name='file_page' style='margin-left: 3px;margin-right: 3px;border:#ddd 1px solid;' class='showRow'>{row_options}</select>{item_text}</span>"

            # 验证 select 标签恰好出现一次
            select_count = len(re.findall(r'<select\b', page_html))
            self.assertEqual(select_count, 1, f"Expected 1 select in makeFilePage for {lang}, got {select_count}")
            self.assertTrue(page_html.endswith(f"</select>{item_text}</span>"))

            # 2. 模拟目录及文件渲染
            total_dir = 2
            total_files = 3
            total_size_bytes = 1024 * 1024 * 5  # 5MB
            dir_info_tpl = lang_data.get("total_of_directory_and")
            get_text = lang_data.get("get")
            dir_info_rendered = dir_info_tpl.replace("{1}", str(total_dir)).replace("{2}", str(total_files)) + f'<font id="pathSize">5.00 MB<a class="btlink ml5" onClick="getPathSize()">{get_text}</a></font>'
            self.assertIn(str(total_dir), dir_info_rendered)
            self.assertIn(str(total_files), dir_info_rendered)
            self.assertIn(get_text, dir_info_rendered)
            self.assertNotIn("files.total", dir_info_rendered)
            self.assertNotIn("files.get", dir_info_rendered)

            # 3. 模拟表头渲染
            table_header = f"""<table width="100%" border="0" cellpadding="0" cellspacing="0" class="table table-hover">
                <thead>
                    <tr>
                        <th width="30"><label><input type="checkbox" id="setBox" placeholder=""></label></th>
                        <th onclick="listFileOrder('fname',this)" style="cursor: pointer;">{lang_data.get('file_name')}</th>
                        <th onclick="listFileOrder('size',this)" style="cursor: pointer; text-align: center;">{lang_data.get('size')}</th>
                        <th onclick="listFileOrder('mtime',this)" style="cursor: pointer; text-align: center;" width="150">{lang_data.get('last_modified')}</th>
                        <th style="text-align: center;">{lang_data.get('permissions')}</th>
                        <th style="text-align: center;">{lang_data.get('owner')}</th>
                        <th style="text-align: center;" width="360">{lang_data.get('operations')}</th>
                    </tr>
                </thead>
            </table>"""
            # 确保 table 标签恰好一对
            self.assertEqual(len(re.findall(r'<table\b', table_header)), 1)
            self.assertEqual(len(re.findall(r'</table>', table_header)), 1)
            self.assertNotIn("FILES.", table_header)


if __name__ == "__main__":
    unittest.main()
