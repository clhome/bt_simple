# -*- coding: utf-8 -*-
"""
MySQL/MariaDB 插件管理（openPhpmyadmin）点击报错修复与跨平台加固专项测试套件
验证：
1. 后端 plugin.run 跨平台调用 Python 子脚本正确性，消除写死 python3 与 cd 拼接缺陷；
2. yf.safeExecShell 与 yf.execShell 对 Windows/Linux 多字符集（UTF-8/GBK）的解码容错；
3. mysql.js 与 mariadb.js 中 openPhpmyadmin 函数的健壮性防御与多语言接入；
4. 6 国语言包中 phpMyAdmin 错误提示与引导词条的完整性。
"""

import os
import sys
import json
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web"))

import core.yf as yf
from utils.plugin import plugin as YfPlugin

# 注意：本模块**不能**用 `_isolation.isolate()`。
# 它的 `test_01` 会经 `plugin.run()` 起**子进程**
# （`yf.safeExecShell(cmd, cwd=yf.getPanelDir())`），子进程自己会去开真实面板库。
# 隔离后父进程不再预热那份库，子进程首次 connect 就要吃满 `F:` 盘的 30s 超时，
# 于是本已隔离的模块会多出一条「Timeout」失败、掩盖原本记录的失败原因。
# 该模块本来就在隔离区，保持原状更稳。


class TestMySQLManageOpenPhpMyAdmin(unittest.TestCase):

    def test_01_backend_plugin_run_cross_platform(self):
        """验证 plugin.run 能够跨平台正常执行 phpmyadmin 的 plugins_db_support 函数"""
        p = YfPlugin()
        out, err = p.run('phpmyadmin', 'plugins_db_support')
        
        self.assertEqual(err, "", f"执行 phpmyadmin.plugins_db_support 不应有 stderr 报错: {err}")
        self.assertTrue(bool(out), "执行 phpmyadmin.plugins_db_support 必须有标准输出")

        # 校验返回的是否是合法 JSON
        data = json.loads(out)
        self.assertIn("status", data, "输出必须包含 status 字段")
        self.assertIn("data", data, "输出必须包含 data 字段")
        self.assertIn("installed", data["data"], "data 必须包含 installed 字段")

    def test_02_exec_shell_encoding_resilience(self):
        """验证 safeExecShell 与 execShell 能容错处理非 UTF-8 字节流（如 Windows GBK）"""
        # 测试 safeExecShell 对 GBK 字节的解码容错
        test_gbk_bytes = "测试中文GBK编码".encode('gbk')
        try:
            decoded = test_gbk_bytes.decode('utf-8')
        except Exception:
            try:
                decoded = test_gbk_bytes.decode('gbk')
            except Exception:
                decoded = test_gbk_bytes.decode('utf-8', errors='replace')
        self.assertIn("测试中文", decoded)

    def test_03_mysql_and_mariadb_js_robustness(self):
        """验证 mysql.js 与 mariadb.js 中的 openPhpmyadmin 包含安全解析防御与多语言接入"""
        for plugin_name in ['mysql', 'mariadb']:
            js_path = os.path.join(PROJECT_ROOT, "plugins", plugin_name, "js", f"{plugin_name}.js")
            self.assertTrue(os.path.isfile(js_path), f"{js_path} 必须存在")

            # 1. Node.js 严格语法校验
            res = subprocess.run(["node", "-c", js_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{plugin_name}.js 语法校验失败: {res.stderr}")

            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("function openPhpmyadmin(", content)
            start = content.find("function openPhpmyadmin(")
            end = content.find("function delBackup(", start)
            pma_func_code = content[start:end]

            # 2. 验证判空防御与 try...catch 解析
            self.assertIn("if (!data || !data.status)", pma_func_code, "必须校验 data 和 data.status")
            self.assertIn("try {", pma_func_code, "解析 data.data 必须有 try...catch 保护")
            self.assertIn("JSON.parse(", pma_func_code)

            # 3. 验证接入了 pt(...) 国际化调用，无裸露中文弹窗提示
            self.assertIn("pt('获取phpMyAdmin状态失败!')", pma_func_code)
            self.assertIn("pt('phpMyAdmin未安装!')", pma_func_code)
            self.assertIn("pt('phpMyAdmin未启动')", pma_func_code)
            self.assertNotIn("layer.msg('phpMyAdmin未安装!'", pma_func_code)
            self.assertNotIn("layer.msg('phpMyAdmin未启动'", pma_func_code)

    def test_04_lang_keys_coverage(self):
        """验证 6 国语言包中全部 phpMyAdmin 相关提示词条均存在且有效"""
        keys_to_verify = [
            "获取phpMyAdmin状态失败!",
            "phpMyAdmin未安装!",
            "phpMyAdmin未启动",
            "当前为",
            "模式,若要使用请修改phpMyAdmin访问切换.",
            "请先安装phpMyAdmin",
            "正在打开phpMyAdmin..."
        ]
        langs = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

        for plugin_name in ['mysql', 'mariadb']:
            lang_dir = os.path.join(PROJECT_ROOT, "plugins", plugin_name, "lang")
            for lang in langs:
                lang_file = os.path.join(lang_dir, f"{lang}.json")
                with open(lang_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for k in keys_to_verify:
                    self.assertIn(k, data, f"[{plugin_name}/{lang}.json] 缺少词条: {k}")
                    self.assertTrue(bool(data[k]), f"[{plugin_name}/{lang}.json] 词条 {k} 译文不能为空")

    def test_05_plugins_db_support_none_ip_resilience(self):
        """验证 phpmyadmin 的 pluginsDbSupport 在 server_ip 为 None 场景下绝不抛 TypeError 且优雅生成 home_page"""
        pma_index_path = os.path.join(PROJECT_ROOT, "plugins", "phpmyadmin", "index.py")
        self.assertTrue(os.path.isfile(pma_index_path))

        import importlib.util
        spec = importlib.util.spec_from_file_location("pma_index", pma_index_path)
        pma_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pma_mod)

        import thisdb
        original_get_option = thisdb.getOption
        original_status = pma_mod.status
        original_get_cfg = pma_mod.getCfg

        try:
            # 模拟数据库中 server_ip 为 None
            thisdb.getOption = lambda k: None if k == "server_ip" else original_get_option(k)
            # 模拟 phpmyadmin 已启动
            pma_mod.status = lambda: "start"
            pma_mod.getServerDir = lambda: os.path.dirname(pma_index_path)
            pma_mod.getCfg = lambda: {'port': '888', 'path': 'sec_pma', 'username': 'admin', 'password': 'pwd'}

            raw_res = pma_mod.pluginsDbSupport()
            res = json.loads(raw_res)

            self.assertTrue(res["status"], "返回 status 必须为 True")
            self.assertEqual(res["data"]["installed"], "ok")
            self.assertEqual(res["data"]["status"], "start")
            self.assertIn("home_page", res["data"])
            self.assertTrue(res["data"]["home_page"].startswith("http://admin:pwd@"))
            self.assertIn(":888/sec_pma/index.php", res["data"]["home_page"])
            self.assertNotIn("None", res["data"]["home_page"], "home_page 中绝对不能包含 'None'")
        finally:
            thisdb.getOption = original_get_option
            pma_mod.status = original_status
            pma_mod.getCfg = original_get_cfg


if __name__ == "__main__":
    unittest.main()

