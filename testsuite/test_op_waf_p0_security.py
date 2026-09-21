# coding:utf-8
import sys
import os
import json
import re

# 统一切换至项目根目录
workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace)
sys.path.insert(0, os.path.join(workspace, 'web'))
sys.path.insert(0, os.path.join(workspace, 'plugins', 'op_waf'))

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def test_p0_lua_waf_init():
    print("[TEST 1] 测试 init.lua 中的 P0 安全加固项...")
    lua_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'init.lua')
    with open(lua_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 验证 waf() 入口函数的 Fail-Open 设计
    assert 'local function waf()' in content or 'function waf()' in content, "未找到 waf 入口函数"
    assert 'waf_run_status' not in content, "waf_run_status 全局变量未彻底废除"
    assert 'pcall(run_app_waf)' in content, "waf() 未使用 pcall 全面保护 run_app_waf"

    # 2. 验证 min_route 鉴权加固
    assert 'local remote_ip = ngx.var.remote_addr' in content, "min_route 未提取 remote_addr"
    assert "remote_ip ~= '127.0.0.1' and remote_ip ~= '::1'" in content, "min_route 未基于物理底层连接 IP 校验"

    # 3. 验证 waf_cc 的 Token 重构
    assert 'secret .. "_" .. ip .. "_" .. request_uri' not in content, "waf_cc 中仍然存在高熵随机 Token 漏洞"
    assert 'cc_s:' in content and 'cc_i:' in content, "waf_cc 未应用分级聚合的 Token 算法"
    print("✓ init.lua P0 安全规则校验全部通过!")

def test_p0_get_safe_logs_path_traversal():
    print("[TEST 2] 测试 index.py 中 getSafeLogs 的路径遍历防御与句柄安全...")
    import index
    
    # 模拟恶意路径穿越参数
    bad_cases = [
        {'siteName': '../../../etc/passwd', 'toDate': '2026-09-20', 'p': '1'},
        {'siteName': 'default..', 'toDate': '2026-09-20', 'p': '1'},
        {'siteName': 'test/attack', 'toDate': '2026-09-20', 'p': '1'},
        {'siteName': 'test\\attack', 'toDate': '2026-09-20', 'p': '1'},
        {'siteName': 'test', 'toDate': '2026/09/20', 'p': '1'},
        {'siteName': 'test', 'toDate': '../../2026', 'p': '1'},
    ]

    for case in bad_cases:
        sys.argv = ['index.py', 'get_safe_logs', json.dumps(case)]
        res_raw = index.getSafeLogs()
        res = json.loads(res_raw)
        assert res['status'] == False, f"未拦截恶意参数: {case}"
        assert '非法' in res['msg'] or '错误' in res['msg'], f"错误提示信息不符合预期: {res['msg']}"

    print("✓ 路径穿越恶意注入测试全部被安全拦截!")

    # 模拟合法不存在的文件
    normal_case = {'siteName': 'mysite_com', 'toDate': '2026-09-20', 'p': '1'}
    sys.argv = ['index.py', 'get_safe_logs', json.dumps(normal_case)]
    res = json.loads(index.getSafeLogs())
    assert res['status'] == False and res['msg'] == '文件不存在!', f"正常缺失文件返回异常: {res}"
    print("✓ getSafeLogs 正常与异常逻辑校验全部通过!")

if __name__ == '__main__':
    test_p0_lua_waf_init()
    test_p0_get_safe_logs_path_traversal()
    print("\n===============================")
    print("🎉 阶段一 (P0) 核心安全测试全部通过!")
    print("===============================")
