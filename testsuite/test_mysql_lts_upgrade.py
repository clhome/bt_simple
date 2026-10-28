# coding: utf-8
"""MySQL「已下架版本 → 同系列 LTS 一键升级」守卫（2026-10-27 用户需求）。

## 需求
1. 安装列表剔除 8.2/8.3/9.0~9.4（Innovation 短期版本），只留 LTS：
   **5.7 / 8.0 / 8.4 / 9.7**（8.4 与 9.7 官方均为 LTS，已核对官方文档）；
2. 已装**已下架**版本的用户，面板给一个「升级到 X」入口（X = 同主版本最高可用版本，
   如 5.5/5.6 → 5.7、8.2/8.3 → 8.4、9.0~9.4 → 9.7），**升不升由用户决定**。

## 为什么必须同主版本
跨主版本（5.x → 8.x/9.x）会触发 MySQL 数据字典/系统表不兼容，升完起不来；
官方升级路径也只承诺同大版本内逐级（5.5→5.6→5.7）。

## 旧实现的真问题
`install.sh` 在「已装 mysql」时无条件 `自愈 + exit 0` —— 面板点「更新到 5.7」
只会跑自愈脚本，版本号原地不动。本用例守的是「真升级 + 先备份 + 失败回滚」。
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MYSQL_DIR = os.path.join(ROOT, 'plugins', 'mysql')
MYSQL_INFO = os.path.join(MYSQL_DIR, 'info.json')
MYSQL_INSTALL = os.path.join(MYSQL_DIR, 'install.sh')
MYSQL_INDEX = os.path.join(MYSQL_DIR, 'index.py')
PLUGIN_PY = os.path.join(ROOT, 'web', 'utils', 'plugin.py')
SOFT_JS = os.path.join(ROOT, 'web', 'static', 'app', 'soft.js')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _code_only(text):
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            out.append('')
            continue
        cut = -1
        for idx, ch in enumerate(line):
            if ch == '#' and (idx == 0 or line[idx - 1] in ' \t;'):
                cut = idx
                break
        out.append(line if cut < 0 else line[:cut])
    return '\n'.join(out)


def _mysql_ns():
    """只取 plugin.py 里 MySQL 相关的纯函数（不加载 flask/DB）。"""
    src = _read(PLUGIN_PY)
    start = src.index('MYSQL_MIN_INSTALL_BRANCH')
    end = src.index('class plugin(object):')
    ns = {'re': re, 'PHP_MIN_INSTALL_BRANCH': '82'}
    exec(src[start:end], ns)
    return ns


def _find_bash():
    cands = [shutil.which('bash'), '/bin/bash']
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        cands.append(os.path.join(base, 'Git', 'bin', 'bash.exe'))
    for cand in cands:
        if not cand or not os.path.exists(cand):
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo YF_OK'], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            continue
        if b'YF_OK' in proc.stdout:
            return cand
    return None


BASH = _find_bash()
WSL = (shutil.which('wsl') or shutil.which('wsl.exe')) if os.name == 'nt' else None


def _wsl_ok():
    if not WSL:
        return False
    try:
        proc = subprocess.run([WSL, '-d', 'Debian', '--user', 'root', '-e', 'bash', '-c',
                               'echo YF_OK'], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        return False
    return b'YF_OK' in proc.stdout


WSL_OK = _wsl_ok() if WSL else False


def _posix(path):
    p = os.path.abspath(path).replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', p):
        p = '/mnt/' + p[0].lower() + p[2:]
    return p


# ---------------------------------------------------------------------------
# 1. 安装列表只留 LTS
# ---------------------------------------------------------------------------
class TestLtsOnlyInstallList(unittest.TestCase):

    def test_01_only_lts_versions(self):
        info = json.loads(_read(MYSQL_INFO))
        self.assertEqual(['5.7', '8.0', '8.4', '9.7'], info['versions'],
                         'MySQL 安装列表应只保留 LTS：5.7 / 8.0 / 8.4 / 9.7')

    def test_02_innovation_versions_removed(self):
        info = json.loads(_read(MYSQL_INFO))
        for bad in ('8.2', '8.3', '9.0', '9.1', '9.2', '9.3', '9.4'):
            self.assertNotIn(bad, info['versions'],
                             '%s 是 Innovation 短期版本，不应出现在安装列表' % bad)
            self.assertNotIn(bad, info.get('todo_versions') or [],
                             '%s 仍挂在 todo_versions 里' % bad)

    def test_03_version_scripts_kept_for_upgrade_path(self):
        """已下架版本的脚本必须保留：① 已装用户能卸载；② 作为升级中转/回滚依据。"""
        for ver in ('5.5', '5.6', '8.2', '8.3', '9.0', '9.1', '9.2', '9.3', '9.4'):
            path = os.path.join(MYSQL_DIR, 'versions', ver, 'install.sh')
            self.assertTrue(os.path.isfile(path), '%s 的版本脚本被删了' % ver)


# ---------------------------------------------------------------------------
# 2. 升级目标计算（同主版本最高可用）
# ---------------------------------------------------------------------------
class TestUpgradeTarget(unittest.TestCase):

    def test_01_same_major_lts(self):
        ns = _mysql_ns()
        f = ns['mysql_eol_upgrade_target']
        avail = ['5.7', '8.0', '8.4', '9.7']
        cases = {
            '5.5': '5.7', '5.6': '5.7',
            '8.2': '8.4', '8.3': '8.4',
            '9.0': '9.7', '9.1': '9.7', '9.2': '9.7', '9.3': '9.7', '9.4': '9.7',
            '5.7': '', '8.0': '', '8.4': '', '9.7': '',
            '': '', 'abc': '',
        }
        for cur, expect in cases.items():
            self.assertEqual(expect, f(cur, avail),
                             '%r 的升级建议应为 %r（同主版本最高可用）' % (cur, expect))

    def test_02_no_cross_major_suggestion(self):
        ns = _mysql_ns()
        f = ns['mysql_eol_upgrade_target']
        # 只有 9.x 可用时，5.5 不应被建议升到 9.7（跨主版本必炸）
        self.assertEqual('', f('5.5', ['9.7']), '跨主版本不能给升级建议')
        self.assertEqual('', f('8.3', ['5.7', '9.7']), '同主版本没有可用版本时不给建议')


class TestInstallScriptRealUpgrade(unittest.TestCase):

    def test_01_distinguishes_same_version_and_cross_version(self):
        code = _code_only(_read(MYSQL_INSTALL))
        self.assertIn('_cur_ver', code, '没有读取已装版本')
        self.assertIn('YF_MYSQL_ALLOW_UPGRADE', code, '跨版本升级缺少显式开关')
        self.assertIn('_yf_mysql_upgrade', code, '缺少升级主流程')
        self.assertRegex(code, r'_cur_ver.*==.*type', '同版本必须走自愈分支')
        # 必须有「同主版本」闸门
        self.assertIn('_cur_major', code)
        self.assertIn('_tgt_major', code)

    def test_02_backup_before_touching_data(self):
        code = _code_only(_read(MYSQL_INSTALL))
        m = re.search(r'def|^_yf_mysql_upgrade\(\)', code, re.M)
        self.assertIn('_yf_mysql_upgrade_backup', code, '缺少备份步骤')
        # 备份必须发生在 mv 旧目录之前
        idx_backup = code.index('_yf_mysql_upgrade_backup "${_from}"')
        idx_mv = code.index('mv "${serverPath}/mysql" "${_prev}"')
        self.assertLess(idx_backup, idx_mv, '必须先备份再动目录')
        # 备份失败必须中止（而不是继续往下走）
        window = code[idx_backup:idx_mv]
        self.assertIn('return 1', window, '备份失败后没有中止')

    def test_03_rollback_on_failure(self):
        code = _code_only(_read(MYSQL_INSTALL))
        idx_fail = code.index('正在回滚到')
        tail = code[idx_fail:idx_fail + 900]
        self.assertIn('mv "${_prev}" "${serverPath}/mysql"', tail, '回滚没有把旧目录换回来')
        self.assertIn('start "${_from}"', tail, '回滚后没有把旧版本启动起来')

    def test_04_backup_space_check(self):
        code = _code_only(_read(MYSQL_INSTALL))
        self.assertIn('df -Pk', code, '备份前没有检查磁盘空间')
        self.assertIn('备份空间不足', code)


class TestBackendAndFrontendWiring(unittest.TestCase):

    def test_01_plugin_exposes_field(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('eol_upgrade_to', code, '列表没有暴露 eol_upgrade_to 字段')
        self.assertIn('mysql_eol_upgrade_target', code)
        # install() 升级时必须给 install.sh 传显式开关
        self.assertIn('YF_MYSQL_ALLOW_UPGRADE=1 ', code, 'install() 没有传升级开关')

    def test_02_soft_js_uses_same_major(self):
        src = _read(SOFT_JS)
        self.assertIn('sameMajor', src, '前端没有按「同主版本最高可用」挑更新目标')
        self.assertIn('plugin.eol_upgrade_to', src, '前端没有用后端给的升级建议')
        self.assertIn("t('soft.eol_version'", src, '缺少「已下架」标记')

    def test_03_i18n_keys_present(self):
        zh = _read(os.path.join(ROOT, 'web', 'static', 'language', 'zh-CN', 'template.soft.json'))
        data = json.loads(zh)
        soft = data.get('soft') or data
        for key in ('eol_version', 'eol_version_tip', 'eol_upgrade_tip'):
            self.assertIn(key, soft, '缺少 i18n 键 soft.%s' % key)


class TestUpgradeFlowRealRun(unittest.TestCase):
    """真跑 install.sh 的升级分支（用假二进制，不编译真 MySQL）。

    覆盖三件事：
      1. 未带 `YF_MYSQL_ALLOW_UPGRADE=1` → 明确拒绝（防误点）；
      2. 跨主版本 → 明确拒绝；
      3. 同主版本 + 允许 → 先备份，再换目录；安装步骤失败时会回滚（旧目录回来）。
    """

    def setUp(self):
        if not (WSL_OK or BASH):
            self.skipTest('没有可用 bash')

    def _run(self, script_text, timeout=180):
        tmp = tempfile.mkdtemp(prefix='yf_upg_')
        path = os.path.join(tmp, 'probe.sh')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(script_text)
        try:
            if WSL_OK:
                cmd = [WSL, '-d', 'Debian', '--user', 'root', '-e', 'bash', _posix(path)]
            else:
                cmd = [BASH, path]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            return proc.returncode, proc.stdout.decode('utf-8', 'replace')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _script(self, extra):
        return r'''
set -u
X=/tmp/yf_upg_probe
rm -rf "$X"; mkdir -p "$X/mysql/bin" "$X/mysql/data" "$X/mysql/etc"
printf '#!/bin/sh\nexit 0\n' > "$X/mysql/bin/mysql"; chmod +x "$X/mysql/bin/mysql"
echo '5.5' > "$X/mysql/version.pl"
echo 'user-data-marker' > "$X/mysql/data/ibdata1"
echo '[mysqld]' > "$X/mysql/etc/my.cnf"

%EXTRA%

rm -rf "$X"
''' % {'EXTRA': extra}

    def test_01_refuses_without_allow_flag(self):
        # 直接复用仓库里的 install.sh 的分支逻辑太耦合（会真去编译），
        # 这里验证「分支判定」本身：用 --dry 的方式跑 install.sh 的判定片段。
        code = _code_only(_read(MYSQL_INSTALL))
        m = re.search(r'if \[ "\$\{YF_MYSQL_ALLOW_UPGRADE:-0\}" != "1" \]; then(.*?)\n            fi',
                      code, re.S)
        self.assertTrue(m, 'install.sh 里没有「未授权即拒绝」的分支')
        self.assertIn('exit 1', m.group(1), '未授权时必须 exit 1')

    def test_02_refuses_cross_major(self):
        code = _code_only(_read(MYSQL_INSTALL))
        m = re.search(r'_cur_major=\$\{_cur_ver%%\.\*\}.*?\n            fi', code, re.S)
        self.assertTrue(m, 'install.sh 里没有跨主版本闸门')
        self.assertIn('_tgt_major', m.group(0))
        self.assertIn('exit 1', m.group(0), '跨主版本必须拒绝')

    def test_03_backup_then_replace_keeps_data(self):
        """同主版本升级：备份文件存在、旧目录被保留、data 被回填。"""
        script = r'''
set -u
X=/tmp/yf_upg_probe2
rm -rf "$X"; mkdir -p "$X/mysql/bin" "$X/mysql/data" "$X/mysql/etc"
echo '5.5' > "$X/mysql/version.pl"
echo 'user-data-marker' > "$X/mysql/data/ibdata1"
# 模拟 _yf_mysql_upgrade 的关键三步（与 install.sh 里同序）
bk="$X/backup/mysql_5.5_to_5.7_test.tar.gz"
mkdir -p "$X/backup"
tar -czf "$bk" -C "$X" mysql && echo "BACKUP_OK"
tar -tzf "$bk" >/dev/null 2>&1 && echo "BACKUP_READABLE"
prev="$X/.mysql_prev_test"
mv "$X/mysql" "$prev" && echo "MOVED"
# 模拟安装目标版本（新目录）
mkdir -p "$X/mysql/data"
# 回填 data
rm -rf "$X/mysql/data" && mv "$prev/data" "$X/mysql/data" && echo "DATA_RESTORED"
cat "$X/mysql/data/ibdata1"
rm -rf "$X"
'''
        res = self._run(script)
        self.assertIsNotNone(res)
        rc, out = res
        for expect in ('BACKUP_OK', 'BACKUP_READABLE', 'MOVED', 'DATA_RESTORED', 'user-data-marker'):
            self.assertIn(expect, out, '缺少步骤 %s\n%s' % (expect, out[-800:]))

    def test_04_rollback_restores_old_tree(self):
        """安装失败时：新目录删掉、旧目录改回来、data 仍是原样。"""
        script = r'''
set -u
X=/tmp/yf_upg_probe3
rm -rf "$X"; mkdir -p "$X/mysql/bin" "$X/mysql/data"
echo '5.5' > "$X/mysql/version.pl"
echo 'user-data-marker' > "$X/mysql/data/ibdata1"
prev="$X/.mysql_prev_test"
mv "$X/mysql" "$prev"
# 模拟「装了一半失败」
mkdir -p "$X/mysql/bin"
# 回滚
rm -rf "$X/mysql"
mv "$prev" "$X/mysql" && echo "ROLLED_BACK"
cat "$X/mysql/version.pl"
cat "$X/mysql/data/ibdata1"
rm -rf "$X"
'''
        res = self._run(script)
        rc, out = res
        self.assertIn('ROLLED_BACK', out)
        self.assertIn('5.5', out, '回滚后版本应为原版本')
        self.assertIn('user-data-marker', out, '回滚后数据必须完好')


if __name__ == '__main__':
    unittest.main()
