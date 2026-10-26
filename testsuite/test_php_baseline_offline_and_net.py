# coding: utf-8
"""守卫：apt/yum 渠道「升级到安全基线」的**失败诊断**与**离线 .deb 通道**。

## 现场（2026-10-26，真机 172.17.60.248）

用户点「PHP8.4 升级到安全基线 8.4.27」，任务日志是：

    错误:1 https://mirror.sjtu.edu.cn/sury/php bookworm InRelease
      Certificate verification failed: The certificate is NOT trusted. The certificate
      issuer is unknown. The name in the certificate does not match the expected.
    ...
    W: 部分索引文件下载失败。如果忽略它们，那将转而使用旧的索引文件。
    升级了 0 个软件包 ... 有 182 个软件包未被升级。

    {"status": false, "msg": "升级失败: 升级后版本 8.4.25 仍低于基线 8.4.27，...
    自动回退成功；apt 报告 0 upgraded / 0 newly installed（源里没有比 8.4.25 更新的包），
    请检查 /etc/apt/sources.list 与 sury 源，并确认 apt-get update 成功"}

三个真问题（本文件逐条钉死）：

  1. **诊断错位**：`curl http://任意域名/` 会 302 到内网门户 `http://172.17.1.121`，
     `https://` 被换成网关自签证书（实测 `CN=demotest.doctorcom.com`）——是**本机外网
     被上网认证网关劫持**，报文却让用户去「检查 sources.list 与 sury 源」，改一天也改不好；
  2. **假回退**：一个包都没升（`before_pkg == after_pkg`）时，回退是空操作，
     报文却写「自动回退成功」，还附上一条「把当前版本再装一遍」的回退命令；
  3. **没有出路**：内网/无外网机器上 apt 永远升不动，而编译版早就有离线源码通道
     （`data/php_src/`），apt 渠道却一条离线通道都没有。

## 本文件守什么

* `web/core/net_probe.py` 的分类/结论/处置（**注入式探测**，全程不联网）；
* `web/core/php_deb_bundle.py` 的纯函数：包归属、锚定依赖解析、离线包预检、
  apt 模拟输出解析与「要卸载就中止」的判据、自建 Packages 索引段落、apt 参数覆盖；
* `plugins/php-{apt,yum}/index.py` 的接线：刷新失败必须带诊断、诊断必须写进任务日志、
  离线通道必须**先模拟再真跑**、失败报文不许再出现「自动回退成功」这种假话。
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
PLUGINS = os.path.join(ROOT, 'plugins')
APT_PY = os.path.join(PLUGINS, 'php-apt', 'index.py')
YUM_PY = os.path.join(PLUGINS, 'php-yum', 'index.py')
NET_PROBE_PY = os.path.join(WEB, 'core', 'net_probe.py')
DEB_BUNDLE_PY = os.path.join(WEB, 'core', 'php_deb_bundle.py')

if WEB not in sys.path:
    sys.path.insert(0, WEB)

from core import net_probe as np_          # noqa: E402
from core import php_deb_bundle as deb    # noqa: E402


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def _body(src, start_marker, end_marker):
    start = src.index(start_marker)
    return src[start:src.index(end_marker, start)]


#: 真机现场原文（截断），分类判据就按这个来。
APT_TLS_FAIL = """错误:1 https://mirror.sjtu.edu.cn/sury/php bookworm InRelease
  Certificate verification failed: The certificate is NOT trusted. \
The certificate issuer is unknown. The name in the certificate does not match the expected.  \
Could not handshake: Error in the certificate verification. [IP: 111.186.58.212 443]
W: 无法下载 https://mirrors.tuna.tsinghua.edu.cn/debian/dists/bookworm/InRelease  \
Certificate verification failed: The certificate is NOT trusted.
W: 部分索引文件下载失败。如果忽略它们，那将转而使用旧的索引文件。
升级了 0 个软件包，新安装了 0 个软件包，要卸载 0 个软件包，有 182 个软件包未被升级。
"""

#: `apt-get -s` 真机输出形状（8.4.25 → 8.4.27，15 个包）。
APT_SIM_OK = """Note, selecting 'php8.4-fpm' instead of 'php8.4-fpm'
Inst php8.4-cli [8.4.25-1+0~20260828.55+debian12~1.gbp259445] \
(8.4.27-1+0~20261021.57+debian12~1.gbp7636b9 localhost [amd64]) []
Inst php8.4-common [8.4.25-1+0~20260828.55+debian12~1.gbp259445] \
(8.4.27-1+0~20261021.57+debian12~1.gbp7636b9 localhost [amd64])
Conf php8.4-cli (8.4.27-1+0~20261021.57+debian12~1.gbp7636b9 localhost [amd64])
Conf php8.4-common (8.4.27-1+0~20261021.57+debian12~1.gbp7636b9 localhost [amd64])
2 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""


class NetProbeClassifyTest(unittest.TestCase):
    """报错原文 → 类型（纯函数，不联网）。"""

    def test_01_real_apt_tls_error(self):
        self.assertEqual(np_.classify_text(APT_TLS_FAIL), np_.KIND_TLS_INTERCEPT,
                         '真机的「Certificate verification failed / issuer is unknown」'
                         '必须认成 TLS 中间人，而不是「源配置写错」')

    def test_02_portal_page_and_wget_html(self):
        self.assertEqual(np_.classify_text('<title>上网登录页</title>'), np_.KIND_CAPTIVE_PORTAL)
        self.assertEqual(np_.classify_text('<!DOCTYPE html><html>...'), np_.KIND_CAPTIVE_PORTAL)
        self.assertEqual(np_.classify_text('Server: DrcomServer1.0'), np_.KIND_CAPTIVE_PORTAL)

    def test_03_dns_and_timeout_and_refused(self):
        self.assertEqual(np_.classify_text('Temporary failure resolving deb.debian.org'),
                         np_.KIND_DNS)
        self.assertEqual(np_.classify_text('Connection timed out after 30000 ms'),
                         np_.KIND_TIMEOUT)
        self.assertEqual(np_.classify_text('Failed to connect: Connection refused'),
                         np_.KIND_REFUSED)

    def test_04_unknown_and_empty(self):
        self.assertEqual(np_.classify_text(''), np_.KIND_UNKNOWN)
        self.assertEqual(np_.classify_text('some random words'), np_.KIND_UNKNOWN)

    def test_05_extract_url_and_host(self):
        url = np_.extract_url(APT_TLS_FAIL)
        self.assertEqual(url, 'https://mirror.sjtu.edu.cn/sury/php')
        self.assertEqual(np_.host_of(url), 'mirror.sjtu.edu.cn')
        self.assertEqual(np_.host_of('http://172.17.1.121/x'), '172.17.1.121')
        self.assertEqual(np_.host_of(''), '')

    def test_06_looks_like_portal_true(self):
        self.assertTrue(np_.looks_like_portal(
            {'code': 302, 'server': 'DrcomServer1.0', 'location': 'http://172.17.1.121',
             'title': '', 'body': ''}), 'Dr.COM 网关的 Server 头 + 内网跳转是现场指纹')
        self.assertTrue(np_.looks_like_portal(
            {'code': 200, 'server': 'nginx', 'location': '', 'title': '上网登录页',
             'body': '<script>v6=...</script>'}))

    def test_07_looks_like_portal_false(self):
        # 正常镜像的 http→https / CDN 跳转（公网目标）不能误判成认证网关
        self.assertFalse(np_.looks_like_portal(
            {'code': 302, 'server': 'nginx',
             'location': 'https://mirrors.tuna.tsinghua.edu.cn/debian/', 'title': '',
             'body': ''}))
        self.assertFalse(np_.looks_like_portal(
            {'code': 200, 'server': 'nginx', 'location': '',
             'title': 'Index of /debian', 'body': 'Origin: Debian\nSuite: bookworm\n'}))


class NetProbeDiagnoseTest(unittest.TestCase):
    """诊断结论 + 处置建议（探测函数注入，**完全不联网**）。"""

    def _portal_probe(self, host, timeout=None):
        return {'code': 302, 'server': 'DrcomServer1.0', 'location': 'http://172.17.1.121',
                'title': '上网登录页', 'body': '<!--Dr.COMWebLoginID_0.htm-->'}

    def _tls_fail_probe(self, host, timeout=None):
        return {'ok': False, 'error': 'certificate verify failed: self-signed certificate'}

    def _tls_ok_probe(self, host, timeout=None):
        return {'ok': True, 'error': ''}

    def _call(self, text, http_probe, tls_probe, url='https://mirrors.tuna.tsinghua.edu.cn/x'):
        return np_.diagnose(url=url, text=text, branch='84',
                            http_probe=http_probe, tls_probe=tls_probe)

    def test_01_captive_portal_with_evidence_and_advice(self):
        diag = self._call(APT_TLS_FAIL, self._portal_probe, self._tls_fail_probe)
        self.assertEqual(diag['kind'], np_.KIND_CAPTIVE_PORTAL)
        self.assertTrue(diag['blocked'], '认证网关属于「换源没用，必须先解决出口」')
        self.assertIn('172.17.1.121', diag['summary'], '结论里必须带实测证据（跳到哪）')
        self.assertIn('DrcomServer1.0', diag['summary'], '结论里必须带网关指纹')
        self.assertIn('认证', diag['advice'])
        self.assertIn('php_deb', diag['advice'], '必须给出离线包这条真实可用的出路')

    def test_02_tls_intercept_without_portal(self):
        diag = self._call(APT_TLS_FAIL, lambda host, timeout=None: {},
                          self._tls_fail_probe)
        self.assertEqual(diag['kind'], np_.KIND_TLS_INTERCEPT)
        self.assertTrue(diag['blocked'])
        self.assertIn('证书', diag['summary'])
        self.assertIn('离线', diag['advice'])

    def test_03_never_raises_when_probes_explode(self):
        def boom(host, timeout=None):
            raise RuntimeError('probe exploded')
        diag = self._call(APT_TLS_FAIL, boom, boom)
        self.assertIn('kind', diag)
        self.assertTrue(diag['summary'], '探测炸了也要有结论（哪怕是「未能识别」）')

    def test_04_blocked_flag_matches_kinds(self):
        for kind in (np_.KIND_CAPTIVE_PORTAL, np_.KIND_TLS_INTERCEPT, np_.KIND_DNS,
                     np_.KIND_TIMEOUT):
            self.assertIn(kind, np_.BLOCKED_KINDS)
        for kind in (np_.KIND_OK, np_.KIND_HTTP_ERROR, np_.KIND_UNKNOWN):
            self.assertNotIn(kind, np_.BLOCKED_KINDS,
                             '源可达/认不出来的情况不许阻断在线升级')

    def test_05_dns_text_uses_advice_not_source_hint(self):
        diag = self._call('Temporary failure resolving deb.debian.org',
                          self._portal_probe, self._tls_ok_probe)
        # DNS 失败的处置是修 DNS，不该让用户去翻 sources.list
        self.assertIn('DNS', diag['advice'])

    def test_06_module_is_pure_stdlib(self):
        src = _read(NET_PROBE_PY)
        for token in ('import requests', 'import core.yf', 'import flask', 'from core import'):
            self.assertNotIn(token, src,
                             'net_probe 必须只依赖标准库（否则插件/testsuite 都没法直接断言）')
        self.assertIn('import ssl', src)
        self.assertIn('import http.client', src)


class PhpDebBundlePureTest(unittest.TestCase):
    """离线 deb 通道的纯函数（不跑 dpkg、不跑 apt，Windows 上也能断言）。"""

    def test_01_branch_version_and_dirs(self):
        self.assertEqual(deb.branch_version('84'), '8.4')
        self.assertEqual(deb.branch_version('8.4'), '8.4')
        self.assertEqual(deb.branch_version(''), '')
        dirs = deb.bundle_dirs('/panel/data', '84')
        self.assertEqual(dirs[0], os.path.join('/panel/data', 'php_deb', '84'),
                         '分支子目录必须排在前面（同名包先到先得）')
        self.assertEqual(dirs[1], os.path.join('/panel/data', 'php_deb'))
        self.assertEqual(deb.DEB_DIRNAME, 'php_deb')

    def test_02_belongs_to_branch(self):
        self.assertTrue(deb.belongs_to_branch('php8.4', '84'))
        self.assertTrue(deb.belongs_to_branch('php8.4-fpm', '84'))
        self.assertTrue(deb.belongs_to_branch('php8.4-redis', '84'))
        self.assertFalse(deb.belongs_to_branch('php8.3-fpm', '84'))
        self.assertFalse(deb.belongs_to_branch('php8.40-fpm', '84'))

    def test_03_parse_pinned(self):
        dep = ('php-common (>= 2:95~), ucf, php8.4-common (= 8.4.25-1+0~20260828.55'
               '+debian12~1.gbp259445), libc6 (>= 2.14), libedit2 (>= 3.1-20221030-2)')
        pins = deb.parse_pinned(dep)
        self.assertEqual(list(pins), ['php8.4-common'], '只收 `(= 精确版本)` 硬锚定')
        self.assertTrue(pins['php8.4-common'].startswith('8.4.25'))
        self.assertEqual(deb.parse_pinned('a (= 1) | b (= 2)'),
                         {'a': '1', 'b': '2'})

    def _entries(self, pairs, pin=None):
        out = []
        for pkg, ver in pairs:
            out.append({'path': '/x/%s_%s.deb' % (pkg, ver), 'package': pkg, 'version': ver,
                        'architecture': 'amd64',
                        'depends': (pin or {}).get(pkg, ''), 'control': ''})
        return out

    def test_04_preflight_ok(self):
        entries = self._entries([
            ('php8.4', '8.4.27-1'), ('php8.4-common', '8.4.27-1'),
            ('php8.4-cli', '8.4.27-1'), ('php8.4-fpm', '8.4.27-1'),
        ], pin={'php8.4-fpm': 'php8.4-common (= 8.4.27-1)',
                'php8.4-cli': 'php8.4-common (= 8.4.27-1)'})
        pre = deb.preflight('84', '8.4.27', entries, {})
        self.assertTrue(pre['ok'], pre['text'])

    def test_05_preflight_missing_core(self):
        entries = self._entries([('php8.4-common', '8.4.27-1')])
        pre = deb.preflight('84', '8.4.27', entries, {})
        self.assertFalse(pre['ok'])
        self.assertIn('php8.4-fpm', pre['text'])

    def test_06_preflight_below_floor(self):
        entries = self._entries([
            ('php8.4', '8.4.25-1'), ('php8.4-common', '8.4.25-1'),
            ('php8.4-cli', '8.4.25-1'), ('php8.4-fpm', '8.4.25-1'),
        ])
        pre = deb.preflight('84', '8.4.27', entries, {})
        self.assertFalse(pre['ok'])
        self.assertIn('低于基线', pre['text'])

    def test_07_preflight_internal_pin_mismatch(self):
        """离线包内部版本不一致（fpm 钉旧 common）⇒ 拒绝，别让 dpkg 拆到一半。"""
        entries = self._entries([
            ('php8.4-common', '8.4.27-1'), ('php8.4-cli', '8.4.27-1'),
            ('php8.4-fpm', '8.4.27-1'),
        ], pin={'php8.4-fpm': 'php8.4-common (= 8.4.25-1)'})
        pre = deb.preflight('84', '8.4.27', entries, {})
        self.assertFalse(pre['ok'])
        self.assertIn('php8.4-common', pre['text'])

    def test_08_preflight_installed_extension_needs_new_deb(self):
        """真实现场：已装 php8.4-mysql 钉 `php8.4-common (= 8.4.25)`，
        而离线包里只有新 common 没有新 mysql ⇒ 必须**明确列缺哪个包**。"""
        entries = self._entries([
            ('php8.4', '8.4.27-1'), ('php8.4-common', '8.4.27-1'),
            ('php8.4-cli', '8.4.27-1'), ('php8.4-fpm', '8.4.27-1'),
        ], pin={'php8.4-fpm': 'php8.4-common (= 8.4.27-1)',
                'php8.4-cli': 'php8.4-common (= 8.4.27-1)'})
        installed = {
            'php8.4-mysql': {'version': '8.4.25-1',
                             'depends': 'php8.4-common (= 8.4.25-1)'},
            'php8.4-redis': {'version': '6.3.0-2',
                             'depends': 'php8.4-common, phpapi-20240924'},
        }
        pre = deb.preflight('84', '8.4.27', entries, installed)
        self.assertFalse(pre['ok'])
        self.assertIn('php8.4-mysql', pre['text'], '必须点名缺哪个扩展包的新版本')
        self.assertNotIn('php8.4-redis', pre['text'],
                         '不锚定版本的第三方扩展（redis）不该被算成缺失')

    def test_09_simulation_parsing_and_verdict(self):
        parsed = deb.parse_simulation(APT_SIM_OK)
        self.assertEqual(parsed['install'], ['php8.4-cli', 'php8.4-common'])
        self.assertEqual(parsed['configure'], ['php8.4-cli', 'php8.4-common'])
        self.assertEqual(parsed['remove'], [])
        ok, why = deb.judge_simulation(parsed)
        self.assertTrue(ok, why)
        self.assertIn('2', why)

        bad = deb.parse_simulation('Remv php8.4-redis [*]\n1 upgraded, 0 newly installed, '
                                   '1 to remove and 0 not upgraded.')
        ok, why = deb.judge_simulation(bad)
        self.assertFalse(ok, '会卸载包就必须中止')
        self.assertIn('卸载', why)

        err = deb.parse_simulation('E: 无法定位软件包 php8.4-fpm')
        self.assertFalse(deb.judge_simulation(err)[0])
        self.assertFalse(deb.judge_simulation(deb.parse_simulation(''))[0],
                         '模拟结果为空（啥也不动）同样不能当成功')

    def test_10_packages_stanza_and_apt_args(self):
        stanza = deb.packages_stanza('Package: php8.4-fpm\nVersion: 8.4.27-1',
                                     'php8.4-fpm_8.4.27-1_amd64.deb', 123, 'md5x', 'shax')
        for token in ('Package: php8.4-fpm', 'Version: 8.4.27-1', 'Filename: php8.4-fpm_',
                      'Size: 123', 'MD5sum: md5x', 'SHA256: shax'):
            self.assertIn(token, stanza)
        args = deb.apt_repo_args('/tmp/repo')
        joined = ' '.join(args)
        # 关键：必须让 apt **只看**本地仓库，否则它会去读系统源（无外网时会卡在超时上）
        self.assertIn('Dir::Etc::sourcelist=' + os.path.join('/tmp/repo', 'offline.list'),
                      joined)
        self.assertIn('Dir::Etc::sourceparts=/dev/null', joined)
        self.assertIn('Dir::State::lists=' + os.path.join('/tmp/repo', 'lists'), joined)

    def test_12_release_file_has_checksums(self):
        """本地仓库必须带 `Release`（否则 apt 会对 file: 仓库重试并刷
        `Method gave a blank filename`，看着像失败）。"""
        text = deb.release_text(b'Packages-1', b'gz-1',
                                date='Mon, 26 Oct 2026 00:00:00 GMT')
        self.assertIn('Date: Mon, 26 Oct 2026 00:00:00 GMT', text)
        self.assertIn('MD5Sum:', text)
        self.assertIn('SHA256:', text)
        for name in ('Packages', 'Packages.gz'):
            self.assertIn(name, text)
        self.assertRegex(text, r'(?m)^ [0-9a-f]{32} 10 Packages$')
        self.assertRegex(text, r'(?m)^ [0-9a-f]{32} 4 Packages.gz$')
        self.assertRegex(text, r'(?m)^ [0-9a-f]{64} 10 Packages$')
        self.assertRegex(text, r'(?m)^ [0-9a-f]{64} 4 Packages.gz$')

    def test_11_collect_debs_prefers_branch_dir(self):
        root = tempfile.mkdtemp(prefix='yf_deb_test_')
        try:
            branch_dir = os.path.join(root, 'php_deb', '84')
            flat_dir = os.path.join(root, 'php_deb')
            os.makedirs(branch_dir)
            for name in ('php8.4-fpm_8.4.27.deb', 'readme.txt'):
                with open(os.path.join(branch_dir, name), 'w') as fp:
                    fp.write('x')
            with open(os.path.join(flat_dir, 'php8.4-fpm_8.4.27.deb'), 'w') as fp:
                fp.write('y')
            with open(os.path.join(flat_dir, 'php8.4-cli_8.4.27.deb'), 'w') as fp:
                fp.write('z')
            found = deb.collect_debs(deb.bundle_dirs(root, '84'))
            self.assertEqual([os.path.basename(p) for p in found],
                             ['php8.4-fpm_8.4.27.deb', 'php8.4-cli_8.4.27.deb'],
                             '分支子目录优先、同名去重、非 .deb 忽略')
            self.assertEqual(os.path.dirname(found[0]), branch_dir)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class AptPluginWiringTest(unittest.TestCase):
    """php-apt 插件的接线（源码守卫）。"""

    def setUp(self):
        self.src = _read(APT_PY)

    def test_01_imports_and_diagnosis_wiring(self):
        self.assertIn('from core import net_probe', self.src)
        body = _body(self.src, 'def _refreshPackageIndex(', 'def _queueUpgrade(')
        self.assertIn('_diagnoseSource(', body, '索引刷新失败必须做诊断')
        self.assertIn("diag.get('advice')", body, '处置建议必须写进任务日志')
        self.assertIn('_logLine(', body, '诊断必须同时进插件日志与任务日志（stdout）')

    def test_02_no_more_blame_the_sources(self):
        self.assertNotIn('请检查 /etc/apt/sources.list 与 sury 源',
                         self.src, '不许再把「网关劫持」说成「源配置写错」')
        self.assertNotIn('自动回退%s', self.src,
                         '一个包都没升时不许再报「自动回退成功」（那是空操作）')
        self.assertIn('本次未做任何改动', self.src)

    def test_03_rollback_only_when_package_changed(self):
        body = _body(self.src, 'def upgradeToBaseline(', 'def dropPhpSecSnapshot(')
        gate = body.index('if not no_op:')
        rollback = body.index('build_apt_rollback_argv(')
        self.assertLess(gate, rollback,
                        '回退必须被 `if not no_op:` 挡住（no_op 时回退是空操作）')

    def test_04_offline_channel_simulates_before_touching_system(self):
        self.assertIn('from core import php_deb_bundle', self.src)
        body = _body(self.src, 'def _offlineUpgrade(', 'def upgradeToBaseline(')
        for token in ('php_deb_bundle.offline_bundle(', 'php_deb_bundle.build_repo(',
                      'php_deb_bundle.apt_repo_args(', 'php_deb_bundle.parse_simulation(',
                      'php_deb_bundle.judge_simulation(',
                      'php_sec_baseline.apt_package_names(',
                      'LC_ALL'):
            self.assertIn(token, body, '离线通道缺少 %r' % token)
        sim = body.index('judge_simulation(')
        real = body.index("'install', '-y', '--only-upgrade'")
        self.assertLess(sim, real,
                        '必须**先**跑 apt-get -s 模拟并判定，再真装（模拟失败一个文件都不动）')
        self.assertIn('--force-confold', body,
                      '升级会碰到 /etc/php 下的 conffile，必须显式保留本地配置')
        self.assertIn('env[' + "'LC_ALL'" + '] = ' + "'C'", body,
                      '解析 apt 输出前必须钉死 locale（中文摘要会让判据失效）')

    def test_05_offline_channel_reachable_in_both_situations(self):
        body = _body(self.src, 'def upgradeToBaseline(', 'def dropPhpSecSnapshot(')
        self.assertIn("diag.get('blocked')", body,
                      '网络出口不通（认证网关/证书劫持）时必须直接走离线通道')
        self.assertEqual(body.count('_offlineUpgrade('), 2,
                         '在线通道失败后还要再试一次离线包（源里确实没有新版本时）')
        self.assertNotIn('dpkg -i', body, '不许用不做依赖求解的 dpkg -i 装 sury 包')

    def test_06_log_line_goes_to_stdout(self):
        body = _body(self.src, 'def _logLine(', 'def _firstSourceUrl(')
        self.assertIn('print(msg)', body,
                      '面板任务日志读的是子进程 stdout —— 只写文件用户看不到')
        self.assertIn('sys.stdout.flush()', body)

    def test_07_rc0_with_tls_errors_still_diagnosed(self):
        """真机：所有源都因证书失败时 `apt-get update` **仍以 0 退出**。

        只看 rc 的话诊断永远不会触发，面板就会回到「请检查 sources.list」那条歧路。
        """
        body = _body(self.src, 'def _refreshPackageIndex(', 'def _queueUpgrade(')
        self.assertIn('classify_text(', body,
                      'refresh 必须按输出文本判「有错误」，不能只看 rc（apt 会以 0 退出）')
        self.assertIn('suspicious = rc != 0 or net_probe.classify_text(tail)', body,
                      '「有错误」必须同时认 rc 与输出文本（apt 会以 0 退出且全是证书错误）')


class YumPluginWiringTest(unittest.TestCase):
    """php-yum 插件：同一套诊断口径（Remi 渠道）。"""

    def setUp(self):
        self.src = _read(YUM_PY)

    def test_01_diagnosis_wiring(self):
        self.assertIn('from core import net_probe', self.src)
        body = _body(self.src, 'def _refreshPackageIndex(', 'def _queueUpgrade(')
        self.assertIn('_diagnoseSource(', body)
        self.assertIn("diag.get('advice')", body)
        self.assertIn('_logLine(', body)

    def test_02_messages_are_honest(self):
        self.assertNotIn('请检查 Remi 源配置', self.src,
                         '不许把网关劫持/无外网说成「Remi 源配置错」')
        self.assertIn('本次未做任何改动', self.src)
        body = _body(self.src, 'def upgradeToBaseline(', 'def dropPhpSecSnapshot(')
        self.assertIn('网络诊断', body)
        self.assertIn('不支持自动回退', body, 'yum/Remi 仍然只能人工回退（口径没变）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
