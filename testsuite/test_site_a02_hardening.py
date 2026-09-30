# coding: utf-8
"""A02 site 模块回归守卫（真机功能测试轮：安全/可靠性修复）。

本轮在真机上把 site 模块的主要路径跑通并暴露了 10 类缺陷，这里逐条锁死：

1. `/site/list` 的搜索框形同虚设 + SQL 注入
   `thisdb.getSitesList` 把 `search` 直接拼进 WHERE：`type_id >= 0` 时它会被
   `" type_id=N"` 覆盖（搜索失效），`type_id=-1` 时原样进 SQL（`' or 1=1 --`
   实测可布尔盲注）；`order` 也直接拼进 ORDER BY（实测 `(select 1)` 可注入，
   非法列名静默返回空列表却仍报 count=2）。
2. 命令注入：`delProxy` 用 `rm -rf {path}.conf*` 拼 shell（`id=y; touch /tmp/x`
   实测在 root 下创建了文件）；`toBackup` 用 `cd '<站点路径>' && zip ...` 拼 shell
   且没有超时。
3. 路径穿越：站点名/模板名/证书名直接拼路径 —— `get_host_conf`、`set_rewrite`
   （实测能写 /tmp 任意文件）、`set_rewrite_tpl`（实测写到 /www/tmp/）、
   `remove_cert`（rmtree）都能用 `../../` 逃出配置目录。
4. 状态假阳性：`add()` 不校验生成的 nginx 配置（非法端口会写坏 vhost，接口仍报
   成功）；`setPhpVersion` 任意版本号都写进 vhost（`enable-php-zz.conf` 不存在
   → nginx -t 失败），同样报“切换成功”。
5. 未转义回显：站点备注（`ps`）与站点名直接拼进列表 HTML + 行内 onclick =
   存储型 XSS（实测 `ps=<img src=x onerror=alert(1)>` 原样存库）。
6. 500 面：`get_backup` 空分页参数 `int('')`、`del_backup` 不存在的 id、
   `set_redirect type=domain` 站点不存在时 `domain_list[0]`，全部 500。
7. 其他：`addDirBind` 目录名为空时缺 `return`（继续把站点根绑成子目录）、
   `delRedirect` 不 reload（删掉规则但 nginx 仍 301）、`setRewrite` 成功不清理
   `_bak`（目录无限堆积）。

断言尽量用 AST 结构 + 真实函数调用，避免被注释或 `if False:` 蒙混。
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.site import sites, safeSiteName, isSafePathInside  # noqa: E402
import utils.site as site_utils  # noqa: E402
import thisdb  # noqa: E402
from thisdb import backup as thisdb_backup  # noqa: E402

SITE_UTILS = os.path.join(WEB, 'utils', 'site.py')
SITE_JS = os.path.join(WEB, 'static', 'app', 'site.js')
THISDB_SITES = os.path.join(WEB, 'thisdb', 'sites.py')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _func_node(rel_path, name, cls=None):
    """按 AST 取函数节点（结构断言，不怕注释/字符串蒙混）。"""
    tree = ast.parse(_read(rel_path))
    body = list(ast.walk(tree))
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            if cls is None:
                return node
            # 只取指定类里的方法
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and parent.name == cls:
                    if node in parent.body:
                        return node
    raise AssertionError('未找到函数 %s' % name)


def _func_src(rel_path, name, cls=None):
    src = _read(rel_path)
    node = _func_node(rel_path, name, cls)
    seg = ast.get_source_segment(src, node)
    return seg or ''


def _call_names(node):
    names = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                names.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                base = fn.value.id if isinstance(fn.value, ast.Name) else ''
                names.append((base + '.' if base else '') + fn.attr)
    return names


def _unsafe_exec_shell_calls(node):
    """非 safeExecShell 的 execShell 调用（safeExecShell 不算）。"""
    hits = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == 'execShell':
                base = sub.func.value.id if isinstance(sub.func.value, ast.Name) else ''
                if base == 'yf':
                    hits.append(sub)
    return hits


class SafeSiteNameTest(unittest.TestCase):

    def test_01_rejects_traversal_and_separators(self):
        bad = ['', None, '..', '../../x', 'a/b', 'a\\b', '/etc/passwd',
               'x' * 101, 'a b', 'a\tb', 'a\nb', 'x\x00y']
        for value in bad:
            self.assertEqual(safeSiteName(value), '',
                             '不该放行：%r' % (value,))

    def test_02_allows_legit_names(self):
        good = ['www.test.com', 'yftest-a02-7c3f.test', '*.test.com',
                'a_b-c.test', '中文站点.test', '172.17.60.248']
        for value in good:
            self.assertEqual(safeSiteName(value), value,
                             '合法名字被误拦：%r' % (value,))

    def test_03_is_safe_path_inside(self):
        base = tempfile.mkdtemp(prefix='yf_a02_base_')
        try:
            inside = os.path.join(base, 'vhost', 'a.conf')
            self.assertTrue(isSafePathInside(base, inside))
            self.assertTrue(isSafePathInside(base, base))
            self.assertFalse(isSafePathInside(base, base + '/../other/file.conf'))
            self.assertFalse(isSafePathInside(base, '/etc/passwd'))
            self.assertFalse(isSafePathInside(base, ''))
            self.assertFalse(isSafePathInside('', inside))
        finally:
            shutil.rmtree(base, ignore_errors=True)


class HostConfNameGuardTest(unittest.TestCase):

    def _obj(self, vhost, rewrite=None):
        obj = sites.__new__(sites)
        obj.vhostPath = vhost
        obj.rewritePath = rewrite or vhost
        return obj

    def test_01_get_host_conf_rejects_traversal(self):
        obj = self._obj('/www/server/web_conf/nginx/vhost')
        self.assertEqual(obj.getHostConf('../../../../../../tmp/yf_probe_a02_read'), '')
        self.assertEqual(obj.getHostConf(''), '')
        self.assertEqual(obj.getRewriteConf('../../etc/passwd'), '')
        self.assertEqual(obj.getDirBindRewrite('site.test', '../../x'), '')
        self.assertEqual(obj.getHostConf('site.test'),
                         '/www/server/web_conf/nginx/vhost/site.test.conf')

    def test_02_set_rewrite_only_writes_inside_rewrite_dir(self):
        base = tempfile.mkdtemp(prefix='yf_a02_rw_')
        try:
            rewrite_dir = os.path.join(base, 'rewrite')
            os.makedirs(rewrite_dir)
            obj = self._obj(os.path.join(base, 'vhost'), rewrite_dir)
            evil = os.path.join(base, 'escaped.conf')
            res = obj.setRewrite(evil, 'INJECTED', 'utf-8')
            self.assertFalse(res['status'], '越界路径必须被拒绝')
            self.assertFalse(os.path.exists(evil), '越界文件不得被创建')
            # 走真实写入路径的越界尝试（含 .. 穿越）也必须被拒
            traversal = os.path.join(rewrite_dir, '..', 'escaped2.conf')
            res2 = obj.setRewrite(traversal, 'INJECTED', 'utf-8')
            self.assertFalse(res2['status'])
            self.assertFalse(os.path.exists(os.path.join(base, 'escaped2.conf')))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_03_save_host_conf_requires_vhost_dir(self):
        src = _func_src(SITE_UTILS, 'saveHostConf', cls='sites')
        self.assertIn('isSafePathInside(self.vhostPath, path)', src)
        # 守卫必须出现在任何写盘之前
        self.assertLess(src.find('isSafePathInside'), src.find('saveBody('))


class SiteListSqlTest(unittest.TestCase):

    def test_01_search_and_type_id_are_parameterized(self):
        src = _func_src(THISDB_SITES, 'getSitesList')
        # 旧实现的三个记号必须消失：拼 WHERE 的变量名与字符串拼接
        self.assertNotIn('sql_where', src)
        self.assertNotIn('name like \'%', src)
        self.assertIn('name like ? or ps like ?', src)
        calls = [n for n in ast.walk(_func_node(THISDB_SITES, 'getSitesList'))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'where']
        self.assertTrue(calls, 'getSitesList 必须用 where(...) 过滤')
        for call in calls:
            self.assertEqual(len(call.args), 2,
                             'where 必须同时传 SQL 与参数元组（参数化查询）')

    def test_02_order_is_whitelisted(self):
        self.assertEqual(thisdb.safeOrder('add_time desc'), 'add_time desc')
        self.assertEqual(thisdb.safeOrder('id asc'), 'id asc')
        for bad in ('(select 1)', 'id desc; drop table sites', 'id, (select 1)',
                    'none', '', None, 'zzz_not_exist'):
            self.assertEqual(thisdb.safeOrder(bad), '',
                             '不该放行排序：%r' % (bad,))

    def test_03_search_still_applies_with_negative_type_id(self):
        """type_id=-1 表示「全部分类」，此时 search 仍必须生效（旧实现会丢/拼错）。"""
        src = _func_src(THISDB_SITES, 'getSitesList')
        self.assertIn('if type_id >= 0:', src)
        self.assertIn("where += 'type_id=?'", src)
        self.assertIn('params.append(type_id)', src)


class ShellInjectionTest(unittest.TestCase):

    def test_01_del_proxy_has_no_shell(self):
        src = _func_src(SITE_UTILS, 'delProxy', cls='sites')
        self.assertNotIn('rm -rf', src)
        node = _func_node(SITE_UTILS, 'delProxy', cls='sites')
        self.assertEqual(_unsafe_exec_shell_calls(node), [],
                         'delProxy 不得再调用 execShell')
        self.assertIn('os.remove(', src)

    def test_02_to_backup_uses_safe_exec_with_timeout(self):
        node = _func_node(SITE_UTILS, 'toBackup', cls='sites')
        self.assertEqual(_unsafe_exec_shell_calls(node), [],
                         'toBackup 不得再用 execShell 拼 cd/zip')
        kws = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == 'safeExecShell':
                kws = {k.arg for k in sub.keywords}
        self.assertIn('cwd', kws)
        self.assertIn('timeout', kws, '备份必须带超时（大站点不能挂死面板）')
        self.assertNotIn("'cd '", _func_src(SITE_UTILS, 'toBackup', cls='sites'))


class AddSiteValidationTest(unittest.TestCase):

    def test_01_add_validates_name_port_and_config(self):
        src = _func_src(SITE_UTILS, 'add', cls='sites')
        self.assertIn('safeSiteName(', src)
        self.assertIn('yf.checkPort(', src)
        self.assertIn('yf.checkWebConfig()', src)
        # 校验失败必须回滚 DB 与配置，而不是留一个坏的 vhost
        self.assertIn('thisdb.deleteSitesById(site_id)', src)
        self.assertIn('yf.deleteFile(self.getHostConf(self.siteName))', src)

    def test_02_set_php_version_validates_and_rolls_back(self):
        src = _func_src(SITE_UTILS, 'setPhpVersion', cls='sites')
        self.assertIn('enable-php-', src)
        self.assertIn('os.path.exists(', src)
        self.assertIn('yf.checkWebConfig()', src)
        self.assertIn('yf.writeFile(file, old_conf)', src)

    def test_03_add_dir_bind_returns_on_empty_dir(self):
        """空目录名必须真的 return（历史上少了 return，会把站点根绑成子目录）。"""
        node = _func_node(SITE_UTILS, 'addDirBind', cls='sites')
        guarded = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and 'dir_name' in ast.dump(sub.test):
                if any(isinstance(x, ast.Return) for x in sub.body):
                    guarded = True
        self.assertTrue(guarded, 'addDirBind 必须对空 dir_name 提前 return')
        self.assertIn('return yf.returnData(False, \'file.dir_empty\')',
                      _func_src(SITE_UTILS, 'addDirBind', cls='sites'))


class FailurePathTest(unittest.TestCase):

    def test_01_del_redirect_reloads_web(self):
        node = _func_node(SITE_UTILS, 'delRedirect', cls='sites')
        self.assertIn('yf.restartWeb', _call_names(node),
                      '删除重定向后必须 reload，否则 nginx 仍按旧规则 301')

    def test_02_set_redirect_handles_missing_site(self):
        src = _func_src(SITE_UTILS, 'setRedirect', cls='sites')
        self.assertIn('if not domain_list:', src,
                      'domains 为空时必须如实报错，不能 domain_list[0] -> 500')

    def test_03_del_backup_guards_missing_row(self):
        src = _func_src(SITE_UTILS, 'delBackup', cls='sites')
        self.assertIn('if not info:', src)

    def test_04_backup_page_safe_defaults(self):
        fake = mock.MagicMock()
        with mock.patch.object(thisdb_backup.yf, 'M', return_value=fake):
            thisdb_backup.getBackupPage(11, '', '')
            self.assertEqual(fake.where.return_value.field.return_value.limit.call_args[0][0],
                             '0,10')
        fake2 = mock.MagicMock()
        with mock.patch.object(thisdb_backup.yf, 'M', return_value=fake2):
            thisdb_backup.getBackupPage(11, '1', '5000')
            self.assertEqual(fake2.where.return_value.field.return_value.limit.call_args[0][0],
                             '0,200', 'limit 必须有上限（防一次性拉全表）')

    def test_09_delete_removes_dir_binding_rewrite(self):
        """删站时必须清掉子目录绑定的伪静态文件（否则 rewrite 目录留孤儿配置）。"""
        src = _func_src(SITE_UTILS, 'delete', cls='sites')
        self.assertIn("self.getDirBindRewrite(webname, x['path'])", src)
        self.assertIn('yf.deleteFile(bind_rewrite)', src)

    def test_05_rewrite_save_cleans_backup_file(self):
        src = _func_src(SITE_UTILS, 'setRewrite', cls='sites')
        self.assertIn('yf.removeBackFile(path)', src,
                      '保存成功必须清理 _bak，否则每次保存堆积一个副本')

    def test_06_cert_remove_is_contained(self):
        src = _func_src(SITE_UTILS, 'removeCert', cls='sites')
        self.assertIn('safeSiteName(cert_name)', src)
        self.assertIn('isSafePathInside(self.sslDir, path)', src)

    def test_07_get_backup_normalizes_paging_before_get_page(self):
        """分页参数为空串时必须先归一化：它们既进 LIMIT 又进分页 HTML（int('') -> 500）。"""
        obj = sites.__new__(sites)
        with mock.patch.object(site_utils.yf, 'getPage', return_value='<div></div>') as get_page, \
                mock.patch.object(site_utils.thisdb, 'getSitesById', return_value={'id': 11}), \
                mock.patch.object(site_utils.thisdb, 'getBackupPage',
                                  return_value={'list': [], 'count': 0}) as page_fn:
            data = obj.getBackup('11', page='', size='')
            self.assertEqual(page_fn.call_args[0][1:], (1, 10))
            self.assertEqual(get_page.call_args[0][0]['p'], 1)
            self.assertEqual(get_page.call_args[0][0]['row'], 10)
        self.assertEqual(data['data'], [])

    def test_08_php_version_and_ssl_survive_missing_conf(self):
        base = tempfile.mkdtemp(prefix='yf_a02_conf_')
        try:
            obj = sites.__new__(sites)
            obj.vhostPath = os.path.join(base, 'vhost')
            obj.sslDir = os.path.join(base, 'ssl')
            os.makedirs(obj.vhostPath)
            # 站点配置不存在（或名字非法）：readFile 得到 False，不得抛异常
            self.assertEqual(obj.getSitePhpVersion('nope.test'), {'phpversion': '00'})
            self.assertEqual(obj.getSitePhpVersion('../../../../tmp/x'), {'phpversion': '00'})
            res = obj.getSsl('nope.test', 'acme')
            self.assertFalse(res['status'])
        finally:
            shutil.rmtree(base, ignore_errors=True)


class SiteJsXssTest(unittest.TestCase):
    """列表渲染必须转义（ps 备注实测可存 <img onerror>）。"""

    def test_01_escaping_helpers_exist_and_are_used(self):
        src = _read(SITE_JS)
        self.assertIn('function yfText(v)', src)
        self.assertIn('function yfJsStr(v)', src)
        loop = src[src.find('for (var i = 0; i < list.length; i++) {'):
                   src.find('// 使用事件委托统一绑定有效期点击事件')]
        self.assertIn('var jsName = yfJsStr(list[i].name);', loop)
        self.assertIn('var psText = yfText(list[i].ps || \'\');', loop)
        self.assertIn('yfText(list[i].name)', loop)
        # 行内 onclick 里的站点名必须走 JS 字符串转义
        self.assertNotIn(",'\" + list[i].name + \"'", loop)

    def test_02_node_render_escapes_payload(self):
        src = _read(SITE_JS)
        h_start = src.find('function yfText(v) {')
        h_end = src.find('/**\n * 取回网站数据列表', h_start)
        s_idx = src.find('for (var i = 0; i < list.length; i++) {')
        e_idx = src.find('// 使用事件委托统一绑定有效期点击事件', s_idx)
        helpers = src[h_start:h_end]
        loop = src[s_idx:e_idx]
        payload = "<img src=x onerror=alert(1)>"
        evil_name = "x' onmouseover='alert(2) \" onfocus='alert(3) & <b>bad</b>"
        node_script = (
            "var lan = {};\n"
            "function toSize(s){return (s||0)+' B';}\n"
            "function t(){return null;}\n"
            + helpers +
            # 最小 HTML 属性名解析器：能识别属性能否被引号/实体逃逸出来
            "function attrNames(html){\n"
            "  var names=[],i=0;\n"
            "  var isWs=function(c){return c===' '||c==='\\t'||c==='\\n'||c==='\\r'||c==='\\f';};\n"
            "  while((i=html.indexOf('<',i))!==-1){\n"
            "    var k=i+1; if(html[k]==='/')k++;\n"
            "    while(k<html.length && !isWs(html[k]) && html[k]!=='>' && html[k]!=='/')k++;\n"
            "    while(k<html.length && html[k]!=='>'){\n"
            "      while(k<html.length && isWs(html[k]))k++;\n"
            "      if(k>=html.length||html[k]==='>')break;\n"
            "      if(html[k]==='/'){k++;continue;}\n"
            "      var name='';\n"
            "      while(k<html.length && !isWs(html[k]) && html[k]!=='=' && html[k]!=='>' && html[k]!=='/'){name+=html[k];k++;}\n"
            "      if(name)names.push(name.toLowerCase());\n"
            "      while(k<html.length && isWs(html[k]))k++;\n"
            "      if(html[k]==='='){\n"
            "        k++;\n"
            "        while(k<html.length && isWs(html[k]))k++;\n"
            "        var q=html[k];\n"
            "        if(q===String.fromCharCode(34)||q===String.fromCharCode(39)){k++;while(k<html.length&&html[k]!==q)k++;k++;}\n"
            "        else{while(k<html.length&&!isWs(html[k])&&html[k]!=='>')k++;}\n"
            "      }\n"
            "    }\n"
            "    i=k+1;\n"
            "  }\n"
            "  return names;\n"
            "}\n"
            "const list=[{id:1,name:" + json.dumps(evil_name) + ",path:'/www/wwwroot/a',"
            "status:'1',backup_count:0,edate:'0000-00-00',php_version:'00',ssl_days:-1,"
            "daily_traffic:0,add_time:'2026-01-01 00:00:00',ps:" + json.dumps(payload) + "}];\n"
            "const data={data:list};const rows=[];\n"
            "const $=function(){return {append:function(h){rows.push(h);}};};\n"
            + loop + "\n"
            "if(rows.length!==1) throw new Error('row count '+rows.length);\n"
            "const html=rows[0];\n"
            "if(html.indexOf('<img')!==-1) throw new Error('raw <img leaked');\n"
            "if(html.indexOf('<b>bad')!==-1) throw new Error('raw <b> leaked');\n"
            "if(html.indexOf('&lt;img src=x onerror=alert(1)&gt;')===-1) throw new Error('ps 未按文本转义');\n"
            "const names=attrNames(html);\n"
            "const bad=names.filter(function(n){return n.indexOf('on')===0 && n!=='onclick';});\n"
            "if(bad.length) throw new Error('属性注入成功: '+bad.join(','));\n"
            "const allowed=names.filter(function(n){return n==='onclick';});\n"
            "if(allowed.length<5) throw new Error('onclick 数量异常: '+allowed.length);\n"
            "const td=(html.match(/<td[\\s>]/g)||[]).length;\n"
            "if(td!==12) throw new Error('td count '+td);\n"
            "console.log('A02_XSS_ESCAPED');\n"
        )
        scratch = tempfile.mkdtemp(prefix='yf_a02_node_')
        try:
            runner = os.path.join(scratch, 'run.js')
            with open(runner, 'w', encoding='utf-8') as fh:
                fh.write(node_script)
            res = subprocess.run(['node', runner], capture_output=True)
            out = (res.stdout or b'').decode('utf-8', errors='replace')
            err = (res.stderr or b'').decode('utf-8', errors='replace')
            self.assertEqual(res.returncode, 0,
                             'node 渲染断言失败：%s' % (err or out))
            self.assertIn('A02_XSS_ESCAPED', out)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class FileHygieneTest(unittest.TestCase):

    def test_01_utf8_no_bom_lf(self):
        for rel in ('web/utils/site.py', 'web/admin/site/site.py',
                    'web/thisdb/sites.py', 'web/thisdb/backup.py',
                    'web/static/app/site.js',
                    'testsuite/test_site_a02_hardening.py'):
            with open(os.path.join(ROOT, rel), 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), rel + ' 不得有 BOM')
            self.assertNotIn(b'\r\n', raw, rel + ' 必须 LF')


if __name__ == '__main__':
    unittest.main()
