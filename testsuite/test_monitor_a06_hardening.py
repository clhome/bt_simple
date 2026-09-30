# coding:utf-8
"""A06 监控模块硬化回归。

覆盖本轮真机测试发现的三类问题：

1. ``POST /system/set_control`` 的「保存天数」直接 ``int(day)``：
   ``day=abc`` / 缺 day / ``day=1 OR 1=1`` → 未捕获 ValueError → **HTTP 500**；
   ``day=99999999999999999999`` 被原样写库 → 历史清理阈值溢出、库无限增长。
2. ``monitor.clearDbFile()``（「清空记录」）用 ``os.remove`` 删 system.db：
   ``core.db`` 按路径按线程缓存连接，web 进程与 panel_task 采样进程都仍指向
   已被 unlink 的 inode → 采样写进「幽灵文件」（监控页永久空白）、
   文件不存在时还抛 FileNotFoundError（接口 500）。改为就地 DELETE 所有表。
3. ``stats.disk()`` 遇到新出现的磁盘（缓存里没有基线）取 ``diskio_cache[name]``
   → KeyError 被外层 except 吞掉 → 整份采样退化成「ALL 全 0」的假数据且缓存不再更新。

另含两条前端守卫：control.js 的 7 个请求必须有 ``.fail()``
（缺了它后端 500 时 ``layer.msg(..., time:0)`` 遮罩永久卡死）。
"""
import ast
import collections
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
sys.path.insert(0, WEB)

# 本地开发机通常没有 psutil（生产 PHP/面板环境才有）：与仓库既有用法一致，
# 缺失时用 MagicMock 顶替，本文件所有用例都显式替换 psutil 调用，不依赖其真实行为。
if 'psutil' not in sys.modules:
    sys.modules['psutil'] = mock.MagicMock()

import core.db as db  # noqa: E402
import core.yf as yf  # noqa: E402
import utils.system  # noqa: E402

MONITOR_MOD = sys.modules['utils.system.monitor']
STATS_MOD = sys.modules['utils.system.stats']
monitor = MONITOR_MOD.monitor
stats = STATS_MOD.stats

SYSTEM_PY = os.path.join(WEB, 'admin', 'system', 'system.py')
MONITOR_PY = os.path.join(WEB, 'utils', 'system', 'monitor.py')
STATS_PY = os.path.join(WEB, 'utils', 'system', 'stats.py')
CONTROL_JS = os.path.join(WEB, 'static', 'app', 'control.js')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _unparse(path):
    return ast.unparse(ast.parse(_read(path)))


def _unparse_fn(path, name):
    return ast.unparse(_get_fn(path, name))


def _call_names(node):
    """收集函数体里真实发生的调用名（注释/文档字符串里提到的不算）。"""
    names = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            names.append(ast.unparse(sub.func))
    return names


def _get_fn(path, name):
    """取函数定义（模块级函数或类方法均可）。"""
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('找不到函数 %s（修复被回退或改名）' % name)


def _load_monitor_day_max():
    """从 monitor.py 单源读出保存天数上限，避免测试里再抄一遍数字。"""
    tree = ast.parse(_read(MONITOR_PY))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'MONITOR_DAY_MAX' for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('monitor.py 缺少 MONITOR_DAY_MAX（单源上限被删）')


def _load_parse_monitor_day():
    """按真实源码抽出 _parseMonitorDay 执行，测行为而不是测字符串。"""
    name = '_parseMonitorDay'
    fn = _get_fn(SYSTEM_PY, name)
    ns = {'MONITOR_DAY_MAX': _load_monitor_day_max()}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), SYSTEM_PY, 'exec'), ns)
    return ns[name]


class TestParseMonitorDay(unittest.TestCase):
    """修复 1：保存天数入参必须被解析成 1..上限 的整数，非法一律拒绝。"""

    def setUp(self):
        self.parse = _load_parse_monitor_day()

    def test_valid_values(self):
        self.assertEqual(self.parse('30'), 30)
        self.assertEqual(self.parse('1'), 1)
        self.assertEqual(self.parse(' 7 '), 7)
        self.assertEqual(self.parse('3650'), 3650)
        # int() 语义：纯空白包裹仍可解析（正常输入），归一化后写库
        self.assertEqual(self.parse('\n30'), 30)

    def test_invalid_values_rejected(self):
        for bad in ('abc', '', '   ', '1 OR 1=1', '30;drop table', '1e5', '30.5',
                    '中文', None, 'nan', 'inf', '0x10'):
            self.assertIsNone(self.parse(bad), '非法保存天数必须被拒: %r' % (bad,))

    def test_out_of_range_rejected(self):
        for bad in ('0', '-1', '-7', '3651', '99999999999999999999'):
            self.assertIsNone(self.parse(bad), '越界保存天数必须被拒: %r' % (bad,))

    def test_route_uses_parser_not_int(self):
        src = _unparse_fn(SYSTEM_PY, 'set_control')
        self.assertEqual(src.count('_parseMonitorDay(day)'), 3,
                         'type=0/1/save_day 三个分支都必须走安全解析')
        self.assertNotIn('int(day)', src, '裸 int(day) 会在非数字入参上抛 500')

    def test_max_constant_is_imported_from_monitor_module(self):
        # `from utils.system import monitor` 拿到的是**类**（utils/system/__init__ 里
        # 子模块名被类覆盖），写 monitor.MONITOR_DAY_MAX 真机上会 AttributeError → 500。
        self.assertIn('from utils.system.monitor import MONITOR_DAY_MAX', _read(SYSTEM_PY))
        self.assertNotIn('monitor.MONITOR_DAY_MAX', _unparse(SYSTEM_PY))


class TestClearMonitorHistory(unittest.TestCase):
    """修复 2：「清空记录」不许删文件（幽灵 inode / FileNotFoundError）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_a06_guard_')
        sql_dir = os.path.join(self.tmp, 'web', 'admin', 'setup', 'sql')
        os.makedirs(sql_dir, exist_ok=True)
        shutil.copy(os.path.join(WEB, 'admin', 'setup', 'sql', 'system.sql'),
                    os.path.join(sql_dir, 'system.sql'))
        self.data = os.path.join(self.tmp, 'data')
        os.makedirs(self.data, exist_ok=True)
        self.patcher_dir = mock.patch.object(yf, 'getPanelDir', lambda *a, **k: self.tmp)
        self.patcher_data = mock.patch.object(yf, 'getPanelDataDir', lambda *a, **k: self.data)
        self.patcher_dir.start()
        self.patcher_data.start()
        self.m = monitor()
        self.m._dbfile = os.path.join(self.data, 'system.db')
        self.m.initDBFile()

    def tearDown(self):
        self.patcher_data.stop()
        self.patcher_dir.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _count(self, table):
        conn = sqlite3.connect(self.m._dbfile)
        try:
            return conn.execute('select count(*) from %s' % table).fetchone()[0]
        finally:
            conn.close()

    def test_clear_keeps_file_and_cached_connection_alive(self):
        sql = db.Sql().dbPos(self.data, 'system')
        # 先写一行，让连接进入 core.db 的按路径缓存（与面板进程现状一致）
        sql.table('cpuio').add('pro,mem,addtime', (1.0, 2.0, 100))
        sql.table('load_average').add('pro,one,five,fifteen,addtime', (1.0, 1.0, 1.0, 1.0, 100))
        self.assertEqual(self._count('cpuio'), 1)

        self.assertTrue(self.m.clearDbFile())
        self.assertTrue(os.path.exists(self.m._dbfile),
                        '清空记录不得删库文件（旧实现 os.remove 后采样写进幽灵 inode）')
        for table in ('cpuio', 'network', 'diskio', 'load_average'):
            self.assertEqual(self._count(table), 0, '清空后 %s 必须为空' % table)

        # 清空后同一个（已缓存的）连接继续写：数据必须落在“可见文件”里
        sql.table('cpuio').add('pro,mem,addtime', (3.0, 4.0, 200))
        self.assertEqual(self._count('cpuio'), 1,
                         '清空后采样必须写进可见文件（旧实现写进已被 unlink 的 inode，这里会是 0）')

    def test_clear_on_missing_file_does_not_raise(self):
        missing = monitor()
        missing._dbfile = os.path.join(self.data, 'never_created.db')
        self.assertTrue(missing.clearDbFile(), '库文件不存在时「清空记录」不得抛异常')

    def test_source_no_longer_removes_db_file(self):
        fn = _get_fn(MONITOR_PY, 'clearDbFile')
        calls = _call_names(fn)
        self.assertNotIn('os.remove', calls, '「清空记录」不得再删库文件')
        self.assertIn('delete', [c.split('.')[-1] for c in calls], '必须改为就地 DELETE')


class TestGetMonitorDayClamp(unittest.TestCase):
    """修复 1 配套：option 里的脏值不能弄崩采样线程，也不能按天文数字保留。"""

    def _call(self, value):
        fake = mock.MagicMock()
        fake.return_value.field.return_value.where.return_value.getField.return_value = value
        with mock.patch.object(yf, 'M', fake):
            return monitor().getMonitorDay()

    def test_defaults(self):
        self.assertEqual(self._call(''), 30)
        self.assertEqual(self._call(None), 30)

    def test_valid(self):
        self.assertEqual(self._call('7'), 7)

    def test_dirty_values_fall_back(self):
        for bad in ('abc', '0', '-3', '99999999999999999999'):
            self.assertEqual(self._call(bad), 30, '脏值 %r 必须退回默认 30 天' % (bad,))

    def test_max_is_shared_single_source(self):
        self.assertEqual(_load_monitor_day_max(), 3650)
        src = _unparse_fn(MONITOR_PY, 'getMonitorDay')
        self.assertIn('MONITOR_DAY_MAX', src, '读侧必须与写侧共用同一个上限常量')


class TestDiskIoNewDevice(unittest.TestCase):
    """修复 3：缓存里没有基线的新磁盘不能让整份磁盘 IO 采样变成假零值。"""

    def setUp(self):
        self._saved_cache = dict(stats.cache)
        stats.cache.clear()
        self.io = collections.namedtuple(
            'sdiskio',
            'read_count write_count read_bytes write_bytes read_time write_time '
            'read_merged_count write_merged_count busy_time')

    def tearDown(self):
        stats.cache.clear()
        stats.cache.update(self._saved_cache)

    def _run(self, current, cache_info, cache_time):
        stats.cache['disk_stat'] = {'info': cache_info, 'time': cache_time}
        fake_psutil = mock.MagicMock()
        fake_psutil.disk_io_counters = lambda perdisk=True: current
        fake_time = mock.MagicMock()
        fake_time.time.return_value = 1000000.0
        with mock.patch.object(STATS_MOD, 'psutil', fake_psutil), \
             mock.patch.object(STATS_MOD, 'time', fake_time):
            return stats().disk()

    def test_new_device_does_not_wipe_sample(self):
        prev_sda = self.io(900, 800, 9000, 8000, 90, 80, 0, 0, 0)
        cur_sda = self.io(1000, 900, 10000, 9000, 100, 90, 0, 0, 0)
        cur_nvme = self.io(5, 6, 70, 80, 1, 2, 0, 0, 0)
        cur = collections.OrderedDict([('sda', cur_sda), ('nvme0n1', cur_nvme)])

        # 缓存里只有 sda（nvme0n1 是新插入的磁盘）
        info = self._run(cur, {'sda': prev_sda}, 1000000 - 10)

        self.assertIn('sda', info)
        self.assertEqual(info['sda']['read_count'], 10)
        self.assertEqual(info['sda']['write_count'], 10)
        self.assertEqual(info['ALL']['read_count'], 10,
                         '老磁盘的增量不能被新磁盘的 KeyError 吞掉（旧实现 ALL 恒为 0）')
        self.assertEqual(info['ALL']['write_bytes'], 100,
                         'ALL 必须累计所有磁盘（旧实现整份采样退化成假零值）')
        self.assertEqual(info['nvme0n1']['read_count'], 0, '无基线的新磁盘本次速率按 0 算')

    def test_new_device_then_next_sample_recovers(self):
        # 第一次遇到新磁盘后缓存已更新，下一次采样必须给出真实增量
        prev = self.io(100, 100, 1000, 1000, 10, 10, 0, 0, 0)
        cur = self.io(120, 130, 1400, 1500, 14, 15, 0, 0, 0)
        first = self._run(collections.OrderedDict([('sda', cur)]), {'sda': prev}, 1000000 - 10)
        self.assertEqual(first['sda']['read_count'], 2)
        self.assertEqual(stats.cache['disk_stat']['info']['sda'].read_count, 120,
                         '采样后必须刷新缓存（旧实现异常路径不更新缓存 → 永久残缺）')

    def test_source_has_no_bare_cache_index(self):
        fn = _get_fn(STATS_PY, 'disk')
        bad = [ast.unparse(n) for n in ast.walk(fn)
               if isinstance(n, ast.Subscript) and ast.unparse(n.value) == 'diskio_cache']
        self.assertEqual(bad, [], '缺基线的磁盘不能直接索引缓存（KeyError 被吞 → 假零值样本）')


class TestFrontendFailHandlers(unittest.TestCase):
    """前端：7 个请求都要有 .fail()，否则 500 时遮罩永久卡死（`.fail` 缺一即红）。"""

    def setUp(self):
        self.src = _read(CONTROL_JS)
    def test_js_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过 JS 语法校验')
        proc = subprocess.run([node, '--check', CONTROL_JS], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_all_requests_have_fail_handler(self):
        self.assertGreaterEqual(self.src.count('.fail(function'), 7)

    def _fail_bodies(self):
        """按花括号配对抽出每个 .fail() 回调体，用于逐个体检（防“留个空壳 .fail”蒙混）。"""
        bodies = []
        marker = '.fail(function () {'
        start = 0
        while True:
            i = self.src.find(marker, start)
            if i < 0:
                return bodies
            j = i + len(marker)
            depth = 1
            while j < len(self.src) and depth:
                if self.src[j] == '{':
                    depth += 1
                elif self.src[j] == '}':
                    depth -= 1
                j += 1
            bodies.append(self.src[i + len(marker):j - 1])
            start = j

    def test_every_fail_body_reports_error(self):
        bodies = self._fail_bodies()
        self.assertGreaterEqual(len(bodies), 7)
        for body in bodies:
            self.assertIn('monitorFailMsg', body, '空的 .fail() 等于没有失败处理：%r' % body)

    def test_mask_requests_close_loading_in_fail(self):
        # 3 个会弹遮罩的 POST（set_control 的查询/设置/清空）必须在失败时关掉遮罩
        self.assertEqual(self.src.count('layer.close(loadT);\n    layer.msg(monitorFailMsg()'), 2)
        self.assertEqual(self.src.count('layer.close(loadT);\n      layer.msg(monitorFailMsg()'), 1)

    def test_status_response_guarded(self):
        self.assertIn('rdata = rdata || {};', self.src)

    def test_fail_message_key_exists_in_all_languages(self):
        key = '"CONNECT_ERR"'
        for lang in ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it'):
            path = os.path.join(WEB, 'static', 'language', lang, 'lan.js')
            self.assertIn(key, _read(path), '%s 缺少 public.CONNECT_ERR' % lang)


MASK_SIM_JS = r'''
// 最小 jQuery/layer 模拟：只验证「请求失败后遮罩有没有被关掉」
var __closed = [];
var __fail = null;
var __MASK = 7;
var layer = {
  msg: function (m, o) { return __MASK; },
  close: function (i) { __closed.push(i); },
  confirm: function (msg, opts, ok) { if (typeof opts === 'function') { opts(); } else if (typeof ok === 'function') { ok(); } }
};
function t(k, d) { return d || k; }
var window = { lan: null, chartInstances: {} };
var document = { getElementById: function () { return null; } };
function shim() {
  return {
    val: function () { return '30'; }, html: function () { return this; },
    prop: function () { return true; }, parent: function () { return this; },
    find: function () { return this; }, on: function () { return this; },
    removeClass: function () { return this; }, addClass: function () { return this; }
  };
}
var $ = shim;
$.post = function (url, data, cb) {
  return { fail: function (h) { __fail = h; return this; }, done: function () { return this; } };
};
$.get = $.post;
__FUNCS__
function __run(name, args, failExpected) {
  __closed = [];
  __fail = null;
  window[name].apply(null, args);
  if (typeof __fail === 'function') { __fail(); }
  return { name: name, maskClosed: __closed.indexOf(__MASK) !== -1 };
}
function __getStatusWrapper() { getStatus(); }
function __setControlWrapper() { setControl('save_day', true); }
window.getStatus = __getStatusWrapper;
window.setControl = __setControlWrapper;
console.log(JSON.stringify([
  __run('getStatus'),
  __run('setControl')
]));
'''


def _extract_js_fn(src, name):
    """从 JS 源码里按花括号配对抽出一个函数定义。"""
    marker = 'function %s(' % name
    i = src.find(marker)
    assert i >= 0, 'control.js 里找不到 %s' % name
    j = src.index('{', i)
    depth = 0
    k = j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    raise AssertionError('函数 %s 括号不配对' % name)


class TestFailedRequestClosesMask(unittest.TestCase):
    """行为级验证（node 模拟）：后端 500 时遮罩必须被关掉。

    修复前 getStatus/setControl/closeControl 都只有 success 回调，
    `layer.msg(..., {time:0})` 的遮罩会永久卡死页面。
    """

    def test_mask_closed_on_request_failure(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过遮罩行为模拟')
        src = _read(CONTROL_JS)
        funcs = '\n'.join(_extract_js_fn(src, n) for n in ('monitorFailMsg', 'getStatus', 'setControl'))
        js = MASK_SIM_JS.replace('__FUNCS__', funcs)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
            fh.write(js)
            path = fh.name
        try:
            proc = subprocess.run([node, path], capture_output=True, text=True)
        finally:
            os.unlink(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        import json as _json
        results = _json.loads(proc.stdout.strip().splitlines()[-1])
        for row in results:
            self.assertTrue(row['maskClosed'],
                            '%s 请求失败后遮罩未关闭（缺 .fail() 的旧行为）' % row['name'])


if __name__ == '__main__':
    unittest.main()
