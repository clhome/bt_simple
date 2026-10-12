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

#: SQL 标识符 / 复制渠道名 / 同步 sign（`FOR CHANNEL 'x'`、`SLAVE 'x'`）：
#: 这些位置无法参数化，只能靠白名单。用户裁定（父 agent §四 裁决）：字符集
#: `[A-Za-z0-9_$-]`，**拒绝反引号/点/空格/引号/`;`/`|`/`$(` 等 shell/SQL 元字符**；
#: 允许 `-` —— MySQL 库名（`my-db`）合法含 `-`，`addDb` 侧白名单也是 `[\w-]+`。
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_$-]{1,64}$')

#: 主库 SSH 回传的同步命令：必须是一条 CHANGE MASTER TO / CHANGE REPLICATION SOURCE TO。
#: MariaDB 允许渠道名形态 `CHANGE MASTER 'r1' TO ...`（渠道名由 `getDbServerId()` 生成，
#: 见 `plugins/mariadb/index.py::getMasterRepSlaveUserCmdSsh`）。渠道名单独捕获后交给
#: `safeIdentifier` 校验 —— 绝不用 `.*?` 把 `MASTER` 与 `TO` 之间放宽了事。
_REPLICATION_CMD_RE = re.compile(
    r"^(?:CHANGE\s+MASTER\s+(?:'(?P<channel>[^']*)'\s+)?TO"
    r"|CHANGE\s+REPLICATION\s+SOURCE\s+TO)\b", re.I)

#: 同步命令里禁止出现的形态：多语句分隔符 / 注释符 / 换行
_REPLICATION_CMD_FORBIDDEN = (';', '--', '#', '/*', '*/', '\n', '\r')

#: 主从同步账号口令：只拒控制字符（\x00-\x1f、\x7f），长度 1–128，其余一律允许。
#: 用户裁定（P0-1④ follow-up）：现网口令常含 `$ ! # * ( )` 等，收紧白名单会让它们
#: 同步失败；注入已由拼接侧 `yf.shlexQuote` 根治，这里只挡会破坏命令行与行协议的
#: 控制字符（NUL/换行/回车/制表符）。匹配必须走 `fullmatch`（等价 `\Z`），**不可用
#: `$`** —— `$` 允许在结尾换行前匹配，`abc\n` 会漏过（探针 M10 自证）。
_SYNC_PASS_RE = re.compile(r'[^\x00-\x1f\x7f]{1,128}')


def safeIdentifier(value):
    """SQL 标识符（反引号包裹的库名）/ 复制渠道名 / 同步 sign 白名单；非法返回 ''。

    用户裁定（父 agent §四 裁决）：字符集 `^[A-Za-z0-9_$-]{1,64}$`，拒绝反引号/点/空格/
    引号/`;`/`|`/`$(` 等 shell/SQL 元字符，但**允许 `-`**（MySQL 库名合法字符，如 `my-db`；
    收紧到不含 `-` 会误拒既有合法库名）。用于**无法参数化**的标识符位置：`show tables from <db>`、
    `REPAIR/OPTIMIZE/ALTER TABLE <db>.<t>`、`STOP/START SLAVE ... FOR CHANNEL '<name>'`。
    这些值来自用户入参（`args['name']`/`args['db_name']`/`deleteSlave` 的 `sign`）或
    服务器回显（`SHOW SLAVE STATUS` 的 `Channel_Name`），都不得裸拼进 SQL 文本。
    """
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        return ''
    return value


def safeReplicationCmd(cmd):
    """主库 SSH 回传的同步命令结构白名单；非法返回 ''。

    该命令会被从库直接 `db.query(cmd)` 执行，而其中的用户名/口令来自主库的
    `master_replication_user`（用户可控）。这里只放行**单条**
    `CHANGE MASTER TO` / `CHANGE REPLICATION SOURCE TO`，以及 MariaDB 的渠道名形态
    `CHANGE MASTER '<channel>' TO ...`；渠道名必须再经 `safeIdentifier` 校验，并拒绝含
    多语句分隔符 `;`、注释符 `--`/`#`/`/*`/`*/` 或换行的形态；校验不过一律 fail closed。
    """
    if not isinstance(cmd, str):
        return ''
    c = cmd.strip()
    m = _REPLICATION_CMD_RE.match(c)
    if not m:
        return ''
    channel = m.groupdict().get('channel')
    if channel is not None and not safeIdentifier(channel):
        return ''
    for token in _REPLICATION_CMD_FORBIDDEN:
        if token in c:
            return ''
    return c


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
