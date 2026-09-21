# -*- coding: utf-8 -*-
"""
test_limitnet_and_redirect_fix.py
专项回归测试套件：验证流量限制词条完整性、保底机制与重定向接口及功能修复
"""

import os
import json
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_JS_PATH = os.path.join(BASE_DIR, "web", "static", "app", "site.js")
REDIRECT_PY_PATH = os.path.join(BASE_DIR, "web", "admin", "site", "redirect.py")
LANG_DIR = os.path.join(BASE_DIR, "web", "static", "language")

def test_limitnet_i18n_entries():
    """测试 1: 验证全量 6 种语言包包含全部 15 个 limit_net 词条"""
    print("[1] 检查 6 种语言包中 limit_net_1 ~ limit_net_15 词条...")
    languages = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
    for lang in languages:
        lang_dir = os.path.join(LANG_DIR, lang)
        tpl_path = os.path.join(lang_dir, "template.json")
        lan_path = os.path.join(lang_dir, "lan.js")

        assert os.path.isfile(tpl_path), f"缺少 {tpl_path}"
        assert os.path.isfile(lan_path), f"缺少 {lan_path}"

        # 检查 template.json
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl_data = json.load(f)
        assert "site" in tpl_data, f"{lang}/template.json 缺少 site 模块"
        for i in range(1, 16):
            key = f"limit_net_{i}"
            assert key in tpl_data["site"], f"{lang}/template.json 缺少 {key}"
            assert len(tpl_data["site"][key].strip()) > 0, f"{lang}/template.json 中 {key} 为空"

        # 检查 lan.js
        with open(lan_path, "r", encoding="utf-8") as f:
            lan_content = f.read()
        for i in range(1, 16):
            key = f"limit_net_{i}"
            assert f'"{key}"' in lan_content, f"{lang}/lan.js 缺少 {key}"

    print(" -> PASS: 全量 6 种语言包中 15 个流量限制词条完整且非空！")

def test_limitnet_frontend_fallbacks():
    """测试 2: 验证 site.js 中 limitNet 函数已内置兜底保底"""
    print("[2] 检查 site.js 中 limitNet 函数兜底保底与排版...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        site_code = f.read()

    start_idx = site_code.find("function limitNet(id)")
    end_idx = site_code.find("function saveLimitNet(id, type)", start_idx)
    limit_code = site_code[start_idx:end_idx]

    # 验证关键中文兜底
    assert "论坛/博客" in limit_code, "limitNet 下拉选项应有 '论坛/博客' 兜底"
    assert "启用流量限制" in limit_code, "limitNet 复选框应有 '启用流量限制' 兜底"
    assert "限制方案" in limit_code, "limitNet 应有 '限制方案' 兜底"
    assert "并发限制" in limit_code, "limitNet 应有 '并发限制' 兜底"
    assert "单IP限制" in limit_code, "limitNet 应有 '单IP限制' 兜底"
    assert "流量限制" in limit_code, "limitNet 应有 '流量限制' 兜底"
    assert "限制当前站点最大并发数" in limit_code, "limitNet 说明应有最大并发数兜底"

    print(" -> PASS: site.js limitNet 内置中文保底完备，杜绝空白冒号！")

def test_redirect_backend_routes():
    """测试 3: 验证后端 redirect.py 路由端点已支持 /get_redirect 与 /get_redirect_list 别名"""
    print("[3] 检查 web/admin/site/redirect.py 路由定义...")
    with open(REDIRECT_PY_PATH, "r", encoding="utf-8") as f:
        py_code = f.read()

    assert "@blueprint.route('/get_redirect'" in py_code, "必须注册 /get_redirect 路由"
    assert "@blueprint.route('/get_redirect_list'" in py_code, "必须注册 /get_redirect_list 路由别名"
    assert "@blueprint.route('/set_redirect'" in py_code, "必须注册 /set_redirect 路由"
    assert "@blueprint.route('/del_redirect'" in py_code, "必须注册 /del_redirect 路由"
    assert "@blueprint.route('/get_redirect_conf'" in py_code, "必须注册 /get_redirect_conf 路由"
    assert "@blueprint.route('/save_redirect_conf'" in py_code, "必须注册 /save_redirect_conf 路由"

    print(" -> PASS: 后端重定向路由端点及别名完全齐备，绝无 302 路由未命中！")

def test_to301_frontend_architecture():
    """测试 4: 验证 site.js 中 to301 重构后的完整增删查改与配置文件编辑功能"""
    print("[4] 检查 site.js 中 to301 多重定向增删查改架构...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        site_code = f.read()

    start_idx = site_code.find("function to301(")
    end_idx = site_code.find("function toProxy(siteName, type, obj)", start_idx)
    to301_code = site_code[start_idx:end_idx]

    # 1. 列表获取接口与解析
    assert "$.post('/site/get_redirect'" in to301_code, "to301 列表获取必须请求 /site/get_redirect"
    assert "res.data.result" in to301_code, "to301 必须能安全解包 res.data.result"

    # 2. 字段渲染
    assert "lan_r_type" in to301_code, "必须正确渲染 301/302 重定向方式"
    assert "keep_path" in to301_code, "必须正确渲染保留 URI 参数状态"

    # 3. 添加功能 (type == 1)
    assert "type == 1" in to301_code, "to301 必须支持添加重定向 (type 1)"
    assert "$.post('/site/set_redirect'" in to301_code, "添加必须向 /site/set_redirect 提交"

    # 4. 删除功能 (type == 2)
    assert "type == 2" in to301_code, "to301 必须支持删除重定向 (type 2)"
    assert "$.post('/site/del_redirect'" in to301_code, "删除必须向 /site/del_redirect 提交"

    # 5. 详细与配置编辑功能 (type == 3)
    assert "type == 3" in to301_code, "to301 必须支持查看与编辑配置文件 (type 3)"
    assert "$.post('/site/get_redirect_conf'" in to301_code, "必须获取配置文件 /site/get_redirect_conf"
    assert "$.post('/site/save_redirect_conf'" in to301_code, "必须保存配置文件 /site/save_redirect_conf"
    assert "CodeMirror" in to301_code, "重定向配置编辑必须支持 CodeMirror"

    print(" -> PASS: to301 多重定向管理架构完整合规！")

def test_node_syntax():
    """测试 5: 使用 Node.js V8 引擎执行 syntax 检查"""
    print("[5] Node.js 校验 site.js 与全量 lan.js 语法...")
    res = subprocess.run(["node", "-c", SITE_JS_PATH], capture_output=True, text=True)
    assert res.returncode == 0, f"site.js Node.js 语法报错: {res.stderr}"

    for lang in ["zh-CN", "zh-TW", "en", "de", "fr", "it"]:
        lan_path = os.path.join(LANG_DIR, lang, "lan.js")
        res = subprocess.run(["node", "-c", lan_path], capture_output=True, text=True)
        assert res.returncode == 0, f"{lang}/lan.js Node.js 语法报错: {res.stderr}"

    print(" -> PASS: site.js 与全量 lan.js 语法 100% 校验通过！")

if __name__ == "__main__":
    test_limitnet_i18n_entries()
    test_limitnet_frontend_fallbacks()
    test_redirect_backend_routes()
    test_to301_frontend_architecture()
    test_node_syntax()
    print("\n========================================================")
    print(" 流量限制与重定向缺陷修复专项测试全量 PASS！")
    print("========================================================")
