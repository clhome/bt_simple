# coding: utf-8
"""B09 phpmyadmin 插件回归守卫（本轮真机功能测试暴露的缺陷）。

被测面 `plugins/phpmyadmin/`。真机 phpmyadmin 已安装（`/www/server/phpmyadmin`，
随机目录 `mhiiopjb`、`cfg.json`/`pma.pass`/`config.inc.php`/vhost conf 齐全），
本轮用「夹具真跑」（把模块 import 进来，把 getServerDir/getConf 指向 /root/yf_probe_B09）
复现并修复了下面几类问题（每条都有真机前后对照，详见 task.md 的 B09 行）：

1. **`setPmaPath` 命令注入**：旧实现只判 `len(path) >= 5` 就 `yf.execShell("mv " + old + " " + new)`。
   夹具真跑 `path="mhiiopjb2; touch /root/yf_probe_B09/INJECTED"` → 回「修改成功!」且
   **marker 真被 root 建出**。修后回「路径只能使用 5-32 位…」、marker 未建。
2. **`setPmaPath` 目录逃逸**：`path="../../../../root/yf_probe_B09/escaped"` 把安装目录
   移出 `/www/server/phpmyadmin`。修后 realpath 校验拒绝。
3. **`setPmaPort` nginx 配置注入 / 非数字端口**：旧实现只挡 `80`。夹具真跑 `port="abc"`
   写入 `listen abc;`；`port="9999;\\n    add_header X-Injected 1;"` 直接把 `add_header`
   注入 vhost。修后回「端口必须是数字!」/「端口范围不合法!」且 conf 不变。
4. **`setPmaUsername` htpasswd 追加用户（认证绕过）**：`pma.pass` 是逐行
   `用户名:口令哈希`，用户名里的换行会追加一个任意 basic-auth 用户。夹具真跑
   `username="evil\\nroot2:$2b$12$AAA…"` → pma.pass 变 2 行。修后回「用户名只能使用…」且仍 1 行。
5. **`setPmaChoose` 任意值**：旧实现直接把入参写进 cfg.json。修后白名单拒绝。
6. **`getCfg` 里两处 shell `mv`**：把 cfg.json 的 path 原样拼进 shell，与 #1 同族。修后
   全改 `shutil.move`（模块内已无 shell mv）。
7. **前端存储型 XSS + 遮罩卡死**：`safeConf`/`pmaService`/`homePage` 把服务端返回的
   用户名/密码/路径/端口/URL 原样拼 innerHTML 与行内 `onclick`（与 A09/A11/A12/B03 同族）；
   `pmaOpService`/`pmaService`/`phpVer` 的 `$.post` 缺 `.fail()`（面板 500 时
   `time:0` 遮罩永久卡死）。

断言策略：能真跑的一律用真实代码/AST 取出的正则真跑行为；结构断言走 AST（注释、
字符串、`if False:` 死分支都骗不过去）；JS 先掩码注释/字符串再看代码结构。
"""
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 变异探针会覆盖这两个路径，指向临时副本
IDX = os.path.join(ROOT, 'plugins', 'phpmyadmin', 'index.py')
JS = os.path.join(ROOT, 'plugins', 'phpmyadmin', 'js', 'phpmyadmin.js')


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _call_names(node):
    """节点内所有调用的点分名（`yf.execShell` / `shutil.move` / `_PMA_PATH_RE.match`）。"""
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            parts = []
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
            if parts:
                names.append('.'.join(reversed(parts)))
    return names


def _module_regex(tree, name):
    """取模块级 `name = re.compile('...')` 的模式串（只认顶层赋值）。"""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    call = node.value
                    if isinstance(call, ast.Call) and isinstance(call.args[0], ast.Constant):
                        return call.args[0].value
    return None


def _module_tuple(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return [e.value for e in node.value.elts]
    return None


def _mask_js(src):
    """把 JS 注释/字符串/正则字面量内容换成空格（长度不变），只看代码结构。"""
    buf = list(src)
    i, n = 0, len(src)
    quote = None

    def _blank(a, b):
        for k in range(a, min(b, n)):
            if buf[k] != '\n':
                buf[k] = ' '

    def _prev_code_ch():
        for k in range(i - 1, -1, -1):
            if src[k] in ' \t\r\n':
                continue
            return src[k]
        return ''

    while i < n:
        ch = src[i]
        if quote:
            if ch == '\\':
                _blank(i, i + 2)
                i += 2
                continue
            if ch == quote:
                quote = None
                _blank(i, i + 1)
                i += 1
                continue
            _blank(i, i + 1)
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            _blank(i, i + 1)
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            start = i
            while i < n and src[i] != '\n':
                i += 1
            _blank(start, i)
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            start = i
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            _blank(start, i)
            continue
        if ch == '/' and _prev_code_ch() in '(,=:[!&|?{};':
            start = i
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '/':
                    i += 1
                    break
                i += 1
            while i < n and src[i].isalpha():
                i += 1
            _blank(start, i)
            continue
        i += 1
    return ''.join(buf)


def _js_function(src, name):
    masked = _mask_js(src)
    at = masked.find('function ' + name + '(')
    if at < 0:
        return ''
    brace = masked.find('{', at)
    if brace < 0:
        return ''
    depth = 0
    for i in range(brace, len(masked)):
        if masked[i] == '{':
            depth += 1
        elif masked[i] == '}':
            depth -= 1
            if depth == 0:
                return masked[at:i + 1]
    return masked[at:]


class TestPmaPathGuard(unittest.TestCase):
    def test_path_regex_rejects_traversal_and_injection(self):
        pat = _module_regex(_tree(IDX), '_PMA_PATH_RE')
        self.assertIsNotNone(pat, '缺少 _PMA_PATH_RE 白名单')
        rx = re.compile(pat)
        for bad in ('../evil', '../../../../root/x', 'ab; touch /tmp/x',
                    'a b', 'a\nb', 'a/b', '', 'abcd', 'a' * 33, 'a$b', 'a`b'):
            self.assertIsNone(rx.match(bad), '非法路径被放行: %r' % bad)
        for good in ('mhiiopjb', 'abcde', 'a' * 32, 'pma-2026_x'):
            self.assertIsNotNone(rx.match(good), '合法路径被拒: %r' % good)

    def test_set_pma_path_uses_shutil_move_not_shell(self):
        fn = _func(_tree(IDX), 'setPmaPath')
        self.assertIsNotNone(fn, '缺少 setPmaPath')
        calls = _call_names(fn)
        self.assertNotIn('yf.execShell', calls, 'setPmaPath 仍走 shell（命令注入）')
        self.assertIn('shutil.move', calls, 'setPmaPath 未用 shutil.move')
        self.assertIn('_PMA_PATH_RE.match', calls, 'setPmaPath 未做路径白名单')

    def test_validator_runs_before_move(self):
        body = ast.get_source_segment(_read(IDX), _func(_tree(IDX), 'setPmaPath'))
        self.assertLess(body.index('_PMA_PATH_RE.match'), body.index('shutil.move'),
                        '白名单校验必须早于移动')

    def test_getcfg_has_no_shell_move(self):
        fn = _func(_tree(IDX), 'getCfg')
        self.assertIsNotNone(fn, '缺少 getCfg')
        calls = _call_names(fn)
        self.assertNotIn('yf.execShell', calls, 'getCfg 仍用 shell mv（path 来自 cfg.json）')

    def test_no_shell_mv_literal_anywhere(self):
        for node in ast.walk(_tree(IDX)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertFalse(node.value.startswith('mv '),
                                 '模块内仍有 shell mv 字符串: %r' % node.value)


class TestPmaPortGuard(unittest.TestCase):
    def test_port_regex_rejects_non_numeric(self):
        pat = _module_regex(_tree(IDX), '_PMA_PORT_RE')
        self.assertIsNotNone(pat, '缺少 _PMA_PORT_RE 白名单')
        rx = re.compile(pat)
        for bad in ('abc', '9999;\n    add_header X-Injected 1;', '', ' 888',
                    '88.8', '-1', '１２３', '1e3', '888;'):
            self.assertIsNone(rx.match(bad), '非法端口被放行: %r' % bad)
        for good in ('888', '9999', '65535', '1'):
            self.assertIsNotNone(rx.match(good), '合法端口被拒: %r' % good)

    def test_set_pma_port_validates_range_and_80(self):
        src = ast.get_source_segment(_read(IDX), _func(_tree(IDX), 'setPmaPort'))
        self.assertIn('_PMA_PORT_RE.match', src, 'setPmaPort 未做数字白名单')
        self.assertRegex(src, r'int\(port\)\s*<\s*1', 'setPmaPort 缺下界校验')
        self.assertRegex(src, r'int\(port\)\s*>\s*65535', 'setPmaPort 缺上界校验')
        self.assertIn("'80'", src, 'setPmaPort 仍应拒绝 80')


class TestPmaUserGuard(unittest.TestCase):
    def test_user_regex_rejects_injection(self):
        pat = _module_regex(_tree(IDX), '_PMA_USER_RE')
        self.assertIsNotNone(pat, '缺少 _PMA_USER_RE 白名单')
        rx = re.compile(pat)
        for bad in ('evil\nroot2:$2b$12$AAA', 'a:b', 'a b', '', 'a\tb',
                    'a' * 65, 'user\rname'):
            self.assertIsNone(rx.match(bad), '非法用户名被放行: %r' % bad)
        for good in ('admin_1', 'a@b.c', 'u-1', 'A' * 64):
            self.assertIsNotNone(rx.match(good), '合法用户名被拒: %r' % good)

    def test_set_pma_username_validates(self):
        calls = _call_names(_func(_tree(IDX), 'setPmaUsername'))
        self.assertIn('_PMA_USER_RE.match', calls, 'setPmaUsername 未做用户名白名单')

    def test_set_pma_password_rejects_newline(self):
        src = ast.get_source_segment(_read(IDX), _func(_tree(IDX), 'setPmaPassword'))
        self.assertIn("'\\n' in password", src, 'setPmaPassword 未拒绝换行')
        self.assertIn("'\\r' in password", src, 'setPmaPassword 未拒绝回车')
        self.assertIn('len(password) > 128', src, 'setPmaPassword 未限制长度')

    def test_set_pma_choose_whitelist(self):
        choices = _module_tuple(_tree(IDX), '_PMA_CHOOSE')
        self.assertIsNotNone(choices, '缺少 _PMA_CHOOSE 白名单')
        for need in ('mysql', 'mariadb', 'mysql-community', 'mysql-apt', 'mysql-yum'):
            self.assertIn(need, choices)
        calls = _call_names(_func(_tree(IDX), 'setPmaChoose'))
        self.assertIn('yf.returnJson', calls)
        src = ast.get_source_segment(_read(IDX), _func(_tree(IDX), 'setPmaChoose'))
        self.assertIn('_PMA_CHOOSE', src, 'setPmaChoose 未校验白名单')


class TestPmaFrontendGuard(unittest.TestCase):
    def test_js_escape_helpers_defined(self):
        masked = _mask_js(_read(JS))
        self.assertIn('function yfPmaText(', masked)
        self.assertIn('function yfPmaJsStr(', masked)

    def test_js_safeconf_escapes_every_cfg_value(self):
        body = _js_function(_read(JS), 'safeConf')
        self.assertTrue(body, '未找到 safeConf')
        for var in ('cfgUser', 'cfgPass', 'cfgPath', 'cfgPort'):
            self.assertIn(var, body, 'safeConf 未转义 %s' % var)
        # 未转义的写法是 `... + cfg['xxx'] + ...`；`cfg['choose']=="…"` 这类
        # 纯逻辑比较不算（前面是 `(` 而不是 `+`）
        self.assertIsNone(re.search(r"\+\s*cfg\[", body),
                          'safeConf 仍把 cfg[...] 直接拼进 HTML')

    def test_js_pma_service_escapes_access_info(self):
        body = _js_function(_read(JS), 'pmaService')
        self.assertTrue(body, '未找到 pmaService')
        for var in ('infoInternal', 'infoExternal', 'infoUser', 'infoPass'):
            self.assertIn(var, body, 'pmaService 未转义 %s' % var)
        self.assertGreaterEqual(body.count('yfPmaText('), 4)
        self.assertIsNone(re.search(r'\+\s*info\.', body),
                          'pmaService 仍把 info.* 直接拼进 HTML')

    def test_js_homepage_uses_js_string_escape(self):
        body = _js_function(_read(JS), 'homePage')
        self.assertTrue(body, '未找到 homePage')
        self.assertIn('yfPmaJsStr(url)', body, 'homePage 的 onclick 未做 JS 字符串转义')
        self.assertIn('yfPmaText(url)', body, 'homePage 的 href/文本未做 HTML 转义')

    def test_js_has_fail_handlers(self):
        masked = _mask_js(_read(JS))
        self.assertGreaterEqual(masked.count('.fail('), 3,
                                'phpmyadmin.js 的裸 $.post 缺 .fail()（遮罩会卡死）')


if __name__ == '__main__':
    unittest.main()
