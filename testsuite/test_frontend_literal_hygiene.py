# coding: utf-8
"""守卫:前端 JS/模板不得出现「拼接字面量被整段复制」的损坏。

损坏特征(历史上某轮 i18n 批量改写留下):
    var s = ('<p class="status">' + ('<p class="status">' + (...) + '<span>' || '回退') + '<span>') + ...
                            ^ 同一个 HTML 开标签在同一个拼接表达式里被重复,多出一层括号

后果:渲染出重复嵌套标签(浏览器容错所以不崩、不报错,极易漏检),并且 `|| 回退文案`
这一分支**永久不可达** → t() 取不到时不再回退,直接渲染空/半截文案。

本轮处理:`web/static/app/public.js`(A09 范围)已修;`web/static/app/config.js`
(A12 范围)的 23 处中 10 处已按「只留内层一份」修好,剩余 16 处按精确行号冻结在
`PENDING` 里(详见 testsuite/test_setting_a12_hardening.py 与 task.md A12 残留)。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 同一开标签紧接 `+ ( '` 再跟同样的开标签
_PAT = re.compile(r"""'<([a-z][a-z0-9]*(?:\s[^']*)?)'\s*\+\s*\(\s*'<\1""")

_SCAN_DIRS = ('web/static', 'plugins', 'web/templates')


def _scan():
    hits = []
    for rel in _SCAN_DIRS:
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d != '__pycache__']
            for f in fn:
                if not f.endswith(('.js', '.html')):
                    continue
                p = os.path.join(dp, f)
                try:
                    text = open(p, encoding='utf-8', errors='replace').read()
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if _PAT.search(line):
                        hits.append('%s:%d' % (os.path.relpath(p, ROOT).replace(os.sep, '/'), i))
    return hits


#: 已知尚未收敛的**精确命中**(文件 + 行号)。只允许变短 —— 任何清单外的新命中
#: 都会让守卫变红。`web/static/app/config.js` 原本有 23 处,其中 10 处(甲类:
#: 组外重复尾巴与组内末字面量逐字相同)已按「只留下内层一份」修好;剩下 16 处属
#: 乙类(组外重复尾巴是组内**某段连续子串**的重复,两种解读渲染出的可见文本相同,
#: 但括号结构会落在不同一侧),改动会静默改变前端结构,故保留并冻结在此。
PENDING = (
    'web/static/app/config.js:106',
    'web/static/app/config.js:219',
    'web/static/app/config.js:275',
    'web/static/app/config.js:300',
    'web/static/app/config.js:836',
    'web/static/app/config.js:1155',
    'web/static/app/config.js:1167',
    'web/static/app/config.js:1263',
    'web/static/app/config.js:1280',
    'web/static/app/config.js:1526',
    'web/static/app/config.js:1659',
    'web/static/app/config.js:1699',
    'web/static/app/config.js:1767',
    'web/static/app/config.js:1792',
    'web/static/app/config.js:1845',
    'web/static/app/config.js:1961',
)


class DuplicatedLiteralTest(unittest.TestCase):

    def test_01_no_duplicated_literal_in_frontend(self):
        hits = sorted(_scan())
        frozen = sorted(PENDING)
        new_hits = sorted(set(hits) - set(frozen))
        fixed = sorted(set(frozen) - set(hits))
        self.assertEqual(
            new_hits, [],
            '发现「拼接字面量被整段复制」的损坏(渲染重复标签 + 回退分支失效):\n  %s'
            % '\n  '.join(new_hits))
        self.assertEqual(
            fixed, [],
            '冻结清单里的这些位置已修好,请把对应行从 PENDING 里删掉:\n  %s'
            % '\n  '.join(fixed))
        self.assertEqual(len(frozen), 16,
                         'PENDING 清单长度变了(原 16 处乙类),请同步复核 A12 结论')

    def test_02_public_js_current_status_is_single_layer(self):
        # 具体回归点:public.js 的 current_status_1 那行只允许出现一次开标签
        p = os.path.join(ROOT, 'web', 'static', 'app', 'public.js')
        text = open(p, encoding='utf-8').read()
        line = [l for l in text.splitlines() if 'current_status_1' in l]
        self.assertTrue(line, 'public.js 的 current_status_1 拼接不见了?')
        self.assertEqual(line[0].count("'<p class=\"status\">'"), 1,
                         'public.js current_status 拼接又出现了重复开标签')
        # 回退分支必须可达(t() 结果直接参与 ||,而不是被括号吞掉)
        self.assertIn("(lan && lan.public && t('public.current_status_1') || '当前状态:')", line[0])


if __name__ == '__main__':
    unittest.main()