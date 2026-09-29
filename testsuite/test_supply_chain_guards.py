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

    def test_14_auto_update_ui_switch_wired(self):
        """G2.2：自动更新开关必须端到端接完（后端 option → 模板 → 前端 → 六语言词条）。

        只做后端不做前端 = 一个用户根本找不到的安全设置，等于没做。
        """
        # 1) 后端把 option 喂给模板
        cfg = _read('web/utils/config.py')
        self.assertIn("data['auto_update'] = thisdb.getOption('auto_update', default='no')", cfg)

        # 2) 模板开关（复用 use_cdn 的范式）
        tpl = _read('web/templates/default/setting.html')
        self.assertIn("id='panelAutoUpdate'", tpl)
        self.assertIn('onclick="setAutoUpdate()"', tpl)
        self.assertIn("data['auto_update'] == 'yes'", tpl)

        # 3) 前端调用后端端点
        js = _read('web/static/app/config.js')
        self.assertIn('function setAutoUpdate()', js)
        self.assertIn("/setting/set_auto_update_status", js)
        # 开启是高风险动作，必须先确认（不能一点就开）
        self.assertIn('layer.confirm', js[js.index('function setAutoUpdate()'):
                                        js.index('function doSetAutoUpdate()')])

        # 4) 六语言词条齐备
        for lang in ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'):
            text = _read('web/static/language/%s/lan.js' % lang)
            for key in ('"auto_update"', '"auto_update_tips"'):
                self.assertIn(key, text, '%s 缺少 %s' % (lang, key))

    def test_15_audit_identity_and_immutability(self):
        """G4：审计流水必须有身份、不可被一键抹除。"""
        yf_text = _read('web/core/yf.py')
        self.assertIn('def _logIdentity()', yf_text)
        # 不得再硬编码 uid=0
        self.assertNotIn('def writeLog(stype, msg, args=()):\n    # 写日志\n    uid = 0', yf_text)
        self.assertIn('audit.write_audit', yf_text)

        logs_text = _read('web/thisdb/logs.py')
        self.assertIn('def archiveLogs()', logs_text)
        self.assertIn("'uid':uid", logs_text.replace(' ', ''),
                      'addLog 仍未写入 uid（历史上那列永远是默认值）')
        self.assertIn("'ip':ip", logs_text.replace(' ', ''))

        audit_text = _read('web/core/audit.py')
        self.assertIn('def verify_chain(', audit_text)
        self.assertIn('prev_hash', audit_text)
        self.assertIn('row_hash', audit_text)

        sql = _read('web/admin/setup/sql/default.sql')
        self.assertIn('panel_audit', sql)

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
    # ------------------------------------------------------- H4 红色门禁修复

    def test_18_requirements_are_tiered_for_patched_versions(self):
        """H4：依赖漏洞修复不能被「为了兼容老 Python」而回退。

        flask/Werkzeug/pyOpenSSL/cryptography 的修复版均要求 Python>=3.9，
        故 requirements.txt 必须以 python_version 分档：
          >=3.9 走修复版；<3.9 保留旧版（上游无修复，属已知残留风险）。
        CI 的 pip-audit 以 Python 3.11 解析，只看得到 >=3.9 分支 → 门禁真实有效。
        """
        lines = [ln.strip() for ln in _read('requirements.txt').split('\n')]
        lines = [ln for ln in lines if ln and not ln.startswith('#')]

        def _name(ln):
            m = re.match(r'^([A-Za-z0-9_.\-]+)', ln)
            return m.group(1).lower() if m else ''

        floors = {'Flask': '3.1.3', 'Werkzeug': '3.1.6',
                  'pyOpenSSL': '26.4.0', 'cryptography': '50.0.0'}
        for pkg, floor in floors.items():
            hits = [ln for ln in lines if _name(ln) == pkg.lower()]
            modern = [ln for ln in hits if "python_version >= '3.9'" in ln]
            legacy = [ln for ln in hits if "python_version < '3.9'" in ln]
            self.assertTrue(modern, '%s 缺少 >=3.9 的修复版分支' % pkg)
            self.assertTrue(legacy, '%s 缺少 <3.9 的兼容分支（老系统会装不上面板）' % pkg)
            self.assertIn('>=%s' % floor, modern[0],
                          '%s 的 >=3.9 下界低于修复版本 %s：%s' % (pkg, floor, modern[0]))
            self.assertNotIn('python_version', legacy[0].split(';')[0],
                             '%s 的旧版本分支必须带 <3.9 标记' % pkg)

    def test_16_bandit_exemptions_are_justified(self):
        """H4：bandit 的每一处豁免都必须写清理由（防止门禁变成静默放行）。

        `# nosec Bxxx` 是绕过安全门禁的唯一手段，因此：
          1. 必须带理由尾注（`# nosec Bxxx  # 理由`），不能只挂一个豁免；
          2. 说明性注释不得以 `# nosec` 开头 —— bandit 会把它作用于下一行，
             可能掩盖真正的告警（踩过一次：注释里的 `# nosec B507：...`）。
        """
        files = ('panel_tools.py', 'scripts/logs_backup.py', 'web/core/yf.py',
                 'web/utils/site.py', 'web/utils/ssh/ssh_local.py',
                 'web/utils/ssh/ssh_terminal.py', 'scripts/tools/build_edition.py')
        total = 0
        for rel in files:
            for i, line in enumerate(_read(rel).split('\n'), 1):
                if '# nosec' not in line:
                    continue
                total += 1
                self.assertIn('  # ', line,
                              '%s:%d nosec 缺理由尾注：%s' % (rel, i, line.strip()))
                self.assertFalse(line.strip().startswith('# nosec'),
                                 '%s:%d 独立成行的 nosec 会误作用于下一行' % (rel, i))
        self.assertGreaterEqual(
            total, 25,
            'bandit 豁免数量异常减少（%d）；若确实是修好了某条，请同步调整本用例' % total)

    def test_17_basic_auth_no_longer_stores_md5(self):
        """B324 收口：basic_auth 与旧密码校验改走统一兼容层，不再自存 MD5。

        历史 MD5 只作为「一次性迁移凭据」由 checkPwdCompat 比对，
        新写入一律 bcrypt（hasPwd）。
        """
        setting = _read('web/admin/setting/setting.py')
        seg = setting[setting.index('def set_basic_auth'):
                      setting.index('def set_status_code')]
        self.assertNotIn('yf.md5(', seg, 'basic_auth 不得再用 MD5 存口令')
        self.assertIn('yf.hasPwd(', seg)

        init = _read('web/admin/__init__.py')
        seg2 = init[init.index("salt = basic_auth["):]
        seg2 = seg2[:seg2.index('sendAuthenticated()')]
        self.assertNotIn('yf.md5(', seg2, 'basic_auth 校验不得再用 MD5')
        self.assertIn('yf.checkPwdCompat(', seg2)

        yf_text = _read('web/core/yf.py')
        self.assertIn('def checkPwdCompat(', yf_text)
        self.assertIn('def isLegacyPwdHash(', yf_text)
        self.assertIn('# nosec B324', yf_text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
