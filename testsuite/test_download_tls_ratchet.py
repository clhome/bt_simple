# coding: utf-8
"""P1-3 棘轮守卫：下载链路的传输层 TLS 校验「默认开启，放宽只减不增」。

被测面
------
* `scripts/github_download.sh` —— 所有 GitHub / 代理下载的落地点（`_gh_try_download`），
  同时是「放宽 TLS 参数」的**单一真源**（`yf_wget_tls_extra_args`）；
* `scripts/lib.sh` —— `yf_download`（非 GitHub URL 与 USTC 镜像分支）；
* `plugins/*/install.sh` —— 插件级安装脚本里自带的 wget 下载点。

为什么要有这个用例
------------------
整改前全仓有 435 行 `no-check-certificate`，其中插件安装脚本里那 10 处是「下完就
`wget -O` 落盘、跳着证书下二进制包」的高危写法。这类点一次修不完（`plugins/` 下
还有 190+ 处历史写法，属 P2-6 与后续项），而「修一半」恰恰是本仓库踩过的坑：
同族点里改了一个、漏了另一个，漏洞照旧。所以用棘轮（ratchet）：把整改后的现状
登记为基线，**只减不增**——谁再往仓库里加一处跳证书，本用例立刻变红。

四条规则
--------
1. **全仓棘轮**：`*.sh` / `*.py` 里含该参数的行数 ≤ `BASELINE_INSECURE_DOWNLOAD_POINTS`；
2. **插件安装脚本口径清零**：`plugins/*/install.sh` 必须是 0，**含注释**
   （注释里的旧写法会被整段复制粘贴回来，历史事故正是这么发生的）；
3. **放宽必须挂在 opt-in 上**：`scripts/lib.sh` / `scripts/github_download.sh` 里
   含该参数的行数**每个文件 ≤ 1**（只允许出现在唯一那个产出参数的函数里），
   且同文件必须出现 `YF_INSECURE_DOWNLOAD` —— 放宽只能由这个环境变量驱动，
   不允许出现「失败后自动降级重试」的隐式分支；
4. **opt-in 必须留痕**：同文件必须有 `[WARN]` 告警文案（放宽时写 stderr）。

另有一条**行为用例**（`test_05`）：真的在子 shell 里 source `github_download.sh`，
断言不带 `YF_INSECURE_DOWNLOAD=1` 时**不输出**放宽参数、带了才输出且带 `[WARN]`。
只看文本容易被「函数写了但没人调用」骗过，所以要真跑一次。

零外部依赖：只用标准库，不联网，不做任何真实下载。
"""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 放宽传输层 TLS 校验的字面量。**刻意拆成两段拼接**：本用例正文里有几处对参数名
#: 的文档性引用，拆开写可以避免用例自己的源码在 grep 时被算进「生产代码点数」，
#: 让「基线 = 报告里那条 grep 命令的结果」保持一一对应。
TLS_RELAX_TOKEN = 'no-check' + '-certificate'

#: 唯一允许驱动「放宽」的环境变量名。
OPT_IN_ENV = 'YF_INSECURE_DOWNLOAD'

#: 放宽时必须出现的告警文案特征。
WARN_MARKERS = ('[WARN]', 'TLS')

#: 整改后（P1-3）实测全仓计数。口径与报告里的同一条命令一致：
#:   grep -rn "no-check-certificate" --include=*.py --include=*.sh . \
#:     | grep -v node_modules | wc -l
#: 整改前 435 → 整改后 423。扫描时**跳过本文件自身**（它有几行对参数名的文档性
#: 引用，不该算成「生产代码里的放宽点」，否则面向自己的断言会自相矛盾）。
#: **只许往下调**；要往上调必须有人先解释为什么。
BASELINE_INSECURE_DOWNLOAD_POINTS = 423

#: 单一真源文件：这两个文件里放宽参数最多各 1 行（唯一那个产出参数的函数）。
SINGLE_SOURCE_FILES = ('scripts/lib.sh', 'scripts/github_download.sh')

#: 必须清零的口径。
PLUGIN_INSTALLERS_GLOB = 'plugins/*/install.sh'

SKIP_DIRS = {'.git', 'node_modules', '__pycache__'}
SCAN_SUFFIXES = ('.sh', '.py')

#: 本用例自身（扫描时跳过，理由见 BASELINE_INSECURE_DOWNLOAD_POINTS 的注释）。
SELF_FILE = os.path.abspath(__file__)


def _abs(rel):
    return os.path.join(ROOT, rel.replace('/', os.sep))


def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def iter_scan_files():
    """遍历全仓 `*.sh` / `*.py`（跳过 .git、node_modules、__pycache__ 与本文件）。"""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(SCAN_SUFFIXES):
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == SELF_FILE:
                continue
            yield path


def plugin_installers():
    """`plugins/*/install.sh`（一层通配，不含 `plugins/*/versions/**`）。"""
    plugins_dir = os.path.join(ROOT, 'plugins')
    if not os.path.isdir(plugins_dir):
        return []
    out = []
    for name in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, name, 'install.sh')
        if os.path.isfile(path):
            out.append(path)
    return out


def insecure_lines(paths):
    """返回 [(相对路径, 行号, 行内容)]，只收集含放宽参数的行。"""
    hits = []
    for path in paths:
        for lineno, line in enumerate(read_text(path).splitlines(), 1):
            if TLS_RELAX_TOKEN in line:
                rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
                hits.append((rel, lineno, line.strip()))
    return hits


class TestDownloadTlsRatchet(unittest.TestCase):
    """规则 1-4：文本棘轮。"""

    def test_01_whole_repo_count_within_baseline(self):
        """全仓放宽点数不得超过基线（只减不增）。"""
        hits = insecure_lines(iter_scan_files())
        self.assertLessEqual(
            len(hits), BASELINE_INSECURE_DOWNLOAD_POINTS,
            '全仓放宽 TLS 校验的点数 %d 超过基线 %d（棘轮只减不增）。\n'
            '新增的点如下（相对基线看不出是哪几个，这里把全部命中列出来）：\n%s'
            % (len(hits), BASELINE_INSECURE_DOWNLOAD_POINTS,
               '\n'.join('  %s:%d  %s' % h for h in hits[:60])))
        self.assertGreater(len(hits), 0, '扫描面失效：全仓一处都没扫到，'
                                         '说明遍历逻辑坏了（而不是真的全仓库清干净了）')

    def test_02_plugin_installers_have_zero(self):
        """`plugins/*/install.sh` 口径必须为 0（含注释）。"""
        installers = plugin_installers()
        self.assertGreaterEqual(
            len(installers), 20,
            '只找到 %d 个 plugins/*/install.sh，疑似扫描面失效' % len(installers))
        hits = insecure_lines(installers)
        self.assertEqual(
            [], hits,
            'plugins/*/install.sh 里仍有 %d 处放宽 TLS 校验（该口径必须为 0，'
            '注释里的旧写法也要清掉，否则会被复制粘贴回来）：\n%s'
            % (len(hits), '\n'.join('  %s:%d  %s' % h for h in hits)))

    def test_03_relax_only_behind_opt_in(self):
        """单一真源文件里放宽参数每文件 ≤ 1 行，且同文件必须出现 opt-in 变量。"""
        for rel in SINGLE_SOURCE_FILES:
            path = _abs(rel)
            self.assertTrue(os.path.isfile(path), '缺少文件: %s' % rel)
            text = read_text(path)
            hits = insecure_lines([path])
            with self.subTest(file=rel):
                self.assertLessEqual(
                    len(hits), 1,
                    '%s 里出现 %d 行放宽参数（每个文件最多 1 行：只允许在唯一那个'
                    '「产出放宽参数」的函数里出现，其余下载点必须调用它）：\n%s'
                    % (rel, len(hits),
                       '\n'.join('  %d  %s' % (h[1], h[2]) for h in hits)))
                self.assertIn(
                    OPT_IN_ENV, text,
                    '%s 里没有 %s：放宽 TLS 校验必须由这个环境变量显式 opt-in，'
                    '不允许只凭代码分支就放宽' % (rel, OPT_IN_ENV))

    def test_04_opt_in_emits_loud_warning(self):
        """放宽时必须打醒目告警（[WARN] + TLS 字样），方便事后追查。"""
        for rel in SINGLE_SOURCE_FILES:
            text = read_text(_abs(rel))
            with self.subTest(file=rel):
                for marker in WARN_MARKERS:
                    self.assertIn(
                        marker, text,
                        '%s 里缺少 `%s` 字样：放宽 TLS 校验时必须向 stderr 打醒目告警'
                        % (rel, marker))

    def test_05_single_source_does_not_leak_relax_args_by_default(self):
        """行为用例：未 opt-in 时不得输出放宽参数；opt-in 时必须输出且带告警。"""
        bash = find_bash()
        if not bash:
            self.skipTest('找不到可用的 bash（Git Bash / MSYS），跳过行为用例')
        lib = _abs('scripts/github_download.sh')
        self.assertTrue(os.path.isfile(lib))
        # 注意：不加 `set -u` —— github_download.sh 顶层的探针缓存在未定义变量上是
        # 容忍式的（`[ -z "$_GH_BEST_PROXY" ]`），那是既有写法，不属于本项范围。
        script = ('source "%s" >/dev/null 2>/dev/null; '
                  'yf_wget_tls_extra_args "https://example.invalid/x.tar.gz"'
                  % lib.replace('\\', '/'))

        # ① 默认（未 opt-in）：不得出现放宽参数，也不得有告警噪音
        rc, out, err = run_bash(bash, script, {})
        self.assertEqual(0, rc, '默认分支执行失败: %s' % err)
        self.assertNotIn(TLS_RELAX_TOKEN, out,
                         '未设置 %s 时竟然输出了放宽参数（默认必须做 TLS 校验）' % OPT_IN_ENV)
        self.assertNotIn('[WARN]', err,
                         '未设置 %s 时不该打告警（说明放宽分支被无条件执行了）' % OPT_IN_ENV)

        # ② 显式 opt-in：必须输出放宽参数 + [WARN] 告警 + URL
        rc, out, err = run_bash(bash, script, {OPT_IN_ENV: '1'})
        self.assertEqual(0, rc, 'opt-in 分支执行失败: %s' % err)
        self.assertIn(TLS_RELAX_TOKEN, out,
                      '%s=1 时应输出放宽参数' % OPT_IN_ENV)
        self.assertIn('[WARN]', err,
                      '%s=1 时必须打醒目告警（放宽 TLS 校验要留痕）' % OPT_IN_ENV)
        self.assertIn('example.invalid', err, '告警里要带上是哪个 URL 被放宽了')

        # ③ 非 1 的值一律视为未开启（只认字符串 1，不做真假值猜测）
        for value in ('0', 'yes', 'true', ''):
            rc, out, err = run_bash(bash, script, {OPT_IN_ENV: value})
            self.assertEqual(0, rc)
            self.assertNotIn(TLS_RELAX_TOKEN, out,
                             '%s=%r 不应被视为开启（只认 1）' % (OPT_IN_ENV, value))

    def test_06_sha256_entrypoint_is_fail_closed(self):
        """行为用例：`yf_download_sha256` 不匹配 / 空期望值必须删包并返回非 0。

        校验入口不能只是「写了就算」——这里把 `scripts/lib.sh` 里的
        `yf_sha256_of_file` + `yf_download_sha256` 抽出来真跑（`yf_download` 用
        本地复制桩替掉，不联网），断言三条 fail-closed 语义。
        """
        bash = find_bash()
        if not bash:
            self.skipTest('找不到可用的 bash（Git Bash / MSYS），跳过行为用例')
        src = read_text(_abs('scripts/lib.sh'))
        extracted = []
        for fn in ('yf_sha256_of_file', 'yf_download_sha256'):
            body = slice_function(src, fn)
            self.assertTrue(body, '`scripts/lib.sh` 里找不到函数 %s（校验入口被删了？）' % fn)
            extracted.append(body)

        script = '\n'.join(extracted) + '''
# 测试桩：用本地复制代替真实下载（本用例不联网）
yf_download() { cp "$STUB_SRC" "$1"; }
printf 'p1-3 payload' > "$TMPD/payload.bin"
STUB_SRC="$TMPD/payload.bin"
GOOD=$(yf_sha256_of_file "$STUB_SRC")
echo "GOOD=$GOOD"
# ① 哈希匹配 -> 保留文件、返回 0
yf_download_sha256 "$TMPD/ok.bin" "https://example.invalid/p.bin" "$GOOD" 5
rc1=$?; [ -f "$TMPD/ok.bin" ] && e1=yes || e1=no
# ② 哈希不匹配 -> 删包、返回非 0
yf_download_sha256 "$TMPD/bad.bin" "https://example.invalid/p.bin" "$(printf 'a%.0s' $(seq 1 64))" 5
rc2=$?; [ -f "$TMPD/bad.bin" ] && e2=yes || e2=no
# ③ 期望值为空 -> 直接拒绝下载
yf_download_sha256 "$TMPD/empty.bin" "https://example.invalid/p.bin" "" 5
rc3=$?; [ -f "$TMPD/empty.bin" ] && e3=yes || e3=no
echo "RESULT|$rc1|$e1|$rc2|$e2|$rc3|$e3"
'''
        tmpd = os.path.join(os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp',
                            'yf_p13_sha256')
        if os.path.isdir(tmpd):
            shutil.rmtree(tmpd, ignore_errors=True)
        os.makedirs(tmpd)
        try:
            rc, out, err = run_bash(bash, script, {'TMPD': tmpd.replace('\\', '/')})
            self.assertEqual(0, rc, '校验入口子 shell 异常退出: %s' % err)
            line = [l for l in out.splitlines() if l.startswith('RESULT|')]
            self.assertTrue(line, '行为用例没拿到 RESULT 行，输出：\n%s\n%s' % (out, err))
            parts = line[-1].split('|')
            _, rc1, e1, rc2, e2, rc3, e3 = parts
            self.assertEqual('0', rc1, '哈希匹配时必须返回 0')
            self.assertEqual('yes', e1, '哈希匹配时必须保留文件')
            self.assertNotEqual('0', rc2, '哈希不匹配必须返回非 0')
            self.assertEqual('no', e2, '哈希不匹配必须删包')
            self.assertNotEqual('0', rc3, '期望值为空必须拒绝下载（防「空串=跳过校验」）')
            self.assertEqual('no', e3, '期望值为空时不应留下文件')
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)


def slice_function(source, name):
    """从 shell 源文本里按 `function <name>() {` ... 行首 `}` 抽出一个函数定义。"""
    lines = source.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('function %s()' % name) or stripped.startswith('%s()' % name):
            out = []
            for cur in lines[idx:]:
                out.append(cur)
                if cur.rstrip() == '}':
                    return '\n'.join(out)
            return ''
    return ''


# ---------------------------------------------------------------- 工具函数 --
#: Windows 上 PATH 里的 bash 可能是 WSL 启动器（无法执行本地脚本），优先 Git Bash。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    '/bin/bash',
    '/usr/bin/bash',
]


def find_bash():
    for cand in BASH_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return shutil.which('bash')


def run_bash(bash, script, extra_env):
    env = dict(os.environ)
    env.pop(OPT_IN_ENV, None)
    env.update(extra_env)
    env['LC_ALL'] = 'C'
    proc = subprocess.run([bash, '-c', script], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=60)
    out = proc.stdout.decode('utf-8', 'replace')
    err = proc.stderr.decode('utf-8', 'replace')
    return proc.returncode, out, err


if __name__ == '__main__':
    unittest.main(verbosity=2)
