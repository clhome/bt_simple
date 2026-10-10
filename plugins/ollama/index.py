# coding:utf-8

import sys
import io
import os
import time
import re
import socket
import json
import shutil
import subprocess

from datetime import datetime

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.ollama')

app_debug = False
if yf.isAppleSystem():
    app_debug = True

# Ollama 模型名白名单：官方形态 `name[:tag]` 或 `namespace/name[:tag]`。
# 首字符必须是字母/数字（否则会被 ollama 当成命令行选项），拒绝 `..`（路径穿越）、
# 空白/控制字符与 shell 元字符（`;`/`&`/`|`/`$`/反引号/引号）。
_MODEL_NAME_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9._-]*(?:/[a-zA-Z0-9][a-zA-Z0-9._-]*)*(?::[a-zA-Z0-9._-]+)?$')
# 监听地址白名单：`host[:port]`，host 仅允许域名/IPv4/IPv6 字面量，端口单独校验范围。
_HOST_RE = re.compile(r'^([0-9a-zA-Z][0-9a-zA-Z.\-]*|\[[0-9a-fA-F:]+\])(?::([0-9]{1,5}))?$')
# OLLAMA_MODELS 存储路径的字符白名单（绝对路径 + 无 `..` 另行判定）。
_MODELS_PATH_RE = re.compile(r'^[0-9a-zA-Z.:\-_/]+$')
_PORT_MIN, _PORT_MAX = 1, 65535
# `systemctl is-enabled` 退出码 0 时可能返回的「已启用」态。
_UNIT_ENABLED_STATES = (
    'enabled', 'enabled-runtime', 'static', 'indirect', 'alias',
    'generated', 'transient', 'linked', 'linked-runtime',
)
_OLLAMA_BIN_CANDIDATES = (
    '/usr/local/bin/ollama', '/usr/bin/ollama', '/bin/ollama',
    '/usr/local/sbin/ollama', '/usr/sbin/ollama',
)
_SERVICE_FILE_PATHS = (
    '/etc/systemd/system/ollama.service',
    '/lib/systemd/system/ollama.service',
    '/usr/lib/systemd/system/ollama.service',
)
# 单个表格字段（模型名/ID/大小/时间）回传前截断，避免畸形超长行把响应撑爆。
_FIELD_MAX = 512


def _asText(val, default=''):
    """把 getArgs 解析出的任意 JSON 值归一化成字符串。

    前端 `JSON.stringify` 后 `true`/数字会变成 bool/int，旧实现直接 `.strip()`
    会 AttributeError（顶层 except 兜成「执行异常」），这里统一归一化。
    """
    if val is None:
        return default
    if isinstance(val, bool):
        return 'true' if val else 'false'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return val
    return default


class App:
    __setupPath = '/www/server/ollama'
    __cfg = ''
    __agent_cfg = ''

    def __init__(self):
        self.__setupPath = self.getServerDir()

    def getArgs(self):
        """解析插件参数。

        面板 `utils/plugin.py::run()` 的真实 argv 是
        `[<index.py>, <func>, <version>, <args>]`，前端把 `args` 作为**一个**
        JSON argv 传进来（`YfPlugin.parseArgs` 统一发 JSON 字符串）。
        旧实现把单个 argv 按 `:` 硬切，键会变成带引号的 `'"model_name"'`
        → `pull_model`/`delete_model`/`set_config` 在真 UI 形态下 100% 恒回
        「模型名称不能为空」/「监听 Host 不能为空」（真机实证）。
        这里 JSON 优先（`{` 开头 + `json.loads` 且 `isinstance(dict)` 才采信），
        再退 `k:v` 旧写法；畸形入参一律回 {} 而不是抛异常。
        """
        tmp = {}
        scan_args = sys.argv[2:]
        for raw in scan_args:
            val = str(raw).strip()
            if not (val.startswith('{') and val.endswith('}')):
                continue
            try:
                parsed = json.loads(val)
            except Exception as _e:
                _log.debug('[ollama] getArgs JSON 解析失败: %s', _e)
                continue
            if isinstance(parsed, dict):
                return parsed

        for raw in scan_args:
            val = str(raw).strip()
            if ':' not in val:
                continue
            key, value = val.split(':', 1)
            key = key.strip().strip('{').strip('}').strip('"').strip("'")
            value = value.strip().strip('"').strip("'").strip('}').strip('{')
            if key:
                tmp[key] = value
        return tmp

    def checkArgs(self, data, ck=[]):
        for i in range(len(ck)):
            if not ck[i] in data:
                return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
        return (True, yf.returnJson(True, 'ok'))

    def getPluginName(self):
        return 'ollama'

    def getPluginDir(self):
        return yf.getPluginDir() + '/' + self.getPluginName()

    def getServerDir(self):
        return yf.getServerDir() + '/' + self.getPluginName()

    def getHomeDir(self):
        if yf.isAppleSystem():
            user = yf.execShell(
                "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
            return '/Users/' + user
        else:
            return '/root'

    def getRunUser(self):
        if yf.isAppleSystem():
            user = yf.execShell(
                "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
            return user
        else:
            return 'root'

    def getOllamaBin(self):
        """定位 ollama 可执行文件；找不到返回 ''（未安装）。零 shell 调用。"""
        for path in _OLLAMA_BIN_CANDIDATES:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        found = shutil.which(self.getPluginName())
        if found and os.path.isfile(found):
            return found
        return ''

    def isInstalled(self):
        """面板口径的「已安装」：version.pl（install.sh 落盘）或 ollama 可执行文件。"""
        if os.path.exists(self.getServerDir() + '/version.pl'):
            return True
        return self.getOllamaBin() != ''

    def status(self):
        if yf.isAppleSystem():
            # macOS 无 systemd，退回进程探测（判据含 grep -v python，排除面板自身）
            cmd = "ps -ef|grep " + self.getPluginName() + " |grep -v grep | grep -v python | awk '{print $2}'"
            data = yf.execShell(cmd)
            if data[0] == '':
                return "stop"
            return 'start'

        # Linux 环境下基于 systemctl 精准探测服务状态（未安装/未运行一律 stop）
        rc, out, _err = yf.execShellRc(
            ['systemctl', 'is-active', self.getPluginName()], shell=False, timeout=15)
        if rc == 0 and (out or '').strip() == 'active':
            return 'start'
        return 'stop'

    def contentReplace(self, content):
        service_path = yf.getServerDir()
        content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$RUN_USER}', self.getRunUser())
        content = content.replace('{$HOME_DIR}', self.getHomeDir())
        return content

    def initDreplace(self):
        # 兼容原有框架结构，如果需要则生成自启动脚本；未安装时零产物
        if not self.isInstalled():
            return ''
        initD_path = self.getServerDir() + '/init.d'
        if not os.path.exists(initD_path):
            os.mkdir(initD_path)

        file_bin = initD_path + '/' + self.getPluginName()
        # 原有逻辑保留但精简，Ollama 主要使用 systemd 服务
        return file_bin

    def init_cfg(self):
        self.initDreplace()

    def oaOp(self, method):
        if method not in ('start', 'stop', 'restart', 'reload'):
            return 'fail'

        if yf.isAppleSystem():
            file = self.initDreplace()
            if not file:
                return 'fail'
            data = yf.execShell(file + ' ' + method)
            if data[1] == '':
                return 'ok'
            return data[0]

        rc, _out, err = yf.execShellRc(
            ['systemctl', method, self.getPluginName()], shell=False, timeout=120)
        if rc != 0:
            _log.debug('[ollama] systemctl %s 失败 rc=%s err=%s', method, rc, err)
            return 'fail'
        # systemctl 回 0 不代表服务真的就绪（unit 缺失/依赖失败/起来即退出）
        # → 回读真实状态，未就绪不得报 ok（旧实现只看 stderr 空 = 假成功）
        expect = 'stop' if method == 'stop' else 'start'
        if self.status() != expect:
            _log.debug('[ollama] systemctl %s 回 0 但状态未就绪', method)
            return 'fail'
        return 'ok'

    def start(self):
        return self.oaOp('start')

    def stop(self):
        return self.oaOp('stop')

    def restart(self):
        return self.oaOp('restart')

    def reload(self):
        return self.oaOp('reload')

    def initd_status(self):
        if yf.isAppleSystem():
            return 'fail'
        # 旧实现解析 `systemctl status` 的人类可读输出（grep loaded|grep "enabled;"），
        # 输出措辞一变即误判；改判 `is-enabled` 退出码 + 状态白名单
        rc, out, _err = yf.execShellRc(
            ['systemctl', 'is-enabled', self.getPluginName()], shell=False, timeout=15)
        if rc == 0 and (out or '').strip() in _UNIT_ENABLED_STATES:
            return 'ok'
        return 'fail'

    def initd_install(self):
        if yf.isAppleSystem():
            return 'ok'
        if not self.isInstalled():
            return 'fail'
        rc, _out, err = yf.execShellRc(
            ['systemctl', 'enable', self.getPluginName()], shell=False, timeout=60)
        if rc != 0:
            _log.debug('[ollama] systemctl enable 失败 rc=%s err=%s', rc, err)
            return 'fail'
        # 回读：enable 回 0 但没真的启用（模板/掩码 unit）不得报 ok
        return self.initd_status()

    def initd_uninstall(self):
        if yf.isAppleSystem():
            return 'ok'
        rc, _out, err = yf.execShellRc(
            ['systemctl', 'disable', self.getPluginName()], shell=False, timeout=60)
        if rc != 0:
            _log.debug('[ollama] systemctl disable 失败 rc=%s err=%s', rc, err)
            return 'fail'
        return 'ok'

    # --- 以下为 v1.1 新增的高级管理接口 ---

    def _parseModelTable(self, text, min_parts, keys):
        """解析 `ollama list`/`ollama ps` 的固定列输出。

        空输出/畸形行/列数不足一律跳过（旧实现同样跳过，但这里补上字段截断，
        避免畸形超长行把响应撑爆）；模型名等字段原样回传，前端负责转义。
        """
        models = []
        lines = (text or '').strip().split('\n')
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'\s{2,}', line)
            if len(parts) < min_parts:
                continue
            item = {}
            for idx, key in enumerate(keys):
                item[key] = parts[idx].strip()[:_FIELD_MAX]
            models.append(item)
        return models

    def _modelOpError(self, err, out=''):
        """把 ollama 的 stderr 归一成可翻译提示（连接失败单独给引导语）。"""
        text = ((err or '') + (out or '')).strip()
        low = text.lower()
        if ('connection refused' in low or 'could not connect' in low
                or 'is it running' in low or 'connection reset' in low):
            return '无法连接到 Ollama 服务，请确保服务已正常启动！'
        return text[:_FIELD_MAX] if text else '无法连接到 Ollama 服务！'

    def get_models(self):
        bin_path = self.getOllamaBin()
        if not bin_path:
            return yf.returnJson(False, '未检测到 Ollama，请先安装后再使用！')

        rc, out, err = yf.execShellRc([bin_path, 'list'], shell=False, timeout=30)
        if rc != 0:
            # 旧实现只在 stderr 里找 'connection refused'，其它失败（未安装/
            # 二进制缺失）会回 status=true + 空列表 = 假成功
            return yf.returnJson(False, self._modelOpError(err, out))

        return yf.returnJson(True, 'ok', self._parseModelTable(
            out, 4, ('name', 'id', 'size', 'modified')))

    def get_running_models(self):
        bin_path = self.getOllamaBin()
        if not bin_path:
            return yf.returnJson(False, '未检测到 Ollama，请先安装后再使用！')

        rc, out, err = yf.execShellRc([bin_path, 'ps'], shell=False, timeout=30)
        if rc != 0:
            return yf.returnJson(False, self._modelOpError(err, out))

        return yf.returnJson(True, 'ok', self._parseModelTable(
            out, 5, ('name', 'id', 'size', 'processor', 'until')))

    def _validModelName(self, model_name):
        if not model_name or len(model_name) > 256:
            return False
        if '..' in model_name:
            return False
        return bool(_MODEL_NAME_RE.match(model_name))

    def pull_model(self):
        args = self.getArgs()
        model_name = _asText(args.get('model_name', '')).strip()
        if not model_name:
            return yf.returnJson(False, '模型名称不能为空！')

        if not self._validModelName(model_name):
            return yf.returnJson(False, '模型名称包含非法字符！')

        bin_path = self.getOllamaBin()
        if not bin_path:
            # 真机实证：旧实现未安装也回「任务已启动」，且 writeFile 会自动建
            # `/www/server/ollama` 目录 → 假成功 + 未安装造产物
            return yf.returnJson(False, '未检测到 Ollama，请先安装后再使用！')

        log_file = self.getServerDir() + '/pull.log'
        pulling_file = self.getServerDir() + '/pulling_name.pl'

        # 后台异步拉取：argv 列表 + 不经过 shell（模型名已白名单，杜绝拼接注入），
        # 输出直接重定向到 pull.log；start_new_session 让任务脱离面板请求生命周期
        try:
            log_fp = open(log_file, 'wb')
        except Exception as e:
            _log.debug('[ollama] 打开拉取日志失败: %s', e)
            return yf.returnJson(False, '模型拉取任务启动失败！')

        try:
            subprocess.Popen(
                [bin_path, 'pull', model_name],
                stdout=log_fp, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, cwd=self.getServerDir(),
                start_new_session=True)
        except Exception as e:
            _log.debug('[ollama] 启动拉取任务失败: %s', e)
            return yf.returnJson(False, '模型拉取任务启动失败！')
        finally:
            try:
                log_fp.close()
            except Exception as _e:
                _log.debug('[ollama] 关闭拉取日志句柄失败: %s', _e)

        yf.writeFile(pulling_file, model_name)
        return yf.returnJson(True, '模型拉取任务已在后台成功启动！')

    def _isPulling(self, model_name):
        """判断目标模型的拉取进程是否仍在运行。

        旧实现用 `ps -ef | grep 'ollama pull' | grep -v grep`（字符串管道），
        这里改列表化 `ps -ef` + Python 侧判据（必须命中 ollama 二进制路径、
        排除 python/grep），面板自身的 python 进程不再可能被误判。
        """
        if not model_name:
            return False
        bin_path = self.getOllamaBin()
        if not bin_path:
            return False
        rc, out, _err = yf.execShellRc(['ps', '-ef'], shell=False, timeout=15)
        if rc != 0:
            return False
        for line in (out or '').split('\n'):
            if ' pull ' not in line or bin_path not in line:
                continue
            if 'python' in line or 'grep' in line:
                continue
            if model_name in line:
                return True
        return False

    def get_pull_log(self):
        log_file = self.getServerDir() + '/pull.log'
        pulling_file = self.getServerDir() + '/pulling_name.pl'

        model_name = ''
        if os.path.exists(pulling_file):
            raw_name = yf.readFile(pulling_file)
            # readFile 失败返回 False（不是空串），直接 .strip() 会 AttributeError
            if isinstance(raw_name, str):
                model_name = raw_name.strip()[:_FIELD_MAX]

        if not os.path.exists(log_file):
            return yf.returnJson(True, '等待任务初始化...', {'status': 'running', 'log': '正在初始化拉取任务...\n', 'model': model_name})

        raw_log = yf.readFile(log_file)
        if not isinstance(raw_log, str):
            return yf.returnJson(False, '获取服务日志失败！')

        # 将 \r 换行处理以防多进度堆叠，只向前端返回最后20行
        clean_content = raw_log.replace('\r', '\n')
        lines = clean_content.split('\n')
        display_log = '\n'.join(lines[-20:])

        is_running = self._isPulling(model_name)

        status = 'running'
        if not is_running:
            status = 'done'
            low = clean_content.lower()
            if 'success' in low:
                status = 'success'
                if os.path.exists(pulling_file):
                    try:
                        os.remove(pulling_file)
                    except Exception as e:
                        _log.debug('[ollama] 清理 pulling_name.pl 失败: %s', e)
            elif 'error' in low or 'failed' in low:
                status = 'failed'

        return yf.returnJson(True, 'ok', {'status': status, 'log': display_log, 'model': model_name})

    def delete_model(self):
        args = self.getArgs()
        model_name = _asText(args.get('model_name', '')).strip()
        if not model_name:
            return yf.returnJson(False, '模型名称不能为空！')

        if not self._validModelName(model_name):
            return yf.returnJson(False, '非法的模型名称！')

        bin_path = self.getOllamaBin()
        if not bin_path:
            return yf.returnJson(False, '未检测到 Ollama，请先安装后再使用！')

        # argv 列表调用（模型名已白名单），不再拼 shell；以退出码判成败
        rc, out, err = yf.execShellRc([bin_path, 'rm', model_name], shell=False, timeout=120)
        if rc == 0:
            return yf.returnJson(True, '模型删除成功！')
        return yf.returnJson(False, '删除失败：{}'.format(
            ((err or '') + (out or '')).strip()[:_FIELD_MAX] or '未知错误'))

    def get_service_file(self):
        for p in _SERVICE_FILE_PATHS:
            if os.path.exists(p):
                return p
        return ''

    def get_config(self):
        service_file = self.get_service_file()
        host = '127.0.0.1:11434'
        models_path = '/usr/share/ollama/.ollama/models'

        if service_file:
            content = yf.readFile(service_file)
            # readFile 失败返回 False；旧实现直接 re.search(pattern, False) → TypeError
            if isinstance(content, str):
                host_match = re.search(r'Environment\s*=\s*"?OLLAMA_HOST=([^"\n\s]+)"?', content)
                if host_match:
                    host = host_match.group(1)

                models_match = re.search(r'Environment\s*=\s*"?OLLAMA_MODELS=([^"\n\s]+)"?', content)
                if models_match:
                    models_path = models_match.group(1)

        # 检测 11434 防火墙端口
        port_open = False
        rc, out, _err = yf.execShellRc(['firewall-cmd', '--list-ports'], shell=False, timeout=15)
        if rc == 0 and '11434/tcp' in (out or ''):
            port_open = True

        return yf.returnJson(True, 'ok', {
            'host': host,
            'models_path': models_path,
            'port_open': port_open,
            'service_file': service_file
        })

    def _parseHostPort(self, host):
        """校验 `host[:port]`，返回 (hostname, port) 或 None。"""
        match = _HOST_RE.match(host)
        if not match:
            return None
        name, port = match.group(1), match.group(2)
        if port is None:
            return (name, 11434)
        try:
            port_num = int(port)
        except Exception:
            return None
        if port_num < _PORT_MIN or port_num > _PORT_MAX:
            return None
        return (name, port_num)

    def _syncFirewallPort(self, want_open):
        """按期望状态收敛 11434 放行。

        旧实现只在 host 含 0.0.0.0 时才动防火墙：把 host 从 `0.0.0.0:11434`
        改回 `127.0.0.1:11434` 时旧放行**不会被收回**（端口长期对公网敞开）。
        """
        rc, out, _err = yf.execShellRc(['firewall-cmd', '--list-ports'], shell=False, timeout=15)
        if rc != 0:
            return False
        is_open = '11434/tcp' in (out or '')
        if is_open == bool(want_open):
            return True
        action = '--add-port=11434/tcp' if want_open else '--remove-port=11434/tcp'
        rc, _o, err = yf.execShellRc(
            ['firewall-cmd', '--zone=public', action, '--permanent'], shell=False, timeout=30)
        if rc != 0:
            _log.debug('[ollama] 防火墙规则变更失败: %s', err)
            return False
        yf.execShellRc(['firewall-cmd', '--reload'], shell=False, timeout=30)
        return True

    def _restoreServiceFile(self, service_file, backup_file):
        try:
            original = yf.readFile(backup_file)
            if isinstance(original, str):
                yf.writeFile(service_file, original)
        except Exception as e:
            _log.debug('[ollama] 回滚服务文件失败: %s', e)

    def set_config(self):
        args = self.getArgs()
        host = _asText(args.get('host', '')).strip()
        models_path = _asText(args.get('models_path', '')).strip()
        port_open = _asText(args.get('port_open', '')).strip()  # 'true' / 'false'

        if not host:
            return yf.returnJson(False, '监听 Host 不能为空！')

        if not re.match(r'^[0-9a-zA-Z.:\-_]+$', host):
            return yf.returnJson(False, 'Host 包含非法字符！')

        # 旧实现只做字符白名单，`999.999.999.999:99999` 之类非法地址照样写进 unit
        if self._parseHostPort(host) is None:
            return yf.returnJson(False, '监听地址不合法！')

        if models_path:
            if not _MODELS_PATH_RE.match(models_path):
                return yf.returnJson(False, '存储路径包含非法字符！')
            # 旧实现允许 `../../etc/x` 这类相对路径/穿越值原样写进 unit
            if not models_path.startswith('/') or '..' in models_path.split('/'):
                return yf.returnJson(False, '存储路径不合法！')

        service_file = self.get_service_file()
        if not service_file:
            return yf.returnJson(False, '找不到 Ollama 服务文件，无法修改配置！')

        content = yf.readFile(service_file)
        if not isinstance(content, str):
            return yf.returnJson(False, '服务配置文件不可读！')

        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if 'OLLAMA_HOST=' in line or 'OLLAMA_MODELS=' in line:
                continue
            new_lines.append(line)

        service_idx = -1
        for idx, line in enumerate(new_lines):
            if '[Service]' in line:
                service_idx = idx
                break

        if service_idx == -1:
            return yf.returnJson(False, 'Systemd 文件格式损坏！')

        new_lines.insert(service_idx + 1, 'Environment="OLLAMA_HOST={}"'.format(host))
        if models_path:
            new_lines.insert(service_idx + 2, 'Environment="OLLAMA_MODELS={}"'.format(models_path))

        # 改 unit 前先留一份原件：daemon-reload/restart 失败时按它回滚，
        # 不留「半套配置 + 服务起不来」的中间态
        backup_file = service_file + '.yf_bak'
        if yf.writeFile(backup_file, content) is not True:
            return yf.returnJson(False, '服务文件写入失败！')
        if yf.writeFile(service_file, '\n'.join(new_lines)) is not True:
            return yf.returnJson(False, '服务文件写入失败！')

        rc, _out, err = yf.execShellRc(['systemctl', 'daemon-reload'], shell=False, timeout=60)
        if rc != 0:
            _log.debug('[ollama] daemon-reload 失败: %s', err)
            self._restoreServiceFile(service_file, backup_file)
            yf.execShellRc(['systemctl', 'daemon-reload'], shell=False, timeout=60)
            return yf.returnJson(False, '服务配置应用失败，已回滚！')

        # 管理端口防火墙放行：按 host 的期望状态收敛（改回 127.0.0.1 时收回放行）
        self._syncFirewallPort('0.0.0.0' in host and port_open == 'true')

        rc, _out, err = yf.execShellRc(
            ['systemctl', 'restart', self.getPluginName()], shell=False, timeout=120)
        if rc != 0 or self.status() != 'start':
            _log.debug('[ollama] 服务重启失败 rc=%s err=%s', rc, err)
            self._restoreServiceFile(service_file, backup_file)
            yf.execShellRc(['systemctl', 'daemon-reload'], shell=False, timeout=60)
            return yf.returnJson(False, '服务配置应用失败，已回滚！')

        return yf.returnJson(True, '配置更新成功，服务已重启生效！')

    def get_service_logs(self):
        # 获取服务最新 100 行日志
        if not self.isInstalled():
            return yf.returnJson(False, '未检测到 Ollama，请先安装后再使用！')
        rc, out, err = yf.execShellRc(
            ['journalctl', '-u', self.getPluginName(), '--no-pager', '-n', '100'],
            shell=False, timeout=30)
        if rc != 0:
            _log.debug('[ollama] journalctl 失败: %s', err)
            return yf.returnJson(False, '获取服务日志失败！')
        return yf.returnJson(True, 'ok', out)

    def get_ollama_access_info(self):
        try:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                internal_ip = s.getsockname()[0]
                s.close()
            except Exception as _e:
                _log.debug('[ollama] get_ollama_access_info 异常已忽略: %s', _e)
                internal_ip = '127.0.0.1'

            try:
                external_ip = yf.getHostAddr()
            except Exception as _e:
                _log.debug('[ollama] get_ollama_access_info 异常已忽略: %s', _e)
                external_ip = internal_ip

            return yf.returnJson(True, 'ok', {
                'internal_url': 'http://' + internal_ip + ':11434/api/tags',
                'external_url': 'http://' + external_ip + ':11434/api/tags'
            })
        except Exception as e:
            return yf.returnJson(False, str(e))


if __name__ == "__main__":
    func = sys.argv[1]

    # 强正则校验白名单，彻底阻断 eval/系统注入可能
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func):
        print(yf.returnJson(False, '函数参数不合法！'))
        sys.exit(0)

    classApp = App()
    try:
        # 使用安全的 getattr 代替有高危注入风险的 eval
        method = getattr(classApp, func, None)
        if method and callable(method):
            data = method()
            print(data)
        else:
            print(yf.returnJson(False, '找不到对应的方法: ' + func))
    except Exception as e:
        print(yf.returnJson(False, '执行异常: ' + str(e)))
