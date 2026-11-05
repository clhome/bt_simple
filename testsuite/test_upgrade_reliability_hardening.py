# -*- coding: utf-8 -*-
"""面板升级可靠性与自愈优化测试套件 (任务 35)"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
import sys
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import core.yf as yf
import utils.system.update as update_mod


class TestUpgradeReliabilityHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_test_upd_rel_')
        self.panel_dir = os.path.join(self.tmp, 'panel')
        self.temp_dir = os.path.join(self.panel_dir, 'temp')
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.panel_dir, 'web'), exist_ok=True)
        with open(os.path.join(self.panel_dir, 'web', 'version.py'), 'w', encoding='utf-8') as fh:
            fh.write("APP_VERSION = '2.0.3'\n")
        with open(os.path.join(self.panel_dir, '.version'), 'w', encoding='utf-8') as fh:
            fh.write("2.0.3\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_pip_install_contains_no_cache_dir(self):
        """pip3 install 必须包含 --no-cache-dir，防止在低配内存服务器上堆积 wheel 缓存导致 OOM。"""
        script = update_mod._build_env_update_script(self.panel_dir)
        self.assertIn('pip3 install --no-cache-dir -r requirements.txt', script)
        self.assertIn('pip3 install --no-cache-dir -r version/r', script)

    def test_02_source_directory_preserved_on_failure(self):
        """依赖安装等后续阶段失败时，升级源码目录绝不能被提前删除（必须保留供重试自愈）。"""
        ver = '2.0.5'
        src_dir = os.path.join(self.temp_dir, f'bt_simple-{ver}')
        os.makedirs(os.path.join(src_dir, 'web'), exist_ok=True)
        with open(os.path.join(src_dir, 'web', 'version.py'), 'w', encoding='utf-8') as fh:
            fh.write(f"APP_VERSION = '{ver}'\n")
        for fn in ('panel_task.py', 'panel_tools.py', 'requirements.txt'):
            with open(os.path.join(src_dir, fn), 'w', encoding='utf-8') as fh:
                fh.write('')

        # 模拟备份成功，但依赖环境安装返回非 0
        with mock.patch.object(update_mod, 'getServerInfo', return_value={'tag_name': f'v{ver}', 'name': 'x', 'body': ''}), \
             mock.patch.object(update_mod, 'backup_panel', return_value=(True, 'backup ok')), \
             mock.patch.object(update_mod.yf, 'getPanelDir', return_value=self.panel_dir), \
             mock.patch.object(update_mod.yf, 'execShellRc', return_value=(1, '', 'pip error')):
            res = update_mod.updateServer('update', f'v{ver}', step='install')

        self.assertFalse(res['status'])
        # 源码目录必须依然存在，未被提前删除！
        self.assertTrue(os.path.exists(src_dir), '依赖更新失败时，源码目录必须保留以供用户重试')

    def test_03_cleanup_runs_after_all_steps_succeed(self):
        """当全部安装与校验步骤成功时，临时源码目录和 yf.zip 必须被正确清理。"""
        ver = '2.0.5'
        src_dir = os.path.join(self.temp_dir, f'bt_simple-{ver}')
        zip_file = os.path.join(self.temp_dir, 'yf.zip')
        os.makedirs(os.path.join(src_dir, 'web'), exist_ok=True)
        with open(os.path.join(src_dir, 'web', 'version.py'), 'w', encoding='utf-8') as fh:
            fh.write(f"APP_VERSION = '{ver}'\n")
        for fn in ('panel_task.py', 'panel_tools.py', 'requirements.txt'):
            with open(os.path.join(src_dir, fn), 'w', encoding='utf-8') as fh:
                fh.write('')
        with open(zip_file, 'w', encoding='utf-8') as fh:
            fh.write('dummy zip')

        with mock.patch.object(update_mod, 'getServerInfo', return_value={'tag_name': f'v{ver}', 'name': 'x', 'body': ''}), \
             mock.patch.object(update_mod, 'backup_panel', return_value=(True, 'backup ok')), \
             mock.patch.object(update_mod.yf, 'getPanelDir', return_value=self.panel_dir), \
             mock.patch.object(update_mod.yf, 'execShellRc', return_value=(0, 'ok', '')), \
             mock.patch.object(update_mod.yf, 'restartPanel', return_value=True):
            res = update_mod.updateServer('update', f'v{ver}', step='install')

        self.assertTrue(res['status'])
        # 安装成功后，临时目录和压缩包被清理
        self.assertFalse(os.path.exists(src_dir))
        self.assertFalse(os.path.exists(zip_file))

    def test_04_restart_panel_is_async_nonblocking(self):
        """yf.restartPanel() 采用守护线程异步延迟执行，绝不阻塞当前同步流程。"""
        with mock.patch('time.sleep', return_value=None), \
             mock.patch('threading.Thread') as mock_thread:
            res = yf.restartPanel()
            self.assertTrue(res)
            self.assertTrue(mock_thread.called)
            # 必须设置 daemon=True
            _, kwargs = mock_thread.call_args
            self.assertTrue(kwargs.get('daemon', False))

    def test_05_wget_has_retry_and_continue_flags(self):
        """github.py 中的 wget 命令必须包含重试 (--tries) 与断点续传 (-c)。"""
        from core.yf import github as gh_mod
        import inspect
        src = inspect.getsource(gh_mod.githubDownload)
        self.assertIn('--tries=2', src)
        self.assertIn('-c', src)

    def test_06_download_dual_channel_fallback(self):
        """Tag 动态归档下载失败时，自动回退下载 Release 静态附件 yf.zip。"""
        ver = '2.0.5'
        urls_called = []

        def fake_download(url, save_path, **kwargs):
            urls_called.append(url)
            # 第一次调用（tag 归档）失败，第二次调用（release 静态附件）成功
            if 'archive/refs/tags' in url:
                return False
            # 落地一个虚拟文件
            with open(save_path, 'wb') as fh:
                fh.write(b'x' * 2000000)
            return True

        with mock.patch.object(update_mod, 'getServerInfo', return_value={'tag_name': f'v{ver}', 'name': 'x', 'body': 'sha256: dummy'}), \
             mock.patch.object(update_mod.yf, 'getPanelDir', return_value=self.panel_dir), \
             mock.patch.object(update_mod.yf, 'githubDownload', side_effect=fake_download), \
             mock.patch.object(update_mod, 'verify_zip_integrity', return_value=(False, 'stop_here')):
            # 这里只要进入 verify_zip_integrity 就证明下载尝试完毕并拿到了落地文件
            res = update_mod.updateServer('update', f'v{ver}', step='download')

        self.assertEqual(len(urls_called), 2)
        self.assertIn(f'archive/refs/tags/v{ver}.zip', urls_called[0])
        self.assertIn(f'releases/download/v{ver}/yf.zip', urls_called[1])


if __name__ == '__main__':
    unittest.main()

