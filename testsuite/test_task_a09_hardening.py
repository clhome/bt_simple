# coding: utf-8
"""A09 task 模块加固守卫（任务队列：分页入参 / 日志 id / 取消 / 前端转义）。

真机实测确认并修复的缺陷，全部在此锁死，防止回退：

1. `POST /task/list` 直接把 `request.form.get('p'/'limit')` 交给 `int()`：
   非数字入参抛 ValueError -> HTTP 500；且 limit 无上限（`limit=-1`/极大值在
   SQLite 下等价于无 LIMIT，一次拉全表）。
2. `POST /task/get_task_log_by_id` 未校验 id：id 被拼进日志路径
   （`tmp/panelTask_{id}.log`），`1/../../../../../var/log/dpkg` 之类可借已存在
   目录穿越读取任意 `*.log` 文件。
3. `POST /task/remove_task` 对不存在的 id 也回「任务已删除!」（假成功）。
4. `web/static/app/public.js` 的 `showTaskLog` 缺 `.fail()`：后端 500 时
   loading 遮罩永久卡死；任务名/日志内容未转义直接拼进 layer 标题 / textarea /
   onclick，构成存储型 XSS。

断言口径（防「假绿」）：
- Python 侧用 **AST** 且过滤 `if False:` 等静态死分支，注释天然不参与；
- JS 侧先做**引号感知的注释剥离**，再对剥离后的源码断言，注释里写关键字蒙混无效。
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TASK_ROUTE_PATH = os.path.join(ROOT, 'web', 'admin', 'task', '__init__.py')
PUBLIC_JS_PATH = os.path.join(ROOT, 'web', 'static', 'app', 'public.js')


# ---------------------------------------------------------------------------
# Python：AST 工具（跳过静态死分支，抵御 `if False:` 蒙混）
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _parse(path):
    return ast.parse(_read(path))


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_const_false(test):
    return isinstance(test, ast.Constant) and not test.value


def _live_nodes(node):
    """产出「可达」AST 节点，跳过 `if False:` / `while False:` 等静态死分支。"""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.If):
            if not _is_const_false(n.test):
                stack.append(n.test)
                stack.extend(n.body)
            stack.extend(n.orelse)
            continue
        if isinstance(n, ast.While) and _is_const_false(n.test):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _live_calls(node):
    """收集「可达」代码里的调用名，跳过 `if False:` / `while False:` 死分支。"""
    names = []
    for n in _live_nodes(node):
        if isinstance(n, ast.Call):
            func = n.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


# ---------------------------------------------------------------------------
# JS：引号感知的注释剥离（注释里写关键字不能蒙混过关）
# ---------------------------------------------------------------------------

def _strip_js_comments(src):
    """剥离 JS 注释，保留字符串/正则字面量。

    朴素做法（只看引号）会被 `.replace(/"/g, ...)` 这类**含引号的正则字面量**带偏：
    正则里的 `"` 会被当成字符串起点，之后整段错位，注释再也剰不掉。
    因此这里用「上一个有效字符」启发式识别正则字面量。
    """
    regex_prev_chars = set("(,=:[!&|?{};+-*%<>~^\n")
    regex_prev_words = {
        'return', 'typeof', 'case', 'in', 'of', 'do', 'else', 'void',
        'delete', 'instanceof', 'new', 'yield', 'throw',
    }
    out = []
    i, n = 0, len(src)
    prev_ch = ''
    prev_word = ''
    word = ''
    while i < n:
        ch = src[i]
        if ch in ('"', "'", '`'):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                c = src[i]
                out.append(c)
                i += 1
                if c == '\\' and i < n:
                    out.append(src[i])
                    i += 1
                    continue
                if c == quote:
                    break
            prev_ch = quote
            prev_word = word
            word = ''
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            i += 2
            while i < n and src[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        if ch == '/' and (prev_ch in regex_prev_chars or prev_word in regex_prev_words):
            out.append(ch)
            i += 1
            in_class = False
            while i < n:
                c = src[i]
                out.append(c)
                i += 1
                if c == '\\' and i < n:
                    out.append(src[i])
                    i += 1
                    continue
                if c == '[':
                    in_class = True
                elif c == ']':
                    in_class = False
                elif c == '/' and not in_class:
                    break
            while i < n and src[i].isalpha():
                out.append(src[i])
                i += 1
            prev_ch = '/'
            prev_word = word
            word = ''
            continue
        out.append(ch)
        if not ch.isspace():
            prev_ch = ch
            if ch.isalnum() or ch == '_':
                word += ch
            else:
                prev_word = word
                word = ''
        i += 1
    return ''.join(out)


class TestTaskA09Hardening(unittest.TestCase):

    # ---- 1. /task/list 分页入参 -------------------------------------------------
    def test_01_task_list_pagination_is_input_safe(self):
        tree = _parse(TASK_ROUTE_PATH)
        fn = _find_func(tree, 'list')
        self.assertIsNotNone(fn, 'task/list 路由函数缺失')
        calls = _live_calls(fn)
        self.assertIn('_to_positive_int', calls,
                      'task/list 必须用 _to_positive_int 容错解析分页参数')

        # 必须对 limit 传上限做钳制（第 3 个位置参数即 maximum）
        clamp_calls = [
            c for c in _live_nodes(fn)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            and c.func.id == '_to_positive_int' and len(c.args) >= 3
        ]
        self.assertTrue(clamp_calls, 'task/list 必须给 limit 传上限，避免一次拉全表')

        # 不得再把 request.form.get(...) 直接交给 int()
        for c in ast.walk(fn):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == 'int'):
                continue
            for arg in c.args:
                self.assertFalse(
                    isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                    and arg.func.attr == 'get',
                    'task/list 仍把 request.form.get(...) 直接交给 int()，非数字入参会 500')

    def test_02_positive_int_helper_rejects_bad_input(self):
        """_to_positive_int 的行为契约：非数字/越界回退默认值，上限钳制。"""
        tree = _parse(TASK_ROUTE_PATH)
        fn = _find_func(tree, '_to_positive_int')
        self.assertIsNotNone(fn, '_to_positive_int 助手缺失')
        # 结构化断言：函数体里必须出现 except (TypeError, ValueError) 兜底
        except_types = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                except_types.add(ast.unparse(node.type))
        joined = ' '.join(sorted(except_types))
        self.assertIn('ValueError', joined,
                      '_to_positive_int 必须捕获 ValueError（int() 对非数字会抛）')

    # ---- 2. /task/get_task_log_by_id id 校验 -----------------------------------
    def test_03_task_log_id_validated_before_path(self):
        tree = _parse(TASK_ROUTE_PATH)
        fn = _find_func(tree, 'get_task_log_by_id')
        self.assertIsNotNone(fn, 'task/get_task_log_by_id 路由函数缺失')
        self.assertIn('_is_task_id', _live_calls(fn),
                      'task/get_task_log_by_id 必须用 _is_task_id 校验入参')
        code = ast.unparse(fn)
        self.assertIn('.format(int(task_id))', code,
                      '日志路径必须用 int(task_id) 拼接')
        self.assertNotIn('.format(task_id)', code,
                         '日志路径不得直接用未校验的 task_id 拼接（可路径穿越）')

    # ---- 3. /task/remove_task 校验 + 如实返回 -----------------------------------
    def test_04_remove_task_validates_and_reports_truthfully(self):
        tree = _parse(TASK_ROUTE_PATH)
        fn = _find_func(tree, 'remove_task')
        self.assertIsNotNone(fn, 'task/remove_task 路由函数缺失')
        calls = _live_calls(fn)
        self.assertIn('_is_task_id', calls,
                      'task/remove_task 必须校验 id 为正整数')
        self.assertIn('removeTask', calls,
                      'task/remove_task 必须委托 utils.task.removeTask 执行')

        # 必须存在「查库确认任务存在 -> 否则 returnData(False, ...)」的守卫
        guarded = False
        for node in _live_nodes(fn):
            if not isinstance(node, ast.If):
                continue
            if 'getField' not in _live_calls(node.test):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and stmt.value is not None:
                    if 'returnData(False' in ast.unparse(stmt.value):
                        guarded = True
        self.assertTrue(
            guarded,
            'remove_task 必须对不存在的任务返回 returnData(False, ...)，不能假成功')

    def test_05_is_task_id_rejects_traversal(self):
        """_is_task_id 的行为契约：只放行正整数。"""
        src = _read(TASK_ROUTE_PATH)
        tree = ast.parse(src)
        fn = _find_func(tree, '_is_task_id')
        self.assertIsNotNone(fn, '_is_task_id 助手缺失')
        code = ast.unparse(fn)
        self.assertIn('isdigit', code, '_is_task_id 必须用 isdigit 限定数字')
        # 用真实实现跑一遍，防止「结构对但语义反」
        ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<a09>', 'exec'), ns)
        is_task_id = ns['_is_task_id']
        self.assertTrue(is_task_id('70'))
        self.assertTrue(is_task_id(' 70 '))
        for bad in ('', 'abc', '1/../../../../../var/log/dpkg', '-1', '0',
                    '1;id', '../../etc/passwd', '1e3', '99999999999999999999x'):
            self.assertFalse(is_task_id(bad), '_is_task_id 放行了非法 id: %r' % bad)

    # ---- 4~6. 前端 public.js ---------------------------------------------------
    def setUp(self):
        self._js = _strip_js_comments(_read(PUBLIC_JS_PATH))

    def test_06_task_log_modal_escapes_and_closes_mask(self):
        self.assertIn('function yfTaskEsc(', self._js,
                      '缺少 yfTaskEsc 转义助手')
        # showTaskLog 失败分支必须关闭 loading 遮罩
        self.assertIn("layer.msg(t('public.load_fail'", self._js,
                      'showTaskLog 失败分支未提示/未关闭遮罩')
        self.assertIn('yfTaskEsc(name)', self._js,
                      'showTaskLog 未转义任务名（layer 标题 XSS）')
        self.assertIn('yfTaskEsc(rdata', self._js,
                      'showTaskLog 未转义日志内容（textarea XSS）')

    def test_07_task_list_escapes_name_and_avoids_inline_js(self):
        self.assertIn('data-task-name="\' + yfTaskEsc(g.data[d].name)',
                      self._js,
                      'task/remind 列表未通过 data 属性传递已转义的任务名')
        self.assertNotIn('onclick="showTaskLog(',
                         self._js,
                         'remind 仍把任务名拼进内联 onclick（单引号可逃逸 -> XSS）')
        self.assertIn('yfTaskEsc(g.data[d].add_time)', self._js,
                      'remind 未转义 add_time')

    def test_08_running_task_view_escapes_name_and_log(self):
        self.assertGreaterEqual(
            self._js.count('yfTaskEsc(h.task[g].name)'), 3,
            'getReloads/renderRunTask 中至少 3 处任务名未转义')
        self.assertIn('yfTaskEsc(f[e])', self._js,
                      'renderRunTask 未转义任务输出行（HTML 注入）')
        self.assertIn('yfTaskEsc(logs)', self._js,
                      'execLog 未转义日志内容（textarea XSS）')


if __name__ == '__main__':
    unittest.main()
