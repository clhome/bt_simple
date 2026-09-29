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

from random import Random

def safeExecShell(cmd_list, cwd=None, timeout=30):
    """
    安全的命令执行（规避命令注入）
    :param cmd_list: 命令列表，如 ['ls', '-l', '/']
    :param cwd: 工作目录
    :param timeout: 超时时间
    :return: (stdout, stderr) 都是 string 类型
    """
    try:
        if not isinstance(cmd_list, list):
            raise Exception("safeExecShell require a list of command arguments")
        
        # 不使用 shell=True，直接调用
        sub = subprocess.Popen(cmd_list, cwd=cwd, stdin=subprocess.PIPE,
                               shell=False, bufsize=4096, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            data = sub.communicate(timeout=timeout)
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
        pass
    return False

def sanitizeCmdScripts(cmdstring, cwd=None):
    """自愈检测：分析命令中涉及的脚本文件，若包含 CRLF 自动清洗为 LF（带内存缓存，避免重复 I/O）"""
    try:
        if not isinstance(cmdstring, str):
            return cmdstring
        if not ('.py' in cmdstring or '.sh' in cmdstring or '.tpl' in cmdstring):
            return cmdstring
        import re
        matches = re.findall(r'[\w\-\./]+\.(?:sh|py|tpl)', cmdstring)
        if not matches:
            return cmdstring

        # 快速判断：如果所有 match 都已在缓存中，直接穿透
        if all(m in _CRLF_CLEAN_CACHE for m in matches):
            return cmdstring

        cd_matches = re.findall(r'cd\s+([^\s&;]+)', cmdstring)
        base_dir = cd_matches[0] if cd_matches else cwd

        panel_dir = getPanelDir() if 'getPanelDir' in globals() else '/www/server/yufeng_panel'

        for match in matches:
            candidates = [match]
            if base_dir:
                candidates.append(os.path.join(base_dir, match))
            if not match.startswith('/'):
                candidates.append(os.path.join(panel_dir, match))

            for file_path in candidates:
                if file_path in _CRLF_CLEAN_CACHE:
                    continue
                if os.path.isfile(file_path):
                    fixCrlf(file_path)
    except Exception as _e:
        pass
    return cmdstring

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

def shlexQuote(s):
    # 安全的 shell 转义
    import shlex
    return shlex.quote(str(s))

#: 路径里绝不应该出现的「垃圾片段」——mock 对象字面量与未展开的格式化占位符
# 实测现场：源码树里凭空出现了 `web/MagicMock/mock()/<id>/` 与 `web/{}/redis/data/redis.log`，
# 根因是测试 mock 未配置 / 格式化串缺参时，**生产代码不校验路径就 makedirs**，
# 把非法路径当真写进了源码树。真实运行下表现为「数据写到意外位置」，以 root 跑时尤危。
_PATH_JUNK_RE = re.compile(r'MagicMock|<MagicMock|mock\(\)')
_PATH_PLACEHOLDER_RE = re.compile(r'\{[^{}]*\}|%[sd]')


def invalidPathReason(path):
    """返回路径被拒绝的原因；`None` 表示放行。

    刻意**不**要求「必须是绝对路径」：有些合法调用会传相对路径，
    一刀切会误伤。这里只拦「无论怎么解释都不可能是合法目录」的输入。
    """
    if not isinstance(path, str):
        return '路径不是字符串（实际是 %s）' % type(path).__name__
    if not path.strip():
        return '路径为空'
    if _PATH_JUNK_RE.search(path):
        return '路径含 mock/测试对象字面量'
    if _PATH_PLACEHOLDER_RE.search(path):
        return '路径含未展开的格式占位符'
    normalized = os.path.normpath(path)
    if normalized in ('/', os.sep, '//', '.'):
        return '路径为文件系统根'
    if re.fullmatch(r'[A-Za-z]:[\\/]', path):
        return '路径为盘符根'
    return None


def makeDirs(path):
    reason = invalidPathReason(path)
    if reason:
        # 不静默：否则现场只剩一个莫名其妙的目录，排查成本极高
        writeFileLog('[makeDirs] 拒绝创建目录：%s -> %r' % (reason, path))
        return False
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as _e:
        return False

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
        except Exception:
            pass

    try:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path, onerror=_handle_remove_readonly)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
                os.remove(path)
        return True
    except Exception as _e:
        return False

def checkBinExist(name):
    import shutil
    if shutil.which(name):
        return True
    d = execShell('which ' + name)
    if d[0] != '':
        return True
    return False



def getTracebackInfo():
    import traceback
    return traceback.format_exc()

# 物理绝对路径锚定面板根目录 (以 core 所在的 web 目录的上级目录为基准，杜绝 os.getcwd() 漂移)
_PANEL_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

def getYfLogs():
    return getPanelDir() + '/logs'

def getPanelLogs():
    return getPanelDir() + '/logs'

def getPanelTmp():
    return getPanelDir() + '/tmp'

def getServerDir():
    parent_dir = os.path.dirname(_PANEL_ROOT_DIR)
    if os.path.basename(parent_dir) == 'server':
        return parent_dir
    return getFatherDir() + '/server'

def getLogsDir():
    return getFatherDir() + '/wwwlogs'

def getRecycleBinDir():
    rb_dir = getFatherDir() + '/recycle_bin'
    if not os.path.exists(rb_dir):
        os.makedirs(rb_dir, exist_ok=True)
    return rb_dir

def getPanelTaskLog():
    return getYfLogs() + '/panel_task.log'

def getPanelTaskExecLog():
    return getYfLogs() + '/panel_exec.log'

def getWwwDir():
    import thisdb
    site_path = thisdb.getOption('site_path', default=getFatherDir()+'/wwwroot')
    return site_path

def getBackupDir():
    import thisdb
    backup_path = thisdb.getOption('backup_path', default=getFatherDir()+'/backup')
    return backup_path

def setBackupDir(bdir):
    import thisdb
    thisdb.setOption('backup_path', bdir)
    return True

def getPanelPort():
    port_file = getPanelDir()+'/data/port.pl'
    port = readFile(port_file).strip()
    if not port:
        return 7200
    return int(port)

def shlex_quote(arg):
    return shlex.quote(arg)

def getRandomString(length):
    # 取随机字符串
    rnd_str = ''
    chars = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789'
    chrlen = len(chars) - 1
    random = Random()
    for i in range(length):
        rnd_str += chars[random.randint(0, chrlen)]
    return rnd_str


def getUniqueId():
    """
    根据时间生成唯一ID
    :return:
    """
    current_time = datetime.datetime.now()
    str_time = current_time.strftime('%Y%m%d%H%M%S%f')[:-3]
    unique_id = "{0}".format(str_time)
    return unique_id

def getDate():
    # 取格式时间
    import time
    return time.strftime('%Y-%m-%d %X', time.localtime())

def isYufengPanel():
    version = 20260606    
    if isinstance(version, int) and version % 2 == 0:
        return True
    else:
        return False

def isChina():
    """
    判断服务器是否在中国境内
    """
    is_china_file = getPanelDataDir() + '/is_china.pl'
    if os.path.exists(is_china_file):
        return readFile(is_china_file).strip() == 'True'
    
    try:
        import urllib.request
        import json
        is_cn = None
        
        # 1. 尝试 ipinfo.io
        try:
            req1 = urllib.request.Request("http://ipinfo.io/json", headers={'User-Agent': 'curl/7.68.0'})
            res1 = urllib.request.urlopen(req1, timeout=3)
            res_json1 = json.loads(res1.read().decode('utf-8'))
            is_cn = res_json1.get('country', '') == 'CN'
        except Exception:
            pass
            
        # 2. 尝试 ipwhois.app 作为备用
        if is_cn is None:
            try:
                req2 = urllib.request.Request("https://ipwhois.app/json/?lang=zh-CN", headers={'User-Agent': 'curl/7.68.0'})
                res2 = urllib.request.urlopen(req2, timeout=3)
                res_json2 = json.loads(res2.read().decode('utf-8'))
                is_cn = res_json2.get('country_code', '') == 'CN'
            except Exception:
                pass
                
        # 3. 如果全部失败，默认当做国内服务器 (置为 True)
        if is_cn is None:
            is_cn = True
            
        writeFile(is_china_file, 'True' if is_cn else 'False')
        return is_cn
    except Exception:
        # 万一整体发生其他异常，默认置为 True
        writeFile(is_china_file, 'True')
        return True

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
        except Exception:
            pass

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
                except Exception:
                    pass
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
        except Exception:
            pass
            
        _IS_TESTING_GITHUB = False
        
    import threading
    t = threading.Thread(target=test_speed_bg)
    t.start()
    
    if wait_if_testing:
        t.join(timeout=10.0)
        if os.path.exists(cache_file):
            try:
                return getObjectByJson(readFile(cache_file))
            except Exception:
                pass

    if cached_data and 'name' in cached_data and 'url' in cached_data:
        return cached_data
    return {"name": "ghproxy.net", "url": "https://ghproxy.net/"}


def getGithubProxy():
    """
    如果在中国境内，返回最快的 GitHub 代理前缀
    """
    return getGithubProxyInfo()['url']


def getGithubProxyName():
    """
    获取当前优选的 GitHub 镜像站名称
    """
    return getGithubProxyInfo()['name']


# ---------- GitHub 代理站列表 ----------
# ⚠️ **单一真源**。以下位置必须与本列表逐项一致：
#   * `scripts/github_download.sh` 的 `_GH_PROXY_LIST`
#   * `deploy.sh` 的 `YF_BOOTSTRAP_PROXY_LIST`（引导期验签下载用）
#   * `deploy.sh` 的 `setup_china_git_config` 内联 `proxies` 数组
# 由 `testsuite/test_deploy_bootstrap.py::test_04` 守卫。
#
# 为什么强调这件事：曾经三处各写一份且**不一致**（面板侧少了 `gh.ddlc.top`），
# 结果是「同一个包在脚本里下得动、在面板里下不动」，极难排查。
# 中国大陆直连 GitHub 经常失败，本列表是可用性的生命线，只许增不许减。
_GITHUB_PROXY_LIST = [
    "",
    "https://gh-proxy.com/",
    "https://cors.zme.ink/",
    "https://gh.ddlc.top/",
    "https://ghproxy.net/",
    "https://gh.con.sh/",
]


def _proxy_display_name(prefix):
    """把代理前缀转成用于展示/测速的名字（`''` -> direct）。"""
    if not prefix:
        return 'direct'
    return prefix.rstrip('/').replace('https://', '').replace('http://', '')


#: 带名字的代理表，**由上面单一真源派生**，避免「列表改了、测速表没改」的漂移
_GITHUB_PROXY_NAMED = [(p, _proxy_display_name(p)) for p in _GITHUB_PROXY_LIST]

def _makeGithubProxyUrl(proxy_prefix, original_url):
    """
    将原始 GitHub URL 加上代理前缀
    部分代理前缀自带 "https://"（如 ghp.ci），需要去重
    """
    if proxy_prefix.endswith("https://"):
        return proxy_prefix + original_url.replace("https://", "", 1)
    return proxy_prefix + original_url


def githubDownload(url, save_path, timeout=10, min_size=0):
    """
    统一的 GitHub 下载函数（Python 端）
    使用优选节点下载，失败后降级轮询。

    @param url: GitHub 原始 URL
    @param save_path: 保存文件路径
    @param timeout: 单次超时秒数
    @param min_size: 期望的最小文件大小(字节)，如果下载结果小于该值将被视为失败并继续轮询
    @return: True=成功 False=全部失败
    """
    # 如果文件已存在且大小 > min_size，则跳过
    if os.path.exists(save_path) and os.path.getsize(save_path) > min_size:
        return True

    def _try_download(download_url):
        """尝试使用 wget 下载，成功返回 True"""
        # 先清除可能的空文件
        if os.path.exists(save_path):
            os.remove(save_path)
        cmd = 'wget --no-check-certificate -O "{}" --timeout={} --tries=1 -q "{}" 2>/dev/null'.format(
            save_path, timeout, download_url
        )
        execShell(cmd)
        if os.path.exists(save_path) and os.path.getsize(save_path) > min_size:
            return True
        # 清理异常小文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return False

    # 步骤1: 尝试最优节点下载，如果是下载大文件，则强制等待后台测速完成
    best_proxy_info = getGithubProxyInfo(wait_if_testing=True)
    best_proxy = best_proxy_info.get('url', '')
    best_url = _makeGithubProxyUrl(best_proxy, url)
    if _try_download(best_url):
        return True

    # 步骤2: 代理降级轮询机制
    for proxy in _GITHUB_PROXY_LIST:
        if proxy == best_proxy:
            continue
        proxy_url = _makeGithubProxyUrl(proxy, url)
        if _try_download(proxy_url):
            return True

    return False



def getDateFromNow(tf_format="%Y-%m-%d %H:%M:%S", time_zone="Asia/Shanghai"):
    # 取格式时间
    import time
    os.environ['TZ'] = time_zone
    time.tzset()
    return time.strftime(tf_format, time.localtime())

def getDataFromInt(val):
    time_format = '%Y-%m-%d %H:%M:%S'
    time_str = time.localtime(val)
    return time.strftime(time_format, time_str)

def getCommonFile():
    # 统一默认配置文件
    base_dir = getPanelDir()+'/'
    data = {
        'debug' : base_dir+'data/debug.pl',                              # DEBUG文件
        'close' : base_dir+'data/close.pl',                              # 识别关闭面板文件
        'basic_auth' : base_dir+'data/basic_auth.json',                  # 面板Basic验证
        'ipv6' : base_dir+'data/ipv6.pl',                                # ipv6识别文件
        'bind_domain' : base_dir+'data/bind_domain.pl',                  # 面板域名绑定
        'auth_secret': base_dir+'data/auth_secret.pl',                   # 二次验证密钥
        'ssl': base_dir+'ssl/choose.pl',                                 # ssl设置
    }
    return data

def checkCert(certPath='ssl/certificate.pem'):
    # 验证证书
    openssl = '/usr/bin/openssl'
    if not os.path.exists(openssl):
        openssl = '/usr/local/openssl/bin/openssl'
    if not os.path.exists(openssl):
        openssl = 'openssl'
    certPem = readFile(certPath)
    s = "\n-----BEGIN CERTIFICATE-----"
    tmp = certPem.strip().split(s)
    for tmp1 in tmp:
        if tmp1.find('-----BEGIN CERTIFICATE-----') == -1:
            tmp1 = s + tmp1
        writeFile(certPath, tmp1)
        result = execShell(openssl + " x509 -in " +
                           certPath + " -noout -subject")
        if result[1].find('-bash:') != -1:
            return True
        if len(result[1]) > 2:
            return False
        if result[0].find('error:') != -1:
            return False
    return True

def sortFileList(path, ftype = 'mtime', sort = 'desc'):
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except Exception:
        entries = []

    reverse = (sort == 'desc')
    if ftype == 'mtime':
        def _get_mtime(e):
            try:
                return e.stat().st_mtime
            except Exception:
                return 0
        entries.sort(key=_get_mtime, reverse=reverse)
    elif ftype == 'size':
        def _get_size(e):
            try:
                return e.stat().st_size
            except Exception:
                return 0
        entries.sort(key=_get_size, reverse=reverse)
    elif ftype == 'fname':
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)
    else:
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)

    return [e.name for e in entries]


def sortAllFileList(path, ftype = 'mtime', sort = 'desc', search = '',limit = 3000):
    count = 0
    flist = []
    for d_list in os.walk(path):
        if count >= limit:
            break

        for d in d_list[1]:
            if count >= limit:
                break
            if d.lower().find(search) != -1:
                filename = d_list[0] + '/' + d
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)

        for f in d_list[2]:
            if count >= limit:
                break

            if f.lower().find(search) != -1:
                filename = d_list[0] + '/' + f
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)

    if ftype == 'mtime':
        if sort == 'desc':
            flist = sorted(flist, key=lambda f: os.path.getmtime(f), reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=lambda f: os.path.getmtime(f), reverse=False)

    if ftype == 'size':
        if sort == 'desc':
            flist = sorted(flist, key=lambda f: os.path.getsize(f), reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=lambda f: os.path.getsize(f), reverse=False)
    return flist

def getPathSize(path):
    # 取文件或目录大小
    if not os.path.exists(path):
        return 0
    if not os.path.isdir(path):
        return os.path.getsize(path)
    size_total = 0
    for nf in os.walk(path):
        for f in nf[2]:
            filename = nf[0] + '/' + f
            size_total += os.path.getsize(filename)
    return size_total

def toSize(size, middle='') -> str:
    """
    字节单位转换
    """
    units = ('b', 'KB', 'MB', 'GB', 'TB')
    s = units[0]
    for u in units:
        if size < 1024:
            return str(round(size, 2)) + middle + u
        size = float(size) / 1024.0
        s = u
    return str(round(size, 2)) + middle + u

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

def returnJson(status, msg, data=None, *args):
    # 空消息或非字符串快速短路，0ms 直出
    if not msg or not isinstance(msg, str) or not msg.strip():
        if data is None:
            return getJson({'status': status, 'msg': msg})
        return getJson({'status': status, 'msg': msg, 'data': data})

    try:
        from core.i18n import t as _t
        translated_msg = _t(msg, *args)
    except Exception:
        translated_msg = msg

    if data is None:
        return getJson({'status': status, 'msg': translated_msg})
    return getJson({'status': status, 'msg': translated_msg, 'data': data})

def readFile(filename):
    # 读文件内容
    try:
        with open(filename, 'r', encoding='utf-8') as fp:
            fBody = fp.read()
        return fBody
    except Exception as e:
        # print('readFile:',str(e))
        return False

def readFileEnd(filename, lines=100):
    # 读取文件尾部指定行数
    try:
        with open(filename, 'rb') as f:
            f.seek(0, 2)
            filesize = f.tell()
            buffer_size = 8192
            if filesize == 0:
                return ''
            block = -1
            data = b''
            while True:
                if (abs(block * buffer_size)) <= filesize:
                    f.seek(block * buffer_size, 2)
                    data = f.read(buffer_size) + data
                else:
                    f.seek(0, 0)
                    data = f.read(filesize + (block + 1) * buffer_size) + data
                    break
                if data.count(b'\n') >= lines:
                    break
                block -= 1
            lines_list = data.splitlines()[-lines:]
            return (b'\n'.join(lines_list)).decode('utf-8', errors='replace')
    except Exception:
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
                        pass
                os.replace(temp_file, filename)
                # 二次校验：非空内容落盘后文件必须 >0，否则视为 ENOSPC/截断失败
                if content is not None and content != '':
                    try:
                        if os.path.getsize(filename) == 0 and len(str(content)) > 0:
                            writeFileLog(f"[writeFile] zero-size after replace: {filename} content_len={len(str(content))}\n{getTracebackInfo()}")
                            return False
                    except Exception as _e:
                        pass
                return True
            except Exception as write_err:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as _e:
                        pass
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


def backFile(file, act=None):
    """
        @name 备份配置文件
        @param file 需要备份的文件
        @param act 如果存在，则备份一份作为默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"

    import shutil
    try:
        shutil.copy2(file, file + file_type)
    except Exception as e:
        pass

def removeBackFile(file, act=None):
    """
        @name 删除备份配置文件
        @param file 需要删除备份文件
        @param act 如果存在，则还原默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"
    import shutil
    target = file + file_type
    try:
        if os.path.exists(target):
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
    except Exception as e:
        pass


def restoreFile(file, act=None):
    """
        @name 还原配置文件
        @param file 需要还原的文件
        @param act 如果存在，则还原默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"
    import shutil
    try:
        shutil.copy2(file + file_type, file)
    except Exception as e:
        pass

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


def formatDate(fmat="%Y-%m-%d %H:%M:%S", times=None, time_zone=None):
    # 格式化指定时间戳
    if not times:
        times = int(time.time())
    
    # if time_zone is None:
    #     try:
    #         import tzlocal
    #         time_zone = str(tzlocal.get_localzone())
    #     except:
    #         try:
    #             time_zone = time.tzname[0]
    #         except:
    #             time_zone = None
    
    if time_zone:
        old_tz = os.environ.get('TZ')
        os.environ['TZ'] = time_zone
        time.tzset()
        time_local = time.localtime(times)
        result = time.strftime(fmat, time_local)
        if old_tz:
            os.environ['TZ'] = old_tz
        else:
            del os.environ['TZ']
        time.tzset()
        return result
    else:
        time_local = time.localtime(times)
        return time.strftime(fmat, time_local)


def strfToTime(sdate):
    # 转换时间
    import time
    return time.strftime('%Y-%m-%d', time.strptime(sdate, '%b %d %H:%M:%S %Y %Z'))


def md5(content):
    # 生成MD5
    # B324 豁免：本函数仅用于缓存键 / 文件名指纹 / 校验和，以及历史弱口令哈希的一次性比对
    # （命中后立即回写 bcrypt，见 checkPwdCompat）；MD5 不用于新写入的任何安全凭据。
    try:
        m = hashlib.md5()  # nosec B324  # 缓存键/指纹/历史哈希比对，见上方说明
        m.update(content.encode("utf-8"))
        return m.hexdigest()
    except Exception as ex:
        return False

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

def checkPwd(password, hashed):
    '''
    验证密码
    '''
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed
    except Exception as _e:
        return False


def isLegacyPwdHash(hashed):
    '''是否为历史遗留弱哈希（32 位 MD5 / 64 位 SHA256 十六进制）。

    仅用于判断「命中后是否需要回写 bcrypt」；新口令一律经 hasPwd() 走 bcrypt，
    不再产生此类值。
    '''
    if not hashed:
        return False
    return bool(re.match(r'^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{64})$', str(hashed)))


def checkPwdCompat(password, stored):
    '''口令校验兼容层：bcrypt 优先，历史 MD5/SHA256 哈希回退比对。

    历史分支只服务于「老安装升级到 bcrypt」：调用方命中后应立即回写新哈希
    （见 admin/dashboard/login.py::_password_matches）。
    '''
    if not password or not stored:
        return False

    try:
        bcrypt_ok = bool(checkPwd(password, stored))
    except Exception as _e:
        # checkPwd 自身已吞异常；此处仅兜底，bcrypt 异常不得阻断历史哈希比对
        bcrypt_ok = False
    if bcrypt_ok:
        return True

    if not isLegacyPwdHash(stored):
        return False

    legacy_md5 = md5(password)
    if legacy_md5 and hmac.compare_digest(str(legacy_md5), str(stored)):
        return True

    try:
        legacy_sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
    except Exception as _e:
        legacy_sha = ''
    if legacy_sha and hmac.compare_digest(legacy_sha, str(stored)):
        return True
    return False


def getFileMd5(filename):
    # 文件的MD5值
    if not os.path.isfile(filename):
        return False

    myhash = hashlib.md5()  # nosec B324  # 文件校验和，非安全用途（Python<3.9 无 usedforsecurity 参数）
    f = open(filename, 'rb')
    while True:
        b = f.read(8096)
        if not b:
            break
        myhash.update(b)
    f.close()
    return myhash.hexdigest()


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
                    pass

            real_ip = request.headers.get('X-Real-IP', '').strip().replace('::ffff:', '')
            if real_ip:
                try:
                    ipaddress.ip_address(real_ip)
                    return real_ip
                except Exception as _e:
                    pass

        return remote_ip
    except Exception:
        return '127.0.0.1'

def checkDomainPanel():
    import thisdb
    from flask import Flask, redirect, request, url_for
    
    current_host = getHost()
    domain = thisdb.getOption('panel_domain', default='')
    port = getPanelPort()
    scheme = 'http'

    panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    if panel_ssl_data['open']:
        if not inArray(['local','nginx'], panel_ssl_data['choose']):
            return False
        scheme = 'https'

    client_ip = getClientIp()
    if client_ip in ['127.0.0.1', 'localhost', '::1']:
        return False

    ip = getHostAddr()
    if isVaildIpV6(ip):
        return False

    if domain == '':
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return False
        if current_host.strip().lower() != ip.strip().lower():
            to = scheme + "://" + ip + ":" + str(port)
            return redirect(to, code=302)
        return False
    else:
        # print(current_host.strip().lower(), domain.strip().lower())
        if current_host.strip().lower() != domain.strip().lower():
            to = scheme + "://" + domain + ":" + str(port)
            return redirect(to, code=302)
    return False

def getLocalIp():
    try:
        filename = getPanelDir() + '/data/iplist.txt'
        try:
            ipaddress = readFile(filename)
            if ipaddress and ipaddress != '127.0.0.1':
                return ipaddress
        except Exception:
            pass
        for flag in ['-4', '-6']:
            try:
                # 向下兼容 Python 2.7 ~ 3.x，移除 f-string，改用字符串拼接
                cmd = "curl --insecure " + flag + " -sS --connect-timeout 5 -m 60 https://speed.cloudflare.com/cdn-cgi/trace" # 使用 speed.cloudflare.com/cdn-cgi/trace 获取公网 IP
                ip = execShell(cmd)
                if ip and isinstance(ip, (tuple, list)) and ip[0]:
                    for line in ip[0].splitlines():
                        if line.startswith('ip='):
                            result = line[3:].strip()
                            if result:
                                writeFile(filename, result)
                                return result
            except Exception:
                continue
    except Exception:
        pass
    return '127.0.0.1'

def inArray(arrays, searchStr):
    # 搜索数据中是否存在
    for key in arrays:
        if key == searchStr:
            return True

    return False

def getJson(data):
    import json
    try:
        return json.dumps(data)
    except Exception:
        return json.dumps(data, default=str)

def getObjectByJson(data):
    import json
    return json.loads(data)


def getSslCrt():
    if os.path.exists('/etc/ssl/certs/ca-certificates.crt'):
        return '/etc/ssl/certs/ca-certificates.crt'
    if os.path.exists('/etc/pki/tls/certs/ca-bundle.crt'):
        return '/etc/pki/tls/certs/ca-bundle.crt'
    return ''


def getOs():
    # python3 -c 'import sys; print(sys.platform)'
    return sys.platform

def getOsName():
    cmd = "cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'"
    data = execShell(cmd)
    return data[0].strip().lower()

def getOsID():
    cmd = "cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'"
    data = execShell(cmd)
    return data[0].strip()

# 获取文件权限描述
def getFileStatsDesc(filename, path=None):
    try:
        import pwd
    except ImportError:
        pwd = None
    if path == '' or filename == '':
        return ';;;;;'
    try:
        filename = filename.replace('//', '/')
        stat = os.stat(filename)
        accept = str(oct(stat.st_mode)[-3:])
        mtime = str(int(stat.st_mtime))
        user = ''
        try:
            if pwd:
                user = str(pwd.getpwuid(stat.st_uid).pw_name)
            else:
                user = 'www'
        except Exception as _e:
            user = str(stat.st_uid)
            
        size = str(stat.st_size)
        link = ''
        if os.path.islink(filename):
            link = ' -> ' + os.readlink(filename)

        if path:
            norm_filename = filename.replace('\\', '/')
            norm_path = path.replace('\\', '/')
            if not norm_path.endswith('/'):
                norm_path += '/'
            if norm_filename.startswith(norm_path):
                filename = norm_filename[len(norm_path):]
            else:
                filename = os.path.basename(filename)

        return filename + ';' + size + ';' + mtime + ';' + accept + ';' + user + ';' + link
    except Exception as e:
        return ';;;;;'

def getFileSuffix(file):
    tmp = file.split('.')
    ext = tmp[len(tmp) - 1]
    return ext

def getPathSuffix(path):
    return os.path.splitext(path)[-1]

def getHostAddr():
    ip_text = getPanelDataDir() + '/iplist.txt'
    if os.path.exists(ip_text):
        return readFile(ip_text).strip()
    return '127.0.0.1'

def checkIp(ip):
    # 检查是否为IPv4地址
    import re
    p = re.compile(r'^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$')
    if p.match(ip):
        return True
    else:
        return False

def createLinuxUser(user, group):
    execShell("groupadd {}".format(group))
    execShell('useradd -s /sbin/nologin -g {} {}'.format(user, group))
    return True


def setOwn(filename, user, group=None):
    if isAppleSystem():
        return True

    # 设置用户组
    if not os.path.exists(filename):
        return False
    from pwd import getpwnam
    try:
        user_info = getpwnam(user)
        user = user_info.pw_uid
        if group:
            user_info = getpwnam(group)
        group = user_info.pw_gid
    except Exception as _e:
        if user == 'www':
            createLinuxUser(user)
        # 如果指定用户或组不存在，则使用www
        try:
            user_info = getpwnam('www')
        except Exception as _e:
            createLinuxUser(user)
            user_info = getpwnam('www')
        user = user_info.pw_uid
        group = user_info.pw_gid
    os.chown(filename, user, group)
    return True

def setMode(filename, mode):
    # 设置文件权限
    if not os.path.exists(filename):
        return False
    mode = int(str(mode), 8)
    os.chmod(filename, mode)
    return True

def getSqitePrefix():
    WIN = sys.platform.startswith('win')
    if WIN:  # 如果是 Windows 系统，使用三个斜线
        prefix = 'sqlite:///'
    else:  # 否则使用四个斜线
        prefix = 'sqlite:////'
    return prefix

def checkPort(port):
    # 检查端口是否合法
    ports = ['21', '443', '888']
    if port in ports:
        return False
    intport = int(port)
    if intport < 1 or intport > 65535:
        return False
    return True

def getStrBetween(startStr, endStr, srcStr):
    # 字符串取中间
    start = srcStr.find(startStr)
    if start == -1:
        return None
    end = srcStr.find(endStr)
    if end == -1:
        return None
    return srcStr[start + 1:end]

def getCpuType():
    cpuType = ''
    if isAppleSystem():
        cmd = "system_profiler SPHardwareDataType | grep 'Processor Name' | awk -F ':' '{print $2}'"
        cpuinfo = execShell(cmd)
        return cpuinfo[0].strip()

    current_os = getOs()
    if current_os.startswith('freebsd'):
        cmd = "sysctl -a | egrep -i 'hw.model' | awk -F ':' '{print $2}'"
        cpuinfo = execShell(cmd)
        return cpuinfo[0].strip()

    # 取CPU类型
    if not os.path.exists('/proc/cpuinfo'):
        return 'Intel/AMD CPU'
    cpuinfo = open('/proc/cpuinfo', 'r').read()
    rep = "model\\s+name\\s+:\\s+(.+)"
    tmp = re.search(rep, cpuinfo, re.I)
    if tmp:
        cpuType = tmp.groups()[0]
    else:
        cpuinfo = execShell('LANG="en_US.UTF-8" && lscpu')[0]
        rep = "Model\\s+name:\\s+(.+)"
        tmp = re.search(rep, cpuinfo, re.I)
        if tmp:
            cpuType = tmp.groups()[0]
    return cpuType


_LANG_CACHE = {'mtime': 0, 'lang': 'zh-CN'}

def getLanguage():
    try:
        from core.i18n import get_current_lang
        return get_current_lang()
    except Exception:
        pass

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


def getStaticJson(name="public"):
    lang = getLanguage()
    file = 'static/language/' + lang + '/' + name + '.json'
    if not os.path.exists(file):
        file = 'static/language/zh-CN/' + name + '.json'
    return file


import functools

@functools.lru_cache(maxsize=128)
def _getCachedStaticJson(name, lang):
    try:
        from core.i18n import get_cached_json
        return get_cached_json(name, lang)
    except Exception:
        pass
    file = 'static/language/' + lang + '/' + name + '.json'
    if not os.path.exists(file):
        file = 'static/language/zh-CN/' + name + '.json'
    try:
        return json.loads(readFile(file))
    except Exception as _e:
        return {}

def returnMsg(status, msg, args=()):
    try:
        from core.i18n import t as _t
        translated = _t(msg, *args)
        return {'status': status, 'msg': translated, 'data': args}
    except Exception:
        pass

    # 回退原字典逻辑
    lang = getLanguage()
    logMessage = _getCachedStaticJson('public', lang)
    keys = logMessage.keys()

    if msg in keys:
        msg = logMessage[msg]
        for i in range(len(args)):
            rep = '{' + str(i + 1) + '}'
            msg = msg.replace(rep, str(args[i]))
    return {'status': status, 'msg': msg, 'data': args}
    
def getInfo(msg, args=()):
    # 取提示消息
    for i in range(len(args)):
        rep = '{' + str(i + 1) + '}'
        msg = msg.replace(rep, args[i])
    return msg

def getLastLine(path, num, p=1):
    try:
        import html
        if not os.path.exists(path):
            return ""
        if num <= 0 or p <= 0:
            return ""

        file_size = os.path.getsize(path)
        if file_size == 0:
            return ""

        start_line = (p - 1) * num
        needed_count = start_line + num

        lines = []
        buf = b""
        block_size = 8192

        with open(path, 'rb') as fp:
            pos = file_size
            while pos > 0 and len(lines) < needed_count:
                read_size = min(block_size, pos)
                pos -= read_size
                fp.seek(pos)
                chunk = fp.read(read_size)
                buf = chunk + buf

                while b'\n' in buf:
                    idx = buf.rfind(b'\n')
                    line_bytes = buf[idx + 1:]
                    buf = buf[:idx]
                    if line_bytes or lines:
                        try:
                            line_str = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                        except Exception as _e:
                            line_str = str(line_bytes)
                        lines.append(html.escape(line_str))
                        if len(lines) >= needed_count:
                            break

            if buf and len(lines) < needed_count:
                try:
                    line_str = buf.decode('utf-8', errors='replace').rstrip('\r')
                except Exception as _e:
                    line_str = str(buf)
                lines.append(html.escape(line_str))

        paged_lines = lines[start_line:needed_count]
        paged_lines.reverse()
        return "\n".join(paged_lines)
    except Exception as e:
        return str(e)

# 获取系统温度
def getSystemDeviceTemperature():
    import psutil
    if not hasattr(psutil, "sensors_temperatures"):
        return False, "platform not supported"
    temps = psutil.sensors_temperatures()
    if not temps:
        return False, "can't read any temperature"
    for name, entries in temps.items():
        for entry in entries:
            return True, entry.label
            # print("%-20s %s °C (high = %s °C, critical = %s °C)" % (
            #     entry.label or name, entry.current, entry.high,
            #     entry.critical))
    return False, ""

def getPage(args, result='1,2,3,4,5,8'):
    data = getPageObject(args, result)
    return data[0]


def getPageObject(args, result='1,2,3,4,5,8'):
    # 取分页
    from utils import page
    # 实例化分页类
    page = page.Page()
    info = {}

    info['count'] = 0
    if 'count' in args:
        info['count'] = int(args['count'])

    info['row'] = 10
    if 'row' in args:
        info['row'] = int(args['row'])

    info['p'] = 1
    if 'p' in args:
        info['p'] = int(args['p'])
    info['uri'] = {}
    info['return_js'] = ''
    if 'tojs' in args:
        info['return_js'] = args['tojs']

    if 'args_tpl' in args:
        info['args_tpl'] = args['args_tpl']

    return (page.GetPage(info, result), page)


def getHostPort():
    port_file = getPanelDir() + '/data/port.pl'
    if os.path.exists(port_file):
        return readFile(port_file).strip()
    return '7200'


def setHostPort(port):
    file = getPanelDir() + '/data/port.pl'
    return writeFile(file, port)

def isAppleSystem():
    if getOs() == 'darwin':
        return True
    return False

def isDocker():
    return os.path.exists('/.dockerenv')

def isSupportSystemctl():
    if isAppleSystem():
        return False
    if isDocker():
        return False

    current_os = getOs()
    if current_os.startswith("freebsd"):
        return False
    return True

def isSupportHttp3(version):
    if version.startswith('1.25'):
        return True 
    if version.startswith('1.27'):
        return True
    if version.startswith('1.29'):
        return True
    if version.startswith('rtmp'):
        return True
    return False

def isVhostHasReuseport():
    vhost_dir = getServerDir() + '/web_conf/nginx/vhost'
    if not os.path.exists(vhost_dir):
        return False
    try:
        for filename in os.listdir(vhost_dir):
            if filename.endswith('.conf'):
                filepath = os.path.join(vhost_dir, filename)
                content = readFile(filepath)
                if content and 'quic reuseport' in content:
                    return True
    except Exception as _e:
        pass
    
    return False

def isDebugMode():
    if isAppleSystem():
        return True

    debug = M('option').field('name').where('name=?',('debug',)).getField('value')
    if debug == 'open':
        return True
    return False

def isNumber(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass

    return False

# 检查端口是否占用
def isOpenPort(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', int(port)))
        s.shutdown(2)
        return True
    except Exception as e:
        return False

def debugLog(*data):
    if isDebugMode():
        print(data)
    return True


def userSafeError(exc, trace_id=None):
    """把内部异常转成「可安全展示给前端」的短消息。

    为什么要脱敏：把 `str(e)` 直接回前端会泄露绝对路径、SQL 片段、依赖版本
    与内网地址 —— 这些恰好是攻击者做下一步利用最想要的信息。
    完整堆栈只进面板日志，前端只拿一个追踪号，便于用户报障时对账。

    追踪号优先复用请求级 `g.request_id`（见 admin/__init__.py 的 before_request），
    这样「用户报的追踪号」与「日志里的请求 ID」是同一个，排查时能直接串起整条链路。
    """
    tid = trace_id
    if not tid:
        try:
            from flask import g as _g
            tid = getattr(_g, 'request_id', None)
        except Exception:
            tid = None
    if not tid:
        try:
            import uuid as _uuid
            tid = _uuid.uuid4().hex[:12]
        except Exception:
            tid = 'unknown'
    try:
        writeFileLog('[userSafeError][%s] %s\n%s' % (tid, exc, getTracebackInfo()))
    except Exception:
        pass
    return '操作失败，请稍后重试或查看面板日志（追踪号 %s）' % tid


def _logIdentity():
    """取当前操作者身份 (uid, username, ip)。无请求上下文时返回 (0, '', '')。

    历史问题：`writeLog` 把 uid **硬编码为 0**（取 session 的代码被注释掉了），
    于是操作日志里「谁做的」永远查不到，也不记来源 IP —— 商业版的审计合规
    直接卡在这一条上。
    """
    uid, username, ip = 0, '', ''
    in_request = False
    try:
        from flask import session, request
        try:
            request.remote_addr  # 不在请求上下文会抛异常
            in_request = True
        except Exception:
            in_request = False
        if in_request:
            try:
                if 'uid' in session:
                    uid = int(session.get('uid') or 0)
                elif session.get('login'):
                    uid = 1
                username = session.get('username') or ''
            except Exception:
                # 会话不可读（签名失效/未登录）：按匿名处理
                uid, username = 0, ''
    except Exception:
        in_request = False

    if in_request:
        try:
            ip = getClientIp()
        except Exception:
            try:
                from flask import request as _r
                ip = getattr(_r, 'remote_addr', '') or ''
            except Exception:
                ip = ''
    return uid, username, ip


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

def writeAudit(action, target='', result='ok', detail=''):
    """显式写一条语义化审计记录（推荐在关键写操作里调用）。

    与 `writeLog` 的分工：`writeLog` 记录「面板做了什么」供界面展示；
    `writeAudit` 额外记录「对哪个对象、结果如何」，供合规审计检索。
    永不抛异常。
    """
    try:
        from core import audit
        return audit.write_audit(action=action, target=target,
                                 result=result, detail=detail)
    except Exception:
        return False


def verifyAuditChain(limit=0):
    """校验审计流水哈希链完整性。返回 (ok, problems, checked)。"""
    try:
        from core import audit
        return audit.verify_chain(limit=limit)
    except Exception as exc:
        return False, ['审计校验调用异常：%s' % exc], 0


def writeFileLog(msg, path=None, limit_size=50 * 1024 * 1024, save_limit=3):
    log_file = getPanelDir() + '/logs/debug.log'
    if path != None:
        log_file = path

    if os.path.exists(log_file):
        size = os.path.getsize(log_file)
        if size > limit_size:
            log_file_rename = log_file + "_" + \
                time.strftime("%Y-%m-%d_%H%M%S") + '.log'
            os.rename(log_file, log_file_rename)
            logs = sorted(glob.glob(log_file + "_*"))
            count = len(logs)
            save_limit = count - save_limit
            for i in range(count):
                if i > save_limit:
                    break
                os.remove(logs[i])
                # print('|---多余日志[' + logs[i] + ']已删除!')

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

def writeDbLog(stype, msg, args=(), uid=1, ip=''):
    try:
        import thisdb
        format_msg = getInfo(msg, args)
        thisdb.addLog(stype, format_msg, uid, ip=ip)
        return True
    except Exception as e:
        # 不能只 print：面板进程的 stdout 会丢，日志落盘才能排查
        writeFileLog('writeDbLog 失败: %s' % e)
        return False

# ---------------------------------------------------------------------------------
# 文件操作进度：内存态（第 0 层磁盘 I/O 治理）
# 原实现每次进度变化都落盘 data/panel_speed.pl（批量删除/复制/清空回收站时
# 产生持续的小文件写放大）。生产环境 workers=1（Flask-SocketIO 约束），
# 进度生产者 web/utils/file.py 与消费者 /files 接口处于同一进程，
# 因此改为纯内存状态，彻底消除该写放大。
# ---------------------------------------------------------------------------------
_SPEED_LOCK = threading.Lock()
_SPEED_STATE = {'title': None, 'progress': 0, 'total': 0, 'used': 0, 'speed': 0}

def writeSpeed(title, used, total, speed=0):
    # 更新内存进度（不落盘）
    if not title:
        data = {'title': None, 'progress': 0, 'total': 0, 'used': 0, 'speed': 0}
    else:
        try:
            progress = int((100.0 * used / total)) if total else 0
        except Exception:
            progress = 0
        data = {'title': title, 'progress': progress, 'total': total, 'used': used, 'speed': speed}
    with _SPEED_LOCK:
        _SPEED_STATE.update(data)
    return True


def getSpeed():
    # 取内存进度（副本，避免调用方并发修改）
    with _SPEED_LOCK:
        return dict(_SPEED_STATE)



def M(table=''):
    import core.db as db
    sql = db.Sql()
    if table == '':
        return sql
    return sql.table(table)


def enDoubleCrypt(key, strings):
    # 加密字符串
    try:
        import base64
        import cryptography
        from cryptography.fernet import Fernet
        
        try:
            from core.crypt_salt import get_salt
            salt = get_salt()
        except Exception as _e:
            salt = None
            
        composite_key = key + salt if salt else key
        _key = md5(composite_key).encode('utf-8')
        _key = base64.urlsafe_b64encode(_key)

        if type(strings) != bytes:
            strings = strings.encode('utf-8')
            
        f = Fernet(_key)
        result = f.encrypt(strings)
        return result.decode('utf-8')
    except Exception as _e:
        writeFileLog(getTracebackInfo())
        return strings


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
                pass

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
            pass
            
    key = getRandomString(16)
    vi = getRandomString(16)
    _aes_key_cache = {'key': key, 'vi': vi}
    try:
        with open(aes_file, 'w') as f:
            f.write(json.dumps(_aes_key_cache))
    except Exception as _e:
        pass
    return _aes_key_cache

def aesEncrypt(data, key=None, vi=None):
    # aes加密
    # @param data 被加密的数据
    # @param key 加解密密匙 16位
    # @param vi 16位
    
    if key is None or vi is None:
        aes_info = getAesKey()
        key = aes_info['key']
        vi = aes_info['vi']

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    if not isinstance(data, bytes):
        data = data.encode()

    # AES_CBC_KEY = os.urandom(32)
    # AES_CBC_IV = os.urandom(16)

    AES_CBC_KEY = key.encode()
    AES_CBC_IV = vi.encode()

    # print("AES_CBC_KEY:", AES_CBC_KEY)
    # print("AES_CBC_IV:", AES_CBC_IV)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(AES_CBC_KEY),
                    modes.CBC(AES_CBC_IV),
                    backend=default_backend())
    encryptor = cipher.encryptor()

    edata = encryptor.update(padded_data)

    # print(edata)
    # print(str(edata))
    # print(edata.decode())
    return edata


def aesDecrypt(data, key=None, vi=None):
    # aes加密
    # @param data 被解密的数据
    # @param key 加解密密匙 16位
    # @param vi 16位

    if key is None or vi is None:
        aes_info = getAesKey()
        key = aes_info['key']
        vi = aes_info['vi']

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    if not isinstance(data, bytes):
        data = data.encode()

    AES_CBC_KEY = key.encode()
    AES_CBC_IV = vi.encode()

    cipher = Cipher(algorithms.AES(AES_CBC_KEY),
                    modes.CBC(AES_CBC_IV),
                    backend=default_backend())
    decryptor = cipher.decryptor()

    ddata = decryptor.update(data)

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    data = unpadder.update(ddata)

    try:
        uppadded_data = data + unpadder.finalize()
    except ValueError:
        raise Exception('无效的加密信息!')

    return uppadded_data

def getDefault(data,val,def_val=''):
    if val in data:
        return data[val]
    return def_val

def encodeImage(imgsrc, newsrc):
    # 图片加密
    import struct
    old_fp = open(imgsrc, 'rb')
    imgFile = old_fp.read()
    old_fp.close()

    new_fp = open(newsrc,"wb")
    for x in imgFile:
        value = x ^ 86
        value = hex(value)
        s = struct.pack('B',int(value,16))
        new_fp.write(s)
    new_fp.close()
    return True
    
def buildSoftLink(src, dst, force=False):
    '''
    建立软连接
    '''
    if not os.path.exists(src):
        return False

    if os.path.exists(dst) and force:
        os.remove(dst)

    if not os.path.exists(dst):
        execShell('ln -sf "' + src + '" "' + dst + '"')
        return True
    return False
# ------------------------------   network start  -----------------------------

def _insecure_ssl_context():
    try:
        import ssl
        return ssl._create_unverified_context()
    except Exception:
        return None

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


def _pool_request(method, url, timeout, body=None, headers=None):
    """先用「验证证书」的连接池请求；失败再降级到不校验证书的池。

    返回解码后的字符串；两者都失败返回 None。保留降级路径是因为部分老系统
    CA 束缺失，强验证会导致插件/GitHub 下载全面失败。
    """
    for insecure in (False, True):
        pool = _get_http_pool(insecure=insecure)
        if not pool:
            continue
        try:
            kwargs = {'timeout': timeout, 'retries': False}
            if body is not None:
                kwargs['body'] = body
            if headers is not None:
                kwargs['headers'] = headers
            resp = pool.request(method, url, **kwargs)
            data = resp.data
            if isinstance(data, bytes):
                data = data[:1048576].decode('utf-8', errors='replace') if len(data) > 1048576 else data.decode('utf-8', errors='replace')
            return data
        except Exception:
            continue
    return None


def HttpGet(url, timeout=10):
    """
    发送GET请求（验证优先，失败降级；连接池复用）
    @url 被请求的URL地址(必需)
    @timeout 超时时间默认60秒
    return string
    """
    data = _pool_request('GET', url, timeout)
    if data is not None:
        return data
    try:
        import urllib.request
        ctx = _insecure_ssl_context()
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        response = urllib.request.urlopen(url, **kwargs)
        result = response.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as ex:
        return str(ex)


def HttpGet2(url, timeout):
    data = _pool_request('GET', url, timeout)
    if data is not None:
        return data
    import urllib.request
    try:
        ctx = _insecure_ssl_context()
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        req = urllib.request.urlopen(url, **kwargs)
        result = req.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as e:
        return str(e)


def httpGet(url, timeout=10):
    return HttpGet2(url, timeout)


def HttpPost(url, data, timeout=10):
    """
    发送POST请求（验证优先，失败降级；1MB 响应截断）
    @url 被请求的URL地址(必需)
    @data POST参数，可以是字符串或字典(必需)
    @timeout 超时时间默认60秒
    return string
    """
    headers = {'User-Agent': 'bt_simple/1.0', 'Content-Type': 'application/x-www-form-urlencoded'}
    if isinstance(data, dict):
        if len(str(data)) > 65536:
            return "POST data too large"
        import urllib.parse as _up
        body = _up.urlencode(data)
    else:
        body = data
    result = _pool_request('POST', url, timeout, body=body, headers=headers)
    if result is not None:
        return result
    try:
        import urllib.request
        ctx = _insecure_ssl_context()
        if isinstance(data, dict):
            if len(str(data)) > 65536:
                return "POST data too large"
            data = urllib.parse.urlencode(data).encode('utf-8')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        req = urllib.request.Request(url, data)
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        req.add_header('User-Agent', 'bt_simple/1.0')
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        response = urllib.request.urlopen(req, **kwargs)
        result = response.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as ex:
        return str(ex)


def httpPost(url, data, timeout=10):
    return HttpPost(url, data, timeout)

# ------------------------------   network end  -----------------------------

# ------------------------------   panel start  -----------------------------

def isRestart():
    # 检查是否允许重启
    num = M('tasks').where('status!=?', ('1',)).count()
    if num > 0:
        return False
    return True

def getAcmeDir():
    acme = '/root/.acme.sh'
    if isAppleSystem():
        cmd = "who | sed -n '2, 1p' |awk '{print $1}'"
        user = execShell(cmd)[0].strip()
        acme = '/Users/' + user + '/.acme.sh'
    # if not os.path.exists(acme):
    #     acme = '/.acme.sh'
    return acme


def getAcmeDomainDir(domain):
    acme_dir = getAcmeDir()
    acme_domain = acme_dir + '/' + domain
    acme_domain_ecc = acme_domain + '_ecc'
    if os.path.exists(acme_domain_ecc):
        acme_domain = acme_domain_ecc
    return acme_domain


def fileNameCheck(filename):
    f_strs = [';', '&', '<', '>']
    for fs in f_strs:
        if filename.find(fs) != -1:
            return False
    return True

def getTriggerTaskLockFile():
    return getPanelDir() + '/logs/panel_task.lock'

def getPanelTaskPidFile():
    return getYfLogs() + '/panel_task.pid'


def wakePanelTask():
    # 事件驱动：通知后台 panel_task 进程立即处理新任务，避免其固定间隔空转。
    # 仅在有 /proc 的 Linux 环境下按 cmdline 严格校验 PID 归属后才发信号，
    # 杜绝 PID 复用导致的误伤（panel_task.py 会注册 SIGUSR1 处理器）。
    import signal
    if not hasattr(signal, 'SIGUSR1'):
        return False
    try:
        if not os.path.isdir('/proc'):
            return False
        pid_file = getPanelTaskPidFile()
        if not os.path.exists(pid_file):
            return False
        with open(pid_file, 'r') as f:
            pid = int((f.read() or '').strip())
        if pid <= 1:
            return False
        cmdline_file = '/proc/%d/cmdline' % pid
        if not os.path.exists(cmdline_file):
            return False
        with open(cmdline_file, 'rb') as cf:
            cmdline = cf.read().decode('utf-8', 'ignore')
        if 'panel_task.py' not in cmdline:
            return False
        os.kill(pid, signal.SIGUSR1)
        return True
    except Exception:
        return False


def triggerTask():
    lock_file = getTriggerTaskLockFile()
    writeFile(lock_file, 'True')
    # 立即唤醒后台任务进程，替代固定 3 秒空转轮询
    wakePanelTask()

def restartTask():
    initd = getPanelDir() + '/scripts/init.d/yf'
    if os.path.exists(initd):
        safeExecShell([initd, 'restart_task'])
    return True

def restartPanel():
    restart_file = getPanelDir()+'/data/restart.pl'
    writeFile(restart_file, 'True')
    # 立即唤醒看门狗执行重启，替代 3 秒空转检测
    wakePanelTask()
    return True

def panelCmd(method):
    allowed = ('restart_task', 'reload', 'restart', 'stop', 'start')
    if method not in allowed:
        method = 'reload'
    import subprocess as _sp
    log_fp = open('/tmp/panelCmd.log', 'ab')
    for _cmd in (getPanelDir() + '/scripts/init.d/yf', '/etc/init.d/yf'):
        if os.path.exists(_cmd):
            try:
                _sp.Popen([_cmd, method], stdout=log_fp, stderr=_sp.STDOUT, start_new_session=True)
            except Exception:
                pass
            return

# ------------------------------    panel end    -----------------------------

# ------------------------------ openresty start -----------------------------

def getOpVer():
    version = ''
    version_file_pl = getServerDir() + '/openresty/version.pl'
    if os.path.exists(version_file_pl):
        version = readFile(version_file_pl)
        version = version.strip()
    return version

def checkWebConfig():
    op_dir = getServerDir() + '/openresty/nginx'
    # "ulimit -n 10240 && " +
    cmd = op_dir + "/sbin/nginx -t -c " + op_dir + "/conf/nginx.conf"
    result = execShell(cmd)
    searchStr = 'test is successful'
    if result[1].find(searchStr) == -1:
        msg = getInfo('配置文件错误[openresty]: {1}', (result[1],))
        writeLog("软件管理", msg)
        return result[1]
    return True

def checkHttpdConfig():
    op_dir = getServerDir() + '/apache/httpd'
    # "ulimit -n 10240 && " +
    cmd = op_dir + "/bin/httpd -t"
    result = execShell(cmd)
    searchStr = 'Syntax OK'
    if result[1].find(searchStr) == -1:
        msg = getInfo('配置文件错误[httpd]: {1}', (result[1],))
        writeLog("软件管理", msg)
        return result[1]
    return True

def isIpAddr(ip):
    check_ip = re.compile(r'^(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|[1-9])\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\\d)$')
    if check_ip.match(ip):
        return True
    else:
        return False

def isVaildIpV4(ip):
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False

def isVaildIpV6(ip):
    import ipaddress
    try:
        ipaddress.IPv6Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False

def isVaildIp(ip):
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        pass

    try:
        ipaddress.IPv6Address(ip)
        return True
    except ipaddress.AddressValueError:
        pass
    return False


def getWebStatus():
    pid = getServerDir() + '/openresty/nginx/logs/nginx.pid'
    if os.path.exists(pid):
        return True
    return False


def restartWeb():
    return opWeb("reload")

def deleteFile(file):
    try:
        if os.path.exists(file) or os.path.islink(file):
            os.remove(file)
    except Exception:
        pass

def isInstalledWeb():
    path = getServerDir() + '/openresty/nginx/sbin/nginx'
    if os.path.exists(path):
        return True
    return False

_reload_timer = None
_reload_lock = threading.Lock()

def _do_reload():
    systemd = systemdCfgDir() + '/openresty.service'
    if os.path.exists(systemd):
        execShell('systemctl reload openresty')
        return True
    sys_initd = '/etc/init.d/openresty'
    if os.path.exists(sys_initd):
        safeExecShell([sys_initd, 'reload'])
        return True
    initd = getServerDir() + '/openresty/init.d/openresty'
    if os.path.exists(initd):
        execShell(initd + ' reload')
        return True
    return False

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

def opLuaMake(cmd_name):
    path = getServerDir() + '/web_conf/nginx/lua/lua.conf'
    root_dir = getServerDir() + '/web_conf/nginx/lua/' + cmd_name
    dst_path = getServerDir() + '/web_conf/nginx/lua/' + cmd_name + '.lua'
    def_path = getServerDir() + '/web_conf/nginx/lua/empty.lua'

    if not os.path.exists(root_dir):
        execShell('mkdir -p ' + root_dir)

    files = []
    for fl in os.listdir(root_dir):
        suffix = getFileSuffix(fl)
        if suffix != 'lua':
            continue
        flpath = os.path.join(root_dir, fl)
        files.append(flpath)

    if len(files) > 0:
        def_path = dst_path
        content = ''
        for f in files:
            t = readFile(f)
            f_base = os.path.basename(f)
            content += '-- ' + '*' * 20 + ' ' + f_base + ' start ' + '*' * 20 + "\n"
            content += t
            content += "\n" + '-- ' + '*' * 20 + ' ' + f_base + ' end ' + '*' * 20 + "\n"
        writeFile(dst_path, content)
    else:
        if os.path.exists(dst_path):
            os.remove(dst_path)

    conf = readFile(path)
    if not isinstance(conf, str):
        conf = ''
    if conf:
        conf = re.sub(cmd_name + ' (.*);',
                      lambda m: cmd_name + " " + def_path.replace('\\', '/') + ";", conf)
        writeFile(path, conf)


def opLuaInitFile():
    opLuaMake('init_by_lua_file')


def opLuaInitWorkerFile():
    opLuaMake('init_worker_by_lua_file')


def opLuaInitAccessFile():
    opLuaMake('access_by_lua_file')


def opLuaMakeAll():
    opLuaInitFile()
    opLuaInitWorkerFile()
    opLuaInitAccessFile()

# ------------------------------ openresty end -----------------------------

# ---------------------------------------------------------------------------------
# PHP START
# ---------------------------------------------------------------------------------

def getFpmConfFile(version):
    return getServerDir() + '/php/' + version + '/etc/php-fpm.d/www.conf'

def getFpmAddress(version):
    fpm_address = '/tmp/php-cgi-{}.sock'.format(version)
    php_fpm_file = getFpmConfFile(version)
    try:
        content = readFile(php_fpm_file)
        tmp = re.findall(r"listen\s*=\s*(.+)", content)
        if not tmp:
            return fpm_address
        if tmp[0].find('sock') != -1:
            return fpm_address
        if tmp[0].find(':') != -1:
            listen_tmp = tmp[0].split(':')
            if bind:
                fpm_address = (listen_tmp[0], int(listen_tmp[1]))
            else:
                fpm_address = ('127.0.0.1', int(listen_tmp[1]))
        else:
            fpm_address = ('127.0.0.1', int(tmp[0]))
        return fpm_address
    except Exception as _e:
        return fpm_address

def requestFcgiPHP(sock, uri, document_root='/tmp', method='GET', pdata=b''):
    # 直接请求到PHP-FPM
    # version php版本
    # uri 请求uri
    # filename 要执行的php文件
    # args 请求参数
    # method 请求方式

    import utils.php.fpm as fpm
    p = fpm.fpm(sock, document_root)

    if type(pdata) == dict:
        pdata = url_encode(pdata)
    result = p.load_url_public(uri, pdata, method)
    return result
# ---------------------------------------------------------------------------------
# PHP END
# ---------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------
# 数据库 START
# ---------------------------------------------------------------------------------

def getMyORM():
    '''
    获取MySQL资源的ORM
    '''
    import core.orm as orm
    o = orm.ORM()
    return o
# ---------------------------------------------------------------------------------
# 数据库 START
# ---------------------------------------------------------------------------------

##################### ssl start #########################################

def strfDate(sdate):
    return time.strftime('%Y-%m-%d', time.strptime(sdate, '%Y%m%d%H%M%S'))

# 获取证书名称
def getCertName(certPath):
    if not os.path.exists(certPath):
        return None
    try:
        import OpenSSL
        result = {}
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, readFile(certPath))
        # 取产品名称
        issuer = x509.get_issuer()
        result['issuer'] = ''
        if hasattr(issuer, 'CN'):
            result['issuer'] = issuer.CN
        if not result['issuer']:
            is_key = [b'0', '0']
            issue_comp = issuer.get_components()
            if len(issue_comp) == 1:
                is_key = [b'CN', 'CN']
            for iss in issue_comp:
                if iss[0] in is_key:
                    result['issuer'] = iss[1].decode()
                    break
        if not result['issuer']:
            if hasattr(issuer, 'O'):
                result['issuer'] = issuer.O

        # 取证书分类（Organization）
        result['issuer_o'] = ''
        if hasattr(issuer, 'O'):
            result['issuer_o'] = issuer.O
        if not result['issuer_o']:
            issue_comp = issuer.get_components()
            for iss in issue_comp:
                if iss[0] in [b'O', 'O']:
                    result['issuer_o'] = iss[1].decode()
                    break

        # 取到期时间
        result['notAfter'] = strfDate(bytes.decode(x509.get_notAfter())[:-1])
        # 取申请时间
        result['notBefore'] = strfDate(bytes.decode(x509.get_notBefore())[:-1])
        # 取可选名称
        result['dns'] = []
        for i in range(x509.get_extension_count()):
            s_name = x509.get_extension(i)
            if s_name.get_short_name() in [b'subjectAltName', 'subjectAltName']:
                s_dns = str(s_name).split(',')
                for d in s_dns:
                    result['dns'].append(d.split(':')[1])
        subject = x509.get_subject().get_components()
        # 取主要认证名称
        if len(subject) == 1:
            result['subject'] = subject[0][1].decode()
        else:
            if not result['dns']:
                for sub in subject:
                    if sub[0] == b'CN':
                        result['subject'] = sub[1].decode()
                        break
                if 'subject' in result:
                    result['dns'].append(result['subject'])
            else:
                result['subject'] = result['dns'][0]
        result['endtime'] = int(int(time.mktime(time.strptime(
            result['notAfter'], "%Y-%m-%d")) - time.time()) / 86400)
        return result
    except Exception as e:
        writeFileLog(getTracebackInfo())
        return None

def createLocalSSL():
    pdir = getPanelDir()
    local_dir = pdir+'/ssl/local'
    if not os.path.exists(local_dir):
        execShell('mkdir -p ' + local_dir)

    # 自签证书
    # if os.path.exists('ssl/local/input.pl'):
    #     return True

    client_ip = getClientIp()

    import OpenSSL
    key = OpenSSL.crypto.PKey()
    key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)
    cert = OpenSSL.crypto.X509()
    cert.set_serial_number(0)
    
    if client_ip == '127.0.0.1':
        cert.get_subject().CN = '127.0.0.1'
    else:
        cert.get_subject().CN = getLocalIp()
    
    cert.set_issuer(cert.get_subject())
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(86400 * 3650)
    cert.set_pubkey(key)
    cert.sign(key, 'sha256')
    cert_ca = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    private_key = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)
    if len(cert_ca) > 100 and len(private_key) > 100:
        writeFile(local_dir+'/cert.pem', cert_ca, 'wb+')
        writeFile(local_dir+'/private.pem', private_key, 'wb+')
        return True
    return False


def getSSHPort():
    try:
        file = '/etc/ssh/sshd_config'
        conf = readFile(file)
        rep = "(#*)?Port\\s+([0-9]+)\\s*\n"
        port = re.search(rep, conf).groups(0)[1]
        return int(port)
    except Exception as _e:
        return 22


def getSSHStatus():
    if os.path.exists('/usr/bin/apt-get'):
        status = execShell("service ssh status | grep -P '(dead|stop)'")
    else:
        import system_api
        version = system_api.system_api().getSystemVersion()
        if version.find(' Mac ') != -1:
            return True
        if version.find(' 7.') != -1:
            status = execShell("systemctl status sshd.service | grep 'dead'")
        else:
            status = execShell(
                "/etc/init.d/sshd status | grep -e 'stopped' -e '已停'")
    if len(status[0]) > 3:
        status = False
    else:
        status = True
    return status

##################### ssl  end #########################################

def getGlibcVersion():
    try:
        cmd_result = execShell("ldd --version")[0]
        if not cmd_result: return ''
        glibc_version = cmd_result.split("\n")[0].split()[-1]
    except Exception as _e:
        return ''
    return glibc_version

##################### ssh  start #########################################
def getSshDir():
    if isAppleSystem():
        user = execShell("who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return '/Users/' + user + '/.ssh'
    return '/root/.ssh'


def processExists(pname, exe=None, cmdline=None):
    # 进程是否存在
    try:
        import psutil
        pids = psutil.pids()
        for pid in pids:
            try:
                p = psutil.Process(pid)
                if p.name() == pname:
                    if not exe and not cmdline:
                        return True
                    else:
                        if exe:
                            if p.exe() == exe:
                                return True
                        if cmdline:
                            if cmdline in p.cmdline():
                                return True
            except Exception as _e:
                pass
        return False
    except Exception as _e:
        return True


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


def createSshInfo():
    ssh_dir = getSshDir()
    if not os.path.exists(ssh_dir + '/id_rsa') or not os.path.exists(ssh_dir + '/id_rsa.pub'):
        createRsa()

    # 检查是否写入authorized_keys
    data = execShell("cat " + ssh_dir + "/id_rsa.pub | awk '{print $3}'")
    if data[0] != "":
        cmd = "cat " + ssh_dir + "/authorized_keys | grep " + data[0]
        ak_data = execShell(cmd)
        if ak_data[0] == "":
            cmd = 'cat ' + ssh_dir + '/id_rsa.pub >> ' + ssh_dir + '/authorized_keys'
            execShell(cmd)
            execShell('chmod 600 ' + ssh_dir + '/authorized_keys')


def connectSsh():
    import paramiko
    ssh = paramiko.SSHClient()
    createSshInfo()
    # B507 豁免：仅连接本机 127.0.0.1/localhost 的面板 SSH，主机密钥为面板自己生成
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507  # 仅连本机 127.0.0.1

    port = getSSHPort()
    try:
        ssh.connect('127.0.0.1', port, timeout=5)
    except Exception as e:
        ssh.connect('localhost', port, timeout=5)
    except Exception as e:
        ssh.connect(getHostAddr(), port, timeout=30)
    except Exception as e:
        return False

    shell = ssh.invoke_shell(term='xterm', width=83, height=21)
    shell.setblocking(0)
    return shell


def clearSsh():
    # 服务器IP
    ip = getHostAddr()
    sh = '''
#!/bin/bash
PLIST=`who | grep localhost | awk '{print $2}'`
for i in $PLIST
do
    ps -t /dev/$i |grep -v TTY | awk '{print $1}' | xargs kill -9
done

# getHostAddr
PLIST=`who | grep "${ip}" | awk '{print $2}'`
for i in $PLIST
do
    ps -t /dev/$i |grep -v TTY | awk '{print $1}' | xargs kill -9
done
'''
    if not isAppleSystem():
        info = execShell(sh)
        print(info[0], info[1])
##################### ssh  end   #########################################
        
##################### notify  start #########################################


def initNotifyConfig():
    p = getNotifyPath()
    if not os.path.exists(p):
        writeFile(p, '{}')
    return True


def getNotifyPath():
    path = 'data/notify.json'
    return path


def getNotifyData(is_parse=False):
    initNotifyConfig()
    notify_file = getNotifyPath()
    notify_data = readFile(notify_file)

    data = json.loads(notify_data)

    if is_parse:
        tag_list = ['tgbot', 'email']
        for t in tag_list:
            if t in data and 'cfg' in data[t]:
                data[t]['data'] = json.loads(deDoubleCrypt(t, data[t]['cfg']))
    return data


def writeNotify(data):
    p = getNotifyPath()
    return writeFile(p, json.dumps(data))


def tgbotNotifyChatID():
    data = getNotifyData(True)
    if 'tgbot' in data and 'enable' in data['tgbot']:
        if data['tgbot']['enable']:
            t = data['tgbot']['data']
            return t['chat_id']
    return ''


def tgbotNotifyObject():
    data = getNotifyData(True)
    if 'tgbot' in data and 'enable' in data['tgbot']:
        if data['tgbot']['enable']:
            t = data['tgbot']['data']
            import telebot
            bot = telebot.TeleBot(app_token)
            return True, bot
    return False, None


def tgbotNotifyMessage(app_token, chat_id, msg):
    import telebot
    bot = telebot.TeleBot(app_token)
    try:
        data = bot.send_message(chat_id, msg)
        return True
    except Exception as e:
        writeFileLog(str(e))
    return False


def tgbotNotifyHttpPost(app_token, chat_id, msg):
    try:
        url = 'https://api.telegram.org/bot' + app_token + '/sendMessage'
        post_data = {
            'chat_id': chat_id,
            'text': msg,
        }
        rdata = httpPost(url, post_data)
        return True
    except Exception as e:
        writeFileLog(str(e))
        return str(e)
    return False


def tgbotNotifyTest(app_token, chat_id):
    msg = 'MW-通知验证测试OK'
    return tgbotNotifyHttpPost(app_token, chat_id, msg)


def emailNotifyMessage(data):
    '''
    邮件通知
    '''
    import utils.email as email
    try:
        if data['smtp_ssl'] == 'ssl':
            r = email.sendSSL(data['smtp_host'], data['smtp_port'],
                           data['username'], data['password'],
                           data['to_mail_addr'], data['subject'], data['content'])
        else:
            r = email.send(data['smtp_host'], data['smtp_port'],
                        data['username'], data['password'],
                        data['to_mail_addr'], data['subject'], data['content'])

            print(r)
        return True
    except Exception as e:
        print(getTracebackInfo())
        return str(e)
    return False


def emailNotifyTest(data):
    # print(data)
    data['subject'] = 'MW通知测试'
    data['content'] = data['mail_test']
    return emailNotifyMessage(data)


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


def notifyMessage(msg, stype='common', trigger_time=300, is_write_log=True):
    try:
        return notifyMessageTry(msg, stype, trigger_time, is_write_log)
    except Exception as e:
        writeFileLog(getTracebackInfo())
        return False


##################### notify  end #########################################

# ---------------------------------------------------------------------------------
# 打印相关 START
# ---------------------------------------------------------------------------------

def echoStart(tag):
    print("=" * 89)
    print("★开始{}[{}]".format(tag, formatDate()))
    print("=" * 89)


def echoEnd(tag):
    print("=" * 89)
    print("☆{}完成[{}]".format(tag, formatDate()))
    print("=" * 89)


def echoInfo(msg):
    print("|-{}".format(msg))

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

