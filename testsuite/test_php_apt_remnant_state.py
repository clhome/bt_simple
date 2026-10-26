# coding: utf-8
"""守卫：apt 渠道的「装了没装」必须看 dpkg 包状态，不能只看版本串。

## 现场（2026-10-26，真机 172.17.60.248，用户第二次报障）

```
[php-apt] 离线包通道不可用：未找到 PHP8.2 的离线 .deb 包…
{"status": false, "msg": "升级失败: 升级后版本 8.2.33 仍低于基线 8.2.35…本次未做任何改动",
 "data": {"before": "8.2.33-1+0~…", "after": "8.2.33-1+0~…", "no_op": true, "diagnosis": {}}}
```

网络已经通了（`apt-get update` 全部「命中」），可 PHP8.2 还是升不动。真相是
**PHP8.2 根本没装**：

```
$ dpkg -l | grep php8.2-fpm
rc  php8.2-fpm  8.2.33-1+0~20260730.92+debian12~1.gbp655644   # ← rc：已卸载，只剩配置文件
$ LC_ALL=C apt-get -s install --only-upgrade php8.2-fpm
Skipping php8.2-fpm, it is not installed and only upgrades are requested.
```

但 `dpkg-query -W -f='${Version}' php8.2-fpm` **照样吐出 8.2.33**（`rc` 状态也保留版本串），
于是：

* `php_sec_scan.read_package_version('apt','82')` 认为「已装 8.2.33」；
* 巡检把 `/etc/php/8.2` 目录当成已装实例 → 报「低于基线 8.2.35」→ 首页卡片/软件页给升级按钮；
* 点升级 → apt 什么都不做 → 用户看到「升级失败」。

## 本文件守什么

1. `parse_dpkg_row()` 对 `rc`/`un`/`ii`/`iU` 与**旧版只有版本串**的输入都给对结论；
2. `read_package_version()` 对 `rc` 残留返回空（插件据此走「先清理残留」的提示）；
3. `collect_apt()` 不把残留当已装实例，`collect_apt_remnants()` 单独采它并进巡检摘要；
4. php-apt 的版本列表以 dpkg 包状态为准，升级入口对残留给**可执行**的清理命令；
5. 语言包里必须有这条提示（否则六语言界面里它会退化成中文原文）。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
APT_PY = os.path.join(ROOT, 'plugins', 'php-apt', 'index.py')
LANG_DIR = os.path.join(ROOT, 'plugins', 'php-apt', 'lang')

if WEB not in sys.path:
    sys.path.insert(0, WEB)

from core import php_sec_scan as scan       # noqa: E402
from core import php_sec_baseline as bl     # noqa: E402

REM_VER = '8.2.33-1+0~20260730.92+debian12~1.gbp655644'
OK_VER = '8.2.35-1+0~20261021.94+debian12~1.gbp8bff78'
#: 六语言都必须有这条提示的键（模板本身）。
PURGE_KEY = ('PHP%s 的 apt 包当前状态是 %s（已卸载，仅剩配置文件），apt 无法升级；'
             '请先清理残留（两条命令）：apt-get purge -y php%s-* ，再执行 '
             'rm -rf /etc/php/%s，然后在面板重新安装 PHP%s')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def _fake_run(state, version):
    """模拟 dpkg-query：任意包都返回同一个状态行。"""
    def run(argv):
        if argv and argv[0] == 'dpkg-query':
            return 0, '%s\t%s' % (state, version)
        return 127, ''
    return run


class ParseDpkgRowTest(unittest.TestCase):
    """`parse_dpkg_row()`：状态 → 已装/残留（纯函数）。"""

    def test_01_removed_with_configs_is_not_installed(self):
        info = scan.parse_dpkg_row('rc\t%s' % REM_VER)
        self.assertFalse(info['installed'], '`rc` = 已卸载只剩配置文件，绝不能算已装')
        self.assertTrue(info['remnant'])
        self.assertEqual(info['state'], 'rc')
        self.assertEqual(info['version'], REM_VER, '残留仍要带出旧版本号（提示里要用）')

    def test_02_installed_states(self):
        for state in ('ii', 'iU', 'iF', 'iH', 'iW', 'it', 'hi'):
            info = scan.parse_dpkg_row('%s\t%s' % (state, OK_VER))
            self.assertTrue(info['installed'], '状态 %s 必须算已装' % state)
            self.assertFalse(info['remnant'])

    def test_03_not_installed_states(self):
        for state in ('un', 'pn', 'in'):
            info = scan.parse_dpkg_row('%s\t%s' % (state, OK_VER))
            self.assertFalse(info['installed'], '状态 %s 不能算已装' % state)
            self.assertFalse(info['remnant'], '`un`/`pn` 不算残留（根本没装过）')

    def test_04_legacy_version_only_shape(self):
        """旧调用点/测试桩只给版本串：必须当作已装（不能把真安装漏判成未装）。"""
        info = scan.parse_dpkg_row('8.2.29-1+deb12u3')
        self.assertTrue(info['installed'])
        self.assertEqual(info['version'], '8.2.29-1+deb12u3')
        self.assertFalse(scan.parse_dpkg_row('')['installed'])
        self.assertFalse(scan.parse_dpkg_row(None)['installed'])


class AptStateReadingTest(unittest.TestCase):
    """`apt_package_state()` / `read_package_version()` / `collect_apt()` 的口径。"""

    def test_01_remnant_version_is_empty(self):
        run = _fake_run('rc', REM_VER)
        self.assertEqual(scan.apt_package_state('82', run=run)['state'], 'rc')
        self.assertTrue(scan.apt_package_state('82', run=run)['remnant'])
        self.assertEqual(scan.read_package_version('apt', '82', run=run), '',
                         '`rc` 残留读出来的版本必须是空，否则插件会去「升级」一个没装的包')

    def test_02_installed_version_read(self):
        run = _fake_run('ii', OK_VER)
        self.assertEqual(scan.read_package_version('apt', '82', run=run), OK_VER)

    def test_03_collect_apt_skips_remnant_and_reports_it(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, '8.2'))
            run = _fake_run('rc', REM_VER)
            self.assertEqual(scan.collect_apt(tmp, run=run), [],
                             '残留目录不能算「已装实例」（否则巡检报一个不存在的 PHP 低于基线）')
            rem = scan.collect_apt_remnants(tmp, run=run)
            self.assertEqual(len(rem), 1)
            self.assertEqual(rem[0]['branch'], '82')
            self.assertEqual(rem[0]['state'], 'rc')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_04_collect_apt_keeps_real_install(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, '8.3'))
            entries = scan.collect_apt(tmp, run=_fake_run('ii', OK_VER))
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['branch'], '83')
            self.assertEqual(entries[0]['version'], '8.2.35')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_05_scan_reports_remnants_in_summary(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, '8.2'))
            data = scan.scan(server_php_dir=os.path.join(tmp, 'none'),
                             apt_root=tmp, yum_root=os.path.join(tmp, 'none'),
                             run=_fake_run('rc', REM_VER))
            self.assertEqual(data['state'], 'empty', '只剩残留时不该告警')
            self.assertEqual(len(data.get('remnants') or []), 1)
            self.assertIn('残留', data['summary'])
            self.assertIn('purge', data['summary'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_06_query_carries_status_field(self):
        """查询必须带 `${db:Status-Abbrev}` —— 只查 `${Version}` 就是这次事故的根因。"""
        src = _read(os.path.join(WEB, 'core', 'php_sec_scan.py'))
        self.assertIn('${db:Status-Abbrev}', src)
        self.assertNotIn("-f=${Version}'", src,
                         '不许再写成只取版本串（`rc` 状态也会返回版本）')


class AptPluginRemnantTest(unittest.TestCase):
    """php-apt 接线：版本列表看包状态、升级入口给可执行的清理命令。"""

    def setUp(self):
        self.src = _read(APT_PY)

    def test_01_version_list_checks_package_state(self):
        start = self.src.index('def getInstalledPhpVersions(')
        body = self.src[start:self.src.index('def remnantHint(', start)]
        self.assertIn("read_package_version('apt'", body,
                      '版本列表必须按 dpkg 包状态过滤，不能只看 /etc/php 目录名')

    def test_02_upgrade_entry_explains_remnant(self):
        self.assertIn('def missingPackageEnvelope(', self.src)
        self.assertIn('def remnantHint(', self.src)
        body = self.src[self.src.index('def upgradeToBaseline('):]
        self.assertIn('missingPackageEnvelope(ver)', body,
                      '读不到已装包时必须走「残留/未安装」提示，而不是笼统一句未检测到')

    def test_03_purge_command_is_pasteable(self):
        start = self.src.index('def remnantHint(')
        body = self.src[start:self.src.index('def ', start + 10)]
        self.assertIn('apt-get purge -y php%s-*', body)
        self.assertIn('rm -rf /etc/php/%s', body)
        # 通配符必须能被 shell 展开：加引号会让 apt 找不到包（`'php8.2-*'` 不是包名）
        self.assertNotIn("'php%s-*'", body)
        self.assertNotIn('shlexQuote', body)

    def test_04_i18n_key_present_in_all_languages(self):
        names = sorted(n for n in os.listdir(LANG_DIR) if n.endswith('.json'))
        self.assertGreaterEqual(len(names), 6, '语言包数量异常: %s' % names)
        for name in names:
            with io.open(os.path.join(LANG_DIR, name), encoding='utf-8') as fp:
                data = json.load(fp)
            self.assertIn(PURGE_KEY, data,
                          '%s 缺少「残留需先清理」这条提示（界面会退化显示中文原文）' % name)
            self.assertTrue(str(data[PURGE_KEY]).strip())


class BaselineSummaryTest(unittest.TestCase):
    """`summary_text()` 必须把残留说出来（否则用户只会看到「全部达标」）。"""

    def test_01_summary_without_remnants_unchanged(self):
        res = {'state': 'ok', 'items': [], 'baseline_date': bl.BASELINE_DATE}
        text = bl.summary_text(res)
        self.assertIn('全部达标', text)
        self.assertNotIn('残留', text)

    def test_02_summary_with_remnants(self):
        res = {'state': 'empty', 'items': [], 'baseline_date': bl.BASELINE_DATE,
               'remnants': [{'branch': '82', 'state': 'rc'}]}
        text = bl.summary_text(res)
        self.assertIn('残留', text)
        self.assertIn('PHP82', text)
        self.assertIn('rc', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
