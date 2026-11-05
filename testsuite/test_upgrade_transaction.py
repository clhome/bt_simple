# -*- coding: utf-8 -*-
"""面板自升级安装事务与前端失败契约回归测试。"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
if WEB not in sys.path:
    sys.path.insert(0, WEB)


class TestUpgradeMessagesAreTranslatable(unittest.TestCase):
    """升级失败文案必须是可翻译的键，且必须真的能查到译文。

    历史缺陷：`py_msg_*` 这类 flat 键嵌在分片的 section 里，而 flat 查找只扫
    主菜单顶层 → 查不到就把**键名本身**显示给用户（升级失败时看到
    `py_msg_339e87`，比报错更让人摸不着头脑）。
    """

    KEYS = (
        'system.py_msg_upd_step',
        'system.py_msg_upd_rb',
        'system.py_msg_upd_norb',
        'system.py_msg_upd_envw',
        'system.py_msg_upd_enve',
    )

    def test_new_keys_have_translations(self):
        from core.i18n import t
        for key in self.KEYS:
            with self.subTest(key=key):
                for lang in ('zh-CN', 'en'):
                    self.assertNotEqual(t(key, lang=lang), key,
                                        '%s 在 %s 里没有译文' % (key, lang))

    def test_placeholders_render_in_every_language(self):
        from core.i18n import t
        for lang in ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it'):
            with self.subTest(lang=lang):
                self.assertIn('boom', t('system.py_msg_upd_rb', 'boom', lang=lang))
                text = t('system.py_msg_upd_enve', 7, 'pip boom', lang=lang)
                self.assertIn('7', text)
                self.assertIn('pip boom', text)

    def test_flat_backend_keys_resolve(self):
        """flat 后端消息键（历史遗留）也要能查到译文，而不是把键名当作消息。"""
        from core.i18n import t
        for key in ('py_msg_f9fd8e', 'py_msg_339e87', 'py_msg_fac254'):
            with self.subTest(key=key):
                self.assertNotEqual(t(key, lang='en'), key)
        self.assertEqual(t('py_msg_no_such_key', lang='en'), 'py_msg_no_such_key',
                         '查不到的键仍须原样返回（不得乱回退到其它条目）')


class TestDependencyScriptExitCode(unittest.TestCase):
    """依赖脚本必须把 pip 失败传播成非 0 退出码。

    旧脚本无 `set -e`：`pip3 install` 失败后继续跑 awk/if，最后一条命令成功
    → 脚本退出码 0 → 升级侧判定「依赖装好了」，用户随后遇到面板起不来。
    """

    def test_pip_failure_makes_script_fail(self):
        import shutil
        import subprocess
        import tempfile
        from types import SimpleNamespace
        import core.yf as real_yf
        import utils.system.update as update_mod

        bash = shutil.which('bash')
        if not bash:
            self.skipTest('未找到 bash')

        tmp = tempfile.mkdtemp(prefix='yf_env_script_')
        self.addCleanup(shutil.rmtree, tmp, True)
        panel = os.path.join(tmp, 'panel')
        os.makedirs(os.path.join(panel, 'version'))
        os.makedirs(os.path.join(panel, 'bin'))
        # 面板侧 venv 激活脚本：能用即可，无需真实 venv
        with open(os.path.join(panel, 'bin', 'activate'), 'w', encoding='utf-8') as fh:
            fh.write(': noop\n')
        with open(os.path.join(panel, 'requirements.txt'), 'w', encoding='utf-8') as fh:
            fh.write('flask\n')

        # pip 替身：固定失败；curl 替身：直接成功（避免访问网络）
        fakebin = os.path.join(tmp, 'fakebin')
        os.makedirs(fakebin)
        for name, body in (('pip3', '#!/bin/sh\nexit 9\n'),
                           ('curl', '#!/bin/sh\nexit 0\n'),
                           ('awk', '#!/bin/sh\ncat\n')):
            path = os.path.join(fakebin, name)
            with open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(body)
            os.chmod(path, 0o755)

        script = update_mod._build_env_update_script(panel)
        script_path = os.path.join(tmp, 'env.sh')
        with open(script_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(script)
        env = dict(os.environ)
        env['PATH'] = fakebin + os.pathsep + env.get('PATH', '')
        proc = subprocess.run([bash, script_path], env=env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0,
                            'pip 失败必须让依赖脚本非 0 退出（否则升级会假成功）')

    def test_script_is_shell_valid(self):
        import shutil
        import subprocess
        import tempfile
        import utils.system.update as update_mod

        bash = shutil.which('bash')
        if not bash:
            self.skipTest('未找到 bash')
        tmp = tempfile.mkdtemp(prefix='yf_env_syntax_')
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, 'env.sh')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(update_mod._build_env_update_script('/www/server/yufeng_panel'))
        proc = subprocess.run([bash, '-n', path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestUpgradeFrontendFailureContract(unittest.TestCase):
    def test_transport_failure_never_advances_install(self):
        with open(INDEX_JS, 'r', encoding='utf-8') as fh:
            content = fh.read()
        match = re.search(r'function updateStep\(.*?\n\}', content, re.S)
        self.assertIsNotNone(match)
        fail_body = match.group(0).split("}, 'json').fail(", 1)[1]
        self.assertNotIn('callback()', fail_body,
                         'HTTP/JSON 失败不得推进后续升级步骤或显示操作成功')
        self.assertNotIn('100%', fail_body)
        self.assertIn('连接失败', fail_body)
        self.assertIn('升级结果未知', fail_body)
        self.assertIn('.attr("disabled", true)', fail_body,
                      '安装请求可能已执行，禁止断线后直接重复点击安装')

    def test_index_javascript_syntax(self):
        result = subprocess.run(['node', '--check', INDEX_JS],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
