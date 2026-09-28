# coding: utf-8
"""
供应链与自动更新守卫（P0-1 / G2）

锁死两件事，防止它们在后续迭代里被改回去：

1. **不得再有「下载脚本后直接执行」的自我更新路径。**
   历史实现是 `bash <(curl -fsSL https://panel.yftec.top/deploy.sh) update`：
   从第三方域名拉脚本、无任何校验、以 root 执行，而且安装时还自动写入月度
   计划任务 —— 域名被劫持/过期即全网 RCE。现改为执行本地 deploy.sh
   （它自己走「已签名发布包 + 验签」）。

2. **自动更新默认关闭，且关闭时会移除历史遗留任务。**
   否则老机器会永远带着那个高危任务跑下去。

另含 release.yml 的结构守卫：必须「出包 → 签名 → 自验 → 上传三件套」，
且缺 Secret 时必须失败而不是静默产出未签名包。
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _fn_body(text, signature):
    """取一个 bash 函数体（从签名行到列 0 的 `}`）。"""
    lines = text.split('\n')
    start = next(i for i, ln in enumerate(lines) if ln.startswith(signature))
    for i in range(start + 1, len(lines)):
        if lines[i] == '}':
            return '\n'.join(lines[start:i + 1])
    raise AssertionError('函数 %s 未闭合' % signature)


class SupplyChainGuardTest(unittest.TestCase):

    # ------------------------------------------------------------ 自我更新路径

    def test_01_yf_tpl_has_no_process_substitution_curl(self):
        """除 `yf_mirror` 外，yf.tpl 不得出现 `<(curl`。

        为什么要剥注释：本文件在描述历史漏洞时就会写到 `bash <(curl ...)`，
        那是说明文字、不会执行，不应该让守卫误报。

        为什么放行 `yf_mirror`：它是**用户主动执行**的「切换系统软件源」助手，
        调用的是社区通用脚本（linuxmirrors.cn / supermanito/LinuxMirrors），
        与「无人值守自动更新面板」是两回事。数量也锁死为 2，
        新增任何一处都要先动本用例 —— 逼一次人工判断。
        """
        text = _read('scripts/init.d/yf.tpl')
        # 剥掉整行注释（保留行号：用等长空格替换）
        stripped = '\n'.join(
            ('' if ln.lstrip().startswith('#') else ln) for ln in text.split('\n'))

        hits = [stripped[:m.start()].count('\n') + 1
                for m in re.finditer(r'<\(curl', stripped)]

        # 全部命中必须落在 yf_mirror 函数体内
        lines = stripped.split('\n')
        start_line = next(i for i, ln in enumerate(lines, 1)
                          if ln.startswith('yf_mirror()'))
        end_line = start_line
        for i in range(start_line, len(lines)):
            if lines[i] == '}':
                end_line = i + 1
                break
        mirror_hits = [ln for ln in hits if start_line <= ln <= end_line]
        outside = [ln for ln in hits if ln not in mirror_hits]

        self.assertEqual(
            outside, [],
            'yf.tpl 中 `<(curl` 只能出现在 yf_mirror（用户主动换源）内；'
            '自我更新必须执行本地 ${PANEL_DIR}/deploy.sh。越界行号=%r' % outside)
        self.assertEqual(
            len(mirror_hits), 2,
            'yf_mirror 的 `<(curl` 数量变了（期望 2，实际 %d）；'
            '新增前请先确认它不是自我更新路径' % len(mirror_hits))

        # 关键：自我更新函数体内一个都不允许
        for fn in ('yf_install(){', 'yf_update()', 'yf_update_dev()',
                   'yf_update_venv()', 'yf_rollback(){'):
            body = _fn_body(stripped, fn)
            self.assertNotIn('<(curl', body, '%s 内又出现了下载即执行的写法' % fn)

    def test_02_yf_tpl_self_update_uses_local_deploy(self):
        """install/update/update_dev/venv/rollback 必须经 yf_require_deploy_script 解析本地脚本。"""
        text = _read('scripts/init.d/yf.tpl')
        self.assertIn('yf_require_deploy_script()', text)
        for fn in ('yf_install(){', 'yf_update()', 'yf_update_dev()',
                   'yf_update_venv()', 'yf_rollback(){'):
            body = _fn_body(text, fn)
            self.assertIn('yf_require_deploy_script', body,
                          '%s 未走本地 deploy.sh 解析器' % fn)
        # 缺脚本时必须拒绝执行，而不是回退到网络
        self.assertIn('未找到本地更新脚本', text)

    def test_03_rollback_command_registered(self):
        """`yf rollback` 必须在帮助与命令分发里都注册。"""
        text = _read('scripts/init.d/yf.tpl')
        self.assertIn('yf rollback', text, '帮助列表未列出 rollback')
        self.assertRegex(text, r"'rollback'\)\s*yf_rollback",
                         '命令分发未注册 rollback')

    def test_04_deploy_sh_has_rollback_subcommand(self):
        text = _read('deploy.sh')
        self.assertIn('rollback_panel() {', text, '缺少 rollback_panel 实现')
        self.assertRegex(text, r"\n\s*rollback\)\n\s*SILENT_MODE=true\n\s*rollback_panel",
                         'main() 未注册 rollback 子命令')
        # 回滚本身必须可回滚：解压前先另存当前状态
        self.assertIn('yufeng_panel.prerollback.', text)
        # 预存归档不能匹配 `yufeng_panel-*`，否则「再回滚一次」会选到回滚后的状态
        self.assertNotIn('yufeng_panel-${ts}.tar.gz', text)

    # ------------------------------------------------------------ 自动更新

    def test_05_auto_update_default_off_and_removes_legacy_cron(self):
        """自动更新默认关闭；关闭时必须移除已存在的历史任务。"""
        text = _read('web/admin/setup/init_cron.py')
        self.assertIn("getOption('auto_update', default='no')", text,
                      '自动更新默认值必须是 no（默认关闭）')
        m = re.search(r'def init_auto_update\(\):(.*?)\n\ndef ', text, re.S)
        self.assertIsNotNone(m, '找不到 init_auto_update')
        body = m.group(1)
        self.assertIn('if not enabled:', body)
        self.assertIn('.delete()', body,
                      '关闭自动更新时必须删除历史遗留的计划任务，否则老机器会一直带着它')
        # 默认值不得被改回 yes
        self.assertNotIn("default='yes')", body)

    def test_06_setting_endpoint_syncs_cron_immediately(self):
        """设置页开关必须立即同步计划任务，而不是等下次启动。"""
        text = _read('web/admin/setting/setting.py')
        self.assertIn('/set_auto_update_status', text)
        seg = text[text.index('/set_auto_update_status'):]
        seg = seg[:seg.index('\n@blueprint.route')] if '\n@blueprint.route' in seg else seg
        self.assertIn('init_auto_update', seg, '开关未同步计划任务')
        self.assertIn('@panel_login_required', seg, '开关必须要求登录')

    # ------------------------------------------------------------ release.yml

    def test_07_release_workflow_signs_and_verifies(self):
        text = _read('.github/workflows/release.yml')
        for need in ('git archive', 'yf_release_sign.py release', 'yf_release_verify.py',
                     'SHA256SUMS.minisig', 'secrets.YF_RELEASE_KEY'):
            self.assertIn(need, text, 'release.yml 缺少：%s' % need)
        # 缺密钥必须失败，不得静默产出未签名包
        self.assertRegex(text, r'if \[ -z "\$\{YF_RELEASE_KEY\}" \]; then[\s\S]{0,200}exit 1',
                         '缺少 YF_RELEASE_KEY 时必须直接失败')
        # 三个附件都要上传
        for asset in ('yf-panel-', 'SHA256SUMS', 'SHA256SUMS.minisig'):
            self.assertIn(asset, text.split('files:')[-1],
                          'Release 附件缺少 %s' % asset)

    def test_08_release_workflow_asserts_tag_matches_version(self):
        text = _read('.github/workflows/release.yml')
        self.assertIn('APP_SMALL_VERSION', text, '未校验 tag 与 version.py 一致')
        self.assertIn('APP_RELEASE', text)
        self.assertIn('不一致', text)

    def test_09_release_workflow_excludes_dev_artifacts(self):
        """发布包自检必须包含「禁止项」断言，防止把开发产物下发给客户。"""
        text = _read('.github/workflows/release.yml')
        for forbid in ('testsuite/', '文档/', 'cl_tasks/', '.i18n.bak'):
            self.assertIn(forbid, text,
                          'release.yml 未校验发布包不得包含 %s' % forbid)

    def test_11_db_selfheal_commands_registered(self):
        """`yf db-check` / `yf migrate` 必须注册并出现在帮助里。

        用户要求「升级后 sqlite 能自愈」——除了升级流程自动跑，
        还需要给用户一个可自助诊断/修复的入口（出事时能自救，不必等我们）。
        """
        text = _read('scripts/init.d/yf.tpl')
        for cmd in ('db-check', 'migrate'):
            self.assertIn('yf %s' % cmd, text, '帮助列表未列出 %s' % cmd)
            self.assertRegex(text, r"'%s'\)\s*yf_" % re.escape(cmd),
                             '命令分发未注册 %s' % cmd)
        self.assertIn('yf_db_check(){', text)
        self.assertIn('yf_migrate(){', text)
        # 两者都必须经本地 deploy.sh 转发（不得自己另写一套路径解析）
        self.assertIn('bash "${script}" db-check', text)
        self.assertIn('bash "${script}" migrate', text)

    def test_12_security_scan_workflow_present(self):
        """H4：供应链安全扫描必须存在，且口径不能被默默改弱。"""
        path = os.path.join(ROOT, '.github/workflows/security-scan.yml')
        self.assertTrue(os.path.isfile(path), '缺少安全扫描 workflow')
        text = _read('.github/workflows/security-scan.yml')
        # 三类扫描都要在
        for tool in ('pip-audit', 'bandit', 'ruff'):
            self.assertIn(tool, text, '缺少 %s' % tool)
        # bandit 只能阻断 HIGH（-lll）；改成全量阻断会让门禁被无视
        self.assertIn('-lll', text)
        # 不得把阻断型 job 改成 continue-on-error（那是假门禁）
        self.assertNotIn('continue-on-error: true', text)
        # 必须有定时巡检（CVE 新披露不会发 PR）
        self.assertIn('schedule:', text)
        self.assertIn('cron:', text)
        # 无 Tab 缩进
        for i, line in enumerate(text.split('\n'), 1):
            self.assertNotRegex(line, r'^\t', 'YAML 第 %d 行用了 Tab 缩进' % i)

    def test_13_dev_requirements_separated(self):
        """开发依赖必须与运行依赖分开（扫描器不能下发到用户机器）。"""
        dev = _read('requirements-dev.txt')
        for tool in ('pip-audit', 'bandit', 'ruff'):
            self.assertIn(tool, dev)
        runtime = _read('requirements.txt')
        for tool in ('pip-audit', 'bandit', 'ruff'):
            self.assertNotIn(tool, runtime,
                             '%s 不应出现在运行依赖里' % tool)

    def test_10_release_workflow_yaml_parses(self):
        raw = _read('.github/workflows/release.yml')

        # 先做不依赖第三方库的结构检查（保证本机也能真跑，而不是「跳过了当通过」）
        self.assertRegex(raw, r'(?m)^jobs:\s*$', 'YAML 缺少顶层 jobs')
        self.assertRegex(raw, r'(?m)^\s+release:\s*$', 'YAML 缺少 release job')
        self.assertRegex(raw, r'(?m)^\s+steps:\s*$', 'YAML 缺少 steps')
        for i, line in enumerate(raw.split('\n'), 1):
            self.assertNotRegex(
                line, r'^\t', 'YAML 第 %d 行用了 Tab 缩进（YAML 禁止）' % i)

        try:
            import yaml
        except ImportError:
            return          # 已用上面的轻量检查兼顾本机
        data = yaml.safe_load(raw)
        self.assertIn('jobs', data)
        self.assertIn('release', data['jobs'])
        self.assertIn('steps', data['jobs']['release'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
