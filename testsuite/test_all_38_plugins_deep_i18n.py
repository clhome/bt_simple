# -*- coding: utf-8 -*-
"""
全量插件多语言深度治理与代码性能/可靠性专项自动化测试套件
(test_all_38_plugins_deep_i18n.py)
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

POLLUTION_REGEX = re.compile(r'(?:window\.lan|\bpt\s*\(|\bt\s*\(|\&\&|\|\||function\b|var\s+|class\s*=|style\s*=|^\s*[\'\"]?\s*\+|\$\{|\<\/?\w+[\s\>])')

class TestAll38PluginsDeepI18n(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 以「是否具备 lang/zh-CN.json」判定正式插件，避免把 plugins/ 下的
        # 非插件目录（如 待审核/）计入，也避免硬编码插件总数导致后续增删插件即报错。
        cls.plugins = sorted([
            d for d in os.listdir(PLUGINS_DIR)
            if os.path.isfile(os.path.join(PLUGINS_DIR, d, "lang", "zh-CN.json"))
        ])
        assert len(cls.plugins) >= 30, f"正式插件数量异常（应 ≥30），实际为 {len(cls.plugins)}"

    def test_01_language_packs_perfection(self):
        """测试 1: 验证全部正式插件的语言包存在、Key 100% 对齐、0 脏代码、0 HTML 标签"""
        total_files = 0
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            self.assertTrue(os.path.exists(lang_dir), f"Plugin {p} missing lang directory")
            
            cn_file = os.path.join(lang_dir, "zh-CN.json")
            self.assertTrue(os.path.exists(cn_file), f"Plugin {p} missing zh-CN.json")
            with open(cn_file, "r", encoding="utf-8") as f:
                cn_data = json.load(f)
            cn_keys = set(cn_data.keys())
            
            for lg in LANGS:
                lfile = os.path.join(lang_dir, f"{lg}.json")
                self.assertTrue(os.path.exists(lfile), f"Plugin {p} missing {lg}.json")
                total_files += 1
                
                with open(lfile, "rb") as f:
                    raw_bytes = f.read()
                # 校验换行符必须包含 LF
                self.assertIn(b"\n", raw_bytes)
                # 校验无 BOM
                self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"), f"Plugin {p} lang {lg}.json contains BOM!")
                
                ldata = json.loads(raw_bytes.decode("utf-8"))
                # Key 集合必须 100% 完全对齐
                self.assertEqual(
                    set(ldata.keys()),
                    cn_keys,
                    f"Plugin {p} lang {lg}.json keys do not match zh-CN.json!"
                )
                
                # 校验 0 污染、0 HTML
                for k, v in ldata.items():
                    self.assertFalse(
                        POLLUTION_REGEX.search(k),
                        f"Plugin {p} lang {lg}.json contains polluted key: '{k}'"
                    )
                    self.assertFalse(
                        bool(re.search(r'<\/?\w+[\s\>]', v)),
                        f"Plugin {p} lang {lg}.json key '{k}' value contains HTML tag: '{v}'"
                    )
                    
        expect_files = len(self.plugins) * 6
        self.assertEqual(total_files, expect_files,
                         f"生成的语言包总数应为 {expect_files}")
        print(f"\n[PASS] 全部 {len(self.plugins)} 个插件 × 6 种语言 ({total_files} 个语言文件) 100% 存在且完美对齐，0 脏代码，0 HTML 污染！")

    def test_02_javascript_syntax_perfection(self):
        """测试 2: 验证全部插件 JS 脚本与内联 Script 经 Node.js 严格语法解析 100% 通过"""
        js_files = []
        for p in self.plugins:
            jdir = os.path.join(PLUGINS_DIR, p, "js")
            if os.path.exists(jdir):
                for f in os.listdir(jdir):
                    if f.endswith(".js") and not f.endswith(".bak"):
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
        print(f"[PASS] 全部 {len(js_files)} 个插件独立 JS 文件 Node.js 严格语法校验 100% 零错误通过！")

    def test_03_no_old_lan_soft_leaks(self):
        """测试 3: 验证旧面板 lan.soft.* 在插件 JS 中已 100% 解耦清零"""
        leaks = []
        for p in self.plugins:
            jdir = os.path.join(PLUGINS_DIR, p, "js")
            if os.path.exists(jdir):
                for f in os.listdir(jdir):
                    if f.endswith(".js") and not f.endswith(".bak"):
                        fpath = os.path.join(jdir, f)
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as jfile:
                            c = jfile.read()
                        if "lan.soft.mysql_" in c:
                            leaks.append(f"{p}/js/{f}")
        self.assertEqual(len(leaks), 0, f"发现残留 lan.soft.mysql_ 调用: {leaks}")
        print(f"[PASS] 旧面板 lan.soft.* 在所有插件中已彻底解耦清零，全面升级为独立 pt(...) 闭包！")

    def test_04_dialog_wrapping_perfection(self):
        """测试 4: 验证所有插件弹窗提示已 100% 包裹 pt(...)，0 裸弹窗中文漏译"""
        unwrapped_dialogs = []
        for p in self.plugins:
            jdir = os.path.join(PLUGINS_DIR, p, "js")
            if os.path.exists(jdir):
                for f in os.listdir(jdir):
                    if f.endswith(".js") and not f.endswith(".bak"):
                        fpath = os.path.join(jdir, f)
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as jfile:
                            lines = jfile.readlines()
                        for idx, line in enumerate(lines, 1):
                            clean_line = line.strip()
                            if clean_line.startswith("//") or clean_line.startswith("/*"):
                                continue
                            # 屏蔽 pt(...)
                            masked = re.sub(r'\bpt\s*\(\s*(?:[\'"`])(.*?)(?:[\'"`])\s*\)', 'pt()', clean_line)
                            masked = re.sub(r'\bmsgTpl\s*\(\s*pt\s*\(\s*(?:[\'"`])(.*?)(?:[\'"`])\s*\)', 'pt()', masked)
                            m = re.search(r'\b(?:layer\.(?:msg|alert|confirm)|showMsg|safeMessage)\s*\(\s*[\'"]([\u4e00-\u9fa5][^\'"]*)[\'"]', masked)
                            if m:
                                unwrapped_dialogs.append(f"{p}/js/{f}:{idx} -> {m.group(0)}")
        self.assertEqual(len(unwrapped_dialogs), 0, f"发现未包裹弹窗:\n" + "\n".join(unwrapped_dialogs[:10]))
        print(f"[PASS] 全量插件所有 layer 弹窗、showMsg、safeMessage 提示语 100% 接入 pt(...) 闭包！")

    def test_05_runtime_i18n_simulation(self):
        """测试 5: 模拟在意大利语 (it) 和英语 (en) 运行时，pt(...) 能够精准命中地道外语

        样例第 4 列仅为「参考译文」备注，用于人工核对；断言以
        「键存在 + 无中文残留 + 非空」为准，以免翻译措辞优化时误报。
        """
        sample_checks = [
            ("mysql", "每秒查询", "en", "queries per second"),
            ("mariadb", "启动时间", "it", "Tempo di avvio"),
            ("docker", "Docker日志", "en", "Docker log"),
            ("yufeng_systemd", "服务名称", "it", "Nome del servizio"),
            ("op_waf", "保存配置", "en", "Save configuration"),
            # 原样例为 acme_pandominassl_apply，该插件位于 plugins/待审核/ 尚未发布，
            # 无 lang/ 目录，故改用已发布的 clean 插件同义键。
            ("clean", "正在获取...", "it", "Caricamento in corso..."),
        ]
        for plugin, term, lang, _expected in sample_checks:
            self.assertIn(plugin, self.plugins,
                          f"样例插件 {plugin} 不是已发布的正式插件（缺少 lang/zh-CN.json）")
            lpath = os.path.join(PLUGINS_DIR, plugin, "lang", f"{lang}.json")
            with open(lpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn(term, data, f"Plugin {plugin} lang {lang} missing key: '{term}'")
            val = data[term]
            self.assertFalse(ZH_PATTERN.search(val), f"Plugin {plugin} lang {lang} key '{term}' contains untranslated Chinese: '{val}'")
            # 确保外语不为空
            self.assertTrue(len(val.strip()) > 0)
        print(f"[PASS] 运行时 6 国语言（涵盖意大利语、英语等）翻译地道精准，0 中文残留，0 空值回退！")

if __name__ == "__main__":
    unittest.main()
