# coding: utf-8
import os
import re
import subprocess
import unittest

class TestAllPluginsJsSyntax(unittest.TestCase):
    def setUp(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.plugins_dir = os.path.join(self.root_dir, "plugins")
        self.web_static_dir = os.path.join(self.root_dir, "web", "static")

    def test_plugins_js_syntax(self):
        """测试 plugins 目录下所有 JS 文件的语法合法性"""
        js_files = []
        for root, dirs, files in os.walk(self.plugins_dir):
            if "待审核" in root or "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith(".js"):
                    js_files.append(os.path.join(root, f))

        syntax_errors = []
        for js_file in js_files:
            rel_path = os.path.relpath(js_file, self.root_dir)
            res = subprocess.run(["node", "-c", js_file], capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                syntax_errors.append((rel_path, res.stderr.strip()))

        error_msg = "\n".join([f"[{path}] -> {err}" for path, err in syntax_errors])
        self.assertEqual(len(syntax_errors), 0, f"发现 {len(syntax_errors)} 个插件 JS 语法错误:\n{error_msg}")

    def test_app_core_js_syntax(self):
        """测试 web/static/app 目录下所有核心业务 JS 文件的语法合法性"""
        app_dir = os.path.join(self.web_static_dir, "app")
        js_files = []
        for root, dirs, files in os.walk(app_dir):
            for f in files:
                if f.endswith(".js"):
                    js_files.append(os.path.join(root, f))

        syntax_errors = []
        for js_file in js_files:
            rel_path = os.path.relpath(js_file, self.root_dir)
            res = subprocess.run(["node", "-c", js_file], capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                syntax_errors.append((rel_path, res.stderr.strip()))

        error_msg = "\n".join([f"[{path}] -> {err}" for path, err in syntax_errors])
        self.assertEqual(len(syntax_errors), 0, f"发现 {len(syntax_errors)} 个前端核心 JS 语法错误:\n{error_msg}")

    def test_invalid_function_dot_syntax_in_all_plugins(self):
        """检查所有插件 JS 中是否存在类似于 function xxx.yyy 的非法函数定义语法"""
        pattern = re.compile(r'function\s+([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\s*\(')
        matches = []
        for root, dirs, files in os.walk(self.plugins_dir):
            if "待审核" in root or "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith((".js", ".html")):
                    file_path = os.path.join(root, f)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                        for line_idx, line in enumerate(fp, 1):
                            m = pattern.search(line)
                            if m:
                                rel_path = os.path.relpath(file_path, self.root_dir)
                                matches.append((rel_path, line_idx, line.strip()))

        error_msg = "\n".join([f"[{path}:{line_no}] {content}" for path, line_no, content in matches])
        self.assertEqual(len(matches), 0, f"发现非法点号函数声明语法:\n{error_msg}")

    def test_plugin_api_polymorphic_signatures(self):
        """测试 plugin_api.js 对 2参数、3参数、4参数调用的多态兼容性"""
        node_script = """
        const fs = require('fs');
        const vm = require('vm');

        const sandbox = {
            window: {},
            document: {},
            layer: {
                msg: function() { return 1; },
                close: function() {}
            },
            YfI18n: {
                createPluginTranslator: function() { return function(k) { return k; }; }
            },
            $: {
                post: function(url, data, cb) {
                    sandbox._lastPost = { url, data };
                    cb({ status: true, msg: 'ok', data: 'success' });
                    return { fail: function() {} };
                }
            }
        };
        sandbox.window = sandbox;

        const code = fs.readFileSync('web/static/app/plugin_api.js', 'utf-8');
        vm.runInNewContext(code, sandbox);

        const api = sandbox.YfPlugin.createApi('docker');

        // 测试 1: 4 参数 (method, version, args, callback)
        let cb4 = false;
        api.post('docker_con_log', '1.0', { Hostname: 'test' }, function(res) {
            cb4 = true;
        });
        if (!cb4 || sandbox._lastPost.data.version !== '1.0' || JSON.parse(sandbox._lastPost.data.args).Hostname !== 'test') {
            console.error('cb4 failed', sandbox._lastPost);
            process.exit(1);
        }

        // 测试 2: 3 参数 (method, args, callback)
        let cb3 = false;
        api.post('con_list', { limit: 10 }, function(res) {
            cb3 = true;
        });
        if (!cb3 || sandbox._lastPost.data.version !== undefined || JSON.parse(sandbox._lastPost.data.args).limit !== 10) {
            console.error('cb3 failed', sandbox._lastPost);
            process.exit(2);
        }

        // 测试 3: 2 参数 (method, callback)
        let cb2 = false;
        api.post('get_status', function(res) {
            cb2 = true;
        });
        if (!cb2 || sandbox._lastPost.data.func !== 'get_status') {
            console.error('cb2 failed', sandbox._lastPost);
            process.exit(3);
        }

        console.log('ALL_POLYMORPHIC_TESTS_PASSED');
        """
        res = subprocess.run(["node", "-e", node_script], cwd=self.root_dir, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"plugin_api.js 多态签名测试失败: {res.stderr}\n{res.stdout}")
        self.assertIn("ALL_POLYMORPHIC_TESTS_PASSED", res.stdout)

    def test_fixed_plugins_functions_defined(self):
        """测试已修复插件中的关键函数正常声明与注册"""
        node_script = """
        const fs = require('fs');
        const vm = require('vm');

        function createMockEnv() {
            const sandbox = {
                window: {},
                document: {},
                $: {
                    post: function() { return { fail: function() {} }; },
                    getScript: function() {}
                },
                layer: {
                    msg: function() { return 1; },
                    close: function() {},
                    open: function() {}
                },
                YfI18n: {
                    createPluginTranslator: function() { return function(k) { return k; }; }
                },
                setInterval: function() {},
                clearInterval: function() {},
                setTimeout: function() {},
                clearTimeout: function() {}
            };
            sandbox.window = sandbox;
            // 载入 plugin_api.js
            const apiCode = fs.readFileSync('web/static/app/plugin_api.js', 'utf-8');
            vm.runInNewContext(apiCode, sandbox);
            return sandbox;
        }

        // 1. Docker
        const dockerEnv = createMockEnv();
        const dockerCode = fs.readFileSync('plugins/docker/js/docker.js', 'utf-8');
        vm.runInNewContext(dockerCode, dockerEnv);
        if (typeof dockerEnv.dockerService !== 'function') throw new Error('dockerService not defined');
        if (typeof dockerEnv.dockerConList !== 'function') throw new Error('dockerConList not defined');

        // 2. Gitea
        const giteaEnv = createMockEnv();
        const giteaCode = fs.readFileSync('plugins/gitea/js/gitea.js', 'utf-8');
        vm.runInNewContext(giteaCode, giteaEnv);
        if (typeof giteaEnv.giteaService !== 'function') throw new Error('giteaService not defined');
        if (typeof giteaEnv.userProjectListPost !== 'function') throw new Error('userProjectListPost not defined');

        // 3. PgAdmin
        const pgadminEnv = createMockEnv();
        const pgadminCode = fs.readFileSync('plugins/pgadmin/js/pgadmin.js', 'utf-8');
        vm.runInNewContext(pgadminCode, pgadminEnv);
        if (typeof pgadminEnv.homePage !== 'function') throw new Error('homePage not defined');
        if (typeof pgadminEnv.safeConf !== 'function') throw new Error('safeConf not defined');

        // 4. PureFTP
        const pureftpEnv = createMockEnv();
        const pureftpCode = fs.readFileSync('plugins/pureftp/js/ftp.js', 'utf-8');
        vm.runInNewContext(pureftpCode, pureftpEnv);
        if (typeof pureftpEnv.ftpList !== 'function') throw new Error('ftpList not defined');

        // 5. Sphinx
        const sphinxEnv = createMockEnv();
        const sphinxCode = fs.readFileSync('plugins/sphinx/js/sphinx.js', 'utf-8');
        vm.runInNewContext(sphinxCode, sphinxEnv);
        if (typeof sphinxEnv.commonFunc !== 'function') throw new Error('commonFunc not defined');

        console.log('ALL_FIXED_PLUGINS_VERIFIED');
        """
        res = subprocess.run(["node", "-e", node_script], cwd=self.root_dir, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"插件函数声明验证失败: {res.stderr}\n{res.stdout}")
        self.assertIn("ALL_FIXED_PLUGINS_VERIFIED", res.stdout)

if __name__ == "__main__":
    unittest.main()
