# coding: utf-8
"""B02 mariadb 插件加固守卫（与 mysql 单侧漂移对齐 · 注入/任意删除/假成功）。

真机夹具真跑（`/root/yf_probe_B02/probe_fixture.py`，old→new 逐条对照）确认并修复的
缺陷，全部在此锁死，防止回退：

1. `dumpMysqlData`：`db` 被直接拼进 shell（`yftest_b02_nodb; touch /tmp/x` 真以 root
   执行）；且 `mysqldump | gzip` 退出码恒为 gzip 的 0 → 库不存在也回 `ok`。
2. `deleteDbBackup`：`path`/`filename` 未校验 → 任意文件删除（`path=/root`、
   `filename=../../../canary.txt` 真删掉站外文件），文件不存在时 `os.remove` traceback。
3. `getDbAccess` / `setDbRw` / `delMasterRepSlaveUser`：`username` 直接拼 SQL。
4. `setUserPwd`：`id` 不存在 → `data['accept']` KeyError，except 分支再引用未赋值的
   `name` → NameError traceback；密码未转义。
5. `setDbRw`：SQL 全失败仍回「切换成功!」（假成功）。
6. `setDbPs`：不存在的 id 回「成功」；失败分支回 `status=True`。
7. `addDb`：非法 `codeing` → KeyError traceback；`dbuser`/`address` 拼 SQL。
8. `binLogList`：`page` 非数字 → ValueError traceback。
9. `setMyPort`：任意 `port` 写进 my.cnf 并重启（`abc`/`70000` 都能写坏配置），
   且不看 `restart()` 结果一律回「编辑成功!」。
10. `importDbExternalProgressBar`：导入目录硬编码 `getFatherDir()+'/backup/import/'`，
    与 `importDbExternal` 的 `yf.getBackupDir()+'/import/'` 不同源。
11. `scripts/backup.py`：`os.chdir(yf.getPanelDir())` 写在 `import core.yf as yf`
    **之前** → Linux 下必然 NameError，mariadb 数据库备份功能整体不可用；
    备份目录写侧硬编码 `getFatherDir()+'/backup/database/mariadb'`（与读侧不同源）；
    导出用 `| gzip > file` 且只判 `os.path.exists` → 0 字节产物也报「备份成功」。

断言口径（防「假绿」）：全部基于 **AST**，过滤 `if False:` 等静态死分支
（`_live_nodes` 只走可达节点），注释天然不参与。
"""
import ast
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')
BACKUP = os.path.join(ROOT, 'plugins', 'mariadb', 'scripts', 'backup.py')


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


def _calls(node, name):
    """收集「可达」代码里对 `name`（Name 调用或 `.name(...)` 属性调用）的调用节点。"""
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


def _assigned_names(node):
    names = []
    for n in _live_nodes(node):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
    return names


def _string_consts(node):
    return [n.value for n in _live_nodes(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _has_whitelist_regex(fn, needles=('\\w', '[0-9]')):
    for c in _calls(fn, 'match'):
        f = c.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 're'):
            continue
        if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str):
            if any(needle in c.args[0].value for needle in needles):
                return True
    return False


def _regex_guard(fn, const_name):
    """函数里是否用 <const_name> 常量（如 `_DB_USER_IDENT_RE.match(...)`）做校验。"""
    for n in _live_nodes(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == const_name:
            return True
    return False


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


class MariadbB02Test(unittest.TestCase):

    def setUp(self):
        self.tree = _parse(IDX)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    # ---- 1. dumpMysqlData：注入 + 假成功 --------------------------------------
    def test_01_dump_mysql_data_is_injection_safe_and_honest(self):
        fn = self._fn('dumpMysqlData')
        self.assertTrue(_has_whitelist_regex(fn), 'dumpMysqlData 必须先对 db 做白名单校验')
        self.assertTrue(_calls(fn, 'Popen'), 'dumpMysqlData 必须用 argv 列表调用 dump（拿真实退出码）')
        self.assertFalse(_calls(fn, 'execShell'), 'dumpMysqlData 不得再用 shell 字符串管道导出')
        self.assertTrue(_calls(fn, 'getsize'), 'dumpMysqlData 必须校验产物大小以发现失败')

    # ---- 2. deleteDbBackup：任意删除 -----------------------------------------
    def test_02_delete_db_backup_validates_path_and_file(self):
        fn = self._fn('deleteDbBackup')
        self.assertTrue(_regex_guard(fn, '_DB_BACKUP_FILE_RE'),
                        'deleteDbBackup 必须用 _DB_BACKUP_FILE_RE 校验文件名')
        self.assertTrue(_calls(fn, 'realpath'), 'deleteDbBackup 必须用 realpath 限定目录')
        self.assertTrue(_calls(fn, 'exists'), 'deleteDbBackup 必须先判存在，不得让 os.remove 抛 traceback')

    def test_03_backup_file_regex_rejects_traversal(self):
        pat = _module_regex(self.tree, '_DB_BACKUP_FILE_RE')
        self.assertIsNotNone(pat, '缺少 _DB_BACKUP_FILE_RE 常量')
        rx = re.compile(pat)
        for bad in ('/etc/passwd', 'a/b.sql.gz', 'x;touch /tmp/p', 'a\\b.sql.gz', 'a b.sql.gz'):
            self.assertIsNone(rx.match(bad), '文件名白名单不应放行 %r' % bad)
        self.assertIsNotNone(rx.match('mariadb104_db_20260101_000000.sql.gz'))

    # ---- 3. 备份目录读写同源 --------------------------------------------------
    def test_04_backup_dirs_single_source(self):
        for name in ('getDbBackupListFunc', 'getDbBackupList',
                     'deleteDbBackup', 'importDbBackup'):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, 'getBackupDir'),
                            '%s 必须走 getBackupDir()（与写入侧同源）' % name)
        bar = self._fn('importDbExternalProgressBar')
        self.assertTrue(_calls(bar, 'getBackupDir'),
                        'importDbExternalProgressBar 必须与 importDbExternal 的导入目录同源')
        self.assertFalse(_calls(bar, 'getFatherDir'),
                         'importDbExternalProgressBar 不得再硬编码 getFatherDir() 目录')

    # ---- 4. SQL 注入面 --------------------------------------------------------
    def test_05_get_db_access_rejects_injection(self):
        fn = self._fn('getDbAccess')
        self.assertTrue(_regex_guard(fn, '_DB_USER_IDENT_RE'),
                        'getDbAccess 必须对 username 做白名单校验')
        for c in _calls(fn, 'query'):
            if c.args:
                self.assertIsInstance(c.args[0], ast.Constant,
                                      'getDbAccess 的 SQL 必须是常量（参数化），不得拼接')

    def test_06_del_master_rep_slave_user_rejects_injection(self):
        fn = self._fn('delMasterRepSlaveUser')
        self.assertTrue(_regex_guard(fn, '_DB_USER_IDENT_RE'),
                        'delMasterRepSlaveUser 必须对 username 做白名单校验')
        for c in _calls(fn, 'query'):
            if c.args:
                self.assertIsInstance(c.args[0], ast.Constant,
                                      'delMasterRepSlaveUser 的 SQL 必须是常量（参数化）')

    # ---- 5. setUserPwd --------------------------------------------------------
    def test_07_set_user_pwd_requires_id_and_escapes(self):
        fn = self._fn('setUserPwd')
        req = None
        for c in _calls(fn, 'checkArgs'):
            if len(c.args) >= 2 and isinstance(c.args[1], ast.List):
                req = [e.value for e in c.args[1].elts if isinstance(e, ast.Constant)]
        self.assertIsNotNone(req, 'setUserPwd 必须有 checkArgs 参数表')
        self.assertIn('id', req, 'setUserPwd 必须把 id 纳入 checkArgs（否则缺参 KeyError）')
        self.assertIn('safe_pwd', _assigned_names(fn), 'setUserPwd 必须转义密码字面量')
        self.assertTrue(_regex_guard(fn, '_DB_USER_IDENT_RE'),
                        'setUserPwd 必须对用户名/host 做白名单校验')
        has_none_guard = any(
            isinstance(n, ast.If) and any(isinstance(c, ast.UnaryOp) and isinstance(c.op, ast.Not)
                                          for c in [n.test])
            for n in _live_nodes(fn))
        self.assertTrue(has_none_guard, 'setUserPwd 必须先判记录是否存在（历史 data=None → traceback）')

    # ---- 6. setDbRw：注入 + 假成功 -------------------------------------------
    def test_08_set_db_rw_is_injection_safe_and_honest(self):
        fn = self._fn('setDbRw')
        self.assertTrue(_regex_guard(fn, '_DB_USER_IDENT_RE'),
                        'setDbRw 必须对 username/host 做白名单校验')
        self.assertIn('failed', _assigned_names(fn), 'setDbRw 必须记录 SQL 成败')
        self.assertTrue(_calls(fn, 'isinstance'), 'setDbRw 必须检查 execute 返回值')

    # ---- 7. binLogList 分页容错 ----------------------------------------------
    def test_09_binlog_list_pagination_is_safe(self):
        fn = self._fn('binLogList')
        has_try = False
        for n in _live_nodes(fn):
            if isinstance(n, ast.Try):
                if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == 'int'
                       for c in ast.walk(n)):
                    has_try = True
        self.assertTrue(has_try, 'binLogList 的 int() 必须在 try/except 内')

    # ---- 8. setMyPort 端口白名单 ---------------------------------------------
    def test_10_set_my_port_validates_range_and_restart(self):
        fn = self._fn('setMyPort')
        self.assertTrue(_has_whitelist_regex(fn), 'setMyPort 必须先做数字白名单校验')
        has_range = any(
            isinstance(n, ast.Compare)
            and any(isinstance(c, ast.Constant) and c.value == 65535 for c in n.comparators)
            for n in _live_nodes(fn))
        self.assertTrue(has_range, 'setMyPort 必须校验端口上限 65535')
        self.assertTrue(_calls(fn, 'restart'), 'setMyPort 必须检查 restart() 结果，不得假成功')
        self.assertTrue(_calls(fn, 'search'), 'setMyPort 必须在写盘前确认 my.cnf 里存在 port 行')

    # ---- 9. addDb 编码/用户名白名单 ------------------------------------------
    def test_11_add_db_validates_codeing_and_user(self):
        fn = self._fn('addDb')
        has_notin = any(
            isinstance(n, ast.Compare)
            and any(isinstance(op, ast.NotIn) for op in n.ops)
            and any(isinstance(c, ast.Name) and c.id == 'wheres' for c in n.comparators)
            for n in _live_nodes(fn))
        self.assertTrue(has_notin, 'addDb 必须校验 codeing 在白名单内（否则 KeyError traceback）')
        self.assertTrue(_regex_guard(fn, '_DB_USER_IDENT_RE'),
                        'addDb 必须对 dbuser/address 做白名单校验')

    # ---- 10. setDbPs 存在性 --------------------------------------------------
    def test_12_set_db_ps_checks_existence(self):
        fn = self._fn('setDbPs')
        self.assertTrue(_calls(fn, 'count'),
                        'setDbPs 必须先 count 判存在，不存在不得回「成功」')

    # ---- 11. 主从同步账户密码转义 --------------------------------------------
    def test_13_replication_user_password_escaped(self):
        for name in ('addMasterRepSlaveUser', 'updateMasterRepSlaveUser'):
            fn = self._fn(name)
            self.assertIn('safe_pwd', _assigned_names(fn), '%s 必须转义密码字面量' % name)


class MariadbBackupScriptTest(unittest.TestCase):
    """plugins/mariadb/scripts/backup.py（数据库备份脚本）的守卫。"""

    def setUp(self):
        self.src = _read(BACKUP)
        self.tree = ast.parse(self.src)

    def test_01_yf_used_only_after_import(self):
        """`yf` 只能在 `import core.yf as yf` 之后使用（历史：chdir 写在 import 前 → NameError）。"""
        import_idx = None
        for i, node in enumerate(self.tree.body):
            if isinstance(node, ast.ImportFrom) and node.module == 'core.yf':
                import_idx = i
                break
            if isinstance(node, ast.Import) and any(a.name == 'core.yf' for a in node.names):
                import_idx = i
                break
        self.assertIsNotNone(import_idx, '未找到 import core.yf')
        for node in self.tree.body[:import_idx]:
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and n.id == 'yf':
                    self.fail('模块顶层在 import core.yf 之前就使用了 yf: %s' % ast.dump(node)[:120])

    def test_02_backup_dir_single_source(self):
        fn = _find_func(self.tree, 'backupDatabase')
        self.assertIsNotNone(fn, '缺少 backupDatabase')
        self.assertTrue(_calls(fn, 'getBackupDir'),
                        'backupDatabase 写侧必须用 yf.getBackupDir()（与读侧同源）')
        self.assertFalse(_calls(fn, 'getFatherDir'),
                         'backupDatabase 不得再硬编码 getFatherDir() 备份目录')

    def test_03_dump_not_fake_success(self):
        fn = _find_func(self.tree, 'backupDatabase')
        self.assertTrue(_calls(fn, 'Popen'), 'backupDatabase 必须用 argv 列表调用 dump')
        self.assertFalse(_calls(fn, 'execShell'),
                         'backupDatabase 不得再用 `dump | gzip > file`（退出码被 gzip 冲成 0）')
        self.assertTrue(_calls(fn, 'getsize'), 'backupDatabase 必须校验产物大小')

    def test_04_cnf_password_restored_before_return(self):
        """失败路径也必须还原 my.cnf（不得把明文 root 密码留在配置里）。"""
        fn = _find_func(self.tree, 'backupDatabase')
        restore_line = None
        fail_line = None
        for n in ast.walk(fn):
            # 还原动作的特征：yf.writeFile(<...>, mycnf)（写回去掉密码的 mycnf）
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'writeFile' and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Name) and n.args[1].id == 'mycnf'):
                if restore_line is None:
                    restore_line = n.lineno
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and '备份失败' in n.value:
                if fail_line is None:
                    fail_line = n.lineno
        self.assertIsNotNone(restore_line, 'backupDatabase 必须还原 my.cnf')
        self.assertIsNotNone(fail_line, 'backupDatabase 必须有备份失败分支')
        self.assertLess(restore_line, fail_line, 'my.cnf 还原必须发生在「备份失败」return 之前')


if __name__ == '__main__':
    unittest.main()
