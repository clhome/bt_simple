# coding: utf-8
"""计划任务列表「日志/执行/编辑/删除」点不动（前端 SyntaxError）回归守卫。

现场症状（真机 Chrome，计划任务列表点「日志」）：
    页面毫无反应，控制台两条红字：
        Uncaught SyntaxError: missing ) after argument list (at VM1724:1:9)
        Uncaught TypeError: console.fail is not a function
            at window.onerror (<anonymous>:6:13)

根因已用真 Chrome 复现定死（
    href="javascript:getLogs('437, 'test')" → 点击即报
    missing ) after argument list @ …:1:9 ，第 9 列正是那个多余的引号）：

1. **拼接处少了一个收尾引号**（P0，日志/删除两个按钮全废）
   `getCronData()` 里是这么拼的：
       '<a href="javascript:getLogs(\'' + id + ", '" + name + '\');">'
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
   `TypeError: console.fail is not a function`，真正错的提示被盖住，
   用户只能看到这两条莫名其妙的错。

断言分两层：
  * 源码层：crontab.js 里不再出现「数据拼进内联 JS」的写法（AST 级太贵，用
    去注释后的整行匹配 + 结构断言）；
  * 行为层：`testsuite/js/crontab_row_actions_probe.js` 在 jsdom + 假 jQuery/layer 上
    真跑 `getCronData()` 与 `getLogs()`，用真实 HTML 解析器回读属性、真触发委派
    点击，断言 6 类畸形任务名下都能正确调到对应函数且参数不失真。
"""
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
    with open(path, encoding='utf-8') as f:
        return f.read()


def _code_only(src):
    """去掉整行注释，避免注释里为了解释「不能这么写」而提到旧写法被误判。"""
    return '\n'.join(l for l in src.splitlines() if not l.strip().startswith('//'))


class TestCrontabFrontendInlineJs(unittest.TestCase):

    def test_01_no_user_data_in_inline_js(self):
        code = _code_only(_read(CRONTAB_JS))
        for bad in ('javascript:startTask(', 'javascript:getLogs(',
                    'javascript:editTaskInfo(', 'javascript:planDel(',
                    'onclick="startTask('):
            self.assertFalse(bad in code, '任务名不能再拼进内联 JS：%s' % bad)

    def test_02_row_actions_use_data_attributes_and_delegation(self):
        code = _code_only(_read(CRONTAB_JS))
        for act in ('run', 'edit', 'log', 'del', 'toggle'):
            self.assertTrue('data-cron-act="%s"' % act in code or 'data-cron-act=\\"%s\\"' % act in code,
                            '缺少 data-cron-act=%s' % act)
        self.assertTrue("$(document).off('click.cronRowAct').on('click.cronRowAct', '.cron-row-act'" in code,
                        '必须用命名空间事件委派（pjax 重进页面不能叠加监听器）')

    def test_03_log_dialog_button_has_no_inline_js(self):
        src = _read(CRONTAB_JS)
        self.assertTrue("layero.find('#cron_log_run').on('click'" in src,
                        '日志弹窗的执行按钮必须用闭包变量绑事件')
        self.assertTrue('cronEsc(task_name)' in src, '弹窗里显示的任务名必须转义')

    def test_04_onerror_hook_does_not_call_missing_console_api(self):
        code = _code_only(_read(SYSTEMD_JS))
        self.assertFalse('console.fail(' in code,
                         'console.fail 不存在，会让错误钩子自己抛 TypeError 并吞掉真错')
        self.assertTrue('console.error(' in code, '错误仍要落到控制台')

    def test_05_jsdom_probe_row_actions(self):
        """jsdom 真跑：畸形任务名下 执行/编辑/日志/删除/启停 都能调到正确函数。"""
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过前端行为夹具')
        env = dict(os.environ)
        env.pop('CRONTAB_JS', None)
        proc = subprocess.run(
            [node, PROBE],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        out = proc.stdout.decode('utf-8', 'replace').strip()
        err = proc.stderr.decode('utf-8', 'replace').strip()
        self.assertTrue(out.startswith('{'), '夹具没有输出 JSON，stderr=%s' % err[:2000])
        res = json.loads(out)
        self.assertTrue(res['ok'], '行内操作夹具失败：%s' % json.dumps(res['failures'][:20], ensure_ascii=False))
        self.assertGreater(len(res['checks']), 100)


if __name__ == '__main__':
    unittest.main()
