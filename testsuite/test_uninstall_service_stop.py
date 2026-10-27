# coding: utf-8
"""卸载「只删目录、不停进程」的共性守卫（2026-10-27 MySQL 现场的另一半）。

## 现场
MySQL 卸载脚本只有 `rm -rf $serverPath/mysql`，`initd_uninstall` 又只 disable 不 stop。
mysqld 带着已删除的 datadir/socket/可执行文件继续占着 3306 → 重装时 `status()` 命中僵尸
→ 初始化被跳过 → 面板 ORM 退回 TCP 连到僵尸 → 1045「数据库密码错误」。

## 同族普查结论（36 个插件，逐个看卸载入口）
各 daemon 插件都只有 `systemctl stop <unit>` / `initd stop`：**只要进程不是该 unit 起的**
（上次卸载删了 unit、手工启动、unit 改名），就杀不掉，症状与 MySQL 完全同款。
此外 `mongodb` 更是把 `rm -rf` 写在 `systemctl stop` **之前**；`pg_docker` 只删插件目录、
compose 起的容器照跑照占端口。

## 修法
新增 `scripts/lib_service_stop.sh`（纯函数，可安全 source）：
  * `yf_svc_stop_units <unit...>`：systemctl/init.d/service 三路都试；
  * `yf_kill_by_exe_prefix <dir>`：只杀「/proc/<pid>/exe 位于该目录下」的进程（TERM→KILL），
    因此**不会**误伤系统里另一套同名服务；
  * `yf_svc_rm_units <unit...>`：删 unit + daemon-reload；
  * `yf_svc_force_stop <dir> [unit...]`：组合包 + 回读是否还有残留。
各插件卸载入口在 `rm -rf` **之前**调用它。

本测试锁死：
  1. 共享库存在，且对 `/`、空串等危险路径拒绝执行；
  2. 「目录下的进程被杀，目录外的同类进程不被杀」（真跑，用真 mariadbd 冒充）；
  3. 每个 daemon 插件的卸载入口都调了 `yf_svc_force_stop`，且调用点位于 `rm -rf` 之前；
  4. pg_docker 卸载会移除容器（不再只删目录）。
"""
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')
LIB = os.path.join(ROOT, 'scripts', 'lib_service_stop.sh')

#: 有常驻服务的插件（卸载必须先停进程）
DAEMON_PLUGINS = {
    'redis': ('redis',),
    'valkey': ('valkey',),
    'mongodb': ('mongodb',),
    'gitea': ('gitea',),
    'pureftp': ('pureftp',),
    'rsyncd': ('rsyncd', 'lsyncd'),
    'supervisor': ('supervisor',),
    'sphinx': ('sphinx',),
    'postgresql': ('postgresql',),
    'openresty': ('openresty',),
    'apache': ('httpd',),
    'mysql': ('mysql',),
    'mariadb': ('mariadb',),
}

#: mysql / mariadb 的「按 exe 归属杀」实现在插件自己的 index.py 里（stop_and_kill：
#  额外识别 /proc/<pid>/exe 带 ' (deleted)' 的僵尸），比 shell 版更强，这里按等价处理。
OWN_PY_STOP = {'mysql': 'stop_and_kill', 'mariadb': 'stop_and_kill'}


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _code_only(text):
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            out.append('')
            continue
        cut = -1
        for idx, ch in enumerate(line):
            if ch == '#' and (idx == 0 or line[idx - 1] in ' \t;'):
                cut = idx
                break
        out.append(line if cut < 0 else line[:cut])
    return '\n'.join(out)


def _find_bash():
    cands = [shutil.which('bash'), '/bin/bash']
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        cands.append(os.path.join(base, 'Git', 'bin', 'bash.exe'))
    for cand in cands:
        if not cand or not os.path.exists(cand):
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo YF_OK'], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            continue
        if b'YF_OK' in proc.stdout:
            return cand
    return None


BASH = _find_bash()
WSL = shutil.which('wsl') or shutil.which('wsl.exe') if os.name == 'nt' else None


def _wsl_ok():
    if not WSL:
        return False
    try:
        proc = subprocess.run([WSL, '-d', 'Debian', '--user', 'root', '-e', 'bash', '-c',
                               'echo YF_OK'], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        return False
    return b'YF_OK' in proc.stdout


WSL_OK = _wsl_ok() if WSL else False


def _posix(path):
    p = os.path.abspath(path).replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', p):
        p = '/mnt/' + p[0].lower() + p[2:]
    return p


def _run_bash(script_text, timeout=180):
    tmp = tempfile.mkdtemp(prefix='yf_svc_')
    path = os.path.join(tmp, 'probe.sh')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(script_text)
    try:
        if WSL_OK:
            cmd = [WSL, '-d', 'Debian', '--user', 'root', '-e', 'bash', _posix(path)]
        elif BASH:
            cmd = [BASH, path]
        else:
            return None
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return proc.returncode, proc.stdout.decode('utf-8', 'replace')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. 共享库本身
# ---------------------------------------------------------------------------
class TestServiceStopLib(unittest.TestCase):

    def test_01_lib_exists_and_defines_api(self):
        self.assertTrue(os.path.isfile(LIB), '缺少 scripts/lib_service_stop.sh')
        code = _code_only(_read(LIB))
        for fn in ('yf_svc_stop_units', 'yf_kill_by_exe_prefix',
                   'yf_svc_rm_units', 'yf_svc_force_stop'):
            self.assertIn('%s()' % fn, code, '缺少函数 %s' % fn)

    def test_02_refuses_dangerous_prefix(self):
        code = _read(LIB)
        for bad in ("'' | '/'", "'/usr'", "'/bin'", "'/var'"):
            self.assertIn(bad, code, '危险路径黑名单缺少 %s' % bad)
        self.assertIn("拒绝在危险路径上按前缀杀进程", code)

    def test_03_kills_only_own_dir_real_run(self):
        """真跑：目录内的「我们的」进程被清理，目录外的同类进程不受影响。"""
        if not (WSL_OK or BASH):
            self.skipTest('没有可用 bash')
        if not os.path.exists('/usr/sbin/mariadbd') and not WSL_OK:
            self.skipTest('缺 mariadbd，跳过真跑')
        script = r'''
set -u
LIB="%(lib)s"
X=/tmp/yf_svc_lib_probe
PORT=$((4300 + RANDOM %% 200))
PORT2=$((PORT + 200))
. "$LIB"

rm -rf "$X"; mkdir -p "$X/data" "$X/other/data"
chown -R mysql:mysql "$X" 2>/dev/null
mariadb-install-db --user=mysql --datadir="$X/other/data" --basedir=/usr \
    --auth-root-authentication-method=normal >/dev/null 2>&1
chown -R mysql:mysql "$X"
/usr/sbin/mariadbd --user=mysql --basedir=/usr --datadir="$X/other/data" \
    --socket="$X/other/m.sock" --port="$PORT2" --pid-file="$X/other/p.pid" \
    --log-error="$X/other/e.log" >/dev/null 2>&1 &
FOREIGN=$!
for i in $(seq 1 30); do [ -S "$X/other/m.sock" ] && break; sleep 1; done

mkdir -p "$X/bin"
cp /usr/sbin/mariadbd "$X/bin/svc"
chmod +x "$X/bin/svc"
mariadb-install-db --user=mysql --datadir="$X/data" --basedir=/usr \
    --auth-root-authentication-method=normal >/dev/null 2>&1
chown -R mysql:mysql "$X"
"$X/bin/svc" --user=mysql --basedir=/usr --datadir="$X/data" \
    --socket="$X/m.sock" --port="$PORT" --pid-file="$X/p.pid" \
    --log-error="$X/e.log" >/dev/null 2>&1 &
OURS=$!
for i in $(seq 1 30); do [ -S "$X/m.sock" ] && break; sleep 1; done

alive() { kill -0 "$1" 2>/dev/null && echo ALIVE || echo GONE; }
echo "BEFORE ours=$(alive $OURS) foreign=$(alive $FOREIGN)"
# 模拟「卸载只删目录」：删掉可执行文件，进程仍在
rm -f "$X/bin/svc"
sleep 1
yf_kill_by_exe_prefix "$X" 1 >/dev/null 2>&1
echo "AFTER ours=$(alive $OURS) foreign=$(alive $FOREIGN)"
kill -9 "$FOREIGN" 2>/dev/null
rm -rf "$X"
''' % {'lib': _posix(LIB)}
        res = _run_bash(script)
        self.assertIsNotNone(res)
        rc, out = res
        joined = out.strip()
        self.assertIn('BEFORE ours=ALIVE foreign=ALIVE', joined, joined[-800:])
        self.assertIn('AFTER ours=GONE', joined, '目录内的进程没被清理:\n%s' % joined[-800:])
        self.assertIn('foreign=ALIVE', joined.split('AFTER')[1],
                      '目录外的同类进程被误杀了:\n%s' % joined[-800:])


# ---------------------------------------------------------------------------
# 2. 各插件卸载入口：调用点在 rm -rf 之前
# ---------------------------------------------------------------------------
class TestPluginsStopBeforeRm(unittest.TestCase):

    def _uninstall_region(self, path, name):
        code = _code_only(_read(path))
        # 取「卸载相关」的整段：从 Uninstall 函数或 action==uninstall 分支开始，到文件尾
        m = re.search(r'\n([A-Za-z_]*[Uu]ninstall[A-Za-z_]*)\s*\(\)\s*\{', code)
        if m:
            start = m.start()
        else:
            m = re.search(r'\nif \[ "\$\{?action\}?" == "uninstall" \]', code)
            self.assertIsNotNone(m, '%s 没有卸载入口' % name)
            start = m.start()
        return code[start:]

    def test_01_each_daemon_stops_before_rm(self):
        missing = []
        for name, units in DAEMON_PLUGINS.items():
            path = os.path.join(PLUGINS, name, 'install.sh')
            self.assertTrue(os.path.isfile(path), '%s 缺 install.sh' % name)
            region = self._uninstall_region(path, name)
            marker = 'yf_svc_force_stop'
            if marker not in region and OWN_PY_STOP.get(name) in region:
                marker = OWN_PY_STOP[name]
            if marker not in region:
                missing.append(name)
                continue
            idx_stop = region.index(marker)
            # 该插件的安装目录（rm -rf 目标）
            m = re.search(r'rm -rf\s+"?\$\{?serverPath\}?/%s' % re.escape(name), region)
            if m:
                self.assertLess(idx_stop, m.start(),
                                '%s 的 rm -rf 发生在停进程之前' % name)
        self.assertEqual([], missing,
                         '这些 daemon 插件卸载时没有「按 exe 归属杀残留」：%s' % missing)

    def test_02_plugins_source_the_lib(self):
        missing = []
        for name in DAEMON_PLUGINS:
            path = os.path.join(PLUGINS, name, 'install.sh')
            code = _read(path)
            if 'lib_service_stop.sh' not in code and name in OWN_PY_STOP:
                continue      # 用插件自带的 Python 版 stop_and_kill（等价实现）
            if 'lib_service_stop.sh' not in code:
                missing.append(name)
        self.assertEqual([], missing, '这些插件没有 source 共享库：%s' % missing)

    def test_03_units_are_passed(self):
        """unit 名要传对（否则 systemctl stop 白跑，只剩 exe 归属兜底）。"""
        for name, units in DAEMON_PLUGINS.items():
            code = _code_only(_read(os.path.join(PLUGINS, name, 'install.sh')))
            for unit in units:
                self.assertIn(unit, code, '%s 没有引用 unit 名 %s' % (name, unit))

    def test_04_version_scripts_stop_first(self):
        """mysql / mariadb / php 的版本脚本卸载同样要先停进程。"""
        groups = [
            ('plugins/mysql/versions', 'stop_and_kill'),
            ('plugins/mariadb/versions', 'yf_svc_force_stop'),
            ('plugins/php/versions', 'yf_svc_force_stop'),
        ]
        for rel, marker in groups:
            base = os.path.join(ROOT, rel)
            names = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
            self.assertTrue(names, '%s 下没有版本目录' % rel)
            for name in names:
                path = os.path.join(base, name, 'install.sh')
                if not os.path.isfile(path):
                    continue
                code = _code_only(_read(path))
                self.assertIn(marker, code, '%s/%s 的卸载没有先停进程' % (rel, name))

    def test_05_pg_docker_removes_containers(self):
        code = _code_only(_read(os.path.join(PLUGINS, 'pg_docker', 'install.sh')))
        region = self._uninstall_region(os.path.join(PLUGINS, 'pg_docker', 'install.sh'),
                                        'pg_docker')
        self.assertIn('docker rm -f', region,
                      'pg_docker 卸载只删目录，compose 容器会继续跑并占端口')
        idx_rm = region.index('docker rm -f')
        idx_dir = region.index('rm -rf $serverPath/pg_docker')
        self.assertLess(idx_rm, idx_dir, '要先删容器再删目录')


if __name__ == '__main__':
    unittest.main()
