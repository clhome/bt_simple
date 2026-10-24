# coding: utf-8
"""P0-2 守卫：存量已装 PHP 的「巡检 → 告警 → 升级 → 回读」全链路。

## 本文件守什么

P0-2 之前的三个事实：

1. 面板只看得见**大版本目录名**（`getInstalledPhpVersions()` 返回 `['82','83']`），
   看不见 `8.2.30` 还是 `8.2.35` —— 存量客户无人告知自己在跑可被 RCE 的版本；
2. 没有任何「已装小版本 vs 安全基线」的比对与告警通道；
3. `versions/<NN>/install.sh` 有两道**大版本判存**（源码层只看 `php_version.h` 在不在、
   安装层只看 `/www/server/php/<NN>` 目录在不在），于是「一键升级」必然假成功。

本文件逐条守：

* 基线表**只有一份定义**（`web/core/php_sec_baseline.py`），testsuite 只引用不复制；
* 巡检判定：基线以下命中 / 基线以上不命中 / 无 PHP 不告警 / apt 渠道带回移标记不误判；
* 告警三态口径：`empty` 不告警、`apt-only` 按回移标记判、`offline` 用内置表并带日期；
* 幂等判定：旧版源码/旧二进制 ⇒ 判「需要重做」，新版 ⇒ 判「跳过」
  （shell 判定逻辑抽在 `plugins/php/versions/common/php_ver_guard.sh`，可直接执行断言）；
* 两道判存真的被替换成「比对完整版本号」（不是只改了注释）；
* 巡检任务挂到 `panel_task.py` 的每日槽位；
* 首页告警卡片的路由 / 模板 / 前端函数 / 六语言文案都在位；
* 升级动作：先快照、后回读断言、失败可回退（apt/yum 不支持自动回退要明示）。

## 为什么部分用例走 shell

「旧的 `php_version.h` / 旧的 `bin/php` 桩 ⇒ 判定需要重装」这条只能在 shell 层证伪 ——
判存就在 shell 里。所以判定逻辑被抽成可独立执行的小脚本（`php_ver_guard.sh`），
本文件用 `bash <guard> <cmd> <dir> <target>` 的**退出码**断言，不真编译 PHP。
本机没有 bash 时这些用例 skip（不会假绿：其余用例仍会跑，且 CI 环境自带 bash）。
"""

import ast
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
PLUGINS = os.path.join(ROOT, 'plugins')
PHP_DIR = os.path.join(PLUGINS, 'php')
VERSIONS_DIR = os.path.join(PHP_DIR, 'versions')
GUARD_SH = os.path.join(VERSIONS_DIR, 'common', 'php_ver_guard.sh')
PANEL_TASK_PY = os.path.join(ROOT, 'panel_task.py')
DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
INDEX_TEMPLATE = os.path.join(WEB, 'templates', 'default', 'index.html')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
LANG_DIR = os.path.join(WEB, 'static', 'language')
BASELINE_PY = os.path.join(WEB, 'core', 'php_sec_baseline.py')
SCAN_PY = os.path.join(WEB, 'core', 'php_sec_scan.py')

if WEB not in sys.path:
    sys.path.insert(0, WEB)

from core import php_sec_baseline as bl   # noqa: E402
from core import php_sec_scan as scan    # noqa: E402

def find_posix_bash():
    candidates = [
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files (x86)\Git\bin\bash.exe',
        r'C:\Program Files\Git\usr\bin\bash.exe',
    ]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, timeout=10)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None

BASH = find_posix_bash()


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def _entries(*specs):
    """[(branch, channel, version, package_version), ...] → evaluate() 的入参。"""
    out = []
    for branch, channel, version, pkg in specs:
        out.append({'branch': branch, 'channel': channel, 'version': version,
                    'package_version': pkg, 'path': '/tmp/php%s' % branch})
    return out


class BaselineSingleSourceTest(unittest.TestCase):
    """基线表只许有一处定义：产品代码定义，测试引用。"""

    def test_01_product_holds_the_only_table(self):
        self.assertTrue(os.path.isfile(BASELINE_PY), '缺少 %s' % BASELINE_PY)
        # 数值口径（方案给定的基线）必须落在这里
        self.assertEqual(bl.BRANCH_BASELINE,
                         {'82': '8.2.35', '83': '8.3.36', '84': '8.4.27', '85': '8.5.12'})
        for ver, sha in (('8.2.35', '5737b986'), ('8.3.36', 'dd54693a'),
                         ('8.4.27', 'dcf93923'), ('8.5.12', '08bc2eba')):
            self.assertTrue(bl.OFFICIAL_SHA256.get(ver, '').startswith(sha),
                            'OFFICIAL_SHA256[%s] 不是官方值' % ver)
        self.assertRegex(bl.BASELINE_DATE, r'^\d{4}-\d{2}-\d{2}$',
                         'BASELINE_DATE 必须是可展示的取值日期（未联网时要标出来）')

    def test_02_testsuite_does_not_keep_a_second_copy(self):
        """testsuite 里不许再出现 `BRANCH_BASELINE = {...}` 字面量（必须 import 产品值）。"""
        offenders = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith('test_') or not name.endswith('.py'):
                continue
            text = _read(os.path.join(HERE, name))
            for m in re.finditer(r'^\s*BRANCH_BASELINE\s*=\s*\{', text, re.M):
                offenders.append('%s:%d' % (name, text.count('\n', 0, m.start()) + 1))
        self.assertEqual(offenders, [],
                         '基线表又出现了第二份定义（应 from core import php_sec_baseline）：%s'
                         % offenders)

    def test_03_baseline_module_is_offline_and_dependency_free(self):
        """未联网口径：基线模块不得有网络/第三方依赖（只能标准库）。"""
        tree = ast.parse(_read(BASELINE_PY))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split('.')[0])
        self.assertEqual(mods - {'re'}, set(),
                         '基线模块只允许 import re（离线可判定），实际：%s' % sorted(mods))


class PatrolJudgeTest(unittest.TestCase):
    """巡检判定四条（方案验收）：基线以下命中 / 以上不命中 / 无 PHP 不告警 / apt 带回移不误判。"""

    def test_04_below_baseline_alarms(self):
        res = bl.evaluate(_entries(('82', 'src', '8.2.30', '')))
        self.assertEqual(res['state'], 'alarm')
        self.assertTrue(res['alarm'])
        item = res['items'][0]
        self.assertEqual(item['status'], bl.STATUS_NEED_UPGRADE)
        self.assertEqual(item['floor'], '8.2.35')
        self.assertEqual(item['upgrade_hint'], 'compiled')
        self.assertEqual(item['plugin'], 'php')

    def test_05_at_or_above_baseline_does_not_alarm(self):
        for branch, ver in (('82', '8.2.35'), ('83', '8.3.36'),
                            ('84', '8.4.27'), ('85', '8.5.12'), ('84', '8.4.30')):
            res = bl.evaluate(_entries((branch, 'src', ver, '')))
            self.assertEqual(res['state'], 'ok', '%s(%s) 不应告警' % (branch, ver))
            self.assertFalse(res['alarm'])
        # 边界：只差一个补丁号也必须命中
        self.assertTrue(bl.evaluate(_entries(('84', 'src', '8.4.26', '')))['alarm'])

    def test_06_no_php_does_not_alarm(self):
        res = bl.evaluate([])
        self.assertEqual(res['state'], 'empty')
        self.assertFalse(res['alarm'])
        self.assertEqual(res['items'], [])
        # 空态也要带基线表日期（前端会显示「基线表日期」）
        self.assertEqual(res['baseline_date'], bl.BASELINE_DATE)

    def test_07_apt_backport_marker_not_misjudged(self):
        """sury/Debian 把补丁回移到旧上游版本号：带标记时不得按数字判危。"""
        cases = [
            (('82', 'apt', '8.2.29', '8.2.29-1+deb12u3'), True),          # Debian 安全回移
            (('83', 'apt', '8.3.30', '2:8.3.30-1+ubuntu22.04.1+deb.sury.org+1'), True),
            (('82', 'apt', '8.2.30', '8.2.30-1+deb.sury.org+2'), True),
            (('82', 'apt', '8.2.29', '8.2.29-1'), False),                 # 无任何渠道标记
        ]
        for spec, has_marker in cases:
            item = bl.judge_entry({'branch': spec[0], 'channel': spec[1],
                                   'version': spec[2], 'package_version': spec[3]})
            self.assertEqual(item['backport_marker'], has_marker, '%s 标记判定错' % (spec[3],))
            if has_marker:
                self.assertEqual(item['status'], bl.STATUS_OK,
                                 '%s 已带回移标记，不得判危' % (spec[3],))
                self.assertFalse(item['alarm'])
            else:
                # 无标记时不能装作达标，也不能直接判「危」：给出需人工确认
                self.assertEqual(item['status'], bl.STATUS_BACKPORT_UNVERIFIED)
        # 仅有 apt 渠道且全部带标记 ⇒ 整体不告警（不是「永远告警」）
        res = bl.evaluate(_entries(
            ('82', 'apt', '8.2.29', '8.2.29-1+deb12u3'),
            ('83', 'yum', '8.3.30', '8.3.30-1.el9.remi'),
        ))
        self.assertEqual(res['state'], 'ok')
        self.assertFalse(res['alarm'])

    def test_08_eol_and_backport_required_branches(self):
        """≤7.3 直接判危；7.4/8.0/8.1 必须看到官方 backport 标记才算合格。"""
        item = bl.judge_entry({'branch': '73', 'channel': 'src', 'version': '7.3.33'})
        self.assertEqual(item['status'], bl.STATUS_NO_FIX)
        self.assertTrue(item['alarm'])
        self.assertEqual(item['upgrade_hint'], 'no_fix', '无官方修复的分支不该给升级按钮')

        for branch in ('74', '80', '81'):
            raw = bl.judge_entry({'branch': branch, 'channel': 'src', 'version': '7.4.33'})
            self.assertEqual(raw['status'], bl.STATUS_BACKPORT_MISSING, branch)
            self.assertTrue(raw['alarm'])
            ok = bl.judge_entry({'branch': branch, 'channel': 'apt', 'version': '7.4.33',
                                 'package_version': '7.4.33-1+deb12u1'})
            self.assertEqual(ok['status'], bl.STATUS_OK, branch)
            self.assertFalse(ok['alarm'])

    def test_09_offline_uses_builtin_table_with_date(self):
        res = bl.evaluate(_entries(('82', 'src', '8.2.30', '')), offline=True)
        self.assertTrue(res['offline'])
        self.assertEqual(res['baseline_date'], bl.BASELINE_DATE)
        self.assertEqual(res['state'], 'alarm')
        summary = bl.summary_text(res)
        self.assertIn(bl.BASELINE_DATE, summary, '日志摘要必须标出基线表日期')
        self.assertIn('离线', summary)


class VersionReadTest(unittest.TestCase):
    """版本读取口径：编译版读 `php -v` 完整版本；apt/yum 读包版本串 + 渠道标记。"""

    def test_10_parse_php_v_output(self):
        self.assertEqual(bl.parse_php_version_output(
            'PHP 8.2.30 (cli) (built: Jan  1 2026 00:00:00) (NTS)\nCopyright ...'), '8.2.30')
        self.assertEqual(bl.parse_php_version_output(
            'PHP 8.4.27 (fpm-fcgi) (built: Nov  1 2025 00:00:00)'), '8.4.27')
        self.assertEqual(bl.parse_php_version_output('php-fpm: command not found'), '')
        self.assertEqual(bl.parse_php_version_output(''), '')

    def test_11_parse_source_header_version(self):
        header = '#define PHP_VERSION "8.2.30"\n#define PHP_MAJOR_VERSION 8\n'
        self.assertEqual(bl.parse_source_header_version(header), '8.2.30')
        self.assertEqual(bl.parse_source_header_version('#define PHP_MAJOR_VERSION 8'), '')
        self.assertEqual(bl.parse_source_header_version(''), '')

    def test_12_parse_package_version_strips_epoch(self):
        self.assertEqual(bl.parse_package_version('2:8.3.30-1+ubuntu22.04.1+deb.sury.org+1')[0],
                         '8.3.30')
        self.assertEqual(bl.parse_package_version('8.2.29-1+deb12u3')[0], '8.2.29')
        self.assertEqual(bl.parse_package_version('')[0], '')

    def test_13_scan_reads_full_version_not_branch_dir(self):
        """巡检必须读出 8.2.30 这种小版本，而不是目录名 `82`。"""
        calls = []

        def fake_run(argv):
            calls.append(argv)
            return 0, 'PHP 8.2.30 (cli) (built: Jan  1 2026 00:00:00) (NTS)\n'

        tmp = tempfile.mkdtemp()
        try:
            prefix = os.path.join(tmp, 'php', '82')
            os.makedirs(os.path.join(prefix, 'bin'))
            with open(os.path.join(prefix, 'bin', 'php'), 'w', encoding='utf-8') as fp:
                fp.write('#!/bin/sh\n')
            entries = scan.collect_compiled(os.path.join(tmp, 'php'), run=fake_run)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['branch'], '82')
            self.assertEqual(entries[0]['version'], '8.2.30',
                             '版本必须是完整小版本，不能是目录名')
            self.assertEqual(entries[0]['channel'], 'src')
            self.assertTrue(calls, '应当真的调用了 php -v')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_14_scan_apt_uses_package_version(self):
        def fake_run(argv):
            if argv and argv[0] == 'dpkg-query':
                return 0, '8.2.29-1+deb12u3'
            return 127, ''

        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, '8.2'))
            entries = scan.collect_apt(tmp, run=fake_run)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['branch'], '82')
            self.assertEqual(entries[0]['version'], '8.2.29')
            self.assertEqual(entries[0]['package_version'], '8.2.29-1+deb12u3',
                             'apt 必须保留包版本串（渠道标记只存在于这里）')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_15_snapshot_write_and_load(self):
        data = scan.scan(server_php_dir='/nonexistent-php-dir',
                         apt_root='/nonexistent-apt',
                         yum_root='/nonexistent-yum', now=1700000000)
        self.assertEqual(data['state'], 'empty')
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, 'php_sec_scan.json')
            scan.write_snapshot(data, path)
            loaded = scan.load_snapshot(path, now=1700000000 + 60)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded['state'], 'empty')
            self.assertEqual(loaded['baseline_date'], bl.BASELINE_DATE)
            # 过期快照必须当没有（否则页面会一直显示两年前的结论）
            self.assertIsNone(scan.load_snapshot(path, now=1700000000 + 40 * 86400))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipIf(not BASH, '本机没有 bash，跳过 shell 判存用例')
class IdempotentGuardShellTest(unittest.TestCase):
    """幂等判定：旧版源码/旧二进制 ⇒ 需要重做；新版 ⇒ 跳过。

    判定逻辑在 `plugins/php/versions/common/php_ver_guard.sh`（可独立执行的 POSIX 小脚本），
    退出码：0=需要重做 / 1=可跳过 / 2=参数非法。
    """

    def _mkfixture(self, ver_src, ver_bin):
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, 'source', 'php84')
        os.makedirs(os.path.join(src, 'main'))
        with open(os.path.join(src, 'main', 'php_version.h'), 'w', encoding='utf-8') as fp:
            fp.write('#define PHP_VERSION "%s"\n#define PHP_MAJOR_VERSION 8\n' % ver_src)
        inst = os.path.join(tmp, 'server', 'php', '84')
        os.makedirs(os.path.join(inst, 'bin'))
        stub = os.path.join(inst, 'bin', 'php')
        with open(stub, 'w', encoding='utf-8') as fp:
            fp.write('#!/bin/sh\necho "PHP %s (cli) (built: Jan  1 2026 00:00:00) (NTS)"\n'
                     % ver_bin)
        os.chmod(stub, 0o755)
        return tmp, src, inst

    def _guard(self, *args):
        return subprocess.run([BASH, GUARD_SH] + list(args), capture_output=True,
                              timeout=60)

    def test_20_old_version_requires_redo(self):
        tmp, src, inst = self._mkfixture('8.2.30', '8.2.30')
        try:
            r = self._guard('src-need-fetch', src, '8.2.35')
            self.assertEqual(r.returncode, 0,
                             '旧源码(8.2.30) vs 目标 8.2.35 应判「需要重新拉取」，'
                             '实际 rc=%d %r' % (r.returncode, r.stdout))
            r = self._guard('inst-need-build', inst, '8.2.35')
            self.assertEqual(r.returncode, 0,
                             '旧二进制(8.2.30) vs 目标 8.2.35 应判「需要重装」，'
                             '实际 rc=%d %r' % (r.returncode, r.stdout))
            self.assertEqual(self._guard('src-version', src).stdout.strip(), b'8.2.30')
            self.assertEqual(self._guard('inst-version', inst).stdout.strip(), b'8.2.30')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_21_new_version_skips(self):
        tmp, src, inst = self._mkfixture('8.2.35', '8.2.35')
        try:
            self.assertEqual(self._guard('src-need-fetch', src, '8.2.35').returncode, 1)
            self.assertEqual(self._guard('inst-need-build', inst, '8.2.35').returncode, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_22_installed_newer_than_target_skips(self):
        """已装版本比目标还新（用户自己升级过）⇒ 不许降级重装。"""
        tmp, src, inst = self._mkfixture('8.2.35', '8.2.36')
        try:
            self.assertEqual(self._guard('inst-need-build', inst, '8.2.35').returncode, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_23_missing_or_broken_install_requires_redo(self):
        """目录在但没有可用二进制 / 目录不存在 ⇒ 一律「需要重装」，不许静默跳过。"""
        tmp, _src, inst = self._mkfixture('8.2.35', '8.2.35')
        try:
            os.remove(os.path.join(inst, 'bin', 'php'))
            self.assertEqual(self._guard('inst-need-build', inst, '8.2.35').returncode, 0)
            self.assertEqual(self._guard('inst-need-build', os.path.join(tmp, 'nope'),
                                         '8.2.35').returncode, 0)
            # 源码目录被清掉 ⇒ 需要重新拉取
            src2 = os.path.join(tmp, 'source', 'gone')
            self.assertEqual(self._guard('src-need-fetch', src2, '8.2.35').returncode, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_24_bad_target_is_error_not_skip(self):
        """目标版本非法必须返回 2（错误），调用方据此 exit 1 —— 不许当成「跳过」。"""
        tmp, src, inst = self._mkfixture('8.2.35', '8.2.35')
        try:
            self.assertEqual(self._guard('src-need-fetch', src, '').returncode, 2)
            self.assertEqual(self._guard('inst-need-build', inst, 'v8.x').returncode, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_25_guard_script_is_syntactically_valid(self):
        for exe in (BASH, shutil.which('sh')):
            if not exe:
                continue
            r = subprocess.run([exe, '-n', GUARD_SH], capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, '%s -n 失败: %r' % (exe, r.stderr))


class InstallShTwoGatesTest(unittest.TestCase):
    """两道大版本判存必须都被替换成「比对完整版本号」（源码层 + 安装层）。"""

    BRANCHES = ('82', '83', '84', '85')

    def test_30_source_layer_compares_version(self):
        problems = []
        for br in self.BRANCHES:
            path = os.path.join(VERSIONS_DIR, br, 'install.sh')
            text = _read(path)
            if 'yf_php_src_needs_fetch' not in text:
                problems.append('%s 未调用 yf_php_src_needs_fetch（源码层仍在只判存在性）' % path)
            if 'yf_php_install_needs_build' not in text:
                problems.append('%s 未调用 yf_php_install_needs_build（安装层仍在只判目录存在）' % path)
            # 旧的两道判存不许残留成「生效的 if」
            if re.search(r'^\s*if \[ ! -f "\$sourcePath/php/php\$\{PHP_VER\}/main/php_version\.h" \];then',
                         text, re.M):
                problems.append('%s 仍保留源码层「只判存在性」的 if' % path)
            if re.search(r'^\s*if \[ ! -d \$serverPath/php/\$\{PHP_VER\} \];then', text, re.M):
                problems.append('%s 仍保留安装层「只判目录存在」的 if' % path)
            # 判存守卫必须真的被 source 进来（否则函数不存在 → 脚本会 exit 1，且无提示）
            if 'php_ver_guard.sh' not in text:
                problems.append('%s 没有 source php_ver_guard.sh' % path)
        self.assertEqual(problems, [], '判存未修好：\n' + '\n'.join(problems))

    def test_31_install_sh_syntax_ok(self):
        if not BASH:
            self.skipTest('本机没有 bash')
        for br in self.BRANCHES:
            path = os.path.join(VERSIONS_DIR, br, 'install.sh')
            r = subprocess.run([BASH, '-n', path], capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, '%s 语法错误: %r' % (path, r.stderr))

    def test_32_guard_loaded_or_install_aborts(self):
        """守卫文件缺失时必须显式失败，而不是继续跑（继续跑 = 回到假成功）。"""
        for br in self.BRANCHES:
            text = _read(os.path.join(VERSIONS_DIR, br, 'install.sh'))
            self.assertIn('command -v yf_php_install_needs_build', text,
                          'PHP%s 的 install.sh 没有校验守卫是否加载成功' % br)
            self.assertRegex(text, r'缺少判存守卫 php_ver_guard\.sh',
                             'PHP%s 的 install.sh 缺少守卫缺失时的显式失败' % br)


class PatrolTaskWiringTest(unittest.TestCase):
    """巡检必须挂到 panel_task.py 的每日槽位（不是只在 Web 请求里现算）。"""

    def test_40_daily_task_registered(self):
        tree = ast.parse(_read(PANEL_TASK_PY))
        consts = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                try:
                    consts[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        self.assertIn('PHP_SEC_SCAN_INTERVAL', consts, '缺少 PHP_SEC_SCAN_INTERVAL 常量')
        self.assertEqual(consts['PHP_SEC_SCAN_INTERVAL'], 86400, '必须是每日一次')

        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn('phpSecurityScan_step', funcs, '缺少 phpSecurityScan_step 巡检步进')

        # add_task(phpSecurityScan_step, PHP_SEC_SCAN_INTERVAL) 必须真的出现在注册段
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == 'add_task'):
                continue
            if len(node.args) < 2:
                continue
            a0, a1 = node.args[0], node.args[1]
            if isinstance(a0, ast.Name) and a0.id == 'phpSecurityScan_step' \
                    and isinstance(a1, ast.Name) and a1.id == 'PHP_SEC_SCAN_INTERVAL':
                found = True
        self.assertTrue(found, 'phpSecurityScan_step 没有以每日间隔注册进 TaskScheduler')

    def test_41_scan_step_never_raises(self):
        """巡检失败不得拖垮其它任务：函数体必须整体包在 try/except 里。"""
        tree = ast.parse(_read(PANEL_TASK_PY))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'phpSecurityScan_step':
                self.assertTrue(any(isinstance(x, ast.Try) for x in node.body),
                                'phpSecurityScan_step 没有 try/except 保护')
                return
        self.fail('找不到 phpSecurityScan_step')


class DashboardCardTest(unittest.TestCase):
    """首页高危卡片：后端路由 + 模板容器 + 前端渲染 + 六语言文案。"""

    def test_50_backend_route_login_required(self):
        text = _read(DASHBOARD_PY)
        self.assertIn("/get_php_security_status", text)
        m = re.search(r"@blueprint\.route\('/get_php_security_status'.*?\ndef "
                      r"get_php_security_status\(\):", text, re.S)
        self.assertIsNotNone(m, '找不到 /get_php_security_status 视图')
        self.assertIn('@panel_login_required', m.group(0),
                      '巡检结果接口必须登录可见（不能匿名暴露服务器版本）')

    def test_51_template_has_card_container(self):
        text = _read(INDEX_TEMPLATE)
        self.assertIn('id="phpSecCard"', text, '首页模板缺少告警卡片容器')
        self.assertIn("index.php_sec_title", text)
        self.assertIn('getPhpSecurityStatus', text, '首页未在启动流水线里调用巡检接口')

    def test_52_frontend_renders_three_states(self):
        text = _read(INDEX_JS)
        for token in ('function getPhpSecurityStatus', 'function phpSecRenderCard',
                      'function upgradePhpToBaseline', "'empty'", "'alarm'",
                      'submit_baseline_upgrade', 'php_sec_no_auto_rollback'):
            self.assertIn(token, text, '前端缺少 %r' % token)

    def test_53_i18n_keys_in_all_six_languages(self):
        keys = ('php_sec_title', 'php_sec_empty', 'php_sec_ok', 'php_sec_alarm',
                'php_sec_need_upgrade', 'php_sec_backport_missing',
                'php_sec_backport_unverified', 'php_sec_no_official_fix',
                'php_sec_baseline', 'php_sec_baseline_date', 'php_sec_scan_time',
                'php_sec_offline', 'php_sec_upgrade', 'php_sec_refresh',
                'php_sec_unknown_version', 'php_sec_no_auto_rollback')
        problems = []
        for lang in ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it'):
            path = os.path.join(LANG_DIR, lang, 'template.index.json')
            data = json.loads(_read(path)).get('index') or {}
            missing = [k for k in keys if not data.get(k)]
            if missing:
                problems.append('%s 缺 %s' % (lang, missing))
        self.assertEqual(problems, [], '首页告警卡片文案缺失：\n' + '\n'.join(problems))


class UpgradeActionTest(unittest.TestCase):
    """升级动作：快照 → 重跑安装 → 回读断言 → 失败可回退。"""

    def test_60_verify_upgrade_ok_and_fail(self):
        ok = bl.verify_upgrade('82', '8.2.30', '8.2.35')
        self.assertTrue(ok['ok'])
        self.assertFalse(ok['rollback'])
        self.assertIn('8.2.35', ok['text'])

        bad = bl.verify_upgrade('82', '8.2.30', '8.2.30')
        self.assertFalse(bad['ok'], '回读仍低于基线必须判失败')
        self.assertTrue(bad['rollback'], '失败必须要求回退（保留旧二进制）')

        unreadable = bl.verify_upgrade('82', '8.2.30', '')
        self.assertFalse(unreadable['ok'], '回读读不出必须判失败，不能当成功')

    def test_61_verify_upgrade_accepts_channel_backport(self):
        v = bl.verify_upgrade('82', '8.2.30', '8.2.29', backport=True)
        self.assertTrue(v['ok'], '渠道已回移补丁时不得把升级判失败')
        self.assertTrue(v['backport'])

    def test_62_upgrade_commands(self):
        argv = bl.build_apt_upgrade_argv('82')
        self.assertIn('--only-upgrade', argv)
        self.assertIn('php8.2-fpm', argv)
        argv = bl.build_yum_upgrade_argv('82')
        self.assertIn('update', argv)
        self.assertIn('php82-php-fpm', argv)
        # 回退命令：apt 可以钉旧版本（--allow-downgrades），yum 只给命令不自动执行
        rb = bl.build_apt_rollback_argv('82', '8.2.30-1+deb12u3')
        self.assertIn('--allow-downgrades', rb)
        self.assertIn('php8.2-fpm=8.2.30-1+deb12u3', rb)
        self.assertIn('php82-php-fpm-8.2.30-1.el9', bl.build_yum_rollback_argv('82', '8.2.30-1.el9'))
        self.assertEqual(bl.AUTO_ROLLBACK_CHANNELS, ('apt',),
                         '只有 apt 允许面板自动回退；yum 必须走人工（UI 明示）')

    def test_63_plugins_expose_upgrade_entry(self):
        for plugin, funcs in (('php', ('submitBaselineUpgrade', 'upgradeToBaseline')),
                              ('php-apt', ('submitBaselineUpgrade',)),
                              ('php-yum', ('submitBaselineUpgrade',))):
            text = _read(os.path.join(PLUGINS, plugin, 'index.py'))
            for fn in funcs:
                self.assertIn('def %s(' % fn, text, '%s 缺少 %s' % (plugin, fn))
            self.assertIn('submit_baseline_upgrade', text,
                          '%s 没有把升级入口接到前端调用点' % plugin)
            self.assertIn('from core import php_sec_baseline', text,
                          '%s 没有引用唯一一份基线表' % plugin)

    def test_64_compiled_upgrade_snapshots_before_and_rolls_back(self):
        """编译版升级必须：先备份 bin/sbin、装完回读、失败还原 + 重启。"""
        text = _read(os.path.join(PHP_DIR, 'index.py'))
        for token in ('def backupRuntimeBinary', 'def restoreRuntimeBinary',
                      'php_sec_baseline.verify_upgrade', 'def getRuntimeVersion',
                      'restart(ver)'):
            self.assertIn(token, text, '编译版升级缺少 %r' % token)
        # 备份失败必须中止（没有回退点不许编译）
        self.assertRegex(text, r'升级前备份旧二进制失败，已取消升级')


if __name__ == '__main__':
    unittest.main(verbosity=2)
