# coding:utf-8
import sys
import os
import json
import shutil
import tempfile
import unittest
import importlib.util

workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace)
sys.path.insert(0, os.path.join(workspace, 'web'))
sys.path.insert(0, os.path.join(workspace, 'plugins', 'op_waf'))

def _load_op_waf():
    spec = importlib.util.spec_from_file_location('op_waf_rule_upgrade_index', os.path.join(workspace, 'plugins', 'op_waf', 'index.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class TestOpWafRuleUpgrade(unittest.TestCase):

    def test_version_and_metadata(self):
        """验证 op_waf 与 fail2ban 版本号提升与 install.sh 规范动作契约"""
        op_waf_info = os.path.join(workspace, 'plugins', 'op_waf', 'info.json')
        with open(op_waf_info, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('1.6', data.get('versions', []), "op_waf 版本未升级至 1.6")

        f2b_info = os.path.join(workspace, 'plugins', 'fail2ban', 'info.json')
        with open(f2b_info, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('1.3.0', data.get('versions', []), "fail2ban 版本未升级至 1.3.0")

        # install.sh 分发动作断言
        op_sh = os.path.join(workspace, 'plugins', 'op_waf', 'install.sh')
        with open(op_sh, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('install|update|upgrade)', content, "op_waf install.sh 缺少 update/upgrade 动作支持")

        f2b_sh = os.path.join(workspace, 'plugins', 'fail2ban', 'install.sh')
        with open(f2b_sh, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('install|update|upgrade)', content, "fail2ban install.sh 缺少 update/upgrade 动作支持")
        self.assertIn('VERSION="1.3.0"', content, "fail2ban install.sh 默认版本未更新至 1.3.0")

    def test_template_rules_content(self):
        """验证新漏洞蜜罐与防护规则模板已正确写入"""
        # 1. 验证 config.json 中的蜜罐端点
        cfg_path = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'config.json')
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        paths = cfg.get('honeypot', {}).get('paths', [])
        self.assertIn('/.~~spring-boot!~/', paths)
        self.assertIn('/.~~spring-boot!~/restart', paths)
        self.assertIn('/WEB-INF/web.xml', paths)
        self.assertIn('/actuator/env', paths)
        self.assertIn('/actuator/heapdump', paths)

        # 2. 验证 vuln.json 中的探针规则
        vuln_path = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'rule', 'vuln.json')
        with open(vuln_path, 'r', encoding='utf-8') as f:
            vuln_rules = json.load(f)
        patterns = [r[1] for r in vuln_rules]
        self.assertTrue(any('spring-boot.*restart' in p and 'php2shell' in p for p in patterns),
                        "vuln.json 中缺少 Spring Boot DevTools 与 php2shell 漏洞探针规则")

        # 3. 验证 url.json 中的端点与遍历防御规则
        url_path = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'rule', 'url.json')
        with open(url_path, 'r', encoding='utf-8') as f:
            url_rules = json.load(f)
        url_descs = [r[2] for r in url_rules]
        self.assertIn('Spring Boot与Java敏感端点探测防御', url_descs)
        self.assertIn('路径遍历与目录穿透防御', url_descs)

        # 4. 验证 op_waf.js 中的默认蜜罐路径完整性
        js_path = os.path.join(workspace, 'plugins', 'op_waf', 'js', 'op_waf.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()
        self.assertIn('/.~~spring-boot!~/restart', js_content)
        self.assertIn('/WEB-INF/web.xml', js_content)

    def test_honeypot_and_rules_safe_merge(self):
        """测试老用户升级时的安全增量合并机制：绝对不覆盖用户自建规则与自建蜜罐路径"""
        op_waf_index = _load_op_waf()

        test_dir = tempfile.mkdtemp(prefix='waf_test_upgrade_')
        waf_dir = os.path.join(test_dir, 'waf')
        rule_dir = os.path.join(waf_dir, 'rule')
        os.makedirs(rule_dir, exist_ok=True)

        original_server_dir = op_waf_index.getServerDir
        op_waf_index.getServerDir = lambda: test_dir

        try:
            # 1. 模拟老用户的 config.json
            user_honeypot_paths = ["/.env", "/my_custom_secret_honeypot", "/old_backup.tar.gz"]
            user_config = {
                "open": True,
                "honeypot": {
                    "open": False,  # 用户自己关掉了蜜罐
                    "status": 403,  # 用户自己改成了 403
                    "paths": list(user_honeypot_paths)
                }
            }
            conf_file = os.path.join(waf_dir, 'config.json')
            with open(conf_file, 'w', encoding='utf-8') as f:
                json.dump(user_config, f, ensure_ascii=False, indent=4)

            # 2. 模拟老用户的 vuln.json
            user_vuln_rules = [
                # 用户禁用了默认第 1 条规则
                [0, "(?i)(spring4shell|log4shell|fastjson|shiro|struts2|thinkphp|weblogic|jenkins|gitlab|zabbix)", "漏洞探测扫描防御", "scan"],
                # 用户自建规则
                [1, "(?i)my_super_hacker_probe_regex", "用户自建防护规则", "scan"]
            ]
            vuln_file = os.path.join(rule_dir, 'vuln.json')
            with open(vuln_file, 'w', encoding='utf-8') as f:
                json.dump(user_vuln_rules, f, ensure_ascii=False, indent=4)

            # 3. 执行 upgradeRules
            changed = op_waf_index.upgradeRules()
            self.assertTrue(changed, "老用户首次升级时应当产生增量合并")

            # 4. 验证 config.json 的合并结果
            with open(conf_file, 'r', encoding='utf-8') as f:
                upgraded_config = json.load(f)

            hp = upgraded_config['honeypot']
            # 用户个性化设置必须完整保留
            self.assertFalse(hp['open'], "用户的 open: false 设置被意外覆盖")
            self.assertEqual(hp['status'], 403, "用户的 status: 403 设置被意外覆盖")
            self.assertIn("/my_custom_secret_honeypot", hp['paths'], "用户自建的蜜罐路径被意外删除或覆盖")
            self.assertIn("/old_backup.tar.gz", hp['paths'], "用户自建的蜜罐路径被意外删除或覆盖")
            # 新官方诱饵路径成功追加
            self.assertIn("/.~~spring-boot!~/", hp['paths'], "新官方蜜罐诱饵路径未被合并")
            self.assertIn("/.~~spring-boot!~/restart", hp['paths'], "新官方蜜罐诱饵路径未被合并")
            self.assertIn("/WEB-INF/web.xml", hp['paths'], "新官方蜜罐诱饵路径未被合并")

            # 5. 验证 vuln.json 的合并结果
            with open(vuln_file, 'r', encoding='utf-8') as f:
                upgraded_rules = json.load(f)

            patterns = [r[1] for r in upgraded_rules]
            # 用户自建规则未被丢弃
            self.assertIn("(?i)my_super_hacker_probe_regex", patterns, "用户自建规则被丢失")
            # 用户禁用状态必须保持为 0
            rule_0 = next(r for r in upgraded_rules if 'spring4shell' in r[1])
            self.assertEqual(rule_0[0], 0, "用户禁用的官方旧规则被意外重置为启用状态")
            # 新规则增量追加
            self.assertTrue(any('spring-boot.*restart' in p for p in patterns), "新规则未成功追加进 vuln.json")

            # 6. 验证幂等性：再次调用返回 False 且内容无变化
            changed_second = op_waf_index.upgradeRules()
            self.assertFalse(changed_second, "升级合并必须幂等，二次调用不应产生变更")

        finally:
            op_waf_index.getServerDir = original_server_dir
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_upgrade_rules_cli_contract_and_error_handling(self):
        """P2-4: 验证 upgradeRulesCli 成功与失败口径契约，杜绝异常被吞返回假成功"""
        op_waf_index = _load_op_waf()

        test_dir = tempfile.mkdtemp(prefix='waf_test_cli_')
        waf_dir = os.path.join(test_dir, 'waf')
        rule_dir = os.path.join(waf_dir, 'rule')
        os.makedirs(rule_dir, exist_ok=True)

        original_server_dir = op_waf_index.getServerDir
        op_waf_index.getServerDir = lambda: test_dir

        try:
            # 1. 正常场景：基于真实模板构造含老用户自定义项的配置与规则文件，CLI 应正常重编并返回 status: True
            src_conf_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'config.json')
            with open(src_conf_file, 'r', encoding='utf-8') as f:
                base_cfg = json.load(f)
            base_cfg['honeypot']['paths'] = ["/my_old_honeypot"]
            conf_file = os.path.join(waf_dir, 'config.json')
            with open(conf_file, 'w', encoding='utf-8') as f:
                json.dump(base_cfg, f, ensure_ascii=False, indent=4)

            vuln_file = os.path.join(rule_dir, 'vuln.json')
            with open(vuln_file, 'w', encoding='utf-8') as f:
                json.dump([[1, "test_rule", "test", "scan"]], f)

            res_normal = op_waf_index.upgradeRulesCli()
            normal_data = json.loads(res_normal)
            self.assertTrue(normal_data.get('status'), f"正常升级 CLI 应返回 status: True, 实际返回: {res_normal}")

            # 2. 异常场景：规则文件损坏导致 JSON 解码失败，CLI 必须返回 status: False 并给出明确错误原因
            with open(vuln_file, 'w', encoding='utf-8') as f:
                f.write("{ invalid json syntax !!!")

            res_error = op_waf_index.upgradeRulesCli()
            error_data = json.loads(res_error)
            self.assertFalse(error_data.get('status'), f"发生合并错误时 CLI 绝不能返回假成功, 实际返回: {res_error}")
            self.assertIn('规则保存失败', error_data.get('msg', ''), "错误信息未明确提示规则保存失败")
            self.assertIn('vuln.json', error_data.get('msg', ''), "错误信息中应指明失败的文件名")

        finally:
            op_waf_index.getServerDir = original_server_dir
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()

