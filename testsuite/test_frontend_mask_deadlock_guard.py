#!/usr/bin/env python3
# coding:utf-8
"""前端「遮罩死锁」守卫（A/B 组交叉核对发现的系统性缺陷族）。

缺陷机制：`var loadT = layer.msg(..., {icon: 16, time: 0})` 捕获遮罩句柄后发起**裸**
`$.post`/`$.ajax`，成功回调里 `layer.close(loadT)`，但**没有 `.fail()`** —— 请求返回
500 或网络中断时成功回调永不执行，遮罩（`time: 0` = 永不自动关闭）**永久卡死**。

范围说明（有意收窄，勿扩面）：
  * 本守卫覆盖**本轮确认并修复**的三个模块：`plugins/mariadb`、`plugins/redis`、
    `plugins/valkey`。
  * 全仓其余「裸 ajax 无 `.fail()`」存量（约 200 处，多数可被后续 `layer.closeAll()`
    恢复）按 task.md §4「系统性残留」登记，**不在此守卫断言范围内** —— 否则会把
    存量一次性拉红，门禁失去意义。
  * `YfPlugin.createApi`（`web/static/app/plugin_api.js::_basePost`）自带 `.fail()` +
    关遮罩，因此所有 `api.post(...)` 调用点天然安全（见 test_04）。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MASK_VAR = re.compile(r'\bvar\s+([A-Za-z_$][\w$]*)\s*=\s*layer\.(?:msg|load)\s*\(')
RAW_AJAX = re.compile(r'\$\.(?:post|get|ajax)\s*\(')
FAIL = re.compile(r'\.fail\s*\(')

#: 遮罩变量声明后向后找裸 ajax 的行数窗口（redis/valkey 实测间隔 12 行）
BACK_WINDOW = 20
#: 裸 ajax 调用后向前找 `.fail(` 的行数窗口
FWD_WINDOW = 15

GUARDED_FILES = (
    'plugins/mariadb/js/mariadb.js',
    'plugins/redis/js/redis.js',
    'plugins/valkey/js/valkey.js',
)


def deadlock_sites(src):
    """返回 [(行号, 遮罩变量名)]：捕获遮罩后紧跟的裸 ajax 未挂 `.fail()`。"""
    lines = src.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = MASK_VAR.search(line)
        if not m:
            continue
        for j in range(i + 1, min(i + BACK_WINDOW, len(lines))):
            if not RAW_AJAX.search(lines[j]):
                continue
            fwd = '\n'.join(lines[j:j + FWD_WINDOW])
            if not FAIL.search(fwd):
                out.append((j + 1, m.group(1)))
            break
    return out


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8', errors='replace')


class TestMaskDeadlockGuard(unittest.TestCase):

    def test_01_mariadb_no_mask_deadlock(self):
        bad = deadlock_sites(read('plugins/mariadb/js/mariadb.js'))
        self.assertEqual([], bad, 'mariadb.js 遮罩后裸 ajax 缺 .fail()：%r' % bad)

    def test_02_redis_no_mask_deadlock(self):
        bad = deadlock_sites(read('plugins/redis/js/redis.js'))
        self.assertEqual([], bad, 'redis.js 遮罩后裸 ajax 缺 .fail()：%r' % bad)

    def test_03_valkey_no_mask_deadlock(self):
        bad = deadlock_sites(read('plugins/valkey/js/valkey.js'))
        self.assertEqual([], bad, 'valkey.js 遮罩后裸 ajax 缺 .fail()：%r' % bad)

    def test_04_shared_api_keeps_fail_handler(self):
        """`YfPlugin.createApi` 的 `_basePost` 必须保留 `.fail()`（api.post 调用点的安全来源）。"""
        src = read('web/static/app/plugin_api.js')
        self.assertIn('function _basePost', src)
        seg = src[src.index('function _basePost'):]
        seg = seg[:seg.index('\n        }') if '\n        }' in seg else len(seg)]
        self.assertRegex(seg, r"\.fail\s*\(")

    def test_05_mariadb_escapes_server_config_values(self):
        """服务端配置值（datadir/port）拼进 HTML 属性前必须过 `maEsc`。"""
        src = read('plugins/mariadb/js/mariadb.js')
        self.assertIn('function maEsc(', src)
        self.assertNotRegex(src, r'value="\'\s*\+\s*data\.data\s*\+\s*\'"')
        self.assertNotRegex(src, r'value="\'\s*\+\s*rdata\.datadir\s*\+\s*\'"')
        self.assertRegex(src, r"maEsc\(data\.data\)")
        self.assertRegex(src, r"maEsc\(rdata\.datadir\)")

    def test_06_scanner_known_answers(self):
        """检测器自证：缺 .fail() 的必须被抓，挂了 .fail() 的必须放行。"""
        bad_sample = (
            "function f(){\n"
            "  var loadT = layer.msg('x', { icon: 16, time: 0 });\n"
            "  $.post('/a', {}, function(d){ layer.close(loadT); });\n"
            "}\n"
        )
        ok_sample = (
            "function f(){\n"
            "  var loadT = layer.msg('x', { icon: 16, time: 0 });\n"
            "  $.post('/a', {}, function(d){ layer.close(loadT); }).fail(function(){ layer.close(loadT); });\n"
            "}\n"
        )
        no_mask_sample = (
            "function f(){\n"
            "  $.post('/a', {}, function(d){ layer.closeAll(); });\n"
            "}\n"
        )
        self.assertEqual(1, len(deadlock_sites(bad_sample)), '缺 .fail() 未被抓出')
        self.assertEqual([], deadlock_sites(ok_sample), '已挂 .fail() 被误报')
        self.assertEqual([], deadlock_sites(no_mask_sample), '无遮罩变量被误报')

    def test_07_guarded_files_exist(self):
        for rel in GUARDED_FILES:
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
