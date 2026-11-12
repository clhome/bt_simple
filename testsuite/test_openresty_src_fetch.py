# coding:utf-8
import sys
import os
import unittest
import subprocess

import shutil

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
common_dir = os.path.join(project_dir, 'plugins', 'openresty', 'versions', 'common')
src_fetch_script = os.path.join(common_dir, 'openresty_src_fetch.sh')


def find_posix_bash():
    candidates = [r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe']
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True, text=True, timeout=5)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


BASH = find_posix_bash()


class TestOpenRestySrcFetch(unittest.TestCase):

    def setUp(self):
        self.versions = ['1.17.8', '1.19.3', '1.21.4', '1.25.3', '1.27.1', '1.29.2', '1.31.1', 'rtmp']

    def test_src_fetch_script_exists(self):
        self.assertTrue(os.path.exists(src_fetch_script), "openresty_src_fetch.sh 必须存在")

    def test_all_versions_use_unified_src_fetch(self):
        for v in self.versions:
            install_path = os.path.join(project_dir, 'plugins', 'openresty', 'versions', v, 'install.sh')
            self.assertTrue(os.path.exists(install_path), f"版本安装脚本应存在: {install_path}")
            with open(install_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn("openresty_src_fetch.sh", content, f"版本 {v} 必须引入 openresty_src_fetch.sh")
            self.assertIn("yf_openresty_src_fetch", content, f"版本 {v} 必须调用 yf_openresty_src_fetch")
            self.assertNotIn("mirrors.ustc.edu.cn", content, f"版本 {v} 严禁包含失效的 ustc 404 镜像")
            self.assertNotIn("-T 3\n", content, f"版本 {v} 严禁使用极易超时的 -T 3 短超时")

    def test_lib_sh_no_ustc_dead_link(self):
        lib_path = os.path.join(project_dir, 'scripts', 'lib.sh')
        with open(lib_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn("mirrors.ustc.edu.cn/openresty", content, "lib.sh 中必须移除 ustc openresty 404 死链接")

    def test_bash_syntax_of_src_fetch(self):
        if not BASH:
            self.skipTest("本机没有可用的 POSIX bash")
        with open(src_fetch_script, 'r', encoding='utf-8') as f:
            script_code = f.read()
        res = subprocess.run([BASH, '-n'], input=script_code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"openresty_src_fetch.sh bash 语法错误: {res.stderr}")

    @unittest.skipIf(BASH is None, '本机没有可用的 POSIX bash')
    def test_idempotent_when_configure_present(self):
        import tempfile
        work = tempfile.mkdtemp()
        try:
            target_dir = os.path.join(work, 'openresty-1.27.1.2')
            os.makedirs(target_dir, exist_ok=True)
            with open(os.path.join(target_dir, 'configure'), 'w') as f:
                f.write('#!/bin/sh\necho ok\n')

            posix_src = src_fetch_script.replace('\\', '/')
            posix_work = work.replace('\\', '/')
            test_script = f'''
source "{posix_src}"
yf_openresty_src_fetch "{posix_work}" "1.27.1.2"
echo "exit_code=$?"
'''
            res = subprocess.run([BASH, '-c', test_script], capture_output=True, text=True)
            self.assertIn("exit_code=0", res.stdout, "已存在 configure 时必须直接幂等成功返回")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 POSIX bash')
    def test_stale_partial_dir_cleaned(self):
        import tempfile
        work = tempfile.mkdtemp()
        try:
            # 模拟被 git clone 误建出的假目录（有目录无 configure）
            target_dir = os.path.join(work, 'openresty-1.27.1.2')
            os.makedirs(os.path.join(target_dir, 'ngx_brotli'), exist_ok=True)

            posix_src = src_fetch_script.replace('\\', '/')
            posix_work = work.replace('\\', '/')
            test_script = f'''
source "{posix_src}"
# 覆盖 wget 与 curl 模拟下载失败
curl() {{ return 1; }}
wget() {{ return 1; }}
yf_openresty_src_fetch "{posix_work}" "1.27.1.2"
'''
            res = subprocess.run([BASH, '-c', test_script], capture_output=True, text=True)
            self.assertFalse(os.path.exists(target_dir), "缺失 configure 的假目录必须在初始自愈阶段被强制清理")
            self.assertIn("检测到残缺源码目录", res.stdout)
        finally:
            shutil.rmtree(work, ignore_errors=True)



if __name__ == '__main__':
    unittest.main()
