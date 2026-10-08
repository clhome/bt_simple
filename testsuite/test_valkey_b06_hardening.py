# coding: utf-8
"""B06 valkey 插件加固守卫（与 plugins/redis/ 同族漂移逐条核对后，按同口径修复并锁死）。

真机（Debian12，valkey 未安装 -> 夹具 + 静态口径，夹具 `/www/server/valkey`）确认：

1. `getRedisCmd()` 拼的是 **shell 字符串**，四个读接口又把它交给 `yf.execShell`：
   port/requirepass 全部来自 valkey.conf，而 `submit_redis_conf` 可写该文件 ——
   真机夹具实测 conf 里 `port 6389 & touch yftest_b06_rce` 会让 `& touch …`
   以 root 身份执行（命令注入，与 B05 的 redis RCE 同族）。
2. `submitRedisConf` 对参数**零校验**：真机夹具实测 `bind="127.0.0.1\\nport 1"`
   回「设置成功」且 `port 1` 被写进 valkey.conf（换行注入）；`port=70000` 同样写入。
3. `submitRedisConf` 不看 `writeFile` 结果、也不看重启结果，永远回「设置成功」。
4. `submitRedisConf` 的无锚点正则会改写**其他行**里的同名片段：真机夹具实测
   密码清空两次得到 `#requirepass ""` -> `##requirepass ""`，同值重提每次都漂字节。
5. `infoReplication`：INFO 只有 `role:master` 而无 `connected_slaves` 时
   `int(result['connected_slaves'])` 抛 KeyError；从库行 `split(':')` 会截断 IPv6 值。
6. `readConfigTpl`：`file` 无任何路径白名单（任意文件读取）+ 传目录时
   `contentReplace(False)` 抛 AttributeError。
7. `clusterNodes`：空应答 `strip().split('\\n')` -> `['']`，前端渲染一行假数据。
8. `getArgs` 从 `argv[3:]` 起读且只认 `k:v`：真实调用形态
   `index.py <func> [version] <args-json>` 下参数被跳过/切碎 -> 提交配置静默失效。
9. `status`：只看 pid 文件**是否存在** -> 陈旧 pid 文件让面板永远显示「运行中」。
10. `start`/`restart`：systemctl 返回成功就 return ok，不做就绪校验（假成功）。
11. `initdStatus`：`systemctl status … | grep enabled;` 依赖会被本地化的人类可读输出。

断言口径（防「假绿」）：AST 为主（`_live_nodes` 过滤 `if False:` 等静态死分支，
注释天然不参与），能取出的函数一律真跑行为（真正则、真回滚、真字节比对）。
"""
import ast
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'valkey', 'index.py')
LANG_DIR = os.path.join(ROOT, 'plugins', 'valkey', 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

# 本次新增/变动的后端消息键（6 语言必须齐备，否则外语界面回落成中文原文）
NEW_KEYS = ('配置文件写入失败！', 'Valkey 重启失败，配置已回滚！',
            '越界访问被拒绝！', '模板文件不存在',
            '未能读取到有效的 Valkey 状态数据:', '参数 [', '密码参数 [')

CONF_TPL = '''daemonize yes
pidfile {$SERVER_PATH}/valkey/valkey.pid

bind 127.0.0.1
port 6389
requirepass {$VALKEY_PASS}

timeout 3
maxclients 10000
databases 16
maxmemory 218mb
'''


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _parse(path):
    return ast.parse(_read(path))


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_const_false(test):
    return isinstance(test, ast.Constant) and not test.value


def _live_nodes(node):
    """产出「可达」AST 节点，跳过 `if False:` / `while False:` 等静态死分支。"""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.If):
            if not _is_const_false(n.test):
                stack.append(n.test)
                stack.extend(n.body)
            stack.extend(n.orelse)
            continue
        if isinstance(n, ast.While) and _is_const_false(n.test):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _calls(node, name):
    out = []
    for n in _live_nodes(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == name:
            out.append(n)
        elif isinstance(f, ast.Attribute) and f.attr == name:
            out.append(n)
    return out


def _string_consts(node):
    """函数体内字面量串（**排除 docstring**：文档里会引用历史缺陷的正则/消息）。"""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    out = []
    for stmt in body:
        out += [n.value for n in _live_nodes(stmt)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return out


class _Log(object):
    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


class _Time(object):
    """time 替身：就绪轮询不必真的睡 5 秒。"""

    def sleep(self, sec):
        pass

    def strftime(self, *a):
        return '2026-01-01 00:00:00'


class _YfStub(object):
    """只提供被测函数真正用到的那几个 yf 原语。"""

    def __init__(self, write_ok=True, server_dir=None, shell_out=None):
        self.write_ok = write_ok
        self.server_dir = server_dir
        self.shell_out = shell_out if shell_out is not None else ''
        self.shell_calls = []
        self.shell_rc_calls = []
        self.writes = []

    def readFile(self, path):
        try:
            with io.open(path, encoding='utf-8') as fh:
                return fh.read()
        except Exception:
            return False

    def writeFile(self, path, content, mode='w+'):
        self.writes.append((path, content))
        if not self.write_ok:
            return False
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        return True

    def returnJson(self, status, msg, data=None):
        return json.dumps({'status': status, 'msg': msg, 'data': data})

    def getJson(self, data):
        return json.dumps(data)

    def execShell(self, cmd, *a, **kw):
        self.shell_calls.append({'cmd': cmd, 'kwargs': kw})
        return (self.shell_out, '')

    def execShellRc(self, argv, *a, **kw):
        self.shell_rc_calls.append({'argv': argv, 'kwargs': kw})
        return (0, self.shell_out, '')

    def getOs(self):
        return 'linux'

    def isAppleSystem(self):
        return False

    def getServerDir(self):
        return self.server_dir

    def getPluginDir(self):
        return os.path.join(ROOT, 'plugins')

    def getFatherDir(self):
        return ROOT

    def checkPid(self, pid):
        return False


class ValkeyB06HardeningTest(unittest.TestCase):

    def setUp(self):
        self.src = _read(IDX)
        self.tree = _parse(IDX)
        self.tmp = tempfile.mkdtemp(prefix='valkey_b06_guard_')
        self.conf = os.path.join(self.tmp, 'valkey.conf')
        self.server_dir = os.path.join(self.tmp, 'server')
        os.makedirs(os.path.join(self.server_dir, 'valkey', 'data'), exist_ok=True)
        self.real_conf = os.path.join(self.server_dir, 'valkey', 'valkey.conf')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    def _exec(self, names, extra=None):
        """把真实函数体取出来在受控命名空间里执行（真跑行为，不是文本匹配）。"""
        ns = {'os': os, 're': re, 'json': json, '_log': _Log(),
              'sys': sys, 'time': _Time()}
        if extra:
            ns.update(extra)
        src = '\n\n'.join(ast.get_source_segment(self.src, self._fn(n)) for n in names)
        exec(compile(src, '<valkey-extract>', 'exec'), ns)
        return ns

    def _conf_info(self, port='6389', passwd=''):
        items = [{'name': 'bind', 'value': '127.0.0.1'},
                 {'name': 'port', 'value': port}]
        if passwd:
            items.append({'name': 'requirepass', 'value': passwd})
        return items

    def _write_conf(self):
        content = CONF_TPL.replace('{$SERVER_PATH}', self.server_dir)
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        return content

    # ---- 1. getRedisCmd 必须返回 argv 列表，密码/端口原样进列表 ------------
    def test_01_get_redis_cmd_returns_argv_list(self):
        nasty = 'My"Complex$Pass`2026'
        yfstub = _YfStub()
        ns = self._exec(['getRedisCmd'], {
            'yf': yfstub,
            'getRedisConfInfo': lambda: self._conf_info('6389', nasty),
            'getServerDir': lambda: os.path.join(self.tmp, 'valkey'),
        })
        argv = ns['getRedisCmd']()
        self.assertIsInstance(argv, list, 'getRedisCmd 必须返回参数列表（字符串形态必然要经过 shell）')
        self.assertEqual(argv[argv.index('-p') + 1], '6389')
        self.assertEqual(argv[argv.index('-a') + 1], nasty,
                         '密码必须原样进入 argv（含 " / $ / 反引号），不做 shell 转义')
        self.assertIn('--no-auth-warning', argv)
        self.assertTrue(argv[0].endswith('valkey-cli'), '必须调用 valkey-cli，不能借用 redis-cli')
        self.assertEqual([a for a in argv if a.startswith('"') or a.endswith('"')], [],
                         '列表传参下任何参数都不得再被 shell 引号包裹')

    # ---- 2. 读接口绝不允许再用 shell 字符串 --------------------------------
    def test_02_readers_never_use_shell_string(self):
        for name in ('valkeyCli', 'runInfo', 'infoReplication', 'clusterInfo', 'clusterNodes'):
            fn = self._fn(name)
            self.assertEqual(_calls(fn, 'execShell'), [],
                             '%s 不得调用 yf.execShell(字符串) —— 那正是 root 命令注入点' % name)
        rc_calls = _calls(self._fn('valkeyCli'), 'execShellRc')
        self.assertTrue(rc_calls, 'valkeyCli 必须用 yf.execShellRc 执行 valkey-cli')
        for c in rc_calls:
            kws = {k.arg: k.value for k in c.keywords}
            self.assertIn('shell', kws, 'execShellRc 必须显式 shell=False')
            self.assertIsInstance(kws['shell'], ast.Constant)
            self.assertFalse(kws['shell'].value, 'execShellRc 必须 shell=False（命令内容不进 shell）')
            self.assertIn('timeout', kws, 'valkey-cli 调用必须有超时，否则会挂死面板线程')

    # ---- 3. 真跑：conf 里的注入载荷只能成为独立 argv 元素 -------------------
    def test_03_conf_payload_stays_single_argv_element(self):
        payload = '6389 & touch yftest_b06_guard_pwn'
        yfstub = _YfStub()
        ns = self._exec(['getRedisCmd', 'valkeyCli'], {
            'yf': yfstub,
            'getRedisConfInfo': lambda: self._conf_info(payload),
            'getServerDir': lambda: os.path.join(self.tmp, 'valkey'),
        })
        ns['valkeyCli']('info')
        self.assertEqual(len(yfstub.shell_rc_calls), 1)
        call = yfstub.shell_rc_calls[0]
        self.assertFalse(call['kwargs'].get('shell', True), 'valkey-cli 必须以 shell=False 执行')
        argv = call['argv']
        self.assertEqual(argv[argv.index('-p') + 1], payload,
                         '端口载荷必须整体成为独立 argv 元素（shell 无法把它当命令分隔符）')
        self.assertEqual(argv[-1], 'info')
        self.assertEqual(yfstub.shell_calls, [], '绝不能有字符串形态的 shell 调用')

    # ---- 4. submitRedisConf：bind/slaveof/密码必须拒绝换行注入 -------------
    def test_04_submit_conf_rejects_newline_injection(self):
        fn = self._fn('submitRedisConf')
        for pat in [s for s in _string_consts(fn) if 'a-zA-Z0-9_' in s and '[' in s]:
            self.assertNotIn(r'\s', pat,
                             'bind/slaveof 白名单不得用 \\s（换行会被配置解析器当新指令）: %r' % pat)

        original = self._write_conf()
        for key, payload in (('bind', '127.0.0.1\nport 1'),
                             ('slaveof', '127.0.0.1:6379\nport 1'),
                             ('requirepass', 'abc\nport 1'),
                             ('masterauth', 'abc\rport 1')):
            yfstub = _YfStub()
            ns = self._exec(['submitRedisConf'], {
                'yf': yfstub,
                'getArgs': lambda k=key, v=payload: {k: v},
                'getConf': lambda: self.conf,
                'status': lambda: 'stop',
                'restart': lambda: 'ok',
            })
            res = json.loads(ns['submitRedisConf']())
            self.assertFalse(res['status'], '%s 含换行必须被拒绝' % key)
            self.assertEqual(yfstub.writes, [], '被拒绝的请求绝不落盘')
            self.assertEqual(_read(self.conf), original, '被拒绝的请求绝不允许改动 valkey.conf')

        # 合法值（IPv4 + 空格分隔 + IPv6 + 逗号 / 常见密码符号）必须放行
        yfstub2 = _YfStub()
        ns2 = self._exec(['submitRedisConf'], {
            'yf': yfstub2,
            'getArgs': lambda: {'bind': '127.0.0.1 -::1,::1', 'requirepass': 'aB3#x_y'},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns2['submitRedisConf']())['status'], '合法值不得被误拒')

    # ---- 5. submitRedisConf：数字项与端口范围校验 --------------------------
    def test_05_submit_conf_port_range_and_numeric(self):
        original = self._write_conf()
        for bad in ('0', '65536', '99999', 'abc', '-1', '6389;touch x'):
            yfstub = _YfStub()
            ns = self._exec(['submitRedisConf'], {
                'yf': yfstub,
                'getArgs': lambda b=bad: {'port': b},
                'getConf': lambda: self.conf,
                'status': lambda: 'stop',
                'restart': lambda: 'ok',
            })
            res = json.loads(ns['submitRedisConf']())
            self.assertFalse(res['status'], '端口 %r 必须被拒绝' % bad)
            self.assertEqual(yfstub.writes, [], '被拒绝的端口不得落盘')
            self.assertEqual(_read(self.conf), original)
        for key in ('timeout', 'maxclients', 'databases', 'maxmemory'):
            yfstub = _YfStub()
            ns = self._exec(['submitRedisConf'], {
                'yf': yfstub,
                'getArgs': lambda k=key: {k: '1gb'},
                'getConf': lambda: self.conf,
                'status': lambda: 'stop',
                'restart': lambda: 'ok',
            })
            self.assertFalse(json.loads(ns['submitRedisConf']())['status'],
                             '%s 必须只接受纯数字' % key)

    # ---- 6. submitRedisConf：重启失败必须回滚 + 如实报错（不许假成功） -----
    def test_06_submit_conf_rollback_on_restart_failure(self):
        original = self._write_conf()
        yfstub = _YfStub()
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'port': '70000'.replace('70000', '9999')},
            'getConf': lambda: self.conf,
            'status': lambda: 'start',
            'restart': lambda: '重启失败，服务未能重新拉起',
        })
        res = json.loads(ns['submitRedisConf']())
        self.assertFalse(res['status'], '重启失败却回「设置成功」就是假成功')
        self.assertIn('回滚', res['msg'])
        self.assertEqual(_read(self.conf), original, '重启失败必须把 valkey.conf 整份回滚')

    # ---- 7. submitRedisConf：落盘失败必须如实报错 --------------------------
    def test_07_submit_conf_write_failure_is_honest(self):
        original = self._write_conf()
        yfstub = _YfStub(write_ok=False)
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'port': '6390'},
            'getConf': lambda: self.conf,
            'status': lambda: 'start',
            'restart': lambda: 'ok',
        })
        res = json.loads(ns['submitRedisConf']())
        self.assertFalse(res['status'], '写盘失败不得回「设置成功」')
        self.assertIn('写入失败', res['msg'])
        self.assertEqual(_read(self.conf), original, '写盘失败时原配置必须保持不动')

    # ---- 8. 原值重提必须零触碰（含密码清空两次） ---------------------------
    def test_08_submit_conf_same_value_keeps_file_byte_identical(self):
        self._write_conf()
        args = {'bind': '127.0.0.1', 'port': '6389', 'timeout': '3',
                'maxclients': '10000', 'databases': '16', 'maxmemory': '218',
                'requirepass': 'Secret123'}
        yfstub = _YfStub()
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda a=args: dict(a),
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns['submitRedisConf']())['status'])
        first = _read(self.conf)
        self.assertTrue(json.loads(ns['submitRedisConf']())['status'])
        self.assertEqual(_read(self.conf), first,
                         '提交与现值相同的配置时文件必须逐字节不变（旧的无锚点正则会改写其他行）')

        # 密码清空两次：旧实现 re.sub('requirepass', '#requirepass') 会叠加成 ##requirepass
        ns2 = self._exec(['submitRedisConf'], {
            'yf': _YfStub(),
            'getArgs': lambda: {'requirepass': ''},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns2['submitRedisConf']())['status'])
        cleared = _read(self.conf)
        self.assertTrue(json.loads(ns2['submitRedisConf']())['status'])
        self.assertEqual(_read(self.conf), cleared,
                         '同一个「清空密码」请求重复提交不得再改动文件字节')
        self.assertNotIn('##requirepass', cleared, '清空密码不得靠叠加 # 实现')
        self.assertIn('#requirepass ""', cleared)

        # 真实运维配置里普遍带上游 valkey.conf 的标准注释：旧的无锚点正则会把注释里的
        # `port 0`/`bind …` 一并当配置项改写（真机夹具实测注释句子被截断），字节漂移。
        commented = ('# Accept connections on the specified port, default is 6389.\n'
                     '# If port 0 is specified Valkey will not listen on a TCP socket.\n'
                     '# bind 127.0.0.1 -::1\n'
                     'bind 127.0.0.1\n'
                     'port 6389\n')
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(commented)
        ns3 = self._exec(['submitRedisConf'], {
            'yf': _YfStub(),
            'getArgs': lambda: {'port': '6389', 'bind': '127.0.0.1'},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns3['submitRedisConf']())['status'])
        after = _read(self.conf)
        self.assertEqual(after, commented,
                         '同值重提不得改动带注释的真实配置文件（旧无锚点正则会改写注释行）')
        self.assertIn('# If port 0 is specified Valkey will not listen on a TCP socket.', after,
                      '注释句子必须逐字保留（旧正则会把 `port 0 …socket.` 整段改成 `port 6389`）')

    # ---- 9. infoReplication 对残缺 INFO 不得抛 KeyError -------------------
    def test_09_info_replication_tolerates_partial_info(self):
        ns = self._exec(['infoReplication'], {
            'status': lambda: 'start',
            'valkeyCli': lambda *a: ('# Replication\r\nrole:master\r\nmaster_repl_offset:0\r\n', ''),
            'yf': _YfStub(),
        })
        try:
            res = json.loads(ns['infoReplication']())
        except KeyError as ex:
            self.fail('缺少 connected_slaves 时必须按 0 处理，实际抛 KeyError: %s' % ex)
        self.assertEqual(res.get('role'), 'master')

        ns2 = self._exec(['infoReplication'], {
            'status': lambda: 'start',
            'valkeyCli': lambda *a: (
                'role:master\nconnected_slaves:1\n'
                'slave0:ip=::1,port=6380,state=online,offset=1,lag=0\n', ''),
            'yf': _YfStub(),
        })
        res2 = json.loads(ns2['infoReplication']())
        self.assertEqual(res2.get('slave0'), 'ip=::1,port=6380,state=online,offset=1,lag=0',
                         '从库行必须按第一个冒号切分，否则 IPv6 值被截断')

    # ---- 10. readConfigTpl：白名单 + 目录/不可读目标如实报错 ---------------
    def test_10_read_config_tpl_rejects_out_of_bounds(self):
        tpl_dir = os.path.join(self.tmp, 'tpl')
        os.makedirs(tpl_dir, exist_ok=True)
        tpl_file = os.path.join(tpl_dir, 'valkey_simple.conf')
        with io.open(tpl_file, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('port 6389\n')
        outside = os.path.join(self.tmp, 'index.py')
        with io.open(outside, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('SECRET_TOKEN\n')

        def run(target):
            ns = self._exec(['readConfigTpl'], {
                'getArgs': lambda t=target: {'file': t},
                'checkArgs': lambda data, ck: (True, ''),
                'getPluginDir': lambda: self.tmp,
                'contentReplace': lambda c: c,
                'yf': _YfStub(),
            })
            return json.loads(ns['readConfigTpl']())

        for target in ('/etc/passwd', outside, os.path.join(tpl_dir, '..', 'index.py'),
                       tpl_dir, tpl_dir + os.sep + 'nonexistent.conf'):
            try:
                res = run(target)
            except AttributeError as ex:
                self.fail('读目录/不可读目标不得抛 AttributeError（真机 traceback 成因）: %s' % ex)
            self.assertFalse(res['status'], '越界/目录/缺失目标必须如实拒绝: %r' % target)
            self.assertNotIn('SECRET_TOKEN', str(res.get('data')))
            self.assertNotIn('root:', str(res.get('data')))

        res_ok = run(tpl_file)
        self.assertTrue(res_ok['status'], 'tpl 目录内的真实文件必须能读')
        self.assertIn('port 6389', res_ok['data'])

    # ---- 11. clusterNodes 空应答必须回空列表 ------------------------------
    def test_11_cluster_nodes_empty_is_empty_list(self):
        ns = self._exec(['clusterNodes'], {
            'status': lambda: 'start',
            'valkeyCli': lambda *a: ('', ''),
            'yf': _YfStub(),
        })
        self.assertEqual(json.loads(ns['clusterNodes']()), [],
                         "空应答必须是 []，不能是 ['']（前端会渲染出一行假数据）")

    # ---- 12. status 不得被陈旧 pid 文件骗成「运行中」 ---------------------
    def test_12_status_ignores_stale_pidfile(self):
        fn = self._fn('status')
        self.assertTrue([c for c in _calls(fn, 'checkPid')],
                        'status 必须校验 pid 是否真实存活（不能只看文件存在）')

        pid_file = os.path.join(self.tmp, 'valkey.pid')
        conf = os.path.join(self.tmp, 'valkey.conf')
        with io.open(conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('pidfile %s\n' % pid_file)
        # 陈旧 pid：文件存在但进程早没了
        with io.open(pid_file, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('999999\n')
        ns = self._exec(['getPidFile', 'status'], {
            'yf': _YfStub(),
            'getConf': lambda: conf,
        })
        try:
            self.assertEqual(ns['status'](), 'stop',
                             'pid 文件存在但进程已死时必须判 stop（否则面板永远显示运行中）')
        except Exception as ex:
            self.fail('status 不得因陈旧/非法 pid 文件抛异常: %s' % ex)

        # 真实存活 pid（本测试进程）-> start
        with io.open(pid_file, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('%d\n' % os.getpid())
        yfstub = _YfStub()
        yfstub.checkPid = lambda pid: pid == os.getpid()
        ns2 = self._exec(['getPidFile', 'status'], {'yf': yfstub, 'getConf': lambda: conf})
        self.assertEqual(ns2['status'](), 'start')

    # ---- 13. start/restart 必须做就绪校验（不许假成功） -------------------
    def test_13_start_and_restart_verify_readiness(self):
        for name in ('start', 'restart'):
            fn = self._fn(name)
            self.assertTrue([c for c in _calls(fn, 'status')],
                            '%s 必须在返回 ok 前校验真实就绪状态' % name)
        ns = self._exec(['start'], {
            'yf': _YfStub(),
            'wkOp': lambda m: 'ok',
            'status': lambda: 'stop',
        })
        res = ns['start']()
        self.assertNotEqual(res, 'ok', 'systemctl 回 ok 但进程没起来时必须如实报失败')

        ns2 = self._exec(['start'], {
            'yf': _YfStub(),
            'wkOp': lambda m: 'ok',
            'status': lambda: 'start',
        })
        self.assertEqual(ns2['start'](), 'ok')

        ns3 = self._exec(['restart'], {
            'yf': _YfStub(),
            'wkOp': lambda m: 'ok',
            'status': lambda: 'stop',
        })
        self.assertNotEqual(ns3['restart'](), 'ok', '重启没就绪不得回 ok（否则回滚判据失效）')

    # ---- 14. 新增消息键 6 语言齐备 ----------------------------------------
    def test_14_lang_keys_present(self):
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANG_DIR, lang + '.json')))
            for k in NEW_KEYS:
                self.assertIn(k, data, '%s 缺少语言键 %r' % (lang, k))
                self.assertTrue(data[k].strip(), '%s 的键 %r 译文为空' % (lang, k))

    # ---- 15. getArgs 必须认得真实调用形态 ---------------------------------
    def test_15_get_args_parses_real_invocation_shapes(self):
        ns = self._exec(['getArgs'])
        old = sys.argv
        cases = [
            (['index.py', 'submit_redis_conf', '{"port":"6389","bind":"127.0.0.1"}'],
             {'port': '6389', 'bind': '127.0.0.1'}),
            (['index.py', 'submit_redis_conf', '8.0.1', '{"port":"6389"}'], {'port': '6389'}),
            (['index.py', 'submit_redis_conf', 'port:6389'], {'port': '6389'}),
            (['index.py', 'submit_redis_conf', 'port=6389'], {'port': '6389'}),
            (['index.py', 'run_info'], {}),
        ]
        try:
            for argv, want in cases:
                sys.argv = argv
                got = ns['getArgs']()
                for k, v in want.items():
                    self.assertEqual(got.get(k), v, 'argv=%r 必须解析出 %r（实得 %r）' % (argv, k, got))
                if not want:
                    self.assertEqual(got, {})
        finally:
            sys.argv = old

    # ---- 16. initdStatus 用机器可读判据（不依赖会被本地化的输出） ---------
    def test_16_initd_status_uses_is_enabled(self):
        ns = self._exec(['initdStatus'], {
            'getPluginName': lambda: 'valkey',
            'getInitDFile': lambda: '/etc/init.d/valkey',
            'yf': _YfStub(server_dir=self.server_dir),
            'os': os,
        })
        yfstub = ns['yf']
        yfstub.shell_out = 'enabled\n'
        self.assertEqual(ns['initdStatus'](), 'ok')
        yfstub.shell_out = 'disabled\n'
        self.assertEqual(ns['initdStatus'](), 'fail')
        yfstub.shell_out = ''
        self.assertEqual(ns['initdStatus'](), 'fail')
        for call in yfstub.shell_calls:
            self.assertIn('is-enabled', call['cmd'], '必须用 is-enabled 判定，而不是 grep 人类可读输出')
            self.assertNotIn('grep', call['cmd'])


if __name__ == '__main__':
    unittest.main()
