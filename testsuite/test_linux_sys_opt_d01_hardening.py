# coding: utf-8
r"""D01 linux_sys_opt 回归守卫（第二轮 49 模块真机功能测试暴露的缺陷）。

被测面 `plugins/linux_sys_opt/`（系统调优类：写 /etc/sysctl.d/99-yufeng-server.conf +
THP sysfs + systemd oneshot unit）。真机 Debian 12（MemTotal 7938MB，落在 8G 档）
实测结论 —— 每条都先复现、再修、再复验：

1. **「已成功生效」是假的（假成功 + 与自己的状态页自相矛盾）**：
   procps 的 `sysctl --system` 把 `/etc/sysctl.conf` 放在**最后**读取（真机确认：
   tail 输出末行 `net.core.somaxconn = 1024` 来自 /etc/sysctl.conf），于是本插件的
   drop-in（写 4096）被覆盖。真机两条证据：
     * 修复前 HTTP `func=apply_opt` → `{"status": true, "msg": "全平台内核优化配置已成功生效！"}`
       而 `sysctl -n net.core.somaxconn` 仍是 **1024**（本插件自己的状态页据此判 ✗）；
     * `/etc/sysctl.d/99-yufeng-server.conf` 内容 `net.core.somaxconn = 4096` 与
       运行值 1024 长期并存（文件 9月14日 写入、机器已重启过）。
   修复：`--system` 之后**再显式套用一次本文件**（`sysctl -p <conf>`），然后逐个回读
   10 个参数与期望值比对，只有全部达标才回成功；不达标/写盘失败/sysctl 失败一律如实报错。
   真机复验：同一条 HTTP 请求后 `net.core.somaxconn` = **4096**，且 conf md5 不变。

2. **写盘与命令退出码一律不看**：`yf.writeFile` / `sysctl --system` / `echo never >` /
   `systemctl enable --now` 的返回值全部丢弃 → 磁盘满、无权限、unit 起不来照样报成功。
   修复：writeFile 失败即返回「内核参数配置文件写入失败:」；THP 写入后回读校验，
   `[never]` 未出现则点名上报；`systemctl daemon-reload/enable` 非 0 也点名上报。
   真机负向探针（内进程直调）：写 /proc 只读路径 → status=False + 路径；
   THP 夹具写不进 → status=False + `.../enabled(实际值 never)`。

3. **`readFile` 返回 False 未判 → AttributeError**：`get_status` 里
   `yf.readFile('/sys/.../enabled').strip()` 一旦读失败（sysfs 不可读/竞态）就 500。
   修复：类型判断后回落 `未知`；真机探针 `readFile → False` 下 get_status 正常返回。

4. **`sysctl -n <key>` 每参数起一个 shell 进程**：状态面板一次要读 10 个参数 =
   10 次 fork + 把参数名拼进 shell 字符串。修复：直读 `/proc/sys/<key>`（无进程、
   无拼接），取不到才回退 `sysctl -n` 且经 `yf.shlexQuote`。

5. **`install.sh` 用 `else` 当卸载兜底**：`bash install.sh`（无参）或任何手误参数都会
   走 Uninstall → `rm -rf ${serverPath}/linux_sys_opt` + 删掉系统内核参数文件 +
   停用 disable-thp.service。修复：显式 `install`/`uninstall` 分支，其余参数报用法并 `exit 1`；
   路径变量加引号。

6. **失败明细无处可看**：修复后失败消息把「哪个参数没达标」放在 `data`，前端 `applyOpt`
   逐行展开（先经 `YfI18n.escapeHtml` 转义），并补两条后端消息的六语言词条。

断言策略：被测函数全部在**桩 yf**（记录型 shell + 内存文件系统）下跑真实源码，不碰宿主机；
结构性断言用 `ast`/源码文本（抗「注释或 `if False:` 蒙混」）；配置内容与 8G 档基准
逐字节比对（base64 冻结），防配置漂移。
"""
import ast
import base64
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN_SRC = os.environ.get('YF_D01_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'linux_sys_opt')

IDX = os.path.join(PLUGIN_SRC, 'index.py')
HTML = os.path.join(PLUGIN_SRC, 'index.html')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANG_DIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

#: 本轮新增的后端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['内核参数配置文件写入失败:', '部分优化项未生效:']
#: 8G 内存档的配置文件基准（真机 /etc/sysctl.d/99-yufeng-server.conf 原字节，md5 a388d11e728ca0aa21eb2464140aee8f）
CONF_REF_B64 = (
    'CiMgMS4g6ZmN5L2OIFN3YXAg5o2i5Ye65YC+5ZCRCnZtLnN3YXBwaW5lc3MgPSAxMAojIDIuIOiEj+mhteW5s+a7keWIt+eb'
    'mAp2bS5kaXJ0eV9iYWNrZ3JvdW5kX3JhdGlvID0gNQp2bS5kaXJ0eV9yYXRpbyA9IDEwCiMgMy4g6YCC5bqm5o+Q6auYIFRD'
    'UCDnm5HlkKzpmJ/liJfkuIrpmZAKbmV0LmNvcmUuc29tYXhjb25uID0gNDA5NgojIDQuIOWinuWKoOi/m+eoi+WPr+aLpeac'
    'ieeahOacgOWkpyBWTUEg5pWw6YePCnZtLm1heF9tYXBfY291bnQgPSAyNjIxNDQKIyA1LiDns7vnu5/nuqfmnIDlpKfmlofk'
    'u7bmj4/ov7DnrKbmlbDph48KZnMuZmlsZS1tYXggPSAyMDk3MTUyCiMgNi4gVElNRV9XQUlUIHNvY2tldCDlpI3nlKgKbmV0'
    'LmlwdjQudGNwX3R3X3JldXNlID0gMQojIDcuIOaJqeWkp+WQkeWklui/nuaOpeeahOerr+WPo+iMg+WbtApuZXQuaXB2NC5p'
    'cF9sb2NhbF9wb3J0X3JhbmdlID0gMTAyNCA2NTAwMAojIDguIOW6lOWvuemrmOW5tuWPkeS4jiBTWU4g5pS75Ye7Cm5ldC5p'
    'cHY0LnRjcF9tYXhfc3luX2JhY2tsb2cgPSA4MTkyCiMgOS4g6ZmQ5Yi25pyA5aSnIFRJTUVfV0FJVCDmlbDph4/vvIznnIHl'
    'hoXlrZgKbmV0LmlwdjQudGNwX21heF90d19idWNrZXRzID0gMjAwMDAK'
)


def _load_index():
    """按源码文件加载插件模块（不复用 sys.modules，保持每个用例互不串台）。"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('linux_sys_opt_index_guard', IDX)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    finally:
        # 插件模块为兼容历史会把 cwd 切到 web/，测试进程要留在原处
        os.chdir(cwd)
    return mod


class YfStub(object):
    """记录型 yf 桩：内存文件系统 + 记录的命令（含退出码）。"""

    def __init__(self):
        self.files = {}
        self.writes = []
        self.cmds = []
        self.write_ok = True
        self.rc_by_prefix = {}
        self.on_cmd = None

    # --- 文件 ---
    def readFile(self, path):
        if path in self.files:
            return self.files[path]
        return False

    def writeFile(self, path, content, mode='w+'):
        if not self.write_ok:
            return False
        self.writes.append((path, content))
        self.files[path] = content
        return True

    # --- 命令 ---
    def execShellRc(self, cmd, cwd=None, timeout=None, shell=True):
        self.cmds.append(cmd)
        if self.on_cmd is not None:
            self.on_cmd(cmd)
        rc = 0
        for prefix, val in self.rc_by_prefix.items():
            if cmd.startswith(prefix):
                rc = val
                break
        return (rc, '', '' if rc == 0 else 'stub failure')

    def execShell(self, cmd, cwd=None, timeout=None, shell=True):
        self.cmds.append(cmd)
        if self.on_cmd is not None:
            self.on_cmd(cmd)
        return ('', '')

    def shlexQuote(self, s):
        return shlex.quote(str(s))

    def returnJson(self, status, msg, data=None, *args):
        return json.dumps({'status': status, 'msg': msg, 'data': data})

    def getServerDir(self):
        return '/www/server'


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = _load_index()
        self.stub = YfStub()
        self.mod.yf = self.stub
        # 真机 Debian12 的 MemTotal（8129264 kB → 7938MB，落在 8G 档）
        self.stub.files['/proc/meminfo'] = 'MemTotal:       8129264 kB\n'

    def tune(self, mem_mb=7938):
        self.assertEqual(self.mod.get_mem_mb(), mem_mb, '内存档位夹具与期望不一致')
        conf, expect = self.mod._tuning_conf(mem_mb)
        for key, val in expect.items():
            self.stub.files['/proc/sys/' + key.replace('.', '/')] = val + '\n'
        return conf, expect

    def call_apply(self):
        return json.loads(self.mod.apply_opt())


class TestConfigBytes(Base):
    def test_01_conf_bytes_frozen_for_8g_tier(self):
        """8G 档配置内容必须与真机既有文件逐字节一致（防重复点击产生配置漂移）。"""
        conf, _expect = self.mod._tuning_conf(7938)
        self.assertEqual(conf.encode('utf-8'), base64.b64decode(CONF_REF_B64))

    def test_02_tier_values_follow_memory(self):
        """三档内存的阶梯值必须与界面评分函数（index.html expected_*）同口径。"""
        cases = {1024: (1024, 2048, 5000, 1048576),
                 7938: (4096, 8192, 20000, 2097152),
                 16384: (8192, 16384, 50000, 6553500)}
        for mem, (somax, syn, tw, fmax) in cases.items():
            conf, expect = self.mod._tuning_conf(mem)
            self.assertEqual(expect['net.core.somaxconn'], str(somax))
            self.assertEqual(expect['net.ipv4.tcp_max_syn_backlog'], str(syn))
            self.assertEqual(expect['net.ipv4.tcp_max_tw_buckets'], str(tw))
            self.assertEqual(expect['fs.file-max'], str(fmax))
            for key, val in expect.items():
                self.assertIn('%s = %s' % (key, val), conf)

    def test_03_conf_path_matches_install_sh_removal_path(self):
        """写入路径必须与 install.sh 卸载时删除的路径一致（否则卸载残留内核配置）。"""
        self.assertEqual(self.mod.SYSCTL_CONF, '/etc/sysctl.d/99-yufeng-server.conf')
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        self.assertIn('rm -f ' + self.mod.SYSCTL_CONF, sh)


class TestApplyOptHonesty(Base):
    def test_04_success_only_when_all_values_effective(self):
        """全部回读达标才回成功。"""
        self.tune()
        r = self.call_apply()
        self.assertTrue(r['status'], r)
        self.assertEqual(r['msg'], '全平台内核优化配置已成功生效！')

    def test_05_mismatch_reports_failure_with_key(self):
        """有一个参数没生效 → 必须失败，并把参数名与期望/实际值放进 data。"""
        self.tune()
        self.stub.files['/proc/sys/net/core/somaxconn'] = '1024\n'   # 模拟被 /etc/sysctl.conf 覆盖
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '部分优化项未生效:')
        self.assertIn('net.core.somaxconn', r['data'])
        self.assertIn('4096', r['data'])
        self.assertIn('1024', r['data'])

    def test_06_reapplies_own_conf_after_system(self):
        """核心修复：`sysctl --system` 之后必须再 `sysctl -p <本插件文件>`，
        否则 /etc/sysctl.conf（最后读取）会覆盖本插件的 drop-in。"""
        self.tune()

        def flip(cmd):
            if cmd.startswith('sysctl -p '):
                # 只有显式套用本插件文件后 somaxconn 才真正变成 4096
                self.stub.files['/proc/sys/net/core/somaxconn'] = '4096\n'

        self.stub.files['/proc/sys/net/core/somaxconn'] = '1024\n'
        self.stub.on_cmd = flip
        r = self.call_apply()

        system_idx = [i for i, c in enumerate(self.stub.cmds) if c == 'sysctl --system']
        own_idx = [i for i, c in enumerate(self.stub.cmds) if c.startswith('sysctl -p ')]
        self.assertTrue(system_idx, self.stub.cmds)
        self.assertTrue(own_idx, self.stub.cmds)
        self.assertLess(system_idx[0], own_idx[0])
        self.assertIn(shlex.quote(self.mod.SYSCTL_CONF), self.stub.cmds[own_idx[0]])
        self.assertTrue(r['status'], r)

    def test_07_sysctl_p_failure_reported(self):
        """`sysctl -p` 非 0 退出 → 必须如实失败。"""
        self.tune()
        self.stub.rc_by_prefix['sysctl -p '] = 1
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertIn('sysctl -p', r['data'])

    def test_08_write_failure_short_circuits(self):
        """写盘失败 → 失败并短路（不再去动内核参数）。"""
        self.tune()
        self.stub.write_ok = False
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertEqual(r['msg'], '内核参数配置文件写入失败:')
        self.assertEqual(self.stub.cmds, [])

    def test_09_write_failure_when_writeFile_returns_false_only(self):
        """writeFile 静默返回 False（磁盘满/权限）也要被判为失败。"""
        self.tune()
        self.stub.write_ok = False
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertIn('写入失败', r['msg'])

    def test_10_thp_readback_verified(self):
        """THP 写入后必须回读校验：没出现 [never] 就点名上报。"""
        self.tune()
        tmpd = tempfile.mkdtemp(prefix='yf_d01_thp_')
        self.addCleanup(shutil.rmtree, tmpd, True)
        # os.path.exists 走真实磁盘，内容走桩内存文件系统
        enabled = os.path.join(tmpd, 'enabled')
        defrag = os.path.join(tmpd, 'defrag')
        for path in (enabled, defrag):
            with io.open(path, 'w', encoding='utf-8') as fp:
                fp.write('')
            self.stub.files[path] = 'always madvise'
        self.mod.THP_ENABLED = enabled
        self.mod.THP_DEFRAG = defrag

        # 桩 shell 不真的写文件 → 回读仍是 always madvise，必须失败
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertIn(enabled, r['data'])

        # 让 shell 把 never 写进去（桩文件系统）→ 必须成功
        def write_never(cmd):
            if cmd.startswith('echo never >'):
                target = cmd.split('>', 1)[1].strip().strip("'")
                self.stub.files[target] = '[never]'

        self.stub.on_cmd = write_never
        r2 = self.call_apply()
        self.assertTrue(r2['status'], r2)

    def test_11_systemd_failure_reported(self):
        """systemctl enable 失败也必须点名上报（历史实现全程不看返回码）。"""
        self.tune()
        self.stub.rc_by_prefix['systemctl enable'] = 1
        r = self.call_apply()
        self.assertFalse(r['status'], r)
        self.assertIn('systemctl enable', r['data'])


class TestGetStatus(Base):
    def test_12_values_normalized_and_unset_marked(self):
        """状态面板：读到值给值、读不到给「未设置」，ip_local_port_range 空白归一化。"""
        self.stub.files['/proc/sys/vm/swappiness'] = '10\n'
        self.stub.files['/proc/sys/net/ipv4/ip_local_port_range'] = '1024\t65000\n'
        r = json.loads(self.mod.get_status())
        self.assertTrue(r['status'])
        self.assertEqual(r['data']['vm_swappiness'], '10')
        self.assertEqual(r['data']['net_ipv4_ip_local_port_range'], '1024 65000')
        self.assertEqual(r['data']['fs_file_max'], '未设置')

    def test_13_readfile_false_does_not_crash(self):
        """readFile 返回 False（老实现 .strip() → AttributeError 500）不得抛异常。

        刻意把 THP 开关路径 "造" 成存在（老实现按 os.path.exists 才去 .strip()），
        这样老代码在任意平台都会抛异常，而新实现回落到「未知」。
        """
        thp = '/sys/kernel/mm/transparent_hugepage/enabled'
        real_exists = os.path.exists
        self.stub.readFile = lambda path: False
        with mock.patch('os.path.exists', lambda p: True if p == thp else real_exists(p)):
            r = json.loads(self.mod.get_status())
        self.assertTrue(r['status'])
        self.assertEqual(r['data']['thp_enabled'], '未知')

    def test_14_frontend_fields_have_backend_values(self):
        """前端用到的每个 data.<字段> 都必须由 get_status 提供（防漏字段）。"""
        html = io.open(HTML, encoding='utf-8').read()
        used = set(re.findall(r'(?<![A-Za-z0-9_])data\.([a-z0-9_]+)', html))
        provided = {f for f, _k in self.mod.STATUS_KEYS} | {'thp_enabled', 'mem_mb'}
        self.assertTrue(used, '未从 index.html 解析到 data.<字段>')
        self.assertEqual(used - provided, set())


class TestReadSysctl(Base):
    def test_15_read_sysctl_reads_proc_first(self):
        """直读 /proc/sys（不起进程），回退 sysctl 时经 yf.shlexQuote。"""
        self.stub.files['/proc/sys/vm/swappiness'] = ' 10 \n'
        self.assertEqual(self.mod.read_sysctl('vm.swappiness'), '10')
        self.assertEqual(self.stub.cmds, [])

    def test_16_read_sysctl_fallback_is_quoted(self):
        """AST：回退分支的 shell 命令必须是 shlexQuote(key)，不得把 key 直接拼进字符串。"""
        tree = ast.parse(io.open(IDX, encoding='utf-8').read())
        fn = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == 'read_sysctl']
        self.assertEqual(len(fn), 1, '未找到 read_sysctl')
        quoted = False
        for node in ast.walk(fn[0]):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, 'attr', None) or getattr(node.func, 'id', None)
            if fname != 'execShellRc':
                continue
            arg = node.args[0] if node.args else None
            self.assertIsInstance(arg, ast.BinOp, 'execShellRc 参数应为字符串拼接（常量 + shlexQuote）')
            names = [getattr(x.func, 'attr', None) or getattr(x.func, 'id', None)
                     for x in ast.walk(arg) if isinstance(x, ast.Call)]
            quoted = quoted or 'shlexQuote' in names
        self.assertTrue(quoted, 'read_sysctl 回退分支未使用 yf.shlexQuote')


class TestInstallSh(Base):
    def test_17_unknown_action_refused(self):
        """缺参数/未知动作必须拒绝，不能走卸载（历史 else 兜底会 rm -rf 安装目录）。"""
        lines = io.open(INSTALL_SH, encoding='utf-8').read().splitlines()
        start = [i for i, l in enumerate(lines) if l.startswith('action=$1')]
        self.assertEqual(len(start), 1, '未找到 action 分发')
        tail = lines[start[0]:]
        text = '\n'.join(tail)
        # 显式 uninstall 分支存在
        self.assertIn("elif [ \"${action}\" == 'uninstall' ]", text)
        # else 分支只报用法并退出，不得调用卸载函数
        else_at = [i for i, l in enumerate(tail) if l.startswith('else')]
        self.assertTrue(else_at, text)
        else_body = '\n'.join(tail[else_at[-1]:])
        self.assertIn('exit 1', else_body)
        self.assertNotIn('Uninstall_', else_body)

    def test_18_install_sh_syntax_and_quoting(self):
        """install.sh 语法自洽 + 路径加引号（防空格/空值下 rm -rf 打到别处）。"""
        import subprocess
        sh = io.open(INSTALL_SH, encoding='utf-8').read()
        self.assertIn('rm -rf "${serverPath}/linux_sys_opt"', sh)
        bash = shutil.which('bash')
        if not bash:
            self.skipTest('环境无 bash，语法检查交由真机/CI 执行')
        rc = subprocess.call([bash, '-n', INSTALL_SH],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(rc, 0, 'install.sh 语法检查失败')


class TestFrontendAndI18n(Base):
    def test_19_frontend_escapes_failure_detail(self):
        """失败明细要逐行展开且先转义（明细来自 shell 输出）。"""
        html = io.open(HTML, encoding='utf-8').read()
        self.assertIn('function sysOptEscape', html)
        self.assertIn('escapeHtml(String(text))', html)
        self.assertIn("split('; ').map(sysOptEscape)", html)
        self.assertIn(".fail(function()", html)

    def test_20_new_msg_keys_in_all_languages(self):
        """新增两条后端消息必须六语言齐备、key 集合对齐、非中文语言无中文残留。"""
        base = None
        for lang in LANGS:
            path = os.path.join(LANG_DIR, '%s.json' % lang)
            data = json.loads(io.open(path, encoding='utf-8').read())
            if base is None:
                base = set(data)
            self.assertEqual(set(data), base, '%s key 集合与 zh-CN 不一致' % lang)
            for key in NEW_MSG_KEYS:
                self.assertIn(key, data, '%s 缺少 %s' % (lang, key))
                self.assertTrue(data[key].strip(), '%s 的 %s 译文为空' % (lang, key))
            if lang in ('en', 'de', 'fr', 'it'):
                for key in NEW_MSG_KEYS:
                    self.assertIsNone(re.search(r'[\u4e00-\u9fa5]', data[key]),
                                      '%s 的 %s 译文残留中文' % (lang, key))


if __name__ == '__main__':
    unittest.main(verbosity=2)
