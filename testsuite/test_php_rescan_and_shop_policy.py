# coding: utf-8
"""守卫：①「再次巡检」必须真的重扫；② 软件商店 PHP 只提供 8.2 及以上。

## 现场（真机 2026-10-26）

用户把 PHP 7.4 卸了，首页「PHP 安全基线」弹窗里**还挂着**「PHP 74 (apt) 7.4.33
存在风险」，点「立即巡检」也不消失。两个原因叠在一起：

  * 后端 `/get_php_security_status` 走 `load_or_scan()`，快照新鲜度上限是 **26 小时**
    —— 装/卸 PHP 不会删快照，卡片就会一直报已经不存在的版本；
  * 前端的「立即巡检」只传了个空 body，`forceRefresh` 仅绕过**浏览器** sessionStorage，
    后端照旧发旧快照 —— 点一百次也不会变。

另外用户提的第二条：软件商店里 PHP 应该只提供 8.2 及以上；已经装过的旧分支保留在列表
但用红色标「建议升级到 8.2 及以上」；把旧分支删掉之后就不该再出现（旧实现拿
`install_checks` 目录判存，卸载留下的目录会让它永久留在列表里）。

## 本文件守什么

1. `php_sec_scan.load_or_scan(force=True)` 绕过快照并落盘新结果；
2. 路由把 `force` 透传下去，且卡片快照的新鲜度上限明显短于 26 小时；
3. 前端「再次巡检」是按钮、带 `force:1`；
4. PHP 装/卸任务结束后删快照（`panel_task`）；
5. `php_sec_scan.installed_branches()` 一次命令拿全、只认已装（`rc` 不算）；
6. `plugin.applyPhpVersionPolicy()`：未装的 <8.2 分支隐藏；已装的保留并打 `php_eol`；
   ≥8.2 与非 PHP 插件不受影响；
7. 前端软件商店渲染红标；语言包有对应键（6 语言，带 `{1}` 占位）。
"""

import io
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
LANG_ROOT = os.path.join(WEB, 'static', 'language')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import php_sec_scan as scan      # noqa: E402
import utils.plugin as plugin_util         # noqa: E402
from utils import plugin as plugin_mod     # noqa: E402

DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
PANEL_TASK_PY = os.path.join(ROOT, 'panel_task.py')
LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


class ForceRescanTest(unittest.TestCase):
    """`再次巡检` 必须在后端真的重扫，而不是再发一次旧快照。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_rescan_')
        self.snap = os.path.join(self.tmp, 'php_sec_scan.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_scan(self, branch):
        """造一份「只有一个分支」的巡检结果（便于断言换没换）。"""
        def _scan(**kwargs):
            return {'state': 'alarm', 'items': [{'branch': branch, 'channel': 'apt',
                                                 'version': '1.0.0', 'status': 'ok',
                                                 'alarm': False}],
                    'count': 1, 'baseline_date': '2026-10-22', 'offline': False,
                    'scan_time': 1, 'summary': 'x'}
        return _scan

    def test_01_force_bypasses_snapshot(self):
        scan.write_snapshot({'state': 'alarm', 'items': [{'branch': '74'}],
                             'count': 1, 'scan_time': int(time.time())}, self.snap)
        with mock.patch.object(scan, 'scan', side_effect=self._fake_scan('82')):
            data = scan.load_or_scan(self.snap, force=True)
        branches = [i['branch'] for i in data['items']]
        self.assertEqual(branches, ['82'], 'force=True 必须忽略旧快照（旧快照里是 74）')
        with io.open(self.snap, encoding='utf-8') as fp:
            on_disk = json.load(fp)
        self.assertEqual([i['branch'] for i in on_disk['items']], ['82'],
                         '重扫结果必须落盘，否则下一次又是旧的')

    def test_02_without_force_still_uses_snapshot(self):
        scan.write_snapshot({'state': 'alarm', 'items': [{'branch': '74'}],
                             'count': 1, 'scan_time': int(time.time())}, self.snap)
        with mock.patch.object(scan, 'scan', side_effect=AssertionError('不该重扫')):
            data = scan.load_or_scan(self.snap)
        self.assertEqual([i['branch'] for i in data['items']], ['74'],
                         '普通加载应继续读快照（首页不能每次都跑 0.5s 的巡检）')

    def test_03_route_passes_force_and_short_max_age(self):
        src = _read(DASHBOARD_PY)
        start = src.index('def get_php_security_status(')
        body = src[start:start + 2500]
        self.assertIn("request.form.get('force'", body, '路由必须读前端传来的 force')
        self.assertIn('force=force', body, 'force 必须透传给 load_or_scan')
        self.assertIn('max_age=_CARD_SNAPSHOT_MAX_AGE', body,
                      '卡片快照需要更短的新鲜度上限（装/卸 PHP 不会删快照）')
        self.assertRegex(src, r'_CARD_SNAPSHOT_MAX_AGE\s*=\s*\d+')
        limit = int(src.split('_CARD_SNAPSHOT_MAX_AGE =')[1].split('\n')[0].strip() or 0)
        self.assertGreater(limit, 0)
        self.assertLess(limit, scan.DEFAULT_MAX_AGE,
                        '卡片新鲜度上限必须比每日快照的 26 小时短')

    def test_04_frontend_button_sends_force(self):
        src = _read(INDEX_JS)
        self.assertIn("{ force: forceRefresh ? 1 : 0 }", src,
                      '点「再次巡检」必须带 force=1，否则后端还会发旧快照')
        self.assertIn('<button', src)
        self.assertIn('phpSecRescanBtn', src)
        self.assertIn("t('index.php_sec_refresh'", src)
        # 按钮所在容器必须允许换行（长译文下按钮不能被压扁）
        self.assertIn('flex-wrap:wrap', src.replace(' ', ''))

    def test_05_refresh_label_renamed(self):
        for lang in LANGS:
            path = os.path.join(LANG_ROOT, lang, 'template.index.json')
            with io.open(path, encoding='utf-8') as fp:
                data = json.load(fp)
            val = (data.get('index') or {}).get('php_sec_refresh')
            self.assertTrue(val, '%s 缺 index.php_sec_refresh' % lang)
            self.assertNotEqual(val, '立即巡检', '%s 的按钮文案应已改名' % lang)

    def test_06_php_task_drops_snapshot(self):
        src = _read(PANEL_TASK_PY)
        self.assertIn('_isPhpInstallTask(', src, '任务完成时必须判断是不是 PHP 装/卸')
        self.assertIn('_dropPhpSecSnapshot()', src)
        self.assertIn("' install ' in low", src)
        self.assertIn("' uninstall' in low", src)


class InstalledBranchesTest(unittest.TestCase):
    """`installed_branches()`：一次命令拿全，只认「真的装了」。"""

    def _run(self, dpkg_out='', rpm_out='', rc=0):
        def run(argv):
            if argv and argv[0] == 'dpkg-query':
                return rc, dpkg_out
            if argv and argv[0] == 'rpm':
                return rc, rpm_out
            return 127, ''
        return run

    def test_01_compiled_requires_non_empty_binary(self):
        tmp = tempfile.mkdtemp()
        try:
            for branch, size in (('80', 0), ('83', 12)):
                d = os.path.join(tmp, branch, 'bin')
                os.makedirs(d)
                with open(os.path.join(d, 'php'), 'wb') as fp:
                    fp.write(b'x' * size)
            got = scan.installed_branches(server_php_dir=tmp,
                                          run=self._run('', ''))
            self.assertEqual(got['src'], {'83'}, '0 字节 bin/php 不算已装')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_02_apt_ignores_remnant(self):
        out = ('php-fpm un \n'
               'php7.4-fpm rc \n'         # 已卸载只剩配置 → 不算
               'php8.2-fpm ii \n'
               'php8.3-fpm iU \n')        # 已解包待配置 → 算
        got = scan.installed_branches(server_php_dir='/nonexistent',
                                      run=self._run(out))
        self.assertEqual(got['apt'], {'82', '83'})

    def test_03_yum_from_rpm(self):
        got = scan.installed_branches(server_php_dir='/nonexistent',
                                      run=self._run('', 'php83-php-fpm\nbash\nphp74-php-cli\n'))
        self.assertEqual(got['yum'], {'83'})

    def test_04_single_command_per_channel(self):
        calls = []

        def run(argv):
            calls.append(argv[0])
            return 0, ''
        scan.installed_branches(server_php_dir='/nonexistent', run=run)
        self.assertEqual(calls.count('dpkg-query'), 1,
                         '软件商店每次加载都跑，apt 只能起一次命令（不能按版本逐个探）')
        self.assertEqual(calls.count('rpm'), 1)


class ShopPhpPolicyTest(unittest.TestCase):
    """软件商店：只提供 8.2+，已装旧分支保留并打红标。"""

    def _obj(self, installed):
        obj = plugin_mod.plugin.__new__(plugin_mod.plugin)
        obj._phpInstalledBranches = lambda: installed
        return obj

    def _rows(self):
        # 默认按「干净的机器」造：旧分支都没装（setup=False），只装了 8.2/8.3。
        return [
            {'name': 'php-apt', 'versions': '74', 'install_checks': '/x/74', 'setup': False},
            {'name': 'php-apt', 'versions': '82', 'install_checks': '/x/82', 'setup': True},
            {'name': 'php', 'versions': '80', 'install_checks': '/x/80', 'setup': False},
            {'name': 'php', 'versions': '83', 'install_checks': '/x/83', 'setup': True},
            {'name': 'php-yum', 'versions': '74', 'install_checks': '/x/74', 'setup': False},
            {'name': 'mysql', 'versions': '57', 'install_checks': '/x/57', 'setup': True},
        ]

    def test_01_hides_uninstalled_old_branches(self):
        out = self._obj({'src': set(), 'apt': set(), 'yum': set()}).applyPhpVersionPolicy(
            self._rows())
        keys = [(r['name'], r['versions']) for r in out]
        self.assertNotIn(('php-apt', '74'), keys, '未装的 7.4 不该出现在商店里')
        self.assertNotIn(('php', '80'), keys)
        self.assertNotIn(('php-yum', '74'), keys)
        self.assertIn(('php-apt', '82'), keys, '8.2 及以上必须保留')
        self.assertIn(('php', '83'), keys)
        self.assertIn(('mysql', '57'), keys, '非 PHP 插件不受这条策略影响')

    def test_02_keeps_installed_old_branch_with_flag(self):
        out = self._obj({'src': {'80'}, 'apt': {'74'}, 'yum': set()}).applyPhpVersionPolicy(
            self._rows())
        by_key = {(r['name'], r['versions']): r for r in out}
        for key in (('php', '80'), ('php-apt', '74')):
            self.assertIn(key, by_key, '已装的旧分支要保留（否则用户没法卸载）')
            self.assertTrue(by_key[key].get('php_eol'), '%s 必须打上已停维标记' % (key,))
            self.assertEqual(by_key[key].get('php_eol_min'), '8.2')
        self.assertFalse(by_key[('php', '83')].get('php_eol'),
                         '8.3 不该被标成已停维')

    def test_03_installed_dir_keeps_row_with_flag(self):
        """`install_checks` 目录还在（= 面板认为已装）⇒ 保留并打红标。

        宁可多显示一条红标，也不能让用户找不到卸载入口（真机 PHP 8.0 的 `bin/php`
        是 0 字节，但目录与 FPM 都在，用户要能一键跳过去卸载）。
        卸载时面板会删掉这个目录，于是下一次它自然就不显示了。
        """
        rows = self._rows()
        for r in rows:
            r['setup'] = (r['name'], r['versions']) == ('php', '80')
        out = self._obj({'src': set(), 'apt': set(), 'yum': set()}).applyPhpVersionPolicy(rows)
        by_key = {(r['name'], r['versions']): r for r in out}
        self.assertIn(('php', '80'), by_key, '目录还在却把行藏了 → 用户无从卸载')
        self.assertTrue(by_key[('php', '80')].get('php_eol'))
        self.assertNotIn(('php-apt', '74'), by_key, '目录已删且包已卸 → 不再显示')

    def test_04_floor_constant_single_source(self):
        self.assertEqual(plugin_mod.PHP_MIN_INSTALL_BRANCH, '82')
        self.assertEqual(plugin_mod._php_branch_of('82'), 82)
        self.assertEqual(plugin_mod._php_branch_of('8.2'), 82)
        self.assertEqual(plugin_mod._php_branch_of('zz'), 0)
        self.assertTrue(plugin_mod._php_family('php'))
        self.assertTrue(plugin_mod._php_family('php-apt'))
        self.assertTrue(plugin_mod._php_family('php-yum'))
        self.assertFalse(plugin_mod._php_family('mysql'))

    def test_05_policy_wired_into_list(self):
        src = _read(os.path.join(WEB, 'utils', 'plugin.py'))
        self.assertIn('plist = self.applyPhpVersionPolicy(plist)', src,
                      '策略必须真的接进 getAllPluginList，否则等于没写')


class InstallGuardTest(unittest.TestCase):
    """接口层也要拦住「装 8.2 以下」：前端看不到按钮 ≠ 接口调不到。"""

    def _obj(self):
        obj = plugin_mod.plugin.__new__(plugin_mod.plugin)
        obj._phpInstalledBranches = lambda: {'src': set(), 'apt': set(), 'yum': set()}
        return obj

    def test_01_refuses_old_branch(self):
        res = self._obj().install('php-apt', '74')
        self.assertFalse(res['status'])
        self.assertIn('8.2', res['msg'], '要给用户一句能看懂的拒绝理由（提到 8.2）')

    def test_02_allows_supported_branch(self):
        res = self._obj().install('php-apt', '83')
        # 允许安装时应当继续往下走（本机没有该插件目录 → 报「插件不存在」），
        # 关键是不能命中「已停维」的拒绝。
        self.assertNotIn('8.2 以下', res.get('msg') or '')

    def test_03_non_php_plugin_untouched(self):
        res = self._obj().install('mysql', '57')
        self.assertNotIn('8.2', res.get('msg') or '')

    def test_04_info_json_lists_old_branches_for_display(self):
        """info.json 必须列着旧分支，否则「已安装的 8.0/8.1」在商店里彻底消失。

        可见性由 `applyPhpVersionPolicy()` 控制（未装隐藏、已装打红标），
        不能靠删 info.json 的版本号来实现「不提供旧版本」。
        """
        with io.open(os.path.join(plugin_util.ROOT if hasattr(plugin_util, 'ROOT')
                                  else ROOT, 'plugins', 'php', 'info.json'),
                     encoding='utf-8') as fp:
            data = json.load(fp)
        for branch in ('74', '80', '81', '82', '83', '84', '85'):
            self.assertIn(branch, data['versions'],
                          'plugins/php/info.json 缺少 %s（已装的旧分支会不可见）' % branch)


class StoreUpgradeBadgeTest(unittest.TestCase):
    """已停维分支不得在商店里露「可更新 / 升级到 8.1.34」——那是一条死路。

    真机现场：PHP-81 8.1.33 挂着「可更新」+「升级到 8.1.34」，点了编译十几分钟，
    最后报「PHP81 没有编译版安全基线，请改用 APT/YUM 渠道升级」。两头都不对：
    8.1.34 同样不含本次 CVE 的修复；「改用 APT/YUM」对普通用户也不是可执行动作。
    """

    def test_01_update_for_skips_eol_branch(self):
        from core import php_release_index as rel
        index = {'81': {'version': '8.1.34', 'sha256': 'a' * 64, 'source': 'php.net'},
                 '82': {'version': '8.2.35', 'sha256': 'b' * 64, 'source': 'php.net'}}
        self.assertIsNone(rel.update_for('8.1.33', '81', index),
                         '8.1 已停维，不该给出「升级到 8.1.34」的目标')
        self.assertIsNone(rel.update_for('8.0.30', '80', index))
        info = rel.update_for('8.2.30', '82', index)
        self.assertIsNotNone(info, '8.2 是维护中的分支，仍要给可更新提示')
        self.assertEqual(info['latest'], '8.2.35')

    def test_02_annotate_items_no_badge_for_eol(self):
        from core import php_release_index as rel
        index = {'81': {'version': '8.1.34', 'sha256': 'a' * 64},
                 '82': {'version': '8.2.35', 'sha256': 'b' * 64}}
        items = [{'name': 'php', 'versions': '81', 'setup': True},
                 {'name': 'php-apt', 'versions': '82', 'setup': True}]
        installed = [{'branch': '81', 'channel': 'src', 'version': '8.1.33'},
                     {'branch': '82', 'channel': 'apt', 'version': '8.2.30'}]
        out = rel.annotate_items(items, installed, index)
        by = {i['versions']: i for i in out}
        self.assertFalse(by['81'].get('php_update_available'),
                         '8.1 不许挂「可更新」徽标')
        self.assertNotIn('php_update', by['81'])
        self.assertEqual(by['81'].get('php_current_version'), '8.1.33',
                         '当前版本仍要带上（界面展示用）')
        self.assertTrue(by['82'].get('php_update_available'))
        self.assertEqual(by['82']['php_update']['latest'], '8.2.35')

    def test_03_plugin_message_tells_you_to_migrate(self):
        src = _read(os.path.join(ROOT, 'plugins', 'php', 'index.py'))
        self.assertIn('官方已停止维护，本次漏洞不会再修复', src)
        self.assertIn('卸载该版本并升级到 PHP 8.2 及以上', src)
        self.assertNotIn('请改用 APT/YUM 渠道升级', src,
                         '别再让用户「改用 APT/YUM」——那是内部渠道名，不是可执行动作')
        # getUpgradeTarget 对已停维分支直接返回空
        start = src.index('def getUpgradeTarget(')
        body = src[start:start + 1600]
        self.assertIn("return ('', '', '')", body)
        self.assertIn('MIGRATION_MIN_BRANCH', body)

    def test_04_lang_key_replaced_in_all_languages(self):
        old = 'PHP%s 没有编译版安全基线，请改用 APT/YUM 渠道升级'
        new = 'PHP%s 官方已停止维护，本次漏洞不会再修复：请卸载该版本并升级到 PHP 8.2 及以上'
        for lang in LANGS:
            path = os.path.join(ROOT, 'plugins', 'php', 'lang', '%s.json' % lang)
            with io.open(path, encoding='utf-8') as fp:
                data = json.load(fp)
            self.assertNotIn(old, data, '%s 还留着旧话术' % lang)
            self.assertIn(new, data, '%s 缺新话术（外语界面会漏翻）' % lang)
            self.assertIn('8.2', data[new])


class MigrateAdviceJumpTest(unittest.TestCase):
    """首页「建议卸载该版本并升级到 PHP 8.2 及以上」必须能一步跳到该版本的卸载入口。"""

    def test_01_advice_is_a_link_to_the_store(self):
        src = _read(INDEX_JS)
        self.assertIn("class=\"f11 php-sec-migrate\"", src)
        self.assertNotIn("class=\"f11 php-sec-migrate\" style=\"margin-left:auto; color:#fa8c16; font-weight:600;\">",
                         src, '仍是不带链接的 span，点不动')
        self.assertIn("'/plugins/index?soft_type=0&soft_search=php'", src,
                      '必须带上商店的定位参数（类型 + 搜索，保证目标行在第一页）')
        self.assertIn("encodeURIComponent(item.plugin || '')", src)
        self.assertIn("encodeURIComponent(item.branch || '')", src,
                      '插件名/分支必须编码后再拼 URL')

    def test_02_soft_js_can_focus_a_version_row(self):
        src = _read(SOFT_JS)
        self.assertIn('data-version="', src,
                      '行上必须有 data-version：coexist 插件的每行 data-name 相同，只有版本能区分')
        self.assertIn('function softFocusTarget(', src)
        self.assertIn('softFocusTarget();', src,
                      '渲染完之后必须调用定位函数')
        self.assertIn("q.soft_name", src)
        self.assertIn("data-version=\"' + ver + '\"", src)
        # 参数白名单：不能把任意字符串拼进选择器/或当作插件名请求 /plugins/setting
        self.assertIn('/^[A-Za-z0-9_-]{1,64}$/', src)
        self.assertIn('/^[A-Za-z0-9._-]{1,32}$/', src)

    def test_03_bootstrap_presets_type_and_search(self):
        src = _read(SOFT_JS)
        self.assertIn("setCookie('soft_type', q.soft_type)", src)
        self.assertIn('$("#SearchValue").val(q.soft_search)', src)

    @unittest.skipIf(not shutil.which('node'), '本机没有 node，跳过解析用例')
    def test_04_query_params_parse(self):
        script = (
            "const fs=require('fs');"
            "const src=fs.readFileSync(process.env.YF_SOFT_JS,'utf8');"
            "function grab(n){const s=src.indexOf('function '+n+'(');let d=0;"
            "for(let i=src.indexOf('{',s);i<src.length;i++){if(src[i]==='{')d++;"
            "else if(src[i]==='}'){d--;if(!d)return src.slice(s,i+1);}}}"
            "global.location={search:'?soft_type=0&soft_search=php&soft_name=php-apt&soft_version=74'};"
            "const f=new Function(grab('softQueryParams')+chr+'return softQueryParams;'+chr)();"
            "console.log(JSON.stringify(f()));"
        ).replace('chr', repr(chr(10)))
        env = dict(os.environ)
        env['YF_SOFT_JS'] = SOFT_JS
        proc = subprocess.run([shutil.which('node'), '-e', script], capture_output=True,
                              encoding='utf-8', errors='replace', timeout=60, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(data.get('soft_name'), 'php-apt')
        self.assertEqual(data.get('soft_version'), '74')
        self.assertEqual(data.get('soft_search'), 'php')


class ShopBadgeFrontendTest(unittest.TestCase):
    """软件商店红标 + 语言包键。"""

    def test_01_soft_js_renders_badge(self):
        src = _read(SOFT_JS)
        self.assertIn('php_eol', src)
        self.assertIn('php-eol-badge', src)
        self.assertIn("t('soft.php_eol'", src)
        self.assertIn("t('soft.php_eol_tip'", src)

    def test_02_i18n_keys_with_placeholder(self):
        for lang in LANGS:
            for carrier in ('template.soft.json', 'template.json'):
                path = os.path.join(LANG_ROOT, lang, carrier)
                with io.open(path, encoding='utf-8') as fp:
                    data = json.load(fp)
                soft = data.get('soft') or {}
                if carrier == 'template.json' and 'php_upgradable' not in soft:
                    continue
                self.assertIn('php_eol', soft, '%s/%s 缺 soft.php_eol' % (lang, carrier))
                self.assertIn('{1}', soft['php_eol'],
                              '%s/%s 的 soft.php_eol 必须用 {1} 占位' % (lang, carrier))
                self.assertTrue(soft.get('php_eol_tip'), '%s/%s 缺 soft.php_eol_tip'
                                % (lang, carrier))


if __name__ == '__main__':
    unittest.main(verbosity=2)
