# coding:utf-8
import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# 确保导入 web 目录
panel_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(panel_dir, 'web'))

# 优雅 mock 缺失模块，确保自包含运行
if 'flask' not in sys.modules:
    mock_flask = MagicMock()
    sys.modules['flask'] = mock_flask

if 'thisdb' not in sys.modules:
    sys.modules['thisdb'] = MagicMock()

import core.yf as yf
import core.db as db

# 注意：本模块**不能**用 `_isolation.isolate()` —— 它的
# `test_01_path_anchor_no_drift` 断言的正是 `getPanelDir()` 的**真实锚点**
# （仓库根目录），重定向到临时区会让该断言必然失败。
# 好在它本来开销就不大（未被门禁的 ⚑ 点名）。

class TestP2DeepRefine(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_path_anchor_no_drift(self):
        """测试 Task 149: 根目录物理绝对路径锚定，杜绝 os.chdir() 漂移脱轨"""
        original_cwd = os.getcwd()
        panel_root = yf.getPanelDir()
        self.assertTrue(os.path.isabs(panel_root), "getPanelDir 必须是绝对路径")
        self.assertTrue(os.path.exists(os.path.join(panel_root, 'web')), "根目录下应包含 web 目录")
        
        # 测试 db.getPanelDir() 是否同步
        self.assertEqual(panel_root, db.getPanelDir())

        # 改变当前工作目录，验证 yf 路径不会随 cwd 漂移
        try:
            os.chdir(self.test_dir)
            self.assertEqual(yf.getPanelDir(), panel_root, "chdir 之后 getPanelDir 绝不能漂移脱轨")
            self.assertEqual(yf.getRunDir(), panel_root, "chdir 之后 getRunDir 绝不能漂移脱轨")
            self.assertEqual(yf.getRootDir(), panel_root, "chdir 之后 getRootDir 绝不能漂移脱轨")
            self.assertEqual(
                os.path.normpath(yf.getPanelDataDir()),
                os.path.normpath(os.path.join(panel_root, 'data'))
            )
        finally:
            os.chdir(original_cwd)

    def test_02_get_client_ip_proxy_and_spoof_defense(self):
        """测试 Task 150: 反代真实 IP 识别与防伪造、防误封 127.0.0.1"""
        import flask
        
        # 1. 直接公网 IP 访问（如 114.114.114.114）：伪造 X-Forwarded-For 应当被忽略，必须返回公网 remote_addr
        mock_req1 = MagicMock()
        mock_req1.remote_addr = '114.114.114.114'
        mock_req1.headers = {'X-Forwarded-For': '10.0.0.1, 1.1.1.1'}
        with patch('flask.request', mock_req1):
            ip = yf.getClientIp()
            self.assertEqual(ip, '114.114.114.114', "非代理直连时，必须以 remote_addr 为准，防御伪造头")

        # 2. 本地回环 127.0.0.1 反代（Nginx/OpenResty）：安全提取合法 X-Forwarded-For
        mock_req2 = MagicMock()
        mock_req2.remote_addr = '127.0.0.1'
        mock_req2.headers = {'X-Forwarded-For': '119.29.29.29, 127.0.0.1'}
        with patch('flask.request', mock_req2):
            ip = yf.getClientIp()
            self.assertEqual(ip, '119.29.29.29', "受信任回环代理下，应准确穿透提取真实客户端 IP")

        # 3. 私网 192.168.1.10 反代：安全提取 X-Real-IP
        mock_req3 = MagicMock()
        mock_req3.remote_addr = '192.168.1.10'
        mock_req3.headers = {'X-Real-IP': '119.29.29.29'}
        with patch('flask.request', mock_req3):
            ip = yf.getClientIp()
            self.assertEqual(ip, '119.29.29.29', "私网反代场景应准确提取 X-Real-IP")

        # 4. 畸变/恶意头输入：防异常注入，安全保底
        mock_req4 = MagicMock()
        mock_req4.remote_addr = '127.0.0.1'
        mock_req4.headers = {'X-Forwarded-For': '../../../etc/passwd'}
        with patch('flask.request', mock_req4):
            ip = yf.getClientIp()
            self.assertEqual(ip, '127.0.0.1', "遇到非法 IP 字符串时应安全保底，不抛异常")

    def test_03_get_last_line_utf8_boundary_and_indentation(self):
        """测试 Task 151: 大日志逆序读取保留缩进且多字节中文不乱码"""
        log_file = os.path.join(self.test_dir, 'test_app.log')
        
        # 构造包含多行缩进、长文本及多字节中文的内容
        content_lines = []
        for i in range(100):
            # 每行包含前导空格缩进和中文
            content_lines.append(f"    [INFO 2026-09-07] 记录项 {i}: 系统运行正常，御风面板高效调度中 🚀✨")
        content_lines.append("  Traceback (most recent call last):")
        content_lines.append('    File "app.py", line 42, in <module>')
        content_lines.append("      raise ValueError('测试中文异常信息')")
        
        raw_text = "\n".join(content_lines) + "\n"
        with open(log_file, 'wb') as fp:
            fp.write(raw_text.encode('utf-8'))

        # 读取最后 3 行
        res = yf.getLastLine(log_file, 3)
        res_lines = res.split('\n')
        self.assertEqual(len(res_lines), 3)
        # 验证包含中文且无解码乱码
        self.assertIn('测试中文异常信息', res_lines[2])
        # 验证缩进得到保留（未被过度 strip）
        self.assertTrue(res_lines[2].startswith('      '), "代码前导缩进空格必须保留")
        self.assertTrue(res_lines[1].startswith('    File'), "Traceback 缩进必须保留")

        # 构造超长文件（超过 8192 字节 block_size）测试跨块逆向读取
        large_log = os.path.join(self.test_dir, 'large.log')
        with open(large_log, 'wb') as fp:
            for i in range(500):
                line = f"Line {i:04d}: " + "中文字符测试" * 20 + "\n"
                fp.write(line.encode('utf-8'))
        
        large_res = yf.getLastLine(large_log, 5)
        large_lines = large_res.split('\n')
        self.assertEqual(len(large_lines), 5)
        self.assertIn("Line 0499:", large_lines[-1])
        self.assertIn("Line 0495:", large_lines[0])

    def test_04_site_native_fs_operations(self):
        """测试 Task 152: site.py 证书清理与目录操作原生化且无外部进程"""
        import utils.site as site_mod
        site_obj = site_mod.sites()
        site_obj.sslDir = os.path.join(self.test_dir, 'ssl')
        os.makedirs(site_obj.sslDir, exist_ok=True)

        # 1. 模拟在 ssl 目录下创建证书子目录
        cert_dir = os.path.join(site_obj.sslDir, 'example.com')
        os.makedirs(cert_dir, exist_ok=True)
        dummy_cert = os.path.join(cert_dir, 'fullchain.pem')
        with open(dummy_cert, 'w') as f:
            f.write('CERT CONTENT')

        # 2. 调用 removeCert
        ret = site_obj.removeCert('example.com')
        self.assertTrue(ret.get('status'), "removeCert 返回状态应为 True")
        self.assertFalse(os.path.exists(cert_dir), "证书目录必须被原生 shutil.rmtree 彻底清除")

        # 3. 验证回收站目录创建原生化
        rb = yf.getRecycleBinDir()
        self.assertTrue(os.path.exists(rb), "回收站目录必须存在")

if __name__ == '__main__':
    unittest.main()
