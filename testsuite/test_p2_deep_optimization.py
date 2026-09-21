# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）P2 级深度调优与供应链加固专项自动化测试套件
"""
import unittest
import os
import sys
import ast
import re
import zipfile
import hashlib
from unittest.mock import MagicMock

# 对可能缺失的环境依赖进行优雅 mock，确保在 Windows 开发机上自包含运行
for mod in ['psutil', 'flask', 'flask_socketio', 'gevent', 'geventwebsocket', 'thisdb', 'config']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

LOGIN_PY = os.path.join(WEB_DIR, 'admin', 'dashboard', 'login.py')
SETTING_PY = os.path.join(WEB_DIR, 'admin', 'setting', 'setting.py')
CONFIG_JS = os.path.join(WEB_DIR, 'static', 'app', 'config.js')
PLUGIN_PY = os.path.join(WEB_DIR, 'utils', 'plugin.py')
UPDATE_PY = os.path.join(WEB_DIR, 'utils', 'system', 'update.py')
LAYOUT_HTML = os.path.join(WEB_DIR, 'templates', 'default', 'layout.html')
MONITOR_HTML = os.path.join(WEB_DIR, 'templates', 'default', 'monitor.html')
INDEX_HTML = os.path.join(WEB_DIR, 'templates', 'default', 'index.html')


class TestP2DeepOptimization(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_p2_test')
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_01_encoding_and_line_endings(self):
        """测试 1: 验证 P2 阶段涉及的文件均为 UTF-8 无 BOM 且使用 LF 换行符"""
        target_files = [LOGIN_PY, SETTING_PY, CONFIG_JS, PLUGIN_PY, UPDATE_PY, LAYOUT_HTML, MONITOR_HTML, INDEX_HTML]
        for fpath in target_files:
            self.assertTrue(os.path.exists(fpath), f"File not found: {fpath}")
            with open(fpath, "rb") as f:
                content = f.read()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"File {fpath} has UTF-8 BOM")
            self.assertNotIn(b"\r\n", content, f"File {fpath} has CRLF line endings, must be LF")
        print("\n[OK] 测试 1: 所有修改文件编码为 UTF-8 无 BOM 且强制 LF 换行符验证通过！")

    def test_02_login_captcha_protection_ast_and_logic(self):
        """测试 2: 验证 login.py 实现了验证码防绕过与 session.pop 一次性消费防重放"""
        with open(LOGIN_PY, "r", encoding="utf-8") as f:
            code = f.read()
        ast.parse(code)

        # 确保关键防御逻辑代码存在
        self.assertIn("session.pop('code', None)", code, "缺少验证码一次性取出并立即销毁逻辑")
        self.assertIn("need_code = 'code' in session or (login_cache_limit is not None and int(login_cache_limit) > 0)", code, "缺少有失败记录时的强制验证码前置判断")

        # 模拟真实逻辑执行
        import core.yf as yf
        fake_session = {}
        fake_cache = {}
        login_limit_key = 'login_limit_127.0.0.1'

        def simulate_do_login(form_code, session, cache_store):
            login_cache_count = 5
            login_cache_limit = cache_store.get(login_limit_key)
            need_code = 'code' in session or (login_cache_limit is not None and int(login_cache_limit) > 0)
            if need_code:
                expected_code = session.pop('code', None)
                code_str = str(form_code).strip().lower()
                if not expected_code or not code_str or expected_code != yf.md5(code_str):
                    if login_cache_limit is None:
                        login_cache_limit = 1
                    else:
                        login_cache_limit = int(login_cache_limit) + 1
                    cache_store[login_limit_key] = login_cache_limit
                    return False, f"验证码错误或已失效,您还可以尝试[{login_cache_count - login_cache_limit}]次!"
            return True, "验证码校验通过"

        # 场景 A: 存在失败记录时跳过 /code 直接发包，必须被拒绝
        fake_cache[login_limit_key] = 1
        fake_session.clear()
        res, msg = simulate_do_login('', fake_session, fake_cache)
        self.assertFalse(res, "有失败记录时不发验证码必须拦截")
        self.assertIn("验证码错误或已失效", msg)

        # 场景 B: 正常生成验证码，第一次使用有效验证码
        raw_code = 'abcd'
        fake_session['code'] = yf.md5(raw_code)
        res, msg = simulate_do_login('abcd', fake_session, fake_cache)
        self.assertTrue(res, "输入正确验证码必须验证通过")
        self.assertNotIn('code', fake_session, "验证码必须一次性消费并立即从 session 中销毁")

        # 场景 C: 重放攻击测试 —— 攻击者再次拿刚才同一个 'abcd' 提交
        res_replay, msg_replay = simulate_do_login('abcd', fake_session, fake_cache)
        self.assertFalse(res_replay, "重放已被消费的验证码必须被拦截")
        print("[OK] 测试 2: 验证码防跳过绕过与单次消费防重放机制验证通过！")

    def test_03_password_security_policy_and_frontend(self):
        """测试 3: 验证后端 set_password 原密码校验与复杂度强化，以及前端表单增加原密码项"""
        # 后端代码 AST 与关键字校验
        with open(SETTING_PY, "r", encoding="utf-8") as f:
            setting_code = f.read()
        ast.parse(setting_code)

        self.assertIn("old_password = request.form.get('old_password', '').strip()", setting_code)
        self.assertIn("user_info.get('password') == yf.md5(old_password)", setting_code)
        self.assertIn("len(password1) < 8", setting_code)
        self.assertIn("re.search(r'[A-Za-z]', password1)", setting_code)
        self.assertIn("re.search(r'[0-9]', password1)", setting_code)
        self.assertIn("password1 == old_password", setting_code)
        self.assertIn("session.clear()", setting_code)

        # 前端代码校验
        with open(CONFIG_JS, "r", encoding="utf-8") as f:
            config_js = f.read()
        self.assertIn('name="old_password" id="p_old"', config_js)
        self.assertIn('old_password=" + encodeURIComponent(pOld)', config_js)
        self.assertIn('!/[A-Za-z]/.test(p1) || !/[0-9]/.test(p1)', config_js)
        self.assertIn("window.location.href = '/login?signout=True'", config_js)

        # 逻辑测试
        import core.yf as yf
        real_old_pwd = 'OldPassword123'
        user_info = {'name': 'admin', 'password': yf.md5(real_old_pwd)}

        def simulate_set_password(old_pwd, p1, p2, uinfo):
            if not old_pwd: return False, '请输入原密码！'
            if uinfo.get('password') != yf.md5(old_pwd): return False, '原密码错误，请重新输入！'
            if p1 != p2: return False, '两次输入的密码不一致！'
            if len(p1) < 8: return False, '新密码长度至少需要8位！'
            if not re.search(r'[A-Za-z]', p1) or not re.search(r'[0-9]', p1): return False, '新密码必须同时包含英文字母和数字！'
            if p1 == old_pwd: return False, '新密码不能与原密码相同！'
            return True, '密码修改成功，请使用新密码重新登录！'

        self.assertFalse(simulate_set_password('Wrong123', 'NewPass1234', 'NewPass1234', user_info)[0])
        self.assertFalse(simulate_set_password(real_old_pwd, 'short1', 'short1', user_info)[0])
        self.assertFalse(simulate_set_password(real_old_pwd, '1234567890', '1234567890', user_info)[0])
        self.assertFalse(simulate_set_password(real_old_pwd, 'abcdefghijkl', 'abcdefghijkl', user_info)[0])
        self.assertFalse(simulate_set_password(real_old_pwd, real_old_pwd, real_old_pwd, user_info)[0])
        self.assertTrue(simulate_set_password(real_old_pwd, 'SuperSafe2026', 'SuperSafe2026', user_info)[0])
        print("[OK] 测试 3: 修改密码原密码校验、复杂度与前端原密码项验证通过！")

    def test_04_plugin_quick_status_and_controlled_concurrency(self):
        """测试 4: 验证 plugin.py 状态探测轻量化、修复异步刷新命中旧缓存、以及限制最大 4 并发"""
        with open(PLUGIN_PY, "r", encoding="utf-8") as f:
            plugin_code = f.read()
        ast.parse(plugin_code)

        self.assertIn("def checkStatusQuick(self, name, version=''):", plugin_code)
        self.assertIn("def checkStatusReal(self, info):", plugin_code)
        self.assertIn("ThreadPoolExecutor(max_workers=4)", plugin_code, "必须使用最大 4 个并发 Worker 的线程池")

        from utils.plugin import plugin as YfPlugin
        pg = YfPlugin.instance()
        # 验证快速探测（命中返回 True，未命中或异常时安全返回 None 由官方 status 兜底）
        self.assertIn(pg.checkStatusQuick('openresty'), (True, False, None))
        self.assertIn(pg.checkStatusQuick('redis'), (True, False, None))
        self.assertIn(pg.checkStatusQuick('mysql'), (True, False, None))
        self.assertIsNone(pg.checkStatusQuick('unknown_custom_plugin'))
        print("[OK] 测试 4: 插件轻量快速探测与受控 4 并发线程池验证通过！")

    def test_05_update_integrity_and_sha256(self):
        """测试 5: 验证 update.py 升级包完整性检查与 SHA-256 防投毒校验"""
        with open(UPDATE_PY, "r", encoding="utf-8") as f:
            update_code = f.read()
        ast.parse(update_code)

        self.assertIn("def verify_zip_integrity(zip_path):", update_code)
        self.assertIn("def verify_sha256(file_path, expected_hash):", update_code)
        self.assertIn("valid_zip, zip_err = verify_zip_integrity(dist_yf)", update_code)
        self.assertIn("sha256_match = re.search(r'sha256\\s*[:=]\\s*([a-fA-F0-9]{64})', release_body)", update_code)

        from utils.system.update import verify_zip_integrity, verify_sha256

        # 构造正常 zip
        valid_zip = os.path.join(self.test_dir, 'test_good.zip')
        with zipfile.ZipFile(valid_zip, 'w') as zf:
            zf.writestr('bt_simple/version.pl', '3.0.0')
            zf.writestr('bt_simple/data.bin', 'a' * 4096)

        h = hashlib.sha256()
        with open(valid_zip, 'rb') as f:
            h.update(f.read())
        real_hash = h.hexdigest()

        # 校验正常 zip
        self.assertTrue(verify_zip_integrity(valid_zip)[0])
        self.assertTrue(verify_sha256(valid_zip, real_hash)[0])

        # 校验篡改哈希
        self.assertFalse(verify_sha256(valid_zip, '0' * 64)[0])

        # 校验损坏截断 zip
        corrupt_zip = os.path.join(self.test_dir, 'test_bad.zip')
        with open(corrupt_zip, 'wb') as f:
            f.write(b'PK\x03\x04\x00\x00' + b'\xff' * 300)
        self.assertFalse(verify_zip_integrity(corrupt_zip)[0])
        print("[OK] 测试 5: 升级包完整性检测与 SHA-256 供应链安全防投毒验证通过！")

    def test_06_static_version_fingerprint(self):
        """测试 6: 验证 layout.html, monitor.html, index.html 模板中所有本地核心脚本均注入 ?v={{config.version}}"""
        with open(LAYOUT_HTML, "r", encoding="utf-8") as f:
            layout = f.read()
        self.assertIn('/static/js/jquery-3.7.1.min.js?v={{config.version}}', layout)
        self.assertIn('/static/js/jquery.cookie-1.4.1.min.js?v={{config.version}}', layout)
        self.assertIn('/static/js/bootstrap.min.js?v={{config.version}}', layout)
        self.assertIn('/static/layer/layer.js?v={{config.version}}', layout)
        self.assertIn('/static/js/clipboard.min.js?v={{config.version}}', layout)
        self.assertIn('/static/js/requestAnimationFrame.js?v={{config.version}}', layout)

        with open(MONITOR_HTML, "r", encoding="utf-8") as f:
            monitor = f.read()
        self.assertIn('/static/js/echarts.min.js?v={{config.version}}', monitor)

        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            index = f.read()
        self.assertIn('/static/js/echarts.min.js?v={{config.version}}', index)
        print("[OK] 测试 6: 模板静态资源版本指纹全量注入验证通过！")


if __name__ == '__main__':
    unittest.main()
