# coding: utf-8
"""凭据处理加固回归（task.md 第 1 层 B1/B2；P0-2 后更新为 POST 快捷登录）。

  B1 快捷登录不得成为限流旁路 / 会话固定入口 / 2FA 旁路 / 弱哈希专属通道
  B2 关联面板密码不得明文入库，接口不得回传明文，前端不得把明文写进 DOM

旧机制 `GET /<安全入口>?login=base64(json{password})` 已废弃（报告 P0-2），
改为 `POST /<安全入口>/quick_login`：口令只在 body、nonce 一次性、强制 2FA。
深度守卫见 `test_quick_login_nonce_hardening.py`。

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


def _body(src, name):
    return src.split('def ' + name + '(')[1].split('\ndef ')[0]


class TestQuickLoginHardening(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/admin/dashboard/dashboard.py')

    def test_legacy_get_login_branch_deprecated(self):
        body = _body(self.src, 'admin_safe_path')
        for banned in ('base64', 'json.loads', '_password_matches', 'time_diff',
                       "session['login']"):
            self.assertNotIn(banned, body,
                             '安全入口 GET ?login= 旧机制必须彻底废弃：%s' % banned)

    def test_quick_login_reuses_rate_limit(self):
        body = _body(self.src, 'quick_login')
        self.assertIn('_is_banned', body, '快捷登录必须复用登录封禁')
        self.assertIn('_register_login_failure', body, '失败必须计入统一失败计数')
        self.assertIn('_reset_login_failure', body, '成功必须清空失败计数')
        self.assertIn('_password_matches', body, '必须支持 bcrypt（而非仅 MD5）')

    def test_quick_login_only_accepts_post(self):
        rule = next(l for l in self.src.splitlines() if "endpoint='quick_login'" in l)
        self.assertIn("methods=['POST']", rule)

    def test_quick_login_time_window_two_sided(self):
        body = _body(self.src, 'quick_login')
        self.assertIn('QUICK_LOGIN_TTL_MS', body)
        self.assertIn('abs(now_ms - stamp_ms)', body, '必须拒绝过旧与未来时间戳')
        ttl = self.src.split('QUICK_LOGIN_TTL_MS = ')[1].split('\n')[0]
        self.assertEqual(ttl.replace(' ', ''), '60*1000')

    def test_quick_login_forces_two_step(self):
        body = _body(self.src, 'quick_login')
        self.assertIn('two_step_verification', body, '必须校验二步验证')
        self.assertIn('quick_login_nonce.burn', body, 'nonce 必须用后即焚')
        self.assertLess(body.index('two_step_verification'), body.index('_login_success(info'),
                        '2FA 判断必须早于建立登录态')


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

    def test_login_payload_minted_server_side(self):
        self.assertIn('def get_panel_login', self.src)
        body = self.src.split('def get_panel_login')[1].split('def del_panel_info')[0]
        self.assertIn('_dec_pwd', body)
        self.assertIn("'fields'", body)
        self.assertNotIn('login=', body, '口令不得再拼进 URL')
        self.assertNotIn('b64encode', body)

    def test_url_scheme_validated(self):
        self.assertIn('_valid_panel_url', self.src)
        for fn in ('add_panel_info', 'set_panel_info', 'get_panel_login'):
            body = self.src.split('def ' + fn)[1].split('\n@blueprint')[0]
            self.assertIn('_valid_panel_url', body, fn)

    def test_frontend_no_plaintext_password_in_dom(self):
        self.assertNotIn('data-pw', self.js, '前端 DOM 不得再携带明文口令')
        self.assertIn('get_panel_login', self.js, '快捷登录必须走服务端现签接口')
        self.assertIn('res.data.fields', self.js, '口令必须装进 POST body 字段')
        self.assertNotIn('window.open(res.data.url)', self.js)


if __name__ == '__main__':
    unittest.main()
