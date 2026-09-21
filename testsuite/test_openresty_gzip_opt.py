# coding:utf-8
import sys
import os
import unittest
import re

# 导入 openresty 模块的 healGzipConf 方法
import importlib.util
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
openresty_index_path = os.path.join(project_dir, 'plugins', 'openresty', 'index.py')
spec = importlib.util.spec_from_file_location("openresty_plugin_module", openresty_index_path)
openresty_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(openresty_plugin)


class TestOpenRestyGzipOpt(unittest.TestCase):

    def test_heal_old_gzip_proxied(self):
        old_conf = """
http {
    gzip on;
    gzip_min_length  1k;
    gzip_buffers     4 16k;
    gzip_http_version 1.1;
    gzip_comp_level 6;
    gzip_types     text/plain text/css application/json application/javascript application/x-javascript text/javascript text/xml application/xml application/xml+rss image/svg+xml;
    gzip_vary on;
    gzip_proxied   expired no-cache no-store private auth;
    gzip_disable   "MSIE [1-6]\\.";
}
"""
        new_conf, need_write = openresty_plugin.healGzipConf(old_conf)
        self.assertTrue(need_write, "应当触发更新")
        self.assertIn("gzip_proxied   any;", new_conf, "gzip_proxied 应当被升级为 any")
        self.assertIn("gzip_static    on;", new_conf, "应当自动补齐 gzip_static on")
        self.assertNotIn("expired no-cache", new_conf, "旧限制性规则应当被移除")

    def test_heal_missing_proxied_and_static(self):
        bare_conf = """
http {
    gzip on;
    gzip_min_length 1k;
}
"""
        new_conf, need_write = openresty_plugin.healGzipConf(bare_conf)
        self.assertTrue(need_write, "应当触发更新")
        self.assertIn("gzip_proxied   any;", new_conf, "应当补齐 gzip_proxied any")
        self.assertIn("gzip_static    on;", new_conf, "应当补齐 gzip_static on")

    def test_heal_already_optimized(self):
        optimized_conf = """
http {
    gzip on;
    gzip_min_length  1k;
    gzip_buffers     4 16k;
    gzip_http_version 1.1;
    gzip_comp_level 6;
    gzip_types     text/plain text/css application/json application/javascript application/x-javascript text/javascript text/xml application/xml application/xml+rss image/svg+xml;
    gzip_vary on;
    gzip_proxied   any;
    gzip_static    on;
    gzip_disable   "MSIE [1-6]\\.";
}
"""
        new_conf, need_write = openresty_plugin.healGzipConf(optimized_conf)
        self.assertFalse(need_write, "已优化配置不应重复触发更新")
        self.assertEqual(optimized_conf, new_conf, "内容应完全保持一致")

    def test_template_contains_optimizations(self):
        tpl_path = os.path.join(project_dir, 'plugins', 'openresty', 'conf', 'nginx.conf')
        with open(tpl_path, 'r', encoding='utf-8') as f:
            tpl_content = f.read()

        self.assertIn("brotli on;", tpl_content, "模板中必须默认开启 brotli on")
        self.assertIn("gzip on;", tpl_content, "模板中必须默认开启 gzip on")
        self.assertIn("gzip_proxied   any;", tpl_content, "模板中必须包含 gzip_proxied any")
        self.assertIn("gzip_static    on;", tpl_content, "模板中必须包含 gzip_static on")
        self.assertIn("brotli_static on;", tpl_content, "模板中必须包含 brotli_static on")


if __name__ == '__main__':
    unittest.main()
