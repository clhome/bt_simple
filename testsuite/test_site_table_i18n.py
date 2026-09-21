# coding:utf-8
import os
import re
import json
import subprocess
import unittest

class TestSiteTableI18n(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.site_js_path = os.path.join(cls.root_dir, 'web', 'static', 'app', 'site.js')
        cls.template_zh_path = os.path.join(cls.root_dir, 'web', 'static', 'language', 'zh-CN', 'template.json')
        cls.template_en_path = os.path.join(cls.root_dir, 'web', 'static', 'language', 'en', 'template.json')
        cls.repaired_funcs_path = os.path.join(cls.root_dir, 'test', 'repaired_functions.js')

        with open(cls.site_js_path, 'r', encoding='utf-8') as f:
            cls.site_js_content = f.read()

        with open(cls.template_zh_path, 'r', encoding='utf-8') as f:
            cls.zh_data = json.load(f)

        with open(cls.template_en_path, 'r', encoding='utf-8') as f:
            cls.en_data = json.load(f)

    def test_01_site_js_syntax(self):
        """测试 site.js 整体语法绝对合法"""
        res = subprocess.run(['node', '--check', self.site_js_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"site.js syntax check failed: {res.stderr}")

    def test_02_no_corrupted_patterns(self):
        """测试 site.js 中不包含任何 AST 机械切分导致的破损特征"""
        corrupted_signatures = [
            "|| ')\\'",
            "|| ')\">",
            "onclick='setSitePath(\" + id + (((",
            "onclick='setSiteRunPath(\" + id + (((",
            "onclick='SetSitePs(\" + id + (((",
            "onclick=\"domainAdd(\" + id + \",\'\" + name + (((",
            "onclick=\"webBackup(\'\" + frdata[\'site\'][\'id\']",
            "onclick=\"to301(\\\'' + siteName + '\\\', 3, \\'' + item.id + (((",
            "onclick=\"setCertSsl(\\\'' + rdata[i].subject"
        ]
        for sig in corrupted_signatures:
            self.assertNotIn(sig, self.site_js_content, f"Found corrupted signature in site.js: {sig}")

    def test_03_table_header_and_row_columns_align_12(self):
        """测试网站列表必须对齐 12 列：表头 12 列，空数据 colspan='12'，数据行 12 个 <td>"""
        # 1. 验证空数据为 colspan="12"
        self.assertIn('colspan="12"', self.site_js_content, "Empty data row must have colspan='12'")

        # 2. 验证循环体内生成的 tr 中 td 的数量必须严格为 12 个
        s_idx = self.site_js_content.find('for (var i = 0; i < list.length; i++) {')
        e_idx = self.site_js_content.find('// 使用事件委托统一绑定有效期点击事件', s_idx)
        self.assertNotEqual(s_idx, -1, "Could not find getWeb loop start in site.js")
        self.assertNotEqual(e_idx, -1, "Could not find getWeb loop end in site.js")
        loop_code = self.site_js_content[s_idx:e_idx]

        # 验证循环体内有且仅有 12 个 <td> / <td ...>
        td_count = len(re.findall(r'<td[\s>]', loop_code))
        self.assertEqual(td_count, 12, f"Expected exactly 12 <td> tags in getWeb row, but found {td_count}")

    def test_04_simulate_getweb_render_in_node(self):
        """在真实 Node.js 环境中模拟渲染 getWeb 表格行，严格断言 12 列与 HTML 结构闭合"""
        s_idx = self.site_js_content.find('for (var i = 0; i < list.length; i++) {')
        e_idx = self.site_js_content.find('// 使用事件委托统一绑定有效期点击事件', s_idx)
        loop_code = self.site_js_content[s_idx:e_idx]

        zh_path_js = self.template_zh_path.replace('\\', '/')
        en_path_js = self.template_en_path.replace('\\', '/')

        node_script = f'''
        const fs = require('fs');

        function t(key) {{
            const parts = key.split('.');
            let cur = lan;
            for (const p of parts) {{
                if (cur && cur[p]) cur = cur[p];
                else return null;
            }}
            return cur || null;
        }}

        function toSize(size) {{ return (size || 0) + ' B'; }}

        // 测试数据集
        const testSites = [
            {{
                id: 1,
                name: 'www.test1.com',
                path: '/www/wwwroot/www.test1.com',
                status: '1',
                backup_count: 2,
                edate: '0000-00-00',
                php_version: '74',
                ssl_days: 30,
                daily_traffic: 1024,
                add_time: '2026-09-04 12:00:00',
                ps: '备注1'
            }},
            {{
                id: 2,
                name: 'www.stopped-site.com',
                path: '/www/wwwroot/www.stopped-site.com',
                status: '0',
                backup_count: 0,
                edate: '2027-01-01',
                php_version: '00',
                ssl_days: -1,
                daily_traffic: 0,
                add_time: '2026-08-01 10:00:00',
                ps: '已停止无备份'
            }},
            {{
                id: 3,
                name: 'www.expiring-ssl.com',
                path: '/www/wwwroot/www.expiring-ssl.com',
                status: '正在运行',
                backup_count: 1,
                edate: '2026-12-31',
                php_version: '80',
                ssl_days: 5,
                daily_traffic: 50000,
                add_time: '2026-07-01 09:00:00',
                ps: '即将到期'
            }}
        ];

        const languages = [
            {{ name: 'zh-CN', dict: JSON.parse(fs.readFileSync('{zh_path_js}', 'utf8')) }},
            {{ name: 'en', dict: JSON.parse(fs.readFileSync('{en_path_js}', 'utf8')) }},
            {{ name: 'fallback', dict: {{}} }}
        ];

        for (const lang of languages) {{
            global.lan = lang.dict;
            const rows = [];
            const data = {{ data: testSites }};
            const list = testSites;
            const $ = function(selector) {{
                return {{
                    append: function(html) {{ rows.push(html); }}
                }};
            }};

            // 执行循环体
            {loop_code}

            if (rows.length !== 3) {{
                throw new Error(lang.name + ': Expected 3 rows, got ' + rows.length);
            }}

            for (let rIdx = 0; rIdx < rows.length; rIdx++) {{
                const rowHtml = rows[rIdx];
                if (!rowHtml.startsWith('<tr') || !rowHtml.endsWith('</tr>')) {{
                    throw new Error(lang.name + ' row ' + rIdx + ' does not have valid <tr></tr>: ' + rowHtml);
                }}

                const tdMatches = rowHtml.match(/<td[\\s>]/g) || [];
                const closeTdMatches = rowHtml.match(/<\\/td>/g) || [];
                if (tdMatches.length !== 12 || closeTdMatches.length !== 12) {{
                    throw new Error(lang.name + ' row ' + rIdx + ' expected 12 <td> and 12 </td>, got ' + tdMatches.length + ' and ' + closeTdMatches.length);
                }}

                const onclickMatches = rowHtml.match(/onclick="([^"]*)"/g) || [];
                for (const oc of onclickMatches) {{
                    if (oc.includes("无备份") || oc.includes("有备份") || oc.includes("运行中") || oc.includes("已停止")) {{
                        if (!oc.includes("webStop") && !oc.includes("webStart") && !oc.includes("getBackup") && !oc.includes("webEdit") && !oc.includes("webDelete") && !oc.includes("changePHPVersion")) {{
                            throw new Error("Corrupted onclick attribute: " + oc);
                        }}
                    }}
                }}
            }}
        }}

        console.log("SIMULATION_PASSED");
        '''

        tmp_runner_path = os.path.join(self.root_dir, 'test', 'tmp_sim_runner.js')
        with open(tmp_runner_path, 'w', encoding='utf-8') as f:
            f.write(node_script)

        try:
            res = subprocess.run(['node', tmp_runner_path], capture_output=True, text=True, cwd=self.root_dir)
            self.assertEqual(res.returncode, 0, f"Node.js simulation failed: {res.stderr}")
            self.assertIn("SIMULATION_PASSED", res.stdout)
        finally:
            if os.path.exists(tmp_runner_path):
                os.remove(tmp_runner_path)

    def test_05_repaired_functions_validity(self):
        """测试 14 个核心修复函数在 Node.js 中均无语法错误"""
        repaired_path_js = self.repaired_funcs_path.replace('\\', '/')
        test_js = f'''
        const functions = require('{repaired_path_js}');
        for (const [name, code] of Object.entries(functions)) {{
            new Function(code);
        }}
        console.log("FUNCTIONS_VALID");
        '''
        res = subprocess.run(['node', '-e', test_js], capture_output=True, text=True, cwd=self.root_dir)
        self.assertEqual(res.returncode, 0, f"Repaired functions validation failed: {res.stderr}")
        self.assertIn("FUNCTIONS_VALID", res.stdout)

    def test_06_site_path_not_truncated_at_30_chars(self):
        """测试网站目录不再被硬编码截断在 30 字符，且支持 CSS 智能自适应防溢出"""
        self.assertNotIn('list[i].path.length > 30', self.site_js_content, "Path must not be arbitrarily truncated at 30 chars")
        self.assertIn("style='display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: middle;'", self.site_js_content)

if __name__ == '__main__':
    unittest.main()
