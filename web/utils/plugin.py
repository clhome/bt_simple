# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import sys
import re
import json
import shlex
import shutil
import hashlib
import hmac
import secrets
import inspect
import threading
import multiprocessing
import zipfile

import core.yf as yf
import thisdb
import logging

_log = logging.getLogger('yf.plugin')


# ---------------------------------------------------------------------------------
# 插件名 / 路径安全校验（防御命令注入与目录穿越）
#   - 插件名严格白名单：字母、数字、下划线、短横线；
#   - 版本号白名单：数字/字母开头，其后为数字、字母、点、下划线、短横线（上限 32 字符）；
#   - 传入的临时目录必须真实位于面板 temp 目录内（realpath 比较，杜绝 ../ 逃逸与软链绕过）。
# ---------------------------------------------------------------------------------
_PLUGIN_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')
_PLUGIN_VERSION_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\-]{0,31}$')
# 首页展示清单条目（`插件名-版本`，版本可为空：历史数据里存在 `python_yf-`）
_PLUGIN_INDEX_ITEM_RE = re.compile(r'^[a-zA-Z0-9_\-]+-[a-zA-Z0-9._\-]*$')

def _valid_plugin_name(name):
    name = str(name or '').strip()
    return bool(name) and bool(_PLUGIN_NAME_RE.match(name))

def _valid_plugin_version(version):
    version = str(version or '').strip()
    return bool(version) and bool(_PLUGIN_VERSION_RE.match(version))

def _has_symlink(path):
    """目录树内是否存在符号链接。

    第三方插件包禁止软链：unzip 会原样还原包内软链，而 inputZipApi 的 copytree
    是「跟随软链」复制，等于把包外文件（/etc/shadow 等）复制成插件目录里的普通
    文件并可通过 /plugins/file 下载。
    """
    for root, dirs, files in os.walk(path):
        for item in list(dirs) + list(files):
            if os.path.islink(os.path.join(root, item)):
                return True
    return False

# ---------------------------------------------------------------------------------
# 插件 zip 包解压（P2-10）：解压**前**的成员校验
#   - 判据不另写：直接复用面板统一的 utils.file.safeArchiveCheck(pkg, dest, 'zip')；
#   - 照 P1-4（plugins/mysql/import_archive.py 的 _safeArchiveCheck）的范式：只在
#     调用时 import，取不到校验函数 / 校验抛异常一律 fail-closed，绝不做
#     「无法校验就当通过」的放行；
#   - 校验通过才 unzip；解压后的 _has_symlink 检查保留为第二道（纵深防御）。
# ---------------------------------------------------------------------------------
PLUGIN_ZIP_KIND = 'zip'


def _pluginArchiveCheck(zip_path, dest_dir):
    """调用面板统一的归档成员校验函数；取不到就抛（由调用方按 fail-closed 处理）。"""
    import utils.file as file_utils
    return file_utils.safeArchiveCheck(zip_path, dest_dir, PLUGIN_ZIP_KIND)


def _safeExtractPluginZip(zip_path, dest_dir):
    """先校验成员名、通过后才解压插件包。返回 `(ok, msg)`。

    `ok=False` 表示**一个成员都没有解压**（越界成员不会写到 dest_dir 内外），
    `msg` 是中文原因（校验被拒时含拒绝码，如 `parent_ref` / `absolute_path` /
    `symlink_escape`）；`ok=True` 时 `msg` 为空串。
    被拒的包本身与解压目录的清理由调用方负责（updateZip 里统一做）。
    """
    try:
        ok, code = _pluginArchiveCheck(zip_path, dest_dir)
    except Exception as _e:
        # 校验函数都跑不起来时同样拒绝（fail-closed）：
        # 放行等于把「无法校验」当成「没有风险」
        _log.warning('[plugin] 插件包成员校验无法执行(%s): %s', zip_path, _e)
        return False, '插件包成员校验无法执行，已拒绝解压（fail-closed）'
    if not ok:
        _log.warning('[plugin] 拒绝越界成员(%s): %s', zip_path, code)
        return False, '插件包含越界或非法成员，已拒绝解压（%s）' % code
    # 校验通过才解压（原行为：unzip 覆盖解压到面板 temp）
    yf.safeExecShell(['unzip', '-o', '-q', zip_path, '-d', dest_dir])
    return True, ''


def _checkPluginSourceDir(src_dir):
    """inputZipApi 的独立入口自校验：源目录树内不得有软链。返回 `(ok, code)`。

    为什么是软链而不是成员名：inputZipApi 不解压任何归档，它做的是
    `shutil.copytree`（默认跟随软链）。对应到 `utils.file.safeArchiveCheck` 的判据里，
    目录形态下唯一的「越界载体」就是软链（校验侧对应拒绝码 `symlink_escape` /
    `symlink_absolute`），故这里复用同一份检测 `_has_symlink`。
    单独调用 /plugins/input_zip 会绕过 updateZip，所以这个入口必须自校验。
    """
    try:
        if not os.path.isdir(src_dir):
            return False, 'bad_dir'
        if _has_symlink(src_dir):
            return False, 'symlink'
    except Exception as _e:
        # 校验跑不起来同样拒绝（fail-closed）
        _log.warning('[plugin] 插件源目录校验无法执行(%s): %s', src_dir, _e)
        return False, 'check_failed'
    return True, 'OK'


def _cleanupRejectedPluginPackage(zip_path, dest_dir, reason):
    """拒绝插件包后的清理：删掉临时 zip + 清空解压目录（保证零落地、无残留）。

    只动这两处：临时 zip 本体（确认是普通文件才删）与 `<面板>/temp` 解压目录
    （`yf.removeDir` 自带非法路径拒绝）。宁可不删，也绝不删目录外的文件。
    """
    yf.writeFileLog('[plugin] 拒绝插件包(%s): %s' % (reason, zip_path))
    try:
        if os.path.isfile(zip_path) and not os.path.islink(zip_path):
            os.remove(zip_path)
    except Exception as _e:
        _log.warning('[plugin] 删除被拒插件包失败(%s): %s', zip_path, _e)
    try:
        if os.path.isdir(dest_dir):
            yf.removeDir(dest_dir)
    except Exception as _e:
        _log.warning('[plugin] 清空插件解压目录失败(%s): %s', dest_dir, _e)


def _valid_script_name(name):
    name = str(name or '').strip()
    return bool(name) and bool(re.match(r'^[a-zA-Z0-9_]+$', name))

#: hook 条目里会被 layout.html / /plugins/menu 当作文件路径使用的字段
_HOOK_PATH_KEYS = ('path', 'css_path', 'js_path')


def _sanitize_hook_item(info):
    """净化第三方插件 info.json 的 hook 条目，返回 (是否可用, 净化后的条目)。

    为什么必须净化：这些条目会被写进 option(hook_menu/hook_global_static) 并原样喂给
    layout.html 与 /plugins/menu。
      - 条目缺 `name` 时，layout.html 的 `t('plugins.' + menu['name'] + '.title')`
        会抛 UndefinedError → **面板每一页都 500**（真机实测：一条坏条目即全站打不开）；
      - `path` 写绝对路径或 `../` 时，/plugins/menu 变成任意文件读，内容还会被 |safe 直出。
    因此只接受「name 合法 + title 非空 + 路径为插件目录内相对路径」的条目。
    """
    if not isinstance(info, dict):
        return False, None

    name = str(info.get('name') or '').strip()
    title = str(info.get('title') or '').strip()
    if not _valid_plugin_name(name) or not title:
        return False, None

    cleaned = dict(info)
    cleaned['name'] = name
    cleaned['title'] = title
    for key in _HOOK_PATH_KEYS:
        if key not in cleaned:
            continue
        val = str(cleaned.get(key) or '').strip()
        parts = val.replace('\\', '/').split('/')
        if not val or val.startswith('/') or '..' in parts:
            cleaned.pop(key, None)
        else:
            cleaned[key] = val
    return True, cleaned


def _path_inside(base, target):
    """target 的 realpath 是否严格位于 base 的 realpath 之内（含相等由调用方決定）。"""
    try:
        real_base = os.path.realpath(base).rstrip('/\\')
        real_target = os.path.realpath(target).rstrip('/\\')
        if not real_base or not real_target:
            return False
        return real_target == real_base or real_target.startswith(real_base + os.sep)
    except Exception:
        return False


# ---------------------------------------------------------------------------------
# 第三方插件包「安装前确认」（轻量信任边界，不建签名体系）
#   第三方 zip 里的 install.sh 会以 **root** 身份执行。本组函数把「执行什么」变成
#   管理员可见 + 需显式确认：安装前展示脚本文本，且安装请求必须携带一个**与包内容
#   强绑定**的确认凭据 confirm_token，否则拒绝安装。
#   - 凭据 = HMAC(服务端密钥, 插件名 + 包内容哈希)；包内容（含 install.sh/info.json）
#     一旦变化，旧凭据即失效；
#   - 只有经第三方 zip 导入通道（inputZipApi）落地的插件才受此约束，面板自带
#     `plugins/` 目录的官方插件与既有白名单渠道保持原样。
# ---------------------------------------------------------------------------------
#: 记录「经第三方 zip 导入」的插件名（服务端记录，包内容无法伪造）
_PLUGIN_THIRD_PARTY_OPTION = 'plugin_third_party_imports'
#: 展示给前端的安装脚本文本上限（防超大脚本撑爆响应）
_PLUGIN_SCRIPT_MAX_CHARS = 20000
_PLUGIN_CONFIRM_FALLBACK_SECRET = None
_PLUGIN_CONFIRM_SECRET_LOCK = threading.Lock()


def _plugin_confirm_secret():
    """确认凭据的服务端密钥：优先复用面板持久化的 session 密钥（跨 worker 一致）。"""
    global _PLUGIN_CONFIRM_FALLBACK_SECRET
    try:
        path = yf.getPanelDataDir() + '/secret_key.pl'
        if os.path.exists(path):
            key = (yf.readFile(path) or '').strip()
            if key:
                return key.encode('utf-8')
    except Exception as _e:
        _log.debug('[plugin] 读取面板密钥失败，回退到进程内密钥: %s', _e)
    # 退化路径（secret_key.pl 不可读/不可写）：进程内随机密钥。重启后旧凭据失效，
    # 属安全预期的失败方向，但仍可用。
    if _PLUGIN_CONFIRM_FALLBACK_SECRET is None:
        with _PLUGIN_CONFIRM_SECRET_LOCK:
            if _PLUGIN_CONFIRM_FALLBACK_SECRET is None:
                _PLUGIN_CONFIRM_FALLBACK_SECRET = secrets.token_bytes(32)
    return _PLUGIN_CONFIRM_FALLBACK_SECRET


def _plugin_package_hash(plugin_dir):
    """插件目录内容的确定性 sha256（相对路径 + 文件字节），用于把凭据绑定到包内容。

    刻意覆盖**整个目录**而非只覆盖 install.sh：包内容（含 info.json 的 shell/路径）
    任何一处变化都会让旧凭据失效。文件模式/时间戳不参与，保证同一内容得到同一哈希。
    """
    h = hashlib.sha256()
    for root, dirs, files in os.walk(plugin_dir):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root, fname)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, plugin_dir).replace('\\', '/')
            h.update(rel.encode('utf-8'))
            h.update(b'\x00')
            try:
                with open(full, 'rb') as fh:
                    h.update(fh.read())
            except OSError:
                h.update(b'<unreadable>')
            h.update(b'\x00')
    return h.hexdigest()


def _plugin_confirm_token(name, content_hash):
    """HMAC 确认凭据：与「插件名 + 包内容哈希」强绑定，只有服务端能签发。"""
    msg = ('%s:%s' % (name, content_hash)).encode('utf-8')
    return hmac.new(_plugin_confirm_secret(), msg, hashlib.sha256).hexdigest()


def _plugin_script_name(info):
    """将被 root 执行的脚本名（info.json 的 shell 字段）。

    只接受「插件目录内的普通文件名」：`install.sh` 通过，`../evil.sh` / `/etc/x` 一律
    拒绝。否则「展示 install.sh、实际执行别的脚本」会让确认环节形同虚设。
    """
    name = str((info or {}).get('shell') or 'install.sh').strip()
    if not name or name in ('.', '..'):
        return None
    if os.path.basename(name) != name or '/' in name or '\\' in name:
        return None
    return name


def _read_plugin_script(plugin_dir, info):
    """读取将被 root 执行的脚本文本（截断到上限）。

    返回 (脚本名, 文本)；脚本名非法 / 文件不存在 / 是软链时返回 (None, '')。
    """
    script = _plugin_script_name(info)
    if not script:
        return None, ''
    path = os.path.join(plugin_dir, script)
    if not os.path.isfile(path) or os.path.islink(path):
        return None, ''
    text = yf.readFile(path) or ''
    if len(text) > _PLUGIN_SCRIPT_MAX_CHARS:
        text = text[:_PLUGIN_SCRIPT_MAX_CHARS] + '\n...(truncated)'
    return script, text


def _plugin_is_third_party(name):
    """该插件是否来自第三方 zip 导入通道（服务端记录，包内容无法伪造）。"""
    names = thisdb.getOptionByJson(_PLUGIN_THIRD_PARTY_OPTION, default=[])
    return isinstance(names, list) and name in names


def _mark_plugin_third_party(name):
    """登记「经第三方 zip 导入」的插件名（幂等）。"""
    names = thisdb.getOptionByJson(_PLUGIN_THIRD_PARTY_OPTION, default=[])
    if not isinstance(names, list):
        names = []
    if name not in names:
        names.append(name)
        thisdb.setOption(_PLUGIN_THIRD_PARTY_OPTION, json.dumps(names))


def _verify_plugin_confirm_token(name, plugin_dir, token):
    """校验第三方插件的确认凭据。返回 (是否通过, 原因)。"""
    token = str(token or '').strip()
    if not token:
        return False, 'missing_token'
    if not os.path.isdir(plugin_dir):
        return False, 'no_plugin_dir'
    expected = _plugin_confirm_token(name, _plugin_package_hash(plugin_dir))
    if not hmac.compare_digest(expected, token):
        return False, 'token_mismatch'
    return True, ''


class pg_thread(threading.Thread):

    def __init__(self, func, args, name=''):
        threading.Thread.__init__(self)
        self.name = name
        self.func = func
        self.args = args
        self.result = None

    def run(self):
        try:
            self.result = self.func(*self.args)
        except Exception:
            self.result = None

    def getResult(self):
        return self.result

_PLUGIN_MODULE_LOCK = threading.RLock()
_PLUGIN_MODULE_MTIME = {}

#: 「PHP 只提供 8.2 及以上」：低于该分支的 PHP 不再出现在软件商店的**可安装**列表里。
#:
#: 口径（用户 2026-10-26 确定）：
#:   * 未安装的旧分支（如 74/80/81）→ 直接从列表里去掉，不再引导人装已停维版本；
#:   * 已安装了旧分支 → **保留在列表里**（否则用户无法停用/卸载），但标 `php_eol=True`，
#:     前端打红标「建议升级到 8.2 及以上」；
#:   * 用户把旧分支删了 → 下一次加载就不再出现（判存以 rpm/dpkg/非空二进制为准，
#:     不看目录残留）。
PHP_MIN_INSTALL_BRANCH = '82'


def _php_family(name):
    """是否本面板托管的 PHP 渠道插件（`php` 编译版 / `php-apt` / `php-yum`）。"""
    n = str(name or '').strip().lower()
    return n == 'php' or n.startswith('php-') or n.startswith('php_')


def _php_branch_of(version):
    """`84` → 84；非纯数字（如 `8.4`）→ 去掉点再转；判不了返回 0。"""
    raw = str(version or '').strip().replace('.', '')
    return int(raw) if raw.isdigit() else 0


class plugin(object):

    def_plugin_type = [
        {
            "title":"全部",
            "key":"soft.type_all",
            "type":0,
            "ps":""
        },
        {
            "title":"已安装",
            "key":"soft.type_installed",
            "type":-1,
            "ps":""
        },
        {
            "title":"运行环境",
            "key":"soft.type_runtime",
            "type":1,
            "ps":""
        },
        {
            "title":"数据库",
            "key":"soft.type_database",
            "type":2,
            "ps":""
        },
        # {
        #     "title":"代码管理",
        #     "key":"soft.type_code_mgr",
        #     "type":3,
        #     "ps":""
        # },
        {
            "title":"系统工具",
            "key":"soft.type_system_tools",
            "type":4,
            "ps":""
        },
        {
            "title":"其他插件",
            "key":"soft.type_other_plugins",
            "type":5,
            "ps":""
        },
        {
            "title":"PHP",
            "key":"soft.type_php",
            "type":6,
            "ps":""
        }

    ]

    __plugin_dir = 'plugins'
    __tasks = None

    __plugin_status_cachekey = 'plugin_list_status'
    __plugin_status_data = None

    __plugin_list_static_cache = None

    # lock
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(plugin, "_instance"):
            with plugin._instance_lock:
                if not hasattr(plugin, "_instance"):
                    plugin._instance = plugin(*args, **kwargs)
        return plugin._instance

    """插件类初始化"""
    def __init__(self):
        self.__plugin_dir = yf.getPluginDir()


    def refreshSetupStatus(self, plist):
        for pInfo in plist:
            pInfo['setup'] = os.path.exists(pInfo['install_checks'])
        return plist

    def _phpInstalledBranches(self):
        """本机**真正装了**的 PHP 分支（每个请求只算一次；判不了一律当没装）。"""
        if getattr(self, '_php_installed_cache', None) is not None:
            return self._php_installed_cache
        data = {'src': set(), 'apt': set(), 'yum': set()}
        try:
            from core import php_sec_scan
            data = php_sec_scan.installed_branches(run=php_sec_scan.make_runner(3))
        except Exception as _e:
            # 探测失败宁可「当没装」：旧分支会被隐藏，而不是把已卸的版本当已装留在列表里
            _log.debug('[plugin] 探测已装 PHP 分支失败: %s', _e)
        self._php_installed_cache = data
        return data

    def applyPhpVersionPolicy(self, plist):
        """PHP 只提供 `PHP_MIN_INSTALL_BRANCH` 及以上（见常量注释）。

        「已装」= 下面**任一**成立就保留（宁可多显示一条红标，也不能让用户找不到卸载入口）：
          * `install_checks` 目录存在 —— 这是面板自己的「已安装」口径，卸载时会被删掉，
            所以「删了就不显示」也由它保证；
          * 判存探针（`php_sec_scan.installed_branches()`）说装了 —— 覆盖「装过但目录不在这」
            的历史机器（例如装完后目录被手工动过）。
        两条都不成立 ⇒ 没装过，直接隐藏，不再引导人安装停止维护的版本。
        """
        if not plist:
            return plist
        floor = _php_branch_of(PHP_MIN_INSTALL_BRANCH)
        installed = None
        kept = []
        for pInfo in plist:
            name = pInfo.get('name', '')
            version = pInfo.get('versions', '')
            if not _php_family(name) or not isinstance(version, str):
                kept.append(pInfo)
                continue
            branch = _php_branch_of(version)
            if not branch or branch >= floor:
                kept.append(pInfo)
                continue
            if installed is None:
                installed = self._phpInstalledBranches()
            channel = 'apt' if str(name).endswith('-apt') else (
                'yum' if str(name).endswith('-yum') else 'src')
            is_installed = bool(pInfo.get('setup'))                 or str(branch) in installed.get(channel, set())
            if not is_installed:
                # 未安装的旧分支：不再提供安装入口（官方已停止维护）
                _log.debug('[plugin] 隐藏未安装的已停维 PHP 分支: %s-%s', name, version)
                continue
            pInfo['php_eol'] = True
            pInfo['php_eol_min'] = '%s.%s' % (PHP_MIN_INSTALL_BRANCH[0], PHP_MIN_INSTALL_BRANCH[1:])
            # 「已安装」也以真实安装为准（目录残留不算）
            pInfo['setup'] = True
            kept.append(pInfo)
        return kept


    def getIndexList(self, simple=False):
        indexList = thisdb.getOptionByJson('display_index', default=[])
        plist = []
        static_list = self.getStaticPluginList()
        for i in indexList:
            tmp = i.split('-')
            tmp_len = len(tmp)
            if tmp_len < 2:
                continue
            plugin_name = tmp[0]
            plugin_ver = tmp[1]
            if tmp_len > 2:
                tmpArr = tmp[0:tmp_len - 1]
                plugin_name = '-'.join(tmpArr)
                plugin_ver = tmp[tmp_len - 1]

            for p in static_list:
                if p.get('name') == plugin_name:
                    if p.get('coexist'):
                        if p.get('versions') == plugin_ver or plugin_ver in p.get('versions', ''):
                            p_copy = p.copy()
                            p_copy['display'] = True
                            plist.append(p_copy)
                            break
                    else:
                        p_copy = p.copy()
                        p_copy['display'] = True
                        plist.append(p_copy)
                        break

        plist = self.checkStatusMThreadsByCache(plist)

        if simple:
            simple_list = []
            for item in plist:
                simple_item = {
                    'name': item.get('name', ''),
                    'title': item.get('title', ''),
                    'setup_version': item.get('setup_version', ''),
                    'status': item.get('status', False),
                    'display_status': item.get('display_status', True),
                    'coexist': item.get('coexist', False),
                    'versions': item.get('versions', '')
                }
                simple_list.append(simple_item)
            plist = simple_list

        return yf.returnData(True, 'ok', plist)

    def init(self):
        not_rec_file = yf.getPanelDataDir() + '/not_recommend.pl'
        if os.path.exists(not_rec_file):
            return yf.returnData(False, 'ok')

        plugin_names = {
            'openresty': '1.31.1',
            'php': '80',
            'swap': '1.1',
            'mysql': '5.7',
            'phpmyadmin': '5.2.1',
        }

        pn_dir = yf.getPluginDir()
        pn_server_dir = yf.getServerDir()
        pn_list = []
        for pn in plugin_names:
            info = {}
            pn_json = pn_dir + '/' + pn + '/info.json'
            pn_server = pn_server_dir + '/' + pn
            if not os.path.exists(pn_server):

                tmp = yf.readFile(pn_json)
                try:
                    tmp = json.loads(tmp)
                except Exception as _e:
                    # 推荐列表依赖插件自带 info.json；缺失/损坏时跳过而不是 500
                    yf.writeFileLog('[plugin] 推荐安装读取 %s 失败: %s' % (pn_json, _e))
                    continue

                info['title'] = tmp.get('title', pn)
                info['name'] = tmp.get('name', pn)
                info['versions'] = tmp.get('versions', '')
                info['default_ver'] = plugin_names[pn]
                pn_list.append(info)
            else:
                return yf.returnData(False, 'ok')

        return yf.returnData(True, 'ok', pn_list)

    def setNotRecommend(self):
        not_rec_file = yf.getPanelDataDir() + '/not_recommend.pl'
        yf.writeFile(not_rec_file, '1')
        return yf.returnData(True, 'ok')

    def initInstall(self, plugin_list):
        try:
            self.setNotRecommend()
            pn_list = json.loads(plugin_list)
            if not isinstance(pn_list, list):
                pn_list = []
            pn_list = [x for x in pn_list if isinstance(x, dict)]
            # 对安装列表进行排序，确保 swap 放置在首位最先安装
            pn_list = sorted(pn_list, key=lambda x: 0 if x.get('name') == 'swap' else 1)
            queued = 0
            for pn in pn_list:
                name = str(pn.get('name', '')).strip()
                version = str(pn.get('version', '')).strip()
                # 安全：推荐安装列表来自客户端 JSON，逐项白名单校验后再拼路径/任务命令
                if not _valid_plugin_name(name) or not _valid_plugin_version(version):
                    yf.writeFileLog('[plugin] 跳过非法推荐安装项: name=%r version=%r' % (name, version))
                    continue
                # 推荐安装只面向面板自带的官方插件；第三方包必须走「安装前确认」通道
                if _plugin_is_third_party(name):
                    yf.writeFileLog('[plugin] 推荐安装跳过第三方插件（需安装前确认）: %s' % name)
                    continue
                info_file = self.__plugin_dir + '/' + name + '/' + 'info.json'
                pluginInfo = json.loads(yf.readFile(info_file))
                self.hookInstall(pluginInfo)

                cmd = 'cd {0} && bash {1} install {2}'.format(
                    yf.getPluginDir() + '/'+name,
                    pluginInfo['shell'],
                    version
                )
                title = '安装[' + name + '-' + version + ']'
                thisdb.addTask(name=title,cmd=cmd)
                queued += 1
            # /www/server/php 常因历史安装残留而存在：用幂等的 makeDirs，
            # 否则报 FileExistsError 时任务已入队但 triggerTask 永远不会执行（假安装）
            yf.makeDirs(yf.getServerDir() + '/php')
            if queued == 0:
                # 一个任务都没入队（空列表/全部非法）却回「添加成功」属于假成功
                return yf.returnData(False, 'ARGS_ERR')
            # 任务执行相关
            yf.triggerTask()
            return yf.returnData(True, 'common.add_success')
        except Exception as e:
            # 不把 traceback（带面板绝对路径）回给前端，只写日志
            yf.writeFileLog('[plugin] 推荐安装失败: %s\n%s' % (e, yf.getTracebackInfo()))
            return yf.returnData(False, 'ERROR')

    def menuGetAbsPath(self, tag, path):
        """插件菜单页文件（hook.menu.path）→ 绝对路径。

        安全：`path` 来自第三方插件 info.json。历史实现把绝对路径原样返回，
        于是 `path=/etc/passwd` 的插件包能让 GET /plugins/menu 读出任意文件
        （真机实测回显 root:x:0:0）。这里强制限定在 `plugins/<tag>/` 之内，
        越界/绝对路径一律不再被跟随。
        """
        tag = str(tag or '').strip()
        path = str(path or '').strip()
        if not _valid_plugin_name(tag) or not path:
            return None
        base = os.path.join(self.__plugin_dir, tag)
        # 路径校验统一按 **POSIX 口径**做，并把反斜杠也当分隔符：
        #   * 绝对路径（`/` 或 `\` 开头）拒绝；
        #   * 任一 `..` 段拒绝。`..\..\x.html` 在 POSIX 上其实不是穿越（会落到插件目录内
        #     变成一个怪文件名），但在 Windows 上是；不统一拒绝的话这条守卫在 Linux 上
        #     形同虚设（用例 `test_plugins_a11_hardening:test_06` 在 CI 实测假红）。
        #   真实插件包的菜单 path 形如 `static/html/index.html`，不会被误伤（已全量扫过）。
        norm_path = path.replace('\\', '/')
        if norm_path.startswith('/') or '..' in norm_path.split('/'):
            return None
        target = os.path.join(base, path)
        if not _path_inside(base, target):
            return None
        return target

    def addIndex(self, name, version):
        # 安全：display_index 是持久化的首页软件清单，非法名/版本会被永久写入并挤占 12 个展示位
        name = str(name or '').strip()
        version = str(version or '').strip()
        if not _valid_plugin_name(name) or (version and not _valid_plugin_version(version)):
            return yf.returnData(False, 'ARGS_ERR')

        vname = name + '-' + version
        indexList = thisdb.getOptionByJson('display_index',default=[])

        if vname in indexList:
            return yf.returnData(False, 'plugin.py_msg_72dee7')
        if len(indexList) > 12:
            return yf.returnData(False, 'plugin.py_msg_78cf3e')

        indexList.append(vname)

        thisdb.setOption('display_index', json.dumps(indexList))
        return yf.returnData(True, 'common.add_success')

    def removeIndex(self, name, version):
        name = str(name or '').strip()
        version = str(version or '').strip()
        if not _valid_plugin_name(name) or (version and not _valid_plugin_version(version)):
            return yf.returnData(False, 'ARGS_ERR')

        vname = name + '-' + version
        indexList = thisdb.getOptionByJson('display_index', default=[])
        if not vname in indexList:
            return yf.returnData(True, 'plugin.py_msg_fc8c87')
        indexList.remove(vname)
        thisdb.setOption('display_index', json.dumps(indexList))
        return yf.returnData(True, 'common.del_success')

    def sortIndex(self, ssort):
        if not ssort:
            return yf.returnData(False, 'common.param_error')
        sort_list = [x.strip() for x in ssort.split('|') if x.strip()]
        if not sort_list:
            return yf.returnData(False, 'common.param_error')

        old_list = thisdb.getOptionByJson('display_index', default=[])
        new_list = []
        for item in sort_list:
            # 只收「插件名-版本」形态的条目，挡住把任意垃圾串永久写进首页清单
            if not _PLUGIN_INDEX_ITEM_RE.match(item):
                continue
            if item not in new_list:
                new_list.append(item)
        for item in old_list:
            if item not in new_list:
                new_list.append(item)

        thisdb.setOption('display_index', json.dumps(new_list))
        return yf.returnData(True, 'common.set_success')

    def hookInstallOption(self, hook_name, info):
        hn_name = 'hook_'+hook_name
        ok, info = _sanitize_hook_item(info)
        if not ok:
            yf.writeFileLog('[plugin] 丢弃非法 %s 钩子条目: %r' % (hn_name, info))
            return False

        src_data = thisdb.getOptionByJson(hn_name,type='hook',default=[])
        if not isinstance(src_data, list):
            src_data = []
        isNeedAdd = True
        for item in src_data:
            # 历史库里可能残留缺字段的条目，取值必须是容错的
            if not isinstance(item, dict):
                continue
            if item.get('title') == info['title'] and item.get('name') == info['name']:
                isNeedAdd = False

        if isNeedAdd:
            src_data.append(info)

        thisdb.setOption(hn_name, json.dumps(src_data), type='hook')
        return True

    def hookUninstallOption(self, hook_name, info):
        hn_name = 'hook_'+hook_name
        src_data = thisdb.getOptionByJson(hn_name,type='hook',default=[])
        for idx in range(len(src_data)):
            if isinstance(src_data[idx], dict) and src_data[idx].get('name') == info.get('name'):
                src_data.remove(src_data[idx])
                break
        thisdb.setOption(hn_name, json.dumps(src_data), type='hook')
        return True

    def hookInstall(self, info):
        valid_hook = ['backup', 'database']
        valid_list_hook = ['menu', 'global_static', 'site_cb']
        if 'hook' in info:
            hooks = info['hook']
            for h in hooks:
                hooks_type = type(h)
                if hooks_type == dict:
                    tag = h['tag']
                    if tag in valid_list_hook:
                        self.hookInstallOption(tag, h[tag])
                elif hooks_type == str:
                    for x in hooks:
                        if x in valid_hook:
                            self.hookInstallOption(x, info)
                            return True
        return False

    def hookUninstall(self, info):
        valid_hook = ['backup', 'database']
        valid_list_hook = ['menu', 'global_static', 'site_cb']
        if 'hook' in info:
            hooks = info['hook']
            for h in hooks:
                hooks_type = type(h)
                if hooks_type == dict:
                    tag = h['tag']
                    if tag in valid_list_hook:
                        self.hookUninstallOption(tag, h[tag])
                elif hooks_type == str:
                    for x in hooks:
                        if x in valid_hook:
                            self.hookUninstallOption(x, info)
                            return True
        return False

    def install(self, name, version,
        upgrade = None,
        confirm_token = ''
    ):
        # 安全：name/version 会拼成插件目录路径与子进程命令（install.sh 以 root 执行），
        # 必须与 /plugins/run 同级做白名单校验，否则 name='../../../../tmp/x' 可执行面板外的任意脚本。
        name = str(name or '').strip()
        version = str(version or '').strip()
        if name == '':
            return yf.returnData(False, 'plugin.py_msg_5e6038', ())

        if version == '':
            return yf.returnData(False, 'plugin.py_msg_988b58', ())

        if not _valid_plugin_name(name) or not _valid_plugin_version(version):
            yf.writeFileLog('[plugin] 拒绝安装非法插件参数: name=%r version=%r' % (name, version))
            return yf.returnData(False, 'ARGS_ERR', ())

        # PHP 只提供 PHP_MIN_INSTALL_BRANCH 及以上（用户 2026-10-26 定的口径）：
        # 低版本官方已停止维护、不再有安全修复，商店里也不展示安装入口。
        # 这里再拦一道，是因为「前端看不到按钮」不等于「接口调不到」。
        if _php_family(name):
            branch = _php_branch_of(version)
            if branch and branch < _php_branch_of(PHP_MIN_INSTALL_BRANCH):
                yf.writeFileLog('[plugin] 拒绝安装已停维的 PHP 分支: name=%s version=%s'
                                % (name, version))
                return yf.returnData(False, 'plugin.php_eol_branch_install', ())

        msg_head = '安装'
        if upgrade is not None and upgrade is True:
            mtype = 'update'
            msg_head = '更新'

        info_file = self.__plugin_dir + '/' + name + '/' + 'info.json'
        if not os.path.exists(info_file):
            return yf.returnData(False, 'plugin.py_msg_dacbd7', ())

        info_data = json.loads(yf.readFile(info_file))

        # 第三方插件包「安装前确认」：必须携带与包内容绑定的有效凭据。
        # 官方插件（未登记为第三方）不走此门，既有安装成功率不变。
        if _plugin_is_third_party(name):
            plugin_dir = os.path.abspath(self.__plugin_dir + '/' + name)
            ok, reason = _verify_plugin_confirm_token(name, plugin_dir, confirm_token)
            if not ok:
                yf.writeFileLog('[plugin] 拒绝未确认的第三方插件安装: name=%s version=%s (%s)'
                                % (name, version, reason))
                return yf.returnData(False, 'plugin.py_msg_6f3a2d')

        exec_bash = 'cd {0} && bash {1} install {2}'.format(
            yf.shlexQuote(yf.getPluginDir() + '/'+name),
            yf.shlexQuote(info_data['shell']),
            yf.shlexQuote(version)
        )

        self.hookInstall(info_data)
        title = '{0}[{1}-{2}]'.format(msg_head,name,version)
        thisdb.addTask(name=title,cmd=exec_bash, status=0)
        yf.triggerTask()
        # 调式日志
        yf.debugLog(exec_bash)
        return yf.returnData(True, 'plugin.py_msg_c3ed11')

    # 卸载插件
    def uninstall(self, name, version, force=False, backup=False):
        # 安全：同 install，name/version 进路径与 shell（uninstall.sh 以 root 执行）。
        name = str(name or '').strip()
        version = str(version or '').strip()
        if name == '':
            return yf.returnData(False, 'plugin.py_msg_5e6038', ())

        if not _valid_plugin_name(name) or (version and not _valid_plugin_version(version)):
            yf.writeFileLog('[plugin] 拒绝卸载非法插件参数: name=%r version=%r' % (name, version))
            return yf.returnData(False, 'ARGS_ERR', ())

        # 解析真实安装目录以支持备份功能
        real_install_path = None
        plugin_path = self.__plugin_dir + '/' + name
        info_file = plugin_path + '/info.json'
        if os.path.exists(info_file):
            try:
                info_data = json.loads(yf.readFile(info_file))
                install_path = info_data.get('path', '')
                if install_path:
                    # 兼容带有 VERSION 的路径占位符
                    if install_path.find('VERSION') > -1:
                        target_ver = version.strip()
                        if not target_ver and 'versions' in info_data:
                            if isinstance(info_data['versions'], list) and len(info_data['versions']) > 0:
                                target_ver = info_data['versions'][0]
                            elif isinstance(info_data['versions'], str):
                                target_ver = info_data['versions']
                        if target_ver:
                            install_path = install_path.replace('VERSION', target_ver)
                    
                    if not install_path.startswith('/'):
                        install_path = yf.getFatherDir() + '/' + install_path
                    
                    real_install_path = os.path.abspath(install_path)
            except Exception as e:
                yf.writeFileLog('[plugin] 解析插件安装路径失败: %s' % e)

        server_base_dir = os.path.abspath(yf.getServerDir()) # 即 /www/server

        # 安全屏障：必须是 /www/server 内部的子级目录，且不能等于 /www/server 自身或根级敏感父节点
        if real_install_path and real_install_path.startswith(server_base_dir) and real_install_path != server_base_dir:
            if os.path.exists(real_install_path):
                # 统一执行卸载前打包备份
                if backup:
                    try:
                        import time
                        backup_dir = yf.getBackupDir()
                        if not os.path.exists(backup_dir):
                            os.makedirs(backup_dir)
                        timestamp = time.strftime('%Y%m%d_%H%M%S')
                        backup_file = "{0}/plugin_backup_{1}_{2}.tar.gz".format(backup_dir, name, timestamp)
                        parent_dir = os.path.dirname(real_install_path)
                        base_name = os.path.basename(real_install_path)
                        tar_cmd = "tar -czf {0} -C {1} {2}".format(backup_file, parent_dir, base_name)
                        yf.execShell(tar_cmd, timeout=yf.EXEC_ARCHIVE_TIMEOUT)
                    except Exception as bex:
                        yf.writeFileLog("卸载前打包备份失败: " + yf.getTracebackInfo())

        # 强制卸载（直接物理删除并清理首页图标配置）
        if force:
            if real_install_path and real_install_path.startswith(server_base_dir) and real_install_path != server_base_dir:
                if os.path.exists(real_install_path):
                    import shutil
                    try:
                        if os.path.isdir(real_install_path):
                            shutil.rmtree(real_install_path)
                        else:
                            os.remove(real_install_path)
                    except Exception as e:
                        yf.removeDir(real_install_path)

            # 从首页展示配置中移除
            try:
                indexList = thisdb.getOptionByJson('display_index', default=[])
                newIndexList = []
                for i in indexList:
                    t = i.split('-')
                    plugin_name = t[0]
                    if len(t) > 2:
                        tArr = t[0:len(t) - 1]
                        plugin_name = '-'.join(tArr)
                    if plugin_name != name:
                        newIndexList.append(i)
                thisdb.setOption('display_index', json.dumps(newIndexList))
            except Exception as e:
                yf.writeFileLog('[plugin] 保存插件显示顺序失败: %s' % e)

            self.__plugin_list_static_cache = None
            return yf.returnData(True, 'plugin.py_msg_c956b1')

        if version == '':
            return yf.returnData(False, 'plugin.py_msg_988b58', ())

        info_file = self.__plugin_dir + '/' + name + '/' + 'info.json'
        if not os.path.exists(info_file):
            return yf.returnData(False, 'plugin.py_msg_dacbd7', ())

        info_data = json.loads(yf.readFile(info_file))

        exec_bash = "cd {0} && /bin/bash {1} uninstall {2}".format(
            yf.shlexQuote(yf.getPluginDir() + '/'+name),
            yf.shlexQuote(info_data['shell']),
            yf.shlexQuote(version)
        )
        # 卸载脚本可能很慢（清理数据/停服务），但仍需有上界，避免永久占死 gunicorn 线程
        rc, out, err = yf.execShellRc(exec_bash, timeout=1800)
        yf.debugLog(exec_bash, (out, err))
        # 失败必须如实上报：原先无论脚本退出码如何都回「卸载执行成功!」，
        # 且钩子/首页图标已被摘除 → 用户以为卸干净了，实际软件还在。
        if rc != 0:
            yf.writeFileLog('[plugin] 卸载脚本失败 name=%s rc=%s err=%s' % (name, rc, (err or out or '').strip()[:500]))
            return yf.returnData(False, 'ERROR')

        self.hookUninstall(info_data)
        self.removeIndex(name, version)
        self.__plugin_list_static_cache = None
        return yf.returnData(True, 'plugin.py_msg_dcd822')

    # 插件搜索匹配
    def searchKey(self, info,
        keyword = None,
    ):
        if keyword == None:
            return True
        try:
            if info['title'].lower().find(keyword) > -1:
                return True
            if info['ps'].lower().find(keyword) > -1:
                return True
            if info['name'].lower().find(keyword) > -1:
                return True
        except Exception as e:
            return False

    def getVersion(self, path):
        version_pl = path + '/version.pl'
        if os.path.exists(version_pl):
            v = yf.readFile(version_pl).strip()
            if v:
                return v

        # 自愈探测机制：如果 version.pl 缺失，尝试根据对应软件二进制探测并自动写回
        try:
            # 1. 探测 Redis
            redis_bin = path + '/bin/redis-server'
            if os.path.exists(redis_bin):
                data = yf.execShell(f"{redis_bin} -v")
                out = data[0] if data and len(data) > 0 else ''
                m = re.search(r'v=([0-9]+\.[0-9]+(?:\.[0-9]+)?)', out)
                if m:
                    ver = m.group(1).strip()
                    yf.writeFile(version_pl, ver)
                    return ver

            # 2. 探测 MySQL / MariaDB
            mysql_bin = path + '/bin/mysql'
            if os.path.exists(mysql_bin):
                data = yf.execShell(f"{mysql_bin} -V")
                out = data[0] if data and len(data) > 0 else ''
                m = re.search(r'Distrib\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)', out)
                if m:
                    ver = m.group(1).strip()
                    yf.writeFile(version_pl, ver)
                    return ver
        except Exception as e:
            yf.writeFileLog('[plugin] 写入插件版本文件失败: %s' % e)

        return ''

    def checkIndexList(self, name, version):
        indexList = thisdb.getOptionByJson('display_index',default=[])
        for i in indexList:
            t = i.split('-')
            tlen = len(t)
            if tlen < 2:
                continue
            plugin_name = t[0]
            plugin_ver = t[1]
            if tlen > 2:
                tArr = t[0:tlen - 1]
                plugin_name = '-'.join(tArr)
                plugin_ver = t[tlen - 1]
            if plugin_name == name:
                return True
        return False

    def checkSetupTask(self, name, version, coexist):
        self.__tasks = thisdb.getTaskRunAll()
        isTask = '1'
        for task in self.__tasks:
            tmpt = yf.getStrBetween('[', ']', task['name'])
            if not tmpt:
                continue

            if not tmpt.startswith(name + '-'):
                continue
            
            remainder = tmpt[len(name)+1:]
            valid_versions = version if isinstance(version, list) else [version]
            matched = False
            for v in valid_versions:
                if remainder == v or remainder.startswith(v + '-'):
                    matched = True
                    break
            
            if matched:
                isTask = task['status']
                break

        return isTask

    def checkDisplayIndex(self, name, version, coexist):
        indexList = thisdb.getOptionByJson('display_index',default=[])
        if coexist:
            if type(version) == list:
                for index in range(len(version)):
                    vname = name + '-' + version[index]
                    if vname in indexList:
                        return True
            else:
                vname = name + '-' + version
                if vname in indexList:
                    return True
        else:
            if type(version) == list:
                for index in range(len(version)):
                    return self.checkIndexList(name, version)
            else:
                return self.checkIndexList(name, version)
        return False

    def makeCoexist(self, data):
        plugins_info = []
        for index in range(len(data['versions'])):
            data_t = data.copy()
            data_t['title'] = data_t['title'] + '-' + data['versions'][index]
            data_t['versions'] = data['versions'][index]
            pg = self.makePluginInfo(data_t)
            plugins_info.append(pg)

        return plugins_info

    # 构造插件基本信息
    def makePluginInfo(self, info):
        checks = ''
        path = ''
        coexist = False

        # 第三方插件包的 info.json 由上传者提供，可能缺 checks；
        # 直接用 info['checks'] 抛 KeyError 会让 /plugins/list 永久 500（整个软件页打不开）。
        checks_src = str(info.get('checks') or '')
        if checks_src.startswith('/'):
            checks = checks_src
        elif checks_src:
            checks = yf.getFatherDir() + '/' + checks_src

        if 'path' in info:
            path = info['path']

        if not path.startswith('/'):
            path = yf.getFatherDir() + '/' + path

        if 'coexist' in info and info['coexist']:
            coexist = True

        pInfo = {
            "id": 10000,
            "sort": 10000,
            "pid": info.get('pid', '0'),
            "type": 1000,
            "name": info.get('name', ''),
            "title": info.get('title', ''),
            "ps": info.get('ps', ''),
            "dependnet": "",
            "mutex": "",
            "icon": "",
            "path": path,
            "install_checks": checks,
            "uninsatll_checks": checks,
            "coexist": coexist,
            "versions": info.get('versions', ''),
            # "updates": info['updates'],
            "task": True,
            "display": False,
            "setup": False,
            "setup_version": "",
            "status": False,
            "install_pre_inspection": False,
            "uninstall_pre_inspection": False,
            "home": info.get('home', ''),
            "date": info.get('date', ''),
            "display_status": info.get('display_status', True),
        }

        if 'icon' in info:
            pInfo['icon'] = info['icon']

        if 'sort' in info:
            pInfo['sort'] = info['sort']

        versions = pInfo['versions']

        if checks.find('VERSION') > -1:
            pInfo['install_checks'] = checks.replace('VERSION', str(versions))

        if path.find('VERSION') > -1:
            pInfo['path'] = path.replace('VERSION', str(versions))

        pInfo['task'] = self.checkSetupTask(pInfo['name'], versions, coexist)
        pInfo['display'] = self.checkDisplayIndex(info['name'], pInfo['versions'], coexist)
        pInfo['setup'] = os.path.exists(pInfo['install_checks'])

        if coexist and pInfo['setup']:
            pInfo['setup_version'] = versions
        elif pInfo['setup']:
            if os.path.isdir(pInfo['install_checks']):
                pInfo['setup_version'] = self.getVersion(pInfo['install_checks'])
            else:
                pInfo['setup_version'] = yf.readFile(pInfo['install_checks']).strip()

        if 'install_pre_inspection' in info:
            pInfo['install_pre_inspection'] = info['install_pre_inspection']
        if 'uninstall_pre_inspection' in info:
            pInfo['uninstall_pre_inspection'] = info['uninstall_pre_inspection']

        pInfo['display_level'] = info.get('display', 1)

        return pInfo

    def makeCoexistData(self, data):
        plugins = []
        if type(data['versions']) == list and 'coexist' in data and data['coexist']:
            data_t = self.makeCoexist(data)
            for index in range(len(data_t)):
                plugins.append(data_t[index])
        else:
            pg = self.makePluginInfo(data)
            plugins.append(pg)
        return plugins

    def makeCoexistDataInstalled(self, data):
        plugins = []
        if type(data['versions']) == list and 'coexist' in data and data['coexist']:
            data_t = self.makeCoexist(data)
            for index in range(len(data_t)):
                if data_t[index]['setup']:
                    plugins.append(data_t[index])
        else:
            pg = self.makePluginInfo(data)
            if pg['setup']:
                plugins.append(pg)
        return plugins

    # 对多版本共存进行处理
    def makeCoexistList(self, data,
        plugin_type = None,
    ):
        plugins_t = []
        # 返回指定类型
        if plugin_type != None and data.get('pid') == plugin_type:
            return self.makeCoexistData(data)

        # 全部
        if plugin_type == None or plugin_type == '0':
            return self.makeCoexistData(data)
        # 已经安装
        if str(plugin_type) == '-1':
            return self.makeCoexistDataInstalled(data)
        return plugins_t

    def getPluginInfo(self, name):
        info = {}
        path = self.__plugin_dir + '/' + name
        info_path = path + '/info.json'
        if not os.path.exists(info_path):
            return info
        try:
            data = json.loads(yf.readFile(info_path))
            return data
        except Exception as e:
            return info

    def getStaticPluginList(self):
        if self.__plugin_list_static_cache is not None:
            return self.__plugin_list_static_cache
        
        static_list = []
        for name in os.listdir(self.__plugin_dir):
            if name.startswith('.') or name == '待审核':
                continue
            data = self.getPluginInfo(name)
            if not data or 'versions' not in data:
                continue
            
            plugin_t = self.makeCoexistList(data, plugin_type='0')
            for index in range(len(plugin_t)):
                static_list.append(plugin_t[index])
        
        self.__plugin_list_static_cache = static_list
        return self.__plugin_list_static_cache

    def clearCache(self, purge_source=True):
        self.__plugin_list_static_cache = None

        # 清除下载的安装包缓存 /www/server/source(实测 554MB,含 mysql/php/openresty 等
        # 安装包)。只为「刷新插件列表」而整目录清空,意味着点一次按钮就要重新下载几百 MB。
        # 真正的清理入口是设置页的「清理缓存」,它传 purge_source=True。
        if purge_source:
            source_dir = yf.getServerDir() + '/source'
            if os.path.exists(source_dir):
                for _name in os.listdir(source_dir):
                    yf.removeDir(os.path.join(source_dir, _name))

        return True

    def refreshDynamicStatus(self, plist):
        self.__tasks = thisdb.getTaskRunAll()
        indexList = thisdb.getOptionByJson('display_index', default=[])
        
        for pInfo in plist:
            name = pInfo['name']
            version = pInfo['versions']
            coexist = pInfo['coexist']
            install_checks = pInfo['install_checks']
            
            pInfo['setup'] = os.path.exists(install_checks)
            
            if coexist and pInfo['setup']:
                pInfo['setup_version'] = version
            elif pInfo['setup']:
                if os.path.isdir(install_checks):
                    pInfo['setup_version'] = self.getVersion(install_checks)
                else:
                    pInfo['setup_version'] = yf.readFile(install_checks).strip()
            else:
                pInfo['setup_version'] = ""
                
            display = False
            if coexist:
                if type(version) == list:
                    for idx in range(len(version)):
                        vname = name + '-' + version[idx]
                        if vname in indexList:
                            display = True
                            break
                else:
                    vname = name + '-' + version
                    if vname in indexList:
                        display = True
            else:
                for i in indexList:
                    t = i.split('-')
                    tlen = len(t)
                    plugin_name = t[0]
                    if tlen > 2:
                        tArr = t[0:tlen - 1]
                        plugin_name = '-'.join(tArr)
                    if plugin_name == name:
                        display = True
                        break
            pInfo['display'] = display
            
            isTask = '1'
            for task in self.__tasks:
                tmpt = yf.getStrBetween('[', ']', task['name'])
                if not tmpt:
                    continue

                if not tmpt.startswith(name + '-'):
                    continue
                
                remainder = tmpt[len(name)+1:]
                valid_versions = version if isinstance(version, list) else [version]
                matched = False
                for v in valid_versions:
                    if remainder == v or remainder.startswith(v + '-'):
                        matched = True
                        break
                
                if matched:
                    isTask = task['status']
                    break
            
            pInfo['task'] = isTask
            
        return plist


    def getPluginList(self, name,
        keyword = None,
        type = None,
    ):
        infos = []
        data = self.getPluginInfo(name)
        if data is None or len(data) == 0:
            return infos
        
        # 判断是否搜索
        if keyword != '' and not self.searchKey(data, keyword):
            return infos

        plugin_t = self.makeCoexistList(data, type)
        for index in range(len(plugin_t)):
            infos.append(plugin_t[index])
        return infos

    # 检查插件状态
    # 轻量级核心服务状态快速探测，优先读取PID文件与进程存活，避免无谓fork外部Python进程
    # 若无法100%确定存活，统一返回 None 由插件官方 status() 兜底判定，确保内外状态绝对一致
    def checkStatusQuick(self, name, version=''):
        server_dir = yf.getServerDir()

        # 1. OpenResty / Nginx 快速探测
        if name in ('openresty', 'openresty-status'):
            pid_file = os.path.join(server_dir, 'openresty/nginx/logs/nginx.pid')
            if not os.path.exists(pid_file):
                pid_file = os.path.join(server_dir, 'openresty/logs/nginx.pid')
            if os.path.exists(pid_file):
                try:
                    pid = yf.readFile(pid_file).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 openresty PID 失败: %s', _e)
            return None

        # 2. MySQL / MariaDB 快速探测
        if name in ('mysql', 'mariadb'):
            pid_file = os.path.join(server_dir, f"{name}/data/{name}.pid")
            if not os.path.exists(pid_file):
                import socket
                hostname = socket.gethostname()
                pid_file = os.path.join(server_dir, f"{name}/data/{hostname}.pid")
            if os.path.exists(pid_file):
                try:
                    pid = yf.readFile(pid_file).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 MySQL/MariaDB PID 失败: %s', _e)
            return None

        # 3. Redis 快速探测
        if name == 'redis':
            pid_file = os.path.join(server_dir, 'redis/data/redis.pid')
            if os.path.exists(pid_file):
                try:
                    pid = yf.readFile(pid_file).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 Redis PID 失败: %s', _e)
            return None

        # 4. Pure-FTPd 快速探测
        if name == 'pureftp':
            pid_file = os.path.join(server_dir, 'pureftp/pure-ftpd.pid')
            if os.path.exists(pid_file):
                try:
                    pid = yf.readFile(pid_file).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 Pure-FTPd PID 失败: %s', _e)
            return None

        # 5. PHP (多版本共存) 快速探测
        if name == 'php-apt':
            ver_str = str(version).strip()
            if ver_str:
                ver_dot = ver_str if '.' in ver_str else (ver_str[0] + '.' + ver_str[1:] if len(ver_str) >= 2 else ver_str)
                for pid_candidate in (f"/run/php/php{ver_dot}-fpm.pid", f"/run/php/php{ver_str}-fpm.pid"):
                    if os.path.exists(pid_candidate):
                        try:
                            pid = yf.readFile(pid_candidate).strip()
                            if pid and yf.checkPid(int(pid)):
                                return True
                        except Exception as _e:
                            _log.debug('[plugin] 读取 PHP-FPM(sury) PID 失败: %s', _e)
            return None
        elif name.startswith('php') or (name == 'php' and version):
            ver_clean = str(version).replace('.', '')
            pid_file = os.path.join(server_dir, f"php/{ver_clean}/var/run/php-fpm.pid")
            if os.path.exists(pid_file):
                try:
                    pid = yf.readFile(pid_file).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 PHP-FPM PID 失败: %s', _e)
            return None

        # 6. Docker 快速探测
        if name == 'docker':
            docker_pid = '/var/run/docker.pid'
            if os.path.exists(docker_pid):
                try:
                    pid = yf.readFile(docker_pid).strip()
                    if pid and yf.checkPid(int(pid)):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 读取 Docker PID 失败: %s', _e)
            sock_file = '/var/run/docker.sock'
            if os.path.exists(sock_file):
                import stat
                try:
                    mode = os.stat(sock_file).st_mode
                    if stat.S_ISSOCK(mode):
                        return True
                except Exception as _e:
                    _log.debug('[plugin] 检测 docker.sock 失败: %s', _e)
            return None

        # 7. OP_WAF 防火墙快速探测
        if name == 'op_waf':
            waf_conf = os.path.join(server_dir, 'web_conf/nginx/vhost/opwaf.conf')
            nginx_conf = os.path.join(server_dir, 'openresty/nginx/conf/nginx.conf')
            if not os.path.exists(waf_conf) or not os.path.exists(nginx_conf):
                return False
            op_status = self.checkStatusQuick('openresty')
            if op_status is True:
                return True
            elif op_status is False:
                return False
            return None

        # 8. Fail2ban 防火墙快速探测
        if name == 'fail2ban':
            for pid_file in ('/run/fail2ban/fail2ban.pid', '/var/run/fail2ban/fail2ban.pid'):
                if os.path.exists(pid_file):
                    try:
                        pid = yf.readFile(pid_file).strip()
                        if pid and yf.checkPid(int(pid)):
                            return True
                    except Exception as _e:
                        _log.debug('[plugin] 读取 fail2ban PID 失败: %s', _e)
            sock_file = '/run/fail2ban/fail2ban.sock'
            if not os.path.exists(sock_file):
                return False
            return None

        # 9. Swap 虚拟内存快速探测
        if name == 'swap':
            sfile = os.path.join(server_dir, 'swap', 'swapfile')
            if not os.path.exists(sfile):
                return False
            if os.path.exists('/proc/swaps'):
                try:
                    sfile_posix = sfile.replace('\\', '/')
                    with open('/proc/swaps', 'r') as f:
                        content = f.read().replace('\\', '/')
                        if sfile_posix in content or sfile in content or '/swap/swapfile' in content:
                            return True
                        return False
                except Exception as _e:
                    _log.debug('[plugin] 解析 /proc/swaps 失败: %s', _e)
            return None

        return None

    # 检查插件真实状态（优先轻量探测，兜底调用插件status）
    def checkStatusReal(self, info):
        if not info.get('setup', False) or not info.get('display_status', True):
            return False

        name = info.get('name', '')
        setup_ver = info.get('setup_version', '')
        quick_res = self.checkStatusQuick(name, setup_ver)
        if quick_res is not None:
            return quick_res

        try:
            data = self.run(name, 'status', setup_ver)
            return data[0].strip() == 'start'
        except Exception:
            return False

    # 检查插件状态（兼容旧接口）
    def checkStatusThreads(self, info, i=0):
        return self.checkStatusReal(info)

    # 检查插件状态（优先从指定缓存读取）
    def checkStatusThreadsByCache(self, info, i=0):
        if not info.get('setup', False) or not info.get('display_status', True):
            return False

        plugin_list_status = self.__plugin_status_data
        if plugin_list_status is not None:
            k = info['name']
            if 'coexist' in info and info['coexist']:
                k = info.get('title', info['name'])
            if k in plugin_list_status:
                return bool(plugin_list_status[k])

        return self.checkStatusReal(info)

    # 多线程检查插件状态[cache] —— 缓存优先 + 后台异步受控并发刷新策略
    def checkStatusMThreadsByCache(self, info):
        try:
            cached_data = thisdb.getOptionByJson(self.__plugin_status_cachekey, default=None)
            if cached_data is None or type(cached_data) != dict:
                cached_data = {}

            self.__plugin_status_data = cached_data

            # 判断缓存是否完整可用（过滤无需探测状态的插件后，已安装的插件在缓存中均有对应条目）
            has_full_cache = True
            for item in info:
                # 未安装 或 明确配置不需要展示状态指示灯的插件（如纯工具/环境类），不纳入探针队列
                if not item.get('setup', False) or not item.get('display_status', True):
                    continue
                k = item['name']
                if 'coexist' in item and item['coexist']:
                    k = item.get('title', item['name'])
                if k not in cached_data:
                    has_full_cache = False
                    break

            from concurrent.futures import ThreadPoolExecutor

            if has_full_cache:
                # 缓存完整：直接使用缓存值返回（0ms零阻塞）
                for i in range(len(info)):
                    if not info[i].get('setup', False) or not info[i].get('display_status', True):
                        info[i]['status'] = False
                        continue
                    k = info[i]['name']
                    if 'coexist' in info[i] and info[i]['coexist']:
                        k = info[i].get('title', info[i]['name'])
                    info[i]['status'] = cached_data.get(k, False)

                # 启动后台受控并发线程异步增量刷新（最大并发为4，使用checkStatusReal穿透旧缓存刷新）
                import copy
                info_copy = copy.deepcopy(info)
                def _async_refresh():
                    try:
                        fresh_data = {}
                        installed_items = [item for item in info_copy if item.get('setup', False) and item.get('display_status', True)]
                        if installed_items:
                            with ThreadPoolExecutor(max_workers=4) as executor:
                                results = list(executor.map(self.checkStatusReal, installed_items))
                                for item, status_val in zip(installed_items, results):
                                    k = item['name']
                                    if 'coexist' in item and item['coexist']:
                                        k = item.get('title', item['name'])
                                    fresh_data[k] = status_val
                        
                        # 增量合并更新缓存，严禁暴力覆盖，杜绝多分类/分页切换时缓存被踩踏抹除
                        curr_data = thisdb.getOptionByJson(self.__plugin_status_cachekey, default={})
                        if not isinstance(curr_data, dict):
                            curr_data = {}
                        curr_data.update(fresh_data)
                        thisdb.setOption(self.__plugin_status_cachekey, json.dumps(curr_data))
                        self.__plugin_status_data = curr_data
                    except Exception as e:
                        yf.writeFileLog('async refresh plugin status error: ' + str(e))

                refresh_thread = threading.Thread(target=_async_refresh)
                refresh_thread.daemon = True
                refresh_thread.start()
            else:
                # 冷启动：受控最大 4 并发线程获取真实状态，杜绝单核机器瞬时高负载
                installed_items = [item for item in info if item.get('setup', False) and item.get('display_status', True)]
                status_map = {}
                if installed_items:
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        results = list(executor.map(self.checkStatusReal, installed_items))
                        for item, status_val in zip(installed_items, results):
                            k = item['name']
                            if 'coexist' in item and item['coexist']:
                                k = item.get('title', item['name'])
                            status_map[k] = status_val

                for i in range(len(info)):
                    if not info[i].get('setup', False) or not info[i].get('display_status', True):
                        info[i]['status'] = False
                        continue
                    k = info[i]['name']
                    if 'coexist' in info[i] and info[i]['coexist']:
                        k = info[i].get('title', info[i]['name'])
                    status_val = status_map.get(k, False)
                    info[i]['status'] = status_val
                    cached_data[k] = status_val

                # 增量合并持久化
                curr_data = thisdb.getOptionByJson(self.__plugin_status_cachekey, default={})
                if not isinstance(curr_data, dict):
                    curr_data = {}
                curr_data.update(cached_data)
                self.__plugin_status_data = curr_data
                thisdb.setOption(self.__plugin_status_cachekey, json.dumps(curr_data))

        except Exception as e:
            yf.writeFileLog(yf.getTracebackInfo())
            yf.writeFileLog('checkStatusMThreadsByCache: ' + str(e))
        return info


    def autoCachePluginStatus(self):
        def _do_cache():
            try:
                info = []
                for name in os.listdir(self.__plugin_dir):
                    if name.startswith('.'):
                        continue
                    t = self.getPluginList(name)
                    for index in range(len(t)):
                        info.append(t[index])

                status_data = {}
                for x in info:
                    if not x['setup']:
                        continue
                    data = self.run(x['name'], 'status', x['setup_version'])
                    k = x['name']
                    if 'coexist' in x and x['coexist']:
                        k = x['title']
                    if data[0].strip() == 'start':
                        status_data[k] = True
                    else:
                        status_data[k] = False
                
                self.__plugin_status_data = status_data
                thisdb.setOption(self.__plugin_status_cachekey, json.dumps(self.__plugin_status_data))
            except Exception as e:
                yf.writeFileLog('autoCachePluginStatus error: ' + yf.getTracebackInfo())

        import threading
        t = threading.Thread(target=_do_cache)
        t.daemon = True
        t.start()
        return True

    # 多线程检查插件状态
    def checkStatusMThreads(self, info):
        try:
            threads = []
            ntmp_list = range(len(info))
            for i in ntmp_list:
                t = pg_thread(self.checkStatusThreads,(info[i], i))
                threads.append(t)

            for i in ntmp_list:
                threads[i].start()
            for i in ntmp_list:
                threads[i].join()

            for i in ntmp_list:
                t = threads[i].getResult()
                info[i]['status'] = t
        except Exception as e:
            yf.writeFileLog('checkStatusMThreads: ' + str(e))

        return info

    def checkAndAutoFixFail2ban(self):
        try:
            f2b_checks = yf.getFatherDir() + '/server/fail2ban'
            if not os.path.exists(f2b_checks):
                import shutil
                if shutil.which('fail2ban-client') is not None or os.path.exists('/usr/bin/fail2ban-client') or os.path.exists('/usr/sbin/fail2ban-client'):
                    os.makedirs(f2b_checks, exist_ok=True)
                    
                    f2b_version = '1.2.0'
                    import re
                    ret = yf.execShell('fail2ban-client --version')
                    if ret[0] and 'Fail2Ban v' in ret[0]:
                        match = re.search(r'Fail2Ban v([0-9\.]+)', ret[0])
                        if match:
                            f2b_version = match.group(1)
                    
                    yf.writeFile(f2b_checks + '/version.pl', f2b_version)
                    
                    rootPath = yf.getPanelDir()
                    yf.execShell('python3 ' + shlex.quote(rootPath + '/plugins/fail2ban/index.py') + ' start')
                    yf.execShell('python3 ' + shlex.quote(rootPath + '/plugins/fail2ban/index.py') + ' initd_install')
                    
                    self.__plugin_list_static_cache = None
        except Exception as e:
            yf.writeFileLog('checkAndAutoFixFail2ban error: ' + str(e))

    def getAllPluginList(
        self,
        type = None,
        keyword = None,
        page = 1, 
        size = 10, 
        show_third_party = 0,
    ):
        self.checkAndAutoFixFail2ban()
        static_list = self.getStaticPluginList()
        
        import copy
        plist = copy.deepcopy(static_list)
        
        plist = self.refreshSetupStatus(plist)
        plist = self.applyPhpVersionPolicy(plist)
        
        filtered_list = []
        for p in plist:
            disp = p.get('display_level', 1)
            if disp == 0:
                continue
            if disp == 1 and str(show_third_party) != '1':
                continue

            if str(type) == '-1':
                if p['setup']:
                    filtered_list.append(p)
            elif type == None or type == '0' or str(p.get('pid')) == str(type):
                filtered_list.append(p)
                
        if keyword:
            searched_list = []
            for p in filtered_list:
                if self.searchKey(p, keyword):
                    searched_list.append(p)
            filtered_list = searched_list
            
        filtered_list = sorted(filtered_list, key=lambda f: int(f['sort']), reverse=False)
        
        start = (page - 1) * size
        end = start + size
        page_items = filtered_list[start:end]
        
        page_items = self.refreshDynamicStatus(page_items)
        
        page_items = self.checkStatusMThreadsByCache(page_items)
        return (page_items, len(filtered_list))

    def localizePluginItems(self, items):
        try:
            from core.i18n import get_current_lang
            lang = get_current_lang()
        except Exception:
            lang = 'zh-CN'
        if not lang or lang == 'zh-CN':
            return items

        if not hasattr(self, '_plugin_lang_dict_cache'):
            self._plugin_lang_dict_cache = {}

        for item in items:
            name = item.get('name')
            if not name:
                continue
            cache_key = (name, lang)
            if cache_key not in self._plugin_lang_dict_cache:
                lang_file = os.path.join(self.__plugin_dir, name, 'lang', f'{lang}.json')
                ld = {}
                if os.path.isfile(lang_file):
                    try:
                        with open(lang_file, 'r', encoding='utf-8') as f:
                            ld = json.load(f)
                    except Exception as _e:
                        _log.debug('[plugin] 读取插件语言包失败: %s -> %s', lang_file, _e)
                self._plugin_lang_dict_cache[cache_key] = ld
            else:
                ld = self._plugin_lang_dict_cache[cache_key]

            if ld:
                if 'plugin_title' in ld and ld['plugin_title']:
                    item['title'] = ld['plugin_title']
                if 'plugin_ps' in ld and ld['plugin_ps']:
                    item['ps'] = ld['plugin_ps']
        return items

    def annotatePhpUpdates(self, items):
        """给 PHP 系插件条目附上「当前版本 / 是否有新版本」信息。

        为什么在插件列表里做：用户报障的口径是「已安装的软件里看不出 PHP 该升级了」——
        `setup_version` 只有分支号（`83`），真实运行时版本（`8.3.30`）与官方最新版
        （`8.3.36`）都不在列表数据里，前端根本无从判断。

        取数口径：
          * 已装版本 ← `php_sec_scan` 的巡检快照（正常 O(1)）；
          * 官方最新版 ← `php_release_index` 的缓存（12h TTL，后台每日刷新）。
        两者任缺其一 → 不标注（不猜、不误报）。

        为什么快照缺失时要「就地巡检一次」而不是直接跳过：一键升级成功后会主动删掉
        快照（让首页告警立刻重算），若不在这里补建，软件列表在「下次每日巡检」之前
        就**完全没有升级信息**（用户刚升完一个分支，另一个分支的可更新提示凭空消失）。
        用 3s 短超时 runner，最坏只多几个毫秒级的 `php -v`。
        """
        try:
            import core.yf as yf
            from core import php_release_index, php_sec_scan
            data_dir = yf.getPanelDataDir()
            snapshot = php_sec_scan.load_or_scan(
                data_dir + '/' + php_sec_scan.SNAPSHOT_FILENAME,
                server_php_dir=yf.getServerDir() + '/php',
                run=php_sec_scan.make_runner(3))
            installed = (snapshot or {}).get('items') or []
            if not installed:
                return items
            index = php_release_index.load_cache(php_release_index.index_path(data_dir))
            if not index:
                index = php_release_index.builtin_index()
            php_release_index.annotate_items(items, installed, index)
        except Exception as e:
            # 升级提醒是附加信息：任何异常都不能让软件列表 500
            _log.debug('[plugin] 计算 PHP 升级信息失败: %s', e)
        return items

    def annotateServiceAlarms(self, items):
        """给插件条目附上「服务存活告警」（《问题报告》P2-2）。

        取数：`panel_task.py::servicePatrol_step` 每 5 分钟落盘的
        `data/service_patrol.json`。这里只**读**快照，不现场跑 systemctl ——
        软件列表是同步渲染路径，不能为它加 40 次 fork。

        任何异常都不影响列表（告警是附加信息，不是列表的前提）。
        """
        try:
            import core.yf as yf
            from core import service_patrol
            snap = service_patrol.load_snapshot(
                yf.getPanelDataDir() + '/' + service_patrol.SNAPSHOT_FILENAME)
            if not snap:
                return items
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                rec = snap.get(item.get('name'))
                if not isinstance(rec, dict) or not rec.get('alarm'):
                    continue
                item['service_alarm'] = {
                    'state': rec.get('state'),
                    'unit': rec.get('unit'),
                    'label': rec.get('label'),
                    'reason': rec.get('reason'),
                }
        except Exception as e:
            _log.debug('[plugin] 计算服务存活告警失败: %s', e)
        return items

    def getList(
        self,
        type = None,
        keyword = None,
        page = 1, 
        size  = 10, 
        show_third_party = 0,
    ) -> object:
        '''
        # print(type,keyword,page,size)
        '''
        rdata = {}
        type_list = []
        for item in self.def_plugin_type:
            item_copy = item.copy()
            if 'key' in item_copy:
                try:
                    from core.i18n import t as _t
                    item_copy['title'] = _t(item_copy['key'], item_copy['title'])
                except Exception as _e:
                    _log.debug('[plugin] 翻译插件标题失败: %s', _e)
            type_list.append(item_copy)
        rdata['type'] = type_list
    
        data = self.getAllPluginList(type, keyword, page, size, show_third_party)
        rdata['data'] = self.annotateServiceAlarms(
            self.annotatePhpUpdates(self.localizePluginItems(data[0])))
        rdata['list'] = yf.getPage({'count':data[1],'p':page,'tojs':'getSList','row':size})
        return rdata

    def updateZip(self, request_zip):
        tmp_path = yf.getPanelDir() + '/temp'
        if not os.path.exists(tmp_path):
            os.makedirs(tmp_path)
        yf.removeDir(tmp_path + '/*')

        tmp_file = tmp_path + '/plugin_tmp.zip'
        if request_zip.filename[-4:] != '.zip':
            return yf.returnData(False, 'plugin.py_msg_7ed95c')

        request_zip.save(tmp_file)
        # 安全（P2-10）：解压**之前**先按面板统一判据校验成员名 —— `../evil`、绝对路径、
        # 软链逃逸一律拒绝。校验不过 / 校验函数跑不起来（fail-closed）→ 临时 zip 与解压
        # 目录一起清掉，**一个文件都不落地**；校验通过才 unzip。
        ok, msg = _safeExtractPluginZip(tmp_file, tmp_path)
        if not ok:
            _cleanupRejectedPluginPackage(tmp_file, tmp_path, msg)
            return yf.returnData(False, msg)
        os.remove(tmp_file)

        # 安全：包内软链会被 unzip 原样还原，后续 inputZipApi 的 copytree 会「跟随软链」把包外
        # 文件（如 /etc/shadow）复制成插件目录里的普通文件并可经 /plugins/file 下载 —— 直接拒收。
        # 这一道是解压前校验之外的第二道（纵深防御），不得删除。
        if _has_symlink(tmp_path):
            yf.writeFileLog('[plugin] 拒绝含软链的插件包: %s' % getattr(request_zip, 'filename', ''))
            yf.removeDir(tmp_path)
            return yf.returnData(False, 'ERROR')

        p_info = tmp_path + '/info.json'
        if not os.path.exists(p_info):
            d_path = None
            for df in os.walk(tmp_path):
                if len(df[2]) < 3:
                    continue
                if not 'info.json' in df[2]:
                    continue
                if not 'install.sh' in df[2]:
                    continue
                if not os.path.exists(df[0] + '/info.json'):
                    continue
                d_path = df[0]
            if d_path:
                tmp_path = d_path
                p_info = tmp_path + '/info.json'
        try:
            data = json.loads(yf.readFile(p_info))
            # 安全：info.json 中的 name 完全来自上传包，必须白名单校验后才能拼路径/进临时目录
            if not isinstance(data, dict) or not _valid_plugin_name(data.get('name')):
                yf.removeDir(tmp_path)
                return yf.returnData(False, 'plugin.py_msg_311637')
            data['size'] = yf.getPathSize(tmp_path)
            if not 'author' in data:
                data['author'] = '未知'
            if not 'home' in data:
                data['home'] = 'https://github.com/clhome/bt_simple'
            plugin_path = yf.getPluginDir() + '/' + data['name'] + '/info.json'
            data['old_version'] = '0'
            data['tmp_path'] = tmp_path
            # 安装前确认：把将被 root 执行的 install.sh 文本一并回给前端展示
            script_name, script_text = _read_plugin_script(tmp_path, data)
            data['shell'] = script_name or data.get('shell', 'install.sh')
            data['install_sh'] = script_text
            if os.path.exists(plugin_path):
                try:
                    old_info = json.loads(yf.readFile(plugin_path))
                    data['old_version'] = old_info['versions']
                except Exception as _e:
                    _log.debug('[plugin] 读取插件旧版信息失败: %s', _e)
        except Exception as _e:
            yf.removeDir(tmp_path)
            return yf.returnData(False, 'plugin.py_msg_311637')
        protectPlist = ('openresty', 'mysql', 'php', 'redis', 'memcached'
                        'mongodb', 'swap', 'gogs', 'pureftp')
        if data['name'] in protectPlist:
            return yf.returnData(False, 'plugin.py_msg_7e5f20')
        return data

    def inputZipApi(self, plugin_name,tmp_path):
        # 安全收口：插件名白名单 + 临时目录必须位于面板 temp 目录内，
        # 彻底堵住 "plugin_name/tmp_path 拼进 shell" 的命令注入与目录穿越。
        if not _valid_plugin_name(plugin_name):
            return yf.returnData(False, 'plugin.py_msg_2ca3e3')

        base_tmp = yf.getPanelDir() + '/temp'
        if not os.path.exists(tmp_path) or not _path_inside(base_tmp, tmp_path) \
                or os.path.realpath(tmp_path) == os.path.realpath(base_tmp):
            return yf.returnData(False, 'plugin.py_msg_2ca3e3')

        plugin_path = os.path.abspath(yf.getPluginDir() + '/' + plugin_name)
        # 安全：copytree 默认跟随软链，会把手伸到插件包外（纵深防御，与 updateZip 同一道门）。
        # tmp_path 可能已被 updateZip 校验过，但 /plugins/input_zip 是**独立入口**，直接调用
        # 可以绕过 updateZip —— 所以这里必须自校验（判据与 safeArchiveCheck 同为「软链」）。
        ok, reject_code = _checkPluginSourceDir(tmp_path)
        if not ok:
            yf.writeFileLog('[plugin] 拒绝非法插件源目录(%s): %s' % (reject_code, tmp_path))
            return yf.returnData(False, 'ERROR')

        try:
            if not os.path.exists(plugin_path):
                yf.makeDirs(plugin_path)

            # 使用 Python 文件 API 替代 cp/chmod 字符串拼接（无 shell，无注入面）
            import shutil
            shutil.copytree(tmp_path, plugin_path, dirs_exist_ok=True)
            for root, dirs, files in os.walk(plugin_path):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o755)
                    except Exception as _e:
                        _log.debug('[plugin] 设置插件目录权限失败: %s', _e)
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o755)
                    except Exception as _e:
                        _log.debug('[plugin] 设置插件文件权限失败: %s', _e)
        except Exception as _e:
            yf.writeFileLog('[plugin.inputZipApi] %s: %s\n%s' % (plugin_name, _e, yf.getTracebackInfo()))
            yf.removeDir(plugin_path)
            return yf.returnData(False, 'plugin.py_msg_99993a')

        p_info = yf.readFile(plugin_path + '/info.json')
        if p_info:
            try:
                self.__plugin_list_static_cache = None
                p_title = json.loads(p_info).get('title', plugin_name)
                yf.writeLog('软件管理', '安装第三方插件[%s]' % p_title)
                # 登记为第三方来源，并签发与包内容绑定的确认凭据：
                # 之后 /plugins/install 必须携带该 token，包内容变化则旧 token 失效。
                _mark_plugin_third_party(plugin_name)
                script_name, script_text = _read_plugin_script(plugin_path, json.loads(p_info))
                confirm_token = ''
                if script_name:
                    confirm_token = _plugin_confirm_token(
                        plugin_name, _plugin_package_hash(plugin_path))
                return yf.returnData(True, 'plugin.py_msg_f1e512', {
                    'name': plugin_name,
                    'shell': script_name or '',
                    'install_sh': script_text,
                    'require_confirm': True,
                    'confirm_token': confirm_token,
                })
            except Exception as _e:
                yf.writeFileLog('[plugin] 安装第三方插件失败: %s' % _e)
        yf.removeDir(plugin_path)
        return yf.returnData(False, 'plugin.py_msg_99993a')

    def confirmPreview(self, name):
        """第三方插件「安装前确认」预览：返回将被 root 执行的 install.sh 与 info.json 关键字段。

        官方插件（面板自带 `plugins/` 目录）返回 require_confirm=False，前端无需额外确认，
        既有安装成功率不变。第三方插件则返回脚本文本 + 与包内容绑定的 confirm_token。
        """
        name = str(name or '').strip()
        if not _valid_plugin_name(name):
            return yf.returnData(False, 'plugin.py_msg_2ca3e3')

        if not _plugin_is_third_party(name):
            return yf.returnData(True, 'OK', {'name': name, 'require_confirm': False})

        plugin_path = os.path.abspath(self.__plugin_dir + '/' + name)
        info_file = plugin_path + '/info.json'
        if not os.path.exists(info_file):
            return yf.returnData(False, 'plugin.py_msg_dacbd7')
        try:
            info = json.loads(yf.readFile(info_file))
        except Exception as _e:
            yf.writeFileLog('[plugin] 确认预览解析 info.json 失败: %s' % _e)
            return yf.returnData(False, 'plugin.py_msg_311637')

        script_name, script_text = _read_plugin_script(plugin_path, info)
        if not script_name:
            # 无法展示/无法确认的脚本绝不签发凭据（否则「确认」是空壳）
            yf.writeFileLog('[plugin] 拒绝确认无法解析的安装脚本: %s' % name)
            return yf.returnData(False, 'plugin.py_msg_6f3a2d')

        return yf.returnData(True, 'OK', {
            'name': name,
            'title': info.get('title', name),
            'versions': info.get('versions', ''),
            'ps': info.get('ps', ''),
            'author': info.get('author', ''),
            'home': info.get('home', ''),
            'shell': script_name,
            'install_sh': script_text,
            'require_confirm': True,
            'confirm_token': _plugin_confirm_token(name, _plugin_package_hash(plugin_path)),
        })

    # [start|stop|restart|reload|restore...]操作, 精确更新与延迟校准
    def runByCache(self, name, func, version, op_result=True):
        try:
            data = thisdb.getOptionByJson(self.__plugin_status_cachekey, default={})
            if not isinstance(data, dict):
                data = {}

            # 清空内存实例缓存
            self.__plugin_status_data = None

            name_lower = str(name).lower()
            func_lower = str(func).lower()
            keys_to_update = {name, name_lower}
            info = self.getPluginInfo(name)
            if isinstance(info, dict):
                title = info.get('title')
                if title:
                    keys_to_update.add(title)
                    keys_to_update.add(str(title).lower())
                if version:
                    keys_to_update.add(f"{name}-{version}")
                    keys_to_update.add(f"{name_lower}-{version}")
                    if title:
                        keys_to_update.add(f"{title}-{version}")
                        keys_to_update.add(f"{str(title).lower()}-{version}")

            # 解析操作意图目标状态
            target_status = None
            if func_lower in ('stop', 'kill') or any(func_lower.startswith(p) for p in ('stop_', 'kill_')):
                target_status = False
            elif func_lower in ('start', 'restart', 'reload') or any(func_lower.startswith(p) for p in ('start_', 'restart_', 'reload_', 'restore_')) or 'restore' in func_lower:
                target_status = True

            if op_result and target_status is not None:
                # 操作成功：直接写入目标状态至缓存，消除守护进程退出/拉起的物理过渡期颠簸
                for k in keys_to_update:
                    data[k] = target_status
                for existing_k in list(data.keys()):
                    ek_lower = str(existing_k).lower()
                    if ek_lower == name_lower or ek_lower.startswith(f"{name_lower}-"):
                        data[existing_k] = target_status
            else:
                # 操作失败或未知状态：清理对应 key，交由真实探测
                for k in list(data.keys()):
                    k_lower = str(k).lower()
                    if k in keys_to_update or k_lower == name_lower or k_lower.startswith(f"{name_lower}-"):
                        data.pop(k, None)

            thisdb.setOption(self.__plugin_status_cachekey, json.dumps(data))
            self.__plugin_status_data = data

            # 启动后台受控延迟校验（2秒后进程完全稳定，做真实物理探针复验）
            def delay_calibrate():
                import time
                time.sleep(2.0)
                try:
                    p_info = self.getPluginInfo(name)
                    if isinstance(p_info, dict) and p_info.get('setup'):
                        real_status = self.checkStatusReal(p_info)
                        curr_data = thisdb.getOptionByJson(self.__plugin_status_cachekey, default={})
                        if isinstance(curr_data, dict):
                            for k in keys_to_update:
                                curr_data[k] = real_status
                            thisdb.setOption(self.__plugin_status_cachekey, json.dumps(curr_data))
                            self.__plugin_status_data = curr_data
                except Exception as e:
                    if yf.isDebugMode():
                        yf.writeFileLog('delay calibrate status error: ' + str(e))

            t = threading.Thread(target=delay_calibrate)
            t.daemon = True
            t.start()
        except Exception as e:
            if yf.isDebugMode():
                yf.writeFileLog(f"runByCache exception: {e}")

    # shell/bash方式调用
    def run(self, name, func,
        version = '',
        args  = '',
        script  = 'index',
    ):
        # 安全：name/script 会被拼接为子进程脚本路径，必须与 callback() 同级的白名单校验，
        # 否则可通过 name=='..' + script 跨目录执行面板内的任意 .py（路径穿越 → 任意代码执行）。
        name = str(name).strip()
        script = str(script).strip() or 'index'
        if not _valid_plugin_name(name) or not _valid_script_name(script):
            return ('', '非法的调用参数!')

        is_state_func = (
            yf.inArray(['start','stop','restart','reload','uninstall_pre_inspection','install','uninstall'], func)
            or any(func.startswith(p) for p in ('start_', 'stop_', 'restart_', 'reload_', 'restore_'))
            or 'restore' in func.lower()
            or 'reload' in func.lower()
            or 'restart' in func.lower()
        )
        try:
            if is_state_func:
                self.runByCache(name, func, version)
        except Exception as e:
            if yf.isDebugMode():
                yf.writeFileLog(f"runByCache error: {e}")

        try:
            path = self.__plugin_dir + '/' + name + '/' + script + '.py'
            if not os.path.exists(path):
                path = self.__plugin_dir + '/' + name + '/' + name + '.py'

            if not os.path.exists(path):
                return ('', f"插件脚本 {name}/{script}.py 不存在")

            cmd_list = [sys.executable, path, func]
            if version != '':
                cmd_list.append(str(version))
            if args != '':
                cmd_list.append(str(args))

            # 超时按时长分类：纯状态查询 30s，启/停/重启类放宽到 300s（数据库崩溃恢复、
            # AOF 重载等常常 >30s），其余交互式调用 600s。固定 30s 会误杀正常启停。
            is_status_query = (func == 'status' or func.startswith('status_'))
            if is_status_query:
                op_timeout = 30
            elif is_state_func:
                op_timeout = 300
            else:
                op_timeout = 600
            # 带退出码执行（shell=False，参数不经 shell）：插件崩溃但没有写 stderr 时，
            # 旧写法（safeExecShell 只看 stderr）会把「脚本失败」报成成功（假成功）。
            rc, out_raw, err_raw = yf.execShellRc(cmd_list, cwd=yf.getPanelDir(),
                                                  timeout=op_timeout, shell=False)
            data = (out_raw, err_raw)
            if yf.isDebugMode():
                yf.writeFileLog('run cmd_list: ' + str(cmd_list))
                yf.writeFileLog(str(data))
            out = data[0].strip() if data and len(data) > 0 and data[0] else ''
            err = data[1].strip() if data and len(data) > 1 and data[1] else ''

            if rc != 0:
                # 退出码非 0 = 失败。插件可能只往 stdout 写原因（真机实测
                # print('start failed') + sys.exit(1)），旧实现只看 stderr 空就报成功。
                # 这里补上失败原因，并撤掉会被上层当成成功的 'ok'。
                if not err:
                    err = out or ('plugin %s:%s exited with code %s' % (name, func, rc))
                if out == 'ok':
                    out = ''

            if is_state_func:
                try:
                    op_ok = bool(rc == 0 and (out == 'ok' or err == ''))
                    self.runByCache(name, func, version, op_result=op_ok)
                except Exception as _e:
                    _log.debug('[plugin] 回写插件状态缓存失败: %s -> %s', name, _e)

            return (out, err)
        except Exception as e:
            if yf.isDebugMode():
                yf.writeFileLog(f"plugin run execution exception: {e}")
            return ('', str(e))

    # 映射包调用（安全反射实现，彻底废除 eval）
    def callback(self, name, func,
        args = '',
        script = 'index',
    ):
        name = str(name).strip()
        func = str(func).strip()
        script = str(script).strip()

        # 安全标识符白名单校验
        if not re.match(r'^[a-zA-Z0-9_\-]+$', name) or not re.match(r'^[a-zA-Z0-9_]+$', script) or not re.match(r'^[a-zA-Z0-9_]+$', func):
            return (False, "非法的调用参数!")

        package = self.__plugin_dir + '/' + name
        if not os.path.exists(package):
            return (False, "插件不存在!")

        # 线程安全维护 sys.path
        if package not in sys.path:
            with _PLUGIN_MODULE_LOCK:
                if package not in sys.path:
                    sys.path.insert(0, package)

        script_file = os.path.join(package, f"{script}.py")
        if not os.path.exists(script_file):
            alt_file = os.path.join(package, f"{name}.py")
            if os.path.exists(alt_file):
                script_file = alt_file

        if yf.isDebugMode():
            yf.writeFileLog('callback safe reflection: ' + str(script) + ' ' + str(func) + ' ' + str(args))

        data = None
        try:
            import importlib
            # 线程安全加载或复用模块，杜绝多线程并发 del sys.modules 导致的 KeyError 竞态
            with _PLUGIN_MODULE_LOCK:
                if script in sys.modules:
                    mod = sys.modules[script]
                    if os.path.exists(script_file):
                        cur_mtime = os.path.getmtime(script_file)
                        last_mtime = _PLUGIN_MODULE_MTIME.get((name, script), 0)
                        if cur_mtime > last_mtime:
                            try:
                                mod = importlib.reload(mod)
                                _PLUGIN_MODULE_MTIME[(name, script)] = cur_mtime
                            except Exception as _e:
                                _log.debug('[plugin] 热重载插件模块失败: %s -> %s', name, _e)
                else:
                    mod = importlib.import_module(script)
                    if os.path.exists(script_file):
                        _PLUGIN_MODULE_MTIME[(name, script)] = os.path.getmtime(script_file)

            if not hasattr(mod, func):
                return (False, f"方法 {func} 不存在!")
            target_func = getattr(mod, func)

            if args:
                try:
                    parsed_args = json.loads(args)
                except Exception:
                    parsed_args = args

                if isinstance(parsed_args, dict):
                    try:
                        # 穿透装饰器解包获取底层真实函数
                        real_func = inspect.unwrap(target_func)
                        sig = inspect.signature(real_func)
                        params = list(sig.parameters.values())

                        # 过滤出显式普通位置/关键字形参（排除 *args 和 **kwargs）
                        explicit_params = [
                            p for p in params 
                            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                        ]

                        if len(params) == 0:
                            # 目标函数为无参定义 def func():
                            call_args = ()
                            call_kwargs = {}
                        elif len(explicit_params) >= 2:
                            # 目标函数明确声明了多个独立的具名形参（如 def func(a, b):）
                            try:
                                sig.bind(**parsed_args)
                                call_args = ()
                                call_kwargs = parsed_args
                            except TypeError:
                                # 关键字无法完全匹配时，降级作为单字典传给首参数
                                call_args = (parsed_args,)
                                call_kwargs = {}
                        else:
                            # 目标函数接收单参数（如 def func(args=None): 或 def func(get):），或是变长参数包装
                            # 面板插件体系核心规范：统一将前端参数字典作为单位置参数传入
                            call_args = (parsed_args,)
                            call_kwargs = {}
                    except Exception:
                        call_args = (parsed_args,)
                        call_kwargs = {}
                elif isinstance(parsed_args, (list, tuple)):
                    try:
                        sig = inspect.signature(target_func)
                        params = list(sig.parameters.values())
                        if len(params) == 1 and params[0].kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                            call_args = (parsed_args,)
                        else:
                            call_args = tuple(parsed_args)
                    except Exception:
                        call_args = tuple(parsed_args)
                    call_kwargs = {}
                else:
                    call_args = (parsed_args,)
                    call_kwargs = {}
            else:
                try:
                    sig = inspect.signature(target_func)
                    params = list(sig.parameters.values())
                    if len(params) == 0:
                        call_args = ()
                    elif len(params) >= 1 and params[0].default is inspect.Parameter.empty and params[0].kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                        # 首个位置参数无默认值，默认传递空字典以兼容单参数插件接口
                        call_args = ({},)
                    else:
                        call_args = ()
                except Exception:
                    call_args = ()
                call_kwargs = {}

            # 真正执行调用，内部抛出的业务异常直接向上冒泡，杜绝错误降级掩盖真相
            data = target_func(*call_args, **call_kwargs)
        except Exception as e:
            if yf.isDebugMode():
                yf.writeFileLog(yf.getTracebackInfo())
            err_msg = str(e)
            if isinstance(e, KeyError):
                err_msg = f"缺少参数或配置: {err_msg}"
            return (False, err_msg)        
        return (True, data)



        