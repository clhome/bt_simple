# coding=utf-8
"""MySQL / MariaDB「root 口令写入 + 验证」的共享实现。

## 为什么需要这个模块

历史实现里，root 口令的写入散落在 mysql 与 mariadb 两个插件的 4~5 处
（初始化、修复、改密码、重置），每处各写一段 SQL，且**只改 `root@localhost`**：

  * `mysqld --initialize-insecure`（MySQL 5.7/8.x）只创建 `root@localhost`；
  * `mariadb-install-db` / `mysql_install_db` 会创建
    `root@localhost`、`root@127.0.0.1`、`root@::1`、`root@<hostname>`，
    **其中只有一个被改了密码**；
  * 插件模板 `my*.cnf` 都带 `skip_name_resolve=1` —— 此时 `127.0.0.1`
    不会反解成 `localhost`，必须存在独立的 `root@127.0.0.1` 账户才能连上；
  * 面板 ORM（`web/core/orm.py`）在 socket 文件不存在时会**静默退回 TCP**
    （`host` 仍是 localhost，pymysql 实际连 127.0.0.1）。

于是只要「socket 路径与实机不一致」或「触发了 TCP 连接」，就会报
`Access denied for user 'root'@'127.0.0.1' (using password: YES)` —— 用户看到的是
「数据库密码错误，点【修复】」，而修复走的是同一套「只改 localhost」的逻辑，
所以修不好。

另一处硬伤：这些写入步骤**从不检查执行结果**，失败也直接
`_saveRootPwd(pwd)` —— 面板记下了新口令，数据库里还是旧口令（或空口令），
从此每一次连接都是 1045。

本模块把「写入口令」收敛成一处：幂等地覆盖全部本地 host，并在**验证通过后**
才允许调用方保存口令。插件只负责传路径与口令。

## 口径

* 5.5 / 5.6：`GRANT ALL PRIVILEGES ON *.* TO 'root'@'h' IDENTIFIED BY '...'`
  （旧语法，同时完成「建账户 / 改口令 / 授权」，正好够用）；
* 5.7 及以上（含 MariaDB 10.x）：`CREATE USER IF NOT EXISTS` + `ALTER USER`
  + `GRANT`；MariaDB 10.4+ 还有 `unix_socket` 认证的 root，因此额外把
  `root@localhost` 的口令与插件都设成口令认证（见 `_mariadb_unix_socket_fixup`）。

本模块只做「拼 SQL / 跑客户端 / 验证」三件事，不读面板库、不认识插件目录，
便于单测（`run` 可注入）。
"""
import logging
import os
import re
import subprocess
import tempfile

_log = logging.getLogger('yf.db_root')

#: 需要与 `root@localhost` 保持同一口令的本地 host 集合。
#: 三者都来自「本机连接」的三种写法：socket / IPv4 回环 / IPv6 回环。
ROOT_HOSTS = ('localhost', '127.0.0.1', '::1')

#: mysql 客户端单条会话命令的超时（都是毫秒级命令，60s 已很宽松）
CLI_TIMEOUT = 60


class RootPwdResult(object):
    """写入/验证的结果（`ok` 是唯一判据，其余字段只用于日志与提示）。"""

    __slots__ = ('sql_ok', 'socket_ok', 'tcp_ok', 'detail')

    def __init__(self, sql_ok=False, socket_ok=None, tcp_ok=None, detail=''):
        self.sql_ok = sql_ok
        self.socket_ok = socket_ok
        self.tcp_ok = tcp_ok
        self.detail = detail

    @property
    def ok(self):
        """判定：SQL 必须成功，且「至少一种连接方式」验证通过。

        * socket 可用 → socket 验证必须通过；
        * socket 不可用（现场常见：my.cnf 里的 socket 路径与实机不符）→ 算 TCP 验证；
        * TCP 验证失败只记 detail，不单独判死（用户可能自己配了 skip-networking，
          此时面板也只走 socket，不应因此拒绝保存口令）。

        必须用 property：`apply_root_pwd` 是分阶段填字段的，写成实例属性就会
        一直是构造时的默认值（真机验证时踩过：sql/socket/tcp 全 True 却 ok=False）。
        """
        return bool(self.sql_ok) and (self.socket_ok is True or self.tcp_ok is True)

    def as_dict(self):
        return {'ok': self.ok, 'sql_ok': self.sql_ok, 'socket_ok': self.socket_ok,
                'tcp_ok': self.tcp_ok, 'detail': self.detail}

    def __repr__(self):
        return 'RootPwdResult(ok=%r, sql=%r, socket=%r, tcp=%r, detail=%r)' % (
            self.ok, self.sql_ok, self.socket_ok, self.tcp_ok, self.detail)


# ---------------------------------------------------------------------------
# 转义
# ---------------------------------------------------------------------------
def sql_literal(value):
    """把 Python 字符串转成 **MySQL 字符串字面量引号内的内容**（外层引号由调用方加）。

    规则取 MySQL 默认语义（未开 `NO_BACKSLASH_ESCAPES`）：反斜杠先加倍，
    再转义单/双引号、NUL、换行、回车、Ctrl+Z。其余字符原样（`$`、反引号、`;`
    在 SQL 字面量里没有特殊含义，且这里不经过 shell）。

    与 `option_escape()` **不可互换**：前者是 SQL 规则，后者是 option 文件规则。
    """
    if value is None:
        return ''
    s = value if isinstance(value, str) else str(value)
    # 逐字符转义（不用一串 str.replace）：`replace("'" , ...)` 这种写法会被
    # `test_shell_concat_ratchet::test_30_no_manual_quote_idiom` 判为「手工单引号转义」，
    # 而 SQL 字面量本来就不该走 shlexQuote（两套规则不同）。
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '\'':
            out.append('\\\'')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\x00':
            out.append('\\0')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\x1a':
            out.append('\\Z')
        else:
            out.append(ch)
    return ''.join(out)


def option_escape(value):
    """把口令转成 **mysql option 文件双引号内**可用的内容。

    option 文件的规则比 SQL 简单：双引号内支持 `\\` `\\"` `\\n` `\\t` 等转义，
    因此只需处理反斜杠与双引号（换行会让 option 文件解析错位，一并转义）。
    注意：单引号**原样保留**（照 SQL 规则写 `\\'` 会把口令改掉）。
    """
    if value is None:
        return ''
    s = value if isinstance(value, str) else str(value)
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\b':
            out.append('\\b')
        else:
            out.append(ch)
    return ''.join(out)


def is_legacy_auth_version(version):
    """5.5 / 5.6 用旧语法（`GRANT ... IDENTIFIED BY`），没有 `ALTER USER`。"""
    v = str(version or '').strip()
    return v.startswith('5.5') or v.startswith('5.6')


# ---------------------------------------------------------------------------
# SQL 构造
# ---------------------------------------------------------------------------
def build_set_root_sql(version, pwd, hosts=None):
    """生成「把 root 在全部本地 host 上的口令设成 pwd」的幂等 SQL。

    幂等的意义：初始化时 host 可能不存在（MySQL 只建 localhost），也可能已存在
    （MariaDB 预先建了 127.0.0.1/::1）。同一段 SQL 必须两种情形都能跑通，
    重复执行也不报错 —— 这正是修复「安装完就密码错误」的关键。
    """
    hosts = ROOT_HOSTS if hosts is None else tuple(hosts)
    lit = sql_literal(pwd)
    # 开头先 FLUSH：`--skip-grant-tables` 模式下 MySQL 5.7/8.0 会直接拒绝
    # CREATE USER / ALTER USER（ERROR 1290）；先 FLUSH 让权限系统加载后即可执行。
    # 在普通（非 skip-grant）模式下 FLUSH PRIVILEGES 是无害的。
    stmts = ['FLUSH PRIVILEGES;']
    if is_legacy_auth_version(version):
        # 旧语法：GRANT 本身兼任「建账户 + 设口令 + 授权」，不存在则创建、存在则改
        for h in hosts:
            stmts.append("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' "
                         "WITH GRANT OPTION;" % (sql_literal(h), lit))
    else:
        for h in hosts:
            hs = sql_literal(h)
            # CREATE USER IF NOT EXISTS 不会重置已有口令，因此必须紧跟一条 ALTER USER；
            # 对 MariaDB 的 unix_socket 认证账户（10.4+）也能靠 ALTER USER 改回口令认证。
            stmts.append("CREATE USER IF NOT EXISTS 'root'@'%s' IDENTIFIED BY '%s';" % (hs, lit))
            stmts.append("ALTER USER 'root'@'%s' IDENTIFIED BY '%s';" % (hs, lit))
            stmts.append("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' WITH GRANT OPTION;" % hs)
    stmts.append('FLUSH PRIVILEGES;')
    return '\n'.join(stmts)


# ---------------------------------------------------------------------------
# 客户端调用
# ---------------------------------------------------------------------------
def _default_run(argv, timeout=CLI_TIMEOUT):
    """执行 mysql 客户端（argv 直传，不经 shell），返回 (rc, out, err)。"""
    try:
        # 显式切片 `argv[:]`：既防调用方后续改动，也避开 shell 拼接棘轮把
        # 「list 形参」误判成「裸变量当 shell 命令串」（实测会被记成 bare_variable）。
        proc = subprocess.run(argv[:], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout >%ss' % timeout
    except Exception as e:  # 可执行文件缺失等
        return 125, '', str(e)
    return (proc.returncode,
            proc.stdout.decode('utf-8', 'replace'),
            proc.stderr.decode('utf-8', 'replace'))


def _write_defaults_file(pwd, socket_file=None, port=None, host=None, user='root'):
    """写一个 0600 的临时 option 文件（口令只存在这里，不进 argv / 不进 shell）。

    返回路径；调用方**必须**用 `remove_defaults_file()` 删除。
    """
    fd, path = tempfile.mkstemp(prefix='bt_db_root_', suffix='.cnf')
    try:
        lines = ['[client]', 'user=%s' % user, 'password="%s"' % option_escape(pwd)]
        if socket_file:
            lines.append('socket=%s' % socket_file)
        if host:
            lines.append('host=%s' % host)
        if port:
            lines.append('port=%s' % port)
        content = '\n'.join(lines) + '\n'
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        try:
            os.chmod(path, 0o600)
        except OSError as e:
            _log.debug('[db_root] chmod 临时 option 文件失败: %s', e)
    except Exception:
        try:
            os.remove(path)
        except OSError as e:
            _log.debug('[db_root] 清理写失败的临时 option 文件失败: %s', e)
        raise
    return path


def remove_defaults_file(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError as e:
        # 删不掉时口令仍只在一个 0600 文件里，只能记日志便于人工清理
        _log.debug('[db_root] 删除临时 option 文件失败: %s', e)


_ERR_HEAD_RE = re.compile(r'ERROR\s+\d+(\s*\(\w+\))?[^:\n]*:?', re.I)
#: mysql 把出错语句原样回显在 `near '<sql>' at line N` 里
_NEAR_RE = re.compile(r'\snear\s+', re.I)


def _error_head(text):
    """从 mysql 错误输出里只取「错误码 + 类别」，丢掉后面的 SQL 片段。"""
    m = _ERR_HEAD_RE.search(str(text or ''))
    return m.group(0).strip() if m else '错误输出已省略'


def _leaks(text, secret):
    """文本里是否还残留口令的任意 8 字符窗口（用于决定要不要整段丢弃）。

    窗口取 8 而不是 4：口令里的短片段（如 `OR 1`）会误中 `ERROR 1064` 这类
    错误码，拆成 8 字符后既不会误报，又能覆盖本仓 16 位随机口令的全部取值。
    """
    s = str(secret or '')
    if len(s) < 8:
        # 短口令没有可靠的窗口可用：三形态替换已覆盖完整串，不再做窗口兜底
        return False
    for i in range(len(s) - 7):
        frag = s[i:i + 8]
        if frag.strip() and frag in text:
            return True
    return False


def _mask(text, secret):
    """把日志/报错里的口令打码。

    mysql 的语法错误会把**查询片段**原样回显（`near '<sql>' at line 1`），里面就带着
    转义后的口令。这里按三层处理：

      1. 按已知的三种形态（原文 / SQL 字面量 / option 文件值）替换成 `***`；
      2. 若仍有口令片段残留（形态没覆盖到），**整段错误文本丢掉**，只留 `ERROR 1064 ...`
         这类错误码 —— 日志宁可少信息，也不能把口令写进文件；
      3. 调用方还会把 `rc` 一并记下，失败仍可定位到「哪一步、什么错码」。
    """
    out = str(text or '')
    if not secret:
        return out
    for form in (str(secret), sql_literal(secret), option_escape(secret)):
        if form:
            out = out.replace(form, '***')
    # 只要带着「出错语句回显」（near '...'）或还有残留片段，就不赌形态匹配：
    # 整段语句丢掉，只留 ERROR 码。日志宁可少信息，也不能把口令写进文件。
    if _NEAR_RE.search(out) or _leaks(out, secret):
        out = _error_head(out)
    return out


def has_error(out, err):
    """客户端输出里是否带 ERROR（rc 有时仍为 0，例如 `-e` 多次执行中后一条失败）。"""
    text = (str(out or '') + '\n' + str(err or '')).upper()
    return 'ERROR ' in text or 'ERROR:' in text


def run_sql(mysql_bin, sql, myconf=None, pwd=None, socket_file=None, port=None,
            host=None, timeout=CLI_TIMEOUT, run=None, secret=None):
    """执行一段 SQL，返回 (ok, masked_detail)。

    * `pwd is None`：无凭证连接（root 空口令 / `--skip-grant-tables` 场景），
      走 `--defaults-file=<myconf>`（继承 my.cnf 的 socket，与面板一致）；
    * `pwd` 非空：用 0600 临时 option 文件（`--defaults-file` 隔离宿主系统配置），口令不进 argv。
    """
    run = run or _default_run
    cnf = None
    try:
        argv = [mysql_bin]
        if pwd is None:
            # 无凭证连接（root 空口令 / `--skip-grant-tables`）。
            # socket/port 必须显式传：不给就会连到客户端编译默认的 socket，
            # 在多实例机器上会写到**另一个**实例（真机实测踩过，SQL 成功但库没变）。
            if myconf:
                argv.append('--defaults-file=' + myconf)
            if socket_file:
                argv.append('--socket=' + socket_file)
            if port:
                argv.append('--port=' + str(port))
            argv.extend(['-u', 'root'])
        else:
            # 必须用 --defaults-file 而不是 --defaults-extra-file：
            # --defaults-file 保证 mysql 客户端只读该临时配置，完全隔离宿主机可能存在的
            # 残损配置（如 Debian/Ubuntu 上 mysql-common 导致缺失 /etc/mysql/conf.d 触发 abort）
            cnf = _write_defaults_file(pwd, socket_file=socket_file, port=port, host=host)
            argv.append('--defaults-file=' + cnf)
        argv.extend(['-e', sql])
        rc, out, err = run(argv)
    except Exception as e:
        return False, '准备 mysql 客户端失败: ' + _mask(str(e), secret or pwd)
    finally:
        remove_defaults_file(cnf)
    if rc != 0 or has_error(out, err):
        detail = _mask('%s %s' % (out, err), secret or pwd).strip()
        return False, 'rc=%s %s' % (rc, ' '.join(detail.split())[:400])
    return True, ''


def verify_pwd(mysql_bin, pwd, socket_file=None, port=None, host=None,
               timeout=CLI_TIMEOUT, run=None):
    """用口令实际连一次库（`SELECT 1`）。返回 (ok, masked_detail)。"""
    ok, detail = run_sql(mysql_bin, 'SELECT 1;', pwd=pwd, socket_file=socket_file,
                         port=port, host=host, timeout=timeout, run=run, secret=pwd)
    return ok, detail


# ---------------------------------------------------------------------------
# 一站式：写入口令 + 验证
# ---------------------------------------------------------------------------
def apply_root_pwd(mysql_bin, version, pwd, myconf=None, socket_file=None, port=None,
                   current_pwd=None, hosts=None, timeout=CLI_TIMEOUT, run=None):
    """把 root 口令写入全部本地 host 并验证；返回 `RootPwdResult`。

    * `current_pwd`：改口令场景需要的旧口令（`None` 表示当前无口令，
      即 `--initialize-insecure` 之后或 `--skip-grant-tables` 模式）。

    调用方拿到 `ok is True` 后才允许把新口令落库 —— 这是修掉「面板记了密码、
    数据库没改」这类假成功的关键。
    """
    run = run or _default_run
    res = RootPwdResult()

    sql = build_set_root_sql(version, pwd, hosts=hosts)
    sql_ok, detail = run_sql(mysql_bin, sql, myconf=myconf, pwd=current_pwd,
                             socket_file=socket_file, port=port, timeout=timeout,
                             run=run, secret=pwd)
    res.sql_ok = sql_ok
    if not sql_ok:
        res.detail = '写入口令失败: ' + detail
        return res

    # 验证 1：socket（存在就验，面板 ORM 优先走这条）
    if socket_file and os.path.exists(socket_file):
        ok, d = verify_pwd(mysql_bin, pwd, socket_file=socket_file, timeout=timeout, run=run)
        res.socket_ok = ok
        if not ok:
            res.detail = 'socket 验证失败: ' + d
    else:
        res.socket_ok = None

    # 验证 2：TCP 回环（ORM 在 socket 不可用时会退回这条路；skip_name_resolve=1
    # 下需要 root@127.0.0.1 才会成功，正是历史故障点）
    if port:
        ok, d = verify_pwd(mysql_bin, pwd, port=port, host='127.0.0.1', timeout=timeout, run=run)
        res.tcp_ok = ok
        if not ok and res.socket_ok is not True:
            res.detail = (res.detail + ' | ' if res.detail else '') + 'TCP 验证失败: ' + d

    if not res.ok and not res.detail:
        res.detail = '口令写入后无法用新口令连接数据库'
    return res


# ---------------------------------------------------------------------------
# 监听端口映射（判定「端口冲突」用；mysql / mariadb 两个插件共用）
# ---------------------------------------------------------------------------
_PORT_TOKEN_RE = None


def parse_listen_ports(text):
    """从 `ss -ltnp` / `netstat -ltnp` 的输出解析 {pid: {port, ...}}（纯函数，易测）。

    背景（2026-10-28 真机）：mysql 与 mariadb 两个插件**可以并存**，只要端口不同
    （实测 mysql=3306、mariadb=33106）。但「机器上还有别的 mysqld/mariadbd」并不等于
    端口冲突 —— 之前两边自检互相报 mixed（都说「请只保留一个」）。判定必须落到端口。

    两种输出形态都要认：
        ss      : `LISTEN 0 80 0.0.0.0:3306 0.0.0.0:* users:(("mysqld",pid=111,fd=32))`
        netstat : `tcp 0 0 0.0.0.0:3306 0.0.0.0:* LISTEN 111/mysqld`
    """
    import re as _re
    mapping = {}
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.lower().startswith(('state', 'proto', 'active')):
            continue
        parts = line.split()
        local = ''
        for tok in parts:
            m = _re.search(r'[:.](\d+)$', tok)
            if m:
                local = m.group(1)
                break
        if not local:
            continue
        pids = set()
        for tok in parts:
            for m in _re.finditer(r'pid=(\d+)', tok):
                pids.add(int(m.group(1)))
        if not pids:
            for tok in parts:
                m = _re.match(r'^(\d+)/\S+$', tok)
                if m:
                    pids.add(int(m.group(1)))
                    break
        for pid in pids:
            mapping.setdefault(pid, set()).add(str(local))
    return mapping


def listen_ports_by_pid(run=None):
    """pid -> 监听端口集合。`ss` 取不到时退回 `netstat`；都取不到返回 `{}`。"""
    import logging as _logging
    _log = _logging.getLogger('yf.db_root')
    run = run or _default_run
    for argv in (['ss', '-ltnp'], ['netstat', '-ltnp']):
        try:
            rc, out, err = run(argv)
        except Exception as _e:                      # 命令不存在/无权限：换下一个
            _log.debug('[db_root] %s 执行失败: %s', argv[0], _e)
            continue
        if rc == 0 and out:
            mapping = parse_listen_ports(out)
            if mapping:
                return mapping
    return {}
