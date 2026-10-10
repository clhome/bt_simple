# coding: utf-8
r"""命令执行原语的「超时后死锁」回归守卫。

## 故障现场（真机 Debian12，2026-10-10）

    root@debian:~# yf 1          # 等价于 bs 1：重启面板服务
    ^CTraceback (most recent call last):
      File ".../web/core/yf/__init__.py", line 89, in safeExecShell
        data = sub.communicate(input=payload, timeout=timeout)
    subprocess.TimeoutExpired: Command '['/etc/rc.d/init.d/yf', 'restart']' timed out after 30 seconds
    During handling of the above exception, another exception occurred:
      File ".../web/core/yf/__init__.py", line 92, in safeExecShell
        data = sub.communicate()          # ← 无超时：永久阻塞
    KeyboardInterrupt

用户按 Ctrl+C 才退出；更糟的是 SIGINT 打进整个前台进程组，**打断了正在执行的
`yf restart` 脚本**（stop 已执行、start 未执行），面板被留在停止态 —— 表现为
「御风面板无法启动」。

## 根因（三条，缺一不可，都已真机复现）

1. **无界等待**：`except subprocess.TimeoutExpired` 里 `sub.kill()` 之后调用
   **不带 timeout 的** `communicate()`。只要 stdout/stderr 管道还被别的进程持有，
   它永远等不到 EOF。`safeExecShell` / `execShell` / `execShellRc` 三个原语同病。
2. **管道被孙子进程持有**：init.d 的 `cd X && python3 panel_task.py >> log 2>&1 &`
   只重定向了「被执行的命令」，承载它的子 shell 仍继承着调用方的 stdout/stderr，
   而它的存活期与 panel_task.py 一样长（真机实测：主脚本 12s 就退出，管道却一直
   不关）→ 调用方必然撞上 30s 超时，再撞上第 1 条的死锁。
3. **超时值过紧**：`restart` 本体真机实测 ~12s，init.d 内部端口等待上限 30s，
   而 `panel_tools.py` 用 safeExecShell 的默认 30s。

## 断言策略

* 死锁/进程组这类「行为」必须**真跑**：用 `sys.executable` 起子进程，不依赖 bash
  （门禁在 Windows 上也要跑）。
* 结构类断言一律走 `ast`（正则会被注释/字符串蒙混，例如本文件顶部就写着旧代码）。
"""

import ast
import os
import subprocess
import sys
import time
import unittest

#: 变异自证时指向临时副本（见 test/_exec_timeout_mutation.py）；正常门禁不设该变量。
ROOT = os.environ.get('YF_EXEC_GUARD_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
YF_INIT = os.path.join(WEB, 'core', 'yf', '__init__.py')
PANEL_TOOLS = os.path.join(ROOT, 'panel_tools.py')
INITD_TPL = os.path.join(ROOT, 'scripts', 'init.d', 'yf.tpl')

#: 死锁场景下允许的最长返回时间。修好之后实测 ~6s（1s 超时 + 5s 回收上限）；
#: 未修时会被孙子进程拖满它的整个睡眠时长（本文件用 30s）。
DEADLOCK_BUDGET = 15.0

sys.path.insert(0, WEB)
import core.yf as yf  # noqa: E402


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _parse(path):
    return ast.parse(_read(path))


def _attr_call_names(node):
    """收集 node 下所有 `<x>.<attr>(...)` 的 attr 名。"""
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            names.append(n.func.attr)
    return names


def _called_names(node):
    """node 下所有被调用函数的名字（Name 与 Attribute 都算）。"""
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                names.append(f.attr)
    return names


def _names(node):
    """node 下所有被引用的变量名（含条件表达式里的）。"""
    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


def _communicate_calls(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == 'communicate':
            yield n


def _timeout_handlers(tree):
    """所有 `except ...TimeoutExpired:` 处理器。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        t = node.type
        name = t.attr if isinstance(t, ast.Attribute) else getattr(t, 'id', None)
        if name == 'TimeoutExpired':
            yield node


#: 「持有管道且不受 killpg 影响」的孙子进程：自己开新会话后长睡。
#: 它继承了父进程的 stdout/stderr —— 父进程退出后管道仍不关闭。
_GRANDCHILD_HOLDING_PIPE = (
    "import os, subprocess, sys\n"
    "kw = {}\n"
    "if hasattr(os, 'setsid'):\n"
    "    kw['start_new_session'] = True\n"
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kw)\n"
)


class ExecTimeoutDeadlockTest(unittest.TestCase):

    # ---------------------------------------------------------------- 行为

    def test_01_normal_path_unchanged(self):
        """常规路径不能被改动影响：stdout / stderr / stdin_data / 退出码。"""
        self.assertEqual(yf.safeExecShell(['echo', 'hello']), ('hello\n', ''))

        out, err = yf.safeExecShell(
            [sys.executable, '-c', 'import sys; sys.stdout.write(sys.stdin.read().upper())'],
            stdin_data='abc')
        self.assertEqual(out, 'ABC')
        self.assertEqual(err, '')

    def test_02_timeout_returns_bounded_when_grandchild_holds_pipe(self):
        """★核心回归：管道被「脱离进程组」的孙子进程持有，也必须**有界**返回。

        未修版本：`sub.kill()` + 无参数 `communicate()` → 一直等到孙子进程自己
        醒来（30s），正是用户看到的那次卡死。
        """
        t0 = time.time()
        out, err = yf.safeExecShell([sys.executable, '-c', _GRANDCHILD_HOLDING_PIPE],
                                    timeout=1)
        elapsed = time.time() - t0
        self.assertLess(elapsed, DEADLOCK_BUDGET,
                        '超时后仍未及时返回（%.1fs）—— communicate() 又被无界调用了' % elapsed)
        self.assertEqual(out, '')
        self.assertIn('Timeout', err)

    def test_03_timeout_kills_whole_process_group(self):
        """超时必须回收整组子进程，不能留下继承管道的孤儿。"""
        if os.name != 'posix':
            self.skipTest('进程组语义仅 POSIX')

        marker = 'yf_exec_guard_sleep_987654'
        code = "import subprocess, sys; subprocess.Popen(['sleep', '600'])"
        # 用 argv[0] 带标记的方式起一个长睡进程，便于事后按标记查存活
        code = ("import subprocess, sys\n"
                "subprocess.Popen(['/bin/sh', '-c', 'exec -a %s sleep 600'])\n" % marker)
        t0 = time.time()
        yf.safeExecShell([sys.executable, '-c', code], timeout=1)
        elapsed = time.time() - t0
        self.assertLess(elapsed, DEADLOCK_BUDGET, '超时未及时返回（%.1fs）' % elapsed)

        # 给 SIGKILL 一点回收时间
        for _ in range(20):
            found = subprocess.run(['pgrep', '-f', marker],
                                   stdout=subprocess.PIPE).stdout.strip()
            if not found:
                break
            time.sleep(0.1)
        self.assertEqual(found, b'',
                         '超时后仍有子进程存活（killpg 未生效）：%r' % found)

    def test_04_execshell_family_timeout_is_bounded(self):
        """execShell / execShellRc 与 safeExecShell 同病，必须一起修。"""
        # 用 shell=False + 正斜杠路径，避免 Windows 上 shlex.split 吃掉反斜杠
        cmd = '"%s" -c "import time; time.sleep(30)"' % sys.executable.replace('\\', '/')

        t0 = time.time()
        with self.assertRaises(Exception) as ctx:
            yf.execShell(cmd, timeout=1, shell=False)
        self.assertLess(time.time() - t0, DEADLOCK_BUDGET, 'execShell 超时后卡住')
        # 既有契约：execShell 超时是**抛异常**（safeExecShell 才是返回空输出）
        self.assertIn('Timeout', str(ctx.exception))

        t0 = time.time()
        rc, out, err = yf.execShellRc(cmd, timeout=1, shell=False)
        self.assertLess(time.time() - t0, DEADLOCK_BUDGET, 'execShellRc 超时后卡住')
        self.assertEqual(rc, -1)
        self.assertEqual(out, '')
        self.assertIn('Timeout', err)

    def test_05_non_list_argument_still_rejected(self):
        """既有契约：safeExecShell 只接受参数列表（防注入的第一道闸）。"""
        out, err = yf.safeExecShell('echo hi')
        self.assertEqual(out, '')
        self.assertIn('list', err)

    # ---------------------------------------------------------------- 结构

    def test_06_no_unbounded_communicate_in_timeout_handler(self):
        """AST：`except TimeoutExpired` 里不允许出现**不带 timeout** 的 communicate()。

        这条是死锁的直接防线 —— 正则会被本文件顶部的故障现场代码蒙混，必须用 ast。
        """
        tree = _parse(YF_INIT)
        offenders = []
        for handler in _timeout_handlers(tree):
            for call in _communicate_calls(handler):
                if not any(kw.arg == 'timeout' for kw in call.keywords):
                    offenders.append(getattr(call, 'lineno', -1))
        self.assertEqual(offenders, [],
                         '超时分支里出现无界 communicate()（死锁根因），行号=%r' % offenders)

    def test_07_exec_primitives_use_own_process_group(self):
        """三个执行原语的 Popen 必须走 `_newProcessGroupKwargs()`（可整组回收 + 免疫 Ctrl+C）。"""
        tree = _parse(YF_INIT)
        helpers = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        self.assertIn('_newProcessGroupKwargs', helpers)
        self.assertIn('_reapTimedOutSub', helpers)

        # 行为侧：POSIX 上必须真的开出新会话（只断言「调用了助手」会被恒等实现蒙混）
        if os.name == 'posix':
            self.assertEqual(yf._newProcessGroupKwargs(), {'start_new_session': True})

        # 源码侧（平台无关）：助手里必须真的出现 start_new_session 这个键，
        # 否则把 `return {}` 写死就能在 Windows 门禁上蒙混过关。
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == '_newProcessGroupKwargs')
        keys = [k.value for d in ast.walk(fn) if isinstance(d, ast.Dict) for k in d.keys
                if isinstance(k, ast.Constant)]
        self.assertIn('start_new_session', keys)

        # 回收时必须真的整组杀（否则持有管道的孙子进程仍会拖住读端）。
        # 用源码断言而非行为断言：POSIX 用例在 Windows 门禁上会被 skip。
        reap = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == '_reapTimedOutSub')
        self.assertIn('killpg', _attr_call_names(reap),
                      '_reapTimedOutSub 未整组 SIGKILL（killpg）')

        popens = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == 'Popen']
        self.assertGreaterEqual(len(popens), 3)
        for call in popens:
            has_kwargs = any(isinstance(kw.value, ast.Call)
                             and getattr(kw.value.func, 'id', None) == '_newProcessGroupKwargs'
                             for kw in call.keywords if kw.arg is None)
            self.assertTrue(has_kwargs,
                            'Popen（行 %d）未启用独立进程组' % getattr(call, 'lineno', -1))

    def test_08_initd_template_does_not_leak_inherited_pipe(self):
        """init.d 模板里的后台任务必须由「子 shell 自身」重定向后再 exec。"""
        text = _read(INITD_TPL)

        # panel_task.py 的后台启动行
        bg = [ln for ln in text.split('\n')
              if 'panel_task.py' in ln and ln.rstrip().endswith('&')]
        self.assertEqual(len(bg), 1, 'panel_task 后台启动行数量变了：%r' % bg)
        line = bg[0].strip()
        self.assertTrue(line.startswith('('),
                        '后台任务没有用子 shell 包住（子 shell 会继承调用方管道）：%s' % line)
        self.assertIn('exec python3 panel_task.py', line,
                      '子 shell 未 exec（会多留一层持有管道的 bash）：%s' % line)
        self.assertIn(') >> ${PANEL_DIR}/logs/panel_task.log 2>&1', line,
                      '重定向没有落在子 shell 上：%s' % line)
        self.assertIn('</dev/null', line, '后台任务未脱离调用方 stdin：%s' % line)

        # gunicorn 前台启动行同理
        self.assertIn('( cd ${PANEL_DIR}/web && exec gunicorn -c setting.py app:app )', text,
                      'gunicorn 启动未用子 shell + exec 隔离调用方管道')

    def test_09_panel_tools_service_commands_use_service_timeout(self):
        """服务类 init.d 命令必须显式传超时（默认 30s 会把慢启动误判成超时）。"""
        tree = _parse(PANEL_TOOLS)
        consts = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        consts[target.id] = node.value.value
        self.assertIn('SERVICE_TIMEOUT', consts)
        self.assertGreaterEqual(consts['SERVICE_TIMEOUT'], 120,
                                'SERVICE_TIMEOUT 太紧（restart 真机本体就要 ~12s）')
        self.assertLessEqual(consts['SERVICE_TIMEOUT'], 180,
                             'SERVICE_TIMEOUT 过宽：管道被外部持有时用户要干等这么久')
        self.assertGreaterEqual(consts.get('UNINSTALL_TIMEOUT', 0), consts['SERVICE_TIMEOUT'],
                                '卸载脚本的余量不能比启停命令还小')

        allowed = {'SERVICE_TIMEOUT', 'UNINSTALL_TIMEOUT'}
        service_cmds = {'restart', 'stop', 'start', 'reload',
                        'restart_panel', 'restart_task', 'uninstall'}
        checked = 0
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'safeExecShell' and call.args):
                continue
            first = call.args[0]
            if not isinstance(first, ast.List) or not first.elts:
                continue
            texts = {e.value for e in first.elts if isinstance(e, ast.Constant)}
            head = first.elts[0]
            is_init_cmd = isinstance(head, ast.Name) and head.id == 'INIT_CMD'
            # ['bash', uninstall_script] 也是服务类命令（卸载脚本可能跑很久）
            is_uninstall = 'bash' in texts
            if not (is_uninstall or (is_init_cmd and (texts & service_cmds))):
                continue
            checked += 1
            names = [kw.value.id for kw in call.keywords
                     if kw.arg == 'timeout' and isinstance(kw.value, ast.Name)]
            self.assertTrue(names and names[0] in allowed,
                            '行 %d 的服务类命令 timeout 不是 %r 之一：%r'
                            % (getattr(call, 'lineno', -1), sorted(allowed), sorted(texts)))
        self.assertGreaterEqual(checked, 8,
                                '识别到的服务类调用只有 %d 处，用例可能失效了' % checked)

    def test_10_service_commands_refresh_init_script_first(self):
        """服务类命令必须先刷新 initd，否则升级后第一次 `yf 1` 仍会「无响应」。

        背景：initd 只在面板**成功启动时**重生成。旧版 initd 的后台任务会泄漏
        调用方管道（见 test_08），因此从旧版升级后的第一次 `yf 1` 跑的还是旧脚本
        → 调用方读不到 EOF。修法 = 执行服务类命令前先 `init_cmd()` 重生成。
        """
        tree = _parse(PANEL_TOOLS)
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn('_refreshInitScript', fns)
        # 刷新必须复用面板启动时的同一段代码，不能另写一份渲染逻辑
        self.assertIn('init_cmd', _called_names(fns['_refreshInitScript']),
                      '_refreshInitScript 没有复用 admin.setup.init_cmd')

        # yfcli 里必须有一处「按 SERVICE_CLI_NUMS 白名单刷新」的分支
        # （只断言「函数被调用过」会被 uninstall 分支里那一处蒙混）
        guarded = [n for n in ast.walk(fns['yfcli']) if isinstance(n, ast.If)
                   and '_refreshInitScript' in _called_names(n)
                   and 'SERVICE_CLI_NUMS' in _names(n.test)]
        self.assertTrue(guarded,
                        '服务类命令前没有「按 SERVICE_CLI_NUMS 白名单刷新 initd」的分支')
        callers = [n for n in ast.walk(fns['yfcli']) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Name) and n.func.id == '_refreshInitScript']
        self.assertGreaterEqual(len(callers), 2, '卸载分支也应先刷新 initd')

        assign = next((n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'SERVICE_CLI_NUMS'
                               for t in n.targets)), None)
        self.assertIsNotNone(assign, '缺少 SERVICE_CLI_NUMS 白名单')
        values = {e.value for e in assign.value.elts if isinstance(e, ast.Constant)}
        self.assertTrue({1, 2, 3, 4, 6, 9}.issubset(values),
                        'SERVICE_CLI_NUMS 未覆盖启停类命令：%r' % sorted(values))


if __name__ == '__main__':
    unittest.main()
