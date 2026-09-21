# -*- coding: utf-8 -*-
"""
文件页面刷新按钮现代化样式与动效自动化测试套件
验证范围：
1. files.html 路径栏刷新按钮：应用统一绿色现代化组件 .btn-refresh-icon，内嵌轻量 SVG 图标，接入 yfRefreshBtn 与 6 国语言国际化；
2. site.css 与 ensite.css：包含 .refreshBtn.btn-refresh-icon 专用高度与留白规则；
3. files.js：第二行工具栏刷新按钮接入 yfRefreshBtn 旋转动效与 refreshLabel 多语言，且 calcPathWidth 动态宽度计算无缝兼容；
4. 全量文件编码为 UTF-8 无 BOM 且强制 LF 换行符。
"""

import os
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES_HTML_PATH = os.path.join(ROOT_DIR, "web", "templates", "default", "files.html")
SITE_CSS_PATH = os.path.join(ROOT_DIR, "web", "static", "css", "site.css")
ENSITE_CSS_PATH = os.path.join(ROOT_DIR, "web", "static", "css", "ensite.css")
FILES_JS_PATH = os.path.join(ROOT_DIR, "web", "static", "app", "files.js")


class TestFilesRefreshBtn(unittest.TestCase):

    def test_01_files_html_refresh_btn_structure_and_i18n(self):
        """验证 files.html 路径栏刷新按钮现代化结构、SVG 图标与多语言绑定"""
        with open(FILES_HTML_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 必须应用现代化组件类
        self.assertIn("btn-refresh-icon refreshBtn pull-right", content, "files.html 中刷新按钮应包含 btn-refresh-icon refreshBtn pull-right")
        self.assertNotIn("backBtn refreshBtn btn btn-default", content, "files.html 中不应再包含旧版灰色默认按钮类 backBtn refreshBtn btn btn-default")
        
        # 必须使用矢量 SVG 图标，不再使用老旧 glyphicon-refresh
        self.assertIn("<svg viewBox=\"0 0 24 24\"", content, "files.html 刷新按钮内应内嵌现代 SVG 矢量图标")
        self.assertNotIn("refreshBtn btn btn-default btn-sm glyphicon glyphicon-refresh", content, "files.html 刷新按钮不应再包含 glyphicon-refresh")

        # 必须包含国际化属性
        self.assertIn('data-i18n="public.refresh"', content, "files.html 刷新按钮应包含 data-i18n=\"public.refresh\"")
        self.assertIn('data-i18n-attr="title"', content, "files.html 刷新按钮应包含 data-i18n-attr=\"title\"")
        self.assertIn("t('public.refresh', '刷新')", content, "files.html 刷新按钮应使用 t('public.refresh', '刷新') 渲染默认 title")

        # 必须接入 yfRefreshBtn
        self.assertIn("onclick=\"yfRefreshBtn(this, function(){ getFiles(getCookie('open_dir_path')); });\"", content, "files.html 刷新按钮应接入全局 yfRefreshBtn 旋转动效")

        # 移除重复的双重 click 监听
        self.assertNotIn('$(".refreshBtn").on(\'click\', function() {', content, "files.html 中不应有重复的 $('.refreshBtn').on('click') 双重请求监听")

    def test_02_css_refresh_btn_styles(self):
        """验证 site.css 与 ensite.css 中包含 .refreshBtn.btn-refresh-icon 专属尺寸与边距适配"""
        for css_path, label in [(SITE_CSS_PATH, "site.css"), (ENSITE_CSS_PATH, "ensite.css")]:
            with open(css_path, "r", encoding="utf-8") as f:
                css_text = f.read()

            self.assertIn(".refreshBtn.btn-refresh-icon", css_text, f"{label} 应包含 .refreshBtn.btn-refresh-icon 规则")
            self.assertIn("height: 28px !important;", css_text, f"{label} 应显式指定高度为 28px 与路径栏严密平齐")
            self.assertIn("min-width: 28px !important;", css_text, f"{label} 应显式指定最小宽度为 28px")
            self.assertIn("margin-left: 6px !important;", css_text, f"{label} 应设置 margin-left: 6px 呼吸留白")

    def test_03_files_js_tools_and_dynamic_width(self):
        """验证 files.js 中 BarTools 刷新按钮动效接入及 calcPathWidth 算法兼容性"""
        with open(FILES_JS_PATH, "r", encoding="utf-8") as f:
            js_text = f.read()

        # 第二行工具栏接入动效与多语言
        self.assertIn("var refreshLabel = (window.lan && lan.public && lan.public.refresh) || t('public.refresh', '刷新');", js_text, "files.js 应定义 refreshLabel 多语言")
        self.assertIn("yfRefreshBtn(this, function(){ getFiles", js_text, "files.js 第二行刷新按钮应调用 yfRefreshBtn 触发平滑旋转动效")
        self.assertIn('title="\' + refreshLabel + \'"', js_text, "files.js 第二行刷新按钮应接入 refreshLabel 国际化提示")

        # calcPathWidth 计算选择器兼容性
        self.assertIn('$(".refreshBtn").outerWidth(true)', js_text, "files.js 中 calcPathWidth 应通过 .refreshBtn 选择器动态测量刷新按钮宽度")

    def test_04_file_encoding_and_lf(self):
        """验证所有修改文件严格使用 UTF-8 (无 BOM) 且换行符强制为 LF"""
        target_files = [FILES_HTML_PATH, SITE_CSS_PATH, ENSITE_CSS_PATH, FILES_JS_PATH]
        for file_path in target_files:
            rel_name = os.path.relpath(file_path, ROOT_DIR)
            with open(file_path, "rb") as f:
                raw_bytes = f.read()

            self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"), f"{rel_name} 不应包含 UTF-8 BOM 头")
            self.assertNotIn(b"\r\n", raw_bytes, f"{rel_name} 必须强制使用 LF (\\n) 换行符，禁止出现 CRLF (\\r\\n)")


if __name__ == "__main__":
    unittest.main()
