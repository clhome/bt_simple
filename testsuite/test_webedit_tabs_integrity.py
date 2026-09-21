# -*- coding: utf-8 -*-
"""
test_webedit_tabs_integrity.py
专项回归测试套件：验证网站修改弹窗（webEdit）各功能 Tab 的数据解包、空值保底、HTML 闭合与 JS 语法完整性
"""

import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_JS_PATH = os.path.join(BASE_DIR, "web", "static", "app", "site.js")

def test_dir_binding_integrity():
    """测试 1: 验证 dirBinding 的数据解包与 delDirBind 函数调用"""
    print("[1] 检查 site.js 中 dirBinding 函数的数据解包与安全保底...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find("function dirBinding(id)")
    end_idx = content.find("function setDirRewrite(id)", start_idx)
    code = content[start_idx:end_idx]

    # 1. 验证安全解包 data.data
    assert "data.data" in code, "dirBinding 必须解包 data.data"
    assert "rdata.dirs.length" not in code, "dirBinding 不得直接访问未解包的 rdata.dirs.length"

    # 2. 验证 dirs 和 binding 具有空数组保底
    assert "Array.isArray(rdata.dirs)" in code or "rdata.dirs || []" in code, "dirs 必须具有空数组保底"
    assert "Array.isArray(rdata.binding)" in code or "rdata.binding || []" in code, "binding 必须具有空数组保底"

    # 3. 验证删除绑定函数名准确为 delDirBind
    assert "delDirBind(" in code, "删除子目录绑定应调用 delDirBind"
    assert "delDirBinding(" not in code, "不应调用未定义的 delDirBinding"

    print(" -> PASS: dirBinding 数据解包规范、删除函数名修正完全合规！")

def test_php_version_integrity():
    """测试 2: 验证 phpVersion 与 setPHPVersion 的 HTML 结构与无残损文本"""
    print("[2] 检查 site.js 中 phpVersion 与 setPHPVersion 的 HTML 结构与提示文字...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find("function phpVersion(siteName)")
    end_idx = content.find("function changePHPVersion(id, siteName, currentVersion)", start_idx)
    code = content[start_idx:end_idx]

    # 1. 验证包含完整的 select id='phpVersion'
    assert "<select id='phpVersion'" in code, "phpVersion 必须包含完整的 select id='phpVersion'"
    assert "修改域名【" not in code, "phpVersion 不得包含遗留的 '修改域名【' 错乱文字"

    # 2. 验证 setPHPVersion 中的 layer.msg 不含 HTML 残片
    assert "</select>" not in code.split("function setPHPVersion")[1].split("$.post('/site/set_php_version'")[0], "setPHPVersion 的 layer.msg 不得包含 </select> 残片"
    assert "正在保存" in code or "site.saving" in code, "setPHPVersion 应包含规范的保存中提示"

    # 3. 验证无确定按钮闭合乱码残片
    assert "确定</button>" not in code, "代码中不得包含 '确定</button>' 乱码残片"

    print(" -> PASS: phpVersion 与 setPHPVersion 结构纯正规范！")

def test_config_file_integrity():
    """测试 3: 验证 configFile 闭合 textarea 与保存按钮 SaveConfigFileBtn"""
    print("[3] 检查 site.js 中 configFile 函数的闭合标签与保存按钮...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find("function configFile(webSite)")
    end_idx = content.find("function saveConfigFile(webSite, encoding, path)", start_idx)
    code = content[start_idx:end_idx]

    # 1. 验证 textarea 正常闭合
    assert "</textarea>" in code, "configFile 中的 textarea 必须闭合"
    assert "wmcms_perfect_cms" not in code, "configFile 不得包含无效的 wmcms_perfect_cms 占位"

    # 2. 验证包含保存按钮与说明文字
    assert "SaveConfigFileBtn" in code, "configFile 必须包含 SaveConfigFileBtn 保存按钮"
    assert "here_is_the_main_configuration" in code or "此处为站点主配置文件" in code, "configFile 必须包含说明列表"

    # 3. 验证安全传递 encoding
    assert "saveConfigFile(webSite, encoding, info['host']);" in code, "configFile 必须安全传递 encoding"

    print(" -> PASS: configFile 闭合标签与保存按钮完全就绪！")

def test_tabs_null_safety_defenses():
    """测试 4: 验证各 Tab 函数（webPathEdit, to301, toProxy, rewrite, domainEdit）的空值防御"""
    print("[4] 检查 site.js 中关键 Tab 函数的空值保底防御机制...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # webPathEdit
    p_start = content.find("function webPathEdit(id)")
    p_end = content.find("function setSitePath(id)", p_start)
    p_code = content[p_start:p_end]
    assert "Array.isArray(run_path_info.dirs)" in p_code, "webPathEdit 必须对 run_path_info.dirs 增加 Array.isArray 防御"

    # to301
    t3_start = content.find("function to301(siteName, type, data)")
    t3_end = content.find("function toRedirect(siteName, redirect_id, type)", t3_start)
    t3_code = content[t3_start:t3_end]
    assert "Array.isArray(list)" in t3_code, "to301 必须对列表增加 Array.isArray 防御"

    # toProxy
    tp_start = content.find("function toProxy(siteName, type, obj)")
    tp_end = content.find("function setProxyStatus(siteName, id, status)", tp_start)
    tp_code = content[tp_start:tp_end]
    assert "Array.isArray(data)" in tp_code, "toProxy 必须对返回的 proxy list 增加 Array.isArray 防御"

    # rewrite
    rw_start = content.find("function rewrite(website)")
    rw_end = content.find("function setRewrite(filename, data)", rw_start)
    rw_code = content[rw_start:rw_end]
    assert "get_rewrite_conf" in rw_code, "rewrite 必须调用 /site/get_rewrite_conf 获取动态配置路径"
    assert "get_rewrite_list" in rw_code, "rewrite 必须调用 /site/get_rewrite_list 获取模板列表"
    assert "typeof fileBody.data.data === 'string'" in rw_code, "rewrite 必须对读取的文件内容进行字符串类型保底"
    assert "setRewriteTel()" in rw_code, "rewrite 必须正确绑定 setRewriteTel 模板保存函数"

    # domainEdit
    dm_start = content.find("function domainEdit(id, name, msg, status)")
    dm_end = content.find("function domainAdd(id, webname, type)", dm_start)
    dm_code = content[dm_start:dm_end]
    assert "Array.isArray(domain)" in dm_code, "domainEdit 必须对 domain 列表增加 Array.isArray 防御"

    print(" -> PASS: 各 Tab 列表遍历均已注入空安全防护，杜绝 reading 'length' 异常！")

def test_node_js_site_syntax():
    """测试 5: 使用 Node.js 检验 site.js 全文语法无任何错误"""
    print("[5] 运行 Node.js 严格校验 site.js 整体语法正确性...")
    node_check = """
    const fs = require('fs');
    const path = require('path');
    const vm = require('vm');

    const filePath = path.join(process.cwd(), 'web', 'static', 'app', 'site.js');
    const code = fs.readFileSync(filePath, 'utf8');

    // 编译检查语法
    try {
        new vm.Script(code, { filename: 'site.js' });
        console.log('SITE_JS_SYNTAX_VALID');
    } catch (e) {
        console.error('SyntaxError in site.js:', e.message);
        process.exit(1);
    }
    """
    res = subprocess.run(["node", "-e", node_check], cwd=BASE_DIR, capture_output=True, text=True)
    assert res.returncode == 0, f"site.js 语法校验失败:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SITE_JS_SYNTAX_VALID" in res.stdout
    print(" -> PASS: Node.js V8 引擎解析 site.js 全量语法 100% 正确！")

if __name__ == "__main__":
    test_dir_binding_integrity()
    test_php_version_integrity()
    test_config_file_integrity()
    test_tabs_null_safety_defenses()
    test_node_js_site_syntax()
    print("\n========================================================")
    print(" 网站修改各功能 Tab 数据解包、空安全与语法专项测试全量 PASS！")
    print("========================================================")
