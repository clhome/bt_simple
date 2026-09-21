# -*- coding: utf-8 -*-
"""
专项测试套件：验证弹窗关闭按钮(X)样式与拦截修复，以及文件列表操作列多语言简写与防折行
"""

import os
import re
import json
import subprocess
import sys
import unittest

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(ROOT_DIR, "web")


class TestModalCloseBtnAndFilesOps(unittest.TestCase):

    def test_01_css_modal_close_btn_rules(self):
        """测试 site.css 与 ensite.css 中弹窗关闭按钮 closeBtn:2 的现代重构"""
        for css_rel in ["web/static/css/site.css", "web/static/css/ensite.css"]:
            css_path = os.path.join(ROOT_DIR, css_rel)
            self.assertTrue(os.path.exists(css_path), f"{css_rel} 不存在")
            with open(css_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证重置了 .layui-layer-setwin .layui-layer-close2
            self.assertIn(".layui-layer-setwin .layui-layer-close2", content, f"{css_rel} 缺少 close2 覆写规则")
            self.assertIn("position: relative !important", content, f"{css_rel} close2 应为 relative 相对定位")
            self.assertIn("display: inline-block !important", content, f"{css_rel} close2 应为行内块")

            # 验证 .layui-layer-setwin 的位置内嵌
            self.assertIn(".layui-layer-setwin", content)

    def test_02_css_files_editmenu_nowrap(self):
        """测试 site.css 与 ensite.css 中 .editmenu 及 span 的 nowrap 防折行与 300px 移除"""
        for css_rel in ["web/static/css/site.css", "web/static/css/ensite.css"]:
            css_path = os.path.join(ROOT_DIR, css_rel)
            with open(css_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证 .editmenu 具有 nowrap
            m_menu = re.search(r'\.editmenu\s*\{([^}]+)\}', content)
            self.assertIsNotNone(m_menu, f"{css_rel} 缺少 .editmenu 规则")
            self.assertIn("white-space: nowrap !important", m_menu.group(1))

            # 验证 .editmenu span 不再硬编码 width: 300px 限制
            m_span = re.search(r'\.editmenu span\s*\{([^}]+)\}', content)
            self.assertIsNotNone(m_span, f"{css_rel} 缺少 .editmenu span 规则")
            self.assertNotIn("width: 300px", m_span.group(1), f"{css_rel} 不应存在硬编码 width: 300px")
            self.assertIn("white-space: nowrap !important", m_span.group(1))

    def test_03_js_public_layer_intercept_close_btn(self):
        """测试 public.js 中全局 Layer 弹窗拦截自动将 closeBtn: 2 归一化为 1"""
        pub_path = os.path.join(WEB_DIR, "static", "app", "public.js")
        self.assertTrue(os.path.exists(pub_path))
        with open(pub_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 confirm, alert, prompt, open 中均有 closeBtn === 2 归一化
        matches = re.findall(r'if\s*\(\s*options\.closeBtn\s*===\s*2\s*\)\s*\{\s*options\.closeBtn\s*=\s*1;\s*\}', content)
        self.assertGreaterEqual(len(matches), 3, "public.js 中全局 Layer 拦截未全面覆盖 closeBtn 归一化")

    def test_04_js_files_table_layout_and_close_btn(self):
        """测试 files.js 中删除弹窗 closeBtn 为 1，且表格列宽合理分配、操作列右对齐"""
        files_js = os.path.join(WEB_DIR, "static", "app", "files.js")
        self.assertTrue(os.path.exists(files_js))
        with open(files_js, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证 deleteFile, deleteDir, allDeleteFileSub, closeRecycleBin 的 closeBtn 为 1
        self.assertIn("function deleteDir(dirName){\n    var confirmMsg = t('files.recycle_bin_confirm_dir'", content)
        self.assertIn("layer.confirm(confirmMsg, {title: titleText, closeBtn: 1, icon: 3}", content)

        # 验证 thead 列宽科学分配
        self.assertIn("width=\"90\">' + fileSizeLabel", content)
        self.assertIn("width=\"70\">' + filePermLabel", content)
        self.assertIn("width=\"80\">' + fileOwnLabel", content)
        self.assertIn("width=\"380\">' + fileActionLabel", content)

        # 验证 td.editmenu 右对齐
        self.assertIn("<td class='editmenu' style='text-align: right; padding-right: 15px;'>", content)

    def test_05_i18n_concise_operations_keys(self):
        """测试 6 国语言包中操作列词条为标准精炼简写且总长度大幅缩减"""
        keys = ['copy_path', 'copy', 'cut', 'rename', 'permissions', 'compress', 'unzip', 'edit', 'preview', 'download', 'delete']
        langs = ['zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it']

        for l in langs:
            lan_path = os.path.join(WEB_DIR, "static", "language", l, "lan.js")
            self.assertTrue(os.path.exists(lan_path), f"{l}/lan.js 不存在")
            with open(lan_path, "r", encoding="utf-8") as f:
                content = f.read()

            m = re.search(r'["\']?files["\']?\s*:\s*\{(.*?)\n\t*\},', content, re.DOTALL)
            self.assertIsNotNone(m, f"{l}/lan.js 缺少 files 命名空间")
            files_block = m.group(1)

            vals = {}
            for k in keys:
                km = re.search(rf'["\']{k}["\']\s*:\s*["\'](.*?)["\']', files_block)
                self.assertIsNotNone(km, f"{l}/lan.js files 命名空间缺少 key: {k}")
                vals[k] = km.group(1)

            # 验证英文精炼度
            if l == 'en':
                self.assertEqual(vals['copy_path'], 'Path')
                self.assertEqual(vals['permissions'], 'Perms')
                self.assertEqual(vals['compress'], 'Zip')
                self.assertEqual(vals['preview'], 'View')
                self.assertEqual(vals['download'], 'Down')
                self.assertEqual(vals['delete'], 'Del')
                # 检查目录操作总长度
                dir_ops = f"{vals['copy_path']} | {vals['copy']} | {vals['cut']} | {vals['rename']} | {vals['permissions']} | {vals['compress']} | {vals['delete']}"
                self.assertLessEqual(len(dir_ops), 50, f"英文目录操作字符串过长: {len(dir_ops)} 字符 (原版为 66 字符)")

            # 验证德文精炼度
            if l == 'de':
                self.assertEqual(vals['copy_path'], 'Pfad')
                self.assertEqual(vals['permissions'], 'Rechte')
                self.assertEqual(vals['compress'], 'Zip')
                self.assertEqual(vals['cut'], 'Cut')
                dir_ops = f"{vals['copy_path']} | {vals['copy']} | {vals['cut']} | {vals['rename']} | {vals['permissions']} | {vals['compress']} | {vals['delete']}"
                self.assertLessEqual(len(dir_ops), 55, f"德文目录操作字符串过长: {len(dir_ops)} 字符")

            # 验证法文精炼度
            if l == 'fr':
                self.assertEqual(vals['copy_path'], 'Chemin')
                self.assertEqual(vals['permissions'], 'Perms')
                self.assertEqual(vals['compress'], 'Zip')
                self.assertEqual(vals['delete'], 'Suppr.')

            # 验证意文精炼度
            if l == 'it':
                self.assertEqual(vals['copy_path'], 'Percorso')
                self.assertEqual(vals['compress'], 'Zip')
                self.assertEqual(vals['delete'], 'Del')

    def test_06_nodejs_syntax_check(self):
        """测试 6 国语言 lan.js 的真实 Node.js 语法校验"""
        node_script = os.path.join(ROOT_DIR, "test", "check_lan_syntax.js")
        result = subprocess.run(["node", node_script], capture_output=True, text=True, cwd=ROOT_DIR)
        self.assertEqual(result.returncode, 0, f"Node.js 语法检测失败:\n{result.stderr}\n{result.stdout}")


if __name__ == '__main__':
    unittest.main()
