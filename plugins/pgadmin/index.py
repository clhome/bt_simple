# coding:utf-8

import sys
import io
import os
import time
import re
import json
import sqlite3

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'pgadmin'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


# config_local.py 模板版本，必须与 conf/config_local.py 里的 PGADMIN_LOCAL_TPL_VERSION 一致
LOCAL_TPL_VERSION = 5
# vhost 模板版本，必须与 conf/pgadmin.conf 里的 PGADMIN_VHOST_TPL_VERSION 一致
VHOST_TPL_VERSION = 3


def getDataDir():
    """pgAdmin 运行时数据根目录。

    **必须与 conf/config_local.py 里 {$DATA_PATH} 的替换值完全一致**
    （initPgConfFile() 用 getDataDir() 替换）。

    getServerDir() 已包含 '/pgadmin'（= yf.getServerDir()+'/pgadmin'），
    所以 getServerDir()+'/data' 实际解析为 <baseServerDir>/pgadmin/data，
    与 pg_init.sh 中 mkdir -p "${pg_dir}/data/pgadmin4" 完全一致。
    """
    return getServerDir() + '/data'


def getPgAdminDbPath():
    return getDataDir() + '/pgadmin4/pgadmin4.db'


def getSessionDir():
    return getDataDir() + '/pgadmin4/sessions'


def getRunDir():
    return getServerDir() + '/run'


def getBasicAuthFile():
    return getServerDir() + '/pg.pass'


def getProvisionScriptPath():
    return getServerDir() + '/pg_user_sync.py'


# pgAdmin 的 validate_email() 走 email_validator，且 config.GLOBALLY_DELIVERABLE = True
# ⇒ 域名必须带点、且不能是 RFC6761 特殊用途域名（local / localhost / internal / test …）。
# 两边口径不一致的后果是**静默失败**：面板把邮箱存进 cfg.json，
# pgAdmin 的 create_user 却报 `Invalid email address`，账号根本没建出来；
# 而登录侧 InternalAuthentication.validate() 第一句也是 validate_email()，
# 会直接把请求打回登录页（302 → /login），与密码对不对无关。
SPECIAL_USE_DOMAINS = (
    'arpa', 'example', 'internal', 'invalid', 'local', 'localhost',
    'onion', 'test', 'localdomain', 'home', 'lan', 'corp', 'intranet',
    'private',
)

_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.\-]+$")
_DOMAIN_RE = re.compile(
    r'^[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?'
    r'(\.[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?)+$')


def isEmail(value):
    """邮箱格式预校验，口径对齐 pgAdmin 的 validate_email()。

    用户名的非法值会让 create_user 直接失败 —— 账号建不出来却把邮箱
    写进 cfg.json，用户拿到的就是登不进去的账号。
    """
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or value.count('@') != 1 or len(value) > 254:
        return False
    local, domain = value.rsplit('@', 1)
    if not local or not domain or len(local) > 64:
        return False
    if local.startswith('.') or local.endswith('.') or '..' in local:
        return False
    if _LOCAL_PART_RE.match(local) is None:
        return False
    domain = domain.rstrip('.')
    if '.' not in domain or _DOMAIN_RE.match(domain) is None:
        return False
    if domain.rsplit('.', 1)[-1].lower() in SPECIAL_USE_DOMAINS:
        return False
    return True


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        raw = args[0].strip()
        # 优先尝试 JSON 解析（框架 plugin_api.js 传递标准 JSON 字符串）
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # 回退到旧的 key:value 格式解析
        # split(':', 1) 保证值里的冒号不被截断（如口令含冒号），
        # 同时缺冒号时不再抛 IndexError
        t = raw.strip('{').strip('}').split(':', 1)
        if len(t) == 2:
            tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            if len(t) == 2:
                tmp[t[0]] = t[1]

    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def getConf():
    return yf.getServerDir() + '/web_conf/nginx/vhost/pgadmin.conf'


def getPort():
    file = getConf()
    content = yf.readFile(file)
    rep = r'listen\s*(.*);'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()


def getHomePage():
    try:
        port = getPort()
        ip = '127.0.0.1'
        if not yf.isAppleSystem():
            ip = yf.getLocalIp()

        cfg = getCfg()
        auth = cfg['username']+':'+cfg['password']
        url = 'http://' + auth + '@' + ip + ':' + port + '/'
        return yf.returnJson(True, 'OK', url)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')


def contentReplace(content):
    cfg = getCfg()
    service_path = yf.getServerDir()

    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$APP_PATH}', service_path+'/'+getPluginName()+'/data')

    port = cfg["port"]
    rep = r'listen\s*(.*);'
    content = re.sub(rep, "listen " + port + ';', content)
    return content


def initCfg():
    cfg = getServerDir() + "/cfg.json"
    if not os.path.exists(cfg):
        data = {}
        data['port'] = '5051'
        data['path'] = ''
        # 基础认证凭据直接随机生成，不留 admin/admin 默认口令窗口
        data['username'] = yf.getRandomString(8)
        data['password'] = yf.getRandomString(10)
        # pgAdmin 内部账号留空，首次启动时随机生成并真正写入数据库
        data['web_pg_username'] = ''
        data['web_pg_password'] = ''
        yf.writeFile(cfg, json.dumps(data))


def getCfg():
    cfg = getServerDir() + "/cfg.json"
    raw = yf.readFile(cfg)
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def setCfg(key, val):
    cfg = getServerDir() + "/cfg.json"
    data = getCfg()
    data[key] = val
    return yf.writeFile(cfg, json.dumps(data))


def returnCfg():
    return yf.readFile(getServerDir() + "/cfg.json")


def __release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().addAcceptPort(port, 'pgAdmin默认端口', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def __delete_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().delAcceptPort(port, 'tcp')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def openPort():
    conf = getCfg()
    port = conf['port']
    for i in [port]:
        __release_port(i)
    return True


def delPort():
    conf = getCfg()
    port = conf['port']
    for i in [port]:
        __delete_port(i)
    return True


def cleanNginxLog():
    log_a = accessLog()
    log_e = errorLog()

    for i in [log_a, log_e]:
        if os.path.exists(i):
            # 用参数列表而不是拼 shell 字符串，避免路径里的特殊字符被解释
            yf.safeExecShell(['truncate', '-s', '0', i], timeout=30)

def getPythonName():
    """返回 venv 中真正承载 pgadmin4 的 pythonX.Y 目录名；未安装时返回 ''。

    旧实现把路径硬编码成 <serverDir>/pgadmin/run/lib/ 且不校验 pgadmin4 是否存在，
    server 目录一变（或 pgadmin4 尚未安装）就会拼出一个不存在的路径。
    """
    lib_dir = getRunDir() + '/lib'
    try:
        names = sorted(os.listdir(lib_dir))
    except Exception:
        return ''
    for name in names:
        if not name.startswith('python'):
            continue
        if os.path.exists(os.path.join(lib_dir, name, 'site-packages/pgadmin4/config.py')):
            return name
    return ''


def getPgAdminDir():
    pyname = getPythonName()
    if not pyname:
        return ''
    return getRunDir() + '/lib/' + pyname + '/site-packages/pgadmin4'


def getPgAdminPython():
    return getRunDir() + '/bin/python'


# ---------------------------------------------------------------------------
# pgAdmin 内部账号：创建 / 改名 / 改密 / 解锁
#
# 「登录后弹回登录页」的三条真实原因（都是本模块的历史缺陷）：
#   1. 插件去 <serverDir>/data/pgadmin4/pgadmin4.db 找库，
#      而 pgAdmin 实际用的是 <serverDir>/pgadmin/data/pgadmin4/pgadmin4.db；
#      于是解锁/改密全部静默失效，而且每次 start/restart 都重新随机一套
#      登录邮箱与口令 —— 用户抄到的凭据在数据库里根本不存在；
#   2. pgAdmin 4 v8+ 的 `setup.py setup-db` 只建表、不建账号；
#   3. 旧代码从 pgadmin.tools.user_management 里导入了一个并不存在的函数名
#      （官方叫 update_user），异常被 except 吞掉，最后仍然返回“同步成功”。
# 所以现在的实现：写完**回读数据库校验**，失败就如实返回失败。
# ---------------------------------------------------------------------------

PROVISION_TEMPLATE = '''# -*- coding: utf-8 -*-
"""pgAdmin 内部账号同步脚本（由 plugins/pgadmin/index.py 生成，请勿手工修改）。

用法: <venv>/bin/python pg_user_sync.py <email> <password> [match_email] [force]
输出: PGA_DB:<实际使用的配置库路径> / PGA_OK / PGA_ERR:<原因> / PGA_EXC:<堆栈>
退出码: 0=成功 2=官方 API 失败 3=写入后查不到 4=账号状态异常 5=异常
"""
import os
import sys

PGADMIN_DIR = {pgadmin_dir!r}
EMAIL = sys.argv[1]
PASSWORD = sys.argv[2]
MATCH = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else EMAIL


def out(tag, msg=''):
    sys.stdout.write('%s%s\\n' % (tag, msg))
    sys.stdout.flush()


def main():
    sys.path.insert(0, PGADMIN_DIR)
    os.chdir(PGADMIN_DIR)

    import config
    out('PGA_DB:', str(getattr(config, 'SQLITE_PATH', '')))

    from pgadmin import create_app
    from pgadmin.model import db, User, Role

    app = create_app(config.APP_NAME + '-cli')
    with app.test_request_context():
        from pgadmin.tools import user_management as um
        create_user = getattr(um, 'create_user', None)
        # 官方函数名是 update_user；历史代码误用了一个并不存在的函数名，
        # 于是 ImportError 被 except 吞掉、账号从未被建出来
        update_user = getattr(um, 'update_user', None)

        user = User.query.filter(
            (User.username == MATCH) | (User.email == MATCH)).first()
        admin = Role.query.filter_by(name='Administrator').first()
        role_id = admin.id if admin else 1

        if user is None:
            if create_user is None:
                out('PGA_ERR:', 'user_management.create_user 不可用')
                return 2
            data = {{
                'email': EMAIL,
                'username': EMAIL,
                'newPassword': PASSWORD,
                'confirmPassword': PASSWORD,
                'role': role_id,
                'active': True,
                'auth_source': 'internal',
            }}
            status, msg = create_user(data)
            db.session.commit()
            if not status:
                out('PGA_ERR:', 'create_user: ' + str(msg))
                return 2
        else:
            # 内部账号不允许通过 data 改 email/username（update_user 会直接拒绝），
            # 先直接改 ORM 对象，再走官方 update_user 处理口令与角色
            user.username = EMAIL
            user.email = EMAIL
            user.active = True
            user.locked = False
            user.login_attempts = 0
            user.auth_source = 'internal'
            db.session.commit()
            if update_user is not None:
                data = {{
                    'newPassword': PASSWORD,
                    'confirmPassword': PASSWORD,
                    'role': role_id,
                    'active': True,
                    'locked': False,
                }}
                status, msg = update_user(user.id, data)
                db.session.commit()
                if not status:
                    out('PGA_ERR:', 'update_user: ' + str(msg))
                    return 2

        # 回读校验：不信任写入返回值
        db.session.expire_all()
        user = User.query.filter(
            (User.username == EMAIL) | (User.email == EMAIL)).first()
        if user is None:
            out('PGA_ERR:', '写入后仍查不到该账号')
            return 3

        bad = []
        if user.username != EMAIL:
            bad.append('username')
        if user.email != EMAIL:
            bad.append('email')
        if not user.active:
            bad.append('active')
        if user.locked:
            bad.append('locked')
        if user.login_attempts:
            bad.append('login_attempts')
        if user.auth_source != 'internal':
            bad.append('auth_source')
        if bad:
            out('PGA_ERR:', '账号状态异常: ' + ','.join(bad))
            return 4

    out('PGA_OK')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        out('PGA_EXC:', traceback.format_exc().replace('\\n', ' | ')[-600:])
        sys.exit(5)
'''


def buildProvisionScript(pgadmin_dir):
    """生成账号同步脚本源码（独立函数，便于用例直接 compile() 校验语法）。"""
    return PROVISION_TEMPLATE.format(pgadmin_dir=pgadmin_dir)


def writeProvisionScript(pgadmin_dir):
    """把账号同步脚本写到运行时目录（不进仓库），返回脚本路径。"""
    script_path = getProvisionScriptPath()
    if not yf.writeFile(script_path, buildProvisionScript(pgadmin_dir)):
        return ''
    return script_path


def parseProvisionResult(stdout, stderr=''):
    """解析账号同步脚本输出 -> (是否成功, 失败原因, 脚本实际使用的库路径)。"""
    stdout = stdout or ''
    stderr = stderr or ''
    db_used = ''
    reason = ''
    ok = False
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('PGA_DB:'):
            db_used = line[len('PGA_DB:'):].strip()
        elif line == 'PGA_OK':
            ok = True
        elif line.startswith('PGA_ERR:'):
            reason = line[len('PGA_ERR:'):].strip()
        elif line.startswith('PGA_EXC:'):
            reason = line[len('PGA_EXC:'):].strip()
    if not ok and not reason:
        tail = (stderr.strip().splitlines() or ['无任何输出'])
        reason = tail[-1][:200]
    return ok, reason, db_used


def syncPgAdminPassword(email, password, match_email=None, force=True):
    """创建/更新 pgAdmin 内部账号，并回读校验。

    :param match_email: 改名场景下用于定位旧账号的邮箱，默认与 email 相同
    :return: (bool, str)
    """
    if not email or not password:
        return False, '用户名或密码为空'

    pgadmin_dir = getPgAdminDir()
    py_bin = getPgAdminPython()
    if not pgadmin_dir or not os.path.exists(os.path.join(pgadmin_dir, 'config.py')):
        return False, '未找到 pgadmin4 安装目录'
    if not os.path.exists(py_bin):
        return False, '未找到 pgAdmin 运行环境: ' + py_bin

    script_path = writeProvisionScript(pgadmin_dir)
    if not script_path:
        return False, '无法写入账号同步脚本'

    out, err = yf.safeExecShell(
        [py_bin, script_path, email, password, match_email or '', '1' if force else '0'],
        cwd=pgadmin_dir, timeout=180)
    ok, reason, db_used = parseProvisionResult(out, err)

    if ok and db_used:
        expect = getPgAdminDbPath()
        try:
            same = os.path.realpath(db_used) == os.path.realpath(expect)
        except Exception:
            same = (db_used == expect)
        if not same:
            # 插件与 pgAdmin 认的不是同一个库 —— 必须报错，否则又会回到
            # “面板显示一套凭据、数据库里是另一套”的老问题
            return False, '数据库路径不一致(插件={0}, pgAdmin={1})'.format(expect, db_used)

    if ok:
        return True, '账号同步成功'
    return False, reason or '未知错误'


def readPgUserState(db_path=None):
    """只读读取 pgadmin4.db 的账号状态。

    连接在返回前一定关闭：旧实现在 sqlite 连接还没关的时候，
    又拉起一个要写同一个库的子进程，会撞 database is locked，
    而异常被 except 吞掉 —— 同步静默失败。
    """
    db_path = db_path or getPgAdminDbPath()
    state = {'db_path': db_path, 'db_exists': os.path.exists(db_path), 'users': [], 'cols': []}
    if not state['db_exists']:
        return state

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        if not cur.fetchone():
            state['error'] = 'user 表不存在'
            return state
        cur.execute("PRAGMA table_info(user)")
        cols = [row[1] for row in cur.fetchall()]
        state['cols'] = cols
        fields = [c for c in ('id', 'email', 'username', 'active', 'locked',
                              'login_attempts', 'auth_source') if c in cols]
        if 'email' not in fields or 'username' not in fields:
            state['error'] = 'user 表字段异常'
            return state
        cur.execute("SELECT " + ", ".join(fields) + " FROM user")
        state['users'] = [dict(zip(fields, row)) for row in cur.fetchall()]
    except Exception as e:
        state['error'] = str(e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return state


def isAccountHealthy(user):
    """账号是否已可用：存在、启用、未锁定、无失败计数、内部认证源。"""
    if not user:
        return False
    return (bool(user.get('active'))
            and not bool(user.get('locked'))
            and not (user.get('login_attempts') or 0)
            and user.get('auth_source') == 'internal')


# ---------------------------------------------------------------------------
# 口令校验（快速路径：不拉起 pgAdmin 应用）
# ---------------------------------------------------------------------------
# 「账号健康」≠「面板显示的口令能登录」。
# isAccountHealthy() 只看 active / locked / login_attempts / auth_source，
# 而 user.password 里的哈希可能来自上一轮随机口令 —— 只要 cfg.json 的口令被
# 重新生成过一次（例如库路径修正之前每次重启都换一套），库里就还是旧哈希。
# 此时账号状态一切正常，但登录一定失败：
#   InternalAuthentication.validate() 里 form.validate_on_submit() 判假
#   → POST /authenticate/login 302 → /login，表现就是「弹回登录页」。
# 更坑的是账号不存在时 _login() 会整块跳过 `if user:`，
# 于是 active / locked / login_attempts 看上去全部正常。
# ⇒ 「账号状态健康」不能作为「能登录」的判据，必须真的把口令验一遍。
#
# 优先使用 pgAdmin 环境内 Flask-Security verify_password 校验（结合 salt 与 normalize）；
# 异常时自动降级到 passlib 直读，保证亚秒级且百分之百准确。
VERIFY_TEMPLATE = '''# -*- coding: utf-8 -*-
"""pgAdmin 口令校验（由 plugins/pgadmin/index.py 生成，请勿手工修改）。

用法: <pgadmin venv>/bin/python pg_password_check.py <email> <password>
输出: PGA_VERIFY_OK / PGA_VERIFY_BAD / PGA_VERIFY_UNKNOWN:<原因> / PGA_VERIFY_ERR:<原因>
退出码: 0=一致 1=不一致 3=配置库不存在 4=账号不存在 6=无法判定
"""
import os
import sqlite3
import sys

DB_PATH = {db_path!r}
PGADMIN_DIR = {pgadmin_dir!r}
EMAIL = sys.argv[1]
PASSWORD = sys.argv[2]

HASHERS = {{}}


def out(tag, msg=''):
    sys.stdout.write('%s%s\\n' % (tag, msg))
    sys.stdout.flush()


def main():
    if not os.path.exists(DB_PATH):
        out('PGA_VERIFY_ERR:', '配置库不存在')
        return 3

    # 优先使用 pgAdmin 原生应用环境和 Flask-Security verify_password 校验
    # Flask-Security 加盐处理了哈希，只有该接口能 100% 准确判别
    if PGADMIN_DIR and os.path.exists(PGADMIN_DIR):
        try:
            sys.path.insert(0, PGADMIN_DIR)
            os.chdir(PGADMIN_DIR)
            import config
            from pgadmin import create_app
            from pgadmin.model import User
            from flask_security.utils import verify_password
            app = create_app(config.APP_NAME + '-cli')
            with app.app_context():
                user = User.query.filter(
                    (User.username == EMAIL) | (User.email == EMAIL)).first()
                if not user:
                    out('PGA_VERIFY_ERR:', '账号不存在')
                    return 4
                ok = bool(verify_password(PASSWORD, user.password))
                out('PGA_VERIFY_OK' if ok else 'PGA_VERIFY_BAD')
                return 0 if ok else 1
        except Exception:
            pass

    conn = None
    row = None
    try:
        # 只读打开，避免与正在运行的 pgAdmin 抢写锁
        conn = sqlite3.connect('file:%s?mode=ro' % DB_PATH, uri=True)
        cur = conn.cursor()
        cur.execute(
            'SELECT password FROM "user" WHERE username = ? OR email = ? '
            'LIMIT 1', (EMAIL, EMAIL))
        row = cur.fetchone()
    except Exception as e:
        out('PGA_VERIFY_UNKNOWN:', '读取账号失败: %s' % e)
        return 6
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not row or not row[0]:
        out('PGA_VERIFY_ERR:', '账号不存在')
        return 4

    hashed = row[0]
    try:
        from passlib.hash import pbkdf2_sha256, pbkdf2_sha512
        HASHERS['pbkdf2-sha256'] = pbkdf2_sha256
        HASHERS['pbkdf2-sha512'] = pbkdf2_sha512
    except Exception as e:
        out('PGA_VERIFY_UNKNOWN:', 'passlib 不可用: %s' % e)
        return 6

    parts = hashed.split('$')
    algo = parts[1] if len(parts) > 2 else ''
    hasher = HASHERS.get(algo)
    if hasher is None:
        out('PGA_VERIFY_UNKNOWN:', '未支持的哈希算法: %s' % algo)
        return 6

    try:
        ok = bool(hasher.verify(PASSWORD, hashed))
    except Exception as e:
        out('PGA_VERIFY_UNKNOWN:', '校验异常: %s' % e)
        return 6

    out('PGA_VERIFY_OK' if ok else 'PGA_VERIFY_BAD')
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        out('PGA_VERIFY_UNKNOWN:',
            traceback.format_exc().replace('\\n', ' | ')[-400:])
        sys.exit(6)
'''


def buildVerifyScript(db_path, pgadmin_dir=None):
    """生成口令校验脚本源码（独立函数，便于用例直接 compile() 校验语法）。"""
    if pgadmin_dir is None:
        try:
            pgadmin_dir = getPgAdminDir()
        except Exception:
            pgadmin_dir = ''
    return VERIFY_TEMPLATE.format(db_path=db_path, pgadmin_dir=pgadmin_dir)


def getVerifyScriptPath():
    return getServerDir() + '/pg_password_check.py'


def runVerifyPassword(email, password):
    """校验 cfg.json 里的口令是否就是配置库中哈希对应的口令。

    :return: (True 一致 / False 不一致 / None 无法判定, 原因)
    """
    if not email or not password:
        return None, '未配置 pgAdmin 登录账号'

    py_bin = getPgAdminPython()
    if not os.path.exists(py_bin):
        return None, '未找到 pgAdmin 运行环境: ' + py_bin

    script_path = getVerifyScriptPath()
    if not yf.writeFile(script_path, buildVerifyScript(getPgAdminDbPath(), getPgAdminDir())):
        return None, '无法写入口令校验脚本'

    out, err = yf.safeExecShell([py_bin, script_path, email, password],
                                cwd=getServerDir(), timeout=60)
    reason = ''
    for line in (out or '').splitlines():
        line = line.strip()
        if line == 'PGA_VERIFY_OK':
            return True, ''
        if line == 'PGA_VERIFY_BAD':
            return False, '口令与配置库不一致'
        if line.startswith('PGA_VERIFY_UNKNOWN:'):
            reason = line[len('PGA_VERIFY_UNKNOWN:'):].strip()
        elif line.startswith('PGA_VERIFY_ERR:'):
            reason = line[len('PGA_VERIFY_ERR:'):].strip()
    if not reason:
        tail = (err or '').strip().splitlines()
        reason = tail[-1][:200] if tail else '口令校验脚本无输出'
    return None, reason


def patchPgAdminModelFile(file_path):
    """就地修复 pgAdmin model 中 is_locked 语义倒置的官方 Bug (CVE-2026-7820)。

    官方在 9.15/9.17 中误以为 Flask-Security 的 is_locked 语义是 True 代表未锁定，
    写成了：
        if self.locked:
            ...
            return False
        return True
    这导致任何正常用户在登录时都被误判为已锁定，且无报错直接弹回登录页。
    本函数检测并纠正为正确的 Flask-Security 契约（锁定返回 True，未锁返回 False）。
    """
    if not file_path or not os.path.exists(file_path):
        return True, '文件不存在，跳过'

    content = yf.readFile(file_path)
    if not content:
        return False, '读取文件为空'

    if 'def is_locked(self' not in content:
        return True, '未定义 is_locked，无需修复'

    # 匹配倒置的模式：if self.locked 块内 return False，外层 return True
    pattern = re.compile(
        r'(def\s+is_locked\s*\(\s*self\s*,\s*form_error\s*=\s*None\s*\)\s*:.*?'
        r'if\s+self\.locked\s*:.*?)'
        r'return\s+False(\s*\n\s*)return\s+True',
        re.DOTALL
    )

    if not pattern.search(content):
        return True, '已是正确逻辑或无需修复'

    new_content = pattern.sub(r'\1return True\2return False', content)
    if new_content == content:
        return True, '内容未变更'

    if not yf.writeFile(file_path, new_content):
        return False, '写入补丁失败'
    return True, '成功修复 is_locked 倒置缺陷'


def patchPgAdminModel():
    """查找并自愈当前环境中的 pgadmin/model/__init__.py。"""
    pgadmin_dir = getPgAdminDir()
    if not pgadmin_dir:
        return True
    model_init = os.path.join(pgadmin_dir, 'pgadmin', 'model', '__init__.py')
    ok, _ = patchPgAdminModelFile(model_init)
    return ok


# 最近一次账号同步 / 口令校验的结果。
#
# 必须落盘：面板是通过 plugin.run() 以
# `[sys.executable, <plugin>/index.py, <func>]` **另起进程**调用插件函数的，
# 模块级变量在两次调用之间并不存在 —— 只存内存的话，
# 「检测账号」里显示的原因永远是空的（旧实现的 _LAST_ACCOUNT 就是这样失效的）。
_LAST_ACCOUNT = {}


def getAccountStatePath():
    return getServerDir() + '/account_state.json'


def saveAccountState(state):
    try:
        return bool(yf.writeFile(getAccountStatePath(),
                                 json.dumps(state, ensure_ascii=False)))
    except Exception:
        return False


def loadAccountState():
    try:
        raw = yf.readFile(getAccountStatePath())
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def unlockPgAdminUsers(force=False):
    """确保 pgAdmin 内部账号存在、可用，且**面板显示的口令真的能登录**。

    短路是有意为之：账号同步要拉起一个完整的 pgAdmin 应用上下文（数秒级），
    而本函数在每次 start / restart / reload 都会被调用。
    但短路条件必须包含**口令校验** —— 只看 active / locked / login_attempts /
    auth_source 是不够的（见上方 VERIFY_TEMPLATE 的说明）。
    """
    global _LAST_ACCOUNT
    try:
        os.makedirs(getSessionDir(), exist_ok=True)
    except Exception:
        pass

    cfg = getCfg()
    email = cfg.get('web_pg_username', '')
    password = cfg.get('web_pg_password', '')

    state = readPgUserState()
    if not state.get('db_exists'):
        _LAST_ACCOUNT = {'status': False, 'skipped': False,
                         'reason': '数据库尚未初始化: ' + state.get('db_path', '')}
        saveAccountState(_LAST_ACCOUNT)
        return _LAST_ACCOUNT

    if not email or not password:
        _LAST_ACCOUNT = {'status': False, 'skipped': False,
                         'reason': '未配置 pgAdmin 登录账号'}
        saveAccountState(_LAST_ACCOUNT)
        return _LAST_ACCOUNT

    matched = [u for u in state.get('users', [])
               if u.get('username') == email or u.get('email') == email]
    if (not force and matched and isAccountHealthy(matched[0])
            and matched[0].get('username') == email):
        verified, why = runVerifyPassword(email, password)
        if verified is True:
            _LAST_ACCOUNT = {'status': True, 'skipped': True, 'password_ok': True,
                             'reason': '账号与登录口令均已校验通过'}
            saveAccountState(_LAST_ACCOUNT)
            return _LAST_ACCOUNT
        # verified 为 False：库里是旧口令，必须重新同步。
        # verified 为 None：无法判定，宁可贵一点也要保证能登录。

    ok, msg = syncPgAdminPassword(email, password, match_email=email, force=True)
    reason = msg
    verified = False
    if ok:
        # 同步返回成功不等于口令就对了，回验一遍才敢在面板上显示
        verified, why = runVerifyPassword(email, password)
        if verified is False:
            ok, reason = False, '同步后口令仍与配置库不一致'
        elif verified is None:
            reason = '账号已同步，但口令校验不可用(' + str(why) + ')'
    _LAST_ACCOUNT = {'status': bool(ok), 'skipped': False,
                     'password_ok': verified is True, 'reason': reason}
    saveAccountState(_LAST_ACCOUNT)
    return _LAST_ACCOUNT


# ---------------------------------------------------------------------------
# 登录链路诊断
#
# pgAdmin 9.x 的 _login() 只有三条路径会 redirect() 回登录页
# （nginx 日志表现：POST /authenticate/login -> 302 -> GET /login）：
#   ① auth_obj.validate() 为假 —— 先 validate_email(邮箱)，再
#      form.validate_on_submit()（flask-security 的表单校验：CSRF + 凭据校验，
#      口令不匹配就在这里被判假。之所以能确定凭据校验在表单里：
#      authenticate() 写的是 getattr(form, 'user', <兜底按用户名查询>)，
#      若表单不设置 form.user，任何存在的账号都能免密登录）；
#   ② auth_obj.login() 为假 —— login_user() 返回假，即 user.is_active 为假；
#   ③ 账号被锁定（login_attempts >= MAX_LOGIN_ATTEMPTS > 0）。
# 关键坑：②③ 都要先命中 `if user:`（账号必须存在于配置库）。账号**不存在**时
# 整块被跳过，于是 active / locked / login_attempts 看上去全部正常，
# 却仍然 302 —— 所以「账号状态健康」不能当作「能登录」的证据。
# 另外：**口令错同样走 302**（凭据校验在 form.validate_on_submit() 内），
# 因此不能凭 nginx 日志里的 302/200 反推原因，必须以真实回放为准。
# ---------------------------------------------------------------------------

DIAG_TEMPLATE = '''# -*- coding: utf-8 -*-
"""pgAdmin 登录链路诊断（由 plugins/pgadmin/index.py 生成，请勿手工修改）。

在真实 app 上下文里把 _login() 的三条失败分支分别跑一遍，
最后输出一行 PGADIAG:<json>。
"""
import json
import os
import re
import sys
import traceback

PGADMIN_DIR = {pgadmin_dir!r}
EMAIL = {email!r}
PASSWORD = {password!r}

R = {{'email': EMAIL}}

# 登录失败时页面上会出现的告警文案，用来判断命中 _login() 的哪条分支
MESSAGES = [
    'Incorrect username or password.',
    'Email/Username is not valid',
    'Email/Username not provided',
    'Password not provided',
    'Login failed',
    'account is locked',
    'more attempt',
    'CSRF',
    'refresh the page',
]


def main():
    sys.path.insert(0, PGADMIN_DIR)
    os.chdir(PGADMIN_DIR)

    import config
    for k in ('APP_VERSION', 'SQLITE_PATH', 'SESSION_DB_PATH', 'LOG_FILE',
              'MAX_LOGIN_ATTEMPTS', 'LOGIN_ATTEMPT_FIELDS',
              'ENHANCED_COOKIE_PROTECTION', 'AUTHENTICATION_SOURCES',
              'SESSION_COOKIE_NAME', 'SESSION_COOKIE_SECURE',
              'SESSION_COOKIE_SAMESITE', 'SESSION_COOKIE_DOMAIN',
              'CHECK_EMAIL_DELIVERABILITY', 'ALLOW_SPECIAL_EMAIL_DOMAINS',
              'GLOBALLY_DELIVERABLE', 'WTF_CSRF_ENABLED', 'SERVER_MODE',
              'PROXY_X_FOR_COUNT', 'PROXY_X_HOST_COUNT', 'PROXY_X_PROTO_COUNT',
              'PROXY_X_PORT_COUNT', 'PROXY_X_PREFIX_COUNT'):
        R['cfg.' + k] = repr(getattr(config, k, '<未定义>'))

    R['db_exists'] = os.path.exists(config.SQLITE_PATH)
    R['session_dir_exists'] = os.path.isdir(config.SESSION_DB_PATH)
    R['session_dir_writable'] = os.access(config.SESSION_DB_PATH, os.W_OK)

    # 分支 ① 的第一道闸：邮箱合法性（pgAdmin 自己的实现）
    from pgadmin.utils.validation_utils import validate_email
    R['validate_email'] = validate_email(EMAIL)

    # 快速口令校验：直接用 passlib 比对库里的哈希，不依赖 app 上下文。
    # 这是判断「面板显示的口令到底对不对」最直接的一条证据。
    try:
        import sqlite3
        from passlib.hash import pbkdf2_sha256, pbkdf2_sha512
        hashers = {{'pbkdf2-sha256': pbkdf2_sha256,
                    'pbkdf2-sha512': pbkdf2_sha512}}
        conn = sqlite3.connect('file:%s?mode=ro' % config.SQLITE_PATH, uri=True)
        try:
            row = conn.execute(
                'SELECT password FROM "user" WHERE username = ? OR email = ? '
                'LIMIT 1', (EMAIL, EMAIL)).fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            R['passlib_verify'] = 'NO_SUCH_USER'
        else:
            parts = row[0].split('$')
            algo = parts[1] if len(parts) > 2 else ''
            R['password_hash_algo'] = algo
            hasher = hashers.get(algo)
            R['passlib_verify'] = (bool(hasher.verify(PASSWORD, row[0]))
                                   if hasher else 'UNSUPPORTED:' + algo)
    except Exception as e:
        R['passlib_verify'] = 'EXC %s: %s' % (type(e).__name__, e)

    from pgadmin import create_app
    from pgadmin.model import db, User

    app = create_app(config.APP_NAME + '-diag')
    with app.test_request_context():
        R['users'] = [{{
            'id': u.id, 'username': u.username, 'email': u.email,
            'active': bool(u.active), 'is_active': bool(u.is_active),
            'locked': bool(u.locked), 'login_attempts': u.login_attempts,
            'auth_source': u.auth_source,
            'pw_prefix': (u.password or '')[:24],
        }} for u in User.query.all()]

        # 与 _login() 里完全一致的查法
        u = User.query.filter_by(username=EMAIL, auth_source='internal').first()
        R['lookup_internal'] = u is not None
        R['lookup_any_username'] = User.query.filter_by(
            username=EMAIL).first() is not None
        if u is not None and PASSWORD:
            try:
                R['verify_password'] = bool(u.verify_password(PASSWORD))
            except Exception as e:
                R['verify_password_error'] = '%s: %s' % (type(e).__name__, e)

    # ------------------------------------------------------------------
    # 真实登录回放：test_client + cookie jar，等价于浏览器走一遍
    #   GET /login（拿 CSRF token 与 pga4_session cookie）
    #   → POST /authenticate/login → 跟随 302 → 看最终落地页与告警文案
    # 这一步直接回答「是服务端坏了，还是浏览器/网关把 Cookie 弄丢了」：
    #   回放能登进去 ⇒ 服务端配置没问题，问题在浏览器或 Nginx 反代；
    #   回放也登不进 ⇒ 服务端就是坏的，看 messages / post_location 定位分支。
    # ------------------------------------------------------------------
    def _replay(label, disable_csrf=False):
        if disable_csrf:
            app.config['WTF_CSRF_ENABLED'] = False
            app.config['WTF_CSRF_CHECK_DEFAULT'] = False
        c = app.test_client()
        g = c.get('/login')
        R[label + '_get_status'] = g.status_code
        html = g.get_data(as_text=True)
        m = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', html)
        token = m.group(1) if m else ''
        R[label + '_has_csrf_input'] = bool(token)
        try:
            with c.session_transaction() as sess:
                R[label + '_session_keys'] = sorted(list(sess.keys()))
        except Exception as e:
            R[label + '_session_exc'] = '%s: %s' % (type(e).__name__, e)

        body = {{'email': EMAIL, 'password': PASSWORD, 'internal_button': '1'}}
        if token and not disable_csrf:
            body['csrf_token'] = token
        p = c.post('/authenticate/login', data=body, follow_redirects=False)
        R[label + '_post_status'] = p.status_code
        loc = p.headers.get('Location', '')
        R[label + '_post_location'] = loc
        R[label + '_login_ok'] = bool(loc) and '/login' not in loc
        if loc:
            f = c.get(loc)
            page = f.get_data(as_text=True)
            R[label + '_final_status'] = f.status_code
            R[label + '_messages'] = [x for x in MESSAGES if x in page]
            R[label + '_alerts'] = [
                re.sub(r'<[^>]+>', '', a).strip()[:160]
                for a in re.findall(r'class="alert[^"]*"[^>]*>(.*?)</div>',
                                    page, re.S)][:6]

    try:
        _replay('replay')
    except Exception as e:
        R['replay_exc'] = '%s: %s' % (type(e).__name__, e)

    # 对照组：关掉 CSRF 再跑一次。
    # 两次结果不同 ⇒ 卡在 CSRF（会话没保住 token）；两次都失败 ⇒ 与 CSRF 无关。
    try:
        _replay('nocsrf', disable_csrf=True)
    except Exception as e:
        R['nocsrf_exc'] = '%s: %s' % (type(e).__name__, e)
    R['csrf_is_the_gate'] = (R.get('nocsrf_login_ok') is True
                             and R.get('replay_login_ok') is not True)

    # 分支 ①：合成一次登录 POST，把 validate() 拆开看
    # （关掉 CSRF，避免合成请求没有 token 造成假阳性；真实浏览器由会话带 token）
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    try:
        from flask_security.views import _security
        FormCls = _security.forms.get('login_form').cls
    except Exception:
        from flask_security.forms import LoginForm as FormCls

    from pgadmin.authenticate.internal import InternalAuthentication
    src = InternalAuthentication()
    with app.test_request_context(
            method='POST',
            data={{'email': EMAIL, 'password': PASSWORD,
                  'internal_button': '1'}}):
        form = FormCls()
        R['form_email'] = repr(form.data.get('email'))
        R['form_validate'] = form.validate()
        R['form_errors'] = {{k: [str(x) for x in v]
                            for k, v in form.errors.items()}}
        for name, fn in (('src_validate', src.validate),
                         ('src_authenticate', src.authenticate),
                         ('src_login', src.login)):
            try:
                R[name] = [str(x) for x in fn(form)]
            except Exception as e:
                R[name] = 'EXC %s: %s' % (type(e).__name__, e)

    R['ok'] = True
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        R['exc'] = traceback.format_exc()[-1800:]
        sys.exit(1)
    finally:
        sys.stdout.write('PGADIAG:' + json.dumps(R, ensure_ascii=False) + '\\n')
        sys.stdout.flush()
'''


def buildDiagScript(pgadmin_dir, email, password):
    """生成登录诊断脚本源码（独立函数，便于用例直接 compile() 校验语法）。"""
    return DIAG_TEMPLATE.format(pgadmin_dir=pgadmin_dir, email=email,
                                password=password)


def getDiagScriptPath():
    return getServerDir() + '/pg_login_diag.py'


def runDiagLogin():
    """跑一次登录链路诊断，返回 (是否拿到结果, 数据或原因)。"""
    cfg = getCfg()
    email = cfg.get('web_pg_username', '')
    password = cfg.get('web_pg_password', '')
    pgadmin_dir = getPgAdminDir()
    py_bin = getPgAdminPython()
    if not pgadmin_dir:
        return False, '未找到 pgadmin4 安装目录'
    if not os.path.exists(py_bin):
        return False, '未找到 pgAdmin 运行环境: ' + py_bin

    script_path = getDiagScriptPath()
    if not yf.writeFile(script_path, buildDiagScript(pgadmin_dir, email, password)):
        return False, '无法写入诊断脚本'

    out, err = yf.safeExecShell([py_bin, script_path], cwd=pgadmin_dir,
                                timeout=300)
    for line in (out or '').splitlines():
        line = line.strip()
        if line.startswith('PGADIAG:'):
            try:
                return True, json.loads(line[len('PGADIAG:'):])
            except Exception as e:
                return False, '诊断输出无法解析: ' + str(e)
    tail = (err or out or '').strip().splitlines()
    return False, (tail[-1][:300] if tail else '诊断脚本无输出')


def getPgAccountInfo():
    """账号诊断：一条命令看清「插件认为的库 / pgAdmin 实际用的库 / 账号是否可用」。"""
    cfg = getCfg()
    email = cfg.get('web_pg_username', '')
    state = readPgUserState()
    users = []
    for u in state.get('users', []):
        users.append({
            'id': u.get('id'),
            'email': u.get('email'),
            'username': u.get('username'),
            'active': bool(u.get('active')),
            'locked': bool(u.get('locked')),
            'login_attempts': u.get('login_attempts'),
            'auth_source': u.get('auth_source'),
            'matches_config': (u.get('username') == email or u.get('email') == email),
        })
    pgadmin_dir = getPgAdminDir()
    structural_ok = any(u['matches_config'] and u['active'] and not u['locked']
                        and not u['login_attempts'] and u['auth_source'] == 'internal'
                        for u in users)
    # 口令校验要另起一个子进程（亚秒级）。只在用户主动点「检测账号」时做；
    # 服务页首次加载读的是落盘的 account_state.json，不会因此变慢。
    password_ok, password_reason = runVerifyPassword(email,
                                                     cfg.get('web_pg_password', ''))
    last = loadAccountState()
    reason = last.get('reason', '')
    if not structural_ok:
        reason = reason or '账号不存在或状态异常'
    elif password_ok is False:
        reason = password_reason or '口令与配置库不一致'
    elif password_ok is None:
        reason = reason or password_reason
    data = {
        'server_dir': getServerDir(),
        'data_dir': getDataDir(),
        'db_path': getPgAdminDbPath(),
        'db_exists': bool(state.get('db_exists')),
        'db_error': state.get('error', ''),
        'users': users,
        'config_email': email,
        'config_password_set': bool(cfg.get('web_pg_password', '')),
        'pgadmin_dir': pgadmin_dir,
        'python': getPgAdminPython(),
        'config_local_installed': bool(pgadmin_dir) and os.path.exists(
            os.path.join(pgadmin_dir, 'config_local.py')),
        'account_ok': structural_ok,
        'password_ok': password_ok,
        'password_reason': password_reason,
        # 只有「账号结构正常」且「口令确实对得上」才敢说能登录
        'login_ok': bool(structural_ok and password_ok is True),
        'last_sync': last,
        'account_reason': reason,
        'diag_hint': '账号看起来正常却仍登不上时，跑 diag_login 回放一次真实登录',
    }
    return yf.returnJson(True, 'ok', data)


def diagLogin():
    """登录链路诊断入口（慢：会拉起完整 pgAdmin 应用上下文）。"""
    ok, data = runDiagLogin()
    if not ok:
        return yf.returnJson(False, '诊断失败: ' + str(data))
    return yf.returnJson(True, 'ok', data)


def fixLogin():
    """一键修复登录：强制把 cfg.json 里的账号与口令写进配置库，并回读校验。

    与 start/restart 里的自动修复是同一套逻辑，区别只是 force=True ——
    不做任何「看起来健康」的短路判断，用户点一下就应该能登进去。
    """
    patchPgAdminModel()
    state = unlockPgAdminUsers(force=True)
    cfg = getCfg()
    email = cfg.get('web_pg_username', '')
    password_ok, password_reason = runVerifyPassword(
        email, cfg.get('web_pg_password', ''))
    data = {
        'synced': bool(state.get('status')),
        'password_ok': password_ok,
        'password_reason': password_reason,
        'reason': state.get('reason', '') or password_reason,
        'db_path': getPgAdminDbPath(),
        'email': email,
    }
    return yf.returnJson(True, 'ok', data)


def initPgConfFile():
    """把 config_local.py 装到 pgadmin4 包目录，并保证与模板同步。

    旧实现只在「4 个键缺失」时才刷新，模板升级（例如新增 Session / 反代配置）
    永远不会生效，线上会一直跑着旧配置。
    改为模板版本号比对：模板一变就刷新。
    """
    pgadmin_dir = getPgAdminDir()
    if not pgadmin_dir:
        return False

    file_tpl = getPluginDir() + '/conf/config_local.py'
    dst_file = pgadmin_dir + '/config_local.py'
    marker = 'PGADMIN_LOCAL_TPL_VERSION = %d' % LOCAL_TPL_VERSION

    if os.path.exists(dst_file):
        content = yf.readFile(dst_file) or ''
        if marker in content:
            return True

    content = yf.readFile(file_tpl)
    if not content:
        return False
    content = content.replace('{$DATA_PATH}', getDataDir())
    return bool(yf.writeFile(dst_file, content))


def ensureBasicAuth():
    """让 cfg.json 里的基础认证账号与 pg.pass 保持一致。

    旧实现只在 pg.pass 不存在时才生成，若 cfg.json 被删或被改，
    面板显示的账号和 Nginx 实际校验的账号就会对不上。
    """
    cfg = getCfg()
    username = cfg.get('username', '')
    password = cfg.get('password', '')
    if username and password:
        content = yf.readFile(getBasicAuthFile())
        if content and content.split(':', 1)[0] == username:
            return True
    else:
        username = yf.getRandomString(8)
        password = yf.getRandomString(10)
        setCfg('username', username)
        setCfg('password', password)

    path = getBasicAuthFile()
    if not yf.writeFile(path, username + ':' + yf.hasPwd(password)):
        return False
    try:
        # 口令文件只允许属主读写
        os.chmod(path, 0o600)
    except Exception:
        pass
    return True


def ensurePgAdminAccount():
    """确保配置库存在，且 cfg.json 里的账号在库中真实可用。

    顺序很关键：先建库（pg_init.sh 只建表/迁移），再同步账号。
    旧代码把凭据生成挂在「库文件是否存在」上，而它检查的路径是错的，
    于是每次 start/restart 都会重新随机一套凭据 —— 这是登录回弹的直接原因。
    """
    if not os.path.exists(getPgAdminDbPath()):
        pg_username = 'yftec_' + yf.getRandomString(8) + '@gmail.com'
        pg_password = yf.getRandomString(10)
        setCfg('web_pg_username', pg_username)
        setCfg('web_pg_password', pg_password)
        pg_init_bash = getPluginDir() + '/pg_init.sh'
        yf.safeExecShell(['bash', pg_init_bash, pg_username, pg_password, yf.getServerDir()],
                         cwd=getPluginDir(), timeout=600)

    # 凭据只生成一次：只要 cfg 里已有值就不再重新生成。
    # 绝不能拿「库文件是否存在」当判据 —— 路径判断一旦有偏差，
    # 每次 start/restart 都会换一套随机凭据，用户抄到的永远是错的。
    cfg = getCfg()
    if not cfg.get('web_pg_username') or not cfg.get('web_pg_password'):
        setCfg('web_pg_username', 'yftec_' + yf.getRandomString(8) + '@gmail.com')
        setCfg('web_pg_password', yf.getRandomString(10))

    return unlockPgAdminUsers()


# 最近一次「建库 + 账号同步」的结果，供 check_pg_account / 服务页 展示。
# 旧实现把 unlockPgAdminUsers() 的返回值直接丢掉 —— 于是账号没建出来也照样
# 往 cfg.json 写凭据、面板上照常显示，用户拿着登不进去的凭据反复试。
_LAST_PROVISION = {}


def initReplace():
    global _LAST_PROVISION
    initPgConfFile()
    patchPgAdminModel()

    file_tpl = getPluginDir() + '/conf/pgadmin.conf'
    file_run = getConf()
    marker = '# PGADMIN_VHOST_TPL_VERSION = %d' % VHOST_TPL_VERSION
    if not os.path.exists(file_run):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(file_run, content)
    else:
        content = yf.readFile(file_run) or ''
        if marker not in content:
            content = yf.readFile(file_tpl)
            content = contentReplace(content)
            yf.writeFile(file_run, content)
            yf.restartWeb()

    ensureBasicAuth()
    _LAST_PROVISION = ensurePgAdminAccount() or {}

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/pgadmin.service'

    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/pgadmin.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$PY_VER}', getPythonName())

        
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')


def pgOp(method, do_init=True):
    if do_init:
        initReplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        return 'ok'

    if current_os.startswith("freebsd"):
        data = yf.execShell('service' + getPluginName() + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method+ ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return data[1]

def status():
    sock = '/tmp/pgadmin4.sock'
    if os.path.exists(sock):
        return 'start'
    return 'stop'


def start():
    initCfg()
    openPort()

    pgOp('start')

    yf.restartWeb()
    return 'ok'


def stop():
    # 停止时不走 initReplace()：那会重新写 vhost、跑建库与账号同步，
    # 对一个「停止」操作来说纯属多余副作用
    pgOp('stop', do_init=False)

    conf = getConf()
    if os.path.exists(conf):
        os.remove(conf)

    delPort()
    yf.restartWeb()
    return 'ok'


def restart():
    cleanNginxLog()
    state = pgOp('restart')
    yf.restartWeb()
    return state


def reload():
    cleanNginxLog()
    return pgOp('reload')

def getPgOption():
    data = getCfg()
    return yf.returnJson(True, 'ok', data)


def getPgPort():
    try:
        port = getPort()
        return yf.returnJson(True, 'OK', port)
    except Exception as e:
        # print(e)
        return yf.returnJson(False, '插件未启动!')


def setPgPort():
    args = getArgs()
    data = checkArgs(args, ['port'])
    if not data[0]:
        return data[1]

    port = str(args['port']).strip()
    # 后端必须自己校验：写进 vhost 的是裸值，
    # 一旦不是合法端口，Nginx 会 reload 失败 → 面板上所有站点一起挂
    if not re.match(r'^\d{1,5}$', port):
        return yf.returnJson(False, '端口范围不合法!')
    if port == '80':
        return yf.returnJson(False, '80端不能使用!')
    if int(port) < 81 or int(port) > 65535:
        return yf.returnJson(False, '端口范围不合法!')

    file = getConf()
    if not os.path.exists(file):
        return yf.returnJson(False, '插件未启动!')
    content = yf.readFile(file)
    rep = r'listen\s*(.*);'
    new_content = re.sub(rep, "listen " + port + ';', content)
    # re.sub 没命中时会原样返回：此时端口并未真正生效，
    # 不能一边报成功一边把端口写进 cfg.json
    if new_content == content:
        return yf.returnJson(False, '修改失败: 未找到 listen 配置!')
    yf.writeFile(file, new_content)

    setCfg("port", port)
    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def setPgUsername():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    username = (args['username'] or '').strip()
    if not username:
        return yf.returnJson(False, '基础认证用户名不能为空!')

    setCfg('username', username)
    if not ensureBasicAuth():
        return yf.returnJson(False, '修改失败!')

    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def setPgPassword():
    args = getArgs()
    data = checkArgs(args, ['password'])
    if not data[0]:
        return data[1]

    password = args['password']
    if not password:
        return yf.returnJson(False, '基础认证密码不能为空!')

    setCfg('password', password)
    if not ensureBasicAuth():
        return yf.returnJson(False, '修改失败!')

    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def setWebPgUsername():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    username = (args['username'] or '').strip()
    if not username:
        return yf.returnJson(False, 'PG登录用户名(邮箱)不能为空!')
    # 用户名即 pgAdmin 的登录邮箱，非法值会让 create_user 直接失败，
    # 账号建不出来却把邮箱写进 cfg.json —— 用户拿到的就是登不进去的账号
    if not isEmail(username):
        return yf.returnJson(False, 'PG登录用户名(邮箱)格式不正确!')

    cfg = getCfg()
    old_email = cfg.get('web_pg_username', '')
    password = cfg.get('web_pg_password', '')
    if not password:
        password = yf.getRandomString(10)
        setCfg('web_pg_password', password)

    setCfg('web_pg_username', username)
    ok, msg = syncPgAdminPassword(username, password, match_email=old_email or username)
    if not ok:
        # 回滚，避免面板显示一个数据库里并不存在的账号
        setCfg('web_pg_username', old_email)
        return yf.returnJson(False, '账号同步失败: ' + msg)
    return yf.returnJson(True, '保存成功!')


def setWebPgPassword():
    args = getArgs()
    data = checkArgs(args, ['password'])
    if not data[0]:
        return data[1]

    password = args['password']
    if not password:
        return yf.returnJson(False, 'PG登录密码不能为空!')

    if len(password) < 6:
        return yf.returnJson(False, 'PG登录密码长度不能少于6位!')

    cfg = getCfg()
    email = cfg.get('web_pg_username', '')
    if not email:
        return yf.returnJson(False, '未找到对应的pgAdmin登录用户名(邮箱)!')

    old_password = cfg.get('web_pg_password', '')
    setCfg('web_pg_password', password)
    ok, msg = syncPgAdminPassword(email, password, match_email=email)
    if not ok:
        # 回滚，避免面板显示一个登不进去的密码
        setCfg('web_pg_password', old_password)
        return yf.returnJson(False, '更新密码失败: ' + msg)
    return yf.returnJson(True, '修改PG登录密码成功!')


def accessLog():
    return getServerDir() + '/access.log'

def errorLog():
    return getServerDir() + '/error.log'


def installVersion():
    return yf.readFile(getServerDir() + '/version.pl')

def getPgAccessInfo():
    try:
        data = {}
        cfg = getCfg()
        port = getPort()
        
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            internal_ip = s.getsockname()[0]
            s.close()
        except:
            internal_ip = '127.0.0.1'
            
        try:
            external_ip = yf.getHostAddr()
        except:
            external_ip = internal_ip
        
        data['internal_url'] = 'http://' + internal_ip + ':' + port + '/'
        data['external_url'] = 'http://' + external_ip + ':' + port + '/'
        data['username'] = cfg.get('username', '')
        data['password'] = cfg.get('password', '')
        data['web_pg_username'] = cfg.get('web_pg_username', '')
        data['web_pg_password'] = cfg.get('web_pg_password', '')
        # 账号是否真的能在 pgAdmin 里登录。
        # 这里刻意不跑口令校验（那要另起一个子进程），只读 start/restart 时
        # 落盘的结果 + 一次廉价的结构性探测，保证服务页秒开。
        data['account_ok'] = False
        data['password_ok'] = None
        data['login_ok'] = False
        last = loadAccountState()
        data['account_reason'] = last.get('reason', '')
        try:
            email = cfg.get('web_pg_username', '')
            state = readPgUserState()
            data['account_ok'] = any(
                (u.get('username') == email or u.get('email') == email)
                and isAccountHealthy(u) for u in state.get('users', []))
            if 'password_ok' in last:
                data['password_ok'] = last.get('password_ok')
            data['login_ok'] = bool(data['account_ok']
                                    and data['password_ok'] is True)
            if not data['account_ok'] and not data['account_reason']:
                data['account_reason'] = '账号不存在或状态异常'
        except Exception as e:
            data['account_reason'] = '账号探测失败: ' + str(e)
        return yf.returnJson(True, 'ok', data)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')

if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print(status())
    elif func == 'start':
        print(start())
    elif func == 'stop':
        print(stop())
    elif func == 'restart':
        print(restart())
    elif func == 'reload':
        print(reload())
    elif func == 'conf':
        print(getConf())
    elif func == 'version':
        print(installVersion())
    elif func == 'get_cfg':
        print(returnCfg())
    elif func == 'get_home_page':
        print(getHomePage())
    elif func == 'get_pg_port':
        print(getPgPort())
    elif func == 'set_pg_port':
        print(setPgPort())
    elif func == 'get_pg_option':
        print(getPgOption())
    elif func == 'set_pg_username':
        print(setPgUsername())
    elif func == 'set_pg_password':
        print(setPgPassword())
    elif func == 'set_web_pg_username':
        print(setWebPgUsername())
    elif func == 'set_web_pg_password':
        print(setWebPgPassword())
    elif func == 'check_pg_account':
        print(getPgAccountInfo())
    elif func == 'diag_login':
        print(diagLogin())
    elif func == 'fix_login':
        print(fixLogin())
    elif func == 'access_log':
        print(accessLog())
    elif func == 'error_log':
        print(errorLog())
    elif func == 'get_pg_access_info':
        print(getPgAccessInfo())
    else:
        print('error')
