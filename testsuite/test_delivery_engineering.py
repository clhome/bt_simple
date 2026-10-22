# coding: utf-8
"""交付工程守卫（测评报告 P1 第 9 条，4 个小项 + 一处跨项依赖）。

## 这个文件在守什么

P1-9 的 4 个子项里，3 个是「交付链路上根本没有这些产物」：

1. **9.2 gunicorn 日志无轮转**：`web/setting.py` 只把 gunicorn 的输出指到
   `logs/panel.log` / `logs/panel_error.log`，仓库里没有任何 logrotate 配置
   ⇒ 长期运行只涨不减，小盘 VPS 会被面板自己的日志写满根分区。
2. **9.4 交付文档与产物分发**：`SECURITY.md`、《组件生命周期与安全响应政策》不存在；
   `release.yml` 只上传 tar.gz / SHA256SUMS / 签名 / deploy.sh.sha256，
   而 `sbom.json` 与 `requirements.lock` 只在 `security-scan.yml` 里作为 CI artifact
   生成，用户拿不到。
3. **9.1 PHP CI**（P0-4 已完成）：只需纳入守卫防回退 —— 真装列表必须仍只有 82~85，
   且「下架版本必须被拒绝」这一步不能被删。

以及一处**跨项依赖**（本文件的第一优先级断言）：

4. **P1-1 的自升级是 fail-closed**：Release body 里没有 `sha256: <64hex>` 就拒绝升级，
   而 `RELEASE_TEMPLATE.md` 原本一行 sha256 都没有 ⇒ 每次发布都会让自升级被拒。
   现在模板里有 `sha256: __SHA256__` 注入点，`release.yml` 出包后把**实际摘要**渲染进
   `dist/RELEASE_BODY.md` 再当 `body_path`；同时 `SHA256SUMS` 必须收录 `yf.zip` 这个名字
   （面板把升级包固定落地成 `temp/yf.zip`，验签器按 basename 查表）。

## 断言口径

* 全部是**文本/结构断言**，零外部依赖（PyYAML 可选：装了就用 `yaml.safe_load` 真解析一遍
  `release.yml` 防把发布流程改坏，没装则退化为结构断言并 `skipTest` 掉解析那条）；
* 一律锚定「在正确的区块里」：例如 `sbom.json` 必须出现在 `files:` 附件清单里，
  只出现在生成步骤里不算数（否则「加了生成步骤但忘了上传」这种缺陷会漏过）；
* 变异自证（本轮实测，见报告）：删掉模板里的 `sha256:` 行 → 用例 1 变红；
  从 `files:` 删掉 `sbom.json` → 用例 6 变红；复原后全绿。
"""
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RELEASE_TEMPLATE = os.path.join(ROOT, 'RELEASE_TEMPLATE.md')
RELEASE_WF = os.path.join(ROOT, '.github', 'workflows', 'release.yml')
PHP_CI_WF = os.path.join(ROOT, '.github', 'workflows', 'python-app-php.yml')
SECURITY_MD = os.path.join(ROOT, 'SECURITY.md')
LIFECYCLE_MD = os.path.join(ROOT, '文档', '组件生命周期与安全响应政策.md')
LOGROTATE_TPL = os.path.join(ROOT, 'scripts', 'install', 'logrotate', 'yf-panel')
LOGROTATE_INSTALL = os.path.join(ROOT, 'scripts', 'install', 'logrotate', 'install.sh')
DEPLOY_SH = os.path.join(ROOT, 'deploy.sh')
CLI_SH = os.path.join(ROOT, 'cli.sh')

#: 模板里的 sha256 注入点（必须独占一行，避免被写成正文里的普通文字）
_SHA256_PLACEHOLDER_RE = re.compile(r'(?m)^sha256:[ \t]*__SHA256__[ \t]*$')


def read_text(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def release_wf_text():
    return read_text(RELEASE_WF)


def release_files_entries(text=None):
    """从 release.yml 取出 `files:` 附件清单（逐行去空白）。

    刻意不做「全文里有没有 sbom.json」这种松断言：那样只加生成步骤、忘了上传
    也会绿 —— 而忘上传正是这条整改要修的东西。

    用行扫描而不是正则：要按**缩进层级**截断块（`files: |` 的下级行缩进更深，
    遇到 `env:` 这类同级键就必须停），否则会把紧跟其后的 `env:` 也吃进来。
    """
    text = release_wf_text() if text is None else text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('files:'):
            continue
        tail = stripped[len('files:'):].strip()
        if tail not in ('|', '|-', '>', '>-', ''):
            continue
        base_indent = len(line) - len(line.lstrip())
        entries = []
        for nxt in lines[idx + 1:]:
            if not nxt.strip():
                continue
            indent = len(nxt) - len(nxt.lstrip())
            if indent <= base_indent:
                break
            entries.append(nxt.strip())
        if entries:
            return entries
    raise AssertionError('release.yml 里找不到 `files: |` 附件清单（发布流程被改坏了？）')


def find_posix_bash():
    """找一个能真正执行本地脚本的 bash；找不到返回 None。

    为何不直接用 `shutil.which('bash')`：Windows 上 PATH 里的 `bash` 可能是 WSL
    启动器（无法执行本地路径的脚本）。候选列表与
    `testsuite/test_install_scripts_hardening.py` 保持同一套。
    """
    candidates = [
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files (x86)\Git\bin\bash.exe',
        r'C:\Program Files\Git\usr\bin\bash.exe',
    ]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, timeout=30)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


def step_index(text, marker):
    """返回 marker 在 workflow 文本里的位置；找不到直接判失败（不返回 -1 蒙混）。"""
    idx = text.find(marker)
    if idx < 0:
        raise AssertionError('release.yml 里找不到标记：%r' % marker)
    return idx


class TestReleaseBodySha256Injection(unittest.TestCase):
    """用例 1：Release 正文必须有 sha256 注入点，且发布流程真的注入实际值。"""

    def test_01_template_has_sha256_injection_point(self):
        """RELEASE_TEMPLATE.md 必须含独占一行的 `sha256: __SHA256__` 注入点。"""
        self.assertTrue(os.path.isfile(RELEASE_TEMPLATE),
                        'RELEASE_TEMPLATE.md 不存在（发布正文模板丢失）')
        text = read_text(RELEASE_TEMPLATE)
        self.assertRegex(
            text, _SHA256_PLACEHOLDER_RE,
            'RELEASE_TEMPLATE.md 缺少 `sha256: __SHA256__` 注入点：'
            '面板自升级 fail-closed，正文没有 sha256 声明会直接拒绝升级')
        # 必须说明「该值由发布流程自动注入」，免得被人当成固定值手工填写
        self.assertIn('完整性校验', text, 'RELEASE_TEMPLATE.md 缺少「完整性校验」小节')
        self.assertIn('自动注入', text, 'RELEASE_TEMPLATE.md 未说明 sha256 由发布流程自动注入')

    def test_02_workflow_renders_body_with_real_sha256(self):
        """release.yml 必须用实际摘要渲染 dist/RELEASE_BODY.md，并把它作为 body_path。"""
        text = release_wf_text()

        # (a) 存在「算实际 sha256 并渲染正文」的步骤
        self.assertIn('hashlib.sha256', text,
                      'release.yml 没有计算实际 sha256 的步骤')
        self.assertIn('dist/RELEASE_BODY.md', text,
                      'release.yml 没有生成渲染后的正文 dist/RELEASE_BODY.md')
        self.assertIn('RELEASE_TEMPLATE.md', text,
                      'release.yml 没有读取 RELEASE_TEMPLATE.md 模板')
        self.assertIn('sha256: __SHA256__', text,
                      'release.yml 没有校验模板里的 sha256 注入点（模板退化会静默放过）')

        # (b) body_path 必须指向渲染产物，而不是静态模板
        self.assertIn('body_path: dist/RELEASE_BODY.md', text,
                      'body_path 未指向渲染后的正文')
        self.assertNotIn(
            'body_path: RELEASE_TEMPLATE.md', text,
            'body_path 仍指向静态模板：占位符不会被替换，自升级会被拒')

        # (c) `body` 与 `body_path` 互斥：不允许同时出现 `body: `
        self.assertIsNone(
            re.search(r'(?m)^[ \t]+body:[ \t]', text),
            'softprops/action-gh-release 的 body 与 body_path 互斥，不能同时传')

        # (d) 注入结果要能匹配面板侧的正则（update.py 要求 `sha256[:=]<64hex>`）
        self.assertIn("grep -qE '^sha256: [0-9a-f]{64}$' dist/RELEASE_BODY.md", text,
                      'release.yml 没有校验渲染结果里的 sha256 行格式')


class TestSelfUpgradePackageName(unittest.TestCase):
    """用例 2：SHA256SUMS 必须覆盖 `yf.zip`（面板自升级按这个 basename 查表）。"""

    def test_03_release_workflow_registers_yf_zip_in_sums(self):
        """发布流程必须在**签名之前**准备 dist/yf.zip，让清单收录这个名字。"""
        text = release_wf_text()

        # (a) 准备 yf.zip 的步骤存在
        prep_marker = '准备自升级通道的 yf.zip'
        prep_idx = step_index(text, prep_marker)
        self.assertIn('dist/yf.zip', text, 'release.yml 没有产出 dist/yf.zip')

        # (b) 签名步骤必须在它之后 —— 否则 SHA256SUMS 里不会有 yf.zip 这一行
        sign_idx = step_index(text, 'yf_release_sign.py release')
        self.assertGreater(
            sign_idx, prep_idx,
            'yf.zip 的准备步骤在签名之后：SHA256SUMS 不会收录 yf.zip，'
            '面板自升级会因「清单里没有该文件名的记录」被拒')

        # (c) 出包自验也要覆盖 yf.zip，别只验 tar.gz
        self.assertIn('--file   "dist/yf.zip"', text,
                      'release.yml 的出包自验没有覆盖 dist/yf.zip')

        # (d) SHA256SUMS 与 yf.zip 的关系必须写清楚（说明「自升级取 yf.zip 名」）
        self.assertIn('SHA256SUMS 必须收录这个名字', text,
                      'release.yml 未说明「SHA256SUMS 必须收录 yf.zip」这条约束')

        # (e) yf.zip 必须是 Release 附件之一（同时充当备用镜像）
        self.assertIn('dist/yf.zip', release_files_entries(),
                      'dist/yf.zip 不在 Release 附件清单里')


class TestSecurityPolicyDocs(unittest.TestCase):
    """用例 3 / 4：安全政策与组件生命周期政策文档存在，且 SLA 数字写具体。"""

    def test_04_security_md_has_report_channel_and_sla(self):
        """SECURITY.md：私密报告入口 + 72 小时受理 + 14 天修复版。"""
        self.assertTrue(os.path.isfile(SECURITY_MD), 'SECURITY.md 不存在')
        text = read_text(SECURITY_MD)
        self.assertIn('72', text, 'SECURITY.md 没有 72 小时口径')
        self.assertIn('14', text, 'SECURITY.md 没有 14 天修复口径')
        # 漏洞报告入口：优先 GitHub Security Advisory（私密），且明确不要公开 issue
        self.assertIn('security/advisories/new', text,
                      'SECURITY.md 没有给出 GitHub Security Advisory 私密报告入口')
        self.assertIn('不要用公开 issue', text,
                      'SECURITY.md 未禁止公开 issue 报漏洞')

    def test_05_lifecycle_policy_doc(self):
        """生命周期政策：组件清单 + EOL 处置 + 72/14 SLA + 「自担风险」放行。"""
        self.assertTrue(os.path.isfile(LIFECYCLE_MD),
                        '文档/组件生命周期与安全响应政策.md 不存在')
        text = read_text(LIFECYCLE_MD)
        for token in ('EOL', '72', '14', '自担风险'):
            self.assertIn(token, text, '生命周期政策缺少关键口径：%r' % token)
        # 被托管组件清单要真的列出来（只写「各组件」等于没写）
        for comp in ('PHP', 'MySQL', 'MariaDB', 'OpenResty', 'Redis', 'PostgreSQL'):
            self.assertIn(comp, text, '生命周期政策缺少组件：%s' % comp)
        # EOL 处置要与 P0-4 的实现对齐
        self.assertIn('YF_ALLOW_UNSAFE_PHP', text,
                      '生命周期政策未与 YF_ALLOW_UNSAFE_PHP 的「自担风险」实现对齐')
        self.assertIn('BASELINE_DATE', text,
                      '生命周期政策未说明与安全基线表 BASELINE_DATE 的关系')


class TestReleaseAttachments(unittest.TestCase):
    """用例 5：Release 附件必须含 sbom.json 与 requirements.lock。"""

    def test_06_files_list_has_sbom_and_lock(self):
        entries = release_files_entries()
        joined = '\n'.join(entries)
        self.assertIn('sbom.json', joined,
                      'release.yml 的 files: 附件清单里没有 sbom.json')
        self.assertIn('requirements.lock', joined,
                      'release.yml 的 files: 附件清单里没有 requirements.lock')

        text = release_wf_text()
        # 生成命令要与 security-scan.yml 保持同源（改一处必须同步另一处）
        self.assertIn('cyclonedx-py environment', text,
                      'release.yml 没有生成 SBOM 的命令（cyclonedx-py environment）')
        self.assertIn('pip-compile --generate-hashes', text,
                      'release.yml 没有生成依赖锁的命令（pip-compile --generate-hashes）')
        # 生成必须在签名之前：这样才能被 SHA256SUMS + 签名覆盖
        self.assertGreater(
            step_index(text, 'yf_release_sign.py release'),
            step_index(text, 'cyclonedx-py environment'),
            'SBOM 生成在签名之后：附件不会被 SHA256SUMS 覆盖')


class TestLogrotateDelivery(unittest.TestCase):
    """用例 6：logrotate 模板存在且被安装/部署脚本下发。"""

    def test_07_logrotate_template_and_dispatch(self):
        self.assertTrue(os.path.isfile(LOGROTATE_TPL),
                        'logrotate 模板不存在：scripts/install/logrotate/yf-panel')
        tpl = read_text(LOGROTATE_TPL)
        for token in ('copytruncate', 'rotate 14', 'daily', 'compress',
                      'missingok', 'notifempty'):
            self.assertIn(token, tpl, 'logrotate 模板缺少指令：%s' % token)
        # gunicorn 不响应 USR1，必须 copytruncate；同时要真的覆盖两条日志
        self.assertIn('panel.log', tpl, '模板未覆盖 logs/panel.log')
        self.assertIn('panel_error.log', tpl, '模板未覆盖 logs/panel_error.log')

        # 下发脚本：安装逻辑本体
        self.assertTrue(os.path.isfile(LOGROTATE_INSTALL),
                        'logrotate 下发脚本不存在：scripts/install/logrotate/install.sh')
        inst = read_text(LOGROTATE_INSTALL)
        self.assertIn('/etc/logrotate.d', inst,
                      '下发脚本没有写到 /etc/logrotate.d')
        self.assertIn('logrotate/yf-panel', inst,
                      '下发脚本没有引用模板 scripts/install/logrotate/yf-panel')

        # 引用点必须真实存在（否则模板进了仓库但装机时永远用不上）
        self.assertIn('scripts/install/logrotate/install.sh', read_text(DEPLOY_SH),
                      'deploy.sh 没有下发 logrotate 配置')
        self.assertIn('scripts/install/logrotate/install.sh', read_text(CLI_SH),
                      'cli.sh 没有在面板启动时自愈 logrotate 配置（自升级路径不跑 deploy.sh）')

        # 下发脚本自己的 shell 语法也要守：它不在 scripts/install/*.sh 的 bash -n
        # 扫描面里（多了一层子目录），破了没人会发现。找不到 bash 则跳过这条。
        bash = find_posix_bash()
        if not bash:
            self.skipTest('本机没有可用的 POSIX bash，跳过 bash -n 语法校验')
        proc = subprocess.run([bash, '-n', LOGROTATE_INSTALL], capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         'logrotate 下发脚本 bash -n 失败：%s' % (proc.stderr or proc.stdout))


class TestPhpCiUnsupportedGuard(unittest.TestCase):
    """用例 7：把 P0-4 的 PHP CI 成果纳入守卫，防回退。"""

    def test_08_php_ci_only_installs_82_to_85_and_rejects_old(self):
        self.assertTrue(os.path.isfile(PHP_CI_WF), 'python-app-php.yml 不存在')
        text = read_text(PHP_CI_WF)
        for ver in ('82', '83', '84', '85'):
            self.assertIn('Install PHP%s' % ver, text,
                          'PHP CI 缺少真装步骤：Install PHP%s' % ver)
        # 7.4 / 8.0 / 8.1 等已下架版本不得再出现在真装步骤里
        for retired in ('Install PHP74', 'Install PHP80', 'Install PHP81',
                        'Install PHP73', 'Install PHP56', 'Install PHP55'):
            self.assertNotIn(retired, text,
                             'PHP CI 又出现已下架版本的真装步骤：%s' % retired)
        self.assertIn('Unsupported PHP versions must be rejected', text,
                      'PHP CI 缺少「下架版本必须被拒绝」的断言步骤')


class TestReleaseWorkflowYamlShape(unittest.TestCase):
    """用例 8：release.yml 必须仍是合法 YAML，附件路径都指向 dist/。"""

    def test_09_yaml_parses_and_files_are_dist_paths(self):
        text = release_wf_text()
        # YAML 不允许 tab 缩进；这条与 PyYAML 无关，任何环境都能判
        self.assertNotIn('\t', text, 'release.yml 出现 tab 缩进（YAML 会解析失败）')

        try:
            import yaml
        except ImportError:  # pragma: no cover - CI 与 requirements.txt 都带 pyyaml
            self.skipTest('本机没有 PyYAML，跳过 safe_load 解析（结构断言已在上面执行）')

        data = yaml.safe_load(text)
        self.assertIsInstance(data, dict, 'release.yml 解析结果不是映射')
        self.assertIn('jobs', data, 'release.yml 缺少 jobs')
        steps = data['jobs']['release']['steps']
        self.assertIsInstance(steps, list, 'release.yml 的 jobs.release.steps 不是列表')

        # 附件清单里每一项都应是 dist/ 下的产物（防写错路径导致 action 静默漏传）
        for entry in release_files_entries():
            self.assertTrue(entry.startswith('dist/'),
                            'Release 附件路径不在 dist/ 下：%r' % entry)

        # action-gh-release 那一步必须同时有 body_path 与 files
        upload = [s for s in steps if 'action-gh-release' in str(s.get('uses', ''))]
        self.assertEqual(len(upload), 1,
                         'release.yml 里 action-gh-release 步骤数量异常：%d' % len(upload))
        with_block = upload[0].get('with') or {}
        self.assertIn('body_path', with_block, 'action-gh-release 缺少 body_path')
        self.assertIn('files', with_block, 'action-gh-release 缺少 files')


if __name__ == '__main__':
    unittest.main()
