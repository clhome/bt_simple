# coding:utf-8
import sys
import os
import json
import re
import contextlib
import threading

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.python_yf')

UV_BIN = os.path.expanduser("~/.local/bin/uv")
#: uv 管理的解释器安装根目录（`uv python install` 的默认落点）。
#: 只有落在这里的解释器才允许卸载 —— 系统自带解释器（/usr/bin/python3.11）不在其中。
UV_PYTHON_DIR = os.path.expanduser("~/.local/share/uv/python")

#: 允许传入的版本标识：`3.13` / `3.13.14` / `cpython-3.13.14-linux-x86_64-gnu`。
#: 该值会被交给 uv 作为 --python / install / uninstall 的实参，必须白名单化
#: （旧实现直接字符串拼接，`3.9.25; touch /x` 与 `--all` 都能注入，已真机实测）。
TARGET_RE = re.compile(r'^(?:cpython-\d+\.\d+(?:\.\d+)?(?:-[a-z0-9_]+)*|\d+\.\d+(?:\.\d+)?)$')

#: uv 常规命令 / 安装（可能要下载数十 MB）的超时（秒）。
#: 旧实现不传 timeout，uv 挂住时面板 gthread 线程会被无限期占用。
_CMD_TIMEOUT = 120
_INSTALL_TIMEOUT = 900

#: 禁止作为虚拟环境父目录的目录（面板自身、系统、uv 自身的数据目录）。
#: 在这些目录下写 .venv 属于越界写入（旧实现 path 只做字符串拼接，面板根目录也能落）。
_FORBIDDEN_DIRS = (
    '/bin', '/sbin', '/lib', '/lib32', '/lib64', '/usr', '/etc', '/boot',
    '/dev', '/proc', '/sys', '/run', '/snap', '/www/server',
    '/var/lib', '/var/log', '/var/spool',
    '/root/.local', '/root/.cache', '/root/.config',
)


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    if not args:
        return tmp

    full_args_str = " ".join(args).strip()
    if (full_args_str.startswith("'") and full_args_str.endswith("'")) or (full_args_str.startswith('"') and full_args_str.endswith('"')):
        full_args_str = full_args_str[1:-1].strip()

    try:
        parsed = json.loads(full_args_str)
        if isinstance(parsed, dict):
            return parsed
    except Exception as _e:
        _log.debug('[python_yf] getArgs 异常已忽略: %s', _e)

    for arg in args:
        arg = arg.strip()
        if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
            arg = arg[1:-1].strip()
        if not arg:
            continue
        try:
            parsed = json.loads(arg)
            if isinstance(parsed, dict):
                return parsed
        except Exception as _e:
            _log.debug('[python_yf] getArgs 异常已忽略: %s', _e)
            continue

    if ":" in full_args_str:
        try:
            parts = full_args_str.split(",")
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    tmp[k.strip().strip("'").strip('"')] = v.strip().strip("'").strip('"')
        except Exception as _e:
            _log.debug('[python_yf] getArgs 异常已忽略: %s', _e)
    return tmp


VENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venvs.json')
_VENV_DIR = os.path.dirname(VENV_FILE)
_VENV_LOCK = threading.Lock()


@contextlib.contextmanager
def _venv_file_lock():
    """序列化 venvs.json 的「读-改-写」。

    面板以多 worker + 多线程运行（gthread），非原子读改写会互相覆盖：真机实测 4 个并发
    create_venv 只登记了 1 个，另外 3 个虚拟环境变成界面永远删不掉的孤儿。
    锁加在**目录**上：yf.writeFile 用 os.replace 换 inode，锁文件本身的 inode 会被换掉。
    """
    with _VENV_LOCK:
        fd = None
        try:
            import fcntl
            fd = os.open(_VENV_DIR, os.O_RDONLY)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except Exception as _e:
            if fd is not None:
                os.close(fd)
                fd = None
            _log.debug('[python_yf] 跨进程锁不可用，退化为进程内锁: %s', _e)
        try:
            yield
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception as _e:
                    _log.debug('[python_yf] 释放文件锁失败: %s', _e)
                os.close(fd)


def _normalize_venvs(data):
    """把登记表归一为 {版本标识: [绝对路径, ...]}。

    非法结构一律丢弃：venvs.json 被写成 list / 值不是数组时，旧实现的 get_venvs()
    会把整个接口打成 AttributeError（真机实测 500），字符串值还会让前端拿到半截数据。
    """
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, paths in data.items():
        if not isinstance(key, str) or not isinstance(paths, list):
            continue
        items = [p for p in paths if isinstance(p, str) and p]
        if items:
            out[key] = items
    return out


def get_venvs():
    if not os.path.exists(VENV_FILE):
        return {}
    raw = yf.readFile(VENV_FILE)
    if not raw or not isinstance(raw, str):
        return {}
    try:
        return _normalize_venvs(json.loads(raw))
    except Exception as _e:
        _log.debug('[python_yf] venvs.json 解析失败: %s', _e)
        return {}


def save_venvs(data):
    """校验后原子落盘（yf.writeFile 内部 temp + os.replace）；结构非法一律不写。"""
    return bool(yf.writeFile(VENV_FILE, json.dumps(_normalize_venvs(data), ensure_ascii=False)))


def _arg_str(args, key):
    """取字符串参数：非字符串标量转字符串，容器/布尔/None 一律视为未提供。"""
    value = args.get(key)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ''


def _valid_target(target):
    return isinstance(target, str) and bool(TARGET_RE.match(target))


def _forbidden_reals():
    """禁止目录的真实路径（两侧都做 realpath，软链与跨平台写法都拦得住）。"""
    out = []
    for base in list(_FORBIDDEN_DIRS) + [yf.getPanelDir()]:
        if not base:
            continue
        out.append(os.path.realpath(base).rstrip('/\\'))
    return out


def _safe_dir(raw):
    """校验虚拟环境的父目录，不通过返回 None。

    旧实现把 path 原样拼进 shell 与文件路径：`path='x; id'` 是命令注入，`path='/etc'`
    或面板根目录会把 .venv 写到系统/面板目录下（真机实测面板根目录也能落）。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    if any(c in raw for c in '\x00\n\r'):
        return None
    if any(part == '..' for part in raw.replace('\\', '/').split('/')):
        return None
    if not os.path.isabs(raw):
        return None
    norm = os.path.normpath(raw)
    real = os.path.realpath(norm)
    # 根目录单独拒：`realpath('/').rstrip('/\\')` 会得到空串，旧写法恒假（变异测试实测
    # 该判据是死代码，Linux 下 `path='/'` 会落到 `/.venv`）。
    root = os.path.realpath(os.sep)
    if real == root or real == root.rstrip('/\\'):
        return None
    for base in _forbidden_reals():
        if base and (real == base or real.startswith(base + os.sep)):
            return None
    if not os.path.isdir(real):
        return None
    return norm


def _run_uv(argv_tail, timeout):
    """以白名单方式调用 uv：每个实参单独 shell 转义，返回 (rc, stdout, stderr)。"""
    cmd = ' '.join([yf.shlexQuote(UV_BIN)] + [yf.shlexQuote(a) for a in argv_tail])
    return yf.execShellRc(cmd, timeout=timeout)


def _target_matches(target, item):
    """`3.13` / `3.13.14` / 完整 uv 标识 都算命中同一解释器。"""
    if target == item.get('name'):
        return True
    ver = item.get('version') or ''
    if target == ver or (ver and ver.startswith(target + '.')):
        return True
    return target.startswith('cpython-') and (item.get('name') or '').startswith(target)


def _python_list():
    """读 `uv python list --output-format json`，返回 (items, 错误文本)。

    items: [{name, version, path, managed}]；managed=解释器落在 uv 管理目录内。
    改用 JSON 而不是解析文本表格：旧实现按「最后一列是否以 / 开头」判已安装，uv 在
    部分环境下把路径缩写成 ~/.local/... 就会把已安装的版本判成未安装。
    """
    rc, out, err = _run_uv(['python', 'list', '--output-format', 'json'], _CMD_TIMEOUT)
    if rc == -1:
        return None, '操作超时，请稍后重试'
    if rc != 0:
        return None, (err or out or '').strip()
    try:
        raw = json.loads(out)
    except Exception as _e:
        _log.debug('[python_yf] uv python list 输出解析失败: %s', _e)
        return None, 'uv 输出无法解析'
    if not isinstance(raw, list):
        return None, 'uv 输出无法解析'

    managed_root = os.path.realpath(UV_PYTHON_DIR)
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get('key') or ''
        if not isinstance(name, str) or not name:
            continue
        # 与旧实现一致：只保留常规 cpython，过滤自由线程版 / pypy / graalpy
        if entry.get('implementation') != 'cpython' or entry.get('variant') == 'freethreaded':
            continue
        target = entry.get('symlink') or entry.get('path') or ''
        if not isinstance(target, str):
            target = ''
        managed = bool(target) and os.path.realpath(target).startswith(managed_root + os.sep)
        items.append({
            'name': name,
            'version': entry.get('version') or '',
            'path': target,
            'managed': managed,
        })
    return items, ''


def get_python_list():
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'python_yf.uv_not_found')

    items, err = _python_list()
    if items is None:
        return yf.returnJson(False, '获取 Python 列表失败: ' + err)

    venvs = get_venvs()
    installed = []
    available = []
    for item in items:
        if item['path']:
            item['venvs'] = venvs.get(item['name'], [])
            installed.append(item)
        else:
            available.append(item)

    data = {
        'installed': installed,
        'available': available,
        'all_versions': items
    }
    return yf.returnJson(True, 'ok', data)


def install_python():
    args = getArgs()
    version = _arg_str(args, 'version')
    if not version:
        return yf.returnJson(False, 'python_yf.specify_install_ver')
    if not _valid_target(version):
        return yf.returnJson(False, '版本标识不合法，已拒绝')
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'python_yf.uv_not_found')

    rc, out, err = _run_uv(['python', 'install', version], _INSTALL_TIMEOUT)
    output = (str(out or '') + ' ' + str(err or '')).strip()
    if rc == -1:
        return yf.returnJson(False, '操作超时，请稍后重试')
    if rc != 0:
        return yf.returnJson(False, f'安装失败: {output}')

    # 退出码为 0 也要回读确认：旧实现只看输出里有没有 "error"，uv 缺失/选项被吞时
    # 会直接回「安装任务已提交」（真机实测假成功）。
    items, _err = _python_list()
    if not items or not any(it['managed'] and _target_matches(version, it) for it in items):
        return yf.returnJson(False, f'未能确认安装结果: {output}')
    return yf.returnJson(True, 'python_yf.install_task_added')


def uninstall_python():
    args = getArgs()
    version = _arg_str(args, 'version')
    if not version:
        return yf.returnJson(False, 'python_yf.specify_uninstall_ver')
    if not _valid_target(version):
        return yf.returnJson(False, '版本标识不合法，已拒绝')
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'python_yf.uv_not_found')

    items, err = _python_list()
    if items is None:
        return yf.returnJson(False, '获取 Python 列表失败: ' + err)

    managed = [it for it in items if it['managed'] and _target_matches(version, it)]
    if not managed:
        # 系统自带或外部环境（如 /usr/bin/python3.11）：uv 不管理它，这里一律拒绝，
        # 绝不把「未安装的版本」回成「卸载成功」（真机实测 --help 也回卸载成功）。
        if any(_target_matches(version, it) for it in items):
            return yf.returnJson(False, '该 Python 为系统或外部环境，禁止卸载')
        return yf.returnJson(False, '该版本未安装，无法卸载')

    venvs = get_venvs()
    for it in managed:
        if venvs.get(it['name']):
            return yf.returnJson(False, '该版本下有关联的虚拟环境({1}个)，为了安全禁止卸载', None, len(venvs[it['name']]))

    rc, out, err = _run_uv(['python', 'uninstall'] + [it['name'] for it in managed], _CMD_TIMEOUT)
    output = (str(out or '') + ' ' + str(err or '')).strip()
    if rc == -1:
        return yf.returnJson(False, '操作超时，请稍后重试')
    if rc != 0:
        return yf.returnJson(False, f'卸载失败: {output}')

    left, _err = _python_list()
    if left is None or [it for it in left if it['managed'] and _target_matches(version, it)]:
        return yf.returnJson(False, f'未能确认卸载结果: {output}')
    return yf.returnJson(True, 'python_yf.uninstall_success')


def create_venv():
    args = getArgs()
    version = _arg_str(args, 'version')
    base_path = _arg_str(args, 'path')
    if not version or not base_path:
        return yf.returnJson(False, 'python_yf.specify_ver_path')
    if not _valid_target(version):
        return yf.returnJson(False, '版本标识不合法，已拒绝')
    base = _safe_dir(base_path)
    if base is None:
        return yf.returnJson(False, '目录路径不合法，已拒绝')
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'python_yf.uv_not_found')

    path = os.path.join(base, '.venv')
    # 项目名只作为终端提示符前缀（避免终端里全是 (.venv)），非白名单字符一律剔除以防注入
    project_name = re.sub(r'[^0-9A-Za-z._-]', '', os.path.basename(base))[:32] or 'venv'

    rc, out, err = _run_uv(['venv', path, '--python', version, '--prompt', project_name], _CMD_TIMEOUT)
    output = (str(out or '') + ' ' + str(err or '')).strip()
    if rc == -1:
        return yf.returnJson(False, '操作超时，请稍后重试')
    if os.path.exists(os.path.join(path, 'bin', 'python')):
        with _venv_file_lock():
            venvs = get_venvs()
            registered = venvs.setdefault(version, [])
            if path not in registered:
                registered.append(path)
                save_venvs(venvs)
        return yf.returnJson(True, 'python_yf.venv_create_success')
    return yf.returnJson(False, f'创建失败: {output}')


def remove_venv():
    args = getArgs()
    version = _arg_str(args, 'version')
    path = _arg_str(args, 'path')
    if not version or not path:
        return yf.returnJson(False, 'python_yf.param_error')

    venvs = get_venvs()
    if path not in venvs.get(version, []):
        return yf.returnJson(False, 'python_yf.venv_not_exists')

    if not os.path.exists(path):
        with _venv_file_lock():
            current = get_venvs()
            if path in current.get(version, []):
                current[version].remove(path)
                save_venvs(current)
        return yf.returnJson(True, 'python_yf.del_success')

    safe = _safe_dir(os.path.dirname(path))
    if safe is None or os.path.basename(path) != '.venv':
        return yf.returnJson(False, '该路径不是虚拟环境目录，未删除')
    if not (os.path.exists(os.path.join(path, 'bin', 'python')) or os.path.exists(os.path.join(path, 'pyvenv.cfg'))):
        return yf.returnJson(False, '该路径不是虚拟环境目录，未删除')

    rc, out, err = yf.execShellRc('rm -rf ' + yf.shlexQuote(path), timeout=_CMD_TIMEOUT)
    if rc == -1:
        return yf.returnJson(False, '操作超时，请稍后重试')
    # 退出码为 0 也可能是「什么都没删」，必须回读确认，否则界面报了成功而目录还在
    if os.path.exists(path):
        detail = str(err or '').strip()
        return yf.returnJson(False, f'删除失败: {detail}')

    with _venv_file_lock():
        current = get_venvs()
        if path in current.get(version, []):
            current[version].remove(path)
            save_venvs(current)
    return yf.returnJson(True, 'python_yf.del_success')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("error")
        sys.exit(0)

    func = sys.argv[1]
    if func == 'get_python_list':
        print(get_python_list())
    elif func == 'install_python':
        print(install_python())
    elif func == 'uninstall_python':
        print(uninstall_python())
    elif func == 'create_venv':
        print(create_venv())
    elif func == 'remove_venv':
        print(remove_venv())
    else:
        print('error')
