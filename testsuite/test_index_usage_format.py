#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：首页 CPU / 内存 / 磁盘 数值展示格式与六国语言同步

需求：
    1. CPU 环下方文案：由「10 个物理核心，」改为「10 核心」（各语言 Core(s) 风格）
    2. 内存：由「1.24/7.75 (GB)」改为「1.2G / 7.8G」——统一按总量单位换算，
       保留 1 位小数四舍五入，斜杠两侧加空格
    3. 磁盘：由「14G/38G」改为「14G / 38G」，斜杠两侧加空格
    4. 所有语言包（lan.js / template.json / template.index.json）同步更新

验证点：
1. index.js 存在 formatMemPair() 且 setMemImg 使用它，不再出现旧的 `' ('+unit+')'` 拼接
2. Node.js 实际执行 formatMemPair，校验换算与四舍五入结果
3. 磁盘渲染斜杠两侧带空格；#core 标签不再使用 cpu_core（改为 core）
4. 6 国语言 3 份语言文件中 index.core 取值正确且三份严格一致
5. UTF-8 无 BOM + LF 换行
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_JS = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')

EXPECTED_CORE = {
    'zh-CN': '核心',
    'zh-TW': '核心',
    'en': 'Core(s)',
    'fr': 'C\u0153ur(s)',
    'de': 'Kern(e)',
    'it': 'Core',
}
LANG_FILES = ['lan.js', 'template.json', 'template.index.json']


def read_text_nobom_lf(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    assert not content.startswith(b'\xef\xbb\xbf'), "BOM detected in %s" % file_path
    assert b'\r\n' not in content, "CRLF detected in %s" % file_path
    return content.decode('utf-8')


def extract_function(src, signature, end_marker):
    start = src.index(signature)
    end = src.index('\n}', src.index(end_marker, start)) + 2
    return src[start:end]


class TestIndexUsageFormat(unittest.TestCase):

    def setUp(self):
        self.js = read_text_nobom_lf(INDEX_JS)

    def test_01_format_mem_pair_wired(self):
        """setMemImg 必须走 formatMemPair，旧的括号单位拼接必须消失"""
        self.assertIn('function formatMemPair(', self.js, "缺少 formatMemPair 函数")
        self.assertIn('var mem_txt = formatMemPair(info.memRealUsed, info.memTotal);', self.js,
                      "setMemImg 未使用 formatMemPair")
        # 旧格式：memRealUsedVal + '/' + memTotalVal + ' ('+ unit +')'
        self.assertNotIn("' ('+ unit +')'", self.js, "仍残留旧的 (GB) 括号拼接格式")
        self.assertNotIn("memRealUsed.split(' ')[0]", self.js, "仍残留旧的 toSize 字符串切割逻辑")

    def test_02_format_mem_pair_output(self):
        """Node.js 实际执行 formatMemPair，校验换算 + 保留 1 位小数四舍五入"""
        fn = extract_function(self.js, 'function formatMemPair(', 'return used.toFixed')
        vectors = [
            (934739968, 8324366336, '0.9G / 7.8G'),
            (268435456, 536870912, '256.0M / 512.0M'),
            (1073741824, 1073741824, '1.0G / 1.0G'),
        ]
        lines = [fn, 'var cases = ' + json.dumps(vectors) + ';',
                 'cases.forEach(function(c){ var got = formatMemPair(c[0], c[1]);',
                 'if (got !== c[2]) { console.error("MISMATCH", c[0], c[1], "got=" + got, "want=" + c[2]); process.exit(1); } });',
                 'console.log("FORMAT_OK");']
        script = '\n'.join(lines)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(script)
            tmp_path = f.name
        try:
            res = subprocess.run('node "%s"' % tmp_path, shell=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0,
                             "formatMemPair 输出不符合预期:\n%s" % (res.stderr or res.stdout))
            self.assertIn('FORMAT_OK', res.stdout)
        finally:
            os.unlink(tmp_path)

    def test_03_disk_and_core_label(self):
        """磁盘斜杠两侧空格；CPU 环下方改用 index.core"""
        self.assertIn("' / ' + item.size[0]", self.js, "磁盘容量未加空格：应为 14G / 38G")
        # 所有写 #core 的行都不得再使用 cpu_core（那是 tooltip 专用的带逗号文案）
        core_lines = [ln for ln in self.js.split('\n') if '#core"' in ln]
        self.assertTrue(core_lines, "未找到 #core 赋值语句")
        for ln in core_lines:
            self.assertNotIn('cpu_core', ln, "CPU 环下方文案仍使用 cpu_core: " + ln.strip())
        self.assertIn('$("#core").html(net.cpu[1] + " " + lan.index.core);', self.js,
                      "iostat 刷新路径未同步为 index.core")

    def test_04_language_packs_synced(self):
        """6 国语言 3 份文件 index.core 取值正确且三份一致"""
        for lang, expected in EXPECTED_CORE.items():
            values = []
            for fn in LANG_FILES:
                path = os.path.join(PROJECT_ROOT, 'web', 'static', 'language', lang, fn)
                text = read_text_nobom_lf(path)
                found = None
                for line in text.split('\n'):
                    if line.strip().startswith('"core"'):
                        colon = line.index(':')
                        q1 = line.index('"', colon)
                        q2 = line.index('"', q1 + 1)
                        found = line[q1 + 1:q2]
                self.assertIsNotNone(found, "%s/%s 缺少 core 键" % (lang, fn))
                self.assertEqual(found, expected,
                                 "%s/%s 的 core 应为 %s，实际 %s" % (lang, fn, expected, found))
                values.append(found)
            self.assertEqual(len(set(values)), 1,
                             "%s 的三份语言文件 core 不一致: %s" % (lang, values))


if __name__ == '__main__':
    unittest.main()
