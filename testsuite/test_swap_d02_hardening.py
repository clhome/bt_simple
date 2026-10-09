# coding: utf-8
r"""D02 swap 回归守卫（第二轮 49 模块真机功能测试暴露的缺陷）。

被测面 `plugins/swap/`（破坏性/持久化语义模块：dd 建 swapfile + mkswap + swapon /
swapoff + systemd unit）。真机 Debian 12（MemTotal 7938MB，既有生产 swap：
`/dev/sda3` 分区 + 本模块的 `/www/server/swap/swapfile` 1024MB）实测结论，
每条都先复现、再修、再复验：

1. **假成功（真机已复现）**：`changeSwap` 先 `swapOp('stop')` 再
   `dd && mkswap && chmod`，**完全不看命令退出码**，然后 `swapOp('start')`
   的结果也丢弃，最后**无条件** return `status:true, "修改成功：已成功挂载 X MB…"`。
   真机用 `chattr +i` 让 dd/mkswap 必然 EPERM：
     * HTTP `func=change_swap&args={"size":"128"}` →
       `{"status": true, "msg": "修改成功：已成功挂载 128 MB 专属虚拟内存文件！"}`；
     * 而同一时刻 `/proc/swaps` 里仍是 `1048572` kB（1024MB）、文件仍是 1073741824 字节。
   更糟的是旧顺序「先 swapoff 再 dd」：dd 一旦失败（磁盘满/权限），结果是
   **原有 swap 已停 + 新 swap 没建 + 依旧回成功**。
   修复：先在同目录建 `.yfnew` 临时文件（dd/mkswap/chmod 逐步判退出码）→ 确认
   原有 swap 真停 → `os.replace` 换入 → 启用后**回读 `/proc/swaps` 校验容量**，
   对不上即回滚旧文件；任一步失败都如实报错且不动原有 swap。

2. **`int(size)` 裸调用 → HTTP 500 + traceback 外泄**：`args={"size":null}` 与
   `args={"size":[1,2]}`（JSON 合法但非标量）抛 `TypeError`。
   修复：先判类型（bool/非 int/str 直接拒绝），`int()` 同时捕获 TypeError/ValueError。

3. **`func=conf` 调未定义的 `getConf()` → NameError + traceback 外泄**：
   `__main__` 里有 `elif func == 'conf': print(getConf())`，而本插件没有 `getConf`。
   修复：删掉这个死分支（插件本就无独立配置文件，落到通用 `error` 分支）。

4. **`status()` 用「路径是 /proc/swaps 文本的子串」判断**：与本次新增的
   `.yfold`/`.yfnew` 兄弟文件、或名为 `swapfile2` 的文件会互相误命中（假 start）。
   修复：`getSwappedKb()` 按 Filename 列**整列相等**解析，并读取容量用于回读校验。

5. **`install.sh` 用 `else` 当卸载兜底**：`bash install.sh`（无参）或任何手误参数
   都会 swapoff + `systemctl disable swap` + `rm -rf ${serverPath}/swap`；
   且安装分支里 dd/mkswap/swapon 的失败全不看 → 磁盘满也报「安装完成」。
   另 `$sysName` 不是 lib.sh 提供的变量（恒为空），Darwin 判断永远为假。
   修复：显式 `install`/`uninstall` 分支 + 未知参数报用法 `exit 1`；
   dd/mkswap/swapon 判退出码；改用 `$SYSOS`。

6. **前端 `$.post` 缺 `.fail()` → 遮罩卡死**：`submitSwap()` 用
   `layer.msg(..., {time: 0, shade: [0.5,'#000']})` 做全屏阻断遮罩，但请求 500/断连
   时无处 `layer.close`，遮罩永久留在页面上；`JSON.parse(data.data)` 也无保护。
   且后端中文 msg 未过 `pt()`（六语言词条已存在却用不上）。
   修复：补 `.fail()`、`JSON.parse` try/catch、成功文案用 `pt()` 词条拼接、
   失败明细经 `YfI18n.escapeHtml` 转义后展示。

断言策略：被测函数全部在**桩 yf + 内存文件系统**（记录型 shell，含退出码与
`/proc/swaps` 状态仿真）下跑真实源码，不碰宿主机；结构性断言用 `ast`/源码文本
（抗「注释或 `if False:` 蒙混」）。可用 `YF_D02_PLUGIN_DIR` 指向另一份插件源码，
用于把修复回退后验证用例变红（变异自证）。
"""
import ast
import collections
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN_SRC = os.environ.get('YF_D02_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'swap')

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'swap.js')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANG_DIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

SERVER_DIR = '/www/server'
SWAP_DIR = SERVER_DIR + '/swap'
LIVE_FILE = SWAP_DIR + '/swapfile'
NEW_FILE = LIVE_FILE + '.yfnew'
OLD_FILE = LIVE_FILE + '.yfold'
PROC_SWAPS = '/proc/swaps'

#: 本轮新增的后端/前端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['请求失败', '虚拟内存文件创建失败！', '虚拟内存工作目录创建失败！',
                '磁盘剩余空间不足，无法创建虚拟内存文件！', '虚拟内存变更未生效，已还原原有配置！']
SWAPS_HEADER = 'Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n'


def _load_index():
    """按源码文件加载插件模块（不复用 sys.modules，保持每个用例互不串台）。"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('swap_index_guard', IDX)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    finally:
        # 插件为兼容历史会把 cwd 切到 web/，测试进程要留在原处
        os.chdir(cwd)
    return mod


class FsStub(object):
    """内存文件系统：text=文本文件内容，bins=二进制文件字节数（swapfile 只关心大小）。"""

    def __init__(self):
        self.text = {}
        self.bins = {}
        self.dirs = set()


class FakeOsPath(object):
    def __init__(self, fs):
        self.fs = fs

    def exists(self, p):
        return p in self.fs.text or p in self.fs.bins

    def isdir(self, p):
        return p in self.fs.dirs

    def getsize(self, p):
        if p in self.fs.bins:
            return self.fs.bins[p]
        if p in self.fs.text:
            return len(self.fs.text[p].encode('utf-8'))
        raise OSError('ENOENT: ' + p)


class FakeOs(object):
    def __init__(self, fs):
        self.fs = fs
        self.path = FakeOsPath(fs)

    def makedirs(self, p, **kw):
        if self.path.exists(p):
            raise OSError('EEXIST: ' + p)
        self.fs.dirs.add(p)

    def mkdir(self, p, mode=None):
        if self.path.exists(p):
            raise OSError('EEXIST: ' + p)
        self.fs.dirs.add(p)

    def remove(self, p):
        if p in self.fs.text:
            del self.fs.text[p]
        elif p in self.fs.bins:
            del self.fs.bins[p]
        else:
            raise OSError('ENOENT: ' + p)

    def replace(self, src, dst):
        if src in self.fs.text:
            self.fs.text[dst] = self.fs.text.pop(src)
        elif src in self.fs.bins:
            self.fs.bins[dst] = self.fs.bins.pop(src)
        else:
            raise OSError('ENOENT: ' + src)


class FakeIo(object):
    def __init__(self, fs):
        self.fs = fs

    def open(self, path, *a, **kw):
        if path in self.fs.text:
            return io.StringIO(self.fs.text[path])
        raise IOError('ENOENT: ' + path)


class FakeShutil(object):
    def __init__(self, free_mb=20000):
        self.free_mb = free_mb

    def disk_usage(self, path):
        usage = collections.namedtuple('usage', 'total used free')
        return usage(0, 0, self.free_mb * 1024 * 1024)


class YfStub(object):
    """记录型 yf 桩：内存文件系统 + 记录的命令（含退出码）。"""

    def __init__(self):
        self.plugin_root = os.path.dirname(PLUGIN_SRC)
        self.writes = []
        self.cmds = []
        self.rc_by_prefix = {}
        self.on_cmd = None

    def readFile(self, path):
        if path in self.fs.text:
            return self.fs.text[path]
        return False

    def writeFile(self, path, content, mode='w+'):
        self.writes.append((path, content))
        self.fs.text[path] = content
        return True

    def execShell(self, cmd, cwd=None, timeout=None, shell=True):
        self.cmds.append(cmd)
        if cmd == 'cat /proc/swaps':
            return (self.fs.text.get(PROC_SWAPS, ''), '')
        rc = self._rc(cmd)
        if self.on_cmd is not None:
            self.on_cmd(cmd, rc)
        return ('', '' if rc == 0 else 'stub failure')

    def execShellRc(self, cmd, cwd=None, timeout=None, shell=True):
        self.cmds.append(cmd)
        rc = self._rc(cmd)
        if self.on_cmd is not None:
            self.on_cmd(cmd, rc)
        return (rc, '', '' if rc == 0 else 'stub failure')

    def _rc(self, cmd):
        for prefix, val in self.rc_by_prefix.items():
            if cmd.startswith(prefix):
                return val
        return 0

    def shlexQuote(self, s):
        return shlex.quote(str(s))

    def returnJson(self, status, msg, data=None, *args):
        return json.dumps({'status': status, 'msg': msg, 'data': data})

    def isAppleSystem(self):
        return False

    def getPanelDir(self):
        return '/www/server/yufeng_panel'

    def getPluginDir(self):
        # 插件自己的 getPluginDir() = yf.getPluginDir() + '/' + 插件名
        return self.plugin_root

    def getServerDir(self):
        return SERVER_DIR

    def systemdCfgDir(self):
        return '/nonexistent-yf-d02-systemd'


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = _load_index()
        self._argv = sys.argv
        self.fs = FsStub()
        self.stub = YfStub()
        self.stub.fs = self.fs
        self.fs.dirs.add(SWAP_DIR)
        # 真机开工态：既有 1024MB swapfile 处于挂载状态
        self.fs.bins[LIVE_FILE] = 1024 * 1024 * 1024
        self.fs.text[PROC_SWAPS] = SWAPS_HEADER + '%s\tfile\t1048572\t0\t-3\n' % LIVE_FILE
        # 插件模板（真源码，从磁盘读；initDreplace 会据此生成 init.d 脚本）
        for tpl in ('init.d/swap.tpl', 'init.d/swap.service.tpl'):
            key = '%s/swap/%s' % (os.path.dirname(PLUGIN_SRC), tpl)
            self.fs.text[key] = io.open(os.path.join(PLUGIN_SRC, *tpl.split('/')),
                                        encoding='utf-8').read()
        # os / io / shutil 三个系统面全部换成内存桩，避免测试碰宿主机
        self.mod.yf = self.stub
        self.mod.os = FakeOs(self.fs)
        self.mod.io = FakeIo(self.fs)
        self.mod.shutil = FakeShutil()
        self.stub.on_cmd = self.emulate_system

    def tearDown(self):
        sys.argv = self._argv

    # --- 系统仿真：systemctl swap / swapon / swapoff / dd ---
    def emulate_system(self, cmd, rc):
        if rc == 0 and cmd.startswith('systemctl stop swap'):
            self.fs.text[PROC_SWAPS] = SWAPS_HEADER
        elif rc == 0 and cmd.startswith('systemctl start swap'):
            self._mount_current_file()
        elif rc == 0 and cmd.startswith('dd '):
            m = re.match(r'dd if=/dev/zero of=(\S+) bs=1M count=(\d+)', cmd)
            if m:
                self.fs.bins[m.group(1)] = int(m.group(2)) * 1024 * 1024

    def _mount_current_file(self):
        """systemctl start swap 的内核效果：/proc/swaps 出现该文件（真机实测比
        文件大小少 4KB，如 128MB → 131068 kB、1024MB → 1048572 kB）。"""
        if LIVE_FILE in self.fs.bins:
            kb = max(self.fs.bins[LIVE_FILE] // 1024 - 4, 0)
            self.fs.text[PROC_SWAPS] = SWAPS_HEADER + '%s\tfile\t%s\t0\t-3\n' % (LIVE_FILE, kb)
        else:
            self.fs.text[PROC_SWAPS] = SWAPS_HEADER

    def ignored_swapon(self):
        """让 start 变成空操作（模拟「启用了但内核表里还是旧容量」）。"""
        self.emulate_system = lambda cmd, rc: None

    # --- 调用 ---
    def call_change(self, size):
        self.mod.sys.argv = ['index.py', 'change_swap', json.dumps({'size': size})]
        return json.loads(self.mod.changeSwap())

    def assertNeverTouchesLiveFile(self):
        """不变量：dd/mkswap/chmod 绝不能直接作用于正在使用的 swapfile。"""
        for cmd in self.stub.cmds:
            try:
                toks = shlex.split(cmd)
            except ValueError:
                toks = cmd.split()
            self.assertNotIn(LIVE_FILE, toks, cmd)
            for t in toks:
                if t.startswith('of='):
                    self.assertNotEqual(t[3:], LIVE_FILE, cmd)


class TestFalseSuccessRepro(Base):
    """缺陷 1：命令失败仍回成功（真机 chattr +i 已复现）。"""

    def test_01_dd_fail_reports_failure_and_leaves_swap_alone(self):
        self.stub.rc_by_prefix = {'dd ': 1}
        r = self.call_change(128)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '虚拟内存文件创建失败！')
        self.assertIn('stub failure', r['data']['detail'])
        # 原有 swap 完全没被动过：没停过、文件大小没变、仍在 /proc/swaps 里
        self.assertNotIn('systemctl stop swap', self.stub.cmds)
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024)
        self.assertIn(LIVE_FILE, self.fs.text[PROC_SWAPS])
        self.assertNotIn(NEW_FILE, self.fs.bins)
        self.assertNeverTouchesLiveFile()

    def test_02_mkswap_fail_reports_failure_and_cleans_temp(self):
        self.stub.rc_by_prefix = {'mkswap ': 1}
        r = self.call_change(256)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '虚拟内存文件创建失败！')
        self.assertNotIn(NEW_FILE, self.fs.bins, '失败后必须清掉临时文件')
        self.assertNotIn('systemctl stop swap', self.stub.cmds)
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024)

    def test_03_chmod_fail_aborts(self):
        self.stub.rc_by_prefix = {'chmod ': 1}
        r = self.call_change(256)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '虚拟内存文件创建失败！')
        self.assertNotIn(NEW_FILE, self.fs.bins)

    def test_04_insufficient_disk_is_refused_before_any_dd(self):
        self.mod.shutil = FakeShutil(free_mb=512)
        r = self.call_change(1024)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '磁盘剩余空间不足，无法创建虚拟内存文件！')
        self.assertIn('1024', r['data']['detail'])
        self.assertIn('512', r['data']['detail'])
        self.assertEqual([c for c in self.stub.cmds if c.startswith('dd ')], [])
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024)


class TestSwapTransaction(Base):
    """缺陷 1：事务顺序与回读校验。"""

    def test_05_success_path_is_verified_by_proc_swaps(self):
        r = self.call_change(128)
        self.assertTrue(r['status'], r)
        self.assertIn('128', r['msg'])
        self.assertEqual(self.fs.bins[LIVE_FILE], 128 * 1024 * 1024)
        # 临时/回滚副本不留残渣
        self.assertNotIn(NEW_FILE, self.fs.bins)
        self.assertNotIn(OLD_FILE, self.fs.bins)
        # 回读判定确实发生：内核表容量与请求一致
        self.assertIn('131068', self.fs.text[PROC_SWAPS])
        # dd 目标是临时文件，绝不直接覆盖在用的 swapfile
        self.assertTrue(any('of=%s bs=1M count=128' % NEW_FILE in c for c in self.stub.cmds),
                        self.stub.cmds)
        self.assertNeverTouchesLiveFile()

    def test_06_new_file_is_built_before_old_swap_stops(self):
        r = self.call_change(128)
        self.assertTrue(r['status'], r)
        cmds = self.stub.cmds
        i_dd = next(i for i, c in enumerate(cmds) if c.startswith('dd '))
        i_stop = next(i for i, c in enumerate(cmds) if c.startswith('systemctl stop swap'))
        self.assertLess(i_dd, i_stop, '必须先建好新文件再停原有 swap，否则失败即双输：%s' % cmds)

    def test_07_unverified_switch_rolls_back(self):
        real = self.emulate_system

        def broken(cmd, rc):
            # start 后内核表里仍是旧容量（dd 写歪/挂了别的文件）→ 必须回滚
            if cmd.startswith('systemctl start swap') and OLD_FILE in self.fs.bins:
                self.fs.text[PROC_SWAPS] = SWAPS_HEADER + '%s\tfile\t1048572\t0\t-3\n' % LIVE_FILE
            else:
                real(cmd, rc)

        self.stub.on_cmd = broken
        r = self.call_change(128)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '虚拟内存变更未生效，已还原原有配置！')
        self.assertIn('128', r['data']['detail'])
        # 回滚：原有 1024MB swapfile 归位并重新挂载
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024)
        self.assertIn(LIVE_FILE, self.fs.text[PROC_SWAPS])
        self.assertIn('1048572', self.fs.text[PROC_SWAPS])

    def test_08_stop_failure_aborts_without_replacing(self):
        self.stub.on_cmd = lambda cmd, rc: None  # swapoff 不生效：文件一直留在内核表
        r = self.call_change(128)
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '虚拟内存变更未生效，已还原原有配置！')
        self.assertIn('停用失败', r['data']['detail'])
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024)
        self.assertNotIn(NEW_FILE, self.fs.bins)


class TestArgumentRobustness(Base):
    """缺陷 2：非标量/非法 size 必须回错误 JSON，绝不能 traceback。"""

    def test_09_bad_sizes_return_json_error(self):
        cases = ['abc', '50', '99999', '', '12.5', '1e3', None, [1, 2], {'a': 1}, True, 100.5]
        for size in cases:
            r = self.call_change(size)
            self.assertFalse(r['status'], (size, r))
            self.assertIn(r['msg'], ['容量大小必须为纯正整数！', '容量大小不合法！范围应在 100MB - 32768MB 之间。'],
                          (size, r))
        self.assertEqual(self.fs.bins[LIVE_FILE], 1024 * 1024 * 1024, '非法入参不得改动系统')

    def test_10_valid_numeric_strings_are_accepted(self):
        for size in ('128', 128, ' 256 '):
            r = self.call_change(size)
            self.assertTrue(r['status'], (size, r))

    def test_11_non_dict_args_falls_back_to_missing_param(self):
        # 旧版对 args='[]' 只会给出「缺少必要参数」，不能 IndexError/KeyError
        self.mod.sys.argv = ['index.py', 'change_swap', '[]']
        r = json.loads(self.mod.changeSwap())
        self.assertFalse(r['status'], r)
        self.assertIn('缺少必要参数', r['msg'])
        self.mod.sys.argv = ['index.py', 'change_swap', 'null']
        r = json.loads(self.mod.changeSwap())
        self.assertFalse(r['status'], r)

    def test_12_shell_metachars_cannot_reach_shell(self):
        for size in ('128; touch /root/PWNED', '128 && rm -rf /', '128\n256', "128' || id"):
            r = self.call_change(size)
            self.assertFalse(r['status'], (size, r))
        for cmd in self.stub.cmds:
            self.assertNotIn('PWNED', cmd)
            self.assertNotIn('rm -rf', cmd)


class TestProcSwapsParsing(Base):
    """缺陷 4：状态判定必须整列比对，不能子串命中。"""

    def test_13_status_start_on_exact_row(self):
        self.assertEqual(self.mod.status(), 'start')
        self.assertEqual(self.mod.getSwappedKb(), 1048572)

    def test_14_status_stop_when_only_sibling_files_present(self):
        # 兄弟文件（本次新增的 .yfold/.yfnew）与 swapfile2 都不能算「本插件 swap 已挂载」
        self.fs.text[PROC_SWAPS] = (SWAPS_HEADER
                                    + '%s\tfile\t1048572\t0\t-3\n' % OLD_FILE
                                    + '%s2\tfile\t1024\t0\t-3\n' % LIVE_FILE)
        self.assertEqual(self.mod.status(), 'stop')
        self.assertIsNone(self.mod.getSwappedKb())

    def test_15_status_stop_when_file_missing(self):
        del self.fs.bins[LIVE_FILE]
        self.assertEqual(self.mod.status(), 'stop')

    def test_16_malformed_row_does_not_crash(self):
        self.fs.text[PROC_SWAPS] = SWAPS_HEADER + '%s\tfile\t\n' % LIVE_FILE
        self.assertIsNone(self.mod.getSwappedKb())
        self.assertEqual(self.mod.status(), 'stop')

    def test_17_proc_swaps_read_failure_falls_back_to_cat(self):
        self.mod.io = FakeIo(FsStub())  # io.open 抛错 → 回落 yf.execShell('cat /proc/swaps')
        self.assertEqual(self.mod.getSwappedKb(), 1048572)


class TestSourceStructure(Base):
    """结构性断言：抗「注释/if False:」蒙混。"""

    def test_18_no_undefined_getconf_branch(self):
        src = io.open(IDX, encoding='utf-8').read()
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn('getConf', names, 'func=conf 调未定义的 getConf() 会 NameError 并把 traceback 外泄')

    def test_19_change_swap_uses_rc_and_quoted_temp_path(self):
        src = io.open(IDX, encoding='utf-8').read()
        body = src.split('def changeSwap():', 1)[1]
        self.assertIn('execShellRc', body, '建文件/格式化必须判退出码')
        self.assertNotIn('execShell(cmd', body, '旧的合并 shell 链（不看退出码）必须移除')
        self.assertIn('yf.shlexQuote', body, '路径必须转义后再拼 shell')
        self.assertIn('getSwappedKb', body, '启用后必须回读 /proc/swaps 校验')
        self.assertIn("'.yfnew'", src)
        self.assertIn('os.replace', body, '换入必须原子替换')

    def test_20_main_dispatch_never_raises(self):
        """真机跑一遍分派（真机 Python 3.11/本地同源）：conf 不得再抛 NameError。"""
        for func in ('conf', 'status'):
            p = subprocess.run([sys.executable, IDX, func], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            err = p.stderr.decode('utf-8', 'replace')
            self.assertEqual(p.returncode, 0, (func, err))
            self.assertNotIn('Traceback', err, (func, err))
            self.assertNotIn('NameError', err, (func, err))


class TestInstallSh(Base):
    def test_21_install_sh_has_explicit_action_branches(self):
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        self.assertIn("'install')", sh)
        self.assertIn("'uninstall')", sh)
        self.assertIn('usage: $0 install|uninstall', sh)
        self.assertNotIn('Uninstall_swap\nfi', sh)
        # 旧版把 else 当卸载兜底：无参 = swapoff + disable + rm -rf
        self.assertNotRegex(sh, r'else\s*\n\s*Uninstall_swap')

    def test_22_install_sh_no_undefined_sysname(self):
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        self.assertNotIn('$sysName', sh)
        self.assertIn('SYSOS', sh)

    def test_23_install_sh_checks_each_step(self):
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        self.assertIn('if ! dd ', sh)
        self.assertIn('if ! mkswap ', sh)
        self.assertIn('if ! swapon ', sh)
        self.assertIn('exit 1', sh)

    def test_24_install_sh_syntax_ok(self):
        # 从 stdin 送入 bash -n：避开 Windows 路径在 MSYS/WSL bash 下的转换问题
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        p = subprocess.run(['bash', '-n'], input=sh.encode('utf-8'),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 0, p.stderr)


class TestFrontendAndLang(Base):
    def test_25_js_closes_overlay_on_failure(self):
        js = io.open(JS, encoding='utf-8').read()
        self.assertIn(".fail(function", js, '缺 .fail() 时 500 会把 time:0 全屏遮罩永久留在页面')
        self.assertIn("layer.close(loadT)", js)
        self.assertNotIn('layer.msg(rdata.msg', js, '后端 msg 必须过 pt() 且成功文案由词条拼接')
        self.assertIn("pt('修改成功：已成功挂载')", js)

    def test_26_js_guards_json_parse_and_escapes_detail(self):
        js = io.open(JS, encoding='utf-8').read()
        self.assertEqual(js.count('JSON.parse(data.data)'), 2, '两处 JSON.parse 都必须包在 try 里')
        self.assertEqual(js.count('try {'), 2)
        self.assertIn('YfI18n.escapeHtml(String(rdata.data.detail))', js)

    def test_27_lang_files_aligned_and_translated(self):
        data = {}
        for lg in LANGS:
            with io.open(os.path.join(LANG_DIR, '%s.json' % lg), encoding='utf-8') as f:
                data[lg] = json.load(f)
        keys = set(data['zh-CN'])
        for lg in LANGS:
            self.assertEqual(set(data[lg]), keys, '%s 语言包键集合与 zh-CN 不一致' % lg)
            for k in NEW_MSG_KEYS:
                self.assertIn(k, data[lg], '%s 缺少词条 %s' % (lg, k))
                self.assertTrue(data[lg][k].strip(), '%s 的 %s 译文为空' % (lg, k))
        for lg in ('de', 'fr', 'it'):
            for k in NEW_MSG_KEYS:
                self.assertIsNone(re.search(r'[\u4e00-\u9fa5]', data[lg][k]),
                                  '%s 的 %s 未翻译：%s' % (lg, k, data[lg][k]))
        self.assertIn('swap', data['en']['虚拟内存文件创建失败！'].lower())


if __name__ == '__main__':
    unittest.main()
