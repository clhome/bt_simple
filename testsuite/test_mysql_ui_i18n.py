# -*- coding: utf-8 -*-
"""
MySQL 插件样式优化与多语言适配专项自动化测试套件
验证弹窗尺寸重置、侧边栏宽度、单层滚动、防折行样式、元数据声明以及多语言词条。
"""

import os
import sys
import json
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MYSQL_DIR = os.path.join(PROJECT_ROOT, "plugins", "mysql")


class TestMySQLUiI18n(unittest.TestCase):

    def test_01_index_html_styles_and_reset(self):
        """验证 plugins/mysql/index.html 弹窗尺寸重置与样式规范"""
        index_html_path = os.path.join(MYSQL_DIR, "index.html")
        self.assertTrue(os.path.isfile(index_html_path), "index.html 必须存在")

        with open(index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. 验证重置弹窗宽高的函数调用
        self.assertIn("resetPluginWinWidth(1050);", content, "必须显式调用 resetPluginWinWidth(1050)")
        self.assertIn("resetPluginWinHeight(650);", content, "必须显式调用 resetPluginWinHeight(650)")

        # 2. 验证左侧菜单宽度为 168px
        self.assertIn("width: 168px !important;", content, "侧边栏宽度必须拓宽至 168px")

        # 3. 验证左侧菜单项文字防截断与悬浮提示
        self.assertIn("text-overflow: ellipsis !important;", content, "侧边栏文字必须配置 ellipsis 溢出防护")
        self.assertIn("syncMenuTitles()", content, "必须调用 syncMenuTitles 同步悬浮 title 提示")

        # 4. 验证内联写死高度已彻底清除
        self.assertNotIn('height:555px', content, "严禁在内容区内联写死 height:555px")
        self.assertNotIn('height: 555px', content, "严禁在内容区内联写死 height: 555px")

        # 5. 验证没有被注释掉的弹窗尺寸残留
        self.assertNotIn("<!-- <script type=\"text/javascript\">\nresetPluginWinWidth", content, "不能有被注释的 resetPluginWinWidth")

    def test_02_info_json_size_metadata(self):
        """验证 plugins/mysql/info.json 中的标准 size 声明"""
        info_json_path = os.path.join(MYSQL_DIR, "info.json")
        self.assertTrue(os.path.isfile(info_json_path), "info.json 必须存在")

        with open(info_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("size", data, "info.json 必须包含 size 字段声明")
        self.assertEqual(data["size"], [1050, 650], "弹窗尺寸声明必须为 [1050, 650]")

    def test_03_mysql_js_layout_and_syntax(self):
        """验证 plugins/mysql/js/mysql.js 语法无误且列表排版防折行"""
        js_path = os.path.join(MYSQL_DIR, "js", "mysql.js")
        self.assertTrue(os.path.isfile(js_path), "mysql.js 必须存在")

        # 1. Node.js 严格语法校验
        result = subprocess.run(["node", "-c", js_path], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"mysql.js 语法校验失败: {result.stderr}")

        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 2. 验证操作列防折行与最小宽度
        self.assertIn("min-width:270px; white-space:nowrap;", content, "操作列必须设置 min-width:270px 与 white-space:nowrap")

        # 3. 验证顶部按钮工具栏弹性布局
        self.assertIn("display:flex; flex-wrap:wrap;", content, "顶部按钮容器必须具备弹性流式换行保护")

    def test_04_lang_json_validity_and_keywords(self):
        """验证全套 6 国语言包 JSON 语法与关键词地道化"""
        lang_dir = os.path.join(MYSQL_DIR, "lang")
        langs = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

        for lang in langs:
            lang_file = os.path.join(lang_dir, f"{lang}.json")
            self.assertTrue(os.path.isfile(lang_file), f"{lang}.json 必须存在")

            with open(lang_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 校验核心基础菜单项存在
            self.assertIn("服务", data, f"{lang}.json 缺少 '服务' 翻译")
            self.assertIn("管理列表", data, f"{lang}.json 缺少 '管理列表' 翻译")
            self.assertIn("性能优化", data, f"{lang}.json 缺少 '性能优化' 翻译")
            self.assertIn("主从配置", data, f"{lang}.json 缺少 '主从配置' 翻译")

        # 专项检查 en 词汇规范（全部精简地道，杜绝省略号）
        with open(os.path.join(lang_dir, "en.json"), "r", encoding="utf-8") as f:
            en_data = json.load(f)
        self.assertEqual(en_data["服务"], "Service", "英文服务应翻译为 Service")
        self.assertEqual(en_data["慢日志"], "Slow Log", "英文慢日志应翻译为 Slow Log")
        self.assertEqual(en_data["存储位置"], "Storage", "英文存储位置应优化为精简的 Storage")
        self.assertEqual(en_data["当前状态"], "Status", "英文当前状态应优化为精简的 Status")
        self.assertEqual(en_data["性能优化"], "Performance", "英文性能优化应优化为精简的 Performance")
        self.assertEqual(en_data["配置文件"], "Configuration", "英文配置文件应优化为 Configuration")
        self.assertEqual(en_data["主从配置"], "Master-Slave", "英文主从配置应优化为 Master-Slave")

        # 专项检查 fr 与 de
        with open(os.path.join(lang_dir, "fr.json"), "r", encoding="utf-8") as f:
            fr_data = json.load(f)
        self.assertEqual(fr_data["服务"], "Service", "法文服务应翻译为 Service")

        with open(os.path.join(lang_dir, "de.json"), "r", encoding="utf-8") as f:
            de_data = json.load(f)
        self.assertEqual(de_data["服务"], "Dienst", "德文服务应翻译为 Dienst")

    def test_05_backend_master_status_no_nameerror(self):
        """验证后端 getMasterStatus 等函数消除 NameError mode 缺陷"""
        py_path = os.path.join(MYSQL_DIR, "index.py")
        import ast

        with open(py_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        # AST 严格检查是否有使用未定义的 mode 变量
        class ModeVisitor(ast.NodeVisitor):
            def __init__(self):
                self.errors = []
            def visit_FunctionDef(self, node):
                assigned = {arg.arg for arg in node.args.args}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        assigned.add(sub.id)
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        if sub.id == 'mode' and 'mode' not in assigned:
                            self.errors.append((node.name, sub.lineno))
                self.generic_visit(node)

        visitor = ModeVisitor()
        visitor.visit(tree)
        self.assertEqual(len(visitor.errors), 0, f"index.py 中存在未定义 mode 变量: {visitor.errors}")

    def test_06_no_literal_pt_in_mysql_js(self):
        """验证 mysql.js 彻底消除字符串字面量中未闭合的 pt(...) 代码泄漏（错误数严格等于 0）"""
        js_path = os.path.join(MYSQL_DIR, "js", "mysql.js")
        with open(js_path, "r", encoding="utf-8") as f:
            text = f.read()

        i = 0
        n = len(text)
        current_quote = None
        line_num = 1
        errors = []

        while i < n:
            ch = text[i]
            if ch == '\n':
                line_num += 1
                i += 1
                continue
            
            if current_quote is None:
                if ch in ('"', "'", '`'):
                    current_quote = ch
            else:
                if ch == '\\':
                    if i + 1 < n and text[i+1] == '\n':
                        line_num += 1
                        i += 2
                        continue
                    elif i + 2 < n and text[i+1:i+3] == '\r\n':
                        line_num += 1
                        i += 3
                        continue
                    else:
                        i += 2
                        continue
                elif ch == current_quote:
                    current_quote = None
                else:
                    if current_quote == '"' and text[i:i+7] in ("' + pt(", "'+pt("):
                        errors.append((line_num, current_quote, text[i:i+35]))
                    elif current_quote == "'" and text[i:i+7] in ('" + pt(', '"+pt('):
                        errors.append((line_num, current_quote, text[i:i+35]))
                    elif current_quote == '`' and text[i:i+7] in ("' + pt(", "'+pt(", '"+pt(', '" + pt('):
                        errors.append((line_num, current_quote, text[i:i+35]))
            i += 1

        self.assertEqual(len(errors), 0, f"mysql.js 依然存在字符串字面量拼接泄漏错误: {errors}")

    def test_07_add_database_modal_i18n_and_elements(self):
        """验证 addDatabase 弹窗各字段与选项完整接入多语言且排版优雅"""
        js_path = os.path.join(MYSQL_DIR, "js", "mysql.js")
        with open(js_path, "r", encoding="utf-8") as f:
            text = f.read()

        self.assertIn("function addDatabase(", text)
        start = text.find("function addDatabase(")
        end = text.find("function setRootPwd(", start)
        add_db_code = text[start:end]

        # 1. 验证尺寸与弹窗配置
        self.assertIn("area: '540px'", add_db_code)
        self.assertIn("title:  pt('添加数据库')", add_db_code)
        self.assertIn('btn: [pt("提交"), pt("关闭")]', add_db_code)

        # 2. 验证各标签与 placeholder 国际化
        required_calls = [
            "pt('数据库名')",
            "pt('新的数据库名称')",
            "pt('用户名')",
            "pt('数据库用户')",
            "pt('密码')",
            "pt('随机密码')",
            "pt('访问权限')",
            "pt('本地服务器')",
            "pt('所有人')",
            "pt('指定IP')",
            "pt('多个IP使用逗号(,)分隔')"
        ]
        for rc in required_calls:
            self.assertIn(rc, add_db_code, f"addDatabase 必须包含 {rc} 的国际化调用")

        # 3. 验证不再有硬编码中文 placeholder
        self.assertNotIn("placeholder='新的数据库名称'", add_db_code)
        self.assertNotIn("placeholder='数据库用户'", add_db_code)
        self.assertNotIn("title='随机密码'", add_db_code)

    def test_08_modal_keywords_coverage_across_6_languages(self):
        """验证全部弹窗关键词条在 6 国语言包中 100% 存在且有效"""
        keys_to_verify = [
            "添加数据库",
            "数据库名",
            "新的数据库名称",
            "用户名",
            "数据库用户",
            "密码",
            "随机密码",
            "访问权限",
            "本地服务器",
            "所有人",
            "指定IP",
            "多个IP使用逗号(,)分隔",
            "root密码",
            "复制ROOT密码",
            "修改本地ROOT记录",
            "强改ROOT密码",
            "选择其中一个复制",
            "同步数据源：",
            "开始",
            "手动命令",
            "端口",
            "同步账户",
            "同步密码",
            "同步模式",
            "经典",
            "CMD[必填]",
            "为空则取第一个!",
            "未设置",
            "已设置"
        ]
        lang_dir = os.path.join(MYSQL_DIR, "lang")
        langs = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

        for lang in langs:
            lang_file = os.path.join(lang_dir, f"{lang}.json")
            with open(lang_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key in keys_to_verify:
                self.assertIn(key, data, f"[{lang}.json] 缺少关键多语言词条: {key}")
                self.assertTrue(bool(data[key]), f"[{lang}.json] 词条 {key} 译文不能为空")


if __name__ == "__main__":
    unittest.main()

