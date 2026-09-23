# -*- coding: utf-8 -*-
"""
插件 i18n 升级回归守卫（标准库 unittest，不依赖 pytest）

把本次升级锁死的红线固化成可重复执行的断言，防止后续改动回退：

  1. 六语言键集与 zh-CN 完全一致（键集漂移 = 漏翻/多键）
  2. 译文不含 HTML 标签
  2b. 全局语言包 HTML 红线（core.i18n.assert_no_html_in_translations）：
      白名单生效 + 白名单外必抛错（自证检测器有效）+ 启动自检不阻断启动
  3. 语言包无「脏键」（键里混入代码片段：HTML/JS 拼接/属性赋值/转义序列...）
  4. 语言包无「死键」（源码里已无任何引用的键）
  5. 所有 msgTpl(...) 调用内必须含 pt(...)（否则确认框永远显示中文）
  6. 所有 pt('字面量') / _t('字面量') 都能在语言包查到键
  7. translatePluginDOM 白名单位置的中文串 100% 有键
  8. 不存在「中文片段 + 变量 + 中文片段」的句中拼接（违反 {n} 模板化红线）
  9. 后端消息回退翻译 translateAny 已实现、已接入 layer.msg、行为测试通过
 10. 全局语言包：JSON 全部可解析 + 单文件内不混用 CRLF/LF；
     后端 returnJson 消息的「可翻译前缀」不含 HTML 且消息含中文时前缀也含中文
 11. zh-TW 无真简体字残留（插件包 + 全局包，需要 opencc，缺失则跳过）
 12. 插件 JS 语法全部通过（需要 node，缺失则跳过）
 13. 无 {0} 占位符 / pt() 只接受单参（含 index.html 全源扫描）

运行：
    python -m unittest discover -s test -p "test_plugins_i18n_upgrade.py" -v
    python test/test_plugins_i18n_upgrade.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGINS = os.path.join(REPO, 'plugins')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

sys.path.insert(0, os.path.join(HERE, 'i18n_scripts'))

NODE_CANDIDATES = [
    os.path.expanduser('~/.workbuddy-ai/binaries/node/versions/22.22.2-2/node.exe'),
    r'C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe',
]
PY_OPENCC_CANDIDATES = [
    os.path.expanduser('~/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe'),
    r'C:\Users\wzucc\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe',
]


# --------------------------------------------------------------------------
# 公共工具
# --------------------------------------------------------------------------
def plugin_names():
    if not os.path.isdir(PLUGINS):
        return []
    return sorted(
        d for d in os.listdir(PLUGINS)
        if os.path.isdir(os.path.join(PLUGINS, d))
        and os.path.isfile(os.path.join(PLUGINS, d, 'lang', 'zh-CN.json'))
    )


def load_lang(name, lang):
    p = os.path.join(PLUGINS, name, 'lang', lang + '.json')
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def read(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def plugin_js_files(name):
    out = []
    for sub in ('js', os.path.join('static', 'js')):
        d = os.path.join(PLUGINS, name, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith('.js') and not fn.endswith('.i18n.bak'):
                    out.append(os.path.join(d, fn))
    return out


def strip_js_comments(js):
    """去掉 // 与 /* */ 注释，保留字符串内容"""
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in '\'"':
            q = c
            out.append(c)
            i += 1
            while i < n:
                out.append(js[i])
                if js[i] == '\\':
                    if i + 1 < n:
                        out.append(js[i + 1])
                    i += 2
                    continue
                if js[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n:
            if js[i + 1] == '/':
                while i < n and js[i] != '\n':
                    i += 1
                continue
            if js[i + 1] == '*':
                i += 2
                while i + 1 < n and not (js[i] == '*' and js[i + 1] == '/'):
                    i += 1
                i += 2
                continue
        out.append(c)
        i += 1
    return ''.join(out)


def mask_global_t(js):
    """屏蔽全局 t(...) 调用（其第二个参数是默认文案，不属于插件语言包）"""
    start = re.compile(r"(?<![\w.$])t\s*\(")
    out, last = [], 0
    for m in start.finditer(js):
        i, depth, n = m.end(), 1, len(js)
        while i < n and depth > 0:
            c = js[i]
            if c in '\'"':
                q = c
                i += 1
                while i < n:
                    if js[i] == '\\':
                        i += 2
                        continue
                    if js[i] == q:
                        break
                    i += 1
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            i += 1
        out.append(js[last:m.start()])
        out.append('__GT__')
        last = i
    out.append(js[last:])
    return ''.join(out)


# --------------------------------------------------------------------------
# 1. 键集一致性
# --------------------------------------------------------------------------
class TestKeySetConsistency(unittest.TestCase):
    def test_six_languages_share_same_keyset(self):
        problems = []
        for name in plugin_names():
            base = set(load_lang(name, 'zh-CN').keys())
            for lang in LANGS[1:]:
                other = set(load_lang(name, lang).keys())
                if other != base:
                    problems.append('%s/%s 差异 %d 条（缺 %d / 多 %d）' % (
                        name, lang, len(base ^ other),
                        len(base - other), len(other - base)))
        self.assertEqual([], problems, '六语言键集必须与 zh-CN 完全一致')


# --------------------------------------------------------------------------
# 2. 译文不含 HTML
# --------------------------------------------------------------------------
HTML_TAG = re.compile(
    r'<(?:br|hr|p|div|span|b|strong|i|em|a|ul|ol|li|code|pre|small|'
    r'table|thead|tbody|tr|td|th|h[1-6])\b[^>]*>', re.I)


class TestNoHtmlInTranslations(unittest.TestCase):
    def test_values_have_no_html(self):
        bad = []
        for name in plugin_names():
            for lang in LANGS:
                for k, v in load_lang(name, lang).items():
                    if isinstance(v, str) and HTML_TAG.search(v):
                        bad.append('%s/%s %r -> %r' % (name, lang, k[:40], v[:60]))
        self.assertEqual([], bad[:20], '译文严禁包含 HTML 标签')


# --------------------------------------------------------------------------
# 2b. 全局语言包 HTML 红线（core.i18n.assert_no_html_in_translations）
# --------------------------------------------------------------------------
class TestGlobalHtmlRedline(unittest.TestCase):
    """`web/core/i18n.py:assert_no_html_in_translations` 是「译文禁含 HTML」红线的
    唯一权威判定。此前它**定义了却全库零调用**，等于红线没有运行时保护。
    本组断言锁死：① 白名单生效、不误报；② 白名单外混入 HTML 必须抛错
    （自证检测器有效，避免「恒返回 0」的假绿）；③ 启动自检已接入且不阻断启动。
    """

    def _i18n(self):
        web = os.path.join(REPO, 'web')
        if web not in sys.path:
            sys.path.insert(0, web)
        import importlib
        import core.i18n as i18n
        importlib.reload(i18n)
        return i18n

    def test_allowlist_contains_countdown_key(self):
        i18n = self._i18n()
        self.assertIn('index.reboot_panel_wait_msg', i18n.HTML_ALLOWLIST,
                      '面板重启倒计时键必须在 HTML 白名单中，否则自检会误报')

    def test_no_violation_in_repo(self):
        i18n = self._i18n()
        self.assertEqual(
            [], i18n.assert_no_html_in_translations(raise_on_error=False),
            '全局语言包存在违反「译文禁含 HTML」红线的条目')

    def test_detector_actually_fires(self):
        """自证：白名单**外**的键含 HTML 时必须抛 ValueError。"""
        i18n = self._i18n()
        real = i18n.get_cached_json

        def fake(sec, lang):
            if sec == 'public' and lang == 'en':
                return {'boom': '<b>oops</b>'}
            return {}

        i18n.get_cached_json = fake
        try:
            with self.assertRaises(ValueError):
                i18n.assert_no_html_in_translations(raise_on_error=True)
        finally:
            i18n.get_cached_json = real

    def test_allowlisted_key_does_not_fire(self):
        """自证：白名单内的键含 HTML 时**不得**抛错。"""
        i18n = self._i18n()
        real = i18n.get_cached_json

        def fake(sec, lang):
            if sec == 'template' and lang == 'en':
                return {'index': {'reboot_panel_wait_msg':
                                  'wait... <span id="restart-countdown">{1}</span> s'}}
            return {}

        i18n.get_cached_json = fake
        try:
            self.assertEqual([], i18n.assert_no_html_in_translations(raise_on_error=True))
        finally:
            i18n.get_cached_json = real

    def test_warn_variant_never_raises(self):
        """启动自检只告警不阻断——面板必须能起来。"""
        i18n = self._i18n()
        real = i18n.get_cached_json

        def fake(sec, lang):
            if sec == 'public' and lang == 'en':
                return {'boom': '<b>oops</b>'}
            return {}

        i18n.get_cached_json = fake
        try:
            errs = i18n.warn_if_html_in_translations()  # 不得抛异常
            self.assertTrue(errs, '告警变体应返回违规清单')
        finally:
            i18n.get_cached_json = real

    def test_startup_hook_wired(self):
        src = read(os.path.join(REPO, 'web', 'admin', '__init__.py'))
        self.assertIn('warn_if_html_in_translations', src,
                      '启动自检未接入 web/admin/__init__.py')


# --------------------------------------------------------------------------
# 3. 脏键
# --------------------------------------------------------------------------
DIRTY_RULES = [
    ('HTML标签', re.compile(r'<[a-zA-Z/][^>]*>')),
    ('JS拼接片段', re.compile(r"'\s*\+|\+\s*'")),
    ('JS多参残留', re.compile(r"'\s*,\s*'")),
    ('JS调用', re.compile(r'\bpt\(|\bmsgTpl\(|\$\(|\blayer\.|\.each\(|function\s*\(')),
    ('属性赋值', re.compile(
        r"\b(class|placeholder|title|style|href|onclick|onchange|value|type|"
        r"colspan|rowspan|id|src)\s*=\s*['\"]")),
    ('转义序列', re.compile(r'\\n|\\r|\\t|\\u[0-9a-fA-F]{4}')),
    ('CSS片段', re.compile(r'[a-z-]{3,}\s*:\s*[^;{]+;')),
    # 首尾引号：仅当整个键被同一对引号包起来才算提取残留
    ('首尾引号', re.compile(r"^(['\"]).*\1$")),
    ('纯标点', re.compile(r'^[\s\W_]+$')),
    ('变量拼接', re.compile(r"'\s*\+\s*[A-Za-z_$]|[A-Za-z_$0-9\]\)]\s*\+\s*'")),
]
# HTML 实体里的分号不是 CSS 声明结尾
ENTITY = re.compile(r'&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);')


class TestNoDirtyKeys(unittest.TestCase):
    def test_lang_keys_are_plain_text(self):
        bad = []
        for name in plugin_names():
            for k in load_lang(name, 'zh-CN'):
                plain = ENTITY.sub('', k)
                for cat, pat in DIRTY_RULES:
                    target = plain if cat == 'CSS片段' else k
                    if pat.search(target):
                        bad.append('%s [%s] %r' % (name, cat, k[:70]))
                        break
        self.assertEqual([], bad[:20], '语言包键不得含功能代码片段')


# --------------------------------------------------------------------------
# 4. 死键
# --------------------------------------------------------------------------
SKIP_DIRS = {'__pycache__', 'versions', 'lang', '.git', 'node_modules'}
SKIP_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2',
            '.ttf', '.eot', '.zip', '.gz', '.tar', '.bz2', '.7z', '.rar',
            '.pyc', '.so', '.dll', '.exe', '.mp4', '.webp', '.pdf')


def _walk_text(root):
    parts = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith('.i18n.bak') or fn.lower().endswith(SKIP_EXT):
                continue
            try:
                parts.append(read(os.path.join(cur, fn)))
            except Exception:
                pass
    return '\n'.join(parts)


_PY_CJK_STR = re.compile(r"(['\"])((?:[^'\"\\\n]|\\.)*)\1")


def backend_literals(pdir):
    """插件 .py 里所有含中文的字符串字面量（后端 returnJson 消息的来源）"""
    out = []
    for cur, dirs, files in os.walk(pdir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'versions', 'lang')]
        for fn in files:
            if not fn.endswith('.py'):
                continue
            try:
                src = read(os.path.join(cur, fn))
            except Exception:
                continue
            for m in _PY_CJK_STR.finditer(src):
                s = m.group(2)
                if re.search(r'[\u4e00-\u9fff]', s):
                    out.append(s)
    return out


class TestNoDeadKeys(unittest.TestCase):
    """死键 = 语言包里源码完全无引用的键。

    例外（保留）：后端 returnJson 消息的静态前缀——前端 layer.msg 拿到的是
    「前缀 + 变量」，静态扫描看不到完整引用，故只要该键是插件 .py 中某个
    中文字面量的子串，即视为「后端预留」。
    """

    def test_every_key_is_referenced(self):
        try:
            import i18n_dead_keys as dk
        except Exception as e:                     # pragma: no cover
            self.skipTest('无法导入 i18n_dead_keys: %s' % e)
        bad = []
        for name in plugin_names():
            reserved = backend_literals(os.path.join(PLUGINS, name))
            for k in dk.dead_keys(name):
                if any(k in s for s in reserved):
                    continue
                bad.append('%s %r' % (name, k[:70]))
        self.assertEqual([], bad[:20], '语言包存在源码未引用的死键')


# --------------------------------------------------------------------------
# 5. msgTpl 必须含 pt
# --------------------------------------------------------------------------
def msgTpl_first_args(js):
    """返回所有 msgTpl( 调用的第一个实参文本"""
    out = []
    for m in re.finditer(r'\bmsgTpl\s*\(', js):
        i, depth, n = m.end(), 1, len(js)
        start = i
        while i < n and depth > 0:
            c = js[i]
            if c in '\'"':
                q = c
                i += 1
                while i < n:
                    if js[i] == '\\':
                        i += 2
                        continue
                    if js[i] == q:
                        break
                    i += 1
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 1:
                break
            i += 1
        out.append(js[start:i])
    return out


class TestMsgTplWrapsPt(unittest.TestCase):
    def test_msgTpl_first_arg_contains_pt(self):
        bad = []
        for name in plugin_names():
            for jf in plugin_js_files(name):
                js = strip_js_comments(read(jf))
                for arg in msgTpl_first_args(js):
                    if 'pt(' not in arg and '_t(' not in arg:
                        bad.append('%s :: msgTpl(%s...)' % (
                            os.path.relpath(jf, REPO).replace('\\', '/'),
                            arg.strip()[:70]))
        self.assertEqual([], bad[:20], 'msgTpl 的第一个参数必须包 pt(...)')


# --------------------------------------------------------------------------
# 6. pt('字面量') 必须有键
# --------------------------------------------------------------------------
PT_LIT = re.compile(
    r"\b(?:pt|_t)\s*\(\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")")


class TestPtLiteralsHaveKeys(unittest.TestCase):
    def test_every_pt_literal_is_a_key(self):
        bad = []
        for name in plugin_names():
            keys = set(load_lang(name, 'zh-CN'))
            for jf in plugin_js_files(name):
                js = mask_global_t(strip_js_comments(read(jf)))
                for m in PT_LIT.finditer(js):
                    s = m.group(1) if m.group(1) is not None else m.group(2)
                    if not s or not re.search(r'[\u4e00-\u9fa5]', s):
                        continue
                    if s not in keys:
                        bad.append('%s %r' % (name, s[:70]))
        self.assertEqual([], sorted(set(bad))[:20],
                         'pt()/  _t() 的字面量必须在语言包中存在')


# --------------------------------------------------------------------------
# 7. translatePluginDOM 白名单位置中文串必须有键
# --------------------------------------------------------------------------
class TestDomWhitelistCoverage(unittest.TestCase):
    def test_whitelisted_dom_text_has_keys(self):
        try:
            import i18n_dom_key_coverage as cov
        except Exception as e:                     # pragma: no cover
            self.skipTest('无法导入 i18n_dom_key_coverage: %s' % e)
        bad = []
        for name in plugin_names():
            r = cov.analyze(name)
            if not r:
                continue
            total, miss = r
            for s in miss:
                bad.append('%s %r' % (name, s[:70]))
        self.assertEqual([], bad[:20],
                         'translatePluginDOM 白名单位置的中文串必须有语言包键')

    def test_all_dom_text_nodes_have_keys(self):
        """全量模式：所有含中文的文本节点 / placeholder / title 都必须有语言包键。

        背景：i18n.js 的 1.3 规则用 TreeWalker 扫**所有文本节点**（父节点非 skip 标签即处理），
        1.1 规则用 `[placeholder], [title]` 通配**任意标签**。因此凡是静态 HTML 里
        「含中文的文本节点 / placeholder / title」都必须有键 —— 缺一个，该处界面在
        非中文语言下就仍是中文，而且语言包与门禁都不会报错（静默失效）。
        oracle 是语言包本身（独立于被守护的框架代码）。
        """
        try:
            import i18n_dom_key_coverage as cov
        except Exception as e:                     # pragma: no cover
            self.skipTest('无法导入 i18n_dom_key_coverage: %s' % e)
        bad = []
        scanned = 0
        for name in plugin_names():
            r = cov.analyze_full(name)
            if not r:
                continue
            scanned += r[0]
            for s in r[1]:
                bad.append('%s %r' % (name, s[:70]))
        # 仓库级契约：扫描面过小说明护栏退化成了「真空通过」
        self.assertGreaterEqual(scanned, 200,
                                '扫描到的中文文本节点过少（%d），护栏可能失效' % scanned)
        self.assertEqual([], bad[:20],
                         '静态 HTML 里含中文的文本节点/属性值必须有语言包键')

    def test_analyzer_actually_fires(self):
        """变异自证：给分析器喂一段「键肯定不存在」的 HTML，它必须报出来。"""
        try:
            import i18n_dom_key_coverage as cov
        except Exception as e:                     # pragma: no cover
            self.skipTest('无法导入 i18n_dom_key_coverage: %s' % e)
        src = ('<div class="x"><span>这个键肯定不存在XYZ</span>'
               '<p title="另一个不存在的键XYZ">ok</p>'
               '<input placeholder="第三个不存在的键XYZ" />'
               '<script>var s = "脚本里的中文不该被收集XYZ";</script></div>')
        got = cov.collect_from_html(src)
        self.assertIn('这个键肯定不存在XYZ', got)
        self.assertIn('另一个不存在的键XYZ', got)
        self.assertIn('第三个不存在的键XYZ', got)
        self.assertNotIn('脚本里的中文不该被收集XYZ', got)

    def test_generic_text_node_fallback_wired(self):
        """框架形状契约：i18n.js 必须保留「通用文本节点兜底」并接入 doTranslateNodes。

        这是**形状检查**（不是行为检查）：白名单是枚举式的，一旦有人删掉通用兜底
        或把 `[placeholder], [title]` 改回枚举标签，自定义说明容器就会重新变成不翻译。
        行为层面的金标准探针见 testsuite/js/dom_i18n_probe.js（需 jsdom）。
        """
        js = read(os.path.join(REPO, 'web', 'static', 'app', 'i18n.js'))
        self.assertIn('function translateLeafTextNodes', js,
                      'i18n.js 缺少通用文本节点兜底 translateLeafTextNodes')
        # 必须是**调用点**：`(?<!function )` 排除函数定义本身，
        # 否则「只留定义、删掉调用」这种退化会蒙混过关（变异测试已钉住）。
        self.assertRegex(js, r'(?<!function )translateLeafTextNodes\s*\(\s*\$scope\s*\)',
                         '通用文本节点兜底未接入 doTranslateNodes')
        self.assertRegex(js, r"find\(\s*'\[placeholder\],\s*\[title\]'\s*\)",
                         'title/placeholder 规则退回了枚举标签白名单')


# --------------------------------------------------------------------------
# 8. 无句中拼接
# --------------------------------------------------------------------------
class TestNoMidSentenceConcat(unittest.TestCase):
    def test_no_sentence_split_by_variable(self):
        try:
            import i18n_concat_audit as ca
        except Exception as e:                     # pragma: no cover
            self.skipTest('无法导入 i18n_concat_audit: %s' % e)
        bad = []
        for name in plugin_names():
            for jf in ca.find_js_files(os.path.join(PLUGINS, name)):
                src = ca.strip_comments(read(jf))
                for m in ca.PAT.finditer(src):
                    g = m.groups()
                    a, c = g[0] or g[1] or g[2], g[4] or g[5] or g[6]
                    if ca.boundary_ok(a, c):
                        continue
                    bad.append('%s :: %r + %s + %r' % (
                        os.path.relpath(jf, REPO).replace('\\', '/'),
                        a[-24:], g[3], c[:24]))
        self.assertEqual([], bad[:20],
                         '句子被变量劈开，应改用 msgTpl(pt("...{1}..."), [x]) 模板')


# --------------------------------------------------------------------------
# 8b. pt() 占位符与参数个数正确
# --------------------------------------------------------------------------
_SKIP_DIRS = {'__pycache__', 'versions', 'lang', '.git', 'node_modules'}
_SRC_EXT = ('.js', '.html', '.htm', '.tpl')
# pt('...') / _t('...')，负向断言避免匹配到 obj.pt( 或 ._t(
PT_CALL = re.compile(r"(?<![\w$.])(?:pt|_t)\s*\(\s*(['\"])((?:[^'\"\\]|\\.)*)\1")
PT_MULTI = re.compile(r"(?<![\w$.])(?:pt|_t)\s*\(\s*(['\"])((?:[^'\"\\]|\\.)*?)\1\s*,")


def plugin_source_files(name):
    """插件下全部可能承载前端文案的源文件（含 index.html，不含 lang/）"""
    out = []
    for root, dirs, files in os.walk(os.path.join(PLUGINS, name)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in sorted(files):
            if fn.endswith('.i18n.bak') or not fn.endswith(_SRC_EXT):
                continue
            out.append(os.path.join(root, fn))
    return out


class TestPtCallShape(unittest.TestCase):
    def test_no_zero_based_placeholder(self):
        """msgTpl() 从 {1} 开始替换，{0} 永远填不上，用户会看到字面 "{0}"。"""
        bad = []
        for name in plugin_names():
            for f in plugin_source_files(name):
                src = read(f)
                for m in PT_CALL.finditer(src):
                    if '{0}' in m.group(2):
                        bad.append('%s :: %r' % (
                            os.path.relpath(f, REPO).replace('\\', '/'), m.group(2)[:60]))
        self.assertEqual([], bad[:20],
                         'pt() 键含 {0} 占位符，应改为 {1} 起始（msgTpl 约定）')

    def test_pt_takes_single_argument(self):
        """pt(key) 只接受 1 个参数；多参调用会静默丢参，用户看到字面 {1}。"""
        bad = []
        for name in plugin_names():
            for f in plugin_source_files(name):
                src = read(f)
                for m in PT_MULTI.finditer(src):
                    bad.append('%s :: %r' % (
                        os.path.relpath(f, REPO).replace('\\', '/'), m.group(2)[:60]))
        self.assertEqual([], bad[:20],
                         'pt() 被传入多个参数，应改用 msgTpl(pt("...{1}..."), [x])')


# --------------------------------------------------------------------------
# 9. 后端消息回退翻译（YfI18n.translateAny）
# --------------------------------------------------------------------------
class TestBackendMessageFallback(unittest.TestCase):
    """插件后端 returnJson 返回的中文消息由 layer.msg 直接展示，
    其原文即插件语言包的键，需由 YfI18n.translateAny() 兜底翻译。"""

    def test_translate_any_is_exported(self):
        src = read(os.path.join(REPO, 'web', 'static', 'app', 'i18n.js'))
        self.assertIn('function translateAny(', src, 'i18n.js 缺少 translateAny 实现')
        self.assertIn('translateAny: translateAny', src, 'translateAny 未挂到 YfI18n 导出对象')

    def test_layer_msg_uses_fallback(self):
        src = read(os.path.join(REPO, 'web', 'static', 'app', 'public.js'))
        self.assertIn('YfI18n.translateAny', src,
                      'layer.msg 拦截器未接入 translateAny 回退')

    def test_translate_any_behaviour(self):
        exe = next((p for p in NODE_CANDIDATES if os.path.isfile(p)), None)
        if not exe:
            self.skipTest('未找到 node')
        script = os.path.join(HERE, 'i18n_scripts', 'tools', 'test_translate_any.js')
        if not os.path.isfile(script):
            self.skipTest('缺少 test_translate_any.js')
        r = subprocess.run([exe, script], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        self.assertEqual(0, r.returncode, 'translateAny 行为测试失败:\n' + r.stdout)
        self.assertIn('ALL PASS', r.stdout)


# --------------------------------------------------------------------------
# 10. 全局语言包完整性 + 后端消息前缀契约
# --------------------------------------------------------------------------
class TestGlobalPackIntegrity(unittest.TestCase):
    def test_all_json_parse_and_no_mixed_line_endings(self):
        """全局语言包须全部可解析，且单个文件内不得混用 CRLF / LF。

        .gitattributes 声明 `*.json text eol=lf`，core.autocrlf=true 时工作区
        检出为 CRLF。若工具写入时只对改动行用 LF，就会出现「半 CRLF 半 LF」，
        虽然 JSON 仍可解析，但会让后续 diff 噪音爆炸。
        """
        base = os.path.join(REPO, 'web', 'static', 'language')
        if not os.path.isdir(base):
            self.skipTest('未找到全局语言包目录')
        mixed, broken = [], []
        for lang in sorted(os.listdir(base)):
            d = os.path.join(base, lang)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith('.json'):
                    continue
                p = os.path.join(d, fn)
                with open(p, 'rb') as f:
                    b = f.read()
                try:
                    json.loads(b.decode('utf-8'))
                except Exception as e:
                    broken.append('%s/%s: %s' % (lang, fn, e))
                crlf = b.count(b'\r\n')
                lone = len(re.findall(rb'(?<!\r)\n', b))
                if crlf and lone:
                    mixed.append('%s/%s (CRLF=%d loneLF=%d)' % (lang, fn, crlf, lone))
        self.assertEqual([], broken[:10], '全局语言包存在无法解析的 JSON')
        self.assertEqual([], mixed[:10], '全局语言包存在混合换行文件')


class TestBackendMsgPrefix(unittest.TestCase):
    def test_prefix_has_no_html_and_contains_cjk(self):
        """后端 returnJson 消息的「可翻译前缀」不得含 HTML，且消息含中文时前缀也须含中文。

        前缀 = 消息首个 : / ：（含）之前的全部内容，会被 translateAny 当作语言包键。
        """
        sys.path.insert(0, os.path.join(REPO, 'scripts'))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'verify_i18n', os.path.join(REPO, 'scripts', 'verify_i18n.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bad = []
        for name in plugin_names():
            p = os.path.join(PLUGINS, name, 'index.py')
            if not os.path.isfile(p):
                continue
            with open(p, encoding='utf-8', errors='replace') as f:
                src = f.read()
            for line, why, prefix in mod._scan_backend_msg_prefix(src):
                bad.append('%s/index.py:%d %s %r' % (name, line, why, prefix[:60]))
        self.assertEqual([], bad[:15], '后端消息前缀违反契约')


class TestBackendMsgKeyCoverage(unittest.TestCase):
    """后端中文消息必须能查到语言包键（复刻 translateAny 的三级匹配）。

    与 test_prefix_has_no_html_and_contains_cjk 互补：
      · 前缀检查管「前缀形态对不对」；
      · 本检查管「前缀到底有没有键」——有前缀无键时外语界面照样漏翻。
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'verify_i18n', os.path.join(REPO, 'scripts', 'verify_i18n.py'))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_no_uncovered_backend_message(self):
        problems = self.mod.check_backend_msg_key({})
        self.assertEqual([], problems[:15],
                         '后端中文消息查不到语言包键（外语界面会漏翻）')

    def test_exceptions_are_documented(self):
        """每条例外必须写明理由，且指向真实存在的插件语言包。"""
        for (name, lit), why in self.mod.BACKEND_MSG_KEY_EXCEPTIONS.items():
            self.assertTrue(why and len(why) > 8,
                            '例外 %s/%r 缺少说明' % (name, lit))
            self.assertTrue(
                os.path.isfile(os.path.join(PLUGINS, name, 'lang', 'zh-CN.json')),
                '例外指向不存在的插件: %s' % name)

    def test_detector_actually_fires(self):
        """检测器自证：对已知答案夹具必须恰好报出 EXPECT_MISS_LINES，且不误报合法写法。

        只断言「结果为 0」的守卫有共同风险——写错了恒返回 0，永远显示全绿。
        """
        fixture = os.path.join(HERE, 'i18n_scripts', 'tools', 'fixtures',
                               'backend_msg_key.py')
        if not os.path.isfile(fixture):
            self.skipTest('缺少夹具 backend_msg_key.py')
        with open(fixture, encoding='utf-8') as f:
            src = f.read()
        ns = {}
        exec(compile(src, fixture, 'exec'), ns)
        keys = {'扫描完成', '获取日志失败:', '读取日志失败: ', '操作失败:'}
        got = [ln for ln, _ in self.mod._scan_backend_msg_keys(src, keys)]
        self.assertEqual(list(ns['EXPECT_MISS_LINES']), got,
                         '检测器报出的行号与夹具期望不一致')
        self.assertEqual(set(), set(got) & set(ns['EXPECT_OK_LINES']),
                         '检测器误报了合法写法')


# --------------------------------------------------------------------------
# 11. zh-TW 无简体残留
# --------------------------------------------------------------------------
# 全局 zh-TW 包残留扫描器（跑在带 opencc 的隔离 venv 里）。
# **两个扫描面缺一不可**：
#   - `.json` 载体面（后端读的是它）
#   - `lan.js` 源面（前端唯一真源；`.json` 由它派生）
# 只扫载体面会漏掉「简体藏在纯注释 / 纯属性里、派生后看不见」的键 ——
# 2026-09-22 实测 `index.disk`（`<!-- 磁盘IO -->`）等 7 个叶子因此长期漏检。
_ZH_TW_SCAN_SCRIPT = r'''
import json, os, re, sys
from opencc import OpenCC
s2t = OpenCC("s2t"); s2twp = OpenCC("s2twp")
B = __GDIR__

def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, str):
        yield o

def bad(v):
    return s2t.convert(v) != v and s2twp.convert(v) != v

bad_list = []
for f in sorted(os.listdir(B)):
    if not f.endswith(".json"):
        continue
    for v in leaves(json.load(open(os.path.join(B, f), encoding="utf-8"))):
        if bad(v):
            bad_list.append(f + " " + repr(v[:60]))

# lan.js 是唯一真源，必须一起扫（lan.js 里没有 \uXXXX 转义，直接正则取值即可）
LAN_JS = os.path.join(B, "lan.js")
if os.path.isfile(LAN_JS):
    raw = open(LAN_JS, encoding="utf-8").read()
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', raw):
        if bad(m.group(2)):
            bad_list.append("lan.js " + repr(m.group(2)[:60]))

for b in bad_list[:20]:
    print(b)
print("COUNT=" + str(len(bad_list)))
'''


def opencc_exe():
    """带 opencc 的隔离 venv 解释器；找不到返回 None（用例应 skipTest）。"""
    return next((p for p in PY_OPENCC_CANDIDATES if os.path.isfile(p)), None)


def zh_tw_scan(exe, gdir):
    """在隔离 venv 里扫一个 zh-TW 包目录，返回 (命中数, stdout, returncode)。"""
    script = _ZH_TW_SCAN_SCRIPT.replace('__GDIR__', repr(gdir))
    r = subprocess.run([exe, '-c', script], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    cnt = 0
    for line in r.stdout.splitlines():
        if line.startswith('COUNT='):
            cnt = int(line.split('=')[1])
    return cnt, r.stdout, r.returncode


class TestZhTwNoSimplified(unittest.TestCase):
    def test_no_simplified_residue(self):
        exe = next((p for p in PY_OPENCC_CANDIDATES if os.path.isfile(p)), None)
        if not exe:
            self.skipTest('未找到带 opencc 的隔离 venv')
        script = r'''
import json, os, sys
sys.path.insert(0, __SCRIPTS__)
from opencc import OpenCC
s2t = OpenCC("s2t"); s2twp = OpenCC("s2twp")
P = __PLUGINS__
bad = []
for n in sorted(os.listdir(P)):
    f = os.path.join(P, n, "lang", "zh-TW.json")
    if not os.path.isfile(f):
        continue
    for k, v in json.load(open(f, encoding="utf-8")).items():
        if not isinstance(v, str):
            continue
        # s2t 变化 = 有真简体字；再看 s2twp 能否修（修不了的是 s2t 变体映射误报，如 峰->峯）
        if s2t.convert(v) != v and s2twp.convert(v) != v:
            bad.append(n + " " + repr(v[:60]))
for b in bad[:20]:
    print(b)
print("COUNT=" + str(len(bad)))
'''
        script = script.replace('__SCRIPTS__', repr(os.path.join(HERE, 'i18n_scripts')))
        script = script.replace('__PLUGINS__', repr(PLUGINS))
        r = subprocess.run([exe, '-c', script], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        if r.returncode != 0:
            self.skipTest('opencc 子进程失败: %s' % (r.stderr or '')[:200])
        cnt = 0
        for line in r.stdout.splitlines():
            if line.startswith('COUNT='):
                cnt = int(line.split('=')[1])
        self.assertEqual(0, cnt, 'zh-TW 仍有真简体字残留:\n' + r.stdout)

    def test_global_pack_no_simplified_residue(self):
        """全局语言包 web/static/language/zh-TW/** 也须无简体残留。

        全局包是**嵌套结构**（template.json 顶层仅 66 键但 9341 个叶子），
        插件侧脚本不适用，需递归扫描。

        **同时扫 `lan.js`**：它是唯一真源，`.json` 由它派生。只扫 `.json` 会漏掉
        「源里有简体、但载体因为没这个键而看不见」的情形 —— 2026-09-22 实测
        漏掉 119 个叶子，收敛（lan.js 单源派生）把它们带进载体后一次性踩出
        238 条红线（HEAD 为 0）。扫源即可从根上堵住。
        另外还有 7 个「藏在被剥掉的注释/属性里」的叶子（`index.disk` 等），
        它们的派生值是空串，同样只有扫源才看得见。见 `TestZhTwScannerSelfProof`。
        """
        exe = opencc_exe()
        if not exe:
            self.skipTest('未找到带 opencc 的隔离 venv')
        gdir = os.path.join(REPO, 'web', 'static', 'language', 'zh-TW')
        if not os.path.isdir(gdir):
            self.skipTest('未找到全局语言包目录')
        cnt, out, rc = zh_tw_scan(exe, gdir)
        if rc != 0:
            self.skipTest('opencc 子进程失败: %s' % (out or '')[:200])
        self.assertEqual(0, cnt, '全局 zh-TW 仍有真简体字残留:\n' + out)


class TestZhTwScannerSelfProof(unittest.TestCase):
    """自证：上面那个扫描器**必须真的会响**，且两个扫描面都要覆盖。

    否则 `assertEqual(0, cnt)` 恒真 —— 扫描器坏了也照样绿（等于没扫）。
    用最小夹具把「载体面」「源面」「不该误报」各钉一条。
    """

    def setUp(self):
        self.exe = opencc_exe()
        if not self.exe:
            self.skipTest('未找到带 opencc 的隔离 venv')

    def _scan_dir(self, files):
        d = tempfile.mkdtemp(prefix='zhtw_scan_')
        self.addCleanup(shutil.rmtree, d, True)
        for name, content in files.items():
            with open(os.path.join(d, name), 'w', encoding='utf-8', newline='\n') as fp:
                fp.write(content)
        return zh_tw_scan(self.exe, d)

    def test_catches_carrier_residue(self):
        """载体面：`.json` 里的简体值必须被抓到。"""
        cnt, out, rc = self._scan_dir({
            'template.index.json': '{"index": {"a": "\u670d\u52a1\u5668\u72b6\u6001"}}',
        })
        self.assertEqual(0, rc, out)
        self.assertGreaterEqual(cnt, 1, '载体面残留未被抓到:\n' + out)

    def test_catches_source_only_residue_invisible_in_carrier(self):
        """源面：**只在 lan.js 里、派生后看不见**的简体必须被抓到。

        夹具就是实测漏掉的那一类 —— `<!-- 磁盘IO -->` 的派生值是空串，
        只看 `.json` 载体永远发现不了（`index.disk` 即此形态）。
        """
        cnt, out, rc = self._scan_dir({
            'lan.js': ('var lan = {\n\t"index": {\n'
                       '\t\t"disk": "<!-- \u78c1\u76d8IO -->",\n'
                       '\t\t"b": "\u6b63\u5e38"\n\t}\n};\n'),
        })
        self.assertEqual(0, rc, out)
        self.assertGreaterEqual(cnt, 1, '源面残留未被抓到:\n' + out)

    def test_clean_pack_not_flagged(self):
        """反向对照：全干净时不得误报（证明判据不是「永远报」）。"""
        cnt, out, rc = self._scan_dir({
            'template.index.json': '{"index": {"a": "\u4f3a\u670d\u5668\u72c0\u614b"}}',
            'lan.js': ('var lan = {\n\t"index": {\n'
                       '\t\t"disk": "<!-- \u78c1\u789fIO -->"\n\t}\n};\n'),
        })
        self.assertEqual(0, rc, out)
        self.assertEqual(0, cnt, '干净夹具被误报（判据过宽）:\n' + out)


# --------------------------------------------------------------------------
# 12. JS 语法
# --------------------------------------------------------------------------
class TestJsSyntax(unittest.TestCase):
    def test_plugin_js_parses(self):
        node = next((p for p in NODE_CANDIDATES if os.path.isfile(p)), None)
        if not node:
            self.skipTest('未找到 node 运行时')
        bad = []
        for name in plugin_names():
            for jf in plugin_js_files(name):
                r = subprocess.run([node, '--check', jf], capture_output=True,
                                   text=True, encoding='utf-8', errors='replace')
                if r.returncode != 0:
                    bad.append('%s :: %s' % (
                        os.path.relpath(jf, REPO).replace('\\', '/'),
                        (r.stderr or '').strip().splitlines()[:2]))
        self.assertEqual([], bad[:10], '插件 JS 存在语法错误')


if __name__ == '__main__':
    unittest.main(verbosity=2)
