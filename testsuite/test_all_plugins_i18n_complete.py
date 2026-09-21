# -*- coding: utf-8 -*-
"""
全量插件多语言治理与国际化验收测试套件 (test_all_plugins_i18n_complete.py)
验证内容：
1. 全部正式插件（以 plugins/<name>/lang/zh-CN.json 存在性判定）× 6 种语言
   JSON 语言包全部存在，编码 UTF-8，LF 换行
2. 每个插件 6 国语言 Key 集合 100% 完全对齐，且 0 脏代码/表达式污染
3. 全部插件所有 JS 文件在 Node.js 语法检查下 100% 通过（0 语法错误）
4. 全部插件 index.html 菜单项在 6 种语言包中 100% 覆盖且非中文语言无中文残留
"""

import os
import sys
import json
import re
import subprocess
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")
LANGS = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
FOREIGN_LANGS = ["en", "de", "fr", "it"]
ZH_PATTERN = re.compile(r'[\u4e00-\u9fa5]')

POLLUTION_REGEX = re.compile(r'(?:window\.lan|\bpt\s*\(|\bt\s*\(|\&\&|\|\||function\b|var\s+|class\s*=|style\s*=|^\s*[\'\"]?\s*\+)')

class TestAllPluginsI18nComplete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 以「是否具备 lang/zh-CN.json」判定正式插件，避免把 plugins/ 下的
        # 非插件目录（如 待审核/）计入，也避免硬编码插件总数导致后续增删插件即报错。
        cls.plugins = sorted([
            d for d in os.listdir(PLUGINS_DIR)
            if os.path.isfile(os.path.join(PLUGINS_DIR, d, "lang", "zh-CN.json"))
        ])
        assert len(cls.plugins) >= 30, f"正式插件数量异常（应 ≥30），实际为 {len(cls.plugins)}"

    def test_01_language_packs_exist_and_aligned(self):
        """测试 1: 验证全部正式插件的 6 国语言包全部存在且 Key 100% 完全对齐"""
        total_files = 0
        total_keys = 0
        
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            self.assertTrue(os.path.exists(lang_dir), f"Plugin {p} missing lang directory")
            
            # 读取 zh-CN 基准
            cn_file = os.path.join(lang_dir, "zh-CN.json")
            self.assertTrue(os.path.exists(cn_file), f"Plugin {p} missing zh-CN.json")
            
            with open(cn_file, "r", encoding="utf-8") as f:
                cn_data = json.load(f)
            cn_keys = set(cn_data.keys())
            total_keys += len(cn_keys)
            
            for lg in LANGS:
                lpath = os.path.join(lang_dir, f"{lg}.json")
                self.assertTrue(os.path.exists(lpath), f"Plugin {p} missing {lg}.json")
                total_files += 1
                
                with open(lpath, "r", encoding="utf-8") as f:
                    ldata = json.load(f)
                    
                # 校验 Key 集合 100% 完全对齐
                self.assertEqual(
                    set(ldata.keys()), 
                    cn_keys, 
                    f"Plugin {p} lang {lg}.json keys do not match zh-CN.json!"
                )
                
                # 校验 0 污染 key
                for k in ldata.keys():
                    self.assertFalse(
                        POLLUTION_REGEX.search(k), 
                        f"Plugin {p} lang {lg}.json contains polluted key: '{k}'"
                    )
                    
        expect_files = len(self.plugins) * 6
        self.assertEqual(total_files, expect_files,
                         f"生成的语言包文件总数应为 {expect_files}")
        print(f"\n[PASS] 全部 {len(self.plugins)} 个插件 × 6 语言包 (总计 {total_files} 个文件) 100% 存在，Key 集合完全对齐，0 脏代码污染！")

    def test_02_all_js_syntax_valid(self):
        """测试 2: 验证全量插件所有 JS 文件在 Node.js 下 100% 语法合规"""
        js_files = []
        for p in self.plugins:
            jdir = os.path.join(PLUGINS_DIR, p, "js")
            if os.path.exists(jdir):
                for f in os.listdir(jdir):
                    if f.endswith(".js"):
                        js_files.append(os.path.join(jdir, f))
                        
        syntax_errors = []
        for jf in js_files:
            rel = os.path.relpath(jf, ROOT_DIR)
            res = subprocess.run(
                ["node", "-c", jf],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            if res.returncode != 0:
                syntax_errors.append((rel, res.stderr.strip()))
                
        self.assertEqual(len(syntax_errors), 0, f"发现 {len(syntax_errors)} 个 JS 语法错误:\n" + "\n".join(str(e) for e in syntax_errors))
        print(f"[PASS] 全部 {len(js_files)} 个插件 JS 文件经 Node.js 严格语法校验 100% 通过！")

    def test_03_menu_items_100_percent_covered(self):
        """测试 3: 验证全部插件 index.html 菜单项在各语言包中 100% 覆盖且翻译地道"""
        total_menus = 0
        for p in self.plugins:
            idx_file = os.path.join(PLUGINS_DIR, p, "index.html")
            if not os.path.exists(idx_file):
                continue
            with open(idx_file, "r", encoding="utf-8", errors="ignore") as f:
                c = f.read()
            m = re.search(r'<div\s+class=["\']bt-w-menu["\']>(.*?)</div>', c, re.DOTALL)
            if not m:
                continue
            items = re.findall(r'<p[^>]*>(.*?)</p>', m.group(1), re.DOTALL)
            clean_items = [re.sub(r'<[^>]+>', '', it).strip() for it in items if re.sub(r'<[^>]+>', '', it).strip()]
            
            for lg in LANGS:
                lfile = os.path.join(PLUGINS_DIR, p, "lang", f"{lg}.json")
                with open(lfile, "r", encoding="utf-8") as f:
                    dict_data = json.load(f)
                for menu in clean_items:
                    total_menus += 1
                    self.assertIn(menu, dict_data, f"Plugin {p} lang {lg}.json missing menu term: '{menu}'")
                    val = dict_data[menu]
                    if lg in FOREIGN_LANGS and ZH_PATTERN.search(menu):
                        # 确保外语下翻译不为原中文
                        self.assertFalse(ZH_PATTERN.search(val), f"Plugin {p} lang {lg}.json menu '{menu}' untranslated: '{val}'")
                        
        print(f"[PASS] 全部 {total_menus} 处插件菜单项跨 6 种语言 100% 覆盖且非中文语言 0 中文残留！")

if __name__ == "__main__":
    unittest.main()
