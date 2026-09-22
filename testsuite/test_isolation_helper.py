# coding: utf-8
"""`testsuite/_isolation.py` 的回归护栏：隔离后的**假面板库必须是 schema 合法的**。

## 为什么值得单独一个模块

`isolate()` 把面板 SQLite 重定向到临时区。如果它只造一个**空文件**，
`yf.M('option')` 就会报 `no such table: option` —— 而这个异常会被框架吞掉，
于是 `thisdb.setOption()` **静默失败**、紧接着回读得到 `{}`，
用例以「读不到刚写进去的数据」的形式**假红**，排查方向完全被带偏。

真实踩过：`test_external_status_sync` 的两条 `runByCache` 用例
（`AssertionError: 'openresty' not found in {}`），根因就是隔离后假库缺表，
而不是被测逻辑有问题。修法见 `_isolation._seed_panel_db()`。

所以这里钉两条：
1. 假面板库里必须有 `option` 表（空库会退化成「写了读不回来」）；
2. 走真实代码路径（`thisdb.setOption` / `getOption`）写入后必须能读回来。

本模块**不依赖**被 gitignore 的 `test/`，也**不依赖**网络与真实数据库。
"""
import os
import sqlite3
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, 'web')
for _p in (BASE_DIR, WEB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402

# 必须在 `import thisdb` 之前：它在导入期就会打开 <panelDir>/data/panel.db
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('isolation_helper_selftest')

import thisdb  # noqa: E402


class TestIsolationHelper(unittest.TestCase):

    def test_panel_db_file_created(self):
        """假面板库文件必须真的建出来了。"""
        db = os.path.join(_PANEL_TMP, 'data', 'panel.db')
        self.assertTrue(os.path.exists(db), '假面板库没被创建：%s' % db)

    def test_panel_db_has_option_table(self):
        """假面板库必须是 schema 合法的（不是空文件）。

        这条是当初假红的直接根因：空库里没有 `option` 表，
        `yf.M('option')` 报错被吞掉 → `setOption()` 静默失败。
        """
        db = os.path.join(_PANEL_TMP, 'data', 'panel.db')
        conn = sqlite3.connect(db)
        try:
            tables = {r[0] for r in
                      conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertIn('option', tables,
                      '假面板库缺 option 表 —— isolate() 退化成空库了，'
                      '依赖 setOption/getOption 的用例会假红。表清单：%s' % sorted(tables))

    def test_option_table_columns(self):
        """`option` 表的列必须齐全（name / type / value），否则读写仍会失败。"""
        db = os.path.join(_PANEL_TMP, 'data', 'panel.db')
        conn = sqlite3.connect(db)
        try:
            cols = {r[1] for r in conn.execute('PRAGMA table_info(option)')}
        finally:
            conn.close()
        for col in ('name', 'type', 'value'):
            self.assertIn(col, cols, 'option 表缺列 %s（实际列：%s）' % (col, sorted(cols)))

    def test_set_option_then_get_option_roundtrip(self):
        """端到端：走真实代码路径写进去，必须能读回来。"""
        thisdb.setOption('isolation_selftest_key', 'hello_isolation')
        self.assertEqual(thisdb.getOption('isolation_selftest_key'), 'hello_isolation')

    def test_set_option_overwrites(self):
        """同键重复写要覆盖（`setOption` 内部是「有则 update、无则 insert」两条分支）。"""
        thisdb.setOption('isolation_selftest_key', 'first')
        thisdb.setOption('isolation_selftest_key', 'second')
        self.assertEqual(thisdb.getOption('isolation_selftest_key'), 'second')

    def test_server_dir_redirected_and_seeded(self):
        """服务目录必须被重定向，且预建 mysql/ 与 mariadb/（否则 sqlite 抛
        `unable to open database file`，被吞掉但脏 stderr）。"""
        for mod in ('mysql', 'mariadb'):
            self.assertTrue(os.path.isdir(os.path.join(_SERVER_TMP, mod)),
                            '缺少 %s/ 目录' % mod)
        self.assertEqual(yf.getServerDir(), _SERVER_TMP)


if __name__ == '__main__':
    unittest.main()
