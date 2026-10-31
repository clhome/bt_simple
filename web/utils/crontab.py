# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import sys
import re
import time
import json
import threading
import multiprocessing

import core.yf as yf
import thisdb
import logging

_log = logging.getLogger('yf.crontab')
from core.i18n import t as _t


def _is_private_url(url):
    """兼容旧调用：URL 是否解析为内网/保留地址（含 DNS 解析校验）。

    校验组件异常时按“不安全”处理，绝不放过。
    """
    try:
        from utils.urlguard import validate_url
        ok, _err, _meta = validate_url(url, resolve=True)
        return not ok
    except Exception:
        return True


def _validate_to_url(url):
    try:
        from utils.urlguard import validate_url
        ok, err, _meta = validate_url(url, resolve=True)
        return ok, (err if not ok else 'OK')
    except Exception as e:
        return False, _t('crontab.url_err_validate_failed', str(e))


# 周期字段最终会被拼进 /var/spool/cron/crontabs/root 的同一行：
# 只要混入换行/分号就能给 root 追加任意计划任务（或让整份 crontab 语法出错）。
# 因此这里只接受纯数字，其余一律拒绝。
_CRON_INT_RE = re.compile(r'^\d{1,4}$')
_CRON_LINE_FIELD_RE = re.compile(r'^(?:\*(?:/\d{1,4})?|\d{1,4}(?:-\d{1,4})?(?:/\d{1,4})?|\d{1,4}(?:,\d{1,4})*)$')
_PLUGIN_DIR_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]+$')
# 脚本文件名（DB 的 echo 列）白名单：该值既是 /www/server/cron/<name> 的文件名，
# 又会被拼进 root crontab 行。历史数据里存在 echo=原始命令（init_cron 恢复
# 「其它系统任务」时写入），含空格/分号/换行/重定向符就会污染文件名并给 root
# 追加任意计划任务，因此只接受纯标识符，其余一律拒绝。
_CRON_NAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
CRON_CYCLE_TYPES = ('day', 'day-n', 'hour', 'hour-n', 'minute-n', 'week', 'month')
CRON_TASK_STYPES = ('toShell', 'toFile', 'toUrl', 'rememory', 'logs', 'site', 'path', 'database')

# 手动执行（面板「执行」按钮 / startTask）用的环境开关：脚本里「执行时段限制」
# 「日期类型限制」这两段前置判定只拦 cron 触发，手动执行必须立刻跑，
# 否则「每N分钟执行(限制: 从09:00起)」的任务点执行只会写一条「跳过执行」。
CRON_FORCE_ENV = 'YF_CRON_FORCE'
# 脚本里的能力标记：存量脚本没有它说明是旧版（不认 CRON_FORCE_ENV），
# startTask 会就地把脚本重生一次（自愈，不必让用户重新保存任务）。
CRON_FORCE_MARKER = '#YF_CRON_FORCE_SUPPORTED'


def _cron_safe_name(echo):
    """把 echo 收敛为合法脚本名；不合规（空格/分号/换行/路径分隔符等）返回空串拒绝。"""
    name = str(echo if echo is not None else '').strip()
    if name in ('.', '..') or not _CRON_NAME_RE.match(name):
        return ''
    return name


# 任务标识不可用于同步的原因码（前端/接口只需认这一个字符串，不必解析文案）。
CRON_SYNC_REASON_NAME_INVALID = 'cron_name_invalid'


def cron_name_status(echo):
    """任务标识（DB 的 echo 列）能否用于同步 —— 列表展示与同步路径共用同一判据。

    判据**只有一个**：`_cron_safe_name()`（即 `_CRON_NAME_RE` 白名单）。这里刻意不另写
    正则，避免「列表说能同步、同步时又被拒」这种两套口径。

    返回 dict（字段名直接用 sync_ 前缀，前端无需再包一层）：
      * 合规：`{'sync_ok': True, 'sync_reason': '', 'sync_reason_code': ''}`
      * 被拒：`{'sync_ok': False, 'sync_reason': <指引文案>, 'sync_reason_code': 'cron_name_invalid'}`

    背景：白名单上线前，`init_cron` 恢复「其它系统任务」时会把**原始命令**写进 echo，
    这类历史任务在同步时被 `getShell()` 静默拒绝（只写日志），用户看不到它已经停摆。
    """
    if _cron_safe_name(echo):
        return {'sync_ok': True, 'sync_reason': '', 'sync_reason_code': ''}
    return {
        'sync_ok': False,
        'sync_reason': _t(
            'crontab.cron_sync_rejected_tip',
            '任务标识含非法字符（仅允许 A-Za-z0-9_.-，最长 64），同步时会被拒绝；'
            '请编辑任务重新保存以生成合规标识'),
        'sync_reason_code': CRON_SYNC_REASON_NAME_INVALID,
    }


def _cron_int(value, lo, hi):
    """周期字段必须是非负纯数字且落在 [lo, hi]；'-1'、'abc'、'1\n* * * * *' 一律不合法。"""
    val = str(value if value is not None else '').strip()
    if not _CRON_INT_RE.match(val):
        return False
    return lo <= int(val) <= hi


def _valid_cron_line(line):
    """写入系统 crontab 前的最后一道闸：必须是单行、且前 5 段都是合法 cron 字段。"""
    if not line or '\n' in line or '\r' in line:
        return False
    parts = line.split()
    if len(parts) < 6:
        return False
    return all(_CRON_LINE_FIELD_RE.match(p) for p in parts[:5])


class crontab(object):
        # lock
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(crontab, "_instance"):
            with crontab._instance_lock:
                if not hasattr(crontab, "_instance"):
                    crontab._instance = crontab(*args, **kwargs)
        return crontab._instance

    def modifyCrond(self,cron_id,data):
        if len(data['name']) < 1:
            return yf.returnData(False, 'crontab.py_msg_db5b0f')

        is_check_pass, msg = self.cronCheck(data)
        if not is_check_pass:
            return yf.returnData(is_check_pass, msg)

        info = thisdb.getCrond(cron_id)
        if info is None:
            return yf.returnData(False, 'common.param_error')

        dbdata = {}
        dbdata['name'] = data['name']
        dbdata['type'] = data['type']
        dbdata['where1'] = data['where1']
        dbdata['where_hour'] = data['hour']
        dbdata['where_minute'] = data['minute']
        dbdata['stype'] = data['stype']

        dbdata['sname'] = yf.getDefault(data, 'sname', '')
        dbdata['backup_to'] = yf.getDefault(data, 'backup_to', '')
        dbdata['save'] = yf.getDefault(data, 'save', '')
        dbdata['sbody'] = yf.getDefault(data, 'sbody', '')
        dbdata['url_address'] = yf.getDefault(data, 'url_address', '')
        dbdata['attr'] = yf.getDefault(data, 'attr', '')
        dbdata['day_type'] = yf.getDefault(data, 'day_type', '0')
        
        dbdata['min_start_en'] = yf.getDefault(data, 'min_start_en', '0')
        dbdata['min_start_h'] = yf.getDefault(data, 'min_start_h', '0')
        dbdata['min_start_m'] = yf.getDefault(data, 'min_start_m', '0')
        dbdata['min_end_en'] = yf.getDefault(data, 'min_end_en', '0')
        dbdata['min_end_h'] = yf.getDefault(data, 'min_end_h', '23')
        dbdata['min_end_m'] = yf.getDefault(data, 'min_end_m', '59')

        # 历史任务的 echo 可能是原始命令（老版本恢复「其它系统任务」时写入），白名单上线后
        # 这类任务永远同步不成功。既然只能靠「重新保存」来修，保存时就顺手换一个新合规标识：
        # 判据仍是 _cron_safe_name()（不另写规则），旧标识对应的 crontab 行在下面先被删掉。
        if not _cron_safe_name(info.get('echo')):
            dbdata['echo'] = yf.md5(yf.md5(str(time.time()) + '_yf'))

        if not self.removeForCrond(info['echo']):
            return yf.returnData(False, 'crontab.py_msg_9b5111')

        thisdb.setCrontabData(cron_id, dbdata)
        if not self.syncToCrond(cron_id) and str(info.get('status', 1)) != '0':
            return yf.returnData(False, 'crontab.py_msg_9b5111')
        msg = _t('crontab.modify_success', data['name'])
        yf.writeLog('计划任务', msg)
        return yf.returnData(True, msg)

    # 取数据列表
    def getDataList(self,stype=''):
    
        bak_data = []
        if stype == 'site' or stype == 'sites' or stype == 'database' or stype.find('database_') > -1 or stype == 'path':
            bak_data = thisdb.getOptionByJson('hook_backup',type='hook', default=[])

        if stype == 'database' or stype.find('database_') > -1:
            sqlite3_name = 'mysql'
            path = yf.getServerDir() + '/mysql'
            if stype != 'database':
                soft_name = stype.replace('database_', '')
                path = yf.getServerDir() + '/' + soft_name

                if soft_name == 'postgresql':
                    sqlite3_name = 'pgsql'

                if soft_name == 'mongodb':
                    sqlite3_name = 'mongodb'

            db_list = {}
            db_list['orderOpt'] = bak_data

            if not os.path.exists(path + '/' + sqlite3_name + '.db'):
                db_list['data'] = []
            else:
                db_list['data'] = yf.M('databases').dbPos(path, sqlite3_name).field('name,ps').select()
            return db_list

        if stype == 'path':
            db_list = {}
            db_list['data'] = [{"name": yf.getWwwDir(), "ps": "www"}]
            db_list['orderOpt'] = bak_data
            return db_list

        data = {}
        data['orderOpt'] = bak_data

        default_db = 'sites'
        data['data'] = yf.M(default_db).field('name,ps').select()
        return data

    def setCronStatus(self,cron_id):
        data = thisdb.getCrond(cron_id)
        if data is None:
            return yf.returnData(False, 'common.param_error')

        status = 1
        status_msg = '开启'
        if data['status'] == status:
            status = 0
            status_msg = '关闭'
            thisdb.setCrontabStatus(cron_id, status)
            self.removeForCrond(data['echo'])
        else:
            data['status'] = 1
            thisdb.setCrontabData(cron_id, data)
            if not self.syncToCrond(cron_id):
                # 写盘失败时不能留下「库里已启用、系统里没有」的假状态
                thisdb.setCrontabStatus(cron_id, 0)
                return yf.returnData(False, 'crontab.py_msg_9b5111')

        msg = '修改计划任务[' + data['name'] + ']状态为[' + str(status_msg) + ']'
        yf.writeLog('计划任务', msg)
        return yf.returnJson(True, msg)


    def cronLog(self, cron_id):
        data = thisdb.getCrond(cron_id)
        if data is None:
            return yf.returnData(False, 'common.param_error')
        log_file = yf.getServerDir() + '/cron/' + data['echo'] + '.log'
        if not os.path.exists(log_file):
            return yf.returnData(True, '')
        content = yf.getLastLine(log_file, 500)
        return yf.returnData(True, content)

    def _rotate_cron_log(self, log_file, max_bytes=10 * 1024 * 1024, keep=3):
        try:
            if os.path.exists(log_file) and os.path.getsize(log_file) > max_bytes:
                for i in range(keep - 1, 0, -1):
                    src = f"{log_file}.{i}"
                    dst = f"{log_file}.{i + 1}"
                    if os.path.exists(src):
                        try:
                            os.replace(src, dst)
                        except Exception as _e:
                            _log.debug('[crontab] 轮转日志失败: %s', _e)
                try:
                    os.replace(log_file, f"{log_file}.1")
                except Exception as _e:
                    _log.debug('[crontab] 轮转主日志失败: %s', _e)
        except Exception as _e:
            _log.debug('[crontab] 读取日志目录失败: %s', _e)

    def _cron_pid_file(self, cron_id):
        return os.path.join(yf.getPanelTmp(), f"cron_{cron_id}.pid")

    def cleanupStaleCron(self, cron_id, timeout_sec=3600):
        try:
            pf = self._cron_pid_file(cron_id)
            if not os.path.exists(pf):
                return False
            pid = int(yf.readFile(pf).strip() or "0")
            if pid and yf.checkPid(pid):
                try:
                    mtime = os.path.getmtime(pf)
                    if time.time() - mtime > timeout_sec:
                        self.killProcessTree(pid)
                        yf.writeFileLog(f"[crontab] killed stale cron {cron_id} pid={pid} after {timeout_sec}s\n")
                        return True
                except Exception as _e:
                    yf.writeFileLog('[crontab] 清理残留 cron 进程失败: %s' % _e)
            else:
                try:
                    os.remove(pf)
                except Exception as _e:
                    _log.debug('[crontab] 清理 PID 文件失败: %s', _e)
            return False
        except Exception:
            return False

    def _is_task_process(self, pid, echo):
        """校验指定 PID 进程是否属于目标任务（防止 PID 复用误杀）。"""
        try:
            if not pid or pid <= 0 or not echo:
                return False

            def match_cmdline(cmd_str):
                if not cmd_str or echo not in cmd_str:
                    return False
                if f'/cron/{echo}' in cmd_str or f'\\cron\\{echo}' in cmd_str:
                    return True
                pattern = r'(?:[\s/\"\'\\]|\bcron[/\\])' + re.escape(echo) + r'(?:\.sh|\.bat|[\s\"\'\x00]|$)'
                return bool(re.search(pattern, cmd_str))

            cmdline_path = f"/proc/{pid}/cmdline"
            if os.path.exists(cmdline_path):
                try:
                    with open(cmdline_path, 'rb') as f:
                        raw = f.read().decode('utf-8', errors='ignore')
                        return match_cmdline(raw)
                except Exception:
                    return False
            try:
                import psutil
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    cmd = ' '.join(p.cmdline())
                    return match_cmdline(cmd)
            except Exception as _e:
                _log.debug('[crontab] psutil 检查任务进程异常: %s', _e)

            # 当系统既无 /proc 伪文件系统也无 psutil 时（如 Windows 最小化开发环境），
            # 降级信任存活的 PID 记录
            if not os.path.exists('/proc'):
                return True

            return False
        except Exception:
            return False

    def _scan_task_pid_by_echo(self, echo):
        """扫描系统进程列表，通过脚本特征名 echo 反查当前运行中的主进程 PID。
        
        具备强关联路径二次校验与多进程冲突防护（发现多候选时拒绝执行并告警）。
        """
        try:
            if not echo:
                return None

            candidates = set()

            def match_cmdline(cmd_str):
                if not cmd_str or echo not in cmd_str:
                    return False
                # 强关联校验：必须包含 cron/{echo} 路径或强脚本边界，杜绝随意包含 echo 子串的无关进程
                if f'/cron/{echo}' in cmd_str or f'\\cron\\{echo}' in cmd_str:
                    return True
                pattern = r'(?:[\s/\"\'\\]|\bcron[/\\])' + re.escape(echo) + r'(?:\.sh|\.bat|[\s\"\'\x00]|$)'
                return bool(re.search(pattern, cmd_str))

            if os.path.exists('/proc'):
                for entry in os.listdir('/proc'):
                    if entry.isdigit():
                        try:
                            cmd_path = f"/proc/{entry}/cmdline"
                            if os.path.exists(cmd_path):
                                with open(cmd_path, 'rb') as f:
                                    raw = f.read().decode('utf-8', errors='ignore')
                                    if match_cmdline(raw):
                                        p_int = int(entry)
                                        if yf.checkPid(p_int):
                                            candidates.add(p_int)
                        except Exception:
                            continue
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info.get('cmdline') or [])
                        if match_cmdline(cmdline):
                            p_int = proc.info.get('pid')
                            if p_int and yf.checkPid(p_int):
                                candidates.add(p_int)
                    except Exception:
                        continue
            except Exception as _e:
                _log.debug('[crontab] psutil 扫描任务 PID 异常: %s', _e)

            if not candidates:
                return None
            if len(candidates) == 1:
                return list(candidates)[0]

            # 命中多个匹配 PID：存在混淆与误杀风险，拒绝盲目执行并记录告警 (P1-5)
            _log.warning('[crontab] 扫描任务(echo=%s)命中多个候选进程 %s，为防误杀拒绝执行', echo, sorted(list(candidates)))
            return None
        except Exception as _e:
            _log.debug('[crontab] 扫描任务 PID 异常: %s', _e)
            return None

    def findTaskPid(self, cron_id):
        """查找指定任务当前正在运行的主进程 PID。

        返回 (pid, task_info)：
          * 若找到存活主进程：返回 (pid, task_info)
          * 若未在运行或任务不存在：返回 (None, task_info)
        """
        try:
            data = thisdb.getCrond(cron_id)
            if not data:
                return None, None
            echo = str(data.get('echo') or '').strip()
            if not echo:
                return None, data

            pf = self._cron_pid_file(cron_id)
            if os.path.exists(pf):
                try:
                    raw_pid = (yf.readFile(pf) or '').strip()
                    if raw_pid.isdigit():
                        candidate_pid = int(raw_pid)
                        if candidate_pid > 0 and yf.checkPid(candidate_pid):
                            if self._is_task_process(candidate_pid, echo):
                                return candidate_pid, data
                        try:
                            os.remove(pf)
                        except Exception as _e:
                            _log.debug('[crontab] 移除死进程 PID 文件异常: %s', _e)
                except Exception as _e:
                    _log.debug('[crontab] 读取 PID 文件异常: %s', _e)

            matched_pid = self._scan_task_pid_by_echo(echo)
            if matched_pid:
                try:
                    yf.writeFile(pf, str(matched_pid))
                except Exception as _e:
                    _log.debug('[crontab] 写入 PID 文件异常: %s', _e)
                return matched_pid, data

            return None, data
        except Exception as _e:
            _log.debug('[crontab] findTaskPid 异常: %s', _e)
            return None, None

    def killProcessTree(self, main_pid):
        """彻底终止目标主进程及其派生出的所有子孙进程树。"""
        if not main_pid or main_pid <= 0:
            return False

        target_pids = set()
        target_pids.add(main_pid)

        try:
            import psutil
            if psutil.pid_exists(main_pid):
                p = psutil.Process(main_pid)
                for child in p.children(recursive=True):
                    target_pids.add(child.pid)
        except Exception as _e:
            _log.debug('[crontab] psutil 获取子进程树异常: %s', _e)

        if os.path.exists('/proc'):
            try:
                parent_map = {}
                for entry in os.listdir('/proc'):
                    if entry.isdigit():
                        try:
                            stat_path = f"/proc/{entry}/stat"
                            if os.path.exists(stat_path):
                                with open(stat_path, 'r', encoding='utf-8', errors='ignore') as sf:
                                    content = sf.read()
                                    rparen = content.rfind(')')
                                    if rparen != -1:
                                        fields = content[rparen + 1:].split()
                                        if len(fields) >= 2:
                                            ppid = int(fields[1])
                                            parent_map.setdefault(ppid, []).append(int(entry))
                        except Exception:
                            continue

                queue = list(target_pids)
                while queue:
                    curr = queue.pop(0)
                    for ch in parent_map.get(curr, []):
                        if ch not in target_pids:
                            target_pids.add(ch)
                            queue.append(ch)
            except Exception as _e:
                _log.debug('[crontab] /proc 构建进程树异常: %s', _e)

        import signal as _sig
        term_sig = getattr(_sig, 'SIGTERM', 15)

        # 仅当目标进程本身就是独立的进程组组长（例如以 start_new_session=True / setsid 启动），
        # 且该组非当前运行进程的进程组（杜绝误杀调用者自身、父进程、Web 面板服务或 CI runner 门禁）时，才允许向该进程组广播信号。
        can_killpg = False
        target_pgid = None
        if hasattr(os, 'killpg') and hasattr(os, 'getpgid') and not yf.isAppleSystem() and os.name != 'nt':
            try:
                pgid = os.getpgid(main_pid)
                cur_pgrp = os.getpgrp() if hasattr(os, 'getpgrp') else os.getpgid(0)
                if pgid and pgid == main_pid and pgid > 1 and pgid != cur_pgrp:
                    can_killpg = True
                    target_pgid = pgid
            except Exception as _e:
                _log.debug('[crontab] 获取进程组 ID 异常: %s', _e)

        if can_killpg and target_pgid:
            try:
                os.killpg(target_pgid, term_sig)
            except Exception as _e:
                _log.debug('[crontab] 向进程组发送 SIGTERM 失败: %s', _e)

        for p in list(target_pids):
            try:
                if yf.checkPid(p):
                    try:
                        import psutil
                        if psutil.pid_exists(p):
                            psutil.Process(p).terminate()
                    except Exception as _ep:
                        _log.debug('[crontab] psutil terminate 异常: %s', _ep)
                    if yf.checkPid(p) and hasattr(os, 'kill'):
                        os.kill(p, term_sig)
            except Exception as _e:
                _log.debug('[crontab] 发送 SIGTERM 到 PID %s 失败: %s', p, _e)

        deadline = time.time() + 1.5
        all_dead = False
        while time.time() < deadline:
            alive = [p for p in target_pids if yf.checkPid(p)]
            if not alive:
                all_dead = True
                break
            time.sleep(0.15)

        if not all_dead:
            if can_killpg and target_pgid:
                try:
                    kill_sig = getattr(_sig, 'SIGKILL', term_sig)
                    os.killpg(target_pgid, kill_sig)
                except Exception as _e:
                    _log.debug('[crontab] 向进程组发送 SIGKILL 失败: %s', _e)

            for p in target_pids:
                try:
                    if yf.checkPid(p):
                        try:
                            import psutil
                            if psutil.pid_exists(p):
                                psutil.Process(p).kill()
                        except Exception as _ep:
                            _log.debug('[crontab] psutil kill 异常: %s', _ep)
                        if yf.checkPid(p) and hasattr(os, 'kill'):
                            kill_sig = getattr(_sig, 'SIGKILL', term_sig)
                            os.kill(p, kill_sig)
                except Exception as _e:
                    _log.debug('[crontab] 强制终止 PID %s 失败: %s', p, _e)

            if sys.platform == 'win32':
                try:
                    import subprocess as _sp
                    for p in target_pids:
                        if yf.checkPid(p):
                            _sp.run(['taskkill', '/F', '/T', '/PID', str(p)], capture_output=True)
                except Exception as _e:
                    _log.debug('[crontab] win32 taskkill 异常: %s', _e)

        # 终极复验：轮询等待并确认目标进程是否全部死亡 (P1-5)
        deadline = time.time() + 1.5
        while time.time() < deadline:
            still_alive = [p for p in target_pids if yf.checkPid(p)]
            if not still_alive:
                return True
            time.sleep(0.1)

        still_alive = [p for p in target_pids if yf.checkPid(p)]
        if still_alive:
            _log.error('[crontab] 强制终止信号发送后仍有残留存活进程: %s', still_alive)
            return False

        return True

    def killTask(self, cron_id):
        """紧急终止指定计划任务。"""
        try:
            main_pid, data = self.findTaskPid(cron_id)
            if not data:
                return yf.returnData(False, 'common.param_error')

            if not main_pid:
                pf = self._cron_pid_file(cron_id)
                if os.path.exists(pf):
                    try:
                        os.remove(pf)
                    except Exception as _e:
                        _log.debug('[crontab] 移除 PID 文件异常: %s', _e)
                return yf.returnData(False, 'crontab.task_not_running')

            killed_ok = self.killProcessTree(main_pid)
            if not killed_ok or yf.checkPid(main_pid):
                return yf.returnData(False, 'crontab.task_terminated_failed', None, f'进程 PID {main_pid} 无法终止（仍在运行或处于不可中断状态）')

            pf = self._cron_pid_file(cron_id)
            try:
                if os.path.exists(pf):
                    os.remove(pf)
            except Exception as _e:
                _log.debug('[crontab] 清理 PID 文件失败: %s', _e)

            try:
                echo = str(data.get('echo') or '').strip()
                if echo:
                    log_file = os.path.join(yf.getServerDir(), 'cron', echo + '.log')
                    end_date = yf.formatDate()
                    append_log = f"\n----------------------------------------------------------------------------\n★[{end_date}] 任务已被手动紧急终止 (PID: {main_pid})\n----------------------------------------------------------------------------\n"
                    with open(log_file, 'a', encoding='utf-8') as lf:
                        lf.write(append_log)
            except Exception as _e:
                _log.debug('[crontab] 写入终止日志异常: %s', _e)

            yf.writeLog('计划任务', f"紧急终止任务[{data.get('name', cron_id)}], PID: {main_pid}")

            return yf.returnData(True, 'crontab.task_terminated_success', str(main_pid), str(main_pid))
        except Exception as e:
            _log.error('[crontab] killTask 异常: %s', e)
            return yf.returnData(False, 'crontab.task_terminated_failed', None, str(e))

    def _prepare_manual_run_script(self, cron_id, data, cmd_file):
        """手动执行前把脚本准备好（**只碰 /www/server/cron 下的脚本文件，不碰系统 crontab**）。

        三种情况：
          * 脚本已存在且带能力标记（`CRON_FORCE_MARKER`）→ 直接用；
          * 脚本已存在但没标记（升级前生成的旧脚本，时段限制无条件生效）→ 重生一次；
          * 脚本不存在（停用中的任务，或历史同步被拒）→ 仅生成脚本文件。
            停用任务手动执行也要能立刻跑，所以这里**不能**走 syncToCrond：
            status=0 会被它直接拒掉，写 crontab 还会把「停用」复活。

        返回 False 表示脚本确实生成不出来（echo 未过白名单 / 写盘失败 / toFile 脚本丢失）。
        写盘走 getShell → yf.writeFile（临时文件 + os.replace 原子替换），
        正在执行的那一份拿着旧 inode，不会被改写打断。
        """
        existed = os.path.exists(cmd_file)
        if existed:
            try:
                if CRON_FORCE_MARKER in (yf.readFile(cmd_file) or ''):
                    return True
            except Exception as _e:
                _log.debug('[crontab] 读取任务脚本失败（任务 %s）: %s', cron_id, _e)
                return False
            # toFile：脚本内容是用户自己上传的整份文件，没有我们生成的头部，
            # 重生会把它覆盖掉（param 里也没有 sFile）—— 直接不动。
            if str(data.get('stype', '')) == 'toFile':
                return True
        try:
            info = dict(data)
            if 'where_hour' in info:
                info['hour'] = info['where_hour']
                info['minute'] = info['where_minute']
                info['week'] = info['where1']
            name = self.getShell(info)
            if not name:
                return False
            if existed:
                yf.writeFileLog('[crontab] 任务 %s 的存量脚本已重生为支持手动执行（忽略时段限制）\n' % cron_id)
            else:
                yf.writeFileLog('[crontab] 任务 %s 的脚本不存在，已为手动执行重新生成\n' % cron_id)
            return True
        except Exception as _e:
            _log.debug('[crontab] 为手动执行准备脚本失败（任务 %s）: %s', cron_id, _e)
            return False

    def startTask(self, cron_id):
        data = thisdb.getCrond(cron_id)
        if data is None:
            return yf.returnData(False, 'common.param_error')
        cmd_file = yf.getServerDir() + '/cron/' + data['echo']
        if not self._prepare_manual_run_script(cron_id, data, cmd_file):
            # 没有脚本就不能假报「已执行」：否则用户看到成功、日志一行没新增。
            # 最常见原因是历史任务的 echo 未过白名单（提示编辑后重新保存）；
            # 其余情况（写盘失败/toFile 脚本丢失）提示文件写入失败。
            status = cron_name_status(data.get('echo'))
            if not status['sync_ok']:
                return yf.returnData(False, status['sync_reason'])
            return yf.returnData(False, 'crontab.py_msg_77c6a9')
        try:
            os.chmod(cmd_file, 0o750)
        except Exception as _e:
            _log.debug('[crontab] 设置任务脚本权限失败: %s', _e)
        import subprocess as _sp
        log_file = cmd_file + '.log'
        self._rotate_cron_log(log_file)
        self.cleanupStaleCron(cron_id)
        pid_file = self._cron_pid_file(cron_id)
        proc = None
        # 手动执行必须「立刻跑」：注入 CRON_FORCE_ENV=1，脚本里的
        # 执行时段限制/日期类型限制整段被跳过（cron 触发时不带这个变量，判定照旧）。
        env = dict(os.environ)
        env[CRON_FORCE_ENV] = '1'
        try:
            lf = open(log_file, 'a')
            proc = _sp.Popen([cmd_file], stdout=lf, stderr=_sp.STDOUT, start_new_session=True,
                             close_fds=True, env=env)
            try:
                yf.writeFile(pid_file, str(proc.pid))
            except Exception as _e:
                yf.writeFileLog('[crontab] 写 PID 文件失败（将无法跟踪该任务）: %s' % _e)
            try:
                lf.close()
            except Exception as _e:
                _log.debug('[crontab] 关闭日志句柄失败: %s', _e)
        except Exception as _e:
            try:
                # 兜底路径（Popen 失败时）同样要带开关；
                # 变量统一走 yf.shlexQuote，避免 shell 拼接（棘轮门禁要求）。
                yf.execShell(yf.shlexQuote(CRON_FORCE_ENV) + '=1 ' + yf.shlexQuote(cmd_file) + ' >> ' + yf.shlexQuote(log_file) + ' 2>&1 &')
            except Exception as _e2:
                yf.writeFileLog('[crontab] 启动任务脚本彻底失败: %s / %s' % (_e, _e2))
        thisdb.setCrontabData(cron_id, {'last_run_time': yf.formatDate()})
        return yf.returnData(True, 'crontab.py_msg_13a0ef', None, data['name'])


    # 获取指定任务数据
    def getCrondFind(self, cron_id):
        return thisdb.getCrond(cron_id)

    def add(self, data):
        if len(data['name']) < 1:
            return -1

        is_check_pass, msg = self.cronCheck(data)
        if not is_check_pass:
            return yf.returnData(is_check_pass, msg)

        # 1. 预先生成随机标识
        cron_name = yf.md5(yf.md5(str(time.time()) + '_yf'))
        data['echo'] = cron_name

        # 2. 构造数据库记录并插入以获取 tid
        add_dbdata = {}
        add_dbdata['name'] = data['name']
        add_dbdata['type'] = data['type']
        add_dbdata['where1'] = data['where1']
        add_dbdata['where_hour'] = data['hour']
        add_dbdata['where_minute'] = data['minute']
        add_dbdata['stype'] = data['stype']
        add_dbdata['echo'] = cron_name

        add_dbdata['sname'] = yf.getDefault(data, 'sname', '')
        add_dbdata['backup_to'] = yf.getDefault(data, 'backup_to', '')
        add_dbdata['save'] = yf.getDefault(data, 'save', '')
        add_dbdata['sbody'] = yf.getDefault(data, 'sbody', '')
        add_dbdata['url_address'] = yf.getDefault(data, 'url_address', '')
        add_dbdata['attr'] = yf.getDefault(data, 'attr', '')
        add_dbdata['day_type'] = yf.getDefault(data, 'day_type', '0')
        
        add_dbdata['min_start_en'] = yf.getDefault(data, 'min_start_en', '0')
        add_dbdata['min_start_h'] = yf.getDefault(data, 'min_start_h', '0')
        add_dbdata['min_start_m'] = yf.getDefault(data, 'min_start_m', '0')
        add_dbdata['min_end_en'] = yf.getDefault(data, 'min_end_en', '0')
        add_dbdata['min_end_h'] = yf.getDefault(data, 'min_end_h', '23')
        add_dbdata['min_end_m'] = yf.getDefault(data, 'min_end_m', '59')

        try:
            tid = thisdb.addCrontab(add_dbdata)
            
            # 3. 如果插入成功，通过 syncToCrond 完成脚本生成和系统同步
            if tid > 0:
                if not yf.isAppleSystem():
                    if not self.syncToCrond(tid):
                        # 写盘失败不能留下“库里有、系统里没有”的幽灵任务
                        thisdb.deleteCronById(tid)
                        return yf.returnData(False, 'crontab.py_msg_9b5111')
            return tid
        except Exception as e:
            return yf.returnData(False, 'utils.py_msg_788ddb', None, str(e))

    def delete(self, tid):
        data = thisdb.getCrond(tid)
        if data is None:
            return yf.returnData(False, 'common.param_error')
        if not self.removeForCrond(data['echo']):
            return yf.returnData(False, 'crontab.py_msg_9b5111')

        cron_path = yf.getServerDir() + '/cron'
        cron_file = cron_path + '/' + data['echo']

        if os.path.exists(cron_file):
            os.remove(cron_file)
        cron_file = cron_path + '/' + data['echo'] + '.log'
        if os.path.exists(cron_file):
            os.remove(cron_file)
        # 立即执行留下的 PID 文件随任务一起清理，避免长期残留在面板 tmp 目录
        try:
            pid_file = self._cron_pid_file(tid)
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception as _e:
            _log.debug('[crontab] 清理任务 PID 文件失败: %s', _e)

        thisdb.deleteCronById(tid)
        msg = _t('crontab.delete_success', data['name'])
        yf.writeLog('计划任务', msg)
        return yf.returnData(True, msg)


    def delLogs(self,cron_id):
        try:
            data = thisdb.getCrond(cron_id)
            if data is None:
                return yf.returnData(False, 'common.param_error')
            log_file = yf.getServerDir() + '/cron/' + data['echo'] + '.log'
            if os.path.exists(log_file):
                os.remove(log_file)
            return yf.returnData(True, 'crontab.py_msg_5d335f')
        except Exception as _e:
            return yf.returnData(False, 'crontab.py_msg_96779b')

    def getCrontabHuman(self, data):
        rdata = []
        week_keys = ('sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday')
        for i in range(len(data)):
            t = data[i]
            t['type_raw'] = t['type']
            if t['type'] == "day":
                t['type'] = _t('crontab.cycle_type_day')
                t['cycle'] = _t('crontab.cycle_desc_day', str(t['where_hour']), str(t['where_minute']))
            elif t['type'] == "day-n":
                t['type'] = _t('crontab.cycle_type_day_n', str(t['where1']))
                t['cycle'] = _t('crontab.cycle_desc_day_n', str(t['where1']), str(t['where_hour']), str(t['where_minute']))
            elif t['type'] == "hour":
                t['type'] = _t('crontab.cycle_type_hour')
                t['cycle'] = _t('crontab.cycle_desc_hour', str(t['where_minute']))
            elif t['type'] == "hour-n":
                t['type'] = _t('crontab.cycle_type_hour_n', str(t['where1']))
                t['cycle'] = _t('crontab.cycle_desc_hour_n', str(t['where1']), str(t['where_minute']))
            elif t['type'] == "minute-n":
                t['type'] = _t('crontab.cycle_type_minute_n', str(t['where1']))
                t['cycle'] = _t('crontab.cycle_desc_minute_n', str(t['where1']))
                if str(t.get('min_start_en', '0')) == '1' or str(t.get('min_end_en', '0')) == '1':
                    limit_str = []
                    if str(t.get('min_start_en', '0')) == '1':
                        limit_str.append(_t('crontab.cycle_limit_from', "%02d:%02d" % (int(t.get('min_start_h', 0)), int(t.get('min_start_m', 0)))))
                    if str(t.get('min_end_en', '0')) == '1':
                        limit_str.append(_t('crontab.cycle_limit_to', "%02d:%02d" % (int(t.get('min_end_h', 23)), int(t.get('min_end_m', 59)))))
                    t['cycle'] += _t('crontab.cycle_limit_wrap', " ".join(limit_str))
            elif t['type'] == "week":
                t['type'] = _t('crontab.cycle_type_week')
                if not t['where1']:
                    t['where1'] = '0'
                try:
                    weekday = _t('crontab.' + week_keys[int(t['where1']) % 7])
                except Exception:
                    weekday = ''
                t['cycle'] = _t('crontab.cycle_desc_week', weekday, str(t['where_hour']), str(t['where_minute']))
            elif t['type'] == "month":
                t['type'] = _t('crontab.cycle_type_month')
                t['cycle'] = _t('crontab.cycle_desc_month', str(t['where1']), str(t['where_hour']), str(t['where_minute']))
            
            # 获取上次执行时间
            if 'last_run_time' in t and t['last_run_time'] and t['last_run_time'] != 'None':
                t['last_run_time'] = t['last_run_time']
            else:
                log_file = yf.getServerDir() + '/cron/' + t['echo'] + '.log'
                if os.path.exists(log_file):
                    t['last_run_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(log_file)))
                else:
                    t['last_run_time'] = _t('crontab.never_run')

            # 获取特定日期类型限制
            day_type_map = {
                '0': _t('crontab.day_none'),
                '1': _t('crontab.day_stock'),
                '2': _t('crontab.day_workday'),
                '3': _t('crontab.day_holiday')
            }
            t['day_type_h'] = day_type_map.get(str(t.get('day_type', '0')), _t('crontab.day_none'))

            # 把「同步时会被拒绝」暴露到列表里：同步路径 getShell() 用的是同一个判据，
            # 历史 echo 为原始命令的任务否则会静默停摆（只留一条日志）。
            # 只新增 sync_ok / sync_reason / sync_reason_code，不动既有字段。
            t.update(cron_name_status(t.get('echo')))

            rdata.append(t)
        return rdata

    # 从crond删除（fcntl 排他锁 + 原子落盘 + 精确锚点，避免误删与竞态）
    def removeForCrond(self, echo):
        if yf.isAppleSystem():
            return True
        cron_files = ['/var/spool/cron/crontabs/root', '/var/spool/cron/root']
        cron_file = next((f for f in cron_files if os.path.exists(f)), '')
        if not cron_file:
            return False
        try:
            import fcntl
            safe_echo = re.escape(str(echo))
            # 精确匹配包含 yf_cron_{echo} 的整行，避免 re.sub(".+echo") 误删前缀相似任务
            pattern = re.compile(r'^.*' + safe_echo + r'.*\n?', re.MULTILINE)
            with open(cron_file, 'r+', encoding='utf-8', errors='ignore') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                content = f.read()
                new_content = pattern.sub('', content)
                if new_content == content:
                    fcntl.flock(f, fcntl.LOCK_UN)
                    return True
                f.seek(0); f.truncate(); f.write(new_content); f.flush()
                try: os.fsync(f.fileno())
                except Exception as _e: _log.debug('[crontab] fsync 失败: %s', _e)
                fcntl.flock(f, fcntl.LOCK_UN)
            self.crondReload()
            return True
        except Exception:
            # 回退旧路径（无锁）保证可用性
            try:
                content = yf.readFile(cron_file)
                rep = ".+" + re.escape(str(echo)) + ".+\n"
                content = re.sub(rep, "", content)
                if not yf.writeFile(cron_file, content):
                    return False
                self.crondReload()
                return True
            except Exception:
                return False

    def getCrontabList(self,
        page = 1,
        size = 10,
        search = '',
        orderby = 'last_run_time',
        order = 'desc'
    ):
        info = thisdb.getCrontabList(page=int(page),size=int(size), search=search, orderby=orderby, order=order)

        rdata = {}
        rdata['data'] = self.getCrontabHuman(info['list'])
        rdata['page'] = yf.getPage({'count':info['count'],'tojs':'getCronData','p':page,'row':size})


        # backup hook
        rdata['backup_hook'] = thisdb.getOptionByJson('hook_backup', type='hook', default=[])
        return rdata

    def getCrondCycle(self, params):
        cron_cmd = ''
        title = ''
        if params['type'] == "day":
            cron_cmd = self.getDay(params)
            title = _t('crontab.cycle_type_day')
        elif params['type'] == "day-n":
            cron_cmd = self.getDay_N(params)
            title = _t('crontab.cycle_type_day_n', str(params['where1']))
        elif params['type'] == "hour":
            cron_cmd = self.getHour(params)
            title = _t('crontab.cycle_type_hour')
        elif params['type'] == "hour-n":
            cron_cmd = self.getHour_N(params)
            title = _t('crontab.cycle_type_hour_n', str(params['where1']))
        elif params['type'] == "minute-n":
            cron_cmd = self.minute_N(params)
        elif params['type'] == "week":
            params['where1'] = params['week']
            cron_cmd = self.week(params)
        elif params['type'] == "month":
            cron_cmd = self.month(params)
        return cron_cmd, title

    # 转换大写星期
    def toWeek(self, num):
        wheres = {
            0:   '日',
            1:   '一',
            2:   '二',
            3:   '三',
            4:   '四',
            5:   '五',
            6:   '六'
        }
        try:
            return wheres[num]
        except Exception as _e:
            return ''

    # 取任务构造Day
    def getDay(self, param):
        cmd = "{0} {1} * * * ".format(param['minute'], param['hour'])
        return cmd

    # 取任务构造Day_n
    def getDay_N(self, param):
        cmd = "{0} {1} */{2} * * ".format(param['minute'], param['hour'], param['where1'])
        return cmd

    # 取任务构造Hour
    def getHour(self, param):
        cmd = "{0} * * * * ".format(param['minute'])
        return cmd

    # 取任务构造Hour-N
    def getHour_N(self, param):
        cmd = "{0} */{1} * * * ".format(param['minute'], param['where1'])
        return cmd

    # 取任务构造Minute-N
    def minute_N(self, param):
        cmd = "*/{0} * * * * ".format(param['where1'])
        return cmd

    # 取任务构造week
    def week(self, param):
        cmd = "{0} {1} * * {2}".format(param['minute'], param['hour'], param['week'])
        return cmd

    # 取任务构造Month
    def month(self, param):
        cmd = "{0} {1} {2} * * ".format(param['minute'], param['hour'], param['where1'])
        return cmd

    # 参数校验
    def cronCheck(self, params):
        stype = str(params.get('stype', '') or '')
        if stype not in CRON_TASK_STYPES and not stype.startswith('database_'):
            return False, 'crontab.the_form_is_invalid'
        if stype.startswith('database_') and not _PLUGIN_DIR_NAME_RE.match(stype[len('database_'):]):
            return False, 'crontab.the_form_is_invalid'
        if str(params.get('type', '') or '') not in CRON_CYCLE_TYPES:
            # 未知周期会生成空的时间字段，把整份 root crontab 写成语法错误
            return False, 'crontab.the_form_is_invalid'
        if params['stype'] == 'site' or params['stype'] == 'database' or params['stype'].find('database_') > -1 or params['stype'] == 'logs' or params['stype'] == 'path':
            if params['save'] == '':
                return False, 'crontab.py_msg_135668'
        if params.get('stype') == 'toUrl':
            ok, err = _validate_to_url(params.get('url_address', ''))
            if not ok:
                return False, err

        if params['type'] == 'day':
            if params['hour'] == '':
                return False, 'crontab.py_msg_d5d1dc'
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'

        if params['type'] == 'day-n':
            if params['where1'] == '':
                return False, 'crontab.py_msg_d510f5'
            if params['hour'] == '':
                return False, 'crontab.py_msg_d5d1dc'
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'
        if params['type'] == 'hour':
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'

        if params['type'] == 'hour-n':
            if params['where1'] == '':
                return False, 'crontab.py_msg_d5d1dc'
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'

        if params['type'] == 'minute-n':
            if params['where1'] == '':
                return False, 'crontab.py_msg_21159d'

        if params['type'] == 'week':
            if params['hour'] == '':
                return False, 'crontab.py_msg_d5d1dc'
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'

        if params['type'] == 'month':
            if params['where1'] == '':
                return False, 'crontab.py_msg_2519d7'
            if params['hour'] == '':
                return False, 'crontab.py_msg_d5d1dc'
            if params['minute'] == '':
                return False, 'crontab.py_msg_21159d'

        # 周期字段最终会拼进 /var/spool/cron/crontabs/root 的一行，
        # 只接受纯数字且在合法取值范围内（挡住换行注入与越界值）。
        if params['type'] in ('day', 'day-n', 'week', 'month'):
            if not _cron_int(params.get('hour'), 0, 23):
                return False, 'crontab.the_hour_is_invalid'
        if params['type'] != 'minute-n':
            if not _cron_int(params.get('minute'), 0, 59):
                return False, 'crontab.the_minute_is_invalid'
        if params['type'] == 'day-n' and not _cron_int(params.get('where1'), 1, 31):
            return False, 'crontab.the_form_is_invalid'
        if params['type'] == 'hour-n' and not _cron_int(params.get('where1'), 1, 23):
            return False, 'crontab.the_form_is_invalid'
        if params['type'] == 'minute-n' and not _cron_int(params.get('where1'), 1, 59):
            return False, 'crontab.the_form_is_invalid'
        if params['type'] == 'minute-n':
            for _k, _lo, _hi in (('min_start_en', 0, 1), ('min_start_h', 0, 23), ('min_start_m', 0, 59),
                                 ('min_end_en', 0, 1), ('min_end_h', 0, 23), ('min_end_m', 0, 59)):
                if str(params.get(_k, '') or '').strip() != '' and not _cron_int(params.get(_k), _lo, _hi):
                    return False, 'crontab.the_form_is_invalid'
        if params['type'] == 'month' and not _cron_int(params.get('where1'), 1, 31):
            return False, 'crontab.the_form_is_invalid'
        if params['type'] == 'week':
            week_val = params.get('week')
            if str(week_val or '').strip() == '':
                week_val = params.get('where1')
            if not _cron_int(week_val, 0, 6):
                return False, 'crontab.the_form_is_invalid'
        # save 会被拼进生成的 root 脚本，backup_to 会当插件目录名拼进脚本路径
        if str(params.get('save', '') or '').strip() != '' and not _cron_int(params.get('save'), 0, 9999):
            return False, 'crontab.the_form_is_invalid'
        backup_to = str(params.get('backup_to', '') or 'localhost').strip() or 'localhost'
        if backup_to != 'localhost' and not _PLUGIN_DIR_NAME_RE.match(backup_to):
            return False, 'crontab.the_form_is_invalid'
        return True, 'OK'


    # 取执行脚本
    def getShell(self, param):
        if not 'echo' in param:
            cron_name = yf.md5(yf.md5(str(time.time()) + '_yf'))
        else:
            cron_name = param['echo']
        # 白名单未通过时必须拒绝：否则 cron_name 会变成 /www/server/cron/<原始命令>
        # 这样的文件名，并原样拼进 root crontab 行（历史系统任务恢复就是这种数据）。
        cron_name = _cron_safe_name(cron_name)
        if not cron_name:
            yf.writeFileLog('[crontab] 拒绝使用非法任务标识作为脚本名（任务 %s）' % param.get('id', '0'))
            return ''
        param['echo'] = cron_name

        # try:
        stype = param['stype']
        if stype == 'toFile':
            shell = param.sFile
        else:
            head = "#!/bin/bash\nPATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin\nexport PATH\n"
            start_head = '''
SCRIPT_RUN_TIME="0s"
YF_ToSeconds()
{
    SEC=$1
    if [ $SEC -lt 60 ]; then
       SCRIPT_RUN_TIME="${SEC}s"
    elif [ $SEC -ge 60 ] && [ $SEC -lt 3600 ];then
       SCRIPT_RUN_TIME="$(( SEC / 60 ))m$(( SEC % 60 ))s"
    elif [ $SEC -ge 3600 ]; then
       SCRIPT_RUN_TIME="$(( SEC / 3600 ))h$(( (SEC % 3600) / 60 ))m$(( (SEC % 3600) % 60 ))s"
    fi
}
START_YF_SHELL_TIME=`date +%s`
''' + CRON_FORCE_MARKER + '''
'''

            source_bin_activate = '''
export LANG=en_US.UTF-8
        YF_PATH=%s/bin/activate
        if [ -f $YF_PATH ];then
            source $YF_PATH
fi''' % (yf.getPanelDir(),)

            head = head + start_head + source_bin_activate + "\n"

            if param.get('id'):
                cron_pid_file = self._cron_pid_file(param.get('id'))
                head += '''
# 记录当前执行 PID 并支持退出自动清理
YF_CRON_PID_FILE="%s"
echo $$ > "$YF_CRON_PID_FILE"
trap 'rm -f "$YF_CRON_PID_FILE"' EXIT
''' % (cron_pid_file,)
            
            # 执行时段/日期限制（cron 触发时才生效；面板点「执行」会带 CRON_FORCE_ENV=1 立刻跑）
            gate_checks = ''
            if 'type' in param and param['type'] == 'minute-n':
                time_check = '''
# 执行时段限制判定
CURRENT_HM=$(date +"%H%M")
'''
                if str(param.get('min_start_en', '0')) == '1':
                    start_hm = "%02d%02d" % (int(param.get('min_start_h', 0)), int(param.get('min_start_m', 0)))
                    time_check += '''
MIN_START_HM="%s"
if [ "$CURRENT_HM" -lt "$MIN_START_HM" ]; then
    echo "----------------------------------------------------------------------------"
    echo "★[$(date +"%%Y-%%m-%%d %%H:%%M:%%S")] 跳过执行：未到允许的开始时间($MIN_START_HM)"
    echo "----------------------------------------------------------------------------"
    exit 0
fi
''' % (start_hm,)
                if str(param.get('min_end_en', '0')) == '1':
                    end_hm = "%02d%02d" % (int(param.get('min_end_h', 23)), int(param.get('min_end_m', 59)))
                    time_check += '''
MIN_END_HM="%s"
if [ "$CURRENT_HM" -gt "$MIN_END_HM" ]; then
    echo "----------------------------------------------------------------------------"
    echo "★[$(date +"%%Y-%%m-%%d %%H:%%M:%%S")] 跳过执行：已过允许的结束时间($MIN_END_HM)"
    echo "----------------------------------------------------------------------------"
    exit 0
fi
''' % (end_hm,)
                gate_checks += time_check

            if 'day_type' in param and (str(param['day_type']) != '0'):
                day_type = str(param['day_type'])
                check_logic = ""
                # 1: 股票开盘日 (type == 0)
                if day_type == "1":
                    check_logic = '[ "$DAY_TYPE" != "0" ]'
                    check_desc = "股票开盘日"
                # 2: 工作日 (type == 0 或 3)
                elif day_type == "2":
                    check_logic = '[ "$DAY_TYPE" != "0" ] && [ "$DAY_TYPE" != "3" ]'
                    check_desc = "工作日"
                # 3: 节假日 (type == 1 或 2)
                elif day_type == "3":
                    check_logic = '[ "$DAY_TYPE" != "1" ] && [ "$DAY_TYPE" != "2" ]'
                    check_desc = "节假日"

                workday_check = '''
# 日期类型判定（带 24h 本地文件缓存，low 档 72h，减少外网依赖与单核阻塞）
CACHE_FILE="''' + yf.getPanelTmp() + '''/timor_holiday_$(date +%%F).json"
if [ -f "$CACHE_FILE" ] && [ $(($(date +%%s) - $(stat -c %%Y "$CACHE_FILE" 2>/dev/null || echo 0))) -lt 86400 ]; then
    RESPONSE=$(cat "$CACHE_FILE")
else
    RESPONSE=$(curl -s --connect-timeout 5 -m 10 --location --request GET "https://timor.tech/api/holiday/info/$(date +%%F)" -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    echo "$RESPONSE" > "$CACHE_FILE" 2>/dev/null
fi
if [ -z "$RESPONSE" ]; then
    echo "----------------------------------------------------------------------------"
    echo "★[$(date +"%%Y-%%m-%%d %%H:%%M:%%S")] 警告：日期接口调用失败，跳过日期限制检查！"
    echo "----------------------------------------------------------------------------"
else
    DAY_TYPE=$(echo $RESPONSE | grep -o '"type":[0-3]' | head -n1 | cut -d: -f2)
    if [ -z "$DAY_TYPE" ]; then
        echo "----------------------------------------------------------------------------"
        echo "★[$(date +"%%Y-%%m-%%d %%H:%%M:%%S")] 警告：日期接口数据解析失败，跳过日期限制检查！"
        echo "----------------------------------------------------------------------------"
    elif %s; then
        echo "----------------------------------------------------------------------------"
        echo "★[$(date +"%%Y-%%m-%%d %%H:%%M:%%S")] 跳过执行：今日非%s"
        echo "----------------------------------------------------------------------------"
        exit 0
    fi
fi
''' % (check_logic, check_desc)
                gate_checks += workday_check

            if gate_checks:
                # 手动执行（面板「执行」按钮）必须立刻跑：Popen 时会给脚本注入
                # CRON_FORCE_ENV=1，这里把整段前置判定包起来跳过，
                # 否则「每N分钟执行(限制:从09:00起)」的任务点执行只会写一条
                # 「跳过执行：未到允许的开始时间」，看起来像按钮失灵。
                head = head + ('''
# 执行时段/日期限制：只在 cron 触发时判定。
# 面板点「执行」（手动执行）会带 CRON_FORCE_ENV=1，忽略这些限制立刻执行。
if [ "${''' + CRON_FORCE_ENV + ''':-0}" = "1" ]; then
    echo "----------------------------------------------------------------------------"
    echo "★[$(date +"%Y-%m-%d %H:%M:%S")] 手动执行：已忽略执行时段/日期限制"
    echo "----------------------------------------------------------------------------"
else
''' + gate_checks + '''fi
''')
            log = '.log'

            #所有
            if param['sname'] == 'ALL':
                log = ''

            script_dir = yf.getPanelDir() + "/scripts"
            source_stype = 'database'
            if stype.find('database_') > -1:
                plugin_name = stype.replace('database_', '')
                script_dir = yf.getPanelDir() + "/plugins/" + plugin_name + "/scripts"

                source_stype = stype
                stype = 'database'

            if stype == 'path' and param['echo'] == '':
                param['echo'] == "1"

            # sname/save/echo 会被拼进生成的 root 脚本（cron/立即执行都以 root 跑），
            # 必须 shlex 转义，否则站点名/目录名里的 `;`、`#` 就是命令注入。
            sid = yf.shlexQuote(param['echo'])
            sname = yf.shlexQuote(param['sname'])
            ssave = yf.shlexQuote(param['save'])

            wheres = {
                'path': head + "python3 " + script_dir + "/backup.py path " + sname + " " + ssave + " " + sid, 
                'site':   head + "python3 " + script_dir + "/backup.py site " + sname + " " + ssave + " " + sid,
                'database': head + "python3 " + script_dir + "/backup.py database " + sname + " " + ssave,
                'logs':   head + "python3 " + script_dir + "/logs_backup.py " + yf.shlexQuote(str(param['sname']) + log) + " " + ssave,
                'rememory': head + "/bin/bash " + script_dir + '/rememory.sh'
            }
            if param['backup_to'] != 'localhost':
                cfile = yf.getPluginDir() + "/" + param['backup_to'] + "/index.py"
                wheres['path'] = head + "python3 " + cfile + " path " + sname + " " + ssave + " " + sid
                wheres['site'] = head + "python3 " + cfile + " site " + sname + " " + ssave + " " + sid
                wheres['database'] = head + "python3 " + cfile + " " + source_stype + " " + sname + " " + ssave
            try:
                shell = wheres[stype]
            except Exception as _e:
                if stype == 'toUrl':
                    # SSRF 纵深防御：
                    #   1. cronCheck 创建任务时已解析域名并拒绝私网；
                    #   2. 运行时由 urlguard 再次解析，并把解析结果用 curl --resolve
                    #      固定，封堵“校验后 DNS 被改写（DNS Rebinding）”的时间窗。
                    raw_url = str(param.get('url_address', '')).strip()
                    ok, _err = _validate_to_url(raw_url)
                    if not ok:
                        shell = head + "echo 'SSRF blocked: private URL not allowed' && exit 1"
                    else:
                        # URL 会拼进以 root 跑的 shell 脚本：统一走 yf.shlexQuote，
                        # 不再手工 `replace("'", "'\\''")`（等价但易写错、难审计）。
                        q_url = yf.shlexQuote(raw_url)
                        q_guard_py = yf.shlexQuote(yf.getPanelDir() + '/web/utils/urlguard.py')
                        shell = head + (
                            "RESOLVE_ARG=$(python3 " + q_guard_py + " " + q_url + ") || "
                            "{ echo 'SSRF blocked: private or unresolvable URL'; exit 1; }\n"
                            "RESOLVE_OPT=''\n"
                            'if [ -n "$RESOLVE_ARG" ]; then RESOLVE_OPT="--resolve $RESOLVE_ARG"; fi\n'
                            "curl -sS --connect-timeout 10 -m 60 --noproxy '*' $RESOLVE_OPT " + q_url
                        )
                else:
                    shell = head + param['sbody'].replace("\r\n", "\n")

            shell += '''
echo "----------------------------------------------------------------------------"
endDate=`date +"%%Y-%%m-%%d %%H:%%M:%%S"`
END_YF_SHELL_TIME=`date +"%%s"`
((SHELL_COS_TIME=($END_YF_SHELL_TIME-$START_YF_SHELL_TIME)))
YF_ToSeconds $SHELL_COS_TIME
echo "★[$endDate] Successful | Script Run [$SCRIPT_RUN_TIME] "
echo "----------------------------------------------------------------------------"

# 更新最后执行时间到数据库
web_dir='%s'
cron_id=%s
python3 -c "import os,sys;os.chdir('$web_dir');sys.path.append('$web_dir');import core.yf as yf,thisdb;thisdb.setCrontabData($cron_id,{'last_run_time':yf.formatDate()})"
''' % (yf.getPanelDir() + '/web', param.get('id', '0'))
        cron_path = yf.getServerDir() + '/cron'
        if not os.path.exists(cron_path):
            yf.makeDirs(cron_path)

        
        file = cron_path + '/' + cron_name
        # print(shell)
        yf.writeFile(file, self.checkScript(shell))
        try:
            os.chmod(file, 0o750)
        except Exception as _e:
            _log.debug('[crontab] 设置任务脚本权限失败: %s', _e)
        return cron_name

    # 检查脚本
    def checkScript(self, shell):
        keys = ['shutdown', 'init 0', 'mkfs', 'passwd',
                'chpasswd', '--stdin', 'mkfs.ext', 'mke2fs']
        for k in keys:
            shell = shell.replace(k, '[***]')
        return shell

    # 系统 crontab 文件落盘后的权限收敛（一律走 os.*，不经过 shell 字符串拼接）
    def _hardenSpoolFile(self, file, mode=0o600):
        try:
            os.chmod(file, mode)
        except Exception as _e:
            _log.debug('[crontab] 设置 crontab 文件权限失败: %s', _e)
        try:
            import pwd as _pwd, grp as _grp
            uid = _pwd.getpwnam('root').pw_uid
            try:
                # 优先 root:crontab，回退 root:root
                gid = _grp.getgrnam('crontab').gr_gid
            except Exception:
                gid = _grp.getgrnam('root').gr_gid
            os.chown(file, uid, gid)
        except Exception as _e:
            _log.debug('[crontab] 设置 crontab 文件属主失败: %s', _e)

    # 将Shell脚本写到文件（fcntl 排他锁 + 原子追加，避免并发覆盖）
    def writeShell(self, bash_script):
        if yf.isAppleSystem():
            return yf.returnData(True, 'ok')
        if not os.path.exists("/var/spool/cron/crontabs"):
            yf.execShell("mkdir -p /var/spool/cron/crontabs")
        file = '/var/spool/cron/crontabs/root'
        sys_os = yf.getOs()
        sys_name = yf.getOsName()
        if sys_os == 'darwin':
            file = '/etc/crontab'
        elif sys_name.startswith("freebsd"):
            file = '/var/cron/tabs/root'
        try:
            import fcntl
            # 确保文件存在
            if not os.path.exists(file):
                yf.writeFile(file, '')
            with open(file, 'a+', encoding='utf-8', errors='ignore') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                existing = f.read()
                # 去重：若已包含相同 echo 锚点则不重复追加（幂等）
                if bash_script.strip() and bash_script.strip() in existing:
                    fcntl.flock(f, fcntl.LOCK_UN)
                    return yf.returnData(True, 'ok')
                f.seek(0, 2)
                f.write(str(bash_script) + "\n")
                f.flush()
                try: os.fsync(f.fileno())
                except Exception as _e: _log.debug('[crontab] fsync 失败: %s', _e)
                fcntl.flock(f, fcntl.LOCK_UN)
            # 权限收敛（不使用 shell 拼接）
            self._hardenSpoolFile(file)
            return yf.returnData(True, 'ok')
        except Exception:
            # 回退旧路径（无锁）
            if not os.path.exists(file):
                yf.writeFile(file, '')
            content = yf.readFile(file)
            if not content:
                content = ''
            content += str(bash_script) + "\n"
            if yf.writeFile(file, content):
                self._hardenSpoolFile(file)
                return yf.returnData(True, 'ok')
            return yf.returnData(False, 'crontab.py_msg_77c6a9')

    # 重载配置
    def crondReload(self):
        if yf.isAppleSystem():
            return True
        # 只「重载」不「重启」：systemd 对同一 unit 的 start 有速率限制
        # （默认 5 次/10 秒），批量添加/导入任务时 restart 会把 cron 打成
        # start-limit-hit 而彻底停服，且面板每一条都还报成功。
        # Debian 的 /etc/init.d/cron reload 是安全的 no-op（cron 自动重读 spool）。
        try:
            if os.path.exists('/etc/init.d/crond'):
                yf.execShell('/etc/init.d/crond reload', timeout=yf.EXEC_SERVICE_TIMEOUT)
            elif os.path.exists('/etc/init.d/cron'):
                yf.execShell('/etc/init.d/cron reload', timeout=yf.EXEC_SERVICE_TIMEOUT)
            else:
                yf.execShell('systemctl reload crond', timeout=yf.EXEC_SERVICE_TIMEOUT)
        except Exception as _e:
            yf.writeFileLog('[crontab] 重载 cron 失败（任务仍会由 cron 自动重读）: %s' % _e)

    def syncToCrond(self, cron_id):
        info = thisdb.getCrond(cron_id)
        if info is None:
            return False
        if 'status' in info:
            if info['status'] == 0:
                return False

        if 'where_hour' in info:
            info['hour'] = info['where_hour']
            info['minute'] = info['where_minute']
            info['week'] = info['where1']

        cmd, _ = self.getCrondCycle(info)
        cron_path = yf.getServerDir() + '/cron'
        cron_name = self.getShell(info)
        if not cron_name:
            # echo 未过白名单，getShell 拒绝生成脚本：绝不能拼接非法名进 root crontab
            return False
        cmd += ' ' + cron_path + '/' + cron_name + ' >> ' + cron_path + '/' + cron_name + '.log 2>&1'
        if not _valid_cron_line(cmd):
            # 历史遗留的非法周期（如 type 被写成未知值）绝不能写进系统 crontab：
            # 一行语法错误会让整份 root crontab 被 cron 忽略。
            yf.writeFileLog('[crontab] 拒绝写入非法 crontab 行（任务 %s）: %s' % (cron_id, cmd.split(' ')[0:6]))
            return False
        ret = self.writeShell(cmd)
        if isinstance(ret, dict) and ret.get('status') is False:
            yf.writeFileLog('[crontab] 写入 crontab 失败（任务 %s）' % cron_id)
            return False
        self.crondReload()
        return True

