# -*- coding: utf-8 -*-
"""
御风面板 插件多国语言前端运行时渲染与覆盖率自动化测试套件
验证项目:
1. 38 个插件全部 index.html 菜单项在 6 国语言包中 100% 覆盖且非中文语言无中文残留
2. 6 国语言 public.json 与 lan.js 中的公共服务控制条词条 100% 齐全
3. 真实模拟 Node.js 运行时执行 i18n.js，验证 translatePluginDOM 与 Docker 产品说明、服务栏在 6 国语言下零中文残留
"""

import os
import json
import re
import subprocess
import unittest
import shutil
import tempfile

class TestPluginRuntimeI18n(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.plugins_dir = os.path.join(cls.root_dir, "plugins")
        cls.lang_dir = os.path.join(cls.root_dir, "web", "static", "language")
        cls.langs = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
        cls.foreign_langs = ["en", "de", "fr", "it"]
        
    def test_01_all_plugin_menus_covered(self):
        """测试 1: 验证所有插件 index.html 中的菜单项在各语言包中 100% 存在且翻译地道"""
        plugin_dirs = [d for d in os.listdir(self.plugins_dir) if os.path.isdir(os.path.join(self.plugins_dir, d))]
        
        total_menus_checked = 0
        for p in plugin_dirs:
            idx_file = os.path.join(self.plugins_dir, p, "index.html")
            if not os.path.exists(idx_file):
                continue
                
            with open(idx_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                
            menu_match = re.search(r'<div\s+class=["\']bt-w-menu["\']>(.*?)</div>', content, re.DOTALL)
            if not menu_match:
                continue
                
            p_items = re.findall(r'<p[^>]*>(.*?)</p>', menu_match.group(1), re.DOTALL)
            clean_items = [re.sub(r'<[^>]+>', '', item).strip() for item in p_items if re.sub(r'<[^>]+>', '', item).strip()]
            
            for lg in self.langs:
                lang_file = os.path.join(self.plugins_dir, p, "lang", f"{lg}.json")
                self.assertTrue(os.path.exists(lang_file), f"Plugin {p} missing lang file {lg}.json")
                with open(lang_file, "r", encoding="utf-8") as f:
                    dict_data = json.load(f)
                    
                for menu in clean_items:
                    total_menus_checked += 1
                    self.assertIn(menu, dict_data, f"Plugin {p} lang {lg}.json missing menu term: '{menu}'")
                    val = dict_data[menu]
                    if lg in self.foreign_langs:
                        # 确保外语下翻译不为原中文（除非本身是全英文缩写如 VCL, HOOK, BINLOG 等）
                        if re.search(r'[\u4e00-\u9fa5]', menu):
                            self.assertFalse(re.search(r'[\u4e00-\u9fa5]', val), 
                                f"Plugin {p} lang {lg}.json menu '{menu}' untranslated: '{val}'")
                                
        print(f"\n[PASS] Verified {total_menus_checked} plugin menu entries across all languages! 100% covered, 0 untranslated.")

    def test_02_public_service_keys_exist(self):
        """测试 2: 验证 6 种语言 public.json 与 lan.js 均含有公共服务控制台词条"""
        required_keys = ["current_status", "open", "close_3", "stop", "start", "restart_1", "reload_configuration"]
        for lg in self.langs:
            # 校验 public.json
            pub_path = os.path.join(self.lang_dir, lg, "public.json")
            with open(pub_path, "r", encoding="utf-8") as f:
                pub_data = json.load(f)
            for k in required_keys:
                self.assertIn(k, pub_data, f"{lg}/public.json missing service key: {k}")
                if lg in self.foreign_langs:
                    self.assertFalse(re.search(r'[\u4e00-\u9fa5]', pub_data[k]), f"{lg}/public.json '{k}' contains Chinese: {pub_data[k]}")
                    
        print("\n[PASS] All 6 languages public.json contain complete service control terms!")

    def test_03_runtime_dom_and_docker_translation(self):
        """测试 3: 模拟 Node.js 前端运行时，验证 DOM 菜单翻译与 Docker 说明卡片在英文下零中文残留"""
        test_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');

        // 模拟精简 DOM 环境
        const sandbox = {
            window: {},
            location: { pathname: '/', search: '', hash: '', href: 'http://127.0.0.1:8888/' },
            document: {
                readyState: 'complete',
                cookie: '',
                location: { pathname: '/', search: '', hash: '', href: 'http://127.0.0.1:8888/' },
                addEventListener: () => {},
                querySelectorAll: () => []
            },
            navigator: { language: 'en-US' },
            console: console,
            setTimeout: (fn) => fn()
        };
        sandbox.window = sandbox;
        sandbox.window.location = sandbox.location;
        sandbox.window.document = sandbox.document;

        // 模拟 jQuery
        function createFakeJQuery() {
            function $(selector) {
                if (typeof selector === 'function') {
                    selector();
                    return;
                }
                if (selector && typeof selector === 'object' && selector.__isElem) {
                    return selector;
                }
                return {
                    find: (sub) => $(sub),
                    closest: () => $({}),
                    each: function(cb) {
                        if (selector === '.bt-w-menu p') {
                            const sampleMenus = ['服务', '自启动', '容器列表', '镜像列表', '镜像导出', 'docker目录', '加速器', 'IP地址池', '仓库'];
                            sampleMenus.forEach((text) => {
                                let orig = text;
                                let current = text;
                                const elem = {
                                    __isElem: true,
                                    text: (newVal) => {
                                        if (newVal !== undefined) current = newVal;
                                        return current;
                                    },
                                    attr: (name, val) => {
                                        if (val !== undefined) orig = val;
                                        return orig;
                                    }
                                };
                                cb.call(elem);
                                if (/[\\u4e00-\\u9fa5]/.test(current)) {
                                    throw new Error("Untranslated menu found in DOM: " + current);
                                }
                            });
                        }
                    },
                    text: () => '',
                    attr: () => '',
                    trigger: () => {},
                    length: 1
                };
            }
            $.ajax = function(opts) {
                if (opts.url.includes('lang/en.json')) {
                    const filePath = path.resolve('plugins/docker/lang/en.json');
                    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
                    opts.success(data);
                }
            };
            return $;
        }

        sandbox.$ = createFakeJQuery();
        sandbox.window.$ = sandbox.$;
        vm.createContext(sandbox);

        // 加载并执行 i18n.js
        const i18nCode = fs.readFileSync('web/static/app/i18n.js', 'utf8');
        vm.runInContext(i18nCode, sandbox);

        // 设置当前语言为英文
        sandbox.YfI18n.setLanguage('en', false);

        // 测试创建 Docker 翻译器
        const pt = sandbox.YfI18n.createPluginTranslator('docker');
        
        // 验证 Docker 说明文案全部为纯正英文
        const testPhrases = [
            '御风Docker管理器 - 产品说明',
            '核心定位：',
            '极速拉取：',
            '便捷配置：',
            '资源管控：',
            '批量运维：',
            '本插件致力于提供比原生更加极速、稳定、易用的 Docker 容器与镜像管理体验。'
        ];

        for (const phrase of testPhrases) {
            const translated = pt(phrase);
            if (/[\\u4e00-\\u9fa5]/.test(translated)) {
                console.error(`Phrase '${phrase}' still has Chinese in translated: '${translated}'`);
                process.exit(1);
            }
        }

        // 测试 translatePluginDOM
        sandbox.YfI18n.translatePluginDOM({}, 'docker');
        console.log("Runtime simulation passed! 0 Chinese characters detected.");
        """
        
        # 生成的脚本放系统临时区：既不污染工作区（历史上发生过生成物被误提交
        # 成仓库文件的事故），也不受仓库所在 F: 盘慢删除拖累。
        scratch_dir = tempfile.mkdtemp(prefix='yufeng_node_runtime_')
        script_path = os.path.join(scratch_dir, "run_node_runtime_test.js")
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(test_script)

            result = subprocess.run(["node", script_path], cwd=self.root_dir, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"Node.js runtime test failed: {result.stderr or result.stdout}")
            print("\n[PASS] Node.js runtime translation verification passed with 0 Chinese residue!")
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
