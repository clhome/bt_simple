# -*- coding: utf-8 -*-
"""MySQL / MariaDB 插件「my.cnf 读取 + 删库」加固与对齐守卫。

背景：这两个插件是近亲复制品（`index.py` 各 4000~5300 行，**136 个同名函数，
其中 95 个函数体已漂移**），历史加固只落在单侧，形成互补缺口：

* `mariadb::delDb` 停留在「ORM + 字符串拼接 SQL + 丢弃 `execute()` 返回值」的老实现，
  而 `mysql::delDb` 已重写为 pymysql 直连 + 超时 + 1008 容错 + `find` 空值保护；
* `mysql::setDbBackup` 缺库名白名单，而 mariadb 侧有；
* mariadb 侧 10 个 my.cnf getter 无守卫：my.cnf 缺失（`content=False`）或未配置该项
  （`tmp=None`）时会抛 `TypeError` / `AttributeError`，mysql 侧同名函数多数已修。

本用例把「修完的结果」钉住，防止再次单侧漂移；同时覆盖 my.cnf 读取缓存的
**失效语义**（文件一改必须重读，绝不能读到旧值 —— 这是数据库面板的底线）。
"""

import ast
import importlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_DIR = os.path.join(PROJECT_ROOT, 'web')
for _p in (PROJECT_ROOT, _WEB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MYSQL_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'mysql', 'index.py')
MARIADB_SRC = os.path.join(PROJECT_ROOT, 'plugins', 'mariadb', 'index.py')

# 两插件里「从 my.cnf 取单个值」的 getter 全集
MYSQL_GETTERS = ['getDbPort', 'getSocketFile', 'getMyPort', 'getMyDbPos', 'getDbServerId',
                 'getLogBinName', 'getPidFile', 'getErrorLogsFile', 'getShowLogFile', 'getAuthPolicy']
MARIADB_GETTERS = ['getDataDir', 'getLogBinName', 'getPidFile', 'getDbPort', 'getDbServerId',
                   'getSocketFile', 'getShowLogFile', 'getMyDbPos', 'getMyPort']


def _read_src(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_source(path, name):
    """返回指定函数的源码文本（按 AST 行号切片）。"""
    src = _read_src(path)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 中找不到函数 %s' % (path, name))


def _unguarded_cnf_parses(path):
    """扫描「my.cnf 内容未经判空就送进 re.search」的写法。

    只认「变量确实来自 `yf.readFile(getConf())`」的链路，避免把同步 SQL 内容
    等无关 `content` 变量误判进来。
    """
    tree = ast.parse(_read_src(path))
    bad = []
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        cnf_vars, reads, guards = set(), {}, []
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == 'getConf'
                    and isinstance(node.targets[0], ast.Name)):
                cnf_vars.add(node.targets[0].id)
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                if (isinstance(call.func, ast.Attribute) and call.func.attr == 'readFile'
                        and call.args and isinstance(call.args[0], ast.Name)
                        and call.args[0].id in cnf_vars
                        and isinstance(node.targets[0], ast.Name)):
                    reads[node.targets[0].id] = node.lineno
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Name):
                    guards.append((test.id, node.lineno))
                elif isinstance(test, ast.UnaryOp) and isinstance(test.operand, ast.Name):
                    guards.append((test.operand.id, node.lineno))
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('search', 'match') and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Name) and node.args[1].id in reads):
                name = node.args[1].id
                if not any(g[0] == name and reads[name] < g[1] < node.lineno for g in guards):
                    bad.append((fn.name, node.lineno))
    return bad


def _import_plugin(modname):
    """导入插件模块并把 cwd 还原。

    插件第 8~13 行有模块级副作用（`sys.path.append(os.getcwd() + "/web")` + `os.chdir`），
    所以导入前必须让 cwd 落在仓库根，导入后立刻还原，避免污染同进程的其它用例。
    """
    cwd = os.getcwd()
    try:
        os.chdir(PROJECT_ROOT)
        return importlib.import_module(modname)
    finally:
        os.chdir(cwd)


@unittest.skipUnless(os.path.exists(MYSQL_SRC) and os.path.exists(MARIADB_SRC), '缺少插件源码')
class TestCnfReaderHardening(unittest.TestCase):
    """一、my.cnf 读取收口（不再每个 getter 各写一套裸解析）"""

    @classmethod
    def setUpClass(cls):
        cls.mysql = _import_plugin('plugins.mysql.index')
        cls.mariadb = _import_plugin('plugins.mariadb.index')

    def test_01_both_plugins_expose_shared_reader(self):
        """两插件都必须有 _readCnf / _cnfValue 单一入口"""
        for mod in (self.mysql, self.mariadb):
            self.assertTrue(callable(getattr(mod, '_readCnf', None)), mod.__name__)
            self.assertTrue(callable(getattr(mod, '_cnfValue', None)), mod.__name__)

    def test_02_no_unguarded_cnf_parse(self):
        """不得再有「读 my.cnf 后不判空就直接 re.search」的写法"""
        for path in (MYSQL_SRC, MARIADB_SRC):
            self.assertEqual([], _unguarded_cnf_parses(path), path)

    def test_03_default_when_cnf_missing(self):
        """my.cnf 不存在时返回默认值，绝不抛 TypeError/AttributeError"""
        for mod in (self.mysql, self.mariadb):
            with patch.object(mod, 'getConf', return_value='/nonexistent/definitely/my.cnf'):
                self.assertEqual('3306', mod._cnfValue(r'port\s*=\s*(.*)', '3306'))
                self.assertEqual('', mod._cnfValue(r'port\s*=\s*(.*)'))
                self.assertEqual('fallback', mod._cnfValue(r'socket\s*=\s*(.*)', 'fallback'))

    def test_04_parses_values_from_cnf(self):
        """能正确解析 port / socket（并忽略同一 key 的其他行）"""
        with tempfile.TemporaryDirectory() as tmp:
            cnf = os.path.join(tmp, 'my.cnf')
            with open(cnf, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write('[mysqld]\nport = 3307\nsocket=/tmp/custom.sock\n')
            for mod in (self.mysql, self.mariadb):
                with patch.object(mod, 'getConf', return_value=cnf):
                    self.assertEqual('3307', mod.getDbPort())
                    self.assertEqual('/tmp/custom.sock', mod.getSocketFile())

    def test_05_getters_survive_without_cnf(self):
        """my.cnf 与全部候选路径都不存在时，所有 getter 仍返回 str 且不抛异常"""
        for mod, names in ((self.mysql, MYSQL_GETTERS), (self.mariadb, MARIADB_GETTERS)):
            with patch.object(mod, 'getConf', return_value='/nonexistent/my.cnf'), \
                 patch.object(mod.os.path, 'exists', return_value=False):
                for name in names:
                    value = getattr(mod, name)()
                    self.assertIsInstance(value, str, '%s.%s' % (mod.__name__, name))


@unittest.skipUnless(os.path.exists(MYSQL_SRC) and os.path.exists(MARIADB_SRC), '缺少插件源码')
class TestCnfCacheSemantics(unittest.TestCase):
    """二、my.cnf 缓存必须「只省重复读盘」，绝不返回旧值"""

    @classmethod
    def setUpClass(cls):
        cls.mysql = _import_plugin('plugins.mysql.index')
        cls.mariadb = _import_plugin('plugins.mariadb.index')

    def _counting_readfile(self, real, counter):
        def fake(path, *args, **kwargs):
            counter['n'] += 1
            return real(path, *args, **kwargs)
        return fake

    def test_06_cache_hits_avoid_repeated_read(self):
        """同一份未变化的 my.cnf：连续 3 次 getDbPort 只读盘 1 次"""
        with tempfile.TemporaryDirectory() as tmp:
            cnf = os.path.join(tmp, 'my.cnf')
            with open(cnf, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write('port = 3310\n')
            for mod in (self.mysql, self.mariadb):
                counter = {'n': 0}
                real = mod.yf.readFile
                with patch.object(mod, 'getConf', return_value=cnf), \
                     patch.object(mod.yf, 'readFile', self._counting_readfile(real, counter)):
                    self.assertEqual(['3310'] * 3, [mod.getDbPort() for _ in range(3)])
                self.assertEqual(1, counter['n'], mod.__name__)

    def test_07_cache_invalidates_on_file_change(self):
        """my.cnf 被改写后必须重读（缓存失效），不能返回旧值"""
        with tempfile.TemporaryDirectory() as tmp:
            cnf = os.path.join(tmp, 'my.cnf')
            for mod in (self.mysql, self.mariadb):
                with open(cnf, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write('port = 3310\n')
                with patch.object(mod, 'getConf', return_value=cnf):
                    self.assertEqual('3310', mod.getDbPort())
                    with open(cnf, 'w', encoding='utf-8', newline='\n') as fh:
                        fh.write('port = 3399\n')          # 内容与长度都变 → stamp 变
                    self.assertEqual('3399', mod.getDbPort())
                    with open(cnf, 'w', encoding='utf-8', newline='\n') as fh:
                        fh.write('port = 3\n')             # 只变长度也必须失效
                    self.assertEqual('3', mod.getDbPort())

    def test_08_cnf_cache_returns_empty_on_stat_error(self):
        """路径不可 stat（目录不存在/无权限）时返回空串，不抛异常"""
        for mod in (self.mysql, self.mariadb):
            with patch.object(mod, 'getConf', return_value=os.path.join(PROJECT_ROOT, 'no_such_dir', 'x.cnf')):
                self.assertEqual('', mod._readCnf())

    def test_09_cache_key_includes_readfile_impl(self):
        """缓存 key 必须含 yf.readFile 的当前实现

        否则测试里 patch 掉 yf.readFile 之后，缓存会把上一个实现的旧内容
        喂给本用例（跨用例串味）。这条断言防止后人「顺手简化」掉该元素。
        """
        for path in (MYSQL_SRC, MARIADB_SRC):
            src = _func_source(path, '_readCnf')
            self.assertIn('yf.readFile', src, path)
            self.assertRegex(src, r'key\s*=\s*\([^)]*yf\.readFile[^)]*\)', path)


@unittest.skipUnless(os.path.exists(MYSQL_SRC) and os.path.exists(MARIADB_SRC), '缺少插件源码')
class TestDelDbHardeningParity(unittest.TestCase):
    """三、delDb：两侧必须同一套加固口径"""

    @classmethod
    def setUpClass(cls):
        cls.mysql = _import_plugin('plugins.mysql.index')
        cls.mariadb = _import_plugin('plugins.mariadb.index')

    def test_10_del_db_has_all_hardening(self):
        for path in (MYSQL_SRC, MARIADB_SRC):
            src = _func_source(path, 'delDb')
            self.assertIn('_dropUserTargets', src, path)               # 白名单拼装
            self.assertIn('WHERE User=%s', src, path)                  # 参数化查询
            self.assertIn("DROP USER \" + ','.join(targets)", src, path)   # 单条批量
            self.assertIn('read_timeout', src, path)                   # 读超时
            self.assertIn('connect_timeout', src, path)                # 连接超时
            self.assertIn('1008', src, path)                           # 库不存在容错
            self.assertIn('if not find:', src, path)                   # 记录空值保护
            self.assertIn("'数据库名称不合法!'", src, path)              # 库名白名单

    def test_11_del_db_drops_legacy_orm_concat(self):
        """不得再出现 ORM + 字符串拼接的老写法（含丢弃返回值）"""
        legacy_patterns = [
            'pdb.execute("drop database',
            'pdb.execute("drop user',
            'pdb.query("select Host from user where User=',
        ]
        for path in (MYSQL_SRC, MARIADB_SRC):
            src = _func_source(path, 'delDb')
            for pat in legacy_patterns:
                self.assertNotIn(pat, src, '%s 仍存在旧写法: %s' % (path, pat))

    def test_12_drop_user_targets_blocks_injection(self):
        """用户名/Host 含白名单外字符时整体放弃，不拼出半截语句"""
        evil_users = ["x'; DROP DATABASE y; --", 'a`b', 'a"b', 'a b', 'a\nb', '']
        for mod in (self.mysql, self.mariadb):
            for evil in evil_users:
                self.assertEqual([], mod._dropUserTargets(evil, ['localhost']),
                                 '%s 放行了恶意用户名 %r' % (mod.__name__, evil))
            self.assertEqual([], mod._dropUserTargets('root', ["1.2.3.4'; DROP"]))

    def test_13_drop_user_targets_builds_multi_host(self):
        """合法输入拼出正确的多目标语句单元"""
        for mod in (self.mysql, self.mariadb):
            targets = mod._dropUserTargets('root', ['localhost', '%', '1.2.3.4', '::1'])
            self.assertEqual(["'root'@'localhost'", "'root'@'%'", "'root'@'1.2.3.4'", "'root'@'::1'"], targets)
            self.assertEqual('DROP USER ' + ','.join(targets), "DROP USER 'root'@'localhost','root'@'%','root'@'1.2.3.4','root'@'::1'")

    def test_14_del_db_uses_panel_log_not_tmp_file(self):
        """重启重试的提示改写面板日志，不再往 /tmp 扔调试文件"""
        self.assertNotIn('/tmp/mysql_del_retry.log', _read_src(MYSQL_SRC))
        self.assertIn('yf.writeFileLog(', _func_source(MYSQL_SRC, 'delDb'))
        self.assertIn('yf.writeFileLog(', _func_source(MARIADB_SRC, 'delDb'))


@unittest.skipUnless(os.path.exists(MYSQL_SRC) and os.path.exists(MARIADB_SRC), '缺少插件源码')
class TestSetDbBackupHardening(unittest.TestCase):
    """四、setDbBackup：库名白名单 + 备份结果不得丢弃"""

    @classmethod
    def setUpClass(cls):
        cls.mysql = _import_plugin('plugins.mysql.index')
        cls.mariadb = _import_plugin('plugins.mariadb.index')

    def test_15_both_validate_db_name(self):
        for path in (MYSQL_SRC, MARIADB_SRC):
            self.assertIn(r'^[\w\.-]+$', _func_source(path, 'setDbBackup'), path)

    def test_16_mysql_rejects_evil_db_name(self):
        """mysql::setDbBackup 遇到非法库名必须直接拒绝，且不得执行任何 shell"""
        with patch.object(self.mysql, 'getArgs', return_value={'name': 'a"; touch /tmp/pwned; echo "'}), \
             patch.object(self.mysql.yf, 'execShell') as mock_shell:
            data = __import__('json').loads(self.mysql.setDbBackup())
        self.assertFalse(data['status'])
        self.assertFalse(mock_shell.called)

    def test_17_mariadb_reports_backup_failure(self):
        """mariadb::setDbBackup 旧实现丢弃 stdout 并无条件返回成功，现必须报错"""
        fake_proc = unittest.mock.MagicMock()
        fake_proc.communicate.return_value = (b'\xe5\xa4\x87\xe4\xbb\xbd\xe5\xa4\xb1\xe8\xb4\xa5!', b'')
        fake_proc.returncode = 0
        with patch.object(self.mariadb, 'getArgs', return_value={'name': 'demo1'}), \
             patch('subprocess.Popen', return_value=fake_proc):
            data = __import__('json').loads(self.mariadb.setDbBackup())
        self.assertFalse(data['status'])

    def test_18_mariadb_reports_nonzero_exit(self):
        fake_proc = unittest.mock.MagicMock()
        fake_proc.communicate.return_value = (b'', b'boom')
        fake_proc.returncode = 1
        with patch.object(self.mariadb, 'getArgs', return_value={'name': 'demo1'}), \
             patch('subprocess.Popen', return_value=fake_proc):
            data = __import__('json').loads(self.mariadb.setDbBackup())
        self.assertFalse(data['status'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
