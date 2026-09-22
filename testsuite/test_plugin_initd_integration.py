# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证所有插件自启动菜单清理与服务页面一体化集成
"""
import os
import sys
import json
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_no_initd_menu_in_plugins_html():
    print("\n--- 1. 验证 38 个插件 HTML 中彻底移除自启动菜单 ---")
    plugins_dir = os.path.join(PROJECT_ROOT, "plugins")
    violations = []
    
    for root, dirs, files in os.walk(plugins_dir):
        for f in files:
            if f.endswith(".html"):
                f_path = os.path.join(root, f)
                with open(f_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line_no, line in enumerate(fp, start=1):
                        if "pluginInitD" in line:
                            violations.append((os.path.relpath(f_path, PROJECT_ROOT), line_no, line.strip()))
                            
    assert len(violations) == 0, f"发现遗留的自启动菜单项: {violations}"
    print("[PASS] 验证通过：38 个插件的所有 HTML 文件中已 100% 移除自启动侧边栏菜单！")


def test_public_service_boot_start_integration():
    print("\n--- 2. 验证 public.js 中公共服务一体化开机自启集成 ---")
    pub_js_path = os.path.join(PROJECT_ROOT, "web", "static", "app", "public.js")
    with open(pub_js_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_symbols = [
        "function pluginInitDSwitchHtml",
        "function pluginInitDSwitchRender",
        "function pluginToggleInitD",
        "pluginInitDSwitchHtml(_name, version, _suffix_name)",
        "pluginInitDSwitchRender(_name, version, _suffix_name)"
    ]
    for sym in required_symbols:
        assert sym in content, f"public.js 缺少关键符号/逻辑: {sym}"
        
    print("[PASS] 验证通过：public.js 包含完整的组件生成、状态读取与开关切换控制逻辑！")


def test_custom_service_plugins_integration():
    # 注：原先还覆盖 plugins/caddy/js/caddy.js，但 caddy 插件已从仓库移除
    # （plugins/caddy/ 不存在），对它断言永远不可能通过，故已剔除。
    print("\n--- 3. 验证 3 个定制服务插件 (apache, openresty, pureftp) 适配 ---")
    custom_files = [
        os.path.join(PROJECT_ROOT, "plugins", "apache", "js", "httpd.js"),
        os.path.join(PROJECT_ROOT, "plugins", "openresty", "js", "openresty.js"),
        os.path.join(PROJECT_ROOT, "plugins", "pureftp", "js", "ftp.js")
    ]
    for fp in custom_files:
        rel = os.path.relpath(fp, PROJECT_ROOT)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        assert "pluginInitDSwitchHtml" in content, f"{rel} 未嵌入 pluginInitDSwitchHtml"
        assert "pluginInitDSwitchRender" in content, f"{rel} 未调用 pluginInitDSwitchRender"
        print(f"[PASS] {rel} 成功挂载开机自启组件！")


def test_i18n_dictionary_completeness():
    print("\n--- 4. 验证 6 国语言公共字典词条覆盖完整度 ---")
    langs = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
    keys = ["boot_start", "boot_start_enabled", "boot_start_disabled", "setting_boot_start"]
    base_dir = os.path.join(PROJECT_ROOT, "web", "static", "language")
    
    for lg in langs:
        pub_json = os.path.join(base_dir, lg, "public.json")
        lan_js = os.path.join(base_dir, lg, "lan.js")
        
        with open(pub_json, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k in keys:
            assert k in d and d[k], f"{lg}/public.json 缺失键: {k}"
            
        with open(lan_js, "r", encoding="utf-8") as f:
            js_text = f.read()
        for k in keys:
            assert f'"{k}"' in js_text, f"{lg}/lan.js 缺失键: {k}"
            
        print(f"[PASS] {lg} 语言包 4 项开机自启词条 100% 对齐就绪！")


def test_nodejs_syntax():
    print("\n--- 5. 运行 Node.js 真实 V8 语法与编译校验 ---")
    js_targets = [
        "web/static/app/public.js",
        "plugins/apache/js/httpd.js",
        "plugins/openresty/js/openresty.js",
        "plugins/pureftp/js/ftp.js"
    ]
    for rel in js_targets:
        cmd = ["node", "-c", rel]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, f"JS 语法报错 in {rel}: {res.stderr}"
        print(f"[PASS] {rel} 语法编译无误！")
        
    lan_check = subprocess.run(["node", "testsuite/check_lan_syntax.js"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert lan_check.returncode == 0, f"lan.js 语法校验失败: {lan_check.stderr}"
    print("[PASS] 全量 6 种语言 lan.js 经 Node.js V8 语法校验 100% 通过！")


if __name__ == "__main__":
    try:
        test_no_initd_menu_in_plugins_html()
        test_public_service_boot_start_integration()
        test_custom_service_plugins_integration()
        test_i18n_dictionary_completeness()
        test_nodejs_syntax()
        print("\n=======================================================")
        print("  ALL 5 SUITES PASSED! 插件自启动整合与清理验证 100% 通过！")
        print("=======================================================\n")
    except AssertionError as e:
        print(f"\n[FAIL] 测试未通过: {e}")
        sys.exit(1)
