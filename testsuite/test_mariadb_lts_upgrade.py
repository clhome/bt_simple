# coding: utf-8
"""MariaDB「只留 LTS + 已下架/已过维护期版本可一键升级」守卫（2026-10-27 用户需求）。

## 官方口径（`downloads.mariadb.org/rest-api/mariadb/` 实查）

    ver    status   support            eol
    10.6   Stable   Long Term Support  2026-07-06   ← 维护期已过（仍按用户要求保留安装）
    10.11  Stable   Long Term Support  2028-02-16
    11.4   Stable   Long Term Support  2029-05-29
    11.8   Stable   Long Term Support  2030-02-13
    13.0   Stable   Rolling            -
    其余 10.7~10.9 / 11.0~11.3 / 11.5~11.7 / 12.x 非 LTS → Rolling 短期版本

所以安装列表只留 **10.6 / 10.11 / 11.4 / 11.8**（用户指定），
其它短期版本下架；已装旧版的用户可以在商店里一键升到**同系列最接近的 LTS**：
    10.7~10.9 → 10.11（10.6 属「已过维护期」，同样建议 10.11）
    11.0~11.3 → 11.4
    11.5~11.7 → 11.8
    12.x      → 无（本仓库没有 12.x 的 LTS 脚本，不给跨主版本建议）
"""
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARIA_DIR = os.path.join(ROOT, 'plugins', 'mariadb')
MARIA_INFO = os.path.join(MARIA_DIR, 'info.json')
MARIA_INSTALL = os.path.join(MARIA_DIR, 'install.sh')
MARIA_INDEX = os.path.join(MARIA_DIR, 'index.py')
PLUGIN_PY = os.path.join(ROOT, 'web', 'utils', 'plugin.py')

MARIA_LTS = ['10.6', '10.11', '11.4', '11.8']
ROLLING = ['10.7', '10.8', '10.9', '11.0', '11.1', '11.2', '11.3', '11.5', '11.6', '11.7', '12.0', '12.1']


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


def _ns():
    """取 plugin.py 里 MySQL/MariaDB 那段纯函数（不加载 flask/DB）。"""
    src = _read(PLUGIN_PY)
    start = src.index('MYSQL_MIN_INSTALL_BRANCH')
    end = src.index('class plugin(object):')
    ns = {'re': re, 'PHP_MIN_INSTALL_BRANCH': '82', 'time': __import__('time')}
    exec(src[start:end], ns)
    return ns


class TestMariaLtsList(unittest.TestCase):

    def test_01_only_lts_versions(self):
        info = json.loads(_read(MARIA_INFO))
        self.assertEqual(MARIA_LTS, info['versions'],
                         'MariaDB 安装列表应只保留 LTS：10.6 / 10.11 / 11.4 / 11.8')

    def test_02_rolling_versions_removed(self):
        info = json.loads(_read(MARIA_INFO))
        for bad in ROLLING:
            self.assertNotIn(bad, info['versions'],
                             '%s 是 Rolling 短期版本，不应出现在安装列表' % bad)

    def test_03_version_scripts_kept(self):
        """已下架版本的脚本必须保留：卸载 + 升级中转/回滚都要用。"""
        for ver in ROLLING:
            path = os.path.join(MARIA_DIR, 'versions', ver, 'install.sh')
            if not os.path.isdir(os.path.join(MARIA_DIR, 'versions', ver)):
                continue
            self.assertTrue(os.path.isfile(path), '%s 的版本脚本被删了' % ver)


class TestMariaUpgradeTarget(unittest.TestCase):

    def test_01_state_and_target(self):
        ns = _ns()
        state = ns['db_eol_state']
        expect = {
            '10.6': ('eol', '10.11'),        # 仍在列表但维护期已过（EOL 2026-07-06）
            '10.7': ('removed', '10.11'),
            '10.8': ('removed', '10.11'),
            '10.9': ('removed', '10.11'),
            '10.11': ('', ''),
            '11.0': ('removed', '11.4'),     # 同系列**最接近**的 LTS，不是 11.8
            '11.1': ('removed', '11.4'),
            '11.2': ('removed', '11.4'),
            '11.3': ('removed', '11.4'),
            '11.4': ('', ''),
            '11.5': ('removed', '11.8'),
            '11.6': ('removed', '11.8'),
            '11.7': ('removed', '11.8'),
            '11.8': ('', ''),
            '12.0': ('removed', ''),         # 没有 12.x LTS 脚本 → 不给跨主版本建议
            '': ('', ''),
        }
        for cur, (kind, tgt) in expect.items():
            got = state('mariadb', cur, MARIA_LTS)
            self.assertEqual((kind, tgt), got, 'mariadb %r 的提示应为 %r，实际 %r'
                             % (cur, (kind, tgt), got))

    def test_02_other_plugins_untouched(self):
        ns = _ns()
        state = ns['db_eol_state']
        self.assertEqual(('', ''), state('redis', '7.4', ['7.4.8']),
                         '非 mysql/mariadb 插件不应有下架提示')
        self.assertEqual(('', ''), state('', '10.7', MARIA_LTS))

    def test_03_installable_whitelist(self):
        ns = _ns()
        self.assertEqual(tuple(MARIA_LTS), ns['db_installable_versions']('mariadb'))
        self.assertEqual(('5.7', '8.0', '8.4', '9.7'), ns['db_installable_versions']('mysql'))
        self.assertEqual((), ns['db_installable_versions']('redis'))

    def test_04_fast_install_suffix_must_pass_whitelist(self):
        """极速安装传的是 `5.7-fast`：剥掉后缀后必须能过 LTS 白名单。

        2026-10-28 真机事故：软件商店「极速安装」按钮 POST `version=5.7-fast`，
        而白名单直接拿整串比对 → 判成「非 LTS」→ 直接拒绝、任务不入队，
        消息盒子「当前没有任务」，用户看到的现象就是「mysql 所有版本都装不上」。
        """
        ns = _ns()
        reject = ns['db_install_reject_key']
        for name, ver in (('mysql', '5.7-fast'), ('mysql', '8.0-fast'),
                          ('mysql', '8.4-fast'), ('mysql', '9.7-fast')):
            self.assertEqual('', reject(name, ver),
                             '%s 的极速安装 %s 被误拒（白名单未剥 -fast 后缀）' % (name, ver))
        # mariadb 自 2026-10-28 起也支持极速安装（Install_fast_mariadb + install.html
        # 的 install_hook_mariadb），所以它的 -fast 同样必须过 LTS 白名单；
        # 但白名单只认分支（10.11 / 11.4 / ...），后缀必须剥掉再比。
        for ver in ('10.11-fast', '11.4-fast', '11.8-fast'):
            self.assertEqual('', reject('mariadb', ver),
                             'mariadb 的极速安装 %s 被误拒' % ver)
        # 非 LTS 带不带后缀都拒
        self.assertEqual('plugin.mariadb_eol_branch_install', reject('mariadb', '10.7-fast'))
        # 非 LTS 带不带后缀都要拒
        for name, ver in (('mysql', '8.2'), ('mysql', '8.2-fast'),
                          ('mariadb', '10.7'), ('mariadb', '12.0-fast')):
            self.assertNotEqual('', reject(name, ver), '%s %s 不该放行' % (name, ver))
        # 其它插件不受该策略影响
        self.assertEqual('', reject('redis', '7.2'))
        self.assertEqual('', reject('php', '84'))

    def test_04b_fast_support_is_explicit_per_plugin(self):
        """`-fast` 只对真正实现极速安装的插件放行（当前仅 mysql）。"""
        ns = _ns()
        self.assertTrue(ns['is_fast_install_supported']('mysql'))
        self.assertTrue(ns['is_fast_install_supported']('mariadb'))
        self.assertFalse(ns['is_fast_install_supported']('redis'))
        self.assertFalse(ns['is_fast_install_supported']('php'))
        self.assertEqual(('mysql', 'mariadb'), tuple(ns['FAST_INSTALL_PLUGINS']))
        # 插件级门禁：其它插件带 -fast 必须按参数错误拒掉
        gate = ns['fast_install_gate_key']
        self.assertEqual('', gate('mysql', '5.7-fast'))
        self.assertEqual('', gate('mariadb', '11.4-fast'))
        self.assertEqual('', gate('redis', '7.2'))
        self.assertEqual('ARGS_ERR', gate('redis', '7.2-fast'))
        self.assertEqual('ARGS_ERR', gate('php', '84-fast'))
        # mysql 的 install.sh 必须真的认 `-fast`（否则放行就是假成功源头）
        sh_mysql = _read('plugins/mysql/install.sh')
        self.assertIn('-fast', sh_mysql, 'mysql/install.sh 未实现 -fast 分支')
        self.assertIn('Install_fast_mysql', sh_mysql, 'mysql/install.sh 缺少极速安装实现')
        # mariadb 的 install.sh 也必须真的认 `-fast`（2026-10-28 新增极速安装）
        sh_maria = _read('plugins/mariadb/install.sh')
        self.assertIn('-fast', sh_maria, 'mariadb/install.sh 未实现 -fast 分支')
        self.assertIn('Install_fast_mariadb', sh_maria,
                      'mariadb/install.sh 缺少极速安装实现')
        # 前端必须有对应的 hook（否则商店永远发不出 -fast）
        html = _read('plugins/mariadb/install.html')
        self.assertIn('window.install_hook_mariadb', html,
                      'mariadb 缺少 install.html 的 install_hook_mariadb')
        self.assertIn('mariadb_install_type', html)

    def test_05_install_uses_normalized_whitelist(self):
        """`plugin.install()` 必须走归一化后的判定（防再退回整串比对）。"""
        body = _read(PLUGIN_PY)
        self.assertIn('db_install_reject_key(_name_l, version)', body,
                      'install() 未使用 db_install_reject_key()')
        self.assertNotIn('_allowed and str(version).strip() not in _allowed', body,
                         'install() 又变回「整串 version 直接比对白名单」了')


class TestMariaInstallScriptUpgrade(unittest.TestCase):

    def test_01_same_version_selfheal_vs_upgrade(self):
        code = _code_only(_read(MARIA_INSTALL))
        self.assertIn('_cur_ver', code, '没有读取已装版本')
        self.assertIn('YF_MARIADB_ALLOW_UPGRADE', code, '跨版本升级缺少显式开关')
        self.assertIn('_yf_maria_upgrade', code, '缺少升级主流程')
        self.assertRegex(code, r'_cur_ver.*==.*type', '同版本必须走自愈分支')

    def test_02_backup_before_moving_dir(self):
        code = _code_only(_read(MARIA_INSTALL))
        self.assertIn('_yf_maria_upgrade_backup', code, '缺少备份步骤')
        idx_backup = code.index('_yf_maria_upgrade_backup "${_from}"')
        idx_mv = code.index('mv "${serverPath}/mariadb" "${_prev}"')
        self.assertLess(idx_backup, idx_mv, '必须先备份再动目录')
        self.assertIn('return 1', code[idx_backup:idx_mv], '备份失败后没有中止')

    def test_03_rollback(self):
        code = _code_only(_read(MARIA_INSTALL))
        idx = code.index('正在回滚到')
        tail = code[idx:idx + 900]
        self.assertIn('mv "${_prev}" "${serverPath}/mariadb"', tail, '回滚没有把旧目录换回来')
        self.assertIn('start "${_from}"', tail, '回滚后没有把旧版本启动起来')

    def test_04_cross_major_refused(self):
        code = _code_only(_read(MARIA_INSTALL))
        self.assertIn('_cur_major', code)
        self.assertIn('_tgt_major', code)
        self.assertIn('拒绝跨主版本升级', code)

    def test_05_backup_space_check(self):
        code = _code_only(_read(MARIA_INSTALL))
        self.assertIn('df -Pk', code, '备份前没有检查磁盘空间')
        self.assertIn('备份空间不足', code)


class TestMariaIndexUpgradeEntry(unittest.TestCase):

    def test_01_command_exists(self):
        src = _read(MARIA_INDEX)
        self.assertIn('def runMariaUpgrade(', src, '缺少 mariadb-upgrade 入口函数')
        self.assertIn("elif func == 'mariadb_upgrade':", src, '入口函数没有接到 __main__ 分发')
        code = _code_only(src)
        self.assertIn('--defaults-extra-file=', code,
                      'mariadb-upgrade 不能用 argv 传口令（ps 可见），要走 0600 option 文件')
        self.assertIn('mariadb-upgrade', code)
        # 兜底老版本用 mysql_upgrade 可执行文件
        self.assertIn("'/bin/mysql_upgrade'", code)

    def test_02_plugin_passes_upgrade_env(self):
        code = _code_only(_read(PLUGIN_PY))
        self.assertIn('YF_MARIADB_ALLOW_UPGRADE=1 ', code,
                      'install() 没给 mariadb 传升级开关')


class TestMariaI18nKeys(unittest.TestCase):

    def test_01_keys_present(self):
        zh = json.loads(_read(os.path.join(ROOT, 'web', 'static', 'language',
                                           'zh-CN', 'template.soft.json')))
        plugin = zh.get('plugin') or {}
        soft = zh.get('soft') or {}
        self.assertIn('mariadb_eol_branch_install', plugin)
        self.assertIn('eol_kind_removed', soft)
        self.assertIn('eol_kind_eol', soft)


if __name__ == '__main__':
    unittest.main()
