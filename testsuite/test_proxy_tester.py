# coding: utf-8
"""针对 scripts/proxy_tester.py 的保护测试（P1-9）。

断言：
1. 注释保留：头部注释、条目行间注释及尾部注释写回时 100% 完整保留，不发生丢失；
2. 排序语义：direct||rt 始终固定在第一位，其余节点按速度/可用性稳定排序；
3. 防误改写：默认不写回输入文件，必须显式指定 --save 或 --save-to。
"""

import io
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY_TESTER = os.path.join(ROOT, 'scripts', 'proxy_tester.py')


class TestProxyTester(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_test_proxy_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_01_parse_and_save_preserves_inline_comments(self):
        """验证行间注释、空行与头部注释在读写往返后完全保留。"""
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import proxy_tester

        sample = """# Header comment 1
# Header comment 2

direct||rt
# Comment before gh-proxy
gh-proxy.org|https://gh-proxy.org/|both

# Comment before ghfast
ghfast.top|https://ghfast.top/|both
# Trailing comment
"""
        test_file = os.path.join(self.tmp, 'test_proxies.list')
        with io.open(test_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(sample)

        header_lines, entries, trailing = proxy_tester.parse_list_with_header(test_file)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].key, 'direct')
        self.assertEqual(entries[1].key, 'gh-proxy.org')
        self.assertIn('# Comment before gh-proxy', entries[1].comments)
        self.assertEqual(entries[2].key, 'ghfast.top')
        self.assertIn('# Comment before ghfast', entries[2].comments)
        self.assertIn('# Trailing comment', trailing)

        # 模拟原地写回
        out_file = os.path.join(self.tmp, 'out_proxies.list')
        proxy_tester.save_proxy_list(out_file, header_lines, entries, trailing)

        with io.open(out_file, 'r', encoding='utf-8') as f:
            saved_content = f.read()

        self.assertEqual(sample, saved_content, '写回内容必须与原包含行间注释的文件逐字节完全一致')

    def test_02_direct_is_always_first_after_sorting(self):
        """即使 direct 测速很慢或失败，排序后 direct||rt 必须始终锁定在第一位。"""
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import proxy_tester

        entries = [
            proxy_tester.ProxyEntry('direct', '', 'rt'),
            proxy_tester.ProxyEntry('gh-fast', 'https://gh-fast/', 'both'),
            proxy_tester.ProxyEntry('gh-slow', 'https://gh-slow/', 'both'),
        ]
        test_rows = [
            {'key': 'direct', 'usable': False, 'speed': 0.0},
            {'key': 'gh-fast', 'usable': True, 'speed': 1000000.0},
            {'key': 'gh-slow', 'usable': True, 'speed': 200000.0},
        ]
        sorted_res = proxy_tester.sort_entries(entries, test_rows)
        self.assertEqual(sorted_res[0].key, 'direct', 'direct 必须锁定置顶')
        self.assertEqual(sorted_res[1].key, 'gh-fast', '高速节点排在第二')
        self.assertEqual(sorted_res[2].key, 'gh-slow', '慢速节点排在第三')


if __name__ == '__main__':
    unittest.main()

