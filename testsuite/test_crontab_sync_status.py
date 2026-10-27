# coding: utf-8
"""P2-15：cron 任务标识白名单的「可见化」守卫。

补的是哪块洞
------------
`cron_name` 白名单（`web/utils/crontab.py` 的 `_CRON_NAME_RE` / `_cron_safe_name()`）上线后，
历史任务里 `echo` 是**原始命令**的那些（老版本 `init_cron` 恢复「其它系统任务」时把整条命令行
写进了 `echo`）会在同步时被 `getShell()` 拒绝 —— 但只写一行日志，**列表里看起来仍然正常**，
用户完全不知道任务已经停摆。

本项只做「可见化 + 文档」，**判定口径一个字没改**（`_cron_safe_name` / `_CRON_NAME_RE` 原样）：

1. `cron_name_status(echo)` —— 模块级纯函数，判定复用 `_cron_safe_name()`（单一判据），
   返回 `{'sync_ok', 'sync_reason', 'sync_reason_code'}`；
2. `getCrontabHuman()` 把这三个字段写进每个列表项（既有字段一个不少、不改名）；
3. 前端列表给被拒任务加红色「同步被拒」标签，`title` 显示原因；
4. 生命周期文档新增「升级需知：cron 任务标识白名单」一节；
5. `modifyCrond()` 在旧 `echo` 过不了白名单时生成新合规标识 —— 否则「编辑并重新保存」这条
   文档指引是假的（原来保存会直接报错失败）。

零外部依赖
----------
`web/utils/crontab.py` 顶层会拉起面板运行时依赖（`core.yf` / `thisdb` / Flask 侧），所以这里用
**AST 抽取真实源码 + stub 命名空间**执行（与 `test_crontab_a05_hardening.py` 同一套手法）：
`yf` / `thisdb` / `_t` 全部用替身，不建库、不碰系统 crontab、不需要 node。

用例分组
--------
1. `CronSyncStatusTest`      —— 列表可见化（1/2/3）与「重新保存即修复」（6）
2. `FrontendAndI18nTest`     —— 前端标记 + 六语言文案（zh-TW 无简体残留）+ 升级说明（4）
3. `SingleSourceStaticTest`  —— 判定正则只有 `_CRON_NAME_RE` 一处（5）
"""
import ast
import hashlib
import io
import json
import logging
import multiprocessing
import os
import re
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CRONTAB_PY = os.path.join(ROOT, 'web', 'utils', 'crontab.py')
CRONTAB_JS = os.path.join(ROOT, 'web', 'static', 'app', 'crontab.js')
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
LIFECYCLE_DOC = os.path.join(ROOT, '文档', '组件生命周期与安全响应政策.md')

LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

#: 被拒任务的原因码（前端/巡检脚本只认这一个字符串）
REASON_CODE = 'cron_name_invalid'

#: 合规任务与被拒任务的历史数据样本
OK_ECHO = 'abc123_x'
BAD_ECHO = 'echo hello; rm -rf /tmp/x'

#: 关键：真实 `_t()` 在语言包缺键时返回**第二个参数（默认文案）**，替身必须同口径，
#: 否则「原因里含修法指引」这条断言会被替身糊过去。
def _fake_t(key, *args):
    return args[0] if args else key


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def _func_src(name, cls=None):
    """按 AST 行号切出函数源码（注释/字符串不影响定位）。"""
    src = _read(CRONTAB_PY)
    tree = ast.parse(src)
    body = tree.body
    if cls:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                body = node.body
                break
        else:
            raise AssertionError('未找到类 %s' % cls)
    node = _func_node(name, cls)
    lines = src.splitlines()
    return '\n'.join(lines[node.lineno - 1:node.end_lineno])


def _func_node(name, cls=None):
    """按名字取函数 AST 节点（判定「代码里做了什么」时不能看注释与文档串）。"""
    src = _read(CRONTAB_PY)
    tree = ast.parse(src)
    body = tree.body
    if cls:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                body = node.body
                break
        else:
            raise AssertionError('未找到类 %s' % cls)
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('未找到函数 %s（%s）' % (name, cls or 'module'))


#: `re` 模块上的函数名：出现即说明该函数自己动了正则，而不是复用 `_cron_safe_name()`。
_RE_FUNCS = ('compile', 'match', 'search', 'sub', 'subn', 'fullmatch', 'findall', 'escape')


def _uses_regex(node):
    """函数**代码**里是否直接调了 `re.xxx()`（不把注释/文档串算进来）。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in _RE_FUNCS and \
                isinstance(sub.value, ast.Name) and sub.value.id == 're':
            return True
    return False


class _FakeYf(object):
    """`core.yf` 替身：只实现被测路径真正会调的接口。"""

    EXEC_SERVICE_TIMEOUT = 10

    @staticmethod
    def returnData(status, msg, data=None, *args):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def getDefault(data, key, default=''):
        val = data.get(key, default)
        return default if val is None else val

    @staticmethod
    def md5(value):
        return hashlib.md5(str(value).encode('utf-8')).hexdigest()

    @staticmethod
    def getServerDir():
        return os.path.join(os.sep, 'tmp', 'yf_p2_15_no_such_server_dir')

    @staticmethod
    def getPanelDir():
        return os.path.join(os.sep, 'tmp', 'yf_p2_15_no_such_panel_dir')

    @staticmethod
    def shlexQuote(value):
        import shlex
        return shlex.quote(str(value))

    @staticmethod
    def writeFileLog(msg, *args):
        return True

    @staticmethod
    def writeLog(category, msg, *args):
        return True

    @staticmethod
    def formatDate():
        return '2026-10-22 00:00:00'

    @staticmethod
    def execShell(cmd, *args, **kwargs):
        return ''


class _FakeDb(object):
    """`thisdb` 替身：只记录写库内容，不建表、不开库。"""

    def __init__(self, info=None):
        self.info = dict(info or {})
        self.updated = None
        self.updated_id = None

    def getCrond(self, cron_id):
        if not self.info:
            return None
        return dict(self.info)

    def setCrontabData(self, cron_id, data):
        self.updated = dict(data)
        self.updated_id = cron_id
        return True


def _load_namespace():
    """把 `crontab.py` 的**全部非 import 顶层语句**放进 stub 命名空间执行。

    保留全部而不是挑几个：模块顶层只有常量、纯函数与 `crontab` 类，逐个挑容易漏掉
    `cronCheck` 依赖的常量，断言就会退化成「只测了替身」。
    """
    src = _read(CRONTAB_PY)
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ns = {
        'os': os, 're': re, 'time': time, 'json': json, 'logging': logging,
        'threading': threading, 'multiprocessing': multiprocessing,
        'yf': _FakeYf, 'thisdb': _FakeDb(), '_t': _fake_t,
        '_log': logging.getLogger('crontab_p2_15_test'),
    }
    exec(compile(ast.Module(body=keep, type_ignores=[]), CRONTAB_PY, 'exec'), ns)
    return ns


def _task(echo, **over):
    """一条 `thisdb.getCrontabList()` 风格的任务行（字段与 `__field` 对齐）。"""
    row = {
        'id': 1, 'name': '测试任务', 'type': 'day', 'where1': '',
        'where_hour': '3', 'where_minute': '30', 'echo': echo, 'status': 1,
        'save': '', 'backup_to': 'localhost', 'stype': 'toShell', 'sname': '',
        'sbody': 'echo hi', 'url_address': '', 'attr': '', 'day_type': 0,
        'min_start_en': 0, 'min_start_h': 0, 'min_start_m': 0,
        'min_end_en': 0, 'min_end_h': 23, 'min_end_m': 59,
        'last_run_time': '2026-10-20 03:30:00', 'add_time': '2026-09-01 00:00:00',
        'update_time': '2026-10-20 03:30:00',
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------
# 1) 列表可见化
# --------------------------------------------------------------------------
class CronSyncStatusTest(unittest.TestCase):
    """被拒任务必须在列表里自报家门，合规任务不被误伤。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_namespace()
        cls.obj = cls.ns['crontab']()
        cls.status = staticmethod(cls.ns['cron_name_status'])

    def human(self, rows):
        return self.obj.getCrontabHuman(rows)

    # ---- 用例 1：合规 / 历史非法各一条 ----
    def test_01_list_exposes_rejected_and_ok(self):
        rows = self.human([_task(OK_ECHO, id=11, name='合规任务'),
                           _task(BAD_ECHO, id=12, name='历史非法任务')])
        self.assertEqual(len(rows), 2)
        ok_item, bad_item = rows[0], rows[1]

        self.assertIs(ok_item['sync_ok'], True, '合规任务 sync_ok 必须为 True')
        self.assertEqual(ok_item['sync_reason'], '', '合规任务不含原因文案（空串口径）')
        self.assertEqual(ok_item['sync_reason_code'], '', '合规任务不含原因码（空串口径）')

        self.assertIs(bad_item['sync_ok'], False, '历史非法任务必须标成不可同步')
        self.assertEqual(bad_item['sync_reason_code'], REASON_CODE)
        self.assertTrue(bad_item['sync_reason'], '被拒任务必须给非空原因')
        self.assertIn('重新保存', bad_item['sync_reason'],
                      '原因必须包含修法指引（编辑并重新保存）')

    # ---- 用例 2：判据单一来源 ----
    def test_02_single_source_of_truth(self):
        """判定结果必须与 `_cron_safe_name(echo)` 逐条一致（同一输入两条路径同结论）。"""
        samples = [
            OK_ECHO, 'a', 'A-z_0.9', 'a' * 64,              # 合规
            BAD_ECHO, '', '   ', None, 'a' * 65, '.', '..',  # 非法
            ' lead', '/abs/path', 'a/b', 'a\nb', '中文任务名',
            'echo a;b', 'x > /tmp/y', 'a b',
        ]
        for echo in samples:
            expect = bool(self.ns['_cron_safe_name'](echo))
            got = self.status(echo)['sync_ok']
            self.assertIs(got, expect,
                          '判定与 _cron_safe_name 不一致：echo=%r 得到 sync_ok=%r' % (echo, got))

        # 列表路径与纯函数路径对同一批输入也必须同结论
        rows = self.human([_task(e, id=i) for i, e in enumerate(samples)])
        for echo, item in zip(samples, rows):
            self.assertIs(item['sync_ok'], self.status(echo)['sync_ok'],
                          '列表与判定函数结论不一致：echo=%r' % (echo,))

    # ---- 用例 3：既有字段一个不少、不改名 ----
    def test_03_keeps_existing_fields(self):
        rows = self.human([_task(OK_ECHO, id=11, name='合规任务'),
                           _task(BAD_ECHO, id=12, name='历史非法任务')])
        # 前端在用的字段（见 web/static/app/crontab.js 的 getCronData）
        for key in ('id', 'name', 'echo', 'type', 'type_raw', 'cycle', 'status',
                    'save', 'stype', 'backup_to', 'day_type', 'day_type_h',
                    'last_run_time'):
            for item in rows:
                self.assertIn(key, item, '既有字段 %s 被弄丢了（id=%s）' % (key, item['id']))
        self.assertEqual([i['id'] for i in rows], [11, 12])
        self.assertEqual(rows[0]['echo'], OK_ECHO)
        self.assertEqual(rows[1]['echo'], BAD_ECHO, 'echo 原值必须保留（前端/日志按它定位）')
        self.assertEqual(rows[1]['type_raw'], 'day', 'type_raw 必须保留原始 type')
        self.assertEqual(rows[1]['name'], '历史非法任务')

    # ---- 用例 6：重新保存即生成合规标识（文档与提示文案都承诺了这一点） ----
    def test_06_resave_regenerates_compliant_name(self):
        data = {
            'name': '历史非法任务', 'type': 'day', 'week': '', 'where1': '',
            'hour': '3', 'minute': '30', 'save': '', 'backup_to': 'localhost',
            'stype': 'toShell', 'sname': '', 'sbody': 'echo hi', 'url_address': '',
            'attr': '', 'day_type': '0', 'min_start_en': '0', 'min_start_h': '0',
            'min_start_m': '0', 'min_end_en': '0', 'min_end_h': '23', 'min_end_m': '59',
        }

        # (a) 旧 echo 非法 → 保存时换新标识
        db = _FakeDb(_task(BAD_ECHO, id=7))
        self.ns['thisdb'].__dict__.update(db.__dict__)
        self.ns['thisdb'].getCrond = db.getCrond
        self.ns['thisdb'].setCrontabData = db.setCrontabData
        obj = self.ns['crontab']()
        obj.removeForCrond = lambda echo: True
        obj.syncToCrond = lambda cron_id: True
        res = obj.modifyCrond(7, dict(data))
        self.assertTrue(res['status'], '保存应当成功：%r' % (res,))
        new_echo = (db.updated or {}).get('echo')
        self.assertIsNotNone(new_echo, '过不了白名单的旧标识必须在保存时被替换')
        self.assertNotEqual(new_echo, BAD_ECHO)
        self.assertTrue(self.ns['_cron_safe_name'](new_echo),
                        '替换后的标识必须过白名单：%r' % (new_echo,))

        # (b) 旧 echo 合规 → 不能乱改（否则每次保存都换脚本名，日志/系统 crontab 全断）
        db2 = _FakeDb(_task(OK_ECHO, id=8))
        self.ns['thisdb'].getCrond = db2.getCrond
        self.ns['thisdb'].setCrontabData = db2.setCrontabData
        obj2 = self.ns['crontab']()
        obj2.removeForCrond = lambda echo: True
        obj2.syncToCrond = lambda cron_id: True
        res2 = obj2.modifyCrond(8, dict(data))
        self.assertTrue(res2['status'], '合规任务保存应当成功：%r' % (res2,))
        self.assertNotIn('echo', db2.updated or {},
                         '合规标识不许在保存时被改写')


# --------------------------------------------------------------------------
# 4) 前端标记 + 文案 + 升级说明
# --------------------------------------------------------------------------
#: zh-TW 里出现即说明混进了简体（取本次新增文案里可能踩到的简体字）
SIMPLIFIED_ONLY = '务标识仅许长时会编辑储产规则'


class FrontendAndI18nTest(unittest.TestCase):
    """前端要看得到、六语言都要有文案、升级说明要写清。"""

    def _lan_value(self, lang, key):
        src = _read(os.path.join(LANG_DIR, lang, 'lan.js'))
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key), src)
        self.assertIsNotNone(m, '%s/lan.js 缺少键 %s' % (lang, key))
        return m.group(1)

    def test_04a_language_keys_in_six_langs(self):
        for lang in LANGS:
            for key in ('cron_sync_rejected', 'cron_sync_rejected_tip'):
                val = self._lan_value(lang, key)
                self.assertTrue(val.strip(), '%s/lan.js 的 %s 是空值' % (lang, key))

    def test_04b_zh_tw_has_no_simplified_residue(self):
        for key in ('cron_sync_rejected', 'cron_sync_rejected_tip'):
            val = self._lan_value('zh-TW', key)
            leaked = [ch for ch in SIMPLIFIED_ONLY if ch in val]
            self.assertEqual(leaked, [], 'zh-TW 的 %s 混进了简体字 %r：%r'
                             % (key, leaked, val))
            self.assertTrue(re.search(r'[\u4e00-\u9fff]', val),
                            'zh-TW 的 %s 应当是繁体文案，不该是英文占位' % key)

    def test_04c_backend_reason_comes_from_language_pack(self):
        """后端原因文案必须走语言包键（`_t`），且 .json 载体已派生（否则外语界面漏翻）。"""
        src = _func_src('cron_name_status')
        self.assertIn("'crontab.cron_sync_rejected_tip'", src,
                      '原因文案必须用语言包键（crontab.cron_sync_rejected_tip）')
        for lang in LANGS:
            carrier = os.path.join(LANG_DIR, lang, 'template.crontab.json')
            self.assertTrue(os.path.isfile(carrier), '缺少派生的 %s' % carrier)
            data = json.loads(_read(carrier))
            sec = data.get('crontab') or {}
            for key in ('cron_sync_rejected', 'cron_sync_rejected_tip'):
                self.assertIn(key, sec,
                              '%s 的 template.crontab.json 没派生出 %s' % (lang, key))

    def test_04d_frontend_marks_rejected_tasks(self):
        src = _read(CRONTAB_JS)
        self.assertIn("rdata.data[i]['sync_ok'] === false", src,
                      '列表必须按 sync_ok 给被拒任务加标记')
        self.assertIn("cronEsc(rdata.data[i]['sync_reason'] || '')", src,
                      '标记的 title 必须显示后端给的原因')
        self.assertIn("t('crontab.cron_sync_rejected'", src,
                      '标记文案必须走 i18n 键')
        self.assertIn('cron-sync-rejected', src, '缺少可定位的标记 class')
        # 标记必须挂在任务名后面（列表可见位置的第二列），不能只塞进 title
        self.assertRegex(src, r"cronEsc\(row_name\) \+ sync_mark")

    def test_04e_upgrade_note_in_doc(self):
        doc = _read(LIFECYCLE_DOC)
        self.assertIn('升级需知：cron 任务标识白名单', doc, '文档缺少升级需知小节')
        self.assertIn('白名单', doc)
        low = doc.lower()
        for needle in ('cron', 'echo', '编辑', '重新保存', 'sync_ok', 'cron_name_invalid'):
            self.assertIn(needle, low if needle == 'cron' else doc,
                          '升级说明缺少要素：%r' % needle)


# --------------------------------------------------------------------------
# 5) 判定正则只有一处
# --------------------------------------------------------------------------
class SingleSourceStaticTest(unittest.TestCase):
    """`_CRON_NAME_RE` 是唯一判据：不许在别处再写一套（否则列表与同步必然漂移）。"""

    def test_05a_only_one_identifier_regex(self):
        src = _read(CRONTAB_PY)
        tree = ast.parse(src)
        # 模块级 `XXX = re.compile('...')` 里，声明「任务标识字符集」的只能有一个
        # （`_PLUGIN_DIR_NAME_RE` 是插件目录名白名单，字符集是 A-Za-z0-9_\-，不含 `.`）
        patterns = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'compile' and call.args):
                continue
            arg = call.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    patterns[tgt.id] = arg.value
        ident_like = sorted(k for k, v in patterns.items() if 'A-Za-z0-9_.-' in v)
        self.assertEqual(ident_like, ['_CRON_NAME_RE'],
                         '任务标识白名单正则必须只有 _CRON_NAME_RE 一处，实测：%r'
                         % (ident_like,))
        # 代码里引用 `_CRON_NAME_RE` 的地方只能有 `_cron_safe_name()` 一处
        # （别处要用白名单只能调它，不能拿正则常量自己再判一次）
        users = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            ids = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            if '_CRON_NAME_RE' in ids:
                users.append(node.name)
        self.assertEqual(sorted(users), ['_cron_safe_name'],
                         '`_CRON_NAME_RE` 只允许被 _cron_safe_name() 使用，实测：%r' % (users,))

    def test_05b_status_function_reuses_it(self):
        node = _func_node('cron_name_status')
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        self.assertIn('_cron_safe_name', names, '判定必须复用 _cron_safe_name()')
        self.assertNotIn('_CRON_NAME_RE', names,
                         '判定函数不该直接碰正则常量（应经 _cron_safe_name()）')
        self.assertFalse(_uses_regex(node), '判定函数不许自己动正则')

    def test_05c_sync_path_shares_the_judgement(self):
        shell = _func_node('getShell', 'crontab')
        self.assertIn('_cron_safe_name',
                      {n.id for n in ast.walk(shell) if isinstance(n, ast.Name)},
                      '同步路径必须用同一判据')
        self.assertFalse(_uses_regex(shell), '同步路径不许另写正则')
        human = _func_node('getCrontabHuman', 'crontab')
        human_names = {n.id for n in ast.walk(human) if isinstance(n, ast.Name)}
        self.assertIn('cron_name_status', human_names, '列表必须用同一个判定函数')
        self.assertNotIn('_CRON_NAME_RE', human_names, '列表不许自己匹配正则')


if __name__ == '__main__':
    unittest.main()
