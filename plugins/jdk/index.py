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

#: 涉及 CVE-2026-91403 与 CVE-2026-114820 的弱私钥根证书别名
_VULN_CA_ALIASES = (
    'emsignrootcag1 [jdk]',
    'emsignrootcag2 [jdk]',
    'emsigneccrootcag3 [jdk]',
    'comodoaaaca [jdk]',
    'emsignrootcag1',
    'emsignrootcag2',
    'emsigneccrootcag3',
    'comodoaaaca',
)


def _system_arch():
    """返回适配 Adoptium 镜像目录的架构名：'x64' 或 'aarch64'。"""
    import platform
    m = platform.machine().lower()
    if m in ('aarch64', 'arm64'):
        return 'aarch64'
    return 'x64'


def _jdk_filename_ver_key(filename):
    """提取文件名中的版本元组与 build 元组作为版本比对 key。
    严格区分 (version, build)，避免 build 号与子补丁版本混淆导致的字典序/段位倒挂。
    例：
      'OpenJDK21U-jdk_x64_linux_hotspot_21.0.13.0.2_1.tar.gz' -> ((21, 0, 13, 0, 2), (1,))
      'OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz'     -> ((21, 0, 13), (9,))
      'OpenJDK8U-jdk_x64_linux_hotspot_8u504b01.tar.gz'      -> ((8, 504), (1,))
    """
    m = re.search(r'hotspot_([0-9a-zA-Z._\-]+)\.tar\.gz$', filename)
    if not m:
        return ((), ())
    body = m.group(1)
    parts = re.split(r'[_b]', body, maxsplit=1)
    ver_str = parts[0]
    build_str = parts[1] if len(parts) > 1 else ''
    ver_tuple = tuple(int(x) for x in re.findall(r'\d+', ver_str))
    build_tuple = tuple(int(x) for x in re.findall(r'\d+', build_str))
    return (ver_tuple, build_tuple)


def _find_cacerts_path(path):
    """根据 java 可执行文件路径推导 cacerts 信任库路径。"""
    if not path or not isinstance(path, str):
        return None
    home = path
    if os.path.basename(path) == 'java':
        home = os.path.dirname(os.path.dirname(path))
    c1 = os.path.join(home, 'lib', 'security', 'cacerts')
    if os.path.isfile(c1):
        return c1
    c2 = os.path.join(home, 'jre', 'lib', 'security', 'cacerts')
    if os.path.isfile(c2):
        return c2
    return None


def _find_keytool_bin(path):
    """查找对应 JDK 的 keytool 可执行文件。"""
    if not path or not isinstance(path, str):
        return 'keytool'
    home = path
    if os.path.basename(path) == 'java':
        home = os.path.dirname(os.path.dirname(path))
    kt = os.path.join(home, 'bin', 'keytool')
    if os.path.isfile(kt) and os.access(kt, os.X_OK):
        return kt
    return 'keytool'


def _scan_cacerts_vuln_aliases(cacerts_path, keytool_bin='keytool'):
    """解析 cacerts，精确查找命中 CVE-2026-91403/114820 的证书，返回匹配到的实际别名列表。
    
    采用 keytool -list -v 结合 Owner DN、指纹与别名综合识别，支持标准 JDK 与 Temurin 等派生别名。
    """
    if not cacerts_path or not os.path.isfile(cacerts_path):
        return []
    
    found_aliases = set()

    # 1. 执行 keytool -list -v 详细模式
    try:
        rc, out, err = yf.execShellRc(
            [keytool_bin, '-list', '-v', '-keystore', cacerts_path, '-storepass', 'changeit'],
            shell=False, timeout=25
        )
        full_text = (out or '') + '\n' + (err or '')

        def evaluate_entry(alias, owner_text, lines_text):
            if not alias:
                return False
            low_alias = alias.lower()
            low_owner = owner_text.lower()
            low_all = (owner_text + ' ' + lines_text).lower()

            # 严格排除正常的 COMODO / Sectigo 根证书，严禁误删
            is_safe_comodo_or_sectigo = any(x in low_owner for x in (
                'comodo rsa certification authority',
                'comodo ecc certification authority',
                'sectigo public root e46',
                'sectigo public root r46',
                'sectigo public root e47',
                'sectigo public root r47',
            ))
            if is_safe_comodo_or_sectigo and 'aaa certificate services' not in low_owner and 'comodoaaaca' not in low_alias:
                return False

            # 目标 1: emSign Root CA - G1
            if 'emsign root ca - g1' in low_owner or 'emsign root ca g1' in low_owner:
                return True
            if 'emsignrootcag1' in low_alias or 'emsign_root_ca__g1' in low_alias or 'emsign_root_ca_g1' in low_alias:
                return True

            # 目标 2: emSign Root CA - G2
            if 'emsign root ca - g2' in low_owner or 'emsign root ca g2' in low_owner:
                return True
            if 'emsignrootcag2' in low_alias or 'emsign_root_ca__g2' in low_alias or 'emsign_root_ca_g2' in low_alias:
                return True

            # 目标 3: emSign ECC Root CA - G3
            if 'emsign ecc root ca - g3' in low_owner or 'emsign ecc root ca g3' in low_owner:
                return True
            if 'emsigneccrootcag3' in low_alias or 'emsign_ecc_root_ca__g3' in low_alias or 'emsign_ecc_root_ca_g3' in low_alias:
                return True

            # 目标 4: AAA Certificate Services (comodoaaaca)
            if 'cn=aaa certificate services' in low_owner or ('aaa certificate services' in low_owner and ('comodo' in low_all or 'sectigo' in low_all)):
                return True
            if 'comodoaaaca' in low_alias or 'aaa_certificate_services' in low_alias:
                return True

            return False

        current_alias = None
        current_owner = ''
        current_entry_lines = []

        for raw_line in full_text.splitlines():
            line = raw_line.strip()
            # 兼容中英文 keytool 别名起始行: "Alias name: ..." 或 "别名: ..." 等
            m_alias = re.match(r'^(?:Alias\s*name|别名|Alias-Name|别名名称)\s*:\s*(.+)$', line, re.I)
            if m_alias:
                if current_alias:
                    if evaluate_entry(current_alias, current_owner, '\n'.join(current_entry_lines)):
                        found_aliases.add(current_alias)
                current_alias = m_alias.group(1).strip()
                current_owner = ''
                current_entry_lines = []
                continue

            if current_alias:
                current_entry_lines.append(line)
                m_owner = re.match(r'^(?:Owner|所有者|Inhaber)\s*:\s*(.+)$', line, re.I)
                if m_owner:
                    current_owner = m_owner.group(1).strip()

        if current_alias:
            if evaluate_entry(current_alias, current_owner, '\n'.join(current_entry_lines)):
                found_aliases.add(current_alias)

    except Exception as e:
        _log.debug('[jdk] 解析 cacerts -v 异常: %s', e)

    # 2. 辅以 keytool -list 简单模式兜底（仅在 -v 详细解析未检出时兜底）
    if not found_aliases:
        try:
            rc, out, _ = yf.execShellRc(
                [keytool_bin, '-list', '-keystore', cacerts_path, '-storepass', 'changeit'],
                shell=False, timeout=15
            )
            if rc == 0 and out:
                for raw_line in out.splitlines():
                    line = raw_line.strip()
                    m_entry = re.search(r'^(.*?),\s*[^,]+,\s*(?:trustedCertEntry|PrivateKeyEntry)', line, re.I)
                    if m_entry:
                        alias_cand = m_entry.group(1).strip()
                    elif ',' in line:
                        alias_cand = line.rsplit(',', 2)[0].strip()
                    else:
                        alias_cand = line
                    low_fp = alias_cand.lower()
                    if any(target in low_fp for target in (
                        'emsignrootcag1', 'emsignrootcag2', 'emsigneccrootcag3', 'comodoaaaca',
                        'cn_emsign_root_ca__g1', 'cn_emsign_root_ca__g2', 'cn_emsign_ecc_root_ca__g3',
                        'aaa_certificate_services'
                    )):
                        found_aliases.add(alias_cand)
        except Exception as e:
            _log.debug('[jdk] 解析 cacerts -list 异常: %s', e)

    return sorted(list(found_aliases))


def _check_cacerts_vuln(cacerts_path, keytool_bin='keytool'):
    """检测 cacerts 中是否存在 CVE-2026-91403 / 114820 漏洞证书。"""
    if not cacerts_path or not os.path.isfile(cacerts_path):
        return False, []
    try:
        found = _scan_cacerts_vuln_aliases(cacerts_path, keytool_bin)
        return len(found) > 0, found
    except Exception as e:
        _log.debug('[jdk] 检测 cacerts 证书异常: %s', e)
        return False, []


def _fix_cacerts_vuln(cacerts_path, keytool_bin='keytool'):
    """删除受影响的弱私钥 CA 根证书（与 _check 共享同一识别逻辑）。"""
    if not cacerts_path or not os.path.isfile(cacerts_path):
        return False, 0

    # 动态扫描匹配到的真实别名
    aliases = _scan_cacerts_vuln_aliases(cacerts_path, keytool_bin)
    candidates = list(aliases)
    for fa in _VULN_CA_ALIASES:
        if fa not in candidates:
            candidates.append(fa)

    fixed_count = 0
    failed_count = 0
    for a in candidates:
        try:
            rc, out, err = yf.execShellRc(
                [keytool_bin, '-delete', '-alias', a, '-keystore', cacerts_path, '-storepass', 'changeit', '-noprompt'],
                shell=False, timeout=10
            )
            if rc == 0:
                fixed_count += 1
            else:
                if a in aliases:
                    failed_count += 1
                    _log.warning('[jdk] 目标证书别名 %s 删除失败: %s', a, (err or out).strip())
        except Exception as e:
            if a in aliases:
                failed_count += 1
            _log.debug('[jdk] 删除证书别名 %s 失败: %s', a, e)

    has_vuln, remaining = _check_cacerts_vuln(cacerts_path, keytool_bin)
    if has_vuln or failed_count > 0:
        return False, fixed_count
    return True, fixed_count


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
            yf.writeFile(version_pl, '1.1')

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
        arch = _system_arch()
        default_jdks = [
            {"version": "jdk-8", "url": f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/{arch}/linux/OpenJDK8U-jdk_{arch}_linux_hotspot_8u504b01.tar.gz"},
            {"version": "jdk-11", "url": f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/11/jdk/{arch}/linux/OpenJDK11U-jdk_{arch}_linux_hotspot_11.0.32.1_1.tar.gz"},
            {"version": "jdk-17", "url": f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/{arch}/linux/OpenJDK17U-jdk_{arch}_linux_hotspot_17.0.21_9.tar.gz"},
            {"version": "jdk-21", "url": f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/{arch}/linux/OpenJDK21U-jdk_{arch}_linux_hotspot_21.0.13_9.tar.gz"},
            {"version": "jdk-25", "url": f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/25/jdk/{arch}/linux/OpenJDK25U-jdk_{arch}_linux_hotspot_25.0.5_8.tar.gz"}
        ]

        if not force_update and os.path.exists(cache_file):
            content = yf.readFile(cache_file)
            if content and isinstance(content, str):
                try:
                    cached = _normalize_jdk_items(json.loads(content))
                    # 检查旧缓存是否过时（如缺少 jdk-25 或仍包含已 404 的老旧版本）
                    cached_vers = [c.get('version') for c in cached]
                    has_stale_url = any('8u492b09' in c.get('url', '') or '21.0.11' in c.get('url', '') for c in cached)
                    if cached and 'jdk-25' in cached_vers and not has_stale_url:
                        return cached
                except Exception as e:
                    _log.debug('[jdk] 在线版本缓存解析失败，改为重新获取: %s', e)

        import urllib.request
        updated_jdks = []
        for jdk in default_jdks:
            v_num = jdk['version'].split('-')[1]
            base_url = f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/{v_num}/jdk/{arch}/linux/"
            try:
                req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    html = response.read().decode('utf-8')
                    pattern = r'href="(OpenJDK' + v_num + r'U-jdk_' + arch + r'_linux_hotspot_[^"]+\.tar\.gz)"'
                    matches = re.findall(pattern, html)
                    if matches:
                        latest_file = max(matches, key=_jdk_filename_ver_key)
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

        def _attach_ca_status(item):
            p = item.get('path')
            if p and os.path.exists(p):
                cacerts = _find_cacerts_path(p)
                if cacerts:
                    kt = _find_keytool_bin(p)
                    has_vuln, aliases = _check_cacerts_vuln(cacerts, kt)
                    item['has_ca_vuln'] = has_vuln
                    item['ca_checked'] = True
                    item['vuln_aliases'] = aliases
                    return
            item['has_ca_vuln'] = False
            item['ca_checked'] = False
            item['vuln_aliases'] = []

        # 1. 获取在线版本 (带本地缓存)
        online_jdks = self.get_online_jdks()
        custom_jdks = config.get("custom", [])

        # 检查在线版本是否已安装
        for jdk in online_jdks:
            jdk_path = self._java_dir + '/' + jdk['version'] + '/bin/java'
            if os.path.exists(jdk_path):
                row = {
                    "name": jdk['version'], "type": "面板安装", "path": jdk_path,
                    "operation": 1, "is_default": (jdk_path == default_jdk), "download_url": jdk['url']
                }
                _attach_ca_status(row)
                ret.append(row)
            elif self._is_installing(jdk['version']):
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 3, "is_default": False, "download_url": jdk['url'],
                    "has_ca_vuln": False, "ca_checked": False
                })
            else:
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 0, "is_default": False, "download_url": jdk['url'],
                    "has_ca_vuln": False, "ca_checked": False
                })

        # 2. 本地自定义 JDK
        for custom_path in custom_jdks:
            if os.path.exists(custom_path):
                row = {
                    "name": "自定义JDK", "type": "用户自定义", "path": custom_path,
                    "operation": 2, "is_default": (custom_path == default_jdk)
                }
                _attach_ca_status(row)
                ret.append(row)

        # 3. 检查系统预装 JDK
        sys_java = '/usr/bin/java'
        if os.path.exists(sys_java):
            real_sys_java = os.path.realpath(sys_java)
            # 防止重复添加（如果它是指向面板已安装JDK的软连接，则不显示）
            if not any(x['path'] == sys_java or x['path'] == real_sys_java for x in ret):
                row = {
                    "name": "系统自带JDK", "type": "系统预装", "path": sys_java,
                    "operation": 4, "is_default": (sys_java == default_jdk)
                }
                _attach_ca_status(row)
                ret.append(row)

        # 纯粹按照版本号降序排列
        def get_ver(name):
            m = re.search(r'\d+', name)
            return int(m.group()) if m else 0

        ret = sorted(ret, key=lambda x: -get_ver(x['name']))
        return yf.returnJson(True, ret)

    def check_ca_security(self, args):
        """检测指定 JDK 的 cacerts 证书安全性"""
        path = _as_text(args.get('path'))
        if not path or not os.path.isabs(path):
            return yf.returnJson(False, '路径无效')
        cacerts = _find_cacerts_path(path)
        if not cacerts:
            return yf.returnJson(False, '未找到有效的 cacerts 信任库文件')
        kt = _find_keytool_bin(path)
        has_vuln, aliases = _check_cacerts_vuln(cacerts, kt)
        return yf.returnJson(True, {
            'has_vuln': has_vuln,
            'cacerts_path': cacerts,
            'aliases': aliases
        })

    def fix_ca_security(self, args):
        """对指定 JDK 执行 CVE-2026-91403 / 114820 证书加固（剔除受损根证书）"""
        path = _as_text(args.get('path'))
        if not path or not os.path.isabs(path):
            return yf.returnJson(False, '路径无效')
        cacerts = _find_cacerts_path(path)
        if not cacerts:
            return yf.returnJson(False, '未找到有效的 cacerts 信任库文件')
        kt = _find_keytool_bin(path)
        ok, count = _fix_cacerts_vuln(cacerts, kt)
        has_vuln, remaining = _check_cacerts_vuln(cacerts, kt)
        if has_vuln:
            return yf.returnJson(False, '加固失败，部分风险根证书未能成功清除')
        return yf.returnJson(True, '证书加固成功，已移除风险根证书')

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
_cacerts={q(dest_dir + '/lib/security/cacerts')}
[ -f "$_cacerts" ] || _cacerts={q(dest_dir + '/jre/lib/security/cacerts')}
_kt={q(dest_dir + '/bin/keytool')}
if [ -f "$_cacerts" ] && [ -x "$_kt" ]; then
    echo '正在执行 cacerts 安全加固 (清理 CVE-2026-91403/114820 风险根证书)...'
    for _alias in "emsignrootcag1 [jdk]" "emsignrootcag2 [jdk]" "emsigneccrootcag3 [jdk]" "comodoaaaca [jdk]" "emsignrootcag1" "emsignrootcag2" "emsigneccrootcag3" "comodoaaaca"; do
        "$_kt" -delete -alias "$_alias" -keystore "$_cacerts" -storepass changeit -noprompt >/dev/null 2>&1 || :
    done
    _dyn_aliases=$("$_kt" -list -keystore "$_cacerts" -storepass changeit 2>/dev/null | grep -iE 'emsign|aaa_certificate_services' | awk -F',' '{{print $1}}' | sed 's/^[ \t]*//;s/[ \t]*$//' || :)
    if [ -n "$_dyn_aliases" ]; then
        while IFS= read -r _d_alias; do
            [ -n "$_d_alias" ] && "$_kt" -delete -alias "$_d_alias" -keystore "$_cacerts" -storepass changeit -noprompt >/dev/null 2>&1 || :
        done <<< "$_dyn_aliases"
    fi
    echo 'cacerts 信任库安全加固完成'
fi
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
