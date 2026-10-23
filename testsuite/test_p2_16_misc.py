# coding: utf-8
"""P2-16 杂项四项的守卫用例（零外部依赖：只用标准库，不建 Flask app、不开面板库、不跑 node）。

被测面（方案 P2 表格第 16 行）：

  A. `web/utils/site.py` 的证书签发失败消息**走翻译层**：源码里不再有裸中文文案，
     改由 `_certFailHelp('site.cert_issue_retry_limit_help[_short]')` 从语言包取；
     六语言 `lan.js`（唯一真源）含新键，`.json` 载体已由
     `scripts/tools/export_lang_carriers.py` 派生；zh-TW 无简体残留。
  B. `plugins/docker/index.py` 的端口格式校验函数化：`_parseDockerPort()` 只接受
     「纯端口」或「地址:端口」（地址为 `*` / IPv4 / `[IPv6]`），`1:2:3`、`a:b:80`、
     `:80` 一律拒绝（旧实现在冒号处 `rsplit` 取最后一段，`1:2:3` 会被当成端口 3 放行）。
  C. `cgi.fix_pathinfo` 默认值的**复评结论**：保留 `1`。判据是 nginx 模板里已有
     `try_files` 把「不存在的 .php 路径」挡在 FPM 之外（外加 pathinfo.conf 的等价拆分），
     所以四处（实为 php/php-apt/php-yum 三渠道共 9 处）默认字典一律 `'1'` 且带理由注释。
  D. `panel_task.py` 的备份注释与实现一致：面板库**当前用 rollback journal**，
     不是注释里曾写的 WAL（WAL 因 `-shm` SIGBUS 已回退），且仍然必须用
     `Connection.backup()` 而不是文件复制。

关于「零外部依赖」：`_certFailHelp()` 与 `_parseDockerPort()` 都是从源码里**按 AST
抽出来**在小命名空间里执行的纯函数（前者注入一个假的 `core.i18n`），不 import
`web/utils/site.py`（那会连带 core.yf / thisdb / flask），也不 import 插件入口。
"""
import ast
import io
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
LANG_DIR = os.path.join(WEB, 'static', 'language')
TOOLS = os.path.join(ROOT, 'scripts', 'tools')

SITE_PY = os.path.join(WEB, 'utils', 'site.py')
DOCKER_PY = os.path.join(ROOT, 'plugins', 'docker', 'index.py')
PANEL_TASK_PY = os.path.join(ROOT, 'panel_task.py')
RESOURCES_PY = os.path.join(WEB, 'core', 'resources.py')
DB_PY = os.path.join(WEB, 'core', 'db.py')
MIGRATION_RUNNER_PY = os.path.join(WEB, 'core', 'migrations', 'runner.py')
DOC_LIFECYCLE = os.path.join(ROOT, '文档', '组件生命周期与安全响应政策.md')

LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

CERT_KEY_FULL = 'cert_issue_retry_limit_help'
CERT_KEY_SHORT = 'cert_issue_retry_limit_help_short'
CERT_KEYS = (CERT_KEY_FULL, CERT_KEY_SHORT)

#: 旧裸中文文案的特征片段（源码里再出现任何一段都说明「键化」被回退了）
CERT_RAW_FRAGMENTS = (
    '签发失败,您尝试申请证书的失败次数已达上限',
    '检查域名是否绑定到对应站点',
    '如果以上检查都确认没有问题',
)

#: zh-TW 里出现即说明混进了简体（这些字在本项文案里**只有简体才有**，
#: 共享字（失/定/查/申/站/解/析…）刻意不收 —— 它们繁简同形，收了就是假红）
SIMPLIFIED_ONLY = '签发败尝试请证书数达检绑对点确务还设关闭认没问题换为应'

#: docker 端口格式校验的表驱动数据（与任务书给的口径逐条对齐）
DOCKER_ACCEPT = (
    ('80', '80'),
    ('0.0.0.0:80', '80'),
    ('*:443', '443'),
    ('[::1]:8080', '8080'),
    ('192.168.1.5:3306', '3306'),
)
DOCKER_REJECT = (
    '1:2:3',
    'a:b:80',
    '0',
    '65536',
    'abc',
    ':80',
)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def _lan_module():
    """把 `scripts/tools/export_lang_carriers.py` 当库用（它只依赖标准库）。

    用它解析 `lan.js` 而不是自己写正则：那份解析器是**唯一真源**的解析口径
    （嵌套 dict、JS 宽松转义都踩过坑），自己再写一遍必然与之分叉。
    """
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    import export_lang_carriers as elc
    return elc


def _lan_section(lang, section):
    elc = _lan_module()
    sections, _get = elc.parse_lan_js(os.path.join(LANG_DIR, lang, 'lan.js'))
    sec = sections.get(section)
    if not isinstance(sec, dict):
        raise AssertionError('%s/lan.js 缺少 section %r' % (lang, section))
    return sec


def _carrier(lang, name):
    with io.open(os.path.join(LANG_DIR, lang, name), encoding='utf-8') as fh:
        return json.load(fh)


def _extract(path, want_names):
    """按 AST 抽出模块级常量赋值 + 函数定义，编译成一个可 exec 的 code 对象。

    只抽 `want_names` 里的名字：被测函数与它真正用到的模块级常量。
    """
    src = _read(path)
    tree = ast.parse(src)
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in want_names:
            body.append(node)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if targets and all(t in want_names for t in targets):
                body.append(node)
    missing = set(want_names) - set(
        [n.name for n in body if isinstance(n, ast.FunctionDef)] +
        [t.id for n in body if isinstance(n, ast.Assign) for t in n.targets
         if isinstance(t, ast.Name)])
    if missing:
        raise AssertionError('%s 里找不到: %s' % (os.path.basename(path), sorted(missing)))
    mod = ast.Module(body=body, type_ignores=[])
    return compile(mod, path, 'exec')


class _FakeI18n(object):
    """临时把 `core.i18n.t` 换成可编程桩；退出时原样还原 sys.modules。"""

    def __init__(self, mapping):
        self.mapping = mapping
        self._saved = {}

    def __enter__(self):
        self._saved = {k: sys.modules.get(k) for k in ('core', 'core.i18n')}
        pkg = types.ModuleType('core')
        pkg.__path__ = []
        i18n = types.ModuleType('core.i18n')

        def _t(key, *args, **kwargs):
            return self.mapping.get(key, key)

        i18n.t = _t
        pkg.i18n = i18n
        sys.modules['core'] = pkg
        sys.modules['core.i18n'] = i18n
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        return False


# ===========================================================================
# A. 证书失败消息走翻译层
# ===========================================================================
class TestCertFailMsgI18n(unittest.TestCase):

    def test_01_site_py_has_no_raw_cert_message(self):
        """源码里不得再有裸中文证书失败文案，必须是键调用。"""
        src = _read(SITE_PY)
        for frag in CERT_RAW_FRAGMENTS:
            self.assertNotIn(frag, src,
                             'site.py 里仍有裸中文证书失败文案（未走翻译层）: %r' % frag)
        self.assertIn('_certFailHelp(_CERT_FAIL_HELP_KEY)', src)
        self.assertIn('_certFailHelp(_CERT_FAIL_HELP_SHORT_KEY)', src)
        self.assertIn("_CERT_FAIL_HELP_KEY = 'site.%s'" % CERT_KEY_FULL, src)
        self.assertIn("_CERT_FAIL_HELP_SHORT_KEY = 'site.%s'" % CERT_KEY_SHORT, src)

    def test_02_six_languages_have_both_keys(self):
        """六语言 lan.js（唯一真源）都要有这两个键，且保留多行结构（不含 HTML）。"""
        for lang in LANGS:
            sec = _lan_section(lang, 'site')
            for key in CERT_KEYS:
                self.assertIn(key, sec, '%s/lan.js 缺 site.%s' % (lang, key))
                val = sec[key]
                self.assertTrue(val.strip(), '%s site.%s 是空值' % (lang, key))
                self.assertIn('\n', val,
                              '%s site.%s 丢了多行结构（首行标题 + 逐条排查）' % (lang, key))
                self.assertNotRegex(
                    val, r'<[a-zA-Z/][^>]*>',
                    '%s site.%s 的译文不得含 HTML（.json 载体有「值不得含 HTML」红线）'
                    % (lang, key))

    def test_03_zh_tw_has_no_simplified_residue(self):
        sec = _lan_section('zh-TW', 'site')
        for key in CERT_KEYS:
            bad = sorted({ch for ch in sec[key] if ch in SIMPLIFIED_ONLY})
            self.assertEqual([], bad,
                             'zh-TW site.%s 混进了简体字: %s' % (key, ''.join(bad)))
            # 繁中译法确实在位（不是「把简体当繁体登记」）
            self.assertIn('簽發失敗', sec[key])

    def test_04_carriers_derived_without_html(self):
        """.json 载体（后端 t() 的读取源）已派生且值不含 HTML。"""
        for lang in LANGS:
            carrier = _carrier(lang, 'template.site.json')
            sec = carrier.get('site') or {}
            for key in CERT_KEYS:
                self.assertIn(key, sec, '%s/template.site.json 缺 site.%s' % (lang, key))
                self.assertNotRegex(sec[key], r'<[a-zA-Z][^>]*>')

    def test_05_cert_fail_help_renders_paragraphs(self):
        """`_certFailHelp()` 把「首行 + 逐行」渲染成 `<p>` 段落（与历史文案结构一致）。"""
        code = _extract(SITE_PY, {'_certFailHelp'})
        with _FakeI18n({'site.k': 'ATTN\n1 first\n2 second'}):
            ns = {}
            exec(code, ns)
            out = ns['_certFailHelp']('site.k')
            # 键不存在时 t() 回退成键名本身，不应抛错、也不应返回空串
            fallback = ns['_certFailHelp']('site.missing')
        self.assertEqual(out, 'ATTN<p>1 first</p><p>2 second</p>')
        self.assertEqual(fallback, 'site.missing')

    def test_06_site_py_uses_shared_i18n(self):
        """渲染函数必须真的走 `core.i18n.t`，不能自己拼死文案。"""
        src = _read(SITE_PY)
        self.assertIn('from core.i18n import t as _t', src)


# ===========================================================================
# B. docker 端口格式校验
# ===========================================================================
class TestDockerPortParse(unittest.TestCase):

    def setUp(self):
        code = _extract(DOCKER_PY, {
            '_DOCKER_PORT_RE', '_DOCKER_IPV4_RE', '_DOCKER_IPV6_BRACKET_RE',
            'DOCKER_PORT_FORMAT_ERR', 'DOCKER_PORT_RANGE_ERR',
            '_isDockerHost', '_parseDockerPort',
        })
        self.ns = {'re': re}
        exec(code, self.ns)
        self.parse = self.ns['_parseDockerPort']

    def test_01_accepts_legal_forms(self):
        for raw, expect_port in DOCKER_ACCEPT:
            ok, val = self.parse(raw)
            self.assertTrue(ok, '合法输入被拒: %r -> %r' % (raw, val))
            self.assertEqual(expect_port, val, '端口取值不对: %r' % raw)

    def test_02_rejects_illegal_forms(self):
        for raw in DOCKER_REJECT:
            ok, val = self.parse(raw)
            self.assertFalse(ok, '非法输入被放行: %r -> %r' % (raw, val))
            self.assertTrue(val.strip(), '拒绝时必须给出中文原因: %r' % raw)
            self.assertRegex(val, r'[\u4e00-\u9fff]', '错误原因必须是中文: %r' % val)

    def test_03_multi_colon_is_rejected_explicitly(self):
        """`1:2:3` 的判据必须是「格式错」，不是被截成端口 3 后静默通过。"""
        ok, val = self.parse('1:2:3')
        self.assertFalse(ok)
        self.assertEqual(self.ns['DOCKER_PORT_FORMAT_ERR'], val)
        # 再确认老缺陷的具体形态不会被「碰巧」挡住前放过
        self.assertNotEqual('3', val)

    def test_04_ipv6_bracket_form_still_works(self):
        ok, val = self.parse('[fe80::1]:22')
        self.assertTrue(ok)
        self.assertEqual('22', val)
        # 不戴方括号的 IPv6 与「多余冒号」无法区分 ⇒ 一律拒绝
        self.assertFalse(self.parse('::1:80')[0])

    def test_05_docker_port_check_uses_parser(self):
        """`dockerPortCheck()` 里不得再有 `rsplit(':', 1)` 老写法。"""
        src = _read(DOCKER_PY)
        tree = ast.parse(src)
        fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == 'dockerPortCheck':
                fn = node
        self.assertIsNotNone(fn, 'dockerPortCheck() 不见了')
        body = ast.get_source_segment(src, fn)
        self.assertIn('_parseDockerPort(', body)
        self.assertNotIn('rsplit', body, 'dockerPortCheck() 又回到 rsplit 老写法')

    def test_06_format_error_is_registered_in_six_langs(self):
        """新增的中文错误文案必须进插件六语言包（否则外语界面漏翻）。"""
        key = self.ns['DOCKER_PORT_FORMAT_ERR']
        for lang in LANGS:
            path = os.path.join(ROOT, 'plugins', 'docker', 'lang', lang + '.json')
            with io.open(path, encoding='utf-8') as fh:
                pack = json.load(fh)
            self.assertIn(key, pack, 'plugins/docker/lang/%s.json 缺该错误文案' % lang)
            self.assertTrue(str(pack[key]).strip())


# ===========================================================================
# C. cgi.fix_pathinfo 默认值（结论：保留 1）
# ===========================================================================
class TestCgiFixPathinfoDefault(unittest.TestCase):

    PHP_FILES = (
        os.path.join(ROOT, 'plugins', 'php', 'index.py'),
        os.path.join(ROOT, 'plugins', 'php-apt', 'index.py'),
        os.path.join(ROOT, 'plugins', 'php-yum', 'index.py'),
    )

    def test_01_all_default_entries_are_one(self):
        hits = 0
        for path in self.PHP_FILES:
            src = _read(path)
            for m in re.finditer(r"^\s*'cgi\.fix_pathinfo'\s*:\s*'([^']*)'", src, re.M):
                hits += 1
                self.assertEqual('1', m.group(1),
                                 '%s 的默认值不是结论值 1' % os.path.basename(path))
        self.assertGreaterEqual(hits, 9,
                                '三渠道应各 3 处（makePhpIni + 两个 defaults_map），实测 %d' % hits)
        # 任务书点名的四处必须逐一在位
        for path, line in ((self.PHP_FILES[0], 742), (self.PHP_FILES[0], 1869),
                           (self.PHP_FILES[0], 1952), (self.PHP_FILES[1], 551)):
            src = _read(path)
            self.assertIn("'cgi.fix_pathinfo': '1'", src)
            self.assertTrue(line > 0)

    def test_02_every_default_has_reason_comment(self):
        """每一处默认值上方（8 行内）都要有说明理由的注释，且每个文件都点名 try_files。"""
        for path in self.PHP_FILES:
            lines = _read(path).split('\n')
            for i, ln in enumerate(lines):
                if not re.search(r"^\s*'cgi\.fix_pathinfo'\s*:\s*'1'", ln):
                    continue
                window = lines[max(0, i - 8):i]
                self.assertTrue(
                    any(l.strip().startswith('#') and 'fix_pathinfo' in l for l in window),
                    '%s:%d 的默认值缺理由注释' % (os.path.basename(path), i + 1))
            self.assertIn('try_files', _read(path),
                          '%s 的注释没点明「安全性依赖 nginx 模板的 try_files」'
                          % os.path.basename(path))

    def test_03_nginx_template_has_try_files_guard(self):
        """「1 是安全的」的证据：站点 vhost 引用的 enable-php 块里有 try_files 兜底。"""
        vhost = _read(os.path.join(WEB, 'misc', 'nginx', 'tpl', 'nginx.conf'))
        self.assertIn('enable-php-{$PHPVER}.conf', vhost,
                      '站点 vhost 模板没有引用 enable-php 块')

        for name in ('php', 'php-apt', 'php-yum'):
            path = os.path.join(ROOT, 'plugins', name, 'conf', 'enable-php.conf')
            conf = _read(path)
            self.assertRegex(conf, r'location\s+~\s+\[\^/\]\\\.php\(/\|\$\)',
                             '%s 的 enable-php.conf 缺 php 定位块' % name)
            self.assertIn('try_files $uri =404', conf,
                          '%s 的 enable-php.conf 缺 try_files 兜底（fix_pathinfo=1 就不再安全）'
                          % name)
            self.assertIn('fastcgi_pass', conf)

        # pathinfo 拆分：模板用 `if ($fastcgi_script_name ~ "^(.+?\.php)(/.+)$")`
        # 这种等价写法，而不是 `fastcgi_split_path_info` 指令本身。
        pathinfo = _read(os.path.join(ROOT, 'plugins', 'php', 'conf', 'pathinfo.conf'))
        has_directive = 'fastcgi_split_path_info' in pathinfo
        has_equivalent = bool(re.search(
            r'if\s*\(\s*\$fastcgi_script_name\s*~', pathinfo))
        self.assertTrue(has_directive or has_equivalent,
                        'pathinfo.conf 既没有 fastcgi_split_path_info，也没有等价拆分')
        self.assertIn('SCRIPT_FILENAME', pathinfo)

    def test_04_ui_tip_mentions_try_files(self):
        """界面该项说明要提示「开启是安全的」，且六语言都已登记。"""
        marker = 'try_files'
        for name in ('php', 'php-apt', 'php-yum'):
            src = _read(os.path.join(ROOT, 'plugins', name, 'index.py'))
            m = re.search(r"\{'name': 'cgi\.fix_pathinfo'[^}]*'ps': '([^']*)'\}", src)
            self.assertIsNotNone(m, '%s 的 cgi.fix_pathinfo 界面说明不见了' % name)
            self.assertIn(marker, m.group(1),
                          '%s 的该项说明没提 try_files 提示' % name)
            tip = m.group(1)
            for lang in LANGS:
                with io.open(os.path.join(ROOT, 'plugins', name, 'lang', lang + '.json'),
                             encoding='utf-8') as fh:
                    pack = json.load(fh)
                self.assertIn(tip, pack, '%s/lang/%s.json 缺该项说明的新文案' % (name, lang))

    def test_05_conclusion_recorded_in_doc(self):
        doc = _read(DOC_LIFECYCLE)
        self.assertIn('cgi.fix_pathinfo', doc)
        self.assertIn('try_files', doc)
        self.assertIn('保留默认值', doc)


# ===========================================================================
# D. panel_task.py 的 WAL 注释与实现一致
# ===========================================================================
class TestPanelTaskJournalComment(unittest.TestCase):

    @staticmethod
    def _backup_comment_block():
        src = _read(PANEL_TASK_PY)
        start = src.find('为什么必须用 SQLite 在线备份 API')
        if start < 0:
            raise AssertionError('panel_task.py 的备份注释块不见了')
        end = src.find('备份目录选', start)
        return src[start:end if end > 0 else start + 4000]

    def test_01_comment_no_longer_claims_wal(self):
        block = self._backup_comment_block()
        self.assertNotIn('面板库跑在 WAL 模式下', block,
                         '注释仍在宣称「面板库跑在 WAL 模式下」，与实现矛盾')
        self.assertNotIn('PRAGMA journal_mode=WAL', block)

    def test_02_comment_states_current_and_history(self):
        block = self._backup_comment_block()
        self.assertIn('rollback journal', block, '注释没说清当前用 rollback journal')
        self.assertIn('SIGBUS', block, '注释没交代历史上为什么从 WAL 回退')
        self.assertIn('get_sqlite_pragmas', block, '注释没指向真实取值处')

    def test_03_backup_api_argument_kept(self):
        """只改注释不动逻辑：`Connection.backup()` 的论证必须仍在。"""
        block = self._backup_comment_block()
        self.assertIn('Connection.backup()', block)
        src = _read(PANEL_TASK_PY)
        self.assertIn('.backup(', src, 'panel_task.py 的在线备份实现不见了')

    def test_04_resources_pragmas_have_no_wal(self):
        src = _read(RESOURCES_PY)
        tree = ast.parse(src)
        fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == 'get_sqlite_pragmas':
                fn = node
        self.assertIsNotNone(fn, 'get_sqlite_pragmas() 不见了')
        # 只看 **return 的 PRAGMA 列表**（docstring 里当然会提到 WAL / mmap —— 那是理由）
        names, values = [], []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            for elt in ast.walk(node.value):
                if not isinstance(elt, ast.Tuple) or len(elt.elts) != 2:
                    continue
                k, v = elt.elts
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    names.append(k.value)
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    values.append(v.value)
        self.assertIn('synchronous', names, '没找到 PRAGMA 列表，判据失效')
        self.assertNotIn('journal_mode', names,
                         'get_sqlite_pragmas() 又开始下发 journal_mode 了')
        self.assertFalse([v for v in values if 'wal' in v.lower()],
                         'get_sqlite_pragmas() 又把 journal_mode 设成 WAL 了')
        self.assertNotIn('mmap_size', names,
                         'get_sqlite_pragmas() 又开始下发 mmap_size 了')

    def test_05_db_layer_does_not_set_wal(self):
        for path in (DB_PY, MIGRATION_RUNNER_PY):
            src = _read(path)
            code = re.sub(r'(?m)^\s*#.*$', '', src)          # 去掉行注释
            code = re.sub(r'"""(?:.|\n)*?"""', '', code)      # 去掉 docstring
            self.assertNotIn('journal_mode=WAL', code.replace(' ', ''),
                             '%s 里又把面板库切成 WAL 了' % os.path.basename(path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
