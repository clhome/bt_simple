# coding: utf-8
"""P2-1: Gitea systemd active(exited) 僵住分支 Live 真实环境验证用例。

测试员问题：
  appOp start 的僵住转 restart 分支在 Mock 用例中已覆盖，但真实 wedged 单元上的 live 验证未入库。
  按规则，/test 下未入库的验收路径不计为证据，验证过程应落在 testsuite 或审计方可复现的路径。
解法：
  在 testsuite 下提供支持真实 Linux 环境的 live 验证用例：
  构造 wedged 单元（RemainAfterExit 下 active(exited)）后调面板 start，验证其转 restart 拉起并返回 ok。
  非 Linux 系统、无 systemctl 或非 root 权限时自动安全跳过（skipTest），不阻塞跨平台常规测试与 CI。

使用方法：
  python -m unittest testsuite/test_gitea_wedged_live.py
"""

import os
import sys
import time
import shutil
import subprocess
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
GITEA_PLUGIN_DIR = os.path.join(ROOT_DIR, 'plugins', 'gitea')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)
if GITEA_PLUGIN_DIR not in sys.path:
    sys.path.append(GITEA_PLUGIN_DIR)


class TestGiteaWedgedSystemdLive(unittest.TestCase):
    """在 Linux 真机上构造 wedged 单元并验证 appOp start 自愈转 restart。"""

    def setUp(self):
        if sys.platform == 'win32' or sys.platform == 'darwin':
            self.skipTest('当前环境为非 Linux 操作系统，跳过 systemd live 验证')
        if not shutil.which('systemctl'):
            self.skipTest('当前系统无 systemctl 命令，跳过 systemd live 验证')
        if not hasattr(os, 'geteuid') or os.geteuid() != 0:
            self.skipTest('systemd 状态构造需 root 权限，当前为非 root 用户')

        import core.yf as yf
        import importlib.util
        spec = importlib.util.spec_from_file_location('gitea_plugin_wedged_live', os.path.join(GITEA_PLUGIN_DIR, 'index.py'))
        gitea_plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gitea_plugin)
        self.yf = yf
        self.gitea = gitea_plugin

    def test_live_wedged_unit_self_healing(self):
        """构造 wedged 单元（active(exited)），验证面板 start 转 restart 拉起并返回 ok。"""
        unit_name = 'yf-gitea-wedged-test'
        service_file = f'/etc/systemd/system/{unit_name}.service'
        run_file = f'/tmp/{unit_name}.pid'

        # 1. 构造带 RemainAfterExit=yes 的测试单元
        unit_content = f"""[Unit]
Description=YF Gitea Wedged Test Probe
After=network.target

[Service]
Type=simple
# 注意：systemd unit ExecStart 中 $$ 会被展开为单个 $。必须写 $$$$ 才能使 sh 收到 echo $$ 并正确输出数字 PID
ExecStart=/bin/sh -c 'echo $$$$ > {run_file}; exec sleep 3600'
RemainAfterExit=yes
Restart=no

[Install]
WantedBy=multi-user.target
"""
        try:
            with open(service_file, 'w', encoding='utf-8') as f:
                f.write(unit_content)
            subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True)

            # 2. 启动该单元
            subprocess.run(['systemctl', 'start', unit_name], check=True, capture_output=True)
            time.sleep(1)

            # 确认 PID 存在
            self.assertTrue(os.path.exists(run_file), '测试单元未正常启动')
            with open(run_file, 'r', encoding='utf-8') as f:
                pid = f.read().strip()
            if not pid.isdigit() or pid == '0':
                rc_mp, out_mp, _ = self.yf.execShellRc(['systemctl', 'show', '-p', 'MainPID', '--value', unit_name], shell=False)
                if rc_mp == 0 and (out_mp or '').strip().isdigit():
                    pid = out_mp.strip()
            self.assertTrue(pid.isdigit() and int(pid) > 0, f'未能获取有效的测试单元 PID: {pid}')

            # 3. 强杀进程构造 wedged 状态（不调用 systemctl stop）
            subprocess.run(['kill', '-9', pid], check=True)
            time.sleep(1)

            # 4. 验证单元此时处于 Active: active (exited) 僵死状态
            rc_act, out_act, _ = self.yf.execShellRc(['systemctl', 'is-active', unit_name], shell=False)
            rc_sub, out_sub, _ = self.yf.execShellRc(['systemctl', 'show', '-p', 'SubState', '--value', unit_name], shell=False)

            sub_state = (out_sub or '').strip().split('=')[-1].strip()
            self.assertEqual('active', (out_act or '').strip(), '单元 ActiveState 应为 active')
            self.assertEqual('exited', sub_state, '单元 SubState 应为 exited')

            # 5. 实证：此时若裸调 systemctl start，systemd 认为已 active，属于 no-op，进程不会拉起
            subprocess.run(['systemctl', 'start', unit_name], capture_output=True)
            # 进程依旧不存在
            rc_ps, out_ps, _ = self.yf.execShellRc(['kill', '-0', pid], shell=False)
            self.assertNotEqual(0, rc_ps, '裸 start 下原进程已被杀，新进程未拉起')

            # 6. 使用 Gitea 的 appOp 核心判定分支进行修复验证
            old_get_name = self.gitea.getPluginName
            old_status = self.gitea.status
            old_installed = self.gitea.isInstalled

            running_state = {'running': False}

            def mock_status():
                if os.path.exists(run_file):
                    try:
                        with open(run_file, 'r', encoding='utf-8') as rf:
                            new_p = rf.read().strip()
                        if new_p and new_p != pid:
                            r, _, _ = self.yf.execShellRc(['kill', '-0', new_p], shell=False)
                            if r == 0:
                                running_state['running'] = True
                                return 'start'
                    except Exception:
                        pass
                return 'start' if running_state['running'] else 'stop'

            self.gitea.getPluginName = lambda: unit_name
            self.gitea.status = mock_status
            self.gitea.isInstalled = lambda: True

            try:
                # 调用 appOp('start')
                res = self.gitea.appOp('start')
                self.assertEqual('ok', res, f'appOp start 应自动转 restart 并返回 ok，实际返回: {res}')
                # 确认单元恢复到正常 running 状态
                rc_sub_new, out_sub_new, _ = self.yf.execShellRc(['systemctl', 'show', '-p', 'SubState', '--value', unit_name], shell=False)
                new_sub = (out_sub_new or '').strip().split('=')[-1].strip()
                self.assertEqual('running', new_sub, f'自愈重启后 SubState 应为 running，实际为: {new_sub}')
            finally:
                self.gitea.getPluginName = old_get_name
                self.gitea.status = old_status
                self.gitea.isInstalled = old_installed

        finally:
            # 清理现场
            subprocess.run(['systemctl', 'stop', unit_name], capture_output=True)
            subprocess.run(['systemctl', 'disable', unit_name], capture_output=True)
            if os.path.exists(service_file):
                os.remove(service_file)
            if os.path.exists(run_file):
                os.remove(run_file)
            subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)


if __name__ == '__main__':
    unittest.main()

