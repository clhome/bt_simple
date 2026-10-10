# coding:utf-8
"""注入面收口回归用例（task.md 第 1 层 A1~A5）。

覆盖：
  A1 插件 zip 安装接口：plugin_name 白名单 + tmp_path 必须位于面板 temp 内
  A2 webssh 插件 CLI：废除 eval，func 白名单
  A3 Docker 插件：废除 eval(ports)，改 ast.literal_eval
  A4 插件 run()：name/script 白名单，堵路径穿越
  A5 site.py：chattr / README 落盘不再拼接未加引号的 shell 字符串

设计约束：既做**行为断言**（恶意输入被拒），也做**源码断言**（危险写法不得复活）。
"""
import os
import sys
import json
import subprocess
import tempfile
import unittest

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(root_dir, 'web')
sys.path.insert(0, web_dir)
sys.path.insert(0, os.path.join(web_dir, 'core'))

import core.yf as yf

# 必须在 import utils.plugin 之前隔离（该模块导入期会打开面板库）
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('p3_injection_hardening')

import utils.plugin as plugin_util  # noqa: E402


def _read(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


class TestInjectionHardening(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_inj_')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- A1 ----------------

    def test_01_plugin_name_validator(self):
        for bad in ['', None, '..', '../x', 'a;b', 'a b', 'a/b', 'a\\b',
                    'a$b', 'a`b', 'a|b', 'a&b', 'a\nb']:
            self.assertFalse(plugin_util._valid_plugin_name(bad), repr(bad))
        for good in ['nginx', 'php-apt', 'a_b', 'A1', 'openresty']:
            self.assertTrue(plugin_util._valid_plugin_name(good), repr(good))

    def test_02_tmp_path_inside_check(self):
        base = os.path.join(self.tmp, 'temp')
        sub = os.path.join(base, 'pkg')
        os.makedirs(sub)
        self.assertTrue(plugin_util._path_inside(base, sub))
        self.assertTrue(plugin_util._path_inside(base, base))
        self.assertFalse(plugin_util._path_inside(base, os.path.join(base, '..', 'etc')))
        self.assertFalse(plugin_util._path_inside(base, os.path.join(base, '..')))
        self.assertFalse(plugin_util._path_inside(base, self.tmp))

    def test_03_input_zip_rejects_command_injection(self):
        pg = plugin_util.plugin.instance()
        # 命令注入型 plugin_name：必须在触碰文件系统前就被拒绝
        r = pg.inputZipApi('x; touch ' + os.path.join(self.tmp, 'pwned') + ' #', self.tmp)
        self.assertFalse(r['status'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'pwned')))

        # tmp_path 注入 + 目录穿越：同样拒绝
        r = pg.inputZipApi('validname', '/etc; rm -rf / #')
        self.assertFalse(r['status'])
        r = pg.inputZipApi('validname', '../../etc')
        self.assertFalse(r['status'])

    def test_04_input_zip_positive_still_works(self):
        panel = tempfile.mkdtemp(prefix='yf_inj_panel_')
        pkg = os.path.join(panel, 'temp', 'mypkg')
        os.makedirs(pkg)
        with open(os.path.join(pkg, 'info.json'), 'w', encoding='utf-8') as fp:
            json.dump({'name': 'mypkg', 'title': 'MyPkg', 'versions': '1.0'}, fp)

        orig = yf.getPanelDir
        yf.getPanelDir = staticmethod(lambda: panel)
        try:
            pg = plugin_util.plugin.instance()
            r = pg.inputZipApi('mypkg', pkg)
            self.assertTrue(r['status'], r)
            self.assertTrue(os.path.exists(
                os.path.join(panel, 'plugins', 'mypkg', 'info.json')))
        finally:
            yf.getPanelDir = orig
            import shutil
            shutil.rmtree(panel, ignore_errors=True)

    # ---------------- A4 ----------------

    def test_05_run_rejects_traversal(self):
        pg = plugin_util.plugin.instance()
        out, err = pg.run('..', 'panel', version='whatever')
        self.assertEqual(out, '')
        self.assertIn('非法', err)

        out, err = pg.run('nginx', 'status', script='../index')
        self.assertEqual(out, '')
        self.assertIn('非法', err)

    # ---------------- A2 ----------------

    def test_06_webssh_cli_whitelist(self):
        script = os.path.join(root_dir, 'plugins', 'webssh', 'index.py')
        payload = ("get_server_list() or __import__('os').system("
                   "'echo YF_PWNED_MARKER') or get_server_list")
        proc = subprocess.run([sys.executable, script, payload],
                              cwd=root_dir, capture_output=True, text=True, timeout=120)
        self.assertNotIn('YF_PWNED_MARKER', proc.stdout)
        self.assertNotEqual(proc.returncode, 0)

    # ---------------- 源码级静态断言 ----------------

    def test_07_no_eval_in_plugin_entrypoints(self):
        docker_src = _read(os.path.join(root_dir, 'plugins', 'docker', 'index.py'))
        self.assertNotIn('ports=eval(', docker_src, 'Docker 插件不得对 ports 使用 eval')
        # E02：ports 的解析已抽到 validatePorts（仍用 ast.literal_eval，只允许字面量容器），
        # 这里同时钉住「助手内部用 literal_eval」与「dockerCreateCon 必须调用它」，
        # 避免绕回 json.loads/裸 eval。
        self.assertIn('ast.literal_eval(text)', docker_src)
        self.assertIn("validatePorts(args['ports'])", docker_src)

        webssh_src = _read(os.path.join(root_dir, 'plugins', 'webssh', 'index.py'))
        self.assertNotIn('eval("classApp."', webssh_src, 'webssh 不得使用 eval 反射')
        self.assertIn('_ALLOWED_FUNCS', webssh_src)

    def test_08_site_chattr_no_shell_concat(self):
        site_src = _read(os.path.join(web_dir, 'utils', 'site.py'))
        self.assertNotIn('which chattr && chattr', site_src,
                         'site.py 的 chattr 必须走 safeExecShell 列表传参')
        self.assertNotIn("echo \"acme\" > ", site_src)
        self.assertNotIn("echo \"lets\" > ", site_src)

    def test_09_plugin_zip_uses_python_file_api(self):
        src = _read(os.path.join(web_dir, 'utils', 'plugin.py'))
        self.assertNotIn('"cp -rf " + tmp_path', src)
        self.assertNotIn("'chmod -R 755 ' + plugin_path", src)
        self.assertIn('shutil.copytree(tmp_path, plugin_path', src)


if __name__ == '__main__':
    unittest.main()
