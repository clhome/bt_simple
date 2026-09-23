# coding: utf-8
"""回归护栏：`yf.returnJson(...)` 的实参不得引用「未定义名」。

## 为什么只盯 returnJson 的实参

`returnJson` 是插件对前端的**输出契约**：它的实参一旦引用未定义名，
运行时必然抛 `NameError`，整个动作 100% 失败，用户看到的是整段堆栈 ——
这正是 2026-09 那次「多语言适配」回归的线上现象：

    File ".../plugins/yufeng_systemd/index.py", line 80, in get_services
        return yf.returnJson(True, "获取成功", res["data"])
    NameError: name 'res' is not defined

那批改写的模式是「按占位键整行替换成模板」，于是把 `services` / `content` /
`[args, dodb]` / `master_status, data` 等**数据实参**换成了模板里的
`res["data"]` / `mode`，并把 `except ... as ex` 分支才存在的 `ex` / `e`
写进了 try 体。护栏就钉在这一层：**窄、零基线、直接对应缺陷成因**。

（仓库里另有若干「非 returnJson 位置」的历史遗留未定义名，属另一类问题，
不在本护栏范围内 —— 见本次交付报告。）

## 判定规则

对每个 `*.returnJson(...)` 调用，取其所有实参里的 `ast.Name`（Load 上下文），
按下面的作用域链判定「是否可解析」：

    内建名 ∪ 模块级绑定 ∪ 各层外层函数绑定 ∪ 当前函数绑定

当前函数的绑定带**行号**：名字必须在该行**之前**已绑定，否则判失败。
这一条是必需的 —— 否则

    return yf.returnJson(False, '创建失败!' + str(ex))   # try 体里
except docker.errors.APIError as ex:                     # ex 在下一行才绑定
    ...

这种「作用域内确实绑定了、但用得太早」的写法会被漏掉（纯作用域判定看不见）。

## 自证

内嵌夹具（`FIXTURE_BAD` / `FIXTURE_GOOD`）用「已知答案」钉住检测器：
既证明它会响（3 处必须报），也证明它不乱响（6 处合法写法不得报）。
只用标准库；不依赖 `test/`（那目录被 .gitignore 忽略，CI 里不存在）。
"""
import ast
import builtins
import io
import os
import sys
import unittest

try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ROOT = os.path.join(BASE_DIR, 'plugins')

EXTRA_GLOBALS = set(dir(builtins)) | {
    '__file__', '__name__', '__doc__', '__package__', '__builtins__',
    '__loader__', '__spec__', '__debug__',
}


# ---------------------------------------------------------------------------
# 作用域绑定收集
# ---------------------------------------------------------------------------

class _Binder(ast.NodeVisitor):
    """收集「一个作用域内绑定的名字 → 首次绑定行号」。

    刻意**不下钻**嵌套 FunctionDef / ClassDef：它们的绑定属于它们自己的作用域。
    这样才能抓住「名字只在兄弟函数里绑定」这类缺陷（`res` 之于 `_run_cmd`）。
    """

    def __init__(self):
        self.first = {}
        self.globals = set()
        self.nonlocals = set()
        self.star_import = False

    def _bind(self, name, lineno):
        if name and name not in self.first:
            self.first[name] = lineno

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._bind(node.id, node.lineno)

    def visit_arg(self, node):
        self._bind(node.arg, node.lineno)

    def visit_FunctionDef(self, node):
        self._bind(node.name, node.lineno)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._bind(node.name, node.lineno)

    def visit_Lambda(self, node):
        # lambda 是独立作用域，但为了不产生假阳性，把它的形参算进当前作用域
        for a in list(node.args.args) + list(node.args.posonlyargs) + \
                list(node.args.kwonlyargs):
            self._bind(a.arg, node.lineno)
        if node.args.vararg:
            self._bind(node.args.vararg.arg, node.lineno)
        if node.args.kwarg:
            self._bind(node.args.kwarg.arg, node.lineno)
        self.generic_visit(node)

    def visit_Import(self, node):
        for a in node.names:
            self._bind((a.asname or a.name).split('.')[0], node.lineno)

    def visit_ImportFrom(self, node):
        for a in node.names:
            if a.name == '*':
                self.star_import = True
            else:
                self._bind(a.asname or a.name, node.lineno)

    def visit_ExceptHandler(self, node):
        if node.name:
            self._bind(node.name, node.lineno)
        self.generic_visit(node)

    def visit_Global(self, node):
        self.globals.update(node.names)

    def visit_Nonlocal(self, node):
        self.nonlocals.update(node.names)


def _collect(body):
    b = _Binder()
    for stmt in body:
        b.visit(stmt)
    return b


# ---------------------------------------------------------------------------
# 主检测器
# ---------------------------------------------------------------------------

def _is_returnjson_call(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'returnJson')


def _load_names(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            yield sub


def scan_source(src, filename='<fixture>'):
    """返回 [(行号, 名字, 调用所在行)] 形式的违规列表。"""
    tree = ast.parse(src, filename)

    module_binder = _collect(tree.body)
    module_names = dict(module_binder.first)
    # `global x` 声明会把 x 提升到模块作用域（可能在别处赋值）
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            for n in node.names:
                module_names.setdefault(n, 0)
    # 星号导入 => 模块级名字集合不可判定，直接放弃扫描（宁可漏报，不可乱报）
    if module_binder.star_import:
        return []

    findings = []

    def walk(node, scopes):
        """scopes: 外层作用域的「名字 -> 首次绑定行」列表（由外到内）。"""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local = _collect(node.body)
            for a in list(node.args.args) + list(node.args.posonlyargs) + \
                    list(node.args.kwonlyargs):
                local.first.setdefault(a.arg, node.lineno)
            if node.args.vararg:
                local.first.setdefault(node.args.vararg.arg, node.lineno)
            if node.args.kwarg:
                local.first.setdefault(node.args.kwarg.arg, node.lineno)
            for name in local.globals:
                module_names.setdefault(name, 0)
            for name in local.nonlocals:
                local.first.setdefault(name, 0)
            inner = scopes + [local.first]
            for stmt in node.body:
                walk(stmt, inner)
            # 装饰器 / 默认值在**外层**作用域求值
            for dec in node.decorator_list:
                walk(dec, scopes)
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                walk(d, scopes)
            return

        if _is_returnjson_call(node):
            args = list(node.args) + [k.value for k in node.keywords]
            for arg in args:
                for name_node in _load_names(arg):
                    name = name_node.id
                    if name in EXTRA_GLOBALS:
                        continue
                    if name in module_names:
                        continue
                    resolved = False
                    for scope in scopes:
                        if name in scope and scope[name] <= name_node.lineno:
                            resolved = True
                            break
                    if not resolved:
                        findings.append((name_node.lineno, name, node.lineno))
            # 实参里也可能嵌着 returnJson（少见），继续下钻
            for arg in args:
                walk(arg, scopes)
            return

        for child in ast.iter_child_nodes(node):
            walk(child, scopes)

    for stmt in tree.body:
        walk(stmt, [])
    return findings


# ---------------------------------------------------------------------------
# 自证夹具
# ---------------------------------------------------------------------------

FIXTURE_BAD = '''# -*- coding: utf-8 -*-
import core.yf as yf


def _run_cmd(cmd):
    res = {"data": ""}
    return res


def get_services():
    services = []
    # BAD-1：数据实参引用了只存在于兄弟函数里的名字（本次线上故障原形）
    return yf.returnJson(True, "获取成功", res["data"])


def create():
    try:
        con = None
        if con:
            return yf.returnJson(True, "创建成功!")
        # BAD-2：ex 要等到下面 except 才绑定，这里用得太早
        return yf.returnJson(False, "创建失败!" + str(ex))
    except ValueError as ex:
        return yf.returnJson(False, "创建失败!" + str(ex))


def set_master():
    # BAD-3：mode 在本作用域内从未绑定
    return yf.returnJson(True, "设置成功", mode)
'''

FIXTURE_GOOD = '''# -*- coding: utf-8 -*-
import core.yf as yf

FLAG = True


def get_services():
    services = []
    return yf.returnJson(True, "获取成功", services)


def create():
    ex = None
    try:
        con = None
        if con:
            return yf.returnJson(True, "创建成功!")
        return yf.returnJson(False, "创建失败!" + str(ex))
    except ValueError as ex:
        return yf.returnJson(False, "创建失败!" + str(ex))


def set_master():
    args = {"mode": "a"}
    mode = args["mode"]
    return yf.returnJson(True, "设置成功", mode)


def set_slave():
    dodb = []
    return yf.returnJson(True, "设置成功", [dodb])


def with_loop():
    for i in range(3):
        pass
    return yf.returnJson(True, "设置成功", i)


def with_closure():
    data = {}

    def inner():
        return data

    return yf.returnJson(True, "设置成功", data)


def with_builtins():
    return yf.returnJson(True, "设置成功", len([1]))


def nested_call():
    return yf.returnJson(True, "设置成功", str(FLAG) + helper())


def helper():
    return ""
'''

FIXTURE_STAR = '''# -*- coding: utf-8 -*-
from struct import *
import core.yf as yf


def f():
    # 星号导入下模块级名字不可判定 -> 检测器必须整体放弃，不得误报
    return yf.returnJson(True, "ok", pack("i", 1))
'''


def _plugin_entry_files():
    out = []
    if not os.path.isdir(PLUGIN_ROOT):
        return out
    for name in sorted(os.listdir(PLUGIN_ROOT)):
        path = os.path.join(PLUGIN_ROOT, name, 'index.py')
        if os.path.isfile(path):
            out.append(path)
    return out


class ReturnJsonNameGuard(unittest.TestCase):
    """检测器自证：既会响，也不乱响。"""

    def test_self_test_bad_fixture_flags_exactly_three(self):
        got = scan_source(FIXTURE_BAD, 'fixture_bad.py')
        names = sorted(n for _, n, _ in got)
        self.assertEqual(names, ['ex', 'mode', 'res'],
                         '内嵌坏夹具应恰好报出 res / ex / mode，实际: %r' % (got,))

    def test_self_test_good_fixture_is_clean(self):
        got = scan_source(FIXTURE_GOOD, 'fixture_good.py')
        self.assertEqual(got, [], '合法写法被误报: %r' % (got,))

    def test_self_test_star_import_is_skipped(self):
        self.assertEqual(scan_source(FIXTURE_STAR, 'fixture_star.py'), [])


class PluginReturnJsonNameContract(unittest.TestCase):
    """仓库级契约：插件入口的 returnJson 实参必须全部可解析。"""

    def test_plugin_index_files_exist(self):
        files = _plugin_entry_files()
        # 扫描面下限：防止路径写错导致「扫了 0 个文件 -> 真空通过」
        self.assertGreaterEqual(len(files), 30, '插件入口数量异常: %d' % len(files))

    def test_no_undefined_name_in_returnjson_args(self):
        problems = []
        scanned = 0
        for path in _plugin_entry_files():
            with io.open(path, encoding='utf-8') as fp:
                src = fp.read()
            scanned += 1
            rel = os.path.relpath(path, BASE_DIR).replace(os.sep, '/')
            for line, name, call_line in scan_source(src, rel):
                problems.append('%s:%d  returnJson(第 %d 行) 实参引用未定义名: %s'
                                % (rel, line, call_line, name))
        self.assertGreaterEqual(scanned, 30, '实际扫描文件数异常: %d' % scanned)
        self.assertEqual(problems, [], '发现未定义名:\n  ' + '\n  '.join(problems))


if __name__ == '__main__':
    unittest.main(verbosity=2)
