# coding: utf-8
"""计划任务「执行」按钮必须立刻执行（忽略执行时段/日期限制）回归守卫。

现场症状（真机）：
    任务 `test` 是「每 30 分钟执行（限制: 从 09:00 起）」，早上 07:49 点「执行」，
    日志里只有：
        ★[2026-10-27 07:49:34] 跳过执行：未到允许的开始时间(0900)
    —— 按钮看起来“没反应”，实际是脚本把自己 exit 了。

根因：`getShell()` 把「执行时段限制」「日期类型限制」判定直接写进了任务脚本，
而手动执行（`startTask()` 只是 `Popen([脚本])`）走的是同一个脚本，于是 cron 触发
和手动触发共用同一套前置判定，手动执行被自己设的时段窗口挡住。

修法（两侧都要，缺一不可）：
  1. 生成的脚本把前置判定包进 `if [ "${YF_CRON_FORCE:-0}" = "1" ] ... else ... fi`，
     并在脚本里留能力标记 `#YF_CRON_FORCE_SUPPORTED`；
  2. `startTask()` 用 `Popen(..., env={YF_CRON_FORCE: '1'})` 启动，cron 触发时不带这个
     变量，判定照旧；
  3. 存量脚本自愈：旧脚本没有标记 → `startTask()` 就地把脚本重生一次，
     升级后不必让用户重新保存任务也能点执行。

本测试用**真 bash** 跑真生成的脚本，验证「不带变量 → 跳过」「带变量 → 真跑」。
"""
import ast
import hashlib
import io
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
CRONTAB_PY = os.path.join(project_dir, 'web', 'utils', 'crontab.py')

FORCE_ENV = 'YF_CRON_FORCE'
FORCE_MARKER = '#YF_CRON_FORCE_SUPPORTED'
RAN = 'YF_MANUAL_RUN_OK'


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def _func_src(name, cls=None):
    """按 AST 行号切出函数源码（避免断言被注释/文档串糊过去）。"""
    src = _read(CRONTAB_PY)
    tree = ast.parse(src)
    body = tree.body
    if cls:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                body = node.body
                break
        else:
            raise AssertionError('未找到类 %s' % cls)
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s（%s）' % (name, cls or 'module'))


def _code_only(src):
    out = []
    for line in src.splitlines():
        if line.strip().startswith('#'):
            continue
        out.append(line)
    return '\n'.join(out)


def _find_real_bash():
    """找一个**能用**的 bash。

    Windows 上 `which bash` 往往命中 C:\\Windows\\System32\\bash.exe（WSL 存根），
    未装 WSL 时它只会输出一堆乱码/报错，所以必须真跑一句验证。
    找不到就把「真跑脚本」那几条用例跳过（结构断言照跑）。
    """
    cands = []
    if os.name == 'nt':
        for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                     os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
            cands.append(os.path.join(base, 'Git', 'bin', 'bash.exe'))
            cands.append(os.path.join(base, 'Git', 'usr', 'bin', 'bash.exe'))
    cands.extend([shutil.which('bash'), shutil.which('bash.exe')])
    for cand in cands:
        if not cand or not os.path.exists(cand):
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo YF_BASH_OK'], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            continue
        if b'YF_BASH_OK' in proc.stdout:
            return cand
    return None


BASH = _find_real_bash()


class _FakeYf(object):
    """`core.yf` 替身：把 getShell 的落盘重定向到临时目录。"""

    EXEC_SERVICE_TIMEOUT = 10
    ROOT = None   # 由测试注入

    @staticmethod
    def returnData(status, msg, data=None, *args):
        return {'status': status, 'msg': msg, 'data': data}

    _ROOT = '/tmp/yf_manual_run_test'

    @classmethod
    def getServerDir(cls):
        return os.path.join(cls._ROOT, 'server')

    @classmethod
    def getPanelDir(cls):
        return os.path.join(cls._ROOT, 'panel')

    @staticmethod
    def getPanelTmp():
        return os.path.join(_FakeYf._ROOT, 'panel', 'tmp')

    @staticmethod
    def md5(value):
        return hashlib.md5(str(value).encode('utf-8')).hexdigest()

    @staticmethod
    def shlexQuote(value):
        return shlex.quote(str(value))

    @staticmethod
    def writeFile(path, content, *args, **kwargs):
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        return True

    @staticmethod
    def readFile(path):
        with io.open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            return fh.read()

    @staticmethod
    def makeDirs(path):
        os.makedirs(path, exist_ok=True)
        return True

    @staticmethod
    def isAppleSystem():
        return False

    @staticmethod
    def writeFileLog(msg, *args):
        return True

    @staticmethod
    def writeLog(category, msg, *args):
        return True

    @staticmethod
    def formatDate():
        return '2026-10-27 00:00:00'

    @staticmethod
    def execShell(cmd, *args, **kwargs):
        return ''

    @staticmethod
    def checkPid(pid):
        return False


def _load_namespace():
    src = _read(CRONTAB_PY)
    tree = ast.parse(src)
    keep = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ns = {
        'os': os, 're': __import__('re'), 'time': time, 'json': __import__('json'),
        'logging': logging, 'threading': __import__('threading'),
        'multiprocessing': __import__('multiprocessing'),
        'yf': _FakeYf, 'thisdb': object(),
        '_t': lambda key, *args: (args[0] if args else key),
        '_log': logging.getLogger('crontab_manual_run_test'),
    }
    exec(compile(ast.Module(body=keep, type_ignores=[]), CRONTAB_PY, 'exec'), ns)
    return ns


def _minute_task(**over):
    """「每 N 分钟执行 + 时段限制」的任务行（限制窗口故意设在“还没到”）。"""
    now = time.localtime()
    start_h = min(now.tm_hour + 2, 23)
    row = {
        'id': 1, 'name': 'test', 'type': 'minute-n', 'where1': '30',
        'where_hour': '', 'where_minute': '', 'echo': 'aaaabbbbccccdddd',
        'status': 1, 'save': '', 'backup_to': 'localhost', 'stype': 'toShell',
        'sname': 'ALL', 'sbody': 'echo ' + RAN, 'url_address': '', 'attr': '',
        'day_type': 0,
        'min_start_en': 1, 'min_start_h': start_h, 'min_start_m': 0,
        'min_end_en': 0, 'min_end_h': 23, 'min_end_m': 59,
        'last_run_time': '', 'add_time': '', 'update_time': '',
    }
    row.update(over)
    return row


class TestManualRunIgnoresScheduleGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='yf_manual_run_')
        _FakeYf._ROOT = cls.tmp
        cls.ns = _load_namespace()
        cls.obj = cls.ns['crontab']()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _script_path(self, info):
        name = self.obj.getShell(dict(info))
        self.assertTrue(name, 'getShell 必须生成脚本')
        path = os.path.join(_FakeYf.getServerDir(), 'cron', name)
        self.assertTrue(os.path.exists(path), '脚本必须落盘：%s' % path)
        return path

    def _run(self, path, with_force):
        env = dict(os.environ)
        env.pop(FORCE_ENV, None)
        if with_force:
            env[FORCE_ENV] = '1'
        run_path = path.replace('\\', '/') if os.name == 'nt' else path
        proc = subprocess.run([BASH, run_path], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=120)
        return proc.stdout.decode('utf-8', 'replace')

    # ---- 1. 源码结构：守卫必须存在，且只在手动执行时绕过 ----
    def test_01_start_task_injects_force_env(self):
        src = _code_only(_func_src('startTask', 'crontab'))
        self.assertIn("env[CRON_FORCE_ENV] = '1'", src,
                      'startTask 必须给子进程注入 YF_CRON_FORCE=1，否则手动执行仍会被时段限制跳过')
        self.assertIn('env=env', src, 'Popen 必须带上这个环境')
        self.assertIn("yf.shlexQuote(CRON_FORCE_ENV) + '=1 '", src,
                      'sh 兜底路径同样要带开关（且变量必须走 shlexQuote，棘轮门禁不许新增裸拼接）')
        self.assertIn('_prepare_manual_run_script', src,
                      '手动执行前必须先确保脚本存在（存量脚本要自愈，停用任务也要能手动跑）')
        self.assertNotIn('syncToCrond(', _code_only(_func_src('_prepare_manual_run_script', 'crontab')),
                         '为手动执行不能走 syncToCrond：status=0 会被拒，写 crontab 还会把停用任务复活')

    def test_02_gate_wrapped_by_force_guard(self):
        src = _func_src('getShell', 'crontab')
        self.assertIn('CRON_FORCE_ENV', src)
        self.assertIn(':-0}', src, '未设置变量时（cron 触发）必须保持原判定')
        self.assertIn('gate_checks', src, '时段/日期判定必须集中起来统一包裹')
        # 判定不能被直接 head + 追加（那样就绕过了开关）
        code = _code_only(src)
        self.assertNotIn('head = head + time_check', code)
        self.assertNotIn('head = head + workday_check', code)

    def setUp(self):
        if BASH is None:
            self.skipTest('没有可用的 bash，跳过真跑脚本的用例')

    # ---- 2. 真 bash：不带变量 → 跳过；带变量 → 真跑 ----
    def test_03_cron_trigger_still_skipped(self):
        path = self._script_path(_minute_task())
        content = _FakeYf.readFile(path)
        self.assertIn(FORCE_MARKER, content, '脚本必须带能力标记（存量自愈靠它）')
        out = self._run(path, with_force=False)
        self.assertIn('跳过执行：未到允许的开始时间', out,
                      'cron 触发路径必须保留时段限制（不能被一起绕过）')
        self.assertNotIn(RAN, out, '未到时段时任务体不能被执行')

    def test_04_manual_run_executes_immediately(self):
        path = self._script_path(_minute_task())
        out = self._run(path, with_force=True)
        self.assertNotIn('跳过执行', out, '手动执行不能被时段限制跳过')
        self.assertIn('手动执行：已忽略执行时段/日期限制', out, '日志要说清楚本次忽略了限制')
        self.assertIn(RAN, out, '手动执行必须真的把任务跑起来')

    def test_05_manual_run_ignores_day_type_gate(self):
        """日期类型限制（工作日/节假日）同样要跳过，且不能为了判定去联网。"""
        path = self._script_path(_minute_task(day_type=2, min_start_en=0))
        content = _FakeYf.readFile(path)
        self.assertIn('日期类型判定', content)
        self.assertIn(FORCE_MARKER, content)
        out = self._run(path, with_force=True)
        self.assertNotIn('跳过执行', out)
        self.assertNotIn('timor.tech', out, '手动执行不应发起节假日接口请求')
        self.assertIn(RAN, out)

    def test_06_in_window_manual_run_also_executes(self):
        """已经在允许时段内的任务，手动执行同样直接跑（不受判定顺序影响）。"""
        now = time.localtime()
        path = self._script_path(_minute_task(min_start_h=0, min_start_m=0,
                                             min_end_en=1, min_end_h=23, min_end_m=59))
        out = self._run(path, with_force=True)
        self.assertIn(RAN, out)
        self.assertNotIn('跳过执行', out)

    # ---- 3. 存量/缺失脚本自愈 ----
    def test_07_legacy_script_regenerated(self):
        info = _minute_task()
        name = self.obj.getShell(dict(info))
        path = os.path.join(_FakeYf.getServerDir(), 'cron', name)
        # 伪装成升级前的老脚本（没有能力标记，判定无条件生效）
        _FakeYf.writeFile(path, '#!/bin/bash\necho "跳过执行：未到允许的开始时间(0900)"\nexit 0\n')
        self.assertNotIn(FORCE_MARKER, _FakeYf.readFile(path))

        class _Db(object):
            @staticmethod
            def getCrond(cron_id):
                row = dict(info)
                row['where_hour'] = row.get('hour', '')
                row['where_minute'] = row.get('minute', '')
                return row

        self.ns['thisdb'] = _Db()
        obj = self.ns['crontab']()
        ok = obj._prepare_manual_run_script(1, _Db.getCrond(1), path)
        self.assertTrue(ok, '存量脚本应被自愈重生')
        regenerated = _FakeYf.readFile(path)
        self.assertIn(FORCE_MARKER, regenerated, '重生后的脚本必须带能力标记')
        self.assertIn(FORCE_ENV, regenerated)
        self.assertNotIn('跳过执行：未到允许的开始时间(0900)', regenerated)

    def test_08_disabled_task_gets_script_without_touching_crontab(self):
        """停用中的任务点「执行」也要能立刻跑：只生成脚本，不写系统 crontab。"""
        info = _minute_task(status=0, echo='manual_only_echo')
        cmd_file = os.path.join(_FakeYf.getServerDir(), 'cron', info['echo'])
        if os.path.exists(cmd_file):
            os.remove(cmd_file)

        class _Db(object):
            @staticmethod
            def getCrond(cron_id):
                return dict(info)

        self.ns['thisdb'] = _Db()
        obj = self.ns['crontab']()
        wrote = {'crontab': False}
        obj.syncToCrond = lambda cron_id: wrote.__setitem__('crontab', True) or True
        ok = obj._prepare_manual_run_script(1, dict(info), cmd_file)
        self.assertTrue(ok, '停用任务的脚本缺失时，手动执行也必须能生成脚本')
        self.assertTrue(os.path.exists(cmd_file), '脚本必须落盘')
        self.assertFalse(wrote['crontab'], '绝不能走 syncToCrond（会把停用任务重新写进 crontab）')
        content = _FakeYf.readFile(cmd_file)
        self.assertIn(FORCE_MARKER, content)
        out = self._run(cmd_file, with_force=True)
        self.assertIn(RAN, out, '停用任务手动执行必须真跑')

    def test_09_no_fake_success_when_script_cannot_be_built(self):
        """脚本生成失败时必须返回失败，不能报「已执行」。"""
        src = _code_only(_func_src('startTask', 'crontab'))
        self.assertIn('_prepare_manual_run_script', src)
        self.assertIn('return yf.returnData(False', src,
                      '脚本拿不到时要明确失败（否则用户看到成功但日志一行没新增）')
        idx = src.index('_prepare_manual_run_script')
        self.assertIn('False', src[idx:src.index('try:', idx)], '失败分支必须存在')


if __name__ == '__main__':
    unittest.main()
