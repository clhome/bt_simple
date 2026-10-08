# coding: utf-8
"""B04 mongodb 插件加固守卫（真机夹具真跑确认的缺陷，全部在此锁死）。

真机夹具真跑（`/root/yf_probe_B04/probe.py`，old=HEAD vs new 逐条对照）确认并修复：

1. `getArgs`：前端（YfPlugin.parseArgs）把参数序列化成 JSON 后由
   `utils/plugin.py::run()` 作为**单个** argv 传入，历史实现只按 `k:v` 切第一段
   → `tmp['"id"'] = '"1","name":...'`，于是**所有带参接口恒回「缺少必要参数」**
   （真机 HTTP 实测：set_db_ps/get_db_backup_list/del_db/set_user_pwd/... 全部不可用）。
2. `check_safe_name` 用 `$` 锚定：`'yftest\\n'` 被放行（夹具真跑 old=True / new=False）。
3. `getConfigData`：配置文件被清空时 `yaml.safe_load('')` 返回 None（不抛异常），
   调用方 `data['net']` → TypeError；纯标量 yaml 同理。
4. `saveConfig`：端口/路径/bindIp 不校验就写进 mongodb.conf 并重启，
   且从不检查 restart 结果（一律回「设置成功」）。
5. `getDbList`：`int(args['page'])` 非数字 → ValueError；`search` 直接拼进 LIKE
   → SQL 注入（夹具真跑：`yftest%' OR '1'='1` 在 old 命中全部行，new 命中 0 行）。
6. `getDbBackupListFunc`：备份目录不存在 → FileNotFoundError（getDbList 每行调一次）。
7. `deleteDbBackup`：`path`+`filename` 无校验 → **root 任意文件删除**
   （夹具真跑 old 删掉了 /tmp/yf_b04_canary 并回 status=True）；文件不存在 → traceback。
8. `importDbBackup`/`importDbExternal`：`tarfile.extractall` 无成员校验（面板 python 3.11
   无 `filter=`）→ 压缩包内 `../../x` 可写出备份目录（夹具真跑 old 逃逸成功）；
   解压目录不清理；`importDbExternal` 把单个 .bson 文件当 `--dir` 传给 mongorestore。
9. `setDbBackup`：`Popen` 后立刻回 'ok'（假成功），而 `scripts/backup.py` 因
   `os.chdir(yf.getPanelDir())` 写在 `import core.yf as yf` 之前**必然 NameError**
   （真机真跑 rc=1）→ 备份功能整体不可用却显示「成功」。
10. `delDb`：id 不存在 → `find['accept']` TypeError traceback。
11. `delDbTable`：库名/集合名零校验 → `name=admin` 可 drop 系统库集合。
12. `setUserPwd`：`args['id']` 在 checkArgs 之外 → 缺参 KeyError；id 不存在 → 报错信息里 name=None。
13. `setDbPs`：失败分支回 `returnJson(True, ...失败!)`（假成功）。
14. `setDbAccess`：角色无白名单（`select=root` 可把库用户提权成超级管理员），
    失败时异常直接冒成 500。
15. `mgOp`/`start`/`restart`：只看 stderr 是否为空 → systemctl 失败也回 'ok'
    （夹具真跑 old='ok' / new='fail: Unit mongodb.service not found.'），且无就绪轮询。
16. `replSetName`/`replClose`：配置缺 `replication` 段 → KeyError traceback。
17. `replSetNode`：`int(args['idx'])` 非数字 → ValueError；节点无 host:port 校验
    （空串/垃圾串入库）；越界 idx 静默什么都不改却回「编辑成功!」。
18. `delReplNode`：节点不存在也回「删除成功!」（假成功）。
19. `getReplConfigData`：repl.json 被写坏 → JSONDecodeError 冒成 500。
20. 读类接口（runInfo/runDocInfo/getAllRole/getDbInfo/syncGetDatabases）：服务未启动时
    直接连驱动 → traceback（夹具真跑 old=TRACEBACK / new=「未启动!」）。
21. `installPreInspectionDebainCheck`：VERSION_ID 非纯数字 → ValueError。
22. `cronAddCheck`/`tool_task.createBgTask`：`crontab.add()` 失败仍回「添加检查任务成功」。
23. `js/mongodb.js`：库名/用户名/备注/密码/副本节点直接拼 innerHTML 与行内 onclick
    → 存储型 XSS；`$.post` 缺 `.fail()` → 500 时遮罩卡死。

断言口径（防「假绿」）：AST 为主（过滤 `if False:` 等静态死分支，注释天然不参与），
可提取的函数/正则一律**取出来真跑行为**（getArgs/校验器/安全解压）。
"""
import ast
import io
import json
import os
import re
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'mongodb', 'index.py')
BACKUP_PY = os.path.join(ROOT, 'plugins', 'mongodb', 'scripts', 'backup.py')
TOOL_TASK = os.path.join(ROOT, 'plugins', 'mongodb', 'tool_task.py')
JS = os.path.join(ROOT, 'plugins', 'mongodb', 'js', 'mongodb.js')
LANG_DIR = os.path.join(ROOT, 'plugins', 'mongodb', 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

# 本次新增/复用的后端消息键（6 语言必须齐备，否则前端 translateAny 落空显示中文）
NEW_KEYS = ('参数不合法:', '操作失败:', '设置失败:', '集合名称不合法!', '节点不存在!',
            '节点格式不合法!', '副本名称不合法!', '端口不合法!', '备份文件不存在!',
            '备份文件名不合法!', '备份目录不合法!', '数据库不存在!', '数据库备份失败:',
            '权限类型不合法!', '删除失败:', '操作异常!')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
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


def _calls(node, name):
    out = []
    for n in _live_nodes(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == name:
            out.append(n)
        elif isinstance(f, ast.Attribute) and f.attr == name:
            out.append(n)
    return out


def _string_consts(node):
    """函数体内字面量串（**排除 docstring**：文档里会引用历史缺陷的正则/消息）。"""
    body = [n for n in node.body]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    out = []
    for stmt in body:
        out += [n.value for n in _live_nodes(stmt)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return out


def _lineno(node):
    return getattr(node, 'lineno', 10 ** 9)


def _match_patterns(node):
    """函数内 `re.match(<literal>, ...)` 的第一个字面量（正则源码）。"""
    pats = []
    for c in _calls(node, 'match'):
        f = c.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 're':
            if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str):
                pats.append(c.args[0].value)
    return pats


def _module_regex(tree, const_name):
    """从模块顶层取出 `const_name = re.compile(r'...')` 的正则源码串。"""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == const_name for t in node.targets):
            continue
        call = node.value
        if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant):
            return call.args[0].value
    return None


class _Log(object):
    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


class MongodbB04Test(unittest.TestCase):

    def setUp(self):
        self.src = _read(IDX)
        self.tree = _parse(IDX)
        self.js = _read(JS)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    def _exec(self, names, extra=None):
        """把真实函数体取出来在受控命名空间里执行（真跑行为，不是文本匹配）。"""
        ns = {'os': os, 're': re, 'json': json, 'tarfile': tarfile, '_log': _Log()}
        if extra:
            ns.update(extra)
        src = '\n\n'.join(ast.get_source_segment(self.src, self._fn(n)) for n in names)
        exec(compile(src, '<mongodb-extract>', 'exec'), ns)
        return ns

    # ---- 1. getArgs：JSON 单 argv 必须解析成 dict（真机 HTTP 全量失效的根因） ----
    def test_01_get_args_parses_json_single_argv(self):
        import sys
        ns = self._exec(['getArgs'], {'sys': sys})
        old = sys.argv
        try:
            sys.argv = ['index.py', 'set_db_ps', '{"id":"1","name":"x","ps":"y"}']
            got = ns['getArgs']()
            self.assertEqual(got, {'id': '1', 'name': 'x', 'ps': 'y'},
                             'getArgs 必须把单个 JSON argv 解析成 dict')
            sys.argv = ['index.py', 'f', '{}']
            self.assertEqual(ns['getArgs'](), {})
            # 兼容插件 CLI 的 `k:v` 多 argv 形式
            sys.argv = ['index.py', 'f', 'id:1', 'name:x']
            self.assertEqual(ns['getArgs'](), {'id': '1', 'name': 'x'})
            sys.argv = ['index.py', 'f', 'id:1']
            self.assertEqual(ns['getArgs'](), {'id': '1'})
            sys.argv = ['index.py', 'f']
            self.assertEqual(ns['getArgs'](), {})
        finally:
            sys.argv = old

    # ---- 2. 名字白名单：\Z 锚定（`$` 会放过尾随换行） --------------------------
    def test_02_safe_name_regex_anchored(self):
        pat = _module_regex(self.tree, '_SAFE_NAME_RE')
        self.assertIsNotNone(pat, '缺少 _SAFE_NAME_RE 常量')
        self.assertIn('\\Z', pat, '库名白名单必须用 \\Z 锚定: %r' % pat)
        rx = re.compile(pat)
        for ok in ('yftest_B04', 'a-b_c9', 'x'):
            self.assertIsNotNone(rx.match(ok), '误拒合法名 %r' % ok)
        for bad in ('yftest\n', 'a\nb', 'x;y', "x' OR '1'='1", 'a b', '', 'x.y', '中文'):
            self.assertIsNone(rx.match(bad), '不得放行 %r' % bad)
        fn = self._fn('check_safe_name')
        self.assertTrue(_calls(fn, '_SAFE_NAME_RE') or _calls(fn, 'match') or 'match' in self.src,
                        'check_safe_name 必须走白名单')
        ns = self._exec(['check_safe_name'], {'_SAFE_NAME_RE': rx})
        self.assertTrue(ns['check_safe_name']('yftest_B04'))
        self.assertFalse(ns['check_safe_name']('yftest_B04\n'))
        self.assertFalse(ns['check_safe_name'](''))

    # ---- 3. 备份文件名白名单：挡 `..` / `.` / 路径 ------------------------------
    def test_03_backup_file_regex(self):
        pat = _module_regex(self.tree, '_DB_BACKUP_FILE_RE')
        self.assertIsNotNone(pat, '缺少 _DB_BACKUP_FILE_RE 常量')
        self.assertIn('\\Z', pat, '备份文件名白名单必须用 \\Z 锚定: %r' % pat)
        rx = re.compile(pat)
        for ok in ('yftest_B04_20260101.tar.gz', 'a.gz', 'x'):
            self.assertIsNotNone(rx.match(ok), '误拒合法文件名 %r' % ok)
        for bad in ('.', '..', '.hidden', '/etc/passwd', 'a/b', 'a\\b', '', 'x\ny', 'x;y'):
            self.assertIsNone(rx.match(bad), '不得放行 %r' % bad)

    # ---- 4. getDbList：分页容错 + LIKE 参数化（SQL 注入） ----------------------
    def test_04_get_db_list_param_and_page(self):
        fn = self._fn('getDbList')
        consts = _string_consts(fn)
        self.assertTrue(any('name like ?' == c for c in consts),
                        'getDbList 的 LIKE 必须参数化（历史实现拼字符串 → 注入）')
        self.assertFalse(any("like '%" in c for c in consts),
                         'getDbList 不得再出现字符串拼接的 LIKE')
        self.assertTrue(_calls(fn, '_parsePageArgs'), 'getDbList 必须用 _parsePageArgs 容错')
        self.assertTrue(_calls(fn, 'where'), 'getDbList 仍应查询面板库')
        # 参数化实参：where(condition, param) 必须把 param 传进去
        self.assertTrue(any(len(c.args) >= 2 for c in _calls(fn, 'where')),
                        'getDbList 必须把 param 传给 where()')

    def test_05_parse_page_args_tolerant(self):
        ns = self._exec(['_parsePageArgs'])
        f = ns['_parsePageArgs']
        self.assertEqual(f({}), (1, 10))
        self.assertEqual(f({'page': 'abc', 'page_size': 'x'}), (1, 10))
        self.assertEqual(f({'page': '0', 'page_size': '0'}), (1, 10))
        self.assertEqual(f({'page': '-5', 'page_size': '-1'}), (1, 10))
        self.assertEqual(f({'page': '2', 'page_size': '9999'}), (2, 100))
        self.assertEqual(f({'page': '3', 'page_size': '20'}), (3, 20))

    # ---- 5. 备份目录：读取侧不抛异常 + 读写同源 --------------------------------
    def test_06_backup_dir_read_safe(self):
        self.assertIsNotNone(_find_func(self.tree, 'getDbBackupDir'),
                             '必须有唯一的备份目录来源函数 getDbBackupDir')
        fn = self._fn('getDbBackupDir')
        self.assertTrue(any('getBackupDir' in c for c in _string_consts(fn)) or
                        _calls(fn, 'getBackupDir'),
                        '备份目录必须来自 yf.getBackupDir()（与写入侧 scripts/backup.py 同源）')
        lf = self._fn('getDbBackupListFunc')
        self.assertTrue(_calls(lf, 'exists'), 'getDbBackupListFunc 必须先判目录存在')
        early_returns = [n for n in _live_nodes(lf) if isinstance(n, ast.Return)
                         and isinstance(n.value, ast.List) and not n.value.elts]
        self.assertTrue(early_returns, 'getDbBackupListFunc 目录缺失时必须 return []')
        il = self._fn('getDbBackupImportList')
        self.assertTrue(_calls(il, 'isfile'), '导入列表必须跳过目录项（getsize 会 IsADirectoryError）')

    # ---- 6. deleteDbBackup：realpath 白名单 + 存在性 + 如实报错 ----------------
    def test_07_delete_db_backup_whitelist(self):
        fn = self._fn('deleteDbBackup')
        self.assertTrue(_calls(fn, 'realpath'), 'deleteDbBackup 必须做 realpath 限定')
        self.assertTrue(_calls(fn, 'exists'), 'deleteDbBackup 必须先判文件存在')
        consts = _string_consts(fn)
        for m in ('备份文件名不合法!', '备份目录不合法!', '备份文件不存在!'):
            self.assertIn(m, consts, 'deleteDbBackup 必须回 %r' % m)
        rm = _calls(fn, 'remove')
        self.assertTrue(rm, '仍应删除文件')
        try_line = _lineno([n for n in _live_nodes(fn) if isinstance(n, ast.Try)][0])
        self.assertTrue(all(_lineno(c) > try_line for c in rm),
                        'os.remove 必须在 try 内（历史实现直接抛 traceback）')

    # ---- 7. delDb：id 不存在如实报错（不再 TypeError） -------------------------
    def test_08_del_db_missing_row(self):
        fn = self._fn('delDb')
        consts = _string_consts(fn)
        self.assertIn('数据库不存在!', consts, 'delDb 必须回「数据库不存在!」')
        find_line = min(_lineno(c) for c in _calls(fn, 'find'))
        guard = [n for n in _live_nodes(fn) if isinstance(n, ast.If)
                 and 'find' in ast.dump(n.test)]
        self.assertTrue(guard, 'delDb 必须对 find 结果做存在性判断')
        self.assertTrue(min(_lineno(g) for g in guard) < find_line + 3,
                        '存在性判断必须紧跟在 find 之后（先于 find[...] 取键）')
        self.assertTrue(_calls(fn, 'drop_database'))

    # ---- 8. delDbTable：库名/集合名双白名单 -----------------------------------
    def test_09_del_db_table_validates(self):
        fn = self._fn('delDbTable')
        names = [n.func.id for n in _calls(fn, 'check_safe_name')]
        self.assertEqual(len(names), 2, 'delDbTable 必须同时校验库名与集合名')
        consts = _string_consts(fn)
        self.assertIn('集合名称不合法!', consts)
        self.assertIn('安全拦截：非法数据库名！', consts)

    # ---- 9. setUserPwd：id 必填 + 记录不存在如实报错 ---------------------------
    def test_10_set_user_pwd_requires_id(self):
        fn = self._fn('setUserPwd')
        ck = _calls(fn, 'checkArgs')
        self.assertTrue(ck, 'setUserPwd 必须 checkArgs')
        args = [e.value for e in ck[0].args[1].elts]
        self.assertIn('id', args, 'id 必须纳入 checkArgs（否则缺参 KeyError traceback）')
        self.assertIn('数据库不存在!', _string_consts(fn))

    # ---- 10. setDbPs：失败必须回 False（假成功） -------------------------------
    def test_11_set_db_ps_honest(self):
        fn = self._fn('setDbPs')
        self.assertTrue(_calls(fn, 'count'), 'setDbPs 必须先确认 id 存在')
        handlers = [n for n in _live_nodes(fn) if isinstance(n, ast.ExceptHandler)]
        self.assertTrue(handlers, 'setDbPs 应有 except 分支')
        for h in handlers:
            rj = [c for c in _calls(h, 'returnJson')]
            self.assertTrue(rj, 'except 分支必须 returnJson')
            for c in rj:
                self.assertIsInstance(c.args[0], ast.Constant)
                self.assertFalse(c.args[0].value,
                                 'setDbPs 失败分支不得回 status=True（假成功）')

    # ---- 11. setDbAccess：角色白名单 -------------------------------------------
    def test_12_set_db_access_role_whitelist(self):
        fn = self._fn('setDbAccess')
        consts = _string_consts(fn)
        self.assertIn('权限类型不合法!', consts, 'setDbAccess 必须回「权限类型不合法!」')
        mod_consts = [n for n in self.tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == '_DB_ACCESS_ROLES' for t in n.targets)]
        self.assertTrue(mod_consts, '缺少 _DB_ACCESS_ROLES 白名单常量')
        roles = [e.value for e in mod_consts[0].value.elts]
        self.assertIn('readWrite', roles)
        self.assertNotIn('root', roles, 'root 不得出现在可授予角色里')
        self.assertTrue(_calls(fn, 'check_safe_name'))

    # ---- 12. saveConfig：端口/路径先校验，且看 restart 结果 --------------------
    def test_13_save_config_validates(self):
        fn = self._fn('saveConfig')
        pats = _match_patterns(fn)
        self.assertTrue(any('[0-9]' in p for p in pats), 'saveConfig 必须有端口白名单')
        ints = [n.value for n in _live_nodes(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, int)]
        self.assertIn(65535, ints, 'saveConfig 必须限制端口上界 65535')
        self.assertTrue(_calls(fn, '_validConfPath'), 'saveConfig 必须校验路径项')
        self.assertTrue(_calls(fn, '_validBindIp'), 'saveConfig 必须校验 bindIp')
        self.assertTrue(_calls(fn, 'restart'), 'saveConfig 仍应重启服务')
        self.assertTrue(any('设置失败: 服务未就绪(' in c for c in _string_consts(fn)),
                        'saveConfig 必须按 restart 结果如实报错')

    def test_14_valid_conf_path_and_bindip(self):
        ns = self._exec(['_validConfPath', '_validBindIp'])
        p = ns['_validConfPath']
        self.assertTrue(p('/www/server/mongodb/data'))
        for bad in ('', '  ', 'relative/path', '/a\nb', '/a\rb', '/a\x00b'):
            self.assertFalse(p(bad), '不得放行路径 %r' % bad)
        b = ns['_validBindIp']
        for ok in ('127.0.0.1', '0.0.0.0', '::1', '127.0.0.1,10.0.0.2'):
            self.assertTrue(b(ok), '误拒 bindIp %r' % ok)
        for bad in ('', 'abc', '1.2.3.4\nsecurity:', 'x;y', '1.2.3.4; id'):
            self.assertFalse(b(bad), '不得放行 bindIp %r' % bad)

    # ---- 13. getConfigData：非 dict 一律兜底（空文件/标量 yaml） ---------------
    def test_15_get_config_data_always_dict(self):
        fn = self._fn('getConfigData')
        self.assertTrue(_calls(fn, 'safe_load'))
        self.assertTrue(_calls(fn, 'isinstance'),
                        'getConfigData 必须用 isinstance(config, dict) 兜底（None/标量 yaml）')
        self.assertTrue(_calls(fn, '_defaultConfigData'))

    def test_16_conf_getters_tolerant(self):
        for name in ('getConfPort', 'getConfAuth', 'getConfIp'):
            fn = self._fn(name)
            bad = []
            for n in _live_nodes(fn):
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) \
                        and n.slice.value in ('net', 'security', 'bindIp', 'port', 'authorization'):
                    bad.append(n.slice.value)
            self.assertFalse(bad,
                             '%s 不得直接下标取配置段（缺段会 KeyError/TypeError）: %r' % (name, bad))

    # ---- 14. mgOp/start/restart：判退出码 + 就绪轮询 ---------------------------
    def test_17_mg_op_checks_rc(self):
        fn = self._fn('mgOp')
        self.assertTrue(_calls(fn, 'execShellRc'), 'mgOp 必须用 execShellRc 拿退出码')
        self.assertTrue(any(isinstance(n, ast.Compare) and
                            any(isinstance(o, ast.Eq) for o in n.ops) for n in _live_nodes(fn)),
                        'mgOp 必须比较 rc')
        self.assertTrue(any('fail: ' in c for c in _string_consts(fn)),
                        'mgOp 失败时必须回带原因的 fail 串（历史实现恒回 ok）')

    def test_18_start_restart_poll_ready(self):
        for name, msg in (('start', '启动后未就绪'), ('restart', '重启后未就绪')):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, 'status'), '%s 必须轮询 status()' % name)
            self.assertTrue(_calls(fn, 'sleep'), '%s 必须 sleep 等待就绪' % name)
            joined = ' '.join(_string_consts(fn))
            self.assertIn(msg, joined, '%s 未就绪时必须如实报错' % name)

    # ---- 15. 副本集：配置缺段不 KeyError、节点输入校验、假成功 ----------------
    def test_19_repl_config_no_keyerror(self):
        for name in ('replSetName', 'replClose'):
            fn = self._fn(name)
            dumps = ast.dump(fn)
            self.assertTrue(('setdefault' in dumps) or ('isinstance' in dumps) or
                            ('get' in dumps and 'replication' in dumps),
                            '%s 必须先确认 replication 段存在（历史 KeyError）' % name)
        rs = self._fn('replSetName')
        self.assertIn('副本名称不合法!', _string_consts(rs))

    def test_20_repl_set_node_validates(self):
        fn = self._fn('replSetNode')
        pats = _match_patterns(fn)
        self.assertTrue(any(':' in p and ('\\d' in p or '[0-9]' in p) for p in pats),
                        'replSetNode 必须校验 host:port 形态')
        consts = _string_consts(fn)
        self.assertIn('节点格式不合法!', consts)
        self.assertIn('节点不存在!', consts, '越界 idx 必须如实报错而不是回「编辑成功!」')
        self.assertIn('参数不合法: 节点参数必须是数字', consts)
        # idx 越界判断必须出现在「编辑成功」返回之前
        out_ok = [n for n in _live_nodes(fn) if isinstance(n, ast.Return)
                  and '编辑成功!' in ast.dump(n)]
        self.assertTrue(out_ok, '编辑成功! 分支应保留')
        self.assertTrue(min(_lineno(g) for g in
                            [n for n in _live_nodes(fn) if isinstance(n, ast.If)
                             and '节点不存在!' in ast.dump(n)]) < _lineno(out_ok[0]))

    def test_21_del_repl_node_honest(self):
        fn = self._fn('delReplNode')
        self.assertIn('节点不存在!', _string_consts(fn))
        self.assertTrue(_calls(fn, 'len'), 'delReplNode 必须比较删除前后节点数')

    def test_22_repl_config_data_tolerant(self):
        fn = self._fn('getReplConfigData')
        self.assertTrue(_calls(fn, 'loads'))
        self.assertTrue(_calls(fn, 'isinstance'), '损坏的 repl.json 必须兜底成空配置')
        try_line = _lineno([n for n in _live_nodes(fn) if isinstance(n, ast.Try)][0])
        self.assertTrue(all(_lineno(c) > try_line for c in _calls(fn, 'loads')),
                        'json.loads 必须在 try 内')

    # ---- 16. 安全解压：zip-slip / 软链 / 绝对路径（真跑行为） ------------------
    def test_23_safe_extract_rejects_escape(self):
        ns = self._exec(['_safeExtractTar'])
        f = ns['_safeExtractTar']
        tmp = tempfile.mkdtemp(prefix='b04_tar_')
        try:
            src = os.path.join(tmp, 'payload.txt')
            with io.open(src, 'w', encoding='utf-8') as fh:
                fh.write('pwn')
            dest = os.path.join(tmp, 'dest')
            os.makedirs(dest)

            # 1) 越界成员
            evil = os.path.join(tmp, 'evil.tar.gz')
            with tarfile.open(evil, 'w:gz') as tar:
                tar.add(src, arcname='../../escaped.txt')
            ok, err = f(evil, dest)
            self.assertFalse(ok, 'zip-slip 必须被拒')
            self.assertFalse(os.path.exists(os.path.join(tmp, 'escaped.txt')), '不得真的写出目录外')

            # 2) 绝对路径成员
            ab = os.path.join(tmp, 'abs.tar.gz')
            with tarfile.open(ab, 'w:gz') as tar:
                ti = tar.gettarinfo(src, arcname='ok.txt')
                ti.name = '/tmp/yf_b04_abs.txt'
                with open(src, 'rb') as fh:
                    tar.addfile(ti, fh)
            ok, err = f(ab, dest)
            self.assertFalse(ok, '绝对路径成员必须被拒')

            # 3) 软链成员
            ln = os.path.join(tmp, 'link.tar.gz')
            with tarfile.open(ln, 'w:gz') as tar:
                ti = tarfile.TarInfo('link')
                ti.type = tarfile.SYMTYPE
                ti.linkname = '/etc/passwd'
                tar.addfile(ti)
            ok, err = f(ln, dest)
            self.assertFalse(ok, '软链成员必须被拒')

            # 4) 正常包可解压
            good = os.path.join(tmp, 'good.tar.gz')
            with tarfile.open(good, 'w:gz') as tar:
                tar.add(src, arcname='zchat.bson')
            ok, err = f(good, dest)
            self.assertTrue(ok, '正常包必须能解压: %s' % err)
            self.assertTrue(os.path.exists(os.path.join(dest, 'zchat.bson')))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_24_import_uses_safe_extract(self):
        for name in ('importDbBackup', 'importDbExternal'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, '_safeExtractTar'), '%s 必须走安全解压' % name)
            dumps = ast.dump(fn)
            self.assertNotIn('extractall', dumps, '%s 不得直接 extractall' % name)
            self.assertTrue([n for n in _live_nodes(fn) if isinstance(n, ast.Try)
                             and n.finalbody], '%s 必须用 finally 清理解压目录' % name)
        ib = self._fn('importDbBackup')
        self.assertIn('备份文件不存在!', _string_consts(ib))

    def test_25_import_external_dir_is_dir(self):
        """mongorestore 的 --dir 必须是目录（历史实现传单个 .bson 文件）。"""
        fn = self._fn('importDbExternal')
        joins = [c for c in _calls(fn, 'join')]
        for c in joins:
            self.assertFalse(any(isinstance(a, ast.Name) and a.id == 'x' for a in c.args),
                             '--dir 不得拼上单个 bson 文件名')
        self.assertTrue(_calls(fn, 'getListBson'))
        self.assertTrue(any('未找到 .bson 文件' in c for c in _string_consts(fn)),
                        '包内无 .bson 时必须如实报错')

    # ---- 17. setDbBackup：判退出码 + 真解释器 --------------------------------
    def test_26_set_db_backup_checks_rc(self):
        fn = self._fn('setDbBackup')
        self.assertTrue(_calls(fn, 'Popen'))
        self.assertTrue(_calls(fn, 'communicate'))
        self.assertTrue(_calls(fn, 'returncode') or 'returncode' in ast.dump(fn),
                        'setDbBackup 必须看 returncode')
        self.assertIn('数据库备份失败:', _string_consts(fn))
        self.assertTrue('executable' in ast.dump(fn),
                        '必须用 sys.executable（历史实现写死 python3）')

    # ---- 18. scripts/backup.py：import 前不得用 yf + 判退出码 + 目录同源 -------
    def test_27_backup_script_fixed(self):
        src = _read(BACKUP_PY)
        tree = ast.parse(src)
        import_line = min(_lineno(n) for n in ast.walk(tree)
                          if isinstance(n, ast.Import) and any(a.name == 'core.yf' for a in n.names))
        yf_uses = [_lineno(n) for n in ast.walk(tree)
                   if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'yf']
        self.assertTrue(min(yf_uses) > import_line,
                        'backup.py 不得在 import core.yf 之前使用 yf（历史 NameError，备份全不可用）')
        fn = _find_func(tree, 'backupDatabase')
        self.assertTrue(_calls(fn, 'getsize') or 'getsize' in ast.dump(fn),
                        'backupDatabase 必须判产物大小/存在')
        self.assertTrue('returncode' in ast.dump(fn), 'backupDatabase 必须判 mongodump 退出码')
        self.assertIn('备份失败', ' '.join(_string_consts(fn)))
        gbl = _find_func(tree, 'getDbBackupList')
        self.assertTrue('getBackupDir' in ast.dump(gbl),
                        'backup.py 的备份列表必须与写入侧同源（getBackupDir）')

    # ---- 19. 读类接口：未启动前置检查 -----------------------------------------
    def test_28_read_funcs_require_running(self):
        for name in ('runInfo', 'runDocInfo', 'getAllRole', 'getDbInfo', 'syncGetDatabases'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, '_requireRunning'),
                            '%s 必须先判服务是否启动（历史 traceback）' % name)
        rf = self._fn('_requireRunning')
        self.assertTrue(_calls(rf, 'status'))
        self.assertIn('未启动!', _string_consts(rf))

    # ---- 20. cron 幂等 + 假成功 ----------------------------------------------
    def test_29_cron_honest(self):
        fn = self._fn('cronAddCheck')
        self.assertTrue('createBgTask' in ast.dump(fn))
        self.assertTrue([n for n in _live_nodes(fn) if isinstance(n, ast.If)],
                        'cronAddCheck 必须看 createBgTask 的返回结果')
        tt = _parse(TOOL_TASK)
        cbn = _find_func(tt, 'createBgTaskByName')
        rets = [n for n in ast.walk(cbn) if isinstance(n, ast.Return)]
        self.assertTrue(any(isinstance(r.value, ast.Constant) and r.value.value is False for r in rets),
                        'createBgTaskByName 失败必须显式 return False')
        self.assertTrue(any(isinstance(r.value, ast.Constant) and r.value.value is True for r in rets),
                        'createBgTaskByName 成功/幂等命中必须 return True')

    # ---- 21. installPreInspectionDebainCheck 容错 -----------------------------
    def test_30_pre_inspection_tolerant(self):
        fn = self._fn('installPreInspectionDebainCheck')
        try_line = _lineno([n for n in _live_nodes(fn) if isinstance(n, ast.Try)][0])
        int_calls = _calls(fn, 'int')
        self.assertTrue(int_calls, '仍应解析 VERSION_ID')
        self.assertTrue(all(_lineno(c) > try_line for c in int_calls),
                        'int(sysId) 必须在 try 内（非纯数字 VERSION_ID 会 ValueError）')

    # ---- 22. 前端：XSS 转义 + .fail() ---------------------------------------
    def test_31_frontend_escapes_and_fail(self):
        self.assertIn('function yfMgText(', self.js, '缺少 HTML 上下文转义函数')
        self.assertIn('function yfMgJsStr(', self.js, '缺少行内 JS 字符串转义函数')
        for needle in ("yfMgText(rdata.data[i]['name'])", "yfMgText(rdata.data[i]['username'])",
                       "yfMgText(rdata.data[i]['ps'])", "yfMgJsStr(rdata.data[i]['password'])",
                       "yfMgJsStr(t['host'])", "yfMgText(rdata.collection_list[i].collection_name)",
                       "yfMgText(file_list[i]['name'])"):
            self.assertIn(needle, self.js, '渲染点未转义: %s' % needle)
        # 未转义的原样拼接必须已全部消失
        for bad in ("'+rdata.data[i]['name']+", "'+rdata.data[i]['ps']+",
                    "'+t['host']+'", "'+rdata.collection_list[i].collection_name+'"):
            self.assertNotIn(bad, self.js, '仍有未转义拼接: %s' % bad)
        self.assertNotIn("'json');", self.js, '$.post 必须补 .fail()（500 时遮罩卡死）')

    def test_32_lang_keys_present(self):
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang + '.json')
            with io.open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            for k in NEW_KEYS:
                self.assertIn(k, data, '%s 缺少语言键 %r' % (lang, k))
                self.assertTrue(data[k], '%s 的键 %r 译文为空' % (lang, k))


if __name__ == '__main__':
    unittest.main()
