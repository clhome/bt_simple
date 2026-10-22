# coding: utf-8
"""P1-8 守卫：插件 install.sh 必须进严格模式，`|| true` 只减不增（棘轮）。

## 背景（为什么需要这个文件）

整改前实测：`plugins/*/install.sh` 共 36 个，**0 个**用 `set -e`，**0 个**有 ERR trap，
`|| true` 共 49 处。结果是「装失败」在面板上永远显示成「安装完成」——最典型的样例是
`fail2ban/install.sh:42,43,52,57,63`（`apt-get update/install ... || true`）与
`php-apt:155,163`（批量扩展 `apt-get install ... || true`）。

本文件钉死三件事：

1. **首批 4 个**（`fail2ban` / `php` / `php-apt` / `php-yum`，都是基础组件或 `|| true` 大户）
   必须有 `set -euo pipefail` + `trap ... ERR` + `source scripts/lib_install_report.sh`
   （且找不到库时必须**明确报错退出**，不能静默跳过）。
2. **棘轮**：`STRICT_MODE_PENDING` 是「整改后仍然没有严格模式」的 install.sh 清单
   （实测 36 - 4 = 32 个），`BARE_TRUE_OR_IGNORE` 是 `plugins/*/install.sh` 里
   `|| true` 的实测基数（整改后 13 处）。两者都**只减不增**——新插件必须带严格模式；
   想放宽只能显式改这两个常量，那是一次可见的、会被 review 到的让步。
3. **剩下的 `|| true` 必须写明为什么留**：首批 4 个文件里每一处保留下来的
   `|| true` 都必须在同一行带 `yf-keep:` 理由，并且实际条数与 `KEEP_LEDGER`
   里登记的台账一致（台账同步写进安装报告的 notes，UI/审计可见）。

另外还有三个**行为**用例（不能只做静态）：

* A：`yf_optional_step` 配必失败命令 -> 不退出，报告 `missing` 里有该条（`json.load` 校验）；
* B：`yf_require_step` 配必失败命令 -> 非零退出 + stderr 含 `[ERROR]` 与描述；
* C：桩环境（`BASH_ENV` 注入的 shell 函数把 apt-get/yum/dnf/systemctl/sh/bash 全部
  替换成「必失败」并在 stderr 打 `[STUB]`）下真跑 install.sh -> 退出码非 0、
  失败原因明确、**不是** `unbound variable` 崩溃。

## 红线（改动本文件前请先读）

* **绝对不许真机执行包管理器 / 服务管理命令。** 桩由 `STUB_SHIM` 提供：函数定义
  **优先于 PATH 查找**，所以即使脚本里写死了 `PATH=/bin:/sbin:...`，跑到 Linux CI 上
  也不会真的调用 `apt-get`。`mkdir`/`touch` 也被 no-op 掉（只有报告目录放行），
  避免桩测试往 `/run`、`/var`、`/www` 里写东西。
* 每个子进程都带超时，卡死直接判失败。
* 用例 C 的入口选择有讲究：`php/install.sh install <不支持版本>` 走 P0-4 拦截的
  `exit 1`；`fail2ban`/`php-apt`/`php-yum` 走「桩命令失败 -> 装不上 -> 非 0」。
  **不能**用「缺少参数」那条路（那条历史上是 `exit 0`，提前 exit 0 不算通过）。
"""
import json
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')
SCRIPTS = os.path.join(ROOT, 'scripts')

LIB_SH = os.path.join(SCRIPTS, 'lib_install_report.sh')

#: 首批整改范围（基础组件 / 曾是 `|| true` 大户）。
FIRST_BATCH = ['fail2ban', 'php', 'php-apt', 'php-yum']

#: 整改后实测：仍然**没有**严格模式的 install.sh（36 - 4 = 32）。
#: 棘轮口径：当前集合必须是它的子集；新增插件不得出现在这里。
STRICT_MODE_PENDING = [
    'apache', 'clean', 'data_query', 'docker', 'gitea', 'jdk', 'linux_sys_opt',
    'mariadb', 'mongodb', 'mysql', 'ollama', 'op_load_balance', 'op_waf',
    'openresty', 'pg_docker', 'pgadmin', 'php-guard', 'phpmyadmin',
    'postgresql', 'pureftp', 'python_yf', 'redis', 'rsyncd', 'sphinx',
    'supervisor', 'swap', 'task_manager', 'valkey', 'varnish', 'webssh',
    'webstats', 'yufeng_systemd',
]

#: 整改后实测：`plugins/*/install.sh` 里 `|| true`（代码位，不含注释）的总数。
#: 整改前是 49；首批 4 个文件从 48 -> 12，linux_sys_opt 的 1 处未动。
BARE_TRUE_OR_IGNORE = 13

#: 首批 4 个文件整改后仍然保留的 `|| true` 台账（代码位条数）。
#: 逐条理由见各文件里的 `# yf-keep:` 行尾注释与报告的 notes。
KEEP_LEDGER = {
    'fail2ban': 7,   # clean_leftover(): rm -rf / rm -f / rmdir 清理残留，路径不存在属正常
    'php': 3,        # 中间编译目录 rm -rf ×2 + systemctl status | tail 纯诊断输出
    'php-apt': 1,    # systemctl status | tail 纯诊断输出
    'php-yum': 1,    # systemctl status | tail 纯诊断输出
}

#: 允许保留下来的 `|| true` 只允许出现在这些命令形态上（清理/诊断）。
KEEP_ALLOWED_PREFIX = ('rm -rf', 'rm -f', 'rmdir', 'systemctl status')

#: 桩：把「真的会改系统」的命令全部换成必失败的 shell 函数。
#: 函数优先于 PATH 查找，所以无论脚本怎么重设 PATH 都拦得住。
STUB_SHIM = r'''# P1-8 用例桩（testsuite/test_plugin_install_strict_mode.py 生成）
apt-get() { echo "[STUB] apt-get $*" >&2; return 100; }
apt() { echo "[STUB] apt $*" >&2; return 100; }
dpkg() { echo "[STUB] dpkg $*" >&2; return 100; }
dnf() { echo "[STUB] dnf $*" >&2; return 100; }
yum() { echo "[STUB] yum $*" >&2; return 100; }
rpm() { echo "[STUB] rpm $*" >&2; return 100; }
systemctl() { echo "[STUB] systemctl $*" >&2; return 100; }
service() { echo "[STUB] service $*" >&2; return 100; }
fail2ban-client() { echo "[STUB] fail2ban-client $*" >&2; return 100; }
add-apt-repository() { echo "[STUB] add-apt-repository $*" >&2; return 100; }
useradd() { return 0; }
groupadd() { return 0; }
python3() { echo "[STUB] python3 $*" >&2; return 100; }
bash() { echo "[STUB] bash $*" >&2; return 100; }
sh() { echo "[STUB] sh $*" >&2; return 100; }
curl() { return 100; }
wget() { return 100; }
# 卸载路径会 rm -rf 系统目录：桩成 no-op，保证桩测试绝不会真删东西
rm() { echo "[STUB] rm $*" >&2; return 0; }
rmdir() { echo "[STUB] rmdir $*" >&2; return 0; }
tar() { echo "[STUB] tar $*" >&2; return 0; }
mkdir() {
	local _last="${!#}"
	case "$_last" in
		"${YF_INSTALL_REPORT_DIR%/}"*) /usr/bin/mkdir -p "$_last" ;;
		*) return 0 ;;
	esac
}
touch() { return 0; }
'''

BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    '/bin/bash',
    '/usr/bin/bash',
]


def find_posix_bash():
    """返回可用的 POSIX bash 路径（排除 Windows 上的 WSL 启动器），找不到返回 None。"""
    candidates = [p for p in BASH_CANDIDATES if os.path.exists(p)]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


def git_bash_path(path):
    """把 Windows 路径转成 Git Bash 能直接用的形式（C:\\a\\b -> C:/a/b）。"""
    return str(path).replace('\\', '/')


def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def install_sh(plugin):
    return os.path.join(PLUGINS, plugin, 'install.sh')


def code_lines(text):
    """返回 [(行号, 代码部分)]：丢掉整行注释与行尾注释。

    `|| true` 的计数必须只看**代码位**，否则文件里解释「为什么保留」的注释
    会把计数抬上去，棘轮就失去意义（也就没法证明真的在减少）。
    """
    rows = []
    for idx, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('#'):
            continue
        rows.append((idx, line.split(' #')[0]))
    return rows


def count_bare_true(text):
    """代码位 `|| true` 的条数。"""
    return sum(1 for _, code in code_lines(text) if re.search(r'\|\|\s*true', code))


def bare_true_lines(text):
    """代码位里带 `|| true` 的 (行号, 原始行) 列表。"""
    out = []
    for idx, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith('#'):
            continue
        if re.search(r'\|\|\s*true', raw.split(' #')[0]):
            out.append((idx, raw))
    return out


def all_install_scripts():
    return sorted(glob.glob(os.path.join(PLUGINS, '*', 'install.sh')))


def plugin_name(path):
    return os.path.basename(os.path.dirname(path))


def has_strict_mode(text):
    """`set -euo pipefail`（或等价的 set -e + set -u + set -o pipefail）+ `trap ... ERR`。"""
    has_set = bool(re.search(r'(?m)^\s*set -euo pipefail\s*$', text))
    has_trap = bool(re.search(r'(?m)^\s*trap\s+.+ERR', text))
    return has_set and has_trap


class FirstBatchStrictModeTest(unittest.TestCase):
    """① 首批 4 个 install.sh：严格模式 + ERR trap + 规范库。"""

    def test_01_first_batch_files_exist(self):
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                self.assertTrue(os.path.isfile(install_sh(name)),
                                '找不到 %s' % install_sh(name))

    def test_02_set_euo_pipefail_present(self):
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertRegex(text, r'(?m)^\s*set -euo pipefail\s*$',
                                 '%s/install.sh 没有 `set -euo pipefail`（严格模式被回退了？）'
                                 % name)

    def test_03_err_trap_prints_script_line_and_command(self):
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                traps = re.findall(r'(?m)^\s*trap\s+.+$', text)
                err_traps = [t for t in traps if re.search(r'\bERR\b', t)]
                self.assertTrue(err_traps,
                                '%s/install.sh 没有 ERR trap' % name)
                joined = ' '.join(err_traps)
                # trap 必须能报出「脚本名 + 行号 + 失败命令」这三要素
                self.assertIn('BASH_SOURCE', joined,
                              '%s 的 ERR trap 没打印脚本名' % name)
                self.assertIn('LINENO', joined,
                              '%s 的 ERR trap 没打印行号' % name)
                self.assertIn('BASH_COMMAND', joined,
                              '%s 的 ERR trap 没打印失败命令' % name)
                self.assertRegex(joined, r'exit 1',
                                 '%s 的 ERR trap 没有 exit 1' % name)

    def test_04_sources_shared_report_library(self):
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertIn('lib_install_report.sh', text,
                              '%s/install.sh 没有 source 共享规范库 scripts/lib_install_report.sh'
                              % name)
                # 库必须真的被 source（而不是只写在注释里）
                self.assertRegex(text, r'(?m)^\s*\.\s+"?\$_yf_report_lib"?\s*$',
                                 '%s/install.sh 没有真正 source 规范库（应有 `. "$_yf_report_lib"`）'
                                 % name)
                # 兼容两种路径：仓库内直跑 + 已安装面板
                self.assertIn('/www/server/yufeng_panel/scripts/lib_install_report.sh', text,
                              '%s/install.sh 没有「已安装面板」路径兜底' % name)
                self.assertRegex(text, r'\.\./\.\./scripts/lib_install_report\.sh',
                                 '%s/install.sh 没有「仓库内直跑」相对路径' % name)

    def test_05_missing_library_is_a_hard_error(self):
        """找不到规范库时必须明确报错退出，不能静默跳过。"""
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertIn('[ERROR] 缺少共享规范库', text,
                              '%s/install.sh 找不到库时没有明确报错' % name)
                idx = text.find('[ERROR] 缺少共享规范库')
                tail = text[idx:idx + 600]
                self.assertRegex(tail, r'(?m)^\s*exit 1\s*$',
                                 '%s/install.sh 找不到库时没有 exit 1（静默跳过）' % name)

    def test_06_first_batch_is_not_in_pending_baseline(self):
        pending = set(STRICT_MODE_PENDING)
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                self.assertNotIn(name, pending,
                                 '%s 已经整改，必须从 STRICT_MODE_PENDING 里删掉' % name)


class StrictModeRatchetTest(unittest.TestCase):
    """② 棘轮：仍无严格模式的 install.sh 清单只减不增。"""

    def test_07_pending_list_matches_reality(self):
        scripts = all_install_scripts()
        self.assertGreaterEqual(len(scripts), 36,
                                '扫描到的 plugins/*/install.sh 只有 %d 个，扫描面失效？'
                                % len(scripts))
        actual = {plugin_name(p) for p in scripts
                  if not has_strict_mode(read_text(p))}
        baseline = set(STRICT_MODE_PENDING)
        new_offenders = sorted(actual - baseline)
        self.assertEqual(new_offenders, [],
                         '这些 install.sh 没有严格模式，又不在基线清单里（新增违规）：%s\n'
                         '—— 新插件必须带 `set -euo pipefail` + ERR trap；'
                         '确需放宽请显式把它加进 STRICT_MODE_PENDING（一次可见的让步）'
                         % new_offenders)
        # 只减不增：修掉一个就该顺手把它从清单里删掉
        fixed = sorted(baseline - actual)
        self.assertEqual(fixed, [],
                         '这些 install.sh 已经有严格模式了，请从 STRICT_MODE_PENDING 删除：%s'
                         % fixed)

    def test_08_pending_baseline_never_grows(self):
        self.assertLessEqual(len(STRICT_MODE_PENDING), 32,
                             'STRICT_MODE_PENDING 变大了（放宽了棘轮）：%d > 32'
                             % len(STRICT_MODE_PENDING))
        self.assertEqual(len(STRICT_MODE_PENDING), len(set(STRICT_MODE_PENDING)),
                         'STRICT_MODE_PENDING 里有重复项')

    def test_09_bare_true_total_never_grows(self):
        total = 0
        detail = {}
        for path in all_install_scripts():
            n = count_bare_true(read_text(path))
            if n:
                detail[plugin_name(path)] = n
            total += n
        self.assertLessEqual(
            total, BARE_TRUE_OR_IGNORE,
            'plugins/*/install.sh 的 `|| true` 共 %d 处，超过基线 %d\n分布：%s\n'
            '—— 吞失败必须换成 yf_optional_step（记进缺失清单）或 yf_require_step（失败即中止）'
            % (total, BARE_TRUE_OR_IGNORE, sorted(detail.items())))

    def test_10_first_batch_keeps_only_documented_bare_true(self):
        """首批 4 个文件：剩下的 `|| true` 必须逐条写在台账里、带 yf-keep 理由。"""
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertEqual(count_bare_true(text), KEEP_LEDGER[name],
                                 '%s/install.sh 的 `|| true` 条数与台账 KEEP_LEDGER[%r]=%d 不一致'
                                 % (name, name, KEEP_LEDGER[name]))
                for lineno, raw in bare_true_lines(text):
                    self.assertIn('yf-keep', raw,
                                  '%s/install.sh:%d 保留了 `|| true` 却没写 `# yf-keep:` 理由：%s'
                                  % (name, lineno, raw.strip()))
                    code = raw.split(' #')[0].strip()
                    self.assertTrue(
                        any(code.startswith(p) for p in KEEP_ALLOWED_PREFIX),
                        '%s/install.sh:%d 保留的 `|| true` 既不是清理也不是诊断输出，'
                        '必须改成 yf_optional_step / yf_require_step：%s'
                        % (name, lineno, code))

    def test_11_keep_reasons_reach_the_report(self):
        """「为什么留」不能只写在源码注释里：报告的 notes 里也要有。"""
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertIn('_yf_report_keep_notes()', text,
                              '%s/install.sh 没有把保留理由写进报告的 notes' % name)
                self.assertRegex(text, r'(?m)^\s*_yf_report_keep_notes\s*$',
                                 '%s/install.sh 定义了保留理由却没调用它' % name)

    def test_12_first_batch_uses_report_steps(self):
        """首批文件必须真的用上两个动作函数（否则严格模式等于没接上）。"""
        for name in FIRST_BATCH:
            with self.subTest(plugin=name):
                text = read_text(install_sh(name))
                self.assertIn('yf_install_report_init', text,
                              '%s/install.sh 没有初始化安装报告' % name)
                self.assertIn('yf_install_report_finish', text,
                              '%s/install.sh 没有落盘安装报告' % name)
                self.assertGreaterEqual(text.count('yf_optional_step'), 3,
                                        '%s/install.sh 几乎没把可选步骤接进报告' % name)
                self.assertIn('yf_require_step', text,
                              '%s/install.sh 没有把必需步骤接进 yf_require_step' % name)


class LibrarySelfTest(unittest.TestCase):
    """③ 规范库自身：语法 + 4 个对外函数 + 报告路径口径。"""

    def setUp(self):
        self.text = read_text(LIB_SH)

    def test_13_library_passes_bash_n(self):
        bash = find_posix_bash()
        if not bash:
            self.skipTest('未找到可用的 POSIX bash')
        proc = subprocess.run([bash, '-n', LIB_SH], capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         'scripts/lib_install_report.sh 语法错误：%s'
                         % (proc.stderr or proc.stdout))

    def test_14_library_exposes_required_functions(self):
        for fn in ('yf_install_report_init', 'yf_optional_step', 'yf_require_step',
                   'yf_install_report_finish', 'yf_install_report_path'):
            with self.subTest(fn=fn):
                self.assertRegex(self.text, r'(?m)^%s\(\)\s*$' % fn,
                                 '规范库缺少函数 %s' % fn)
        for helper in ('yf_install_report_dir', 'yf_install_report_note',
                       'yf_install_report_fail'):
            with self.subTest(fn=helper):
                self.assertRegex(self.text, r'(?m)^%s\(\)\s*$' % helper,
                                 '规范库缺少辅助函数 %s' % helper)

    def test_15_report_path_convention(self):
        """报告路径口径：${serverPath:-/www/server}/plugin_install_report/<plugin>.json。"""
        self.assertIn('${serverPath:-/www/server}/plugin_install_report', self.text,
                      '规范库的报告目录不是 ${serverPath:-/www/server}/plugin_install_report')
        self.assertIn("printf '%s/%s.json'", self.text,
                      'yf_install_report_path 的输出格式不是 <dir>/<plugin>.json')
        # 必须允许测试/离线覆盖根目录，否则行为用例只能写真实 /www/server
        self.assertIn('YF_INSTALL_REPORT_DIR', self.text,
                      '规范库没有 YF_INSTALL_REPORT_DIR 覆盖口径')

    def test_16_library_has_no_new_dependency(self):
        """纯 bash：报告落盘不许依赖 jq / python。"""
        for forbidden in ('jq ', 'python3 ', 'python '):
            with self.subTest(token=forbidden):
                self.assertNotIn('$(' + forbidden, self.text,
                                 '规范库引用了外部依赖 %r' % forbidden.strip())


class BehaviourCaseTest(unittest.TestCase):
    """④ 行为用例 A/B/C（真跑 bash，全部带超时 + 桩环境）。"""

    @classmethod
    def setUpClass(cls):
        cls.bash = find_posix_bash()
        if not cls.bash:
            raise unittest.SkipTest('未找到可用的 POSIX bash')

    # ---------------- 公共夹具 ----------------
    def _run(self, script_text, extra_env=None, timeout=60, cwd=None):
        tmp = tempfile.mkdtemp(prefix='yf_p1_8_')
        self.addCleanup(shutil.rmtree, tmp, True)
        script = os.path.join(tmp, 'case.sh')
        with open(script, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(script_text)
        env = dict(os.environ)
        env['YF_INSTALL_REPORT_DIR'] = os.path.join(tmp, 'report')
        env.update(extra_env or {})
        proc = subprocess.run([self.bash, git_bash_path(script)],
                              cwd=cwd or ROOT, env=env,
                              capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
        return proc, tmp

    def _run_installer(self, plugin, args, timeout=60):
        """桩环境下真跑 install.sh。"""
        tmp = tempfile.mkdtemp(prefix='yf_p1_8_stub_')
        self.addCleanup(shutil.rmtree, tmp, True)
        shim = os.path.join(tmp, 'stub_shim.sh')
        with open(shim, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(STUB_SHIM)
        report_dir = os.path.join(tmp, 'report')
        env = dict(os.environ)
        env['BASH_ENV'] = git_bash_path(shim)
        env['YF_INSTALL_REPORT_DIR'] = report_dir
        proc = subprocess.run(
            [self.bash, git_bash_path(install_sh(plugin))] + list(args),
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout)
        return proc, report_dir

    def _assert_clean_failure(self, plugin, proc):
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotEqual(proc.returncode, 0,
                            '%s/install.sh 在桩环境下居然返回 0 —— '
                            '安装失败被吞掉了\nstdout=%s\nstderr=%s'
                            % (plugin, proc.stdout, proc.stderr))
        self.assertNotIn('unbound variable', out,
                         '%s/install.sh 在桩环境下崩在 set -u（unbound variable），'
                         '这不是「明确的失败原因」\n%s' % (plugin, out))
        has_reason = any(k in out for k in ('[ERROR]', '失败', '不支持', '拒绝'))
        self.assertTrue(has_reason,
                        '%s/install.sh 失败但没有任何明确原因\n%s' % (plugin, out))

    # ---------------- 用例 A ----------------
    def test_17_optional_step_failure_does_not_exit_and_is_recorded(self):
        script = (
            '#!/bin/bash\n'
            'set -euo pipefail\n'
            '. "%s"\n'
            'yf_install_report_init yf_case_a\n'
            'yf_optional_step "用例A：不存在的命令" command_that_does_not_exist_xyz\n'
            'yf_optional_step --quiet "用例A：false" false\n'
            'yf_install_report_finish\n'
            'echo "REACHED_END rc=$YF_LAST_STEP_RC"\n'
        ) % git_bash_path(LIB_SH)
        proc, tmp = self._run(script)
        self.assertEqual(proc.returncode, 0,
                         'yf_optional_step 失败后不该退出（set -e 下必须被吞成 0）\n'
                         'stdout=%s\nstderr=%s' % (proc.stdout, proc.stderr))
        self.assertIn('REACHED_END', proc.stdout,
                      '脚本没跑到 yf_optional_step 之后')
        self.assertIn('[WARN]', proc.stderr,
                      'yf_optional_step 失败没有打 [WARN]（又变成静默了）')

        report_path = os.path.join(tmp, 'report', 'yf_case_a.json')
        self.assertTrue(os.path.isfile(report_path),
                        '报告文件不存在：%s' % report_path)
        with open(report_path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)   # 必须能被 Python 解析
        self.assertEqual(data['plugin'], 'yf_case_a')
        self.assertEqual(data['status'], 'degraded',
                         '有缺失项时 status 应为 degraded，实际 %r' % data.get('status'))
        steps = [m['step'] for m in data['missing']]
        self.assertTrue(any('不存在的命令' in s for s in steps),
                        'missing 里没有失败的那一条：%r' % steps)
        entry = [m for m in data['missing'] if '不存在的命令' in m['step']][0]
        self.assertEqual(entry['exit_code'], 127,
                         '缺失项的退出码应为 127（command not found），实际 %r'
                         % entry['exit_code'])
        self.assertEqual(entry['command'], 'command_that_does_not_exist_xyz',
                         '缺失项没有记录命令首词：%r' % entry['command'])
        self.assertEqual(data['missing_count'], 2,
                         '两条可选步骤都失败，missing_count 应为 2，实际 %r'
                         % data['missing_count'])
        # 摘要里必须真的打印缺失清单
        self.assertIn('缺失项', proc.stdout,
                      'yf_install_report_finish 没有打印缺失清单摘要')

    def test_18_optional_step_success_writes_clean_report(self):
        script = (
            '#!/bin/bash\n'
            'set -euo pipefail\n'
            '. "%s"\n'
            'yf_install_report_init yf_case_a_ok\n'
            'yf_optional_step "用例A-ok：肯定成功的命令" true\n'
            'yf_install_report_finish\n'
        ) % git_bash_path(LIB_SH)
        proc, tmp = self._run(script)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('无缺失项', proc.stdout,
                      '没有缺失项时应打印「无缺失项」，实际输出：%s' % proc.stdout)
        with open(os.path.join(tmp, 'report', 'yf_case_a_ok.json'), 'r',
                  encoding='utf-8') as fp:
            data = json.load(fp)
        self.assertEqual(data['missing'], [])
        self.assertEqual(data['status'], 'ok')

    # ---------------- 用例 B ----------------
    def test_19_require_step_failure_aborts_nonzero(self):
        script = (
            '#!/bin/bash\n'
            'set -euo pipefail\n'
            '. "%s"\n'
            'yf_install_report_init yf_case_b\n'
            'yf_require_step "用例B：必需步骤必然失败" false\n'
            'echo "SHOULD_NOT_REACH"\n'
        ) % git_bash_path(LIB_SH)
        proc, tmp = self._run(script)
        self.assertNotEqual(proc.returncode, 0,
                            'yf_require_step 失败后必须非零退出')
        self.assertNotIn('SHOULD_NOT_REACH', proc.stdout,
                         'yf_require_step 失败后脚本还在继续执行（没有真的中止）')
        self.assertIn('[ERROR]', proc.stderr,
                      'yf_require_step 失败没有打 [ERROR]：%s' % proc.stderr)
        self.assertIn('用例B：必需步骤必然失败', proc.stderr,
                      'stderr 里没有步骤描述：%s' % proc.stderr)

        report_path = os.path.join(tmp, 'report', 'yf_case_b.json')
        self.assertTrue(os.path.isfile(report_path),
                        '失败时也必须落盘报告（否则面板只看到一行日志）')
        with open(report_path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['failed_count'], 1)
        self.assertIn('用例B', data['failed'][0]['step'])

    # ---------------- 用例 C ----------------
    def test_20_stub_run_fail2ban_fails_loudly(self):
        """桩环境下装不上 fail2ban -> 必须非 0 退出 + 原因明确 + 不是 unbound 崩溃。"""
        proc, report_dir = self._run_installer('fail2ban', ['install', '1.2.0'])
        self._assert_clean_failure('fail2ban', proc)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('[STUB]', out,
                      '桩没生效（没有任何 [STUB] 输出），说明真的调用了系统命令！\n%s' % out)
        self.assertIn('[ERROR] 必需步骤失败', out,
                      '没有走「必需步骤失败」路径：%s' % out)
        self.assertIn('fail2ban', out)
        report_path = os.path.join(report_dir, 'fail2ban.json')
        self.assertTrue(os.path.isfile(report_path),
                        '失败报告没落盘：%s' % report_path)
        with open(report_path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        self.assertEqual(data['status'], 'failed')
        self.assertGreaterEqual(data['failed_count'], 1,
                                'fail2ban 安装失败，报告里 failed 却为空')
        self.assertGreaterEqual(data['missing_count'], 1,
                                'apt 源刷新/dpkg 修复这类可选步骤的失败也应进缺失清单')

    def test_21_stub_run_php_rejects_delisted_version_without_crash(self):
        """php/install.sh：限定版本 -> 走 P0-4 拒绝分支（确定性的失败路径，不装任何东西）。"""
        proc, _report_dir = self._run_installer('php', ['install', '73'])
        self._assert_clean_failure('php', proc)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('拒绝安装 PHP73', out,
                      'php/install.sh 没有走「下架版本默认拒绝」分支：%s' % out)

    def test_22_stub_run_php_subinstaller_failure_aborts(self):
        """php/install.sh：桩把 versions/<NN>/install.sh 打成失败 -> 必须中止。

        这条不能用「缺少参数」那条路（历史上是 exit 0，提前 exit 0 不算通过）。
        """
        proc, _report_dir = self._run_installer('php', ['install', '82'])
        self._assert_clean_failure('php', proc)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('[STUB]', out,
                      '桩没生效（没有任何 [STUB] 输出）\n%s' % out)
        self.assertIn('[ERROR] 必需步骤失败', out,
                      'php 本体安装失败没有走 yf_require_step 的失败出口：%s' % out)

    def test_23_stub_run_php_apt_fails_loudly(self):
        """php-apt：桩让 apt-get update 失败 -> 必须非 0 退出且原因明确。"""
        proc, report_dir = self._run_installer('php-apt', ['install', '82'])
        self._assert_clean_failure('php-apt', proc)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('[STUB]', out,
                      '桩没生效（没有任何 [STUB] 输出）\n%s' % out)
        self.assertIn('[ERROR]', out,
                      'php-apt 失败没有 [ERROR] 文案：%s' % out)
        report_path = os.path.join(report_dir, 'php-apt.json')
        self.assertTrue(os.path.isfile(report_path),
                        '失败报告没落盘：%s' % report_path)
        with open(report_path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        self.assertEqual(data['status'], 'failed')

    def test_24_stub_run_php_yum_fails_loudly(self):
        """php-yum：桩让 getos/yum/sh 全失败 -> 必须非 0 退出且原因明确。"""
        proc, _report_dir = self._run_installer('php-yum', ['install', '82'])
        self._assert_clean_failure('php-yum', proc)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('[STUB]', out,
                      '桩没生效（没有任何 [STUB] 输出）\n%s' % out)

    def test_26_stub_run_fail2ban_uninstall_succeeds_with_report(self):
        """卸载路径也要在严格模式下跑通：rc=0、报告 status=ok、不许 unbound 崩溃。

        rm/rmdir/tar 在桩里是 no-op，所以这条用例不会真的删任何系统目录。
        """
        proc, report_dir = self._run_installer('fail2ban', ['uninstall', '1.2.0'])
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotIn('unbound variable', out,
                         'fail2ban/install.sh uninstall 崩在 set -u：' + out)
        self.assertEqual(proc.returncode, 0,
                         'fail2ban 卸载在桩环境下应成功（清理类失败只记缺失项）：'
                         + repr(proc.stdout) + repr(proc.stderr))
        self.assertIn('卸载fail2ban成功', out)
        report_path = os.path.join(report_dir, 'fail2ban.json')
        self.assertTrue(os.path.isfile(report_path),
                        '卸载也要落盘报告：%s' % report_path)
        with open(report_path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        # 桩里 systemctl/apt-get 全部失败，而这批操作在卸载阶段都是「真可选」，
        # 所以期望：成功退出 + failed 为空 + 失败的那几条全部进 missing（不再静默吞掉）
        self.assertEqual(data['failed'], [],
                         '卸载时不该有「必需步骤失败」：%r' % data['failed'])
        self.assertEqual(data['status'], 'degraded',
                         '有可选步骤失败时 status 应为 degraded，实际 %r'
                         % data.get('status'))
        self.assertGreaterEqual(data['missing_count'], 3,
                                '桩里 systemctl/apt-get 都失败了，缺失清单却是空的（又静默了？）'
                                ': %r' % data['missing'])
        steps = ' '.join(m['step'] for m in data['missing'])
        self.assertIn('systemctl', steps,
                      'missing 里没有记录停止/禁用服务的失败：%s' % steps)

    def test_25_unsupported_action_is_rejected_before_dispatch(self):
        """动作白名单：错动作必须在下发到 versions/<NN>/install.sh 之前被拦下。"""
        for plugin in ('php', 'php-apt', 'php-yum'):
            with self.subTest(plugin=plugin):
                proc, _ = self._run_installer(plugin, ['restart', '82'])
                self._assert_clean_failure(plugin, proc)
                out = (proc.stdout or '') + (proc.stderr or '')
                self.assertIn('不支持的动作', out,
                              '%s/install.sh 没有拦下不支持的动作 restart：%s'
                              % (plugin, out))


if __name__ == '__main__':
    unittest.main(verbosity=2)
