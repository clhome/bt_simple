import sys
import os
import time
import unittest

web_dir = os.path.abspath('web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

import core.yf as yf
from core.i18n import t as _t

class TestPluginRunSpeed(unittest.TestCase):

    def test_return_data_fast_path(self):
        """验证 returnData 与 returnJson 对空消息与纯数据的极速短路性能"""
        t0 = time.time()
        for _ in range(10000):
            r = yf.returnData(True, "", "some_data")
        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000
        print(f"\n[PERF] 10,000次 returnData 空消息穿透耗时: {elapsed_ms:.2f} ms (单次: {elapsed_ms/10000:.4f} ms)")
        self.assertLess(elapsed_ms, 50.0) # 1万次小于50ms
        self.assertTrue(r['status'])
        self.assertEqual(r['data'], "some_data")

    def test_sanitize_cmd_fast_path(self):
        """验证 sanitizeCmdScripts 针对无脚本命令的零延迟穿透"""
        cmd = "cd /www/server/panel && python3 plugins/docker/index.py status"
        # 预热一次进入缓存
        yf.sanitizeCmdScripts(cmd)
        
        t0 = time.time()
        for _ in range(5000):
            yf.sanitizeCmdScripts(cmd)
        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000
        print(f"[PERF] 5,000次 sanitizeCmdScripts 缓存穿透耗时: {elapsed_ms:.2f} ms (单次: {elapsed_ms/5000:.4f} ms)")
        self.assertLess(elapsed_ms, 60.0)

    def test_subprocess_avoid_template_json(self):
        """验证在子进程环境（无 Web 上下文）中查询 k_ 散列 key 不会加载巨型 template.json"""
        t0 = time.time()
        # 模拟插件子进程调用
        res = _t("k_8c718510")
        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000
        print(f"[PERF] 插件私有散列 key 0ms 短路耗时: {elapsed_ms:.4f} ms")
        self.assertLess(elapsed_ms, 1.0)
        self.assertEqual(res, "k_8c718510")

if __name__ == '__main__':
    unittest.main()
