# -*- coding: utf-8 -*-
"""ORM 查询结果参与字符串拼接时必须先有「真值守卫」——全仓棘轮（基线 0）。

## 为什么要有这条守卫

`web/core/db.py` 的 `getField()` / `find()` 在**查不到行**时返回 `None`（不是空串）：

    def getField(self, keyName):
        result = self.field(keyName).select()
        if len(result) == 1:
            return result[0][keyName]
        return None

于是「先查库、再拼日志/命令」这种写法在查不到时会炸：

    name = yf.M('databases').where('name=?', (name,)).getField('name')   # 查不到 -> None
    if not name:
        log = "数据库[" + name + "]不存在!"        # TypeError: can only concatenate str
        print(log)

2026-10-09 实测确认这是**成片的单侧漂移**（不是孤例）：

* `plugins/mongodb/scripts/backup.py::backupDatabase` 已用 `req_name = str(name)`
  保留调用方入参的写法修过；
* 但 `scripts/backup.py::backupDatabase`（面板级，mysql 用）与
  `plugins/mariadb/scripts/backup.py::backupDatabase` **逐字节同源、都没修**；
* `plugins/mysql/scripts/tools.py::set_panel_username` 的
  `print('username: ' + username)`、`plugins/{mysql,mariadb}/index.py` 主从同步链路里
  `'-p' + pwd`（`pwd = ...getField('mysql_root')`）同族。

所以守卫按**机制**扫全仓，而不是钉某几个函数 —— 避免「点名 bug 只改点名处」。

## 判定规则（两条，都很窄，避免误报）

设 `X` 是某函数内「由 ORM `.getField(`/`.find(` 赋值、且调用链含
`where(`/`M(`/`Sql(`/`dbPos(`/`pSqliteDb(`/`table(`」的局部变量：

1. **在 `if not X:` 的体内**把 `X` 拿去 `+` 拼接 → 违规（这正是上面那个 TypeError）。
2. 在别处把 `X` 拿去 `+` 拼接，但**前面没有**「会提前退出（return/raise/continue/break）
   的 `not X` 守卫」→ 违规。

已覆盖的合法写法（`test_02`/`test_03` 用内嵌夹具钉住，防止守卫被「顺手放宽」）：

* `if not X or not checkSafeName(X): return` —— `or` 复合条件也算守卫；
* `if not X: return` 之后再 `"..." + X` —— 已提前退出，安全；
* `req_name = str(X)` 先留一份入参，再让 `X` 被查询结果覆盖。
"""

import ast
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_ROOTS = ('scripts', 'web', 'plugins')
SKIP_DIRS = ('__pycache__', 'node_modules', '.git')

# 只有「ORM 链」才算：`str.find()` 之类的同名方法必须排除（首版扫描就误报过
# php-apt/php/php-yum 的 `eq_idx = line.find('=')`、redis 的 `first_n = s.find(...)`）。
ORM_CHAIN_MARKERS = ('where(', 'M(', 'Sql(', 'dbPos(', 'pSqliteDb(', 'table(')


def _orm_assigned_names(func, src):
    """函数内「由 ORM getField/find 赋值」的局部变量 -> 首次赋值行号。"""
    out = {}
    for sub in ast.walk(func):
        if not (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call)):
            continue
        fn = sub.value.func
        name = fn.attr if isinstance(fn, ast.Attribute) else ''
        if name not in ('getField', 'find'):
            continue
        seg = ast.get_source_segment(src, sub.value) or ''
        if not any(m in seg for m in ORM_CHAIN_MARKERS):
            continue
        for target in sub.targets:
            if isinstance(target, ast.Name):
                out[target.id] = sub.lineno
    return out


def _mentions_falsy(test, name):
    """`not X` / `not X or ...` / `X is None` / `X == None` 都算真值守卫。"""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return isinstance(test.operand, ast.Name) and test.operand.id == name
    if isinstance(test, ast.BoolOp):
        return any(_mentions_falsy(v, name) for v in test.values)
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, op, right = test.left, test.ops[0], test.comparators[0]
        if isinstance(op, (ast.Is, ast.Eq)) and isinstance(left, ast.Name) and left.id == name:
            return isinstance(right, ast.Constant) and right.value is None
    return False


def _exits(body):
    """if 体里是否含提前退出语句。"""
    for node in body:
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                return True
    return False


def scan_source(path, src):
    """返回该源码里所有违规的 (行号, 函数名, 说明)。"""
    violations = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return violations
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        names = _orm_assigned_names(func, src)
        if not names:
            continue
        guard_lines = {}      # name -> 最早的「提前退出型 not 守卫」行号
        guard_bodies = []     # (name, lo, hi) 该守卫体的行号范围
        for sub in ast.walk(func):
            if isinstance(sub, ast.If) and _exits(sub.body):
                for name in names:
                    if _mentions_falsy(sub.test, name):
                        guard_lines[name] = min(guard_lines.get(name, 10 ** 9), sub.lineno)
                        lines = [getattr(n, 'lineno', sub.lineno) for n in sub.body]
                        ends = [getattr(n, 'end_lineno', getattr(n, 'lineno', sub.lineno))
                                for n in sub.body]
                        guard_bodies.append((name, min(lines), max(ends)))
        for sub in ast.walk(func):
            if not (isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Add)):
                continue
            for side in (sub.left, sub.right):
                if not (isinstance(side, ast.Name) and side.id in names):
                    continue
                name = side.id
                in_body = any(name == g and lo <= sub.lineno <= hi
                              for g, lo, hi in guard_bodies)
                guarded = guard_lines.get(name, 10 ** 9) < sub.lineno
                if in_body:
                    violations.append((sub.lineno, func.name,
                                       '在 `if not %s:` 体内把 %s 拿去拼接' % (name, name)))
                elif not guarded:
                    violations.append((sub.lineno, func.name,
                                       '%s 来自 ORM 查询却无前置真值守卫就拼接' % name))
    return sorted(set(violations))


def scan_workspace():
    """扫描全仓，返回 ['相对路径:行号 函数名 说明', ...]。"""
    out = []
    for root in SCAN_ROOTS:
        base = os.path.join(PROJECT_ROOT, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                full = os.path.join(dirpath, filename)
                try:
                    with open(full, encoding='utf-8') as fh:
                        src = fh.read()
                except (OSError, UnicodeDecodeError):
                    continue
                rel = os.path.relpath(full, PROJECT_ROOT).replace(os.sep, '/')
                for lineno, func, why in scan_source(full, src):
                    out.append('%s:%d  %s()  %s' % (rel, lineno, func, why))
    return sorted(out)


class OrmFieldConcatGuardTest(unittest.TestCase):

    def test_01_workspace_has_no_unguarded_concat(self):
        """棘轮：全仓基线 0，任何新增的「查库结果直接拼接」都会红。"""
        problems = scan_workspace()
        self.assertEqual([], problems,
                         'ORM 查询结果参与拼接前必须做真值守卫：\n  ' + '\n  '.join(problems))

    # ---- 检测器自证：内嵌夹具（已知答案），防止守卫被「顺手放宽」 ----

    def test_02_detector_catches_known_bad_fixture(self):
        bad = (
            'def backupDatabase(name):\n'
            '    name = yf.M("databases").where("name=?", (name,)).getField("name")\n'
            '    if not name:\n'
            '        log = "数据库[" + name + "]不存在!"\n'
            '        print(log)\n'
            '        return\n'
        )
        hits = scan_source('fixture_bad.py', bad)
        self.assertEqual(1, len(hits), '必须命中「if not X 体内拼接」，实际: %r' % (hits,))
        self.assertIn('体内', hits[0][2])

    def test_03_detector_accepts_guarded_fixtures(self):
        cases = {
            'or 复合守卫': (
                'def setDbRw(uid):\n'
                '    dbname = psdb.where("id=?", (uid,)).getField("name")\n'
                '    if not dbname or not checkSafeName(dbname):\n'
                '        return "err"\n'
                '    sql = "REVOKE ALL ON database " + dbname + " FROM u"\n'
                '    return sql\n'
            ),
            '提前退出后使用': (
                'def f(name):\n'
                '    name = yf.M("databases").where("name=?", (name,)).getField("name")\n'
                '    if not name:\n'
                '        return\n'
                '    log = "数据库[" + name + "]备份成功"\n'
                '    return log\n'
            ),
            'req_name 保留入参': (
                'def backupDatabase(name):\n'
                '    req_name = str(name)\n'
                '    name = yf.M("databases").where("name=?", (name,)).getField("name")\n'
                '    if not name:\n'
                '        log = "数据库[" + req_name + "]不存在!"\n'
                '        return log\n'
            ),
            'X is None 守卫': (
                'def f(pwd):\n'
                '    pwd = pSqliteDb("config").where("id=?", (1,)).getField("mysql_root")\n'
                '    if pwd is None:\n'
                '        return ""\n'
                '    return "-p" + pwd\n'
            ),
        }
        for label, src in cases.items():
            self.assertEqual([], scan_source('fixture_ok.py', src),
                             '合法写法被误报（%s）: %r' % (label, src))

    def test_04_detector_ignores_str_find_and_non_orm(self):
        """`str.find()` 与普通变量不得被当成 ORM 结果（首版误报过 eq_idx/first_n）。"""
        src = (
            'def remove_putenv(line):\n'
            '    eq_idx = line.find("=")\n'
            '    if eq_idx > 0:\n'
            '        out = "prefix" + str(eq_idx) + line\n'
            '        return out\n'
            '    plain = "x"\n'
            '    return "y" + plain\n'
        )
        self.assertEqual([], scan_source('fixture_str.py', src))


if __name__ == '__main__':
    unittest.main(verbosity=2)
