# coding: utf-8
"""A03 files 模块回归守卫（真机功能测试轮：路径穿越 / 假成功 / XSS 修复）。

本轮在 Debian 真机上把文件管理的主要路径跑通，暴露并修掉以下缺陷：

1. 回收站任意文件删除：`delRecycleBin(path)` 直接把 `path` 拼在回收站目录后
   （实测 `path=../../../tmp/yf_A03_victim.txt` → HTTP 200 且文件真的被删），
   且条目不存在时 `os.remove` 抛异常 → 500。
2. 回收站任意文件搬运：`reRecycleBin(path)` 的源是 `rb_dir + '/' + path`
   （可 `../` 逃逸），目标是把条目名反解出来的**相对路径**并按面板 cwd 解析：
   实测 `path=yf_A03_rb_x`（回收站里任意一个文件）被搬进
   `/www/server/yufeng_panel/web/`；`path=../../../../tmp/x_yf_y` 还能跨目录搬运。
3. 任意文件读取：`GET /files/download?filename=/etc/shadow` 未过 `safePath`
   → 实测 200 + 1028 字节 shadow；`/files/get_last_body` 同理能读 shadow 末行；
   `zip` 的 `sfile` 未校验 → 实测把 `/etc/passwd` 压进可下载的 zip。
4. 假成功：`createFile` 的 except 分支返回 `status=True`（消息却是“文件创建失败”），
   前端按成功图标提示。
5. 存储型 XSS：`files.js` 把磁盘上的文件名/路径直接拼进列表 HTML 与行内 onclick
   （实测 `get_dir` JSON 原样回显 `<img src=x onerror=alert(1)>.txt`）。

断言分两层：能真跑的函数（回收站两个入口）用**真实文件系统**执行；路由/前端
接入用 AST 与源码结构断言，避免被注释或 `if False:` 蒙混。
"""
import ast
import logging
import os
import re
import shutil
import sys
import tempfile
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

FILE_PY = 'web/utils/file.py'
FILES_PY = 'web/admin/files/files.py'
FILES_JS = 'web/static/app/files.js'


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


def _func_src(rel, name):
    """取某个函数的源码文本（按 AST 行号切片，注释/字符串不影响定位）。"""
    src = _read(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s' % name)


def _returns_in_except(rel, func_name):
    """收集函数内 except 处理器里 `yf.returnData/returnJson(第一个实参)` 的取值。"""
    src = _read(rel)
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.ExceptHandler):
                    continue
                for call in ast.walk(sub):
                    if not isinstance(call, ast.Call):
                        continue
                    fn = call.func
                    attr = getattr(fn, 'attr', '')
                    if attr in ('returnData', 'returnJson') and call.args:
                        out.append(call.args[0])
    return out


def _calls_in_func(rel, func_name, callee_text):
    """函数体里是否出现某个调用（按源码文本，含关键字形式）。"""
    body = _func_src(rel, func_name)
    return callee_text in body


class TestRecycleBinGuard(unittest.TestCase):
    """把 web/utils/file.py 的回收站入口抽出来，对真实临时目录执行。"""

    @classmethod
    def setUpClass(cls):
        src = _read(FILE_PY)
        tree = ast.parse(src)
        want_assign = {'_SENSITIVE_PATHS', '_SENSITIVE_EXACT', '_PANEL_SENSITIVE_REL'}
        want_func = {'_posix_norm', 'safePath', '_recycleBinEntry',
                     'delRecycleBin', 'reRecycleBin'}
        keep = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', '') in want_assign for t in node.targets):
                keep.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in want_func:
                keep.append(node)

        class _FakeYf:
            rb_dir = ''
            panel_dir = '/www/server/yufeng_panel'

            @classmethod
            def getRecycleBinDir(cls):
                os.makedirs(cls.rb_dir, exist_ok=True)
                return cls.rb_dir

            @classmethod
            def getPanelDir(cls):
                return cls.panel_dir

            @staticmethod
            def _pack(status, msg, data=None):
                return {'status': status, 'msg': msg, 'data': data}

            @classmethod
            def returnData(cls, status, msg, data=None, *args):
                return cls._pack(status, msg, data)

            @classmethod
            def returnJson(cls, status, msg, data=None, *args):
                return cls._pack(status, msg, data)

            @staticmethod
            def getInfo(tpl, args=()):
                return tpl

            @staticmethod
            def writeLog(*a, **k):
                return True

        ns = {'os': os, 'shutil': shutil, 'time': __import__('time'),
              '_log': logging.getLogger('files-a03-test'), 'yf': _FakeYf}
        exec(compile(ast.Module(body=keep, type_ignores=[]), FILE_PY, 'exec'), ns)
        cls.yf = _FakeYf
        cls.delRecycleBin = staticmethod(ns['delRecycleBin'])
        cls.reRecycleBin = staticmethod(ns['reRecycleBin'])
        cls.entry = staticmethod(ns['_recycleBinEntry'])

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='yf_a03_rb_'))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.rb_dir = os.path.join(self.root, 'recycle_bin')
        os.makedirs(self.rb_dir)
        self.yf.rb_dir = self.rb_dir
        self.outside = os.path.join(self.root, 'outside.txt')
        with open(self.outside, 'w', encoding='utf-8') as f:
            f.write('victim')

    # ---- 任意删除 ----

    def test_01_del_recycle_bin_rejects_traversal(self):
        """修复前：path=../.. 直接删掉回收站外的真实文件。"""
        r = self.delRecycleBin('../outside.txt')
        self.assertFalse(r['status'], r)
        self.assertTrue(os.path.exists(self.outside), '回收站外的文件被删掉了')

    def test_02_del_recycle_bin_rejects_absolute(self):
        r = self.delRecycleBin(self.outside)
        self.assertFalse(r['status'], r)
        self.assertTrue(os.path.exists(self.outside))

    def test_03_del_recycle_bin_purges_entry(self):
        entry = os.path.join(self.rb_dir, 'www_yf_wwwroot_yf_a.txt_t_1')
        with open(entry, 'w', encoding='utf-8') as f:
            f.write('x')
        r = self.delRecycleBin('www_yf_wwwroot_yf_a.txt_t_1')
        self.assertTrue(r['status'], r)
        self.assertFalse(os.path.exists(entry))

    def test_04_del_recycle_bin_purges_dir_and_symlink(self):
        d = os.path.join(self.rb_dir, 'dir_entry_t_2')
        os.makedirs(d)
        link = os.path.join(self.rb_dir, 'link_entry_t_3')
        try:
            os.symlink(self.outside, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest('当前平台不支持创建软链')
        self.assertTrue(self.delRecycleBin('dir_entry_t_2')['status'])
        self.assertFalse(os.path.exists(d))
        r = self.delRecycleBin('link_entry_t_3')
        self.assertTrue(r['status'], r)
        self.assertFalse(os.path.lexists(link))

    def test_05_del_recycle_bin_missing_entry_no_raise(self):
        """修复前：条目不存在 -> os.remove 抛异常 -> 路由 500。"""
        r = self.delRecycleBin('no_such_entry_t_9')
        self.assertFalse(r['status'], r)

    # ---- 任意搬运 / 还原 ----

    def test_06_re_recycle_bin_rejects_traversal(self):
        r = self.reRecycleBin('../../../outside.txt')
        self.assertFalse(r['status'], r)
        self.assertTrue(os.path.exists(self.outside))

    def test_07_re_recycle_bin_rejects_fabricated_entry(self):
        """回收站里存在但没有任何 `_t_` 时间戳的条目：dst 会退化成 cwd 相对路径。"""
        entry = os.path.join(self.rb_dir, 'yf_A03_rb_x')
        with open(entry, 'w', encoding='utf-8') as f:
            f.write('payload')
        r = self.reRecycleBin('yf_A03_rb_x')
        self.assertFalse(r['status'], r)
        self.assertTrue(os.path.exists(entry), '条目被搬出回收站目录了')

    @unittest.skipIf(os.name == 'nt', '回收站条目名按 POSIX 路径生成，含 ntpath 非法字符 \':\'，仅能在 Linux 实测')
    def test_08_re_recycle_bin_restores_absolute_entry(self):
        """正常条目（原路径 + _t_<时间戳>）必须能还原回原位置。"""
        orig_dir = os.path.join(self.root, 'site')
        os.makedirs(orig_dir)
        orig = os.path.join(orig_dir, 'a.txt')
        with open(orig, 'w', encoding='utf-8') as f:
            f.write('data')
        entry_name = orig.replace('\\', '/').replace('/', '_yf_') + '_t_1234567890'
        entry = os.path.join(self.rb_dir, entry_name)
        shutil.move(orig, entry)

        r = self.reRecycleBin(entry_name)
        self.assertTrue(r['status'], r)
        self.assertTrue(os.path.exists(orig), '未还原到原路径')
        self.assertFalse(os.path.exists(entry))

    def test_09_entry_resolves_inside_recycle_dir(self):
        rb_dir, path = self.entry('www_yf_wwwroot_yf_a.txt_t_1')
        self.assertEqual(os.path.dirname(path), os.path.realpath(self.rb_dir))
        self.assertTrue(path.startswith(os.path.realpath(self.rb_dir) + os.sep))
    def test_10_entry_helper_blocks_separators_and_nul(self):
        for bad in ('a/b_t_1', '..', '.', '', None, 'a\x00b_t_1', '\\windows\\x_t_1'):
            rb_dir, path = self.entry(bad)
            self.assertIsNone(path, repr(bad))


class TestSafePathCoverage(unittest.TestCase):
    """读/写/归档入口必须全部走 safePath（真机实测的 /etc/shadow 读取面）。"""

    def test_11_zip_sfile_checked(self):
        body = _func_src(FILE_PY, 'zip')
        self.assertIn('safePath(sf)', body, 'zip 未校验被压缩对象')
        self.assertIn("sfile.split(',')", body)

    def test_12_unzip_uncompress_sfile_checked(self):
        for fn in ('unzip', 'uncompress'):
            body = _func_src(FILE_PY, fn)
            self.assertIn('safePath(sfile)', body, '%s 未校验压缩包路径' % fn)

    def test_13_routes_guard_read_entrypoints(self):
        for fn, token in (('download', 'file.safePath(filename)'),
                          ('get_file_last_body', 'file.safePath(path)')):
            self.assertTrue(_calls_in_func(FILES_PY, fn, token),
                            '%s 未走 safePath' % fn)

    def test_14_create_file_reports_failure(self):
        """createFile 的 except 分支不能返回 status=True（消息是“文件创建失败”）。"""
        args = _returns_in_except(FILE_PY, 'createFile')
        self.assertTrue(args, 'createFile 里没有 except 返回值？')
        for arg in args:
            self.assertIsInstance(arg, ast.Constant, 'except 分支的 status 必须是字面量')
            self.assertIs(arg.value, False, 'createFile 失败仍返回 status=True')


def _norm_js(src):
    """去整行注释 + 压缩空白：把 `if (false)` 之流的遮蔽器暴露成文本差异。"""
    src = re.sub(r'/\*[\s\S]*?\*/', ' ', src)
    src = re.sub(r'(?m)^\s*//.*$', '', src)
    return re.sub(r'\s+', ' ', src)


class TestFilesJsEscaping(unittest.TestCase):
    """前端把磁盘文件名/路径拼进 HTML：必须有转义（真机实测原样回显 <img onerror>）。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _norm_js(_read(FILES_JS))

    def test_15_helpers_defined(self):
        for header in ('function yfFilesText(v)', 'function yfFilesJsStr(v)',
                       'function yfFilesRecycleItem(it)'):
            self.assertIn(header, self.js, '缺少转义助手 ' + header)

    def test_16_recycle_bin_rows_escaped(self):
        # 两条 map 必须是回收站回调里紧跟着 rdata 取值的语句（不被 if 包住）
        self.assertIn(
            "var rdata = data['data']; "
            "rdata.dirs = (rdata.dirs || []).map(yfFilesRecycleItem); "
            "rdata.files = (rdata.files || []).map(yfFilesRecycleItem); var body = ''",
            self.js, '回收站条目未在此处统一转义')

    def test_17_get_dir_escapes_names_and_path(self):
        self.assertIn(
            "var rawPath = rdata.path; "
            "if (typeof rdata.path === 'string') { rdata.path = yfFilesJsStr(rdata.path); }",
            self.js, '路径未做转义')
        self.assertIn('fmp[0] = yfFilesJsStr(rawName);', self.js, '文件名未做转义')
        self.assertIn('cnametext = yfFilesText(cnametext);', self.js, '展示文本未做转义')
        self.assertNotIn("fmp[0].replace(/'/", self.js, '旧的仅处理单引号的拼接方式残留')

    def test_18_breadcrumb_and_tabs_escaped(self):
        for token in ('yfFilesText(parts[i])', 'yfFilesText(tabs[i].name)'):
            self.assertIn(token, self.js, '未转义：' + token)


if __name__ == '__main__':
    unittest.main()
