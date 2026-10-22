# coding: utf-8
"""P2-2「明文 HTTP 告警」的四层守卫：判定函数 / 渲染点接线 / 模板 / i18n。

## 背景

面板未开启面板 SSL 时会话 Cookie 走明文 HTTP，链路上任何一跳都能嗅探到它
（拿到即等价于登录态）。本任务的路线是**只做显著告警**：登录页 + 首页显著提示
「当前为明文 HTTP，登录 Cookie 可被嗅探」，**不改**部署默认值、**不改**
`web/admin/__init__.py` 里 `SESSION_COOKIE_SECURE` 的既有开关逻辑。

## 四层断言（缺一层就会留下静默失效的口子）

1. **判定函数**（表驱动）：`plain_http_warning_decision()` 是纯函数，参数化覆盖
   `is_secure` / `scheme` / `X-Forwarded-Proto` / `X-Forwarded-Scheme` /
   `panel_ssl` 的全部口径组合。函数判错 → 告警要么永不出现、要么一直出现。
2. **渲染点接线**：`dashboard.py`（首页）与 `login.py`（登录页）必须真的把
   `plain_http_warning=` 传进模板 —— 「函数对了但没人调用」同样等于没做。
3. **模板**：两个模板都必须有告警块，且**受该标志控制**（去掉条件判断就会在
   HTTPS 环境下也报警，属误报）。
4. **i18n**：六语言的 `lan.js`（前端唯一真源）+ `template.json`（兼容垫片）+
   `template.setting.json`（后端实际命中 `public.*` 的分片）都要有这两个文案键。
   缺一个 → 某语言下告警是空白或硬编码中文。

第 5 层：**真渲染**。用 Jinja2（不依赖 flask app，面板 app 初始化会连带建库）
把 `default/login.html` 真渲染两遍，断言中文告警随标志出现/消失。
"""

import importlib.util
import io
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
TEMPLATE_DIR = os.path.join(WEB, 'templates')
LANG_DIR = os.path.join(WEB, 'static', 'language')

LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

WARN_MODULE_PY = os.path.join(WEB, 'admin', 'dashboard', 'plain_http_warning.py')
DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
LOGIN_PY = os.path.join(WEB, 'admin', 'dashboard', 'login.py')
LOGIN_TMPL = os.path.join(TEMPLATE_DIR, 'default', 'login.html')
INDEX_TMPL = os.path.join(TEMPLATE_DIR, 'default', 'index.html')

#: i18n 键：放 `public` 分组（登录页与首页共用同一组文案，避免两份翻译各自漂移）
GROUP = 'public'
KEY_TITLE = 'plain_http_warning_title'
KEY_DESC = 'plain_http_warning_desc'

#: 中文源文（其余五语言必须有自己的译文，不得回落到中文）
ZH_TITLE = '当前为明文 HTTP，登录 Cookie 可被嗅探'
ZH_DESC = '请尽快在「面板设置」中启用 HTTPS；在启用前不要通过公网使用此面板。'

#: 模板里判定的标志变量名
FLAG = 'plain_http_warning'


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def load_warn_module():
    """按文件路径加载判定模块。

    刻意**不走** `import admin.dashboard.plain_http_warning`：那会触发
    `admin/__init__.py` 建 Flask app、初始化面板库，在纯静态环境里跑不起来。
    判定模块本身零依赖（不碰 flask / 不碰数据库），可以独立加载。
    """
    spec = importlib.util.spec_from_file_location('yf_plain_http_warning', WARN_MODULE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guarded_region(src, flag=FLAG):
    """取出 `{% if <flag> %} ... {% endif %}` 之间的模板片段（取最长的一段）。

    这样能区分「告警块受标志控制」与「告警块写在条件外面」——后者在 HTTPS 下
    也会显示，属误报。
    """
    pat = re.compile(r'\{%-?\s*if\s+' + re.escape(flag) +
                     r'\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}', re.S)
    blocks = pat.findall(src)
    if not blocks:
        return None
    return max(blocks, key=len)


class _FakeRequest(object):
    """最小请求桩：只提供判定函数用到的三个属性。"""

    def __init__(self, is_secure=False, scheme='http', headers=None):
        self.is_secure = is_secure
        self.scheme = scheme
        self.headers = headers or {}


# --------------------------------------------------------------------------
# 1) 判定函数（表驱动）
# --------------------------------------------------------------------------
class TestDecision(unittest.TestCase):
    """`plain_http_warning_decision` 的口径表。

    判定口径：**明文 HTTP 且面板 SSL 未开启**才告警。
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_warn_module()

    def _decide(self, **kwargs):
        return self.mod.plain_http_warning_decision(**kwargs)

    def test_table(self):
        cases = [
            # --- 已加密：一律不告警 ---
            ('is_secure=True',
             dict(is_secure=True), False),
            ('scheme=https',
             dict(scheme='https'), False),
            ('scheme=HTTPS（大小写不敏感）',
             dict(scheme='HTTPS'), False),
            ('X-Forwarded-Proto: https',
             dict(forwarded_proto='https'), False),
            ('X-Forwarded-Proto: https, http（多级反代链）',
             dict(forwarded_proto='https, http'), False),
            ('X-Forwarded-Scheme: https',
             dict(forwarded_scheme='https'), False),
            # --- 明文：看面板 SSL 开关 ---
            ('明文 + panel_ssl.open=False → 告警',
             dict(scheme='http', panel_ssl={'open': False}), True),
            ('明文 + panel_ssl.open=True → 不告警',
             dict(scheme='http', panel_ssl={'open': True}), False),
            ('缺 panel_ssl 选项（None → 默认 open=False）→ 告警',
             dict(scheme='http', panel_ssl=None), True),
            ('panel_ssl 非 dict（脏数据 → 默认 open=False）→ 告警',
             dict(scheme='http', panel_ssl='not-a-dict'), True),
            ('panel_ssl 空 dict（缺 open → 视为关闭）→ 告警',
             dict(scheme='http', panel_ssl={}), True),
            ('明文 + 反代头说 http → 告警',
             dict(forwarded_proto='http', forwarded_scheme='http',
                  panel_ssl={'open': False}), True),
        ]
        for name, kwargs, want in cases:
            with self.subTest(name):
                got, hint = self._decide(**kwargs)
                self.assertEqual(want, got, '%s：期望 should_warn=%s，实际 %s'
                                 % (name, want, got))
                if want:
                    self.assertEqual('', hint, '%s：告警时不应给出「已加密」提示' % name)
                else:
                    self.assertTrue(hint, '%s：判为已加密时必须留下 hint 便于排查' % name)

    def test_wrapper_reads_request(self):
        """胶水层：从请求对象取 is_secure / scheme / 两个转发头。"""
        def warn(**kwargs):
            return self.mod.plain_http_warning(**kwargs)[0]

        # 明文请求 + 面板 SSL 关闭 → 告警
        self.assertTrue(warn(
            request_obj=_FakeRequest(), panel_ssl={'open': False}))
        # 反代声明 https → 不告警
        self.assertFalse(warn(
            request_obj=_FakeRequest(headers={'X-Forwarded-Proto': 'https'}),
            panel_ssl={'open': False}))
        self.assertFalse(warn(
            request_obj=_FakeRequest(headers={'X-Forwarded-Scheme': 'https'}),
            panel_ssl={'open': False}))
        # 面板 SSL 开启 → 不告警（与 admin/__init__.py:113 同口径）
        self.assertFalse(warn(
            request_obj=_FakeRequest(), panel_ssl={'open': True}))
        # 请求对象残缺（取属性就抛）不得让页面 500：按明文判
        class _Broken(object):
            @property
            def is_secure(self):
                raise RuntimeError('boom')

        self.assertTrue(warn(
            request_obj=_Broken(), panel_ssl={'open': False}))

    def test_flag_wrapper_returns_bool(self):
        self.assertIs(True, self.mod.plain_http_warning_flag(
            request_obj=_FakeRequest(), panel_ssl={'open': False}))
        self.assertIs(False, self.mod.plain_http_warning_flag(
            request_obj=_FakeRequest(), panel_ssl={'open': True}))


# --------------------------------------------------------------------------
# 2) 渲染点接线：视图必须真的把标志传进模板
# --------------------------------------------------------------------------
class TestRenderPointsWired(unittest.TestCase):
    def _assert_wired(self, src, tpl, label):
        # 渲染点内延迟导入（dashboard.py 会被用例按文件路径 exec，模块级相对导入会炸）
        self.assertIn('from .plain_http_warning import plain_http_warning_flag', src,
                      '%s 未引入告警判定函数' % label)
        # 模板实参传法按文件现状各不相同（都是 `'%s/xxx.html' % name`），
        # 断言的是「同一个 render_template 调用里带上了 plain_http_warning="
        call = re.escape("'%s/" + tpl + "' % name") + r'\s*,\s*' + FLAG + \
            r'\s*=\s*plain_http_warning_flag\(\)'
        self.assertRegex(src, r'render_template\(\s*' + call,
                         '%s 的渲染点没有传 %s=plain_http_warning_flag()' % (label, FLAG))

    def test_index_view_passes_flag(self):
        self._assert_wired(_read(DASHBOARD_PY), 'index.html', 'dashboard.py（首页）')

    def test_login_view_passes_flag(self):
        self._assert_wired(_read(LOGIN_PY), 'login.html', 'login.py（登录页）')


# --------------------------------------------------------------------------
# 3) 模板：两个页面都要有告警块，且受标志控制
# --------------------------------------------------------------------------
class TestTemplates(unittest.TestCase):
    def _check(self, path, label):
        src = _read(path)
        block = _guarded_region(src)
        self.assertIsNotNone(
            block,
            '%s 缺少 `{%% if %s %%} ... {%% endif %%}` 告警块' % (label, FLAG))
        self.assertIn('plainHttpWarning', block,
                      '%s 的告警块里缺少固定的告警容器 id=plainHttpWarning' % label)
        for key in ('%s.%s' % (GROUP, KEY_TITLE), '%s.%s' % (GROUP, KEY_DESC)):
            self.assertIn("t('%s'" % key, block,
                          '%s 的告警块没有用 t() 取键 %s' % (label, key))
            self.assertIn('data-i18n="%s"' % key, block,
                          '%s 的告警块缺少前端 i18n 钩子 data-i18n="%s"' % (label, key))
        # 「不改文案就静默消失」的防线：告警文案不得只出现在条件块之外
        outside = src.replace(block, '')
        self.assertNotIn(KEY_TITLE, outside,
                         '%s 里告警文案出现在条件块之外（会无条件显示/或块被拆散）' % label)

    def test_login_template_has_warning(self):
        self._check(LOGIN_TMPL, 'login.html')

    def test_index_template_has_warning(self):
        self._check(INDEX_TMPL, 'index.html')

    def test_warning_is_not_closable(self):
        """告警必须是「不可关闭」的：不得出现关闭按钮/隐藏脚本。"""
        for path, label in ((LOGIN_TMPL, 'login.html'), (INDEX_TMPL, 'index.html')):
            block = _guarded_region(_read(path)) or ''
            for bad in ('close', 'onclick', 'display:none', 'layer.msg'):
                self.assertNotIn(bad, block.lower().replace(' ', ''),
                                 '%s 的告警块疑似可关闭/可隐藏（出现 %r）' % (label, bad))


# --------------------------------------------------------------------------
# 4) i18n：六语言 × lan.js + template.json（+ 后端实际命中的 setting 分片）
# --------------------------------------------------------------------------
class TestI18n(unittest.TestCase):
    def _lang_pack(self, lang, filename):
        with io.open(os.path.join(LANG_DIR, lang, filename), encoding='utf-8') as fh:
            return json.load(fh)

    def test_lan_js_has_keys(self):
        for lang in LANGS:
            src = _read(os.path.join(LANG_DIR, lang, 'lan.js'))
            for key in (KEY_TITLE, KEY_DESC):
                m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key), src)
                self.assertIsNotNone(m, '%s/lan.js 缺少键 %s' % (lang, key))
                self.assertTrue(m.group(1).strip(), '%s/lan.js 的 %s 译文为空' % (lang, key))

    def test_template_json_has_keys(self):
        for lang in LANGS:
            data = self._lang_pack(lang, 'template.json')
            group = data.get(GROUP) or {}
            for key in (KEY_TITLE, KEY_DESC):
                self.assertTrue((group.get(key) or '').strip(),
                                '%s/template.json 的 %s.%s 缺失或为空' % (lang, GROUP, key))

    def test_setting_shard_has_keys(self):
        """后端 `t('public.x')` 实际命中的是 template.setting.json 的 public 段。"""
        for lang in LANGS:
            data = self._lang_pack(lang, 'template.setting.json')
            group = data.get(GROUP) or {}
            for key in (KEY_TITLE, KEY_DESC):
                self.assertTrue((group.get(key) or '').strip(),
                                '%s/template.setting.json 的 %s.%s 缺失或为空'
                                % (lang, GROUP, key))

    def test_zh_source_text_exact(self):
        data = self._lang_pack('zh-CN', 'template.json')[GROUP]
        self.assertEqual(ZH_TITLE, data[KEY_TITLE])
        self.assertEqual(ZH_DESC, data[KEY_DESC])

    def test_other_languages_are_translated(self):
        """非中文语言不得回落成中文源文（等于没翻译）。"""
        for lang in ('en', 'de', 'fr', 'it'):
            data = self._lang_pack(lang, 'template.json')[GROUP]
            for key in (KEY_TITLE, KEY_DESC):
                val = data[key]
                self.assertIsNone(re.search(r'[\u4e00-\u9fff]', val),
                                  '%s/template.json 的 %s 仍含中文：%r' % (lang, key, val))


# --------------------------------------------------------------------------
# 5) 真渲染：登录页 / 首页的告警随标志出现 / 消失
# --------------------------------------------------------------------------
def _translate():
    """优先用仓库真实的 core.i18n（zh-CN），拿不到就退回「默认值即译文」。"""
    if WEB not in sys.path:
        sys.path.insert(0, WEB)
    try:
        from core.i18n import t as _t

        def _t_zh(key, default=None):
            return _t(key, default, lang='zh-CN')
        return _t_zh
    except Exception:
        def _t_fallback(key, default=None):
            return default if default is not None else key
        return _t_fallback


def _render(template_name, flag):
    """用 Jinja2 直接渲染模板（不初始化面板 Flask app/数据库）。

    `web/templates/default/login.html` 是独立页（不 extends）；
    `web/templates/default/index.html` extends `layout.html`，而 `layout.html` 实际由
    `site`/`task` 蓝图那边的 `template_folder='../../templates/default'` 提供，
    所以搜索路径要把 `templates` 与 `templates/default` 都放进去。
    """
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([TEMPLATE_DIR, os.path.join(TEMPLATE_DIR, 'default')]),
        autoescape=jinja2.select_autoescape(['html', 'htm', 'xml']),
        trim_blocks=True,
    )
    ctx = {
        FLAG: flag,
        'config': {'version': 'test-version', 'title': '御风面板', 'ip': '127.0.0.1'},
        'data': {'title': '御风面板', 'home_notice': '', 'gpu_detect': 'no'},
        'current_lang': 'zh-CN',
        'supported_languages': [],
        'csrf_token': '',
        'asset_v': lambda _p: 'v',
        'session': {'code': '', 'login': False},
        'g': {'lang': 'zh-CN'},
        't': _translate(),
    }
    return env.get_template(template_name).render(**ctx)


class TestRender(unittest.TestCase):
    """真渲染：告警必须随 `plain_http_warning` 出现/消失（而不是只在字符串里）。"""

    TEMPLATES = (
        ('default/login.html', '登录页'),
        ('default/index.html', '首页'),
    )

    def test_flag_true_shows_warning(self):
        for tpl, label in self.TEMPLATES:
            with self.subTest(label):
                html = _render(tpl, True)
                self.assertIn('plainHttpWarning', html, '%s：标志为真时未输出告警块' % label)
                self.assertIn('明文 HTTP', html, '%s：告警标题未渲染出中文文案' % label)
                self.assertIn('Cookie 可被嗅探', html, '%s：告警标题不完整' % label)
                self.assertIn('请尽快在「面板设置」中启用 HTTPS', html,
                              '%s：告警说明未渲染出中文文案' % label)

    def test_flag_false_hides_warning(self):
        for tpl, label in self.TEMPLATES:
            with self.subTest(label):
                html = _render(tpl, False)
                self.assertNotIn('plainHttpWarning', html,
                                 '%s：标志为假时仍输出了告警块' % label)
                self.assertNotIn('明文 HTTP', html, '%s：标志为假时仍渲染出告警文案' % label)

    def test_warning_contains_no_sensitive_info(self):
        """告警不得泄露版本/路径/端口等信息（只讲风险与做法）。"""
        for tpl, label in self.TEMPLATES:
            with self.subTest(label):
                html = _render(tpl, True)
                start = html.find('plainHttpWarning')
                end = html.find('</div>', start)
                block = html[start:end]
                for leak in ('test-version', '127.0.0.1', '/www/', 'python'):
                    self.assertNotIn(leak, block, '%s：告警块里泄露了 %r' % (label, leak))


if __name__ == '__main__':
    unittest.main()
