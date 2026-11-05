# coding: utf-8
import os
import sys
import types
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
for _p in (project_root, web_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_admin_pkg = types.ModuleType('admin')
_admin_pkg.__path__ = [os.path.join(web_dir, 'admin')]
sys.modules.setdefault('admin', _admin_pkg)

# Mock flask
class DummyBlueprint:
    def __init__(self, *args, **kwargs):
        pass
    def route(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

mock_flask = MagicMock()
mock_flask.Blueprint = DummyBlueprint
sys.modules['flask'] = mock_flask

if 'admin.user_login_check' not in sys.modules:
    mock_auth = MagicMock()
    mock_auth.panel_login_required = lambda f: f
    sys.modules['admin.user_login_check'] = mock_auth

import core.yf as yf
import thisdb
import flask
flask.Blueprint = DummyBlueprint


class TestCrontabSystemTaskGuard(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='yf_cron_guard_')

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_backend_del_and_modify_protects_system_tasks(self):
        # 1. Mock 系统核心任务与普通任务
        tasks_db = {
            '1': {'id': 1, 'name': '[勿删]ACME定时强制更新', 'echo': 'echo_acme'},
            '2': {'id': 2, 'name': '[勿删]御风OP防火墙后台任务', 'echo': 'echo_op_waf'},
            '3': {'id': 3, 'name': '[系统]日志维护任务', 'echo': 'echo_sys_log'},
            '4': {'id': 4, 'name': '普通用户备份任务', 'echo': 'echo_normal'}
        }

        old_getCrond = thisdb.getCrond
        thisdb.getCrond = lambda tid: tasks_db.get(str(tid))

        try:
            from core.i18n import t as _t
            from admin.crontab import crontab_del, modify_crond

            # 测试 1: 尝试删除 [勿删]ACME定时强制更新
            flask.request.form = {'id': '1'}
            res = crontab_del()
            self.assertFalse(res['status'])
            self.assertEqual(res['msg'], _t('crontab.system_task_protected'))

            # 测试 2: 尝试删除 [勿删]御风OP防火墙后台任务
            flask.request.form = {'id': '2'}
            res = crontab_del()
            self.assertFalse(res['status'])
            self.assertEqual(res['msg'], _t('crontab.system_task_protected'))

            # 测试 3: 尝试修改系统核心任务
            flask.request.form = {'id': '2', 'name': '篡改名字'}
            res = modify_crond()
            self.assertFalse(res['status'])
            self.assertEqual(res['msg'], _t('crontab.system_task_modify_protected'))

            # 测试 4: 普通任务不会被拦截为系统保护任务
            flask.request.form = {'id': '4'}
            res = crontab_del()
            self.assertNotEqual(res.get('msg'), _t('crontab.system_task_protected'))
        finally:
            thisdb.getCrond = old_getCrond

    def test_02_frontend_crontab_js_system_task_rendering(self):
        # 验证前端源码中系统任务的徽章渲染、禁用复选框以及去除编辑/删除按钮
        crontab_js_path = os.path.join(web_dir, 'static', 'app', 'crontab.js')
        with open(crontab_js_path, 'r', encoding='utf-8') as f:
            src = f.read()

        # 1. 必须包含系统任务判断
        self.assertIn("row_name.indexOf('[勿删]') === 0", src)
        # 2. 系统任务徽章必须存在
        self.assertIn("label-success", src)
        # 3. 必须对系统任务禁用 checkbox
        self.assertIn("disabled title=", src)
        # 4. 在系统任务分支中，不拼接 edit 与 del 动作
        self.assertIn("if (is_system)", src)
        # 5. planDel 函数具有前置防御
        self.assertIn("function planDel(id, name)", src)
        self.assertIn("name.indexOf('[勿删]') === 0", src)
        # 6. translateTaskName 函数存在并被使用
        self.assertIn("function translateTaskName(name)", src)
        self.assertIn("translateTaskName(row_name)", src)

    def test_03_multilingual_task_name_translation(self):
        from utils.crontab import crontab as crontab_util
        cron_inst = crontab_util.instance()

        # 1. 验证后端 humanTaskName 对常见系统任务的翻译识别
        self.assertTrue(hasattr(cron_inst, 'humanTaskName'))
        
        # ACME
        name_acme = cron_inst.humanTaskName("[勿删]ACME定时强制更新")
        self.assertNotIn("[勿删]", name_acme)
        self.assertTrue(len(name_acme) > 0)

        # OP 防火墙
        name_waf = cron_inst.humanTaskName("[勿删]御风OP防火墙后台任务")
        self.assertNotIn("[勿删]", name_waf)
        self.assertTrue(len(name_waf) > 0)

        # 备份数据库
        name_db = cron_inst.humanTaskName("备份数据库[ALL]")
        self.assertIn("[ALL]", name_db)

        # 备份网站
        name_site = cron_inst.humanTaskName("备份网站[ALL]")
        self.assertIn("[ALL]", name_site)

        # 释放内存
        name_mem = cron_inst.humanTaskName("释放内存")
        self.assertTrue(len(name_mem) > 0)

        # 检查网站是否正常
        name_chk = cron_inst.humanTaskName("检查网站是否正常")
        self.assertTrue(len(name_chk) > 0)

        # 验证 getCrontabHuman 中输出包含 name_display 字段
        dummy_list = [{'id': 1, 'name': '[勿删]ACME定时强制更新', 'type': 'day', 'where_hour': '4', 'where_minute': '15', 'echo': 'dummy'}]
        human_res = cron_inst.getCrontabHuman(dummy_list)
        self.assertEqual(len(human_res), 1)
        self.assertIn('name_display', human_res[0])
        self.assertNotIn('[勿删]', human_res[0]['name_display'])


if __name__ == '__main__':
    unittest.main()
