# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）插件运行状态探测与进程检测专项自动化测试套件
验证 yf.checkPid 与 plugin.py 中 checkStatusQuick / checkStatusReal 的鲁棒性与内外一致性
"""
import unittest
import os
import sys
import ast
import tempfile
import shutil
import errno
from unittest.mock import patch, MagicMock

# 优先尝试导入真实的 psutil，若缺失才提供 mock
try:
    import psutil
except ImportError:
    psutil = MagicMock()
    psutil.pid_exists.side_effect = lambda p: p == os.getpid()
    sys.modules['psutil'] = psutil

# 对其他 Web 外部依赖模块进行优雅 mock
for mod in ['flask', 'flask_socketio', 'gevent', 'geventwebsocket', 'thisdb', 'config']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

YF_PY = os.path.join(WEB_DIR, 'core', 'yf.py')
PLUGIN_PY = os.path.join(WEB_DIR, 'utils', 'plugin.py')
REDIS_INDEX_PY = os.path.join(ROOT_DIR, 'plugins', 'redis', 'index.py')


class TestPluginStatusDetection(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='yf_status_test_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_01_encoding_and_lf(self):
        """测试 1: 验证修改的关键文件均为 UTF-8 无 BOM 且使用 LF 换行符"""
        for fpath in [YF_PY, PLUGIN_PY]:
            self.assertTrue(os.path.exists(fpath), f"文件不存在: {fpath}")
            with open(fpath, "rb") as f:
                content = f.read()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"文件 {fpath} 含有 UTF-8 BOM")
            self.assertNotIn(b"\r\n", content, f"文件 {fpath} 含有 CRLF 换行符，必须为 LF")
        print("\n[OK] 测试 1: 核心文件 UTF-8 无 BOM 与 LF 换行符验证通过！")

    def test_02_yf_check_pid_basic(self):
        """测试 2: 验证 yf.checkPid 基本有效性与边界安全防御"""
        import core.yf as yf

        # 1. 验证当前进程 PID 必须存活
        current_pid = os.getpid()
        if isinstance(sys.modules.get('psutil'), MagicMock):
            sys.modules['psutil'].pid_exists.side_effect = lambda p: int(p) == current_pid

        self.assertTrue(yf.checkPid(current_pid), f"当前运行进程 PID={current_pid} 应当被识别为存活")
        self.assertTrue(yf.checkPid(str(current_pid)), "字符串格式 PID 应当被正确转换识别")

        # 2. 验证极大不存在的 PID 判定为假
        fake_pid = 99999999
        self.assertFalse(yf.checkPid(fake_pid), "不存在的超大 PID 应当判定为 False")

        # 3. 验证异常边界输入防崩溃
        self.assertFalse(yf.checkPid(0), "PID=0 应当返回 False")
        self.assertFalse(yf.checkPid(-1), "负数 PID 应当返回 False")
        self.assertFalse(yf.checkPid(""), "空字符串 PID 应当返回 False")
        self.assertFalse(yf.checkPid(None), "None PID 应当返回 False")
        self.assertFalse(yf.checkPid("invalid_str"), "非数字字符串 PID 应当返回 False 且不报错")
        print("[OK] 测试 2: yf.checkPid 基本存活判定与非法输入防崩溃验证通过！")

    def test_03_yf_check_pid_linux_posix_mock(self):
        """测试 3: 模拟 Linux POSIX 环境下 checkPid 的 /proc 与 os.kill 信号分支"""
        import core.yf as yf

        # 模拟 sys.platform == 'linux'
        with patch('sys.platform', 'linux'):
            # 场景 A: /proc/{pid} 存在
            with patch('os.path.exists', side_effect=lambda p: p == '/proc/1234'):
                self.assertTrue(yf.checkPid(1234), "/proc/1234 存在时应返回 True")

            # 场景 B: /proc/{pid} 不存在，但 os.kill(pid, 0) 成功
            with patch('os.path.exists', return_value=False):
                with patch('os.kill', return_value=None):
                    self.assertTrue(yf.checkPid(1234), "os.kill 成功时应返回 True")

            # 场景 C: 遇到 PermissionError (errno.EPERM)，说明是 root 进程，应当判定存活
            with patch('os.path.exists', return_value=False):
                perm_err = OSError()
                perm_err.errno = errno.EPERM
                with patch('os.kill', side_effect=perm_err):
                    self.assertTrue(yf.checkPid(1234), "os.kill 遇到 EPERM 权限不足时说明进程存在，应返回 True")

            # 场景 D: 遇到 ProcessLookupError (errno.ESRCH)，说明无此进程，判定已退出
            with patch('os.path.exists', return_value=False):
                srch_err = OSError()
                srch_err.errno = errno.ESRCH
                with patch('os.kill', side_effect=srch_err):
                    self.assertFalse(yf.checkPid(1234), "os.kill 遇到 ESRCH 时说明进程已死，应返回 False")
        print("[OK] 测试 3: yf.checkPid Linux/POSIX 机制模拟验证通过！")

    def test_04_check_status_quick_fallback_logic(self):
        """测试 4: 验证 checkStatusQuick 在无法确认时返回 None，杜绝阻断兜底降级"""
        from utils.plugin import plugin as YfPlugin
        pg = YfPlugin.instance()

        # 任意未配置快速探测的插件，必须返回 None
        self.assertIsNone(pg.checkStatusQuick('clean'), "未配置快速探测的插件应返回 None")
        self.assertIsNone(pg.checkStatusQuick('demo_plugin'), "未配置快速探测的插件应返回 None")

        # 模拟各核心服务的快速探测：当 PID 文件不存在时，必须返回 None，以便交由官方 status() 兜底
        with patch('core.yf.getServerDir', return_value=self.test_dir):
            self.assertIsNone(pg.checkStatusQuick('openresty'), "PID 不存在时 openresty 快速探测必须返回 None 触发兜底")
            self.assertIsNone(pg.checkStatusQuick('mysql'), "PID 不存在时 mysql 快速探测必须返回 None 触发兜底")
            self.assertIsNone(pg.checkStatusQuick('redis'), "PID 不存在时 redis 快速探测必须返回 None 触发兜底")
            self.assertIsNone(pg.checkStatusQuick('pureftp'), "PID 不存在时 pureftp 快速探测必须返回 None 触发兜底")
            self.assertIsNone(pg.checkStatusQuick('php', '80'), "PID 不存在时 php 快速探测必须返回 None 触发兜底")
        print("[OK] 测试 4: checkStatusQuick 无法确认时统一返回 None 验证通过！")

    def test_05_openresty_quick_and_real_status_alignment(self):
        """测试 5: 验证 OpenResty 真实场景：存活命中快速通道、非标路径与停止状态平滑降级"""
        from utils.plugin import plugin as YfPlugin
        import core.yf as yf
        pg = YfPlugin.instance()

        server_dir = self.test_dir
        nginx_log_dir = os.path.join(server_dir, 'openresty', 'nginx', 'logs')
        os.makedirs(nginx_log_dir, exist_ok=True)
        pid_file = os.path.join(nginx_log_dir, 'nginx.pid')

        # 场景 1: PID 文件存在且进程存活（当前进程PID）
        yf.writeFile(pid_file, str(os.getpid()))
        with patch('core.yf.getServerDir', return_value=server_dir):
            self.assertTrue(pg.checkStatusQuick('openresty'), "有效存活 PID 时快速探测必须直接返回 True")
            info = {'name': 'openresty', 'setup': True, 'setup_version': '1.31.1'}
            self.assertTrue(pg.checkStatusReal(info), "存活状态下 checkStatusReal 必须为 True")

        # 场景 2: PID 文件不存在（例如用户改了路径），快速探测返回 None，回退到 self.run 获取官方状态
        if os.path.exists(pid_file):
            os.remove(pid_file)

        with patch('core.yf.getServerDir', return_value=server_dir):
            self.assertIsNone(pg.checkStatusQuick('openresty'), "PID 文件不存在时快速探测必须返回 None")

            # 模拟 self.run 官方插件返回 'start'（如弹窗内部所示）
            with patch.object(pg, 'run', return_value=('start\n', '')):
                info = {'name': 'openresty', 'setup': True, 'setup_version': '1.31.1'}
                self.assertTrue(pg.checkStatusReal(info), "降级到 self.run 返回 start 时，外部必须与内部一致返回 True")

            # 模拟 self.run 官方插件返回 'stop'（真实已停止）
            with patch.object(pg, 'run', return_value=('stop\n', '')):
                info = {'name': 'openresty', 'setup': True, 'setup_version': '1.31.1'}
                self.assertFalse(pg.checkStatusReal(info), "降级到 self.run 返回 stop 时，外部必须准确返回 False")

        # 场景 3: 未安装插件
        info_uninstalled = {'name': 'openresty', 'setup': False}
        self.assertFalse(pg.checkStatusReal(info_uninstalled), "未安装插件直接返回 False")
        print("[OK] 测试 5: OpenResty 快速命中、降级回退与内外状态 100% 对齐验证通过！")


if __name__ == '__main__':
    unittest.main()
