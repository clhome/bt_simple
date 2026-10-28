# coding: utf-8
"""Redis「3 个系列 + 自动取最新补丁版 + 同大版本可升级」守卫（2026-10-28 用户需求）。

## 需求原文（用户口径）

    12 个三位版本号直接精简为 3 个系列：
      Redis 7.2（经典稳定 / 纯开源协议 / 生产首选）← 默认推荐
      Redis 8.2（LTS / 长期演进 / 支持新特性）
      Redis 6.2（极简轻量 / 适合 512MB 内存机器）
    面板底层逻辑：用户选 7.2 时，面板自动去拉 7.2.x（如当前最新的 7.2.17）安装；
    以后无论上游发多少补丁，前端一行都不用改。
    注意：要考虑老用户的升级情况，相同大版本支持升级。

## 用户当面确认的三条边界（2026-10-28）

  1. 已装版本不在 3 个系列里 → 标「已不在列表」；**只有当同大版本存在更高版本时**
     才给「升级到 X」入口（7.4.8 / 8.4.2 / 8.6.3 **不降级**；4.x / 5.x 无同大版本系列）；
  2. 本轮必须实现**真正的**同大版本升级（旧行为是「点更新只自愈、不换二进制」＝假成功）；
  3. 系列→补丁版的解析 = 在线索引 + 12h 缓存 + 内置兜底。

## 本文件守什么

  * `plugins/redis/info.json` 只有 3 个系列 + 默认系列；
  * `web/core/redis_release_index.py` 的纯逻辑（数值排序、RC 排除、缓存/兜底、
    `series_state` 的状态矩阵）；
  * `plugins/redis/install.sh` 的真升级（显式开关、先备份后换 bin、失败回滚、
    拒绝跨主版本、拒绝降级、装后回读版本）；
  * `web/utils/plugin.py` 的接入（系列解析、`YF_REDIS_ALLOW_UPGRADE`、
    任务标题系列匹配）；
  * 前端 `soft.js`：预选推荐系列、说明文案、`series_update` 入口；
  * i18n 键在 6 种语言里都齐全。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
REDIS_DIR = os.path.join(ROOT, 'plugins', 'redis')
REDIS_INFO = os.path.join(REDIS_DIR, 'info.json')
REDIS_INSTALL = os.path.join(REDIS_DIR, 'install.sh')
REDIS_INDEX = os.path.join(REDIS_DIR, 'index.py')
PLUGIN_PY = os.path.join(ROOT, 'web', 'utils', 'plugin.py')
SOFT_JS = os.path.join(ROOT, 'web', 'static', 'app', 'soft.js')
PANEL_TASK = os.path.join(ROOT, 'panel_task.py')
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
LANGUAGES = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

SERIES = ['7.2', '8.2', '6.2']
# 2026-10-28 从 download.redis.io/releases/ 实查（内置兜底表就是这几个）
LATEST = {'7.2': '7.2.17', '8.2': '8.2.11', '6.2': '6.2.24'}

if WEB not in sys.path:
    sys.path.insert(0, WEB)


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _code_only(text):
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            out.append('')
            continue
        cut = -1
        for idx, ch in enumerate(line):
            if ch == '#' and (idx == 0 or line[idx - 1] in ' \t;'):
                cut = idx
                break
        out.append(line if cut < 0 else line[:cut])
    return '\n'.join(out)


def _rri():
    from core import redis_release_index
    return redis_release_index


def _plugin_ns(data_dir=None):
    """取 plugin.py 里「MySQL/MariaDB + Redis 系列」那段纯函数（不加载 flask/DB）。"""
    src = _read(PLUGIN_PY)
    start = src.index('MYSQL_MIN_INSTALL_BRANCH')
    end = src.index('class plugin(object):')

    class _Yf(object):
        def getPanelDataDir(self):
            return data_dir or ''

    class _Log(object):
        def debug(self, *a, **kw):
            pass

        def warning(self, *a, **kw):
            pass

        def info(self, *a, **kw):
            pass

    ns = {
        're': re, 'time': __import__('time'), 'PHP_MIN_INSTALL_BRANCH': '82',
        'yf': _Yf(), '_log': _Log(), 'logging': __import__('logging'),
    }
    exec(compile(src[start:end], PLUGIN_PY, 'exec'), ns)
    return ns


class TestRedisSeriesList(unittest.TestCase):
    """商店里只允许出现 3 个系列。"""

    def test_01_only_three_series(self):
        info = json.loads(_read(REDIS_INFO))
        self.assertEqual(SERIES, info['versions'],
                         'Redis 安装列表应只剩 7.2 / 8.2 / 6.2 三个系列')

    def test_02_no_patch_version_in_list(self):
        """`versions` 里不能出现三段式补丁版 —— 否则上游发版就要改前端。"""
        info = json.loads(_read(REDIS_INFO))
        for ver in info['versions']:
            self.assertRegex(ver, r'^\d+\.\d+$',
                             '%r 是三段式补丁版：前端会被迫跟着上游发版' % ver)

    def test_03_default_is_7_2(self):
        info = json.loads(_read(REDIS_INFO))
        self.assertEqual('7.2', info.get('version_default'), '默认推荐必须是 Redis 7.2')
        self.assertTrue(info.get('version_series'), '必须声明 version_series')
        self.assertEqual('7.2', info['versions'][0], '7.2 应排在最前（默认选中项）')

    def test_04_notes_key_per_series(self):
        info = json.loads(_read(REDIS_INFO))
        notes = info.get('version_notes') or {}
        for series in SERIES:
            self.assertIn(series, notes, '%s 缺少系列说明文案的 i18n 键' % series)
            self.assertTrue(str(notes[series]).startswith('soft.'),
                            '%s 的说明必须是 soft.* i18n 键（不能是硬编码中文）' % series)


class TestRedisI18nKeys(unittest.TestCase):

    KEYS = {
        'soft': ['recommended', 'redis_series_72', 'redis_series_82',
                 'redis_series_62', 'series_patch_update_tip'],
        'plugin': ['series_resolve_fail'],
    }

    def test_01_carriers_have_keys(self):
        for lang in LANGUAGES:
            for section, keys in self.KEYS.items():
                data = json.loads(_read(os.path.join(LANG_DIR, lang, 'template.soft.json')))
                sec = data.get(section) or {}
                for key in keys:
                    self.assertIn(key, sec, '%s/template.soft.json 缺 %s.%s'
                                  % (lang, section, key))
                    self.assertTrue(str(sec[key]).strip(),
                                    '%s 的 %s.%s 是空值' % (lang, section, key))

    def test_02_lan_js_source_has_keys(self):
        """lan.js 是单一真源，键必须先落在这里（否则下次派生就丢了）。"""
        for lang in LANGUAGES:
            src = _read(os.path.join(LANG_DIR, lang, 'lan.js'))
            for section, keys in self.KEYS.items():
                for key in keys:
                    self.assertIn('"%s"' % key, src,
                                  '%s/lan.js 缺 %s.%s' % (lang, section, key))


class TestReleaseIndexPure(unittest.TestCase):
    """解析/排序/兜底：最容易写错的是字符串排序与 RC 混入。"""

    #: 刻意混入 RC、两段版本、以及「字典序会判反」的组合
    HTML = """
    <a href="redis-7.2.9.tar.gz">redis-7.2.9.tar.gz</a>
    <a href="redis-7.2.17.tar.gz">redis-7.2.17.tar.gz</a>
    <a href="redis-7.2.0-rc1.tar.gz">redis-7.2.0-rc1.tar.gz</a>
    <a href="redis-8.2.11.tar.gz">redis-8.2.11.tar.gz</a>
    <a href="redis-8.10.3.tar.gz">redis-8.10.3.tar.gz</a>
    <a href="redis-6.2.24.tar.gz">redis-6.2.24.tar.gz</a>
    <a href="redis-1.2.tar.gz">redis-1.2.tar.gz</a>
    """

    def test_01_parse_excludes_prerelease(self):
        rri = _rri()
        vers = rri.parse_listing(self.HTML)
        self.assertNotIn('7.2.0-rc1', vers, 'RC 版本不能进候选')
        self.assertNotIn('1.2', vers, '两段版本不是补丁版')
        self.assertIn('7.2.17', vers)

    def test_02_numeric_max_not_lexicographic(self):
        rri = _rri()
        got = rri.pick_by_series(rri.parse_listing(self.HTML), SERIES)
        self.assertEqual('7.2.17', got.get('7.2'),
                         '7.2.9 与 7.2.17 必须按数值取最大（字典序会取到 7.2.9）')
        # 8.10.3 属于系列 8.10，不在请求的 3 个系列里 → 不能污染 8.2
        self.assertEqual('8.2.11', got.get('8.2'),
                         '8.10.3 不能算进 8.2（字典序下 8.10<8.2 会判反）')
        self.assertEqual('6.2.24', got.get('6.2'))

    def test_03_version_tuple_and_compare(self):
        rri = _rri()
        self.assertEqual((7, 2, 17), rri.version_tuple('7.2.17'))
        self.assertEqual((7, 2, 0), rri.version_tuple('7.2'))
        self.assertEqual((), rri.version_tuple('redis'))
        self.assertEqual(7, rri.major_of('7.4.8'))
        self.assertEqual('7.4', rri.series_of('7.4.8'))
        self.assertTrue(rri.is_newer('7.2.17', '7.2.9'))
        self.assertFalse(rri.is_newer('7.2.9', '7.2.17'))
        self.assertFalse(rri.is_newer('7.2.17', '7.2.17'))
        self.assertFalse(rri.is_newer('x', '7.2.17'), '判不了必须返回 False，不能猜')

    def test_04_resolve(self):
        rri = _rri()
        mapping = {'7.2': '7.2.17'}
        self.assertEqual('7.2.17', rri.resolve('7.2', SERIES, mapping))
        self.assertEqual('7.2.9', rri.resolve('7.2.9', SERIES, mapping),
                         '用户显式指定补丁版时尊重它')
        self.assertEqual('7.2.17', rri.resolve('7.2', SERIES, {}),
                         '索引为空时必须回退内置表')
        self.assertEqual('', rri.resolve('9.9', SERIES, {}),
                         '未知系列必须返回空串（否则会拼出 redis-.tar.gz）')
        self.assertEqual('', rri.resolve('', SERIES, mapping))
        self.assertEqual('', rri.resolve('7.2.17-rc1', SERIES, mapping))

    def test_05_series_state_matrix(self):
        rri = _rri()
        expect = {
            # 同系列有补丁版 → update
            '7.2.13': ('update', '7.2.17'),
            '6.2.21': ('update', '6.2.24'),
            '8.2.5': ('update', '8.2.11'),
            # 已是最新 → 无提示
            '7.2.17': ('', ''),
            '6.2.24': ('', ''),
            '8.2.11': ('', ''),
            # 系列已下架，但同大版本里有更高版本 → removed + 可升级
            '7.0.15': ('removed', '7.2.17'),
            '6.0.20': ('removed', '6.2.24'),
            '8.0.6': ('removed', '8.2.11'),
            # 比在售系列都新 → 只标，不降级
            '7.4.8': ('removed', ''),
            '8.4.2': ('removed', ''),
            '8.6.3': ('removed', ''),
            # 无同大版本系列 → 只标
            '4.0.14': ('removed', ''),
            '5.0.14': ('removed', ''),
            '': ('', ''),
        }
        mapping = dict(LATEST)
        for cur, want in expect.items():
            got = rri.series_state(cur, SERIES, mapping)
            self.assertEqual(want, got, '已装 %r 的提示应为 %r，实际 %r'
                             % (cur, want, got))

    def test_06_series_state_prefers_closest_series(self):
        """同主版本有多个在售系列时，取「最接近」的那个（跨度最小）。"""
        rri = _rri()
        got = rri.series_state('7.2.1', ['7.2', '7.4'], {'7.2': '7.2.17', '7.4': '7.4.8'})
        self.assertFalse(got[0] == 'removed' and got[1] == '7.4.8',
                         '7.2.1 属于在售系列 7.2，不应该被推到 7.4')


class TestReleaseIndexCache(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_redis_idx_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fetch_ok(self, url, timeout=None):
        return ('<a href="redis-7.2.17.tar.gz">x</a>'
                '<a href="redis-8.2.11.tar.gz">x</a>'
                '<a href="redis-6.2.24.tar.gz">x</a>')

    def test_01_refresh_online_then_cache(self):
        rri = _rri()
        mapping, info = rri.refresh(self.tmp, SERIES, fetcher=self._fetch_ok, now=1000)
        self.assertTrue(info['online'])
        self.assertEqual('online', info['source'])
        self.assertEqual('7.2.17', mapping['7.2'])
        self.assertTrue(os.path.isfile(rri.index_path(self.tmp)), '必须落缓存')

        offline, meta = rri.offline_index(self.tmp, SERIES, now=1000 + 60)
        self.assertEqual(mapping, offline)
        self.assertTrue(meta['fresh'])

    def test_02_offline_falls_back_to_builtin(self):
        rri = _rri()
        mapping, info = rri.refresh(self.tmp, SERIES, fetcher=lambda u, t=None: '', now=1000)
        self.assertFalse(info['online'])
        self.assertEqual('builtin', info['source'])
        self.assertEqual(LATEST, mapping, '无网且无缓存时必须用内置表')
        self.assertTrue(info['error'], '离线必须留痕（不能静默）')

    def test_03_hijack_page_is_failure_not_empty(self):
        """200 但内容解析不出 = 内网认证页/网关劫持，必须报错并回退，不能当成「没有新版」。"""
        rri = _rri()
        portal = '<html><body>请先登录上网认证</body></html>'
        mapping, info = rri.refresh(self.tmp, SERIES, fetcher=lambda u, t=None: portal, now=5)
        self.assertFalse(info['online'])
        self.assertEqual(LATEST, mapping)
        self.assertIn('无法解析', info['error'])

    def test_04_stale_cache_still_beats_builtin(self):
        rri = _rri()
        rri.refresh(self.tmp, SERIES, fetcher=self._fetch_ok, now=1000)
        # 远超 TTL 且此时断网：仍应沿用缓存里的 7.2.17（而不是丢回内置表）
        later = 1000 + rri.DEFAULT_TTL * 3
        mapping, info = rri.refresh(self.tmp, SERIES, fetcher=lambda u, t=None: '', now=later)
        self.assertEqual('7.2.17', mapping['7.2'])
        self.assertEqual('cache', info['source'])

    def test_05_dirty_cache_ignored(self):
        rri = _rri()
        path = rri.index_path(self.tmp)
        with io.open(path, 'w', encoding='utf-8') as fh:
            json.dump({'schema': rri.SCHEMA,
                       'series': {'7.2': {'version': '8.2.11', 'fetched_at': 1}}}, fh)
        self.assertEqual({}, rri.load_cache(path),
                         '系列与版本号对不上的缓存必须丢弃')

    def test_06_save_cache_atomic_and_safe(self):
        rri = _rri()
        ok = rri.save_cache(os.path.join(self.tmp, 'x.json'), {'7.2': '7.2.17'}, now=1)
        self.assertTrue(ok)
        # 目标目录不存在：返回 False 但**绝不抛异常**（缓存失败不能拖垮安装）
        self.assertFalse(rri.save_cache(os.path.join(self.tmp, 'no', 'x.json'),
                                        {'7.2': '7.2.17'}))
        self.assertEqual({}, rri.load_cache(os.path.join(self.tmp, 'no', 'x.json')))


class TestRedisInstallScript(unittest.TestCase):
    """真升级的硬约束：显式开关、先备份、可回滚、拒绝降级/跨主版本。"""

    def setUp(self):
        self.code = _code_only(_read(REDIS_INSTALL))

    def test_01_series_resolution(self):
        self.assertIn('_yf_redis_resolve_version', self.code,
                      'install.sh 必须能兜底解析系列号（面板外直接调用时才不会拼空包）')
        self.assertIn('resolve_version', self.code)
        self.assertIn('无法把系列号', self.code, '解析失败必须明确报错')

    def test_02_version_gate_still_blocks_empty(self):
        self.assertIn('拒绝拼 redis-.tar.gz', self.code)
        self.assertRegex(self.code, r"\*\.\.\*", '必须挡住 7..2 这类空段落版本号')

    def test_03_upgrade_needs_explicit_switch(self):
        self.assertIn('YF_REDIS_ALLOW_UPGRADE', self.code,
                      '换二进制必须有显式开关（防误点/脚本误调）')
        idx = self.code.index('YF_REDIS_ALLOW_UPGRADE')
        self.assertLess(self.code.index('_yf_redis_upgrade "${_cur_ver}"'),
                        len(self.code))
        self.assertIn('请在软件商店里点', self.code[idx:idx + 400],
                      '没有开关时要告诉用户正确入口')

    def test_04_backup_before_swap(self):
        self.assertIn('_yf_redis_upgrade()', self.code)
        i_bak = self.code.index('redis_${from}_to_${to}_')
        i_mv = self.code.index('mv "${serverPath}/redis/bin" "${prev_bin}"')
        self.assertLess(i_bak, i_mv, '必须先备份再动 bin')
        # 备份必须**真的执行**（不只是写了「备份失败」的文案），且备份包要回验
        seg = self.code[i_bak:i_mv]
        self.assertIn('tar -czf "${bak}" -C "${serverPath}" redis/data redis/redis.conf', seg,
                      '备份命令不见了（只留下失败文案 = 假守卫）')
        self.assertIn('tar -tzf "${bak}"', seg, '备份包必须回验（-s + tar -tzf），不能只看 tar 返回码')
        self.assertIn('备份失败', seg)
        i_upg = self.code.index('_yf_redis_upgrade()')
        self.assertIn('df -Pk', self.code[i_upg:i_mv], '备份前必须查磁盘空间')

    def test_05_rollback(self):
        idx = self.code.index('升级失败，正在回滚到')
        tail = self.code[idx:idx + 900]
        self.assertIn('mv "${prev_bin}" "${serverPath}/redis/bin"', tail,
                      '回滚没有把旧 bin 换回来')
        self.assertIn('index.py" start', tail, '回滚后没有把旧版本启动起来')

    def test_06_refuse_cross_major_and_downgrade(self):
        self.assertIn('_yf_redis_ver_gt', self.code, '缺少版本数值比较')
        self.assertIn('拒绝跨主版本升级', self.code)
        self.assertIn('拒绝降级', self.code)
        self.assertIn('读不了新版本写出的 RDB', self.code,
                      '拒绝降级要说明原因（不是随便拒）')

    def test_07_verify_binary_after_swap(self):
        self.assertIn('升级后二进制版本回读不符', self.code,
                      '换完 bin 必须回读 redis-server -v，不能只看启动成功')

    def test_08_keeps_content_verification(self):
        """下载校验不能因为这次重排而丢掉（下载/解压失败必须中止）。"""
        self.assertIn('gzip -t', self.code)
        self.assertIn('解压 ${file_tgz} 失败', self.code)
        self.assertIn('安装产物缺失', self.code)

    def test_09_same_version_only_selfheals(self):
        self.assertIn('== "${VERSION}"', self.code,
                      '同版本必须走自愈分支（不编译、不换 bin）')

    def test_10_conf_from_plugin_tpl(self):
        """新装时配置模板必须用绝对路径：旧写法依赖 cwd，会生成 0 字节 redis.conf。"""
        self.assertIn('${curPath}/config/redis.conf', self.code)


class TestRedisIndexPy(unittest.TestCase):

    def test_01_resolve_entry_wired(self):
        src = _read(REDIS_INDEX)
        self.assertIn('def resolveVersion(', src)
        self.assertIn("func == 'resolve_version'", src)
        self.assertIn('def getSeriesList(', src)
        self.assertIn("'/info.json'", src, '系列列表必须从 info.json 取（单一真源）')

    def test_02_version_pl_fallback_not_series(self):
        """没有二进制时的兜底不能把系列号（7.2）写进 version.pl。"""
        src = _read(REDIS_INDEX)
        idx = src.index('def detectAndFixVersion(')
        body = src[idx:src.index('def getConfTpl(')]
        self.assertIn('offline_index', body,
                      '兜底必须解析成具体补丁版，且不能联网（status 路径会反复调用）')


class TestPluginPyIntegration(unittest.TestCase):

    def test_01_series_plugins_whitelist(self):
        ns = _plugin_ns()
        self.assertEqual(('redis',), ns['SERIES_INDEX_PLUGINS'])

    def test_02_series_helpers(self):
        ns = _plugin_ns()
        self.assertTrue(ns['_is_series_text']('7.2'))
        self.assertFalse(ns['_is_series_text']('7.2.17'))
        self.assertEqual('7.2', ns['_series_of_text']('7.2.13'))
        self.assertEqual('', ns['_series_of_text']('7'))

    def test_03_series_prefix_match(self):
        """任务标题带补丁版（7.2.17）、列表声明系列号（7.2）——必须判为同一行。"""
        ns = _plugin_ns()
        m = ns['_series_prefix_match']
        self.assertTrue(m('7.2.17', '7.2'))
        self.assertFalse(m('6.20.1', '6.2'), '按字符串前缀会把 6.20.1 误判成 6.2')
        self.assertFalse(m('7.2', '7.2'), '长度不足时由 == 分支负责')
        self.assertFalse(m('7.3.1', '7.2'))

    def test_04_series_list_of(self):
        ns = _plugin_ns()
        got = ns['_series_list_of']({'versions': ['7.2', '8.2', '7.2', '']})
        self.assertEqual(['7.2', '8.2'], got)
        self.assertEqual(['9.9'], ns['_series_list_of']({'versions': '9.9'}))
        self.assertEqual([], ns['_series_list_of']({}))

    def test_05_state_of_reads_cache_offline(self):
        """`_series_state_of` 走离线索引（列表页不许等网络）。"""
        tmp = tempfile.mkdtemp(prefix='yf_redis_state_')
        try:
            rri = _rri()
            rri.save_cache(rri.index_path(tmp), {'7.2': '7.2.17'}, now=2 ** 31 - 10)
            ns = _plugin_ns(data_dir=tmp)
            self.assertEqual(('update', '7.2.17'),
                             ns['_series_state_of']('redis', '7.2.13', SERIES))
            self.assertEqual(('removed', '7.2.17'),
                             ns['_series_state_of']('redis', '7.0.15', SERIES))
            self.assertEqual(('', ''), ns['_series_state_of']('mysql', '7.2.13', SERIES),
                             '只对声明了 version_series 的插件生效')
            # 列表页是同步渲染路径：不许联网刷新（只能读缓存/内置表）
            src = _read(PLUGIN_PY)
            idx = src.index('def _series_state_of(')
            body = src[idx:idx + 1200]
            self.assertIn('offline_index', body)
            self.assertNotIn('rri.refresh', body,
                             '列表渲染路径不能调 refresh（会为每个列表请求等网络）')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_06_install_passes_upgrade_env(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('YF_REDIS_ALLOW_UPGRADE=1 ', code,
                      'install() 没给 redis 传升级开关，真升级永远不会被触发')

    def test_07_install_resolves_series(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('_redis_resolve_series', code)
        # 必须是 **失败** 返回：改成 True 就等于「报了个错但还是去装空版本包」
        self.assertIn("if not _resolved:", code)
        self.assertIn("return yf.returnData(False, 'plugin.series_resolve_fail',", code,
                      '解析失败必须返回 status=False 的可翻译错误')
        # returnData 的第三个位置参数是 data：插值参数必须写在它之后（前面显式 None），
        # 否则文案里的 {1}/{2} 会原样显示给用户（已踩过）。
        self.assertIn("'plugin.series_resolve_fail',", code)
        self.assertIn('None, version, _cycle)', code,
                      '插值参数必须写在 data 之后（前显式 None）')

    def test_08_hint_hooked_into_list_items(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('self._seriesApplyVersionHint(pInfo)', code)
        self.assertIn('"version_series": bool(info.get', code)
        self.assertIn('"version_default": str(info.get', code)
        self.assertIn('"version_notes": info.get', code)

    def test_09_hint_sets_eol_only_for_removed(self):
        """`series_update` 与 `eol_kind` 不能同时出现（否则界面会给两条升级入口）。"""
        src = _read(PLUGIN_PY)
        idx = src.index('def _seriesApplyVersionHint')
        body = src[idx:idx + 2600]
        self.assertIn("if kind == 'update':", body)
        self.assertIn("elif kind == 'removed':", body)
        self.assertIn("pInfo['eol_kind'] = 'removed'", body)

    def test_10_task_status_matches_series(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('_series_prefix_match(remainder, v)', code,
                      '安装中列表行必须显示「正在安装」（任务标题是补丁版，声明是系列号）')


class TestSoftJsFrontend(unittest.TestCase):

    def setUp(self):
        self.src = _read(SOFT_JS)

    def test_01_install_link_carries_series_meta(self):
        self.assertIn('data-vdefault=', self.src)
        self.assertIn('data-vnotes=', self.src)

    def test_02_option_needs_value_attr(self):
        """选项必须显式带 value：`.val()` 拿不到 value 时会回退文本，
        而文本里现在多了说明与「推荐」，解析 version 会出错。"""
        idx = self.src.index('function addVersion(')
        body = self.src[idx:idx + 3200]
        self.assertIn('<option value="', body)
        self.assertIn("' selected'", body, '默认系列必须预选')
        self.assertIn('vdefault', body)
        self.assertIn('vnotes', body)

    def test_03_recommended_order(self):
        idx = self.src.index('function addVersion(')
        body = self.src[idx:idx + 3200]
        self.assertIn('vdefault ? veropt.slice() : veropt.slice().reverse()', body,
                      '有推荐系列时按声明顺序（7.2 在最前），否则沿用倒序')

    def test_04_series_update_link(self):
        self.assertIn('seriesUpdateLink', self.src)
        self.assertIn('soft.series_patch_update_tip', self.src)
        # 条件必须是「后端给了 series_update 且有 latest」——写成 if (false) 这种
        # 「代码在、入口没了」的形态要能被抓出来
        self.assertIn('if (plugin.series_update && plugin.series_update.latest) {', self.src)
        idx = self.src.index('if (plugin.series_update && plugin.series_update.latest) {')
        body = self.src[idx:idx + 900]
        self.assertIn('softUpdate(', body, '升级入口必须复用会备份/回滚的 softUpdate')
        self.assertIn('plugin.series_update.latest', body)
        self.assertIn('handle = eolBadge + eolUpgradeLink + seriesUpdateLink', self.src,
                      'seriesUpdateLink 必须真的拼进操作列')

    def test_05_generic_compare_disabled_for_series(self):
        self.assertIn("if (plugin.version_series) { mupdate = ''; }", self.src,
                      '系列号与补丁版是两种东西，不能让通用比较再给一条「更新」')


NODE_CANDIDATES = [
    'node',
    r'C:/Users/wzucc/.workbuddy-ai/binaries/node/versions/22.22.2-2/node.exe',
]
ADDV_HARNESS = os.path.join(HERE, 'i18n_scripts', 'tools',
                            'test_soft_addversion_series.js')


def _find_node():
    for cand in NODE_CANDIDATES:
        path = shutil.which(cand) or (cand if os.path.isfile(cand) else None)
        if not path:
            continue
        try:
            r = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if r.returncode == 0:
            return path
    return None


NODE = _find_node()


class TestSoftJsBehavior(unittest.TestCase):
    """安装弹窗的**行为**测试：用 Node 求值 soft.js 里真实的 addVersion。

    源码级 grep 只能证明「代码在」，证明不了「选对了」——选项顺序、预选、
    value 属性这些都要真的跑一遍才算（否则文案里多个「·」就能把版本号解析搞坏）。
    """

    def setUp(self):
        if NODE is None:
            self.skipTest('未找到可用的 node')
        if not os.path.isfile(ADDV_HARNESS):
            self.skipTest('缺少夹具 test_soft_addversion_series.js')

    def _run(self, env_extra=None):
        env = dict(os.environ)
        env.update(env_extra or {})
        return subprocess.run([NODE, ADDV_HARNESS], cwd=ROOT, capture_output=True,
                              text=True, encoding='utf-8', errors='replace',
                              timeout=120, env=env)

    def test_01_harness_passes_on_real_code(self):
        r = self._run()
        msg = (r.stdout or '') + (r.stderr or '')
        self.assertEqual(0, r.returncode, '安装弹窗行为测试未通过：' + msg)

    def test_02_mutation_self_proof_order(self):
        """变异自证：去掉「有推荐系列时按声明顺序」→ 行为测试必须转红。"""
        needle = 'var order = vdefault ? veropt.slice() : veropt.slice().reverse();'
        src = _read(SOFT_JS)
        self.assertEqual(1, src.count(needle), '未能唯一定位选项排序那一行')
        self._assert_mutant_fails(
            src.replace(needle, 'var order = veropt.slice().reverse();'),
            '排序回退成无条件倒序（7.2 不再是第一项）')

    def test_03_mutation_self_proof_selected(self):
        """变异自证：不再预选推荐系列 → 行为测试必须转红。"""
        needle = "(isDefault ? ' selected' : '')"
        src = _read(SOFT_JS)
        self.assertEqual(1, src.count(needle), '未能唯一定位 selected 那一行')
        self._assert_mutant_fails(src.replace(needle, "''"), '不再预选推荐系列')

    def _assert_mutant_fails(self, mutant, what):
        tmpdir = tempfile.mkdtemp(prefix='yf_softmut_')
        try:
            path = os.path.join(tmpdir, 'soft_mutated.js')
            with io.open(path, 'w', encoding='utf-8', newline=chr(10)) as fh:
                fh.write(mutant)
            r = self._run({'YF_SOFT_JS': path})
            self.assertNotEqual(0, r.returncode,
                                '变异体（%s）竟然通过了行为测试 → 断言恒真' % what)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestPanelTaskRefresh(unittest.TestCase):

    def test_01_daily_refresh_registered(self):
        src = _read(PANEL_TASK)
        self.assertIn('def redisReleaseIndex_step(', src)
        self.assertIn('REDIS_RELEASE_INDEX_INTERVAL', src)
        self.assertIn('watchdog_scheduler.add_task(redisReleaseIndex_step,'
                      ' REDIS_RELEASE_INDEX_INTERVAL)', src)

    def test_02_series_read_from_info_json(self):
        src = _read(PANEL_TASK)
        idx = src.index('def _redisSeriesList(')
        body = src[idx:idx + 800]
        self.assertIn('info.json', body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
