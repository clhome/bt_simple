# coding: utf-8
"""MySQL「最低从 5.7 开始」的口径守卫（2026-10-27 用户决定下架 5.5/5.6）。

## 为什么下架
* 5.5 / 5.6 上游早已 EOL；
* 它们的 `cmake/ssl.cmake` **只认 OpenSSL 1.0.x**，且 5.6.51 已移除 `extra/yassl`
  —— 在 OpenSSL 3.x 的发行版（Debian 12 / Ubuntu 22.04）上必须**自建一份 OpenSSL 1.0.2**
  才能编译：每次安装多 3~15 分钟，还多一个「openssl release 下载失败」的失败面。
  （同一天 CI 因为这个点了三次红。）

## 口径（与 PHP 的 `PHP_MIN_INSTALL_BRANCH` 一致）
1. **安装入口**：`plugins/mysql/info.json` 的 `versions` / `todo_versions` 不再包含 5.5/5.6；
2. **接口层**：`web/utils/plugin.py::install()` 再拦一道（前端看不到 ≠ 接口调不到），
   返回 `plugin.mysql_eol_branch_install`；
3. **卸载能力必须保留**：`plugins/mysql/versions/{5.5,5.6}/install.sh` 与
   `conf/my5.{5,6}.cnf` **不删** —— 已装用户还要能卸载 / 拿回原配置模板；
4. 读不到 `version.pl` 时的兜底版本从 `5.6` 改成 `5.7`（面板最老的受支持版本）。
"""
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN_PY = os.path.join(ROOT, 'web', 'utils', 'plugin.py')
MYSQL_DIR = os.path.join(ROOT, 'plugins', 'mysql')
MYSQL_INFO = os.path.join(MYSQL_DIR, 'info.json')
MYSQL_INDEX = os.path.join(MYSQL_DIR, 'index.py')
MYSQL_VERSIONS = os.path.join(MYSQL_DIR, 'versions')
MYSQL_CONF = os.path.join(MYSQL_DIR, 'conf')
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')


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


def _mysql_helpers():
    """只取 plugin.py 里 MySQL 那段纯函数（不加载 flask/DB 依赖）。"""
    src = _read(PLUGIN_PY)
    start = src.index('MYSQL_MIN_INSTALL_BRANCH')
    end = src.index('class plugin(object):')
    ns = {'re': re, 'PHP_MIN_INSTALL_BRANCH': '82'}
    exec(src[start:end], ns)
    return ns


class TestInstallList(unittest.TestCase):

    def test_01_info_versions_start_at_5_7(self):
        info = json.loads(_read(MYSQL_INFO))
        versions = info.get('versions') or []
        self.assertNotIn('5.5', versions, 'info.json 仍在提供 5.5 的安装入口')
        self.assertNotIn('5.6', versions, 'info.json 仍在提供 5.6 的安装入口')
        self.assertEqual('5.7', versions[0],
                         '安装列表最低版本应为 5.7，实际首项 %r' % (versions[:1],))
        self.assertEqual(sorted(versions, key=lambda v: [int(x) for x in v.split('.')]),
                         sorted(versions),
                         'versions 应按版本号升序')

    def test_02_info_todo_versions_also_clean(self):
        info = json.loads(_read(MYSQL_INFO))
        todo = info.get('todo_versions') or []
        for bad in ('5.5', '5.6'):
            self.assertNotIn(bad, todo, 'todo_versions 仍列着 %s' % bad)

    def test_03_no_old_workflow_left(self):
        """5.5/5.6 的集成冒烟 workflow 一并删除（留着就是「支持安装」的声明）。"""
        for name in ('python-app-mysql55.yml', 'python-app-mysql56.yml'):
            self.assertFalse(os.path.exists(os.path.join(WORKFLOWS, name)),
                             '%s 仍在，等于声明支持安装已下架版本' % name)
        self.assertTrue(os.path.exists(os.path.join(WORKFLOWS, 'python-app-mysql57.yml')),
                        '5.7 的集成冒烟必须保留')


class TestInstallApiGate(unittest.TestCase):

    def test_01_constant_and_helpers(self):
        ns = _mysql_helpers()
        self.assertEqual('5.7', ns['MYSQL_MIN_INSTALL_BRANCH'])
        fn = ns['_mysql_is_eol_branch']
        for v in ('5.5', '5.6', '5.6.51'):
            self.assertTrue(fn(v), '%r 应被判定为已下架' % v)
        for v in ('5.7', '5.7.44', '8.0', '8.4', '9.7', ''):
            self.assertFalse(fn(v), '%r 不应被拦' % v)

    def test_02_install_returns_i18n_key(self):
        code = _code_only(_read(PLUGIN_PY))
        m = re.search(r'\n    def install\(self.*?(?=\n    def )', code, re.S)
        self.assertTrue(m, '没找到 plugin.install')
        body = m.group(0)
        self.assertIn("'mysql'", body, 'install() 没有单独处理 mysql')
        # 2026-10-27 起改为「按 LTS 允许列表拦截」（mysql 与 mariadb 共用同一段逻辑）
        self.assertIn('db_installable_versions', body,
                      'install() 没有按 LTS 允许列表拦截已下架版本')
        self.assertIn('plugin.mysql_eol_branch_install', body,
                      '拦截必须返回 i18n 键，不能拼中文（外语界面会漏翻）')
        self.assertIn('MYSQL_LTS_VERSIONS', _code_only(_read(PLUGIN_PY)),
                      '缺少 MySQL 的 LTS 允许列表常量')


class TestUninstallStillPossible(unittest.TestCase):

    def test_01_version_scripts_kept(self):
        """已装 5.5/5.6 的用户必须还能卸载 —— 卸载走 version 脚本。"""
        for ver in ('5.5', '5.6'):
            path = os.path.join(MYSQL_VERSIONS, ver, 'install.sh')
            self.assertTrue(os.path.isfile(path),
                            '%s 的卸载脚本被删了，已装用户将无法卸载' % ver)
            code = _code_only(_read(path))
            self.assertIn('Uninstall_mysql()', code)

    def test_02_conf_templates_kept(self):
        """老实例的 my.cnf 模板也要留着（回退/对照用）。"""
        for name in ('my5.5.cnf', 'my5.6.cnf'):
            self.assertTrue(os.path.isfile(os.path.join(MYSQL_CONF, name)),
                            '%s 模板被删了' % name)


class TestFallbackVersion(unittest.TestCase):

    def test_01_fallback_is_5_7(self):
        code = _code_only(_read(MYSQL_INDEX))
        self.assertNotRegex(code, r'version\s*=\s*"5\.6"',
                            '读不到 version.pl 时的兜底仍是 5.6（面板已不支持该版本）')
        self.assertNotRegex(code, r'db_version\s*=\s*"5\.6"')
        self.assertRegex(code, r'version\s*=\s*"5\.7"', '兜底版本应为 5.7')


if __name__ == '__main__':
    unittest.main()
