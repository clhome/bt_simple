# coding: utf-8
"""
P1-3 收口回归：C7 静态资源去重 + N1 `/metrics` 探针

C7  `web/static/bootstrap-3.3.5` 是 bootstrap 3.4.1 迁移后的**遗留目录**
    （见 `文档/jq升级3.7/jq升级3.7.md`：“CSS 需要同步升级为 3.4.1（目录重命名为
    bootstrap-3.4.1）”）。此处锁死三件事：
      * 目录必须已删除，且源码里不得留任何引用（含字符串里的动态拼接）；
      * 静态目录只允许保留一个 bootstrap 版本，避免继续“两版并存”；
      * 不允许用 `'bootstrap-' + ver` 这类拼接绕过静态引用扫描。

N1  `/metrics`（Prometheus 文本端点，**默认关闭**）：
      * 默认关闭（`metrics_open` 默认 'no'），未开启返回 **404** 而不是 403；
      * 必须加入「关站 / 安全入口」重定向豁免，否则开了也抓不到；
      * 只出健康类指标，不回显版本号 / 数据库路径等指纹；
      * 探针必须只读，不得出现写库 / 写审计调用。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_INIT = os.path.join(ROOT, 'web', 'admin', '__init__.py')
STATIC_DIR = os.path.join(ROOT, 'web', 'static')

SCAN_DIRS = ('web', 'plugins')
SCAN_EXT = ('.py', '.html', '.js', '.json', '.css', '.scss', '.htm', '.tpl')
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai', '.pi'}


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read().replace('\r\n', '\n')


def _iter_source():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                if fn.endswith(SCAN_EXT):
                    yield os.path.join(root, fn)


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')


class StaticAssetDedupTest(unittest.TestCase):
    """C7：bootstrap 3.3.5 遗留目录清理。"""

    def test_01_legacy_dir_removed(self):
        legacy = os.path.join(STATIC_DIR, 'bootstrap-3.3.5')
        self.assertFalse(os.path.exists(legacy),
                         'web/static/bootstrap-3.3.5 应已删除（3.4.1 迁移后的遗留目录）')

    def test_02_no_reference_anywhere(self):
        """源码里不得再有任何引用（html/js/py/json/css 全覆盖）。"""
        hits = []
        for path in _iter_source():
            if 'bootstrap-3.3' in _read(path):
                hits.append(_rel(path))
        self.assertEqual(hits, [], '仍有文件引用 bootstrap-3.3.5：%r' % hits)

    def test_03_no_dynamic_bootstrap_path(self):
        """禁止用拼接方式绕过静态引用扫描（如 `'bootstrap-' + ver`）。"""
        pat = re.compile(r"""bootstrap-\s*["']?\s*(\+|%s|\{\}|\.format)""")
        bad = []
        for path in _iter_source():
            for i, line in enumerate(_read(path).split('\n'), 1):
                if pat.search(line):
                    bad.append('%s:%d %s' % (_rel(path), i, line.strip()))
        self.assertEqual(bad, [], '发现动态拼接的 bootstrap 路径：%r' % bad)

    def test_04_only_one_bootstrap_version(self):
        dirs = sorted(d for d in os.listdir(STATIC_DIR) if d.startswith('bootstrap-'))
        self.assertEqual(dirs, ['bootstrap-3.4.1'],
                         '静态目录只应保留一个 bootstrap 版本：%r' % dirs)


class MetricsEndpointTest(unittest.TestCase):
    """N1：/metrics 探针（默认关闭 + 只出健康类指标 + 只读）。"""

    def setUp(self):
        self.text = _read(ADMIN_INIT)
        start = self.text.index("@app.route('/metrics')")
        self.body = self.text[start:self.text.index('@app.errorhandler(404)')]

    def test_05_route_declared(self):
        self.assertIn("@app.route('/metrics')", self.text)
        self.assertIn('def metrics():', self.text)

    def test_06_default_closed_returns_404(self):
        self.assertIn("getOption('metrics_open', default='no')", self.body,
                      '默认必须关闭（metrics_open 默认 no）')
        self.assertIn('abort(404)', self.body,
                      '未开启应返回 404（不暴露端点存在），而不是 403')
        self.assertNotIn('abort(403)', self.body)

    def test_07_exempt_from_close_redirect(self):
        self.assertIn("request.path == '/metrics'", self.text,
                      '/metrics 必须加入关站/安全入口豁免，否则开启后也抓不到')
        # 回归保护：healthz 的既有豁免不能被顺手改掉
        self.assertIn("request.path == '/healthz'", self.text)

    def test_08_prometheus_text_format(self):
        self.assertIn('text/plain; version=0.0.4', self.body,
                      '必须显式声明 Prometheus exposition format 0.0.4')
        for metric in ('yf_up', 'yf_db_ok', 'yf_data_writable'):
            self.assertIn("'# TYPE %s gauge'" % metric, self.body,
                          '缺少指标类型声明：%s' % metric)
        self.assertNotIn('application/json', self.body)

    def test_09_no_fingerprint_leak(self):
        for leak in ('APP_VERSION', "'db_path'", 'getTracebackInfo', 'sys.path'):
            self.assertNotIn(leak, self.body,
                             '/metrics 不得回显指纹信息（%s）' % leak)
        self.assertIn("resp.headers['Cache-Control'] = 'no-store'", self.body)

    def test_10_probe_is_read_only(self):
        """探针必须是只读的：不得出现写库 / 写审计调用。"""
        for bad in ('writeLog', 'writeAudit', 'write_audit', 'INSERT', 'UPDATE '):
            self.assertNotIn(bad, self.body,
                             '/metrics 必须只读，不得出现 %s' % bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
