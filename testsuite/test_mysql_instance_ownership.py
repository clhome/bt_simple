# coding: utf-8
"""MySQL「装了但不可用」根因守卫：**跑着的 mysqld 到底是不是我们这一个实例**。

## 现场（2026-10-27 真机，装完 MySQL 5.7 后点性能优化）

    [orm] socket 文件不存在（/www/server/mysql/mysql.sock），退回 TCP 连接 localhost:3306
    [orm] query 连接失败: (1045, "Access denied for user 'root'@'127.0.0.1' (using password: YES)")
    → 数据库密码错误,在管理列表-点击【修复】!

再点「日志」：

    File "/www/server/yufeng_panel/plugins/mysql/index.py", line 644, in binLog
        for n in os.listdir(path):
    FileNotFoundError: [Errno 2] No such file or directory: '/www/server/mysql/data'

## 根因

`getMysqldPid()` 取的是「机器上任意 mysqld」。机器上若另有系统装的 MySQL/MariaDB
占着 3306（apt/yum 装过、或以前装过别家面板），面板会：

  * 把**别人的**实例当成自己的（`status()` 返回 start）；
  * 所有 SQL 打到别人的库 → 口令不同 → 1045 root@127.0.0.1，点【修复】还会去
    停别人的实例、加 skip-grant-tables、改别人 root 口令；
  * 自己的 `/www/server/mysql/data` 从没初始化 → 日志页 listdir 直接 500。

## 修法

1. `getRunningMysqldProcs()`：只读 `/proc`，拿到每个 mysqld 的 exe / cmdline / datadir；
2. `instanceOwnership()`：判定 ok / not_running / foreign_only / mixed / datadir_missing；
3. `runInfo`（性能优化、当前状态）与 `fixDbAccess`（修复）先判归属，foreign 直接
   给出「先停掉冲突实例」的处置建议，不再报「数据库密码错误」，也不误伤别人的库；
4. `binLog` / `binLogList` 数据目录缺失时返回可读错误，不再 traceback；
5. install.sh 装完跑 `self_check`，不通过即非 0 退出（不再「安装成功」但不可用）；
6. `getSocketFile()` 在配置路径不存在时，采信**本插件自己**那个 mysqld 的 `--socket=`。
"""
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
INSTALL_SH = os.path.join(ROOT, 'plugins', 'mysql', 'install.sh')

for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from testsuite._isolation import isolate  # noqa: E402

isolate('mysql_instance_ownership')

_MOD = None


def _module():
    """按路径加载 `plugins/mysql/index.py`（模块级会 chdir 到 web/，这里恢复 cwd）。"""
    global _MOD
    if _MOD is not None:
        return _MOD
    name = 'yf_mysql_instance_ownership_under_test'
    spec = importlib.util.spec_from_file_location(name, IDX)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    _MOD = mod
    return mod


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _as_dict(res):
    """`yf.returnJson()` 返回的是 JSON 字符串，统一解析成 dict 便于断言。"""
    if isinstance(res, dict):
        return res
    if isinstance(res, (str, bytes)):
        try:
            return json.loads(res)
        except Exception:
            return {}
    if isinstance(res, bool):
        return {'status': res}
    return {}


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


class _Fixture(object):
    """搭一个假的面板 MySQL 目录树，并替换掉读 /proc 与配置读取。"""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_own_')
        self.server = os.path.join(self.tmp, 'mysql')
        os.makedirs(os.path.join(self.server, 'bin'), exist_ok=True)
        os.makedirs(os.path.join(self.server, 'etc'), exist_ok=True)
        self.data = os.path.join(self.server, 'data')
        self.sock = os.path.join(self.server, 'mysql.sock')
        self.mycnf = os.path.join(self.server, 'etc', 'my.cnf')
        with open(self.mycnf, 'w', encoding='utf-8') as fh:
            fh.write('[mysqld]' + chr(10))
            fh.write('datadir = %s' % self.data + chr(10))
            fh.write('socket = %s' % self.sock + chr(10))
            fh.write('port = 3306' + chr(10))
            fh.write('log-bin=mysql-bin' + chr(10) + 'binlog_format=mixed' + chr(10))
        # 我们的 mysqld 二进制
        with open(os.path.join(self.server, 'bin', 'mysqld'), 'w') as fh:
            fh.write('#!/bin/sh\n')
        os.chmod(os.path.join(self.server, 'bin', 'mysqld'), 0o755)
        self.mod = _module()
        self._orig = {}

    def patch(self, **kw):
        m = self.mod
        for name, value in kw.items():
            if name not in self._orig:
                self._orig[name] = getattr(m, name)
            setattr(m, name, value)
        return self

    def install_defaults(self, procs=(), sock=..., datadir=...):
        m = self.mod
        self.patch(
            getServerDir=lambda *a, **k: self.server,
            getDataDir=lambda: (self.data if datadir is ... else datadir),
            _cnfValue=lambda *a, **k: (self.sock if sock is ... else sock),
            getRunningMysqldProcs=lambda: list(procs),
            # 让「无法判定归属」的分支不生效（Windows 上没有 /proc）
            _procAvailable=lambda: True,
            getConf=lambda: self.mycnf,
        )
        return self

    def close(self):
        for name, value in self._orig.items():
            setattr(self.mod, name, value)
        self._orig = {}
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 便捷构造
    def ours_proc(self, cmdline='', datadir=''):
        return {'pid': 111, 'exe': os.path.join(self.server, 'bin', 'mysqld'),
                'cmdline': cmdline, 'data_dir': datadir or self.data}

    def foreign_proc(self):
        return {'pid': 222, 'exe': '/usr/sbin/mysqld',
                'cmdline': '/usr/sbin/mysqld --datadir=/var/lib/mysql',
                'data_dir': '/var/lib/mysql'}


class TestOwnership(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture()

    def tearDown(self):
        self.fx.close()

    def test_01_not_running(self):
        self.fx.install_defaults(procs=[])
        own = self.fx.mod.instanceOwnership()
        self.assertEqual('not_running', own['status'], own)
        self.assertFalse(own['datadir_exists'], '前提：本用例的数据目录还没建')

    def test_02_ours_running_ok(self):
        os.makedirs(os.path.join(self.fx.data, 'mysql'), exist_ok=True)
        open(self.fx.sock, 'w').close()
        self.fx.install_defaults(procs=[self.fx.ours_proc()])
        own = self.fx.mod.instanceOwnership()
        self.assertEqual('ok', own['status'], own)
        self.assertTrue(own['datadir_exists'])
        self.assertTrue(own['socket_exists'])
        self.assertEqual('', own['reason'])

    def test_03_foreign_only(self):
        """机器上只有别人的 mysqld → 必须认出来（这就是 1045 的来源）。"""
        self.fx.install_defaults(procs=[self.fx.foreign_proc()])
        own = self.fx.mod.instanceOwnership()
        self.assertEqual('foreign_only', own['status'], own)
        self.assertIn('3306', own['reason'])
        self.assertIn('停', own['reason'], '要给出处置建议（先停掉冲突实例）')

    def test_04_mixed(self):
        os.makedirs(os.path.join(self.fx.data, 'mysql'), exist_ok=True)
        self.fx.install_defaults(procs=[self.fx.ours_proc(), self.fx.foreign_proc()])
        own = self.fx.mod.instanceOwnership()
        self.assertEqual('mixed', own['status'], own)
        self.assertIn('端口冲突', own['reason'])

    def test_05_datadir_missing(self):
        """我们的进程在跑，但数据目录不存在（初始化被跳过）→ 单独一类。"""
        self.fx.install_defaults(procs=[self.fx.ours_proc()])
        own = self.fx.mod.instanceOwnership()
        self.assertEqual('datadir_missing', own['status'], own)
        self.assertIn('数据目录不存在', own['reason'])

    def test_06_proc_parsing_is_readonly_and_tolerant(self):
        """`getRunningMysqldProcs` 只读 /proc；没有 /proc（Windows）也要返回空列表。"""
        m = self.fx.mod
        # 还原 fixture 的替换，调真实的 /proc 读取实现
        self.fx.close()
        procs = m.getRunningMysqldProcs()
        self.assertIsInstance(procs, list)
        for p in procs:
            self.assertIn('pid', p)
            self.assertIn('exe', p)
            self.assertIn('cmdline', p)
        # 空夹具环境（无 /proc 或没有 mysqld）时归属判定必须是 unknown/not_running，不能崩
        own = m.instanceOwnership()
        self.assertIn(own['status'], ('unknown', 'not_running', 'foreign_only', 'ok',
                                      'mixed', 'datadir_missing'))

    def test_07_socket_from_running_instance(self):
        """配置里的 socket 不存在时，采信我们自己 mysqld 的 --socket=。"""
        real_sock = os.path.join(self.fx.tmp, 'real.sock')
        open(real_sock, 'w').close()
        os.makedirs(os.path.join(self.fx.data, 'mysql'), exist_ok=True)
        self.fx.install_defaults(
            procs=[self.fx.ours_proc(cmdline='/x/mysql/bin/mysqld --socket=%s' % real_sock)])
        m = self.fx.mod
        m.getSocketFile = self.fx._orig.get('getSocketFile') or getattr(m, 'getSocketFile')
        # 直接用模块原始实现（fixture 没替换它）
        sock = m.getSocketFile()
        self.assertEqual(real_sock, sock)

    def test_08_socket_not_taken_from_foreign_instance(self):
        """别人的实例的 socket 绝不能拿来用（会把口令/数据打到别人的库）。"""
        foreign_sock = os.path.join(self.fx.tmp, 'foreign.sock')
        open(foreign_sock, 'w').close()
        self.fx.install_defaults(
            procs=[{'pid': 9, 'exe': '/usr/sbin/mysqld',
                    'cmdline': '/usr/sbin/mysqld --socket=%s' % foreign_sock,
                    'data_dir': '/var/lib/mysql'}])
        sock = self.fx.mod.getSocketFile()
        self.assertNotEqual(foreign_sock, sock)


class TestCallersRefuseAndDegrade(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture()
        self.fx.install_defaults(procs=[])

    def tearDown(self):
        self.fx.close()

    def test_01_run_info_reports_instance_problem(self):
        self.fx.install_defaults(procs=[self.fx.foreign_proc()])
        # status 在本夹具里没有真实 PID 文件，直接声明「进程在跑」以走到归属判定
        self.fx.patch(status=lambda *a, **k: 'start')
        res = _as_dict(self.fx.mod.runInfo('5.7'))
        self.assertIs(res.get('status'), False, res)
        self.assertIn('实例异常', res['msg'])
        self.assertNotIn('数据库密码错误', res['msg'], '不该只报密码错误（会引导用户白点修复）')

    def test_02_run_info_does_not_query_foreign_db(self):
        queried = []

        class _Db(object):
            def query(self, sql, *a, **k):
                queried.append(sql)
                return []

        self.fx.install_defaults(procs=[self.fx.foreign_proc()])
        self.fx.patch(pMysqlDb=lambda *a, **k: _Db())
        self.fx.mod.runInfo('5.7')
        self.assertEqual([], queried, '判定为别人的实例后不能再发 SQL')

    def test_03_fix_db_access_refuses_foreign(self):
        called = []
        self.fx.install_defaults(procs=[self.fx.foreign_proc()])
        self.fx.patch(
            appCMD=lambda *a, **k: called.append(a),
            pMysqlDb=lambda *a, **k: type('D', (), {'query': lambda s, q: []})(),
        )
        res = _as_dict(self.fx.mod.fixDbAccess('5.7'))
        self.assertIs(res.get('status'), False, res)
        self.assertEqual([], called, '【修复】不能去停别人实例/加 skip-grant-tables')

    def test_04_binlog_degrades_without_datadir(self):
        """日志页：数据目录不存在要返回可读错误，不能再抛 FileNotFoundError。"""
        self.fx.install_defaults(procs=[self.fx.foreign_proc()])
        # 数据目录不存在 → 必须返回可读错误（不能 traceback）
        self.fx.patch(getArgs=lambda: {'version': ''})
        res = _as_dict(self.fx.mod.binLog('5.7'))
        self.assertIn('数据目录不存在', res.get('msg') or '', res)

    def test_05_binlog_list_degrades_without_datadir(self):
        self.fx.patch(getArgs=lambda: {'page': '1', 'page_size': '10', 'tojs': 'x'})
        res = _as_dict(self.fx.mod.binLogList())
        self.assertIs(res.get('status'), False, res)
        self.assertIn('数据目录不存在', res['msg'])


class TestInstallSelfCheck(unittest.TestCase):

    def test_01_install_runs_self_check(self):
        code = _code_only(_read(INSTALL_SH))
        self.assertIn('index.py self_check', code, '装完必须自检（否则「安装成功但不可用」）')
        self.assertIn('[ERROR] MySQL 自检未通过', code)

    def test_02_index_has_self_check_entry(self):
        src = _read(IDX)
        self.assertIn("func == 'self_check'", src)
        self.assertRegex(src, r"sys\.exit\(0 if _sc\.get\('status'\) else 1\)",
                         'self_check 必须以退出码表达结果（install.sh 靠它判）')

    def test_03_datadir_readers_degrade_gracefully(self):
        """binLog / binLogList（面板「日志」页）必须先判数据目录存在。"""
        src = _read(IDX)
        for fn in ('binLog', 'binLogList'):
            m = re.search(r'\ndef %s\(.*?\n(?=\ndef )' % fn, src, re.S)
            self.assertTrue(m, '没找到函数 %s' % fn)
            body = m.group(0)
            self.assertIn('数据目录不存在', body,
                          '%s 在数据目录缺失时没有可读错误（会 500 traceback）' % fn)
            self.assertRegex(body, r'os\.path\.isdir\(',
                             '%s 必须先判 isdir 再 listdir' % fn)


if __name__ == '__main__':
    unittest.main()
