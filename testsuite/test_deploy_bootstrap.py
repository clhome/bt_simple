# coding: utf-8
"""
deploy.sh 引导块漂移守卫（供应链可信 P0-1）

deploy.sh 为了能在「仓库尚未落地」时验签，内嵌了两份副本：
  1. 引导级校验器（与 scripts/tools/yf_release_verify.py 必须逐字节一致）
  2. 发布公钥（与 keys/yf-release.pub 必须逐字节一致）
以及一份代理列表（与 scripts/github_download.sh 的 _GH_PROXY_LIST 必须一致）。

这些副本一旦脱节，最坏结果是「本地验签通过、用户装机验签失败」或
「脚本能下的包、面板下不动」——都是极难排查的问题。所以这里做硬比对。

另外守一条红线：deploy.sh **不得再出现「下载脚本后 source 执行」的写法**，
那是本次要堵的供应链漏洞；一旦被重新引入，门禁直接变红。
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DEPLOY = os.path.join(ROOT, 'deploy.sh')
VERIFIER = os.path.join(ROOT, 'scripts', 'tools', 'yf_release_verify.py')
PUBKEY = os.path.join(ROOT, 'keys', 'yf-release.pub')
GH_DL = os.path.join(ROOT, 'scripts', 'github_download.sh')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _extract_py_str_list(text, name):
    """取出 Python 源码里 `NAME = [ "...", ... ]` 的字符串项（保持顺序）。"""
    m = re.search(re.escape(name) + r"\s*=\s*\[(.*?)\]", text, re.S)
    if not m:
        raise AssertionError('找不到 Python 列表：%s' % name)
    return re.findall(r'"([^"]*)"', m.group(1))


def _extract_heredoc(text, marker):
    """取出 `<<'MARKER'` 与单独一行 MARKER 之间的内容。"""
    start_pat = re.compile(r"<<'" + re.escape(marker) + r"'\n")
    m = start_pat.search(text)
    if not m:
        raise AssertionError('deploy.sh 中找不到 heredoc 起始标记 %s' % marker)
    body_start = m.end()
    end = text.find('\n' + marker, body_start)
    if end < 0:
        raise AssertionError('deploy.sh 中找不到 heredoc 结束标记 %s' % marker)
    return text[body_start:end + 1]


def _extract_bash_array(text, name):
    """取出 bash 数组定义里的条目（保持顺序，去掉空串也保留）。"""
    m = re.search(re.escape(name) + r"=\((.*?)\n\)", text, re.S)
    if not m:
        raise AssertionError('找不到 bash 数组：%s' % name)
    entries = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        line = line.rstrip(',')
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        entries.append(line)
    return entries


class DeployBootstrapGuardTest(unittest.TestCase):

    def test_01_embedded_verifier_matches_source(self):
        """deploy.sh 内嵌校验器必须与 scripts/tools/yf_release_verify.py 逐字节一致。"""
        deploy_text = _read(DEPLOY)
        embedded = _extract_heredoc(deploy_text, 'YF_VERIFY_EOF')
        source = _read(VERIFIER)
        if embedded != source:
            # 给出最小差异提示，便于定位（不做全文 diff 刷屏）
            e_lines = embedded.splitlines()
            s_lines = source.splitlines()
            first = None
            for i in range(max(len(e_lines), len(s_lines))):
                ev = e_lines[i] if i < len(e_lines) else '<缺失>'
                sv = s_lines[i] if i < len(s_lines) else '<缺失>'
                if ev != sv:
                    first = i + 1
                    break
            self.fail(
                'deploy.sh 内嵌的校验器与 %s 不一致（首个差异在第 %s 行）。\n'
                '请把 scripts/tools/yf_release_verify.py 的完整内容同步进 '
                "deploy.sh 的 <<'YF_VERIFY_EOF' 块。\n"
                '  deploy.sh: %r\n  source   : %r'
                % (os.path.relpath(VERIFIER, ROOT), first,
                   (embedded.splitlines()[first - 1] if first and first <= len(embedded.splitlines()) else ''),
                   (source.splitlines()[first - 1] if first and first <= len(source.splitlines()) else '')))

    def test_02_embedded_pubkey_matches_repo_key(self):
        """deploy.sh 内嵌公钥必须与 keys/yf-release.pub 严格一致。"""
        deploy_text = _read(DEPLOY)
        embedded = _extract_heredoc(deploy_text, 'YF_PUBKEY_EOF')
        source = _read(PUBKEY)
        self.assertEqual(
            embedded, source,
            'deploy.sh 内嵌公钥与 keys/yf-release.pub 不一致。\n'
            '轮换密钥后必须同时更新两处，否则旧 deploy.sh 的用户会全部验签失败。')

    def test_03_pubkey_is_parseable_or_explicitly_placeholder(self):
        """公钥必须处于「可解析」或「显式占位」两态之一，不允许是坏文件。"""
        sys.path.insert(0, os.path.join(ROOT, 'scripts', 'tools'))
        import yf_release_verify as verify
        text = _read(PUBKEY)
        if 'PLACEHOLDER_NOT_GENERATED' in text:
            with self.assertRaises(verify.VerifyError):
                verify.parse_public_key(text)
        else:
            keyid, pubkey_raw = verify.parse_public_key(text)
            self.assertEqual(keyid, verify.key_id(pubkey_raw))
            self.assertEqual(len(pubkey_raw), 32)

    def test_04_proxy_list_single_source(self):
        """代理列表必须单一真源：三处（shell 库 / deploy.sh 引导 / 面板 yf.py）逐项一致。

        用户明确要求（2026-09-28）：修改必须保证所有内置代理地址继续可用。
        实测历史上三处各写一份且**不一致**（面板侧少了 `gh.ddlc.top`），
        于是出现「同一个包在脚本里下得动、在面板里下不动」——大陆环境极难排查。
        本用例锁死：三处必须逐项相等，且都包含已知的全部代理。
        """
        deploy_text = _read(DEPLOY)
        gh_text = _read(GH_DL)
        yf_text = _read(os.path.join(ROOT, 'web', 'core', 'yf.py'))

        boot = _extract_bash_array(deploy_text, 'YF_BOOTSTRAP_PROXY_LIST')
        main = _extract_bash_array(gh_text, '_GH_PROXY_LIST')
        panel = _extract_py_str_list(yf_text, '_GITHUB_PROXY_LIST')

        self.assertEqual(
            boot, main,
            '代理列表已脱节：\n  deploy.sh 引导期 = %r\n  github_download.sh = %r' % (boot, main))
        self.assertEqual(
            panel, main,
            '面板侧代理列表与脚本侧脱节（会导致「脚本能下、面板下不动」）：\n'
            '  web/core/yf.py = %r\n  github_download.sh = %r' % (panel, main))

        # 已知代理一个都不能少（大陆可用性生命线，只许增不许减）
        for required in ('https://gh-proxy.com/', 'https://cors.zme.ink/',
                         'https://gh.ddlc.top/', 'https://ghproxy.net/'):
            self.assertIn(required, main, '代理被删了：%s' % required)
        self.assertEqual(main[0], '', '首位必须留空串（官方直连优先）')

        # deploy.sh 的 git 清理列表必须从单一真源派生，不得再手写一份
        self.assertIn('for _p in "${YF_BOOTSTRAP_PROXY_LIST[@]}"', deploy_text,
                      'setup_china_git_config 又手写了一份代理列表')

    def test_11_proxy_speed_test_table_derives_from_list(self):
        """测速表必须从代理列表派生，否则新增代理永远选不上。"""
        yf_text = _read(os.path.join(ROOT, 'web', 'core', 'yf.py'))
        self.assertIn('_GITHUB_PROXY_NAMED', yf_text)
        self.assertIn("test_list = {name: prefix for prefix, name in _GITHUB_PROXY_NAMED}",
                      yf_text, '测速表又变成手写字典了')
        self.assertNotIn('"gh.con.sh": "https://gh.con.sh/"', yf_text,
                         '测速表仍有手写副本')

    def test_05_no_remote_script_execution(self):
        """红线：deploy.sh 不得「下载脚本后 source 执行」。

        允许 source 的对象只有两类：
          (a) 本地仓库内已知路径（scripts/github_download.sh）；
          (b) 从**已验签**的发布包内导入的 scripts/github_download.sh。
        禁止出现 `source "$变量"` 且该变量来自网络下载的状态文件。
        """
        text = _read(DEPLOY)
        offenders = []
        for m in re.finditer(r'^\s*(?:\.|source)\s+(.+)$', text, re.M):
            arg = m.group(1).strip()
            if arg.startswith('"$_gh_deploy_lib"'):
                continue                      # (a) 本地仓库路径
            if arg.startswith('"$lib"') and 'github_download.sh' in text[max(0, m.start() - 400):m.start()]:
                continue                      # (b) 已验签发布包内的库
            offenders.append((text[:m.start()].count('\n') + 1, arg))
        self.assertEqual(
            offenders, [],
            'deploy.sh 中出现了未经许可的 source 目标（供应链红线）：%r' % (offenders,))

        # 反向断言：旧的「从 GitHub raw / 代理拉脚本再 source」写法必须已消失
        self.assertNotIn('raw.githubusercontent.com/clhome/bt_simple/master/scripts/github_download.sh',
                         text, '旧的远端脚本拉取路径仍在，未验签就可能执行远端代码')

    def test_06_deploy_sh_syntax(self):
        """deploy.sh 必须通过 bash 语法检查。

        跨平台注意：Windows 下 `bash` 可能是 WSL 的 bash，它不认识 `F:\\...`，
        会把「路径找不到」（126/127）与「语法错」（2）混在一起报。这里两者严格区分：
        所有候选路径都找不到 -> 跳过；只要能执行却语法错 -> 变红。
        """
        candidates = [DEPLOY]
        try:
            uni = subprocess.check_output(['cygpath', '-u', DEPLOY],
                                          stderr=subprocess.DEVNULL).decode().strip()
            if uni and uni != DEPLOY:
                candidates.insert(0, uni)
        except Exception:
            pass

        last_err = None
        for path in candidates:
            for bash in ('bash', '/bin/bash', '/usr/bin/bash'):
                try:
                    proc = subprocess.run([bash, '-n', path], capture_output=True)
                except FileNotFoundError:
                    continue
                if proc.returncode == 0:
                    return
                if proc.returncode in (126, 127):
                    last_err = proc.stderr.decode('utf-8', 'replace')
                    continue
                self.fail('deploy.sh 语法检查失败（%s -n %s）：\n%s'
                          % (bash, path, proc.stderr.decode('utf-8', 'replace')))
        self.skipTest('本机无可用 bash 检查该路径（Linux/CI 会执行）：%s' % last_err)

    def test_08_verification_scope_is_panel_release_only(self):
        """验签范围必须是「仅面板自身发布包」，不得漫延到第三方下载。

        用户明确要求（2026-09-28）：插件拉取的 openresty / php / mysql / jdk 等
        第三方仓库**不需要**用本项目的发布密钥验签。
        本用例把这条口径锁死：
          (a) yf_verify_release 只能在 yf_fetch_signed_release 里被调用；
          (b) 该函数只校验 yf-panel-<版本>.tar.gz 这一种产物；
          (c) 插件目录里不得出现发布公钥或发布校验器。
        """
        text = _read(DEPLOY)

        # (a) 调用点唯一（含函数定义共 2 处：1 定义 + 1 调用）
        calls = [text[:m.start()].count('\n') + 1
                 for m in re.finditer(r'(?<![\w-])yf_verify_release(?![\w-])', text)]
        self.assertEqual(
            len(calls), 2,
            'yf_verify_release 出现了 %d 次（应仅 1 处定义 + 1 处调用）；'
            '验签范围只能限定在面板自身发布包，禁止扩散到第三方下载。行号=%r'
            % (len(calls), calls))

        # (b) 只校验面板发布包这一种产物名
        self.assertIn('yf-panel-${ver}.tar.gz', text,
                      '发布包命名约定被改了：请同步 deploy.sh / release.yml / 文档')
        self.assertNotIn('verify_release("$work/openresty', text)
        self.assertNotIn('verify_release("$work/php', text)

        # (c) 发布公钥/校验器不得出现在插件目录
        leak = []
        plugins_dir = os.path.join(ROOT, 'plugins')
        for root, dirs, files in os.walk(plugins_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for fn in files:
                if fn in ('yf-release.pub', 'yf_release_verify.py'):
                    leak.append(os.path.relpath(os.path.join(root, fn), ROOT))
        self.assertEqual(leak, [],
                         '发布公钥/校验器不应出现在插件目录（第三方下载不走本项目验签）：%r' % leak)

    def test_09_signed_path_is_wired_and_permissive_by_default(self):
        """签名路径必须真的被调用，且当前默认放行（不阻断升级）。

        用户口径（2026-09-28）：先默认放行，待首个签名 Release 真机验证后再翻转为 fail-closed。
        本用例同时防止两件事：
          (a) 签名代码变成「写了但从不调用」的死代码；
          (b) 有人未经宣布就把默认改成 1（会阻断所有人的升级）。
        """
        text = _read(DEPLOY)

        # (a) 真的调用（定义 1 + 调用 1 = 2）
        calls = re.findall(r'(?<![\w-])yf_fetch_signed_release(?![\w-])', text)
        self.assertEqual(len(calls), 2,
                         'yf_fetch_signed_release 应恰好 1 处定义 + 1 处调用，实际 %d 处' % len(calls))

        # (b) 默认放行
        self.assertIn('YF_REQUIRE_SIGNATURE="${YF_REQUIRE_SIGNATURE:-0}"', text,
                      '签名强制开关的默认值被改了：翻转为 fail-closed 前需确认已有签名 Release 落地')
        self.assertIn('回退到 git clone（未验签，存在供应链风险）', text,
                      '回退路径必须保留醒目告警，不能静默降级')
        self.assertIn('YF_REQUIRE_SIGNATURE=1 bash deploy.sh', text,
                      '回退时必须给用户开启强制验签的明确指引')

        # 公钥未配置时必须在 test_10 单独校验（= 跳过而非失败）

    def test_10_placeholder_pubkey_semantics(self):
        """占位符必须是「跳过」语义（2），不得是「失败」语义（1）。"""
        text = _read(DEPLOY)
        seg = re.search(r'if \[ "\$YF_PUBKEY_PLACEHOLDER" = "1" \]; then(.*?)\n    fi', text, re.S)
        self.assertIsNotNone(seg, '找不到占位符判定块')
        self.assertIn('return 2', seg.group(1))
        self.assertNotIn('return 1', seg.group(1))

    def test_07_verifier_still_importable_after_embed(self):
        """内嵌副本本身必须是一段可独立执行的 Python（不是残缺文本）。"""
        deploy_text = _read(DEPLOY)
        embedded = _extract_heredoc(deploy_text, 'YF_VERIFY_EOF')
        self.assertIn("if __name__ == '__main__':", embedded)
        compile(embedded, 'embedded_verifier.py', 'exec')   # 语法错会直接抛


if __name__ == '__main__':
    unittest.main(verbosity=2)
