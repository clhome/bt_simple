# coding:utf-8
"""
D03 clean 回归守卫：破坏性清理模块的路径白名单 / 判据一致性 / 分类限定 / 前端转义。

真机证据见 task.md D03 行；本用例是「同一批修复被回退就变红」的自动化保险。
- 夹具目录通过注入 ALLOWED_DIR_PREFIXES 进入白名单（不改生产语义）
- 结构性断言用 ast（抗注释与 `if False:` 蒙混）
- 支持 YF_D03_PLUGIN_DIR 指向变异副本（test/_d03_mutations.py 用）
"""
import ast
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.environ.get('YF_D03_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'clean')
HTML = os.path.join(PLUGIN, 'index.html')


def read_text(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def strip_js_comments(src):
    out = []
    i = 0
    n = len(src)
    while i < n:
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
        else:
            out.append(src[i])
            i += 1
    return ''.join(out)


class CleanD03Hardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._path_backup = list(sys.path)
        cls._mod_backup = {k: sys.modules.get(k) for k in ('clean_security', 'clean_scanner', 'clean_executor')}
        for k in cls._mod_backup:
            sys.modules.pop(k, None)
        sys.path.insert(0, PLUGIN)
        import importlib
        importlib.invalidate_caches()
        import clean_security
        import clean_scanner
        import clean_executor
        cls.cs = clean_security
        cls.sc = clean_scanner
        cls.ce = clean_executor
        cls.tmp = tempfile.mkdtemp(prefix='yf_d03_guard_')
        cls._allowed_backup = list(clean_security.ALLOWED_DIR_PREFIXES)
        clean_security.ALLOWED_DIR_PREFIXES = list(cls._allowed_backup) + [cls.tmp]
        # 插件自身的战报/运行日志：夹具进程内重定向到临时目录，绝不写工作区/真机状态
        cls._hist_backup = clean_executor.get_history_file
        cls._log_backup = clean_executor.get_run_log_file
        clean_executor.get_history_file = lambda: os.path.join(cls.tmp, 'clean_history.json')
        clean_executor.get_run_log_file = lambda: os.path.join(cls.tmp, 'clean.log')

    @classmethod
    def tearDownClass(cls):
        cls.cs.ALLOWED_DIR_PREFIXES = cls._allowed_backup
        cls.ce.get_history_file = cls._hist_backup
        cls.ce.get_run_log_file = cls._log_backup
        shutil.rmtree(cls.tmp, ignore_errors=True)
        sys.path[:] = cls._path_backup
        for k, v in cls._mod_backup.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def fixture(self, name, data=b'A' * 1024):
        p = os.path.join(self.tmp, name)
        d = os.path.dirname(p)
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)
        return p

    # ---------------- 面 2：越界/通配拒绝矩阵 ----------------
    def test_01_reject_matrix(self):
        cases = [
            '../../etc/passwd', '/etc/passwd', '/etc', '/', '/root', '/bin', '/usr',
            '/www/server/php/83/etc/php.ini', '/www/server/mysql/data/ibdata1',
            '/www/server/yufeng_panel/data/panel.db', '/www/wwwroot/test1/index.php',
            '/tmp/../../etc/passwd', '/ETC/passwd', '/tmp/中文/日志.log',
            '/tmp/' + 'a' * 3000,
        ]
        for p in cases:
            ok, _msg = self.cs.is_safe_path(p)
            # Windows 下 /www/... 会被映射到当前盘符（F:/www/...），与本机盘符口径
            # 混淆，因此「绝对生产路径必须被拒」的硬断言只在 POSIX 上执行；
            # 跨平台硬断言放在下面的「操作必须被拒」上。
            if p.startswith('/') and os.name != 'nt':
                self.assertFalse(ok, '绝对路径未被拒绝: %s' % p)
            t_ok, t_msg = self.ce.truncate_single_file(p)
            self.assertFalse(t_ok, '越界路径截断未被拒绝: %s -> %s' % (p, t_msg))
            d_ok, _f, d_msg = self.cs.safe_delete_file(p)
            self.assertFalse(d_ok, '越界路径删除未被拒绝: %s -> %s' % (p, d_msg))
        # 跨平台（含 Windows）必须被拒的越界路径
        outside = os.path.join(os.path.dirname(os.getcwd()), 'yf_d03_outside_check.log')
        for p in (os.path.abspath(os.sep), outside):
            ok, _m = self.cs.is_safe_path(p)
            self.assertFalse(ok, '白名单外路径未被拒绝: %s' % p)
        for bad in ('', None, 0, [], {}):
            ok, _m = self.cs.is_safe_path(bad)
            self.assertFalse(ok, '空/非字符串未被拒绝: %r' % (bad,))

    def test_02_glob_control_chars(self):
        for payload in ('/tmp/*', '/tmp/app?.log', '/tmp/**/*.log', '/tmp/[ab].log',
                        '/tmp/x\0y', '/tmp/a\n/etc/passwd', 'a;rm -rf /', 'a&&ls', 'a|ls', 'a`id`', 'a$HOME'):
            ok, msg = self.cs.is_safe_path(payload)
            self.assertFalse(ok, '通配/危险字符未被拒绝: %r' % (payload,))
        ok, msg = self.cs.is_safe_path('/tmp/a]b.log')
        self.assertFalse(ok, '] 通配字符未被拒绝')

    def test_03_symlink_escape(self):
        # 受害文件必须落在白名单之外（Windows 下白名单含 cwd，故不能放仓库内）
        outside = tempfile.mkdtemp(prefix='yf_d03_outside_')
        try:
            victim = os.path.join(outside, 'victim.txt')
            with open(victim, 'wb') as fh:
                fh.write(b'V' * 4096)
            link = os.path.join(self.tmp, 'escape_link')
            try:
                if os.path.islink(link):
                    os.unlink(link)
                os.symlink(victim, link)
            except (OSError, NotImplementedError) as e:
                self.skipTest('本机不支持创建软链: %s' % e)
            ok, msg = self.cs.is_safe_path(link)
            self.assertFalse(ok, '白名单内软链逃逸未被拒绝: %s' % msg)
            t_ok, _f, t_msg = self.cs.safe_truncate_file(link)
            self.assertFalse(t_ok, '软链逃逸截断未被拒绝: %s' % t_msg)
            self.assertEqual(os.path.getsize(victim), 4096, '白名单外受害文件被改写（软链逃逸）')
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    # ---------------- 面 4：数据/配置文件一律不可清空 ----------------
    def test_04_forbidden_types(self):
        for name in ('php.ini', 'panel.db', 'clean_history.json', 'nginx.conf', 'install.sql',
                     'ibdata1', 'dump.rdb', 'x.sock', 'libphp.so', 'index.php', 'app.py'):
            p = self.fixture(name)
            forbidden, why = self.cs.is_forbidden_file(p)
            self.assertTrue(forbidden, '受保护文件类型未被识别: %s' % name)
            t_ok, msg = self.ce.truncate_single_file(p)
            self.assertFalse(t_ok, '受保护文件被允许清空: %s (%s)' % (name, msg))
            # 底层截断/删除原语也必须自带同一判据（防止绕过入口直调）
            p_ok, _pf, p_msg = self.cs.safe_truncate_file(p)
            self.assertFalse(p_ok, 'safe_truncate_file 未复用禁用清单: %s (%s)' % (name, p_msg))
            d_ok2, _df, d_msg2 = self.cs.safe_delete_file(p)
            self.assertFalse(d_ok2, 'safe_delete_file 未复用禁用清单: %s (%s)' % (name, d_msg2))
            self.assertEqual(os.path.getsize(p), 1024, '受保护文件内容被改动: %s' % name)
        self.assertFalse(self.sc.is_valid_log_or_cache_file(self.fixture('a.sql'), cat_key='database'))
        self.assertFalse(self.sc.is_valid_log_or_cache_file(self.fixture('nginx.pid'), cat_key='database'))

    def test_05_critical_audit_rotations(self):
        protected = ['/var/log/wtmp', '/var/log/btmp', '/var/log/lastlog', '/var/log/secure',
                     '/var/log/auth.log', '/var/log/audit/audit.log', '/var/log/wtmp.1',
                     '/var/log/btmp.1', '/var/log/lastlog.1', '/var/log/auth.log.2.gz',
                     '/var/log/secure.1', '/var/log/audit/audit.log.20260101']
        for p in protected:
            self.assertTrue(self.cs.is_critical_audit_log(p), '轮转/活跃审计日志未被保护: %s' % p)
            t_ok, _f, t_msg = self.cs.safe_truncate_file(p)
            self.assertFalse(t_ok, '审计日志被允许截断: %s (%s)' % (p, t_msg))
            d_ok, _f2, d_msg = self.cs.safe_delete_file(p)
            self.assertFalse(d_ok, '审计日志被允许删除: %s (%s)' % (p, d_msg))
        self.assertFalse(self.cs.is_critical_audit_log('/var/log/messages.1'))

    # ---------------- 面 1：白名单内正常清理 ----------------
    def test_06_fixture_normal_ops(self):
        logs = os.path.join(self.tmp, 'logs')
        os.makedirs(logs, exist_ok=True)
        big = self.fixture('logs/app.log', b'Y' * (1024 * 1024))
        arch = self.fixture('logs/app.log.1', b'Y' * 2048)
        old = 1.0
        os.utime(arch, (old, old))
        found = self.sc.scan_directory_files(logs, cat_key='cache')
        names = sorted(f['name'] for f in found)
        self.assertIn('app.log', names)
        self.assertIn('app.log.1', names)
        self.assertTrue(self.sc.is_archive_or_rotated('app.log.1'))
        ok, msg = self.ce.truncate_single_file(big)
        self.assertTrue(ok, '白名单内活跃日志截断失败: %s' % msg)
        self.assertEqual(os.path.getsize(big), 0)
        self.assertTrue(os.path.exists(big))
        ok, _f, msg = self.cs.safe_delete_file(arch)
        self.assertTrue(ok, '白名单内归档日志删除失败: %s' % msg)
        self.assertFalse(os.path.exists(arch))

    # ---------------- 面 5：失败路径如实报错 ----------------
    def test_07_failures_honest(self):
        ok, _f, msg = self.cs.safe_delete_file(os.path.join(self.tmp, 'no_such.log'))
        self.assertFalse(ok)
        self.assertIn('文件不存在', msg)
        ok, _f, msg = self.cs.safe_delete_file(self.tmp)
        self.assertFalse(ok, '目录不能被删除')
        ok, _f, msg = self.cs.safe_truncate_file(self.tmp)
        self.assertFalse(ok, '目录不能被截断')
        ok, _f, msg = self.cs.safe_delete_file(self.fixture('again.log'))
        self.assertTrue(ok)
        ok2, _f, msg2 = self.cs.safe_delete_file(os.path.join(self.tmp, 'again.log'))
        self.assertFalse(ok2, '重复删除必须如实回不存在')

    # ---------------- 面 1/面 5：分类限定与自身产物 ----------------
    def test_08_category_scope(self):
        web_log = self.fixture('cat/web_access.log', b'Y' * 4096)
        sys_log = self.fixture('cat/syslog', b'Y' * 4096)
        orig_scan = self.ce.scan_all_categories
        orig_yf = self.ce.yf
        self.ce.yf = None  # 夹具进程内不做 journal/包缓存/信号刷新
        self.ce.scan_all_categories = lambda *a, **k: ({'categories': {}}, [
            {'path': web_log, 'name': 'web_access.log', 'size': 4096, 'mtime': 1.0, 'category': 'web'},
            {'path': sys_log, 'name': 'syslog', 'size': 4096, 'mtime': 1.0, 'category': 'system'},
        ])
        try:
            from clean_scanner import is_archive_or_rotated as _a  # noqa: F401
            rec = self.ce.execute_clean({'categories': ['web'], 'retention_days': 7,
                                         'size_threshold_mb': 0, 'clean_journal': False,
                                         'clean_pkg_cache': False})
        finally:
            self.ce.scan_all_categories = orig_scan
            self.ce.yf = orig_yf
        self.assertEqual(rec['scanned_files'], 2)
        self.assertEqual(rec['cleaned_files'], 1, '未勾选的 system 分类被误清理')
        self.assertEqual(os.path.getsize(web_log), 0, '勾选的 web 分类日志未被处理')
        self.assertEqual(os.path.getsize(sys_log), 4096, '未勾选的分类文件被改动')
        self.assertEqual([d['path'] for d in rec['details']], [web_log])

    # ---------------- 面 6：结构性断言（抗注释/if False 蒙混） ----------------
    def test_09_source_structure(self):
        sec = read_text(os.path.join(PLUGIN, 'clean_security.py'))
        scr = read_text(os.path.join(PLUGIN, 'clean_scanner.py'))
        exe = read_text(os.path.join(PLUGIN, 'clean_executor.py'))
        idx = read_text(os.path.join(PLUGIN, 'index.py'))

        self.assertIn('realpath', sec, 'is_safe_path 未做软链真实路径校验')
        self.assertIn('GLOB_META_CHARS', sec, '缺少通配符拒绝常量')
        self.assertIn("'\\0' in target_path", sec, '缺少空字节拒绝')
        self.assertIn('def is_forbidden_file', sec, '缺少禁用清单判据函数')
        for const in ('FORBIDDEN_EXTENSIONS', 'FORBIDDEN_BASENAMES', 'FORBIDDEN_PATH_SEGMENTS'):
            self.assertIn(const, sec, '判据常量未收敛到 clean_security: %s' % const)
            self.assertNotIn('%s = {' % const, scr, 'clean_scanner 仍重复定义判据常量: %s' % const)
        self.assertIn('_rotation_base_candidates', sec, '缺少审计日志轮转后缀归一化')

        # safe_truncate_file / safe_delete_file 必须调用 is_forbidden_file（ast 判定真实调用）
        tree = ast.parse(sec)
        calls = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ('safe_truncate_file', 'safe_delete_file'):
                names = set()
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        names.add(getattr(f, 'id', None) or getattr(f, 'attr', None))
                calls[node.name] = names
        self.assertIn('is_forbidden_file', calls.get('safe_truncate_file', set()),
                      'safe_truncate_file 未复用禁用清单判据')
        self.assertIn('is_forbidden_file', calls.get('safe_delete_file', set()),
                      'safe_delete_file 未复用禁用清单判据')

        # truncate_single_file 必须调用 is_valid_log_or_cache_file
        tree = ast.parse(exe)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'truncate_single_file':
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        names.add(getattr(f, 'id', None) or getattr(f, 'attr', None))
        self.assertIn('is_valid_log_or_cache_file', names, 'truncate_single_file 未复用日志判据')
        self.assertIn('is_critical_audit_log', names, 'truncate_single_file 未做审计保护')

        # execute_clean 必须按 category 过滤
        self.assertIn("item.get('category')", exe, 'execute_clean 未按勾选分类过滤')
        self.assertIn('selected_categories', exe)
        # is_valid_log_or_cache_file 必须复用 is_forbidden_file
        self.assertIn('is_forbidden_file(norm_path)', scr, '扫描器判据未复用禁用清单')
        # do_truncate_file 必须做 str 类型守卫（此前裸 .strip() 会 500）
        self.assertIn("isinstance(filepath, str)", idx, 'do_truncate_file 缺少类型守卫')

    # ---------------- 面 6/面 4：前端转义 ----------------
    def test_10_frontend_escaping(self):
        src = strip_js_comments(read_text(HTML))
        self.assertIn('function cleanEsc(', src, '缺少 HTML 转义函数')
        for sink in ("cleanEsc(res.msg)", "cleanEsc(item.name)", "cleanEsc(item.path)",
                     "cleanEsc(d.path)", "cleanEsc(realPath)"):
            self.assertIn(sink, src, '未转义的回显点: %s' % sink)
        self.assertNotIn('+ item.path +', src, '日志路径仍原样拼进 HTML')
        self.assertNotIn("""alert-danger">' + res.msg""", src, '后端消息仍原样拼进 HTML')
        self.assertIn('function cleanEsc', src)
        # escape/unescape 仍用于 onclick 传参（引号安全）
        self.assertIn('escape(item.path)', src)
        # 每个 ajax 都必须带 .fail()
        self.assertGreaterEqual(src.count('.fail('), src.count('$.post('))


if __name__ == '__main__':
    unittest.main(verbosity=2)
