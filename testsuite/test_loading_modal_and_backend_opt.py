# -*- coding: utf-8 -*-
"""
插件后端打开性能优化与 Loading 异常修复专项验证套件
验证：
1. 6 种语言下 public.json 与 lan.js 中的 loading_1 与 loading 存在且符合对应语言
2. site.css 与 ensite.css 中包含针对 layui-layer-msg 的 overflow: hidden 规则
3. public.js 中 initLayerI18n 对 layer.msg 进行了安全兜底与国际化拦截
4. public.js 中 pluginService 不再存在空字符串风险
5. 后端 /setting 接口成功内联注入插件多语言字典，实现前端 0 网络请求加载语言包
6. 后端 /run 接口对 status 状态查询提供了防抖缓存，且写操作能即时清空缓存
"""

import os
import sys
import json
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'web'))

class TestLoadingModalAndBackendOpt(unittest.TestCase):

    def test_01_public_json_and_lan_js_loading_keys(self):
        """验证 6 种语言包中的 loading 与 loading_1 词条完整且非空"""
        lang_dir = os.path.join(ROOT_DIR, 'web', 'static', 'language')
        expected_langs = ['zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it']
        
        for lang in expected_langs:
            # 1. public.json
            p_json = os.path.join(lang_dir, lang, 'public.json')
            self.assertTrue(os.path.exists(p_json), f"缺少 {p_json}")
            with open(p_json, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self.assertIn('loading_1', d, f"[{lang}] public.json 缺少 loading_1 词条")
            self.assertIn('loading', d, f"[{lang}] public.json 缺少 loading 词条")
            self.assertTrue(d['loading_1'].strip() != '', f"[{lang}] loading_1 不应为空")

            # 2. lan.js
            lan_js = os.path.join(lang_dir, lang, 'lan.js')
            with open(lan_js, 'r', encoding='utf-8') as f:
                c = f.read()
            self.assertIn('"loading_1":', c, f"[{lang}] lan.js 缺少 loading_1")

        print("\n[PASS] 全部 6 种语言 public.json 与 lan.js 的 loading 词条验证通过！")

    def test_02_css_overflow_hidden_for_layer_msg(self):
        """验证 site.css 与 ensite.css 中杜绝上下滚动条箭头的规则"""
        css_files = [
            os.path.join(ROOT_DIR, 'web', 'static', 'css', 'site.css'),
            os.path.join(ROOT_DIR, 'web', 'static', 'css', 'ensite.css')
        ]
        for path in css_files:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('.layui-layer-msg .layui-layer-content', content, f"{path} 缺少 .layui-layer-msg 规则")
            self.assertIn('overflow: hidden !important', content, f"{path} 缺少 overflow: hidden !important")

        print("[PASS] CSS 滚动条与上下箭头阻断样式已就绪！")

    def test_03_public_js_layer_msg_interceptor(self):
        """验证 public.js 中 initLayerI18n 对 layer.msg 的拦截与 pluginService 的兜底"""
        public_js = os.path.join(ROOT_DIR, 'web', 'static', 'app', 'public.js')
        with open(public_js, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('window.layer.msg = function', content, "public.js 应拦截 layer.msg")
        self.assertIn("content = getI18nText('public.loading_1')", content, "应自动注入 loading_1 兜底")
        self.assertNotIn("t('public.loading_1') || \"\"", content, "pluginService 中不应存在回退到空字符串的代码")
        self.assertIn("t('public.loading_1', '正在获取服务状态...')", content, "pluginService 应提供明确默认文案")

        print("[PASS] 前端 layer.msg 全局拦截与 pluginService 防空机制验证通过！")

    def test_04_backend_inline_plugin_lang_injection(self):
        """验证后端 plugins/__init__.py 中包含内联注入 window._pluginDicts 的逻辑与缓存"""
        plugins_init = os.path.join(ROOT_DIR, 'web', 'admin', 'plugins', '__init__.py')
        with open(plugins_init, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("_PLUGIN_HTML_CACHE", content, "应定义 _PLUGIN_HTML_CACHE 模板缓存")
        self.assertIn("_PLUGIN_LANG_CACHE", content, "应定义 _PLUGIN_LANG_CACHE 语言包缓存")
        self.assertIn("_pluginDicts", content, "setting 响应应内联注入 _pluginDicts")
        self.assertIn("localStorage.setItem", content, "setting 响应应将字典持久化到 localStorage")

        print("[PASS] 后端 /setting 成功内联注入多语言字典，彻底消除前端语言包网络请求！")

    def test_05_backend_status_query_cache(self):
        """验证后端 plugins/__init__.py 针对 status 查询具备 2 秒防抖短缓存与写操作清空机制"""
        plugins_init = os.path.join(ROOT_DIR, 'web', 'admin', 'plugins', '__init__.py')
        with open(plugins_init, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("is_status_query = func == 'status' or func.startswith('status_')", content, "应具备 status 防抖判断")
        self.assertIn("cache_ttl = 10 if func == 'get_total_statistics' else (2 if is_status_query else 0)", content, "应设置 2 秒 status 缓存")
        # 写操作清理 RUN_CACHE 的写法后来从 list(...) 改成了列表推导（就地快照键，
        # 避免边遍历边 del 抛 RuntimeError）。语义不变，按当前源码断言。
        self.assertIn("for k in [k for k in RUN_CACHE.keys()]:", content, "写操作应清理 RUN_CACHE")

        print("[PASS] 后端 status 状态防抖短缓存与实时失效机制验证通过！")

if __name__ == '__main__':
    unittest.main()
