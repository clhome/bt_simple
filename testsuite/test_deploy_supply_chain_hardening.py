# coding: utf-8
"""供应链 fail-closed 守卫（测评报告 P0-4）。

锁死四件事，任何一件被改回 fail-open 都必须让门禁变红：

  1. `YF_REQUIRE_SIGNATURE` 默认值为 **1**（fail-closed），且验签失败分支
     必须 `exit 1` 中止、只允许显式 `YF_REQUIRE_SIGNATURE=0` 才回退；
  2. deploy.sh 中**不存在**「下载脚本后管道执行」形态（`curl ... | sh` / `| bash`）；
  3. acme.sh 安装必须先 sha256 校验通过再执行，校验和为空或校验失败一律拒绝；
  4. `-k` / `--no-check-certificate` 附近有理由注释（老系统 CA 缺失 + 后续验签兜底），
     代理列表处注明「仅作传输加速、关键产物必须验签」，README 有「安装前校验」小节。

变异自证见 `test/p0_supply_mutation_probe.py`（把上述修复逐条改回坏写法，守卫须全红）。
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DEPLOY = os.path.join(ROOT, 'deploy.sh')
README = os.path.join(ROOT, 'README.md')
RELEASE_WF = os.path.join(ROOT, '.github', 'workflows', 'release.yml')

#: 「下载脚本后管道执行」的判定：管道右侧是 sh/bash（可带 sudo）。
PIPE_TO_SHELL = re.compile(r'\|\s*(?:sudo\s+)?(?:sh|bash)(?:\s|$)')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _non_comment_lines(text):
    """返回 [(行号, 行内容)]，跳过整行注释（避免注释里的示例写法误报）。"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('#'):
            continue
        out.append((i, line))
    return out


class DeploySupplyChainHardeningTest(unittest.TestCase):

    def test_01_signature_default_is_fail_closed(self):
        """YF_REQUIRE_SIGNATURE 默认必须是 1，且失败分支真的中止安装。"""
        text = _read(DEPLOY)

        m = re.search(r'^YF_REQUIRE_SIGNATURE="\$\{YF_REQUIRE_SIGNATURE:-(\d+)\}"',
                      text, re.M)
        self.assertIsNotNone(m, 'deploy.sh 找不到 YF_REQUIRE_SIGNATURE 默认值赋值')
        self.assertEqual(m.group(1), '1',
                         'YF_REQUIRE_SIGNATURE 默认值必须为 1（全量 fail-closed）')

        block = re.search(r'if \[ "\$YF_REQUIRE_SIGNATURE" = "1" \]; then(.*?)\n    fi',
                          text, re.S)
        self.assertIsNotNone(block, '找不到 YF_REQUIRE_SIGNATURE=1 的 fail-closed 分支')
        self.assertIn('exit 1', block.group(1),
                      'fail-closed 分支必须中止安装（exit 1），不得静默继续')

        # 必须给出显式手动绕过指引（只认 YF_REQUIRE_SIGNATURE=0）
        self.assertIn('YF_REQUIRE_SIGNATURE=0', text,
                      '缺少显式关闭校验（YF_REQUIRE_SIGNATURE=0）的绕过指引')
        # 旧的 fail-open 措辞不得回归
        self.assertNotIn('本次跳过签名校验（不影响安装）', text,
                         '旧的「跳过签名校验」fail-open 措辞仍在')

    def test_02_no_pipe_to_shell(self):
        """红线：deploy.sh 不得出现「下载脚本后管道执行」。"""
        text = _read(DEPLOY)
        offenders = [(ln, line.strip())
                     for ln, line in _non_comment_lines(text)
                     if PIPE_TO_SHELL.search(line)]
        self.assertEqual(
            offenders, [],
            'deploy.sh 出现 pipe-to-shell（供应链红线）：%r' % (offenders,))
        self.assertNotIn('get.acme.sh', text,
                         '仍在用 get.acme.sh 的管道安装脚本')

    def test_03_acme_sha256_verified_before_exec(self):
        """acme.sh 必须固定版本 + sha256 校验通过后才执行，且失败即拒绝。"""
        text = _read(DEPLOY)

        ver = re.search(r'^YF_ACME_VERSION="\$\{YF_ACME_VERSION:-([^}]+)\}"', text, re.M)
        self.assertIsNotNone(ver, '缺少 acme.sh 固定版本常量 YF_ACME_VERSION')
        self.assertRegex(ver.group(1), r'^\d+\.\d+\.\d+$',
                         'acme.sh 版本必须是具体 tag（形如 3.1.6），不得为 master')

        sha = re.search(r'^YF_ACME_SHA256="\$\{YF_ACME_SHA256:-([0-9a-fA-F]{64})\}"',
                        text, re.M)
        self.assertIsNotNone(sha, '缺少 64 位 acme.sh 期望 sha256 常量')

        self.assertIn('refs/tags/${YF_ACME_VERSION}', text,
                      'acme.sh 下载 URL 必须指向固定 tag')
        self.assertNotIn('acme.sh/archive/master.tar.gz', text,
                         'acme.sh 仍指向 master 分支（未固定版本）')

        # 校验分支存在
        self.assertIn('!= "$YF_ACME_SHA256"', text, '缺少 sha256 比对分支')
        self.assertIn('拒绝执行未校验的安装包', text,
                      '缺少「哈希未配置即拒绝」的 fail-closed 分支')
        self.assertIn('拒绝执行该安装包', text, '缺少「校验失败即拒绝」的 fail-closed 分支')

        # 执行必须在校验之后
        self.assertLess(text.index('!= "$YF_ACME_SHA256"'),
                        text.index('./acme.sh --install'),
                        'acme.sh 安装执行出现在 sha256 校验之前')

    def test_04_k_flag_and_proxy_have_reason_comments(self):
        """-k / --no-check-certificate 附近必须有理由注释；代理列表须注明仅传输加速。"""
        text = _read(DEPLOY)
        lines = text.splitlines()

        targets = [i for i, l in enumerate(lines)
                   if re.search(r'-k\s|--no-check-certificate', l)]
        self.assertTrue(targets, 'deploy.sh 里找不到 -k / --no-check-certificate 使用点')
        for i in targets:
            ctx = '\n'.join(lines[max(0, i - 4):i + 1])
            self.assertTrue(
                any(k in ctx for k in ('CA', '兜底', '验签', 'sha256')),
                '第 %d 行的 TLS 放宽缺少理由/兜底注释：%s' % (i + 1, lines[i].strip()))

        proxy_block = re.search(r'# 引导期代理列表(.*?)YF_BOOTSTRAP_PROXY_LIST=\(', text, re.S)
        self.assertIsNotNone(proxy_block, '找不到引导期代理列表注释块')
        self.assertIn('代理', proxy_block.group(0))
        self.assertIn('验签', proxy_block.group(0),
                      '代理列表处未注明「关键产物必须验签」')

    def test_05_readme_has_preinstall_verification(self):
        """README 必须有「安装前校验」小节，给出 sha256 核对命令与期望值来源。"""
        readme = _read(README)
        self.assertIn('安装前校验', readme, 'README 缺少「安装前校验」小节')
        self.assertIn('sha256sum deploy.sh', readme,
                      'README 缺少 `sha256sum deploy.sh` 核对命令')
        self.assertIn('deploy.sh.sha256', readme,
                      'README 未说明期望值来自 Release 的 deploy.sh.sha256')

    def test_06_release_workflow_publishes_deploy_sh_sha256(self):
        """发布工作流必须自动生成 deploy.sh.sha256 并作为 Release 附件上传。"""
        wf = _read(RELEASE_WF)
        self.assertIn('sha256sum deploy.sh', wf,
                      'release.yml 未生成 deploy.sh 的 sha256')
        self.assertIn('deploy.sh.sha256', wf,
                      'release.yml 未把 deploy.sh.sha256 作为发布产物')


if __name__ == '__main__':
    unittest.main()
