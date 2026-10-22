# coding: utf-8
"""已装 PHP 运行时版本的巡检采集器（P0-2）。

职责：**只读**地把「这台机器上装了哪些 PHP、各自是什么完整小版本、走的什么渠道」
采集出来，交给 `core.php_sec_baseline.evaluate()` 判定。

三条渠道分开采：
  * 编译版（`plugins/php`）：`<server>/php/<NN>/bin/php -v` / `sbin/php-fpm -v`
    的**完整版本**（不是目录名 `<NN>` —— 目录名只有大版本，这正是 P0-2 指出的缺口）；
  * apt（`plugins/php-apt`）：`/etc/php/<X.Y>` 有目录 + `dpkg-query` 的**包版本串**
    （渠道回移补丁的标记只存在于包版本串里，二进制版本看不出来）；
  * yum（`plugins/php-yum`）：`/etc/opt/remi/php<NN>` + `rpm -q` 的**包版本串**。

本模块不 import 面板运行时（`core.yf`），只依赖标准库：这样 `panel_task.py`、
Flask 视图与 testsuite 都能用同一份采集逻辑，离线（Windows 开发机）也能跑 ——
采集不到就返回空列表，判定层会给出 `empty` 态而不是告警。

内置断言口径：**读不到版本不等于达标**。二进制损坏/输出无法解析时，
`version` 留空并由判定层标成 `unknown`，绝不默认成「已达标」。
"""

import json
import os
import re
import subprocess
import time

from core import php_sec_baseline as baseline

#: 编译版安装根（面板 `yf.getServerDir() + '/php'`，默认 /www/server/php）。
DEFAULT_SERVER_PHP_DIR = '/www/server/php'
#: apt 版配置根（`plugins/php-apt/index.py::getServerDir()`）。
DEFAULT_APT_ROOT = '/etc/php'
#: yum（Remi）版配置根（`plugins/php-yum/index.py::getServerDir()`）。
DEFAULT_YUM_ROOT = '/etc/opt/remi'

#: 快照文件名（落在面板 data 目录，供首页告警卡片读取）。
SNAPSHOT_FILENAME = 'php_sec_scan.json'
#: 快照新鲜度上限：每日一次巡检 + 一天余量（超过就当没有，卡片会触发一次即时巡检）。
DEFAULT_MAX_AGE = 26 * 3600
#: 单条外部命令超时（`php -v` / `dpkg-query` 都是毫秒级，8s 已极宽）。
CMD_TIMEOUT = 8

_BRANCH_DIR_RE = re.compile(r'^\d{2}$')
_APT_DIR_RE = re.compile(r'^(\d+)\.(\d+)$')
_YUM_DIR_RE = re.compile(r'^php(\d{2})$')


def _run(argv, timeout=CMD_TIMEOUT):
    """执行命令并返回 (rc, 合并输出)。**任何异常都折成 rc!=0**，不向上抛。

    巡检是每日后台任务：一条命令异常不该让整次巡检失败（否则快照停止更新，
    前端会一直显示上一次的结果，比没有结果更误导）。
    """
    try:
        # 一律「列表 argv + shell=False」（不存在任何 shell 解析面），并就地强制转成 str：
        #   * 不拼命令行 ⇒ 天然没有注入面（这也是不对 argv 做字符串拼接的原因）；
        #   * 用推导式复制一份，避免调用方传入的可变列表在子进程运行期间被改动；
        #   * 写成推导式而不是先赋变量，是为了让 shell 拼接棘轮守卫（
        #     testsuite/test_shell_concat_ratchet.py）能静态看清「这里不是 shell 字符串」。
        p = subprocess.run([str(a) for a in argv], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or b'').decode('utf-8', 'replace')
    except Exception as e:                      # noqa: BLE001 - 见 docstring
        return 127, '%s: %s' % (e.__class__.__name__, e)


def make_runner(timeout=CMD_TIMEOUT):
    """造一个固定超时的 runner（Web 请求里用短超时，后台任务用默认值）。"""
    def _runner(argv):
        return _run(argv, timeout=timeout)
    return _runner


def read_binary_version(prefix, run=_run):
    """读某编译版安装前缀里 `bin/php -v` 或 `sbin/php-fpm -v` 的完整版本。"""
    for rel in (('bin', 'php'), ('sbin', 'php-fpm')):
        exe = os.path.join(prefix, *rel)
        if not os.path.isfile(exe):
            continue
        rc, out = run([exe, '-v'])
        ver = baseline.parse_php_version_output(out)
        if ver:
            return ver
    return ''


def read_source_version(src_dir):
    """读源码目录 `main/php_version.h` 的 `PHP_VERSION`（供安装脚本幂等逻辑复用）。"""
    path = os.path.join(src_dir, 'main', 'php_version.h')
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fp:
            return baseline.parse_source_header_version(fp.read())
    except OSError:
        return ''


def collect_compiled(server_php_dir=DEFAULT_SERVER_PHP_DIR, run=_run):
    """采集编译版（`/www/server/php/<NN>`）已装实例。"""
    out = []
    try:
        names = sorted(os.listdir(server_php_dir))
    except OSError:
        return out
    for name in names:
        if not _BRANCH_DIR_RE.match(name):
            continue
        prefix = os.path.join(server_php_dir, name)
        if not os.path.isdir(prefix):
            continue
        # 与 plugins/php/index.py::isInstalled() 同口径：有可执行文件才算装了
        if not (os.path.isfile(os.path.join(prefix, 'bin', 'php'))
                or os.path.isfile(os.path.join(prefix, 'sbin', 'php-fpm'))):
            continue
        out.append({
            'branch': name,
            'channel': 'src',
            'version': read_binary_version(prefix, run=run),
            'package_version': '',
            'path': prefix,
        })
    return out


def _apt_package_version(branch, run=_run):
    """dpkg-query 取 apt 包里 fpm/cli/common 任一已装包的版本串。"""
    ver = '%s.%s' % (str(branch)[0], str(branch)[1:])
    for pkg in ('php%s-fpm' % ver, 'php%s-cli' % ver, 'php%s-common' % ver):
        rc, out = run(['dpkg-query', '-W', '-f=${Version}', pkg])
        if rc == 0 and out.strip():
            return out.strip()
    return ''


def collect_apt(apt_root=DEFAULT_APT_ROOT, run=_run):
    """采集 apt 版（`/etc/php/<X.Y>`）已装实例：数字版本 + 包版本串（渠道标记）。"""
    out = []
    try:
        names = sorted(os.listdir(apt_root))
    except OSError:
        return out
    for name in names:
        m = _APT_DIR_RE.match(name)
        if not m:
            continue
        path = os.path.join(apt_root, name)
        if not os.path.isdir(path):
            continue
        branch = m.group(1) + m.group(2)
        pkg_ver = _apt_package_version(branch, run=run)
        num, _raw = baseline.parse_package_version(pkg_ver)
        out.append({
            'branch': branch,
            'channel': 'apt',
            'version': num,
            'package_version': pkg_ver,
            'path': path,
        })
    return out


def _yum_package_version(branch, run=_run):
    """rpm 取 Remi 包里 fpm/cli/common 任一已装包的 `版本-发布` 串。"""
    for pkg in baseline.yum_package_names(branch):
        rc, out = run(['rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', pkg])
        if rc == 0 and out.strip():
            return out.strip()
    return ''


def read_package_version(channel, branch, run=_run):
    """读 apt/yum 渠道的**包版本串**（渠道回移标记只存在于此，二进制版本看不出来）。"""
    channel = str(channel or '').strip().lower()
    if channel == 'apt':
        return _apt_package_version(str(branch), run=run)
    if channel == 'yum':
        return _yum_package_version(str(branch), run=run)
    return ''


def collect_yum(yum_root=DEFAULT_YUM_ROOT, run=_run):
    """采集 yum（Remi，`/etc/opt/remi/php<NN>`）已装实例。"""
    out = []
    try:
        names = sorted(os.listdir(yum_root))
    except OSError:
        return out
    for name in names:
        m = _YUM_DIR_RE.match(name)
        if not m:
            continue
        path = os.path.join(yum_root, name)
        if not os.path.isdir(path):
            continue
        branch = m.group(1)
        pkg_ver = _yum_package_version(branch, run=run)
        num, _raw = baseline.parse_package_version(pkg_ver)
        out.append({
            'branch': branch,
            'channel': 'yum',
            'version': num,
            'package_version': pkg_ver,
            'path': path,
        })
    return out


def scan(server_php_dir=DEFAULT_SERVER_PHP_DIR, apt_root=DEFAULT_APT_ROOT,
         yum_root=DEFAULT_YUM_ROOT, offline=False, run=_run, now=None):
    """采全三条渠道并判定，返回可直接 JSON 化的巡检结果。"""
    entries = []
    entries.extend(collect_compiled(server_php_dir, run=run))
    entries.extend(collect_apt(apt_root, run=run))
    entries.extend(collect_yum(yum_root, run=run))
    result = baseline.evaluate(entries, offline=offline)
    result['scan_time'] = int(now if now is not None else time.time())
    result['scan_time_text'] = time.strftime('%Y-%m-%d %H:%M:%S',
                                             time.localtime(result['scan_time']))
    result['summary'] = baseline.summary_text(result)
    return result


def write_snapshot(data, path):
    """原子写快照：先写 `.tmp` 再 rename，中断不会留下半个 JSON。"""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def load_snapshot(path, max_age=DEFAULT_MAX_AGE, now=None):
    """读快照；文件不存在/损坏/过期一律返回 None（调用方决定是否即时巡检）。"""
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or 'state' not in data:
        return None
    age = (now if now is not None else time.time()) - int(data.get('scan_time') or 0)
    if age > max_age or age < -3600:
        return None
    data['stale'] = False
    return data


def load_or_scan(path, max_age=DEFAULT_MAX_AGE, server_php_dir=DEFAULT_SERVER_PHP_DIR,
                 apt_root=DEFAULT_APT_ROOT, yum_root=DEFAULT_YUM_ROOT,
                 offline=False, run=_run, now=None):
    """优先读快照；没有/过期则**即时巡检一次**并把结果落盘。

    这是首页告警卡片的取数入口：正常情况下读每日巡检留下的快照（O(1)）；
    面板任务进程未运行 / 刚装完时退化成一次即时巡检（Web 侧应传短超时 runner）。
    """
    data = load_snapshot(path, max_age=max_age, now=now)
    if data is not None:
        return data
    data = scan(server_php_dir=server_php_dir, apt_root=apt_root, yum_root=yum_root,
                offline=offline, run=run, now=now)
    try:
        write_snapshot(data, path)
    except OSError as e:
        # 落盘失败不影响本次展示；下一请求会重算（这里不抛，首页不能因为写文件失败而 500）
        data['snapshot_error'] = '%s: %s' % (e.__class__.__name__, e)
    data['stale'] = True
    return data
