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

# ---------------------------------------------------------------------------
# 「pt(...) 被写进了字符串字面量里」检测器
# ---------------------------------------------------------------------------
# 要抓的 bug：作者少写了一个闭合引号，于是 `pt('中文')` 连同 `+` 号一起
# 落进了字符串内部，页面上会**原样显示** `" + pt('中文') + "` 这种代码碎片。
#
# 判定规则：当扫描器**处于某个字符串内部**时，若遇到另一种引号，且紧跟
# `+ pt(`（允许空格），说明那个引号本该是 JS 字符串的结束符却没起作用。
#
# 这个检测器必须先把**注释**和**正则字面量**跳过去，否则里面的引号会把
# 引号状态机带偏，后面整片区域都会被误判。实测踩过的坑：
#     const ch_reg = /channel \'(.*)\';/;
# 正则里的 `\'` 被当成字符串开引号，扫描器从那一行起一路失步，
# 把 mysql.js 里 17 处**正确**的 `" + pt('中文') + "` 写法全报成泄漏
# （用 node 真求值那段 content: 表达式，渲染结果是翻译后的文字，证实是误报）。
#
# 因此这里是一个小词法器：引号配对栈 + 跳过 // 行注释、/* */ 块注释、
# 以及「值位置」上的 /.../flags 正则字面量。
import re as _re

_LEAK_TAIL_RE = _re.compile(r'''(['"`])\s*\+\s*pt\(''')
#: 上一个「有意义字符」落在这些里面时，`/` 只能是除号，不是正则开头。
_NO_REGEX_AFTER = set(')]}"\'`')


def _regex_can_start(prev_sig):
    """根据上一个有意义字符判断 `/` 是正则字面量开头还是除号。"""
    if prev_sig == '':
        return True
    if prev_sig.isalnum() or prev_sig in ' _$':
        return False
    if prev_sig in _NO_REGEX_AFTER:
        return False
    return True


def find_literal_pt_leaks(text):
    """返回 [(偏移, 片段)] —— 字符串字面量内部出现的 pt() 拼接残留。"""
    leaks = []
    stack = []
    i = 0
    n = len(text)
    prev_sig = ''       # 上一个有意义字符（跳过空白），用于区分除号 / 正则
    while i < n:
        ch = text[i]

        if stack:
            if ch == '\\':
                i += 2          # 转义：连反斜杠带被转义字符一起跳过
                continue
            if ch == stack[-1]:
                stack.pop()     # 配对成功，退出当前字符串
                prev_sig = ch
                i += 1
                continue
            # 字符串内部遇到了「另一种引号 + pt(」，即漏写闭合引号
            if ch in ('"', "'", '`') and _LEAK_TAIL_RE.match(text, i):
                leaks.append((i, text[i:i + 40]))
            i += 1
            continue

        # ---- 不在字符串里：先跳过注释与正则字面量 ----
        if ch == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            i = n if j < 0 else j + 1
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == '/' and _regex_can_start(prev_sig):
            j = i + 1
            in_class = False
            while j < n:
                c = text[j]
                if c == '\\':
                    j += 2
                    continue
                if c == '\n':
                    break
                if c == '[':
                    in_class = True
                elif c == ']':
                    in_class = False
                elif c == '/' and not in_class:
                    break
                j += 1
            if j < n and text[j] == '/':
                i = j + 1
                while i < n and text[i].isalpha():   # 正则 flags
                    i += 1
                prev_sig = '/'
                continue

        if ch in ('"', "'", '`'):
            stack.append(ch)
        if not ch.isspace():
            prev_sig = ch
        i += 1
    return leaks


class TestMySQLUiI18n(unittest.TestCase):

    def test_01_index_html_styles_and_reset(self):
        """验证 plugins/mysql/index.html 弹窗尺寸重置与样式规范"""
        index_html_path = os.path.join(MYSQL_DIR, "index.html")
        self.assertTrue(os.path.isfile(index_html_path), "index.html 必须存在")

        with open(index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. 验证重置弹窗宽高的函数调用
        # 宽度随列数增加调整过：1050 -> 1180（见 plugins/mysql/index.html）。
        self.assertIn("resetPluginWinWidth(1180);", content, "必须显式调用 resetPluginWinWidth(1180)")
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
        # 最小宽度随列数调整过：270px -> 230px（见 mysql.js 里操作列表头/单元格）。
        self.assertIn("min-width:230px; white-space:nowrap;", content, "操作列必须设置 min-width:230px 与 white-space:nowrap")

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

        leaks = find_literal_pt_leaks(text)
        self.assertEqual(len(leaks), 0, f"mysql.js 依然存在字符串字面量拼接泄漏错误: {leaks}")

    def test_06b_pt_leak_scanner_self_check(self):
        """自证：检测器必须能抓到真泄漏、且不对本仓库的正确写法误报。

        用合成样本当判定基准（与被检测的 mysql.js 无关），否则「0 处泄漏」
        分不清是「真的干净」还是「检测器压根不工作」。
        """
        # 1) 真泄漏：少写闭合引号，`+ pt(` 连同引号一起落进字符串里 —— 必须抓到。
        #    形如 `'<span class="x">" + pt('中文') + "</span>'`：
        #    那个 `"` 本该是 JS 字符串的结束符，却留在了字符串内部。
        leaky = [
            """var h = '<span class="x">" + pt('中文') + "</span>';""",
            """var h = "<span class='x'>' + pt('中文') + '</span>";""",
        ]
        for src in leaky:
            self.assertTrue(find_literal_pt_leaks(src), f"检测器漏报了真泄漏: {src!r}")

        # 2) 正确写法：本仓库大量使用的「HTML 属性用另一种引号」+ 正常拼接 —— 不许误报
        clean = [
            """var Con = '<div class="divtable">' + pt('启动时间') + '</div>';""",
            """var a = "<span class='f14 c6 mr20'>" + pt('中文') + "</span>";""",
            """content:"<div class='bt-form pd20 c6'>" + pt('同步配置') + "</div>",""",
            """var t = 'it\\'s ok'; var b = 'x' + pt('中文');""",
            """var c = 'a' + pt('b') + 'c' + pt('d') + 'e';""",
            # 回归：正则字面量里的撇号曾把扫描器带偏（见上方注释）。
            # 跳过正则后，后面的 `'x' + pt('中文')` 必须判为干净。
            """var ch_reg = /channel \\'(.*)\\';/; var b = 'x' + pt('中文');""",
            """var n = a / b; var b = 'x' + pt('中文');""",
            """var s = 'a' + pt('b'); // 注释里有撇号 it's fine""",
        ]
        for src in clean:
            self.assertEqual(find_literal_pt_leaks(src), [],
                             f"检测器对正确写法误报了: {src!r}")

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

