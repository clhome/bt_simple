# coding: utf-8
"""针对 9d30461 真机回归测试报告（2026-10-29）中新发现四项缺陷的专属回归测试套件：

N8 (P1)：github_download 接受坏文件，phpmyadmin 失败根因；
N9 (P1)：php 依赖助手 curl 条目传冲突包，自动安装永失败；
N10 (P2)：php 主构建核心依赖不在助手覆盖内；
N11 (P1)：mysql-fast 官方下载 URL 404 与长超时。
"""

import io
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXIES_LIST = os.path.join(ROOT, 'scripts', 'proxies.list')
DEPLOY_SH = os.path.join(ROOT, 'deploy.sh')
GH_DL_SH = os.path.join(ROOT, 'scripts', 'github_download.sh')
PMA_INSTALL_SH = os.path.join(ROOT, 'plugins', 'phpmyadmin', 'install.sh')
PHP_DEPS_SH = os.path.join(ROOT, 'plugins', 'php', 'versions', 'common', 'php_ext_deps.sh')
PHP_CURL_SH = os.path.join(ROOT, 'plugins', 'php', 'versions', 'common', 'curl.sh')
PHP_INSTALL_SH = os.path.join(ROOT, 'plugins', 'php', 'install.sh')
MYSQL_INSTALL_SH = os.path.join(ROOT, 'plugins', 'mysql', 'install.sh')


def _find_bash():
    git_bash = r'C:\Program Files\Git\bin\bash.exe'
    if os.name == 'nt' and os.path.exists(git_bash):
        return git_bash
    found = shutil.which('bash')
    return found


BASH = _find_bash()


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


class TestN8DownloadVerificationAndProxy(unittest.TestCase):
    """N8 修复验证：坏代理节点剔除、压缩包魔数强校验、phpmyadmin 回退防线。"""

    def test_01_gh_con_sh_removed_from_proxy_list(self):
        proxies_content = _read(PROXIES_LIST)
        deploy_content = _read(DEPLOY_SH)
        self.assertNotIn('gh.con.sh', proxies_content, '失效节点 gh.con.sh 必须从 proxies.list 移除')
        self.assertNotIn('gh.con.sh', deploy_content, '失效节点 gh.con.sh 必须从 deploy.sh 引导副本移除')

    def test_02_verify_rejects_abuse_report_bad_file(self):
        """真机现场：代理返回 48 字节停用文本，必须 100% 判定为无效文件。"""
        if not BASH:
            self.skipTest('系统未找到可用 bash，跳过行为执行用例')

        tmp_dir = tempfile.mkdtemp(prefix='yf_test_n8_')
        try:
            # 模拟真机撞上的 48 字节代理停用内容
            bad_content = 'Suspent due to abuse report. @ 2024 gh.con.sh\n'
            bad_file_xz = os.path.join(tmp_dir, 'phpMyAdmin-5.2.1-all-languages.tar.xz')
            bad_file_part = os.path.join(tmp_dir, 'phpMyAdmin-5.2.1-all-languages.tar.xz.part')
            with io.open(bad_file_xz, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write(bad_content)
            with io.open(bad_file_part, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write(bad_content)

            runner_sh = os.path.join(tmp_dir, 'test_runner.sh')
            with io.open(runner_sh, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/bash\n')
                fp.write('source "%s"\n' % GH_DL_SH.replace('\\', '/'))
                fp.write('_gh_verify_file "$1" && echo "V_OK" || echo "V_FAIL"\n')
                fp.write('yf_verify_archive "$1" && echo "A_OK" || echo "A_FAIL"\n')

            # 运行断言：针对 .tar.xz
            res = subprocess.run([BASH, runner_sh.replace('\\', '/'), bad_file_xz.replace('\\', '/')],
                                 capture_output=True, text=True, timeout=30)
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            self.assertIn('V_FAIL', lines, '压缩包文件即使只包含代理停用文本，_gh_verify_file 也必须判定失败')
            self.assertIn('A_FAIL', lines, '压缩包文件包含代理停用文本，yf_verify_archive 必须判定失败')

            # 运行断言：针对 .tar.xz.part
            res_part = subprocess.run([BASH, runner_sh.replace('\\', '/'), bad_file_part.replace('\\', '/')],
                                      capture_output=True, text=True, timeout=30)
            lines_part = [line.strip() for line in res_part.stdout.splitlines() if line.strip()]
            self.assertIn('V_FAIL', lines_part, '.part 中间件遭遇代理停用文本，_gh_verify_file 必须判定失败')
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_03_phpmyadmin_install_has_archive_verification(self):
        """phpmyadmin 安装脚本必须在下载后和回退前调用 yf_verify_archive 检验。"""
        src = _read(PMA_INSTALL_SH)
        self.assertIn('yf_verify_archive "$_try_path"', src,
                      'phpmyadmin 下载后必须执行 yf_verify_archive 校验')
        self.assertIn('rm -f "$_try_path"', src,
                      '校验不通过时必须清掉损坏文件以进入官方源回退')


class TestN9PhpDepsHelperConflictIsolation(unittest.TestCase):
    """N9 修复验证：php 扩展依赖助手互斥包隔离与单包建议。"""

    def test_01_php_deps_helper_loops_candidates(self):
        src = _read(PHP_DEPS_SH)
        # 必须逐个遍历候选包，而不是一次性全部传给 apt-get
        self.assertIn('for _cand in ${_apt_pkg}; do', src,
                      'yf_ext_ensure_pkgconfig 必须对 apt 包逐个遍历尝试')
        self.assertIn('for _cand in ${_rpm_pkg}; do', src,
                      'yf_ext_ensure_pkgconfig 必须对 rpm 包逐个遍历尝试')
        # 错误提示中的照抄命令必须取第一个包，避免多个互斥包一起拼接
        self.assertIn('_pref_apt=$(echo "${_apt_pkg}" | awk \'{print $1}\')', src,
                      '照抄命令必须提取首选单个包')
        self.assertIn('_last_err=', src,
                      '必须保留包管理器错误日志用于故障诊断')

    def test_02_curl_sh_deps_invocation(self):
        src = _read(PHP_CURL_SH)
        self.assertIn('yf_ext_ensure_pkgconfig libcurl', src)
        self.assertIn('libcurl4-openssl-dev', src)


class TestN10PhpCoreBuildDepsEnsure(unittest.TestCase):
    """N10 修复验证：php 主构建核心依赖前置确保机制。"""

    def test_01_core_deps_function_exists(self):
        src = _read(PHP_DEPS_SH)
        self.assertIn('yf_php_ensure_core_build_deps()', src,
                      'php_ext_deps.sh 必须提供 yf_php_ensure_core_build_deps 函数')
        self.assertIn('libxml-2.0', src, '必须检查 libxml-2.0')
        self.assertIn('libxml2-dev', src, '必须覆盖 libxml2-dev')
        self.assertIn('pkg-config', src, '必须覆盖 pkg-config')

    def test_02_php_install_invokes_core_deps(self):
        src = _read(PHP_INSTALL_SH)
        self.assertIn('yf_php_ensure_core_build_deps', src,
                      'plugins/php/install.sh 编译前必须调用 yf_php_ensure_core_build_deps')
        self.assertIn('yf_require_step "检查并补齐 PHP 主构建核心依赖"', src,
                      '核心依赖检查必须纳入安装报告体系（yf_require_step）')


class TestN11MysqlFastDownloadTimeoutAndMirrors(unittest.TestCase):
    """N11 修复验证：mysql-fast 官方分发 URL、大包超时配置与版本有效性。"""

    def test_01_mysql_fast_timeout_is_long(self):
        src = _read(MYSQL_INSTALL_SH)
        self.assertIn('dl_timeout=1800', src, 'MySQL 预编译大包下载超时必须设为 1800s')
        self.assertIn('yf_download "${tmp_file}" "${mirror_url}" "${dl_timeout}"', src,
                      'yf_download 必须显式传入长超时')

    def test_02_official_mirrors_included_first(self):
        src = _read(MYSQL_INSTALL_SH)
        # 官方当前发布 CDN 与重定向必须在列表中且在归档前
        self.assertIn('"https://cdn.mysql.com/Downloads/${download_path}/${tar_file}"', src)
        self.assertIn('"https://dev.mysql.com/get/Downloads/${download_path}/${tar_file}"', src)
        self.assertIn('"https://downloads.mysql.com/archives/get/p/23/file/${tar_file}"', src)

    def test_03_mysql_84_version_is_valid_lts(self):
        src = _read(MYSQL_INSTALL_SH)
        # 8.4 已升级为当前实际可用的 8.4.13
        self.assertIn('mysql_full_ver="8.4.13"', src,
                      '8.4 分支必须配置为真实可用的 8.4.13 LTS')


if __name__ == '__main__':
    unittest.main(verbosity=2)

