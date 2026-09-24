# -*- coding: utf-8 -*-
"""首页「概览（Overview）」卡片插件名称多语言专项回归测试。

## 背景（本用例守护的真实缺陷）

概览区里 op_waf / fail2ban 两张卡片的标题曾在 `web/static/app/index.js` 中
**硬编码简体中文**：

    show_name = '御风OP防火墙';
    show_name = '御风F2B底层防火墙';

于是切到 en / fr / de / it 时，其它卡片都已是母语，只有这两张仍是中文
（见截图：Overview 中两个红框内文字未适配多语言）。

修法：改用既有词条 `index.yufeng_op_firewall` / `index.yufeng_layer_firewall`
渲染，并在 `renderOverviewFromCache()` 中对旧的 localStorage 缓存**重新解析**
一次语言，避免升级后首屏闪出中文。

## 判定要点

1. `loadKeyDataCount()` 与 `renderOverviewFromCache()` 都必须走 `t('index.*')`，
   且不得再出现「裸中文赋值」。
2. 六个语言包（`lan.js` 与派生的 `template.json`）都必须有这两个键；
   外语值不得含 CJK（切到外文界面不能出现汉字）。
3. `index.js` 语法有效、UTF-8 无 BOM、LF 换行。
"""
import json
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX_JS = os.path.join(ROOT, 'web', 'static', 'app', 'index.js')
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')

ALL_LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')
FOREIGN_LANGS = ('en', 'fr', 'de', 'it')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')

# 键 -> 简体中文原文（= JS 里 t() 的 defaultText）
OVERVIEW_KEYS = {
    'yufeng_op_firewall': '御风OP防火墙',
    'yufeng_layer_firewall': '御风F2B底层防火墙',
}


def _read_utf8_lf(path):
    """读取文本并强制 UTF-8 无 BOM、LF 换行。"""
    with open(path, 'rb') as fh:
        raw = fh.read()
    assert not raw.startswith(b'\xef\xbb\xbf'), 'BOM detected in %s' % path
    assert b'\r\n' not in raw, 'CRLF detected in %s, must use LF' % path
    return raw.decode('utf-8')


class TestOverviewPluginI18n(unittest.TestCase):

    def test_index_js_renders_via_i18n_keys(self):
        """概览卡片渲染必须走 t('index.*')，不得再硬编码中文。"""
        js = _read_utf8_lf(INDEX_JS)

        for key, zh in OVERVIEW_KEYS.items():
            call = "t('index.%s'" % key
            self.assertIn(call, js, 'index.js 未使用多语言词条 %s' % call)

        # 缓存秒开路径：必须重新解析语言，而不是直接吃缓存里的 show_name
        self.assertIn('function renderOverviewFromCache()', js,
                      'index.js 缺失 renderOverviewFromCache 函数')
        for key, zh in OVERVIEW_KEYS.items():
            self.assertIn("cachedName = t('index.%s'" % key, js,
                          'renderOverviewFromCache 未对 %s 重新解析语言' % key)

        # 硬编码反例：裸中文赋值必须绝迹
        bare_patterns = [
            r"show_name\s*=\s*'%s'" % re.escape(zh) for zh in OVERVIEW_KEYS.values()
        ] + [
            r"cachedName\s*=\s*'%s'" % re.escape(zh) for zh in OVERVIEW_KEYS.values()
        ]
        for pat in bare_patterns:
            self.assertEqual(re.findall(pat, js), [],
                             'index.js 仍存在概览卡片硬编码中文：%s' % pat)

    def test_overview_branch_keeps_other_plugins(self):
        """改名不得牵连品牌名：mysql / pg_docker 分支必须原样保留。"""
        js = _read_utf8_lf(INDEX_JS)
        self.assertIn("show_name = 'MySQL';", js)
        self.assertIn("show_name = 'PostgreSQL (Docker)';", js)
        self.assertIn("pname == 'pg_docker'", js)

    def test_language_packs_have_keys(self):
        """六个语言包（lan.js + template.json）都含两键，外语值不得含中文。"""
        for lang in ALL_LANGS:
            lan_path = os.path.join(LANG_DIR, lang, 'lan.js')
            tpl_path = os.path.join(LANG_DIR, lang, 'template.json')
            lan_text = _read_utf8_lf(lan_path)
            with open(tpl_path, encoding='utf-8') as fh:
                index_section = json.load(fh).get('index', {})

            for key, zh in OVERVIEW_KEYS.items():
                self.assertIn('"%s"' % key, lan_text,
                              '%s/lan.js 缺失词条 %s' % (lang, key))
                value = index_section.get(key)
                self.assertTrue(value, '%s/template.json 缺失或空词条 %s' % (lang, key))

                if lang in FOREIGN_LANGS:
                    self.assertFalse(CJK_RE.search(value),
                                     '%s 的 %s 仍含中文：%s' % (lang, key, value))

            # 简体中文原文必须与 JS 兜底一致，否则外语查表会落空
            if lang == 'zh-CN':
                for key, zh in OVERVIEW_KEYS.items():
                    self.assertEqual(index_section.get(key), zh,
                                     '%s 的 %s 与 JS 兜底原文不一致' % (lang, key))

    def test_index_js_syntax(self):
        """Node.js 校验 index.js 语法。"""
        res = subprocess.run(['node', '-c', INDEX_JS],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0,
                         'index.js 语法错误：\n%s' % res.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
