# coding: utf-8
r"""E02 docker 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/docker/`（index.py / pull_task.py / js/docker.js / lang）。
真机 Debian12 现状（2026-10-10）：docker 29.6.2 daemon active、DockerRootDir=/docker2026、
本地只有 `postgres:18.4-bookworm` 镜像、**无公网**；已有生产容器 `pg-test1`（只读禁动）。

真机实测（夹具 + 真实容器闭环，全部在 /root/yf_probe_* 与 yftest_E02_* 下完成并清理）：

  * **P0 硬编码 `privileged=True`**：面板创建的每个容器都拿全主机特权。
    夹具记录到的 `containers.run` 实参里 `privileged="True"`。
  * **P0 `volumes` 无任何校验**：`{"/": {"bind": "/host", "mode": "rw"}}` 真机建出容器，
    容器内 `cat /host/etc/shadow` **读到了宿主机 root 口令哈希**（配合特权 = 宿主接管）；
    `{"/etc": ...}` 同样放行；`volumes="not-json"` 直接 JSONDecodeError traceback。
  * **`cpu_shares=int(...)` 裸转换**：`cpu_shares=abc` → ValueError traceback；
    `999999999` 原样下发。
  * **端口放行从未生效**：`__release_port(ports)` 收到的是整个 ports 字典字符串，
    firewall 的 parsePortSpec 判非法 → 一条规则也没下发（容器起了、端口对外不通）。
  * **匿名卷泄漏**：`conFind.remove(force=True)` 不带 `v=True`，真机 `docker volume ls`
    累积了孤儿卷（本次清理掉本轮探针产生的 7 个，历史遗留 42 个）。
  * **`python pull_task.py`**：真机只有 python3，`python` 不存在 → 拉取任务 100% 失败。
  * **`docker_exec`** 把 Hostname 原样拼进交给 webssh 的命令行（`a'; touch ...; #`）。
  * **配置损坏全 500**：iplist.json / user.json 损坏时 get/add/del/repoList 全 traceback。
  * **`docker_logout` 假成功**：非 docker.io 的 registry 直接返回 None；失败也回 status=true。
  * **`dockerLoginCheck`** 把口令拼进命令行（`-p <口令>` 出现在宿主机 ps 里）。
  * **`set_accelerator`** 不校验 mirrors → 垃圾内容写进 /etc/docker/daemon.json 并重启 docker。
  * **`migrate_docker_dir` / `check_docker_migrate_space`** 的 new_path 无校验（`/etc` 也放行）。
  * **前端**：28 处 innerHTML 里容器名/镜像名/IP 池/仓库信息/容器命令全部未转义（存储型 XSS）；
    `$.post('/files/delete')` 缺 `.fail()`。

断言策略：能真跑的用夹具真跑（假 docker 客户端记录 `containers.run` 实参、假 `__release_port`
记录放行端口、临时目录里的 iplist/user.json 损坏夹具）；结构类断言用 `ast`（抗 `if False:`
与注释蒙混）；前端断言用去注释后的源码。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.environ.get('YF_E02_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'docker')
INDEX_PY = os.path.join(PLUGIN_DIR, 'index.py')
PULL_TASK = os.path.join(PLUGIN_DIR, 'pull_task.py')
DOCKER_JS = os.path.join(PLUGIN_DIR, 'js', 'docker.js')
LANG_DIR = os.path.join(PLUGIN_DIR, 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _strip_py_comments(src):
    """只删注释（保留原有缩进/格式/字符串）：
    `# 旧实现硬编码 privileged=True` 这类注释不得算命中，
    但用 token 重组会打乱格式，因此只把注释所在位置挖空。"""
    lines = src.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                lines[row - 1] = lines[row - 1][:col]
    except Exception:
        return src
    return '\n'.join(lines)


def _strip_js_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)^[ \t]*//.*$', '', src)
    return src


def _load_plugin(name='docker_e02_guard'):
    """加载 plugins/docker/index.py（导入期会 chdir 到 web/，必须从仓库根启动并还原 cwd）"""
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        spec = importlib.util.spec_from_file_location(name, INDEX_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


class _FakeContainer(object):
    def __init__(self, **kw):
        self.kw = kw


class _FakeContainers(object):
    def __init__(self, sink, fail=False):
        self.sink = sink
        self.fail = fail

    def run(self, **kw):
        self.sink.append(kw)
        if self.fail:
            raise RuntimeError('fixture stop')
        return _FakeContainer(**kw)

    def get(self, name):
        if name.startswith('missing'):
            raise Exception('no such container')
        return _FakeContainer(name=name)


class _FakeClient(object):
    def __init__(self, sink, fail=False):
        self.containers = _FakeContainers(sink, fail=fail)


class DockerE02Guard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_plugin()
        cls.index_src = _read(INDEX_PY)
        cls.index_code = _strip_py_comments(cls.index_src)
        cls.pull_src = _read(PULL_TASK)
        cls.js_src = _strip_js_comments(_read(DOCKER_JS))
        cls.tree = ast.parse(cls.index_src)

    def setUp(self):
        self._argv = list(sys.argv)
        self._getDClient = self.mod.getDClient
        self._release = getattr(self.mod, '__release_port')

    def tearDown(self):
        sys.argv = self._argv
        self.mod.getDClient = self._getDClient
        setattr(self.mod, '__release_port', self._release)

    # ---------------- 夹具工具 ----------------
    def _install_fake_client(self, fail=False):
        # 无条件注入最小 `docker.errors.APIError`（开发机上 `import docker` 可能解析到
        # 别的模块），保证 `except docker.errors.APIError` 与真机同一语义
        self.mod.docker = types.SimpleNamespace(
            errors=types.SimpleNamespace(APIError=RuntimeError))
        sink = []
        self.mod.getDClient = lambda: _FakeClient(sink, fail=fail)
        return sink

    def _install_fake_release(self):
        ports = []
        setattr(self.mod, '__release_port', lambda p: ports.append(p))
        return ports

    def _call(self, func, args=None):
        argv = [INDEX_PY, func]
        if args is not None:
            argv.append(json.dumps(args))
        sys.argv = argv
        return json.loads(getattr(self.mod, func)())

    def _create_args(self, **over):
        args = {
            'name': 'yftest_E02_guard',
            'environments': 'POSTGRES_PASSWORD=x',
            'command': '', 'entrypoint': '',
            'image': 'postgres:18.4-bookworm',
            'mem_limit': '128',
            'ports': '{}',
            'volumes': '{}',
            'cpu_shares': '50',
            'privileged': '0',
        }
        args.update(over)
        return args

    def _func(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail('函数 %s 不存在' % name)

    def _func_src(self, name):
        node = self._func(name)
        return _strip_py_comments(ast.get_source_segment(self.index_src, node) or '')

    # ---------------- 1. 结构断言（抗注释蒙混） ----------------
    def test_01_no_hardcoded_privileged(self):
        """privileged 必须是入参（默认关），不得再硬编码 True"""
        src = self._func_src('dockerCreateCon')
        self.assertNotIn('privileged=True', src)
        self.assertIn('privileged=privileged', src)
        self.assertIn('isTruthy(', src)
        tree = ast.parse(src)
        kw = [n.keywords for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == 'run']
        self.assertTrue(kw, '找不到 containers.run 调用')
        names = [k.arg for k in kw[0]]
        self.assertIn('privileged', names)
        priv = [k for k in kw[0] if k.arg == 'privileged'][0]
        self.assertIsInstance(priv.value, ast.Name,
                              'privileged 必须是变量（来自前端入参），不得是字面量')
        self.assertEqual(priv.value.id, 'privileged')

    def test_02_mounts_validated_before_run(self):
        """volumes 必须过 validateMounts，不得再 json.loads 直用"""
        src = self._func_src('dockerCreateCon')
        self.assertNotIn('json.loads(volumes)', src)
        self.assertIn('validateMounts(', src)
        self.assertIn('volumes=volumes_parsed', src)
        self.assertTrue(hasattr(self.mod, 'validateMounts'))

    def test_03_ports_validated_and_tuple_form(self):
        """ports 必须过 validatePorts，且喂给 docker-py 的是 2 元 tuple"""
        src = self._func_src('dockerCreateCon')
        self.assertIn('validatePorts(', src)
        vp = self._func_src('validatePorts')
        self.assertIn('result[key] = (host_ip, host_port)', vp)
        self.assertNotIn('result[key] = [host_ip, host_port]', vp)

    def test_04_cpu_shares_no_bare_int(self):
        src = self._func_src('dockerCreateCon')
        self.assertNotIn('cpu_shares=int(', src)
        self.assertIn('toInt(', src)
        self.assertIn('CPU配额设置值范围应为 [1-100]!', src)

    def test_05_release_port_uses_host_ports(self):
        src = self._func_src('dockerCreateCon')
        self.assertNotIn('__release_port(ports)', src)
        self.assertIn('for host_port in host_ports', src)
        self.assertIn('__release_port(host_port)', src)

    def test_06_blacklist_and_data_root_helpers(self):
        for name in ('forbiddenMountSource', 'invalidDataRoot', 'toInt', 'readJsonFile',
                     'loadIpList', 'isTruthy'):
            self.assertTrue(hasattr(self.mod, name), '缺少助手 %s' % name)
        for const in ('CONTAINER_NAME_RE', 'IMAGE_REF_RE', 'MIRROR_URL_RE',
                      'FORBIDDEN_MOUNT_SOURCES', 'ALLOWED_MOUNT_SOURCES',
                      'FORBIDDEN_DATA_ROOTS', 'CONTAINER_PORT_RE'):
            self.assertTrue(hasattr(self.mod, const), '缺少常量 %s' % const)

    def test_07_getargs_handles_json_argv_and_garbage(self):
        """getArgs 必须吃下前端 JSON 单 argv（含带 version 的两段形态），且不抛异常"""
        cases = [
            (['x', 'f', '{"Hostname":"a"}'], {'Hostname': 'a'}),
            (['x', 'f', '1.0', '{"Hostname":"b"}'], {'Hostname': 'b'}),
            (['x', 'f', 'null'], {}),
            (['x', 'f', '123'], {}),
            (['x', 'f', '["a"]'], {}),
            (['x', 'f'], {}),
        ]
        for argv, expect in cases:
            sys.argv = argv
            got = self.mod.getArgs()
            self.assertIsInstance(got, dict, 'argv=%r 未返回 dict' % argv)
            self.assertEqual(got, expect, 'argv=%r' % argv)

    def test_08_checkargs_survives_non_dict(self):
        ok, msg = self.mod.checkArgs(None, ['name'])
        self.assertFalse(ok)
        self.assertIn('缺少必要参数', json.loads(msg)['msg'])

    def test_09_exec_shell_false_needs_execshellrc(self):
        """列表化调用必须走 execShellRc：execShell 的 shell=False 分支会对 list 调 shlex.split"""
        src = self.index_src
        self.assertNotIn("yf.execShell([", src)
        self.assertIn("yf.execShellRc([", src)

    def test_10_pull_task_uses_panel_python(self):
        src = self._func_src('docker_pull_with_mirror')
        self.assertNotIn('&& python pull_task.py', src)
        self.assertIn('sys.executable', src)

    def test_11_login_check_password_via_stdin(self):
        src = self._func_src('dockerLoginCheck')
        self.assertIn('--password-stdin', src)
        self.assertNotIn("'-p'", src)
        self.assertNotIn(' -p ', src)

    def test_12_pull_task_static_shape(self):
        tree = ast.parse(self.pull_src)
        srcs = ast.get_source_segment(self.pull_src, tree) or ''
        self.assertIn("'docker', 'pull'", self.pull_src)
        self.assertNotIn('shlex.split(cmd)', self.pull_src)
        self.assertIn('IMAGE_REF_RE', self.pull_src)
        self.assertIn('MIRROR_HOST_RE', self.pull_src)
        self.assertIn("['docker', 'tag'", self.pull_src)
        self.assertIn("['docker', 'rmi'", self.pull_src)

    def test_13_service_ops_listed_and_rc_based(self):
        """systemctl 调用列表化 + 判 rc（旧实现拼 shell 且以「stderr 为空」当成功）"""
        for name in ('dockerOp', 'initdInstall', 'initdUinstall', 'initdStatus'):
            src = self._func_src(name)
            self.assertIn('execShellRc(', src, '%s 必须走 execShellRc' % name)
            self.assertIn('shell=False', src, '%s 必须列表化调用' % name)
            self.assertNotIn("'systemctl ' +", src)
            self.assertNotIn("'systemctl status ", src)
        # 同族：不得硬编码旧面板目录名，不得用 ps -ef|grep 判进程
        self.assertNotIn('mdserver-web', self.index_code)
        self.assertNotIn('ps -ef', self.index_code)

    def test_14_no_bare_shell_concat_in_service_ops(self):
        """服务/进程操作不得把参数拼进 shell：systemctl 要么是常量、要么走列表；
        chattr 必须列表化（migrate/加速器里的 `systemctl restart docker` 是无入参常量，不在此列）"""
        for marker in ("'systemctl ' +", '"systemctl " +', "'chattr ", 'chattr -R -i %s'):
            self.assertNotIn(marker, self.index_code, '仍存在 shell 拼接: %s' % marker)

    # ---------------- 2. 挂载白/黑名单 ----------------
    def test_20_forbidden_mount_sources(self):
        for bad in ('/', '/etc', '/etc/', '/root', '/root/.ssh', '/proc', '/sys',
                    '/sys/kernel', '/dev', '/boot', '/usr/bin', '/var/run',
                    '/var/run/docker.sock', '/var/lib/docker', '/www/server'):
            self.assertTrue(self.mod.forbiddenMountSource(bad), '%s 必须被拒' % bad)
        panel_dir = os.path.normpath(self.mod.yf.getPanelDir())
        self.assertTrue(self.mod.forbiddenMountSource(panel_dir))
        self.assertTrue(self.mod.forbiddenMountSource(panel_dir + '/plugins'))

    def test_21_allowed_mount_sources(self):
        for ok in ('/sys/fs/cgroup', '/www/wwwroot/site', '/data/app', '/docker2026',
                   'named_volume'):
            self.assertIsNone(self.mod.forbiddenMountSource(ok), '%s 不应被拒' % ok)

    def test_22_validate_mounts_rejects_and_accepts(self):
        mod = self.mod
        for bad in ('{"/": {"bind": "/host", "mode": "rw"}}',
                    '{"/etc": {"bind": "/hostetc", "mode": "rw"}}',
                    '{"/root": {"bind": "/r", "mode": "rw"}}',
                    '{"/var/run/docker.sock": {"bind": "/d.sock", "mode": "rw"}}',
                    'not-json', '[]', 'null', '"x"',
                    '{"/data": "/host/dir"}',
                    '{"/data": {"bind": "", "mode": "rw"}}',
                    '{"/data": {"bind": "/", "mode": "rw"}}',
                    '{"/data": {"bind": "relative", "mode": "rw"}}',
                    '{"/data": {"bind": "/data", "mode": "exec"}}',
                    '{"/data": {"mode": "rw"}}',
                    '{"relative": {"bind": "/data", "mode": "rw"}}',
                    '{"/sys": {"bind": "/sys", "mode": "rw"}}'):
            volumes, err = mod.validateMounts(bad)
            self.assertIsNotNone(err, '%r 必须被拒' % bad)
            self.assertIsNone(volumes)
        volumes, err = mod.validateMounts('{"/data": {"bind": "/data", "mode": "rw"}, '
                                          '"/sys/fs/cgroup": {"bind": "/sys/fs/cgroup", "mode": "rw"}}')
        self.assertIsNone(err)
        self.assertEqual(volumes['/data'], {'bind': '/data', 'mode': 'rw'})
        self.assertEqual(volumes['/sys/fs/cgroup'], {'bind': '/sys/fs/cgroup', 'mode': 'rw'})
        volumes, err = mod.validateMounts('')
        self.assertEqual(volumes, {})
        self.assertIsNone(err)

    # ---------------- 3. 端口映射 ----------------
    def test_23_validate_ports_rejects(self):
        for bad in ('not-json', '[]', '{"5432": [["0.0.0.0"], 1]}',
                    '{"99999/tcp": ["0.0.0.0", 15440]}',
                    '{"5432/tcp": ["0.0.0.0", 99999]}',
                    '{"5432/tcp": ["0.0.0.0", 0]}',
                    '{"5432/tcp": ["0.0.0.0", "abc"]}',
                    '{"5432/tcp": ["<img src=x>", 15440]}',
                    '{"5432/sctp": ["0.0.0.0", 15440]}',
                    '{"5432/tcp": ["0.0.0.0", 15440, 15441]}',
                    '{"0/tcp": ["0.0.0.0", 15440]}'):
            ports, host_ports, err = self.mod.validatePorts(bad)
            self.assertIsNotNone(err, '%r 必须被拒' % bad)

    def test_24_validate_ports_accepts_ui_shape(self):
        ports, host_ports, err = self.mod.validatePorts('{"5432/tcp": ["0.0.0.0", 15440]}')
        self.assertIsNone(err)
        self.assertEqual(ports, {'5432/tcp': ('0.0.0.0', 15440)})
        self.assertIsInstance(ports['5432/tcp'], tuple)
        self.assertEqual(host_ports, ['15440'])
        ports, host_ports, err = self.mod.validatePorts('{"80": 8080}')
        self.assertIsNone(err)
        self.assertEqual(ports, {'80/tcp': ('0.0.0.0', 8080)})
        self.assertEqual(host_ports, ['8080'])

    # ---------------- 4. 数据目录 ----------------
    def test_25_invalid_data_root(self):
        for bad in ('/etc', '/etc/docker', '/root', '/', 'relative', '', '/www/server/x',
                    '/proc', '/dev', '/usr/local'):
            self.assertTrue(self.mod.invalidDataRoot(bad), '%r 必须被拒' % bad)
        for ok in ('/docker2026', '/data/docker', '/www/docker'):
            self.assertIsNone(self.mod.invalidDataRoot(ok), '%r 不应被拒' % ok)

    def test_26_to_int_never_raises(self):
        mod = self.mod
        self.assertEqual(mod.toInt('50', None, 1, 100), 50)
        self.assertIsNone(mod.toInt('abc', None, 1, 100))
        self.assertIsNone(mod.toInt(None, None, 1, 100))
        self.assertIsNone(mod.toInt('', None, 1, 100))
        self.assertIsNone(mod.toInt('101', None, 1, 100))
        self.assertIsNone(mod.toInt('0', None, 1, 100))
        self.assertIsNone(mod.toInt([], None, 1, 100))
        self.assertEqual(mod.toInt('128', None, 1, 1048576), 128)

    # ---------------- 5. dockerCreateCon 真跑（假客户端） ----------------
    def test_30_create_normal_kwargs(self):
        sink = self._install_fake_client()
        ports = self._install_fake_release()
        res = self._call('dockerCreateCon', self._create_args(
            ports='{"5432/tcp": ["0.0.0.0", 15440]}'))
        self.assertTrue(res['status'], res)
        self.assertEqual(len(sink), 1)
        kw = sink[0]
        self.assertFalse(kw['privileged'], 'privileged 默认必须为 False')
        self.assertEqual(kw['ports'], {'5432/tcp': ('0.0.0.0', 15440)})
        self.assertEqual(kw['volumes'], {})
        self.assertEqual(kw['cpu_shares'], 50)
        self.assertEqual(kw['mem_limit'], '128M')
        self.assertEqual(kw['environment'], ['POSTGRES_PASSWORD=x'])
        self.assertEqual(ports, ['15440'], '防火墙放行必须收到宿主机端口')

    def test_31_create_privileged_opt_in(self):
        sink = self._install_fake_client()
        self._install_fake_release()
        res = self._call('dockerCreateCon', self._create_args(privileged='1'))
        self.assertTrue(res['status'])
        self.assertTrue(sink[0]['privileged'])
        for value in ('0', '', 'off', 'no', 'false', 'maybe'):
            sink = self._install_fake_client()
            res = self._call('dockerCreateCon', self._create_args(privileged=value))
            self.assertFalse(sink[0]['privileged'], 'privileged=%r 不应开启' % value)

    def test_32_create_rejects_attacks_without_docker_call(self):
        attacks = [
            dict(volumes='{"/": {"bind": "/host", "mode": "rw"}}'),
            dict(volumes='{"/etc": {"bind": "/hostetc", "mode": "rw"}}'),
            dict(volumes='{"/root": {"bind": "/r", "mode": "rw"}}'),
            dict(volumes='{"/var/run/docker.sock": {"bind": "/d.sock", "mode": "rw"}}'),
            dict(volumes='not-json'),
            dict(volumes='{"/data": "/host/dir"}'),
            dict(cpu_shares='abc'),
            dict(cpu_shares='999999'),
            dict(name=''),
            dict(name='a b'),
            dict(name="a'; touch /root/PWNED; #"),
            dict(name='-evil'),
            dict(mem_limit='abc'),
            dict(mem_limit='0'),
            dict(image=''),
            dict(image='-q'),
            dict(image='a b'),
            dict(ports='{"99999/tcp": ["0.0.0.0", 15440]}'),
            dict(ports='{"5432/tcp": ["$(id)", 15440]}'),
        ]
        for attack in attacks:
            sink = self._install_fake_client()
            ports = self._install_fake_release()
            res = self._call('dockerCreateCon', self._create_args(**attack))
            self.assertFalse(res['status'], '必须拒绝: %r' % attack)
            self.assertEqual(sink, [], '拒绝时不得调用 docker: %r' % attack)
            self.assertEqual(ports, [], '拒绝时不得放行端口: %r' % attack)

    def test_33_create_failure_reports_honestly(self):
        """docker 侧异常（含 docker-py 自身 ValueError）必须是业务失败，不是 500"""
        self._install_fake_client(fail=True)
        self._install_fake_release()
        res = self._call('dockerCreateCon', self._create_args())
        self.assertFalse(res['status'])
        self.assertIn('创建失败', res['msg'])

    def test_34_release_port_not_called_on_failure(self):
        ports = self._install_fake_release()
        self._install_fake_client(fail=True)
        self._call('dockerCreateCon', self._create_args(ports='{"80/tcp": ["0.0.0.0", 8080]}'))
        self.assertEqual(ports, [])

    # ---------------- 6. 其它入口的真跑降级 ----------------
    def test_40_exec_rejects_injected_name(self):
        self._install_fake_client()
        for bad in ("a'; touch /root/PWNED; #", 'a b', '$(id)', 'a`id`', 'a;id', ''):
            res = self._call('dockerExec', {'Hostname': bad})
            self.assertFalse(res['status'], '%r 必须被拒' % bad)
        res = self._call('dockerExec', {'Hostname': 'pg-test1'})
        self.assertTrue(res['status'], res)
        self.assertEqual(res['msg'], 'docker container exec -it pg-test1 /bin/sh')

    def test_41_corrupt_iplist_degrades(self):
        """iplist.json 损坏：读接口降级为空、写接口如实报错且不覆盖原文件"""
        mod = self.mod
        server_dir = mod.getServerDir()
        existed = os.path.isdir(server_dir)
        ip_conf = os.path.join(server_dir, 'iplist.json')
        backup = None
        if os.path.exists(ip_conf):
            backup = _read(ip_conf)
        try:
            if not existed:
                os.makedirs(server_dir, exist_ok=True)
            with io.open(ip_conf, 'w', encoding='utf-8') as fh:
                fh.write('{broken')
            res = self._call('getDockerIpList')
            self.assertTrue(res['status'])
            self.assertEqual(res['data'], [])
            res = self._call('dockerAddIP', {'address': '1.2.3.4', 'netmask': '255.255.255.0',
                                             'gateway': '1.2.3.1'})
            self.assertFalse(res['status'], '损坏的池不得被静默覆盖')
            self.assertIn('已损坏', res['msg'])
            self.assertEqual(_read(ip_conf), '{broken', '损坏文件不得被覆盖')
            res = self._call('dockerDelIP', {'address': '1.2.3.4'})
            self.assertFalse(res['status'])
            self.assertEqual(_read(ip_conf), '{broken')
        finally:
            if backup is None:
                if os.path.exists(ip_conf):
                    os.remove(ip_conf)
            else:
                with io.open(ip_conf, 'w', encoding='utf-8') as fh:
                    fh.write(backup)
            if not existed and os.path.isdir(server_dir) and not os.listdir(server_dir):
                shutil.rmtree(server_dir, ignore_errors=True)

    def test_42_corrupt_user_json_degrades(self):
        mod = self.mod
        server_dir = mod.getServerDir()
        existed = os.path.isdir(server_dir)
        user_conf = os.path.join(server_dir, 'user.json')
        backup = None
        if os.path.exists(user_conf):
            backup = _read(user_conf)
        try:
            if not existed:
                os.makedirs(server_dir, exist_ok=True)
            with io.open(user_conf, 'w', encoding='utf-8') as fh:
                fh.write('{broken')
            res = self._call('repoList')
            self.assertTrue(res['status'])
            self.assertEqual(res['data'], [])
            self.assertFalse(mod.delete_user_info('docker.io'))
        finally:
            if backup is None:
                if os.path.exists(user_conf):
                    os.remove(user_conf)
            else:
                with io.open(user_conf, 'w', encoding='utf-8') as fh:
                    fh.write(backup)
            if not existed and os.path.isdir(server_dir) and not os.listdir(server_dir):
                shutil.rmtree(server_dir, ignore_errors=True)

    def test_43_add_ip_validates_format(self):
        mod = self.mod
        server_dir = mod.getServerDir()
        existed = os.path.isdir(server_dir)
        ip_conf = os.path.join(server_dir, 'iplist.json')
        backup = _read(ip_conf) if os.path.exists(ip_conf) else None
        try:
            if not existed:
                os.makedirs(server_dir, exist_ok=True)
            if os.path.exists(ip_conf):
                os.remove(ip_conf)
            for bad in ('<img src=x onerror=alert(1)>', '1.2.3.4; id', '', 'a b'):
                res = self._call('dockerAddIP', {'address': bad, 'netmask': '255.255.255.0',
                                                 'gateway': '1.2.3.1'})
                self.assertFalse(res['status'], '%r 必须被拒' % bad)
            self.assertFalse(os.path.exists(ip_conf), '非法输入不得落盘')
            res = self._call('dockerAddIP', {'address': '10.0.0.9', 'netmask': '255.255.255.0',
                                             'gateway': '10.0.0.1'})
            self.assertTrue(res['status'], res)
            self.assertIn('10.0.0.9', _read(ip_conf))
            res = self._call('dockerDelIP', {'address': '10.0.0.9'})
            self.assertTrue(res['status'], res)
            self.assertNotIn('10.0.0.9', _read(ip_conf))
        finally:
            if backup is None:
                if os.path.exists(ip_conf):
                    os.remove(ip_conf)
            else:
                with io.open(ip_conf, 'w', encoding='utf-8') as fh:
                    fh.write(backup)
            if not existed and os.path.isdir(server_dir) and not os.listdir(server_dir):
                shutil.rmtree(server_dir, ignore_errors=True)

    def test_44_port_check_parses_address_form(self):
        """`地址:端口` 必须被解析：旧实现整串当端口 → getaddrinfo 报错 → 恒回未占用"""
        res = self._call('dockerPortCheck', {'port': 'abc'})
        self.assertFalse(res['status'])
        self.assertIn('端口设置值范围无效', res['msg'])
        for bad in ('0', '70000', '*:', '1:2:3'):
            res = self._call('dockerPortCheck', {'port': bad})
            self.assertFalse(res['status'], '%r 必须被拒' % bad)
        # 真占用判定：本进程自己占一个端口，再问面板
        import socket
        s = socket.socket()
        s.bind(('0.0.0.0', 0))
        # backlog 要给够：每次探测都会留一个未被 accept 的连接，
        # backlog=1 时第二次 connect 会被内核直接拒掉（本机真机探测不受影响）
        s.listen(10)
        port = s.getsockname()[1]
        try:
            res = self._call('dockerPortCheck', {'port': '127.0.0.1:%d' % port})
            self.assertTrue(res['status'], '已占用端口必须被判为占用')
            res = self._call('dockerPortCheck', {'port': '*:%d' % port})
            self.assertTrue(res['status'], '`*:端口` 形态同样必须判为占用')
        finally:
            s.close()

    def test_45_logout_honest(self):
        src = self._func_src('dockerLogout')
        self.assertNotIn("yf.returnJson(True, '退出失败')", src)
        self.assertIn("yf.returnJson(False, '退出失败')", src)
        self.assertIn('not removed', src)
        # 非 docker.io 的 registry 也要走到底（旧实现返回 None）
        node = self._func('dockerLogout')
        last = node.body[-1]
        self.assertIsInstance(last, ast.Return, 'dockerLogout 末尾必须是 return')

    def test_46_accelerator_validates_mirrors(self):
        src = self._func_src('set_accelerator')
        self.assertIn('MIRROR_URL_RE', src)
        self.assertIn('镜像加速器地址不合法', src)
        for bad in ('</textarea><script>alert(1)</script>', 'not-a-url', 'http://a b',
                    'file:///etc/passwd', 'javascript:alert(1)'):
            self.assertIsNone(self.mod.MIRROR_URL_RE.match(bad), '%r 不应通过' % bad)
        for ok in ('https://docker.1ms.run', 'http://mirror.gcr.io', 'https://a.b:8443/v2'):
            self.assertTrue(self.mod.MIRROR_URL_RE.match(ok), '%r 应通过' % ok)

    def test_47_migrate_paths_validated(self):
        for func in ('checkDockerMigrateSpace', 'migrateDockerDir'):
            src = self._func_src(func)
            self.assertIn('invalidDataRoot(', src)
            self.assertIn('不安全的目录路径: ', src)

    def test_48_image_load_uses_realpath(self):
        src = self._func_src('dockerImagePickLoad')
        # 目录内放一个指向 /etc/shadow 的软链就能绕过 abspath 判定
        self.assertIn('os.path.realpath(os.path.abspath(file_path))', src)
        self.assertIn('os.path.realpath(os.path.abspath(', src)

    def test_49_remove_con_drops_anonymous_volumes(self):
        src = self._func_src('dockerRemoveCon')
        self.assertIn('remove(force=True, v=True)', src)

    def test_50_image_name_whitelist(self):
        for bad in ('', '-q', 'a b', 'a;id', '$(id)', 'a`id`', 'x' * 300):
            self.assertIsNone(self.mod.IMAGE_REF_RE.match(bad), '%r 不应通过' % bad)
        for ok in ('nginx', 'nginx:latest', 'library/postgres:18.4-bookworm',
                   'registry.example.com:5000/ns/img:1.0', 'img@sha256:abc'):
            self.assertTrue(self.mod.IMAGE_REF_RE.match(ok), '%r 应通过' % ok)

    # ---------------- 7. pull_task.py 行为 ----------------
    def test_60_pull_task_rejects_bad_args(self):
        py = sys.executable
        proc = subprocess.run([py, PULL_TASK, '-q', '[]'], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertIn('invalid image name', proc.stdout + proc.stderr)
        proc = subprocess.run([py, PULL_TASK, 'nginx:latest', 'not-json'],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertIn('Error parsing mirrors JSON', proc.stdout + proc.stderr)
        proc = subprocess.run([py, PULL_TASK, 'nginx:latest', '{}'],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertIn('must be a JSON array', proc.stdout + proc.stderr)

    def test_61_pull_task_mirror_state_machine(self):
        """夹具：假 subprocess 记录 argv —— 成功节点即停、失败节点继续、全失败退出码 1"""
        harness = r'''
import json, sys, types, io
sys.argv = ['pull_task.py', 'nginx:latest', json.dumps(["https://m1", "bad mirror", "https://m2"])]
calls = []
class P:
    def __init__(self, cmd, **kw):
        calls.append(cmd)
        self.stdout = io.StringIO('log line\n')
        self.rc = 0 if cmd[2].startswith('m2/') else 1
    def wait(self):
        return self.rc
def fake_popen(cmd, **kw):
    return P(cmd, **kw)
def fake_run(cmd, **kw):
    calls.append(cmd)
    return types.SimpleNamespace(returncode=0, stderr='')
import subprocess as sp
sp.Popen = fake_popen
sp.run = fake_run
sys.path.insert(0, %r)
import importlib.util
spec = importlib.util.spec_from_file_location('pt', %r)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    mod.main()
except SystemExit as e:
    print('EXIT=%%s' %% e.code)
print('CALLS=' + json.dumps(calls))
''' % (os.path.dirname(PULL_TASK), PULL_TASK)
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as fh:
            fh.write(harness)
            path = fh.name
        try:
            proc = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=60)
        finally:
            os.remove(path)
        out = proc.stdout + proc.stderr
        self.assertIn('EXIT=0', out, out)
        self.assertIn('bad mirror', out)
        calls = json.loads([l for l in out.splitlines() if l.startswith('CALLS=')][0][6:])
        pulls = [c for c in calls if c[:2] == ['docker', 'pull']]
        self.assertEqual(len(pulls), 2, '非法节点必须被跳过（不产生 docker 调用）: %r' % pulls)
        self.assertEqual(pulls[0][2], 'm1/library/nginx:latest')
        self.assertEqual(pulls[1][2], 'm2/library/nginx:latest')
        self.assertIn(['docker', 'tag', 'm2/library/nginx:latest', 'nginx:latest'], calls)
        self.assertIn(['docker', 'rmi', 'm2/library/nginx:latest'], calls)

    # ---------------- 8. 前端 ----------------
    def test_70_js_escape_helpers_exist(self):
        self.assertIn('function dockerEsc(', self.js_src)
        self.assertIn('function dockerJsArg(', self.js_src)
        for marker in ('&amp;', '&lt;', '&gt;', '&quot;', '&#39;'):
            self.assertIn(marker, self.js_src)

    def test_71_js_con_and_image_rows_escaped(self):
        for marker in ("dockerEsc(rlist[i]['Name']",
                       "dockerEsc(rlist[i]['Config'] ? rlist[i]['Config']['Image']",
                       "dockerJsArg(rlist[i]['Config'] ? rlist[i]['Config']['Hostname']",
                       "dockerEsc(repoTags)", "dockerJsArg(repoTags)",
                       "dockerEsc(rlist[i]['address'])",
                       "dockerEsc(rlist[i]['hub_name'])",
                       "dockerJsArg(rlist[i]['registry'])"):
            self.assertIn(marker, self.js_src, '未转义: %s' % marker)
        self.assertNotIn("onclick=\"execCon(\\'' + (rlist[i]['Config']", self.js_src)
        self.assertNotIn("onclick=\"deleteIpList(\\'' + rlist[i]['address']", self.js_src)

    def test_72_js_details_escaped(self):
        for marker in ('dockerEsc(m.Source)', 'dockerEsc(m.Destination)',
                       'fullCmdEsc', 'dockerEsc(con.Config.Image)',
                       'dockerEsc(con.Name.substring(1))'):
            self.assertIn(marker, self.js_src, '未转义: %s' % marker)
        self.assertNotIn("+ fullCmd +", self.js_src)

    def test_73_js_privileged_checkbox(self):
        self.assertIn('docker-privileged', self.js_src)
        self.assertIn("privileged: $('.docker-privileged').is(':checked') ? '1' : '0'", self.js_src)
        # cgroup 挂载必须受特权勾选控制
        idx = self.js_src.find("volumes['/sys/fs/cgroup']")
        self.assertGreater(idx, 0)
        window = self.js_src[max(0, idx - 300):idx]
        self.assertIn("$('.docker-privileged').is(':checked')", window)

    def test_74_js_fail_handler(self):
        idx = self.js_src.find("/files/delete")
        self.assertGreater(idx, 0)
        window = self.js_src[idx:idx + 600]
        self.assertIn('.fail(', window, '$.post 缺少 .fail()')

    def test_76_js_escape_helpers_behavior(self):
        """node 真跑载荷：dockerEsc 不得漏出 `<`/`>`/引号，dockerJsArg 不得漏出可逃逸字符
        （只断「助手存在」挡不住「把转义改成恒等」这类回退）"""
        node = shutil.which('node')
        if not node:
            self.skipTest('本机无 node')
        script = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function dockerEsc(');
const end = src.indexOf('var _dockerConReqId');
if (start < 0 || end < 0 || end <= start) { console.log('EXTRACT_FAILED'); process.exit(0); }
eval(src.slice(start, end));
const payloads = [
    "a';alert(1);//", 'a") ; alert(2) ;//', '<img src=x onerror=alert(3)>',
    '</script><script>alert(4)</script>', 'a\\\';alert(5);//', 'a\nb', '"><script>alert(6)</script>',
    'a&b', 'a\\b', 'x`id`y', '$(id)', 'a b', '-q', '&quot;', '&#39;', 'a\\'
];
const bad = [];
for (const p of payloads) {
    const e = dockerEsc(p);
    if (/[<>"']/.test(e)) bad.push('dockerEsc:' + JSON.stringify(p) + '=>' + e);
    const j = dockerJsArg(p);
    if (/['"<>&\r\n]/.test(j)) bad.push('dockerJsArg:' + JSON.stringify(p) + '=>' + j);
    // 行内 onclick 里末尾的单个反斜杠会把闭合引号转义掉（逃出字符串字面量）
    const trailing = j.match(/\\+$/);
    if (trailing && trailing[0].length % 2 === 1) {
        bad.push('dockerJsArg-trailing-backslash:' + JSON.stringify(p) + '=>' + j);
    }
}
console.log(bad.length ? 'BAD=' + JSON.stringify(bad) : 'OK');
'''
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
            fh.write(script)
            path = fh.name
        try:
            proc = subprocess.run([node, path, DOCKER_JS], capture_output=True, text=True, timeout=120)
        finally:
            os.remove(path)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotIn('EXTRACT_FAILED', out)
        self.assertIn('OK', out, out[:600])

    def test_75_lang_keys_present(self):
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang + '.json')
            data = json.loads(_read(path))
            for key in ('请求失败', '容器名称不合法，仅允许字母、数字、下划线、点和短横线',
                        '内存配额不合法', '镜像名称不合法', '目录映射参数不合法',
                        '不允许映射宿主机敏感目录:', '不允许映射到容器根目录',
                        'IP地址池数据已损坏，请先删除 iplist.json', 'IP地址不合法',
                        '镜像加速器地址不合法', '不安全的目录路径:', '添加失败!',
                        '特权模式', '特权模式说明'):
                self.assertIn(key, data, '%s 缺少键 %r' % (lang, key))
            self.assertTrue(data.get('请求失败'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
