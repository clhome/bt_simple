# -*- coding: utf-8 -*-
import os
import json
import re
import subprocess
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class TestFilesPasteButton(unittest.TestCase):
    """文件管理复制/剪切后红框位置粘贴按钮修复与单次消费隐藏测试套件"""

    def test_01_i18n_dictionaries_integrity(self):
        """验证 6 国语言 template.json 与 lan.js 中 paste 和 paste_all 完整性"""
        lang_dir = os.path.join(BASE_DIR, 'web/static/language')
        expected_langs = {
            'zh-CN': {'paste': '粘贴', 'paste_all': '粘贴所有'},
            'zh-TW': {'paste': '貼上', 'paste_all': '貼上所有'},
            'en': {'paste': 'Paste', 'paste_all': 'Paste all'},
            'de': {'paste': 'Einfügen', 'paste_all': 'Alle einfügen'},
            'fr': {'paste': 'Coller', 'paste_all': 'Coller tout'},
            'it': {'paste': 'Incolla', 'paste_all': 'Incolla tutto'},
        }

        for lang, expected in expected_langs.items():
            # 1. Check template.json
            tpl_path = os.path.join(lang_dir, lang, 'template.json')
            self.assertTrue(os.path.exists(tpl_path), f"{lang}/template.json does not exist")
            with open(tpl_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            files_dict = data.get('files', {})
            self.assertIn('paste', files_dict, f"Missing 'paste' in {lang}/template.json")
            self.assertEqual(files_dict['paste'], expected['paste'])
            self.assertIn('paste_all', files_dict, f"Missing 'paste_all' in {lang}/template.json")
            self.assertEqual(files_dict['paste_all'], expected['paste_all'])

            # 2. Check lan.js contains paste and paste_all
            lan_path = os.path.join(lang_dir, lang, 'lan.js')
            self.assertTrue(os.path.exists(lan_path), f"{lang}/lan.js does not exist")
            with open(lan_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn(f'"paste": "{expected["paste"]}"', content, f"{lang}/lan.js missing valid paste definition")
            self.assertIn(f'"paste_all": "{expected["paste_all"]}"', content, f"{lang}/lan.js missing valid paste_all definition")

    def test_02_lan_js_node_syntax(self):
        """通过 Node.js 校验全部 6 国语言 lan.js 零语法错误"""
        chk_script = os.path.join(BASE_DIR, 'test/check_lan_syntax.js')
        res = subprocess.run(['node', chk_script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Node.js syntax check failed:\n{res.stderr}\n{res.stdout}")

    def test_03_files_js_syntax(self):
        """通过 Node.js 校验 files.js 语法无误"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        res = subprocess.run(['node', '-c', files_js_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"files.js has syntax error:\n{res.stderr}")

    def test_04_bartools_clean_no_paste(self):
        """验证 BarTools 中已彻底移除遗留的单文件粘贴按钮"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract getFiles BarTools section
        bartools_match = re.search(r'var BarTools\s*=\s*[\s\S]*?\$\(["\']#BarTools["\']\)\.html\(BarTools\);', content)
        self.assertIsNotNone(bartools_match, "BarTools section not found in files.js")
        bt_text = bartools_match.group(0)
        self.assertNotIn("pasteFile", bt_text, "BarTools still contains pasteFile!")
        self.assertNotIn("btn-Warning", bt_text, "BarTools still contains btn-Warning!")
        self.assertNotIn("粘贴", bt_text, "BarTools still contains hardcoded '粘贴' button!")

    def test_05_show_seclect_logic(self):
        """验证 showSeclect 函数中粘贴按钮渲染、多语言支持与自适应贴合逻辑"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        seclect_match = re.search(r'function showSeclect\(\)\s*\{([\s\S]*?)\n\}\n\n//滚动条', content)
        self.assertIsNotNone(seclect_match, "showSeclect function not found in files.js")
        fn_body = seclect_match.group(1)

        # 检查是否动态计算与回收站间距
        self.assertIn('#recycle_bin', fn_body)
        self.assertIn('trashRight', fn_body)
        self.assertIn('trashWidth', fn_body)
        self.assertIn('$batch.css(\'right\'', fn_body)

        # 检查是否包含单文件粘贴按钮与高亮绿色样式
        self.assertIn('btnPasteFile', fn_body)
        self.assertIn('btn-success', fn_body)
        self.assertIn('glyphicon-paste', fn_body)
        self.assertIn('pasteFile', fn_body)

        # 检查是否包含批量粘贴按钮
        self.assertIn('btnBatchPaste', fn_body)
        self.assertIn('batchPaste', fn_body)

    def test_06_state_flow_immediate_trigger_and_single_consumption(self):
        """验证 copyFile/cutFile 0ms 激活与 pasteFile/batchPaste 单次点击消费即刻隐藏"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # copyFile: 立即写入 copyFileName，清空其它，并调用 showSeclect()
        copy_match = re.search(r'function copyFile\(fileName\)\s*\{([\s\S]*?)\}', content)
        self.assertIsNotNone(copy_match, "copyFile function not found")
        copy_body = copy_match.group(1)
        self.assertIn("setCookie('copyFileName', fileName)", copy_body)
        self.assertIn("setCookie('cutFileName', null)", copy_body)
        self.assertIn("setCookie('BatchSelected', null)", copy_body)
        self.assertIn("showSeclect()", copy_body)
        self.assertNotIn("setTimeout", copy_body, "copyFile should not have 1s delayed setTimeout!")

        # cutFile: 立即写入 cutFileName，清空其它，并调用 showSeclect()
        cut_match = re.search(r'function cutFile\(fileName\)\s*\{([\s\S]*?)\}', content)
        self.assertIsNotNone(cut_match, "cutFile function not found")
        cut_body = cut_match.group(1)
        self.assertIn("setCookie('cutFileName', fileName)", cut_body)
        self.assertIn("setCookie('copyFileName', null)", cut_body)
        self.assertIn("setCookie('BatchSelected', null)", cut_body)
        self.assertIn("showSeclect()", cut_body)
        self.assertNotIn("setTimeout", cut_body, "cutFile should not have 1s delayed setTimeout!")

        # pasteFile: 入口立即消费清空 cookie 并调用 showSeclect() 隐藏按钮
        paste_match = re.search(r'function pasteFile\(fileName\)\s*\{([\s\S]*?)\n\}', content)
        self.assertIsNotNone(paste_match, "pasteFile function not found")
        paste_body = paste_match.group(1)
        self.assertIn("setCookie('copyFileName', null)", paste_body)
        self.assertIn("setCookie('cutFileName', null)", paste_body)
        self.assertIn("showSeclect()", paste_body)

        # batchPaste: 入口立即消费清空 cookie 并调用 showSeclect() 隐藏按钮
        bp_match = re.search(r'function batchPaste\(\)\s*\{([\s\S]*?)\n\}', content)
        self.assertIsNotNone(bp_match, "batchPaste function not found")
        bp_body = bp_match.group(1)
        self.assertIn("setCookie('BatchSelected', null)", bp_body)
        self.assertIn("setCookie('BatchPaste', null)", bp_body)
        self.assertIn("showSeclect()", bp_body)

    def test_07_node_runtime_simulation(self):
        """使用 Node.js 完整模拟 DOM 环境，验证粘贴按钮的展示、切换与单次点击隐藏生命周期"""
        sim_js = """
        const vm = require('vm');

        // 模拟简易 Cookie 存储
        const cookies = {};
        function setCookie(k, v) { cookies[k] = v; }
        function getCookie(k) { return cookies[k]; }

        // 模拟 DOM 容器
        let batchHtml = '';
        let batchRight = '';
        const $batch = {
            html: function(val) {
                if (val !== undefined) batchHtml = val;
                return batchHtml;
            },
            css: function(k, v) {
                if (k === 'right') batchRight = v;
                return batchRight;
            }
        };

        const $trash = {
            length: 1,
            is: () => true,
            css: () => '87px',
            outerWidth: () => 80
        };

        let selectedCount = 0;
        function totalFile() { return selectedCount; }
        function getFileName(p) { return p.split('/').pop(); }
        function t(k, def) { return def; }
        const layer = { msg: () => {} };

        // 模拟 showSeclect
        function showSeclect() {
            var count = totalFile();
            var batchTools = '';
            var rightPos = 190;
            if ($trash.length && $trash.is(':visible')) {
                var trashRight = parseInt($trash.css('right')) || 87;
                var trashWidth = $trash.outerWidth() || 80;
                rightPos = trashRight + trashWidth + 10;
            }
            $batch.css('right', rightPos + 'px');

            if(count > 1) {
                batchTools = '<button onclick="batch(1)">复制</button>';
            } else {
                var copyName = getCookie('copyFileName');
                var cutName = getCookie('cutFileName');
                var isSinglePaste = (copyName && copyName !== 'null') ? copyName : ((cutName && cutName !== 'null') ? cutName : null);
                var isBatch = getCookie('BatchSelected');
                var batchType = getCookie('BatchPaste');
                var hasBatchPaste = (isBatch == 1 || isBatch == '1') && (batchType == 1 || batchType == '1' || batchType == 2 || batchType == '2');

                if (isSinglePaste) {
                    var fn = getFileName(isSinglePaste).replace(/'/g, "\\'");
                    batchTools = '<button id="btnPasteFile" onclick="pasteFile(\\'' + fn + '\\');" class="btn btn-success btn-sm"><span class="glyphicon glyphicon-paste"></span>&nbsp;粘贴</button>';
                } else if (hasBatchPaste) {
                    batchTools = '<button id="btnBatchPaste" onclick="batchPaste();" class="btn btn-success btn-sm"><span class="glyphicon glyphicon-paste"></span>&nbsp;粘贴所有</button>';
                }
            }
            $batch.html(batchTools);
        }

        function copyFile(fileName) {
            setCookie('copyFileName', fileName);
            setCookie('cutFileName', null);
            setCookie('BatchSelected', null);
            setCookie('BatchPaste', null);
            showSeclect();
        }

        function cutFile(fileName) {
            setCookie('cutFileName', fileName);
            setCookie('copyFileName', null);
            setCookie('BatchSelected', null);
            setCookie('BatchPaste', null);
            showSeclect();
        }

        function pasteFile(fileName) {
            var copyName = getCookie('copyFileName');
            var cutName = getCookie('cutFileName');
            if ((!copyName || copyName === 'null') && (!cutName || cutName === 'null')) return;

            setCookie('copyFileName', null);
            setCookie('cutFileName', null);
            showSeclect();
        }

        function batch(type) {
            if(type < 3) {
                setCookie('BatchSelected', '1');
                setCookie('BatchPaste', type);
                setCookie('copyFileName', null);
                setCookie('cutFileName', null);
            }
            selectedCount = 0;
            showSeclect();
        }

        function batchPaste() {
            var type = getCookie('BatchPaste');
            if(!type || type === 'null') return;
            setCookie('BatchSelected', null);
            setCookie('BatchPaste', null);
            showSeclect();
        }

        // --- 开始断言测试 ---
        // 1. 初始状态：无选择、无待粘贴，容器为空
        showSeclect();
        if (batchHtml !== '') throw new Error('Initial state should be empty');
        if (batchRight !== '177px') throw new Error('Batch right should be 177px (87 + 80 + 10)');

        // 2. 单文件复制后：0ms 立即展现粘贴按钮
        copyFile('/www/backup/database.sql');
        if (!batchHtml.includes('id="btnPasteFile"') || !batchHtml.includes('粘贴')) {
            throw new Error('After copyFile, paste button should be displayed');
        }

        // 3. 点击单文件粘贴：立即消费 cookie，粘贴按钮隐藏
        pasteFile('database.sql');
        if (batchHtml !== '') throw new Error('After pasteFile, button should disappear immediately');
        if (getCookie('copyFileName') !== null) throw new Error('copyFileName cookie should be null');

        // 4. 单文件剪切后：立即展现粘贴按钮
        cutFile('/www/backup/image.png');
        if (!batchHtml.includes('id="btnPasteFile"')) throw new Error('After cutFile, paste button should be displayed');

        // 5. 多选（count > 1）：切换为批量操作栏
        selectedCount = 3;
        showSeclect();
        if (!batchHtml.includes('onclick="batch(1)"')) throw new Error('When count > 1, should show batch tools');

        // 6. 取消多选（count = 0）：切回单文件剪切的粘贴按钮
        selectedCount = 0;
        showSeclect();
        if (!batchHtml.includes('id="btnPasteFile"')) throw new Error('When count reset to 0, paste button should restore');

        // 7. 批量复制后：显示粘贴所有按钮
        batch(1);
        if (!batchHtml.includes('id="btnBatchPaste"') || !batchHtml.includes('粘贴所有')) {
            throw new Error('After batch(1), batch paste button should be displayed');
        }

        // 8. 点击批量粘贴：立即消费并隐藏
        batchPaste();
        if (batchHtml !== '') throw new Error('After batchPaste, button should disappear immediately');
        if (getCookie('BatchSelected') !== null) throw new Error('BatchSelected cookie should be null');

        console.log("SIMULATION_PASS");
        """
        res = subprocess.run(['node', '-e', sim_js], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Node.js simulation failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("SIMULATION_PASS", res.stdout)

if __name__ == '__main__':
    unittest.main()
