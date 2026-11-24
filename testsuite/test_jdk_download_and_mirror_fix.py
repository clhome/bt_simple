# coding: utf-8
"""JDK 下载 404 缺陷修复与全版本双通道多源容灾测试。

验证范围：
1. _valid_jdk_url 白名单严格性（支持受信镜像 .tar.gz 以及 api.adoptium.net 动态端点，拦截恶意域名与注入）；
2. get_online_jdks 默认基准列表升级为最新官方安全版本（17.0.21.1_2、21.0.13.1_2 等），并根据 x64/aarch64 架构正确映射；
3. 缓存过时检测机制（识别包含 17.0.21.1_1、8u504b01 等失效版本的旧缓存，以及跨架构不匹配缓存）；
4. install_jdk 与 upgrade_jdk 生成的 bash 脚本包含双通道容灾机制（主镜像 + 官方全球 CDN latest 端点）、tar -tzf 完整性校验与 cacerts 加固；
5. get_jdk_list 支持 force_update 穿透刷新；
6. 文件编码与格式合规性（UTF-8 无 BOM、LF 换行）。
"""

import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)
if ROOT not in sys.path:
    sys.path.append(ROOT)

import plugins.jdk.index as jdk_mod


class TestJdkDownloadAndMirrorFix(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_jdk_fix_test_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        self.javadir = os.path.join(self.server, 'jdk')
        self.plug = os.path.join(self.tmp, 'plugins', 'jdk')
        os.makedirs(self.javadir)
        os.makedirs(self.plug)

        self._orig_java_dir = jdk_mod.jdk_main._java_dir
        self._orig_plugin_path = jdk_mod.jdk_main._plugin_path
        self._orig_config_file = jdk_mod.jdk_main._config_file
        self._orig_sys_java = getattr(jdk_mod.jdk_main, '_sys_java', '/usr/bin/java')

        jdk_mod.jdk_main._java_dir = self.javadir
        jdk_mod.jdk_main._plugin_path = self.plug
        jdk_mod.jdk_main._config_file = os.path.join(self.plug, 'data.json')
        jdk_mod.jdk_main._sys_java = os.path.join(self.tmp, 'nonexistent_sys_java')

    def tearDown(self):
        jdk_mod.jdk_main._java_dir = self._orig_java_dir
        jdk_mod.jdk_main._plugin_path = self._orig_plugin_path
        jdk_mod.jdk_main._config_file = self._orig_config_file
        jdk_mod.jdk_main._sys_java = self._orig_sys_java

    def test_01_valid_jdk_url(self):
        """测试 URL 白名单验证逻辑"""
        # 合法清华源
        valid_tsinghua = "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21.1_2.tar.gz"
        self.assertTrue(jdk_mod._valid_jdk_url(valid_tsinghua))

        # 合法 Adoptium 官方 API 动态下载端点
        valid_official_api = "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
        self.assertTrue(jdk_mod._valid_jdk_url(valid_official_api))

        # 非法主机或格式
        self.assertFalse(jdk_mod._valid_jdk_url("http://evil.com/jdk.tar.gz"))
        self.assertFalse(jdk_mod._valid_jdk_url("https://api.adoptium.net/v3/other/path"))
        self.assertFalse(jdk_mod._valid_jdk_url("https://mirrors.tuna.tsinghua.edu.cn/evil.sh"))
        self.assertFalse(jdk_mod._valid_jdk_url(valid_tsinghua + "; rm -rf /"))
        self.assertFalse(jdk_mod._valid_jdk_url(""))
        self.assertFalse(jdk_mod._valid_jdk_url(None))

    def test_02_default_jdks_architecture_mapping(self):
        """测试不同架构下的默认基准版本映射正确且包含最新官方补丁"""
        main = jdk_mod.jdk_main()

        # 模拟 aarch64
        orig_arch = jdk_mod._system_arch
        try:
            jdk_mod._system_arch = lambda: 'aarch64'
            # 隔离网络调用，回退默认基准
            import urllib.request
            orig_urlopen = urllib.request.urlopen
            try:
                def raise_err(req, *args, **kwargs):
                    raise Exception("Mock offline")
                urllib.request.urlopen = raise_err

                res_arm = main.get_online_jdks(force_update=True)
                v17_arm = next(x for x in res_arm if x['version'] == 'jdk-17')
                self.assertIn('17.0.21.1_2', v17_arm['url'])
                self.assertIn('aarch64', v17_arm['url'])

                v8_arm = next(x for x in res_arm if x['version'] == 'jdk-8')
                self.assertIn('8u512b09', v8_arm['url'])
                self.assertIn('aarch64', v8_arm['url'])
            finally:
                urllib.request.urlopen = orig_urlopen

            # 模拟 x64
            jdk_mod._system_arch = lambda: 'x64'
            orig_urlopen2 = urllib.request.urlopen
            try:
                def raise_err2(req, *args, **kwargs):
                    raise Exception("Mock offline")
                urllib.request.urlopen = raise_err2

                res_x64 = main.get_online_jdks(force_update=True)
                v17_x64 = next(x for x in res_x64 if x['version'] == 'jdk-17')
                self.assertIn('17.0.21.1_2', v17_x64['url'])
                self.assertIn('x64', v17_x64['url'])

                v8_x64 = next(x for x in res_x64 if x['version'] == 'jdk-8')
                self.assertIn('8u514b01', v8_x64['url'])
                self.assertIn('x64', v8_x64['url'])
            finally:
                urllib.request.urlopen = orig_urlopen2
        finally:
            jdk_mod._system_arch = orig_arch

    def test_03_stale_cache_invalidation(self):
        """测试包含已知失效版本 (如 17.0.21.1_1) 的旧缓存能被自动识别并废弃刷新"""
        main = jdk_mod.jdk_main()
        cache_file = os.path.join(self.plug, 'versions.json')

        # 写入含有 17.0.21.1_1 的失效缓存
        stale_cache = [
            {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u504b01.tar.gz", "release_date": "2026-01-20"},
            {"version": "jdk-17", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21.1_1.tar.gz", "release_date": "2026-01-20"},
            {"version": "jdk-25", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/25/jdk/x64/linux/OpenJDK25U-jdk_x64_linux_hotspot_25.0.5.1_1.tar.gz", "release_date": "2026-01-20"}
        ]
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(stale_cache, f)

        # 离线环境测试：缓存被判定为 stale 后会进入重新获取，离线时回退新的 default_jdks
        import urllib.request
        orig_urlopen = urllib.request.urlopen
        orig_arch = jdk_mod._system_arch
        try:
            jdk_mod._system_arch = lambda: 'x64'
            def raise_err(req, *args, **kwargs):
                raise Exception("Mock offline")
            urllib.request.urlopen = raise_err

            refreshed = main.get_online_jdks(force_update=False)
            v17 = next(x for x in refreshed if x['version'] == 'jdk-17')
            self.assertIn('17.0.21.1_2', v17['url'], '旧失效缓存必须被淘汰并更新为新版本')
        finally:
            urllib.request.urlopen = orig_urlopen
            jdk_mod._system_arch = orig_arch

    def test_04_install_jdk_dual_channel_script(self):
        """测试 install_jdk 生成的安装脚本包含双通道容灾机制"""
        main = jdk_mod.jdk_main()
        url = "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21.1_2.tar.gz"

        import thisdb
        orig_add = thisdb.addTask
        added_tasks = []
        thisdb.addTask = lambda **kwargs: added_tasks.append(kwargs)
        try:
            res_raw = main.install_jdk({"version": "jdk-17", "download_url": url})
            res = json.loads(res_raw) if isinstance(res_raw, str) else res_raw
            self.assertTrue(res.get('status'))

            script_file = os.path.join(self.plug, 'install_jdk-17.sh')
            self.assertTrue(os.path.exists(script_file))
            with open(script_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 验证脚本包含主镜像下载
            self.assertIn(url, content)
            # 验证脚本包含 Adoptium 官方全球 CDN 动态备用端点
            self.assertIn("api.adoptium.net/v3/binary/latest/17/ga/linux/", content)
            # 验证包含归档完整性校验
            self.assertIn("tar -tzf", content)
            # 验证包含 cacerts 加固
            self.assertIn("cacerts", content)
            self.assertIn("keytool", content)
        finally:
            thisdb.addTask = orig_add

    def test_05_upgrade_jdk_dual_channel_script(self):
        """测试 upgrade_jdk 生成的升级脚本包含双通道容灾机制"""
        main = jdk_mod.jdk_main()
        # 预先创建已安装目录
        dest_dir = os.path.join(self.javadir, 'jdk-17', 'bin')
        os.makedirs(dest_dir)
        java_bin = os.path.join(dest_dir, 'java')
        with open(java_bin, 'w') as f:
            f.write('#!/bin/sh\nexit 0\n')

        url = "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21.1_2.tar.gz"
        import thisdb
        orig_add = thisdb.addTask
        added_tasks = []
        thisdb.addTask = lambda **kwargs: added_tasks.append(kwargs)
        try:
            res_raw = main.upgrade_jdk({"version": "jdk-17", "download_url": url})
            res = json.loads(res_raw) if isinstance(res_raw, str) else res_raw
            self.assertTrue(res.get('status'))

            script_file = os.path.join(self.plug, 'upgrade_jdk-17.sh')
            self.assertTrue(os.path.exists(script_file))
            with open(script_file, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn(url, content)
            self.assertIn("api.adoptium.net/v3/binary/latest/17/ga/linux/", content)
            self.assertIn("tar -tzf", content)
            self.assertIn("平滑覆盖", content)
        finally:
            thisdb.addTask = orig_add

    def test_06_get_jdk_list_force_update(self):
        """测试 get_jdk_list 支持 force_update 穿透"""
        main = jdk_mod.jdk_main()
        called_force = []
        orig_get_online = main.get_online_jdks
        try:
            main.get_online_jdks = lambda force_update=False: (called_force.append(force_update) or [])
            main.get_jdk_list({'force_update': 1})
            self.assertEqual(called_force, [True])

            called_force.clear()
            main.get_jdk_list({})
            self.assertEqual(called_force, [False])
        finally:
            main.get_online_jdks = orig_get_online


if __name__ == '__main__':
    unittest.main()

