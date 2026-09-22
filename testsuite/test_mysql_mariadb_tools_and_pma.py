# -*- coding: utf-8 -*-
import os
import re
import json
import unittest
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MYSQL_LANG_DIR = os.path.join(PROJECT_ROOT, "plugins", "mysql", "lang")
MARIADB_LANG_DIR = os.path.join(PROJECT_ROOT, "plugins", "mariadb", "lang")
MYSQL_JS_PATH = os.path.join(PROJECT_ROOT, "plugins", "mysql", "js", "mysql.js")
MARIADB_JS_PATH = os.path.join(PROJECT_ROOT, "plugins", "mariadb", "js", "mariadb.js")
MYSQL_PY_PATH = os.path.join(PROJECT_ROOT, "plugins", "mysql", "index.py")
MARIADB_PY_PATH = os.path.join(PROJECT_ROOT, "plugins", "mariadb", "index.py")

TOOL_KEYS = [
    "优化全库碎片",
    "对该数据库下所有数据表执行碎片整理",
    "转为InnoDB",
    "转为MyISAM",
    "正在执行修复指令,请稍候...",
    "正在优化数据表碎片,请稍候...",
    "正在转换引擎类型,请稍候...",
    "请至少选择一张表!",
    "大小：",
    "【修复】尝试使用 REPAIR TABLE 修复损坏的数据表（注：仅 MyISAM 引擎生效，InnoDB 表具备事务自愈机制无需修复）。",
    "【优化】执行 OPTIMIZE TABLE 回收删除或更新产生的未释放磁盘空间与碎片，建议定期执行。",
    "【转为InnoDB】将 MyISAM 表升级为 InnoDB 事务引擎，获得行级锁与高并发抗崩溃保护。"
]

# 工具箱标题是**按插件区分**的：mysql 用「MySQL工具箱」、mariadb 用「MariaDB工具箱」
# （见各自 js 里 `pt('MySQL工具箱')` / `pt('MariaDB工具箱')`）。
# 别再要求两边都有两个键——那会凭空多出一个死键断言。
TOOLBOX_KEY = {"MySQL": "MySQL工具箱", "MariaDB": "MariaDB工具箱"}

LANGUAGES = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
WESTERN_LANGS = ["en", "de", "fr", "it"]


class TestMysqlMariadbToolsAndPma(unittest.TestCase):

    def test_01_open_phpmyadmin_logic(self):
        """验证 openPhpmyadmin 彻底移除了 url.indexOf('phpmyadmin') == -1 错误校验，并支持随机安全路径"""
        for js_name, js_path in [("mysql.js", MYSQL_JS_PATH), ("mariadb.js", MARIADB_JS_PATH)]:
            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. 确保不再包含 url.indexOf('phpmyadmin') == -1 的错误拦截
            self.assertNotIn("url.indexOf('phpmyadmin') == -1", content,
                             f"[{js_name}] 仍残留错误的 url.indexOf('phpmyadmin') == -1 校验！")

            # 2. 确保 openPhpmyadmin 函数定义存在
            self.assertIn("function openPhpmyadmin", content,
                          f"[{js_name}] 未找到 openPhpmyadmin 函数定义")

            # 3. 验证安全性与动态表单构建
            self.assertIn("pma_username", content, f"[{js_name}] 未找到 pma_username 传参字段")
            self.assertIn("pma_password", content, f"[{js_name}] 未找到 pma_password 传参字段")
            # 打开机制已从「window.open(url...)」改为「隐藏 POST 表单自动提交」：
            # 密码走请求体而不是 URL 查询串，避免凭据留在浏览器历史 / 服务器日志里。
            # 见 plugins/mysql/js/mysql.js 的 openPhpmyadmin()（$("#toPHPMyAdmin").submit()）。
            self.assertIn('id="toPHPMyAdmin"', content, f"[{js_name}] 未找到隐藏跳转表单 toPHPMyAdmin")
            self.assertIn('target="_blank"', content, f"[{js_name}] 跳转表单未以新窗口打开（缺 target=_blank）")
            self.assertIn('$("#toPHPMyAdmin").submit()', content, f"[{js_name}] 未保留新窗口打开机制（表单未自动提交）")

    def test_02_backend_tools_defect_fixed(self):
        """验证后端 repairTable、optTable、alterTable 彻底移除了成功操作仍写死返回 False 的缺陷"""
        for py_name, py_path in [("mysql/index.py", MYSQL_PY_PATH), ("mariadb/index.py", MARIADB_PY_PATH)]:
            with open(py_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查 repairTable 实现
            repair_match = re.search(r'def repairTable\(\):(.*?)(?=\ndef |\Z)', content, re.DOTALL)
            self.assertIsNotNone(repair_match, f"[{py_name}] 未找到 repairTable 方法")
            repair_code = repair_match.group(1)
            # 确保彻底消除了成功提示却返回 False 的荒唐错误
            self.assertNotIn('return yf.returnJson(False, "数据表修复操作执行完毕!")', repair_code,
                             f"[{py_name}] repairTable 中仍存在成功操作写死返回 False 的缺陷！")
            self.assertIn("REPAIR TABLE", repair_code, f"[{py_name}] repairTable 缺少 REPAIR TABLE SQL 语句")
            self.assertIn('return yf.returnJson(True, "数据表修复操作执行完毕!")', repair_code,
                          f"[{py_name}] repairTable 缺少成功的 returnJson(True, ...) 返回！")

            # 检查 optTable 实现
            opt_match = re.search(r'def optTable\(\):(.*?)(?=\ndef |\Z)', content, re.DOTALL)
            self.assertIsNotNone(opt_match, f"[{py_name}] 未找到 optTable 方法")
            opt_code = opt_match.group(1)
            self.assertNotIn('return yf.returnJson(False, "数据表优化完成', opt_code,
                             f"[{py_name}] optTable 中仍存在成功操作写死返回 False 的缺陷！")
            self.assertIn("OPTIMIZE TABLE", opt_code, f"[{py_name}] optTable 缺少 OPTIMIZE TABLE SQL 语句")
            self.assertIn('return yf.returnJson(True, "数据表优化完成', opt_code,
                          f"[{py_name}] optTable 缺少成功的 returnJson(True, ...) 返回！")

            # 检查 alterTable 实现
            alter_match = re.search(r'def alterTable\(\):(.*?)(?=\ndef |\Z)', content, re.DOTALL)
            self.assertIsNotNone(alter_match, f"[{py_name}] 未找到 alterTable 方法")
            alter_code = alter_match.group(1)
            self.assertNotIn('return yf.returnJson(False, "数据表引擎已成功转换为', alter_code,
                             f"[{py_name}] alterTable 中仍存在成功操作写死返回 False 的缺陷！")
            self.assertIn("ENGINE=", alter_code, f"[{py_name}] alterTable 缺少 ENGINE= 转换语句")
            self.assertIn('return yf.returnJson(True, "数据表引擎已成功转换为', alter_code,
                          f"[{py_name}] alterTable 缺少成功的 returnJson(True, ...) 返回！")

    def test_03_frontend_tools_interaction_and_all_opt(self):
        """验证前端工具箱逻辑：全库优化支持、操作按钮智能渲染与多语言 title"""
        for js_name, js_path in [("mysql.js", MYSQL_JS_PATH), ("mariadb.js", MARIADB_JS_PATH)]:
            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. 验证 optDatabase 具备 'ALL' 全选优化分支
            self.assertIn("tables === 'ALL'", content,
                          f"[{js_name}] optDatabase 缺少 tables === 'ALL' 全库优化分支")

            # 2. 验证 renderDefaultDbTools 具备一键优化全库碎片
            self.assertIn("renderDefaultDbTools", content,
                          f"[{js_name}] 缺少 renderDefaultDbTools 函数")
            self.assertIn("optDatabase", content, f"[{js_name}] 缺少 optDatabase 调用")

            # 3. 验证 repTools 初始化及取消选中均恢复默认按钮
            self.assertIn("renderDefaultDbTools(db_name);", content,
                          f"[{js_name}] 未在 repTools 或 selectedTools 中恢复默认按钮")

            # 4. 验证引擎转换智能判断
            self.assertIn("targetTypeLabel", content,
                          f"[{js_name}] 缺少针对表当前引擎的智能目标标签映射")

            # 5. 验证弹窗关闭按钮优化为 1（标准右上角 X）
            self.assertIn("closeBtn: 1", content,
                          f"[{js_name}] layer.open 建议使用 closeBtn: 1 保持统一风格")

    def test_04_tools_i18n_completeness(self):
        """验证 MySQL 和 MariaDB 的全部 6 国语言包中工具箱词条均已完整翻译，西欧语言无汉字残留"""
        chinese_char_pattern = re.compile(r'[\u4e00-\u9fa5]')

        for plugin_name, lang_dir in [("MySQL", MYSQL_LANG_DIR), ("MariaDB", MARIADB_LANG_DIR)]:
            keys = TOOL_KEYS + [TOOLBOX_KEY[plugin_name]]
            for lang in LANGUAGES:
                file_path = os.path.join(lang_dir, f"{lang}.json")
                self.assertTrue(os.path.exists(file_path), f"[{plugin_name}] Missing lang file: {file_path}")

                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for key in keys:
                    self.assertIn(key, data, f"[{plugin_name} - {lang}] Key '{key}' not found in {lang}.json")
                    val = data[key]
                    self.assertTrue(bool(val and val.strip()), f"[{plugin_name} - {lang}] Key '{key}' has empty translation")

                    # 西欧语言包中绝不能残留汉字
                    if lang in WESTERN_LANGS:
                        has_chinese = bool(chinese_char_pattern.search(val))
                        self.assertFalse(has_chinese, f"[{plugin_name} - {lang}] Key '{key}' contains untranslated Chinese: {val}")

    def test_05_javascript_syntax_validity(self):
        """通过 node -c 严格验证 mysql.js 与 mariadb.js 的 JS 语法规范"""
        for js_file in [MYSQL_JS_PATH, MARIADB_JS_PATH]:
            res = subprocess.run(["node", "-c", js_file], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"JS Syntax Error in {js_file}:\n{res.stderr}")


if __name__ == '__main__':
    unittest.main()
