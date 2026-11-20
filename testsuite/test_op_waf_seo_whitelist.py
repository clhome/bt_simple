# coding: utf-8
import sys
import os
import re
import json
import unittest

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, "web"))
sys.path.insert(0, os.path.join(base_dir, "plugins", "op_waf"))

import plugins.op_waf.index as waf_index


class TestOpWafSeoWhitelist(unittest.TestCase):
    """
    测试御风网站防火墙 op_waf 底层 SEO 白名单与蜘蛛白名单优化
    """

    @classmethod
    def setUpClass(cls):
        cls.init_lua_path = os.path.join(base_dir, "plugins", "op_waf", "waf", "lua", "init.lua")
        cls.spider_ip_json_path = os.path.join(base_dir, "plugins", "op_waf", "waf", "rule", "spider_ip.json")
        cls.url_white_json_path = os.path.join(base_dir, "plugins", "op_waf", "waf", "rule", "url_white.json")

    def test_01_init_lua_contains_seo_whitelist_logic(self):
        """验证 init.lua 中正确实现了 waf_seo_white 并在 run_app_waf 中被正确接入"""
        with open(self.init_lua_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("local function waf_seo_white()", content, "init.lua 必须实现 waf_seo_white 函数")
        self.assertIn("method ~= \"GET\" and method ~= \"HEAD\"", content, "waf_seo_white 必须限制安全只读方法")
        self.assertIn("/robots.txt", content, "waf_seo_white 必须包含 /robots.txt 放行")
        self.assertIn("/sitemap", content, "waf_seo_white 必须包含 /sitemap 相关路径放行")
        self.assertIn("if waf_seo_white() then return true end", content, "run_app_waf 必须在防御链中调用 waf_seo_white")

    def test_02_seo_path_regex_matching(self):
        """验证 SEO 路径正则能匹配所有标准 Sitemap 和 Robots 变体"""
        # 复现 Lua 中的正则逻辑: ^/sitemap([-_a-z0-9]*)?\.(xml|txt|xml\.gz)$
        sitemap_pattern = re.compile(r"^/sitemap([-_a-z0-9]*)?\.(xml|txt|xml\.gz)$", re.IGNORECASE)

        valid_sitemaps = [
            "/sitemap.xml",
            "/sitemap.txt",
            "/sitemap.xml.gz",
            "/sitemap_index.xml",
            "/sitemap-posts.xml",
            "/sitemap_1.xml",
            "/sitemap2026.xml",
            "/sitemap-pages.xml.gz",
        ]
        for path in valid_sitemaps:
            self.assertTrue(sitemap_pattern.match(path), f"合法站点地图路径应被命中: {path}")

        invalid_paths = [
            "/sitemap.php",
            "/sitemap.html",
            "/sitemap/",
            "/admin/sitemap.xml",
            "/index.php",
            "/robots.txt.bak",
        ]
        for path in invalid_paths:
            self.assertFalse(sitemap_pattern.match(path), f"非标准站点地图路径不得误放行: {path}")

    def test_03_spider_ua_regex_expansion(self):
        """验证 UA 扩展正则能精准匹配 Google 官方全套工具及各大现代爬虫"""
        with open(self.init_lua_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 init.lua 中的蜘蛛匹配正则
        m = re.search(r'ngx\.re\.find\(ua,\s*"([^"]+)",\s*"ijo"\)', content)
        self.assertIsNotNone(m, "必须找到 ua 正则表达式")
        lua_pattern_str = m.group(1)

        spider_re = re.compile(lua_pattern_str, re.IGNORECASE)

        # 1. 应当被成功识别为蜘蛛的 UA
        legit_spiders = [
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; Google-InspectionTool/1.0;)",  # GSC 实时测试
            "Google-Site-Verification/1.0",  # GSC 验证工具
            "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
            "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
            "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
            "Mozilla/5.0 (compatible; Bytespider; https://zhanzhang.toutiao.com/)",
            "Mozilla/5.0 (compatible; 360Spider/3.0;)",
            "Mozilla/5.0 (compatible; HaosouSpider;)",
            "Mozilla/5.0 (compatible; Sogou web spider/4.0; +http://www.sogou.com/docs/help/websearchhelp.htm)",
            "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
            "DuckDuckBot/1.0; (+http://duckduckgo.com/duckduckbot.html)",
        ]
        for ua in legit_spiders:
            self.assertTrue(spider_re.search(ua), f"主流爬虫 UA 必须被识别: {ua}")

        # 2. 普通访客 / 攻击载荷不应误识别为蜘蛛
        regular_visitors = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "curl/7.88.1",
            "python-requests/2.28.1",
            "sqlmap/1.6#stable",
            "Wget/1.21.3",
        ]
        for ua in regular_visitors:
            self.assertFalse(spider_re.search(ua), f"常规访客/攻击工具不应误判为蜘蛛: {ua}")

    def test_04_spider_ip_contains_google_ipv6_and_modern_cidrs(self):
        """验证 spider_ip.json 中补齐了 Google 官方公布的 IPv6 与现代 IPv4 网段"""
        with open(self.spider_ip_json_path, 'r', encoding='utf-8') as f:
            spider_rules = json.load(f)

        ips = [r[0] for r in spider_rules]
        descriptions = [r[1] for r in spider_rules]

        # 验证 IPv4 核心段
        self.assertIn("66.249.64.0/19", ips, "必须包含 66.249.64.0/19")
        self.assertIn("66.102.6.0/23", ips, "必须包含 66.102.6.0/23")
        self.assertIn("66.249.80.0/20", ips, "必须包含 66.249.80.0/20")

        # 验证 IPv6 官方段
        self.assertIn("2001:4860:4801::/48", ips, "必须包含 Google IPv6 网段 2001:4860:4801::/48")
        self.assertIn("2001:4860:4802::/48", ips, "必须包含 Google IPv6 网段 2001:4860:4802::/48")

        # 验证 Bingbot 与 DuckDuckGo
        self.assertIn("2a01:111:2006::/48", ips, "必须包含 Bing IPv6 网段")
        self.assertIn("20.191.45.0/24", ips, "必须包含 DuckDuckGo 网段")

        # 验证总规则数丰富度
        self.assertGreaterEqual(len(spider_rules), 60, "权威爬虫规则库总条数应 >= 60 条")

    def test_05_url_white_contains_robots_and_sitemap(self):
        """验证 url_white.json 默认预置了 /robots.txt 和 /sitemap.*"""
        with open(self.url_white_json_path, 'r', encoding='utf-8') as f:
            white_rules = json.load(f)

        patterns = [r[1] for r in white_rules]
        self.assertTrue(any("robots" in p for p in patterns), "url_white 必须预置 robots.txt 白名单")
        self.assertTrue(any("sitemap" in p for p in patterns), "url_white 必须预置 sitemap.* 白名单")


if __name__ == "__main__":
    unittest.main()

