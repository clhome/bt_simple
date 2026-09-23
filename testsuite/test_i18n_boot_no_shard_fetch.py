# -*- coding: utf-8 -*-
"""i18n 启动期不得再拉语言分片（回归守卫）。

## 背景

`web/static/app/i18n.js` 原有一段「按路由懒加载 `template.<menu>.json`」的代码
（`loadMenuLan`）。实测它的合并结果**从未被读取**：

1. 分片顶层键 = section 名（`index`/`site`/`files`/…），而 `window.lan` 由 `lan.js`
   **同步**装载（`layout.html` 里 `lan.js` 在 `i18n.js` 之前）⇒ 这些键必然已存在
   ⇒ 合并守卫 `!(k in window.lan)` 恒为假。
2. 真正会被合并的只有 36 个「非 section 扁平键」
   （`yufeng_panel_btsimple`/`day_limit`/`replace_with`/…）。
   对全仓 `t('键')` / `data-i18n="键"` / `lan.键` / `pt('键')` / `_t('键')`
   做**扁平形式**检索，命中 **0 处** —— 代码一律走 `public.xxx` 点号路径。

净效果只是「白付一次 HTTP」，而且把 `[data-i18n]` 的首次翻译**挂在 ajax 的
`complete` 回调上** —— 翻译要等网络往返结束。

## 本用例钉死什么

1. 启动期 **0 次 ajax**（不再有分片请求）
2. DOM 就绪**即**完成 `[data-i18n]` 翻译（不依赖任何网络）
3. 死 API 不再导出（`loadMenuLan` / `detectCurrentMenu`）

并带**变异自证**：往启动路径里塞回一次 ajax 调用，断言必须变红 ——
否则 `assertEqual(0, ajaxCalls)` 就是恒真断言（等于没测）。

## 注意

分片 `.json` **文件必须保留** —— 后端 `web/core/i18n.py` 读它们。
本用例只禁「前端启动期拉分片」，不禁分片文件本身。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LAN_JS = os.path.join(REPO, 'web', 'static', 'language', 'zh-TW', 'lan.js')
I18N_JS = os.path.join(REPO, 'web', 'static', 'app', 'i18n.js')

NODE_CANDIDATES = [
    r'C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe',
    r'C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\24.20.0\node.exe',
    r'd:\Program Files\nodejs\node.exe',
    'node',
]

# 最小 DOM 桩：跑 lan.js + i18n.js，然后「触发 DOMContentLoaded」，
# 分别在「DOM 就绪时」和「ajax 响应到达后」两个时刻采样。
#
# 用原始字符串，所以 JS 里的换行转义写单反斜杠（`'\n'`），
# 注释里也不能出现三引号（会提前闭合）。
_HARNESS = r'''
const fs = require('fs');
const vm = require('vm');

const LAN_PATH = __LAN__;
const I18N_PATH = __I18N__;

const ctx = {};
ctx.window = ctx;                       // window === 全局，便于 window.lan 解析
ctx.console = console;
ctx.setTimeout = setTimeout;
ctx.location = { pathname: '/index', href: 'http://x/index', reload() {} };
ctx.navigator = { language: 'zh-TW' };
ctx.localStorage = { getItem: () => null, setItem() {} };
ctx._SERVER_LANG = 'zh-TW';

ctx.__ajaxCalls = 0;
ctx.__pendingComplete = null;
ctx.$ = function () { return { trigger() {} }; };
ctx.$.ajax = function (opts) {
  ctx.__ajaxCalls++;
  if (opts && typeof opts.complete === 'function') ctx.__pendingComplete = opts.complete;
};
ctx.$.post = function () {};

ctx.document = {
  readyState: 'loading',
  cookie: '',
  _ls: {},
  addEventListener(ev, fn) { (this._ls[ev] = this._ls[ev] || []).push(fn); },
  querySelectorAll() { return ctx.__nodes; },
  dispatch(ev) { (this._ls[ev] || []).forEach((f) => f()); },
};

const el = {
  tagName: 'SPAN', type: '',
  _attrs: { 'data-i18n': 'index.H1' },
  _text: '',
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
  setAttribute(k, v) { this._attrs[k] = v; },
  get textContent() { return this._text; },
  set textContent(v) { this._text = v; },
};
ctx.__nodes = [el];

vm.createContext(ctx);
vm.runInContext(fs.readFileSync(LAN_PATH, 'utf8'), ctx, { filename: 'lan.js' });
vm.runInContext(fs.readFileSync(I18N_PATH, 'utf8'), ctx, { filename: 'i18n.js' });

ctx.document.dispatch('DOMContentLoaded');
const afterDomReady = {
  text: el._text, dataI18nLang: el._attrs['data-i18n-lang'], ajaxCalls: ctx.__ajaxCalls,
};
// 模拟 HTTP 响应到达（HEAD 版把首次翻译挂在 complete 里）
if (ctx.__pendingComplete) ctx.__pendingComplete();

process.stdout.write(JSON.stringify({
  after_dom_ready: afterDomReady,
  after_ajax_complete: {
    text: el._text, dataI18nLang: el._attrs['data-i18n-lang'], ajaxCalls: ctx.__ajaxCalls,
  },
  api_loadMenuLan: typeof ctx.YfI18n.loadMenuLan,
  api_detectCurrentMenu: typeof ctx.YfI18n.detectCurrentMenu,
  api_translateDOM: typeof ctx.YfI18n.translateDOM,
}), () => process.exit(0));
'''


def node_exe():
    for p in NODE_CANDIDATES:
        if p == 'node' or os.path.isfile(p):
            return p
    return None


def run_boot(node, i18n_path=I18N_JS, lan_path=LAN_JS, timeout=60):
    """跑一次启动桩，返回 (结果 dict, stderr)。失败抛 AssertionError。"""
    script = (_HARNESS
              .replace('__LAN__', json.dumps(lan_path))
              .replace('__I18N__', json.dumps(i18n_path)))
    r = subprocess.run([node, '-e', script], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout)
    if r.returncode != 0:
        raise AssertionError('启动桩失败 (rc=%s):\n%s' % (r.returncode, (r.stderr or '')[:1500]))
    try:
        return json.loads(r.stdout), r.stderr
    except ValueError:
        raise AssertionError('启动桩输出不是 JSON:\n%s' % (r.stdout or '')[:1500])


class TestI18nBootNoShardFetch(unittest.TestCase):

    def setUp(self):
        self.node = node_exe()
        if not self.node:
            self.skipTest('未找到 node 运行时')
        if not (os.path.isfile(LAN_JS) and os.path.isfile(I18N_JS)):
            self.skipTest('缺少 lan.js / i18n.js')

    def test_no_ajax_on_boot(self):
        """启动期不得发起任何 ajax（分片懒加载已删除）。"""
        res, _ = run_boot(self.node)
        self.assertEqual(0, res['after_dom_ready']['ajaxCalls'],
                         '启动期仍发起了 ajax：%r' % res)
        self.assertEqual(0, res['after_ajax_complete']['ajaxCalls'],
                         '启动期仍发起了 ajax：%r' % res)

    def test_translate_dom_runs_at_dom_ready(self):
        """DOM 就绪即完成 [data-i18n] 翻译，不依赖网络。"""
        res, _ = run_boot(self.node)
        d = res['after_dom_ready']
        self.assertTrue(d['text'], 'DOM 就绪时 [data-i18n] 未翻译：%r' % res)
        self.assertNotEqual('index.H1', d['text'], '译成了键名本身：%r' % res)
        self.assertEqual('zh-TW', d['dataI18nLang'], '未标记已翻译语言：%r' % res)

    def test_dead_api_not_exported(self):
        """死 API 不应再挂在 YfI18n 上。"""
        res, _ = run_boot(self.node)
        self.assertEqual('undefined', res['api_loadMenuLan'], 'loadMenuLan 仍在导出')
        self.assertEqual('undefined', res['api_detectCurrentMenu'], 'detectCurrentMenu 仍在导出')
        self.assertEqual('function', res['api_translateDOM'], 'translateDOM 被误删')

    def test_source_has_no_shard_fetch(self):
        """源码层面：i18n.js 不得再出现分片拉取 URL 或已删符号。"""
        with open(I18N_JS, encoding='utf-8') as fp:
            src = fp.read()
        # 剥掉注释，避免「记录删除原因」的说明文字触发
        code = re.sub(r'/\*[\s\S]*?\*/', '', src)
        code = re.sub(r'^\s*//.*$', '', code, flags=re.M)
        # 逐条判定后 fail（不要用 assertNotIn：它会把整份文件倒进报错信息）
        for bad in ('template.\' + menu', 'template." + menu',
                    'loadMenuLan(', 'PATH_TO_MENU', '_MENU_LOADED', '_MENU_QUEUE'):
            if bad in code:
                self.fail('i18n.js 仍残留分片懒加载痕迹: %s' % bad)
        if '/static/language/' in code:
            self.fail('i18n.js 仍在拼 /static/language/ 路径')

    # ---------------- 变异自证 ----------------

    def test_guard_fires_when_ajax_added_back(self):
        """变异：往启动路径塞回一次 ajax，`no_ajax_on_boot` 必须变红。"""
        d = tempfile.mkdtemp(prefix='i18n_boot_mut_')
        self.addCleanup(shutil.rmtree, d, True)
        with open(I18N_JS, encoding='utf-8') as fp:
            src = fp.read()
        anchor = '    window.YfI18n = YfI18n;'
        self.assertIn(anchor, src, '锚点丢失，变异无法注入')
        mut = src.replace(
            anchor,
            anchor + '\n    if (window.$ && window.$.ajax) { window.$.ajax({ url: "/x" }); }')
        mut_path = os.path.join(d, 'i18n.js')
        with open(mut_path, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(mut)
        res, _ = run_boot(self.node, i18n_path=mut_path)
        self.assertGreater(res['after_dom_ready']['ajaxCalls'], 0,
                           '注入 ajax 后计数仍为 0 —— 判据没反应，护栏是装饰')

    def test_guard_fires_when_translate_dom_removed(self):
        """变异：把 DOMContentLoaded 的 translateDOM 摘掉，翻译断言必须变红。"""
        d = tempfile.mkdtemp(prefix='i18n_boot_mut_')
        self.addCleanup(shutil.rmtree, d, True)
        with open(I18N_JS, encoding='utf-8') as fp:
            src = fp.read()
        anchor = "document.addEventListener('DOMContentLoaded', function() { translateDOM(); });"
        self.assertIn(anchor, src, '锚点丢失，变异无法注入')
        mut = src.replace(anchor, 'document.addEventListener(\'DOMContentLoaded\', function() {});')
        mut_path = os.path.join(d, 'i18n.js')
        with open(mut_path, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(mut)
        res, _ = run_boot(self.node, i18n_path=mut_path)
        self.assertFalse(res['after_dom_ready']['text'],
                         '摘掉 translateDOM 后仍翻译了 —— 判据没反应，护栏是装饰')


if __name__ == '__main__':
    unittest.main(verbosity=2)
