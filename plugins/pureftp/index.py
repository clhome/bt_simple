# coding:utf-8

import sys
import io
import os
import re
import json
import time
import shutil

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.pureftp')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


#: FTP 用户名白名单。用户名会作为 argv 交给 pure-pw，并写进面板 ftps 表：
#: 空白 / shell 元字符（`;` `|` `$` 反引号 换行）/ 首字符 `-`（会被 pure-pw 当选项）一律拒绝。
_USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')

#: 面板 ftps 表里口令的加密盐值（只写不读：列表接口不再回传口令）
_PWD_CRYPT_KEY = 'pureftp'

#: `systemctl is-enabled` 的「已启用」状态集合（单元类型/systemd 版本不同词不同）
_UNIT_ENABLED_STATES = ('enabled', 'enabled-runtime', 'alias', 'static', 'indirect', 'generated')


def getPluginName():
    return 'pureftp'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConf():
    path = getServerDir() + "/etc/pure-ftpd.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/pure-ftpd.tpl"
    return path


def getArgs():
    """解析插件入参。

    前端（`web/static/app/plugin_api.js::parseArgs`）与 `utils/plugin.py::run()`
    都把 args 作为**一个** argv 传进来（内容是 JSON 字符串），旧实现只按 `k:v` 切，
    于是整段 JSON 被当成一个键 → add_ftp/del_ftp/mod_ftp/mod_ftp_port/stop_ftp/
    start_ftp 恒回「缺少必要参数」、get_ftp_list 的 page/search 全部失效。
    """
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                _log.debug('[pureftp] getArgs JSON 解析失败: %s', e)
        t = val.strip('{').strip('}')
        if t.strip() != '':
            t = t.split(':', 1)
            if len(t) == 2:
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            if len(t) == 2:
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v

    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def isInstalled():
    """已安装判据 = install.sh 落下的 version.pl。

    不能用「目录存在」：yf.writeFile 会自动建父目录，未安装的机器也会被凭空造出
    /www/server/pureftp 与整套 systemd/init.d/conf 产物（真机实测 HEAD 版 start
    在未安装时造产物、放行防火墙端口，然后才报失败）。
    """
    return os.path.exists(getServerDir() + '/version.pl')


def getPidFile():
    """从 pure-ftpd.conf 读 PIDFile（安装时已展开为绝对路径）。"""
    conf = yf.readFile(getConf())
    if isinstance(conf, str):
        m = re.search(r'(?mi)^\s*PIDFile\s+(\S+)', conf)
        if m:
            return m.group(1)
    return getServerDir() + '/etc/pure-ftpd.pid'


def pidAlive(pid):
    try:
        os.kill(pid, 0)
    except OSError as err:
        import errno
        return err.errno == errno.EPERM
    except Exception:
        return False
    return True


def _isPureFtpdProc(pid):
    """comm == 'pure-ftpd' 且 exe 在插件安装目录内 —— 同名诱饵进程不会被误认。"""
    if not pidAlive(pid):
        return False
    try:
        with open('/proc/%d/comm' % pid, 'r') as fp:
            comm = fp.read().strip()
    except Exception:
        return False
    if comm != 'pure-ftpd':
        return False
    try:
        exe = os.path.realpath('/proc/%d/exe' % pid)
    except Exception:
        return False
    return exe.startswith(os.path.realpath(getServerDir()) + os.sep)


def pureFtpdPids():
    """扫 /proc 找本插件安装目录下的 pure-ftpd 进程（零 fork）。"""
    pids = []
    try:
        names = os.listdir('/proc')
    except Exception as e:
        _log.debug('[pureftp] 读取 /proc 失败: %s', e)
        return pids
    for name in names:
        if not name.isdigit():
            continue
        if _isPureFtpdProc(int(name)):
            pids.append(name)
    return pids


def status():
    # 精确判据：pid 文件 + /proc 双核对，再退回 /proc 全扫。
    # 旧实现 `ps -ef|grep pure-ftpd |grep -v grep | grep -v python | awk '{print $2}'`
    # 靠子串匹配：任何 cmdline 里含 'pure-ftpd' 的进程（含诱饵）都会被误判成 start。
    raw = yf.readFile(getPidFile())
    if isinstance(raw, str) and raw.strip().isdigit():
        if _isPureFtpdProc(int(raw.strip())):
            return 'start'
    if pureFtpdPids():
        return 'start'
    return 'stop'


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    return content


def ftp_release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().addAcceptPort(port, 'pure-ftpd', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def openFtpPort():
    for i in ["21", "39000:40000"]:
        ftp_release_port(i)
    return True


def initDreplace():

    if not isInstalled():
        # 未安装不造任何产物：旧实现会在这里写出 init.d/pureftp、sbin/pure-config.pl、
        # etc/pure-ftpd.conf、/lib/systemd/system/pureftp.service，并放行 21 与
        # 39000:40000 防火墙端口。
        return ''

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
        openFtpPort()
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShellRc(['chmod', '+x', file_bin], shell=False, timeout=15)

    pureSbinConfig = getServerDir() + "/sbin/pure-config.pl"
    if not os.path.exists(pureSbinConfig):
        pureTplConfig = getPluginDir() + "/init.d/pure-config.pl"
        content = yf.readFile(pureTplConfig)
        content = contentReplace(content)
        yf.writeFile(pureSbinConfig, content)
        yf.execShellRc(['chmod', '+x', pureSbinConfig], shell=False, timeout=15)

    pureFtpdConfig = getServerDir() + "/etc/pure-ftpd.conf"
    pureFtpdConfigBak = getServerDir() + "/etc/pure-ftpd.bak.conf"
    pureFtpdConfigTpl = getPluginDir() + "/conf/pure-ftpd.conf"

    if not os.path.exists(pureFtpdConfigBak) or not os.path.exists(pureFtpdConfig):
        if os.path.exists(pureFtpdConfig):
            shutil.copyfile(pureFtpdConfig, pureFtpdConfigBak)
        content = yf.readFile(pureFtpdConfigTpl)
        content = contentReplace(content)
        yf.writeFile(pureFtpdConfig, content)

     # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/pureftp.service'
    systemServiceTpl = getPluginDir() + '/init.d/pureftp.service.tpl'

    if os.path.exists(systemDir):
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, content)
        yf.execShellRc(['systemctl', 'daemon-reload'], shell=False, timeout=30)

    return file_bin


def pfOp(method):
    if not isInstalled():
        # 未安装：不造 unit/init 脚本、不调 systemctl、不动防火墙，如实报失败
        _log.debug('[pureftp] %s 被拒：未安装', method)
        return 'fail'

    file = initDreplace()

    if not yf.isAppleSystem():
        rc, out, err = yf.execShellRc(['systemctl', method, getPluginName()], shell=False, timeout=120)
        if rc != 0:
            # 旧实现只看 stderr 是否为空：systemctl 失败但输出在 stdout 时会被吞成成功
            _log.debug('[pureftp] systemctl %s 失败: %s', method, (err or out).strip())
            return 'fail'
        # 启/停/重启/重载后回读真实进程，杜绝「命令返回 0 但服务没起来」的假成功
        want = 'stop' if method == 'stop' else 'start'
        for _ in range(10):
            if status() == want:
                return 'ok'
            time.sleep(0.5)
        _log.debug('[pureftp] %s 后状态未就绪', method)
        return 'fail'

    data = yf.execShellRc([file, method], shell=False, timeout=120)
    if data[0] == 0:
        return 'ok'
    return (data[2] or data[1]).strip()


def start():
    return pfOp('start')


def stop():
    return pfOp('stop')


def restart():
    return pfOp('restart')


def reload():
    return pfOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    # 旧实现 `systemctl status pureftp | grep loaded | grep "enabled;"` 依赖人类可读输出：
    # SysV 生成的单元显示 `generated`（没有 `enabled;`）→ 已启用被误判 fail（与 C02/D06 同族）。
    rc, out, _err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()], shell=False, timeout=15)
    if rc != 0:
        return 'fail'
    if (out or '').strip() in _UNIT_ENABLED_STATES:
        return 'ok'
    return 'fail'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    # 旧实现无条件回 ok：单元不存在 / systemctl 失败时也报「已开启」
    rc, out, err = yf.execShellRc(['systemctl', 'enable', getPluginName()], shell=False, timeout=30)
    if rc != 0:
        _log.debug('[pureftp] enable 失败: %s', (err or out).strip())
        return 'fail'
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    rc, out, err = yf.execShellRc(['systemctl', 'disable', getPluginName()], shell=False, timeout=30)
    if rc != 0:
        _log.debug('[pureftp] disable 失败: %s', (err or out).strip())
        return 'fail'
    return 'ok'


def pftpDB():
    file = getServerDir() + '/ftps.db'
    if not os.path.exists(file):
        conn = yf.M('ftps').dbPos(getServerDir(), 'ftps')
        csql = yf.readFile(getPluginDir() + '/conf/ftps.sql')
        if not isinstance(csql, str):
            return None
        # 末尾 `;` 切出来的空片段不能丢给 sqlite（旧实现把 '' 也 execute 一次）
        for sql in csql.split(';'):
            if sql.strip() == '':
                continue
            conn.execute(sql, ())
    else:
        conn = yf.M('ftps').dbPos(getServerDir(), 'ftps')
    return conn


def pftpUser():
    if yf.isAppleSystem():
        user = yf.execShell(
            "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return user
    return 'www'


def validUsername(username):
    """FTP 用户名白名单：拒绝空、超长、空白、首字符 `-` 与一切 shell 元字符。"""
    if not isinstance(username, str) or username != username.strip():
        return False
    if username in ('.', '..') or username.startswith('-'):
        return False
    return bool(_USERNAME_RE.match(username))


def validPassword(password):
    """口令校验：非空、≤128 字符、不含控制字符。

    换行必须拒绝：pure-pw 从 stdin 读两次口令确认，口令里带换行会截断输入；
    旧实现用 heredoc 喂口令，口令里出现单独一行 `EOF` 会提前结束 heredoc
    并把后面的行当命令执行。
    """
    if not isinstance(password, str) or password == '' or len(password) > 128:
        return False
    return not any(ord(c) < 32 or ord(c) == 127 for c in password)


def invalidHomePathReason(path):
    """FTP 家目录白名单：必须绝对路径、无 `..`，且落在网站目录之内。

    为什么必须限定根：pftpAdd 会以 root 身份 makedirs 并把目录 chown 给 www，
    旧实现允许任意路径 —— `path=/root/.ssh` 即可让 FTP 用户 www 拿到 root 的
    SSH 目录写权限（提权），`path=/etc` 则把系统配置暴露成 FTP 根。
    """
    if not isinstance(path, str) or path.strip() == '':
        return 'empty'
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        # 内嵌 NUL/换行等控制字符的路径永远不是合法目录（且会让 realpath 抛异常）
        return 'control'
    if not os.path.isabs(path):
        return 'relative'
    if '..' in re.split(r'[\\/]+', path):
        return 'traversal'
    try:
        norm = os.path.normpath(path)
        if norm == os.sep or norm == '/':
            return 'root'
        real = os.path.realpath(norm)
        root = os.path.realpath(yf.getWwwDir())
    except Exception:
        # 非法字符（如内嵌 NUL）会让 realpath 抛异常
        return 'invalid'
    if real == root or real.startswith(root + os.sep):
        return None
    return 'outside'


def purePwRun(argv, stdin_data=None, timeout=60):
    """以参数列表方式调用 pure-pw（绝不拼 shell）。返回 (ok, 消息)。

    为什么必须列表化：旧实现把 username/password/path 直接拼进 shell 字符串，
    `username="a; touch /root/PWNED; #"` 即 root 命令注入（真机已复现）。
    口令只走 stdin：argv 对同机任意用户可见（/proc/<pid>/cmdline）。
    """
    bin_path = getServerDir() + '/bin/pure-pw'
    if not os.path.exists(bin_path):
        return (False, 'pure-pw 不存在，请先安装 Pure-Ftpd')
    cmd = [bin_path] + [str(a) for a in argv]
    if stdin_data is None:
        rc, out, err = yf.execShellRc(cmd, shell=False, timeout=timeout)
        if rc != 0:
            return (False, (err or out or ('pure-pw 退出码 %s' % rc)).strip())
        return (True, (out or '').strip())
    out, err = yf.safeExecShell(cmd, stdin_data=stdin_data, timeout=timeout)
    return (True, (err or out or '').strip())


def purePwShow(username):
    """回读确认：`pure-pw show <user>` 退出码为 0 才算真的写进去了。"""
    rc, out, _err = yf.execShellRc(
        [getServerDir() + '/bin/pure-pw', 'show', username], shell=False, timeout=30)
    if rc != 0:
        return None
    return out or ''


def pftpAdd(username, password, path):
    user = pftpUser()

    if not os.path.exists(path):
        if not yf.makeDirs(path):
            return (False, '创建 FTP 根目录失败: ' + path)
        # 变量路径不得进 shell：用 shutil.chown，顺带消除 macOS/BSD 的 `.` 分隔写法
        try:
            if yf.isAppleSystem():
                shutil.chown(path, user, 'staff')
            else:
                shutil.chown(path, 'www', 'www')
        except Exception as _e:
            yf.writeFileLog('[pureftp] chown 失败：%s -> %r' % (_e, path))
            return (False, '设置 FTP 根目录属主失败（请确认 www 用户存在）: ' + path)

    ok, msg = purePwRun(['useradd', username, '-u', user, '-d', path],
                        stdin_data=password + '\n' + password + '\n')
    if not ok:
        return (False, msg)
    if purePwShow(username) is None:
        return (False, msg or 'pure-pw 未写入该用户')
    return (True, 'ok')


def pftpMod(username, password):
    ok, msg = purePwRun(['passwd', username],
                        stdin_data=password + '\n' + password + '\n')
    if not ok:
        return (False, msg)
    if purePwShow(username) is None:
        return (False, msg or 'pure-pw 未找到该用户')
    return (True, 'ok')


def pftpStop(username):
    return purePwRun(['usermod', username, '-r', '1'])


def pftpStart(username):
    return purePwRun(['usermod', username, '-r', ''])


def pftpReload():
    """重建 pureftpd.pdb。失败不静默：返回 (ok, 消息)。"""
    return purePwRun(['mkdb', getServerDir() + '/etc/pureftpd.pdb'])


def getWwwDir():
    path = yf.getWwwDir()
    return path


def getFtpPort():
    # readFile 失败返回 False（不是空串），旧实现直接交给 re.search → TypeError
    conf = yf.readFile(getConf())
    if not isinstance(conf, str):
        return '21'
    m = re.search(r"\n#?\s*Bind\s+[0-9]+\.[0-9]+\.[0-9]+\.+[0-9]+,([0-9]+)", conf)
    if m is None:
        return '21'
    return m.group(1)


def _pageArgs(args):
    """page/page_size 白名单：旧实现 int(args['page']) 在非数字入参上直接 500。"""
    try:
        page = int(str(args.get('page', 1)).strip())
    except Exception:
        page = 1
    try:
        page_size = int(str(args.get('page_size', 10)).strip())
    except Exception:
        page_size = 10
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 1000:
        page_size = 10
    return page, page_size


def getFtpList():
    args = getArgs()
    page, page_size = _pageArgs(args)
    search = args.get('search', '')
    if not isinstance(search, str):
        search = ''
    search = search.strip()[:64]

    data = {}
    conn = pftpDB()
    if conn is None:
        return yf.returnJson(False, '操作失败:')
    limit = str((page - 1) * page_size) + ',' + str(page_size)
    # 参数化：旧实现 condition = "name like '%" + search + "%'" 直接拼 where，
    # `search=' OR '1'='1` 即注入（可配合 UNION 读出整库）。
    condition = ''
    param = ()
    if search != '':
        condition = 'name like ?'
        param = ('%' + search + '%',)
    # 不再回传 password：明文 FTP 口令不应进入 HTTP 响应与列表界面
    field = 'id,pid,name,path,status,ps,addtime'
    clist = conn.where(condition, param).field(
        field).limit(limit).order('id desc').select()

    count = conn.where(condition, param).count()
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = 'ftpList'
    data['page'] = yf.getPage(_page)

    info = {}
    
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        internal_ip = s.getsockname()[0]
        s.close()
    except Exception as _e:
        _log.debug('[pureftp] getFtpList 异常已忽略: %s', _e)
        internal_ip = '127.0.0.1'
        
    try:
        external_ip = yf.getHostAddr()
    except Exception as _e:
        _log.debug('[pureftp] getFtpList 异常已忽略: %s', _e)
        external_ip = internal_ip

    info['ip'] = internal_ip
    info['external_ip'] = external_ip
    info['port'] = getFtpPort()
    data['info'] = info
    data['data'] = clist

    return yf.getJson(data)


def _rowId(value):
    """id 归一：旧实现 int(args['id']) 在非数字入参上直接 ValueError/500。"""
    try:
        row_id = int(str(value).strip())
    except Exception:
        return None
    if row_id < 1:
        return None
    return row_id


def _reloadPwDb():
    """重建 pdb 并把失败写进调试日志（调用方已各自报错，这里只保证不静默）。"""
    ok, msg = pftpReload()
    if not ok:
        _log.debug('[pureftp] pure-pw mkdb 失败: %s', msg)
    return ok


def addFtp():
    import urllib.parse
    args = getArgs()
    data = checkArgs(args, ['ftp_username', 'ftp_password', 'path', 'ps'])
    if not data[0]:
        return data[1]

    path = urllib.parse.unquote(str(args['path'])).strip()
    user = str(args['ftp_username']).strip()
    pwd = str(args['ftp_password'])
    ps = str(args['ps'])

    if not validUsername(user):
        return yf.returnJson(False, '用户名不合法!')
    reason = invalidHomePathReason(path)
    if reason is not None:
        _log.debug('[pureftp] 拒绝 FTP 根目录 %r: %s', path, reason)
        return yf.returnJson(False, 'FTP 根目录不合法!')
    if not validPassword(pwd):
        return yf.returnJson(False, 'FTP 密码不合法!')
    if len(ps) > 200:
        return yf.returnJson(False, '备注过长!')

    conn = pftpDB()
    if conn is None:
        return yf.returnJson(False, '操作失败:')
    if conn.where('name=?', (user,)).count() > 0:
        return yf.returnJson(False, 'FTP 用户已存在!')

    ok, msg = pftpAdd(user, pwd, path)
    if not ok:
        return yf.returnJson(False, '操作失败: ' + msg)

    addtime = time.strftime('%Y-%m-%d %X', time.localtime())
    # 口令加密落库（旧实现写明文；列表接口也不再回传，界面无从泄漏）
    conn.add('pid,name,password,path,status,ps,addtime',
             (0, user, yf.enDoubleCrypt(_PWD_CRYPT_KEY, pwd), path, 1, ps, addtime))
    _reloadPwDb()
    return 'ok'


def delFtp():
    args = getArgs()
    data = checkArgs(args, ['id', 'username'])
    if not data[0]:
        return data[1]

    username = str(args['username']).strip()
    if not validUsername(username):
        return yf.returnJson(False, '用户名不合法!')
    row_id = _rowId(args['id'])
    if row_id is None:
        return yf.returnJson(False, '参数不合法!')

    # 旧实现不判成败：pure-pw 不存在/报错也删掉面板记录并回 ok（假成功，账号依旧可登录）
    ok, msg = purePwRun(['userdel', username])
    if not ok:
        return yf.returnJson(False, '操作失败: ' + msg)
    _reloadPwDb()
    conn = pftpDB()
    if conn is None:
        return yf.returnJson(False, '操作失败:')
    conn.where("id=?", (row_id,)).delete()
    yf.writeLog('FTP管理', '删除FTP用户[{1}]成功!', (username,))
    return 'ok'


def modFtp():
    args = getArgs()
    data = checkArgs(args, ['id', 'name', 'password'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    pwd = str(args['password'])
    if not validUsername(name):
        return yf.returnJson(False, '用户名不合法!')
    if not validPassword(pwd):
        return yf.returnJson(False, 'FTP 密码不合法!')
    row_id = _rowId(args['id'])
    if row_id is None:
        return yf.returnJson(False, '参数不合法!')

    ok, msg = pftpMod(name, pwd)
    if not ok:
        return yf.returnJson(False, '操作失败: ' + msg)
    _reloadPwDb()

    conn = pftpDB()
    if conn is None:
        return yf.returnJson(False, '操作失败:')
    conn.where('id=?', (row_id,)).save(
        'password', (yf.enDoubleCrypt(_PWD_CRYPT_KEY, pwd),))
    return 'ok'


def modFtpPort():
    args = getArgs()
    if not 'port' in args:
        return yf.returnJson(False, '缺少必要参数: port')
    port = str(args['port']).strip()
    if not re.match(r'^[0-9]{1,5}$', port) or int(port) < 1 or int(port) > 65535:
        return yf.returnJson(False, '端口范围不正确!')
    file = getConf()
    conf = yf.readFile(file)
    if not isinstance(conf, str):
        # 旧实现把 False 交给 re.sub → TypeError，异常文本原样回给前端
        return yf.returnJson(False, '操作失败:')
    rep = r"\n#?\s*Bind\s+[0-9]+\.[0-9]+\.[0-9]+\.+[0-9]+,([0-9]+)"
    conf = re.sub(rep, "\nBind                         0.0.0.0," + port, conf)
    yf.writeFile(file, conf)
    restart()
    return 'ok'


def _switchPort(start_it):
    args = getArgs()
    for key in ('id', 'username', 'status'):
        if key not in args:
            return yf.returnJson(False, '缺少必要参数: ' + key)

    username = str(args['username']).strip()
    if not validUsername(username):
        return yf.returnJson(False, '用户名不合法!')
    status_val = str(args['status']).strip()
    if status_val not in ('0', '1'):
        return yf.returnJson(False, '状态值不合法!')
    row_id = _rowId(args['id'])
    if row_id is None:
        return yf.returnJson(False, '参数不合法!')

    ok, msg = pftpStart(username) if start_it else pftpStop(username)
    if not ok:
        return yf.returnJson(False, '操作失败: ' + msg)
    _reloadPwDb()
    conn = pftpDB()
    if conn is None:
        return yf.returnJson(False, '操作失败:')
    conn.where('id=?', (row_id,)).save('status', (status_val,))
    return 'ok'


def stopPort():
    return _switchPort(False)


def startPort():
    return _switchPort(True)


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
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'conf':
        print(getConf())
    elif func == 'get_www_dir':
        print(getWwwDir())
    elif func == 'get_ftp_list':
        print(getFtpList())
    elif func == 'add_ftp':
        print(addFtp())
    elif func == 'del_ftp':
        print(delFtp())
    elif func == 'mod_ftp':
        print(modFtp())
    elif func == 'mod_ftp_port':
        print(modFtpPort())
    elif func == 'stop_ftp':
        print(stopPort())
    elif func == 'start_ftp':
        print(startPort())
    else:
        print('error')
