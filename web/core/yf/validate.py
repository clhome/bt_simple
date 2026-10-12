# coding=utf-8
"""core.yf 子模块：shell/路径拼接前的输入白名单校验。

背景：`plugins/mysql` 与 `plugins/mariadb` 是近亲复制品（136 个同名函数），安全
加固历史上只落在单侧 —— `mysql::safe_check_args` 有 7 处调用，`mariadb` 整文件
0 处，测评报告 P0-1③ 称之为最典型的「修了一半」。校验收敛到这里后，两端引用
**同一个实现**，再次单侧漂移就会在守卫用例里直接变红。

约定：所有函数「不合法返回空串 / None / False」，调用方必须显式拒绝，
绝不静默放行。**口令是例外**：只挡控制字符（用户裁定，见 `safeSyncPass`），
注入由拼接侧 `yf.shlexQuote` 的单引号包裹根治，写入侧 + 拼接侧双保险不变。
"""

import ipaddress
import re

from .shell import invalidPathReason

#: 库名 / 数据库用户名：与 mysql 插件历史白名单逐字符一致
_DB_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

#: 同步标识（sign）：mysql 插件历史白名单，另允许 `.` 与 `:`
_SIGN_RE = re.compile(r'^[a-zA-Z0-9_\-\.:]+$')

#: datadir：绝对路径 + 限字符集 + 限长（`..` 由 safeDatadir 显式拒绝）
_DATADIR_RE = re.compile(r'^/[A-Za-z0-9_./-]{1,200}$')

#: 主从同步账号用户名：白名单字符集，天然排除引号/空白/shell 元字符（; | & $ ` ( ) < > 等）
_SYNC_USER_RE = re.compile(r'^[A-Za-z0-9_@.\-]{1,64}$')

#: 主从同步账号口令：只拒控制字符（\x00-\x1f、\x7f），长度 1–128，其余一律允许。
#: 用户裁定（P0-1④ follow-up）：现网口令常含 `$ ! # * ( )` 等，收紧白名单会让它们
#: 同步失败；注入已由拼接侧 `yf.shlexQuote` 根治，这里只挡会破坏命令行与行协议的
#: 控制字符（NUL/换行/回车/制表符）。匹配必须走 `fullmatch`（等价 `\Z`），**不可用
#: `$`** —— `$` 允许在结尾换行前匹配，`abc\n` 会漏过（探针 M10 自证）。
_SYNC_PASS_RE = re.compile(r'[^\x00-\x1f\x7f]{1,128}')


def dbSafeCheckArgs(db_name=None, sign_val=None, username=None):
    """库名/同步标识/用户名白名单（None 表示「不校验该项」，与旧签名一致）。"""
    if db_name is not None and not _DB_NAME_RE.match(str(db_name)):
        return False
    if sign_val is not None and not _SIGN_RE.match(str(sign_val)):
        return False
    if username is not None and not _DB_NAME_RE.match(str(username)):
        return False
    return True


def safeDatadir(path):
    """datadir 白名单：绝对路径、拒 `..`、限字符集与长度；非法返回 ''。

    先沿用 `yf.invalidPathReason` 的既有语义（拒根目录/占位符/非字符串），再叠加
    shell 元字符不可能出现在白名单字符集里这一层 —— 只靠 `invalidPathReason`
    是拦不住 `;`、`$()`、反引号、管道的（测评报告 P0-1②）。
    """
    if not isinstance(path, str):
        return ''
    path = path.strip()
    if not path or '..' in path:
        return ''
    if invalidPathReason(path):
        return ''
    if not _DATADIR_RE.match(path):
        return ''
    return path


def safeSyncIp(ip):
    """IPv4/IPv6 地址校验（兼容两者）；非法返回 ''。"""
    if not isinstance(ip, str) or not ip or ip.strip() != ip:
        return ''
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return ''


def safeSyncPort(port):
    """端口校验：1–65535 的整数（入参可为 str/int）；非法返回 None。"""
    try:
        value = int(str(port).strip())
    except (TypeError, ValueError):
        return None
    if value < 1 or value > 65535:
        return None
    return value


def safeSyncUser(user):
    """主从同步账号用户名白名单；非法返回 ''。"""
    if not isinstance(user, str) or not _SYNC_USER_RE.match(user):
        return ''
    return user


def safeSyncPass(apass):
    r"""主从同步账号口令校验：只拒控制字符；非法返回 ''。

    用户裁定（P0-1④ follow-up）：放宽为「可打印字符 + 强制引用」。现网口令常含
    `$ ! # * ( ) ;` 等，按字符集白名单收紧会让存量账号同步失败。**注入由拼接侧
    `yf.shlexQuote` 的单引号包裹保证**（`doFullSyncUser` 里是 `-p` + shlexQuote(apass)，
    单引号本身也被转义），本函数只挡控制字符：NUL/换行/回车/制表符会破坏命令行
    分词与「一行一条记录」的协议。

    用 `fullmatch`（等价 `\Z`）而非 `$` 锚定：`$` 会在结尾换行前匹配，`abc\n` 漏过。
    """
    if not isinstance(apass, str) or not _SYNC_PASS_RE.fullmatch(apass):
        return ''
    return apass
