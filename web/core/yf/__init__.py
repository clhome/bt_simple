# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 核心方法库
# ---------------------------------------------------------------------------------


import os


import sys


import time


import threading


import string


import json


import hashlib


import hmac


import shlex


import datetime


import subprocess


import glob


import base64


import re


import logging


from random import Random


_log = logging.getLogger('yf.core')


def safeExecShell(cmd_list, cwd=None, timeout=30, stdin_data=None):
    """
    安全的命令执行（规避命令注入）
    :param cmd_list: 命令列表，如 ['ls', '-l', '/']
    :param cwd: 工作目录
    :param timeout: 超时时间
    :param stdin_data: 需要从标准输入喂给子进程的数据（str 或 bytes）。
        **口令等敏感数据必须走这里，绝不能塞进 cmd_list** —— argv 对同机任意用户可见
        （`ps -eo args` / `/proc/<pid>/cmdline`），stdin 不会落进命令行。
    :return: (stdout, stderr) 都是 string 类型
    """
    try:
        if not isinstance(cmd_list, list):
            raise Exception("safeExecShell require a list of command arguments")

        payload = stdin_data.encode('utf-8') if isinstance(stdin_data, str) else stdin_data

        # 不使用 shell=True，直接调用
        sub = subprocess.Popen(cmd_list, cwd=cwd, stdin=subprocess.PIPE,
                               shell=False, bufsize=4096, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            data = sub.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            sub.kill()
            data = sub.communicate()
            raise Exception("Timeout：%s" % str(cmd_list))
            
        success = data[0]
        error = data[1]
        
        if isinstance(success, bytes):
            try:
                success = success.decode('utf-8')
            except Exception:
                try:
                    success = success.decode('gbk')
                except Exception:
                    success = success.decode('utf-8', errors='replace')
                
        if isinstance(error, bytes):
            try:
                error = error.decode('utf-8')
            except Exception:
                try:
                    error = error.decode('gbk')
                except Exception:
                    error = error.decode('utf-8', errors='replace')
                
        return success, error
    except Exception as e:
        return "", str(e)


_CRLF_CLEAN_CACHE = set()


def fixCrlf(file_path):
    """清洗文件中的 Windows CRLF 换行符与 BOM，保证 Linux 下正常执行"""
    global _CRLF_CLEAN_CACHE
    if file_path in _CRLF_CLEAN_CACHE:
        return False
    try:
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            if b'\r\n' in content or content.startswith(b'\xef\xbb\xbf'):
                new_content = content.replace(b'\r\n', b'\n')
                if new_content.startswith(b'\xef\xbb\xbf'):
                    new_content = new_content[3:]
                with open(file_path, 'wb') as f:
                    f.write(new_content)
                _CRLF_CLEAN_CACHE.add(file_path)
                return True
            else:
                _CRLF_CLEAN_CACHE.add(file_path)
    except Exception as _e:
        _log.debug('[yf] 记录 CRLF 已清洗文件失败: %s', _e)
    return False


def execShell(cmdstring, cwd=None, timeout=None, shell=True):
    if shell and isinstance(cmdstring, str):
        cmdstring = sanitizeCmdScripts(cmdstring, cwd=cwd)

    if shell:
        cmdstring_list = cmdstring
    else:
        cmdstring_list = shlex.split(cmdstring)
    # B602 豁免：execShell 是面板「执行 shell 命令」的核心原语，shell 由调用方决定；
    # 调用点集中在受控路径（常量 / 白名单校验后的参数），此处不改为 shell=False。
    sub = subprocess.Popen(cmdstring_list, cwd=cwd, stdin=subprocess.PIPE,
                           shell=shell, bufsize=4096, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # nosec B602  # execShell 为面板执行 shell 的核心原语

    try:
        data = sub.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        sub.kill()
        data = sub.communicate()
        raise Exception("Timeout：%s" % cmdstring)

    data = data

    success = data[0]
    error = data[1]
    # python3 fix 返回byte数据
    if isinstance(success, bytes):
        try:
            success = success.decode('utf-8')
        except Exception:
            try:
                success = success.decode('gbk')
            except Exception:
                success = success.decode('utf-8', errors='replace')

    if isinstance(error, bytes):
        try:
            error = error.decode('utf-8')
        except Exception:
            try:
                error = error.decode('gbk')
            except Exception:
                error = error.decode('utf-8', errors='replace')
    return (success, error)


def execShellRc(cmdstring, cwd=None, timeout=None, shell=True):
    """与 execShell 同样的执行语义，但额外返回子进程退出码：(rc, stdout, stderr)。

    为什么需要：execShell 的 (out, err) 契约无法区分「脚本失败」与「脚本无输出」，
    调用方只能无条件报成功（插件卸载曾因此假成功）；需要判成败的场景用本函数，
    rc 取不到时统一回 -1（err 带原因）。
    """
    if shell:
        if isinstance(cmdstring, str):
            cmdstring = sanitizeCmdScripts(cmdstring, cwd=cwd)
        cmdstring_list = cmdstring
    else:
        cmdstring_list = cmdstring if isinstance(cmdstring, (list, tuple)) else shlex.split(cmdstring)
    try:
        sub = subprocess.Popen(cmdstring_list, cwd=cwd, stdin=subprocess.PIPE,
                               shell=shell, bufsize=4096, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)  # nosec B602
        try:
            data = sub.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            sub.kill()
            sub.communicate()
            return (-1, '', 'Timeout：%s' % cmdstring)
        rc = sub.returncode
    except Exception as e:
        return (-1, '', str(e))

    out = data[0]
    err = data[1]
    for idx, raw in enumerate((out, err)):
        if isinstance(raw, bytes):
            try:
                raw = raw.decode('utf-8')
            except Exception:
                try:
                    raw = raw.decode('gbk')
                except Exception:
                    raw = raw.decode('utf-8', 'replace')
            if idx == 0:
                out = raw
            else:
                err = raw
    return (rc, out, err)


#: 路径里绝不应该出现的「垃圾片段」——mock 对象字面量与未展开的格式化占位符
# 实测现场：源码树里凭空出现了 `web/MagicMock/mock()/<id>/` 与 `web/{}/redis/data/redis.log`，
# 根因是测试 mock 未配置 / 格式化串缺参时，**生产代码不校验路径就 makedirs**，
# 把非法路径当真写进了源码树。真实运行下表现为「数据写到意外位置」，以 root 跑时尤危。
_PATH_JUNK_RE = re.compile(r'MagicMock|<MagicMock|mock\(\)')


_PATH_PLACEHOLDER_RE = re.compile(r'\{[^{}]*\}|%[sd]')


def removeDir(path):
    import shutil
    import stat

    # 递归删除是高危操作：路径非法时宁可拒绝，也不要把现场搞得更坏
    reason = invalidPathReason(path)
    if reason:
        writeFileLog('[removeDir] 拒绝删除：%s -> %r' % (reason, path))
        return False

    def _handle_remove_readonly(func, file_path, exc_info):
        try:
            os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            func(file_path)
        except Exception as e:
            _log.debug('[yf] 删除只读文件失败: %s -> %s', file_path, e)

    try:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path, onerror=_handle_remove_readonly)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                except Exception as e:
                    _log.debug('[yf] 去除只读属性失败: %s -> %s', path, e)
                os.remove(path)
        return True
    except Exception as _e:
        return False


def getTracebackInfo():
    import traceback
    return traceback.format_exc()


# 物理绝对路径锚定面板根目录 (以 core 所在的 web 目录的上级目录为基准，杜绝 os.getcwd() 漂移)
_PANEL_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def getRunDir():
    return _PANEL_ROOT_DIR


def getRootDir():
    return _PANEL_ROOT_DIR


def getPanelDir():
    return _PANEL_ROOT_DIR


def getFatherDir():
    return os.path.dirname(os.path.dirname(_PANEL_ROOT_DIR))


def getPluginDir():
    return getPanelDir() + '/plugins'


def getPanelDataDir():
    return getPanelDir() + '/data'


def getServerDir():
    parent_dir = os.path.dirname(_PANEL_ROOT_DIR)
    if os.path.basename(parent_dir) == 'server':
        return parent_dir
    return getFatherDir() + '/server'


_IS_TESTING_GITHUB = False


def getGithubProxyInfo(wait_if_testing=False):
    """
    获取最快的 GitHub 代理站信息，如果在中国境内，则进行后台测速并缓存10分钟
    返回格式：{"name": "gh-proxy.org", "url": "https://gh-proxy.org/"}
    """
    if not isChina():
        return {"name": "Direct", "url": ""}

    cache_file = getPanelTmp() + '/fastest_github_proxy.json'
    import time
    global _IS_TESTING_GITHUB
    
    cached_data = None
    # 尝试命中缓存
    if os.path.exists(cache_file):
        try:
            mtime = os.path.getmtime(cache_file)
            cached_data = getObjectByJson(readFile(cache_file))
            if time.time() - mtime < 600: # 10分钟缓存
                if cached_data and 'name' in cached_data and 'url' in cached_data:
                    return cached_data
        except Exception as e:
            _log.debug('[yf] 解析测速节点缓存失败: %s', e)

    if _IS_TESTING_GITHUB:
        if wait_if_testing:
            # 阻塞等待后台测速完成（最多等待 10 秒）
            for _ in range(100):
                if not _IS_TESTING_GITHUB:
                    break
                time.sleep(0.1)
            if os.path.exists(cache_file):
                try:
                    return getObjectByJson(readFile(cache_file))
                except Exception as e:
                    _log.debug('[yf] 读取缓存文件失败: %s -> %s', cache_file, e)
        else:
            if cached_data and 'name' in cached_data and 'url' in cached_data:
                return cached_data
            return {"name": "ghproxy.net", "url": "https://ghproxy.net/"}

    _IS_TESTING_GITHUB = True
    
    def test_speed_bg():
        global _IS_TESTING_GITHUB
        # 测速表从 _GITHUB_PROXY_LIST 派生（单一真源），
        # 避免「代理列表加了新站、测速表还是旧的」导致新站永远选不上
        test_list = {name: prefix for prefix, name in _GITHUB_PROXY_NAMED}
        
        test_url = "https://github.com/clhome/bt_simple/archive/refs/heads/master.tar.gz"
        best_speed = -1.0
        best_name = "direct"
        best_url = ""
        try:
            from core.resources import get_github_speed_limit
            speed_limit = float(get_github_speed_limit())
        except Exception:
            speed_limit = 3145728.0

        for name, prefix in test_list.items():
            try:
                full_url = prefix + test_url if prefix == "" else prefix + test_url.replace("https://", "")
                cmd = 'LC_ALL=C curl -s -L -o /dev/null -w "%{{http_code}}:%{{speed_download}}" -m 5 "{}"'.format(full_url)
                out, err = execShell(cmd)
                
                parts = out.strip().split(':')
                if len(parts) >= 2 and parts[0] in ['200', '206']:
                    speed = float(parts[1])
                    if speed > best_speed:
                        best_speed = speed
                        best_name = name
                        best_url = prefix
                    
                    if speed >= speed_limit:
                        break # 速度达标，提前退出测速
            except Exception:
                continue

        result = {"name": best_name, "url": best_url}
        try:
            cache_dir = os.path.dirname(cache_file)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
            writeFile(cache_file, getJson(result))
        except Exception as e:
            _log.debug('[yf] 写入缓存文件失败: %s -> %s', cache_file, e)
            
        _IS_TESTING_GITHUB = False
        
    import threading
    t = threading.Thread(target=test_speed_bg)
    t.start()
    
    if wait_if_testing:
        t.join(timeout=10.0)
        if os.path.exists(cache_file):
            try:
                return getObjectByJson(readFile(cache_file))
            except Exception as e:
                _log.debug('[yf] 读取缓存文件失败: %s -> %s', cache_file, e)

    if cached_data and 'name' in cached_data and 'url' in cached_data:
        return cached_data
    return {"name": "ghproxy.net", "url": "https://ghproxy.net/"}


# ---------- GitHub 代理站列表 ----------
# ⚠️ **单一真源 = 仓库根目录 `scripts/proxies.list`**（取作用域 rt / both，保持文件顺序）。
# 与脚本侧的分工：
#   * `scripts/github_download.sh` 读同一文件（shell 侧）
#   * `deploy.sh` 引导期在仓库落地前运行、读不到文件，保留内嵌副本
# 由 `testsuite/test_deploy_bootstrap.py::test_04` 守卫「文件 == deploy 内嵌 == 本列表」。
#
# 为什么强调这件事：曾经多处各写一份且**不一致**（面板侧少了 `gh.ddlc.top`），
# 结果是「同一个包在脚本里下得动、在面板里下不动」，极难排查。
# 中国大陆直连 GitHub 经常失败，本列表是可用性的生命线，只许增不许减。
_PROXY_LIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'scripts', 'proxies.list')


def _load_github_proxy_list():
    """从 `scripts/proxies.list` 读取运行时回退顺序（rt / both）。

    读不到 / 解析为空时退化为「仅官方直连」，绝不因清单缺失而卡死下载。
    """
    items = []
    try:
        with open(_PROXY_LIST_FILE, 'r', encoding='utf-8') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) < 3:
                    continue
                if parts[2].strip() in ('rt', 'both'):
                    items.append(parts[1].strip())
    except OSError:
        items = []
    return items or ['']


_GITHUB_PROXY_LIST = _load_github_proxy_list()


def _proxy_display_name(prefix):
    """把代理前缀转成用于展示/测速的名字（`''` -> direct）。"""
    if not prefix:
        return 'direct'
    return prefix.rstrip('/').replace('https://', '').replace('http://', '')


#: 带名字的代理表，**由上面单一真源派生**，避免「列表改了、测速表没改」的漂移
_GITHUB_PROXY_NAMED = [(p, _proxy_display_name(p)) for p in _GITHUB_PROXY_LIST]


def returnData(status, msg, data=None, *args):
    # 空消息或非字符串快速短路，0ms 直出（大幅提升底层数据管道性能）
    if not msg or not isinstance(msg, str) or not msg.strip():
        if data is None:
            return {'status': status, 'msg': msg}
        return {'status': status, 'msg': msg, 'data': data}

    try:
        from core.i18n import t as _t
        translated_msg = _t(msg, *args)
    except Exception:
        translated_msg = msg

    if data is None:
        return {'status': status, 'msg': translated_msg}
    return {'status': status, 'msg': translated_msg, 'data': data}


def readFile(filename):
    # 读文件内容
    try:
        with open(filename, 'r', encoding='utf-8') as fp:
            fBody = fp.read()
        return fBody
    except Exception as e:
        # print('readFile:',str(e))
        return False


def writeFile(filename, content, mode='w+'):
    # 写文件内容 (覆写模式支持原子落盘，防止断电/OOM/磁盘满导致文件截断为0字节)
    # 关键配置落盘后追加 size>0 二次校验，区分 ENOSPC 场景
    try:
        parent_dir = os.path.dirname(filename)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        if mode in ('w', 'w+'):
            temp_file = filename + f".tmp.{os.getpid()}_{int(time.time()*1000)}"
            try:
                with open(temp_file, mode, encoding='utf-8') as fp:
                    fp.write(content)
                    fp.flush()
                    try:
                        os.fsync(fp.fileno())
                    except Exception as _e:
                        writeFileLog('[yf.writeFile] fsync 失败: %s -> %s' % (filename, _e))
                os.replace(temp_file, filename)
                # 二次校验：非空内容落盘后文件必须 >0，否则视为 ENOSPC/截断失败
                if content is not None and content != '':
                    try:
                        if os.path.getsize(filename) == 0 and len(str(content)) > 0:
                            writeFileLog(f"[writeFile] zero-size after replace: {filename} content_len={len(str(content))}\n{getTracebackInfo()}")
                            return False
                    except Exception as _e:
                        writeFileLog('[yf.writeFile] 校验替换结果失败: %s -> %s' % (filename, _e))
                return True
            except Exception as write_err:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as _e:
                        writeFileLog('[yf.writeFile] 清理临时文件失败: %s -> %s' % (temp_file, _e))
                # ENOSPC / 配额错误带文件名打日志，便于排障
                try:
                    import errno as _errno
                    err_no = getattr(write_err, 'errno', None)
                    tag = f" errno={err_no}({os.strerror(err_no) if err_no else ''})" if err_no else ""
                    writeFileLog(f"[writeFile] {filename}{tag}: {write_err}\n{getTracebackInfo()}")
                except Exception as _e:
                    writeFileLog(f"[writeFile] {filename}: {write_err}\n{getTracebackInfo()}")
                raise write_err
        else:
            with open(filename, mode, encoding='utf-8') as fp:
                fp.write(content)
            return True
    except Exception as e:
        # 顶层兜底已在内层打过日志，此处仅补充一次
        try:
            writeFileLog(f"[writeFile] {filename} failed: {e}\n{getTracebackInfo()}")
        except Exception as _e:
            writeFileLog(getTracebackInfo())
        return False


def systemdCfgDir():
    # ubuntu
    cfg_dir = '/lib/systemd/system'
    if os.path.exists(cfg_dir):
        return cfg_dir

    # debian,centos
    cfg_dir = '/usr/lib/systemd/system'
    if os.path.exists(cfg_dir):
        return cfg_dir

    # local test
    return "/tmp"


def hasPwd(password):
    '''
    加密密码字符
    '''
    try:
        import bcrypt
        salt = bcrypt.gensalt()
        hpw = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hpw.decode('utf-8')
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode('utf-8')).hexdigest()


def getHost(port=False):
    from flask import request
    host_tmp = request.headers.get('host')
    if not host_tmp:
        if request.url_root:
            tmp = re.findall(r"(https|http)://([\w:\.-]+)", request.url_root)
            if tmp:
                host_tmp = tmp[0][1]
    if not host_tmp:
        host_tmp = getLocalIp() + ':' + readFile('data/port.pl').strip()
    try:
        if host_tmp.find(':') == -1:
            host_tmp += ':80'
    except Exception as _e:
        host_tmp = "127.0.0.1:8888"
    h = host_tmp.split(':')
    if port:
        return h[-1]
    return ':'.join(h[0:-1])


def getClientIp():
    from flask import request
    try:
        remote_ip = (request.remote_addr or '127.0.0.1').replace('::ffff:', '')
        # 当直接请求来源于本地回环或内网私网反向代理时，安全提取穿透转发头，防误封 127.0.0.1
        is_proxy_source = False
        import ipaddress
        try:
            ip_obj = ipaddress.ip_address(remote_ip)
            is_proxy_source = ip_obj.is_loopback or ip_obj.is_private
        except Exception as _e:
            if remote_ip in ('127.0.0.1', 'localhost', '::1'):
                is_proxy_source = True

        if is_proxy_source:
            forwarded = request.headers.get('X-Forwarded-For', '').strip()
            if forwarded:
                candidate = forwarded.split(',')[0].strip().replace('::ffff:', '')
                try:
                    ipaddress.ip_address(candidate)
                    return candidate
                except Exception as _e:
                    _log.debug('[yf] X-Forwarded-For 非合法 IP，忽略: %s -> %s', candidate, _e)

            real_ip = request.headers.get('X-Real-IP', '').strip().replace('::ffff:', '')
            if real_ip:
                try:
                    ipaddress.ip_address(real_ip)
                    return real_ip
                except Exception as _e:
                    _log.debug('[yf] X-Real-IP 非合法 IP，忽略: %s -> %s', real_ip, _e)

        return remote_ip
    except Exception:
        return '127.0.0.1'


def getJson(data):
    import json
    try:
        return json.dumps(data)
    except Exception:
        return json.dumps(data, default=str)


def getOs():
    # python3 -c 'import sys; print(sys.platform)'
    return sys.platform


def getHostAddr():
    ip_text = getPanelDataDir() + '/iplist.txt'
    if os.path.exists(ip_text):
        return readFile(ip_text).strip()
    return '127.0.0.1'


_LANG_CACHE = {'mtime': 0, 'lang': 'zh-CN'}


def getLanguage():
    try:
        from core.i18n import get_current_lang
        return get_current_lang()
    except Exception as e:
        _log.debug('[yf] i18n 当前语言获取失败，回退文件读取: %s', e)

    global _LANG_CACHE
    panel_dir = getPanelDir()
    path = panel_dir+'/data/language.pl'
    if not os.path.exists(path):
        return 'zh-CN'
    try:
        mtime = os.path.getmtime(path)
        if mtime == _LANG_CACHE['mtime']:
            return _LANG_CACHE['lang']
        
        lang = readFile(path).strip()
        _LANG_CACHE['mtime'] = mtime
        _LANG_CACHE['lang'] = lang
        return lang
    except Exception:
        return 'zh-CN'


import functools


@functools.lru_cache(maxsize=128)
def _getCachedStaticJson(name, lang):
    try:
        from core.i18n import get_cached_json
        return get_cached_json(name, lang)
    except Exception as e:
        _log.debug('[yf] i18n 静态 JSON 缓存获取失败，回退文件读取: %s', e)
    file = 'static/language/' + lang + '/' + name + '.json'
    if not os.path.exists(file):
        file = 'static/language/zh-CN/' + name + '.json'
    try:
        return json.loads(readFile(file))
    except Exception as _e:
        return {}


    
def getInfo(msg, args=()):
    # 取提示消息
    for i in range(len(args)):
        rep = '{' + str(i + 1) + '}'
        msg = msg.replace(rep, args[i])
    return msg


def isAppleSystem():
    if getOs() == 'darwin':
        return True
    return False


def isSupportSystemctl():
    if isAppleSystem():
        return False
    if isDocker():
        return False

    current_os = getOs()
    if current_os.startswith("freebsd"):
        return False
    return True


def isDebugMode():
    if isAppleSystem():
        return True

    debug = M('option').field('name').where('name=?',('debug',)).getField('value')
    if debug == 'open':
        return True
    return False


def writeLog(stype, msg, args=()):
    """写操作日志（面向界面）。

    同时**落审计流水**（append-only + 哈希链），从而让已有的 120 处
    `writeLog` 调用点无需逐个改造就获得完整审计覆盖。
    """
    uid, username, ip = _logIdentity()
    ok = writeDbLog(stype, msg, args, uid, ip=ip)

    try:
        from core import audit
        audit.write_audit(action=stype, target='', result='ok',
                          detail=getInfo(msg, args), uid=uid, username=username)
    except Exception as exc:
        # 审计失败不能拖垮业务操作，但也不能完全无声（否则审计静默失效无人察觉）
        writeFileLog('writeLog 审计落库失败: %s' % exc)
    return ok


#: 面板日志写入锁：gunicorn 多线程下避免同时轮转导致 os.rename 竞争（文件已被
#: 另一个线程改名时第二次 rename 会抛 FileNotFoundError，进而把调用方弄崩）。
_WRITE_LOG_LOCK = threading.Lock()


def writeFileLog(msg, path=None, limit_size=50 * 1024 * 1024, save_limit=3):
    log_file = getPanelDir() + '/logs/debug.log'
    if path != None:
        log_file = path

    with _WRITE_LOG_LOCK:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            if size > limit_size:
                log_file_rename = log_file + "_" + \
                    time.strftime("%Y-%m-%d_%H%M%S") + '.log'
                try:
                    os.rename(log_file, log_file_rename)
                    logs = sorted(glob.glob(log_file + "_*"))
                    count = len(logs)
                    save_limit = count - save_limit
                    for i in range(count):
                        if i > save_limit:
                            break
                        try:
                            os.remove(logs[i])
                        except OSError as e:
                            # 文件已不存在/被占用：跳过，不影响本次写入
                            _log.debug('[yf] 清理旧日志失败: %s -> %s', logs[i], e)
                except OSError as e:
                    # 轮转失败不能阻断写日志（否则日志丢了、调用方也可能被弄崩）
                    _log.debug('[yf] 轮转日志失败: %s -> %s', log_file, e)

        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        f = open(log_file, 'ab+')
        msg += "\n"
        if __name__ == '__main__':
            print(msg)
        f.write(msg.encode('utf-8'))
        f.close()
    return True


# ---------------------------------------------------------------------------------
# 文件操作进度：内存态（第 0 层磁盘 I/O 治理）
# 原实现每次进度变化都落盘 data/panel_speed.pl（批量删除/复制/清空回收站时
# 产生持续的小文件写放大）。生产环境 workers=1（Flask-SocketIO 约束），
# 进度生产者 web/utils/file.py 与消费者 /files 接口处于同一进程，
# 因此改为纯内存状态，彻底消除该写放大。
# ---------------------------------------------------------------------------------
_SPEED_LOCK = threading.Lock()


_SPEED_STATE = {'title': None, 'progress': 0, 'total': 0, 'used': 0, 'speed': 0}


def M(table=''):
    import core.db as db
    sql = db.Sql()
    if table == '':
        return sql
    return sql.table(table)


def deDoubleCrypt(key, strings):
    # 解密字符串
    try:
        import base64
        from cryptography.fernet import Fernet, InvalidToken
        
        if type(strings) != bytes:
            strings = strings.encode('utf-8')

        try:
            from core.crypt_salt import get_salt
            salt = get_salt()
        except Exception as _e:
            salt = None

        if salt:
            composite_key = key + salt
            _key = md5(composite_key).encode('utf-8')
            _key = base64.urlsafe_b64encode(_key)
            try:
                f = Fernet(_key)
                result = f.decrypt(strings).decode('utf-8')
                return result
            except InvalidToken:
                _log.debug('[yf] Fernet(盐) 解密失败，回退无盐 key')

        _key = md5(key).encode('utf-8')
        _key = base64.urlsafe_b64encode(_key)
        f = Fernet(_key)
        result = f.decrypt(strings).decode('utf-8')
        return result
    except Exception as _e:
        writeFileLog(getTracebackInfo())
        return strings


_aes_key_cache = None


def getAesKey():
    global _aes_key_cache
    if _aes_key_cache:
        return _aes_key_cache
    
    aes_file = getPanelDataDir() + '/aes.json'
    if os.path.exists(aes_file):
        try:
            with open(aes_file, 'r') as f:
                _aes_key_cache = json.loads(f.read())
                return _aes_key_cache
        except Exception as _e:
            _log.debug('[yf] 读取 AES key 缓存失败: %s', _e)
            
    key = getRandomString(16)
    vi = getRandomString(16)
    _aes_key_cache = {'key': key, 'vi': vi}
    try:
        with open(aes_file, 'w') as f:
            f.write(json.dumps(_aes_key_cache))
    except Exception as _e:
        _log.debug('[yf] 写入 AES key 缓存失败: %s', _e)
    return _aes_key_cache


_HTTP_POOL = None            # 验证证书的连接池（默认路径）


_HTTP_POOL_INSECURE = None   # 不验证证书的连接池（降级兼底：老系统 CA 缺失时）


_HTTP_POOL_LOCK = None


def _get_http_pool(insecure=False):
    global _HTTP_POOL, _HTTP_POOL_INSECURE, _HTTP_POOL_LOCK
    cached = _HTTP_POOL_INSECURE if insecure else _HTTP_POOL
    if cached is not None:
        return cached
    try:
        import threading as _th
        if _HTTP_POOL_LOCK is None:
            _HTTP_POOL_LOCK = _th.Lock()
        with _HTTP_POOL_LOCK:
            cached = _HTTP_POOL_INSECURE if insecure else _HTTP_POOL
            if cached is not None:
                return cached
            try:
                import urllib3 as _u3
                _u3.disable_warnings()
                _timeout = _u3.Timeout(connect=5, read=10)
                if insecure:
                    pool = _u3.PoolManager(cert_reqs='CERT_NONE', retries=False,
                                           timeout=_timeout, maxsize=32, block=True,
                                           ssl_context=_insecure_ssl_context())
                    _HTTP_POOL_INSECURE = pool
                else:
                    # 验证优先：使用系统/urllib3 默认 CA 束
                    pool = _u3.PoolManager(cert_reqs='CERT_REQUIRED', retries=False,
                                           timeout=_timeout, maxsize=32, block=True)
                    _HTTP_POOL = pool
                return pool
            except Exception:
                if insecure:
                    _HTTP_POOL_INSECURE = False
                else:
                    _HTTP_POOL = False
                return None
    except Exception:
        return None


def httpGet(url, timeout=10):
    return HttpGet2(url, timeout)


def httpPost(url, data, timeout=10):
    return HttpPost(url, data, timeout)


def isVaildIpV6(ip):
    import ipaddress
    try:
        ipaddress.IPv6Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False


_reload_timer = None


_reload_lock = threading.Lock()


def opWeb(method):
    if not isInstalledWeb():
        return False
        
    global _reload_timer
    if method == 'reload':
        with _reload_lock:
            if _reload_timer:
                _reload_timer.cancel()
            _reload_timer = threading.Timer(1.5, _do_reload)
            _reload_timer.start()
        return True

    # systemd
    systemd = systemdCfgDir() + '/openresty.service'
    if os.path.exists(systemd):
        execShell('systemctl ' + method + ' openresty')
        return True


    sys_initd = '/etc/init.d/openresty'
    if os.path.exists(sys_initd):
        allowed_ops = ('reload', 'restart', 'stop', 'start', 'status')
        if method not in allowed_ops:
            method = 'reload'
        safeExecShell([sys_initd, method])
        return True

    # initd
    initd = getServerDir() + '/openresty/init.d/openresty'
    if os.path.exists(initd):
        execShell(initd + ' ' + method)
        return True

    return False


def createRsa():
    ssh_dir = getSshDir()
    if not os.path.exists(ssh_dir + '/authorized_keys'):
        execShell('touch ' + ssh_dir + '/authorized_keys')

    if not os.path.exists(ssh_dir + '/id_rsa.pub') and os.path.exists(ssh_dir + '/id_rsa'):
        execShell('echo y | ssh-keygen -q -t rsa -P "" -f ' +
                  ssh_dir + '/id_rsa')
    else:
        execShell('ssh-keygen -q -t rsa -P "" -f ' + ssh_dir + '/id_rsa')

    execShell('cat ' + ssh_dir + '/id_rsa.pub >> ' +
              ssh_dir + '/authorized_keys')
    execShell('chmod 600 ' + ssh_dir + '/authorized_keys')


_NOTIFY_MEMORY_LOCK = {}


def notifyMessageTry(msg, stype='common', trigger_time=300, is_write_log=True):
    global _NOTIFY_MEMORY_LOCK
    now = time.time()

    if stype in _NOTIFY_MEMORY_LOCK:
        diff_time = now - _NOTIFY_MEMORY_LOCK[stype]['do_time']
        if diff_time >= trigger_time:
            _NOTIFY_MEMORY_LOCK[stype]['do_time'] = now
        else:
            return False
    else:
        _NOTIFY_MEMORY_LOCK[stype] = {'do_time': now}

    if is_write_log:
        writeLog("通知管理[" + stype + "]", msg)

    data = getNotifyData(True)
    # tag_list = ['tgbot', 'email']
    # tagbot
    do_notify = False
    if 'tgbot' in data and 'enable' in data['tgbot']:
        if data['tgbot']['enable']:
            t = data['tgbot']['data']
            i = sys.version_info

            # telebot 在python小于3.7无法使用
            if i[0] < 3 or i[1] < 7:
                do_notify = tgbotNotifyHttpPost(
                    t['app_token'], t['chat_id'], msg)
            else:
                do_notify = tgbotNotifyMessage(
                    t['app_token'], t['chat_id'], msg)

    if 'email' in data and 'enable' in data['email']:
        if data['email']['enable']:
            t = data['email']['data']
            t['subject'] = 'MW通知'
            t['content'] = msg
            do_notify = emailNotifyMessage(t)
    return do_notify


# ---------------------------------------------------------------------------------
# 打印相关 END
# ---------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------
# 进程管理与存活检测
# ---------------------------------------------------------------------------------

def checkPid(pid):
    """
    检查指定 PID 进程是否存在并存活
    :param pid: 进程 PID (int 或 str)
    :return: bool (True: 存活, False: 不存在或已退出)
    """
    try:
        if not pid:
            return False
        pid = int(str(pid).strip())
        if pid <= 0:
            return False

        # Windows 开发机环境兼容
        if sys.platform == 'win32':
            try:
                import psutil
                return psutil.pid_exists(pid)
            except Exception:
                return False

        # Linux / POSIX 标准环境
        # 1. /proc 伪文件系统直接探测（零阻塞，准确直接）
        proc_path = f"/proc/{pid}"
        if os.path.exists(proc_path):
            return True

        # 2. os.kill(pid, 0) 发送空信号探测
        try:
            os.kill(pid, 0)
            return True
        except OSError as err:
            import errno
            # errno.EPERM 说明进程存在但属于更高权限用户 (如 root)，依然视为存活
            return err.errno == errno.EPERM
    except Exception:
        return False


def syncPidFile(pid_file, pid):
    """
    把存活 PID 安全写回守护进程的 pid 文件（供面板的「状态自愈」使用）。

    为什么不直接用 writeFile：pid 文件往往属于**另一个用户**运行的守护进程
    （例：MySQL 由 systemd 以 User=mysql 启动，datadir 为 750 mysql:mysql，
    pid 文件由 mysqld 自己创建维护）。面板以 root 运行，直接写会替换 inode 并把
    属主改成 root，于是 mysqld 下次启动**无法创建自己的 pid 文件**而启动失败
    （真机实测 P0：Can't create/write to file '.../mysql.pid' (Errcode: 13 -
    Permission denied)，服务被留在 failed）。

    安全规则（任一不满足即放弃写入；只放弃「快速探针」优化，不影响状态判定正确性）：
      1. 目录不存在 -> 不写（状态检查不该顺手造目录）；
      2. 目录属主不是当前用户 -> 不写（里面可能是别人的守护进程文件）；
      3. 文件已存在且属主不是当前用户 -> 不写（绝不改属主）。
    :param pid_file: pid 文件路径
    :param pid: 存活 PID
    :return: True 表示已写入或已是目标值；False 表示按规则跳过
    """
    try:
        if not pid_file or not pid:
            return False
        geteuid = getattr(os, 'geteuid', None)
        if geteuid is None:
            # Windows 开发机没有 uid 概念，交由调用方自身逻辑处理
            return False
        euid = geteuid()
        p_dir = os.path.dirname(pid_file) or '.'
        if not os.path.isdir(p_dir):
            return False
        if os.stat(p_dir).st_uid != euid:
            return False
        if os.path.exists(pid_file) and os.stat(pid_file).st_uid != euid:
            return False
        if os.path.exists(pid_file):
            try:
                if readFile(pid_file).strip() == str(pid):
                    # 已是目标值：不重复写盘（status 会被高频轮询）
                    return True
            except Exception as _e:
                _log.debug('[yf] syncPidFile 读取现有 pid 失败，继续写入: %s', _e)
        writeFile(pid_file, str(pid))
        return True
    except Exception as _e:
        _log.debug('[yf] syncPidFile 跳过（安全规则或异常）: %s', _e)
        return False


from . import fileio
from .fileio import backFile, getCommonFile, getFileMd5, getFileStatsDesc, getPathSize, readFileEnd, removeBackFile, restoreFile, sortAllFileList, sortFileList
from . import github
from .github import _makeGithubProxyUrl, getGithubProxy, getGithubProxyName, getSpeed, githubDownload, writeSpeed
from . import paths
from .paths import getAcmeDir, getAcmeDomainDir, getBackupDir, getLogsDir, getNotifyPath, getPanelLogs, getPanelPort, getPanelTaskExecLog, getPanelTaskLog, getPanelTaskPidFile, getPanelTmp, getRecycleBinDir, getSqitePrefix, getSshDir, getTriggerTaskLockFile, getWwwDir, getYfLogs, setBackupDir
from . import security
from .security import aesDecrypt, aesEncrypt, checkPwd, checkPwdCompat, enDoubleCrypt, encodeImage, isLegacyPwdHash, md5
from . import shell
from .shell import buildSoftLink, checkBinExist, checkPort, createLinuxUser, deleteFile, getGlibcVersion, invalidPathReason, isOpenPort, makeDirs, processExists, sanitizeCmdScripts, setMode, setOwn, shlexQuote, shlex_quote
from . import textutil
from .textutil import formatDate, getDataFromInt, getDate, getDateFromNow, getDefault, getFileSuffix, getLastLine, getPathSuffix, getRandomString, getStrBetween, getUniqueId, inArray, isNumber, strfDate, strfToTime, toSize
from . import log
from .log import _logIdentity, debugLog, echoEnd, echoInfo, echoStart, returnJson, returnMsg, userSafeError, verifyAuditChain, writeAudit, writeDbLog
from . import net
from .net import HttpGet, HttpGet2, HttpPost, _insecure_ssl_context, _pool_request, checkCert, checkIp, clearSsh, connectSsh, createLocalSSL, createSshInfo, getHostPort, getLocalIp, getSSHPort, getSSHStatus, getSslCrt, isIpAddr, isVaildIp, isVaildIpV4, setHostPort
from . import panel
from .panel import _do_reload, checkHttpdConfig, checkWebConfig, emailNotifyMessage, emailNotifyTest, getFpmAddress, getFpmConfFile, getMyORM, getNotifyData, getOpVer, getWebStatus, initNotifyConfig, isInstalledWeb, isRestart, notifyMessage, opLuaInitAccessFile, opLuaInitFile, opLuaInitWorkerFile, opLuaMake, opLuaMakeAll, panelCmd, requestFcgiPHP, restartPanel, restartTask, restartWeb, tgbotNotifyChatID, tgbotNotifyHttpPost, tgbotNotifyMessage, tgbotNotifyObject, tgbotNotifyTest, triggerTask, wakePanelTask, writeNotify
from . import system
from .system import checkDomainPanel, fileNameCheck, getCertName, getCpuType, getObjectByJson, getOsID, getOsName, getPage, getPageObject, getStaticJson, getSystemDeviceTemperature, isChina, isDocker, isSupportHttp3, isVhostHasReuseport, isYufengPanel
