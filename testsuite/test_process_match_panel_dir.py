# -*- coding: utf-8 -*-
"""进程匹配「面板目录」守卫：写死的 `mdserver-web` 已失效，必须用运行时面板目录。

真机事实（2026-09-29，Debian 12）：
    `/www/server/mdserver-web` 是软链 -> `/www/server/yufeng_panel`，面板实际以
    `/www/server/yufeng_panel/bin/python3 ...` 启动 → **cmdline 里含 `mdserver-web`
    的进程数 = 0**。于是：

    * `plugins/sphinx/index.py::status()` 的 `ps -ef|grep sphinx|...|grep -v mdserver-web`
      过滤不掉插件自己（面板以 `python <面板目录>/plugins/sphinx/index.py status` 调用，
      cmdline 含 "sphinx"）→ **未安装 sphinx 也返回 start**（真机复现）；
      同族的 varnish/postgresql 因为多一个 `grep -v python` 而侥幸正确。
    * `task_manager` 的两处 `cmdline.find('mdserver-web...')` 对面板真实进程恒为 False
      → 面板插件进程与面板本体都被错误分类。

本用例钉住修复：路径判据一律走 `yf.getPanelDir()`，且 `status()` 必须排除面板自身进程。
"""

import ast
import importlib
import logging
import os
import re
import sys
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_DIR = os.path.join(PROJECT_ROOT, 'web')
for _p in (PROJECT_ROOT, _WEB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf   # noqa: E402  （必须在 sys.path 设置之后导入）

SPHINX_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'sphinx', 'index.py')
POSTGRES_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'postgresql', 'index.py')
VARNISH_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'varnish', 'index.py')
TASKMGR_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'task_manager', 'task_manager_index.py')

# 真机取到的真实 cmdline 样本（task-5 取证）
REAL_PANEL_DIR = '/www/server/yufeng_panel'
REAL_PLUGIN_CMDLINE = (REAL_PANEL_DIR + '/bin/python ' + REAL_PANEL_DIR
                       + '/plugins/sphinx/index.py status')
REAL_PANEL_CMDLINE = (REAL_PANEL_DIR + '/bin/python3 ' + REAL_PANEL_DIR
                      + '/bin/gunicorn -c setting.py app:app')
LEGACY_PLUGIN_CMDLINE = ('/www/server/mdserver-web/bin/python3 '
                         '/www/server/mdserver-web/plugins/sphinx/index.py status')
LEGACY_PANEL_CMDLINE = ('/www/server/mdserver-web/bin/python3 '
                        '/www/server/mdserver-web/bin/gunicorn -c setting.py app:app')

# 失效的「路径判据」写法（webssh 的 'mdserver-web' 是加解密盐值，不是路径）
DEAD_GUARD_PATTERNS = [
    re.compile(r'grep\s+-v\s+mdserver-web'),
    re.compile(r"""find\(\s*['"]mdserver-web"""),
]
SALT_HINTS = ('deDoubleCrypt', 'enDoubleCrypt')


def _read_src(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_source(path, name):
    src = _read_src(path)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 中找不到函数 %s' % (path, name))


def _func_code_only(path, name):
    """函数的「去注释」源码。

    不能直接对带注释的源码做 `assertIn('grep -v python')`：注释里解释成因时
    很容易写出同样的字样，于是命令被删掉也能通过（本用例的变异自证就抓到过
    这个假绿）。`ast.unparse` 会丢掉注释，只留下真实代码。
    """
    return ast.unparse(ast.parse(_func_source(path, name)))


def _import_plugin(modname):
    """导入插件模块并把 cwd 还原（插件模块级有 sys.path.append + os.chdir 副作用）。"""
    cwd = os.getcwd()
    try:
        os.chdir(PROJECT_ROOT)
        return importlib.import_module(modname)
    finally:
        os.chdir(cwd)


def _load_taskmgr_helpers(panel_dir):
    """抽取 task_manager 的三个纯字符串助手并在 stub 命名空间里执行。

    该模块 `import psutil`，本地开发机没有 psutil；助手本身只依赖 yf.getPanelDir，
    因此用 AST 切片 + stub 执行，既能验证**真实源码**又不必安装依赖。
    """
    code = '\n'.join(_func_source(TASKMGR_SRC, n)
                     for n in ('_panel_dir_marks', '_is_panel_process', '_is_panel_plugin_process'))
    ns = {
        'yf': types.SimpleNamespace(getPanelDir=lambda: panel_dir),
        '_log': logging.getLogger('test.taskmgr'),
    }
    exec(compile(code, TASKMGR_SRC, 'exec'), ns)
    return ns


class TestNoDeadPanelPathGuard(unittest.TestCase):
    """A. 失效的写死路径判据必须清零"""

    def test_01_no_dead_mdserver_web_path_guard(self):
        bad = []
        roots = [os.path.join(PROJECT_ROOT, 'plugins'), os.path.join(PROJECT_ROOT, 'web')]
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != '__pycache__']
                for fn in filenames:
                    if not fn.endswith('.py'):
                        continue
                    path = os.path.join(dirpath, fn)
                    rel = os.path.relpath(path, PROJECT_ROOT).replace(os.sep, '/')
                    for i, line in enumerate(_read_src(path).splitlines(), 1):
                        if any(h in line for h in SALT_HINTS):
                            continue  # 加解密盐值，不是路径判据
                        if any(p.search(line) for p in DEAD_GUARD_PATTERNS):
                            bad.append('%s:%d  %s' % (rel, i, line.strip()))
        self.assertEqual(bad, [], '这些地方仍在用失效的写死路径判据（cmdline 里已无 mdserver-web）：\n  '
                                  + '\n  '.join(bad))

    def test_02_status_commands_filter_panel_process(self):
        """sphinx/postgresql/varnish 的 status 必须排除面板自身进程（两种合格形态之一）"""
        for path in (SPHINX_SRC, POSTGRES_SRC, VARNISH_SRC):
            code = _func_code_only(path, 'status')   # 去注释，避免注释里的字样造成假绿
            rel = os.path.relpath(path, PROJECT_ROOT).replace(os.sep, '/')
            if "'pgrep', '-x'" in code:
                # 更强形态：按**精确进程名**判定（`pgrep -x <进程名>`）。既不匹配面板
                # 自己的 python 子进程，也不匹配 cmdline 里提到服务名的无关进程
                # （真机实测：varnish 旧写法对 `tail -f /var/log/varnish/varnish.log`
                # 误报 start）。此形态下不再需要 grep 过滤链。
                self.assertNotIn('ps -ef', code, '%s::status 不得再用 ps|grep 判据' % rel)
                self.assertNotIn('mdserver-web', code, '%s::status 仍在用过期的 mdserver-web 判据' % rel)
                self.assertNotIn("grep -v", code, '%s::status 不得混用 grep 过滤链' % rel)
                continue
            self.assertIn('grep -v python', code,
                          '%s::status 少了 `grep -v python`（面板以 python 调用插件，'
                          '不排除会把插件自己当成服务在跑 → 未安装也报 start）' % rel)
            self.assertIn('yf.getPanelDir()', code,
                          '%s::status 未使用运行时面板目录' % rel)
            self.assertNotIn('mdserver-web', code,
                             '%s::status 仍在用过期的 mdserver-web 判据' % rel)
            self.assertNotIn("'/www/server/", code,
                             '%s::status 里出现了硬编码的 /www/server/ 路径' % rel)


class TestStatusCommandBehaviour(unittest.TestCase):
    """B. 行为验证：真正传给 execShell 的命令串"""

    def test_03_command_excludes_panel_and_uses_runtime_dir(self):
        """sphinx 已收窄到「精确进程名」形态：`execShellRc(['pgrep','-x','searchd'])`。

        旧写法 `ps -ef|grep sphinx|…|grep -v python|grep -v <面板目录>` 只是滤掉了面板
        自己，仍会误报 cmdline 里提到 sphinx 的无关进程（真机：`tail -f …/searchd.log`）。
        精确进程名形态下无需任何 grep 过滤链，也不可能再命中面板 python 子进程。
        """
        mod = _import_plugin('plugins.sphinx.index')
        self.assertEqual('searchd', mod.SEARCHD_PROCESS,
                         'sphinx 守护进程名必须是 searchd（不是插件名 sphinx）')
        with patch.object(yf, 'execShellRc', return_value=(1, '', '')) as mock_rc:
            self.assertEqual('stop', mod.status())
        self.assertEqual(['pgrep', '-x', 'searchd'], list(mock_rc.call_args[0][0]),
                         'plugins.sphinx.index 必须按精确进程名探活')
        self.assertFalse(mock_rc.call_args[1].get('shell', False),
                         'plugins.sphinx.index 不得经 shell（否则 grep 链会回来）')

    def test_03b_varnish_uses_exact_process_name(self):
        """varnish 走精确进程名形态：面板 python 自身与「cmdline 提到 varnish」的无关
        进程都不得被当成服务在运行（真机实测 HEAD 版对 decoy 进程误报 start）。"""
        mod = _import_plugin('plugins.varnish.index')
        self.assertEqual('varnishd', mod.VARNISH_PROCESS,
                         'varnish 守护进程名必须是 varnishd（不是插件名 varnish）')
        with patch.object(yf, 'execShellRc', return_value=(1, '', '')) as mock_rc:
            self.assertEqual('stop', mod.status())
        self.assertEqual(['pgrep', '-x', mod.VARNISH_PROCESS], list(mock_rc.call_args[0][0]))
        with patch.object(yf, 'execShellRc', return_value=(0, '4245\n', '')):
            self.assertEqual('start', mod.status())

    def test_04_sphinx_status_returns_stop_when_no_process(self):
        """无 searchd 进程（pgrep rc=1）-> 必须返回 stop（真机 P0 形态）"""
        mod = _import_plugin('plugins.sphinx.index')
        with patch.object(yf, 'execShellRc', return_value=(1, '', '')):
            self.assertEqual('stop', mod.status())

    def test_05_sphinx_status_returns_start_when_process_exists(self):
        mod = _import_plugin('plugins.sphinx.index')
        with patch.object(yf, 'execShellRc', return_value=(0, '1234\n', '')):
            self.assertEqual('start', mod.status())

    def test_05b_sphinx_status_does_not_touch_cmdline_grep(self):
        """真机误报形态：无关进程 cmdline 里提到 sphinx 时不得报 start。
        等价断言 = 探活命令只能是 argv 形式的 pgrep -x（无从做 cmdline 子串匹配）。"""
        mod = _import_plugin('plugins.sphinx.index')
        with patch.object(yf, 'execShellRc', return_value=(0, '1234\n', '')) as mock_rc:
            mod.status()
        argv = list(mock_rc.call_args[0][0])
        self.assertEqual('pgrep', argv[0])
        self.assertNotIn('-f', argv, "pgrep -f 是 cmdline 子串匹配（真机误报根因）")
        self.assertNotIn('grep', argv)


class TestPanelProcessClassification(unittest.TestCase):
    """C. task_manager 分类助手对真机真实 cmdline 的判定"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_taskmgr_helpers(REAL_PANEL_DIR)
        cls.marks = cls.ns['_panel_dir_marks']()

    def test_06_marks_contain_runtime_dir_and_legacy_name(self):
        self.assertIn(REAL_PANEL_DIR, self.marks, '标记里没有运行时面板目录')
        self.assertIn('mdserver-web', self.marks, '缺少旧软链名兼容')

    def test_07_panel_plugin_process_is_recognised(self):
        self.assertTrue(self.ns['_is_panel_plugin_process'](REAL_PLUGIN_CMDLINE, self.marks),
                        '面板真实调用形式的插件进程必须被识别为「面板插件进程」')
        self.assertFalse(self.ns['_is_panel_process'](REAL_PLUGIN_CMDLINE, self.marks),
                         '插件进程不该被识别为面板本体')

    def test_08_panel_gunicorn_is_recognised(self):
        self.assertTrue(self.ns['_is_panel_process'](REAL_PANEL_CMDLINE, self.marks),
                        '面板本体 gunicorn 必须被识别为「御风面板」')
        self.assertFalse(self.ns['_is_panel_plugin_process'](REAL_PANEL_CMDLINE, self.marks),
                         '面板本体不该被识别为插件进程')

    def test_09_legacy_symlink_path_still_recognised(self):
        """仍以软链路径启动的旧部署不能退化"""
        self.assertTrue(self.ns['_is_panel_plugin_process'](LEGACY_PLUGIN_CMDLINE, self.marks))
        self.assertTrue(self.ns['_is_panel_process'](LEGACY_PANEL_CMDLINE, self.marks))

    def test_10_unrelated_processes_are_not_panel(self):
        # 注：判据是「cmdline 里出现 <面板目录>/plugins/」，不做路径规范化。
        # 因此 `…/yufeng_panel/plugins/../other/index.py` 会被判为插件进程 —— 这是可辩护的
        # （确实是从面板 plugins 路径下起来的 python），且面板 `plugin.run()` 会对插件名做
        # 白名单校验、不可能产生这种 cmdline，所以不作为缺陷。
        for cmdline in (
            '/usr/sbin/varnishd -a :6081 -f /etc/varnish/default.vcl',
            '/www/server/sphinx/bin/searchd --config /www/server/sphinx/etc/sphinx.conf',
            '/usr/bin/python3 /opt/other/app.py',
            '/usr/bin/python3 /opt/panel_copy/plugins/other/index.py',
        ):
            self.assertFalse(self.ns['_is_panel_plugin_process'](cmdline, self.marks),
                             '误判为插件进程: %s' % cmdline)
            self.assertFalse(self.ns['_is_panel_process'](cmdline, self.marks),
                             '误判为面板本体: %s' % cmdline)


if __name__ == '__main__':
    unittest.main(verbosity=2)
