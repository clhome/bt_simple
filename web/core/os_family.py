# coding: utf-8
"""发行版家族识别：决定「某个包管理渠道的插件该不该出现在软件商店里」。

## 为什么需要它

面板同时提供 `php-apt`（Debian/Ubuntu 的 sury 源）与 `php-yum`（RHEL 系的 Remi 源）
两个渠道插件。在 Debian 上装 `php-yum` 必然失败（没有 yum/remi 源），反之亦然 ——
但软件商店会把这些选项一并列出来，用户点进去只得到一堆与发行版无关的报错。

所以需要一个**可靠的发行版家族判定**，供 `web/utils/plugin.py::applyPhpChannelPolicy()`
（展示层过滤）与 `plugin.install()`（接口层拦截）共用。

## 纪律

* **纯标准库、纯函数**：不启子进程（容器里 `lsb_release` 常常没装），只读
  `/etc/os-release`（缺失时退 `/etc/issue`）；`detect(text=...)` 可直接喂样本做单测；
* **`ID_LIKE` 优先于 `ID`**：Linux Mint 是 `ID=linuxmint, ID_LIKE=ubuntu debian`，
  Kali 是 `ID=kali, ID_LIKE=debian`，AWS Linux 是 `ID=amzn, ID_LIKE="centos rhel fedora"`；
* **认不出来就是 `unknown`**，调用方**不得**据此隐藏任何东西（宁可多显示，不可误伤）；
* **刻意不猜**：不靠「`apt-get` 命令存在」判断家族（在 RHEL 上装了 epel 的兼容层时
  会误判）。只有在 `ID`/`ID_LIKE` 都判不出、且 `os-release` 明确缺失时，
  `detect()` 才回退到 `/etc/issue` 的文本特征。
"""

import logging
import os
import re

_log = logging.getLogger('yf.os_family')

#: 家族常量（与 `info.json` 里 `os_family` 的取值一一对应）。
FAMILY_DEB = 'deb'
FAMILY_RPM = 'rpm'
FAMILY_SUSE = 'suse'
FAMILY_ARCH = 'arch'
FAMILY_ALPINE = 'alpine'
FAMILY_MACOS = 'macos'
FAMILY_UNKNOWN = 'unknown'

ALL_FAMILIES = (FAMILY_DEB, FAMILY_RPM, FAMILY_SUSE, FAMILY_ARCH, FAMILY_ALPINE,
                FAMILY_MACOS, FAMILY_UNKNOWN)

#: 发行版 ID → 家族。仅用于 `ID`；`ID_LIKE` 走同一张表（两边出现的名字都收）。
_DEB_IDS = frozenset((
    'debian', 'ubuntu', 'raspbian', 'linuxmint', 'mint', 'deepin', 'kali', 'pop',
    'elementary', 'zorin', 'neon', 'devuan', 'mx', 'parrot', 'armbian', 'uos',
    'ubuntu-core', 'tuxedo', 'pureos', 'tails', 'antix', 'bodhi', 'peppermint',
))
_RPM_IDS = frozenset((
    'rhel', 'redhat', 'centos', 'centos-stream', 'rocky', 'alma', 'almalinux',
    'fedora', 'ol', 'oracle', 'alinux', 'aliyun', 'amzn', 'amazon', 'cloudlinux',
    'opencloudos', 'tencentos', 'openeuler', 'euler', 'anolis',
    'circle', 'virtuozzo', 'scientific', 'navy', 'bclinux',
))
#: **刻意不收**的歧义 ID：银河麒麟 / 统信 UOS 同时有 deb 系（桌面）与 rpm 系（服务器）
#: 产品，同一个 `ID` 两种家族。它们只靠 `ID_LIKE` 定性；`ID_LIKE` 缺失时判为
#: `unknown`（不隐藏任何插件）—— 误藏一个渠道的代价远大于多显示一行。
_SUSE_IDS = frozenset(('opensuse', 'opensuse-leap', 'opensuse-tumbleweed', 'sles',
                       'sled', 'suse', 'opensuse-microos'))
_ARCH_IDS = frozenset(('arch', 'manjaro', 'endeavouros', 'garuda', 'arcolinux',
                       'artix', 'cachyos'))
_ALPINE_IDS = frozenset(('alpine',))

#: `ID_LIKE` 里的通用别名（有的发行版写 `ID_LIKE=rhel`、有的写 `ID_LIKE="centos rhel"`）。
_LIKE_TO_FAMILY = {
    FAMILY_DEB: _DEB_IDS,
    FAMILY_RPM: _RPM_IDS,
    FAMILY_SUSE: _SUSE_IDS,
    FAMILY_ARCH: _ARCH_IDS,
    FAMILY_ALPINE: _ALPINE_IDS,
}

_DEB_RELEASE_RE = re.compile(r'\b(debian|ubuntu|raspbian|linux mint|kali|deepin|uos)\b',
                             re.I)
_RPM_RELEASE_RE = re.compile(r'\b(centos|red hat|rhel|fedora|rocky|alma|alibaba|anolis|'
                             r'opencloudos|openeuler|kylin|amazon linux)\b', re.I)
_SUSE_RELEASE_RE = re.compile(r'\b(opensuse|suse)\b', re.I)
_ALPINE_RELEASE_RE = re.compile(r'\balpine\b', re.I)


def parse_os_release(text):
    """解析 `os-release` 文本 → `{id, id_like, version_id, pretty}`（纯函数）。

    只认 `KEY=VALUE` 行，值两端的单/双引号会被剥掉；`ID_LIKE` 用空白切成列表。
    畸形行直接忽略（不能让一个坏行把整份文件判废）。
    """
    out = {'id': '', 'id_like': [], 'version_id': '', 'pretty': '', 'version': ''}
    for raw in str(text or '').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip().upper()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key == 'ID':
            out['id'] = val.strip().lower()
        elif key == 'ID_LIKE':
            out['id_like'] = [x.strip().lower() for x in val.replace(',', ' ').split()
                              if x.strip()]
        elif key in ('VERSION_ID', 'VERSION'):
            out[key.lower()] = val.strip()
        elif key == 'PRETTY_NAME':
            out['pretty'] = val.strip()
    return out


def _family_of_single(token):
    """单个 ID 词 → 家族；认不出返回空串。"""
    token = str(token or '').strip().lower()
    if not token:
        return ''
    for family, ids in _LIKE_TO_FAMILY.items():
        if token in ids:
            return family
    return ''


def family_of(os_id, id_like):
    """`(os_id, id_like[])` → 家族。**`ID_LIKE` 优先**（见模块文档）。

    `ID_LIKE` 里多个词时取**第一个认得出来的**：Debian 系派生通常写
    `ID_LIKE=ubuntu debian`（两个都是 deb），rpm 派生写 `ID_LIKE="centos rhel fedora"`
    （三个都是 rpm），所以顺序不影响结论；真有混血（如 `ID_LIKE="debian rhel"`）
    时按书写顺序取第一个 —— 那已经超出了「可靠判定」的边界，不如老实按用户写的来。
    """
    for token in (id_like or []):
        fam = _family_of_single(token)
        if fam:
            return fam
    fam = _family_of_single(os_id)
    if fam:
        return fam
    return FAMILY_UNKNOWN


def family_of_issue_text(text):
    """从 `/etc/issue` 或 `PRETTY_NAME` 的文本特征猜家族（只在没有 os-release 时用）。"""
    raw = str(text or '')
    if not raw.strip():
        return FAMILY_UNKNOWN
    # 顺序有意义：openSUSE 的 banner 里可能带 "SUSE Linux Enterprise"，
    # 而 Alpine 的 banner 只有 alpine，先判更具体的。
    if _ALPINE_RELEASE_RE.search(raw):
        return FAMILY_ALPINE
    if _SUSE_RELEASE_RE.search(raw):
        return FAMILY_SUSE
    if _DEB_RELEASE_RE.search(raw):
        return FAMILY_DEB
    if _RPM_RELEASE_RE.search(raw):
        return FAMILY_RPM
    return FAMILY_UNKNOWN


def _read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fp:
            return fp.read()
    except OSError as ex:
        _log.debug('[os_family] 读取 %s 失败: %s', path, ex)
        return ''


def detect(path='/etc/os-release', text=None):
    """识别当前系统 → `{family, id, id_like, version_id, pretty, source}`。

    :param path: os-release 路径（测试可指向样本文件）
    :param text: 直接给 os-release 文本（优先于 path，便于单测）
    """
    if text is None:
        raw = _read_text(path)
        source = path
        if not raw.strip():
            # 老系统/容器可能只有 /etc/issue
            raw = ''
            source = '/etc/issue'
            issue = _read_text('/etc/issue')
            return {
                'family': family_of_issue_text(issue),
                'id': '', 'id_like': [], 'version_id': '', 'pretty': '',
                'source': source,
            }
    else:
        raw = text
        source = 'text'

    info = parse_os_release(raw)
    family = family_of(info.get('id'), info.get('id_like'))
    if family == FAMILY_UNKNOWN:
        # os-release 在、但 ID/ID_LIKE 都不认识：再用 PRETTY_NAME 兜一层
        family = family_of_issue_text(info.get('pretty'))
    return {
        'family': family,
        'id': info.get('id') or '',
        'id_like': info.get('id_like') or [],
        'version_id': info.get('version_id') or '',
        'pretty': info.get('pretty') or '',
        'source': source,
    }


def family_supports(os_family, families):
    """当前家族是否满足插件的 `os_family` 声明。

    * `families` 为空/不是列表 ⇒ **全平台**（老插件、第三方插件都走这条）；
    * 当前家族 `unknown` ⇒ **一律支持**（宁可多显示，不可误伤）。
    """
    if not isinstance(families, (list, tuple)) or not families:
        return True
    now = str(os_family or '').strip().lower()
    if not now or now == FAMILY_UNKNOWN:
        return True
    wanted = {str(x).strip().lower() for x in families if str(x).strip()}
    if not wanted:
        return True
    return now in wanted


def family_label(family):
    """家族 → 人话（面板日志/自检输出用；前端另有 i18n 文案）。"""
    return {
        FAMILY_DEB: 'Debian/Ubuntu 系',
        FAMILY_RPM: 'RHEL/CentOS 系',
        FAMILY_SUSE: 'SUSE 系',
        FAMILY_ARCH: 'Arch 系',
        FAMILY_ALPINE: 'Alpine',
        FAMILY_MACOS: 'macOS',
        FAMILY_UNKNOWN: '未识别',
    }.get(str(family or '').strip().lower(), '未识别')


def is_linux_container_friendly():
    """是否存在 `/etc/os-release`（容器里常见；仅用于自检提示，不影响判定）。"""
    return os.path.isfile('/etc/os-release')
