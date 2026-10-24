# coding: utf-8
"""弹窗尺寸自适应守卫（layer 兜底层 + 调用点归一化）。

## 现场（2026-10-24）

「关闭SSL证书」确认框写死 `area: ['480px', '280px']`：中文两行提示放得下，
英文/德文提示变成三行 + 输入框，**输入框被切在弹窗底边之外**，用户以为弹窗坏了。
同类写死高度的弹窗全站有 16 处（`700x250` / `420x220` / `500x355` …），
逐个人工调尺寸既改不完，也防不住以后新写的弹窗 + 新语种。

## 方案（两层）

1. **调用点归一化**：`area: [宽, 高度px]` 中 `高度 < 500` 的一律改成 `'auto'`
   —— 这类都是文本/确认框，内容多高就多高。由本用例的静态扫描守住。
2. **运行期兜底层** `web/static/app/dialog_adaptive.js`：接管 `layer.open`，
   - 宽度夹到 `min(配置, 94vw)`、下限 300px（小屏不横向溢出）；
   - 非 iframe 且高度 < 500 → `'auto'`；其余夹到 `88vh`；
   - 打开后再量一次：超宽收窄、超高压缩（内容区滚动），长标题（>20 字）允许换行；
   - 注入 `word-break: break-word`，长 URL/长单词不撑破弹窗；
   - `yfAdaptive: false` 可整体绕过。

## 为什么要有 node 行为用例

「归一化函数写对了但没接上 layer」或「接管后把调用方的 success 吞掉」都是静默失效：
界面还在，弹窗却依旧切字 / 初始化逻辑不再执行。这里用 vm 真跑一遍组件，断言
`layer.open` 收到的 `area`、`layer.style` 的校正调用、以及调用方 `success` 仍然被执行。
"""

import io
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
APP_DIR = os.path.join(WEB, 'static', 'app')
ADAPTIVE_JS = os.path.join(APP_DIR, 'dialog_adaptive.js')
LAYOUT = os.path.join(WEB, 'templates', 'default', 'layout.html')
LOGIN_HTML = os.path.join(WEB, 'templates', 'default', 'login.html')

#: 允许保留「写死小高度」的调用点（文件:片段 → 原因）。
#: 目前为空：文本/确认框都已改成 'auto'。新增条目必须是**产品决策**（如 iframe 页）。
FIXED_HEIGHT_ALLOWLIST = {}

_AREA_RE = re.compile(r"""area:\s*\[\s*(['"])([^'"]+)\1\s*,\s*(['"])(\d+)px\3\s*\]""")


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def _app_js_files():
    return [os.path.join(APP_DIR, f) for f in sorted(os.listdir(APP_DIR)) if f.endswith('.js')]


class TestNoHardcodedSmallDialogHeight(unittest.TestCase):
    """一、调用点：文本/确认类弹窗不得再写死小高度。"""

    def test_no_fixed_height_under_500(self):
        offenders = []
        for path in _app_js_files():
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            for line_no, line in enumerate(_read(path).splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith(('*', '//', '/*')):
                    continue  # 文档/注释里引用的示例写法不算调用点
                for m in _AREA_RE.finditer(line):
                    height = int(m.group(4))
                    if height >= 500:
                        continue
                    key = '%s:%s' % (rel, m.group(0))
                    if key in FIXED_HEIGHT_ALLOWLIST:
                        continue
                    offenders.append('%s:%d  %s' % (rel, line_no, m.group(0)))
        self.assertEqual(
            [], offenders,
            '这些弹窗仍写死小高度，中英文文案一长就会切字，请改成 [\'宽px\', \'auto\']：\n  %s'
            % '\n  '.join(offenders))

    def test_close_ssl_dialog_body_not_duplicated(self):
        """回归点：关闭SSL证书弹窗原来把整段 body 拼了两遍（内层一份 + 外层一份）。

        后果比切字更糟：两个 `#prompt_input_box`（重复 id）、嵌套的 confirm-info-box，
        外加写死 105px 高度，英文文案一长输入框就被挤出可视区。
        """
        src = _read(os.path.join(APP_DIR, 'config.js'))
        self.assertEqual(1, src.count('id="prompt_input_box"'),
                         '关闭SSL证书弹窗的输入框被重复拼装了（应只有一处）')
        self.assertEqual(1, src.count('class="confirm-info-box"'),
                         '关闭SSL证书弹窗的提示框被重复拼装了（应只有一处）')
        self.assertEqual(1, src.count('class="hint_con"'))

    def test_close_ssl_dialog_is_auto_height(self):
        """回归点：关闭SSL证书确认框（用户实测切字的那一个）。"""
        src = _read(os.path.join(APP_DIR, 'config.js'))
        self.assertIn("area: ['480px', 'auto']", src,
                      '关闭SSL证书弹窗又改回写死高度了（280px 装不下英文三行提示 + 输入框）')


class TestAdapterWiring(unittest.TestCase):

    def test_adapter_file_exists_and_exposes_api(self):
        src = _read(ADAPTIVE_JS)
        for token in ('layer.open = function', 'normalizeArea', 'window.YfAdaptiveDialog',
                      'yfAdaptive === false', 'word-break:break-word'):
            self.assertIn(token, src, '兜底层缺少关键实现: %r' % token)

    def test_layout_loads_adapter_after_layer(self):
        for path in (LAYOUT, LOGIN_HTML):
            src = _read(path)
            name = os.path.basename(path)
            self.assertIn("asset_v('app/dialog_adaptive.js')", src,
                          '%s 未引入弹窗自适应脚本（或缺少缓存指纹）' % name)
            self.assertLess(src.index('layer.js'),
                            src.index('dialog_adaptive.js'),
                            '%s：自适应脚本必须在 layer.js 之后加载，否则 patch 不到 layer.open' % name)


class TestAdapterBehaviour(unittest.TestCase):
    """二、行为：用 node + vm 真跑一遍兜底层。"""

    def _run(self, script):
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过前端行为用例')
        res = subprocess.run([node, '-e', script], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(res.returncode, 0, 'node 用例失败: %s\n%s' % (res.stderr, res.stdout))
        return res.stdout

    def test_area_normalization_and_fit(self):
        script = r"""
        const fs = require('fs');
        const vm = require('vm');

        const opened = [];
        const styled = [];
        const layer = {
          open: function (opts) { opened.push(opts); return opened.length; },
          style: function (index, css) { styled.push({ index: index, css: css }); }
        };
        const sandbox = {
          console: console,
          layer: layer,
          innerWidth: 800,
          innerHeight: 600,
          requestAnimationFrame: function (fn) { fn(); },
          document: {
            head: { appendChild: function () {} },
            getElementById: function () { return null; },
            createElement: function () { return { appendChild: function () {} }; },
            createTextNode: function (t) { return { text: t }; },
            getElementsByTagName: function () { return []; }
          }
        };
        sandbox.window = sandbox;
        vm.createContext(sandbox);
        vm.runInContext(fs.readFileSync('web/static/app/dialog_adaptive.js', 'utf8'), sandbox);

        const api = sandbox.YfAdaptiveDialog;
        if (!api) { console.error('未暴露 YfAdaptiveDialog'); process.exit(2); }

        function areaOf(opts) {
          layer.open(opts);
          return opened[opened.length - 1].area;
        }

        // 1) 文本/确认框：小高度 -> auto（中英文都不再切字）
        let a = areaOf({ type: 1, area: ['480px', '280px'], content: 'x' });
        if (a[0] !== '480px' || a[1] !== 'auto') {
          console.error('小高度弹窗未改成 auto: ' + JSON.stringify(a)); process.exit(3);
        }

        // 2) 宽高都超视口：宽度 94vw、高度 88vh
        a = areaOf({ type: 1, area: ['1200px', '900px'], content: 'x' });
        if (a[0] !== '752px' || a[1] !== '528px') {
          console.error('超大弹窗未夹到视口: ' + JSON.stringify(a)); process.exit(4);
        }

        // 3) 百分比布局弹窗原样不动（设计稿就是百分比）
        a = areaOf({ type: 1, area: ['85%', '85%'], content: 'x' });
        if (a[0] !== '85%' || a[1] !== '85%') {
          console.error('百分比弹窗被误改: ' + JSON.stringify(a)); process.exit(5);
        }

        // 4) iframe 页必须保留高度（auto 会让 iframe 高度塌成 0）
        a = areaOf({ type: 2, area: ['600px', '300px'], content: 'http://x' });
        if (a[1] !== '300px') {
          console.error('iframe 弹窗高度被误改为 auto: ' + JSON.stringify(a)); process.exit(6);
        }

        // 5) 逃生口：yfAdaptive:false 原样透传
        a = areaOf({ type: 1, area: ['480px', '280px'], content: 'x', yfAdaptive: false });
        if (a[1] !== '280px') {
          console.error('yfAdaptive:false 未被尊重: ' + JSON.stringify(a)); process.exit(7);
        }

        // 6) 调用方 success 必须仍被执行，且超高时会被压缩
        let called = false;
        const tallLayero = {
          length: 1,
          outerWidth: function () { return 480; },
          outerHeight: function () { return 900; },
          find: function () { return { length: 0, text: function () { return ''; } }; },
          addClass: function () {}
        };
        layer.open({
          type: 1, area: ['480px', 'auto'], content: 'x',
          success: function (layero, index) { called = true; }
        });
        const opts = opened[opened.length - 1];
        opts.success(tallLayero, 9);
        if (!called) { console.error('调用方 success 被吞掉了'); process.exit(8); }
        if (!styled.some(function (s) { return s.css.height === '528px'; })) {
          console.error('超高弹窗未被压缩: ' + JSON.stringify(styled)); process.exit(9);
        }

        // 7) 完全没写 area 的弹窗：超宽时收窄，并且高度交回内容（否则换行后又被切）
        styled.length = 0;
        layer.open({ type: 1, content: '很长的一段说明文字' });
        const noAreaOpts = opened[opened.length - 1];
        noAreaOpts.success({
          length: 1,
          outerWidth: function () { return 1200; },
          outerHeight: function () { return 200; },
          find: function () { return { length: 0, text: function () { return ''; } }; },
          addClass: function () {}
        }, 11);
        if (!styled.some(function (s) { return s.css.width === '752px' && s.css.height === 'auto'; })) {
          console.error('无 area 弹窗收窄后未把高度交回内容: ' + JSON.stringify(styled));
          process.exit(11);
        }

        // 8) 内容异步变高后，业务可手动复算
        if (typeof api.fit !== 'function') { console.error('缺少 fit 复算入口'); process.exit(12); }

        // 9) 组件不可用时不得崩（layer 缺失）
        const sandbox2 = { console: console, document: sandbox.document };
        sandbox2.window = sandbox2;
        vm.createContext(sandbox2);
        vm.runInContext(fs.readFileSync('web/static/app/dialog_adaptive.js', 'utf8'), sandbox2);
        if (sandbox2.YfAdaptiveDialog) { console.error('无 layer 时不应导出 API'); process.exit(10); }

        console.log('DIALOG_ADAPTIVE_TESTS_PASSED');
        """
        self.assertIn('DIALOG_ADAPTIVE_TESTS_PASSED', self._run(script))


class TestLongTranslationFits(unittest.TestCase):
    """三、中英文都得放得下：拿最长的几条译文核对「不会有写死高度兜不住」的回归。"""

    LONG_KEYS = ('turning_off_ssl_makes', 'please_enter_the_following',
                 'you_will_use_the', 'ssl_step_cert_warning')

    def test_long_texts_exist_in_all_languages(self):
        import json
        import os as _os
        lang_dir = _os.path.join(WEB, 'static', 'language')
        for lang in ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'):
            carrier = json.loads(_read(_os.path.join(lang_dir, lang, 'template.setting.json')))
            config = carrier.get('config') or {}
            missing = [k for k in self.LONG_KEYS if not config.get(k)]
            self.assertEqual([], missing, '%s 缺少长文案键: %r' % (lang, missing))

    def test_english_close_ssl_text_is_longer_than_chinese(self):
        """英文比中文长 —— 这正是「写死高度」必然切字的原因，留作说明性断言。"""
        import json
        import os as _os
        lang_dir = _os.path.join(WEB, 'static', 'language')
        zh = json.loads(_read(_os.path.join(lang_dir, 'zh-CN', 'template.setting.json')))['config']
        en = json.loads(_read(_os.path.join(lang_dir, 'en', 'template.setting.json')))['config']
        self.assertGreater(len(en['turning_off_ssl_makes']), len(zh['turning_off_ssl_makes']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
