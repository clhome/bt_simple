# coding: utf-8
"""计划任务列表「日志/执行/编辑/删除」点不动（前端 SyntaxError）回归守卫。

现场症状（真机 Chrome，计划任务列表点「日志」）：
    页面毫无反应，控制台两条红字：
        Uncaught SyntaxError: missing ) after argument list (at VM1724:1:9)
        Uncaught TypeError: console.fail is not a function
            at window.onerror (<anonymous>:6:13)

根因已用真 Chrome 复现定死（`href="javascript:getLogs('437, 'test')"` → 点击即报
`missing ) after argument list @ …:1:9`，第 9 列正是那个多余的引号）：

1. **拼接处少了一个收尾引号**（P0，日志/删除两个按钮全废）
   `getCronData()` 里是这么拼的：
       '<a href="javascript:getLogs(\\'' + id + ", '" + name + '\\');">'
   生成 `getLogs('437, 'test')` —— id 被包进了前面那个字符串，收尾 `'` 丢了。
   这是与任务名无关的硬错，**每一行点日志都是 SyntaxError**，`getLogs` 根本不会
   执行（所以“点日志没任何反应”）。`planDel` 同一个拼法，删除同样点不动。
   另外任务名本身也是用户输入（手工创建/导入 JSON/从服务器同步），带引号时
   内联代码同样会被截断。
   修法：不再把数据拼进 `javascript:`/`onclick`。ID/名字挂 data-* 属性（经 cronEsc
   转义），点击走事件委派，日志弹窗里的「执行任务」用闭包变量绑事件。

2. **错误钩子自己是坏的**（P1，把真错吞掉）
   `plugins/yufeng_systemd/js/yufeng_systemd.js` 把 `window.onerror` 换成自己的，
   里面调 `console.fail(...)` —— 浏览器没有这个方法，于是处理器先抛
   `TypeError: console.fail is not a function`，真正错的提示被盖住。

## 测试架构（2026-10-27 改为不依赖 jsdom）

CI（GitHub Actions）只装 Python 依赖，没有 `node_modules`，原夹具
`require('jsdom')` 直接 `MODULE_NOT_FOUND` → 门禁红。现在拆两层：

* `testsuite/js/crontab_row_actions_probe.js`：只用 node 内置 `vm` 跑 `crontab.js`，
  输出**生成的 HTML 字符串** + 委派点击的实参；
* 本文件：用标准库 `html.parser` 做**真实 HTML 解析**（属性实体解码、引号截断
  都按浏览器语义），断言行内链接没有参数化 JS、data-* 能原样回读，再把解析出的
  属性喂回 node 验证委派实参。

这样既不需要第三方 node 模块，又保留「真实 HTML 解析」这一最关键的断言能力
（任务名带双引号时 HTML 属性会被截断，正是靠它抓）。
"""
import html.parser
import io
import json
import os
import shutil
import subprocess
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(current_dir)
CRONTAB_JS = os.path.join(ROOT, 'web', 'static', 'app', 'crontab.js')
SYSTEMD_JS = os.path.join(ROOT, 'plugins', 'yufeng_systemd', 'js', 'yufeng_systemd.js')
PROBE = os.path.join(ROOT, 'testsuite', 'js', 'crontab_row_actions_probe.js')


def _read(path):
    with io.open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _code_only(src):
    """去掉整行注释，避免注释里为了解释「不能这么写」而提到旧写法被误判。"""
    return '\n'.join(l for l in src.splitlines() if not l.strip().startswith('//'))


class _Collector(html.parser.HTMLParser):
    """收集所有 <a>/<span> 的属性与文本 —— 用标准库做真实 HTML 解析。

    用 HTMLParser 而不是正则的原因：浏览器对 `href="javascript:getLogs('437, 'test')"`
    这类属性的解析是「按 HTML 规则解码实体 + 以引号定界」。正则会把两种都对上，
    于是「属性被截断」这个真实现象就测不出来。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        item = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
        self.tags.append(item)
        if tag not in ('br', 'img', 'input', 'hr', 'meta', 'link'):
            self._stack.append(item)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]['tag'] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]['text'] += data


def _parse(fragment):
    p = _Collector()
    p.feed(fragment)
    p.close()
    return p.tags


NODE = shutil.which('node')


@unittest.skipUnless(NODE, '未安装 node，跳过前端行为夹具')
class TestCrontabFrontendInlineJs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        env = dict(os.environ)
        env.pop('CRONTAB_JS', None)
        env.pop('CRON_ATTRS', None)
        proc = subprocess.run([NODE, PROBE], cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        out = proc.stdout.decode('utf-8', 'replace').strip()
        err = proc.stderr.decode('utf-8', 'replace').strip()
        if not out.startswith('{'):
            raise AssertionError('夹具没有输出 JSON，stderr=%s' % err[:2000])
        cls.base = json.loads(out)

    # ---- 1. 源码层 ----
    def test_01_no_user_data_in_inline_js(self):
        fails = [f for f in self.base['failures'] if '源码' in f]
        self.assertEqual([], fails, '源码仍有用户数据拼进内联 JS：%s' % fails)

    def test_02_row_actions_use_data_attributes_and_delegation(self):
        """源码里必须用 data-cron-act + 命名空间事件委派。"""
        code = _code_only(_read(CRONTAB_JS))
        for act in ('run', 'edit', 'log', 'del', 'toggle'):
            self.assertIn('data-cron-act="%s"' % act if act != 'run' else 'data-cron-act=\\"run\\"',
                          code)
        self.assertIn("$(document).off('click.cronRowAct').on('click.cronRowAct', '.cron-row-act'",
                      code, '必须用命名空间事件委派（pjax 重进页面不能叠加监听器）')

    def test_03_log_dialog_button_has_no_inline_js(self):
        src = _read(CRONTAB_JS)
        self.assertIn("layero.find('#cron_log_run').on('click'", src,
                      '日志弹窗的执行按钮必须用闭包变量绑事件')
        self.assertIn('cronEsc(task_name)', src, '弹窗里显示的任务名必须转义')

    def test_04_onerror_hook_does_not_call_missing_console_api(self):
        code = _code_only(_read(SYSTEMD_JS))
        self.assertFalse('console.fail(' in code,
                         'console.fail 不存在，会让错误钩子自己抛 TypeError 并吞掉真错')
        self.assertTrue('console.error(' in code, '错误仍要落到控制台')

    # ---- 2. 真实 HTML 解析：每行 4 个操作链接、href 不带参数化 JS ----
    def test_05_rendered_rows_have_no_parametrized_js(self):
        rendered = self.base['rendered']
        self.assertEqual(7, len(rendered), '夹具应覆盖 7 类畸形任务名')
        for item in rendered:
            name = item['name']
            tags = _parse('<table><tbody>' + item['html'] + '</tbody></table>')
            anchors = [t for t in tags if t['tag'] == 'a']
            self.assertEqual(4, len(anchors),
                             '每行应有 4 个行内操作链接（任务名=%r，实际 %d）'
                             % (name, len(anchors)))
            for a in anchors:
                href = a['attrs'].get('href') or ''
                self.assertRegex(href, r'^javascript:;?$',
                                 '行内链接 href 仍带参数化 JS（任务名=%r）：%r' % (name, href))
                self.assertIsNone(a['attrs'].get('onclick'),
                                  '行内链接仍有 onclick（任务名=%r）' % name)
            # 不可注入标签
            self.assertNotIn('<img', item['html'], '任务名注入了标签：%r' % name)
            self.assertNotIn('<script', item['html'], '任务名注入了脚本：%r' % name)

            # data-* 必须能原样回读（HTML 实体解码后等于原文）
            acts = {}
            for t in tags:
                act = t['attrs'].get('data-cron-act')
                if act:
                    acts[act] = t
            for act in ('run', 'edit', 'log', 'del', 'toggle'):
                self.assertIn(act, acts, '缺少 data-cron-act=%s（任务名=%r）' % (act, name))
            self.assertEqual('42', acts['log']['attrs'].get('data-cron-id'))
            self.assertEqual(name, acts['log']['attrs'].get('data-cron-name'),
                             'data-cron-name 回读失真（任务名=%r，得到 %r）'
                             % (name, acts['log']['attrs'].get('data-cron-name')))
            self.assertEqual(name, acts['del']['attrs'].get('data-cron-name'))

    # ---- 3. 委派点击：把解析出的属性喂回 node，验证实参 ----
    def test_06_delegation_passes_exact_values(self):
        cases = []
        for item in self.base['rendered']:
            tags = _parse('<table><tbody>' + item['html'] + '</tbody></table>')
            acts = {}
            for t in tags:
                act = t['attrs'].get('data-cron-act')
                if act:
                    acts[act] = t['attrs']
            for act in ('run', 'edit', 'log', 'del', 'toggle'):
                cases.append({'act': act, 'name': item['name'],
                              'attrs': acts[act]})
        env = dict(os.environ)
        env['CRON_ATTRS'] = json.dumps(cases)
        proc = subprocess.run([NODE, PROBE], cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        out = proc.stdout.decode('utf-8', 'replace').strip()
        self.assertTrue(out.startswith('{'), '第二阶段夹具没有输出 JSON')
        res = json.loads(out)
        expect_fn = {'run': 'startTask', 'edit': 'editTaskInfo', 'log': 'getLogs',
                     'del': 'planDel', 'toggle': 'setTaskStatus'}
        for c in res['delegatedProbe']:
            self.assertIsNone(c.get('error'), '委派点击抛异常：%s' % c.get('error'))
            calls = c.get('calls') or []
            self.assertEqual(1, len(calls), '委派点击没有调用目标函数：%r' % (c,))
            fn, args = calls[0]['fn'], calls[0]['args']
            self.assertEqual(expect_fn[c['act']], fn,
                             '点击 %s 调错了函数：%s' % (c['act'], fn))
            self.assertEqual('42', str(args[0]), '点击 %s 传错 id：%r' % (c['act'], args))
            if c['act'] in ('log', 'del'):
                self.assertEqual(c['name'], args[1],
                                 '点击 %s 传错任务名：%r' % (c['act'], args[1]))
            if c['act'] == 'toggle':
                self.assertEqual(0, args[1], '启用按钮状态值应为 0')

    # ---- 4. 日志弹窗：无内联 onclick、名字只作文本、执行按钮闭包正确 ----
    def test_07_log_dialog_content(self):
        probes = self.base['dialogProbes']
        self.assertTrue(probes, '夹具没有弹窗探针')
        for p in probes:
            name = p['name']
            self.assertIsNone(p.get('error'), '日志弹窗构造/绑定抛异常（任务名=%r）：%s'
                              % (name, p.get('error')))
            content = p['content']
            self.assertNotIn('onclick', content, '弹窗里仍有内联 onclick（任务名=%r）' % name)
            self.assertNotIn('<img', content, '弹窗内容被任务名注入标签（任务名=%r）' % name)
            tags = _parse('<div>' + content + '</div>')
            self.assertTrue(any(t['tag'] == 'button' and t['attrs'].get('id') == 'cron_log_run'
                                for t in tags if t['tag'] == 'button'),
                            '弹窗里没有 #cron_log_run 执行按钮（任务名=%r）' % name)
            # 任务名只作为文本出现（等价原文）
            self.assertTrue(any((t['text'] or '').strip() == name for t in tags),
                            '弹窗里任务名不是以纯文本呈现（任务名=%r）' % name)
            # 闭包绑定的执行按钮
            self.assertTrue(p.get('bound'), '执行任务按钮没有绑定 click（任务名=%r）' % name)
            calls = p.get('calls') or []
            self.assertEqual(1, len(calls), '执行按钮没有触发 startTask（任务名=%r）' % name)
            self.assertEqual('42', str(calls[0][0]))
            self.assertEqual(name, calls[0][1], '执行按钮传错任务名（任务名=%r）' % name)
            self.assertIs(True, calls[0][2], '执行按钮应带 is_log_open=true')

    # ---- 5. 空 id 不发请求 ----
    def test_08_empty_id_is_noop(self):
        empty = self.base['emptyId']
        self.assertIsNone(empty['open'], '无 id 时不应打开日志弹窗')
        self.assertEqual(0, empty['posts'], '无 id 时不应发日志请求')


if __name__ == '__main__':
    unittest.main()
