# coding: utf-8
"""测试：已安装的存量 PHP 旧版本（如 PHP 7.1 等不在静态 info.json 中的版本）
必须能在软件商店中被正确发现并展示，确保用户能通过软件商店执行卸载。
"""

import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import plugin as plugin_mod


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


class PhpInstalledLegacyVersionsTest(unittest.TestCase):
    """验证存量已装但静态清单未列出的老版本 PHP（如 7.1）能够动态补全展示并供卸载。"""

    def _obj(self, installed):
        obj = plugin_mod.plugin.__new__(plugin_mod.plugin)
        obj._plugin_dir = os.path.join(ROOT, 'plugins')
        setattr(obj, '_plugin__plugin_dir', os.path.join(ROOT, 'plugins'))
        obj._phpInstalledBranches = lambda: installed
        return obj

    def _rows_without_71(self):
        """模拟软件商店基于静态 info.json 生成的原始 PHP 列表（只有 8.2~8.5）。"""
        return [
            {'name': 'php-apt', 'versions': '82', 'install_checks': '/x/82', 'setup': False, 'coexist': True},
            {'name': 'php-apt', 'versions': '83', 'install_checks': '/x/83', 'setup': False, 'coexist': True},
            {'name': 'php', 'versions': '82', 'install_checks': '/x/php82', 'setup': False, 'coexist': True},
            {'name': 'mysql', 'versions': '57', 'install_checks': '/x/mysql57', 'setup': True, 'coexist': False},
        ]

    def test_01_dynamic_inject_installed_apt_71(self):
        """当探针探测到 apt 安装了 7.1 时，列表必须补全该条目并标记已装与停维。"""
        installed = {'src': set(), 'apt': {'71'}, 'yum': set()}
        rows = self._rows_without_71()
        out = self._obj(installed).applyPhpVersionPolicy(rows)
        by_key = {(r['name'], r['versions']): r for r in out}

        self.assertIn(('php-apt', '71'), by_key, '已装的 php-apt 71 必须被动态补全进入列表')
        item = by_key[('php-apt', '71')]
        self.assertTrue(item.get('setup'), '已安装老版本 setup 必须为 True')
        self.assertEqual(item.get('setup_version'), '71')
        self.assertTrue(item.get('php_eol'), '低于 8.2 的旧分支必须标停维 php_eol')
        self.assertEqual(item.get('php_eol_min'), '8.2')
        self.assertTrue(item.get('setup_by_probe'))

    def test_02_uninstalled_legacy_not_injected(self):
        """当探针未探测到老版本时，绝不可无故凭空注入未安装的停维老版本。"""
        installed = {'src': set(), 'apt': set(), 'yum': set()}
        rows = self._rows_without_71()
        out = self._obj(installed).applyPhpVersionPolicy(rows)
        keys = [(r['name'], r['versions']) for r in out]

        self.assertNotIn(('php-apt', '71'), keys, '未安装的 71 不得出现在软件列表中')
        self.assertNotIn(('php-apt', '74'), keys)
        self.assertIn(('php-apt', '82'), keys)

    def test_03_refresh_dynamic_status_preserves_probe_setup(self):
        """即使磁盘上未建立标志目录，探针确认已装的条目也不能被 refreshDynamicStatus 覆盖为未装。"""
        obj = self._obj({'src': set(), 'apt': {'71'}, 'yum': set()})
        items = [{
            'name': 'php-apt',
            'versions': '71',
            'coexist': True,
            'install_checks': '/nonexistent/path/server/php-apt/71',
            'setup': True,
            'setup_version': '71',
            'setup_by_probe': True,
            'display_status': True,
        }]
        refreshed = obj.refreshDynamicStatus(items)
        self.assertTrue(refreshed[0]['setup'], 'setup_by_probe 的条目不能因目录缺失变成未安装')
        self.assertEqual(refreshed[0]['setup_version'], '71', 'setup_version 必须保持版本号')

    def test_04_uninstall_script_has_no_dir_check_gate(self):
        """卸载脚本不能因为目录缺失而跳过 stop / 清理。"""
        apt_sh = _read(os.path.join(ROOT, 'plugins', 'php-apt', 'install.sh'))
        self.assertIn('if [ "${action}" == "uninstall" ];then', apt_sh)
        self.assertNotIn('if [ "${action}" == "uninstall" ] && [ -d', apt_sh)

        yum_sh = _read(os.path.join(ROOT, 'plugins', 'php-yum', 'install.sh'))
        self.assertIn('if [ "${action}" == "uninstall" ];then', yum_sh)
        self.assertNotIn('if [ "${action}" == "uninstall" ] && [ -d', yum_sh)

    def test_05_dynamic_inject_compiled_and_yum_legacy(self):
        """同理覆盖编译版（如 56）和 yum 渠道（如 71）的存量老版本发现。"""
        installed = {'src': {'56'}, 'apt': set(), 'yum': {'71'}}
        rows = self._rows_without_71()
        out = self._obj(installed).applyPhpVersionPolicy(rows)
        by_key = {(r['name'], r['versions']): r for r in out}

        self.assertIn(('php', '56'), by_key, '已装的编译版 php 56 必须补全')
        self.assertTrue(by_key[('php', '56')]['setup'])
        self.assertTrue(by_key[('php', '56')]['php_eol'])

        self.assertIn(('php-yum', '71'), by_key, '已装的 yum php-yum 71 必须补全')
        self.assertTrue(by_key[('php-yum', '71')]['setup'])
        self.assertTrue(by_key[('php-yum', '71')]['php_eol'])

    def test_06_search_keyword_matches_dynamic_item(self):
        """搜索 php 时，动态补全的 PHP 条目必须能被 searchKey 匹配命中。"""
        installed = {'src': set(), 'apt': {'71'}, 'yum': set()}
        rows = self._rows_without_71()
        obj = self._obj(installed)
        out = obj.applyPhpVersionPolicy(rows)
        by_key = {(r['name'], r['versions']): r for r in out}
        item_71 = by_key[('php-apt', '71')]
        self.assertTrue(obj.searchKey(item_71, 'php'), '搜索 php 必须能搜到补全的 php-apt 71')


if __name__ == '__main__':
    unittest.main()
