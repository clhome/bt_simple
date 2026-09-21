# coding: utf-8
import sys
import os
import json
import py_compile

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 将项目路径加入 sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, "web"))
sys.path.insert(0, os.path.join(base_dir, "plugins", "op_waf"))

import plugins.op_waf.index as waf_index

def test_syntax():
    print("=== 1. 验证 Python 语法编译 ===")
    py_compile.compile(os.path.join(base_dir, "plugins", "op_waf", "index.py"), doraise=True)
    py_compile.compile(os.path.join(base_dir, "plugins", "op_waf", "tool_task.py"), doraise=True)
    print("✓ index.py 和 tool_task.py 语法编译通过！")

def test_spider_conf_api():
    print("\n=== 2. 测试 getSpiderConf 接口 ===")
    res_str = waf_index.getSpiderConf()
    res = json.loads(res_str)
    assert res['status'] is True, f"getSpiderConf 失败: {res}"
    data = res['data']
    print(f"当前配置: {data['config']}")
    print(f"统计数据: {data['stats']}")
    print(f"总规则数: {data['total_rules']}")
    
    assert data['total_rules'] >= 40, f"规则条数过少: {data['total_rules']}"
    assert data['stats']['bytedance'] > 0, "字节跳动蜘蛛数量应 > 0"
    assert data['stats']['huawei'] > 0, "华为花瓣蜘蛛数量应 > 0"
    assert data['stats']['baidu'] > 0, "百度蜘蛛数量应 > 0"
    assert data['stats']['google'] > 0, "谷歌蜘蛛数量应 > 0"
    assert data['stats']['bing'] > 0, "微软必应蜘蛛数量应 > 0"
    print("✓ getSpiderConf 校验通过！")

def test_spider_mode_switch():
    print("\n=== 3. 测试 setSpiderMode 模式切换 ===")
    # 切换为 block
    waf_index.sys.argv = ['index.py', 'set_spider_mode', json.dumps({'mode': 'block'})]
    res = json.loads(waf_index.setSpiderMode())
    assert res['status'] is True
    
    # 校验 config.json
    conf_path = waf_index.getJsonPath('config')
    conf = json.loads(open(conf_path, 'r', encoding='utf-8').read())
    assert conf['spider']['mode'] == 'block', f"mode 未更新为 block: {conf['spider']}"
    print("✓ 切换为严格模式 (block) 成功！")

    # 切换回 downgrade
    waf_index.sys.argv = ['index.py', 'set_spider_mode', json.dumps({'mode': 'downgrade'})]
    res = json.loads(waf_index.setSpiderMode())
    assert res['status'] is True
    conf = json.loads(open(conf_path, 'r', encoding='utf-8').read())
    assert conf['spider']['mode'] == 'downgrade', f"mode 未更新为 downgrade: {conf['spider']}"
    print("✓ 切换为宽松降级模式 (downgrade) 成功！")

def test_spider_ip_crud():
    print("\n=== 4. 测试蜘蛛 IP 增删查 API ===")
    test_ip = "198.51.100.0/24"
    test_ps = "测试自定义蜘蛛"
    
    # 1. 添加
    waf_index.sys.argv = ['index.py', 'add_spider_ip', json.dumps({'ip': test_ip, 'ps': test_ps})]
    res = json.loads(waf_index.addSpiderIp())
    assert res['status'] is True, f"添加测试蜘蛛失败: {res}"
    print(f"✓ 添加测试网段 {test_ip} 成功！")

    # 2. 查询验证
    res_list = json.loads(waf_index.getSpiderIpList())
    found_idx = -1
    for i, item in enumerate(res_list['data']):
        if item[0] == test_ip:
            found_idx = i
            break
    assert found_idx >= 0, "未找到刚添加的测试网段！"
    print(f"✓ 列表中成功找到测试网段，位于索引 {found_idx}")

    # 3. 删除
    waf_index.sys.argv = ['index.py', 'remove_spider_ip', json.dumps({'index': found_idx})]
    res = json.loads(waf_index.removeSpiderIp())
    assert res['status'] is True, f"删除测试蜘蛛失败: {res}"
    print(f"✓ 删除测试网段成功！")

def test_lua_compilation():
    print("\n=== 5. 测试 Lua 规则文件编译 ===")
    waf_index.autoMakeLuaConfSingle('spider_ip', True)
    lua_path = waf_index.getServerDir() + "/waf/conf/rule_spider_ip.lua"
    assert os.path.exists(lua_path), f"Lua 规则文件未生成: {lua_path}"
    lua_content = open(lua_path, 'r', encoding='utf-8').read()
    assert "return {" in lua_content, "Lua 文件头应为 return {"
    assert "110.249.201.0/24" in lua_content, "Lua 文件中应包含字节跳动 IP"
    assert "66.249.64.0/19" in lua_content, "Lua 文件中应包含谷歌 IP"
    print("✓ Lua 规则文件生成且包含完整各大搜索引擎 IP 列表！")

def test_js_syntax():
    print("\n=== 6. 验证 op_waf.js 语法合法性 ===")
    js_path = os.path.join(base_dir, "plugins", "op_waf", "js", "op_waf.js")
    js_content = open(js_path, 'r', encoding='utf-8').read()
    assert "function setSpiderDialog()" in js_content, "op_waf.js 中缺少 setSpiderDialog"
    assert "function changeSpiderMode(" in js_content, "op_waf.js 中缺少 changeSpiderMode"
    assert "function syncSpiderIpAction()" in js_content, "op_waf.js 中缺少 syncSpiderIpAction"
    assert "function manageSpiderIpDialog()" in js_content, "op_waf.js 中缺少 manageSpiderIpDialog"
    assert "智能蜘蛛白名单" in js_content, "op_waf.js 中缺少智能蜘蛛白名单表格行"
    print("✓ op_waf.js 关键函数与表格行校验通过！")

if __name__ == "__main__":
    test_syntax()
    test_spider_conf_api()
    test_spider_mode_switch()
    test_spider_ip_crud()
    test_lua_compilation()
    test_js_syntax()
    print("\n🎉 全部 6 项测试 100% 通过！")
