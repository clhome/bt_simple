# coding: utf-8
"""A08 system 系统信息/运维操作回归守卫（本轮真机功能测试暴露的缺陷）。

本轮在 Debian 12 真机（172.17.60.248）上把系统信息接口、面板/服务器重启、
监控设置、测速、面板自身升级的失败分支跑了一遍，真机上确认了下面 4 类问题
（每条都先复现、再修、再复验）：

1. **升级版本参数 → root 命令注入 + 路径穿越**：`/system/update_server?type=update
   &version=...` 的 `version` 未做任何校验，被直接拼进下载 URL，而
   `core/yf/github.py::githubDownload` 又把该 URL 拼进 `wget ... "{}"` 的 shell 命令。
   真机实测（stub 掉 `getServerInfo` 后走真实代码路径）：
   `version='v9.9.9"; touch /tmp/yf_a08_canary2; echo "'` → 下载如实失败，
   但 **canary 文件被创建**（root 权限任意命令执行）。同一参数还被当成
   `temp/bt_simple-<version>` 目录名交给安装阶段（cp/removeDir），`..` 可打到面板目录之外。
   修复：只放行「形状合法且等于本次检测到的 tag」的版本号。
2. **安装阶段假成功 / 无回滚**：`yf.execShell('cp -rf ' + src_path + '/* ' + panel_dir)`
   丢弃返回码，且 `src_path` 的目录名来自解压包（拼 shell 可被目录名注入）。
   拷贝失败时依旧写 `.version`、跑 pip、`restartPanel()` 并回报「安装更新成功!」，
   面板停在「半新半旧」状态。修复：`shutil.copytree`（不经 shell）+ 失败时用
   升级前快照 `rollback_panel()` 回滚并如实报错。
3. **`/system/restart_server` 状态假阳性**：`sys.restartServer()` 是 `@yf_async` 装饰的
   异步函数，`isRestart()` 判定在线程体内，而路由无条件返回「正在重启服务器!」——
   有安装任务在跑（`isRestart()=False`）时根本不会重启却照样报成功。
   真机 stub 实测：`isRestart=False -> reboot cmd executed=[]`（没执行）但响应仍是成功。
4. **系统详情接口无负缓存 → 每次请求白等 3 秒**：`getSystemDetails()` 每次
   都在线拉 `curl -fsSL -m 3 http://ipinfo.io/json`，失败时不落任何缓存——
   真机实测模块级单次 3.061s（本机 ipinfo 不可达，每次请求都白等满超时）。
   面板只有 1 个 gthread worker（8 线程），反复打开「系统详情」就反复白占线程。
   修复：失败落空缓存文件做负缓存（5 分钟内不重试），并把「有没有数据」的判定
   从真假值改为 `is None`。真机复验：首次 0.257s、后续 0.032s / 0.047s 且不再发 curl。

附带修掉 `getDiskInfo()` 的下标越界：`df -h` 与 `df -i` 是两次独立 shell 调用，
行数不齐（期间挂载/卸载）时按序号取会抛 IndexError → HTTP 500。

断言策略：能直接跑的函数（`isAllowedUpdateVersion`/`updateServer`/`getDiskInfo`/
`getSystemDetails`）用**真实源码 + 桩**跑；路由函数（`restart_server`）用 `ast`
抽出函数体后在 stub 命名空间里执行**真实源码**（本地无 flask），
避免被注释或 `if False:` 蒙混。

桩的粒度刻意压在**被测模块自己的 `yf` 名**上（`_yf_stub()`），不去改共享的 yf 包
命名空间：一是作用域小、不串台，二是 `testsuite/test_yf_package_contract.py` 要求
被 `patch.object(yf, ...)` 的符号必须登记进 codemod 补丁集，改模块内的名即可绕开
那套登记（本文件不新增补丁符号）。
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
sys.path.insert(0, WEB)
sys.path.insert(0, ROOT)

# 本地开发机没有 psutil（生产面板环境才有）：与仓库既有用法一致用 MagicMock 顶替，
# 本文件所有用例都显式替换 psutil 调用，不依赖其真实行为。
if 'psutil' not in sys.modules:
    sys.modules['psutil'] = mock.MagicMock()

import core.yf as yf  # noqa: E402
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('system_a08')

import utils.system.main as main_mod  # noqa: E402
import utils.system.update as update_mod  # noqa: E402

SYSTEM_PY = os.path.join(WEB, 'admin', 'system', 'system.py')
UPGRADE_PY = os.path.join(WEB, 'admin', 'system', 'upgrade.py')
UPDATE_PY = os.path.join(WEB, 'utils', 'system', 'update.py')
MAIN_PY = os.path.join(WEB, 'utils', 'system', 'main.py')

#: 被测模块会用到的 yf 符号（桩以真实实现为底，只覆盖用例要控制的那几个）
_YF_NAMES = ('execShell', 'safeExecShell', 'execShellRc', 'readFile', 'writeFile',
             'writeFileLog', 'toSize', 'getRunDir', 'getCpuType', 'getOs',
             'getPanelDir', 'getPanelDataDir', 'isAppleSystem', 'isRestart',
             'githubDownload', 'makeDirs', 'deleteFile', 'removeDir', 'returnData')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _get_fn(path, name):
    for node in ast.walk(ast.parse(_read(path))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('未找到函数 %s' % name)


def _fn_src(path, name):
    """函数源码（含装饰器；unparse 后注释全消失，注释/字符串蒙混不了）。"""
    return ast.unparse(_get_fn(path, name))


def _msg_is(res, key):
    """returnData 会做 i18n 替换：按解析后的 msg 判键（不是看 raw 字符串）。"""
    from core.i18n import t as _t
    return res.get('msg') in (key, _t(key))


def _yf_stub(**overrides):
    """给被测模块换一个「yf 名」的桩：真实实现做底 + 本用例的覆盖。"""
    ns = SimpleNamespace()
    for name in _YF_NAMES:
        setattr(ns, name, getattr(yf, name))
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


def _fake_psutil():
    """够 getSystemDetails 跑完的最小 psutil 桩（全部返回真数值，不触发 Mock 比较异常）。"""
    ps = mock.MagicMock()
    ps.cpu_count.return_value = 4
    ps.cpu_freq.return_value = None
    ps.disk_usage.return_value = SimpleNamespace(total=1000, used=400, free=600, percent=40.0)
    ps.virtual_memory.return_value = SimpleNamespace(total=2000, used=800, available=1200, percent=40.0)
    ps.swap_memory.return_value = SimpleNamespace(total=0, used=0, percent=0.0)
    ps.net_if_addrs.return_value = {}
    return ps


class _BlueprintStub(object):
    """裸 exec 路由函数源码时的蓝图桩：route() 原样返回被装饰函数。"""

    def route(self, *args, **kwargs):
        return lambda fn: fn


def _load_route_fn(path, name):
    """在 stub 命名空间里执行**真实源码**，返回可直接调用的路由函数。"""
    ns = {
        'blueprint': _BlueprintStub(),
        'panel_login_required': lambda fn: fn,
        'request': SimpleNamespace(form={}, args={}),
        'render_template': lambda *a, **k: '',
        'yf': SimpleNamespace(),
        'sys': SimpleNamespace(),
    }
    exec(compile(ast.unparse(_get_fn(path, name)), path, 'exec'), ns)
    return ns


class TestA08UpdateVersionGuard(unittest.TestCase):
    """缺陷 1：升级版本参数未校验 → root 命令注入 + 路径穿越。"""

    INJECTIONS = [
        'v9.9.9"; touch /tmp/pwned; echo "',
        "v9.9.9'; touch /tmp/pwned; echo '",
        'v9.9.9`touch /tmp/pwned`',
        'v9.9.9$(touch /tmp/pwned)',
        'v9.9.9|touch /tmp/pwned',
        'v9.9.9;touch /tmp/pwned',
        '../../../../etc',
        '../../../../www/server/etc',
        '/tmp/x',
        'v1.0.0/../../x',
        'v1.0.0\nid',
        'v1.0.0 ',
        '',
    ]

    def test_01_rejects_injection_and_traversal(self):
        for bad in self.INJECTIONS:
            with self.subTest(version=bad):
                self.assertFalse(
                    update_mod.isAllowedUpdateVersion(bad, 'v9.9.9'),
                    'version=%r 必须被拒（它会被拼进下载 URL 与 temp 目录名）' % bad)

    def test_02_accepts_only_detected_tag(self):
        self.assertTrue(update_mod.isAllowedUpdateVersion('v1.2.3', 'v1.2.3'))
        self.assertTrue(update_mod.isAllowedUpdateVersion('1.2.3', 'v1.2.3'))
        self.assertTrue(update_mod.isAllowedUpdateVersion('v1.2.3', '1.2.3'))
        # 同形状但不是本次检测到的 tag：同样拒（否则可指定任意历史/伪造 tag）
        self.assertFalse(update_mod.isAllowedUpdateVersion('v1.2.4', 'v1.2.3'))
        self.assertFalse(update_mod.isAllowedUpdateVersion('v1.2.3', ''))
        self.assertFalse(update_mod.isAllowedUpdateVersion('v1.2.3', None))

    def _call_update(self, version, step, tmpdir, remote_tag='v9.9.9'):
        """走真实的 updateServer，只把「网络 / 面板目录」两处外部依赖换成桩。"""
        urls = []

        def fake_download(url, save_path, timeout=10, min_size=0):
            urls.append(url)
            return False

        with mock.patch.object(update_mod, 'getServerInfo',
                               lambda: {'tag_name': remote_tag, 'name': 'x', 'body': ''}), \
                mock.patch.object(update_mod, 'yf', _yf_stub(
                    isRestart=lambda: True,
                    githubDownload=fake_download,
                    getPanelDir=lambda: tmpdir)):
            res = update_mod.updateServer('update', version, step=step)
        return res, urls

    def test_03_rejected_version_never_reaches_download(self):
        tmp = tempfile.mkdtemp(prefix='yufeng_a08_ver_')
        payload = 'v9.9.9"; touch /tmp/pwned_a08; echo "'
        try:
            res, urls = self._call_update(payload, 'download', tmp)
            self.assertFalse(res['status'], '注入版本号必须被拒')
            self.assertTrue(_msg_is(res, 'system.py_msg_7f876a'),
                            '应回报「升级版本参数非法」，实际=%r' % res['msg'])
            self.assertEqual(urls, [], '被拒的版本号绝不能触发下载（下载 URL 会进 shell）')
            self.assertFalse(os.path.exists('/tmp/pwned_a08'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_04_mutation_positive_control(self):
        """反证：把校验摘掉（旧实现），同一个 payload 就会进下载 URL。"""
        tmp = tempfile.mkdtemp(prefix='yufeng_a08_ver_mut_')
        payload = 'v9.9.9"; touch /tmp/pwned_a08_mut; echo "'
        try:
            with mock.patch.object(update_mod, 'isAllowedUpdateVersion', lambda *a: True):
                res, urls = self._call_update(payload, 'download', tmp)
            self.assertEqual(len(urls), 1, '旧实现下必须真的走到下载（证明断言有效）')
            self.assertIn(payload, urls[0], '旧实现下 payload 原样进下载 URL = 命令注入')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_05_source_guard_runs_before_url_build(self):
        src = _fn_src(UPDATE_PY, 'updateServer')
        self.assertIn('isAllowedUpdateVersion(version, new_ver)', src,
                      'updateServer 必须在拼下载 URL 之前校验 version')
        self.assertLess(src.index('isAllowedUpdateVersion(version, new_ver)'),
                        src.index('archive/refs/tags/'),
                        '校验必须出现在构造下载 URL 之前')

    def test_06_upgrade_route_only_three_params(self):
        """升级路由不接受 url / path 之类的「自定义升级包地址」参数。"""
        src = _fn_src(UPGRADE_PY, 'update_server')
        self.assertNotIn("request.args.get('url'", src)
        self.assertNotIn('request.args.get("url"', src)
        for name in ('panel_type', 'version', 'step'):
            self.assertIn(name, src)


class TestA08InstallRollback(unittest.TestCase):
    """缺陷 2：安装阶段丢弃 cp 返回码 → 拷贝失败仍回报「安装更新成功」。"""

    def _run_install(self, tmpdir, copy_exc=None, backup_ok=True):
        src_dir = os.path.join(tmpdir, 'temp', 'bt_simple-v9.9.9')
        os.makedirs(os.path.join(src_dir, 'web'), exist_ok=True)
        with open(os.path.join(src_dir, 'web', 'marker.txt'), 'w', encoding='utf-8') as fh:
            fh.write('new')

        rollback_calls = []
        remove_calls = []

        def fake_copy(*a, **k):
            if copy_exc is not None:
                raise copy_exc
            return os.path.join(tmpdir, 'web')

        with mock.patch.object(update_mod, 'getServerInfo',
                               lambda: {'tag_name': 'v9.9.9', 'name': 'x', 'body': ''}), \
                mock.patch.object(update_mod, 'backup_panel',
                                  lambda: (backup_ok, '备份成功: /www/backup/panel/x.tar.gz')), \
                mock.patch.object(update_mod, 'rollback_panel',
                                  lambda *a, **k: rollback_calls.append(a) or (True, 'ok')), \
                mock.patch.object(shutil, 'copytree', fake_copy), \
                mock.patch.object(update_mod, 'yf', _yf_stub(
                    isRestart=lambda: True,
                    getPanelDir=lambda: tmpdir,
                    removeDir=lambda p: remove_calls.append(p),
                    writeFileLog=lambda *a, **k: True)):
            res = update_mod.updateServer('update', 'v9.9.9', step='install')
        return res, rollback_calls, remove_calls

    def test_10_copy_uses_shutil_not_shell_concat(self):
        src = _read(UPDATE_PY)
        self.assertNotIn("yf.execShell('cp -rf '", src,
                         '代码覆盖不得拼 shell（src_path 目录名来自解压包）')
        self.assertIn('shutil.copytree(src_path, panel_dir, dirs_exist_ok=True',
                      src, '代码覆盖应走 shutil.copytree')

    def test_11_copy_failure_rolls_back_and_reports_failure(self):
        tmp = tempfile.mkdtemp(prefix='yufeng_a08_cp_')
        try:
            res, rollback_calls, remove_calls = self._run_install(
                tmp, copy_exc=OSError('disk full'))
            self.assertFalse(res['status'], '拷贝失败绝不能回报安装成功')
            self.assertTrue(_msg_is(res, 'system.py_msg_339e87'),
                            '应回报「已回滚到升级前快照」，实际=%r' % res['msg'])
            self.assertEqual(len(rollback_calls), 1, '拷贝失败必须回滚')
            self.assertEqual(remove_calls, [], '回滚路径不得继续清理/推进安装')
            self.assertFalse(os.path.exists(os.path.join(tmp, '.version')),
                             '失败时不得写入 .version')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_12_copy_failure_without_backup_reports_failure(self):
        tmp = tempfile.mkdtemp(prefix='yufeng_a08_cp2_')
        try:
            res, rollback_calls, _ = self._run_install(
                tmp, copy_exc=OSError('disk full'), backup_ok=False)
            self.assertFalse(res['status'])
            self.assertTrue(_msg_is(res, 'system.py_msg_fac254'),
                            '无快照时也要如实报错，实际=%r' % res['msg'])
            self.assertEqual(rollback_calls, [], '没有本次快照就不能拿旧快照去覆盖面板')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_13_rollback_panel_does_not_concat_shell(self):
        src = _fn_src(UPDATE_PY, 'rollback_panel')
        self.assertIn('safeExecShell', src, '回滚解压必须走列表传参，不拼 shell')
        self.assertNotIn('yf.execShell(cmd)', src)


class TestA08RestartServerGuard(unittest.TestCase):
    """缺陷 3：路由无条件回报「正在重启服务器」（异步判定藏在工作线程里）。"""

    def setUp(self):
        self.ns = _load_route_fn(SYSTEM_PY, 'restart_server')
        self.calls = []
        self.ns['sys'].restartServer = lambda: self.calls.append('restart')
        self.ns['yf'].returnData = (
            lambda status, msg, data=None, *a: {'status': status, 'msg': msg})
        self.ns['yf'].isAppleSystem = lambda: False
        self.ns['yf'].isRestart = lambda: False

    def test_20_returns_failure_when_restart_forbidden(self):
        res = self.ns['restart_server']()
        self.assertFalse(res['status'], '有安装任务在跑时不能回报重启成功')
        self.assertTrue(_msg_is(res, 'system.py_msg_0322b3'), res['msg'])
        self.assertEqual(self.calls, [], '被拒时不得触发重启')

    def test_21_dispatches_when_allowed(self):
        self.ns['yf'].isRestart = lambda: True
        res = self.ns['restart_server']()
        self.assertTrue(res['status'])
        self.assertEqual(self.calls, ['restart'])

    def test_22_guard_precedes_dispatch_in_source(self):
        src = _fn_src(SYSTEM_PY, 'restart_server')
        self.assertIn('yf.isRestart()', src)
        self.assertLess(src.index('yf.isRestart()'), src.index('sys.restartServer()'),
                        'isRestart() 判定必须在触发重启之前')

    def test_23_apple_shortcut_still_first(self):
        self.ns['yf'].isAppleSystem = lambda: True
        res = self.ns['restart_server']()
        self.assertFalse(res['status'])
        self.assertTrue(_msg_is(res, 'system.py_msg_529504'), res['msg'])
        self.assertEqual(self.calls, [])


class TestA08SystemDetailsIpCache(unittest.TestCase):
    """缺陷 4：公网 IP 查询无负缓存 → 每次请求白等满 3 秒超时。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_a08_ip_')
        self.cache = os.path.join(self.tmp, 'tmp', 'panel_ip_info.json')
        os.makedirs(os.path.dirname(self.cache), exist_ok=True)
        self.exec_calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _details(self, ipinfo_out):
        def fake_exec(cmd, cwd=None, timeout=None, shell=True):
            if 'ipinfo' in cmd:
                self.exec_calls.append(cmd)
            return (ipinfo_out, '')

        # sys.platform 走 win32 分支 → 缓存落在 getRunDir() 下（= 本用例的临时目录）
        with mock.patch.object(main_mod, 'sys', SimpleNamespace(platform='win32')), \
                mock.patch.object(main_mod, 'psutil', _fake_psutil()), \
                mock.patch.object(main_mod, 'yf', _yf_stub(
                    getRunDir=lambda: self.tmp, execShell=fake_exec)):
            return main_mod.getSystemDetails()

    def test_30_failed_lookup_is_negatively_cached(self):
        self._details('')
        self.assertEqual(len(self.exec_calls), 1, '第一次查不到公网 IP 才允许发 curl')
        self.assertTrue(os.path.exists(self.cache), '失败也要落缓存文件（负缓存）')
        self.assertEqual(os.path.getsize(self.cache), 0, '负缓存内容为空')
        # 第二次必须不再发起阻塞式 curl
        self._details('')
        self.assertEqual(len(self.exec_calls), 1,
                         '5 分钟内的第二次请求不得再发起 3 秒阻塞的 curl')

    def test_31_successful_lookup_is_cached(self):
        data = self._details('{"org": "ISP", "city": "SZ", "country": "CN"}')
        self.assertEqual(len(self.exec_calls), 1)
        self.assertEqual(data['network']['isp'], 'ISP')
        self.assertEqual(data['network']['location'], 'SZ/CN')
        self.assertGreater(os.path.getsize(self.cache), 0)
        self._details('')
        self.assertEqual(len(self.exec_calls), 1, '成功缓存 24h 内不得重查')

    def test_32_corrupt_cache_is_retried_once_then_negative_cached(self):
        with open(self.cache, 'w', encoding='utf-8') as fh:
            fh.write('{not json')
        self._details('')
        self.assertEqual(len(self.exec_calls), 1)
        self._details('')
        self.assertEqual(len(self.exec_calls), 1)

    def test_33_source_uses_none_sentinel_not_truthiness(self):
        src = _fn_src(MAIN_PY, 'getSystemDetails')
        self.assertIn('if ip_data is None:', src,
                      '空 dict（负缓存命中）不能被当成「没查过」再查一次')


class TestA08DiskInfoGuards(unittest.TestCase):
    """附带：df -h 与 df -i 分开执行，行/列数不齐时下标越界 → HTTP 500。"""

    def _disk_info(self, df_h, df_i):
        def fake_exec(cmd, cwd=None, timeout=None, shell=True):
            if cmd.startswith('df -h'):
                return (df_h, '')
            return (df_i, '')

        with mock.patch.object(main_mod, 'yf', _yf_stub(execShell=fake_exec)):
            return main_mod.getDiskInfo()

    def test_40_uneven_rows_do_not_raise(self):
        rows = self._disk_info(
            '/dev/sda2 38G 14G 23G 39% /\n/dev/sdb1 100G 1G 99G 1% /data',
            '/dev/sda2 2526384 281856 2244528 12% /')
        self.assertEqual([r['path'] for r in rows], ['/'])

    def test_41_short_lines_skipped(self):
        rows = self._disk_info(
            '/dev/sda2 38G 14G 23G 39% /',
            '/dev/sda2 2526384 281856 2244528 12% /\n/dev/sdb1 1 2 3')
        self.assertEqual([r['path'] for r in rows], ['/'])

    def test_42_normal_rows_still_parsed(self):
        rows = self._disk_info(
            '/dev/sda2 38G 14G 23G 39% /',
            '/dev/sda2 2526384 281856 2244528 12% /')
        self.assertEqual(rows[0]['size'], ['38G', '14G', '23G', '39%'])
        self.assertEqual(rows[0]['inodes'], ['2526384', '281856', '2244528', '12%'])


class TestA08RememoryEndpointAndFrontend(unittest.TestCase):
    """缺陷 5：首页「释放内存」按钮的后端路由 `/system/rememory` 整体缺失。

    真机事实：`web/static/app/index.js::reMemory()` POST `/system/rememory`，
    而 `web/admin/` 下 grep 不到该路由（真机 `POST /system/rememory` → 302 到登录页 HTML）。
    jQuery 以 `'json'` 解析 HTML 失败 → 成功回调永不执行 → 圈上「正在释放」永久卡住。
    同链路其它部件都在（模板 `mem-release` 圆环、6 语言 `memre_ok*` 键、
    `scripts/rememory.sh`、crontab 的 `rememory` 任务类型）→ 属重构中丢失。

    修复：补 `POST /system/rememory`（契约 = 顶层 `memTotal`/`memRealUsed`，单位 MB，
    与 index.js 的 `* 1024 * 1024` 换算一致），脚本走列表传参 + 面板目录绝对路径
    + 显式超时；`scripts/rememory.sh` 的 `$(pwd)` 依赖改成脚本自身位置；前端补 `.fail()`。

    本类**不执行** `rememory.sh` 本体（它会 reload 生产 mysql/openresty/php83 并
    drop_caches），只做结构断言与 cwd 无关性证明。
    """

    SYS_PY = os.path.join(WEB, 'admin', 'system', 'system.py')
    INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
    SH = os.path.join(ROOT, 'scripts', 'rememory.sh')

    def _route_fn(self, name, script_exists=True):
        """在带 os 的 stub 命名空间里执行真实路由源码（`_load_route_fn` 的 ns 没有 os）。

        `script_exists` 控制 `os.path.exists(脚本)` 的桩结果：本地开发机没有面板
        安装目录，不能让它真实去查文件，否则会掉进「脚本不存在」分支。
        """
        ns = {
            'blueprint': _BlueprintStub(),
            'panel_login_required': lambda fn: fn,
            'request': SimpleNamespace(form={}, args={}),
            'render_template': lambda *a, **k: '',
            'os': SimpleNamespace(path=SimpleNamespace(
                join=os.path.join, exists=lambda p: script_exists)),
            'yf': SimpleNamespace(),
            'sys': SimpleNamespace(),
        }
        exec(compile(ast.unparse(_get_fn(self.SYS_PY, name)), self.SYS_PY, 'exec'), ns)
        return ns

    def test_50_route_is_post_only_and_login_guarded(self):
        tree = ast.parse(_read(self.SYS_PY))
        fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == 'rememory':
                fn = node
        self.assertIsNotNone(fn, '/system/rememory 路由缺失（前端按钮会永久卡在「正在释放」）')
        decs = [ast.unparse(d) for d in fn.decorator_list]
        self.assertTrue(any("methods=['POST']" in d for d in decs),
                        'rememory 必须是 POST（前端 $.post）')
        self.assertTrue(any('panel_login_required' in d for d in decs),
                        'rememory 必须要求登录/API 凭据，不能裸奔')

    def test_51_script_path_is_panel_dir_absolute(self):
        src = ast.unparse(_get_fn(self.SYS_PY, 'rememory'))
        self.assertIn('getPanelDir', src, '脚本路径必须由 yf.getPanelDir() 解析，不能依赖 cwd')
        for banned in ('getcwd', 'pwd', 'chdir'):
            self.assertNotIn(banned, src, 'rememory 不得依赖进程 cwd（%s）' % banned)

    def test_52_no_shell_string_and_timeout_present(self):
        fn = _get_fn(self.SYS_PY, 'rememory')
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        execs = [c for c in calls if isinstance(c.func, ast.Attribute)
                 and c.func.attr in ('execShellRc', 'safeExecShell', 'execShell')]
        self.assertTrue(execs, '必须走 yf 的 shell 助手，不要自拼 subprocess')
        for call in execs:
            src = ast.unparse(call)
            self.assertNotIn('shell=True', src, '禁止 shell=True 字符串拼接')
            self.assertTrue(any(k.arg == 'timeout' for k in call.keywords),
                            '必须带显式超时（脚本会 sleep/reload，不能无限挂住 worker）')

    def test_53_contract_is_top_level_mb_keys(self):
        """契约断言：前端直读顶层 memRealUsed/memTotal，单位 MB。"""
        ns = self._route_fn('rememory')
        ns['yf'] = SimpleNamespace(
            getPanelDir=lambda: '/www/server/yufeng_panel',
            writeFileLog=lambda *a, **k: None,
            returnData=lambda *a, **k: {'__error__': a},
            execShellRc=lambda *a, **k: (0, '', ''),
            getJson=lambda data: {'__json__': data})
        total_bytes = 8 * 1024 * 1024 * 1024 + 512 * 1024 * 1024
        used_bytes = 2 * 1024 * 1024 * 1024 + 256 * 1024 * 1024
        ns['sys'] = SimpleNamespace(getMemInfo=lambda: {
            'memTotal': total_bytes, 'memRealUsed': used_bytes})
        out = ns['rememory']()
        self.assertIn('__json__', out, '成功路径必须回平铺 JSON（前端直读顶层键）')
        data = out['__json__']
        self.assertEqual(sorted(data.keys()), ['memRealUsed', 'memTotal'],
                         '必须是顶层 memTotal/memRealUsed，不能包 envelope')
        self.assertAlmostEqual(data['memTotal'], round(total_bytes / 1048576, 2))
        self.assertAlmostEqual(data['memRealUsed'], round(used_bytes / 1048576, 2))
        self.assertLess(data['memRealUsed'], data['memTotal'])

    def test_54_script_failure_is_reported_not_faked(self):
        ns = self._route_fn('rememory')
        ns['yf'] = SimpleNamespace(
            getPanelDir=lambda: '/www/server/yufeng_panel',
            writeFileLog=lambda *a, **k: None,
            returnData=lambda ok, *a, **k: {'__error__': (ok, a)},
            execShellRc=lambda *a, **k: (1, '', 'boom'),
            getJson=lambda data: {'__json__': data})
        ns['sys'] = SimpleNamespace(getMemInfo=lambda: {
            'memTotal': 1, 'memRealUsed': 1})
        out = ns['rememory']()
        self.assertIn('__error__', out, '脚本 rc!=0 必须如实报错，不能回假成功')
        self.assertFalse(out['__error__'][0])

    def test_55_shell_script_is_cwd_independent(self):
        """`scripts/rememory.sh` 原本用 `curPath=$(pwd)` 推 rootPath，
        面板（cwd=面板目录）与 crontab/手工（cwd=/root）算出的根目录不一致，
        回落分支会指向错误目录。改成按脚本自身位置解析后，任意 cwd 结果相同。"""
        src = _read(self.SH)
        self.assertNotIn('$(pwd)', src, '不得用 $(pwd) 推根目录')
        self.assertIn('BASH_SOURCE', src, '必须用 BASH_SOURCE 定位脚本自身')
        lines = [ln for ln in src.splitlines()
                 if 'SCRIPT_DIR=' in ln or 'rootPath=' in ln]
        self.assertTrue(lines, '未找到 rootPath 解析行')
        bash = shutil.which('bash')
        if not bash:
            self.skipTest('未安装 bash，跳过脚本执行校验')
        # 必须让 BASH_SOURCE 真实生效：`bash -c` 下 BASH_SOURCE 是空的
        # （dirname "" = "." → 结果退化成 cwd，测了个寂寞）。所以把**真实脚本的
        # 路径解析行**截断成临时副本，当文件执行；三个不同 cwd 下结果必须一致，
        # 且只能由「脚本自身位置」推出来。
        tmpdir = tempfile.mkdtemp(prefix='yf_a08_sh_')
        self.addCleanup(shutil.rmtree, tmpdir, True)
        copy = os.path.join(tmpdir, 'rememory.sh')
        with open(copy, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#!/bin/bash\n' + '\n'.join(lines) + '\necho "$rootPath"\n')
        # Windows 路径里的反斜杠在 bash 里会被当转义字符 → BASH_SOURCE 解析失败，
        # 所以传给 bash 的路径必须正斜杠化（git-bash 认 C:/... 形式）。
        copy_argv = copy.replace(os.sep, '/')
        outs = []
        for cwd in (ROOT, os.path.join(ROOT, 'web'), tempfile.gettempdir()):
            proc = subprocess.run([bash, copy_argv], capture_output=True, text=True,
                                  cwd=cwd, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outs.append(proc.stdout.strip())
        self.assertEqual(len(set(outs)), 1,
                         '不同 cwd 下 rootPath 必须一致，实际：%r' % (outs,))
        # 期望值必须用 bash 自己算：git-bash 里 /tmp 就是 Windows 的 %TEMP%，
        # Python 侧 os.path 算出来的路径写法与 bash 看到的不是同一套，硬比会假失败。
        # 语义：rootPath = 脚本所在目录的上一级的上一级（部署时 <面板>/scripts → /www/server）。
        probe = 'd=$(cd "$(dirname "$1")" && pwd); dirname "$(dirname "$d")"'
        expect = subprocess.run([bash, '-c', probe, '_', copy_argv],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(expect.returncode, 0, expect.stderr)
        self.assertEqual(outs[0], expect.stdout.strip(),
                         'rootPath 应只由脚本自身位置推出（与 cwd 无关）')
        syntax = subprocess.run([bash, '-n', self.SH], capture_output=True, text=True,
                                timeout=30)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    @staticmethod
    def _brace_block(src, marker):
        """从 marker 后第一个 '{' 开始做花括号配对，返回块体（防“留个空壳”蒙混）。"""
        i = src.find(marker)
        if i < 0:
            return None
        k = src.find('{', i)
        depth = 0
        end = k
        while end < len(src):
            if src[end] == '{':
                depth += 1
            elif src[end] == '}':
                depth -= 1
                if depth == 0:
                    break
            end += 1
        return src[k:end + 1]

    def _restore_mask_body(self):
        body = self._brace_block(_read(self.INDEX_JS), 'var restoreMask = function')
        self.assertIsNotNone(
            body, 'reMemory 里找不到 restoreMask 失败出口（遮罩不会还原）')
        return body

    def test_56_frontend_fail_restores_mask(self):
        body = self._restore_mask_body()
        for need in ('mem-release', 'removeClass("mem-action")', 'mem-re-min', 'layer.msg'):
            self.assertIn(need, body, 'restoreMask 缺 %s，遮罩不会被还原' % need)
        self.assertGreater(len(body.strip()), 80, 'restoreMask 是空壳')
        src = _read(self.INDEX_JS)
        self.assertIn(".fail(restoreMask)", src,
                      '$.post(\'/system/rememory\') 必须挂失败出口：HTTP 失败时遮罩会永久卡住')

    def test_57_loading_mask_html_is_restored(self):
        """失败时要还原成加载前的真实百分比（而不是写死 --%）。"""
        body = self._restore_mask_body()
        self.assertIn('$mask.html(maskHtml)', body,
                      '失败时必须用加载前快照还原遮罩，不能留「正在释放」文案')
        src = _read(self.INDEX_JS)
        i = src.find('function reMemory()')
        seg = src[i:src.find("$.post('/system/rememory'", i)]
        self.assertIn('var maskHtml = $mask.html()', seg,
                      'reMemory 必须先快照加载前的遮罩内容')

    def test_59_success_callback_checks_status_contract(self):
        """后端失败时返回的是 `returnData(False, ...)`（无 memTotal/memRealUsed），
        而成功回调原来直接拿 `rdata.memRealUsed` 算百分比 → NaN 且遮罩不复位。
        契约守卫：回调必须先判 `status === false`（或缺 memTotal）并走失败出口。"""
        src = _read(self.INDEX_JS)
        i = src.find("$.post('/system/rememory'")
        self.assertGreater(i, -1)
        body = self._brace_block(src[i:], 'function(rdata)')
        self.assertIsNotNone(body, '找不到成功回调体')
        self.assertIn('rdata.status === false', body,
                      '成功回调必须识别 status:false（否则会显示 NaN 并卡住遮罩）')
        self.assertIn('restoreMask()', body, 'status:false 必须走失败出口')

    def test_58_js_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过 JS 语法校验')
        proc = subprocess.run([node, '--check', self.INDEX_JS],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == '__main__':
    unittest.main()
