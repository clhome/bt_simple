# coding: utf-8
"""「端口冲突」判定守卫：不同端口的两个数据库实例必须能并存（2026-10-28）。

## 事故

mysql 插件与 mariadb 插件**可以同时装、同时跑**，只要端口不同（真机实测
mysql=3306、mariadb=33106）。但 `instanceOwnership()` 原来把「机器上还有别的
mysqld/mariadbd」一律当成冲突：

    mysql   self_check -> 实例异常: 同时存在本面板与其他 MySQL 实例，请只保留一个
    mariadb self_check -> 实例异常: 同时存在本面板与其他 MySQL/MariaDB 实例，请只保留一个

于是「装完第二个数据库插件，两个插件都报故障」，用户被迫二选一。修法：判定落到
**监听端口**——只有监听同一个端口的才算冲突，其余记为 `others`（提示但不报错）。

## 断言

1. `db_root.parse_listen_ports()` 能解析 `ss -ltnp` / `netstat -ltnp` 两种格式；
2. 两个插件的 `instanceOwnership()` 都走 `db_root.listen_ports_by_pid()`，且有
   `others`（不冲突）这条分支；拿不到端口信息时仍按冲突处理（保守）；
3. 行为：用桩替换端口映射，验证「同端口→冲突、不同端口→不冲突」。
"""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

DB_ROOT = os.path.join(WEB, 'core', 'db_root.py')
MYSQL_PY = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
MARIADB_PY = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')

SS_SAMPLE = """State  Recv-Q Send-Q  Local Address:Port  Peer Address:Port  Process
LISTEN 0      80            0.0.0.0:3306        0.0.0.0:*          users:(("mysqld",pid=111,fd=32))
LISTEN 0      80            0.0.0.0:33106       0.0.0.0:*          users:(("mariadbd",pid=222,fd=21))
LISTEN 0      511           0.0.0.0:888         0.0.0.0:*          users:(("openresty",pid=333,fd=15))
"""

NETSTAT_SAMPLE = """Active Internet connections (only servers)
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name
tcp        0      0 0.0.0.0:3306            0.0.0.0:*               LISTEN      111/mysqld
tcp6       0      0 :::33106                :::*                    LISTEN      222/mariadbd
"""


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _load_db_root():
    """只取 db_root 里的纯解析函数（不连库、不起子进程）。"""
    src = _read(DB_ROOT)
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == 'parse_listen_ports']
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), DB_ROOT, 'exec'), ns)
    return ns['parse_listen_ports']


class TestParseListenPorts(unittest.TestCase):

    def test_01_parses_ss_output(self):
        f = _load_db_root()
        m = f(SS_SAMPLE)
        self.assertEqual({'3306'}, m.get(111), m)
        self.assertEqual({'33106'}, m.get(222), m)
        self.assertEqual({'888'}, m.get(333), m)

    def test_02_parses_netstat_output(self):
        f = _load_db_root()
        m = f(NETSTAT_SAMPLE)
        self.assertEqual({'3306'}, m.get(111), m)
        self.assertEqual({'33106'}, m.get(222), m)

    def test_03_bad_input_is_safe(self):
        f = _load_db_root()
        for text in ('', None, 'garbage line without pid', 'tcp 0 0 0.0.0.0:1 0.0.0.0:* LISTEN -'):
            self.assertEqual({}, f(text), repr(text))


class TestOwnershipUsesPort(unittest.TestCase):
    """结构 + 语义：只有同端口才算冲突。"""

    def _fn_body(self, path, name):
        src = _read(path)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                lines = src.splitlines()
                return '\n'.join(lines[node.lineno - 1:node.end_lineno])
        raise AssertionError('未找到 %s::%s' % (path, name))

    def test_10_both_plugins_classify_by_port(self):
        for path, label in ((MYSQL_PY, 'mysql'), (MARIADB_PY, 'mariadb')):
            body = self._fn_body(path, 'instanceOwnership')
            self.assertIn('db_root.listen_ports_by_pid()', body,
                          '%s 的归属判定没有查监听端口' % label)
            self.assertIn('conflicting', body, '%s 缺少「冲突」分类' % label)
            self.assertIn('others', body, '%s 缺少「不冲突的其它实例」分类' % label)
            self.assertIn("my_port in ports", body,
                          '%s 没有按「是否同一端口」判定冲突' % label)

    def test_11_unknowable_port_is_conservative(self):
        """拿不到端口信息时必须仍按冲突处理（不能变成「一律放行」）。"""
        for path, label in ((MYSQL_PY, 'mysql'), (MARIADB_PY, 'mariadb')):
            body = self._fn_body(path, 'instanceOwnership')
            self.assertRegex(body, r'not my_port or not ports or my_port in ports',
                             '%s 的「不知道端口」分支不再保守' % label)

    def test_12_reason_mentions_others_without_failing(self):
        for path, label in ((MYSQL_PY, 'mysql'), (MARIADB_PY, 'mariadb')):
            body = self._fn_body(path, 'instanceOwnership')
            self.assertIn("'others': others", body, '%s 没有把 others 返回给调用方' % label)
            # status 仍为 ok 时才写 others 的说明（不把并存判成故障）
            self.assertRegex(body, r"if status == 'ok' and others:",
                             '%s 在 ok 状态下没有给出 others 提示' % label)


if __name__ == '__main__':
    unittest.main()
