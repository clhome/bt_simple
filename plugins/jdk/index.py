# coding: utf-8
# ---------------------------------------------------------------------------------
# 御风面板
# ---------------------------------------------------------------------------------
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# JAVA环境管理器
# ---------------------------------------------------------------------------------

import os, sys, json, re
from urllib.parse import urlparse


# 御风面板路径
web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)
import core.yf as yf
import logging

_log = logging.getLogger('yf.jdk')

#: 允许作为面板安装目录名的版本号（如 jdk-8 / jdk-21）。
#  该值会进入目录路径、脚本文件名与 shell 命令，必须严格白名单：
#  不含 `/`、`..`、空白、引号与任何 shell 元字符。
_JDK_VERSION_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._\-]{0,31}$')

#: 允许下载 JDK 的镜像主机白名单。url 完全来自前端回显（download_url），
#  面板以 root 身份对它发起 HEAD 预检与 wget，任意主机即等于 root SSRF，
#  故只放行面板自身的镜像来源。
_JDK_URL_HOSTS = (
    'mirrors.tuna.tsinghua.edu.cn',
    'mirrors.aliyun.com',
    'mirrors.cloud.tencent.com',
    'mirrors.huaweicloud.com',
    'github.com',
    'objects.githubusercontent.com',
    'api.adoptium.net',
)

#: 绝不允许作为 JDK 主目录 / 删除目标的系统目录（纵深防御，主判据是「必须是面板 JDK 目录的直接子目录」）
_FORBIDDEN_DIRS = (
    '/', '/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/boot',
    '/dev', '/proc', '/sys', '/var', '/root', '/home', '/www', '/opt', '/tmp',
)

#: 面板设置默认 JDK 时写出的环境变量文件与软链（卸载时按需回收）
_JAVA_PROFILE = '/etc/profile.d/java.sh'
_JAVA_LINKS = ('/usr/bin/java', '/usr/bin/javac')


def _as_text(value):
    """把入参归一为去空白字符串；非字符串（None/int/list…）一律返回空串。

    插件入参来自前端 JSON，历史实现直接 `.strip()` / `os.path.*()`，
    非字符串会抛 AttributeError/TypeError → HTTP 500。
    """
    if isinstance(value, str):
        return value.strip()
    return ''


def _is_under(path, root):
    """realpath 包含判定：path 必须真实位于 root 之下（含软链解析）。"""
    if not path or not root:
        return False
    try:
        rp = os.path.realpath(path)
        rr = os.path.realpath(root)
    except Exception:
        return False
    return rp == rr or rp.startswith(rr + os.sep)


def _link_points_to(link, target):
    """软链 link 是否指向 target（设置默认 JDK 后回读确认，避免假成功）。"""
    try:
        if not os.path.islink(link):
            return False
        return os.path.realpath(link) == os.path.realpath(target)
    except Exception:
        return False


def _valid_jdk_version(version):
    if not version or not isinstance(version, str):
        return False
    if '..' in version:
        return False
    return bool(_JDK_VERSION_RE.match(version))


def _valid_jdk_url(url):
    """只放行「受信镜像 + http(s) + .tar.gz」的下载地址。"""
    if not url or not isinstance(url, str):
        return False
    if any(ch in url for ch in (' ', '\t', '\n', '\r', '"', "'", '`', '\\', ';', '|', '&', '$', '<', '>')):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if host not in _JDK_URL_HOSTS:
        return False
    return parsed.path.endswith('.tar.gz')


def _normalize_jdk_items(items):
    """过滤在线版本清单：只保留 version 合法、url 合法的条目。

    清单来自本地缓存（可能被截断/手改）与镜像站 HTML 解析结果，
    旧实现直接 `jdk['version']` 取值 → 畸形条目即 KeyError/TypeError 500。
    """
    ret = []
    if not isinstance(items, list):
        return ret
    for item in items:
        if not isinstance(item, dict):
            continue
        version = item.get('version')
        url = item.get('url')
        if _valid_jdk_version(version) and _valid_jdk_url(url):
            ret.append({'version': version, 'url': url})
    return ret


class jdk_main:
    _panel_path = yf.getPanelDir()
    _plugin_path = yf.getPluginDir() + '/jdk'
    _java_dir = yf.getServerDir() + '/jdk'
    _config_file = _plugin_path + '/data.json'

    def __init__(self):
        if not os.path.exists(self._plugin_path):
            os.makedirs(self._plugin_path)
        if not os.path.exists(self._java_dir):
            os.makedirs(self._java_dir)
        if not os.path.exists(self._config_file):
            yf.writeFile(self._config_file, json.dumps({"custom": [], "default": ""}))

        # 自动生成 version.pl 以便面板首页识别版本
        version_pl = self._java_dir + '/version.pl'
        if not os.path.exists(version_pl):
            yf.writeFile(version_pl, '1.0')

    def get_config(self):
        """读取 data.json 并归一化；缺失/畸形/结构非法时回退空配置。

        旧实现 `json.loads(yf.readFile(...))`：readFile 失败返回 False、
        内容畸形抛 JSONDecodeError、顶层非 dict 再 AttributeError，三条路径都会 500。
        """
        raw = yf.readFile(self._config_file)
        if not raw or not isinstance(raw, str):
            return {"custom": [], "default": ""}
        try:
            config = json.loads(raw)
        except Exception as e:
            _log.debug('[jdk] data.json 解析失败，回退空配置: %s', e)
            return {"custom": [], "default": ""}
        if not isinstance(config, dict):
            return {"custom": [], "default": ""}

        custom = config.get("custom")
        if not isinstance(custom, list):
            custom = []
        custom = [c.strip() for c in custom if isinstance(c, str) and c.strip()]

        default = config.get("default")
        if not isinstance(default, str):
            default = ""
        return {"custom": custom, "default": default}

    def _save_config(self, config):
        return yf.writeFile(self._config_file, json.dumps(config))

    def get_online_jdks(self, force_update=False):
        cache_file = self._plugin_path + '/versions.json'
        default_jdks = [
            {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u492b09.tar.gz"},
            {"version": "jdk-11", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/11/jdk/x64/linux/OpenJDK11U-jdk_x64_linux_hotspot_11.0.31_11.tar.gz"},
            {"version": "jdk-17", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.19_10.tar.gz"},
            {"version": "jdk-21", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.11_10.tar.gz"}
        ]

        if not force_update and os.path.exists(cache_file):
            content = yf.readFile(cache_file)
            if content and isinstance(content, str):
                try:
                    cached = _normalize_jdk_items(json.loads(content))
                    if cached:
                        return cached
                except Exception as e:
                    _log.debug('[jdk] 在线版本缓存解析失败，改为重新获取: %s', e)

        import urllib.request
        updated_jdks = []
        for jdk in default_jdks:
            v_num = jdk['version'].split('-')[1]
            base_url = f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/{v_num}/jdk/x64/linux/"
            try:
                req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    html = response.read().decode('utf-8')
                    pattern = r'href="(OpenJDK' + v_num + r'U-jdk_x64_linux_hotspot_[^"]+\.tar\.gz)"'
                    matches = re.findall(pattern, html)
                    if matches:
                        latest_file = sorted(matches)[-1]
                        candidate = base_url + latest_file
                        # 镜像返回的文件名不可信：仍按同一套 url 白名单校验后才采用
                        if _valid_jdk_url(candidate):
                            updated_jdks.append({"version": jdk['version'], "url": candidate})
                            continue
            except Exception as e:
                _log.debug('[jdk] get_online_jdks 异常已忽略: %s', e)
            updated_jdks.append(jdk)

        yf.writeFile(cache_file, json.dumps(updated_jdks))
        return updated_jdks

    def _is_installing(self, version):
        r"""是否存在正在下载该版本的 wget 进程。

        旧实现走 `ps` + `grep` 管道（版本号直接拼进 grep 模式），且要靠排除自身
        `sh -c` 命令行才不假报；改为列表化 pgrep（无 shell），并在 Python 侧精确匹配。
        改为列表化 pgrep（无 shell），并在 Python 侧做精确匹配。
        """
        if not version or not isinstance(version, str):
            return False
        try:
            rc, out, _ = yf.execShellRc(['pgrep', '-af', 'wget'], shell=False, timeout=10)
        except Exception as e:
            _log.debug('[jdk] 安装中判定失败: %s', e)
            return False
        if rc != 0 or not out:
            return False
        for line in out.splitlines():
            if 'wget' in line and version in line:
                return True
        return False

    def get_jdk_list(self, args=None):
        """获取所有JDK列表 (包括预设在线版本和已安装版本)"""
        ret = []
        config = self.get_config()
        default_jdk = config.get("default", "")

        # 1. 获取在线版本 (带本地缓存)
        online_jdks = self.get_online_jdks()
        custom_jdks = config.get("custom", [])

        # 检查在线版本是否已安装
        for jdk in online_jdks:
            jdk_path = self._java_dir + '/' + jdk['version'] + '/bin/java'
            if os.path.exists(jdk_path):
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": jdk_path,
                    "operation": 1, "is_default": (jdk_path == default_jdk), "download_url": jdk['url']
                })
            elif self._is_installing(jdk['version']):
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 3, "is_default": False, "download_url": jdk['url']
                })
            else:
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 0, "is_default": False, "download_url": jdk['url']
                })

        # 2. 本地自定义 JDK
        for custom_path in custom_jdks:
            if os.path.exists(custom_path):
                ret.append({
                    "name": "自定义JDK", "type": "用户自定义", "path": custom_path,
                    "operation": 2, "is_default": (custom_path == default_jdk)
                })

        # 3. 检查系统预装 JDK
        sys_java = '/usr/bin/java'
        if os.path.exists(sys_java):
            real_sys_java = os.path.realpath(sys_java)
            # 防止重复添加（如果它是指向面板已安装JDK的软连接，则不显示）
            if not any(x['path'] == sys_java or x['path'] == real_sys_java for x in ret):
                ret.append({
                    "name": "系统自带JDK", "type": "系统预装", "path": sys_java,
                    "operation": 4, "is_default": (sys_java == default_jdk)
                })

        # 纯粹按照版本号降序排列
        def get_ver(name):
            m = re.search(r'\d+', name)
            return int(m.group()) if m else 0

        ret = sorted(ret, key=lambda x: -get_ver(x['name']))
        return yf.returnJson(True, ret)

    def add_custom_jdk(self, args):
        """添加自定义JDK"""
        path = _as_text(args.get("path"))
        if not path or not os.path.isabs(path) or not path.endswith('/bin/java'):
            return yf.returnJson(False, 'jdk.invalid_path')
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            return yf.returnJson(False, 'jdk.path_not_exists')

        # 列表化执行（不经过 shell）：路径来自用户，拼串即等于 root 命令注入
        try:
            rc, out, err = yf.execShellRc([path, '-version'], shell=False, timeout=15)
        except Exception as e:
            _log.debug('[jdk] 自定义JDK校验失败: %s', e)
            return yf.returnJson(False, 'jdk.verify_failed')
        if rc != 0 or 'version' not in (out + err):
            return yf.returnJson(False, 'jdk.verify_failed')

        config = self.get_config()
        if path in config["custom"]:
            return yf.returnJson(False, 'jdk.already_exists')

        config["custom"].append(path)
        if not self._save_config(config):
            return yf.returnJson(False, 'jdk.save_failed')
        return yf.returnJson(True, 'jdk.add_success')

    def install_jdk(self, args):
        """发起后台下载并解压"""
        version = _as_text(args.get("version"))
        url = _as_text(args.get("download_url"))
        if not version or not url:
            return yf.returnJson(False, 'jdk.param_error')
        # version 会进入目录路径、脚本文件名与脚本正文；url 会进入 wget 命令与 HEAD 预检。
        # 两者都是前端回显值，必须以白名单拦住路径穿越 / 命令注入 / SSRF。
        if not _valid_jdk_version(version):
            return yf.returnJson(False, 'jdk.invalid_version')
        if not _valid_jdk_url(url):
            return yf.returnJson(False, 'jdk.invalid_url')

        dest_dir = self._java_dir + '/' + version
        # 纵深防御：即使白名单被绕过，安装目录也必须落在面板 JDK 目录之内
        if not _is_under(dest_dir, self._java_dir) or os.path.realpath(os.path.dirname(dest_dir)) != os.path.realpath(self._java_dir):
            return yf.returnJson(False, 'jdk.invalid_version')

        # 下载前预检URL，如果404则自动刷新提取最新版本
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                online_jdks = self.get_online_jdks(force_update=True)
                for jdk in online_jdks:
                    if jdk['version'] == version:
                        url = jdk['url']
                        break
        except Exception as e:
            # 忽略其他网络错误，交由bash脚本处理
            _log.debug('[jdk] install_jdk 预检异常已忽略: %s', e)

        java_bin = dest_dir + '/bin/java'
        if os.path.exists(java_bin):
            return yf.returnJson(False, 'jdk.already_installed')

        # 如果存在空目录（上次安装失败残留），先清理
        if os.path.exists(dest_dir):
            yf.removeDir(dest_dir)

        # 写入安装脚本并投递至任务队列
        import thisdb
        script_file = self._plugin_path + '/install_' + version + '.sh'
        tarball = version + '.tar.gz'
        q = yf.shlexQuote
        script_content = f"""#!/bin/bash
mkdir -p {q(dest_dir)}
cd {q(self._java_dir)}
wget --timeout=60 --tries=3 -O {q(tarball)} {q(url)}
if [ $? -ne 0 ]; then
    echo 'JDK {version} 下载失败，请检查网络连接'
    rm -f {q(tarball)}
    rm -rf {q(dest_dir)}
    exit 1
fi
tar -zxf {q(tarball)} -C {q(dest_dir)} --strip-components=1
if [ ! -f {q(java_bin)} ]; then
    echo 'JDK {version} 解压异常，未找到 bin/java'
    rm -f {q(tarball)}
    rm -rf {q(dest_dir)}
    exit 1
fi
rm -f {q(tarball)}
chmod +x {q(dest_dir + '/bin')}/*
echo 'JDK {version} 安装完成'
""".replace('\r\n', '\n')
        # 上面所有插值都经 shlexQuote；echo 里的 {version} 已由 _JDK_VERSION_RE 白名单保证无 shell 元字符
        if not yf.writeFile(script_file, script_content):
            return yf.returnJson(False, 'jdk.task_added_failed')
        cmd = f"bash {q(script_file)}"
        title = f'安装JDK-{version}'
        thisdb.addTask(name=title, cmd=cmd, status=0)
        yf.triggerTask()
        return yf.returnJson(True, 'jdk.task_added')

    def _managed_java_home(self, path):
        """把「<面板JDK目录>/<版本>/bin/java」还原为受管主目录；不合规返回 None。

        旧实现直接 `rm -rf {dirname(dirname(path))}`：path='/etc/passwd' 时
        dirname 两次得到 `/`，即 root 执行 `rm -rf /`；path 为任意深层路径时
        会递归删掉其祖父目录。这里要求主目录必须是面板 JDK 目录的直接子目录。
        """
        if not path or not isinstance(path, str) or not os.path.isabs(path) or os.path.basename(path) != 'java':
            return None
        home = os.path.normpath(os.path.dirname(os.path.dirname(path)))
        if home in _FORBIDDEN_DIRS or home == os.path.normpath(self._java_dir):
            return None
        java_dir = os.path.realpath(self._java_dir)
        if os.path.realpath(os.path.dirname(home)) != java_dir:
            return None
        return home

    def _drop_java_links(self, home):
        """回收面板建立的 /usr/bin/java(javac) 软链——仅当它指向被卸载的主目录。"""
        for link in _JAVA_LINKS:
            try:
                if os.path.islink(link) and _is_under(os.path.realpath(link), home):
                    os.unlink(link)
            except Exception as e:
                _log.debug('[jdk] 清理软链 %s 失败: %s', link, e)

    def uninstall_jdk(self, args):
        """卸载/移除JDK"""
        path = _as_text(args.get("path"))
        jdk_type = _as_text(args.get("type"))

        config = self.get_config()

        if jdk_type == '面板安装':
            home = self._managed_java_home(path)
            if home is None:
                return yf.returnJson(False, 'jdk.invalid_path')
            # 校验是否被使用
            try:
                rc, out, _ = yf.execShellRc(['lsof', '+D', home], shell=False, timeout=30)
            except Exception as e:
                _log.debug('[jdk] 占用检查失败: %s', e)
                return yf.returnJson(False, 'jdk.uninstall_failed')
            if out and out.strip():
                return yf.returnJson(False, 'jdk.in_use_error')
            # 删除前二次校验（realpath 之后仍需是受管主目录）
            if self._managed_java_home(home + '/bin/java') != home:
                return yf.returnJson(False, 'jdk.invalid_path')
            try:
                rc, out, err = yf.execShellRc(['rm', '-rf', home], shell=False, timeout=120)
            except Exception as e:
                _log.debug('[jdk] 卸载失败: %s', e)
                return yf.returnJson(False, 'jdk.uninstall_failed')
            if rc != 0 or os.path.exists(home):
                return yf.returnJson(False, 'jdk.uninstall_failed')
            self._drop_java_links(home)
        elif jdk_type == '用户自定义':
            if path in config.get("custom", []):
                config["custom"].remove(path)
            else:
                return yf.returnJson(False, 'jdk.path_not_exists')
        else:
            return yf.returnJson(False, 'jdk.param_error')

        if config.get("default") == path:
            config["default"] = ""
            # 清除环境变量（旧实现还跟着 `source /etc/profile`，在子 shell 里毫无作用）
            yf.execShellRc(['rm', '-f', _JAVA_PROFILE], shell=False, timeout=10)

        if not self._save_config(config):
            return yf.returnJson(False, 'jdk.save_failed')
        return yf.returnJson(True, 'jdk.uninstall_success')

    def set_default_jdk(self, args):
        """设置系统级默认全局JAVA_HOME"""
        path = _as_text(args.get("path"))
        if not path or not os.path.isabs(path) or not path.endswith('/bin/java'):
            return yf.returnJson(False, 'jdk.invalid_path')
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            return yf.returnJson(False, 'jdk.path_not_exists')

        java_home = os.path.normpath(os.path.dirname(os.path.dirname(path)))
        # java_home 会被写进 /etc/profile.d/java.sh（登录 shell 以 root 读取执行），
        # 必须是真实存在的目录、且不是系统根目录，否则等于把 /etc 之类目录当作 JAVA_HOME。
        if not os.path.isdir(java_home) or java_home in _FORBIDDEN_DIRS:
            return yf.returnJson(False, 'jdk.invalid_path')
        if any(ch in java_home for ch in ('\n', '\r', '\x00')):
            return yf.returnJson(False, 'jdk.invalid_path')

        q = yf.shlexQuote
        env_content = (
            "export JAVA_HOME={0}\n"
            "export PATH=$JAVA_HOME/bin:$PATH\n"
            "export CLASSPATH=.:$JAVA_HOME/lib/dt.jar:$JAVA_HOME/lib/tools.jar\n"
        ).format(q(java_home)).replace('\r\n', '\n')
        if not yf.writeFile(_JAVA_PROFILE, env_content):
            return yf.returnJson(False, 'jdk.set_default_failed')
        if 'JAVA_HOME=' not in (yf.readFile(_JAVA_PROFILE) or ''):
            return yf.returnJson(False, 'jdk.set_default_failed')

        # 建立软连接，让当前已打开的终端也能立刻生效
        yf.execShellRc(['ln', '-sf', java_home + '/bin/java', '/usr/bin/java'], shell=False, timeout=10)
        yf.execShellRc(['ln', '-sf', java_home + '/bin/javac', '/usr/bin/javac'], shell=False, timeout=10)
        if not _link_points_to('/usr/bin/java', path):
            return yf.returnJson(False, 'jdk.set_default_failed')

        # 保存到配置文件
        config = self.get_config()
        config["default"] = path
        if not self._save_config(config):
            return yf.returnJson(False, 'jdk.save_failed')

        return yf.returnJson(True, 'jdk.set_default_success')


def getArgs():
    tmp = {}
    # 从 sys.argv[2:] 开始扫描，兼容面板框架 version 为空时索引偏移的情况
    scan_args = sys.argv[2:]
    if not scan_args:
        return tmp

    args_str = " ".join(scan_args).strip()
    if (args_str.startswith("'") and args_str.endswith("'")) or (args_str.startswith('"') and args_str.endswith('"')):
        args_str = args_str[1:-1].strip()

    # 尝试直接解析整个拼接字符串
    try:
        parsed = json.loads(args_str)
        if isinstance(parsed, dict):
            return parsed
    except Exception as _e:
        _log.debug('[jdk] getArgs 异常已忽略: %s', _e)

    # 逐个元素尝试解析 JSON
    for arg in scan_args:
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
            _log.debug('[jdk] getArgs 异常已忽略: %s', _e)
            continue

    # 兼容 key:value 格式
    if ":" in args_str:
        try:
            parts = args_str.split(",")
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    tmp[k.strip().strip("'").strip('"')] = v.strip().strip("'").strip('"')
        except Exception as _e:
            _log.debug('[jdk] getArgs 异常已忽略: %s', _e)
    return tmp

if __name__ == "__main__":
    if len(sys.argv) > 1:
        func = sys.argv[1]
        args = getArgs()
        plugin_obj = jdk_main()
        if hasattr(plugin_obj, func):
            func_obj = getattr(plugin_obj, func)
            print(func_obj(args))
        else:
            print('error')
