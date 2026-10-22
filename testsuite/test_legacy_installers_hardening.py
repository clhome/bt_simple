# coding: utf-8
"""历史安装/更新脚本供应链守卫（测评报告 P1-2）。

被测面：`scripts/install.sh`、`scripts/install_dev.sh`、`scripts/update.sh`、
`scripts/update_dev.sh` 四个「一键安装/升级」脚本。

为什么**不能**直接删掉这四个脚本（改动本文件前请先读懂）：

* `.github/workflows/python-app-*.yml`（php / op / mysql55 / mysql56 / mysql57 /
  mysql80 六个 workflow）里 CI 会 `sudo bash scripts/install_dev.sh` 真装整套面板；
* `testsuite/test_deploy_bootstrap.py` 的 `PROXY_CONSUMERS` 要求这四个文件都存在。

所以修复路线是「验签门 / 默认拒绝」：文件保留，但**未经验证的下载一律拒绝执行**——
分支快照（master/dev tarball）不再解包，第三方脚本（get.acme.sh / macos.sh）不再
管道进解释器，acme.sh 改为固定 tag + sha256 校验通过后才执行。

本用例锁死五条（任何一条被改回旧写法都必须让门禁变红）：

1. 四个脚本内放宽传输层 TLS 校验的参数**计数为 0**（含注释，禁止复制粘贴回来）；
2. 四个脚本内**不存在**「下载内容直接管道进解释器」形态（`| bash` / `|sh` ...）；
3. 存在**默认拒绝**分支：中文拒绝文案 + `exit 1` + 指向 `deploy.sh`，
   且**没有**静默跳过的环境变量开关（方案明确要求）；
4. 分支快照下载路径（`refs/heads/master.tar.gz` / `refs/heads/dev.tar.gz`）已消失，
   acme.sh 走「固定 tag + sha256 校验 → 才执行」；
5. `install_dev.sh` / `update_dev.sh` 仍存在且仍被 CI 引用（防止有人真的去删）。

另加两条行为用例（无运行时副作用，均不需要 root）：

* `bash -n` 语法检查（只解析，不执行）；
* 把拒绝函数**抽出来**在子 shell 里单独跑，断言它真的 `exit 1` 且打印拒绝文案。
"""
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SCRIPTS = ('scripts/install.sh', 'scripts/install_dev.sh',
           'scripts/update.sh', 'scripts/update_dev.sh')
DEV_SCRIPTS = ('scripts/install_dev.sh', 'scripts/update_dev.sh')
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')
REFUSE_FN = 'yf_refuse_unverified_source'

#: 放宽传输层 TLS 校验的写法（三个都要清零）。
TLS_RELAX = re.compile(r'--insecure|no-check-certificate|\bcurl\b[^\n|]*\s-k\b')

#: 「下载内容直接管道进解释器」：管道右侧是 sh/bash（可带 sudo）。
PIPE_TO_SHELL = re.compile(r'\|\s*(?:sudo\s+)?(?:sh|bash)(?=\s|$)')

#: 静默放行的开关（方案要求不提供）：环境变量式跳过 / 显式 --allow-unverified。
SILENT_BYPASS = re.compile(r'YF_ALLOW_UNVERIFIED|ALLOW_INSECURE|SKIP_VERIFY|'
                           r'--allow-unverified|--no-verify')

#: 默认拒绝分支必须出现的两类字样。
DENY_WORDS = ('拒绝', '不允许')

# Windows 上 PATH 里的 bash 可能是 WSL 启动器（无法执行本地脚本），优先 Git Bash。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
]


def read_text(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def code_lines(text):
    """返回 [(行号, 行内容)]，跳过整行注释（避免注释里的历史写法被误判成现存问题）。"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('#'):
            continue
        out.append((i, line))
    return out


def find_posix_bash():
    """返回可用于执行 / 语法校验的 POSIX shell 路径，找不到返回 None。"""
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


def extract_shell_function(src, name):
    """取出 `name()` / `function name()` 的完整定义（按大括号配平，不按行截断）。"""
    m = re.search(r'^(?:function\s+)?' + re.escape(name) + r'\s*\(\s*\)\s*\{', src, re.M)
    if not m:
        raise AssertionError('未找到 shell 函数定义: %s' % name)
    start = src.index('{', m.start())
    depth = 0
    for idx in range(start, len(src)):
        ch = src[idx]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():idx + 1]
    raise AssertionError('shell 函数定义未闭合: %s' % name)


class LegacyInstallerHardeningTest(unittest.TestCase):

    def test_01_no_tls_relaxation_flags(self):
        """四个脚本内不得再出现放宽传输层 TLS 校验的参数（计数必须为 0）。

        旧写法：`curl --insecure -sSLo /tmp/master.tar.gz ...`（install.sh:369 等 7 处）。
        分支包 / acme.sh / macos.sh 都是 root 执行的可执行内容，放宽 TLS 等于把
        「谁能改链路谁就能改代码」。现在要么走已验签发布包，要么走 sha256 固定校验。
        """
        for rel in SCRIPTS:
            text = read_text(rel)
            hits = [i for i, line in enumerate(text.splitlines(), 1)
                    if TLS_RELAX.search(line)]
            self.assertEqual(
                hits, [],
                '%s 第 %r 行仍在放宽传输层 TLS 校验（应为 0 处）' % (rel, hits))

    def test_02_no_pipe_to_shell(self):
        """四个脚本内不得把下载内容直接管道进解释器。"""
        for rel in SCRIPTS:
            text = read_text(rel)
            offenders = [(ln, line.strip())
                         for ln, line in code_lines(text)
                         if PIPE_TO_SHELL.search(line)]
            self.assertEqual(
                offenders, [],
                '%s 出现 pipe-to-shell（供应链红线）：%r' % (rel, offenders))
            self.assertNotIn('get.acme.sh', text,
                             '%s 仍在用 get.acme.sh 的管道安装脚本' % rel)

    def test_03_branch_snapshot_download_path_is_gone(self):
        """未签名的分支快照下载路径必须消失（默认拒绝，不再有下载-解包-覆盖）。"""
        tokens = ('refs/heads/master.tar.gz', 'refs/heads/dev.tar.gz',
                  'scripts/install/macos.sh | bash')
        for rel in SCRIPTS:
            text = read_text(rel)
            hits = [(ln, token) for ln, line in code_lines(text)
                    for token in tokens if token in line]
            self.assertEqual(
                hits, [],
                '%s 仍在拉取 / 管道执行未验签内容（行号, 片段）：%r' % (rel, hits))

    def test_04_default_deny_branch_exists(self):
        """必须有默认拒绝分支：中文拒绝文案 + exit 1 + 指向 deploy.sh。"""
        for rel in SCRIPTS:
            text = read_text(rel)
            # 定义 1 处 + 至少 1 处调用（防止「写了但从不调用」的死代码）
            self.assertGreaterEqual(
                len(re.findall(re.escape(REFUSE_FN), text)), 2,
                '%s 缺少 %s 的调用点（只有定义 = 写了不用）' % (rel, REFUSE_FN))
            self.assertTrue(any(w in text for w in DENY_WORDS),
                            '%s 缺少「拒绝 / 不允许」类中文提示' % rel)
            self.assertIn('exit 1', text,
                          '%s 的拒绝分支必须真正中止（exit 1），不得打印一行后继续' % rel)
            self.assertIn('deploy.sh', text,
                          '%s 的拒绝文案必须指向已验签的 deploy.sh（给出可用替代路径）' % rel)
            # 方案要求：不留静默跳过口（环境变量 / 隐式参数）
            self.assertEqual(
                SILENT_BYPASS.findall(text), [],
                '%s 出现了静默跳过校验的开关，方案明确禁止' % rel)

    def test_05_acme_installed_only_after_sha256_check(self):
        """acme.sh 必须固定 tag + sha256 校验通过后才执行，下载与执行顺序不得倒置。"""
        for rel in ('scripts/install.sh', 'scripts/install_dev.sh'):
            text = read_text(rel)
            self.assertIn('YF_ACME_SHA256', text, '%s 缺少 acme.sh 期望 sha256 常量' % rel)
            self.assertRegex(text, r'YF_ACME_VERSION="?\d+\.\d+\.\d+"?',
                             '%s 的 acme.sh 版本必须是具体 tag' % rel)
            self.assertIn('refs/tags/${YF_ACME_VERSION}', text,
                          '%s 的 acme.sh 下载 URL 必须指向固定 tag' % rel)
            self.assertNotIn('acme.sh/archive/master.tar.gz', text,
                             '%s 的 acme.sh 仍指向 master 分支' % rel)
            self.assertIn('拒绝执行该安装包', text,
                          '%s 缺少「哈希不符即拒绝执行」的 fail-closed 分支' % rel)
            self.assertLess(
                text.index('!= "$YF_ACME_SHA256"'), text.index('./acme.sh --install'),
                '%s 的 acme.sh 执行出现在 sha256 校验之前' % rel)

    def test_06_dev_installers_exist_and_are_used_by_ci(self):
        """install_dev.sh / update_dev.sh 必须仍存在，且 CI 仍在调用（防止误删）。"""
        for rel in DEV_SCRIPTS:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)),
                            '%s 被删了：CI（.github/workflows/python-app-*.yml）依赖它' % rel)

        wf_text = ''
        for name in sorted(os.listdir(WORKFLOWS)):
            if name.endswith(('.yml', '.yaml')):
                with open(os.path.join(WORKFLOWS, name), encoding='utf-8') as fh:
                    wf_text += fh.read()
        self.assertIn('scripts/install_dev.sh', wf_text,
                      'CI 里已没有 scripts/install_dev.sh 调用点，本守卫的前提需要复核')

    def test_07_bash_syntax(self):
        """四个脚本必须通过 bash 语法检查（只解析，不执行，无运行时副作用）。"""
        bash = find_posix_bash()
        if not bash:
            self.skipTest('本机无可用 POSIX bash（Linux/CI 会执行）')
        for rel in SCRIPTS:
            path = os.path.join(ROOT, rel)
            proc = subprocess.run([bash, '-n', path], capture_output=True)
            self.assertEqual(
                proc.returncode, 0,
                '%s 语法检查失败：\n%s'
                % (rel, proc.stderr.decode('utf-8', 'replace')))

    def test_08_refusal_really_aborts(self):
        """行为用例：拒绝函数必须真的 exit 1，且打印拒绝文案（不只是文本存在）。"""
        bash = find_posix_bash()
        if not bash:
            self.skipTest('本机无可用 POSIX bash（Linux/CI 会执行）')
        for rel in SCRIPTS:
            fn_text = extract_shell_function(read_text(rel), REFUSE_FN)
            script = '\n'.join([
                'ERROR="[ERR]"',
                fn_text,
                '%s "测试内容"' % REFUSE_FN,
                'echo REACHED_AFTER_REFUSE',
            ])
            # 注意：Windows 中文环境的默认解码是 GBK，输出里带 UTF-8 中文时
            # `text=True` 会直接抛 UnicodeDecodeError，必须自己按 UTF-8 解码。
            proc = subprocess.run([bash, '-c', script], capture_output=True, timeout=60)
            out = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
            self.assertNotEqual(proc.returncode, 0,
                                '%s 的拒绝函数没有中止（退出码 0）' % rel)
            self.assertNotIn('REACHED_AFTER_REFUSE', out,
                             '%s 的拒绝函数没有阻断后续语句' % rel)
            self.assertIn('拒绝', out, '%s 的拒绝函数没有打印拒绝文案' % rel)
            self.assertIn('deploy.sh', out,
                          '%s 的拒绝文案没有给出 deploy.sh 替代路径' % rel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
