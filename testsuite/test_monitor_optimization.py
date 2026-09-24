# -*- coding: utf-8 -*-
"""
系统监控页面性能优化与多国语言适配自动化回归测试套件
验证项目：
1. monitor.html 模板 Jinja2 语法编译与渲染，验证 4 卡片容器、顶部统一控制栏与底部全局时间滑块
2. control.js 源码语法与请求单态性（验证 get_cpu_io 仅请求 1 次，杜绝重复冗余）
3. 底部全局时间滑块联动机制（renderGlobalTimeline, bindInsideZoomSync 与 dispatchAction）
4. 6 国语言词典（zh-CN, zh-TW, en, fr, de, it）100% 对齐与 0 中文残留
5. 文件编码为 UTF-8 无 BOM，换行符强制 LF
"""

import unittest
import os
import re
import json
import jinja2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = [
    os.path.join(ROOT_DIR, "web", "templates", "default"),
    os.path.join(ROOT_DIR, "web", "templates")
]
STATIC_DIR = os.path.join(ROOT_DIR, "web", "static")
LANG_DIR = os.path.join(STATIC_DIR, "language")
ALL_LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
FOREIGN_LANGS = ["en", "fr", "de", "it"]
ZH_REGEX = re.compile(r'[\u4e00-\u9fa5]')

class TestMonitorOptimization(unittest.TestCase):

    def test_file_formats(self):
        """测试修改文件的换行符为 LF，编码为 UTF-8 无 BOM"""
        target_files = [
            os.path.join(ROOT_DIR, "web", "templates", "default", "monitor.html"),
            os.path.join(STATIC_DIR, "app", "control.js")
        ]
        for lang in ALL_LANGS:
            target_files.append(os.path.join(LANG_DIR, lang, "template.json"))
            target_files.append(os.path.join(LANG_DIR, lang, "lan.js"))

        for fp in target_files:
            self.assertTrue(os.path.isfile(fp), f"文件不存在: {fp}")
            with open(fp, "rb") as f:
                content = f.read()
                self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM 头: {fp}")
                self.assertNotIn(b'\r\n', content, f"文件包含 CRLF 换行符: {fp}")

    def test_monitor_html_template_syntax(self):
        """测试 monitor.html 模板通过 Jinja2 正确编译与渲染"""
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES_DIR))
        def mock_t(key, default_text=""):
            return default_text or key

        class MockG:
            is_pjax = False
            lang = 'zh-CN'

        env.globals['t'] = mock_t
        env.globals['asset_v'] = lambda path: 'test'
        env.globals['config'] = {'version': '2.0.0', 'title': '御风面板'}

        template = env.get_template("monitor.html")
        html = template.render(
            g=MockG(),
            session={"login": True, "username": "admin"},
            data={"use_cdn": "no", "ip": "127.0.0.1"},
            config={"version": "2.0.0", "title": "御风面板"},
            current_lang="zh-CN",
            menu=[]
        )
        
        # 验证 4 大聚合卡片容器存在
        self.assertIn('id="compute_view"', html)
        self.assertIn('id="getload_average_view"', html)
        self.assertIn('id="diskview"', html)
        self.assertIn('id="network"', html)
        
        # 验证顶部统一水平居中控制栏与全局时间选择器
        self.assertIn('monitor-topbar', html)
        self.assertIn('monitor-topbar-left', html)
        self.assertIn('monitor-topbar-center', html)
        self.assertIn('monitor-topbar-right', html)
        self.assertIn('globalSearchTime', html)
        self.assertIn('setGlobalDay(\'24h\')', html)
        self.assertIn('data-day="24h"', html)
        self.assertIn('setGlobalDay(0)', html)

        # 验证卡片头部已移除冗余重复的时间按钮组
        self.assertNotIn('compute-time', html)
        self.assertNotIn('load-time', html)
        self.assertNotIn('disk-time', html)
        self.assertNotIn('network-time', html)

        # 验证底部全局时间轴拖动滑块容器存在
        self.assertIn('id="global_timeline_view"', html)
        self.assertIn('global-slider-box', html)
        
        # 验证自定义时间弹窗具备高层级 z-index，彻底杜绝下方卡片遮挡
        self.assertIn('z-index: 9999 !important;', html)

    def test_control_js_single_request_and_slider(self):
        """测试 control.js 中仅包含一次 get_cpu_io 请求，并包含底部整体时间滑块联动"""
        js_path = os.path.join(STATIC_DIR, "app", "control.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # 统计 get_cpu_io 出现次数
        cpu_requests = re.findall(r'/system/get_cpu_io', js_content)
        self.assertEqual(len(cpu_requests), 1, f"get_cpu_io 请求应仅出现 1 次，但出现了 {len(cpu_requests)} 次")

        # 验证核心函数定义与 24h 逻辑
        self.assertIn('function compute(b, e)', js_content)
        self.assertIn('function getload(b, e)', js_content)
        self.assertIn('function disk(b, e)', js_content)
        self.assertIn('function network(b, e)', js_content)
        self.assertIn('function setGlobalDay(day)', js_content)
        self.assertIn('function renderGlobalTimeline(xData)', js_content)
        self.assertIn('function bindInsideZoomSync(chartInst)', js_content)
        self.assertIn('day === \'24h\'', js_content)
        self.assertIn('setGlobalDay(\'24h\');', js_content)

        # 验证全局滑块联动与 dispatchAction
        self.assertIn('window.chartInstances[\'global_timeline_view\']', js_content)
        self.assertIn('chart.dispatchAction({', js_content)

        # 验证时间选取条最低显示到分钟（labelFormatter 截取前 11 位）、左右对称留白加大至 105px（left: 105, right: 105）
        self.assertIn('labelFormatter', js_content)
        self.assertIn('left: 105', js_content)
        self.assertIn('right: 105', js_content)

        # 验证性能核心配置：LTTB 降采样、消除平滑开销、禁用补间动画、RAF 节流与磁吸附 snap
        self.assertIn('sampling: \'lttb\'', js_content)
        self.assertIn('smooth: false', js_content)
        self.assertIn('animationDurationUpdate: 0', js_content)
        self.assertIn('requestAnimationFrame', js_content)
        self.assertIn('snap: true', js_content)

        # 验证彻底根除未解析占位符，且所有 Tooltip 均启用边界防裁剪（confine: true）
        self.assertNotIn('{a1}', js_content)
        self.assertNotIn('{c1}', js_content)
        self.assertIn('confine: true', js_content)

        # 验证智能均值降采样算法与 100ms 停顿触发
        self.assertIn('function aggregateSeries', js_content)
        self.assertIn('triggerOn: \'none\'', js_content)
        self.assertIn('hoverDebounceTimer', js_content)
        self.assertIn('convertFromPixel', js_content)
        self.assertIn('100', js_content)

    def test_query_sampling_alignment(self):
        """测试 query.py 中数据查询统一按 addtime 时间戳对齐，无跨表错位抽样"""
        query_path = os.path.join(ROOT_DIR, "web", "utils", "system", "query.py")
        with open(query_path, "r", encoding="utf-8") as f:
            q_content = f.read()
        self.assertNotIn('(id %', q_content)
        self.assertIn('def get_sampling_condition(table, start, end):', q_content)

    def test_i18n_dictionary_completeness(self):
        """测试 6 国语言词典中新增监控词条 100% 对齐"""
        required_keys = [
            "hours_24",
            "compute_resources",
            "load_saturation",
            "load_saturation_tips",
            "global_time_range",
            "all_charts",
            "cpu",
            "mem",
            "load_safe_line",
            "load_limit_line"
        ]

        for lang in ALL_LANGS:
            # 1. template.json
            t_path = os.path.join(LANG_DIR, lang, "template.json")
            with open(t_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
            self.assertIn("control", t_data, f"[{lang}] 缺失 control section")
            for k in required_keys:
                self.assertIn(k, t_data["control"], f"[{lang}] template.json 缺失词条: control.{k}")
                self.assertTrue(len(t_data["control"][k].strip()) > 0, f"[{lang}] control.{k} 为空")

            # 2. lan.js
            l_path = os.path.join(LANG_DIR, lang, "lan.js")
            with open(l_path, "r", encoding="utf-8") as f:
                l_content = f.read()
            for k in required_keys:
                self.assertIn(f'"{k}"', l_content, f"[{lang}] lan.js 缺失词条: {k}")

    def test_zero_chinese_in_foreign_languages(self):
        """测试 4 种外语新增词条绝无中文字符残留"""
        for lang in FOREIGN_LANGS:
            t_path = os.path.join(LANG_DIR, lang, "template.json")
            with open(t_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
            
            control_data = t_data.get("control", {})
            for k, val in control_data.items():
                if isinstance(val, str) and ZH_REGEX.search(val):
                    self.fail(f"[{lang}] control.{k} 包含中文字符: {val}")

if __name__ == '__main__':
    unittest.main()
