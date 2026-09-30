# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import html
import os
import re
import shlex
from datetime import datetime

import core.yf as yf

__months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
            'Jul': '07', 'Aug': '08', 'Sep': '09', 'Sept': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}

#: 日志审计只允许访问 /var/log 及其子目录（如 sa/sa01）。
_LOG_DIR = '/var/log'

#: 合法日志名白名单：字母数字开头，仅含字母数字、下划线、点、连字符、斜杠。
#: 明确禁止：绝对路径（前导 /）、空白、shell 元字符、``..``。
_LOG_NAME_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-/]*$')

#: lastlog 的「从未登录」提示（英文）。本地化环境下文案会变，
#: 因此真正的判据是「结构上取不到日期」，而不是这句英文。
_NEVER_LOGGED_RE = re.compile(r'never\s+logged\s+in', re.IGNORECASE)

_WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def _safeLogPath(log_name):
    """校验日志名并解析为 /var/log 下的真实路径；非法返回 None。

    安全背景（原实现是一个任意文件读取 / 命令注入入口）：
    老代码把用户提交的 ``log_name`` 直接拼进文件路径与 shell 命令，
    于是 ``../../etc/shadow`` 能越权读文件、``wtmp; rm -rf /`` 能注入命令。
    这里做三层校验：字符白名单 -> 拒绝 ``..`` -> realpath 必须仍在 /var/log 内。
    """
    if not log_name or not isinstance(log_name, str) or len(log_name) > 255:
        return None
    log_name = log_name.strip()
    if not _LOG_NAME_RE.match(log_name):
        return None
    if '..' in log_name.split('/'):
        return None
    base = os.path.realpath(_LOG_DIR)
    target = os.path.realpath(os.path.join(base, log_name))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _escapeRows(rows):
    """对将直接拼进前端 HTML 的日志字段做转义（防存储型 XSS）。

    日志内容（用户名、来源 IP、事件文本）是攻击者可影响的外部输入：
    例如用 ``<img src=x onerror=...>`` 当 SSH 用户名做失败登录，就会写进
    btmp/wtmp/系统日志；管理员在日志审计页查看时即触发脚本执行。
    与 ``getLastLine`` 对普通日志文件的 ``html.escape`` 保持一致。
    """
    escaped = []
    for row in rows:
        if isinstance(row, dict):
            escaped.append({k: (html.escape(v) if isinstance(v, str) else v)
                            for k, v in row.items()})
        else:
            escaped.append(row)
    return escaped

def getAuditLogsFiles():
    log_dir = _LOG_DIR
    log_files = []
    try:
        entries = os.listdir(log_dir)
    except OSError as e:
        yf.writeFileLog('[adult_log] 读取日志目录失败: %s' % e)
        return log_files

    def _collect(name, size, path, uptime):
        log_files.append({
            'name': name,
            'size': size,
            'log_file': path,
            'title': getLogsTitle(name),
            'uptime': uptime,
        })

    for log_file in entries:
        if log_file in ('.', '..'):
            continue
        if log_file.rsplit('.', 1)[-1] in ('gz', 'xz', 'bz2', 'asl'):
            continue

        filename = os.path.join(log_dir, log_file)
        try:
            if not os.path.exists(filename):
                continue

            if os.path.isfile(filename):
                file_size = os.path.getsize(filename)
                if file_size:
                    _collect(log_file, file_size, filename, os.path.getmtime(filename))
                continue

            # 子目录（如 /var/log/nginx）：权限不足或被并发删除时跳过，不影响其它日志
            for next_name in os.listdir(filename):
                if next_name[-3:] in ('.gz', '.xz'):
                    continue
                next_file = os.path.join(filename, next_name)
                if not os.path.isfile(next_file):
                    continue
                file_size = os.path.getsize(next_file)
                if not file_size:
                    continue
                log_name = '{}/{}'.format(log_file, next_name)
                _collect(log_name, file_size, next_file, os.path.getmtime(next_file))
        except OSError as e:
            # 权限不足 / 文件被并发删除：跳过并记录，不让单条异常弄崩整个列表
            yf.writeFileLog('[adult_log] 跳过日志 %s: %s' % (filename, e))
            continue

    log_files = sorted(log_files, key=lambda x: x['name'], reverse=True)
    return log_files

def __to_date2(date_str):
    tmp = (date_str or '').split()
    if len(tmp) < 4:
        # 列塌缩 / 本地化：退化为原文，绝不抛 IndexError（否则整个接口 500）
        return (date_str or '').strip() or '-'
    s_date = str(tmp[-1]) + '-' + __months.get(tmp[1], tmp[1]) + '-' + tmp[2] + ' ' + tmp[3]
    return s_date


def __to_date3(date_str):
    tmp = (date_str or '').split()
    if len(tmp) < 4:
        return (date_str or '').strip() or '-'
    s_date = str(datetime.now().year) + '-' + __months.get(tmp[1], tmp[1]) + '-' + tmp[2] + ' ' + tmp[3]
    return s_date


def __to_date4(date_str):
    tmp = (date_str or '').split()
    if len(tmp) < 3:
        return (date_str or '').strip() or '-'
    s_date = str(datetime.now().year) + '-' + __months.get(tmp[0], tmp[0]) + '-' + tmp[1] + ' ' + tmp[2]
    return s_date

def __parse_last_line(_line):
    """解析 ``last``（wtmp/btmp/utmp）的一行；字段不足时返回 None，不抛异常。"""
    sp_arr = _line.split()
    if not sp_arr:
        return None
    tmp = {'用户': sp_arr[0]}
    if sp_arr[0] == 'runlevel':
        if len(sp_arr) < 5:
            return None
        tmp['来源'] = sp_arr[4]
        tmp['端口'] = ' '.join(sp_arr[1:4])
        tmp['时间'] = __to_date3(' '.join(sp_arr[5:])) + ' ' + ' '.join(sp_arr[-2:])
    elif sp_arr[0] in ['reboot', 'shutdown']:
        if len(sp_arr) < 4:
            return None
        tmp['来源'] = sp_arr[3]
        tmp['端口'] = ' '.join(sp_arr[1:3])
        if sp_arr[-3] == '-':
            tmp['时间'] = __to_date3(
                ' '.join(sp_arr[4:])) + ' ' + ' '.join(sp_arr[-3:])
        else:
            tmp['时间'] = __to_date3(
                ' '.join(sp_arr[4:])) + ' ' + ' '.join(sp_arr[-2:])
    elif len(sp_arr) > 1 and (sp_arr[1] in ['tty1', 'tty', 'tty2', 'tty3', 'hvc0', 'hvc1', 'hvc2'] or len(sp_arr) == 9):
        tmp['来源'] = ''
        tmp['端口'] = sp_arr[1]
        tmp['时间'] = __to_date3(' '.join(sp_arr[2:])) + ' ' + ' '.join(sp_arr[-3:])
    else:
        if len(sp_arr) < 3:
            return None
        tmp['来源'] = sp_arr[2]
        tmp['端口'] = sp_arr[1]
        tmp['时间'] = __to_date3(' '.join(sp_arr[3:])) + ' ' + ' '.join(sp_arr[-3:])
    return tmp


def getAuditLast(log_file):
    """读取 wtmp/btmp/utmp（``log_file`` 必须是 _safeLogPath 的返回值）。

    强制 ``LC_ALL=C``：否则本地化环境（LANGUAGE/LC_*）下 ``last`` 的月份名会变成本地
    语言，既解析错乱也可能直接抛异常。同时加超时，避免异常大的日志卡死工作线程。
    """
    cmd = "LC_ALL=C LANGUAGE=C last -n 200 -x -f {} | grep -v 127.0.0.1 | grep -v ' begins'".format(
        shlex.quote(log_file))
    result = yf.execShell(cmd, timeout=30)
    lastlog_list = []
    for _line in (result[0] or '').split("\n"):
        if not _line.strip():
            continue
        try:
            tmp = __parse_last_line(_line)
        except Exception as e:
            # 单行异常不能弄崩整个接口
            yf.writeFileLog('[adult_log] last 行解析失败: %r -> %s' % (_line, e))
            continue
        if tmp:
            lastlog_list.append(tmp)
    # lastlog_list = sorted(lastlog_list,key=lambda x:x['时间'],reverse=True)
    return yf.returnData(True, 'ok!', _escapeRows(lastlog_list))


def __parse_lastlog_fields(sp_arr):
    """从 lastlog 的空白切分结果里拆出 (端口, 来源, 日期串)。

    lastlog 的 Port/From 两列为空时会在输出里塌缩，不能死认下标，
    否则输出会错位（例如本机登录没有 From 时把星期名当成来源）。
    """
    rest = list(sp_arr[1:])
    port, src = '', ''
    if rest and ('/' in rest[0] or rest[0][:3] in ('tty', 'hvc', 'pts')):
        port = rest.pop(0)
    if rest and rest[0][:3] not in __months and rest[0] not in _WEEKDAYS:
        src = rest.pop(0)
    return port, src, ' '.join(rest)


def __parse_lastlog_line(_line):
    """解析 lastlog 的一行；无法解析时按「从未登录」处理（绝不抛异常）。"""
    sp_arr = _line.split()
    if not sp_arr:
        return None
    user = sp_arr[0]
    rest = sp_arr[1:]
    has_date = any(tok[:3] in __months or tok in _WEEKDAYS for tok in rest)
    if _NEVER_LOGGED_RE.search(_line) or not has_date:
        # 结构判据：有效登录记录一定带「月份/星期 + 日期」。
        # 本地化提示语（如「**从未登录过**」）无法依赖英文文案，故用结构判定。
        return {'用户': user, '最后登录时间': '0',
                '最后登录来源': '-', '最后登录端口': '-'}
    port, src, date_str = __parse_lastlog_fields(sp_arr)
    return {'用户': user,
            '最后登录来源': src or '-',
            '最后登录端口': port or '-',
            '最后登录时间': __to_date2(date_str)}


def getAuditLastLog():
    cmd = 'LC_ALL=C LANGUAGE=C lastlog | grep -v Username'
    result = yf.execShell(cmd, timeout=30)
    lastlog_list = []
    for _line in (result[0] or '').split("\n"):
        if not _line.strip():
            continue
        try:
            tmp = __parse_lastlog_line(_line)
        except Exception as e:
            yf.writeFileLog('[adult_log] lastlog 行解析失败: %r -> %s' % (_line, e))
            continue
        if tmp:
            lastlog_list.append(tmp)
    lastlog_list = sorted(lastlog_list, key=lambda x: x['最后登录时间'], reverse=True)
    for i in range(len(lastlog_list)):
        if lastlog_list[i]['最后登录时间'] == '0':
            lastlog_list[i]['最后登录时间'] = '从未登录过'
    return yf.returnData(True, 'ok!', _escapeRows(lastlog_list))

def parseAuditFileLine(log_name, _line):
    is_string = True
    if log_name.find('sa/sa') == -1:
        if _line[:3] in __months:
            _msg = _line[16:]
            _tmp = _msg.split(": ")
            # print('tmp: ',_tmp)
            _act = ''
            if len(_tmp) > 1:
                _act = _tmp[0]
                _msg = _tmp[1]
            else:
                _msg = _tmp[0]
            _line = {
                "时间": __to_date4(_line[:16].strip()),
                "角色": _act,
                "事件": _msg
            }
            is_string = False
        elif _line[:2] in ['19', '20', '21', '22', '23', '24']:
            # print(_line)
            _msg = _line[19:]
            _tmp = _msg.split(" ")
            _act = _tmp[1]
            _msg = ' '.join(_tmp[2:])
            _line = {
                "时间": _line[:19].strip(),
                "角色": _act,
                "事件": _msg
            }
            is_string = False
        elif log_name.find('alternatives') == 0:
            _tmp = _line.split(": ")
            _last = _tmp[0].split(" ")
            _act = _last[0]
            _msg = ' '.join(_tmp[1:])
            _line = {
                "时间": ' '.join(_last[1:]).strip(),
                "角色": _act,
                "事件": _msg
            }
            is_string = False
        else:
            if not is_string:
                if type(_line) != dict:
                    return _line
    return _line

def parseAuditFile(log_name, result):
    log_list = []
    for _line in result.split("\n"):
        if not _line.strip():
            continue
        try:
            _line = parseAuditFileLine(log_name, _line)
        except Exception as e:
            yf.writeFileLog(str(e))
        
        log_list.append(_line)
    return log_list

def getAuditLogsName(log_name):
    # 统一先校验：拒绝越权路径 / shell 元字符 / 绝对路径。
    # 校验失败与「文件不存在」返回同一提示，避免用错误信息探测路径是否存在。
    if not isinstance(log_name, str):
        return yf.returnData(False, 'logs.py_msg_c90f98')
    log_name = log_name.strip()
    log_file = _safeLogPath(log_name)
    if log_file is None:
        return yf.returnData(False, 'logs.py_msg_c90f98')

    # 与旧行为保持一致：按相对名前缀判定（路径已通过 _safeLogPath 校验）
    if log_name.startswith(('wtmp', 'btmp', 'utmp')):
        return getAuditLast(log_file)

    if log_name.startswith('lastlog'):
        return getAuditLastLog()

    if log_name.startswith('sa/sa'):
        if 'sar' not in log_name:
            # sar 输出可能很长，限制行数；shlex.quote 防命令注入
            cmd = "LC_ALL=C LANGUAGE=C sar -f {} | tail -n 500".format(
                shlex.quote(log_file))
            return html.escape(yf.execShell(cmd, timeout=30)[0] or '')

    if not os.path.exists(log_file):
        return yf.returnData(False, 'logs.py_msg_c90f98')
    result = yf.getLastLine(log_file, 100)
    try:
        log_list = parseAuditFile(log_name, result)
        _string = []
        _dict = []
        _list = []
        for _line in log_list:
            if isinstance(_line, str):
                _string.append(_line.strip())
            elif isinstance(_line, dict):
                _dict.append(_line)
            elif isinstance(_line, list):
                _list.append(_line)
            else:
                continue
        _str_len = len(_string)
        _dict_len = len(_dict)
        _list_len = len(_list)
        if _str_len > _dict_len + _list_len:
            return "\n".join(_string)
        elif _dict_len > _str_len + _list_len:
            return yf.returnData(True, 'ok!', _dict)
        else:
            return yf.returnData(True, 'ok!', _list)

    except Exception as e:
        # print(yf.getTracebackInfo())
        return yf.returnData(True, 'ok!', result)

def getLogsTitle(log_name):
    from core.i18n import t as _t

    log_name = log_name.replace('.1', '')
    if log_name in ['mw-update.log', 'yf-update.log']:
        return _t('TITLE_PANEL_UPDATE')
    if log_name in ['mw-install.log', 'yf-install.log']:
        return _t('TITLE_PANEL_INSTALL')
    if log_name in ['auth.log', 'secure'] or log_name.find('auth.') == 0:
        return _t('TITLE_AUTH')
    if log_name in ['dmesg'] or log_name.find('dmesg') == 0:
        return _t('TITLE_DMESG')
    if log_name in ['syslog'] or log_name.find('syslog') == 0:
        return _t('TITLE_SYSLOG')
    if log_name in ['rsyncd.log']:
        return _t('TITLE_RSYNCD')
    if log_name in ['btmp']:
        return _t('TITLE_BTMP')
    if log_name in ['utmp', 'wtmp']:
        return _t('TITLE_WTMP')
    if log_name in ['lastlog']:
        return _t('TITLE_LASTLOG')
    if log_name in ['yum.log']:
        return _t('TITLE_YUM')
    if log_name in ['anaconda.log']:
        return _t('TITLE_ANACONDA')
    if log_name in ['dpkg.log']:
        return _t('TITLE_DPKG')
    if log_name in ['daemon.log']:
        return _t('TITLE_DAEMON')
    if log_name in ['boot.log']:
        return _t('TITLE_BOOT')
    if log_name in ['kern.log']:
        return _t('TITLE_KERN')
    if log_name in ['maillog', 'mail.log']:
        return _t('TITLE_MAIL')
    if log_name.find('Xorg') == 0:
        return _t('TITLE_XORG')
    if log_name in ['cron.log']:
        return _t('TITLE_CRON')
    if log_name in ['alternatives.log']:
        return _t('TITLE_ALTERNATIVES')
    if log_name in ['debug']:
        return _t('TITLE_DEBUG')
    if log_name.find('apt') == 0:
        return _t('TITLE_APT')
    if log_name.find('installer') == 0:
        return _t('TITLE_INSTALLER')
    if log_name in ['messages']:
        return _t('TITLE_MESSAGES')
    return _t('TITLE_GENERIC', log_name.split('.')[0])