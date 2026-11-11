# coding:utf-8
import sys
import os
import unittest
import importlib.util

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
openresty_index_path = os.path.join(project_dir, 'plugins', 'openresty', 'index.py')
spec = importlib.util.spec_from_file_location("openresty_plugin_module", openresty_index_path)
openresty_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(openresty_plugin)


class TestOpenRestyServerHeaderHeal(unittest.TestCase):

    def test_heal_old_header_double_quotes(self):
        old_conf = """
http {
    server_tokens off;
    access_log /dev/null;
    more_set_headers "Server: mdserver-web";
    
    include /www/server/web_conf/nginx/vhost/*.conf;
}
"""
        new_conf, need_write = openresty_plugin.healServerHeader(old_conf)
        self.assertTrue(need_write, "旧双引号 mdserver-web 头应当触发自愈写盘")
        self.assertIn('more_set_headers "Server: Yufeng-Panel";', new_conf)
        self.assertNotIn("mdserver-web", new_conf)

    def test_heal_old_header_single_quotes(self):
        old_conf = """
http {
    server_tokens off;
    more_set_headers 'Server: mdserver-web';
}
"""
        new_conf, need_write = openresty_plugin.healServerHeader(old_conf)
        self.assertTrue(need_write, "旧单引号 mdserver-web 头应当触发自愈写盘")
        self.assertIn('more_set_headers "Server: Yufeng-Panel";', new_conf)
        self.assertNotIn("mdserver-web", new_conf)

    def test_heal_old_header_spacing_variants(self):
        old_conf = """
http {
    server_tokens off;
    more_set_headers "Server:   mdserver-web" ;
}
"""
        new_conf, need_write = openresty_plugin.healServerHeader(old_conf)
        self.assertTrue(need_write, "包含额外空格的旧配置应当触发自愈写盘")
        self.assertIn('more_set_headers "Server: Yufeng-Panel";', new_conf)
        self.assertNotIn("mdserver-web", new_conf)

    def test_heal_already_yufeng_panel(self):
        current_conf = """
http {
    server_tokens off;
    access_log /dev/null;
    more_set_headers "Server: Yufeng-Panel";
    
    include /www/server/web_conf/nginx/vhost/*.conf;
}
"""
        new_conf, need_write = openresty_plugin.healServerHeader(current_conf)
        self.assertFalse(need_write, "已经是御风面板标头时不应触发任何写盘动作（0额外IO）")
        self.assertEqual(current_conf, new_conf, "内容必须保持严格一致")

    def test_heal_clean_conf_without_header(self):
        clean_conf = """
http {
    server_tokens off;
    access_log /dev/null;
}
"""
        new_conf, need_write = openresty_plugin.healServerHeader(clean_conf)
        self.assertFalse(need_write, "未配置自定义标头的正常配置不应触发自愈")
        self.assertEqual(clean_conf, new_conf)

    def test_template_integrity(self):
        tpl_path = os.path.join(project_dir, 'plugins', 'openresty', 'conf', 'nginx.conf')
        self.assertTrue(os.path.exists(tpl_path), "openresty 默认模板必须存在")
        with open(tpl_path, 'r', encoding='utf-8') as f:
            tpl_content = f.read()

        self.assertIn('more_set_headers "Server: Yufeng-Panel";', tpl_content, "模板中必须为御风面板标头")
        self.assertNotIn("mdserver-web", tpl_content, "模板中严禁残留 mdserver-web 标头")


if __name__ == '__main__':
    unittest.main()

