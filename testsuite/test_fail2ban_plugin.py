# coding: utf-8
"""
fail2ban 插件回归测试套件

覆盖范围：
  1. 安全校验层（safe_ip / safe_port / safe_int / safe_bool / 白名单 / shlex 转义）
  2. backend 解析（杜绝 [DEFAULT] backend 污染 mysql/redis jail）
  3. 黑名单生效链路（yf-manual 永久封禁 jail / SQL 下推 / 解封校验）
  4. 日志解析与尾读（parse_ban_line / read_tail_lines）
  5. 多国语言覆盖率（六语种键集一致、无 HTML、pt() 全覆盖、菜单键存在）
  6. 编码规范（UTF-8 无 BOM + LF）
  7. install.sh 加固（语法、依赖、卸载保留用户配置）

运行： python3 test/test_fail2ban_plugin.py -v
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, 'web')
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins', 'fail2ban')
LANG_DIR = os.path.join(PLUGIN_DIR, 'lang')

if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import index as f2b  # noqa: E402

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

# index.html 左侧菜单文本（由 translatePluginDOM 依据 data-i18n-orig 自动翻译）
MENU_LABELS = ['首页', '服务', '配置修改', '系统防护', '网站防护', '防护历史', 'IP黑名单', '运行日志']

# Windows 上 PATH 里的 bash 往往是 System32\bash.exe（WSL 启动器），
# 它无法直接执行本地脚本，必须优先定位 Git Bash。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    os.path.join(os.path.expanduser('~'), '.workbuddy-ai', 'binaries', 'PortableGit',
                 'versions', '1.2.0', 'bin', 'bash.exe'),
]


def find_posix_bash():
    """返回可用于 bash -n 校验的 POSIX shell 路径，找不到返回 None"""
    import shutil
    candidates = [p for p in BASH_CANDIDATES if os.path.exists(p)]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue  # 排除 WSL 启动器
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'],
                                  capture_output=True, text=True, timeout=30)
            if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
                return cand
        except Exception:
            continue
    return None


def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_lang(name):
    with open(os.path.join(LANG_DIR, name + '.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


class TestSecurityLayer(unittest.TestCase):
    """安全校验层：所有来自前端的参数必须经校验后才能进入配置与 shell"""

    def test_safe_ip_rejects_injection_and_invalid(self):
        bad = [
            '1.1.1.1;rm -rf /',
            '1.1.1.1 && cat /etc/passwd',
            '$(id)',
            '`id`',
            '1.1.1.1\n2.2.2.2',
            "1.1.1.1'",
            '999.1.1.1',
            '1.1.1',
            '::gg',
            '',
            '   ',
            None,
            123,
            ['1.1.1.1'],
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertIsNone(f2b.safe_ip(value))

    def test_safe_ip_accepts_valid_forms(self):
        cases = {
            '1.1.1.1': '1.1.1.1',
            ' 8.8.8.8 ': '8.8.8.8',
            '10.0.0.0/8': '10.0.0.0/8',
            '::1': '::1',
            '2001:db8::/32': '2001:db8::/32',
        }
        for raw, expect in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(f2b.safe_ip(raw), expect)

    def test_safe_port_blocks_config_injection(self):
        self.assertEqual(f2b.safe_port('80,443'), '80,443')
        self.assertEqual(f2b.safe_port('1:65535'), '1:65535')
        self.assertEqual(f2b.safe_port('22'), '22')
        self.assertEqual(f2b.safe_port(22), '22')
        # 注入尝试一律回落到默认值
        self.assertEqual(f2b.safe_port('80\nlogpath=/etc/passwd', 'DEF'), 'DEF')
        self.assertEqual(f2b.safe_port('80; rm -rf /', 'DEF'), 'DEF')
        self.assertEqual(f2b.safe_port('abc', 'DEF'), 'DEF')
        self.assertEqual(f2b.safe_port('', 'DEF'), 'DEF')
        self.assertEqual(f2b.safe_port(None, 'DEF'), 'DEF')

    def test_safe_int_clamps_to_limits(self):
        self.assertEqual(f2b.safe_int('5', 0, 'maxretry'), 5)
        self.assertEqual(f2b.safe_int('0', 9, 'maxretry'), 1)          # 下界收敛
        self.assertEqual(f2b.safe_int('999999999', 9, 'maxretry'), 100000)  # 上界收敛
        self.assertEqual(f2b.safe_int('-1', 9, 'bantime'), -1)         # -1 表示永久
        self.assertEqual(f2b.safe_int('-100', 9, 'bantime'), -1)
        self.assertEqual(f2b.safe_int('99999999', 9, 'bantime'), 31536000)
        self.assertEqual(f2b.safe_int('abc', 7, 'maxretry'), 7)
        self.assertEqual(f2b.safe_int(None, 7, 'findtime'), 7)

    def test_safe_bool_parsing(self):
        for truthy in ['true', 'TRUE', '1', 'yes', 'on', True]:
            with self.subTest(v=truthy):
                self.assertTrue(f2b.safe_bool(truthy, False))
        for falsy in ['false', '0', 'off', '', False]:
            with self.subTest(v=falsy):
                self.assertFalse(f2b.safe_bool(falsy, True))
        self.assertTrue(f2b.safe_bool(None, True))
        self.assertFalse(f2b.safe_bool(None, False))

    def test_is_allowed_mode_whitelist(self):
        for mode in f2b.ALLOWED_MODES:
            self.assertTrue(f2b.is_allowed_mode(mode))
        for mode in ['sshd; rm -rf /', '../etc', 'sshd\n', '', None, 1, 'yf-manual']:
            with self.subTest(mode=mode):
                self.assertFalse(f2b.is_allowed_mode(mode))

    def test_f2b_client_quotes_every_argument(self):
        captured = []

        def fake_exec(cmd, *a, **kw):
            captured.append(cmd)
            return ('', '')

        with patch.object(f2b.yf, 'execShell', side_effect=fake_exec):
            f2b.f2b_client('set', f2b.MANUAL_JAIL, 'banip', '1.1.1.1; rm -rf /')

        self.assertEqual(len(captured), 1)
        cmd = captured[0]
        # 危险载荷必须被单引号包裹，且不出现裸露的分号分隔
        self.assertIn("'1.1.1.1; rm -rf /'", cmd)
        self.assertTrue(cmd.startswith('fail2ban-client '))
        self.assertNotIn('; rm', cmd.replace("'1.1.1.1; rm -rf /'", ''))

    def test_f2b_client_ok_detects_failure(self):
        with patch.object(f2b, 'f2b_client', return_value=('ERROR Invalid jail name', '')):
            ok, msg = f2b.f2b_client_ok('set', 'nope', 'banip', '1.1.1.1')
            self.assertFalse(ok)
            self.assertIn('Invalid', msg)

        with patch.object(f2b, 'f2b_client', return_value=('1.1.1.1', '')):
            ok, _ = f2b.f2b_client_ok('set', f2b.MANUAL_JAIL, 'banip', '1.1.1.1')
            self.assertTrue(ok)


class TestBackendResolution(unittest.TestCase):
    """backend 必须逐 jail 声明，绝不允许写在 [DEFAULT] 段污染其他 jail"""

    def test_pick_logpath_returns_none_when_all_missing(self):
        with patch.object(f2b, '_glob_exists', return_value=False):
            self.assertIsNone(f2b.pick_logpath('mysql'))
            self.assertIsNone(f2b.pick_logpath('unknown-mode'))

    def test_pick_logpath_returns_first_hit(self):
        target = f2b.SERVICE_LOGPATHS['mysql'][1]

        def fake_glob(pattern):
            return pattern == target

        with patch.object(f2b, '_glob_exists', side_effect=fake_glob):
            self.assertEqual(f2b.pick_logpath('mysql'), target)

    def test_resolve_backend_prefers_real_log(self):
        log = '/var/log/mysql/error.log'
        with patch.object(f2b, 'pick_logpath', return_value=log):
            self.assertEqual(f2b.resolve_backend('mysql'), ('auto', log))

    def test_resolve_backend_falls_back_to_systemd(self):
        orig_exists = os.path.exists

        def fake_exists(path):
            if path in ('/run/systemd/system', '/lib/systemd/system'):
                return True
            return orig_exists(path)

        with patch.object(f2b, 'pick_logpath', return_value=None), \
             patch.object(os.path, 'exists', side_effect=fake_exists):
            self.assertEqual(f2b.resolve_backend('redis'), ('systemd', None))

    def test_sshd_uses_ssh_log_detection(self):
        with patch.object(f2b, 'getSshLogConfig', return_value=('auto', '/var/log/auth.log')) as m:
            self.assertEqual(f2b.resolve_backend('sshd'), ('auto', '/var/log/auth.log'))
            m.assert_called_once()

    def test_default_section_has_no_backend(self):
        """核心回归：backend 绝不能出现在 [DEFAULT] 段"""
        inst = f2b.fail2ban_main()
        tmp = tempfile.mkdtemp()
        try:
            inst._jail_local_file = os.path.join(tmp, 'jail.local')
            conf = {
                "strict": True,
                "server": [{"mode": "sshd", "port": "22", "maxretry": "5",
                            "findtime": "300", "bantime": "86400", "act": "true"}],
                "site": [{"mode": "global-cc", "port": "80,443", "maxretry": "60",
                          "findtime": "60", "bantime": "86400", "act": "true"}],
            }
            with patch.object(f2b, 'getSshLogConfig', return_value=('auto', '/var/log/auth.log')):
                inst.sync_jail_local(conf)

            content = read_text(inst._jail_local_file)
            default_block = content.split('[sshd]')[0]
            self.assertIn('[DEFAULT]', default_block)
            self.assertNotIn('backend', default_block)

            # 每个 jail 段都必须自带 backend
            for section in ('[sshd]', '[global-cc]'):
                seg = content.split(section)[1].split('\n[')[0]
                self.assertIn('backend =', seg, '%s 缺少独立 backend' % section)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestBlacklistChain(unittest.TestCase):
    """黑名单链路：先落盘 → 同步 yf-manual jail → 批量下发"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.black_file = os.path.join(self.tmp, 'black_list.json')
        self.config_file = os.path.join(self.tmp, 'config.json')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_paths(self):
        return patch.multiple(
            f2b,
            getBlackFile=lambda: self.black_file,
            getConfigFile=lambda: self.config_file,
        )

    def test_set_black_ip_rejects_injection_without_writing(self):
        argv = ['index.py', 'setBlackIp', json.dumps({'black_ip': '1.1.1.1; rm -rf /'})]
        with patch.object(sys, 'argv', argv), self._patch_paths():
            res = json.loads(f2b.setBlackIp())
        self.assertFalse(res['status'])
        self.assertIn('IP格式错误', res['msg'])
        # 非法输入绝不落盘（文件可能被 _read_conf 初始化为空数组，但不得含注入内容）
        if os.path.exists(self.black_file):
            self.assertEqual(json.loads(read_text(self.black_file)), [])

    def test_set_black_ip_writes_file_and_uses_manual_jail(self):
        calls = []
        argv = ['index.py', 'setBlackIp',
                json.dumps({'black_ip': '1.1.1.1,2.2.2.2'})]

        def fake_client_ok(*args):
            calls.append(args)
            return (True, 'ok')

        with patch.object(sys, 'argv', argv), self._patch_paths(), \
             patch.object(f2b, 'status', return_value='start'), \
             patch.object(f2b, 'f2b_client_ok', side_effect=fake_client_ok), \
             patch.object(f2b, '_sync_manual_jail', return_value=None):
            res = json.loads(f2b.setBlackIp())

        self.assertTrue(res['status'])

        # 1. 黑名单必须先落盘
        self.assertTrue(os.path.exists(self.black_file))
        self.assertEqual(json.loads(read_text(self.black_file)), ['1.1.1.1', '2.2.2.2'])

        # 2. 封禁必须打到 yf-manual 专用 jail，且为批量单次调用
        banip_calls = [c for c in calls if len(c) >= 3 and c[2] == 'banip']
        self.assertEqual(len(banip_calls), 1)
        self.assertEqual(banip_calls[0][1], f2b.MANUAL_JAIL)
        self.assertEqual(banip_calls[0][3], '1.1.1.1 2.2.2.2')

        # 3. 绝不能出现历史上打到 "server" 假 jail 的调用
        self.assertFalse([c for c in calls if len(c) >= 2 and c[1] == 'server'])

    def test_set_black_ip_service_down_only_persists(self):
        calls = []
        argv = ['index.py', 'setBlackIp', json.dumps({'black_ip': '1.1.1.1'})]

        with patch.object(sys, 'argv', argv), self._patch_paths(), \
             patch.object(f2b, 'status', return_value='stop'), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, 'ok'))[1]), \
             patch.object(f2b, '_sync_manual_jail', return_value=None):
            res = json.loads(f2b.setBlackIp())

        self.assertTrue(res['status'])
        self.assertEqual(json.loads(read_text(self.black_file)), ['1.1.1.1'])
        self.assertEqual(calls, [], '服务未运行时不应下发任何 fail2ban-client 命令')

    def test_set_black_ip_removes_dropped_ip(self):
        with open(self.black_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(['1.1.1.1', '9.9.9.9']))

        calls = []
        argv = ['index.py', 'setBlackIp', json.dumps({'black_ip': '1.1.1.1'})]

        with patch.object(sys, 'argv', argv), self._patch_paths(), \
             patch.object(f2b, 'status', return_value='start'), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, 'ok'))[1]), \
             patch.object(f2b, '_sync_manual_jail', return_value=None):
            f2b.setBlackIp()

        self.assertEqual(json.loads(read_text(self.black_file)), ['1.1.1.1'])
        unban_calls = [c for c in calls if len(c) >= 3 and c[2] == 'unbanip']
        self.assertEqual(unban_calls[0][3], '9.9.9.9')

    def test_unban_active_ip_rejects_invalid_ip(self):
        argv = ['index.py', 'unban_active_ip', json.dumps({'ip': '1.1.1.1; rm -rf /'})]
        calls = []
        with patch.object(sys, 'argv', argv), self._patch_paths(), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, ''))[1]):
            res = json.loads(f2b.unban_active_ip())

        self.assertFalse(res['status'])
        self.assertEqual(calls, [], '非法 IP 不得触发任何 shell 调用')

    def test_unban_active_ip_syncs_blacklist_file(self):
        with open(self.black_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(['1.1.1.1', '2.2.2.2']))

        argv = ['index.py', 'unban_active_ip',
                json.dumps({'ip': '1.1.1.1', 'jail': f2b.MANUAL_JAIL})]
        calls = []
        with patch.object(sys, 'argv', argv), self._patch_paths(), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, ''))[1]):
            res = json.loads(f2b.unban_active_ip())

        self.assertTrue(res['status'])
        # 解封后必须同步移出黑名单文件，避免下次启动被重新封禁
        self.assertEqual(json.loads(read_text(self.black_file)), ['2.2.2.2'])
        self.assertEqual(calls[0][:3], ('set', f2b.MANUAL_JAIL, 'unbanip'))

    def test_get_active_bans_sql_pushdown_and_manual_flag(self):
        db_path = os.path.join(self.tmp, 'fail2ban.sqlite3')
        conn = sqlite3.connect(db_path)
        conn.execute('CREATE TABLE bans (jail TEXT, ip TEXT, timeofban INTEGER, bantime INTEGER)')
        now = int(time.time())
        conn.execute('INSERT INTO bans VALUES (?,?,?,?)', ('sshd', '1.1.1.1', now - 10, 86400))
        conn.execute('INSERT INTO bans VALUES (?,?,?,?)', ('sshd', '2.2.2.2', now - 100000, 10))
        conn.execute('INSERT INTO bans VALUES (?,?,?,?)', (f2b.MANUAL_JAIL, '3.3.3.3', now - 10, -1))
        conn.commit()
        conn.close()

        with open(self.black_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(['3.3.3.3']))

        with self._patch_paths(), patch.object(f2b, 'get_dbfile_path', return_value=db_path):
            res = json.loads(f2b.get_active_bans())

        self.assertTrue(res['status'])
        rows = res['data']
        ips = [r['ip'] for r in rows]

        # 过期记录必须被 SQL 条件下推过滤掉
        self.assertNotIn('2.2.2.2', ips)
        self.assertIn('1.1.1.1', ips)
        self.assertIn('3.3.3.3', ips)

        by_ip = {r['ip']: r for r in rows}
        self.assertTrue(by_ip['3.3.3.3']['manual'])
        self.assertFalse(by_ip['1.1.1.1']['manual'])
        # 永久封禁排在前面
        self.assertEqual(ips[0], '3.3.3.3')

    def test_get_active_bans_without_db_returns_error(self):
        with self._patch_paths(), \
             patch.object(f2b, 'get_dbfile_path', return_value=os.path.join(self.tmp, 'none.sqlite3')):
            res = json.loads(f2b.get_active_bans())
        self.assertFalse(res['status'])

    def test_apply_black_list_skips_when_empty(self):
        calls = []
        with self._patch_paths(), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, ''))[1]):
            self.assertTrue(f2b.apply_black_list())
        self.assertEqual(calls, [])

    def test_apply_black_list_reapplies_all_ips(self):
        with open(self.black_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(['1.1.1.1', '2.2.2.2']))

        calls = []
        with self._patch_paths(), \
             patch.object(f2b, 'status', return_value='start'), \
             patch.object(f2b, 'f2b_client_ok', side_effect=lambda *a: (calls.append(a), (True, ''))[1]):
            self.assertTrue(f2b.apply_black_list())

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ('set', f2b.MANUAL_JAIL, 'banip', '1.1.1.1 2.2.2.2'))


class TestLogParsing(unittest.TestCase):
    """日志结构化解析与高效尾读"""

    def test_parse_ban_line_plain(self):
        line = '2026-09-20 10:00:00,123 fail2ban.actions [123]: NOTICE  [sshd] Ban 1.1.1.1'
        rec = f2b.parse_ban_line(line)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['ip'], '1.1.1.1')
        self.assertEqual(rec['rule_name'], 'sshd')
        self.assertEqual(rec['reason_code'], f2b.REASON_MAP['sshd'])
        self.assertFalse(rec['restore'])

    def test_parse_ban_line_restore(self):
        line = '2026-09-20 10:00:00,123 fail2ban.actions [123]: NOTICE  [sshd] Restore Ban 1.1.1.1'
        rec = f2b.parse_ban_line(line)
        self.assertIsNotNone(rec)
        self.assertTrue(rec['restore'])
        self.assertEqual(rec['rule_name'], 'sshd')

    def test_parse_ban_line_cc_and_scan(self):
        cc = f2b.parse_ban_line(
            '2026-09-20 10:00:00,123 fail2ban.actions [1]: NOTICE  [global-cc] Ban 1.1.1.1')
        scan = f2b.parse_ban_line(
            '2026-09-20 10:00:00,123 fail2ban.actions [1]: NOTICE  [global-scan] Ban 1.1.1.1')
        self.assertIn('CC', cc['reason_code'])
        self.assertIn('扫描', scan['reason_code'])

    def test_parse_ban_line_manual_jail(self):
        rec = f2b.parse_ban_line(
            '2026-09-20 10:00:00,123 fail2ban.actions [1]: NOTICE  [%s] Ban 1.1.1.1' % f2b.MANUAL_JAIL)
        self.assertIn('永久封禁', rec['reason_code'])

    def test_parse_ban_line_ignores_non_ban_lines(self):
        self.assertIsNone(f2b.parse_ban_line('2026-09-20 10:00:00,123 fail2ban.actions [1]: NOTICE  [sshd] Unban 1.1.1.1'))
        self.assertIsNone(f2b.parse_ban_line(''))
        self.assertIsNone(f2b.parse_ban_line('garbage'))

    def test_read_tail_lines_ring_buffer(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, 'f.log')
            # 定长零填充，避免 'entry-42' 误匹配 'entry-420'
            with open(path, 'w', encoding='utf-8') as f:
                for i in range(1000):
                    f.write('entry-%04d\n' % i)

            # 无过滤 → 取最后 N 行
            tail = f2b.read_tail_lines(path, max_lines=10)
            self.assertEqual(len(tail), 10)
            self.assertEqual(tail[-1].strip(), 'entry-0999')

            # 关键字过滤（精确唯一命中）
            hits = f2b.read_tail_lines(path, max_lines=10, keywords=['entry-0042'])
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].strip(), 'entry-0042')

            # 正则过滤
            rx = re.compile(r'entry-0007$')
            hits2 = f2b.read_tail_lines(path, max_lines=10, matcher=rx)
            self.assertEqual(len(hits2), 1)
            self.assertEqual(hits2[0].strip(), 'entry-0007')

            # 文件不存在 → 空列表且不抛异常
            self.assertEqual(f2b.read_tail_lines(os.path.join(tmp, 'nope.log')), [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_candidates_includes_rotated(self):
        with patch.object(f2b, 'runLog', return_value='/var/log/fail2ban.log'):
            cands = f2b.log_candidates()
        self.assertEqual(cands[0], '/var/log/fail2ban.log')
        self.assertEqual(len(cands), 4)
        self.assertTrue(all(c.startswith('/var/log/fail2ban.log') for c in cands))


class TestI18nCoverage(unittest.TestCase):
    """六语种语言包完整性与前端翻译覆盖率"""

    def test_all_langs_exist_and_share_identical_keys(self):
        dicts = {name: load_lang(name) for name in LANGS}
        base = set(dicts['zh-CN'])
        self.assertGreater(len(base), 100, '语言包键数量异常偏少')
        for name in LANGS[1:]:
            with self.subTest(lang=name):
                self.assertEqual(set(dicts[name]), base,
                                 '%s 键集与 zh-CN 不一致：%s' % (name, set(dicts[name]) ^ base))

    def test_zh_cn_is_identity_baseline(self):
        zh = load_lang('zh-CN')
        for key, value in zh.items():
            with self.subTest(key=key):
                self.assertEqual(key, value, 'zh-CN 必须是 key == value 的基线')

    def test_no_html_in_translation_values(self):
        """硬约束：译文值中出现 HTML 会导致 web/core/i18n.py 抛错"""
        pattern = re.compile(r'<(?:br|div|span|p|a|b|i|script|style)\b|</', re.I)
        for name in LANGS:
            for key, value in load_lang(name).items():
                with self.subTest(lang=name, key=key):
                    self.assertIsNone(pattern.search(value),
                                      '%s 的 %s 译文含 HTML' % (name, key))

    def test_no_empty_values(self):
        for name in LANGS:
            for key, value in load_lang(name).items():
                with self.subTest(lang=name, key=key):
                    self.assertTrue(str(value).strip(), '%s 的 %s 译文为空' % (name, key))

    def test_every_pt_literal_has_translation(self):
        js = read_text(os.path.join(PLUGIN_DIR, 'js', 'fail2ban.js'))
        literals = set(re.findall(r"pt\(\s*'((?:[^'\\]|\\.)*)'", js))
        self.assertGreater(len(literals), 50, 'pt() 字面量数量异常偏少')
        base = load_lang('zh-CN')
        missing = sorted(x.replace("\\'", "'") for x in literals
                         if x.replace("\\'", "'") not in base)
        self.assertEqual(missing, [], '以下 pt() 键缺少 zh-CN 译文：%s' % missing)

    def test_menu_labels_are_translatable(self):
        """左侧菜单由 translatePluginDOM 依据中文原文查表，键必须存在"""
        html = read_text(os.path.join(PLUGIN_DIR, 'index.html'))
        for label in MENU_LABELS:
            with self.subTest(label=label):
                self.assertIn('>%s<' % label, html)
                for name in LANGS:
                    self.assertIn(label, load_lang(name),
                                  '%s 缺少菜单键 %s' % (name, label))

    def test_no_manual_lang_placeholder_fragments(self):
        """历史脏键回归：碎片化键会导致拼接错乱"""
        # 使用纯子串匹配，避免正则元字符（( ) ! 等）引发的转义问题
        forbidden = ['\\uFEFF', 'args dump', ')没有!', '参数:(', '次 /', 'IP不能为空!']
        base = load_lang('zh-CN')
        for key in base:
            for frag in forbidden:
                with self.subTest(key=key, frag=frag):
                    self.assertNotIn(frag, key, '残留脏键: %s' % key)

    def test_lang_files_are_valid_json(self):
        for name in LANGS:
            with self.subTest(lang=name):
                data = load_lang(name)
                self.assertIsInstance(data, dict)


class TestEncodingConvention(unittest.TestCase):
    """项目约定：UTF-8 无 BOM、LF 换行"""

    TARGETS = [
        'index.py', 'index.html', 'install.sh',
        'js/fail2ban.js',
        'init.d/fail2ban.init.tpl', 'init.d/fail2ban.service.tpl',
        'info.json',
    ]

    def _check(self, rel_path):
        path = os.path.join(PLUGIN_DIR, rel_path)
        with open(path, 'rb') as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), '%s 含 UTF-8 BOM' % rel_path)
        self.assertEqual(raw.count(b'\r\n'), 0, '%s 含 CRLF 换行' % rel_path)
        raw.decode('utf-8')  # 必须可解码为 UTF-8

    def test_plugin_sources_are_utf8_lf(self):
        for rel in self.TARGETS:
            with self.subTest(file=rel):
                self._check(rel)

    def test_lang_files_are_utf8_lf(self):
        for name in LANGS:
            with self.subTest(lang=name):
                self._check(os.path.join('lang', name + '.json'))


class TestInstallScript(unittest.TestCase):
    """install.sh 加固：语法、依赖、卸载保留用户自定义配置"""

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(PLUGIN_DIR, 'install.sh')
        cls.content = read_text(cls.path)

    def test_bash_syntax_is_valid(self):
        bash = find_posix_bash()
        if not bash:
            self.skipTest('未找到可用的 POSIX shell（Windows 上的 bash 可能指向 WSL 启动器）')
        proc = subprocess.run([bash, '-n', self.path],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         'bash -n 失败: %s' % (proc.stderr or proc.stdout))

    def test_verifies_installation_before_reporting_success(self):
        self.assertIn('verify_install', self.content)
        self.assertIn('fail2ban-client', self.content)
        install_body = self.content.split('Install_App()')[1].split('Uninstall_App()')[0]
        self.assertIn('verify_install', install_body)
        self.assertIn('die', install_body)

    def test_installs_runtime_dependencies(self):
        for dep in ['iptables', 'ipset', 'fail2ban']:
            with self.subTest(dep=dep):
                self.assertIn(dep, self.content)

    def test_no_dead_yum_purge_line(self):
        self.assertNotIn('yum purge', self.content)

    def test_supports_dnf(self):
        self.assertIn('dnf', self.content)

    def test_uninstall_backs_up_before_purging(self):
        self.assertIn('backup_etc', self.content)
        body = self.content.split('Uninstall_App()')[1]
        self.assertLess(body.index('backup_etc'), body.index('remove_pkg'),
                        '必须先备份 /etc/fail2ban 再卸载软件包')
        self.assertLess(body.index('remove_pkg'), body.index('preserve_or_remove_etc'))

    def test_does_not_blindly_delete_etc_fail2ban(self):
        # rm -rf /etc/fail2ban 只允许出现一次，且必须位于有 find 守卫的函数内
        self.assertEqual(self.content.count('rm -rf /etc/fail2ban'), 1)
        self.assertIn('find /etc/fail2ban -type f -print -quit', self.content)
        guard = self.content.split('preserve_or_remove_etc()')[1].split('Uninstall_App()')[0]
        self.assertIn('rm -rf /etc/fail2ban', guard)

    def test_cleans_up_leftovers(self):
        for leftover in ['/var/lib/fail2ban', '/run/fail2ban',
                         '/var/log/fail2ban.log', 'fail2ban-manual.log']:
            with self.subTest(leftover=leftover):
                self.assertIn(leftover, self.content)

    def test_action_dispatch_is_whitelisted(self):
        self.assertIn('install)', self.content)
        self.assertIn('uninstall)', self.content)
        self.assertIn('case "$action" in', self.content)

    def test_uses_pipefail(self):
        self.assertIn('set -o pipefail', self.content)


class TestPluginManifest(unittest.TestCase):
    """info.json 与面板加载约定"""

    @classmethod
    def setUpClass(cls):
        cls.info = json.loads(read_text(os.path.join(PLUGIN_DIR, 'info.json')))

    def test_required_fields(self):
        for key in ['name', 'title', 'shell', 'versions', 'checks', 'path']:
            self.assertIn(key, self.info)
        self.assertEqual(self.info['name'], 'fail2ban')
        self.assertEqual(self.info['shell'], 'install.sh')

    def test_versions_non_empty_list(self):
        self.assertIsInstance(self.info['versions'], list)
        self.assertTrue(self.info['versions'])

    def test_path_aligns_with_server_dir(self):
        self.assertEqual(self.info['path'], 'server/fail2ban')
        self.assertEqual(self.info['checks'], 'server/fail2ban')


class TestPopupLayout(unittest.TestCase):
    """
    弹窗高度与滚动条回归。

    历史 Bug：`.soft-man-con` 内联固定 height:520px，而 `.bt-w-con` 的内容盒只有
    578 - 60(内边距) = 518px，恒溢出 2px → 外层滚动条；英/德/法/意文案更长时又撑破
    520px → 内层滚动条。最终在非中文界面下同时出现内外两条滚动条。
    """

    @classmethod
    def setUpClass(cls):
        cls.html = read_text(os.path.join(PLUGIN_DIR, 'index.html'))

    def test_soft_man_con_has_no_inline_fixed_height(self):
        m = re.search(r'<div[^>]*class="soft-man-con"[^>]*>', self.html)
        self.assertIsNotNone(m, '未找到 .soft-man-con 容器')
        tag = m.group(0)
        self.assertNotIn('height', tag,
                         '内容区不得内联固定高度，否则会与外层滚动条叠加')
        self.assertNotIn('overflow', tag,
                         '内容区滚动应交给外层 .bt-w-con 统一处理')

    def test_css_forces_natural_height_on_content_area(self):
        # 必须存在一条针对 .bt-w-con > .soft-man-con 的 height:auto 规则
        block = re.search(
            r'\.bt-w-con\s*>\s*\.soft-man-con\s*\{([^}]*)\}', self.html, re.S)
        self.assertIsNotNone(block, '缺少 .bt-w-con > .soft-man-con 高度覆盖规则')
        self.assertIn('height: auto', block.group(1))

    def test_outer_container_remains_single_scroller(self):
        block = re.search(r'\.bt-w-con\s*\{([^}]*)\}', self.html, re.S)
        self.assertIsNotNone(block)
        css = block.group(1)
        self.assertIn('overflow-y: auto', css, '纵向滚动应由外层容器唯一承担')
        self.assertIn('box-sizing: border-box', css,
                      '必须 border-box，否则内边距会撑破高度预算')

    def test_popup_height_is_viewport_adaptive_with_floor(self):
        # 不再是硬编码的 resetPluginWinHeight(620)
        self.assertNotRegex(
            self.html, r'resetPluginWinHeight\(\s*620\s*\)\s*;',
            '弹窗高度不应再硬编码为 620')
        self.assertRegex(self.html, r'resetPluginWinHeight\(\s*h\s*\)',
                         '弹窗高度应使用自适应变量')
        # 下限不得低于原先的 620
        floor = re.search(r'Math\.max\(\s*(\d+)\s*,', self.html)
        self.assertIsNotNone(floor, '缺少高度下限保护')
        self.assertGreaterEqual(int(floor.group(1)), 620,
                                '自适应高度下限不得小于原值 620')
        # 上限存在，避免超大屏过度拉伸
        self.assertRegex(self.html, r'Math\.min\(\s*\d+\s*,', '缺少高度上限保护')

    def test_inline_script_is_syntactically_valid(self):
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', self.html, re.S)
        self.assertTrue(scripts, 'index.html 应包含内联脚本')
        import shutil
        node = shutil.which('node')
        if not node:
            self.skipTest('未找到 node，跳过内联脚本语法校验')
        import tempfile
        for idx, code in enumerate(scripts):
            fd, path = tempfile.mkstemp(suffix='.js')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(code)
                proc = subprocess.run([node, '--check', path],
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0,
                                 '内联脚本语法错误: %s' % (proc.stderr or proc.stdout))
            finally:
                os.remove(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
