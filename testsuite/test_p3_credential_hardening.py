# coding: utf-8
"""凭据处理加固回归（task.md 第 1 层 B1/B2）。

  B1 快捷登录（admin_safe_path?login=）不得成为限流旁路 / 会话固定入口 / 弱哈希专属通道
  B2 关联面板密码不得明文入库，接口不得回传明文，前端不得把明文写进 DOM

沿用仓库既有风格：静态/AST 断言，不依赖 flask app 上下文、不发起网络请求。
"""
import ast
import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


class TestQuickLoginHardening(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/admin/dashboard/dashboard.py')

    def _safe_path_body(self):
        return self.src.split('def admin_safe_path(')[1].split('\ndef ')[0]

    def test_quick_login_reuses_rate_limit(self):
        body = self._safe_path_body()
        self.assertIn('_is_banned', body, '快捷登录必须复用登录封禁')
        self.assertIn('_register_login_failure', body, '失败必须计入统一失败计数')
        self.assertIn('_reset_login_failure', body, '成功必须清空失败计数')
        self.assertIn('_password_matches', body, '必须支持 bcrypt（而非仅 MD5）')

    def test_quick_login_no_plain_md5_compare(self):
        body = self._safe_path_body()
        self.assertNotIn("yf.md5(data['password'])", body,
                         '不得再直接比较 MD5，bcrypt 迁移后该路径会失效')

    def test_quick_login_clears_session(self):
        body = self._safe_path_body()
        self.assertIn('session.clear()', body, '设置登录态前必须清空旧会话，防会话固定')

    def test_quick_login_time_window_two_sided(self):
        body = self._safe_path_body()
        self.assertIn('time_diff < -2000', body, '必须拒绝未来时间戳')


class TestPanelBookmarkCredentialHardening(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/admin/setting/panel_bookmark.py')
        cls.js = _read('web/static/app/public.js')

    def test_password_encrypted_at_rest(self):
        self.assertIn('def _enc_pwd', self.src)
        self.assertIn('enDoubleCrypt', self.src)
        add_body = self.src.split('def add_panel_info')[1].split('def get_panel_list')[0]
        self.assertIn('_enc_pwd(password)', add_body)
        set_body = self.src.split('def set_panel_info')[1]
        self.assertIn('_enc_pwd(password)', set_body)
        # 空密码代表“不修改”，不得清空历史密码
        self.assertIn('if password:', set_body)

    def test_list_does_not_return_password(self):
        list_body = self.src.split('def get_panel_list')[1].split('def get_panel_login')[0]
        self.assertNotIn('password', list_body,
                         'get_panel_list 不得再回传明文密码')

    def test_login_url_minted_server_side(self):
        self.assertIn('def get_panel_login', self.src)
        body = self.src.split('def get_panel_login')[1].split('def del_panel_info')[0]
        self.assertIn('_dec_pwd', body)
        self.assertIn("'login='", body)

    def test_url_scheme_validated(self):
        self.assertIn('_valid_panel_url', self.src)
        for fn in ('add_panel_info', 'set_panel_info', 'get_panel_login'):
            body = self.src.split('def ' + fn)[1].split('\n@blueprint')[0]
            self.assertIn('_valid_panel_url', body, fn)

    def test_frontend_no_plaintext_password_in_dom(self):
        self.assertNotIn('data-pw', self.js, '前端 DOM 不得再携带明文口令')
        self.assertIn('get_panel_login', self.js, '快捷登录必须走服务端现签接口')


if __name__ == '__main__':
    unittest.main()
