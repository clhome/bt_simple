# coding: utf-8
"""计划任务紧急终止按钮与进程管理回归测试套件。

覆盖：
1. 后端路由 `/crontab/kill_task` 的注册、方法限制与鉴权；
2. 服务层 `findTaskPid`：PID 文件与 `/proc` 进程特征反查双轨机制；
3. 服务层 `killProcessTree` / `killTask`：终止长耗时运行任务、清理 PID 文件、追加终止日志；
4. 任务未运行/非法 ID 的防御性返回；
5. 前端 `crontab.js` 红色紧急终止按钮 DOM、样式与事件绑定断言；
6. 六国多语言语言包 (zh-CN, zh-TW, en, de, fr, it) 词条完整性。
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
web_dir = os.path.join(project_dir, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

CRONTAB_PY = os.path.join(project_dir, 'web', 'utils', 'crontab.py')
ROUTE_PY = os.path.join(project_dir, 'web', 'admin', 'crontab', '__init__.py')
APP_JS = os.path.join(project_dir, 'web', 'static', 'app', 'crontab.js')
LANG_DIR = os.path.join(project_dir, 'web', 'static', 'language')


class TestCrontabKillTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import core.yf as yf
        cls.yf = yf
        from utils.crontab import crontab
        cls.crontab = crontab

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='yf_test_kill_')
        self.orig_server_dir = getattr(self.yf, 'getServerDir', None)
        self.orig_tmp_dir = getattr(self.yf, 'getPanelTmp', None)

        self.server_cron_dir = os.path.join(self.temp_dir, 'server', 'cron')
        self.panel_tmp_dir = os.path.join(self.temp_dir, 'tmp')
        os.makedirs(self.server_cron_dir, exist_ok=True)
        os.makedirs(self.panel_tmp_dir, exist_ok=True)

        self.yf.getServerDir = lambda: os.path.join(self.temp_dir, 'server')
        self.yf.getPanelTmp = lambda: self.panel_tmp_dir

    def tearDown(self):
        if self.orig_server_dir:
            self.yf.getServerDir = self.orig_server_dir
        if self.orig_tmp_dir:
            self.yf.getPanelTmp = self.orig_tmp_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_route_registration_and_auth(self):
        """验证 /crontab/kill_task 路由、方法限制及 @panel_login_required 存在。"""
        with open(ROUTE_PY, 'r', encoding='utf-8') as f:
            code = f.read()

        tree = ast.parse(code, filename=ROUTE_PY)
        found_route = False
        found_login_check = False
        methods_post = False

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'kill_task':
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == 'panel_login_required':
                        found_login_check = True
                    elif isinstance(dec, ast.Call):
                        # blueprint.route(...)
                        dec_repr = ast.unparse(dec) if hasattr(ast, 'unparse') else ''
                        if '/kill_task' in dec_repr:
                            found_route = True
                            if 'POST' in dec_repr:
                                methods_post = True

        self.assertTrue(found_route, "未找到 /kill_task 路由注册")
        self.assertTrue(found_login_check, "kill_task 路由必须具有 @panel_login_required 鉴权守卫")
        self.assertTrue(methods_post, "kill_task 必须限制为 POST 请求")

    def test_02_invalid_cron_id_returns_error(self):
        """传入非法/不存在的任务 ID 时安全返回 param_error，不崩溃。"""
        inst = self.crontab.instance()
        for bad_id in ('', None, '-999', 'not_exist_id'):
            res = inst.killTask(bad_id)
            self.assertIsInstance(res, dict)
            self.assertFalse(res.get('status'), f"非法 ID {bad_id} 应该返回 status=False")
            self.assertIn(res.get('msg'), ('common.param_error', '参数错误'))

    def test_03_task_not_running(self):
        """任务存在但当前没有进程在运行，返回 task_not_running，并清理残留 pid 文件。"""
        inst = self.crontab.instance()
        cron_id = '99991'
        echo = 'mock_echo_not_running_12345678'
        mock_data = {
            'id': cron_id,
            'name': '测试未运行任务',
            'echo': echo
        }

        import thisdb
        orig_getCrond = thisdb.getCrond
        thisdb.getCrond = lambda cid: mock_data if str(cid) == cron_id else None
        try:
            # 制造一个死 PID 的残留文件
            pf = inst._cron_pid_file(cron_id)
            with open(pf, 'w', encoding='utf-8') as f:
                f.write('9999999')  # 不存在的 PID

            res = inst.killTask(cron_id)
            self.assertFalse(res['status'])
            self.assertIn(res['msg'], ('crontab.task_not_running', '任务未在运行或已结束'))
            self.assertFalse(os.path.exists(pf), "死 PID 文件应在检测后被安全清理")
        finally:
            thisdb.getCrond = orig_getCrond

    def test_04_find_and_kill_running_process_via_pid_file(self):
        """模拟长时间运行任务（写 PID 文件），测试精准发现 PID 并杀死进程树。"""
        inst = self.crontab.instance()
        cron_id = '99992'
        echo = 'mock_echo_running_task_abcdef'
        mock_data = {
            'id': cron_id,
            'name': '长时间备份测试任务',
            'echo': echo
        }

        import thisdb
        orig_getCrond = thisdb.getCrond
        thisdb.getCrond = lambda cid: mock_data if str(cid) == cron_id else None

        proc = None
        try:
            # 启动一个带特征命令行子进程（长时间 sleep）
            cmd = [sys.executable, '-c', f'# {echo}\nimport time\ntime.sleep(60)']
            proc = subprocess.Popen(cmd)
            # 确认测试子进程已成功启动
            started = False
            start_deadline = time.time() + 2.0
            while time.time() < start_deadline:
                if self.yf.checkPid(proc.pid):
                    started = True
                    break
                time.sleep(0.05)
            self.assertTrue(started, "测试子进程必须成功启动")

            # 写入 PID 文件
            pf = inst._cron_pid_file(cron_id)
            with open(pf, 'w', encoding='utf-8') as f:
                f.write(str(proc.pid))

            # 验证 findTaskPid 能查到
            found_pid, data = inst.findTaskPid(cron_id)
            self.assertEqual(found_pid, proc.pid)

            # 调用 killTask
            res = inst.killTask(cron_id)
            self.assertTrue(res['status'])
            self.assertEqual(str(res.get('data')), str(proc.pid))
            self.assertIn(str(proc.pid), res.get('msg', ''))

            # 验证进程已被彻底杀死（proc.poll() 负责内核状态收割，checkPid 负责存活校验）
            deadline = time.time() + 2.0
            dead = False
            while time.time() < deadline:
                if proc.poll() is not None or not self.yf.checkPid(proc.pid):
                    dead = True
                    break
                time.sleep(0.1)
            self.assertTrue(dead, f"进程 {proc.pid} 必须被杀死")

            # 验证 PID 文件已被清理
            self.assertFalse(os.path.exists(pf), "PID 文件必须在终止后被删除")

            # 验证日志文件已追加终止信息
            log_file = os.path.join(self.server_cron_dir, echo + '.log')
            self.assertTrue(os.path.exists(log_file), "任务日志文件应记录终止信息")
            with open(log_file, 'r', encoding='utf-8') as lf:
                log_content = lf.read()
            self.assertIn('任务已被手动紧急终止', log_content)
            self.assertIn(str(proc.pid), log_content)
        finally:
            thisdb.getCrond = orig_getCrond
            if proc:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def test_05_find_and_kill_process_via_cmdline_scan(self):
        """当 PID 文件丢失或未写入时，测试通过命令行 echo 特征反查 PID 并杀死。"""
        try:
            import psutil
            has_psutil = True
        except Exception:
            has_psutil = False

        if not os.path.exists('/proc') and not has_psutil:
            self.skipTest("当前环境无 /proc 伪文件系统且未安装 psutil，跳过命令行特征扫描测试")

        inst = self.crontab.instance()
        cron_id = '99993'
        echo = 'unique_echo_for_proc_scan_789xyz'
        mock_data = {
            'id': cron_id,
            'name': '特征反查任务',
            'echo': echo
        }

        import thisdb
        orig_getCrond = thisdb.getCrond
        thisdb.getCrond = lambda cid: mock_data if str(cid) == cron_id else None

        proc = None
        try:
            # 启动包含唯一 echo 特征的进程
            cmd = [sys.executable, '-c', f'# {echo}\nimport time\ntime.sleep(60)']
            proc = subprocess.Popen(cmd)
            # 确认测试子进程已成功启动
            started = False
            start_deadline = time.time() + 2.0
            while time.time() < start_deadline:
                if self.yf.checkPid(proc.pid):
                    started = True
                    break
                time.sleep(0.05)
            self.assertTrue(started, "测试子进程必须成功启动")

            # 不写 PID 文件，验证特征扫描能查到
            found_pid, data = inst.findTaskPid(cron_id)
            self.assertEqual(found_pid, proc.pid)

            # 调用 killTask
            res = inst.killTask(cron_id)
            self.assertTrue(res['status'])
            self.assertEqual(str(res['data']), str(proc.pid))

            # 再次查杀应返回 task_not_running（幂等）
            res2 = inst.killTask(cron_id)
            self.assertFalse(res2['status'])
            self.assertIn(res2['msg'], ('crontab.task_not_running', '任务未在运行或已结束'))
        finally:
            thisdb.getCrond = orig_getCrond
            if proc:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def test_06_frontend_js_kill_button_and_binding(self):
        """验证前端 crontab.js 中包含红色紧急终止按钮、防误触 confirm 与安全事件绑定。"""
        with open(APP_JS, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn('id="cron_log_kill"', js, "日志弹窗内必须包含 id='cron_log_kill' 的终止按钮")
        self.assertIn('btn-danger', js, "紧急终止按钮必须采用红色 (btn-danger) 警示样式")
        self.assertIn("t('crontab.emergency_stop'", js, "按钮文案必须支持国际化 emergency_stop")
        self.assertIn("function killTask(", js, "必须定义 killTask 函数")
        self.assertIn("layer.confirm(", js, "紧急终止必须提供 layer.confirm 二次防误触确认")
        self.assertIn("'/crontab/kill_task'", js, "必须通过 POST 请求调用 /crontab/kill_task 接口")

    def test_07_all_languages_contain_kill_terms(self):
        """断言 zh-CN, zh-TW, en, de, fr, it 6 种语言包均包含所有终止相关词条。"""
        required_keys = [
            'emergency_stop',
            'confirm_emergency_stop',
            'task_not_running',
            'task_terminated_success',
            'task_terminated_failed',
            'terminating_task'
        ]

        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        for lang in langs:
            lang_file = os.path.join(LANG_DIR, lang, 'template.crontab.json')
            self.assertTrue(os.path.exists(lang_file), f"语言文件缺失: {lang_file}")
            with open(lang_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cron_dict = data.get('crontab', {})
            for rk in required_keys:
                self.assertIn(rk, cron_dict, f"语言包 {lang} 缺少必要词条 crontab.{rk}")
                self.assertTrue(bool(cron_dict[rk]), f"语言包 {lang} 词条 crontab.{rk} 不能为空")

    def test_08_process_group_safety_guard(self):
        """验证 killProcessTree 存在防自杀与进程组安全守卫，绝不向当前调用者或父进程组广播信号。"""
        with open(CRONTAB_PY, 'r', encoding='utf-8') as f:
            src = f.read()

        # 源码级防误杀硬断言：必须限制 pgid == main_pid 且排除当前进程组
        self.assertIn('pgid == main_pid', src, "killpg 必须严格限制目标进程为主进程组长，严禁向父进程组广播")
        self.assertIn('pgid != cur_pgrp', src, "killpg 必须显式排除当前进程组，绝不能广播给调用者所在组")

        # 运行时模拟：mock 一个非组长的主进程，断言不会调用 os.killpg
        inst = self.crontab.instance()
        killpg_called = []
        orig_killpg = getattr(os, 'killpg', None)
        try:
            os.killpg = lambda pgid, sig: killpg_called.append((pgid, sig))
            # 模拟 pgid != main_pid 或 pgid == cur_pgrp 的场景
            inst.killProcessTree(9999999)
            self.assertEqual(len(killpg_called), 0, "当目标进程不是独立会话组长时，严禁调用 os.killpg")
        finally:
            if orig_killpg is not None:
                os.killpg = orig_killpg
            elif hasattr(os, 'killpg'):
                delattr(os, 'killpg')


if __name__ == '__main__':
    unittest.main()
