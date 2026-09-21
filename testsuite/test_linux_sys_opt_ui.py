# -*- coding: utf-8 -*-
"""
test/test_linux_sys_opt_ui.py
验证 Linux 系统优化插件 (linux_sys_opt) 弹窗宽度拓宽、表格防重叠、底部公司信息独立换行及固定底部的正确性。
"""

import os
import re
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, 'plugins', 'linux_sys_opt', 'index.html')
LANG_DIR = os.path.join(BASE_DIR, 'plugins', 'linux_sys_opt', 'lang')

class TestLinuxSysOptUI(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(INDEX_HTML), "index.html 文件必须存在")
        with open(INDEX_HTML, 'r', encoding='utf-8') as f:
            self.content = f.read()

    def test_file_format(self):
        """测试文件无 BOM，使用 LF 换行"""
        with open(INDEX_HTML, 'rb') as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), "index.html 不应包含 UTF-8 BOM")
        self.assertNotIn(b'\r\n', raw, "index.html 应使用 LF 换行符，不应有 CRLF")

    def test_window_width(self):
        """测试弹窗宽度拓宽至 1050px"""
        self.assertIn("resetPluginWinWidth(1050);", self.content, "必须将初始宽度设置为 1050")
        self.assertIn("layuiLayer.css('width', '1050px');", self.content, "动态拉宽应设置为 1050px")
        self.assertIn("width() < 1050", self.content, "动态宽度判定阈值应为 1050")
        self.assertNotIn("resetPluginWinWidth(850);", self.content, "旧的 850 宽度必须已更新")

    def test_table_column_widths(self):
        """测试表格 4 列宽度比例优化（30%, 40%, 18%, 12%）"""
        self.assertIn('<th width="30%"', self.content, "参数名列宽应分配 30%")
        self.assertIn('<th width="40%"', self.content, "作用描述列宽应分配 40%")
        self.assertIn('<th width="18%"', self.content, "当前值列宽应分配 18%")
        self.assertIn('<th width="12%"', self.content, "评分列宽应分配 12%")

    def test_table_cells_overflow_protection(self):
        """测试表格数据单元格防溢出与 title 提示属性"""
        # 提取表格 tbody 中的所有 <tr>
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', self.content, re.DOTALL)
        self.assertTrue(tbody_match, "必须包含 tbody 区域")
        tbody = tbody_match.group(1)
        rows = re.findall(r'<tr>(.*?)</tr>', tbody, re.DOTALL)
        self.assertEqual(len(rows), 11, "应该包含 11 行参数指标")

        for i, row in enumerate(rows):
            tds = re.findall(r'<td[^>]*>', row)
            self.assertEqual(len(tds), 3, f"第 {i+1} 行应有 3 个原生 td 标签（第 4 个由 getScoreTD 返回）")
            for td in tds:
                self.assertIn('overflow: hidden;', td, f"单元格必须包含 overflow: hidden; -> {td}")
                self.assertIn('text-overflow: ellipsis;', td, f"单元格必须包含 text-overflow: ellipsis; -> {td}")
                self.assertIn('white-space: nowrap;', td, f"单元格必须包含 white-space: nowrap; -> {td}")
                self.assertIn('title=', td, f"单元格必须包含 title 属性 -> {td}")

    def test_opt_status_bottom_layout(self):
        """测试优化状态界面中，按钮与公司信息彻底解耦分行"""
        # 确保不存在旧版的同一相对定位容器内重叠定位
        self.assertNotIn('position: absolute; right: 0; bottom: 0;', self.content, "旧版重叠的绝对定位必须清除")

        # 检查按钮独立居中容器
        button_container = re.search(r'<div style="[^"]*text-align:\s*center[^"]*">\s*<button[^>]*applyOpt[^>]*>', self.content)
        self.assertTrue(button_container, "一键优化按钮应位于独立的居中容器内")

        # 检查公司信息单独一行位于最底部
        copyright_pattern = re.search(r'<div style="text-align:\s*right;[^"]*">\s*\${pt\(\'衢州御风科技有限公司出品\'\)}\s*</div>', self.content)
        self.assertTrue(copyright_pattern, "公司信息必须另换一行并在最底部右对齐展示")

    def test_readme_fixed_bottom(self):
        """测试插件说明界面使用 Flex 垂直弹性盒固定底部公司信息"""
        self.assertIn("function readme() {", self.content, "必须存在 readme 函数")
        readme_idx = self.content.find("function readme() {")
        readme_code = self.content[readme_idx:]

        self.assertIn('display: flex;', readme_code, "说明外层卡片应使用 display: flex")
        self.assertIn('flex-direction: column;', readme_code, "说明外层卡片应使用 flex-direction: column")
        self.assertIn('flex: 1; overflow-y: auto;', readme_code, "文档内容应为 flex: 1 且允许纵向滚动")
        self.assertIn('flex-shrink: 0;', readme_code, "底部公司信息应使用 flex-shrink: 0 保持固定")

    def test_languages_coverage(self):
        """测试 6 国语言包完整覆盖相关文案"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = [
            '衢州御风科技有限公司出品',
            '内核与并发参数状态',
            '一键全局优化',
            '参数名',
            '作用描述',
            '当前值',
            '评分'
        ]
        for lang in langs:
            lang_path = os.path.join(LANG_DIR, f'{lang}.json')
            self.assertTrue(os.path.exists(lang_path), f"语言包 {lang}.json 必须存在")
            with open(lang_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in required_keys:
                self.assertIn(k, data, f"语言包 {lang}.json 缺少关键词条：{k}")
                self.assertTrue(data[k], f"语言包 {lang}.json 词条 {k} 不应为空")

    def test_inline_js_syntax(self):
        """测试 index.html 中的内联 JS 通过 Node.js 语法编译校验"""
        import subprocess
        script_match = re.search(r'<script[^>]*>(.*?)</script>', self.content, re.DOTALL)
        self.assertTrue(script_match, "必须包含内联 script")
        js_code = script_match.group(1)

        # 调用 node --check 校验语法
        proc = subprocess.run(['node', '--check'], input=js_code, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, f"JS 语法检测失败：{proc.stderr}")

    def test_memory_tier_tip_abbreviation(self):
        """测试在所有非中文（en, de, fr, it）环境下右上角提示采用精炼专业的紧凑缩写"""
        foreign_langs = ['en', 'de', 'fr', 'it']
        mem_val = "7.8GB"
        for lang in foreign_langs:
            lang_path = os.path.join(LANG_DIR, f'{lang}.json')
            with open(lang_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            part1 = data.get('当前内存为：', '')
            part2 = data.get('，优化脚本会', '')
            part3 = data.get('自动匹配', '')
            part4 = data.get('不同内存阶梯配置', '')

            full_rendered = f"{part1}{mem_val}{part2}{part3}{part4}"
            # 严格验证长度不超过 45 个字符，杜绝原先近 100 字符导致的折行和截断
            self.assertLessEqual(len(full_rendered), 45, 
                f"{lang}.json 右上角提示长度过长 ({len(full_rendered)} 字符)：'{full_rendered}'")
            # 验证采用 RAM 缩写
            self.assertTrue(part1.startswith('RAM'), f"{lang}.json 应采用 RAM 等专业缩写：'{part1}'")

if __name__ == '__main__':
    unittest.main()
