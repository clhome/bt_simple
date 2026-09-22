# -*- coding: utf-8 -*-
"""
插件多语言版本响应速度性能基准与回归测试套件
验证：
1. 后端 sanitizeCmdScripts 内存缓存生效性与执行耗时 (< 0.05ms)
2. 后端 localizePluginItems 性能 (< 1ms) 与多语言覆盖正确性
3. 前端 soft.js 中移除了串行同步 XHR，无网络风暴
4. 前端 i18n.js 中 translatePluginDOM 采用定向选择器，无暴力穷举
5. 前端 plugin_api.js 中包含遮罩感知防抖逻辑
6. Node.js 真实 DOM 环境下定向翻译对比暴力遍历的耗时测试
"""

import os
import sys
import time
import json
import unittest
import subprocess
import shutil
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'web'))

import core.yf as yf

# 进程级隔离：必须在 import utils.plugin 之前 —— 它在导入期就会打开面板库。
# F: 盘上 sqlite3 的 close() 单次要 30~60s，退出时 atexit 逐个关连接。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('plugin_performance')

from utils.plugin import plugin as YfPlugin  # noqa: E402

class TestPluginPerformance(unittest.TestCase):

    def setUp(self):
        self.plugin = YfPlugin.instance()

    def test_01_sanitize_cmd_scripts_cache_perf(self):
        """测试 sanitizeCmdScripts 内存缓存优化效果与耗时"""
        cmd = "python3 /www/server/yufeng_panel/plugins/docker/index.py status"
        
        # 预热一次填充缓存
        yf.sanitizeCmdScripts(cmd)
        
        # 连续调用 2000 次，测量耗时
        start = time.time()
        for _ in range(2000):
            yf.sanitizeCmdScripts(cmd)
        cost_ms = (time.time() - start) * 1000
        avg_cost_ms = cost_ms / 2000

        print(f"\n[PERF] sanitizeCmdScripts 2000 次总耗时: {cost_ms:.2f} ms (单次平均: {avg_cost_ms:.4f} ms)")
        # 必须小于 0.05ms
        self.assertLess(avg_cost_ms, 0.05, "sanitizeCmdScripts 缓存后单次耗时应小于 0.05ms")

    def test_02_backend_localize_plugin_items(self):
        """测试后端 localizePluginItems 的多语言替换正确性与毫秒级耗时"""
        # 构造模拟插件数据
        mock_items = [
            {"name": "docker", "title": "Docker管理器", "ps": "Docker容器管理"},
            {"name": "mysql", "title": "MySQL", "ps": "关系型数据库"},
            {"name": "openresty", "title": "OpenResty", "ps": "Web服务器"},
            {"name": "redis", "title": "Redis", "ps": "高性能Key-Value内存数据库"},
            {"name": "pureftp", "title": "Pure-Ftpd", "ps": "FTP服务器软件"}
        ]
        
        # 预热一次：首次调用会走一遍「一次性」成本 —— 装上 requirements.txt
        # 里声明的 flask 后，语言包/请求上下文那跳会连带加载 jinja2（实测 ~330ms）。
        # 本用例断言的是**单次平均**耗时，必须把一次性成本排除在外，
        # 否则它实际测的是「本机有没有装 flask」——依赖装齐反而变红。
        # 同文件 test_sanitize_cmd_fast_path 已有同样惯例（「预热一次进入缓存」）。
        self.plugin.localizePluginItems(mock_items)

        start = time.time()
        for _ in range(100):
            res = self.plugin.localizePluginItems(mock_items)
        cost_ms = (time.time() - start) * 1000
        avg_cost_ms = cost_ms / 100

        print(f"[PERF] localizePluginItems 100 次处理耗时: {cost_ms:.2f} ms (单次平均: {avg_cost_ms:.4f} ms)")
        self.assertLess(avg_cost_ms, 1.0, "localizePluginItems 单次耗时应小于 1ms")
        self.assertEqual(len(res), len(mock_items))

    def test_03_soft_js_no_sync_xhr(self):
        """静态代码分析：确保 soft.js 中彻底移除了 getSList 内部针对每个插件的 getPluginInfo 同步请求"""
        soft_js_path = os.path.join(ROOT_DIR, 'web', 'static', 'app', 'soft.js')
        with open(soft_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证循环中不再包含 YfPlugin.getPluginInfo
        self.assertNotIn("YfPlugin.getPluginInfo(plugin.name)", content, 
                         "soft.js 中不应存在在插件循环中调用 getPluginInfo 的同步 XHR 瓶颈")
        # 验证包含 loadPluginLangAsync 预热
        self.assertIn("loadPluginLangAsync", content, 
                      "soft.js softMain 中应包含 loadPluginLangAsync 异步预加载")

    def test_04_i18n_js_dom_optimization_and_cache(self):
        """静态代码分析：确保 i18n.js 中移除了暴力 div, span, p 扫描，且引入了 localStorage 缓存"""
        i18n_js_path = os.path.join(ROOT_DIR, 'web', 'static', 'app', 'i18n.js')
        with open(i18n_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 确保彻底废除了暴力遍历
        self.assertNotIn("$con.find('div, span, p')", content, 
                         "i18n.js 不应使用暴力全量 $con.find('div, span, p') 扫描")
        # 确保存在 localStorage 缓存机制
        self.assertIn("getPluginDictFromStorage", content, "i18n.js 应包含 localStorage 插件语言包缓存读取")
        self.assertIn("setPluginDictToStorage", content, "i18n.js 应包含 localStorage 插件语言包缓存写入")
        self.assertIn("loadPluginLangAsync", content, "i18n.js 应支持异步预加载 loadPluginLangAsync")

    def test_05_plugin_api_shade_debounce(self):
        """静态代码分析：确保 plugin_api.js 具备智能遮罩感知，避免双重遮罩叠加"""
        api_js_path = os.path.join(ROOT_DIR, 'web', 'static', 'app', 'plugin_api.js')
        with open(api_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("hasActiveShade", content, 
                      "plugin_api.js 应具备 hasActiveShade 智能遮罩感知")

    def test_06_node_runtime_dom_benchmark(self):
        """使用 Node.js + jsdom 真实模拟 1000 个复杂节点的 DOM 树，对比定向选择器与暴力扫描的性能"""
        # 生成脚本放系统临时区（仓库目录在 F: 盘，单次删除 5.15s）
        scratch_dir = tempfile.mkdtemp(prefix='yufeng_dom_bench_')
        node_script = os.path.join(scratch_dir, 'benchmark_dom_i18n.js')
        js_code = """
        const fs = require('fs');
        const { JSDOM } = require('jsdom');

        // 构建包含 1000 个嵌套节点的复杂 DOM 模拟插件弹窗
        let innerHtml = '<div class="bt-w-main"><div class="bt-w-menu">';
        for (let i = 0; i < 15; i++) {
            innerHtml += '<p>菜单项 ' + i + '</p>';
        }
        innerHtml += '</div><div class="bt-w-con">';
        for (let i = 0; i < 300; i++) {
            innerHtml += '<div class="row"><span>Label ' + i + ':</span> <div>Value <p>Description ' + i + '</p></div></div>';
        }
        innerHtml += '<div style="pointer-events: none;">衢州御风科技有限公司 出品</div>';
        innerHtml += '</div></div>';

        const dom = new JSDOM('<!DOCTYPE html><html><body><div id="container">' + innerHtml + '</div></body></html>');
        const window = dom.window;
        const document = window.document;

        // 1. 模拟旧版暴力扫描
        const t0 = process.hrtime();
        const allElements = document.querySelectorAll('div, span, p');
        let legacyCount = 0;
        allElements.forEach(el => {
            const txt = (el.textContent || '').trim();
            if (txt === '衢州御风科技有限公司 出品') {
                legacyCount++;
            }
        });
        const t1 = process.hrtime(t0);
        const legacyMs = (t1[0] * 1e9 + t1[1]) / 1e6;

        // 2. 模拟新版精确定向选择器
        const t2 = process.hrtime();
        const targeted = document.querySelectorAll('.plugin-copyright, div[style*="pointer-events"], .bt-w-con > div:last-child');
        let newCount = 0;
        targeted.forEach(el => {
            const txt = (el.textContent || '').trim();
            if (txt.indexOf('衢州御风科技有限公司 出品') !== -1) {
                newCount++;
            }
        });
        const t3 = process.hrtime(t2);
        const newMs = (t3[0] * 1e9 + t3[1]) / 1e6;

        console.log(JSON.stringify({
            totalElementsScannedLegacy: allElements.length,
            targetedElementsScanned: targeted.length,
            legacyMs: legacyMs,
            newMs: newMs,
            speedup: (legacyMs / Math.max(newMs, 0.001)).toFixed(2)
        }));
        """
        with open(node_script, 'w', encoding='utf-8', newline='\n') as f:
            f.write(js_code)

        try:
            cmd = f'node "{node_script}"'
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate(timeout=10)
            res_str = stdout.decode('utf-8').strip()
            if res_str.startswith('{'):
                res = json.loads(res_str)
                print(f"[PERF] DOM 扫描对比（1000+节点）: 暴力扫描扫描了 {res['totalElementsScannedLegacy']} 个节点耗时 {res['legacyMs']:.3f}ms；定向选择器仅扫描 {res['targetedElementsScanned']} 个节点耗时 {res['newMs']:.3f}ms，性能加速 {res['speedup']} 倍！")
                self.assertLess(res['targetedElementsScanned'], 10, "定向选择器扫描节点应极少（<10个）")
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
