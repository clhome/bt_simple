# coding: utf-8
"""OpenResty 版本在线同步 + 统一版本同步任务 的验收用例。

覆盖四层：
  1. `web/core/openresty_release_index.py` 的解析/比较/缓存/离线兜底；
  2. 版本安装脚本自动生成（`ensure_version_script`）的幂等与安全边界；
  3. `plugins/openresty/versions/1.31.9.1/install.sh` 与 `info.json` 的落地一致性；
  4. `web/core/version_sync.py` 的任务注册/历史 JDK 任务迁移 与统一同步汇总。
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (ROOT, WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import openresty_release_index as idx  # noqa: E402
from core import version_sync as vs              # noqa: E402
import core.yf as yf                             # noqa: E402

OPENRESTY_PLUGIN = os.path.join(ROOT, 'plugins', 'openresty')

SAMPLE_PAGE = '''
<h2>Latest release</h2>
<p><a href="https://openresty.org/download/openresty-1.31.9.1.tar.gz">openresty-1.31.9.1.tar.gz</a>
   6.5MB [PGP] [Changes] - 23 November 2026</p>
<h2>Legacy releases</h2>
<p><a href="https://openresty.org/download/openresty-1.31.8.1.tar.gz">openresty-1.31.8.1.tar.gz</a> - 26 October 2026</p>
<p><a href="https://openresty.org/download/ngx_openresty-1.9.7.2.tar.gz">ngx_openresty-1.9.7.2.tar.gz</a> - 8 September 2019</p>
<p><a href="https://openresty.org/download/openresty-1.31.10.1-rc1.tar.gz">rc</a></p>
'''


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


class TestOpenrestyReleaseIndex(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_or_idx_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_parse_listing_only_official_versions(self):
        got = idx.parse_listing(SAMPLE_PAGE)
        # 只认 4 段正式版；ngx_openresty 历史包与 -rc 包都不许进列表
        self.assertIn('1.31.9.1', got)
        self.assertIn('1.31.8.1', got)
        self.assertNotIn('1.9.7.2', got)
        self.assertNotIn('1.31.10.1', got)
        self.assertEqual(got['1.31.9.1'], '2026-11-23')
        self.assertEqual(got['1.31.8.1'], '2026-10-26')
        # 空/畸形输入必须是「抓取失败」而不是「没有新版本」
        self.assertEqual(idx.parse_listing(''), {})
        self.assertEqual(idx.parse_listing('<html>captive portal</html>'), {})

    def test_02_version_math_and_needs_update(self):
        self.assertTrue(idx.is_newer('1.31.9.1', '1.31.8.1'))
        # 数值比较：1.31.10.1 必须大于 1.31.9.1（字典序会判反）
        self.assertTrue(idx.is_newer('1.31.10.1', '1.31.9.1'))
        self.assertFalse(idx.is_newer('1.31.9.1', '1.31.9.1'))
        self.assertTrue(idx.is_version('1.31.9.1'))
        self.assertFalse(idx.is_version('1.31.1'))

        # 三段历史号（1.31.1）与上游 1.31.1.1 视为同版本，不能反复提示升级
        self.assertFalse(idx.needs_update('1.31.1', '1.31.1.1'))
        self.assertTrue(idx.needs_update('1.31.1', '1.31.9.1'))
        self.assertTrue(idx.needs_update('1.31.1.1', '1.31.9.1'))
        self.assertFalse(idx.needs_update('1.31.9.1', '1.31.9.1'))
        self.assertFalse(idx.needs_update('', '1.31.9.1'))
        self.assertEqual(idx.latest_of({'1.31.1.1': '', '1.31.9.1': ''}), '1.31.9.1')
        self.assertEqual(idx.changelog_url('1.31.9.1'),
                         'https://openresty.org/en/changelog-1031009.html')

    def test_03_offline_versions_falls_back_to_builtin(self):
        versions, meta = idx.offline_versions(self.tmp)
        self.assertEqual(meta['source'], 'builtin')
        self.assertFalse(meta['fresh'])
        self.assertEqual(meta['latest'], idx.latest_of(idx.BUILTIN_VERSIONS))
        self.assertIn('1.31.9.1', versions)

    def test_04_refresh_writes_cache_and_degrades_gracefully(self):
        versions, info = idx.refresh(self.tmp, fetcher=lambda url, timeout=None: SAMPLE_PAGE, now=1000)
        self.assertEqual(info['source'], 'online')
        self.assertTrue(info['online'])
        self.assertEqual(info['latest'], '1.31.9.1')
        cached = idx.load_cache(idx.index_path(self.tmp))
        self.assertIn('1.31.9.1', cached['versions'])

        # 网络抛异常：回退缓存且不抛、不把「抓不到」当「没有新版本」
        def _boom(url, timeout=None):
            raise IOError('network down')

        versions2, info2 = idx.refresh(self.tmp, fetcher=_boom, now=2000)
        self.assertEqual(info2['source'], 'cache')
        self.assertIn('network down', info2['error'])
        self.assertEqual(info2['latest'], '1.31.9.1')

        # 200 但内容不可解析（认证页/劫持）：必须留 error
        _v3, info3 = idx.refresh(self.tmp, fetcher=lambda url, timeout=None: '<html>login</html>', now=3000)
        self.assertIn('无法解析', info3['error'])

    def test_05_ensure_version_script_idempotent_and_safe(self):
        plugin_dir = os.path.join(self.tmp, 'openresty')
        path = idx.ensure_version_script(plugin_dir, '1.32.1.1')
        self.assertTrue(path.endswith(os.path.join('versions', '1.32.1.1', 'install.sh')))
        body = io.open(path, encoding='utf-8').read()
        self.assertIn('YF_OPENRESTY_VERSION="1.32.1.1"', body)
        self.assertIn('common/openresty_build.sh', body)
        # 生成结果必须是合法 bash（Windows 开发机上可能没有 bash，有则必须通过）
        _bash = shutil.which('bash')
        if _bash:
            self.assertEqual(subprocess.call([_bash, '-n', path]), 0)

        # 已存在（手写）脚本绝不被覆盖
        _write(path, '#!/bin/bash\necho hand-written\n')
        idx.ensure_version_script(plugin_dir, '1.32.1.1')
        self.assertIn('hand-written', io.open(path, encoding='utf-8').read())

        # 非法版本号（目录穿越 / 三段号）一律拒绝
        self.assertEqual(idx.ensure_version_script(plugin_dir, '../../etc'), '')
        self.assertEqual(idx.ensure_version_script(plugin_dir, '1.31.1'), '')

    def test_06_panel_hint_uses_offline_index(self):
        _write(idx.index_path(self.tmp), json.dumps({
            'schema': idx.SCHEMA, 'fetched_at': 2000000000,
            'versions': {'1.31.9.1': '2026-11-23'},
        }))
        hint = idx.panel_hint('1.31.1', self.tmp, now=2000000100)
        self.assertEqual(hint['latest'], '1.31.9.1')
        self.assertEqual(hint['release_date'], '2026-11-23')
        self.assertTrue(hint['needs_update'])
        # 已装最新 → 不提示
        self.assertIsNone(idx.panel_hint('1.31.9.1', self.tmp, now=2000000100))
        # 未装/版本畸形 → 不提示
        self.assertIsNone(idx.panel_hint('', self.tmp))
        self.assertIsNone(idx.panel_hint('abc', self.tmp))


class TestOpenrestyPluginArtifacts(unittest.TestCase):

    def test_07_shipped_versions_are_installable(self):
        info = json.loads(io.open(os.path.join(OPENRESTY_PLUGIN, 'info.json'), encoding='utf-8').read())
        self.assertIn('1.31.9.1', info['versions'])
        # 前端把 versions 末项当「最新」：1.31.9.1 必须在最后
        self.assertEqual(info['versions'][-1], '1.31.9.1')
        for ver in info['versions']:
            script = os.path.join(OPENRESTY_PLUGIN, 'versions', ver, 'install.sh')
            self.assertTrue(os.path.isfile(script), 'missing version script: %s' % script)
            _bash = shutil.which('bash')
            if _bash:
                self.assertEqual(subprocess.call([_bash, '-n', script]), 0)

        new_script = os.path.join(OPENRESTY_PLUGIN, 'versions', '1.31.9.1', 'install.sh')
        body = io.open(new_script, encoding='utf-8').read()
        self.assertIn('YF_OPENRESTY_VERSION="1.31.9.1"', body)
        # 构建配方必须是共享文件，不能退回到「每版一份完整拷贝」
        self.assertIn('common/openresty_build.sh', body)

        build = io.open(os.path.join(OPENRESTY_PLUGIN, 'versions', 'common', 'openresty_build.sh'),
                        encoding='utf-8').read()
        self.assertIn('--with-http_v3_module', build)
        # 版本脚本必须写完整上游版本号（否则补丁差异不可见）
        self.assertIn('version.pl', build)

    def test_08_frontend_and_backend_hooks_wired(self):
        js = io.open(os.path.join(WEB, 'static', 'app', 'soft.js'), encoding='utf-8').read()
        self.assertIn('online_update_to', js)
        self.assertIn('soft_new_version_badge', js)

        plugin_js = io.open(os.path.join(OPENRESTY_PLUGIN, 'js', 'openresty.js'), encoding='utf-8').read()
        self.assertIn('function orVersionCheck', plugin_js)
        self.assertIn('version_info', plugin_js)

        plugin_html = io.open(os.path.join(OPENRESTY_PLUGIN, 'index.html'), encoding='utf-8').read()
        self.assertIn('orVerTip', plugin_html)
        self.assertIn('orVersionCheck()', plugin_html)

        plugin_py = io.open(os.path.join(OPENRESTY_PLUGIN, 'index.py'), encoding='utf-8').read()
        self.assertIn('def versionInfo', plugin_py)
        self.assertIn("func == 'version_info'", plugin_py)

        plugin_mgr = io.open(os.path.join(WEB, 'utils', 'plugin.py'), encoding='utf-8').read()
        self.assertIn('_onlineApplyVersionHint', plugin_mgr)
        self.assertIn('ONLINE_VERSION_INDEX_PLUGINS', plugin_mgr)
        self.assertIn('ensure_version_script', plugin_mgr)

    def test_09_crontab_task_name_translated(self):
        from utils.crontab import crontab as crontab_util
        inst = crontab_util.instance()
        name = inst.humanTaskName('[勿删]御风软件版本在线同步')
        self.assertNotIn('[勿删]', name)
        self.assertTrue(name)
        js = io.open(os.path.join(WEB, 'static', 'app', 'crontab.js'), encoding='utf-8').read()
        self.assertIn('task_name_version_sync', js)


class TestUnifiedVersionSyncTask(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_vs_task_')
        self._orig = (yf.M, yf.writeFileLog, yf.getServerDir, yf.getPanelDir, yf.getPluginDir)
        yf.getServerDir = lambda: os.path.join(self.tmp, 'server')
        yf.getPanelDir = lambda: self.tmp
        yf.getPluginDir = lambda: os.path.join(self.tmp, 'plugins')
        yf.writeFileLog = lambda *a, **k: None
        vs._last_ensure_at[0] = 0.0

    def tearDown(self):
        yf.M, yf.writeFileLog, yf.getServerDir, yf.getPanelDir, yf.getPluginDir = self._orig
        vs._last_ensure_at[0] = 0.0
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_10_ensure_task_migrates_legacy_jdk_task(self):
        legacy = {'id': 5, 'name': '[勿删]御风JDK在线版本同步', 'echo': 'echo_jdk', 'sbody': 'old'}

        fake_db = MagicMock()
        # 第一次查统一任务名 → None；第二次查历史 JDK 任务 → legacy
        fake_db.field.return_value.where.return_value.find.side_effect = [None, legacy]
        old_M = yf.M
        yf.M = MagicMock(return_value=fake_db)

        mock_crontab = MagicMock()
        mock_crontab.add.return_value = 99
        from utils.crontab import crontab as YfCrontab
        old_inst = YfCrontab.instance
        YfCrontab.instance = MagicMock(return_value=mock_crontab)

        try:
            self.assertTrue(vs.ensure_task(force=True))
            # 迁移：不新建任务，而是改名 + 换脚本文案（保住原 id 与用户改过的周期）
            mock_crontab.add.assert_not_called()
            call = yf.M('crontab').where('id=?', (5,)).save.call_args
            # save() 的签名是 save('col1,col2', (v1, v2))（传字典会 TypeError）
            cols, vals = call[0][0], call[0][1]
            saved = dict(zip(cols.split(','), vals))
            self.assertEqual(saved['name'], vs.TASK_NAME)
            self.assertIn('scripts/version_sync.py', saved['sbody'].replace('\\', '/'))
            self.assertIn(' run', saved['sbody'])
            mock_crontab.syncToCrond.assert_called_with(5)
        finally:
            yf.M = old_M
            YfCrontab.instance = old_inst

    def test_11_ensure_task_creates_new_task_when_absent(self):
        fake_db = MagicMock()
        fake_db.field.return_value.where.return_value.find.return_value = None
        old_M = yf.M
        yf.M = MagicMock(return_value=fake_db)

        mock_crontab = MagicMock()
        mock_crontab.add.return_value = 77
        from utils.crontab import crontab as YfCrontab
        old_inst = YfCrontab.instance
        YfCrontab.instance = MagicMock(return_value=mock_crontab)

        try:
            self.assertTrue(vs.ensure_task(force=True))
            mock_crontab.add.assert_called_once()
            params = mock_crontab.add.call_args[0][0]
            self.assertEqual(params['name'], vs.TASK_NAME)
            self.assertEqual(params['type'], 'day')
            self.assertEqual(params['hour'], '2')
            self.assertEqual(params['minute'], '10')
            self.assertIn('version_sync.py', params['sbody'])
        finally:
            yf.M = old_M
            YfCrontab.instance = old_inst

    def test_12_run_collects_all_sources_and_survives_failures(self):
        calls = []

        def _ok():
            calls.append('ok')
            return {'ok': True, 'count': 3, 'lines': ['  - demo ok']}

        def _boom():
            calls.append('boom')
            raise RuntimeError('upstream down')

        old_sources = vs.SOURCES
        vs.SOURCES = (('a', '源A', _ok), ('b', '源B', _boom))
        try:
            results, lines = vs.run()
        finally:
            vs.SOURCES = old_sources

        self.assertEqual(calls, ['ok', 'boom'])
        self.assertEqual([r[0] for r in results], ['a', 'b'])
        self.assertTrue(results[0][1])
        self.assertFalse(results[1][1])
        self.assertIn('upstream down', results[1][2])
        # 核心模块不 print（web 代码质量棘轮），输出通过返回的行交给 CLI
        self.assertTrue(any('demo ok' in line for line in lines))

    def test_13_openresty_source_sync_generates_script(self):
        plugin_dir = os.path.join(self.tmp, 'plugins', 'openresty')
        os.makedirs(plugin_dir, exist_ok=True)
        data_dir = os.path.join(self.tmp, 'data')
        res = idx.sync_versions(plugin_dir, data_dir,
                                fetcher=lambda url, timeout=None: SAMPLE_PAGE,
                                now=1000)
        self.assertEqual(res['latest'], '1.31.9.1')
        self.assertTrue(res['script'])
        self.assertTrue(os.path.isfile(res['script']))
        self.assertEqual(res['error'], '')

        # 抓取失败时仍要返回可用的兜底结论（内置表），且把错误如实带出
        def _boom(url, timeout=None):
            raise IOError('dns fail')

        res2 = idx.sync_versions(plugin_dir, data_dir, fetcher=_boom, now=2000)
        self.assertEqual(res2['latest'], '1.31.9.1')
        self.assertIn('dns fail', res2['error'])

    def test_14_crontab_find_normalizes_spaced_column_keys(self):
        """面板 DB 多列查询会给后续列名带前导空格，不归一化会让 sbody 永远读不到。"""
        fake_db = MagicMock()
        fake_db.field.return_value.where.return_value.find.return_value = {
            'id': 5, ' name': '[勿删]测试', ' echo': 'echo_x', ' sbody': 'body'}
        old_M = yf.M
        yf.M = MagicMock(return_value=fake_db)
        try:
            row = vs._crontab_find('[勿删]测试')
            self.assertIsNotNone(row)
            self.assertEqual(row['id'], 5)
            self.assertEqual(row['name'], '[勿删]测试')
            self.assertEqual(row['sbody'], 'body')
        finally:
            yf.M = old_M


if __name__ == '__main__':
    unittest.main()
