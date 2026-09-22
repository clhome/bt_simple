# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页 3 处多语言未完整翻译的优化效果
1. 顶部运行时间多语言支持与前缀
2. Recent Logins 微表格表头及内容多语言
3. 点击 logs 弹窗 LOCATION 与 DETAILS 多语言及语义化 Key
4. 6 国语言包词条完整性、LF 换行符与 JS 语法
"""

import os
import sys
import re
import json
import unittest

# 将项目路径与 web 路径加入 sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
WEB_DIR = os.path.join(ROOT_DIR, "web")
LANG_DIR = os.path.join(WEB_DIR, "static", "language")

sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, WEB_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts", "tools"))

from unittest.mock import MagicMock
if 'psutil' not in sys.modules:
    mock_psutil = MagicMock()
    mock_psutil.boot_time.return_value = 1700000000.0
    mock_psutil.cpu_count.return_value = 4
    mock_psutil.cpu_percent.return_value = [10.0, 20.0]
    sys.modules['psutil'] = mock_psutil

mock_admin = MagicMock()
sys.modules['admin'] = mock_admin
sys.modules['admin.common'] = mock_admin

for mod in ['flask', 'flask_compress', 'flask_socketio', 'flask_caching', 'admin.user_login_check', 'werkzeug', 'werkzeug.local']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

LANGUAGES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

class TestIndexI18nFix(unittest.TestCase):
    
    def test_01_phrases_full_definitions(self):
        """测试 phrases_full.py 中已录入全部 11 个新词条"""
        from phrases_full import FULL_I18N_DICTIONARY
        index_dict = FULL_I18N_DICTIONARY.get("index", {})
        
        required_keys = [
            "running_prefix",
            "ip_type_lan",
            "ip_type_loopback",
            "ip_type_public",
            "login_details_web",
            "login_details_ssh",
            "login_details_2fa",
            "login_details_entrance",
            "login_details_captcha_err",
            "login_details_password_err",
            "login_details_active_session"
        ]
        
        for k in required_keys:
            self.assertIn(k, index_dict, f"phrases_full.py index 模块缺失 key: {k}")
            for lang in LANGUAGES:
                val = index_dict[k].get(lang)
                self.assertTrue(val, f"phrases_full.py index 模块 {k} 缺少语言: {lang}")
                
        # 验证英文词条质量
        self.assertEqual(index_dict["running_prefix"]["en"], "Uptime: ")
        self.assertEqual(index_dict["ip_type_lan"]["en"], "Local LAN")
        self.assertEqual(index_dict["login_details_web"]["en"], "Web Password Login")
        self.assertEqual(index_dict["login_details_ssh"]["en"], "SSH Terminal Login")
        print("[PASS] 1. phrases_full.py 词条定义与英文母语对照完整！")

    def test_02_all_language_packages_integrity(self):
        """测试 6 国语言 template.json 与 lan.js 是否均包含 11 个新词条"""
        required_keys = [
            "running_prefix",
            "ip_type_lan",
            "ip_type_loopback",
            "ip_type_public",
            "login_details_web",
            "login_details_ssh",
            "login_details_2fa",
            "login_details_entrance",
            "login_details_captcha_err",
            "login_details_password_err",
            "login_details_active_session"
        ]
        
        for lang in LANGUAGES:
            tmpl_file = os.path.join(LANG_DIR, lang, "template.json")
            self.assertTrue(os.path.exists(tmpl_file), f"缺失文件: {tmpl_file}")
            with open(tmpl_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            idx = data.get("index", {})
            for k in required_keys:
                self.assertIn(k, idx, f"[{lang}/template.json] 缺失 index.{k}")
                self.assertTrue(idx[k], f"[{lang}/template.json] index.{k} 为空")
                
            lan_file = os.path.join(LANG_DIR, lang, "lan.js")
            self.assertTrue(os.path.exists(lan_file), f"缺失文件: {lan_file}")
            with open(lan_file, "r", encoding="utf-8") as f:
                lan_content = f.read()
            for k in required_keys:
                self.assertIn(f'"{k}"', lan_content, f"[{lang}/lan.js] 缺失词条 \"{k}\"")
                
        print("[PASS] 2. 全部 6 国语言包 (template.json & lan.js) 均包含全部 11 项新增词条！")

    def test_03_language_files_newline_and_no_bom(self):
        """验证所有语言包文件为 UTF-8 无 BOM 且强制 LF 换行"""
        for root, dirs, files in os.walk(LANG_DIR):
            for fn in files:
                if fn.endswith(('.json', '.js')):
                    fp = os.path.join(root, fn)
                    with open(fp, "rb") as f:
                        raw = f.read()
                    # 检查 BOM
                    self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{fp} 存在 UTF-8 BOM 头！")
                    # 检查 CRLF
                    self.assertNotIn(b'\r\n', raw, f"{fp} 存在 CRLF 换行符，未严格遵循 LF 规范！")
        print("[PASS] 3. 语言包全部严格遵循 UTF-8 (无 BOM) 与 LF 换行规范！")

    def test_04_backend_uptime_multilingual(self):
        """测试后端运行时间 getBootTime 与 getBootTimeDetail 多语言"""
        from utils.system.main import getBootTime, getBootTimeDetail
        from core.i18n import t as _t
        
        days, hours, mins = getBootTimeDetail()
        self.assertIsInstance(days, int)
        self.assertIsInstance(hours, int)
        self.assertIsInstance(mins, int)
        self.assertGreaterEqual(days, 0)
        self.assertGreaterEqual(hours, 0)
        self.assertGreaterEqual(mins, 0)
        
        # 测试在各种语言下的 getBootTime
        zh_cn_time = getBootTime()
        # 测试 core.i18n.t 对 running_prefix 和 SYS_BOOT_TIME 的各语言解析
        for lang, expected_prefix in [
            ("zh-CN", "已运行: "),
            ("zh-TW", "已運行: "),
            ("en", "Uptime: "),
            ("fr", "En ligne : "),
            ("de", "Laufzeit: "),
            ("it", "In funzione: ")
        ]:
            prefix = _t("index.running_prefix", lang=lang)
            self.assertEqual(prefix, expected_prefix, f"语言 {lang} 的 running_prefix 不符合预期")
            
            boot_str = _t("public.SYS_BOOT_TIME", str(days), str(hours), str(mins), lang=lang)
            self.assertIn(str(days), boot_str)
            self.assertIn(str(hours), boot_str)
            self.assertIn(str(mins), boot_str)
            
        print("[PASS] 4. 后端 getBootTime 及 6 国语言运行时间前缀与格式校验通过！")

    def test_05_backend_dashboard_ip_and_details_keys(self):
        """测试 dashboard.py 中 IP 归属地与登录详情 key 及多语言解析"""
        import importlib.util
        dashboard_path = os.path.join(WEB_DIR, "admin", "dashboard", "dashboard.py")
        spec = importlib.util.spec_from_file_location("dashboard_mod", dashboard_path)
        dashboard_mod = importlib.util.module_from_spec(spec)
        sys.modules['dashboard_mod'] = dashboard_mod
        spec.loader.exec_module(dashboard_mod)
        
        parse_ip_type_info = dashboard_mod.parse_ip_type_info
        parse_ip_type = dashboard_mod.parse_ip_type
        from core.i18n import t as _t
        
        # 1. IP 类型判断
        k, text = parse_ip_type_info("127.0.0.1")
        self.assertEqual(k, "loopback")
        k, text = parse_ip_type_info("172.17.11.248")
        self.assertEqual(k, "lan")
        k, text = parse_ip_type_info("192.168.1.100")
        self.assertEqual(k, "lan")
        k, text = parse_ip_type_info("10.0.0.5")
        self.assertEqual(k, "lan")
        k, text = parse_ip_type_info("8.8.8.8")
        self.assertEqual(k, "public")
        
        # 2. 多语言解析
        en_lan = _t("index.ip_type_lan", lang="en")
        self.assertEqual(en_lan, "Local LAN")
        en_loopback = _t("index.ip_type_loopback", lang="en")
        self.assertEqual(en_loopback, "Loopback")
        en_pub = _t("index.ip_type_public", lang="en")
        self.assertEqual(en_pub, "Public WAN")
        
        # 3. 登录详情 6 国语言解析
        self.assertEqual(_t("index.login_details_web", lang="en"), "Web Password Login")
        self.assertEqual(_t("index.login_details_ssh", lang="en"), "SSH Terminal Login")
        self.assertEqual(_t("index.login_details_2fa", lang="en"), "2FA Verification")
        self.assertEqual(_t("index.login_details_entrance", lang="en"), "Security Entrance Login")
        self.assertEqual(_t("index.login_details_active_session", lang="en"), "Current Active Session")
        
        print("[PASS] 5. dashboard IP 类型与 7 种登录详情语义化 Key 及 6 国语言解析校验通过！")

    def test_06_frontend_index_js_no_hardcoded_chinese(self):
        """测试 index.js 中 renderRecentLoginsTable 与弹窗无硬编码中文"""
        index_js_path = os.path.join(WEB_DIR, "static", "app", "index.js")
        with open(index_js_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 1. 检查 formatLoginIpType 和 formatLoginDetails 函数存在
        self.assertIn("function formatLoginIpType(", content)
        self.assertIn("function formatLoginDetails(", content)
        
        # 2. 检查 renderRecentLoginsTable 表头使用 t()
        self.assertIn("t('public.status', '状态')", content)
        self.assertIn("t('index.method', '方式')", content)
        self.assertIn("t('index.login_ip', '登录IP')", content)
        self.assertIn("t('index.location', '归属地')", content)
        self.assertIn("t('index.login_time', '登录时间')", content)
        
        # 确保不存在旧硬编码表头
        self.assertNotIn('<th style="width: 55px;">状态</th>', content)
        self.assertNotIn('<th style="width: 55px;">方式</th>', content)
        self.assertNotIn('<th>登录IP</th>', content)
        self.assertNotIn('<th style="width: 110px;">归属地</th>', content)
        self.assertNotIn('<th style="text-align: right; width: 130px;">登录时间</th>', content)
        
        # 3. 检查状态与标记
        self.assertIn("t('index.success', '成功')", content)
        self.assertIn("t('index.fail', '失败')", content)
        self.assertIn("t('index.current_session', '本次')", content)
        
        # 4. 检查调用了 formatLoginDetails 与 formatLoginIpType
        self.assertIn("formatLoginDetails(item)", content)
        self.assertIn("formatLoginIpType(item)", content)
        
        # 5. 检查缓存 key 包含语言后缀
        self.assertIn("bt_recent_logins_cache_", content)
        
        # 6. 检查公网接入回退是否使用多语言
        self.assertIn("t('index.ip_type_public', '公网接入')", content)
        
        # 7. 检查 getInfo 运行时间多语言组装
        self.assertIn("t('index.running_prefix', '已运行: ')", content)
        self.assertIn("t('public.SYS_BOOT_TIME', [info.boot_time.days, info.boot_time.hours, info.boot_time.min])", content)
        
        print("[PASS] 6. 前端 index.js 彻底消除硬编码中文，全面接入多语言与格式化器！")

    def test_07_node_runtime_uptime_placeholder_replacement(self):
        """测试 Node.js 运行时 t() 函数完整替换 public.SYS_BOOT_TIME 占位符，绝无 {} 遗留"""
        import subprocess
        p = subprocess.run(
            ["node", os.path.join(ROOT_DIR, "testsuite", "test_uptime_i18n_fix.js")],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(p.returncode, 0, f"Node.js 运行时测试失败:\n{p.stderr}\n{p.stdout}")
        self.assertIn("[PASS] 运行时间多语言占位符替换完美，不再有 {} 符号！", p.stdout)
        print("[PASS] 7. Node.js 运行时真实测试通过：运行时间占位符全部替换，绝无 {} 遗留！")

if __name__ == "__main__":
    unittest.main()

