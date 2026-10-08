# coding: utf-8
"""B05 redis 插件加固守卫（真机真跑确认的缺陷，全部在此锁死）。

真机真跑（Debian12 + redis 8.6.3，探针 `/root/yf_probe_B05/probe_*.py`）确认并修复：

1. `execRedisCommand` 第 3 级回退（redis-cli）把用户命令**原样拼进 shell**：
   `yf.execShell(getRedisCmd() + command)`。真机端到端复现（redis 停机时）：
   `POST /plugins/callback` name=redis func=execRedisCommand args=`info; id > /tmp/x`
   → `uid=0(root)` 落盘。触发条件就是「前两级不可达」：Redis 未启动 / 端口不符 /
   socket 超时 / 空应答。
2. 同一个 `getRedisCmd()` 还把 requirepass 拼成 `-a "明文"`（shell 转义版），
   既进 shell 又进 argv（`ps -ef` 可见）。
3. `execRedisCommand` 对空命令/非字符串静默返回 ('', '')：调用方会误判成
   「执行成功但无输出」。
4. `execRedisCommand` 第 1 级（redis-py）在应答为 nil 时不返回、继续回退，
   同一条命令被重复执行一次（非幂等命令语义被破坏）。
5. `submitRedisConf` 的 bind/slaveof 白名单用 `\\s` 表示分隔符，而 `\\s` 含
   `\\n/\\r/\\f/\\v` —— 真机实测 `slaveof="127.0.0.1:6379\\nport 1"` 通过校验，
   追加到 conf 末尾的 `port 1` 生效，服务被改端口。
6. `submitRedisConf` 落盘后不看 `restart()` 结果、也不回滚：真机实测
   `port=888`（openresty 已占）→ 回「设置成功」而 Redis 停在 failed、坏配置留在盘上。
7. `infoReplication`：INFO 里只有 `role:master` 而无 `connected_slaves` 时
   `int(result['connected_slaves'])` 抛 KeyError（HTTP 下变 stderr traceback）；
   从库行解析用 `split(':')` 会把 IPv6 值截断。
8. `readConfigTpl`：`file` 传目录时 `yf.readFile` 返回 False → `contentReplace(False)`
   抛 AttributeError（应如实报「模板文件不存在」）。
9. `clusterNodes`：空应答 `strip().split('\\n')` → `['']`，前端渲染出一行假空行。
10. `getRunLog` 的 journalctl 兜底分支返回**未转义**原文，与 `getLastLine` 的转义
    口径不一致（日志里出现 `</textarea>` 即可从日志文本框逃逸）。

断言口径（防「假绿」）：AST 为主（`_live_nodes` 过滤 `if False:` 等静态死分支，
注释天然不参与），可提取的函数一律**取出来真跑行为**（真正则、真列表、真回滚）。
"""
import ast
import io
import json
import os
import socket
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'redis', 'index.py')
LANG_DIR = os.path.join(ROOT, 'plugins', 'redis', 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

# 本次新增的后端消息键（6 语言必须齐备，否则外语界面回落成中文原文）
NEW_KEYS = ('配置文件写入失败！', 'Redis 重启失败，配置已回滚！')


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


def _dead_port():
    """拿一个刚关闭的空闲端口：连接必然 ECONNREFUSED，用于逼出第 3 级回退。"""
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Log(object):
    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


class _YfStub(object):
    """只提供被测函数真正用到的那几个 yf 原语。"""

    def __init__(self, conf_path=None, write_ok=True):
        self.conf_path = conf_path
        self.write_ok = write_ok
        self.shell_rc_calls = []
        self.shell_calls = []
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

    def execShellRc(self, argv, *a, **kw):
        self.shell_rc_calls.append({'argv': argv, 'kwargs': kw})
        return (0, 'FROM-CLI', '')

    def execShell(self, cmd, *a, **kw):
        self.shell_calls.append({'cmd': cmd, 'kwargs': kw})
        return ('FROM-CLI', '')

    def getOs(self):
        return 'linux'

    def isAppleSystem(self):
        return False

    def shlex_quote(self, s):
        import shlex
        return shlex.quote(s)


class RedisB05HardeningTest(unittest.TestCase):

    def setUp(self):
        self.src = _read(IDX)
        self.tree = _parse(IDX)
        self.tmp = tempfile.mkdtemp(prefix='redis_b05_guard_')
        self.conf = os.path.join(self.tmp, 'redis.conf')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fn(self, name):
        fn = _find_func(self.tree, name)
        self.assertIsNotNone(fn, '函数缺失: %s' % name)
        return fn

    def _exec(self, names, extra=None):
        """把真实函数体取出来在受控命名空间里执行（真跑行为，不是文本匹配）。"""
        ns = {'os': os, 're': __import__('re'), 'json': json, '_log': _Log()}
        if extra:
            ns.update(extra)
        src = '\n\n'.join(ast.get_source_segment(self.src, self._fn(n)) for n in names)
        exec(compile(src, '<redis-extract>', 'exec'), ns)
        return ns

    def _conf_info(self, port='6379', passwd=''):
        items = [{'name': 'bind', 'value': '127.0.0.1'},
                 {'name': 'port', 'value': port}]
        if passwd:
            items.append({'name': 'requirepass', 'value': passwd})
        return items

    # ---- 1. getRedisCmd 必须返回 argv 列表，且密码原样进列表 ----------------
    def test_01_get_redis_cmd_returns_argv_list(self):
        nasty = 'My"Complex$Pass`2026'
        ns = self._exec(['getRedisCmd'], {
            'getRedisConfInfo': lambda: self._conf_info('6380', nasty),
            'getServerDir': lambda: self.tmp,
        })
        argv = ns['getRedisCmd']()
        self.assertIsInstance(argv, list, 'getRedisCmd 必须返回参数列表（字符串形态必然要经过 shell）')
        self.assertEqual(argv[argv.index('-p') + 1], '6380')
        self.assertEqual(argv[argv.index('-a') + 1], nasty,
                         '密码必须原样进入 argv（含 " / $ / 反引号），不做 shell 转义')
        self.assertIn('--no-auth-warning', argv)
        self.assertEqual(argv[0].count('"'), 0, 'redis-cli 路径不得被引号包裹')
        self.assertEqual([a for a in argv if a.startswith('"') or a.endswith('"')], [],
                         '列表传参下任何参数都不得再被 shell 引号包裹')

    # ---- 2. 第 3 级回退绝不允许再走 shell 字符串 ---------------------------
    def test_02_path3_no_shell_string_execution(self):
        fn = self._fn('execRedisCommand')
        self.assertEqual(_calls(fn, 'execShell'), [],
                         'execRedisCommand 不得再调用 yf.execShell(字符串) —— 那正是 root 命令注入点')
        rc_calls = _calls(fn, 'execShellRc')
        self.assertTrue(rc_calls, '第 3 级回退必须用 yf.execShellRc 执行 redis-cli')
        for c in rc_calls:
            kws = {k.arg: k.value for k in c.keywords}
            self.assertIn('shell', kws, 'execShellRc 必须显式 shell=False')
            self.assertIsInstance(kws['shell'], ast.Constant)
            self.assertFalse(kws['shell'].value, 'execShellRc 必须 shell=False（命令内容不进 shell）')

    # ---- 3. 真跑：注入载荷只能成为独立 argv 元素，不会被 shell 解释 --------
    def test_03_path3_injection_payload_is_argv_element(self):
        dead = _dead_port()
        payload = 'info; touch /tmp/yftest_b05_guard_pwn'
        yfstub = _YfStub()
        ns = self._exec(['getRedisCmd', 'execRedisCommand'], {
            'yf': yfstub,
            'getRedisConfInfo': lambda: self._conf_info(str(dead), 'pw'),
            'getServerDir': lambda: self.tmp,
        })
        ns['execRedisCommand'](payload)
        self.assertEqual(len(yfstub.shell_rc_calls), 1,
                         '前两级不可达时必须落到第 3 级回退（redis-cli）')
        call = yfstub.shell_rc_calls[0]
        self.assertFalse(call['kwargs'].get('shell', True), 'redis-cli 必须以 shell=False 执行')
        self.assertIn('timeout', call['kwargs'], '第 3 级回退必须有超时，否则会挂死面板线程')
        argv = call['argv']
        self.assertEqual(argv[-3:], ['info;', 'touch', '/tmp/yftest_b05_guard_pwn'],
                         '注入载荷必须整体成为独立 argv 元素（shell 无法把它当命令分隔符）')
        self.assertEqual(yfstub.shell_calls, [], '绝不能有字符串形态的 shell 调用')

    # ---- 4. 空命令 / 非字符串命令必须如实拒绝 ------------------------------
    def test_04_empty_or_non_str_command_rejected(self):
        dead = _dead_port()
        yfstub = _YfStub()
        ns = self._exec(['getRedisCmd', 'execRedisCommand'], {
            'yf': yfstub,
            'getRedisConfInfo': lambda: self._conf_info(str(dead)),
            'getServerDir': lambda: self.tmp,
        })
        for bad in ('', '   ', None, {'command': 'info'}, 123):
            out, err = ns['execRedisCommand'](bad)
            self.assertEqual(out, '')
            self.assertTrue(err.strip(), '空/非法命令必须如实报错，不能静默返回空')
        self.assertEqual(yfstub.shell_rc_calls, [], '空命令不该白跑一次 redis-cli')

    # ---- 5. 第 1 级成功（含 nil 应答）必须立即返回，不重复执行 --------------
    def test_05_nil_reply_does_not_fall_through(self):
        calls = []

        class _FakeRedisConn(object):
            def execute_command(self, *parts):
                calls.append(parts)
                return None

            def close(self):
                pass

        fake = types.ModuleType('redis')
        fake.Redis = lambda **kw: _FakeRedisConn()
        old = sys.modules.get('redis')
        sys.modules['redis'] = fake
        try:
            yfstub = _YfStub()
            ns = self._exec(['getRedisCmd', 'execRedisCommand'], {
                'yf': yfstub,
                'getRedisConfInfo': lambda: self._conf_info(str(_dead_port())),
                'getServerDir': lambda: self.tmp,
            })
            out, err = ns['execRedisCommand']('get yftest_b05_missing')
        finally:
            if old is None:
                sys.modules.pop('redis', None)
            else:
                sys.modules['redis'] = old
        self.assertEqual((out, err), ('', ''), 'nil 应答应回空串，不是报错')
        self.assertEqual(len(calls), 1, 'nil 应答不得触发第 2/3 级回退（同一条命令被重复执行）')
        self.assertEqual(yfstub.shell_rc_calls, [], 'nil 应答不得回退到 redis-cli')
        self.assertEqual(yfstub.shell_calls, [], 'nil 应答不得回退到 redis-cli（字符串 shell 形态）')

    # ---- 6. submitRedisConf：bind/slaveof 必须拒绝控制字符（换行注入） ------
    def test_06_submit_conf_rejects_newline_injection(self):
        fn = self._fn('submitRedisConf')
        # AST：bind/slaveof 的字符类里绝不能再出现 \s（\s 含 \n/\r/\f/\v）
        for pat in [s for s in _string_consts(fn) if 'a-zA-Z0-9_' in s and '[' in s]:
            self.assertNotIn(r'\s', pat,
                             'bind/slaveof 白名单不得用 \\s（换行会被 Redis 配置解析器当新指令）: %r' % pat)

        original = 'bind 127.0.0.1\nport 6379\nrequirepass Old\n'
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(original)
        yfstub = _YfStub()
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'slaveof': '127.0.0.1:6379\nport 1'},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        res = json.loads(ns['submitRedisConf']())
        self.assertFalse(res['status'], 'bind/slaveof 含换行必须被拒绝')
        self.assertEqual(_read(self.conf), original, '被拒绝的请求绝不允许改动 redis.conf')

        # 合法值（IPv4 + 空格分隔 + IPv6 短写 + 逗号）必须放行
        yfstub2 = _YfStub()
        ns2 = self._exec(['submitRedisConf'], {
            'yf': yfstub2,
            'getArgs': lambda: {'bind': '127.0.0.1 -::1,::1'},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns2['submitRedisConf']())['status'], '合法 bind 值不得被误拒')

    # ---- 7. submitRedisConf：端口范围校验 ----------------------------------
    def test_07_submit_conf_port_range(self):
        for bad in ('0', '65536', '99999'):
            yfstub = _YfStub()
            ns = self._exec(['submitRedisConf'], {
                'yf': yfstub,
                'getArgs': lambda b=bad: {'port': b},
                'getConf': lambda: self.conf,
                'status': lambda: 'stop',
                'restart': lambda: 'ok',
            })
            res = json.loads(ns['submitRedisConf']())
            self.assertFalse(res['status'], '越界端口 %s 必须被拒绝' % bad)
            self.assertEqual(yfstub.writes, [], '被拒绝的端口不得落盘')

    # ---- 8. submitRedisConf：重启失败必须回滚 + 如实报错（不许假成功） -----
    def test_08_submit_conf_rollback_on_restart_failure(self):
        original = 'port 6379\nrequirepass Old\n'
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(original)
        yfstub = _YfStub()
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'port': '888'},
            'getConf': lambda: self.conf,
            'status': lambda: 'start',
            'restart': lambda: '重启失败，服务未能重新拉起',
        })
        res = json.loads(ns['submitRedisConf']())
        self.assertFalse(res['status'], '重启失败却回「设置成功」就是假成功')
        self.assertIn('回滚', res['msg'])
        self.assertEqual(_read(self.conf), original, '重启失败必须把 redis.conf 整份回滚')

    # ---- 9. submitRedisConf：落盘失败必须如实报错 --------------------------
    def test_09_submit_conf_write_failure_is_honest(self):
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('port 6379\n')
        yfstub = _YfStub(write_ok=False)
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'port': '6380'},
            'getConf': lambda: self.conf,
            'status': lambda: 'start',
            'restart': lambda: 'ok',
        })
        res = json.loads(ns['submitRedisConf']())
        self.assertFalse(res['status'], '写盘失败不得回「设置成功」')
        self.assertEqual(_read(self.conf), 'port 6379\n', '写盘失败时原配置必须保持不动')

    # ---- 10. infoReplication 对残缺 INFO 不得抛 KeyError -------------------
    def test_10_info_replication_tolerates_partial_info(self):
        ns = self._exec(['infoReplication'], {
            'status': lambda: 'start',
            'execRedisCommand': lambda c='info': ('# Replication\r\nrole:master\r\nmaster_repl_offset:0\r\n', ''),
            'yf': _YfStub(),
        })
        try:
            res = json.loads(ns['infoReplication']())
        except KeyError as ex:
            self.fail('缺少 connected_slaves 时必须按 0 处理，实际抛 KeyError: %s' % ex)
        self.assertEqual(res.get('role'), 'master')

        # 从库行含冒号（IPv6）时不得截断值
        ns2 = self._exec(['infoReplication'], {
            'status': lambda: 'start',
            'execRedisCommand': lambda c='info': (
                'role:master\nconnected_slaves:1\nslave0:ip=::1,port=6380,state=online,offset=1,lag=0\n', ''),
            'yf': _YfStub(),
        })
        res2 = json.loads(ns2['infoReplication']())
        self.assertEqual(res2.get('slave0'), 'ip=::1,port=6380,state=online,offset=1,lag=0',
                         '从库行必须按第一个冒号切分，否则 IPv6 值被截断')

    # ---- 11. readConfigTpl：目录/不可读目标必须如实报错，不得抛异常 --------
    def test_11_read_config_tpl_directory_is_honest(self):
        tpl_dir = os.path.join(self.tmp, 'tpl')
        os.makedirs(tpl_dir, exist_ok=True)
        ns = self._exec(['readConfigTpl'], {
            'getArgs': lambda: {'file': tpl_dir},
            'checkArgs': lambda data, ck: (True, ''),
            'getPluginDir': lambda: self.tmp,
            'contentReplace': lambda c: c,
            'yf': _YfStub(),
        })
        try:
            res = json.loads(ns['readConfigTpl']())
        except AttributeError as ex:
            self.fail('传目录不得抛 AttributeError（真机 traceback 成因）: %s' % ex)
        self.assertFalse(res['status'])
        self.assertIn('不存在', res['msg'])

    # ---- 12. clusterNodes 空应答必须回空列表 ------------------------------
    def test_12_cluster_nodes_empty_is_empty_list(self):
        ns = self._exec(['clusterNodes'], {
            'status': lambda: 'start',
            'execRedisCommand': lambda c='info': ('', ''),
            'yf': _YfStub(),
        })
        self.assertEqual(json.loads(ns['clusterNodes']()), [],
                         "空应答必须是 []，不能是 ['']（前端会渲染出一行假数据）")

    # ---- 13. getRunLog 的 journalctl 兜底必须与 getLastLine 同口径转义 -----
    def test_13_get_run_log_escapes_fallback_content(self):
        fn = self._fn('getRunLog')
        escaped = []
        for c in _calls(fn, 'escape'):
            if c.args and isinstance(c.args[0], ast.Name):
                escaped.append(c.args[0].id)
        self.assertIn('j_out', escaped,
                      'journalctl 兜底内容必须 html.escape(j_out)（否则 </textarea> 可逃逸出 HTML）')

    # ---- 14. 原值重提必须零触碰（写回正则不得吃掉该行前面的空行） ---------
    def test_14_submit_conf_same_value_keeps_file_byte_identical(self):
        original = ('daemonize yes\n'
                    'pidfile /www/server/redis/redis.pid\n'
                    '\n'
                    'bind 127.0.0.1\n'
                    'port 6379\n'
                    'requirepass Old\n')
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(original)
        yfstub = _YfStub()
        ns = self._exec(['submitRedisConf'], {
            'yf': yfstub,
            'getArgs': lambda: {'bind': '127.0.0.1', 'port': '6379'},
            'getConf': lambda: self.conf,
            'status': lambda: 'stop',
            'restart': lambda: 'ok',
        })
        self.assertTrue(json.loads(ns['submitRedisConf']())['status'])
        self.assertEqual(_read(self.conf), original,
                         '提交与现值相同的配置时文件必须逐字节不变（旧正则的 \\s* 会吃掉空行）')

    # ---- 15. 新增消息键 6 语言齐备 ----------------------------------------
    def test_15_lang_keys_present(self):
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANG_DIR, lang + '.json')))
            for k in NEW_KEYS:
                self.assertIn(k, data, '%s 缺少语言键 %r' % (lang, k))
                self.assertTrue(data[k].strip(), '%s 的键 %r 译文为空' % (lang, k))


if __name__ == '__main__':
    unittest.main()
