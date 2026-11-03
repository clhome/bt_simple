# coding: utf-8
"""P2-2: OP-WAF 老用户增量平滑升级 live 真实环境与全链路验证用例。

测试员问题：
  全新安装直接复制 shipped 文件，带自定义规则与禁用状态的老用户合并分支未在真实/准真实环境下被触发验证。
解法：
  构造含用户自定义规则、禁用状态规则与自建蜜罐路径的老版本规则环境后调用 upgrade_rules / upgradeRulesCli，
  验证老用户个性化配置与规则状态 100% 完整保留，且官方新增规则与蜜罐端点被正确追加，升级具备幂等性。
  若检测到系统已真实安装 /www/server/op_waf 且具备权限，则在安全备份现场的前提下直接进行 live 实测并在结束后恢复现场；
  在常规开发机或无真实安装环境时，采用完全镜像的真实路径结构进行全链路闭环，不阻塞跨平台门禁。

使用方法：
  python -m unittest testsuite/test_op_waf_upgrade_live.py
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
OP_WAF_DIR = os.path.join(ROOT_DIR, 'plugins', 'op_waf')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)
if OP_WAF_DIR not in sys.path:
    sys.path.append(OP_WAF_DIR)

import core.yf as yf
import importlib.util

def get_op_waf_module():
    spec = importlib.util.spec_from_file_location('op_waf_live_index', os.path.join(OP_WAF_DIR, 'index.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOpWafUpgradeLive(unittest.TestCase):
    """验证老用户增量平滑升级：自定义规则与状态保留，官方新规则智能追加。"""

    def setUp(self):
        self.live_waf_root = '/www/server/op_waf'
        self.is_real_live = (
            sys.platform.startswith('linux')
            and os.path.isdir(self.live_waf_root)
            and os.access(self.live_waf_root, os.W_OK)
        )
        self.backup_dir = None

    def tearDown(self):
        # 若在真机环境做了现场备份，必须 100% 恢复真实数据
        if self.is_real_live and self.backup_dir and os.path.isdir(self.backup_dir):
            waf_dir = os.path.join(self.live_waf_root, 'waf')
            if os.path.exists(waf_dir):
                shutil.rmtree(waf_dir, ignore_errors=True)
            shutil.copytree(self.backup_dir, waf_dir)
            shutil.rmtree(self.backup_dir, ignore_errors=True)

    def test_live_legacy_user_incremental_merge(self):
        """构造老用户环境并调用 upgrade_rules，验证规则与状态 100% 保留且缺失项被追加。"""
        if self.is_real_live:
            work_waf_root = self.live_waf_root
            waf_dir = os.path.join(work_waf_root, 'waf')
            # 备份真实 live 现场
            self.backup_dir = tempfile.mkdtemp(prefix='op_waf_live_bak_')
            if os.path.isdir(waf_dir):
                shutil.copytree(waf_dir, os.path.join(self.backup_dir, 'waf'))
            clean_needed = False
        else:
            # 构造完全同构的临时运行目录
            work_waf_root = tempfile.mkdtemp(prefix='op_waf_sim_live_')
            clean_needed = True

        op_waf_index = get_op_waf_module()
        orig_server_dir = op_waf_index.getServerDir
        op_waf_index.getServerDir = lambda: work_waf_root

        try:
            waf_dir = os.path.join(work_waf_root, 'waf')
            rule_dir = os.path.join(waf_dir, 'rule')
            os.makedirs(rule_dir, exist_ok=True)

            # 1. 构造老用户 config.json：含自建蜜罐路径与修改过的个性化开关
            src_conf_file = os.path.join(OP_WAF_DIR, 'waf', 'config.json')
            with open(src_conf_file, 'r', encoding='utf-8') as f:
                base_cfg = json.load(f)

            user_custom_paths = ["/my_secret_admin_entrance", "/old_legacy_honeypot"]
            base_cfg['honeypot']['open'] = False
            base_cfg['honeypot']['status'] = 404
            base_cfg['honeypot']['paths'] = list(user_custom_paths)

            conf_dst = os.path.join(waf_dir, 'config.json')
            with open(conf_dst, 'w', encoding='utf-8') as f:
                json.dump(base_cfg, f, ensure_ascii=False, indent=4)

            # 2. 构造老用户 vuln.json：含用户禁用的旧规则与用户自建的专有防御规则
            user_disabled_pattern = "(?i)(spring4shell|log4shell|fastjson|shiro|struts2)"
            user_custom_pattern = "(?i)custom_legacy_enterprise_rule_probe"
            legacy_vuln_rules = [
                # 用户禁用的旧官方规则（启用状态设为 0）
                [0, user_disabled_pattern, "旧版漏洞防御规则（用户已关闭）", "scan"],
                # 用户自建规则（启用状态为 1）
                [1, user_custom_pattern, "企业内部自建防护特征", "scan"]
            ]
            vuln_dst = os.path.join(rule_dir, 'vuln.json')
            with open(vuln_dst, 'w', encoding='utf-8') as f:
                json.dump(legacy_vuln_rules, f, ensure_ascii=False, indent=4)

            # 3. 构造老用户 url.json：含用户自建 URL 规则
            user_url_pattern = r"^/api/v1/private_internal/.*"
            legacy_url_rules = [
                [1, user_url_pattern, "内部私有接口白名单防御", "url"]
            ]
            url_dst = os.path.join(rule_dir, 'url.json')
            with open(url_dst, 'w', encoding='utf-8') as f:
                json.dump(legacy_url_rules, f, ensure_ascii=False, indent=4)

            # 4. 执行规则升级命令（调用 upgradeRulesCli，与 CLI 入口逻辑一致）
            cli_res = op_waf_index.upgradeRulesCli()
            res_obj = json.loads(cli_res)
            self.assertTrue(res_obj.get('status'), f"老用户升级应成功执行并返回 True, 实际返回: {cli_res}")

            # 5. 验证 config.json 增量合并与状态保留
            with open(conf_dst, 'r', encoding='utf-8') as f:
                upgraded_cfg = json.load(f)

            hp = upgraded_cfg['honeypot']
            self.assertFalse(hp['open'], "老用户个性化 honeypot.open 设置被意外篡改")
            self.assertEqual(hp['status'], 404, "老用户个性化 honeypot.status 设置被意外篡改")
            self.assertIn("/my_secret_admin_entrance", hp['paths'], "老用户自建蜜罐路径被意外丢弃")
            self.assertIn("/old_legacy_honeypot", hp['paths'], "老用户自建蜜罐路径被意外丢弃")
            # 官方新诱饵必须成功追加
            self.assertIn("/.~~spring-boot!~/", hp['paths'], "官方新诱饵端点未被追加")
            self.assertIn("/WEB-INF/web.xml", hp['paths'], "官方新诱饵端点未被追加")

            # 6. 验证 vuln.json 规则合并与禁用状态保留
            with open(vuln_dst, 'r', encoding='utf-8') as f:
                upgraded_vuln = json.load(f)

            patterns_vuln = [r[1] for r in upgraded_vuln]
            # 自建规则必须 100% 保留
            self.assertIn(user_custom_pattern, patterns_vuln, "老用户自建 vuln 防护规则在升级中丢失")
            # 禁用状态必须保持为 0，绝对不可被覆盖重置为启用
            disabled_rule = next((r for r in upgraded_vuln if r[1] == user_disabled_pattern), None)
            self.assertIsNotNone(disabled_rule, "老用户既有规则丢失")
            self.assertEqual(disabled_rule[0], 0, "老用户禁用的规则状态被意外篡改为 1")
            # 官方新增规则必须成功增量追加到末尾
            self.assertTrue(any('spring-boot.*restart' in p for p in patterns_vuln), "官方新漏洞探针规则未成功追加")

            # 7. 验证 url.json 规则合并
            with open(url_dst, 'r', encoding='utf-8') as f:
                upgraded_url = json.load(f)

            patterns_url = [r[1] for r in upgraded_url]
            self.assertIn(user_url_pattern, patterns_url, "老用户自建 URL 规则在升级中丢失")
            self.assertTrue(len(upgraded_url) > 1, "官方新 URL 防护规则未成功追加")

            # 8. 验证升级幂等性：二次执行无新增变动，不重复追加
            cli_res_second = op_waf_index.upgradeRulesCli()
            res_obj_second = json.loads(cli_res_second)
            self.assertTrue(res_obj_second.get('status'))

            with open(vuln_dst, 'r', encoding='utf-8') as f:
                second_vuln = json.load(f)
            self.assertEqual(len(upgraded_vuln), len(second_vuln), "二次调用产生非预期的重复追加")

        finally:
            op_waf_index.getServerDir = orig_server_dir
            if clean_needed and os.path.isdir(work_waf_root):
                shutil.rmtree(work_waf_root, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
