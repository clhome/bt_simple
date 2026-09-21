#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Redis 多语言适配与配置修改模板国际化自动化回归测试套件
验证 6 国语言包（zh-CN, zh-TW, en, fr, de, it）的完整性、翻译质量与防截断特性
"""

import os
import sys
import json
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestRedisI18nCompletion(unittest.TestCase):

    LANGS = ['zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it']

    REPL_KEYS = [
        '角色', '连接主库HOST', '连接主库PORT', '连接主库状态', '上次同步时间',
        '正在同步中', '从库读取复制位置', '从库复制位置', '从库是否仅读', '已复制副本',
        '连接数量', '主库故障状态', '主库复制ID', '主库复制位置', 'backlog复制大小',
        '复制位置时间', '第一个字节偏移量', 'backlog中数据的长度', '开启复制缓冲区',
        '同步优先级', '从库配置信息'
    ]

    CLUSTER_KEYS = [
        '集群状态', '被分配的槽', '被分配的槽状态', '知道的节点', '大小',
        '发送', '接收', '集群当前epoch', '当前我的epoch',
        '处于PFAIL状态的槽数', '处于FAIL状态的槽数', '超出缓冲区总数'
    ]

    MENU_KEYS = [
        '服务', '配置修改', '性能调整', '负载状态', '主从状态',
        '集群状态', '集群节点', '运行日志', '相关说明'
    ]

    COMMON_KEYS = [
        '字段', '当前值', '说明', '节点信息', '无数据/未设置集群'
    ]

    PUBLIC_CONFIG_KEYS = [
        'tip_use_ctrl_to_2', 'this_is_2', 'main_configuration_file_if_1', 'retrieving_configuration_template'
    ]

    def test_01_redis_language_files_valid_and_complete(self):
        """测试 Redis 插件 6 大语言包 JSON 格式合法且关键词条 100% 覆盖"""
        all_required = self.REPL_KEYS + self.CLUSTER_KEYS + self.MENU_KEYS + self.COMMON_KEYS

        for lang in self.LANGS:
            path = os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'lang', f'{lang}.json')
            self.assertTrue(os.path.exists(path), f"Language file not found: {path}")

            with open(path, 'r', encoding='utf-8') as fp:
                data = json.load(fp)

            missing = [k for k in all_required if k not in data or not str(data[k]).strip()]
            self.assertEqual(len(missing), 0, f"[{lang}] Missing translation keys: {missing}")

    def test_02_redis_menu_no_truncation_in_english(self):
        """测试 Redis 英文语言包中左侧导航菜单精炼且字符长度在 140px 安全区间内"""
        path = os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'lang', 'en.json')
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        # 重点检查之前被截断的几项
        self.assertEqual(data.get('主从状态'), 'Replication', "主从状态应翻译为标准 Replication，防止截断为 master-")
        self.assertEqual(data.get('配置修改'), 'Configuration', "配置修改应精炼为 Configuration，防止截断为 Configurat...")
        self.assertEqual(data.get('性能调整'), 'Performance', "性能调整应精炼为 Performance，防止截断为 Performan...")
        self.assertEqual(data.get('服务'), 'Service')
        self.assertEqual(data.get('负载状态'), 'Load Status')
        self.assertEqual(data.get('集群节点'), 'Cluster Nodes')

        # 所有菜单项长度不应超过 15 个字符
        for k in self.MENU_KEYS:
            trans = data.get(k, '')
            self.assertLessEqual(len(trans), 15, f"Menu item '{trans}' for '{k}' is too long, risks truncation!")

    def test_03_redis_repl_terms_quality(self):
        """测试 Redis 主从状态英文词条遵循官方标准术语（拒绝 library 机器翻译）"""
        path = os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'lang', 'en.json')
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        # 杜绝将 database 翻译成 library 的机械翻译
        self.assertNotIn('library', data.get('连接主库HOST', '').lower())
        self.assertNotIn('library', data.get('从库复制位置', '').lower())
        self.assertNotIn('library', data.get('主库复制位置', '').lower())

        self.assertEqual(data.get('角色'), 'Role')
        self.assertEqual(data.get('连接数量'), 'Connected Slaves')
        self.assertEqual(data.get('主库故障状态'), 'Master Failover State')
        self.assertEqual(data.get('主库复制ID'), 'Master Replication ID')
        self.assertEqual(data.get('主库复制位置'), 'Master Replication Offset')

    def test_04_public_language_files_contain_config_keys(self):
        """测试 6 大公共语言包 (web/static/language/*/public.json) 均包含配置模板多语言词条"""
        for lang in self.LANGS:
            path = os.path.join(PROJECT_ROOT, 'web', 'static', 'language', lang, 'public.json')
            self.assertTrue(os.path.exists(path), f"public.json not found: {path}")

            with open(path, 'r', encoding='utf-8') as fp:
                data = json.load(fp)

            for k in self.PUBLIC_CONFIG_KEYS:
                self.assertIn(k, data, f"[{lang}] Missing key in public.json: {k}")
                self.assertTrue(str(data[k]).strip(), f"[{lang}] Empty value for key: {k}")

    def test_05_public_config_tpl_rendered_content(self):
        """测试配置修改模板在各语言下的组装文本准确无误"""
        for lang in self.LANGS:
            path = os.path.join(PROJECT_ROOT, 'web', 'static', 'language', lang, 'public.json')
            with open(path, 'r', encoding='utf-8') as fp:
                data = json.load(fp)

            this_is = data['this_is_2']
            main_cfg = data['main_configuration_file_if_1']
            tip = data['tip_use_ctrl_to_2']

            rendered_hint = f"{this_is}redis 8.6.3{main_cfg}"
            self.assertIn("8.6.3", rendered_hint)
            if lang == 'en':
                self.assertIn("This is [", rendered_hint)
                self.assertIn("main configuration file", rendered_hint)
                self.assertIn("Tip: Ctrl+F", tip)
            elif lang == 'zh-CN':
                self.assertIn("此处为【", rendered_hint)
                self.assertIn("主配置文件", rendered_hint)
                self.assertIn("提示：Ctrl+F", tip)

    def test_06_encoding_utf8_no_bom_and_lf(self):
        """测试所有改动文件均采用 UTF-8 无 BOM 编码且使用 LF 换行符"""
        target_files = [
            os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'public.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'index.html'),
            os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'js', 'redis.js'),
        ]
        for lang in self.LANGS:
            target_files.append(os.path.join(PROJECT_ROOT, 'plugins', 'redis', 'lang', f'{lang}.json'))
            target_files.append(os.path.join(PROJECT_ROOT, 'web', 'static', 'language', lang, 'public.json'))

        for p in target_files:
            with open(p, 'rb') as fp:
                raw = fp.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"File has UTF-8 BOM: {p}")
            self.assertNotIn(b'\r\n', raw, f"File contains CRLF line endings (must use LF): {p}")

if __name__ == '__main__':
    unittest.main()
