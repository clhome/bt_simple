#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页磁盘分区环形图“框架先行”体验优化

背景（用户反馈）：
    磁盘环形图是接口返回后才整体 append 的，导致负载/CPU/内存的圆环和数值都出来了，
    磁盘要等到最后（错峰 800ms 之后）才整块出现，视觉上像“漏了一块再补上”。

验证点：
1. web/static/app/index.js
   - 新增 DISK_CACHE_KEY 本地二级缓存键
   - buildDiskBoxHtml()：缓存/实时共用同一套环形图渲染（保证样式绝对一致）
   - renderDiskSkeleton()：数据返回前先绘制空环形框架（骨架屏）
   - renderDiskFromCache()：刷新页面 0ms 用上次数据秒开
   - renderDiskList()：数据返回后原子替换骨架/缓存，避免重复与抖动
   - initDiskPlaceholder()：优先缓存，其次骨架屏
   - getDiskInfo() 复用 buildDiskBoxHtml/renderDiskList，不再整块延迟出现
2. setImg() 对“···/...”等占位文本做 NaN 兜底，保持灰色空环而不是产生无效 transform
3. web/templates/default/index.html
   - 0ms 内先调用 initDiskPlaceholder()，且必须在 indexSoft 之前
   - 磁盘接口错峰延迟不再是最慢的 800ms
   - GPU 环形图不再初始 display:none（同样“框架先行”）
4. web/static/css/site.css 提供 .disk-skeleton 骨架样式与呼吸动画
5. Node.js V8 语法校验 + UTF-8 无 BOM + LF 换行
"""

import os
import re
import subprocess
import sys
import unittest

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_JS = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
INDEX_HTML = os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'index.html')
SITE_CSS = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')


def read_text_nobom_lf(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    assert not content.startswith(b'\xef\xbb\xbf'), f"BOM detected in {file_path}"
    assert b'\r\n' not in content, f"CRLF detected in {file_path}, must use LF"
    return content.decode('utf-8')


class TestIndexDiskSkeleton(unittest.TestCase):

    def setUp(self):
        self.js = read_text_nobom_lf(INDEX_JS)
        self.html = read_text_nobom_lf(INDEX_HTML)
        self.css = read_text_nobom_lf(SITE_CSS)

    def test_01_disk_frame_first_functions(self):
        """index.js 必须具备骨架屏/缓存秒开/原子替换的完整能力"""
        for fn in [
            'var DISK_CACHE_KEY',
            'function buildDiskBoxHtml(',
            'function renderDiskSkeleton(',
            'function renderDiskFromCache(',
            'function renderDiskList(',
            'function initDiskPlaceholder(',
            'function getDiskInfo(',
        ]:
            self.assertIn(fn, self.js, f"index.js 缺失: {fn}")

        # getDiskInfo 必须走统一的渲染入口，杜绝再次整块延迟 append
        self.assertIn('renderDiskList(diskList, true);', self.js,
                      "getDiskInfo 必须通过 renderDiskList 原子替换渲染")
        # 骨架屏元素必须带 diskbox 类，保证实时数据到达时可被统一清除
        self.assertIn('diskbox disk-skeleton', self.js, "骨架屏缺少 diskbox/disk-skeleton 标记")
        self.assertIn("localStorage.setItem(DISK_CACHE_KEY", self.js, "磁盘数据未写入本地缓存")
        self.assertIn("localStorage.getItem(DISK_CACHE_KEY)", self.js, "未读取磁盘本地缓存")

    def test_02_setimg_nan_guard(self):
        """setImg 必须对占位文本做 NaN 兜底，避免无效 transform 破坏环形图"""
        self.assertIn('isNaN(val) ? 0 : val * 3.6', self.js,
                      "setImg 缺少 NaN 兜底，骨架屏占位会生成无效 rotate")
        # 骨架屏 mask 没有 data 属性，hover 绑定不应误设 undefined
        self.assertIn(".diskbox .mask[data]", self.js,
                      "磁盘 tips 应只绑定带 data 的真实数据 mask")

    def test_03_html_startup_order_and_gpu(self):
        """首页启动时序：磁盘框架必须与其它环形图同时出现"""
        cache_idx = self.html.find('initDiskPlaceholder()')
        soft_idx = self.html.find('indexSoft(startLoadStatus)')
        self.assertNotEqual(cache_idx, -1, "index.html 缺失 initDiskPlaceholder() 0ms 调用")
        self.assertNotEqual(soft_idx, -1, "index.html 缺失 indexSoft(startLoadStatus) 调用")
        self.assertLess(cache_idx, soft_idx, "initDiskPlaceholder 必须在 indexSoft 之前执行")

        # 磁盘不再是最慢的 800ms 错峰项
        self.assertIn('getDiskInfo();', self.html, "index.html 缺失 getDiskInfo 调用")
        self.assertNotIn('}, 800);', self.html, "磁盘接口仍保留 800ms 最慢错峰延迟")
        self.assertIn('}, 500);', self.html, "磁盘接口应提前到 500ms 错峰")

        # GPU 环形图同样“框架先行”，不再初始隐藏
        self.assertIn('id="gpuChart"', self.html, "index.html 缺失 gpuChart 容器")
        gpu_tag = re.search(r'<li[^>]*id="gpuChart"[^>]*>', self.html)
        self.assertIsNotNone(gpu_tag, "未匹配到 gpuChart 的 li 标签")
        self.assertNotIn('display: none', gpu_tag.group(0), "GPU 环形图不应再初始 display:none")

    def test_04_skeleton_css(self):
        """骨架屏样式与呼吸动画必须存在"""
        self.assertIn('.disk-skeleton', self.css, "site.css 缺失 .disk-skeleton 样式")
        self.assertIn('.disk-sk-bar', self.css, "site.css 缺失骨架条样式")
        self.assertIn('@keyframes diskSkPulse', self.css, "site.css 缺失骨架呼吸动画")

    def test_05_js_syntax(self):
        """Node.js V8 引擎校验 index.js 语法"""
        res = subprocess.run(f'node -c "{INDEX_JS}"', shell=True,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"index.js 语法校验失败:\n{res.stderr}")


if __name__ == '__main__':
    unittest.main()
