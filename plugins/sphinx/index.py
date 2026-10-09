# coding:utf-8

import sys
import io
import os
import time
import json
import re
import string
import subprocess

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.sphinx')

app_debug = False
if yf.isAppleSystem():
    app_debug = True

#: 守护进程名（`pgrep -x` 精确匹配用）。注意与插件名 `sphinx` 不同：
#: `ps -ef|grep sphinx` 是 cmdline **子串**匹配，会把 `tail -f …/sphinx/index/searchd.log`、
#: `sleep …/sphinx/sphinx.conf` 这类无关进程算成「sphinx 正在运行」（真机实测误报 start）。
SEARCHD_PROCESS = 'searchd'

#: 配置模板目录（read_config_tpl / config_tpl 的可读范围）
TPL_SUFFIX = '.conf'

#: 库名/表名白名单：这两个值会被拼进 information_schema 查询与生成的 sphinx.conf
DB_TABLE_NAME_RE = re.compile(r'^[A-Za-z0-9_]{1,64}$')

#: version.pl 内容白名单（会被 sphinx_make 拿去 float() 比较，非数字会 ValueError）
VERSION_RE = re.compile(r'^\d+\.\d+(\.\d+)?$')


def getPluginName():
    return 'sphinx'

def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()

sys.path.append(getPluginDir() +"/class")

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConfTpl():
    path = getPluginDir() + "/conf/sphinx.conf"
    return path


def getConf():
    path = getServerDir() + "/sphinx.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 0:
        return tmp

    # 面板 `plugin.run()` 把前端 args 原样作为一个 argv 传进来（/plugins/run 的 args
    # 字段 = JSON.stringify({...})）。旧实现只认「唯一 argv 且是 JSON 对象」：
    # 带 version 时 args 会变成第 2 个 argv（`func <version> <json>`）→ 退化成按 `:` 硬切，
    # 键变成 `'{"file"'` → 带参接口在真 UI 形态下恒回「缺少必要参数」。
    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
            except Exception as e:
                _log.debug('[sphinx] getArgs JSON 解析失败: %s', e)
                data = None
            if isinstance(data, dict):
                return data
        # 兼容旧 `k:v` 形态；值里含 `:`（盘符、URL）时不得截断
        t = val.strip('{').strip('}').split(':')
        if len(t) >= 2:
            tmp[t[0]] = ':'.join(t[1:])
    elif args_len > 1:
        for i in range(len(args)):
            one = args[i].strip()
            # 多 argv 时同样优先认 JSON 对象（version + args 形态）
            if one.startswith('{') and one.endswith('}'):
                try:
                    data = json.loads(one)
                except Exception as e:
                    _log.debug('[sphinx] getArgs JSON 解析失败: %s', e)
                    data = None
                if isinstance(data, dict):
                    tmp.update(data)
                    continue
            t = one.split(':')
            if len(t) >= 2:
                tmp[t[0]] = ':'.join(t[1:])
    return tmp


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '缺少必要参数: ' + (ck[0] if ck else '')))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def configTpl():
    path = getPluginDir() + '/tpl'
    if not os.path.isdir(path):
        return yf.getJson([])
    tmp = []
    for one in sorted(os.listdir(path)):
        # 与 readConfigTpl 的白名单同口径：只列可读的模板
        if not one.endswith(TPL_SUFFIX):
            continue
        tmp.append(path + '/' + one)
    return yf.getJson(tmp)


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    file_arg = args['file']
    if not isinstance(file_arg, str) or not file_arg.strip():
        return yf.returnJson(False, '缺少必要参数: file')

    # 安全：只允许读模板目录下的模板文件。旧实现把前端给的**任意路径**交给
    # readFile → 真机实测 `file=/etc/hostname` 原样回显（任意文件读取），
    # 且文件不存在时把 False 交给 contentReplace → AttributeError traceback。
    target_file = os.path.realpath(file_arg)
    tpl_dir = os.path.realpath(getPluginDir() + '/tpl')
    if not target_file.startswith(tpl_dir + os.sep) or not target_file.endswith(TPL_SUFFIX):
        return yf.returnJson(False, '越权访问拦截：仅允许读取模板目录下的配置文件！')

    content = yf.readFile(target_file)
    if not isinstance(content, str):
        return yf.returnJson(False, '配置文件不存在或无法读取!')
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/'+getPluginName())
    return content


def getSearchdBin():
    # install.sh 解包出的布局：<server>/sphinx/bin/bin/searchd
    return getServerDir() + '/bin/bin/searchd'


def isInstalled():
    """已安装判据 = searchd 主程序存在。

    不能用「目录存在」（自愈/探针会留下空目录）也不能用 conf 存在（`initdreplace`
    会给未安装的机器凭空写 conf）——否则未安装时 start 会伪造 systemd unit 与整套目录。
    """
    return os.path.exists(getSearchdBin())


def status():
    # 真判据 = searchd 守护进程存活，且必须按**精确进程名**判定。
    # 历史沿革（2026-09-29 与 2026-10-09 两次真机实测）：
    #   * `ps -ef|grep sphinx|grep -v <旧软链名>` —— 面板自己拉起的
    #     `bin/python3 …/plugins/sphinx/index.py status` 命中自身 → 未安装也回 start；
    #   * 补 `grep -v python` 只能挡住面板自身，**cmdline 子串匹配**仍未解决：
    #     未安装、零 searchd 时，一条 `tail -f …/sphinx/index/searchd.log` 就会回 start。
    # pgrep -x 只按进程名精确匹配（无匹配时 rc=1）。
    rc, out, err = yf.execShellRc(['pgrep', '-x', SEARCHD_PROCESS], shell=False, timeout=10)
    if rc == 0 and out.strip():
        return 'start'
    return 'stop'


def mkdirAll():
    content = yf.readFile(getConf())
    # readFile 失败返回 False：旧实现把 False 交给 re.findall → TypeError traceback
    if not isinstance(content, str):
        return False
    rep = r'path\s*=\s*(.*)'
    p = re.compile(rep)
    tmp = p.findall(content)

    for x in tmp:
        if x.find('binlog') != -1:
            yf.makeDirs(x)
        else:
            yf.makeDirs(os.path.dirname(x))


def initDreplace():
    # 未安装时不得伪造 init.d 脚本 / sphinx.conf / systemd unit / 索引目录（真机实测
    # HEAD 版 `start`（未安装）会写出 4 类共 8 个产物并把 sphinx.service 注册进 systemctl）
    if not isInstalled():
        return ''

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    # config replace
    conf_bin = getConf()
    if not os.path.exists(conf_bin):
        conf_content = yf.readFile(getConfTpl())
        conf_content = contentReplace(conf_content)
        yf.writeFile(getServerDir() + '/sphinx.conf', conf_content)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/sphinx.service'
    systemServiceTpl = getPluginDir() + '/init.d/sphinx.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    mkdirAll()
    return file_bin


def checkIndexSph():
    content = yf.readFile(getConf())
    if not isinstance(content, str):
        return True
    rep = r'path\s*=\s*(.*)'
    p = re.compile(rep)
    tmp = p.findall(content)
    for x in tmp:
        if x.find('binlog') != -1:
            continue
        else:
            p = x + '.sph'
            if os.path.exists(p):
                return False
    return True


def sphOp(method):
    # 未安装：一律拒绝，且不造产物、不碰 systemctl（旧实现先 initdreplace 写出 unit 再
    # 跑 systemctl start，未安装的机器上留下「半装」痕迹）
    if not isInstalled():
        return 'ERROR: sphinx 未安装'

    file = initDreplace()

    if not yf.isAppleSystem():
        # 成败必须看退出码：execShell 的 (stdout, stderr) 契约无法区分「失败」与「无输出」
        rc, out, err = yf.execShellRc(['systemctl', method, getPluginName()], shell=False, timeout=120)
        if rc == 0:
            return 'ok'
        return 'fail'

    if not file:
        return 'ERROR: sphinx 未安装'
    data = yf.execShell(file + ' ' + method)
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    # 计划任务（全量/增量索引）只在已安装时创建：旧实现未安装也把 2 条
    # [勿删]Sphinx全量/增量更新 写进面板 crontab，且它们指向不存在的 indexer
    if not isInstalled():
        return 'ERROR: sphinx 未安装'
    import tool_cron
    tool_cron.createBgTask()
    return sphOp('start')


def stop():
    import tool_cron
    # start() 会建**两**条计划任务（全量 + 增量，`createBgTask` 内部两个都建），
    # 旧实现只 removeBgTask() → 停服后 `[勿删]Sphinx增量更新` 留在面板 crontab 里继续跑。
    tool_cron.removeBgTask()
    tool_cron.removeDeltaBgTask()
    return sphOp('stop')


def restart():
    return sphOp('restart')


def reload():
    return sphOp('reload')


def rebuild():
    if not isInstalled():
        return 'ERROR: sphinx 未安装'
    file = initDreplace()
    if not file:
        return 'ERROR: sphinx 未安装'
    cmd = file + ' rebuild'
    data = yf.execShell(cmd)
    if data[0].find('successfully')<0:
        return data[0].replace("\n","<br/>")
    return 'ok'


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    # 旧写法 `systemctl status … | grep loaded | grep "enabled;"` 依赖人类可读输出
    # （语言/版式一变就误判），改用机器可读的 `is-enabled` 退出码 + 输出判定。
    rc, out, err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()],
                                  shell=False, timeout=10)
    if rc == 0 and out.strip().startswith('enabled'):
        return 'ok'
    return 'fail'


def initdOp(action):
    """systemctl enable/disable 的真成败。旧实现无条件回 'ok'：真机实测 unit
    不存在（`systemctl is-enabled sphinx` = `No such file or directory`）时，
    面板仍显示「开机启动 已开启」。失败原因写 stderr（面板 /plugins/run 以 stderr
    判定插件失败并回给前端）。"""
    if not isInstalled():
        sys.stderr.write('sphinx 未安装!')
        return 'fail'

    rc, out, err = yf.execShellRc(['systemctl', action, getPluginName()],
                                  shell=False, timeout=30)
    if rc == 0:
        return 'ok'
    sys.stderr.write('开机启动设置失败!')
    return 'fail'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    return initdOp('enable')


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    return initdOp('disable')


def _confValue(pattern):
    """抓 sphinx.conf 里单个配置值；conf 缺失/无匹配一律回 ''。

    旧实现 `re.search(rep, yf.readFile(path))`：未安装时 readFile 返回 False，
    真机实测 `run_log`/`query_log`/`sphinx_cmd` 全部 `TypeError: expected string or
    bytes-like object, got 'bool'`（HTTP 面即 500）。
    """
    content = yf.readFile(getConf())
    if not isinstance(content, str):
        return ''
    tmp = re.search(pattern, content)
    if not tmp:
        return ''
    return tmp.groups()[0].strip()


def runLog():
    path = _confValue(r'log\s*=\s*(.*)')
    if not path:
        # pluginLogs 契约：回业务错误信封，前端解析 msg（旧实现在未安装时整段 traceback）
        return yf.returnJson(False, 'sphinx 配置文件不存在或无法读取!')
    return path


def getPort():
    return _confValue(r'listen\s*=\s*(.*)')


def queryLog():
    return _confValue(r'query_log\s*=\s*(.*)')


def runStatus():
    if not isInstalled():
        return yf.returnJson(False, 'sphinx 未安装!')

    s = status()
    if s != 'start':
        return yf.returnJson(False, '没有启动程序')

    port = getPort()
    # 端口取自 conf 的 `listen = 9312`：必须是纯数字才能进 sphinxapi（字符串端口会在
    # socket.connect 处 TypeError）；conf 缺失时回可翻译消息而不是 traceback。
    if not port.isdigit():
        return yf.returnJson(False, '未找到有效的查询端口配置!')

    sys.path.append(getPluginDir() + "/class")
    import sphinxapi

    sh = sphinxapi.SphinxClient()
    sh.SetServer('127.0.0.1', int(port))
    info_status = sh.Status()
    # searchd 不可达时 sphinxapi 回 False（旧实现直接 len(False) → TypeError）
    if not info_status:
        return yf.returnJson(False, '无法连接Sphinx服务!')

    rData = {}
    for x in range(len(info_status)):
        rData[info_status[x][0]] = info_status[x][1]

    return yf.returnJson(True, 'ok', rData)


def sphinxConfParse():
    bin_dir = getServerDir()
    cmd = {}
    cmd['cmd'] = bin_dir + '/bin/bin/indexer -c ' + bin_dir + '/sphinx.conf'
    cmd['index'] = []

    content = yf.readFile(getConf())
    # conf 缺失（未安装）时旧实现 re.findall(pattern, False) → TypeError；
    # 回同形状的空结构，调用方（sphinxCmd/updateAll/updateDelta）走既有「无索引」分支。
    if not isinstance(content, str):
        return cmd

    rep = r'index\s(.*)'
    sindex = re.findall(rep, content)
    indexlen = len(sindex)
    cmd_index = []
    cmd_delta = []
    if indexlen > 0:
        for x in range(indexlen):
            name = sindex[x].strip()
            if name == '':
                continue
            if  name.find(':') != -1:
                cmd_delta.append(name.strip())
            else:
                cmd_index.append(name.strip())

    # print(cmd_index)
    # print(cmd_delta)

    for ci in cmd_index:
        val = {}
        val['index'] = ci

        for cd in cmd_delta:
            cd = cd.replace(" ", '')
            if cd.find(":"+ci) > -1:
                val['delta'] = cd.split(":")[0].strip()
                break

        cmd['index'].append(val)
    return cmd


def sphinxCmd():
    data = sphinxConfParse()
    if 'index' in data:
        return yf.returnJson(True, 'ok', data)
    else:
        return yf.returnJson(False, 'no index')

def makeDbToSphinxTest():        
    conf_file = getConf()
    import  sphinx_make
    sph_make = sphinx_make.sphinxMake()
    conf = sph_make.makeSqlToSphinxAll()

    yf.writeFile(conf_file,conf)
    print(conf)
    # makeSqlToSphinxTable()
    return True

def makeDbToSphinx():
    args = getArgs()
    check = checkArgs(args, ['db','tables','is_delta','is_cover'])
    if not check[0]:
        return check[1]

    db = args['db']
    tables = args['tables']
    is_delta = args['is_delta']
    is_cover = args['is_cover']

    if is_cover != 'yes':
        return yf.returnJson(False,'暂时仅支持覆盖!')

    # db / tables 会被拼进 information_schema 查询（见 sphinx_make），必须白名单：
    # 旧实现任意字符串直入 SQL 与生成的 sphinx.conf。
    if not isinstance(db, str) or not DB_TABLE_NAME_RE.match(db):
        return yf.returnJson(False,'数据库名称不合法!')
    if not isinstance(tables, str):
        return yf.returnJson(False,'参数格式错误!')
    table_list = [x for x in tables.split(',') if x.strip()]
    if not table_list:
        return yf.returnJson(False,'缺少必要参数: tables')
    for one in table_list:
        if not DB_TABLE_NAME_RE.match(one.strip()):
            return yf.returnJson(False,'表名不合法!')

    sph_file = getConf()

    import  sphinx_make
    sph_make = sphinx_make.sphinxMake()

    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        # readFile 失败返回 False → 旧实现直接 .strip() AttributeError；
        # 版本号会被 sphinx_make 拿去 float() 比较，非数字同样 ValueError，故加白名单。
        ver = yf.readFile(version_pl)
        if isinstance(ver, str) and VERSION_RE.match(ver.strip()):
            sph_make.setVersion(ver.strip())

    if not sph_make.checkDbName(db):
        return yf.returnJson(False,'保留数据库名称,不可用!')
    is_delta_bool = False
    if is_delta == 'yes':
        is_delta_bool = True
    if is_cover == 'yes':
        tables = [x.strip() for x in table_list]
        content = sph_make.makeSqlToSphinx(db, tables, is_delta_bool)
        yf.writeFile(sph_file,content)
        mkdirAll()
        return yf.returnJson(True,'设置成功!')

    return yf.returnJson(True,'测试中')


# 全量更新
def updateAll():
    data = sphinxConfParse()
    cmd = data['cmd']
    if not 'index' in data:
        return '无更新'
    index = data['index']

    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    for x in range(len(index)):
        idx_name = index[x]['index']
        if not pattern.match(idx_name):
            print("安全拦截: 非法的索引名称 ->", idx_name)
            continue
        # cmd 由 sphinxConfParse 用服务端路径拼出（无引号/空格），idx_name 已由上方正则白名单校验；
        # 改用列表参数后完全不经过 shell，隔离命令注入。
        cmd_index = cmd.split() + [idx_name, '--rotate']
        print(cmd_index)
        yf.safeExecShell(cmd_index)
    return ''

#增量更新
def updateDelta():
    data = sphinxConfParse()
    cmd = data['cmd']
    if not 'index' in data:
        return '无更新'
    index = data['index']

    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    for x in range(len(index)):
        idx_name = index[x]['index']
        if not pattern.match(idx_name):
            print("安全拦截: 非法的索引名称 ->", idx_name)
            continue

        if 'delta' in index[x]:
            delta_name = index[x]['delta']
            if not pattern.match(delta_name):
                print("安全拦截: 非法的增量索引名称 ->", delta_name)
                continue
            # cmd 同上：服务器生成；delta_name 已白名单校验，列表参数零 shell 拼接
            cmd_index = cmd.split() + [delta_name, '--rotate']
            print(cmd_index)
            yf.safeExecShell(cmd_index)

            cmd_index_merge = cmd.split() + ['--merge', idx_name, delta_name, '--rotate']
            print(cmd_index_merge)
            yf.safeExecShell(cmd_index_merge)
        else:
            print(idx_name,'no delta')

    return ''

def installPreInspection(version):
    if yf.isAppleSystem():
        return 'ok'
    data = yf.execShell('arch')
    if data[0].strip().startswith('aarch'):
        return '不支持aarch架构'
    return 'ok'

if __name__ == "__main__":
    version = "3.1.1"
    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        ver = yf.readFile(version_pl)
        if isinstance(ver, str) and ver.strip():
            version = ver.strip()

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
    elif func == 'rebuild':
        print(rebuild())
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'install_pre_inspection':
        print(installPreInspection(version))
    elif func == 'conf':
        print(getConf())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'run_log':
        print(runLog())
    elif func == 'query_log':
        print(queryLog())
    elif func == 'run_status':
        print(runStatus())
    elif func == 'sphinx_cmd':
        print(sphinxCmd())
    elif func == 'db_to_sphinx':
        print(makeDbToSphinx())
    elif func == 'update_all':
        print(updateAll())
    elif func == 'update_delta':
        print(updateDelta())
    else:
        print('error')
