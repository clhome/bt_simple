# coding:utf-8
import os
import re
import unittest

class TestFooterHeight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.site_css_path = os.path.join(cls.root_dir, "web", "static", "css", "site.css")
        cls.ensite_css_path = os.path.join(cls.root_dir, "web", "static", "css", "ensite.css")
        cls.layout_html_path = os.path.join(cls.root_dir, "web", "templates", "default", "layout.html")

    def test_site_css_footer_and_sidebar_collapse_height(self):
        self.assertTrue(os.path.exists(self.site_css_path), "site.css exists")
        with open(self.site_css_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配独立的 .footer
        footer_match = re.search(r'(?:^|\n)\.footer\s*\{([^}]+)\}', content)
        self.assertIsNotNone(footer_match, "site.css should define .footer")
        footer_rules = footer_match.group(1)
        self.assertIn("height: 40px", footer_rules, ".footer should have height: 40px")
        self.assertIn("line-height: 40px", footer_rules, ".footer should have line-height: 40px")

        # 匹配独立的 .sidebar-collapse
        collapse_match = re.search(r'(?:^|\n)\.sidebar-collapse\s*\{([^}]+)\}', content)
        self.assertIsNotNone(collapse_match, "site.css should define .sidebar-collapse")
        collapse_rules = collapse_match.group(1)
        self.assertIn("height: 40px", collapse_rules, ".sidebar-collapse should have height: 40px")
        self.assertIn("line-height: 40px", collapse_rules, ".sidebar-collapse should have line-height: 40px")

    def test_ensite_css_footer_height(self):
        self.assertTrue(os.path.exists(self.ensite_css_path), "ensite.css exists")
        with open(self.ensite_css_path, "r", encoding="utf-8") as f:
            content = f.read()

        footer_match = re.search(r'(?:^|\n)\.footer\s*\{([^}]+)\}', content)
        self.assertIsNotNone(footer_match, "ensite.css should define .footer")
        footer_rules = footer_match.group(1)
        self.assertIn("height: 40px", footer_rules, ".footer should have height: 40px in ensite.css")
        self.assertIn("line-height: 40px", footer_rules, ".footer should have line-height: 40px in ensite.css")

    def test_layout_html_structure(self):
        self.assertTrue(os.path.exists(self.layout_html_path), "layout.html exists")
        with open(self.layout_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('class="footer bgw"', content, "layout.html should contain .footer.bgw")
        self.assertIn('id="sidebar-collapse"', content, "layout.html should contain sidebar-collapse")

if __name__ == "__main__":
    unittest.main()
