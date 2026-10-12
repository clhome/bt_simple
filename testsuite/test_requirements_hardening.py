# coding: utf-8
"""P0-5 依赖供应链守卫：CVE 下界收紧 + 死依赖清理 + lock 生成方式。

对应测评报告「九、依赖供应链」九.1~九.8 与附录 B-5。守护四件事：

  1. 五个高危包的下界必须 >= CVE 修复版（gunicorn 22.0.0 / requests 2.32.4 /
     urllib3 2.0.7 / pillow 12.3.0 / pyyaml 5.4），且所在行写明 CVE 编号；
  2. 死依赖 chardet / flask-helper / supervisor 不再出现在 requirements.txt；
  3. 这些死依赖在全仓（web/ plugins/ scripts/ 等）确实零 import（静态扫描）；
  4. 报告误判为死依赖、实际在用的 pymongo / pymemcache / redis 必须保留；
  5. scripts/gen_requirements_lock.sh 存在、有 shebang、`bash -n` 通过，
     且 requirements.txt 注释指向它。

断言「真能失败」：本文件用 requirements.txt 的真实文本做正则解析，不硬编码常量；
`test/p0_deps_mutation_probe.py` 逐条回退版本下界、把死依赖加回，每条都让本文件变红。
"""
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REQ = os.path.join(ROOT, 'requirements.txt')
LOCK_SCRIPT = os.path.join(ROOT, 'scripts', 'gen_requirements_lock.sh')

#: 包名（小写）→ CVE 修复版下界
REQUIRED_LOWER_BOUNDS = {
    'gunicorn': '22.0.0',   # CVE-2024-1135 / CVE-2024-6827
    'requests': '2.32.4',   # CVE-2023-32681 / CVE-2024-35195 / CVE-2024-47081
    'urllib3': '2.0.7',     # CVE-2023-43804 / CVE-2023-45803
    'pillow': '12.3.0',     # CVE-2025-48379、CVE-2026-25990/40192/54058~59205
    'pyyaml': '5.4',        # CVE-2020-14343
}

#: 已删除的死依赖：requirements.txt 里的包名（小写）→ 全仓静态扫描的 import 名
REMOVED_DEAD_DEPS = {
    'chardet': 'chardet',
    'flask-helper': 'flask_helper',
    'supervisor': 'supervisor',
}

#: 报告称「无 import」但实测在用的可选驱动，必须保留（防过度清理）
STILL_USED_OPTIONAL_DRIVERS = ('pymongo', 'pymemcache', 'redis')

SCAN_DIRS = ('web', 'plugins', 'scripts', 'testsuite')
SCAN_FILES = ('panel_task.py', 'panel_tools.py')
SCAN_EXT = ('.py', '.sh')
EXCLUDE_DIRS = {'__pycache__', 'node_modules', '.git', 'data', 'logs', 'tmp'}
#: 扫描面下限：低于它说明扫描逻辑失效（而非「仓库很干净」），必须报错
MIN_SCAN_FILES = 300

IMPORT_RE = re.compile(r'^[ \t]*(?:from|import)[ \t]+([A-Za-z_][\w.]*)', re.M)

# Windows 上 PATH 里的 bash 常是 System32\bash.exe（WSL 启动器），不能执行本地脚本，
# 故优先定位 Git Bash（沿用 testsuite/test_fail2ban_plugin.py 的做法）。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    os.path.join(os.path.expanduser('~'), '.workbuddy-ai', 'binaries', 'PortableGit',
                 'versions', '1.2.0', 'bin', 'bash.exe'),
]


def _find_bash():
    """返回可用于 `bash -n` 的 POSIX shell 路径，找不到返回 None。"""
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
        except OSError:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read()


def _requirement_lines(text):
    """返回 [(包名小写, 约束串, 原始行)]，跳过空行与整行注释（保留行内注释在原始行里）。"""
    out = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        m = re.match(r'^([A-Za-z0-9_.\-]+)[ \t]*(.*)$', line)
        if m:
            out.append((m.group(1).lower(), m.group(2).strip(), raw))
    return out


def _vtuple(version):
    return tuple(int(x) for x in re.findall(r'\d+', version))


def _iter_source():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                if fn.endswith(SCAN_EXT):
                    yield os.path.join(root, fn)
    for rel in SCAN_FILES:
        path = os.path.join(ROOT, rel)
        if os.path.isfile(path):
            yield path


class RequirementsLowerBoundsTest(unittest.TestCase):
    """九.1~九.7：五个高危包的下界必须顶到 CVE 修复版，且注释写明 CVE。"""

    def setUp(self):
        self.lines = _requirement_lines(_read(REQ))

    def _lines_for(self, name):
        hits = [l for l in self.lines if l[0] == name]
        self.assertTrue(hits, 'requirements.txt 缺少包 %s' % name)
        return hits

    def test_01_lower_bounds_reach_cve_fixed_versions(self):
        for name, want in sorted(REQUIRED_LOWER_BOUNDS.items()):
            bounds = []
            for _n, spec, _raw in self._lines_for(name):
                m = re.search(r'>=[ \t]*([0-9][\w.\-]*)', spec)
                if m:
                    bounds.append(m.group(1))
            self.assertTrue(bounds, '%s 没有 >= 下界' % name)
            best = max(bounds, key=_vtuple)
            self.assertGreaterEqual(
                _vtuple(best), _vtuple(want),
                '%s 下界 %s 低于 CVE 修复版 %s' % (name, best, want))

    def test_02_bound_lines_document_cve(self):
        for name in REQUIRED_LOWER_BOUNDS:
            for _n, _spec, raw in self._lines_for(name):
                self.assertIn('CVE-', raw,
                              '%s 的下界行缺 CVE 编号注释：%r' % (name, raw))

    def test_03_dead_deps_removed_from_requirements(self):
        for name in REMOVED_DEAD_DEPS:
            hits = [l for l in self.lines if l[0] == name]
            self.assertEqual(hits, [], '死依赖 %s 又回到 requirements.txt：%r' % (name, hits))
        # 两种拼写都不允许（flask-helper 的 import 名是 flask_helper）
        self.assertNotIn('flask_helper', _read(REQ),
                         'requirements.txt 出现 flask_helper 拼写')

    def test_04_still_used_optional_drivers_kept(self):
        for name in STILL_USED_OPTIONAL_DRIVERS:
            hits = [l for l in self.lines if l[0] == name]
            self.assertTrue(hits, '在用依赖 %s 被误删（报告误判为死依赖）' % name)


class DeadDependencyImportScanTest(unittest.TestCase):
    """九.10/九.11：被删依赖在全仓确实零 import（静态扫描，防止误删活依赖）。"""

    def test_05_removed_deps_have_no_import_anywhere(self):
        paths = list(_iter_source())
        self.assertGreaterEqual(len(paths), MIN_SCAN_FILES,
                                '扫描面过小（%d 个文件），静态扫描可能已失效' % len(paths))
        offenders = {}
        for path in paths:
            text = _read(path)
            for dep, module in REMOVED_DEAD_DEPS.items():
                for m in IMPORT_RE.finditer(text):
                    top = m.group(1).split('.')[0]
                    if top == module:
                        lineno = text[:m.start()].count('\n') + 1
                        offenders.setdefault(dep, []).append(
                            '%s:%d' % (os.path.relpath(path, ROOT).replace(os.sep, '/'), lineno))
        self.assertEqual(offenders, {}, '死依赖仍有 import：%r' % offenders)


class LockScriptTest(unittest.TestCase):
    """九.8：无 lockfile 的修复入口 —— 可复现的锁生成脚本。"""

    def test_06_lock_script_exists_and_shell_valid(self):
        self.assertTrue(os.path.isfile(LOCK_SCRIPT),
                        '缺少锁生成脚本 scripts/gen_requirements_lock.sh')
        self.assertTrue(os.access(LOCK_SCRIPT, os.X_OK),
                        '锁生成脚本不可执行（需 chmod +x）')
        self.assertTrue(_read(LOCK_SCRIPT).startswith('#!'),
                        '锁生成脚本缺 shebang')
        bash = _find_bash()
        if bash is None:
            self.skipTest('未找到可用 bash')
        proc = subprocess.run([bash, '-n', LOCK_SCRIPT], capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         'bash -n 失败：%s' % ((proc.stderr or proc.stdout) or '').strip())

    def test_07_requirements_points_to_lock_script(self):
        self.assertIn('scripts/gen_requirements_lock.sh', _read(REQ),
                      'requirements.txt 注释未指向锁生成脚本')


if __name__ == '__main__':
    unittest.main(verbosity=2)
