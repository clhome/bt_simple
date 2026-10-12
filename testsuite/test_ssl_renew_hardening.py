# coding: utf-8
"""P0-1① 修复守卫：`/site/renew_ssl` 的 site_name 命令注入（root RCE）。

修复前的写法（测评报告 P0-1①，`web/admin/site/ssl.py::renew_ssl`）：

    site_name = request.form.get('site_name', '')          # 无任何校验
    cmd = f"{acme_dir}/acme.sh --renew -d {site_name} --force >> {log_file} 2>&1"
    yf.execShell(cmd)                                      # root 下执行任意命令
    yf.execShell('echo "acme" > "' + dst_path + '/README"')

`site_name` 同时被拼进证书目录路径，因此既能注入命令也能穿越目录。

本用例锁死四件事（都要求**真能失败**，由 `test/p0_ssl_injection_mutation_probe.py`
逐个回退修复点自证）：

1. 入口校验：`renew_ssl` 第一段就是 `safeSiteName(...)` + 非法即 return；
2. 行为：恶意 site_name 被拒，且 **execShell 一次都没被调用**（把函数体从 AST 里
   抽出来在 mock 环境真调用，不是读源码字符串）；
3. 写法：`--renew -d` 必须走 `yf.shlexQuote(...)`；`echo "acme" >` 这类无谓 shell
   不得复活（README 改用 `yf.writeFile`）；
4. 覆盖面：`ssl.py` 其余路由的 site_name 都经 `safeSiteName`/`getHostConf` 收口。
"""
import ast
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.site import safeSiteName  # noqa: E402

SSL_ROUTE = os.path.join(WEB, 'admin', 'site', 'ssl.py')
SITE_UTILS = os.path.join(WEB, 'utils', 'site.py')

#: 入口必须拒的载荷。`x;id` / `$(id)` / 反引号 / `x|id` 都不含空白与斜杠，
#: 只靠「拒空白+拒 `/`」的旧白名单是拦不住的（修复前实测全部放行）。
INJECTION_PAYLOADS = [
    '$(id)',
    'x$(id)',
    '`id`',
    'x;id',
    'x|id',
    'x&&id',
    'x\nid',
    'x id',
    'x\ty',
    '../x',
    '..',
    'x' * 101,
    '',
]

LEGIT_SITE_NAMES = [
    'www.test.com',
    '*.test.com',
    'a_b-c.test',
    '172.17.60.248',
    '中文站点.test',
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _func_node(path, name, cls=None):
    """按 AST 取函数/方法节点（结构断言，注释或 `if False:` 蒙混不过去）。"""
    tree = ast.parse(_read(path))
    if cls is None:
        candidates = tree.body
    else:
        candidates = []
        for top in tree.body:
            if isinstance(top, ast.ClassDef) and top.name == cls:
                candidates = top.body
                break
    for node in candidates:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError('未找到 %s.%s（%s）' % (cls or '', name, path))


def _func_src(path, name, cls=None):
    node = _func_node(path, name, cls=cls)
    return ast.get_source_segment(_read(path), node)


def _calls_of(node, attr):
    """函数体内所有 `xxx.<attr>(...)` 调用的行号。"""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == attr:
                out.append(sub.lineno)
    return out


# ---------------------------------------------------------------------------
# 行为测试的运行台：把 renew_ssl 的函数体单独编译执行，yf / YfSites / request 全 mock
# ---------------------------------------------------------------------------
class _Recorder:
    def __init__(self):
        self.calls = []
        self.shell = []

    def note(self, name):
        self.calls.append(name)


class _FakeYf:
    """只实现 renew_ssl 用到的那几个 yf 函数；shell 一律记账，绝不真执行。"""

    #: 生产 `core.yf` 的超时常量（renew_ssl 显式传 timeout= 时会读它们）
    EXEC_DEFAULT_TIMEOUT = 60
    EXEC_SERVICE_TIMEOUT = 120
    EXEC_DOWNLOAD_TIMEOUT = 600
    EXEC_ARCHIVE_TIMEOUT = 1800

    def __init__(self, rec, tmp):
        self.rec = rec
        self.tmp = tmp
        self.writes = []

    def getAcmeDir(self):
        self.rec.note('getAcmeDir')
        return os.path.join(self.tmp, 'acme')

    def getAcmeDomainDir(self, domain):
        self.rec.note('getAcmeDomainDir')
        return os.path.join(self.tmp, 'acme', str(domain))

    def shlexQuote(self, s):
        import shlex
        return shlex.quote(str(s))

    def writeFile(self, path, content, mode='w+'):
        self.rec.note('writeFile')
        self.writes.append((path, content))
        return True

    def writeFileLog(self, msg, *a, **k):
        self.rec.note('writeFileLog')

    def readFile(self, path, *a, **k):
        self.rec.note('readFile')
        return ''

    def execShell(self, cmd, *a, **k):
        self.rec.note('execShell')
        self.rec.shell.append(cmd)
        return ('', '')

    def returnData(self, status, msg, *a, **k):
        self.rec.note('returnData')
        return {'status': status, 'msg': msg}

    def makeDirs(self, path):
        self.rec.note('makeDirs')
        return True

    def buildSoftLink(self, src, dst, force=False):
        self.rec.note('buildSoftLink')
        return True

    def restartWeb(self):
        self.rec.note('restartWeb')
        return True

    def getCertName(self, path):
        self.rec.note('getCertName')
        return None


class _FakeSitesInstance:

    def __init__(self, rec, tmp):
        self.rec = rec
        self.sslDir = os.path.join(tmp, 'ssl')

    def acmeLogFile(self):
        self.rec.note('acmeLogFile')
        return os.path.join(self.rec.tmp, 'acme.log')

    def getSitePath(self, name):
        self.rec.note('getSitePath')
        return ''

    def closeProxyAll(self, name):
        self.rec.note('closeProxyAll')

    def closeRedirectAll(self, name):
        self.rec.note('closeRedirectAll')

    def openProxyByOpen(self, name):
        self.rec.note('openProxyByOpen')

    def openRedirectByOpen(self, name):
        self.rec.note('openRedirectByOpen')

    def setSslConf(self, name):
        self.rec.note('setSslConf')
        return {'status': True}


class _FakeRequest:

    def __init__(self, form):
        self.form = dict(form)


def _compile_renew_ssl(globals_dict):
    """把 renew_ssl 的函数体编译成可调用对象（剥掉 blueprint 装饰器，不起 Flask）。"""
    node = _func_node(SSL_ROUTE, 'renew_ssl')
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    code = compile(ast.fix_missing_locations(module), SSL_ROUTE, 'exec')
    env = {'__name__': 'yf_ssl_renew_harness', '__builtins__': __builtins__}
    env.update(globals_dict)
    exec(code, env)
    return env['renew_ssl']


def _run_renew(form):
    """真调用 renew_ssl，返回 (recorder, 返回值, 临时目录)。"""
    tmp = tempfile.mkdtemp(prefix='yf_ssl_renew_')
    rec = _Recorder()
    rec.tmp = tmp
    fake_yf = _FakeYf(rec, tmp)

    class _Sites:
        @staticmethod
        def instance():
            return _FakeSitesInstance(rec, tmp)

    fn = _compile_renew_ssl({
        'request': _FakeRequest(form),
        'yf': fake_yf,
        'YfSites': _Sites,
        'safeSiteName': safeSiteName,
        'os': os,
    })
    return rec, fn(), tmp


class TestSafeSiteNameShellHardening(unittest.TestCase):
    """白名单本身必须拦住「不需要空白/斜杠也能成立」的注入载荷。"""

    def test_01_rejects_shell_metachars(self):
        for payload in INJECTION_PAYLOADS:
            self.assertEqual(safeSiteName(payload), '',
                             '白名单放行了 %r' % (payload,))

    def test_02_keeps_legit_names(self):
        for name in LEGIT_SITE_NAMES:
            self.assertEqual(safeSiteName(name), name,
                             '合法站点名被误拦：%r' % (name,))


class TestRenewSslEntryGuard(unittest.TestCase):
    """入口校验：静态结构 + 真实调用行为。"""

    def test_03_validates_before_any_shell(self):
        node = _func_node(SSL_ROUTE, 'renew_ssl')
        src = _read(SSL_ROUTE)

        validate_lines = [n.lineno for n in ast.walk(node)
                          if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name) and n.func.id == 'safeSiteName']
        self.assertTrue(validate_lines, 'renew_ssl 入口没有调用 safeSiteName')

        shell_lines = _calls_of(node, 'execShell')
        self.assertTrue(shell_lines,
                        'renew_ssl 已不再执行 acme.sh（守卫前提变了，请同步本用例）')

        returns = [n for n in ast.walk(node)
                   if isinstance(n, ast.Return) and n.lineno < min(shell_lines)]
        self.assertTrue(returns, '校验失败没有在 execShell 之前 return')
        self.assertLess(min(validate_lines), min(r.lineno for r in returns),
                        'return 必须紧跟在校验之后')
        early_ret = min(returns, key=lambda n: n.lineno)
        ret_src = ast.get_source_segment(src, early_ret.value)
        self.assertIn('returnData(False', ret_src,
                      '非法站点名必须返回失败：%s' % ret_src)

    def test_04_malicious_site_name_rejected_without_shell(self):
        for payload in INJECTION_PAYLOADS:
            rec, result, _tmp = _run_renew({'site_name': payload, 'ssl_type': 'acme'})
            self.assertFalse(result['status'], '恶意 site_name %r 未被拒绝' % (payload,))
            self.assertEqual(result['msg'], 'site.py_msg_dbd9b9',
                             '恶意 site_name %r 的拒绝原因不对' % (payload,))
            self.assertEqual(rec.shell, [],
                             '恶意 site_name %r 触发了 execShell：%r' % (payload, rec.shell))
            self.assertNotIn('getAcmeDir', rec.calls,
                             '恶意 site_name %r 未被入口拦截，已进入续签流程' % (payload,))

    def test_05_legit_site_name_still_renews_and_is_quoted(self):
        rec, result, _tmp = _run_renew({'site_name': '*.test.com', 'ssl_type': 'acme'})
        self.assertEqual(len(rec.shell), 2,
                         '合法站点名应走完常规续签 + Let\'s Encrypt 后备重试：%r' % (rec.shell,))
        for cmd in rec.shell:
            self.assertIn("--renew -d '*.test.com'", cmd,
                          'acme.sh 的 -d 参数未做 shell 转义：%r' % (cmd,))
            self.assertNotIn('--renew -d *.test.com', cmd,
                             '未转义的泛域名会被 shell 展开：%r' % (cmd,))
        # 假证书目录下必然续签不成功 —— 但流程确实走完了（没有被入口拦下）
        self.assertFalse(result['status'])
        self.assertEqual(result['msg'], 'site.py_msg_2b7ff5')

    def test_06_shell_concat_is_quoted_and_readme_uses_writefile(self):
        src = _read(SSL_ROUTE)
        self.assertIn('--renew -d {yf.shlexQuote(site_name)}', src,
                      'acme.sh 的 -d 参数必须经 yf.shlexQuote')
        self.assertNotIn('--renew -d {site_name}', src,
                         '未转义的 site_name 又回到了 shell 命令里')
        for bad in ("execShell('echo", 'execShell("echo'):
            self.assertNotIn(bad, src, '无谓的 shell 落盘写法复活了：%s' % bad)
        self.assertIn("yf.writeFile(dst_path + '/README', 'acme')", src,
                      'README 应改用 yf.writeFile 落盘')

    def test_07_other_ssl_routes_funnel_site_name_through_whitelist(self):
        """ssl.py 其余路由的 site_name 都进 safeSiteName / getHostConf 收口。"""
        for method in ('closeSslConf', 'deleteSsl', 'setSsl',
                       'setCertToSite', 'removeCert'):
            src = _func_src(SITE_UTILS, method, cls='sites')
            self.assertIn('safeSiteName(', src,
                          '%s 未对 site_name/cert_name 做白名单校验' % method)
        for method in ('getSsl', 'httpToHttps', 'closeToHttps'):
            src = _func_src(SITE_UTILS, method, cls='sites')
            self.assertIn('getHostConf(', src,
                          '%s 未走 getHostConf（站点名会直接进路径）' % method)
        self.assertIn('safeSiteName(', _func_src(SITE_UTILS, 'getHostConf', cls='sites'),
                      'getHostConf 是站点名进路径的咽喉，必须做白名单校验')


if __name__ == '__main__':
    unittest.main()
