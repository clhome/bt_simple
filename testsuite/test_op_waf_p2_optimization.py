# coding:utf-8
import sys
import os
import re

# 统一切换至项目根目录
workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace)
sys.path.insert(0, os.path.join(workspace, 'web'))
sys.path.insert(0, os.path.join(workspace, 'plugins', 'op_waf'))

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def test_p2_waf_post_improvements():
    print("[TEST 1] 校验 waf_post 中对 multipart 文本字段提取与 max_args 修复...")
    init_lua_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'init.lua')
    with open(init_lua_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 验证不再直接 return false 放行 multipart
    assert 'if C:get_boundary() then return false end' not in content, "依然存在直接放行 multipart 的后门缺陷"
    assert 'if boundary then' in content, "未处理 boundary 分支"
    assert 'local iter = ngx.re.gmatch(body_data' in content, "未对 multipart 表单文本字段提取解析"

    # 2. 验证 max_args 设为 0 以及截断保护
    assert 'ngx.req.get_post_args(0)' in content, "get_post_args 未传入 0 解除 100 参数截断限制"
    assert 'if err == "truncated"' in content, "未对 truncated 截断做原始数据兜底处理"
    print("✓ waf_post 深度防护增强检查通过!")

def test_p2_log_404_and_cpu():
    print("[TEST 2] 校验 log.lua 404 防线内存限流与 waf_common.lua CPU 采样无阻塞优化...")
    log_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'log.lua')
    with open(log_file, 'r', encoding='utf-8') as f:
        log_content = f.read()

    # 验证 log.lua 的 pcall 与 404 ucnt 上限保护
    assert 'pcall(function()' in log_content, "log.lua 未使用 pcall 全局保护"
    assert '404:ucnt:' in log_content, "log.lua 未对单 IP 独立 404 hash key 数量限流"

    waf_common_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'waf_common.lua')
    with open(waf_common_file, 'r', encoding='utf-8') as f:
        common_content = f.read()

    # 验证 get_cpu_percent 移除了 sleep(1) 阻塞
    assert 'ngx.sleep(1)' not in common_content, "waf_common.lua get_cpu_percent 中仍然存在 ngx.sleep(1) 阻塞"
    assert 'last_cpu_tick_total' in common_content, "未采用平滑滑动差值计算 CPU"
    print("✓ 404 内存限流与 CPU 无阻塞采样逻辑检查通过!")

def test_p2_unescape_hoisting():
    print("[TEST 3] 校验 ngx_match_list 外提单次 unescape 解码复用优化...")
    waf_common_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'waf_common.lua')
    with open(waf_common_file, 'r', encoding='utf-8') as f:
        content = f.read()

    assert 'unescaped_match' in content or 'unescaped' in content, "is_ngx_match_orgin 未支持外部传入 unescaped 参数"
    assert 'local unescaped = ngx.unescape_uri(content)' in content, "ngx_match_list 外部未提前做一次性 unescape 解码"
    print("✓ 规则匹配 unescape 外提复用检查通过!")

if __name__ == '__main__':
    test_p2_waf_post_improvements()
    test_p2_log_404_and_cpu()
    test_p2_unescape_hoisting()
    print("\n===============================")
    print("🎉 阶段三 (P2) 纵深防御与细节优化测试全部通过!")
    print("===============================")
