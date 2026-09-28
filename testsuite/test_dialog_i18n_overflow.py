# -*- coding: utf-8 -*-
"""弹窗多语言「显示不全」回归锁。

## 背景（用户反馈）

非中文译文长度约为中文的 1.5~2 倍，而弹窗里的标签槽是定宽的，于是出现：

- 插件左侧菜单项被 ellipsis 截成 `Global configur…`；
- 表单标签（`.line .tname` 100px）被截断；
- 封锁历史 / 防爆破历史的时间筛选按钮组写死 `width:350px` + `space-between`，
  英文下按钮组实际占 ~535px，把右侧「解封所有 / 测试 / 刷新」挤到换行重叠
  （本次用户截图的直接成因）。

处置口径（用户确认）：**缩写译文 + 适度加宽弹窗，保持显示内容不变**。
译文只改 value、不改 key；已精简且放得下的既有译文不做无谓降级
（`redis.配置修改 = Configuration` 这类基线仍由既有用例守护）。

## 本护栏守护什么

1. 插件左侧菜单项：各语言译文宽度 ≤ 该插件 `.bt-w-menu` 的实际可用宽度；
2. 插件表单标签：`.line .tname` 译文宽度 ≤ 100px；
3. 面板弹窗标签：`.line .tname` / `.line .span_tit` 译文宽度 ≤ 槽宽；
4. 时间筛选工具条：不得再出现写死宽度 + 挤压式 `space-between`，
   必须允许换行（`flex-wrap`）；
5. 消息盒子菜单：加宽后的 140px 槽必须容得下「标签 + (0)」（en 基线不得缩写）。

## 为什么护栏自带宽度估算

判定基准必须独立：这里用**中英文字宽经验公式**（CJK=1em，拉丁=0.55em，13px）
作为 oracle，而不是任何业务代码里的常量。译文超长会直接让它变红。
"""
import ast
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(ROOT, 'plugins')
APP_DIR = os.path.join(ROOT, 'web', 'static', 'app')
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
I18N_PY = os.path.join(ROOT, 'web', 'core', 'i18n.py')

NON_CJK_LANGS = ('en', 'de', 'fr', 'it')
FONT_PX = 13.0
LATIN_RATIO = 0.55

MENU_BLOCK_RE = re.compile(r'<div class="bt-w-menu"[^>]*>(.*?)</div>', re.S)
MENU_ITEM_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.S)
TAG_RE = re.compile(r'<[^>]+>')
MENU_WIDTH_RE = re.compile(r'\.bt-w-menu\s*\{[^}]*?width:\s*(\d+)px', re.S)
MENU_PAD_RE = re.compile(r'\.bt-w-menu\s+p\s*\{[^}]*?padding:\s*([^;]+);', re.S)
PT_KEY_RE = re.compile(r"""pt\(\s*['"]([^'"]+)['"]\s*\)""")
TNAME_RE = re.compile(r"""<span[^>]*class=['"][^'"]*(tname|span_tit)[^'"]*['"][^>]*>(.*?)</span>""", re.S)
T_KEY_RE = re.compile(r"""t\(\s*['"]([^'"]+)['"]\s*[,)]""")
LAN_KEY_RE = re.compile(r"""lan\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)""")

# 站点设置弹窗左侧菜单（由 webEdit_menu 变量拼接，不在静态 <div> 里，单独列白名单守护）
SITE_EDIT_MENU_KEYS = (
    'site.domain_management', 'site.subdirectory_mapping', 'site.website_directory',
    'site.data_limit', 'site.pseudo_static', 'site.default_document',
    'site.configuration_file', 'site.php_version', 'site.redirect',
    'site.reverse_proxy', 'site.hotlink_protection', 'site.response_log',
    'site.error_log',
)
# 消息盒子左侧菜单（槽 140px - padding-left 20px = 120px，且带「(0)」计数尾巴）
MSG_BOX_MENU_KEYS = ('public.task_list', 'public.message_list', 'public.execution_log')
MSG_BOX_MENU_AVAIL = 120


def est_width(text, font=FONT_PX):
    """粗略估算渲染宽度（px）：CJK 按 1em，其余按 0.55em。"""
    return sum(font if ord(c) > 0x2E7F else font * LATIN_RATIO for c in text)


def menu_avail_width(html):
    m = MENU_WIDTH_RE.search(html)
    width = int(m.group(1)) if m else 120
    pad = 0
    pm = MENU_PAD_RE.search(html)
    if pm:
        pad = max([int(float(x[:-2])) for x in pm.group(1).split() if x.endswith('px')] or [0])
    return max(width - 2 * pad, 40)


def menu_items(html):
    block = MENU_BLOCK_RE.search(html)
    if not block:
        return []
    return [TAG_RE.sub('', x).strip() for x in MENU_ITEM_RE.findall(block.group(1))]


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def plugin_lang(name, lang):
    key = (name, lang)
    if key in _LANG_CACHE:
        return _LANG_CACHE[key]
    path = os.path.join(PLUGINS_DIR, name, 'lang', lang + '.json')
    dic = load_json(path) if os.path.isfile(path) else {}
    _LANG_CACHE[key] = dic
    return dic


_SOURCE_CACHE = {}
_LANG_CACHE = {}


def plugin_sources(name):
    """index.html + js/*.js 的源码文本列表（带缓存，避免重复读盘）。"""
    if name in _SOURCE_CACHE:
        return _SOURCE_CACHE[name]
    out = []
    hp = os.path.join(PLUGINS_DIR, name, 'index.html')
    if os.path.isfile(hp):
        with open(hp, encoding='utf-8') as f:
            out.append(f.read())
    jsdir = os.path.join(PLUGINS_DIR, name, 'js')
    if os.path.isdir(jsdir):
        for fn in sorted(os.listdir(jsdir)):
            if fn.endswith('.js'):
                with open(os.path.join(jsdir, fn), encoding='utf-8') as f:
                    out.append(f.read())
    _SOURCE_CACHE[name] = out
    return out


def label_key(fragment):
    """从一个标签片段里取出语言包键：pt('x') 优先，否则取纯文本（中文字面量）。"""
    keys = PT_KEY_RE.findall(fragment)
    if keys:
        return keys[0]
    plain = TAG_RE.sub('', fragment).strip()
    return plain or None


def plugin_labels(name, kind):
    """取指定槽类型的标签集合（`tname` / `span_tit`）。"""
    labels = set()
    for src in plugin_sources(name):
        for found, frag in TNAME_RE.findall(src):
            if found != kind:
                continue
            k = label_key(frag)
            if k:
                labels.add(k)
    return labels


def plugin_tname_labels(name):
    """只取 `.line .tname` 标签（span_tit 另算，槽宽不同）。"""
    return plugin_labels(name, 'tname')


def plugin_spantit_labels(name):
    return plugin_labels(name, 'span_tit')


STYLE_BLOCK_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.S | re.I)
CSS_RULE_RE = re.compile(r'([^{}]*)\{([^}]*)\}')


def css_slot_override(html, cls, default):
    """插件自己 `<style>` 里对 `.<cls>` 的宽度覆盖（取最大，可为 175px/150px）。"""
    widths = []
    cls_re = re.compile(r'\b%s\b' % cls)
    for block in STYLE_BLOCK_RE.findall(html):
        for selector, body in CSS_RULE_RE.findall(block):
            if not cls_re.search(selector):
                continue
            m = re.search(r'width:\s*(\d+)px', body)
            if m:
                widths.append(int(m.group(1)))
    return max([default] + widths)


def panel_dicts():
    """{lang: {'section.key': value}}，由构建期派生的 .json 载体读取。

    载体与 `lan.js` 的等价性由 `test_lang_carrier_derivation.py` 单独守护，
    所以这里不必解析 JS。
    """
    out = {}
    for lang in ('zh-CN',) + NON_CJK_LANGS:
        d = {}
        tpl = os.path.join(LANG_DIR, lang, 'template.json')
        if os.path.isfile(tpl):
            for sec, obj in load_json(tpl).items():
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str):
                            d['%s.%s' % (sec, k)] = v
        pub = os.path.join(LANG_DIR, lang, 'public.json')
        if os.path.isfile(pub):
            for k, v in load_json(pub).items():
                if isinstance(v, str):
                    d.setdefault('public.%s' % k, v)
        out[lang] = d
    return out


def panel_slots():
    """扫描面板 app 脚本里的定宽标签槽，返回 [(key_or_text, slot_px, where)]。"""
    slots = []
    for fn in sorted(os.listdir(APP_DIR)):
        if not fn.endswith('.js'):
            continue
        with open(os.path.join(APP_DIR, fn), encoding='utf-8') as f:
            src = f.read()
        for m in TNAME_RE.finditer(src):
            kind, body = m.group(1), m.group(2)
            slot = 105 if kind == 'span_tit' else 100
            tk = T_KEY_RE.search(body)
            if tk and '.' in tk.group(1):
                slots.append((tk.group(1), slot, '%s:%d' % (fn, src[:m.start()].count('\n') + 1)))
                continue
            lk = LAN_KEY_RE.search(body)
            if lk:
                slots.append(('%s.%s' % (lk.group(1), lk.group(2)), slot,
                              '%s:%d' % (fn, src[:m.start()].count('\n') + 1)))
                continue
            plain = TAG_RE.sub('', body).strip()
            if plain:
                slots.append((plain, slot, '%s:%d' % (fn, src[:m.start()].count('\n') + 1)))
    return slots


class TestDialogI18nOverflow(unittest.TestCase):

    def _all_source_files(self):
        """插件（含子目录静态资源）+ 面板 app 脚本的全部源码文件。"""
        out = []
        for dirpath, dirnames, filenames in os.walk(PLUGINS_DIR):
            dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'versions')]
            out += [os.path.join(dirpath, f) for f in filenames if f.endswith(('.js', '.html'))]
        out += [os.path.join(APP_DIR, f) for f in os.listdir(APP_DIR) if f.endswith('.js')]
        return sorted(out)

    # ------------------------------------------------------------ 插件弹窗
    def test_01_plugin_menu_labels_fit(self):
        """插件左侧菜单：每种语言的菜单项都必须放得进该插件自己的菜单槽。"""
        failures = []
        names = sorted(n for n in os.listdir(PLUGINS_DIR)
                       if os.path.isdir(os.path.join(PLUGINS_DIR, n)))
        for name in names:
            hp = os.path.join(PLUGINS_DIR, name, 'index.html')
            if not os.path.isfile(hp):
                continue
            with open(hp, encoding='utf-8') as f:
                html = f.read()
            items = menu_items(html)
            if not items:
                continue
            avail = menu_avail_width(html)
            for lang in NON_CJK_LANGS:
                dic = plugin_lang(name, lang)
                for item in items:
                    trans = dic.get(item, item)
                    if est_width(trans) > avail:
                        failures.append('%s/%s %r=%.0fpx > %.0fpx'
                                        % (name, lang, trans, est_width(trans), avail))
        self.assertEqual([], failures, '插件左侧菜单在非中文下会被截断：\n' + '\n'.join(failures))

    def test_02_plugin_form_labels_fit(self):
        """插件表单标签：`.line .tname`（默认 100px）与 `.line .span_tit`（默认 110px）
        必须放得下各自语言的译文（槽宽取插件自己的 CSS 覆盖）。"""
        failures = []
        names = sorted(n for n in os.listdir(PLUGINS_DIR)
                       if os.path.isdir(os.path.join(PLUGINS_DIR, n)))
        for name in names:
            hp = os.path.join(PLUGINS_DIR, name, 'index.html')
            if os.path.isfile(hp):
                with open(hp, encoding='utf-8') as f:
                    html = f.read()
            else:
                html = ''
            groups = (
                (plugin_tname_labels(name), css_slot_override(html, 'tname', 100)),
                (plugin_spantit_labels(name), css_slot_override(html, 'span_tit', 110)),
            )
            for labels, slot in groups:
                if not labels:
                    continue
                for lang in NON_CJK_LANGS:
                    dic = plugin_lang(name, lang)
                    for label in labels:
                        if label not in dic:      # JS 字面量（技术标识符）不走翻译
                            continue
                        trans = dic[label]
                        if est_width(trans) > slot + 1:
                            failures.append('%s/%s %r=%.0fpx > %dpx'
                                            % (name, lang, trans, est_width(trans), slot))
        self.assertEqual([], failures, '插件表单标签在非中文下会被截断：\n' + '\n'.join(failures))

    # ------------------------------------------------------------ 面板弹窗
    def test_03_panel_dialog_labels_fit(self):
        """面板弹窗（.tname / .span_tit）：译文必须放得进各自的槽。"""
        dicts = panel_dicts()
        zh = dicts['zh-CN']
        zh_to_key = {v: k for k, v in zh.items()}
        failures = []
        for label, slot, where in panel_slots():
            key = label if label in zh else zh_to_key.get(label)
            if not key:
                continue                      # 未翻译的字面量（另有 i18n 缺口用例负责）
            for lang in NON_CJK_LANGS:
                trans = dicts[lang].get(key)
                if trans and est_width(trans) > slot + 1:
                    failures.append('%s %s/%s %r=%.0fpx > %dpx'
                                    % (where, lang, key, trans, est_width(trans), slot))
        self.assertEqual([], failures, '面板弹窗标签在非中文下会被截断：\n' + '\n'.join(failures))

    def test_04_panel_menus_fit(self):
        """站点设置弹窗菜单（100px）与消息盒子菜单（120px，含「(0)」）都要放得下。"""
        dicts = panel_dicts()
        failures = []
        for key in SITE_EDIT_MENU_KEYS:
            for lang in NON_CJK_LANGS:
                trans = dicts[lang].get(key)
                if trans and est_width(trans) > 101:
                    failures.append('站点设置菜单 %s/%s %r=%.0fpx' % (lang, key, trans, est_width(trans)))
        for key in MSG_BOX_MENU_KEYS:
            for lang in NON_CJK_LANGS:
                trans = dicts[lang].get(key)
                if trans and est_width(trans + '(0)') > MSG_BOX_MENU_AVAIL:
                    failures.append('消息盒子菜单 %s/%s %r(+0)=%.0fpx'
                                    % (lang, key, trans, est_width(trans + '(0)')))
        self.assertEqual([], failures, '面板弹窗菜单在非中文下会被截断：\n' + '\n'.join(failures))

    def test_05_msg_box_menu_widened(self):
        """消息盒子菜单槽必须已加宽到 140px（否则 en 的 Execution Log(0) 仍会被截断）。"""
        for css_name in ('site.css', 'ensite.css'):
            path = os.path.join(ROOT, 'web', 'static', 'css', css_name)
            with open(path, encoding='utf-8') as f:
                css = f.read()
            self.assertIn('.layui-layer-page .msg-box-form .bt-w-menu', css,
                          '%s 缺少消息盒子菜单加宽规则' % css_name)
            rule = re.search(r'\.layui-layer-page \.msg-box-form \.bt-w-menu\s*\{[^}]*\}', css)
            self.assertIsNotNone(rule, '%s 消息盒子菜单规则解析失败' % css_name)
            self.assertIn('140px', rule.group(0), '%s 消息盒子菜单宽度必须是 140px' % css_name)

    # ------------------------------------------------------------ 工具条
    def test_06_time_filter_toolbar_not_broken(self):
        """时间筛选工具条：外层必须允许换行、右侧按钮组不得被压缩，
        且 bootstrap `.input-group` 必须保持 table 布局。

        `.form-control` 在 bootstrap 里是 `float:left; width:100%; z-index:2`，
        依赖 `.input-group` 的 table-cell 布局；改成 `inline-flex` 后输入框会
        直接盖住按钮（已发生过的线上回归，用户第二次截图）。
        """
        cases = (
            os.path.join(PLUGINS_DIR, 'op_waf', 'js', 'op_waf.js'),
            os.path.join(PLUGINS_DIR, 'fail2ban', 'js', 'fail2ban.js'),
        )
        for path in cases:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            label = os.path.basename(path)
            self.assertIn('flex-wrap: wrap', src,
                          '%s 工具条外层未允许换行（右侧按钮会被挤到换行重叠）' % label)
            self.assertIn('flex-shrink: 0; white-space: nowrap;', src,
                          '%s 右侧按钮组未禁止压缩，仍可能被压成两行' % label)
        self._assert_input_group_table_layout()

    def _assert_input_group_table_layout(self):
        """所有含按钮的 bootstrap `.input-group` 不得被改成非 table 显示。"""
        failures = []
        for path in self._all_source_files():
            with open(path, encoding='utf-8') as f:
                src = f.read()
            for m in re.finditer(r"""<div[^>]*class\s*=\s*['\"][^'\"]*input-group[^'\"]*['\"][^>]*>""", src):
                tag = m.group(0)
                sm = re.search(r"""style\s*=\s*['\"]([^'\"]*)['\"]""", tag)
                if not sm:
                    continue
                flat = re.sub(r'\s+', '', sm.group(1).lower())
                if 'display:' not in flat or 'table' in flat:
                    continue
                failures.append('%s:%d %s' % (os.path.relpath(path, ROOT),
                                               src[:m.start()].count('\n') + 1, flat[:80]))
        self.assertEqual([], failures,
                         '.input-group 被改成非 table 显示（输入框会盖住按钮）：\n'
                         + '\n'.join(failures))

    def test_07_time_range_labels_shortened(self):
        """时间范围按钮必须已缩写（`7 Days` 之类），否则英文下整组仍占 ~535px。"""
        for name in ('op_waf', 'fail2ban', 'webstats'):
            for lang in NON_CJK_LANGS:
                dic = plugin_lang(name, lang)
                for key in ('近7天', '近30天', '自定义时间'):
                    if key not in dic:
                        continue
                    self.assertLessEqual(est_width(dic[key]), 100,
                                         '%s/%s %s 译文过长：%r' % (name, lang, key, dic[key]))

    def test_09_flex_rows_with_controls_allow_wrap(self):
        """类级护栏：`flex + space-between` 且同行含按钮/控件的行必须允许换行。

        不允许换行时，宽度不足会把右侧按钮压成两行（`Unblock All` 断词、
        `Refresh` 掉到下一行），正是本次缺陷形态。
        """
        failures = []
        for path in self._all_source_files():
            with open(path, encoding='utf-8') as f:
                src = f.read()
            for m in re.finditer(r"""style\s*=\s*(['\"])(.*?)\1""", src, re.S | re.I):
                flat = re.sub(r'\s+', '', m.group(2).lower())
                if 'display:flex' not in flat or 'space-between' not in flat:
                    continue
                if 'flex-wrap' in flat:
                    continue
                tail = src[m.end():m.end() + 900]
                if not ('<button' in tail or '<select' in tail or 'input-group' in tail):
                    continue
                failures.append('%s:%d %s' % (os.path.relpath(path, ROOT),
                                               src[:m.start()].count('\n') + 1, m.group(2)[:80]))
        self.assertEqual([], failures,
                         'space-between 行未允许换行，右侧按钮会被压缩：\n' + '\n'.join(failures))

    # ------------------------------------------------------------ 契约
    def test_08_section_map_contract_reads_ok(self):
        """面板 section→分片映射必须仍可读（本文件的 oracle 依赖它，坏了要响）。"""
        with open(I18N_PY, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        mapping = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == '_SECTION_TO_MENU' for t in node.targets):
                mapping = ast.literal_eval(node.value)
        self.assertIsInstance(mapping, dict, 'web/core/i18n.py 缺失 _SECTION_TO_MENU')
        self.assertEqual('site', mapping.get('site'))
        self.assertEqual('setting', mapping.get('config'))


if __name__ == '__main__':
    unittest.main()
