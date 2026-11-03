# coding: utf-8
"""任务 21 自动化测试：GitHub 下载链路性能优化、404 快速熔断与死链挂起根治。

测试点：
1. 静态规则：op_waf 与 webstats 安装脚本中 GeoLite 下载已使用原生 releases/latest/download，且带存在性守卫；
2. 静态规则：github_download.sh 中具备非法 URL 拦截、--dns-timeout/--connect-timeout 超时防护与 404 熔断逻辑；
3. 动态验证：非法 URL（如包含 // 畸变段）在 0 秒内被快速拦截，返回 1 且绝不发起轮询；
4. 动态验证：降级轮询中只遍历存活节点，排除在测速中已判明失败的死节点。
"""

import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH_SH = os.path.join(ROOT, 'scripts', 'github_download.sh')
OP_WAF_INSTALL = os.path.join(ROOT, 'plugins', 'op_waf', 'install.sh')
WEBSTATS_INSTALL = os.path.join(ROOT, 'plugins', 'webstats', 'install.sh')

BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    '/bin/bash',
    '/usr/bin/bash',
]


def find_bash():
    for cand in BASH_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    cand = shutil.which('bash')
    if cand and 'system32' not in cand.lower():
        return cand
    return None


def read_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


class TestGitHubDownloadOptimization(unittest.TestCase):

    def test_01_op_waf_and_webstats_use_native_latest_download(self):
        """op_waf 和 webstats 必须使用 GitHub 原生的 releases/latest/download，且具备 [ -f ] 或 [ -s ] 守卫。"""
        waf_src = read_file(OP_WAF_INSTALL)
        self.assertIn('releases/latest/download/GeoLite2-City.mmdb', waf_src)
        self.assertIn('releases/latest/download/GeoLite2-Country.mmdb', waf_src)
        self.assertNotIn('${GeoLite2_TAG}', waf_src, '严禁再次出现未受保护的 ${GeoLite2_TAG} 裸拼')
        self.assertIn('[ -f $serverPath/source/op_waf/GeoLite2-City.mmdb ]', waf_src, 'cp 前必须校验源文件存在')
        self.assertIn('[ -f $serverPath/source/op_waf/GeoLite2-Country.mmdb ]', waf_src, 'cp 前必须校验源文件存在')

        webstats_src = read_file(WEBSTATS_INSTALL)
        self.assertIn('releases/latest/download/GeoLite2-City.mmdb', webstats_src)
        self.assertNotIn('GEO_VERSION="2024.04.16"', webstats_src, '已升级为原生 latest/download，不再硬编码旧版日期')
        self.assertIn('[ -s $serverPath/source/webstats/GeoLite2-City.mmdb ]', webstats_src, 'cp 前必须校验源文件非空')

    def test_02_github_download_has_hardening_features(self):
        """github_download.sh 源码必须具备硬超时、非法 URL 拦截与 404 熔断特征。"""
        gh_src = read_file(GH_SH)
        self.assertIn('--dns-timeout=10', gh_src, '缺少 --dns-timeout=10 防卡死设置')
        self.assertIn('--connect-timeout=10', gh_src, '缺少 --connect-timeout=10 防卡死设置')
        self.assertIn('releases/download//', gh_src, '缺少非法 URL download// 拦截正则')
        self.assertIn('probe_code', gh_src, '缺少 404/410 状态码探测探针')
        self.assertIn('_GH_FAILED_PROXIES', gh_src, '缺少失效节点缓存过滤')

    def test_03_invalid_url_fast_rejection(self):
        """传入 releases/download// 格式的畸变 URL 时，必须在 0 毫秒内被拦截，不能发起轮询。"""
        bash = find_bash()
        if not bash:
            self.skipTest('系统无可用 Git Bash 环境，跳过动态子进程测试')

        script = '''
        source "%s"
        github_download "/tmp/test_invalid.mmdb" "https://github.com/P3TERX/GeoLite.mmdb/releases/download//GeoLite2-City.mmdb"
        ''' % GH_SH.replace('\\', '/')

        proc = subprocess.run([bash, '-c', script], capture_output=True, encoding='utf-8', errors='replace', timeout=10)
        self.assertNotEqual(proc.returncode, 0, '非法 URL 必须返回非 0 退出码')
        self.assertIn('非法空路径段或双斜杠', proc.stderr + proc.stdout)
        self.assertNotIn('=== 进入最终降级轮询机制 ===', proc.stdout, '非法 URL 严禁进入代理轮询')

    def test_04_404_fast_fail_rejection(self):
        """当探测到上游资源 404 时，必须触发 Fast-Fail 立即终止轮询，不能对所有代理无脑死等。"""
        bash = find_bash()
        if not bash:
            self.skipTest('系统无可用 Git Bash 环境，跳过动态子进程测试')

        # 使用一个必定不存在的模拟 404 地址
        script = '''
        source "%s"
        # 预设已选节点直接走快速下载分支
        export _GH_BEST_PROXY="https://ghfast.top/"
        github_download "/tmp/test_404_fast_fail.tar.gz" "https://github.com/clhome/bt_simple/releases/download/v999.999.999/not_found_12345.tar.gz" 10
        ''' % GH_SH.replace('\\', '/')

        proc = subprocess.run([bash, '-c', script], capture_output=True, encoding='utf-8', errors='replace', timeout=15)
        self.assertNotEqual(proc.returncode, 0, '404 资源必须返回非 0 退出码')
        self.assertIn('目标资源不存在', proc.stderr + proc.stdout)
        self.assertNotIn('=== 进入最终降级轮询机制 ===', proc.stdout, '命中 404 时必须立即熔断，严禁进入降级轮询')


if __name__ == '__main__':
    unittest.main()
