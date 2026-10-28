# coding: utf-8
"""守卫：插件/后端内部不得把「JSON 字符串」当 dict 用（也不得重复编码）。

## 为什么有这个用例

`yf.returnJson(...)` / `yf.getJson(...)` 返回的是**字符串**（给 HTTP/CLI 出口用的），
而 `yf.returnData(...)` / `yf.returnMsg(...)` 返回 **dict**（内部传递用）。两者混用时
不会在定义处报错，只在使用处炸，且往往炸在「安装/修复」这种最要紧的路径上：

* mysql 插件 `selfCheck()` 曾返回 JSON 串，两处调用点却 `.get('status')`：
    - `index.py self_check` → 自检**通过了**却带 traceback 退出 1，install.sh 判
      「自检未通过」（CI 红灯）；
    - 面板【修复】→ 实例已修好，却回「修复失败,错误: 'str' object has no attribute 'get'」。
* docker 插件 `repoList()` 返回 JSON 串，`dockerPullPrivateNew` 却写
  `isinstance(my_repo, dict)` → 恒 False → **私库拉取 100% 报「未登录任何私人存储库」**。

修法统一为「内部返回 dict / 出口再序列化」，并给入口加 `_resultDict()` 归一化。
本用例把这套判据钉成静态扫描，防止同类写法再长回来。

## 判据

1. 收集「返回 JSON 字符串」的内部函数（函数体里 `return yf.returnJson(...)` /
   `yf.getJson(...)` / `json.dumps(...)`）。
2. 找这些函数返回值被**当 dict 用**的位置：`.get(` / `.keys(` / 下标取值 /
   `isinstance(x, dict)` / 再 `json.dumps(x)` / 再 `yf.getJson(x)`。
3. 允许清单（`ALLOW`）只放**确实有意**双编码且前端配套解析的点，必须写原因。
"""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOTS = ('plugins', 'web')
SKIP_DIRS = {'__pycache__', 'versions', 'node_modules', '.git'}
JSON_CALLS = {'returnJson', 'getJson', 'dumps'}
DICT_ATTRS = {'get', 'keys', 'items', 'values', 'setdefault', 'update'}

#: 有意为之 / 已被前置守卫排除的点（file, kind, 所在函数）→ 原因。
#: 按「函数」而不是「文件」或「行号」登记：行号会漂，按文件太宽（会掩护同文件里的新缺陷）。
ALLOW = {
    # op_waf 的历史契约：`get_site_config` 的 data 是字符串，前端 `wafSite()` 里
    # `JSON.parse(data.data)` 之后再 `JSON.parse(tmp.data)`。去掉双编码会让
    # 「网站防火墙列表」整页报错，属前后端成对契约，不在本轮收敛。
    ('plugins/op_waf/index.py', 'DOUBLE_JSON', 'getSiteConfig'):
        '前端 wafSite() 按两层 JSON.parse 解析（成对契约）',
    # 同上契约的另一个出口；`get_site_rule` 目前前端未调用，行为保持不变。
    ('plugins/op_waf/index.py', 'DOUBLE_JSON', 'getSiteRule'):
        '与 getSiteConfig 同一套双编码契约，前端未调用，暂不动',
    # `getLibConf` 开头是 `if isinstance(libs, str): return libs`，走到 returnJson
    # 时 libs 必为 dict —— 扫描器不做控制流分析，这里如实登记。
    ('plugins/php/index.py', 'DOUBLE_JSON', 'getLibConf'):
        '前置 isinstance(libs, str) 已提前返回，到达此处必为 dict',
}


def _callee(node):
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _is_json_str_expr(node):
    return _callee(node) in JSON_CALLS


def _enclosing_func(tree):
    """node id -> 所在函数名（模块级为 '<module>'）。"""
    owner = {}

    def walk(node, cur):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner[id(ch)] = ch.name
                walk(ch, ch.name)
            else:
                owner[id(ch)] = cur
                walk(ch, cur)

    walk(tree, '<module>')
    return owner


def _scope_nodes(scope):
    """遍历一个作用域内的节点，**不进入**嵌套的函数/类（避免把别的函数的局部变量算进来）。"""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def scan_source(src, rel):
    """返回命中列表 [(kind, rel, line, detail)]。"""
    tree = ast.parse(src)
    json_funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and _is_json_str_expr(sub.value):
                    json_funcs.add(node.name)
                    break
    owner = _enclosing_func(tree)
    hits = []
    if not json_funcs:
        return hits

    def _func_of(node):
        return owner.get(id(node), '<module>')

    def is_json_call(node):
        """这个调用是否会给出 JSON 字符串（直调出口，或调用了内部 JSON 函数）。"""
        name = _callee(node)
        return name in JSON_CALLS or name in json_funcs

    # 直接链式：f(...).get() / f(...)[k]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in DICT_ATTRS and is_json_call(node.value):
            hits.append(('STR_USED_AS_DICT', rel, node.lineno, _func_of(node),
                         '对 %s() 的返回值直接取 .%s()' % (_callee(node.value), node.attr)))
        elif isinstance(node, ast.Subscript) and is_json_call(node.value):
            hits.append(('STR_USED_AS_DICT', rel, node.lineno, _func_of(node),
                         '对 %s() 的返回值直接下标取值' % _callee(node.value)))

    # 赋值污点（含模块级作用域）：按「行号时间线」跟踪每个名字最近一次赋值，
    # 只看最近一次赋值是 JSON 串的那些使用点（否则 `content = json.loads(content)`
    # 这种重新赋值会被误报）。
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        # name -> [(lineno, is_json, callee)]
        assigns = {}
        json_assign_nodes = set()
        for node in _scope_nodes(scope):
            if isinstance(node, ast.Assign):
                is_json = is_json_call(node.value)
                if is_json:
                    json_assign_nodes.add(id(node.value))
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        assigns.setdefault(t.id, []).append(
                            (node.lineno, is_json, _callee(node.value)))
        if not any(a[1] for lst in assigns.values() for a in lst):
            continue

        def _taint_at(name, lineno):
            """该名字在第 lineno 行时是不是「JSON 字符串」（按最近一次赋值判断）。"""
            hist = [a for a in assigns.get(name, []) if a[0] < lineno]
            if not hist:
                return None
            last = max(hist, key=lambda a: a[0])
            return last if last[1] else None

        for node in _scope_nodes(scope):
            if id(node) in json_assign_nodes:
                continue

            def _hit(base):
                return _taint_at(base.id, node.lineno) if isinstance(base, ast.Name) else None

            if isinstance(node, ast.Attribute) and node.attr in DICT_ATTRS:
                t = _hit(node.value)
                if t:
                    hits.append(('STR_USED_AS_DICT', rel, node.lineno, _func_of(node),
                                 '%s = %s(...)（第 %d 行）之后被当成 dict 用 .%s()'
                                 % (node.value.id, t[2], t[0], node.attr)))
            elif isinstance(node, ast.Subscript):
                t = _hit(node.value)
                if t:
                    hits.append(('STR_USED_AS_DICT', rel, node.lineno, _func_of(node),
                                 '%s = %s(...)（第 %d 行）之后被下标取值'
                                 % (node.value.id, t[2], t[0])))
            elif isinstance(node, ast.Call) and _callee(node) == 'isinstance' and len(node.args) == 2:
                arg, typ = node.args
                if isinstance(typ, ast.Name) and typ.id == 'dict':
                    t = _hit(arg)
                    if t:
                        hits.append(('STR_USED_AS_DICT', rel, node.lineno, _func_of(node),
                                     'isinstance(%s, dict) 恒为 False（%s 是 JSON 串）'
                                     % (arg.id, t[2])))
            elif isinstance(node, ast.Call) and _callee(node) in ('dumps', 'getJson', 'returnJson'):
                for a in node.args:
                    t = _hit(a)
                    if t:
                        hits.append(('DOUBLE_JSON', rel, node.lineno, _func_of(node),
                                     '%s(%s)，而 %s 已是 JSON 串（第 %d 行）'
                                     % (_callee(node), a.id, a.id, t[0])))
    return hits


def scan_repo():
    hits = []
    for root in SCAN_ROOTS:
        base = os.path.join(ROOT, root)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if not name.endswith('.py'):
                    continue
                p = os.path.join(dirpath, name)
                rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
                with open(p, encoding='utf-8', errors='replace') as f:
                    src = f.read()
                try:
                    hits.extend(scan_source(src, rel))
                except SyntaxError:
                    continue
    return hits


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _func_src(rel, name):
    src = _read(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s::%s' % (rel, name))


MYSQL_PY = 'plugins/mysql/index.py'
MARIADB_PY = 'plugins/mariadb/index.py'
DOCKER_PY = 'plugins/docker/index.py'
MARIADB_SH = 'plugins/mariadb/install.sh'


class TestPluginJsonReturnType(unittest.TestCase):

    # ---- 1. 仓库级扫描 ----

    def test_01_no_json_string_used_as_dict(self):
        """全仓不得再有「JSON 串当 dict 用 / 重复编码」，允许清单必须写明原因。"""
        bad = []
        for kind, rel, line, func, detail in scan_repo():
            if (rel, kind, func) in ALLOW:
                continue
            bad.append('%s:%d [%s/%s] %s' % (rel, line, kind, func, detail))
        self.assertEqual([], bad,
                         'JSON 字符串被当成 dict / 重复编码（内部返回请用 returnData/returnMsg，'
                         '调用点用 _resultDict 归一化）：\n  ' + '\n  '.join(bad))

    def test_02_scanner_actually_catches_the_historical_bug(self):
        """变异自证：把 mysql 修复前的写法喂给扫描器，必须命中（否则本用例是永绿）。"""
        fixture = (
            'def selfCheck(v):\n'
            '    return yf.returnJson(True, "ok")\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    _sc = selfCheck("5.7")\n'
            '    print(_sc.get("status"))\n'
        )
        hits = scan_source(fixture, 'fixture.py')
        self.assertTrue(any(k == 'STR_USED_AS_DICT' for k, _r, _l, _f, _d in hits),
                        '扫描器没能识别「返回 JSON 串的函数的返回值被 .get()」，变异未生效')

    def test_03_scanner_catches_isinstance_dict_on_json_string(self):
        """docker 私库拉取那种写法（isinstance 恒 False）也必须被识别。"""
        fixture = (
            'def repoList():\n'
            '    return yf.returnJson(True, "ok", [])\n'
            '\n'
            'def pull():\n'
            '    my_repo = repoList()\n'
            '    if not isinstance(my_repo, dict) or not my_repo.get("data"):\n'
            '        return None\n'
        )
        hits = scan_source(fixture, 'fixture.py')
        detail = ' '.join(d for _k, _r, _l, _f, d in hits)
        self.assertIn('isinstance', detail, '扫描器没识别 isinstance(x, dict) 恒假：%s' % detail)

    # ---- 2. mysql / mariadb 对称性（装后自检这一层）----

    def _assert_selfcheck_contract(self, rel, label):
        src = _read(rel)
        self.assertIn('def selfCheck(', src, '%s 缺少 selfCheck' % label)
        body = _func_src(rel, 'selfCheck')
        self.assertIn('_result(', body,
                      '%s selfCheck 必须返回 dict（经 _result 构造），不能返回 JSON 串' % label)
        self.assertNotIn('yf.returnJson(', body,
                         '%s selfCheck 里出现 returnJson → 内部调用方 .get() 会炸' % label)
        # CLI 入口必须归一化再 .get('status')
        self.assertIn("elif func == 'self_check':", src,
                      '%s 缺少 self_check 命令行入口（install.sh 靠它做装后自检）' % label)
        idx = src.index("elif func == 'self_check':")
        block = src[idx:idx + 600]
        self.assertIn('_resultDict(selfCheck(', block,
                      '%s 的 self_check 入口必须先 _resultDict 归一化' % label)
        self.assertIn(".get('status')", block, '%s 的 self_check 入口应据 status 定退出码' % label)

    def test_10_mysql_selfcheck_contract(self):
        self._assert_selfcheck_contract(MYSQL_PY, 'mysql')

    def test_11_mariadb_selfcheck_contract(self):
        """mariadb 与 mysql 必须同口径：装后自检 + 实例归属 + 修复前的归属判定。"""
        self._assert_selfcheck_contract(MARIADB_PY, 'mariadb')
        src = _read(MARIADB_PY)
        self.assertIn('def instanceOwnership(', src,
                      'mariadb 缺少实例归属判定：3306 被别人的实例占着时会把假成功当成功')
        self.assertIn('def getRunningMariadbdProcs(', src, 'mariadb 缺少 /proc 进程扫描')
        fix = _func_src(MARIADB_PY, 'fixDbAccess')
        self.assertIn('instanceOwnership()', fix,
                      'mariadb【修复】缺少归属判定：会停掉别人的实例并改它 root 口令')
        self.assertIn("own['status'] in ('foreign_only', 'mixed')", fix,
                      'mariadb【修复】的归属判定必须拒 foreign_only / mixed')
        self.assertIn('_resultDict(selfCheck(version))', fix,
                      'mariadb【修复】要在修完后自检，且必须归一化后再 .get()')
        boot = _func_src(MARIADB_PY, 'start')
        self.assertIn("'stale_ours'", boot,
                      'mariadb start 必须先清理「程序文件已删但进程还在」的僵尸实例')

    def test_12_mariadb_install_sh_runs_selfcheck(self):
        """mariadb 的 install.sh 装完必须跑 self_check（只看 data 目录在不在是假成功）。"""
        sh = _read(MARIADB_SH)
        self.assertIn('plugins/mariadb/index.py self_check', sh,
                      'mariadb install.sh 没有调用 self_check，装完无法发现「连不上自己的库」')
        self.assertIn('plugins/mariadb/index.py fix_db_access', sh,
                      'mariadb install.sh 应在自检前先 fix_db_access（首次安装写 root 口令）')
        self.assertIn('MariaDB 自检未通过', sh, 'mariadb install.sh 缺少自检失败提示')

    # ---- 3. docker 私库拉取 ----

    def test_20_docker_private_pull_parses_repolist(self):
        """dockerPullPrivateNew 必须先把 repoList() 的 JSON 串归一化成 dict。"""
        body = _func_src(DOCKER_PY, 'dockerPullPrivateNew')
        self.assertIn('_resultDict(repoList())', body,
                      'repoList() 返回 JSON 串，必须 _resultDict 归一化后再取 data')
        self.assertNotIn('isinstance(my_repo, dict)', body,
                         'isinstance(JSON 串, dict) 恒为 False → 私库拉取永远报「未登录」')
        src = _read(DOCKER_PY)
        self.assertIn('def _resultDict(', src, 'docker 插件缺少 _resultDict 归一化助手')


if __name__ == '__main__':
    unittest.main()
