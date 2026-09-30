# coding: utf-8
"""A05 crontab 模块回归守卫（真机功能测试轮：crontab 注入 / 500 / cron 被打停）。

本轮在 Debian 真机上把计划任务的六类路径跑通，暴露并修掉以下缺陷：

1. **任意 root 计划任务注入（P0）**：`minute/hour/where1/week` 直接拼进
   `/var/spool/cron/crontabs/root` 的一行。实测
   `minute="\n* * * * * /bin/touch /tmp/x #"` → HTTP 200 且 **60 秒内真的以 root 建了文件**。
2. **整份 root crontab 被写成语法错误（P0）**：`minute=-1/999/abc`、`hour=99`、
   `type=evil`（不生成时间字段）都被接受，cron 日志报
   `bad minute/bad hour` + `(root) ERROR (Syntax error, this crontab file will be ignored)`
   → 生产上所有 root 计划任务（含 acme.sh 续期）静默全部停摆。
3. **生成的 root 脚本命令注入（P0）**：`sname`/`save` 未转义拼进脚本，
   实测脚本里出现 `backup.py site ALL; /bin/touch /tmp/yf_A05_sname_inj # 3 <echo>`；
   `backup_to=../../../../tmp` 还能把执行路径穿出 plugins 目录。
4. **cron 被面板打成 start-limit-hit（P0）**：`crondReload()` 用 `service cron restart`，
   systemd 对同一 unit 的 start 有速率限制（5 次/10 秒）→ 连续加/改几个任务就把
   `cron.service` 打成 failed 且不再启动，而面板每条都返回“成功”。
5. **失败/非法入参一律 500（P1）**：`del/logs/set_cron_status/start_task/get_crond_find/
   modify_crond` 传不存在的 id、`list?p=abc`、`list?limit=abc` 全部 500。
6. **存储型 XSS（P1）**：任务名 `<img src=x onerror=alert(1)>` 原样拼进列表 HTML；
   任务日志（脚本输出，用户可控）用 `.html()` 渲染。
7. **N 分钟「执行时段限制」被丢弃（P2）**：路由没读 `min_start_*`/`min_end_*`，
   实测保存后 DB 里恒为默认值 0/0/0/0/23/59。
8. **ORDER BY 注入面（P2）**：`orderby` 直接拼进 SQL（无法参数化，只能白名单），
   实测 `orderby=(SELECT 1)` 被当表达式执行。
9. **删除任务残留 PID 文件（P2）**：实测 `/www/server/yufeng_panel/tmp/cron_27.pid`。

断言分两层：能纯逻辑跑的（`cronCheck`/`_valid_cron_line`）用 **AST 抽取真实源码 +
stub 命名空间** 执行；路由/DB/前端接入用 AST 与源码结构断言，避免被注释或 `if False:` 蒙混。
"""
import ast
import json
import logging
import multiprocessing
import os
import re
import sys
import threading
import time
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

CRONTAB_PY = 'web/utils/crontab.py'
ROUTE_PY = 'web/admin/crontab/__init__.py'
THISDB_PY = 'web/thisdb/crontab.py'
CRONTAB_JS = 'web/static/app/crontab.js'

INJECT_MINUTE = '\n* * * * * /bin/touch /tmp/yf_A05_pwned #'


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


def _func_src(rel, name, cls=None):
    """取函数源码（按 AST 行号切片，注释/字符串不影响定位）。"""
    src = _read(rel)
    tree = ast.parse(src)
    body = tree.body
    if cls:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                body = node.body
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s（%s）' % (name, rel))


def _code_only(text):
    """剥掉注释与字符串字面量后的小写源码，用来防止「注释里写旧代码」蒙混断言。"""
    out = []
    for line in text.splitlines():
        line = re.sub(r'#.*$', '', line)
        line = re.sub(r'(""".*?"""|\'\'\'.*?\'\'\')', '', line)
        out.append(line)
    return '\n'.join(out)


class TestCronCheckValidation(unittest.TestCase):
    """cronCheck / _valid_cron_line：真实源码 + stub 命名空间执行。"""

    @classmethod
    def setUpClass(cls):
        src = _read(CRONTAB_PY)
        tree = ast.parse(src)
        want_assign = {'_CRON_INT_RE', '_CRON_LINE_FIELD_RE', '_PLUGIN_DIR_NAME_RE',
                       'CRON_CYCLE_TYPES', 'CRON_TASK_STYPES'}
        want_func = {'_cron_int', '_valid_cron_line', '_validate_to_url', '_is_private_url'}
        keep = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', '') in want_assign for t in node.targets):
                keep.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in want_func:
                keep.append(node)
            elif isinstance(node, ast.ClassDef) and node.name == 'crontab':
                keep.append(node)

        class _FakeYf:
            @staticmethod
            def returnData(status, msg, data=None, *args):
                return {'status': status, 'msg': msg, 'data': data}

            @staticmethod
            def shlexQuote(s):
                import shlex
                return shlex.quote(str(s))

        ns = {'os': os, 're': re, 'time': time, 'json': json, 'threading': threading,
              'multiprocessing': multiprocessing, '_log': logging.getLogger('cron-a05-test'),
              'yf': _FakeYf, 'thisdb': object(),
              '_t': lambda key, *a: key}
        exec(compile(ast.Module(body=keep, type_ignores=[]), CRONTAB_PY, 'exec'), ns)
        cls.obj = ns['crontab']()
        cls.valid_line = staticmethod(ns['_valid_cron_line'])

    @staticmethod
    def base(**over):
        data = {'name': 'yftest_A05_x', 'type': 'day', 'week': '', 'where1': '',
                'hour': '1', 'minute': '30', 'save': '', 'backup_to': 'localhost',
                'stype': 'toShell', 'sname': '', 'sbody': 'echo x', 'url_address': '',
                'attr': '', 'day_type': '0', 'min_start_en': '0', 'min_start_h': '0',
                'min_start_m': '0', 'min_end_en': '0', 'min_end_h': '23', 'min_end_m': '59'}
        data.update(over)
        return data

    def assertRejected(self, **over):
        ok, msg = self.obj.cronCheck(self.base(**over))
        self.assertFalse(ok, '本应拒绝却放行：%r → %s' % (over, msg))
        return msg

    def assertAccepted(self, **over):
        ok, msg = self.obj.cronCheck(self.base(**over))
        self.assertTrue(ok, '合法配置被误拒：%r → %s' % (over, msg))

    # ---- 1. 换行注入（真机实测可执行） ----
    def test_01_minute_newline_injection_rejected(self):
        self.assertRejected(minute=INJECT_MINUTE)

    def test_02_hour_newline_injection_rejected(self):
        self.assertRejected(hour='1\n* * * * * /bin/touch /tmp/x #')

    def test_03_where1_newline_injection_rejected(self):
        self.assertRejected(type='day-n', where1='1\n* * * * * /bin/touch /tmp/x #')
        self.assertRejected(type='minute-n', where1='5\n* * * * * /bin/touch /tmp/x #')

    def test_04_week_newline_injection_rejected(self):
        self.assertRejected(type='week', week='1\n* * * * * /bin/touch /tmp/x #',
                            where1='1\n* * * * * /bin/touch /tmp/x #')

    def test_05_minute_n_range_fields_rejected(self):
        self.assertRejected(type='minute-n', where1='10', minute='',
                            min_start_h='9; /bin/touch /tmp/x')
        self.assertRejected(type='minute-n', where1='10', minute='', min_end_m='abc')
        self.assertRejected(type='minute-n', where1='10', minute='', min_start_en='2')

    # ---- 2. 越界 / 非数字 ----
    def test_06_out_of_range_and_non_numeric_rejected(self):
        for over in ({'minute': '-1'}, {'minute': '999'}, {'minute': 'abc'},
                     {'minute': '30.5'}, {'minute': ''}, {'hour': '99'}, {'hour': '-1'},
                     {'hour': 'x'}, {'type': 'day-n', 'where1': '0'},
                     {'type': 'day-n', 'where1': '32'}, {'type': 'month', 'where1': '99'},
                     {'type': 'minute-n', 'where1': '60', 'minute': ''},
                     {'type': 'week', 'week': '7', 'where1': '7'}):
            self.assertRejected(**over)

    # ---- 3. type / stype / save / backup_to ----
    def test_07_unknown_type_rejected(self):
        self.assertRejected(type='evil')
        self.assertRejected(type='')

    def test_08_unknown_stype_and_traversal_rejected(self):
        self.assertRejected(stype='evil')
        self.assertRejected(stype='database_../../../../tmp')
        self.assertRejected(stype='database_x;id')

    def test_09_save_and_backup_to_injection_rejected(self):
        self.assertRejected(stype='site', save='1; /bin/touch /tmp/x #')
        self.assertRejected(stype='site', save='21abc')
        self.assertRejected(stype='site', save='1', backup_to='../../../../tmp')
        self.assertRejected(stype='site', save='1', backup_to='a/b')

    # ---- 4. 合法配置必须照样通过（防误伤） ----
    def test_10_legit_configs_accepted(self):
        self.assertAccepted(type='day', hour='0', minute='0', stype='toShell')
        self.assertAccepted(type='day-n', hour='23', minute='59', where1='3')
        self.assertAccepted(type='hour', hour='', minute='15', where1='')
        self.assertAccepted(type='hour-n', hour='', minute='15', where1='6')
        self.assertAccepted(type='minute-n', hour='', minute='', where1='10',
                            min_start_en='1', min_start_h='9', min_start_m='15',
                            min_end_en='1', min_end_h='18', min_end_m='45')
        self.assertAccepted(type='week', week='0', where1='0', hour='2', minute='5')
        self.assertAccepted(type='week', week='6', where1='6', hour='2', minute='5')
        self.assertAccepted(type='month', where1='31', hour='2', minute='5')
        self.assertAccepted(stype='site', sname='ALL', save='3')
        self.assertAccepted(stype='database_mysql', sname='cc2', save='5')
        self.assertAccepted(stype='database_mysql-apt', sname='cc2', save='5')
        self.assertAccepted(stype='logs', sname='site.log', save='7')
        self.assertAccepted(stype='path', sname='/www/wwwroot', save='1')
        self.assertAccepted(stype='rememory')
        self.assertAccepted(stype='toShell', sbody='echo hi')

    # ---- 5. 落盘前的整行闸门 ----
    def test_11_valid_cron_line_guard(self):
        good = ('5 2 * * *  /www/server/cron/245532c3bab7100b7a20cb6134c2f8f2 '
                '>> /www/server/cron/245532c3bab7100b7a20cb6134c2f8f2.log 2>&1')
        self.assertTrue(self.valid_line(good))
        self.assertTrue(self.valid_line('15 4 */15 * *  /www/server/cron/x >> /www/server/cron/x.log 2>&1'))
        for bad in ('', '0', ' /www/server/cron/x >> /www/server/cron/x.log 2>&1',
                    good + '\n* * * * * /bin/touch /tmp/x',
                    'abc 1 * * *  /www/server/cron/x >> /www/server/cron/x.log 2>&1'):
            self.assertFalse(self.valid_line(bad), '非法行被放行：%r' % bad)


class TestRouteAndDbGuards(unittest.TestCase):
    """路由 / thisdb / 前端接入的结构断言。"""

    def test_20_route_list_tolerates_bad_paging(self):
        src = _code_only(_func_src(ROUTE_PY, 'list'))
        self.assertIn('try:', src, '分页参数必须有容错转换，否则 ?p=abc 直接 500')
        self.assertIn('except (TypeError, ValueError):', src)
        self.assertRegex(src, r'min\(max\(.*?1\), 1000\)', 'limit 必须有上下界')
        self.assertNotIn('page=int(page)', src)

    def test_21_route_handles_missing_cron(self):
        src = _code_only(_func_src(ROUTE_PY, 'get_crond_find'))
        self.assertIn('is None', src, '任务不存在时不能把 None 当响应返回（Flask 500）')
        self.assertIn('common.param_error', src)

    def test_22_route_passes_minute_n_range_fields(self):
        for fn in ('add', 'modify_crond'):
            src = _code_only(_func_src(ROUTE_PY, fn))
            for key in ('min_start_en', 'min_start_h', 'min_start_m',
                        'min_end_en', 'min_end_h', 'min_end_m'):
                self.assertIn("'%s'" % key, src,
                              '%s 必须带上 %s，否则「N分钟执行时段」保存后丢失' % (fn, key))
            self.assertIn('request.form.get(_k, _d)', src)

    def test_23_class_guards_missing_task(self):
        for fn in ('delete', 'cronLog', 'setCronStatus', 'startTask', 'modifyCrond', 'delLogs'):
            src = _code_only(_func_src(CRONTAB_PY, fn, cls='crontab'))
            self.assertIn('is None', src, '%s 必须先判空，否则不存在 id → 500' % fn)
            self.assertIn('common.param_error', src)

    def test_24_crond_reload_never_restarts(self):
        src = _code_only(_func_src(CRONTAB_PY, 'crondReload', cls='crontab'))
        self.assertNotIn('cron restart', src,
                         'restart 会被 systemd 的 start 速率限制打成 start-limit-hit，把 cron 停掉')
        self.assertNotIn('cron.service', src)
        self.assertIn("/etc/init.d/cron reload", src)
        self.assertIn("/etc/init.d/crond reload", src)

    def test_25_sync_guards_illegal_line(self):
        src = _code_only(_func_src(CRONTAB_PY, 'syncToCrond', cls='crontab'))
        self.assertIn('_valid_cron_line(cmd)', src, '写盘前必须校验整行')
        self.assertIn('return False', src)

    def test_26_generated_script_shlex_quotes_user_values(self):
        src = _code_only(_func_src(CRONTAB_PY, 'getShell', cls='crontab'))
        self.assertIn('shlexQuote', src, 'sname/save/echo 必须转义后再拼进 root 脚本')
        for leak in ("param['sname'] + \" \"", "str(param['save'])", "str(param['echo'])"):
            self.assertNotIn(leak, src, '仍有未转义拼接：%s' % leak)

    def test_27_delete_cleans_pid_file(self):
        src = _code_only(_func_src(CRONTAB_PY, 'delete', cls='crontab'))
        self.assertIn('_cron_pid_file(tid)', src)
        self.assertIn('os.remove(pid_file)', src)

    def test_28_thisdb_order_by_whitelist(self):
        src = _func_src(THISDB_PY, 'getCrontabList')
        self.assertIn('__order_fields', src, 'ORDER BY 只能白名单')
        self.assertIn("('asc', 'desc')", src)
        tree = ast.parse(src)
        guards = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Compare) and isinstance(n.ops[0], (ast.In, ast.NotIn))]
        self.assertTrue(guards, 'orderby/order 必须有白名单比较')
        self.assertNotIn('str(page) + str(size)', src)

    def test_29_js_escapes_task_name_and_logs(self):
        src = _read(CRONTAB_JS)
        self.assertIn("title='\" + cronEsc(rdata.data[i].name)", src,
                      '任务名必须转义后再拼进列表 HTML（存储型 XSS）')
        self.assertIn('textContent = rdata.msg', src, '任务日志必须当纯文本渲染')
        self.assertNotIn('$("#crontab_log").html(rdata.msg)', src)
        self.assertIn('function cronEsc(', src)
        self.assertIn('function cronEscJs(', src)


if __name__ == '__main__':
    unittest.main()
