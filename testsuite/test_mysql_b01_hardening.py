# coding: utf-8
"""B01 mysql 插件加固守卫（备份/导入/删除路径 · 命令与 SQL 注入 · 失败面诚实）。

真机实测确认并修复的缺陷，全部在此锁死，防止回退：

1. `dumpMysqlData`：`db` 参数被直接拼进 shell（`test1; touch /tmp/x` 真以 root
   执行）；且 `mysqldump | gzip` 的退出码恒为 gzip 的 0 → 导出失败也回 `ok`。
2. `importDbBackup` / `importDbBackupProgressBar`：`file` 参数拼进 `gzip`/`mysql`
   命令（`x.sql.gz; touch /tmp/x; #` 真以 root 执行），并硬编码
   `getFatherDir()+'/backup/database'`。
3. `deleteDbBackup`：`path`+`filename` 未校验 → root 删任意文件（`path=/tmp` 直接
   删 /tmp 下文件、`../../../` 可穿越），文件不存在时 `os.remove` 抛 traceback。
4. 备份目录「读/写不同源」：写入侧（scripts/backup.py）走 `yf.getBackupDir()`，
   而读取/导入/删除侧硬编码 `yf.getFatherDir()+'/backup/database'` → 用户改过
   备份目录后备份不可见/不可导入/不可删除。
5. `getDbAccess`：`username` 直接拼 SQL（`x' OR '1'='1` 读出全部 Host）。
6. `setUserPwd`：缺 `id` 直接 KeyError traceback；`username`/`password` 可注入；
   accept 查询误用**库名**而不是用户名 → 非 localhost 的 host 改不到密码。
7. `setDbRw`：`username` 拼 SQL；无论 SQL 成败都回「切换成功!」（假成功）。
8. `binLogList`：`page`/`page_size` 非数字 → ValueError traceback。
9. `setMyPort`：任意 `port` 写进 my.cnf 并重启 → mysql 起不来（真机服务 failed），
   接口仍回「编辑成功!」。
10. `addDb`：非法 `codeing` → KeyError traceback；`dbuser`/`address` 拼 SQL。
11. `setDbPs`：不存在的 id 回「成功」（假成功）。
12. `getSlaveName`：引用只在 `__main__` 存在的全局 `version` → 被 import 时 NameError。

断言口径（防「假绿」）：全部基于 **AST**，且过滤 `if False:` 等静态死分支
（`ast.walk` 会遍历死分支，这里用 `_live_nodes` 只走可达节点），注释天然不参与。
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')


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


def _loaded_names(node):
    return [n.id for n in _live_nodes(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]


def _string_consts(node):
    return [n.value for n in _live_nodes(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _has_whitelist_regex(fn, needles=('\\w', '[0-9]')):
    """函数里是否有 `re.match(<含白名单字符类的模式>, ...)` 校验。"""
    for c in _calls(fn, 'match'):
        f = c.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 're'):
            continue
        if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str):
            if any(needle in c.args[0].value for needle in needles):
                return True
    return False


class MysqlB01Test(unittest.TestCase):

    def setUp(self):
        self.tree = _parse(IDX)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    # ---- 1. dumpMysqlData：注入 + 假成功 --------------------------------------
    def test_01_dump_mysql_data_is_injection_safe_and_honest(self):
        fn = self._fn('dumpMysqlData')
        self.assertTrue(_has_whitelist_regex(fn),
                        'dumpMysqlData 必须先对 db 做白名单校验再使用')
        # 不再用 shell 管道（退出码会被 gzip 冲成 0 → 假成功）
        self.assertTrue(_calls(fn, 'Popen'),
                        'dumpMysqlData 必须用 argv 列表调用 mysqldump（可拿到真实退出码）')
        self.assertFalse(_calls(fn, 'execShell'),
                         'dumpMysqlData 不得再用 shell 字符串管道导出')
        # 失败必须能被检出：看退出码 + 产物大小
        self.assertTrue(_calls(fn, 'getsize'), 'dumpMysqlData 必须校验产物大小以发现失败')

    # ---- 2. 备份/导入文件白名单 ----------------------------------------------
    def test_02_import_db_backup_validates_filename(self):
        for name in ('importDbBackup', 'importDbBackupProgressBar'):
            fn = self._fn(name)
            guards = [c for c in _calls(fn, 'match')
                      if isinstance(c.func, ast.Attribute)
                      and isinstance(c.func.value, ast.Name)
                      and c.func.value.id == '_DB_BACKUP_FILE_RE']
            self.assertTrue(guards, '%s 必须用 _DB_BACKUP_FILE_RE 校验 file' % name)
            self.assertTrue(_has_whitelist_regex(fn), '%s 必须校验 db 名' % name)

    def test_03_delete_db_backup_validates_path_and_file(self):
        fn = self._fn('deleteDbBackup')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_BACKUP_FILE_RE']
        self.assertTrue(guards, 'deleteDbBackup 必须用 _DB_BACKUP_FILE_RE 校验文件名')
        self.assertTrue(_calls(fn, 'realpath'), 'deleteDbBackup 必须用 realpath 限定目录')

    # ---- 3. 备份目录读写同源 --------------------------------------------------
    def test_04_backup_dir_single_source(self):
        for helper in ('getDbBackupDir', 'getDbImportDir'):
            self.assertIsNotNone(_find_func(self.tree, helper), '缺少路径助手 %s' % helper)
        for name, helper in (
                ('getDbBackupListFunc', 'getDbBackupDir'),
                ('setDbBackup', 'getDbBackupDir'),
                ('packageDbBackups', 'getDbBackupDir'),
                ('getDbBackupList', 'getDbBackupDir'),
                ('deleteDbBackup', 'getDbBackupDir'),
                ('importDbBackup', 'getDbBackupDir'),
                ('importDbBackupProgressBar', 'getDbBackupDir'),
                ('getDbBackupImportList', 'getDbImportDir'),
                ('importDbExternalProgressBar', 'getDbImportDir')):
            fn = self._fn(name)
            self.assertTrue(_calls(fn, helper),
                            '%s 必须走 %s（与写入侧同源）' % (name, helper))
            self.assertFalse(_calls(fn, 'getFatherDir'),
                             '%s 不得再硬编码 getFatherDir() 备份目录' % name)

    # ---- 4. getDbAccess：SQL 注入 ---------------------------------------------
    def test_05_get_db_access_rejects_injection(self):
        fn = self._fn('getDbAccess')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_USER_IDENT_RE']
        self.assertTrue(guards, 'getDbAccess 必须对 username 做白名单校验')
        # 查询 SQL 必须是常量（参数化），不能是拼接表达式
        for c in _calls(fn, 'query'):
            if c.args:
                self.assertIsInstance(c.args[0], ast.Constant,
                                      'getDbAccess 的 SQL 必须是常量（参数化），不得拼接')

    # ---- 5. setUserPwd --------------------------------------------------------
    def test_06_set_user_pwd_requires_id_and_escapes(self):
        fn = self._fn('setUserPwd')
        # checkArgs 必须包含 'id'
        req = None
        for c in _calls(fn, 'checkArgs'):
            if len(c.args) >= 2 and isinstance(c.args[1], ast.List):
                req = [e.value for e in c.args[1].elts if isinstance(e, ast.Constant)]
        self.assertIsNotNone(req, 'setUserPwd 必须有 checkArgs 参数表')
        self.assertIn('id', req, "setUserPwd 必须把 id 纳入 checkArgs（否则缺参 KeyError）")
        self.assertIn('safe_pwd', _assigned_names(fn), 'setUserPwd 必须转义密码字面量')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_USER_IDENT_RE']
        self.assertTrue(guards, 'setUserPwd 必须对用户名/库名做白名单校验')
        # accept 查询必须用 username，不得用库名 name
        accept_calls = [c for c in _calls(fn, 'query')
                        if c.args and isinstance(c.args[0], ast.Constant)
                        and 'mysql.user' in str(c.args[0].value)]
        self.assertTrue(accept_calls, 'setUserPwd 必须查询 mysql.user')
        for c in accept_calls:
            params = c.args[1] if len(c.args) > 1 else None
            self.assertIsNotNone(params, 'accept 查询必须参数化')
            self.assertIn('username', ast.dump(params),
                          'accept 查询必须用 username（历史缺陷：误用库名 name）')

    # ---- 6. setDbRw：注入 + 假成功 -------------------------------------------
    def test_07_set_db_rw_is_injection_safe_and_honest(self):
        fn = self._fn('setDbRw')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_USER_IDENT_RE']
        self.assertTrue(guards, 'setDbRw 必须对 username 做白名单校验')
        self.assertIn('failed', _assigned_names(fn), 'setDbRw 必须记录 SQL 成败')
        self.assertTrue(_calls(fn, 'isinstance'), 'setDbRw 必须检查 execute 返回值')

    # ---- 7. binLogList 分页容错 ----------------------------------------------
    def test_08_binlog_list_pagination_is_safe(self):
        fn = self._fn('binLogList')
        has_try = False
        for n in _live_nodes(fn):
            if isinstance(n, ast.Try):
                if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                       and c.func.id == 'int' for c in ast.walk(n)):
                    has_try = True
        self.assertTrue(has_try, 'binLogList 的 int() 必须在 try/except 内')

    # ---- 8. setMyPort 端口白名单 ---------------------------------------------
    def test_09_set_my_port_validates_range(self):
        fn = self._fn('setMyPort')
        self.assertTrue(_has_whitelist_regex(fn), 'setMyPort 必须先做数字白名单校验')
        has_range = any(
            isinstance(n, ast.Compare)
            and any(isinstance(c, ast.Constant) and c.value == 65535 for c in n.comparators)
            for n in _live_nodes(fn))
        self.assertTrue(has_range, 'setMyPort 必须校验端口上限 65535')

    # ---- 9. addDb 编码/用户名白名单 ------------------------------------------
    def test_10_add_db_validates_codeing_and_user(self):
        fn = self._fn('addDb')
        has_notin = any(
            isinstance(n, ast.Compare)
            and any(isinstance(op, ast.NotIn) for op in n.ops)
            and any(isinstance(c, ast.Name) and c.id == 'wheres' for c in n.comparators)
            for n in _live_nodes(fn))
        self.assertTrue(has_notin, 'addDb 必须校验 codeing 是否在白名单里（否则 KeyError）')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_USER_IDENT_RE']
        self.assertTrue(guards, 'addDb 必须对 dbuser/address 做白名单校验')

    # ---- 10. setDbPs 存在性 --------------------------------------------------
    def test_11_set_db_ps_checks_existence(self):
        fn = self._fn('setDbPs')
        self.assertTrue(_calls(fn, 'count'),
                        'setDbPs 必须先 count 判存在，不存在不得回「成功」')

    # ---- 11. getSlaveName 不再 NameError -------------------------------------
    def test_12_get_slave_name_has_no_bare_version(self):
        fn = self._fn('getSlaveName')
        self.assertNotIn('version', _loaded_names(fn),
                         'getSlaveName 不得直接引用全局 version（import 时 NameError）')
        self.assertTrue(_calls(fn, 'get'), 'getSlaveName 必须用 globals().get("version") 兜底')

    # ---- 12. 主从同步账户密码转义 --------------------------------------------
    def test_13_replication_user_password_escaped(self):
        for name in ('addMasterRepSlaveUser', 'updateMasterRepSlaveUser'):
            fn = self._fn(name)
            self.assertIn('safe_pwd', _assigned_names(fn),
                          '%s 必须转义密码字面量' % name)

    # ---- 13. setDbAccess host 白名单 -----------------------------------------
    def test_14_set_db_access_validates_hosts(self):
        fn = self._fn('setDbAccess')
        guards = [c for c in _calls(fn, 'match')
                  if isinstance(c.func, ast.Attribute)
                  and isinstance(c.func.value, ast.Name)
                  and c.func.value.id == '_DB_USER_IDENT_RE']
        self.assertTrue(guards, 'setDbAccess 必须对目标 host 做白名单校验')


if __name__ == '__main__':
    unittest.main()
