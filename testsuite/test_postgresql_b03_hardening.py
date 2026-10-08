# coding: utf-8
"""B03 postgresql 插件加固守卫（真机夹具真跑确认的缺陷，全部在此锁死）。

真机夹具真跑（`/root/yf_probe_B03/probe.py`，old=HEAD vs new 逐条对照）确认并修复：

1. `checkSafeName/Password/Filename/Access`：`$` 在 Python 里也匹配「结尾换行之前」，
   于是 `"1.2.3.4/32\\n"` 被放行 → 换行被写进 pg_hba.conf / 拼进 shell 与 SQL。
2. `pgCmd`：`su - postgres -c "<cmd>"` 未转义反斜杠与双引号与 `$` 与反引号
   → **面板(root)命令注入**（真机实测 `x" ; touch /tmp/xxx ; echo "` 建出了 marker）。
3. `setPgPort`：端口不校验就写进 postgresql.conf 再重启（`abc`/`70000`/`0`/空/
   `5432; touch /tmp/x` 全都能落盘），接口一律回「编辑成功!」。
4. `pgSetDbStatus`/`sedConf`：遍历**全部**入参写配置（`port` 也能被改写），
   值里带 `\\n` 可注入任意配置行，值里带 `;` 可污染配置。
5. `readConfigTpl`：`file` 参数无校验 → 任意文件读取（真机实测读到 `/etc/shadow`）。
6. `getDbPort`：配置无 `port =` 行时 `re.search` 未命中 → AttributeError traceback。
7. `getPgPort`：`(.*)` 会把 `port = 5432; touch /tmp/x` 整串读出来并拼进 shell。
8. `getSocketFile`：`sock_name` 被写死成 `''` → 恒返回 `/tmp/`，pgDb() 永远连不上。
9. `deleteDbBackup`：文件不存在 → FileNotFoundError traceback；无 realpath 限定。
10. `importDbBackup`：损坏的 .gz 也回「导入成功!」（管道退出码取 psql 的，假成功）。
11. `pgBack`/`setDbBackup`：`pg_dump | gzip > f` 失败只留下一个合法空 gz（62B）→ 假成功。
12. `setDbRw`：SQL 全失败仍回「切换成功!」；`rw` 无白名单（任意值 → GRANT all）。
13. `setUserPwd`：`args['id']` 在 checkArgs 之外 → 缺参 KeyError；id 不存在 →
    `getInfo` 收到 name=None → TypeError。
14. `delDb`：id 不存在 → `len(None)` TypeError。
15. `getDbList`/`getMasterRepSlaveList`/`getSlaveSSHList`：裸 `int(page)` → ValueError；
    `args['tojs']` 缺参 → KeyError。
16. `getSlaveList`：调试 `print(res)` 把非 JSON 文本写进 stdout → 前端 JSON.parse 失败。
17. `setMasterStatus`/`setSlaveStatus`：readFile 回 False 时 `False.find` → AttributeError。
18. `pgDbStatus`：畸形配置（缺 `=`）→ IndexError；非 UTF-8 → 解析异常冒成 500。
19. `start`/`restart`：无论是否起来都回 `ok`（真机实测 status='stop' 仍回 ok）。
20. `init.d/postgresql.tpl` 的 `pg_status`：`ps aux | grep postgres` 缺 `grep -v python`
    → 面板调插件时的 python 进程被当成 PG 实例（真机实测多匹配 1 个 PID）。
21. `js/postgresql.js`：库名/用户名/备注/密码/IP 直接拼 innerHTML 与行内 onclick
    → 存储型 XSS（备注里存 `<img src=x onerror=...>` 即触发）。

断言口径（防「假绿」）：全部基于 **AST**，过滤 `if False:` 等静态死分支
（`_live_nodes` 只走可达节点），注释天然不参与；正则类断言直接把 AST 里的
正则字面量取出来真跑行为。
"""
import ast
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'postgresql', 'index.py')
TPL = os.path.join(ROOT, 'plugins', 'postgresql', 'init.d', 'postgresql.tpl')
JS = os.path.join(ROOT, 'plugins', 'postgresql', 'js', 'postgresql.js')
LANG_DIR = os.path.join(ROOT, 'plugins', 'postgresql', 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')


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
    """函数体内字面量串（**排除 docstring**：文档里会引用历史缺陷的正则）。"""
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


def _names_used(node):
    return set(n.id for n in _live_nodes(node) if isinstance(n, ast.Name))


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


class PostgresqlB03Test(unittest.TestCase):

    def setUp(self):
        self.tree = _parse(IDX)
        self.src = _read(IDX)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    # ---- 1. 四个校验器：\Z 锚定，尾随换行必须被拒 -------------------------------
    def test_01_safe_validators_reject_trailing_newline(self):
        cases = {
            'checkSafeName': ('ok', 'a.b-c_d', '中文名'),
            'checkSafePassword': ('Abc12345', 'a.b-c_d', 'p@ss#word'),
            'checkSafeFilename': ('ok.gz', 'a.b-c_d.gz'),
            'checkSafeAccess': ('127.0.0.1/32', '1.2.3.4/32'),
        }
        for fname, good in cases.items():
            pats = _match_patterns(self._fn(fname))
            self.assertTrue(pats, '%s 缺少 re.match 白名单' % fname)
            for pat in pats:
                self.assertIn('\\Z', pat,
                              '%s 的白名单必须用 \\Z 锚定（`$` 会放过尾随换行）: %r' % (fname, pat))
                rx = re.compile(pat)
                for ok in good:
                    self.assertIsNotNone(rx.match(ok), '%s 误拒合法值 %r' % (fname, ok))
                for bad in ('a\n', 'x\ny', 'ok.gz\n', '1.2.3.4/32\n'):
                    self.assertIsNone(rx.match(bad),
                                      '%s 不得放行尾随换行/多行输入 %r' % (fname, bad))
                for bad in ("x' OR '1'='1", 'x;y', 'x"y', 'x\\y', '$(id)', ''):
                    self.assertIsNone(rx.match(bad), '%s 不得放行 %r' % (fname, bad))

    # ---- 2. pgCmd：shell 双引号内必须转义 --------------------------------------
    def test_02_pg_cmd_escapes_shell_metachars(self):
        fn = self._fn('pgCmd')
        self.assertTrue(_calls(fn, 'replace'), 'pgCmd 必须对 cmd 做转义')
        consts = _string_consts(fn)
        for needle in ('\\\\', '\\"', '\\$', '\\`'):
            self.assertIn(needle, consts, 'pgCmd 必须转义 %r' % needle)
        self.assertTrue(any('su - postgres -c' in c for c in consts),
                        'pgCmd 仍应通过 su - postgres -c 执行')

    # ---- 3. setPgPort：先校验后写盘 + 如实报错 ---------------------------------
    def test_03_set_pg_port_validates_before_write(self):
        fn = self._fn('setPgPort')
        pats = _match_patterns(fn) + [p for p in _string_consts(fn) if '[0-9]' in p]
        self.assertTrue(pats, 'setPgPort 必须有端口白名单（正则或 _isPortValue）')
        if not _match_patterns(fn):
            self.assertTrue(_calls(fn, '_isPortValue'),
                            'setPgPort 必须走 _isPortValue 或内联数字白名单')
        helper = _find_func(self.tree, '_isPortValue')
        self.assertIsNotNone(helper, '缺少 _isPortValue 端口白名单')
        hp = _match_patterns(helper)
        self.assertTrue(hp and any('[0-9]' in p for p in hp),
                        '_isPortValue 必须限制为纯数字')
        self.assertTrue(_calls(fn, 'int'), 'setPgPort 必须做范围校验（int 比较）')
        writes = _calls(fn, 'writeFile')
        restarts = _calls(fn, 'restart')
        self.assertTrue(writes and restarts, 'setPgPort 必须写盘并重启')
        self.assertLess(min(_lineno(c) for c in writes), min(_lineno(c) for c in restarts),
                        'setPgPort 必须先写盘后重启')
        self.assertIn('端口不合法!', _string_consts(fn), 'setPgPort 必须对非法端口如实报错')
        self.assertTrue(any('未就绪' in c for c in _string_consts(fn)),
                        'setPgPort 必须检查 restart() 结果')

    # ---- 4. sedConf / pgSetDbStatus：键值双白名单 -------------------------------
    def test_04_sed_conf_is_whitelisted(self):
        fn = self._fn('sedConf')
        self.assertTrue(_calls(fn, '_safeConfValue'), 'sedConf 必须用 _safeConfValue 校验值')
        self.assertIn('_PG_CONF_KEYS', _names_used(fn), 'sedConf 必须用 _PG_CONF_KEYS 白名单键')
        self.assertTrue(_calls(fn, 'writeFile'), 'sedConf 必须判 writeFile 结果')

        status = self._fn('pgSetDbStatus')
        self.assertIn('配置文件写入失败!', _string_consts(status),
                      'pgSetDbStatus 写失败必须如实报错')
        self.assertFalse(_calls(status, 'items'),
                         'pgSetDbStatus 不得遍历全部入参（任意键会写进配置）')
        self.assertIn('_PG_CONF_KEYS', _names_used(status),
                      'pgSetDbStatus 必须只遍历 _PG_CONF_KEYS')
        self.assertTrue(_calls(status, 'sedConf'), 'pgSetDbStatus 必须调 sedConf')

        helper = self._fn('_safeConfValue')
        pat = _module_regex(self.tree, '_PG_CONF_VALUE_RE')
        self.assertIsNotNone(pat, '缺少 _PG_CONF_VALUE_RE 常量')
        self.assertTrue(_calls(helper, 'match'), '_safeConfValue 必须做值白名单校验')
        rx = re.compile(pat)
        for ok in ('128MB', '4MB', '0', '200', '2MB'):
            self.assertIsNotNone(rx.match(ok), '合法配置值被误拒: %r' % ok)
        for bad in ('4MB\nyf_x = 1', 'x; touch /tmp/p', '4MB\t', '', '$(id)'):
            self.assertIsNone(rx.match(bad), '非法配置值被放行: %r' % bad)

    # ---- 5. readConfigTpl：任意文件读 ------------------------------------------
    def test_05_read_config_tpl_is_path_limited(self):
        fn = self._fn('readConfigTpl')
        self.assertTrue(_calls(fn, 'realpath'), 'readConfigTpl 必须用 realpath 限定路径')
        used = _names_used(fn)
        self.assertTrue('getConf' in used or 'pgHbaConf' in used,
                        'readConfigTpl 只允许读本插件的配置文件')
        self.assertIn('配置文件路径不合法!', _string_consts(fn),
                      'readConfigTpl 必须对白名单外路径如实拒绝')

    # ---- 6/7/8. 端口与 socket 取值 --------------------------------------------
    def test_06_get_db_port_and_pg_port_are_digit_only(self):
        for fname in ('getDbPort', 'getPgPort'):
            fn = self._fn(fname)
            pats = _match_patterns(fn) + [p for p in _string_consts(fn) if 'port' in p]
            self.assertTrue(any('[0-9]' in p for p in pats),
                            '%s 必须只取数字端口（不得 (.*) 整串读出）' % fname)
            self.assertFalse(any(p.strip() == '(.*)' or '(.*)' in p for p in pats),
                             '%s 不得用 (.*) 读端口' % fname)
            self.assertTrue(_calls(fn, 'exists'), '%s 必须判配置文件存在' % fname)

    def test_07_get_socket_file_uses_real_socket_name(self):
        fn = self._fn('getSocketFile')
        consts = _string_consts(fn)
        self.assertIn('.s.PGSQL.', consts, 'getSocketFile 必须拼出 .s.PGSQL.<port>')
        self.assertFalse(any(c.strip() == '' and i < 3 for i, c in enumerate(consts[:3])),
                         'getSocketFile 不得把 sock_name 写死成空串（恒返回 /tmp/）')

    # ---- 9/10/11. 备份：任意删除 / 假成功 --------------------------------------
    def test_08_delete_db_backup_exists_and_realpath(self):
        fn = self._fn('deleteDbBackup')
        self.assertTrue(_calls(fn, 'realpath'), 'deleteDbBackup 必须用 realpath 限定目录')
        self.assertTrue(_calls(fn, 'exists'), 'deleteDbBackup 必须先判存在')
        self.assertIn('备份文件不存在!', _string_consts(fn), 'deleteDbBackup 必须如实报不存在')
        self.assertFalse(_calls(fn, 'remove') and not _calls(fn, 'exists'),
                         'deleteDbBackup 不得裸调 os.remove')

    def test_09_import_db_backup_verifies_archive(self):
        fn = self._fn('importDbBackup')
        self.assertTrue(_calls(fn, '_gzContentSize'),
                        'importDbBackup 必须验归档内容（否则损坏 .gz 也回成功）')
        self.assertTrue(_calls(fn, 'realpath'), 'importDbBackup 必须用 realpath 限定目录')
        self.assertIn('导入失败!', _string_consts(fn), 'importDbBackup 必须能报失败')

    def test_10_backup_pipeline_checks_content(self):
        helper = self._fn('_gzContentSize')
        consts = _string_consts(helper)
        self.assertTrue(any('gunzip -c' in c for c in consts), '_gzContentSize 必须解压取内容')
        self.assertTrue(any('wc -c' in c for c in consts), '_gzContentSize 必须量未压缩字节数')
        self.assertTrue(_calls(helper, 'shlexQuote'), '_gzContentSize 必须转义路径')

        dump = self._fn('_pgDumpToFile')
        self.assertTrue(_calls(dump, '_gzContentSize'),
                        '_pgDumpToFile 必须校验未压缩内容（空 gz 就是 pg_dump 失败的形态）')
        self.assertTrue(_calls(dump, 'shlexQuote'), '_pgDumpToFile 必须转义命令参数')
        for name in ('pgBack', 'setDbBackup'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, '_pgDumpToFile'),
                            '%s 必须复用 _pgDumpToFile（含失败判定）' % name)
            self.assertTrue(any('备份失败' in c for c in _string_consts(fn)) or
                            any('备份失败' in c for c in _string_consts(dump)),
                            '%s 失败路径必须如实报错' % name)

    # ---- 12/13/14. 账户与库 ----------------------------------------------------
    def test_11_set_db_rw_whitelist_and_honest_result(self):
        fn = self._fn('setDbRw')
        consts = _string_consts(fn)
        for v in ('rw', 'r', 'all'):
            self.assertIn(v, consts, 'setDbRw 的 rw 白名单缺 %r' % v)
        self.assertIn('权限类型不合法!', consts, 'setDbRw 必须拒绝白名单外的 rw')
        self.assertTrue(_calls(fn, 'isinstance'),
                        'setDbRw 必须按 execute 结果判成败（不得假成功）')
        self.assertIn('切换失败!', consts, 'setDbRw 必须能报失败')

    def test_12_set_user_pwd_requires_id_and_guards_row(self):
        fn = self._fn('setUserPwd')
        ck = _calls(fn, 'checkArgs')
        self.assertTrue(ck, 'setUserPwd 必须调 checkArgs')
        required = []
        for c in ck:
            for a in c.args:
                if isinstance(a, (ast.List, ast.Tuple)):
                    required += [e.value for e in a.elts
                                 if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        for k in ('password', 'name', 'id'):
            self.assertIn(k, required, 'setUserPwd 的 checkArgs 必须要求 %r' % k)
        self.assertTrue(_calls(fn, 'find') or _calls(fn, 'getField'),
                        'setUserPwd 必须先查库中是否存在该 id')
        self.assertTrue(_calls(fn, 'replace'), 'setUserPwd 必须对口令做字面量转义')
        self.assertIn('数据库不存在!', _string_consts(fn), 'setUserPwd 必须如实报不存在')

    def test_13_del_db_guards_missing_id(self):
        fn = self._fn('delDb')
        self.assertTrue(_calls(fn, 'escape'), 'delDb 的 pg_hba 清理必须 re.escape 库名')
        has_none_check = any(
            isinstance(n, ast.Compare) and any(isinstance(o, ast.Is) for o in n.ops)
            for n in _live_nodes(fn))
        self.assertTrue(has_none_check, 'delDb 必须判 getField 回 None（不得 len(None)）')
        self.assertIn('数据库不存在!', _string_consts(fn), 'delDb 必须如实报不存在')

    # ---- 15. 分页容错 ----------------------------------------------------------
    def test_14_pagination_is_tolerant(self):
        helper = self._fn('_parsePageArgs')
        self.assertTrue(_calls(helper, 'get'), '_parsePageArgs 必须用 .get 取参')
        self.assertTrue(_calls(helper, 'int'), '_parsePageArgs 必须 try/int 容错')
        for name in ('getDbList', 'getMasterRepSlaveList', 'getSlaveSSHList'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, '_parsePageArgs'),
                            '%s 必须走 _parsePageArgs（裸 int() 会 ValueError）' % name)
            for c in _calls(fn, 'int'):
                self.fail('%s 仍有裸 int() 转换: 行 %d' % (name, _lineno(c)))
        ssh = self._fn('getSlaveSSHList')
        self.assertTrue(any('tojs' in c for c in _string_consts(ssh)),
                        'getSlaveSSHList 必须给 tojs 兜底默认值')

    # ---- 16. stdout 洁净 -------------------------------------------------------
    def test_15_get_slave_list_prints_nothing(self):
        fn = self._fn('getSlaveList')
        self.assertFalse(_calls(fn, 'print'),
                         'getSlaveList 不得 print（非 JSON 文本会破坏面板解析）')

    # ---- 17/18. 配置读取健壮性 -------------------------------------------------
    def test_16_master_slave_status_guards_read(self):
        for name in ('setMasterStatus', 'setSlaveStatus'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, 'exists'), '%s 必须判配置文件存在' % name)
            self.assertTrue(_calls(fn, 'writeFile'), '%s 必须写盘' % name)
            self.assertIn('读取postgresql配置失败!', _string_consts(fn),
                          '%s 必须处理 readFile 回 False' % name)
            self.assertTrue(_calls(fn, 'restart'), '%s 必须重启生效' % name)

    def test_17_pg_db_status_tolerates_malformed_conf(self):
        fn = self._fn('pgDbStatus')
        self.assertTrue(_calls(fn, '_confValue'),
                        'pgDbStatus 必须用 _confValue（缺 = 的行会 IndexError）')
        for c in _calls(fn, 'split'):
            self.fail('pgDbStatus 仍有裸 split 取值: 行 %d' % _lineno(c))
        self.assertTrue(_calls(fn, 'readFile'), 'pgDbStatus 必须用 yf.readFile 容错读')
        helper = self._fn('_confValue')
        self.assertTrue(_calls(helper, 'split'), '_confValue 必须处理缺 = 的行')

    # ---- 19. start/restart 就绪判定 -------------------------------------------
    def test_18_start_and_restart_poll_readiness(self):
        for name in ('start', 'restart'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, 'status'), '%s 必须轮询 status()' % name)
            self.assertTrue(_calls(fn, 'sleep'), '%s 必须有轮询等待' % name)
            self.assertTrue(any('未就绪' in c for c in _string_consts(fn)),
                            '%s 未就绪时必须如实返回失败（不得回 ok）' % name)

    # ---- 20. init.d 模板 ------------------------------------------------------
    def test_19_initd_template_filters_python(self):
        body = _read(TPL)
        self.assertIn('pg_status()', body)
        lines = [ln for ln in body.splitlines() if 'isStart=$(' in ln]
        self.assertTrue(lines, '模板里找不到 pg_status 的进程判据行')
        for ln in lines:
            # 断言落在**同一条判据命令**上：注释/死分支里补关键字骗不过
            self.assertIn('grep -v python', ln,
                          'pg_status 的进程判据必须过滤 python: %r' % ln)
            self.assertLess(ln.index('grep -v python'), ln.index('awk'),
                            'grep -v python 必须在 awk 之前生效')

    # ---- 21. 前端转义 ---------------------------------------------------------
    def test_20_frontend_escapes_db_values(self):
        js = _read(JS)
        self.assertIn('function yfPgText(', js, '缺少 HTML 上下文转义助手')
        self.assertIn('function yfPgJsStr(', js, '缺少行内 onclick JS 字符串转义助手')
        raw_patterns = [
            "+rdata.data[i]['name']+'", "+rdata.data[i]['username']+'",
            "+rdata.data[i]['ps']+'", "+rdata.data[i]['password']+'\">***",
            "onclick=\"setDbPs(\\''+rdata.data[i]['name']",
            "onclick=\"delDb(\\''+rdata.data[i]['id']+'\\',\\''+rdata.data[i]['name']",
            "+user_list[i]['password']+'",
            "+pdata.username+",
            "+ip+'</td>",
        ]
        for pat in raw_patterns:
            self.assertNotIn(pat, js, '前端仍有未转义的库内数据拼接: %r' % pat)
        self.assertIn("$('textarea[name=\"id_rsa\"]').val(id_rsa)", js,
                      '私钥必须用 .val() 赋值，.html() 会当 HTML 解析')

    # ---- 22. 新增语言键六语齐备 ------------------------------------------------
    def test_21_new_lang_keys_present_in_all_langs(self):
        keys = ['端口不合法!', '配置文件中未找到端口配置!', '修改端口后服务未就绪:',
                '权限类型不合法!', '导入失败!', '删除失败!',
                '切换失败!', '配置文件路径不合法!', '配置文件写入失败!',
                '服务重启后未就绪:']
        base = None
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang + '.json')
            with io.open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            if base is None:
                base = set(data)
            self.assertEqual(base, set(data), '%s 的键集与 zh-CN 不一致' % lang)
            for k in keys:
                self.assertIn(k, data, '%s 缺键: %r' % (lang, k))
                self.assertTrue(str(data[k]).strip(), '%s 的 %r 译文为空' % (lang, k))


if __name__ == '__main__':
    unittest.main()
