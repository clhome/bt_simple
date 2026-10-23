# coding: utf-8
"""P2-9 依赖边界守卫：14 个无界依赖的「补下界 / 登记例外」二选一 + 交付口径。

## 这个文件在守什么

`requirements.txt` 里原本有 14 个依赖没有任何版本边界（packaging / bcrypt / pyotp /
pymongo / pymemcache / redis / pytz / croniter / tldextract / pyTelegramBotAPI /
telebot / brotli / zstd / zstandard）。整改纪律是**不许凭印象写上游最新版**
（开发机离线，无依据的数字会把安装挡死或等于没锁），只能二选一：

* **A 类**：有本地实测依据 → 补 `>=实测版本`，且行内注明「下界取自开发环境实测版本」；
* **B 类**：没有依据 → 保持无版本，但必须登记进 `requirements.txt` 文末的
  「无界依赖例外清单（P2-9）」，逐条写理由与复核时机。

于是本文件断言：

1. `requirements.txt` 里**每条生效依赖**要么带版本边界（`>=` / `==` / `<` / `>` 等），
   要么其包名出现在例外清单里 —— 新增一个无界依赖却没登记，门禁必须变红；
2. 例外清单**不能腐烂**：登记项必须真的存在于 `requirements.txt`、且确实仍无边界，
   且理由与复核时机都不为空（补上边界后就该从清单里删掉，否则重复断言会报红）；
3. A 类补的下界不得被悄悄下调（对照本文件记录的实测值），且仍带来源注释；
4. `python_version < '3.9'` 分档仍是 4 处（flask / Werkzeug / pyOpenSSL / cryptography），
   而《组件生命周期与安全响应政策》确实写明了 **2027-06-30** 的 EOL 口径与
   Python 版本支持说明，`SECURITY.md` 的「已知取舍」指向该章节；
5. `release.yml` 的 `files:` 附件清单仍含 `requirements.lock`（P1-9 成果，防回退）；
6. `scripts/verify_requirements_lock.py` 的正反两路都真的会动：合规模具 → 退出码 0，
   缺哈希夹具 → 退出码 1 并**点名**缺哈希的包；本地没有锁文件时不算失败（它不入库）。

## 与既有守卫的分工（刻意不重复）

* CVE 下界（flask / Werkzeug / gunicorn / requests / urllib3 / pillow / pyyaml）、
  死依赖清理、EOL 日期在 `requirements.txt` 与 `README.md` 的双处声明，
  由 `testsuite/test_requirements_hardening.py` 守 —— 本文件**不改**它，只补它没覆盖的
  「边界是否缺失」这一层。
* 本文件读的是同一份 `requirements.txt` 真实文本（不硬编码常量），所以改坏格式同样会红。

## 变异自证（本轮实测）

① 往 `requirements.txt` 加一行无界的 `websocket-client` → `test_01` 变红；
② 把 `packaging>=23.2` 退回成 `packaging` → `test_01`（未登记例外）与 `test_04` 同时变红；
复原后全绿。另见 `test_03` 的内嵌文本自证：检测器本身被证明能抓到注入的无界依赖。
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REQ = os.path.join(ROOT, 'requirements.txt')
LIFECYCLE_DOC = os.path.join(ROOT, '文档', '组件生命周期与安全响应政策.md')
SECURITY_MD = os.path.join(ROOT, 'SECURITY.md')
RELEASE_WF = os.path.join(ROOT, '.github', 'workflows', 'release.yml')
LOCK_VERIFIER = os.path.join(ROOT, 'scripts', 'verify_requirements_lock.py')
DEFAULT_LOCK = os.path.join(ROOT, 'requirements.lock')

#: `requirements.txt` 里的例外清单标记（逐字取自小节标题；
#: 带上首尾 `---` 是为了不匹到文首锁策略第 7 条里对它的引用）
EXC_MARKER = '--- 无界依赖例外清单（P2-9）---'
#: 例外清单条目格式：`#   <包名>  —— 理由：…；复核时机：…`
EXC_ENTRY_RE = re.compile(
    r'^#\s+(?P<name>[A-Za-z0-9_.\-]+)\s+——\s*理由：(?P<reason>.+?)'
    r'[；;]\s*复核时机：(?P<when>.+?)\s*$')
#: 版本边界运算符（`>` 也算：`whitenoise>5.3.0` 是排他下界，不强制改写既有行）
BOUND_RE = re.compile(r'(>=|<=|==|~=|<|>)')
#: A 类补下界必须带的来源注释（红线：版本号要有出处）
MEASURED_NOTE = '下界取自开发环境实测版本'
#: 本机（Python 3.10 开发环境）实测版本 —— A 类下界不得被下调到它以下
MEASURED_FLOORS = {
    'packaging': '23.2',
    'bcrypt': '4.1.2',
    'pytz': '2023.3.post1',
    'zstandard': '0.22.0',
}
#: `py<3.9` 过渡分档必须仍在的 4 个包（removed 前不许减少）
PY39_BRANCH_PACKAGES = ('flask', 'werkzeug', 'pyopenssl', 'cryptography')
#: 用户裁定的 EOL 日期（与 test_requirements_hardening 同一口径）
EOL_DATE = '2027-06-30'
#: 交付文档里必须出现的章节标题（SECURITY.md 指向它，靠字符串对齐）
DOC_SECTION = '依赖与 Python 版本支持'

#: 不是「依赖声明」的行：pip 选项 / 本地路径 / 直接引用
SKIP_PREFIXES = ('-r', '-e', '-c', '--', 'git+', 'http://', 'https://', 'file:', '.')

NAME_RE = re.compile(r'^([A-Za-z0-9_.\-]+)[ \t]*(.*)$')


def read(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read().replace('\r\n', '\n')


def requirement_lines(text):
    """把 requirements 文本解析成 `[(name_lower, spec, raw_line, lineno)]`。

    跳过空行、整行注释与 pip 选项行；环境标记（`; python_version ...`）保留在 spec 里，
    需要判断边界时用 `spec_core()` 剥掉。
    """
    out = []
    for lineno, raw in enumerate(text.split('\n'), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith(SKIP_PREFIXES):
            continue
        m = NAME_RE.match(line)
        if not m:
            continue
        out.append((m.group(1).lower(), m.group(2).strip(), raw, lineno))
    return out


def spec_core(spec):
    """去掉环境标记后的版本约束部分。"""
    return spec.split(';', 1)[0].strip()


def has_bound(spec):
    return bool(BOUND_RE.search(spec_core(spec)))


def version_tuple(version):
    return tuple(int(x) for x in re.findall(r'\d+', version))


def comment_section(text, marker):
    """取含 marker 的注释小节：从其所在行起，连续注释（允许中间空行）到首个非注释行为止。"""
    lines = text.split('\n')
    start = None
    for i, line in enumerate(lines):
        if marker in line and line.strip().startswith('#'):
            start = i
            break
    if start is None:
        return []
    block = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            block.append(line)
            continue
        if not stripped.startswith('#'):
            break
        block.append(line)
    return block


def exception_entries(text):
    """解析例外清单 → `{包名小写: {'reason':…, 'when':…, 'raw':…}}`（保持清单顺序）。"""
    out = {}
    for line in comment_section(text, EXC_MARKER):
        m = EXC_ENTRY_RE.match(line.strip())
        if not m:
            continue
        out[m.group('name').lower()] = {
            'reason': m.group('reason').strip(),
            'when': m.group('when').strip(),
            'raw': line,
        }
    return out


def unbounded_requirements(text):
    """返回「没有版本边界、也没登记进例外清单」的依赖 → `[(name, lineno, raw)]`。"""
    exempt = exception_entries(text)
    bad = []
    for name, spec, raw, lineno in requirement_lines(text):
        if has_bound(spec) or name in exempt:
            continue
        bad.append((name, lineno, raw.strip()))
    return bad


def release_files_entries(text=None):
    """从 release.yml 取 `files:` 附件清单（按缩进截断块，`sbom.json` 那类只生成不上传的不算）。"""
    text = read(RELEASE_WF) if text is None else text
    lines = text.split('\n')
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('files:'):
            continue
        if stripped[len('files:'):].strip() not in ('|', '|-', '>', '>-', ''):
            continue
        base_indent = len(line) - len(line.lstrip())
        entries = []
        for nxt in lines[idx + 1:]:
            if not nxt.strip():
                continue
            if len(nxt) - len(nxt.lstrip()) <= base_indent:
                break
            entries.append(nxt.strip())
        if entries:
            return entries
    raise AssertionError('release.yml 里找不到 `files: |` 附件清单（发布流程被改坏了？）')


def run_verifier(path_arg=None):
    """跑锁文件校验器，返回 `(退出码, 输出文本)`。"""
    cmd = [sys.executable, LOCK_VERIFIER]
    if path_arg is not None:
        cmd.append(path_arg)
    env = os.environ.copy()
    # 子进程统一 UTF-8，避免 Windows 控制台 GBK 把中文输出变成乱码导致断言假红
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, env=env, timeout=120)
    text = (proc.stdout + b'\n' + proc.stderr).decode('utf-8', 'replace')
    return proc.returncode, text


def _hash_line(digit, repeat=64):
    return '    --hash=sha256:' + digit * repeat


class RequirementBoundPolicyTest(unittest.TestCase):
    """核心判据：每条生效依赖要么有版本边界，要么在例外清单里。"""

    def setUp(self):
        self.text = read(REQ)
        self.lines = requirement_lines(self.text)

    def test_01_every_requirement_has_bound_or_is_registered_exception(self):
        bad = unbounded_requirements(self.text)
        self.assertEqual(
            bad, [],
            '以下依赖既没有版本边界，也没登记进「无界依赖例外清单」：%r\n'
            '（有本地实测依据 → 补 >=实测版本 并注明来源；没有依据 → 写进文末例外清单，'
            '逐条给理由与复核时机）' % (bad,))

    def test_02_exception_list_cannot_rot(self):
        entries = exception_entries(self.text)
        self.assertTrue(entries, 'requirements.txt 里解析不到「%s」的条目' % EXC_MARKER)
        by_name = {}
        for name, spec, _raw, lineno in self.lines:
            by_name.setdefault(name, []).append((spec, lineno))

        problems = []
        for name, info in entries.items():
            if not info['reason'] or len(info['reason']) < 8:
                problems.append('%s 的理由太短/为空' % name)
            if not info['when'] or len(info['when']) < 4:
                problems.append('%s 缺复核时机' % name)
            if name not in by_name:
                problems.append('%s 在 requirements.txt 里已不存在（清单腐烂）' % name)
                continue
            # 例外 = 确实仍无边界；补上边界后就该从清单里删掉
            if all(has_bound(spec) for spec, _ln in by_name[name]):
                problems.append('%s 已补上版本边界，请从例外清单移除' % name)
        self.assertEqual(problems, [], '「无界依赖例外清单」台账不自洽：%r' % problems)

    def test_03_detector_flags_injected_unbounded_dep(self):
        """反向自证：注入一个无界依赖，检测器必须能捞出来（否则是假绿）。"""
        probe = self.text + '\nwebsocket-client\n'
        caught = [name for name, _ln, _raw in unbounded_requirements(probe)]
        self.assertIn('websocket-client', caught,
                      '检测器抓不到新增的无界依赖，本守卫形同虚设：%r' % caught)
        # 已登记的例外项不该被误报
        for name in exception_entries(self.text):
            self.assertNotIn(name, caught, '例外清单里的 %s 被误判成漏登记' % name)

    def test_04_measured_floors_are_kept_and_sourced(self):
        """A 类下界不得被下调，且必须写明来源（开发环境实测）。"""
        for name, floor in MEASURED_FLOORS.items():
            hits = [(spec, raw) for n, spec, raw, _ln in self.lines if n == name]
            self.assertTrue(hits, 'requirements.txt 缺少 A 类依赖 %s' % name)
            found = any(has_bound(spec) and version_tuple(
                re.search(r'>=?\s*([0-9][\w.\-]*)', spec_core(spec)).group(1)) >=
                version_tuple(floor) for spec, _raw in hits
                if re.search(r'>=?\s*([0-9][\w.\-]*)', spec_core(spec)))
            self.assertTrue(found,
                            '%s 的下界被下调到实测版本 %s 以下（或边界丢失）' % (name, floor))
            self.assertTrue(any(MEASURED_NOTE in raw for _spec, raw in hits),
                            '%s 的下界行没有写明「%s」（红线：版本号必须有出处）'
                            % (name, MEASURED_NOTE))


class Python39AndDeliveryDocTest(unittest.TestCase):
    """交付口径：`py<3.9` 分档 + 文档写清 EOL，SECURITY.md 指向该章节。"""

    def setUp(self):
        self.req = read(REQ)

    def test_05_py39_branches_still_four(self):
        branch = {name for name, spec, _raw, _ln in requirement_lines(self.req)
                  if "python_version < '3.9'" in spec}
        self.assertEqual(
            sorted(PY39_BRANCH_PACKAGES), sorted(branch),
            "`python_version < '3.9'` 过渡分档应为 %r 四处，实际 %r"
            '（提前移除会让 CentOS 7 / Debian 10 装不上；移除必须等到 %s）'
            % (list(PY39_BRANCH_PACKAGES), sorted(branch), EOL_DATE))

    def test_06_lifecycle_doc_declares_python_support_and_eol(self):
        self.assertTrue(os.path.isfile(LIFECYCLE_DOC), '缺少《组件生命周期与安全响应政策》')
        doc = read(LIFECYCLE_DOC)
        self.assertIn(DOC_SECTION, doc,
                      '文档缺少「%s」章节（py<3.9 口径没写进交付说明）' % DOC_SECTION)
        self.assertIn(EOL_DATE, doc, '文档未写明 Python <3.9 分档的 EOL 日期 %s' % EOL_DATE)
        self.assertIn('3.9', doc, '文档未点名 Python 3.9')
        for phrase in ('CentOS 7', 'Debian 10', '已知残留风险'):
            self.assertIn(phrase, doc,
                          '文档的 Python 版本支持说明缺少关键口径：%s' % phrase)

    def test_07_security_md_points_to_that_section(self):
        text = read(SECURITY_MD)
        self.assertIn(DOC_SECTION, text,
                      'SECURITY.md「已知取舍」没有指向文档的「%s」章节' % DOC_SECTION)
        self.assertIn('组件生命周期与安全响应政策', text,
                      'SECURITY.md 的指向没给出文档名，读者找不到出处')

    def test_08_release_workflow_still_ships_requirements_lock(self):
        entries = release_files_entries()
        self.assertIn('dist/requirements.lock', entries,
                      'release.yml 的 files: 附件清单里没有 requirements.lock（P1-9 回退）：%r'
                      % entries)


class LockHashVerifierTest(unittest.TestCase):
    """`scripts/verify_requirements_lock.py`：正反两路都要真的会动。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='yf_lock_verify_')
        cls.good = os.path.join(cls.tmp, 'good.lock')
        cls.missing = os.path.join(cls.tmp, 'missing_hash.lock')
        cls.truncated = os.path.join(cls.tmp, 'truncated_hash.lock')
        cls.absent = os.path.join(cls.tmp, 'not_generated.lock')

        # 夹具一：合规（两个包，各自带完整 64 位 sha256）
        cls._write(cls.good, '\n'.join([
            '#',
            '# This file is autogenerated by pip-compile with Python 3.11',
            '#    pip-compile --generate-hashes --output-file requirements.lock requirements.txt',
            '#',
            'flask==3.1.3 \\',
            _hash_line('1') + ' \\',
            _hash_line('2'),
            '    # via -r requirements.txt',
            'pyyaml==6.0.2 \\',
            _hash_line('3'),
            '    # via -r requirements.txt',
            '',
        ]))
        # 夹具二：缺哈希（pyyaml / pip 两行没有 --hash）
        cls._write(cls.missing, '\n'.join([
            '# autogenerated by pip-compile',
            'flask==3.1.3 \\',
            _hash_line('1'),
            '    # via -r requirements.txt',
            'pyyaml==6.0.2',
            '    # via -r requirements.txt',
            'pip==24.0',
            '',
        ]))
        # 夹具三：哈希被截断（63 位）—— 「形似哈希」也要拦
        cls._write(cls.truncated, '\n'.join([
            '# autogenerated by pip-compile',
            'requests==2.32.4 \\',
            _hash_line('a', 63),
            '',
        ]))

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _write(path, text):
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)

    def test_09_verifier_accepts_compliant_lock(self):
        self.assertTrue(os.path.isfile(LOCK_VERIFIER),
                        '缺少 scripts/verify_requirements_lock.py')
        code, out = run_verifier(self.good)
        self.assertEqual(code, 0, '合规模具被判红（脚本误报）：%s' % out)
        self.assertIn('[通过]', out, '合规时应给出通过摘要：%s' % out)

    def test_10_verifier_rejects_lock_without_hash(self):
        code, out = run_verifier(self.missing)
        self.assertEqual(code, 1, '缺哈希的锁文件必须判红，实际退出码 %d：%s' % (code, out))
        self.assertIn('pyyaml==6.0.2', out, '报错未点名缺少哈希的包：%s' % out)
        self.assertIn('pip==24.0', out, '报错未点名缺少哈希的包：%s' % out)
        # 合规的那一行不该被误报
        self.assertNotIn('- flask==3.1.3', out, '合规的包被误报：%s' % out)

    def test_11_verifier_rejects_truncated_hash(self):
        code, out = run_verifier(self.truncated)
        self.assertEqual(code, 1, '被截断的 sha256 摘要必须判红：%s' % out)
        self.assertIn('requests==2.32.4', out, '报错未点名摘要非法的包：%s' % out)

    def test_12_absent_lock_is_not_a_failure(self):
        """锁文件不入库：本地没有它属于正常，不能因此判红（把关点在 release 流程）。"""
        code, out = run_verifier(self.absent)
        self.assertEqual(code, 0, '锁文件不存在时不该判红（离线开发常态）：%s' % out)
        self.assertIn('release', out, '未生成时应提示「按 release 流程生成」：%s' % out)

    def test_13_repo_default_path_is_consistent(self):
        """不带参数跑一次仓库默认路径：退出码必须 0（未生成 → 0；已生成 → 必须全部带哈希）。"""
        code, out = run_verifier(None)
        self.assertEqual(code, 0,
                         '仓库默认 requirements.lock 校验未通过（若已提交锁文件，说明缺哈希）：%s'
                         % out)
        if os.path.isfile(DEFAULT_LOCK):
            self.assertIn('[通过]', out, '已存在锁文件却未给出通过摘要：%s' % out)


class RequirementsFileDecodabilityTest(unittest.TestCase):
    """`requirements.txt` 必须自带 coding cookie —— 否则 pip 在非 UTF-8 locale 下崩。

    2026-10-23 实测（Windows 10 / GBK 控制台 / pip 23.0.1）：

        pip install -r requirements.txt
        UnicodeDecodeError: 'gbk' codec can't decode byte 0xa3 in position 90

    一个包都装不上。原因：pip 的 `auto_decode()` 只在「有 BOM」或「前两行有
    `coding[:=]<enc>` 声明」时才按 UTF-8 解码，否则回落到 `locale.getpreferredencoding()`
    —— 本文件满是中文注释，GBK 必然解不开。

    为什么 CI 没暴露：Linux 上 PEP 538 会把 C locale 强制成 C.UTF-8，于是「碰巧能读」。
    这种「只有 Linux CI 绿」的坑一旦反过来（比如某天 runner 的 locale 变了），
    就会表现成「依赖装不上 → 一堆用例 ModuleNotFoundError」，极难归因。
    """

    def test_14_requirements_declares_utf8_coding(self):
        with open(REQ, 'rb') as fp:
            head = fp.read(4096).decode('utf-8', 'replace')
        first_two = head.split('\n')[:2]
        self.assertTrue(
            any(re.search(r'coding[:=]\s*utf-8', line, re.I) for line in first_two),
            'requirements.txt 前两行没有 UTF-8 coding cookie（pip 会用 locale 编码解码，'
            '在 GBK/CP1252 环境下直接 UnicodeDecodeError）：前两行=%r' % (first_two,))

    def test_15_file_is_really_valid_utf8(self):
        """cookie 只是「声明」；文件本身必须真的是合法 UTF-8（否则 pip 解出乱码）。"""
        with open(REQ, 'rb') as fp:
            raw = fp.read()
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            self.fail('requirements.txt 不是合法 UTF-8：%s' % exc)
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'),
                         'requirements.txt 带了 UTF-8 BOM（pip 虽能处理，但会把首行注释'
                         '变成正文，破坏注释语义）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
