# coding: utf-8
"""A12 setting 面板设置模块的回归守卫(真机测试轮次产出)。

覆盖本轮真机实测发现并修复的问题:

1. `/setting/get_app_list` 的裸 `int(page)` / `int(limit)` → 真机 `page=abc` 返回 500;
2. `/setting/get_temp_login` 的裸 `int(p)` / `int(limit)` → 真机 `limit=abc` 返回 500;
3. `/setting/set_notify_email_test` / `set_notify_tgbot_test` 裸 `json.loads` → 500;
4. `data/menu.json` 的坏条目(缺 `id` / 非 str / 非 dict)会让全站 500
   (`layout.html` 用 `t('menu.' + item.id, ...)` 拼 key);
5. `templates/default/setting.html` 把 `item.path` / `item.warning` 原样拼进
   行内 `onclick="compressBtBackup('...')"` / `deleteBtBackup('...')` → 属性逃逸 XSS;
6. `config.js` 的「拼接字面量被整段复制」损坏(214 处 → 见清单)。

写法约定:与仓库既有 A0x 守卫一致 —— 结构断言用 `ast` / 正则均要求
「回退修复即变红」,不做弱断言。
"""
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTING_DIR = os.path.join(ROOT, 'web', 'admin', 'setting')
SETTING_HTML = os.path.join(ROOT, 'web', 'templates', 'default', 'setting.html')
CONFIG_JS = os.path.join(ROOT, 'web', 'static', 'app', 'config.js')
UTILS_CONFIG = os.path.join(ROOT, 'web', 'utils', 'config.py')


def _read(path):
    with open(path, encoding='utf-8') as fp:
        return fp.read()


def _func_src(path, name):
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(_read(path), node) or ''
    raise AssertionError('function %s not found in %s' % (name, path))


class PagingParamHardeningTest(unittest.TestCase):
    """1+2:分页 / 行数参数必须是容错的,而不是裸 int()。"""

    def test_01_get_app_list_does_not_bare_int_cast(self):
        src = _func_src(os.path.join(SETTING_DIR, 'app.py'), 'get_app_list')
        self.assertNotRegex(
            src, r"int\(\s*(page|limit)\s*\)",
            'get_app_list 又出现了裸 int(page)/int(limit):非数字入参会 500')
        self.assertIn('_parse_page_args', src,
                      'get_app_list 必须走容错解析(下限夹取 + 非数字回退默认页)')

    def test_02_get_temp_login_does_not_bare_int_cast(self):
        src = _func_src(os.path.join(SETTING_DIR, 'temp_login.py'), 'get_temp_login')
        self.assertNotRegex(
            src, r"int\(\s*(p|limit)\s*\)",
            'get_temp_login 又出现了裸 int(p)/int(limit):非数字入参会 500')
        self.assertIn('_parse_page_args', src,
                      'get_temp_login 必须走容错解析')

    def test_03_parse_page_args_behaviour(self):
        """直接跑辅助函数,验证边界(不在 Flask 里也能测)。"""
        src = _read(os.path.join(SETTING_DIR, 'setting.py'))
        ns = {'re': re}
        tree = ast.parse(src)
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == '_parse_page_args')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<a12>', 'exec'), ns)
        parse = ns['_parse_page_args']
        # 正常
        self.assertEqual(parse('3', '20'), (3, 20))
        # 非数字 → 回退默认
        self.assertEqual(parse('abc', 'xyz'), (1, 10))
        self.assertEqual(parse(None, None), (1, 10))
        # 越界 → 夹取
        self.assertEqual(parse('0', '0'), (1, 1))
        self.assertEqual(parse('-5', '-9'), (1, 1))
        self.assertEqual(parse('1', '999999'), (1, 100))
        self.assertEqual(parse('1e9', '5'), (1, 5))
        self.assertEqual(parse('True', '5'), (1, 5))
        self.assertEqual(parse('', ''), (1, 10))
        self.assertEqual(parse(' 7 ', ' 8 '), (7, 8))


class MenuConfigHardeningTest(unittest.TestCase):
    """4:menu.json 的坏条目必须被跳过,否则全站 500。"""

    def test_04_get_menu_config_filters_bad_items(self):
        src = _func_src(UTILS_CONFIG, 'get_menu_config')
        self.assertIn('_filter_menu_items', src,
                      'get_menu_config 必须过滤坏条目(缺 id / 非 str / 非 dict)')

    def test_05_filter_menu_items_behaviour(self):
        src = _read(UTILS_CONFIG)
        ns = {}
        tree = ast.parse(src)
        nodes = [n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == '_filter_menu_items']
        self.assertTrue(nodes, '缺少 _filter_menu_items')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<a12>', 'exec'), ns)
        f = ns['_filter_menu_items']
        good = {'id': 'memuA', 'name': '首页', 'class': 'menu_home', 'url': '/', 'show': True}
        self.assertEqual(f([good]), [good])
        # 坏条目全部被丢弃
        for bad in ([{'name': 'x'}],                      # 缺 id
                    [{'id': None}],                       # id 非 str
                    [{'id': 123}],                        # id 非 str
                    [{'id': ''}],                         # id 空
                    ['not-a-dict'],                       # 非 dict
                    [None],
                    [{'id': 'memuA', 'show': 'yes'}],     # show 非 bool
                    [{'id': 123, 'name': 'x'}],           # id 非 str
                    [{'id': 'memuA', 'url': 5}],          # url 非 str
                    [{'id': 'memuA', 'class': 7}],        # class 非 str
                    [{'id': 'memuA', 'name': None}]):     # name 非 str
            self.assertEqual(f(bad), [], '坏条目必须被丢弃:%r' % (bad,))
        # 非 list 输入
        self.assertEqual(f(None), [])
        self.assertEqual(f({'id': 'x'}), [])
        self.assertEqual(f('abc'), [])
        # 混合:只留好的
        self.assertEqual(f([bad[0], good]), [good])

    def test_06_menu_guard_also_covers_templates(self):
        """模板里的 t('menu.' + item.id) 只在 id 是 str 时才安全 —— 由过滤保证。"""
        html = _read(os.path.join(ROOT, 'web', 'templates', 'default', 'layout.html'))
        self.assertIn("t('menu.' + item.id", html,
                      'layout.html 的菜单 key 拼法变了,请同步复核过滤逻辑')

    def test_06b_save_menu_config_validates_before_write(self):
        """写入侧也必须校验:坏条目一旦落盘就会锁死全站。"""
        src = _func_src(os.path.join(SETTING_DIR, 'setting.py'), 'save_menu_config')
        self.assertIn('_filter_menu_items', src,
                      'save_menu_config 写入前必须过滤坏条目')
        self.assertRegex(
            src, r'if\s+len\(valid\)\s*!=\s*len\(menus\)',
            'save_menu_config 必须拒绝「含坏条目」的提交,而不是静默丢弃')


class SettingTemplateEscapeTest(unittest.TestCase):
    """5:setting.html 的行内 onclick 必须走转义助手。"""

    @staticmethod
    def _onclick_args(html, fn_name):
        """抽出所有 `onclick="<fn>(...)"` 的属性值。"""
        args = []
        marker = 'onclick="' + fn_name + '('
        idx = html.find(marker)
        while idx != -1:
            start = idx + len('onclick="')
            j = start
            while j < len(html):
                if html[j] == '\\':
                    j += 2
                    continue
                if html[j] == '"':
                    break
                j += 1
            args.append(html[start:j])
            idx = html.find(marker, idx + 1)
        return args

    def test_07_bt_backup_onclick_uses_escape_helper(self):
        html = _read(SETTING_HTML)
        # 行内属性里每一个「可空字段」都必须经 yfSettingJsStr 包一层 ——
        # 只有逐个断言才能抓住「某一处忘了加」的回归。
        expected = {
            'compressBtBackup': ["+yfSettingJsStr(item.path)+"],
            'deleteBtBackup': ["+yfSettingJsStr(item.path)+",
                               "+yfSettingJsStr(item.warning || '')+"],
        }
        for fn, fragments in expected.items():
            args = self._onclick_args(html, fn)
            self.assertTrue(args, '%s 的行内 onclick 锚点没找到(模板结构变了?)' % fn)
            joined = '\n'.join(args)
            for frag in fragments:
                self.assertIn(frag, joined,
                              '%s 的行内 onclick 缺转义调用:%s\n实参=%r'
                              % (fn, frag, args))
            self.assertNotIn("openPath(''+item", joined)
        # openPath 也同样必须过 JS 字符串转义
        op_args = self._onclick_args(html, 'openPath')
        self.assertTrue(op_args, 'openPath 的行内 onclick 锚点没找到')
        for arg in op_args:
            self.assertIn('yfSettingJsStr(', arg,
                          'openPath 实参未过 JS 字符串转义:%r' % arg)
        # 返回给 HTML 的字段也要过 HTML 转义
        self.assertIn('yfSettingEsc(item.path)', html)
        self.assertIn('yfSettingEsc(item.warning)', html)
        self.assertIn('yfSettingEsc(item.desc)', html)
        self.assertIn('yfSettingEsc(item.size)', html)

    def test_08_escape_helpers_have_required_replacements(self):
        html = _read(SETTING_HTML)
        start = html.find('function yfSettingEsc')
        self.assertGreater(start, 0, '缺少 yfSettingEsc')
        end = html.find('function loadBtBackups', start)
        seg = html[start:end]
        self.assertGreater(end, start, '找不到 yfSettingEsc/yfSettingJsStr 的结束边界')
        esc_body = seg[:seg.find('function yfSettingJsStr')]
        js_body = seg[seg.find('function yfSettingJsStr'):]
        # HTML 上下文:& 必须**最先**替换,否则后续实体会被二次转义
        order = [".replace(/&/g, '&amp;')", ".replace(/</g, '&lt;')",
                 ".replace(/>/g, '&gt;')", '.replace(/"/g, \'&quot;\')',
                 ".replace(/'/g, '&#39;')"]
        pos = -1
        for frag in order:
            i = esc_body.find(frag)
            self.assertGreater(i, pos, 'yfSettingEsc 缺/乱序替换:%s' % frag)
            pos = i
        # JS 字面量上下文:反斜杠、单引号、换行、尖括号都必须处理
        for frag in (".replace(/\\\\/g, '&#92;')", ".replace(/'/g, '&#39;')",
                     '.replace(/\\r/g,', '.replace(/\\n/g,'):
            self.assertIn(frag, js_body, 'yfSettingJsStr 缺替换:%s' % frag)


class BackupPathHardeningTest(unittest.TestCase):
    """备份压缩/删除的路径校验(修前能写出 /etc.zip、能删站外目录)。"""

    def test_12_bt_backup_path_rejects_traversal(self):
        src = _read(os.path.join(SETTING_DIR, 'setting.py'))
        ns = {'os': os}
        tree = ast.parse(src)
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == '_safe_bt_backup_path')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<a12>', 'exec'), ns)
        safe = ns['_safe_bt_backup_path']
        # 非法
        for bad in ('', None, '/etc', '/etc/passwd', '/www/server/../../../etc',
                    '/www/server/../../tmp/yftest', '/www/server/../server',
                    '/www/other', 'www/server/data_bt_bak', '/www/server/',
                    '/www/server\x00/evil'):
            self.assertEqual(safe(bad), '', '必须拒绝:%r' % (bad,))
        # 白名单根目录自身也拒绝(删/压 /www/server 本身就是灾难)
        if os.path.exists('/www/server'):
            self.assertEqual(safe('/www/server'), '', '/www/server 自身必须拒绝')
            self.assertNotEqual(safe('/www/server/yufeng_panel'), '',
                                '/www/server 下的子目录必须放行')

    def test_13_backup_handlers_use_the_validator(self):
        for name in ('compress_bt_backup', 'delete_bt_backup'):
            src = _func_src(os.path.join(SETTING_DIR, 'setting.py'), name)
            self.assertIn('_safe_bt_backup_path(', src,
                          '%s 必须走 _safe_bt_backup_path 校验' % name)
        # 压缩不能再拼 shell
        src = _func_src(os.path.join(SETTING_DIR, 'setting.py'), 'compress_bt_backup')
        self.assertIn('execShellRc', src, 'compress_bt_backup 不得再拼 shell 执行 zip')
        self.assertNotIn('&& zip -r', src)


class PortSettingHardeningTest(unittest.TestCase):
    """set_port:非法/越界/带攻击载荷的端口不得写进 data/port.pl(否则面板自锁)。"""

    def test_14_set_port_validates_before_write(self):
        src = _func_src(os.path.join(SETTING_DIR, 'setting.py'), 'set_port')
        self.assertIn('parsePortSpec', src, 'set_port 必须走端口白名单')  # 复用 A04 的解析器
        self.assertRegex(
            src, r'if\s+span\s+is\s+None',
            'set_port 必须在写盘前拒绝非法端口')
        # 校验必须在 setHostPort 之前
        self.assertLess(src.index('parsePortSpec'), src.index('setHostPort'),
                        'set_port 必须先校验后写盘')


class AppStatusHardeningTest(unittest.TestCase):
    """toggle_app_status:不存在的 id 不得 500。"""

    def test_15_toggle_app_status_checks_existence(self):
        src = _func_src(os.path.join(SETTING_DIR, 'app.py'), 'toggle_app_status')
        self.assertIn('getAppById', src, 'toggle_app_status 必须先判 id 存在性(否则 500)')


class MigrateSitesHardeningTest(unittest.TestCase):
    """migrate_sites:函数内 `import os` 会让外层 `os.path` 抛 UnboundLocalError。"""

    def test_16_no_local_import_os_in_migrate_handlers(self):
        for name in ('migrate_sites', 'migrate_restore'):
            src = _func_src(os.path.join(SETTING_DIR, 'setting.py'), name)
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names]
                    self.assertNotIn('os', names,
                                     '%s 里又在函数内 `import os` 了(会把 os 变局部名)' % name)
                    self.assertNotIn('sys', names,
                                     '%s 里又在函数内 `import sys` 了' % name)


class TimezoneHardeningTest(unittest.TestCase):
    """set_timezone:参数不得拼 shell,且非法值不得假成功。"""

    def test_17_set_timezone_is_argument_safe(self):
        src = _func_src(os.path.join(SETTING_DIR, 'timezone.py'), 'set_timezone')
        tree = ast.parse(src)
        # 不得再把 timezone 参数拼进 shell 字符串(白名单 + 参数表执行)
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                seg = ast.get_source_segment(src, node) or ''
                self.assertNotIn('timezone', seg,
                                 'set_timezone 又用字符串拼接构造命令:%r' % seg)
            if isinstance(node, ast.JoinedStr):        # f-string
                seg = ast.get_source_segment(src, node) or ''
                self.assertNotIn('timezone', seg,
                                 'set_timezone 又用 f-string 构造命令:%r' % seg)
        self.assertIn('all_timezones', src, 'set_timezone 必须校验时区名(白名单)')
        self.assertIn('execShellRc', src, 'set_timezone 必须看退出码(否则假成功)')
        self.assertIn('shell=False', src, 'set_timezone 不得走 shell')


class ConfigJsDupLiteralTest(unittest.TestCase):
    """6:config.js 的「字面量整段复制」—— 只允许剩下已冻结的精确行号。"""

    #: 已知未闭环(乙类:两种解读可见文本等价,改动会静默改前端结构)。
    #: **按文件 + 行号精确冻结**:新出现的命中会因不在清单里而失败;修好一条就删一行。
    FROZEN = (
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

    def test_09_config_js_dup_literal_hits_match_frozen_list(self):
        from testsuite import test_frontend_literal_hygiene as G
        hits = sorted(h for h in G._scan()
                      if h.startswith('web/static/app/config.js:'))
        frozen = sorted(self.FROZEN)
        self.assertEqual(
            hits, frozen,
            'config.js 的「字面量整段复制」命中与冻结清单不一致:\n'
            '  新增(必须修):%s\n  已修好(请从冻结清单删掉):%s'
            % (sorted(set(hits) - set(frozen)), sorted(set(frozen) - set(hits))))

    def test_10_fixed_sites_are_really_de_duplicated(self):
        """甲类修复点:同一行里同一个开标签不得再出现两次相邻复制。"""
        text = _read(CONFIG_JS)
        from testsuite import test_frontend_literal_hygiene as G
        for ln in (417, 642, 1039, 1259, 1276, 1292, 1359, 1491, 1494, 1497):
            line = text.split('\n')[ln - 1]
            self.assertIsNone(G._PAT.search(line),
                              'line %d 又出现整段复制:%.80s' % (ln, line))

    def test_11_fixed_sites_keep_single_copy_of_literal(self):
        """甲类修复必须是「删重」而不是「删内容」:被去重的那段字面量仍出现一次。"""
        text = _read(CONFIG_JS).split('\n')
        cases = {1292: "'<option value=\"none\">'",
                 1497: "'<a>'",
                 1491: "'<a style=\"color:green;\">'",
                 1494: "'<a style=\"color:brown;\">'",
                 417: '<div class="bt-form bt-form pd20">'}
        for ln, lit in cases.items():
            self.assertEqual(text[ln - 1].count(lit), 1,
                             'line %d 的 %r 应恰好出现一次(去重不能连内容一起删)'
                             % (ln, lit))


if __name__ == '__main__':
    unittest.main()