# coding: utf-8
"""P2-4：数据库口令「静态加密」守卫（明文落库治理）。

## 覆盖的问题

历史实现把 MySQL/MariaDB root 口令**明文**写进
`<server>/<mod>/<mod>.db` 的 `config.mysql_root`（新建库用户口令同样明文进
`databases.password`），`data/default.pl` 还是 0644 的明文快照。任何读得到这些
文件的进程 / 备份 / 磁盘快照都能直接拿到数据库超级用户口令。

本用例钉住四件事：

1. **往返**：`web/core/db_pwd.py` 的加解密必须逐字符还原（含引号、`$()`、中文、空格）。
2. **向后兼容**：没有 `yfenc:` 标记的历史明文必须原样返回（老数据不用迁移）。
3. **fail-closed**：密文解不开时**绝不能把密文当口令用**，且必须留日志。
4. **读写点清零（静态）**：mysql / mariadb 插件里 `save('mysql_root', ...)` 的写入值
   必须是 `encrypt_pwd(...)`；`getField('mysql_root')` 的读取值必须经过解密；
   `deploy.sh` 写 `data/default.pl` 之后必须 `chmod 600`；`data_query` 的口令候选探测
   必须解密（否则它会拿密文去连库，功能静默坏掉）。

判定口径：行为用例真调 `encrypt_pwd`/`decrypt_pwd`；静态用例走 AST（不靠正则猜）。
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')

if WEB not in sys.path:
    sys.path.insert(0, WEB)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 进程级隔离（面板/服务目录重定向到临时区）必须早于会打开面板库的模块导入
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('db_password_at_rest')

import core.db_pwd as db_pwd  # noqa: E402

MYSQL_PY = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
MARIADB_PY = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')
COMMON_DB_PY = os.path.join(ROOT, 'plugins', 'data_query', 'common_db.py')
SQL_MYSQL_PY = os.path.join(ROOT, 'plugins', 'data_query', 'sql_mysql.py')
DEPLOY_SH = os.path.join(ROOT, 'deploy.sh')

#: 判定「解密」函数名：`decrypt_pwd` / `db_pwd.decrypt_pwd` / `_decUserPwd` / `_decUserRows` …
_DECRYPT_NAMES = ('decrypt_pwd', 'decrypt_pwd_any', 'decrypt_pwd_strict',
                  '_decRootPwd', '_decUserPwd', '_decUserRows', '_decPwd')
#: 判定「加密」函数名
_ENCRYPT_NAMES = ('encrypt_pwd', '_encRootPwd', '_encUserPwd', '_encPwd')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _callee_name(node):
    """取调用表达式的函数名（`a.b.c(x)` -> 'c'，`f(x)` -> 'f'）。"""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ''


def _call_name_in(node, names):
    """node 子树里是否出现了名字在 names 里的调用。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _callee_name(sub) in names:
            return True
    return False


def _parents(tree):
    """子节点 -> 父节点 映射（AST 没有 parent 指针）。"""
    out = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            out[child] = parent
    return out


def _enclosing_func(tree, node):
    parents = _parents(tree)
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
    return None


def _find_calls(tree, attr):
    """所有 `xxx.<attr>(...)` 调用。"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr:
            out.append(node)
    return out


def _encrypted_var_names(func):
    """函数内「由 encrypt_pwd/_encUserPwd 等赋值」的局部变量名集合。

    AST 判定「写入值已加密」的两种合法写法：
      (a) 直接 `save(..., (db_pwd.encrypt_pwd(scope, pwd),))`；
      (b) 先 `stored = _encUserPwd(pwd)` 再 `add(..., (..., stored, ...))`
          —— 变量名来自加密调用（本仓 addDb 用这种写法，因为既有用例对
          `psdb.add(...)` 的文本形态有断言，嵌套括号会破坏它）。
    """
    names = set()
    if func is None:
        return names
    for sub in ast.walk(func):
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
            if _callee_name(sub.value) in _ENCRYPT_NAMES:
                for tgt in sub.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
    return names


def _first_arg_is_const(node, value):
    return (len(node.args) >= 1 and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == value)


class TestDbPwdRoundTrip(unittest.TestCase):
    """1. 往返：加密后再解密必须逐字符等于原文。"""

    def test_01_round_trip_plain_ascii(self):
        raw = 'p@ss$()"' + "'"
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, raw)
        self.assertTrue(enc.startswith(db_pwd.MARKER), '加密结果必须带标记 %r' % enc)
        self.assertNotIn(raw, enc, '密文里不得残留明文口令')
        self.assertEqual(raw, db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, enc),
                         '解密必须逐字符还原（含引号 / $()）')

    def test_02_round_trip_chinese_and_spaces(self):
        raw = '  中文 口令 with 空格 '
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, raw)
        self.assertTrue(enc.startswith(db_pwd.MARKER))
        out = db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, enc)
        self.assertEqual(raw, out, '中文与空格必须逐字符还原')
        self.assertEqual(raw.encode('utf-8'), out.encode('utf-8'), '字节级也必须一致')

    def test_03_round_trip_mariadb_scope(self):
        raw = 'maria#pwd'
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MARIADB_ROOT, raw)
        self.assertTrue(enc.startswith(db_pwd.MARKER))
        self.assertEqual(raw, db_pwd.decrypt_pwd(db_pwd.SCOPE_MARIADB_ROOT, enc))

    def test_04_cross_scope_must_not_decrypt(self):
        """两个命名空间必须互不相通（否则 mysql 能解 mariadb 的口令）。"""
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'cross_scope_pwd')
        self.assertIsNone(db_pwd.decrypt_pwd(db_pwd.SCOPE_MARIADB_ROOT, enc),
                          '跨命名空间解密必须失败（fail-closed）')

    def test_05_encrypt_is_idempotent(self):
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'idem_pwd')
        self.assertEqual(enc, db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, enc),
                         '把已加密的值再加密一次必须原样返回（不能双重加密）')

    def test_06_scope_constants_are_fixed(self):
        self.assertEqual('mysql_root', db_pwd.SCOPE_MYSQL_ROOT)
        self.assertEqual('mariadb_root', db_pwd.SCOPE_MARIADB_ROOT)
        self.assertEqual('yfenc:', db_pwd.MARKER)


class TestDbPwdBackwardCompat(unittest.TestCase):
    """2. 向后兼容：历史明文（无标记）原样返回，无需迁移。"""

    def test_07_legacy_plaintext_untouched(self):
        self.assertEqual('plain123', db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'plain123'))
        self.assertEqual('root_pass_666',
                         db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'root_pass_666'))

    def test_08_none_and_empty_untouched(self):
        self.assertIsNone(db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, None))
        self.assertEqual('', db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, ''))
        self.assertIsNone(db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, None))
        self.assertEqual('', db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, ''),
                         '空口令不加密（否则「没有口令」会变成「有密文」）')

    def test_09_any_scope_passes_legacy_through(self):
        self.assertEqual('unit_test_root_pwd', db_pwd.decrypt_pwd_any('unit_test_root_pwd'))

    def test_10_any_scope_decrypts_known_namespaces(self):
        for scope in (db_pwd.SCOPE_MYSQL_ROOT, db_pwd.SCOPE_MARIADB_ROOT):
            enc = db_pwd.encrypt_pwd(scope, 'any_scope_pwd')
            self.assertEqual('any_scope_pwd', db_pwd.decrypt_pwd_any(enc),
                             '跨插件探测必须能解开任一已知命名空间的密文')


class TestDbPwdFailClosed(unittest.TestCase):
    """3. fail-closed：密文解不开时不得返回「看起来像口令」的东西，且要留日志。"""

    def setUp(self):
        self.logs = []
        db_pwd.set_log_writer(self.logs.append)

    def tearDown(self):
        db_pwd.set_log_writer(None)

    def test_11_garbage_token_is_none_not_ciphertext(self):
        out = db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'yfenc:garbage')
        self.assertIsNone(out, '解不开的密文必须 fail-closed 返回 None，实际 %r' % (out,))
        self.assertNotEqual('garbage', out, '绝不能把标记后的内容当口令返回')

    def test_12_garbage_token_logs(self):
        db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'yfenc:garbage')
        self.assertTrue(self.logs, 'fail-closed 必须留下日志（否则现场无从定位）')
        self.assertTrue(any('db_pwd' in str(m) for m in self.logs), self.logs)

    def test_13_strict_raises_named_exception(self):
        with self.assertRaises(db_pwd.PwdCryptError):
            db_pwd.decrypt_pwd_strict(db_pwd.SCOPE_MYSQL_ROOT, 'yfenc:garbage')

    def test_14_strict_passes_legacy_plaintext(self):
        self.assertEqual('plain123',
                         db_pwd.decrypt_pwd_strict(db_pwd.SCOPE_MYSQL_ROOT, 'plain123'))

    def test_15_any_scope_garbage_is_none(self):
        self.assertIsNone(db_pwd.decrypt_pwd_any('yfenc:garbage'))

    def test_16_truncated_real_token_is_none(self):
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, 'truncate_me')
        broken = enc[:len(enc) // 2]
        self.assertIsNone(db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, broken),
                          '被截断的密文也必须 fail-closed')


class TestMysqlRootWritePointsStatic(unittest.TestCase):
    """4. 写点清零：`save('mysql_root', ...)` 的写入值必须是 encrypt_pwd(...)。"""

    def _check(self, path):
        src = _read(path)
        tree = ast.parse(src)
        saves = [c for c in _find_calls(tree, 'save') if _first_arg_is_const(c, 'mysql_root')]
        self.assertTrue(saves, '%s 里扫不到 save(\'mysql_root\', ...) 调用，守卫失效'
                        % os.path.basename(path))
        for node in saves:
            self.assertGreaterEqual(len(node.args), 2, 'save 缺值参数')
            value = node.args[1]
            self.assertIsInstance(value, (ast.Tuple, ast.List),
                                  'save(\'mysql_root\', ...) 的值应是元组')
            first = value.elts[0]
            # 允许两种写法：(a) 直接 encrypt_pwd(...)；(b) 先赋给「已加密变量」再传入。
            # 本仓用的是 (a)：值元组的第一个元素就是 db_pwd.encrypt_pwd(...) 调用。
            ok = isinstance(first, ast.Call) and _callee_name(first) in _ENCRYPT_NAMES
            self.assertTrue(ok,
                            '%s:%d save(\'mysql_root\') 的写入值不是 encrypt_pwd(...) 调用: %s'
                            % (os.path.basename(path), node.lineno, ast.dump(first)[:120]))
            # 加密调用的第二个实参必须就是那个口令变量（不是常量、不是别的字段）
            self.assertGreaterEqual(len(first.args), 2,
                                    '%s:%d encrypt_pwd 必须显式传 (scope, 口令)'
                                    % (os.path.basename(path), node.lineno))
        return len(saves)

    def test_17_mysql_root_write_is_encrypted(self):
        self.assertEqual(1, self._check(MYSQL_PY),
                         'mysql 的 mysql_root 写点应收敛到唯一的 _saveRootPwd 里')

    def test_18_mariadb_root_write_is_encrypted(self):
        self.assertEqual(1, self._check(MARIADB_PY),
                         'mariadb 的 mysql_root 写点应收敛到唯一的 _saveRootPwd 里')

    def test_19_no_plaintext_save_left(self):
        """文本兜底：历史明文写法一条都不许留。"""
        for path in (MYSQL_PY, MARIADB_PY):
            src = _read(path)
            for bad in ("save('mysql_root', (pwd,))", "save('mysql_root', (password,))",
                        'save("mysql_root", (pwd,))', 'save("mysql_root", (password,))'):
                self.assertNotIn(bad, src, '%s 仍有明文写点: %s'
                                 % (os.path.basename(path), bad))

    def test_20_mariadb_uses_its_own_scope(self):
        """mariadb 不许复用 mysql 的命名空间（否则两插件互相解不开）。"""
        src = _read(MARIADB_PY)
        self.assertIn('SCOPE_MARIADB_ROOT', src, 'mariadb 插件必须用自己的加密命名空间')
        self.assertIn('_PWD_SCOPE = db_pwd.SCOPE_MARIADB_ROOT', src)

    def test_21_dbuser_password_write_is_encrypted(self):
        """新建库用户 / 改库用户口令的写入值也要加密。

        豁免：`addMasterRepSlaveUser` / `updateMasterRepSlaveUser` 写的是
        `master_replication_user`（主从复制账户）表，属**已知遗留**（本轮只治理
        root 口令与 databases 库用户口令，见报告「遗留说明」）。显式列成白名单，
        新增的明文写入点仍会变红。
        """
        legacy_plaintext = {'addMasterRepSlaveUser', 'updateMasterRepSlaveUser'}
        for path in (MYSQL_PY, MARIADB_PY):
            src = _read(path)
            tree = ast.parse(src)
            checked = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                attr = node.func.attr
                if attr not in ('add', 'setField', 'save') or len(node.args) < 2:
                    continue
                keys = node.args[0]
                if not (isinstance(keys, ast.Constant) and isinstance(keys.value, str)):
                    continue
                cols = [c.strip() for c in keys.value.split(',')]
                if 'password' not in cols:
                    continue
                if attr == 'add':
                    value = node.args[1]
                    if not isinstance(value, (ast.Tuple, ast.List)):
                        continue
                    idx = cols.index('password')
                    if len(value.elts) <= idx:
                        continue
                    elt = value.elts[idx]
                    if isinstance(elt, ast.Constant) and elt.value == '':
                        continue  # 从服务器同步来的空口令，不加密
                elif attr == 'save':
                    value = node.args[1]
                    if not isinstance(value, (ast.Tuple, ast.List)):
                        continue
                    elt = value.elts[0]
                else:
                    elt = node.args[1]

                func = _enclosing_func(tree, node)
                fname = func.name if func else '<module>'
                if fname in legacy_plaintext:
                    continue
                enc_vars = _encrypted_var_names(func)
                ok = ((isinstance(elt, ast.Call) and _callee_name(elt) in _ENCRYPT_NAMES)
                      or (isinstance(elt, ast.Name) and elt.id in enc_vars))
                self.assertTrue(ok,
                                '%s:%d %s::password 列未加密: %s'
                                % (os.path.basename(path), node.lineno, fname, ast.dump(elt)[:100]))
                checked += 1
            self.assertGreaterEqual(checked, 1,
                                    '%s 未扫到任何「带 password 列的写入」，守卫失效'
                                    % os.path.basename(path))


class TestMysqlRootReadPointsStatic(unittest.TestCase):
    """5. 读点清零：`getField('mysql_root')` 的返回值必须经过解密。"""

    def _check(self, path):
        src = _read(path)
        tree = ast.parse(src)
        reads = [c for c in _find_calls(tree, 'getField') if _first_arg_is_const(c, 'mysql_root')]
        self.assertTrue(reads, '%s 里扫不到 getField(\'mysql_root\')，守卫失效'
                        % os.path.basename(path))
        for node in reads:
            func = _enclosing_func(tree, node)
            self.assertIsNotNone(func, 'getField(\'mysql_root\') 不在任何函数内？')
            body = ast.get_source_segment(src, func) or ''
            self.assertTrue(any(n in body for n in _DECRYPT_NAMES),
                            '%s::%s 读 mysql_root 却没有解密调用（读点必须过 decrypt_pwd）'
                            % (os.path.basename(path), func.name))
        return reads

    def test_22_mysql_root_read_is_decrypted(self):
        self._check(MYSQL_PY)
        tree = ast.parse(_read(MYSQL_PY))
        reads = [c for c in _find_calls(tree, 'getField') if _first_arg_is_const(c, 'mysql_root')]
        self.assertEqual(1, len(reads),
                         'mysql 的 mysql_root 读点应收敛到唯一的 _storedRootPwd()（当前 %d 处）'
                         % len(reads))
        self.assertEqual('_storedRootPwd', _enclosing_func(tree, reads[0]).name)

    def test_23_mariadb_root_read_is_decrypted(self):
        self._check(MARIADB_PY)
        tree = ast.parse(_read(MARIADB_PY))
        reads = [c for c in _find_calls(tree, 'getField') if _first_arg_is_const(c, 'mysql_root')]
        self.assertEqual(1, len(reads),
                         'mariadb 的 mysql_root 读点应收敛到唯一的 _storedRootPwd()（当前 %d 处）'
                         % len(reads))
        self.assertEqual('_storedRootPwd', _enclosing_func(tree, reads[0]).name)

    def test_24_read_funnel_calls_decrypt(self):
        """唯一读点 `_storedRootPwd` 的消费方 `getRootPwd` 必须解密且 fail-closed 兜底。"""
        for path in (MYSQL_PY, MARIADB_PY):
            src = _read(path)
            fn = None
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef) and node.name == 'getRootPwd':
                    fn = node
                    break
            self.assertIsNotNone(fn, '%s 缺 getRootPwd()：读点没有统一入口'
                                 % os.path.basename(path))
            body = ast.get_source_segment(src, fn) or ''
            self.assertIn('decrypt_pwd', body, '%s::getRootPwd 未调用 decrypt_pwd'
                          % os.path.basename(path))
            self.assertIn('is None', body, '%s::getRootPwd 必须对「解不开」做 None 兜底'
                          % os.path.basename(path))


class TestDeployShDefaultPlPermissions(unittest.TestCase):
    """6. deploy.sh：写 data/default.pl 之后必须 chmod 600（且失败要 WARN）。"""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(DEPLOY_SH)

    def test_25_no_raw_write_without_chmod(self):
        raw_writes = [ln for ln in self.src.splitlines()
                      if '> ${PANEL_DIR}/data/default.pl' in ln
                      and not ln.strip().startswith('#')]
        self.assertEqual([], raw_writes,
                         'deploy.sh 仍有绕过 write_default_pl 的裸写: %r' % raw_writes)

    def test_26_writer_sets_600(self):
        self.assertIn('write_default_pl()', self.src, 'deploy.sh 缺统一写入口 write_default_pl()')
        start = self.src.index('write_default_pl() {')
        body = self.src[start:self.src.index('\n}', start)]
        self.assertIn('chmod 600', body, 'write_default_pl 必须 chmod 600')
        self.assertIn('log_warn', body, 'chmod 失败必须明确 WARN，不能静默留 0644')
        # chmod 那一行不许用 `|| true` 把失败吞掉（那是“看起来加固了”的假加固）
        chmod_lines = [ln for ln in body.splitlines()
                       if 'chmod 600' in ln and 'log_' not in ln]
        self.assertTrue(chmod_lines, 'write_default_pl 里找不到 chmod 600 执行行')
        for ln in chmod_lines:
            self.assertNotIn('|| true', ln, 'chmod 失败不许用 `|| true` 吞掉: %r' % ln)

    def test_27_all_three_write_points_go_through_writer(self):
        uses = [ln for ln in self.src.splitlines()
                if ln.strip() == 'write_default_pl "$rand_pass"']
        self.assertEqual(3, len(uses),
                         'deploy.sh 三处写默认密码必须都走 write_default_pl（当前 %d 处）'
                         % len(uses))

    def test_28_user_visible_deletion_hint(self):
        self.assertIn('rm -f $(default_pl_path)', self.src,
                      '安装结束提示里必须给出「首次登录后删除 default.pl」的可复制命令')
        self.assertIn('首次登录', self.src, '提示文案缺失')


class TestDataQueryPasswordCandidates(unittest.TestCase):
    """7. data_query：口令候选探测必须解密（否则拿密文连库，功能静默坏掉）。"""

    def test_29_common_db_imports_db_pwd(self):
        src = _read(COMMON_DB_PY)
        self.assertIn('import core.db_pwd as db_pwd', src,
                      'common_db 未引入 db_pwd：候选口令仍是密文')

    def test_30_common_db_decrypts_candidates(self):
        src = _read(COMMON_DB_PY)
        tree = ast.parse(src)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'detectLocalMySQLPasswords':
                fn = node
        self.assertIsNotNone(fn, 'common_db 缺 detectLocalMySQLPasswords')
        body = ast.get_source_segment(src, fn) or ''
        self.assertTrue(_call_name_in(fn, _DECRYPT_NAMES),
                        'detectLocalMySQLPasswords 未对口令候选做解密')
        self.assertIn('_add_pwd', body, '_add_pwd 是候选统一入口，解密应放在这里')

    def test_31_sql_mysql_decrypts_mysql_root(self):
        src = _read(SQL_MYSQL_PY)
        self.assertIn('db_pwd', src, 'sql_mysql 未引入 db_pwd')
        tree = ast.parse(src)
        reads = [c for c in _find_calls(tree, 'getField') if _first_arg_is_const(c, 'mysql_root')]
        self.assertTrue(reads, 'sql_mysql 里扫不到 getField(\'mysql_root\')，守卫失效')
        parents = _parents(tree)
        for node in reads:
            parent = parents.get(node)
            ok = isinstance(parent, ast.Call) and _callee_name(parent) in _DECRYPT_NAMES
            self.assertTrue(ok, 'sql_mysql:%d 读 mysql_root 未包解密调用' % node.lineno)


if __name__ == '__main__':
    unittest.main(verbosity=2)
