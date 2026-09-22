# -*- coding: utf-8 -*-
"""
验证文件/目录删除确认弹窗多语言适配与内容显示自动化测试套件
覆盖 6 种语言：zh-CN, zh-TW, en, fr, de, it
"""
import os
import sys
import json
import re
import unittest
import subprocess

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LANG_DIR = os.path.join(BASE_DIR, "web", "static", "language")
FILES_JS = os.path.join(BASE_DIR, "web", "static", "app", "files.js")
I18N_JS = os.path.join(BASE_DIR, "web", "static", "app", "i18n.js")
PUBLIC_JS = os.path.join(BASE_DIR, "web", "static", "app", "public.js")

LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
REQUIRED_KEYS = [
    "recycle_bin_confirm",
    "recycle_bin_confirm_dir",
    "delete_file",
    "delete_directory",
    "batch_delete_files",
    "are_you_sure_you",
    "deleting_please_wait"
]

class TestFilesDeleteModalI18n(unittest.TestCase):

    def test_01_files_js_delete_functions_i18n_call(self):
        """测试 files.js 中 deleteFile, deleteDir 与 allDeleteFileSub 不存在硬编码中文标题与无参数兜底"""
        with open(FILES_JS, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. 验证 deleteFile
        m_file = re.search(r'function deleteFile\(fileName\)\s*\{([\s\S]*?)\n\}', content)
        self.assertTrue(m_file, "未找到 deleteFile 函数定义")
        body_file = m_file.group(1)
        self.assertIn("t('files.recycle_bin_confirm'", body_file, "deleteFile 应调用 t('files.recycle_bin_confirm')")
        self.assertIn("t('files.delete_file'", body_file, "deleteFile 应调用 t('files.delete_file')")
        self.assertNotIn("{title:'删除文件'", body_file, "deleteFile 仍包含写死的中文标题")

        # 2. 验证 deleteDir
        m_dir = re.search(r'function deleteDir\(dirName\)\s*\{([\s\S]*?)\n\}', content)
        self.assertTrue(m_dir, "未找到 deleteDir 函数定义")
        body_dir = m_dir.group(1)
        self.assertIn("t('files.recycle_bin_confirm_dir'", body_dir, "deleteDir 应调用 t('files.recycle_bin_confirm_dir')")
        self.assertIn("t('files.delete_directory'", body_dir, "deleteDir 应调用 t('files.delete_directory')")
        self.assertNotIn("{title:'删除目录'", body_dir, "deleteDir 仍包含写死的中文标题")

        # 3. 验证 allDeleteFileSub
        m_batch = re.search(r'function allDeleteFileSub\(data,path\)\s*\{([\s\S]*?)\n\}', content)
        self.assertTrue(m_batch, "未找到 allDeleteFileSub 函数定义")
        body_batch = m_batch.group(1)
        self.assertIn("t('files.are_you_sure_you'", body_batch, "allDeleteFileSub 应调用 t('files.are_you_sure_you')")
        self.assertIn("t('files.batch_delete_files'", body_batch, "allDeleteFileSub 应调用 t('files.batch_delete_files')")
        self.assertNotIn("{title:'批量删除文件'", body_batch, "allDeleteFileSub 仍包含写死的中文标题")

    def test_02_template_json_delete_keys_all_languages(self):
        """测试 6 国语言 template.json 中必须包含全部删除与回收站关键条目且非空"""
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang, "template.json")
            self.assertTrue(os.path.exists(path), f"{lang}/template.json 不存在")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            files = data.get("files", {})
            for key in REQUIRED_KEYS:
                self.assertIn(key, files, f"[{lang}] template.json files 中缺少 {key}")
                val = files[key]
                self.assertTrue(val and str(val).strip(), f"[{lang}] template.json files.{key} 为空")

    def test_03_lan_js_msgs_dict_all_languages(self):
        """测试 6 国语言 lan.js 中 msgs 字典包含 recycle_bin_confirm 条目且非空"""
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang, "lan.js")
            self.assertTrue(os.path.exists(path), f"{lang}/lan.js 不存在")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"recycle_bin_confirm":', content, f"[{lang}] lan.js msgs 中未定义 recycle_bin_confirm")
            self.assertIn('"recycle_bin_confirm_dir":', content, f"[{lang}] lan.js msgs 中未定义 recycle_bin_confirm_dir")

    def test_04_js_syntax_validation(self):
        """使用 Node.js 校验全部涉及的 JS 文件语法"""
        js_files = [FILES_JS, I18N_JS, PUBLIC_JS]
        for lang in LANGS:
            js_files.append(os.path.join(LANG_DIR, lang, "lan.js"))

        for file_path in js_files:
            cmd = ["node", "-c", file_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            self.assertEqual(res.returncode, 0, f"JS 语法解析错误: {file_path}\n{res.stderr}")

    def test_05_node_runtime_delete_file_modal_simulation(self):
        """在真实的 Node.js 环境下模拟 6 国语言环境，测试 deleteFile 触发的 confirm 标题与内容插值"""
        node_script = r"""
        const fs = require('fs');
        const path = require('path');

        const langs = ['zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it'];
        const results = {};

        for (const lang of langs) {
            const domMock = {
                cookie: 'yf_lang=' + lang,
                location: { search: '' },
                querySelectorAll: () => []
            };

            const windowMock = {
                document: domMock,
                navigator: { languages: [lang], language: lang },
                location: domMock.location,
                _SERVER_LANG: lang
            };

            // 1. 加载 lan.js
            const lanCode = fs.readFileSync(path.join('web/static/language', lang, 'lan.js'), 'utf-8');
            const runLan = new Function('window', 'document', lanCode + '; return lan;');
            windowMock.lan = runLan(windowMock, domMock);

            // 2. 加载 i18n.js
            const i18nCode = fs.readFileSync('web/static/app/i18n.js', 'utf-8');
            const runI18n = new Function('window', 'document', i18nCode);
            runI18n(windowMock, domMock);

            // 3. 模拟 layer.confirm
            let captured = {};
            windowMock.layer = {
                confirm: (msg, opts, callback) => {
                    captured = { msg: msg, opts: opts };
                },
                msg: () => {},
                closeAll: () => {}
            };

            const createChainable = () => new Proxy(function() {}, {
                get: (target, prop) => {
                    if (prop === 'length') return 0;
                    if (prop === 'width' || prop === 'height') return () => 1200;
                    if (prop === 'val') return () => '/www/backup';
                    return createChainable;
                },
                apply: (target, thisArg, args) => {
                    if (args.length === 1 && typeof args[0] === 'function') {
                        // 避免在定义阶段自动触发 ready 回调引起副作用
                    }
                    return createChainable();
                }
            });
            const mockDollar = createChainable();
            mockDollar.post = () => {};
            mockDollar.get = () => {};
            mockDollar.ajax = () => {};
            windowMock.$ = mockDollar;

            // 4. 加载 public.js (layer 拦截器)
            const publicCode = fs.readFileSync('web/static/app/public.js', 'utf-8');
            const runPublic = new Function('window', 'document', 't', 'lan', 'layer', '$',
                publicCode + '; if(typeof initLayerI18n === "function") initLayerI18n();');
            runPublic(windowMock, domMock, windowMock.t, windowMock.lan, windowMock.layer, mockDollar);

            // 5. 执行 deleteFile('my_test_file.zip')
            const t = windowMock.t;
            const lan = windowMock.lan;
            const layer = windowMock.layer;
            const $ = mockDollar;

            // 提取 files.js 中的 deleteFile 函数体执行
            const filesCode = fs.readFileSync('web/static/app/files.js', 'utf-8');
            const startIdx = filesCode.indexOf('function deleteFile(fileName){');
            const endIdx = filesCode.indexOf('//删除目录', startIdx);
            const rawBody = filesCode.substring(startIdx + 'function deleteFile(fileName){'.length, endIdx);
            const lastBrace = rawBody.lastIndexOf('}');
            const funcBody = rawBody.substring(0, lastBrace);

            const runDeleteFile = new Function('fileName', 't', 'lan', 'layer', '$', funcBody);
            runDeleteFile('my_test_file.zip', t, lan, layer, $);

            // 测试 lan.get 直接调用
            const lanGetResult = windowMock.lan.get('recycle_bin_confirm', ['standalone.log']);

            results[lang] = {
                capturedTitle: captured.opts ? captured.opts.title : '',
                capturedMsg: captured.msg || '',
                lanGetResult: lanGetResult
            };
        }

        // public.js 顶层注册了 setInterval（系统信息轮询等），node 的事件循环
        // 因此不会自然退出；结果已经算完，显式 flush 后主动退出，
        // 否则 subprocess.run 会一直等待这个永不结束的子进程。
        // 注意：本段外层是 Python 原始字符串（r 前缀），这里必须写单反斜杠加 n，
        // 写双反斜杠会被原样送进 JS，变成「反斜杠 + n」两个字面字符污染 stdout。
        process.stdout.write(JSON.stringify(results) + '\n', () => process.exit(0));
        """

        res = subprocess.run(["node", "-e", node_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", cwd=BASE_DIR, timeout=120)
        self.assertEqual(res.returncode, 0, f"Node 执行失败: {res.stderr}")
        data = json.loads(res.stdout.strip())

        # 验证英文环境
        en_res = data.get("en", {})
        self.assertEqual(en_res.get("capturedTitle"), "Delete File", "英文下弹窗标题应为 Delete File")
        self.assertEqual(en_res.get("capturedMsg"), "Are you sure you want to move file [my_test_file.zip] to the recycle bin?", "英文下弹窗内容应为标准英文提示并包含文件名")
        self.assertIn("standalone.log", en_res.get("lanGetResult", ""), "lan.get 结果必须包含传入的文件名")
        self.assertNotIn("[\u4e00-\u9fff]", en_res.get("capturedMsg"), "英文弹窗内容中不应包含中文字符")

        # 验证简体中文
        zh_res = data.get("zh-CN", {})
        self.assertEqual(zh_res.get("capturedTitle"), "删除文件")
        self.assertEqual(zh_res.get("capturedMsg"), "您确实要把此文件[my_test_file.zip]放入回收站吗?")

        # 验证繁体中文
        tw_res = data.get("zh-TW", {})
        self.assertEqual(tw_res.get("capturedTitle"), "刪除檔案")
        self.assertEqual(tw_res.get("capturedMsg"), "您確實要把此檔案[my_test_file.zip]放入資源回收筒嗎?")

        # 验证德语
        de_res = data.get("de", {})
        self.assertEqual(de_res.get("capturedTitle"), "Datei löschen")
        self.assertEqual(de_res.get("capturedMsg"), "Möchten Sie die Datei [my_test_file.zip] wirklich in den Papierkorb verschieben?")

        # 验证法语
        fr_res = data.get("fr", {})
        self.assertEqual(fr_res.get("capturedTitle"), "Supprimer le fichier")
        self.assertEqual(fr_res.get("capturedMsg"), "Voulez-vous vraiment mettre le fichier [my_test_file.zip] dans la corbeille ?")

        # 验证意大利语
        it_res = data.get("it", {})
        self.assertEqual(it_res.get("capturedTitle"), "Elimina file")
        self.assertEqual(it_res.get("capturedMsg"), "Sei sicuro di voler spostare il file [my_test_file.zip] nel cestino?")


if __name__ == "__main__":
    unittest.main()
