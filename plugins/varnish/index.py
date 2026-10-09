# coding:utf-8

import sys
import io
import os
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True

#: varnish 由发行版包管理器安装（没有面板自建目录），按候选路径探测主程序
VARNISH_BIN_CANDIDATES = (
    '/usr/sbin/varnishd',
    '/usr/bin/varnishd',
    '/usr/local/sbin/varnishd',
)

#: 守护进程名（`pgrep -x` 精确匹配用）。注意与插件名 `varnish` 不同：
#: 宽泛匹配 `varnish` 会把 `tail -f /var/log/varnish/…`、`vim /etc/varnish/…` 等
#: 无关进程算成「varnish 正在运行」。
VARNISH_PROCESS = 'varnishd'

#: 日志候选路径（varnish 默认 log 与 ncsa 日志）
VARNISH_LOG_CANDIDATES = (
    '/var/log/varnish/varnish.log',
    '/var/log/varnish/varnishncsa.log',
)


def getPluginName():
    return 'varnish'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getVarnishBin():
    for path in VARNISH_BIN_CANDIDATES:
        if os.path.exists(path):
            return path
    return ''


def isInstalled():
    """已安装判据：发行版装的 varnishd 主程序，或面板安装标记目录
    （install.sh 建的 `<server>/varnish`）。两者都不存在时不得伪造 unit、
    不得把 start/stop/initd_install 报成成功。"""
    if getVarnishBin():
        return True
    return os.path.exists(getServerDir())


def getConf():
    path = '/etc/varnish/vcl.conf'
    if os.path.exists(path):
        return path
    path = "/etc/varnish/default.vcl"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/varnish')
    return content


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    # 面板 `plugin.run()` 把前端 args 作为**一个** JSON argv 传进来
    # （`/plugins/run` 的 args 字段 = JSON.stringify({...})）。旧实现按 `:` 硬切，
    # 键会变成 `'"file"'` → 带参接口（read_config_tpl）在真 UI 形态下恒回
    # 「缺少必要参数」；畸形 argv（裸值/数组）直接 IndexError traceback 回前端。
    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
            except Exception:
                data = None
            if isinstance(data, dict):
                return data
        t = val.strip('{').strip('}').split(':')
        # 兼容旧 `k:v` 形态；值里含 `:`（Windows 盘符、URL）时不得把参数值截断
        if len(t) >= 2:
            tmp[t[0]] = ':'.join(t[1:])
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            if len(t) < 2:
                continue
            tmp[t[0]] = ':'.join(t[1:])
    return tmp


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '缺少必要参数: ' + (ck[0] if ck else '')))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def status():
    # 真判据 = 守护进程存活，且必须按**精确进程名**判定：
    #   * 旧写法 `ps -ef|grep varnish|grep -v grep`（缺 `grep -v python`）在未安装的
    #     机器上会匹配到面板自己拉起的 `python3 plugins/varnish/index.py status`
    #     （真机实测 pids=自身 python 进程）→ 恒报 start；
    #   * 即便加上 `grep -v python`，`grep varnish` 仍会命中 `tail -f
    #     /var/log/varnish/varnish.log` 这类无关进程（真机实测）→ 同样误报 start。
    # 只看 pid 文件/目录存在性也不成立（陈旧 pid 会假阳性）。
    rc, out, err = yf.execShellRc(['pgrep', '-x', VARNISH_PROCESS], shell=False, timeout=10)
    if rc == 0 and out.strip():
        return 'start'
    return 'stop'


def vaOp(method):
    if not isInstalled():
        return 'ERROR: varnish 未安装'
    # 成败必须看退出码：execShell 的 (stdout, stderr) 契约无法区分「失败」与「无输出」。
    yf.execShellRc(['systemctl', 'daemon-reload'], shell=False, timeout=30)
    rc, out, err = yf.execShellRc(['systemctl', method, getPluginName()], shell=False, timeout=120)
    if rc == 0:
        return 'ok'
    return 'fail'


def start():
    return vaOp('start')


def stop():
    return vaOp('stop')


def restart():
    return vaOp('restart')


def reload():
    return vaOp('reload')


def runInfo():
    if not isInstalled():
        return yf.returnJson(False, 'varnish 未安装!')
    # 带超时：varnishstat 卡住时不能把面板子进程一起拖死
    rc, out, err = yf.execShellRc(['varnishstat', '-j'], shell=False, timeout=20)
    if rc != 0 or not out.strip():
        return yf.returnJson(False, 'Varnish 状态获取失败,请检查服务是否已启动!')
    # 成功时回原始 JSON 文本（前端直接 JSON.parse 后按 counters 渲染）
    return out.strip()


def configTpl():
    path = getPluginDir() + '/tpl'
    if not os.path.isdir(path):
        return yf.getJson([])
    tmp = []
    for one in os.listdir(path):
        # 与 readConfigTpl 的白名单同口径：只列可读的 .vcl 模板
        if not one.endswith('.vcl'):
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

    # 安全检查：限制读取的文件必须是 tpl 目录下的 .vcl 模板（realpath 解掉软链逃逸）
    target_file = os.path.realpath(file_arg)
    tpl_dir = os.path.realpath(getPluginDir() + '/tpl')

    if not target_file.startswith(tpl_dir + os.sep) or not target_file.endswith('.vcl'):
        return yf.returnJson(False, '越权访问拦截：仅允许读取模板目录下的VCL配置文件！')

    content = yf.readFile(target_file)
    # readFile 失败返回 False：旧实现直接交给 contentReplace → AttributeError traceback 回前端
    if not isinstance(content, str):
        return yf.returnJson(False, '配置文件不存在或无法读取!')
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    # 旧写法 `systemctl status … | grep loaded | grep "enabled;"` 依赖人类可读输出
    # （语言/版式一变就误判），改用机器可读的 `is-enabled` 退出码 + 单字输出。
    rc, out, err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()],
                                  shell=False, timeout=10)
    if rc == 0 and out.strip().startswith('enabled'):
        return 'ok'
    return 'fail'


def initdOp(action):
    """systemctl enable/disable 的真成败。旧实现无条件回 'ok'：真机实测
    `systemctl is-enabled varnish` = `No such file or directory`（根本没装）时
    面板仍显示「开机启动 已开启」。失败原因写 stderr（面板 /plugins/run 以 stderr
    判定插件失败并把消息回给前端）。"""
    if not isInstalled():
        sys.stderr.write('varnish 未安装!')
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


def runLog():
    for path in VARNISH_LOG_CANDIDATES:
        if os.path.exists(path):
            return path

    # 旧实现恒回固定路径：前端拿它去读不存在的文件，用户看不到「没装/没日志」的真相。
    # 这里按 pluginLogs 既有契约回业务错误信封（前端会解析出 msg 提示）。
    return yf.returnJson(False, 'varnish 日志文件不存在!')


def confService():
    return yf.systemdCfgDir() + '/varnish.service'

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
    elif func == 'run_info':
        print(runInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'conf_service':
        print(confService())
    elif func == 'run_log':
        print(runLog())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    else:
        print('error')
