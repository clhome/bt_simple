# coding:utf-8
"""日志模块多国语言适配回归。

覆盖三层：

1. ``web/core/i18n.py`` 把 ``log.json`` 纳入后端词典查找（平面键，且优先于
   public.json —— 两者有 47 个同名键）。
2. ``web/utils/log_i18n.py`` 把「库里的中文原文」按目标语言重新渲染：
   类型、整句模板（含 ``{n}`` / ``{}`` / ``%s`` 占位符）、以及历史 HTML 片段。
   匹配不到时必须原样返回（操作系统/命令行输出的中文不翻译）。
3. ``web/utils/adult_log.getLogsTitle`` 的日志审计标题走词典。
"""
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
sys.path.insert(0, os.path.join(ROOT, 'web'))

import core.i18n as i18n  # noqa: E402
import utils.log_i18n as log_i18n  # noqa: E402
import utils.adult_log as adult_log  # noqa: E402

LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')


def load_log(lang):
    with io.open(os.path.join(LANG_DIR, lang, 'log.json'), encoding='utf-8') as fh:
        return json.load(fh)


class _ForceLang(object):
    """把后端当前语言钉死，避免依赖面板 data/language.pl。"""

    def __init__(self, lang):
        self.lang = lang
        self._patcher = None

    def __enter__(self):
        self._patcher = mock.patch.object(i18n, 'get_current_lang', lambda: self.lang)
        self._patcher.start()
        return self

    def __exit__(self, *a):
        self._patcher.stop()


class TestLogDictionary(unittest.TestCase):
    def test_new_keys_present_and_uniform(self):
        base = set(load_log('zh-CN'))
        for lang in LANGS:
            self.assertEqual(set(load_log(lang)), base,
                             '%s/log.json 键集与 zh-CN 不一致' % lang)

    def test_required_keys_exist(self):
        zh = load_log('zh-CN')
        for key in ('TYPE_SSH', 'TYPE_PLUGIN', 'MOVE_RENAME_SUCCESS',
                    'LOGIN_SUCCESS_USER', 'OP_WAF_LINK_FAIL',
                    'TITLE_AUTH', 'TITLE_GENERIC', 'PANEL_PHP_CLI_VERSION'):
            self.assertIn(key, zh, '缺少日志词典键 %s' % key)

    def test_dirty_duplicate_value_fixed(self):
        """FILE_ALL_DEL 曾误抄 FILE_ALL_ACCESS 的原文（批量设置权限成功!）。"""
        zh = load_log('zh-CN')
        self.assertNotEqual(zh['FILE_ALL_DEL'], zh['FILE_ALL_ACCESS'])
        self.assertIn('删除', zh['FILE_ALL_DEL'])

    def test_log_json_wins_over_public_json(self):
        """FILE_SAVE_SUCCESS 两处都有，日志文案必须以 log.json 为准（带 {1}）。"""
        with _ForceLang('en'):
            self.assertIn('{1}', i18n.t('FILE_SAVE_SUCCESS'))
            self.assertEqual(i18n.t('FILE_SAVE_SUCCESS', '/x'),
                             'The file [/x] was saved successfully!')

    def test_values_have_no_html(self):
        import re
        html = re.compile(r'<[a-zA-Z/][^>]*>')
        for lang in LANGS:
            for key, value in load_log(lang).items():
                self.assertFalse(html.search(value),
                                 '%s %s 译文含 HTML' % (lang, key))


class TestLogType(unittest.TestCase):
    def test_known_types(self):
        with _ForceLang('en'):
            self.assertEqual(log_i18n.translate_log_type('文件管理'), 'File Management')
            self.assertEqual(log_i18n.translate_log_type('用户登录'), 'User Login')
            self.assertEqual(log_i18n.translate_log_type('安全机制'), 'Security')

    def test_dynamic_suffix_kept(self):
        with _ForceLang('en'):
            self.assertEqual(log_i18n.translate_log_type('插件管理[PHP]'),
                             'Plugin Management[PHP]')

    def test_plugin_name_untouched(self):
        """插件名不是中文，不属于面板词典。"""
        with _ForceLang('en'):
            self.assertEqual(log_i18n.translate_log_type('fail2ban'), 'fail2ban')

    def test_zh_cn_roundtrip(self):
        with _ForceLang('zh-CN'):
            self.assertEqual(log_i18n.translate_log_type('文件管理'), '文件管理')


class TestLogMessage(unittest.TestCase):
    def test_rendered_history_records(self):
        """库里存的是插值后的整句，必须能反解出参数并重新渲染。"""
        with _ForceLang('en'):
            self.assertEqual(
                log_i18n.translate_log_message('文件[/x]保存成功'),
                'The file [/x] was saved successfully!')
            self.assertEqual(
                log_i18n.translate_log_message('创建文件[//c]成功!'),
                'The file [//c] was successfully created!')
            self.assertEqual(
                log_i18n.translate_log_message('用户[a]登录成功, 登录IP:1.2.3.4'),
                'User [a] logged in successfully, Login IP: 1.2.3.4')
            # 历史记录里逗号后可能没有空格
            self.assertEqual(
                log_i18n.translate_log_message('用户[a]登录成功,登录IP:1.2.3.4'),
                'User [a] logged in successfully, Login IP: 1.2.3.4')

    def test_percent_and_brace_placeholders(self):
        with _ForceLang('en'):
            self.assertEqual(
                log_i18n.translate_log_message('设置PHP-CLI版本为: 8.2'),
                'PHP-CLI version set to: 8.2')

    def test_multi_arg_and_reordered_output(self):
        with _ForceLang('en'):
            self.assertEqual(
                log_i18n.translate_log_message('网站[test]删除域名[a.com:80]成功!'),
                'The domain [a.com:80] was deleted from the website [test] successfully!')

    def test_legacy_html_fragment_stripped(self):
        with _ForceLang('en'):
            msg = ("<a style='color: red'>用户名或密码错误</a>,帐号:admin,"
                   "密码:******,登录IP:1.2.3.4")
            out = log_i18n.translate_log_message(msg)
            self.assertNotIn('<a ', out)
            self.assertIn('admin', out)

    def test_os_text_passthrough(self):
        """操作系统/命令行输出的中文不从面板词典来，必须原样返回。"""
        raw = '部分不受词典覆盖的系统提示，例如: 无法识别的设备'
        with _ForceLang('en'):
            self.assertEqual(log_i18n.translate_log_message(raw), raw)
            self.assertEqual(log_i18n.translate_log_message('File saved'), 'File saved')

    def test_pureftp_style_message(self):
        """历史缺陷：调用曾把词典键当消息、丢失类型中文；现改为完整中文模板。"""
        with _ForceLang('en'):
            self.assertEqual(
                log_i18n.translate_log_message('删除FTP用户[web1]成功!'),
                'The FTP user [web1] has been successfully deleted!')

    def test_zh_tw(self):
        with _ForceLang('zh-TW'):
            self.assertEqual(log_i18n.translate_log_message('文件[/x]保存成功'),
                             '檔案[/x]儲存成功!')


class TestAuditTitles(unittest.TestCase):
    def test_titles_translated(self):
        with _ForceLang('en'):
            self.assertEqual(adult_log.getLogsTitle('auth.log'), 'Authorization Log')
            self.assertEqual(adult_log.getLogsTitle('wtmp'), 'Login and Reboot Records')
            self.assertEqual(adult_log.getLogsTitle('lastlog'), 'Last User Login')

    def test_generic_fallback_keeps_name(self):
        with _ForceLang('en'):
            self.assertEqual(adult_log.getLogsTitle('php8.4-fpm.log.1'), 'php8 log')

    def test_zh_cn_titles(self):
        with _ForceLang('zh-CN'):
            self.assertEqual(adult_log.getLogsTitle('auth.log'), '授权日志')
            self.assertEqual(adult_log.getLogsTitle('README'), 'README日志')


if __name__ == '__main__':
    unittest.main()
