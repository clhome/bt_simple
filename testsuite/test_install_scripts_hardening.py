# coding: utf-8
"""安装/更新脚本健壮性守卫（测评报告 P1-6）。

被测面：

* `scripts/install.sh` —— 严格模式（`set -euo pipefail`）、`die()` + `trap ERR`、
  磁盘/内存预检（口径对齐 `deploy.sh::check_system_resources()`）、组/用户幂等创建；
* `scripts/update.sh` —— 升级前备份（命名与 `deploy.sh` 一致，失败即停）；
* `scripts/lib.sh` + `scripts/install/*.sh` —— 依赖安装失败必须让退出码非 0，
  否则 `install.sh` 的 fail-stop 形同虚设。

三条硬约束（改动本文件前请先读懂）：

1. **禁止真机执行安装/更新脚本**。这里只做 `bash -n`、把预检函数从
   `install.sh` 里**抽出来**在子 shell 里跑（函数级单测）、以及静态断言。
   真跑 `install.sh` 会以 root 改系统，绝不允许出现在用例里。
2. **断言必须真能失败**。静态断言一律按行锚定（`^set -euo pipefail$` 等），
   把修复写进注释 / `if False:` 蒙混不过去；行为断言必须真跑 bash 并核对退出码。
   变异自证见 `test/p1_install_mutation_probe.py`（本地探针，`test/` 不入库）。
3. 预检读到的值允许用 `YF_FAKE_MEM_MB` / `YF_FAKE_DISK_MB` 覆盖，否则失败路径
   只能在「内存本来就小」的机器上复现，等于没测。
"""
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL_SH = os.path.join(ROOT, 'scripts', 'install.sh')
UPDATE_SH = os.path.join(ROOT, 'scripts', 'update.sh')
LIB_SH = os.path.join(ROOT, 'scripts', 'lib.sh')
INSTALL_DIR = os.path.join(ROOT, 'scripts', 'install')

# Windows 上 PATH 里的 `bash` 可能是 WSL 启动器（它无法执行本地脚本），
# 必须优先定位 Git Bash —— 与 testsuite/test_fail2ban_plugin.py 同一套候选。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    os.path.join(os.path.expanduser('~'), '.workbuddy-ai', 'binaries', 'PortableGit',
                 'versions', '1.2.0', 'bin', 'bash.exe'),
]


def find_posix_bash():
    """返回可用于执行/语法校验的 POSIX shell 路径，找不到返回 None。"""
    candidates = [p for p in BASH_CANDIDATES if os.path.exists(p)]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue  # 排除 WSL 启动器
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, timeout=30)
            if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
                return cand
        except Exception:
            continue
    return None


def read_text(path):
    with open(path, encoding='utf-8') as fp:
        return fp.read()


def extract_shell_function(src, name):
    """从 shell 源码里取出 `name()` / `function name()` 的完整定义文本。

    用大括号配平而不是「找到下一个 `}`」：函数体里有 `${VAR}`、`awk '{print $1}'`
    这类成对括号，只按行找会截断。
    """
    m = re.search(r'^(?:function\s+)?' + re.escape(name) + r'\s*\(\s*\)\s*\{', src, re.M)
    if not m:
        raise AssertionError('未找到 shell 函数定义: %s' % name)
    start = m.start()
    i = src.index('{', m.start())
    depth = 0
    while i < len(src):
        ch = src[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError('函数 %s 的大括号不配平' % name)


def run_bash(script_text, env_extra=None, bash=None):
    """把脚本交给 bash 执行，返回 (returncode, 合并输出)。"""
    bash = bash or find_posix_bash()
    if not bash:
        raise unittest.SkipTest('未找到可用的 POSIX shell（Windows 上的 bash 可能指向 WSL 启动器）')
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([bash, '-c', script_text], capture_output=True,
                          text=True, encoding='utf-8', errors='replace',
                          env=env, timeout=60)
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


class TestShellSyntax(unittest.TestCase):
    """所有被改动的脚本必须语法正确（bash -n，不执行）。"""

    @classmethod
    def setUpClass(cls):
        cls.bash = find_posix_bash()
        if not cls.bash:
            raise unittest.SkipTest('未找到可用的 POSIX shell')

    def test_01_bash_n_passes_for_every_touched_script(self):
        targets = [INSTALL_SH, UPDATE_SH, LIB_SH]
        targets += [os.path.join(INSTALL_DIR, n)
                    for n in sorted(os.listdir(INSTALL_DIR)) if n.endswith('.sh')]
        self.assertGreaterEqual(len(targets), 15, '扫描到的安装脚本数量异常，疑似扫描面失效')
        for path in targets:
            with self.subTest(script=os.path.relpath(path, ROOT)):
                proc = subprocess.run([self.bash, '-n', path], capture_output=True,
                                      text=True, timeout=60)
                self.assertEqual(proc.returncode, 0,
                                 'bash -n 失败: %s' % (proc.stderr or proc.stdout))


class TestInstallShStrictMode(unittest.TestCase):
    """install.sh 的失败语义：严格模式、die/trap、成功文案只走成功路径。"""

    @classmethod
    def setUpClass(cls):
        cls.src = read_text(INSTALL_SH)

    def test_02_strict_mode_enabled_after_variable_init(self):
        m = re.search(r'^set -euo pipefail$', self.src, re.M)
        self.assertIsNotNone(m, 'install.sh 缺少 `set -euo pipefail` 整行（必须独占一行，'
                                '写在注释里的不算）')
        init = re.search(r'^LOG_FILE=/var/log/yf-install\.log$', self.src, re.M)
        self.assertIsNotNone(init, '变量初始化行被改动，请同步更新本用例')
        self.assertLess(init.start(), m.start(),
                        '严格模式必须在变量初始化之后启用（否则 set -u 会在初始化期误杀）')

    def test_03_die_exits_nonzero_and_err_trap_is_installed(self):
        body = extract_shell_function(self.src, 'die')
        self.assertRegex(body, r'exit\s+"\$_code"',
                         'die() 必须真的以非 0 退出码结束（去掉 exit 即退回「静默继续」）')
        trap = re.search(r"^trap 'die [^']*' ERR$", self.src, re.M)
        self.assertIsNotNone(trap, "缺少 `trap 'die ...' ERR`（没有它，中间步骤失败不会中止）")

    def test_04_success_banner_only_reachable_on_success(self):
        # 只数「真正打印成功文案的语句」，注释里提到这句话不算
        banners = list(re.finditer(r'^echo .*Install completed', self.src, re.M))
        self.assertEqual(len(banners), 1,
                         '"Install completed" 必须只被打印一次（多出来的那处必然是无条件打印）')
        block_end = self.src.index('} 1> >(tee $LOG_FILE) 2>&1')
        self.assertGreater(banners[0].start(), block_end,
                           '成功文案必须在日志块结束之后，否则失败路径也会打印成功')
        # 严格模式与 ERR trap 都必须在日志块之前生效，块内的失败才拦得住
        self.assertLess(self.src.index('set -euo pipefail'), block_end)
        self.assertLess(re.search(r"^trap 'die [^']*' ERR$", self.src, re.M).start(), block_end)

    def test_05_precheck_function_exists_and_is_called_before_install(self):
        extract_shell_function(self.src, 'check_system_resources')
        call = re.search(r'^\s*if ! check_system_resources; then$', self.src, re.M)
        self.assertIsNotNone(call, 'check_system_resources 只定义不调用等于没有预检')
        self.assertIn('YF_FAKE_MEM_MB', self.src)
        self.assertIn('YF_FAKE_DISK_MB', self.src)
        # 预检必须在真正的安装步骤（用户/目录创建、下载、install/*.sh）之前
        for later in ('mkdir -p /www/server', 'bash scripts/install/${OSNAME}.sh'):
            self.assertLess(call.start(), self.src.index(later),
                            '预检必须在 %s 之前' % later)

    def test_06_group_and_user_creation_is_idempotent(self):
        self.assertRegex(self.src, r'getent group www',
                         'groupadd 前必须先判断用户组是否存在')
        self.assertRegex(self.src, r'id -u www',
                         'useradd 前必须先判断用户是否存在')
        self.assertLess(self.src.index('getent group www'), self.src.index('groupadd www'),
                        '判断必须写在 groupadd 之前')
        self.assertLess(self.src.index('id -u www'),
                        self.src.index('useradd -g www -s /usr/sbin/nologin www'),
                        '判断必须写在 useradd 之前')


class TestPrecheckBehavior(unittest.TestCase):
    """预检函数的行为断言：真的跑 bash，核对退出码与输出（不执行安装）。"""

    PREAMBLE = "WARN='[WARN]'; ERROR='[ERROR]'; SUCCESS='[OK]'\n"

    @classmethod
    def setUpClass(cls):
        cls.src = read_text(INSTALL_SH)
        cls.func = extract_shell_function(cls.src, 'check_system_resources')

    def _run_precheck(self, env_extra):
        script = ('set -euo pipefail\n'
                  + self.PREAMBLE
                  + self.func + '\n'
                  + 'if ! check_system_resources; then\n'
                  + '    echo "PRECHECK_FAIL"\n'
                  + '    exit 7\n'
                  + 'fi\n'
                  + 'echo "PRECHECK_OK"\n')
        return run_bash(script, env_extra)

    def test_07_low_memory_aborts(self):
        rc, out = self._run_precheck({'YF_FAKE_MEM_MB': '100'})
        self.assertEqual(rc, 7, '内存不足时必须让预检失败（退出码 7），实际输出: %s' % out)
        self.assertIn('PRECHECK_FAIL', out)
        self.assertNotIn('Install completed', out)

    def test_08_low_disk_aborts(self):
        rc, out = self._run_precheck({'YF_FAKE_MEM_MB': '4096', 'YF_FAKE_DISK_MB': '100'})
        self.assertEqual(rc, 7, '磁盘不足时必须让预检失败（退出码 7），实际输出: %s' % out)
        self.assertNotIn('Install completed', out)

    def test_09_enough_resources_passes(self):
        rc, out = self._run_precheck({'YF_FAKE_MEM_MB': '4096', 'YF_FAKE_DISK_MB': '51200'})
        self.assertEqual(rc, 0, '资源充足时必须放行，实际输出: %s' % out)
        self.assertIn('PRECHECK_OK', out)

    def test_10_die_plus_err_trap_stops_before_success_banner(self):
        """把 install.sh 里的 die() 与 trap 行原样搬进子 shell：失败必须中止，
        不得走到成功文案。"""
        die_src = extract_shell_function(self.src, 'die')
        trap_line = re.search(r"^trap 'die [^']*' ERR$", self.src, re.M).group(0)
        script = ('set -euo pipefail\n'
                  + "ERROR='[ERROR]'; LOG_FILE=/tmp/yf-install-test.log\n"
                  + die_src + '\n'
                  + trap_line + '\n'
                  + 'false\n'
                  + 'echo "Install completed"\n')
        rc, out = run_bash(script)
        self.assertNotEqual(rc, 0, '中间步骤失败必须非 0 退出，实际: %s' % out)
        self.assertNotIn('Install completed', out,
                         '失败路径绝不能打印成功文案')


class TestUpdateShBackup(unittest.TestCase):
    """update.sh 的升级前备份与失败即停。"""

    @classmethod
    def setUpClass(cls):
        cls.src = read_text(UPDATE_SH)

    def test_11_backup_function_defined_and_called_before_code_replacement(self):
        extract_shell_function(self.src, 'backup_before_update')
        call = re.search(r'^\s*if ! backup_before_update; then$', self.src, re.M)
        self.assertIsNotNone(call, 'backup_before_update 只定义不调用等于没有备份')
        self.assertLess(call.start(), self.src.index('echo "update bt_simple code start"'),
                        '备份必须发生在覆盖代码之前')
        # 命名必须与 deploy.sh 一致，否则 `deploy.sh rollback` 找不到这个回滚点
        self.assertIn('BACKUP_DIR=/www/backup', self.src)
        self.assertIn('yufeng_panel-${ts}.tar.gz', self.src)
        self.assertIn('--exclude=\'yufeng_panel/bin\'', self.src)

    def test_12_backup_failure_stops_update(self):
        self.assertIsNotNone(re.search(r'^\s*die "升级前备份失败[^"]*" 1$', self.src, re.M),
                             '备份失败必须以非 0 退出码中止更新')
        body = extract_shell_function(self.src, 'backup_before_update')
        self.assertEqual(body.count('return 0'), 1,
                         '除了最后一步成功返回，函数里不允许有静默放行（return 0）')
        self.assertRegex(body, r'return 1', '备份失败必须返回非 0')
        self.assertRegex(body, r'\[ ! -s "\$\{backup_file\}" \]',
                         'tar 返回 0 但文件为空同样是失败，必须拦下')


class TestDependencyFailurePropagation(unittest.TestCase):
    """lib.sh 的依赖安装失败必须让退出码非 0，并由 install/*.sh 传播出去。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = read_text(LIB_SH)

    def test_13_lib_sh_exits_nonzero_when_both_pip_sources_fail(self):
        lines = self.lib.splitlines()
        fallbacks = 0
        for idx, line in enumerate(lines):
            if not line.strip().startswith('if ! pip3 install'):
                continue
            if '/www/server/yufeng_panel/requirements.txt' not in line:
                continue
            fallbacks += 1
            window = '\n'.join(lines[idx:idx + 4])
            self.assertIn('exit 1', window,
                          '备源也失败时必须 exit 1，否则 install/*.sh 会当成安装成功：\n%s'
                          % window)
        self.assertEqual(fallbacks, 2, '两个备源分支都要有失败退出（找到 %d 处）' % fallbacks)
        self.assertGreaterEqual(self.lib.count('exit 1'), 3,
                                '版本专属依赖 (version/r*.txt) 安装失败同样要 exit 1')

    def test_14_install_subscripts_propagate_lib_failure(self):
        scripts = [n for n in sorted(os.listdir(INSTALL_DIR)) if n.endswith('.sh')]
        checked = 0
        for name in scripts:
            src = read_text(os.path.join(INSTALL_DIR, name))
            for line in src.splitlines():
                if 'bash lib.sh' not in line:
                    continue
                checked += 1
                with self.subTest(script=name):
                    self.assertIn('|| exit 1', line,
                                  'lib.sh 失败必须让子脚本退出码非 0（否则最后的 chmod 会把它抹平）：%s'
                                  % line)
        self.assertGreaterEqual(checked, 14, '扫描到的 lib.sh 调用点过少（%d），疑似扫描面失效' % checked)


if __name__ == '__main__':
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError):
            pass
    unittest.main(verbosity=2)
