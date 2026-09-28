#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：弹窗（layer）卡顿治理 — 回归锁

背景（用户反馈）：
    「项目的所有弹窗都要卡顿」，两类独立成因叠加：
    A. 主线程长任务 —— 插件弹窗 opening 时同步做全量子树 i18n 扫描（且被调用两次），
       并在弹窗存续期间被 MutationObserver 反复全量重扫；缓存未命中时还有 async:false
       的同步 XHR 兜底，会直接冻结整个渲染主线程。
    B. 动画/合成层 —— layer 默认 bounceIn 缩放动画叠加弹窗的大阴影与圆角裁剪，
       每帧都要重新光栅化；再加上全站 `* { transition: ... transform, box-shadow }`
       与 5 处 backdrop-filter 模糊。

验证点：
1. web/static/app/i18n.js
   - 已移除 async:false 的同步 XHR 兜底（不再冻结主线程）
   - 新增在途请求合并（_pluginDictPending）与字典就绪重扫钩子（onPluginDictReady）
   - translatePluginDOM 具备「同容器只全量扫一次」的幂等闸门（yf-i18n-scanned）
   - MutationObserver 改为只扫新增子树（pendingRoots + pushPendingRoot），
     不再出现 observer 回调里对 $con 的全量 doTranslateNodes
   - 白名单文本提取仅在确有图标子节点时才 clone
2. web/static/css/site.css
   - 不再存在 `* { transition: ... }` 通配过渡（尤其不得再过渡 transform）
   - 不再存在真实的 backdrop-filter 声明（注释除外）
   - 新增 yfLayerIn / yfLayerOut，并覆写 .layui-layer 的各 layer-anim 类
   - 弹窗阴影已收窄（不再使用 0 12px 36px）
   - 提供 prefers-reduced-motion 降级
3. web/static/css/ensite.css
   - 与 site.css 保持一致（双语版行为统一）
4. Node.js V8 语法校验 + UTF-8 无 BOM + LF 换行
"""

import os
import re
import subprocess
import sys
import unittest

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N_JS = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'i18n.js')
SITE_CSS = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')
ENSITE_CSS = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css')

# 除注释外不得再出现的 css 片段
CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)


def read_text_nobom_lf(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    assert not content.startswith(b'\xef\xbb\xbf'), f"BOM detected in {file_path}"
    assert b'\r\n' not in content, f"CRLF detected in {file_path}, must use LF"
    return content.decode('utf-8')


def strip_css_comments(text):
    return CSS_COMMENT_RE.sub('', text)


class TestModalPerfOpt(unittest.TestCase):

    def setUp(self):
        self.js = read_text_nobom_lf(I18N_JS)
        self.site_css = read_text_nobom_lf(SITE_CSS)
        self.ensite_css = read_text_nobom_lf(ENSITE_CSS)
        self.site_css_body = strip_css_comments(self.site_css)
        self.ensite_css_body = strip_css_comments(self.ensite_css)

    # ------------------------------------------------------------------ JS

    def test_01_no_sync_xhr(self):
        """i18n.js 不得再出现 async:false 的同步 XHR（会冻结整个渲染主线程）"""
        self.assertNotIn('async: false', self.js,
                         "i18n.js 重新引入了 async:false 同步 XHR，弹窗打开会被网络阻塞")

    def test_02_plugin_dict_async_plumbing(self):
        """字典异步补齐链路必须完整：在途合并 + 就绪重扫钩子"""
        for token in ('_pluginDictPending', 'onPluginDictReady', 'firePluginDictReady'):
            self.assertIn(token, self.js, f"i18n.js 缺失 {token}（异步字典补齐链路被破坏）")
        # 创建翻译器时不得再走同步兜底，必须交给异步通道
        self.assertIn('loadPluginLangAsync(pluginName);', self.js,
                      "createPluginTranslator 未改为异步补齐字典")

    def test_03_container_idempotent_scan(self):
        """同一容器只允许做一次全量扫描（消除 success 双调用造成的重复扫描）"""
        self.assertIn("__yfI18nScanned", self.js,
                      "i18n.js 缺失 __yfI18nScanned 幂等闸门，弹窗会被同步扫两遍")

    def test_04_incremental_mutation_scan(self):
        """MutationObserver 必须只扫新增子树，禁止再全量重扫整个弹窗"""
        self.assertIn('pendingRoots', self.js, "i18n.js 缺失增量扫描队列 pendingRoots")
        self.assertIn('pushPendingRoot', self.js, "i18n.js 缺失 pushPendingRoot 去重/吞并逻辑")
        self.assertIn('doTranslateNodes(window.$(roots[k]))', self.js,
                      "MutationObserver 未改为按新增子树增量翻译")
        # 取 observer 回调体，确认其中不再出现对 $con 的全量扫描
        obs = self.js[self.js.index('new MutationObserver(function (mutations)'):]
        obs_body = obs[:obs.index('observer.observe($con[0]')]
        self.assertNotIn('doTranslateNodes($con)', obs_body,
                         "MutationObserver 回调里仍在全量重扫 $con，弹窗开着就会持续发顿")

    def test_05_clone_only_when_needed(self):
        """白名单文本提取：仅在确有图标子节点时才 clone"""
        self.assertIn('hasIconChild', self.js,
                      "i18n.js 未做 clone 短路优化，表格类弹窗会 clone 成百上千个节点")

    def test_06_js_syntax(self):
        """Node.js V8 引擎校验 i18n.js 语法"""
        res = subprocess.run(f'node -c "{I18N_JS}"', shell=True,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"i18n.js 语法校验失败:\n{res.stderr}")

    # ----------------------------------------------------------------- CSS

    def _assert_layer_anim_css(self, css_body, css_raw, label):
        self.assertIn('@keyframes yfLayerIn', css_body, f"{label} 缺失 yfLayerIn 进场动画")
        self.assertIn('@keyframes yfLayerOut', css_body, f"{label} 缺失 yfLayerOut 关闭动画")
        self.assertIn('.layui-layer[class*="layer-anim"]', css_body,
                      f"{label} 未覆写 layer 的各 layer-anim 进场动画")
        self.assertIn('.layui-layer[class*="layer-anim-close"]', css_body,
                      f"{label} 未覆写 layer-anim-close 关闭动画")
        self.assertIn('prefers-reduced-motion', css_body,
                      f"{label} 缺失 prefers-reduced-motion 降级")

    def test_07_no_universal_transition(self):
        """site.css 不得再存在通配过渡（会给每个节点注册过渡并插值 transform）"""
        self.assertIsNone(re.search(r'(^|\n)\s*\*\s*\{', self.site_css_body),
                          "site.css 重新引入了 `* { ... }` 通配规则")
        # 替代方案：收窄到交互控件，且不外扩 box-shadow/transform
        self.assertIn('.layui-layer-title {', self.site_css_body,
                      "site.css 缺失交互控件过渡白名单")

    def test_08_no_backdrop_filter(self):
        """纯色底上的 backdrop-filter 必须清除（弹窗期间会反复重算大面积模糊）"""
        for label, body in (('site.css', self.site_css_body),
                            ('ensite.css', self.ensite_css_body)):
            self.assertNotIn('backdrop-filter', body,
                             f"{label} 仍有真实 backdrop-filter 声明")

    def test_09_layer_shadow_tightened(self):
        """弹窗弥散阴影必须收窄，降低单帧光栅化成本"""
        for label, body in (('site.css', self.site_css_body),
                            ('ensite.css', self.ensite_css_body)):
            self.assertNotIn('0 12px 36px', body,
                             f"{label} 弹窗阴影仍是 36px 大弥散")

    def test_10_keep_legacy_layer_msg_rule(self):
        """历史修复不得被本次性能改造误删（layer.msg 滚动条/箭头异常）"""
        for label, body in (('site.css', self.site_css_body),
                            ('ensite.css', self.ensite_css_body)):
            self.assertIn('.layui-layer-msg .layui-layer-content', body,
                          f"{label} 丢失 .layui-layer-msg .layui-layer-content 规则")
            self.assertIn('overflow: hidden !important', body,
                          f"{label} 丢失 overflow: hidden !important 兜底")

    def test_11_site_and_ensite_consistent(self):
        """双语版 CSS 的弹窗动画覆写必须一致"""
        self._assert_layer_anim_css(self.site_css_body, self.site_css, 'site.css')
        self._assert_layer_anim_css(self.ensite_css_body, self.ensite_css, 'ensite.css')


if __name__ == '__main__':
    unittest.main()
