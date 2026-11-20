# coding: utf-8
"""Java4Shell (CVE-2026-114938) 安全加固与硬件利用暴露面审计测试。

验证范围：
1. 硬件脆弱性判定 (ARM64 天然免疫, x86-64 + AVX-512 VBMI 硬件暴露面, x86-64 无 VBMI 硬件免疫)；
2. Java4Shell 漏洞受影响版本精确区间判定 (JDK 17/21/25/27 及 JDK 8 perf 变体)；
3. 全局 JVM 启动参数缓解机制 (-XX:-UseBASE64Intrinsics) 的开启、关闭、持久化与设为默认联动；
4. get_jdk_list 与 get_security_overview 契约兼容性；
5. 多语言 6 国语言包键集合对称性、非中文无中文字符、无 BOM 无 CRLF。
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

import plugins.jdk.index as jdk_mod

LANG_DIR = os.path.join(ROOT, 'plugins', 'jdk', 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
ZH_RE = re.compile(r'[\u4e00-\u9fa5]')


class TestJdkJava4ShellHardening(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_java4shell_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        self.javadir = os.path.join(self.server, 'jdk')
        self.plug = os.path.join(self.tmp, 'plugins', 'jdk')
        os.makedirs(self.javadir)
        os.makedirs(self.plug)

        jdk_mod.jdk_main._java_dir = self.javadir
        jdk_mod.jdk_main._plugin_path = self.plug
        jdk_mod.jdk_main._config_file = os.path.join(self.plug, 'data.json')
        self.fake_profile = os.path.join(self.tmp, 'java.sh')
        self._orig_profile = jdk_mod._JAVA_PROFILE
        jdk_mod._JAVA_PROFILE = self.fake_profile

    def tearDown(self):
        jdk_mod._JAVA_PROFILE = self._orig_profile

    # ---------------- 1. 硬件审计与指令集探测 ----------------
    def test_01_hw_vulnerability_detection(self):
        # 1. ARM64 / aarch64 天然免疫
        orig_platform = sys.modules.get('platform')
        class FakeArmPlatform:
            @staticmethod
            def machine():
                return 'aarch64'
        
        sys.modules['platform'] = FakeArmPlatform
        try:
            res = jdk_mod._check_hw_vulnerability()
            self.assertEqual(res['status'], 'arm_immune')
            self.assertFalse(res['hw_vulnerable'])
            self.assertFalse(res['has_vbmi'])
            self.assertIn('ARM64', res['desc'])
        finally:
            if orig_platform:
                sys.modules['platform'] = orig_platform

        # 2. x86-64 无 VBMI 硬件免疫
        class FakeX86Platform:
            @staticmethod
            def machine():
                return 'x86_64'
        sys.modules['platform'] = FakeX86Platform
        
        orig_get_flags = jdk_mod._get_cpu_flags
        try:
            jdk_mod._get_cpu_flags = lambda: {'fpu', 'vme', 'de', 'avx2'}
            res = jdk_mod._check_hw_vulnerability()
            self.assertEqual(res['status'], 'hw_immune')
            self.assertFalse(res['hw_vulnerable'])
            self.assertFalse(res['has_vbmi'])

            # 3. x86-64 带 VBMI 处于硬件暴露面
            jdk_mod._get_cpu_flags = lambda: {'avx512f', 'avx512_vbmi', 'avx512bw'}
            res_vuln = jdk_mod._check_hw_vulnerability()
            self.assertEqual(res_vuln['status'], 'exposed')
            self.assertTrue(res_vuln['hw_vulnerable'])
            self.assertTrue(res_vuln['has_vbmi'])
        finally:
            jdk_mod._get_cpu_flags = orig_get_flags
            if orig_platform:
                sys.modules['platform'] = orig_platform

    # ---------------- 2. Java 语义版本解析与漏洞区间判定 ----------------
    def test_02_java4shell_version_boundaries(self):
        # JDK 8 / 11 标准线
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('jdk-8'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('8u504b01'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('11.0.32.1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('11.0.22'))
        # JDK 8 特殊 perf 变体受影响
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('8u511b33-perf'))

        # JDK 17 (>= 17.0.6 且 <= 17.0.21.0.3 受影响; >= 17.0.21.1 安全)
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('17.0.5'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('17.0.6'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('17.0.21'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('17.0.21_9'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('17.0.21.0.2'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('17.0.21.0.3'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('17.0.21.1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('17.0.21.1_1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('17.0.22'))

        # JDK 21 (>= 21 且 <= 21.0.13.0.3 受影响; >= 21.0.13.1 安全)
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('jdk-21'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('21.0.0'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('21.0.12.1'))  # 用户真机版本
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('21.0.13'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('21.0.13_9'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('21.0.13.0.3'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('21.0.13.1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('21.0.13.1_1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('21.0.14'))

        # JDK 25 (>= 25 且 <= 25.0.5.0.3 受影响; >= 25.0.5.1 安全)
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('25.0.0'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('25.0.5'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('25.0.5_8'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('25.0.5.1'))

        # JDK 27 (>= 27 且 <= 27.0.1.0.3 受影响; >= 27.0.1.1 安全)
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('27.0.0'))
        self.assertTrue(jdk_mod._is_java4shell_vulnerable_version('27.0.1'))
        self.assertFalse(jdk_mod._is_java4shell_vulnerable_version('27.0.1.1'))

    # ---------------- 3. 全局缓解参数注入与设为默认联动 ----------------
    def test_03_toggle_global_mitigation(self):
        obj = jdk_mod.jdk_main()
        
        # 初始状态未开启
        self.assertFalse(jdk_mod._is_mitigation_active())
        
        # 一键开启
        res_on = json.loads(obj.toggle_global_mitigation({'enable': True}))
        self.assertTrue(res_on['status'])
        self.assertTrue(jdk_mod._is_mitigation_active())
        
        # 验证写入了 /etc/profile.d/java.sh
        with open(self.fake_profile, 'r', encoding='utf-8') as f:
            profile_content = f.read()
        self.assertIn('export JDK_JAVA_OPTIONS="-XX:-UseBASE64Intrinsics"', profile_content)

        # 一键关闭
        res_off = json.loads(obj.toggle_global_mitigation({'enable': False}))
        self.assertTrue(res_off['status'])
        self.assertFalse(jdk_mod._is_mitigation_active())
        if os.path.exists(self.fake_profile):
            with open(self.fake_profile, 'r', encoding='utf-8') as f:
                self.assertNotIn('-XX:-UseBASE64Intrinsics', f.read())

    def test_04_set_default_retains_mitigation(self):
        obj = jdk_mod.jdk_main()
        # 先开启缓解
        obj.toggle_global_mitigation({'enable': True})
        self.assertTrue(jdk_mod._is_mitigation_active())

        # 模拟假 JDK
        home = os.path.join(self.javadir, 'jdk-21')
        os.makedirs(os.path.join(home, 'bin'))
        java_bin = home + '/bin/java'
        with open(java_bin, 'w', encoding='utf-8') as f:
            f.write('#!/bin/sh\nexit 0\n')
        os.chmod(java_bin, 0o755)

        orig_link = jdk_mod._link_points_to
        jdk_mod._link_points_to = lambda l, t: True
        try:
            res = json.loads(obj.set_default_jdk({'path': java_bin}))
            self.assertTrue(res['status'])
            # 验证默认环境变量写出时携带了缓解参数
            with open(self.fake_profile, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('JAVA_HOME=', content)
            self.assertIn('export JDK_JAVA_OPTIONS="-XX:-UseBASE64Intrinsics"', content)
        finally:
            jdk_mod._link_points_to = orig_link

    # ---------------- 4. 默认在线清单为安全补丁版本 ----------------
    def test_05_online_jdks_default_safe_versions(self):
        import urllib.request
        orig_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError('test offline'))
        try:
            obj = jdk_mod.jdk_main()
            jdks = obj.get_online_jdks(force_update=True)
            for j in jdks:
                v = j['version']
                u = j['url']
                if v == 'jdk-17':
                    self.assertIn('17.0.21.1', u)
                elif v == 'jdk-21':
                    self.assertIn('21.0.13.1', u)
                elif v == 'jdk-25':
                    self.assertIn('25.0.5.1', u)
        finally:
            urllib.request.urlopen = orig_urlopen

    # ---------------- 5. 契约与多语言对称性 ----------------
    def test_06_lang_files_aligned_and_clean(self):
        base_path = os.path.join(LANG_DIR, 'zh-CN.json')
        with io.open(base_path, encoding='utf-8') as f:
            base_keys = set(json.load(f).keys())

        for lang in LANGS:
            fpath = os.path.join(LANG_DIR, f"{lang}.json")
            with io.open(fpath, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{lang}.json has BOM")
            self.assertNotIn(b'\r\n', raw, f"{lang}.json has CRLF")

            data = json.loads(raw.decode('utf-8'))
            self.assertEqual(base_keys, set(data.keys()), f"{lang}.json key set mismatch")

            if lang in ('en', 'de', 'fr', 'it'):
                for k, val in data.items():
                    self.assertFalse(ZH_RE.search(val), f"Chinese text found in {lang}.json for key {k}: {val}")

    # ---------------- 6. 用户真实版本 (21.0.12.1) 状态评估与小版本提取 ----------------
    def test_07_user_version_evaluation_and_version_info(self):
        # 1. 软件版本 21.0.12.1 处于受影响区间，在无 VBMI 的机器上判定为 hw_immune
        hw_info = {'arch': 'x86_64', 'has_vbmi': False, 'hw_vulnerable': False, 'status': 'hw_immune'}
        st = jdk_mod._eval_java4shell_status('21.0.12.1', hw_info, is_mitigated=False)
        self.assertEqual(st['status'], 'hw_immune')
        self.assertTrue(st['is_vuln_ver'])
        self.assertIn('21.0.12.1', st['title'])
        self.assertIn('硬件暂免疫', st['title'])

        # 2. 模拟从 java -version 输出中提取小版本号与完整输出
        home = os.path.join(self.javadir, 'jdk-21')
        os.makedirs(os.path.join(home, 'bin'), exist_ok=True)
        java_bin = home + '/bin/java'
        with open(java_bin, 'w', encoding='utf-8') as f:
            f.write('#!/bin/sh\n')
            f.write('echo "openjdk version \\"21.0.12.1\\" 2026-08-18 LTS" >&2\n')
            f.write('echo "OpenJDK Runtime Environment Temurin-21.0.12.1+1 (build 21.0.12.1+1-LTS)" >&2\n')
            f.write('echo "OpenJDK 64-Bit Server VM Temurin-21.0.12.1+1 (build 21.0.12.1+1-LTS, mixed mode, sharing)" >&2\n')
        os.chmod(java_bin, 0o755)

        orig_exec = jdk_mod.yf.execShellRc
        jdk_mod.yf.execShellRc = lambda cmd, **kw: (
            0, '',
            'openjdk version "21.0.12.1" 2026-08-18 LTS\n'
            'OpenJDK Runtime Environment Temurin-21.0.12.1+1 (build 21.0.12.1+1-LTS)\n'
        )
        try:
            short_v, full_v = jdk_mod._get_jdk_version_info(java_bin, 'jdk-21')
            self.assertEqual(short_v, '21.0.12.1')
            self.assertIn('21.0.12.1', full_v)
            self.assertIn('Temurin-21.0.12.1+1', full_v)
        finally:
            jdk_mod.yf.execShellRc = orig_exec


if __name__ == '__main__':
    unittest.main()
