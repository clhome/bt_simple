# coding: utf-8
"""守卫：自愈类用例不得改写仓库内的 plugins/*/plugin_version.pl。

背景（2026-10-12 修复）：`testsuite/test_php_plugins_self_healing.py` 的
test_03/04/05 会跑 php / php-apt / php-yum 的 checkPluginUpgrade()，把版本文件
从 1.0 自愈写成 2.0。旧写法直接落在仓库 `plugins/<name>/plugin_version.pl` 上：
php-apt 的仓库版本是 1.0，每跑一次门禁就被改写成 2.0，工作区变脏，污染 git status
与提交核对。修复方式是把被测插件的 `getPluginDir()` / `getServerDir()` 指向
tempfile 副本（见被测用例的 `run_version_self_healing`），写操作只落副本。

本守卫把三件事钉死（每条都能真的失败）：
  1. 跑完隔离的自愈流程后，仓库内三个 plugin_version.pl 与运行前**逐字节一致**；
  2. 隔离副本里**确实出现**了新的版本标记 2.0（证明流程真的跑了，不是被跳过）；
  3. 静态断言被测用例没有构造「仓库内 plugin_version.pl」路径（防回退成直写真实路径）。

探针 `test/p1_testhygiene_mutation_probe.py` 通过环境变量 `YF_ISOLATION_TEST`
把被测用例换成「回退版」副本，验证本守卫会随之变红。
"""
import ast
import importlib.util
import io
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 被测用例；探针用它注入「回退版」副本。
ISOLATION_TEST = os.environ.get(
    'YF_ISOLATION_TEST',
    os.path.join(PROJECT_ROOT, 'testsuite', 'test_php_plugins_self_healing.py'))


def _read_bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _load_isolation_module():
    """从 ISOLATION_TEST 路径加载被测用例模块（探针可换成副本）。"""
    spec = importlib.util.spec_from_file_location('p1_isolation_under_test', ISOLATION_TEST)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPluginVersionFileIsolation(unittest.TestCase):

    def test_01_self_healing_keeps_repo_version_files_untouched(self):
        """跑完隔离自愈后：仓库版本文件逐字节不变，且副本拿到 2.0。"""
        iso = _load_isolation_module()
        repo_files = {name: os.path.join(PROJECT_ROOT, 'plugins', name, 'plugin_version.pl')
                      for name in iso.SELF_HEALING_PLUGINS}
        before = {name: _read_bytes(p) for name, p in repo_files.items()}

        for name in iso.SELF_HEALING_PLUGINS:
            module = iso.load_plugin_module(name)
            result = iso.run_version_self_healing(module, name)
            # 副本里确实出现了新版本标记（证明流程真的跑了，不是被跳过）
            self.assertEqual(result['observed'], '2.0',
                             '%s 的隔离副本未拿到新版本标记，自愈流程可能被跳过' % name)

        # 仓库内文件逐字节不变
        after = {name: _read_bytes(p) for name, p in repo_files.items()}
        changed = [n for n in iso.SELF_HEALING_PLUGINS if after[n] != before[n]]
        self.assertEqual(changed, [],
                         '自愈流程改写了仓库内 plugin_version.pl：' + ', '.join(changed))

    def test_02_isolation_test_source_never_builds_repo_version_path(self):
        """静态断言：被测用例源码里不得构造仓库内的 plugin_version.pl 路径。"""
        with io.open(ISOLATION_TEST, encoding='utf-8') as fh:
            src = fh.read()

        # 隔离机制必须在位：临时目录 + 重定向插件目录
        self.assertIn('tempfile.mkdtemp(', src, '被测用例没有用临时目录做隔离')
        self.assertRegex(src, r'\.getPluginDir\s*=', '被测用例没有重定向插件目录 getPluginDir')

        # 任何一行都不得同时出现 PROJECT_ROOT 与 plugin_version —— 那正是「真实路径」
        offenders = [i + 1 for i, line in enumerate(src.splitlines())
                     if 'PROJECT_ROOT' in line and 'plugin_version' in line]
        self.assertEqual(offenders, [],
                         '被测用例把真实插件路径（PROJECT_ROOT + plugin_version.pl）传给了写操作，'
                         '行号 %s' % offenders)

        # AST 复核：源码里不得出现 plugin_version.pl 字面量（唯一合法入口是 getPluginVersionFile）
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Constant) and node.value == 'plugin_version.pl':
                self.fail('被测用例源码出现字面量 plugin_version.pl（行 %d），疑似直写真实路径'
                          % node.lineno)


if __name__ == '__main__':
    unittest.main()
