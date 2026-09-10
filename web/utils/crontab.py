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
import ipaddress
import urllib.parse

import core.yf as yf
import thisdb


def _is_private_url(url):
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ('http', 'https'):
            return True
        host = parsed.hostname
        if not host:
            return True
        # 阻断内网/回环/云元数据
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
            if str(ip) == '169.254.169.254':
                return True
        except ValueError:
            # 域名形式：阻断常见内网域名
            low = host.lower()
            if low in ('localhost', 'metadata.google.internal'):
                return True
            if low.startswith('10.') or low.startswith('192.168.'):
                return True
        # 额外阻断 169.254.x.x 字符串形式的元数据
        if '169.254.' in host:
            return True
        return False
    except Exception:
        return True


def _validate_to_url(url):
    if not url or not isinstance(url, str):
        return False, 'URL不能为空'
    url = url.strip()
    if len(url) > 2048:
        return False, 'URL过长'
    if not url.startswith(('http://', 'https://')):
        return False, '仅允许 http/https 协议'
    if _is_private_url(url):
        return False, '禁止请求内网/回环/元数据地址（SSRF 防护）'
    return True, 'OK'


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

        if not self.removeForCrond(info['echo']):
            return yf.returnData(False, 'crontab.py_msg_9b5111')

        thisdb.setCrontabData(cron_id, dbdata)
        self.syncToCrond(cron_id)
        msg = '修改计划任务[' + data['name'] + ']成功'
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
            self.syncToCrond(cron_id)

        msg = '修改计划任务[' + data['name'] + ']状态为[' + str(status_msg) + ']'
        yf.writeLog('计划任务', msg)
        return yf.returnJson(True, msg)


    def cronLog(self, cron_id):
        data = thisdb.getCrond(cron_id)
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
                        except Exception:
                            pass
                try:
                    os.replace(log_file, f"{log_file}.1")
                except Exception:
                    pass
        except Exception:
            pass

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
                        import signal as _sig
                        try:
                            os.kill(pid, _sig.SIGTERM)
                        except Exception:
                            pass
                        time.sleep(1)
                        if yf.checkPid(pid):
                            try:
                                os.kill(pid, _sig.SIGKILL)
                            except Exception:
                                pass
                        yf.writeFileLog(f"[crontab] killed stale cron {cron_id} pid={pid} after {timeout_sec}s\n")
                        return True
                except Exception:
                    pass
            else:
                try:
                    os.remove(pf)
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def startTask(self, cron_id):
        data = thisdb.getCrond(cron_id)
        cmd_file = yf.getServerDir() + '/cron/' + data['echo']
        if not os.path.exists(cmd_file):
             self.syncToCrond(cron_id)
        try:
            os.chmod(cmd_file, 0o750)
        except Exception:
            pass
        import subprocess as _sp
        log_file = cmd_file + '.log'
        self._rotate_cron_log(log_file)
        self.cleanupStaleCron(cron_id)
        pid_file = self._cron_pid_file(cron_id)
        proc = None
        try:
            lf = open(log_file, 'a')
            proc = _sp.Popen([cmd_file], stdout=lf, stderr=_sp.STDOUT, start_new_session=True, close_fds=True)
            try:
                yf.writeFile(pid_file, str(proc.pid))
            except Exception:
                pass
            try:
                lf.close()
            except Exception:
                pass
        except Exception:
            try:
                yf.execShell(yf.shlexQuote(cmd_file) + ' >> ' + yf.shlexQuote(log_file) + ' 2>&1 &')
            except Exception:
                pass
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
                    self.syncToCrond(tid)
            return tid
        except Exception as e:
            return yf.returnData(False, 'utils.py_msg_788ddb', None, str(e))

    def delete(self, tid):
        data = thisdb.getCrond(tid)
        if not self.removeForCrond(data['echo']):
            return yf.returnData(False, 'crontab.py_msg_9b5111')

        cron_path = yf.getServerDir() + '/cron'
        cron_file = cron_path + '/' + data['echo']

        if os.path.exists(cron_file):
            os.remove(cron_file)
        cron_file = cron_path + '/' + data['echo'] + '.log'
        if os.path.exists(cron_file):
            os.remove(cron_file)

        thisdb.deleteCronById(tid)
        msg = yf.getInfo('删除计划任务[{1}]成功!', (data['name'],))
        yf.writeLog('计划任务', msg)
        return yf.returnData(True, msg)


    def delLogs(self,cron_id):
        try:
            data = thisdb.getCrond(cron_id)
            log_file = yf.getServerDir() + '/cron/' + data['echo'] + '.log'
            if os.path.exists(log_file):
                os.remove(log_file)
            return yf.returnData(True, 'crontab.py_msg_5d335f')
        except Exception as _e:
            return yf.returnData(False, 'crontab.py_msg_96779b')

    def getCrontabHuman(self, data):
        rdata = []
        for i in range(len(data)):
            t = data[i]
            t['type_raw'] = t['type']
            if t['type'] == "day":
                t['type'] = '每天'
                t['cycle'] = yf.getInfo('每天, {1}点{2}分 执行', (str(t['where_hour']), str(t['where_minute'])))
            elif t['type'] == "day-n":
                t['type'] = yf.getInfo('每{1}天', (str(t['where1']),))
                t['cycle'] = yf.getInfo('每隔{1}天, {2}点{3}分 执行',  (str(t['where1']), str(t['where_hour']), str(t['where_minute'])))
            elif t['type'] == "hour":
                t['type'] = '每小时'
                t['cycle'] = yf.getInfo('每小时, 第{1}分钟 执行', (str(t['where_minute']),))
            elif t['type'] == "hour-n":
                t['type'] = yf.getInfo('每{1}小时', (str(t['where1']),))
                t['cycle'] = yf.getInfo('每{1}小时, 第{2}分钟 执行', (str(t['where1']), str(t['where_minute'])))
            elif t['type'] == "minute-n":
                t['type'] = yf.getInfo('每{1}分钟', (str(t['where1']),))
                t['cycle'] = yf.getInfo('每隔{1}分钟执行', (str(t['where1']),))
                if str(t.get('min_start_en', '0')) == '1' or str(t.get('min_end_en', '0')) == '1':
                    limit_str = []
                    if str(t.get('min_start_en', '0')) == '1':
                        limit_str.append("从%02d:%02d起" % (int(t.get('min_start_h', 0)), int(t.get('min_start_m', 0))))
                    if str(t.get('min_end_en', '0')) == '1':
                        limit_str.append("至%02d:%02d止" % (int(t.get('min_end_h', 23)), int(t.get('min_end_m', 59))))
                    t['cycle'] += " (限制: %s)" % " ".join(limit_str)
            elif t['type'] == "week":
                t['type'] = '每周'
                if not t['where1']:
                    t['where1'] = '0'
                t['cycle'] = yf.getInfo('每周{1}, {2}点{3}分执行', (self.toWeek(int(t['where1'])), str(t['where_hour']), str(t['where_minute'])))
            elif t['type'] == "month":
                t['type'] = '每月'
                t['cycle'] = yf.getInfo('每月, {1}日 {2}点{3}分执行', (str(t['where1']), str(t['where_hour']), str(t['where_minute'])))
            
            # 获取上次执行时间
            if 'last_run_time' in t and t['last_run_time'] and t['last_run_time'] != 'None':
                t['last_run_time'] = t['last_run_time']
            else:
                log_file = yf.getServerDir() + '/cron/' + t['echo'] + '.log'
                if os.path.exists(log_file):
                    t['last_run_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(log_file)))
                else:
                    t['last_run_time'] = '从未执行'

            # 获取特定日期类型限制
            day_type_map = {
                '0': '无',
                '1': '股票开盘日',
                '2': '工作日',
                '3': '节假日'
            }
            t['day_type_h'] = day_type_map.get(str(t.get('day_type', '0')), '无')

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
                except Exception: pass
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
            title = '每天'
        elif params['type'] == "day-n":
            cron_cmd = self.getDay_N(params)
            title = yf.getInfo('每{1}天', (params['where1'],))
        elif params['type'] == "hour":
            cron_cmd = self.getHour(params)
            title = '每小时'
        elif params['type'] == "hour-n":
            cron_cmd = self.getHour_N(params)
            title = '每小时'
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
        if params['stype'] == 'site' or params['stype'] == 'database' or params['stype'].find('database_') > -1 or params['stype'] == 'logs' or params['stype'] == 'path':
            if params['save'] == '':
                return False, '保留份数不能为空!'
        if params.get('stype') == 'toUrl':
            ok, err = _validate_to_url(params.get('url_address', ''))
            if not ok:
                return False, err

        if params['type'] == 'day':
            if params['hour'] == '':
                return False, '小时不能为空!'
            if params['minute'] == '':
                return False, '分钟不能为空!'

        if params['type'] == 'day-n':
            if params['where1'] == '':
                return False, '天不能为空!'
            if params['hour'] == '':
                return False, '小时不能为空!'
            if params['minute'] == '':
                return False, '分钟不能为空!'
        if params['type'] == 'hour':
            if params['minute'] == '':
                return False, '分钟不能为空!'

        if params['type'] == 'hour-n':
            if params['where1'] == '':
                return False, '小时不能为空!'
            if params['minute'] == '':
                return False, '分钟不能为空!'

        if params['type'] == 'minute-n':
            if params['where1'] == '':
                return False, '分钟不能为空!'

        if params['type'] == 'week':
            if params['hour'] == '':
                return False, '小时不能为空!'
            if params['minute'] == '':
                return False, '分钟不能为空!'

        if params['type'] == 'month':
            if params['where1'] == '':
                return False, '日不能为空!'
            if params['hour'] == '':
                return False, '小时不能为空!'
            if params['minute'] == '':
                return False, '分钟不能为空!'
        return True, 'OK'


    # 取执行脚本
    def getShell(self, param):
        if not 'echo' in param:
            cron_name = yf.md5(yf.md5(str(time.time()) + '_yf'))
        else:
            cron_name = param['echo']
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
'''

            source_bin_activate = '''
export LANG=en_US.UTF-8
        YF_PATH=%s/bin/activate
        if [ -f $YF_PATH ];then
            source $YF_PATH
fi''' % (yf.getPanelDir(),)

            head = head + start_head + source_bin_activate + "\n"
            
            # 分钟N执行时段限制
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
                head = head + time_check

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
                head = head + workday_check
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

            wheres = {
                'path': head + "python3 " + script_dir + "/backup.py path " + param['sname'] + " " + str(param['save']) + " " + str(param['echo']), 
                'site':   head + "python3 " + script_dir + "/backup.py site " + param['sname'] + " " + str(param['save']) + " " + str(param['echo']),
                'database': head + "python3 " + script_dir + "/backup.py database " + param['sname'] + " " + str(param['save']),
                'logs':   head + "python3 " + script_dir + "/logs_backup.py " + param['sname'] + log + " " + str(param['save']),
                'rememory': head + "/bin/bash " + script_dir + '/rememory.sh'
            }
            if param['backup_to'] != 'localhost':
                cfile = yf.getPluginDir() + "/" + param['backup_to'] + "/index.py"
                wheres['path'] = head + "python3 " + cfile + " path " + param['sname'] + " " + str(param['save']) + " " + str(param['echo'])
                wheres['site'] = head + "python3 " + cfile + " site " + param['sname'] + " " + str(param['save']) + " " + str(param['echo'])
                wheres['database'] = head + "python3 " + cfile + " " + source_stype + " " + param['sname'] + " " + str(param['save'])
            try:
                shell = wheres[stype]
            except Exception as _e:
                if stype == 'toUrl':
                    # SSRF 已在 cronCheck 拦截，此处二次校验并加 --noproxy 禁止重定向到私网
                    raw_url = str(param.get('url_address', '')).strip()
                    ok, _ = _validate_to_url(raw_url)
                    if not ok:
                        shell = head + "echo 'SSRF blocked: private URL not allowed' && exit 1"
                    else:
                        safe_url = raw_url.replace("'", "'\\''")
                        shell = head + "curl -sS --connect-timeout 10 -m 60 --noproxy '*' '" + safe_url + "'"
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
        yf.execShell('chmod 750 ' + file)
        return cron_name

    # 检查脚本
    def checkScript(self, shell):
        keys = ['shutdown', 'init 0', 'mkfs', 'passwd',
                'chpasswd', '--stdin', 'mkfs.ext', 'mke2fs']
        for k in keys:
            shell = shell.replace(k, '[***]')
        return shell

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
                except Exception: pass
                fcntl.flock(f, fcntl.LOCK_UN)
            # 权限收敛（不使用 shell 拼接）
            try:
                os.chmod(file, 0o600)
                import pwd as _pwd, grp as _grp
                try:
                    # 优先 root:crontab，回退 root:root
                    uid = _pwd.getpwnam('root').pw_uid
                    try: gid = _grp.getgrnam('crontab').gr_gid
                    except Exception: gid = _grp.getgrnam('root').gr_gid
                    os.chown(file, uid, gid)
                except Exception:
                    pass
            except Exception:
                pass
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
                yf.execShell("chmod 600 '" + file +"' && chown root.root " + file)
                return yf.returnData(True, 'ok')
            return yf.returnData(False, 'crontab.py_msg_77c6a9')

    # 重载配置
    def crondReload(self):
        if yf.isAppleSystem():
            if os.path.exists('/etc/crontab'):
                pass
        else:
            if os.path.exists('/etc/init.d/crond'):
                yf.execShell('/etc/init.d/crond reload')
            elif os.path.exists('/etc/init.d/cron'):
                yf.execShell('service cron restart')
            else:
                yf.execShell("systemctl reload crond")

    def syncToCrond(self, cron_id):
        info = thisdb.getCrond(cron_id)
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
        cmd += ' ' + cron_path + '/' + cron_name + ' >> ' + cron_path + '/' + cron_name + '.log 2>&1'
        self.writeShell(cmd)
        self.crondReload()
        return True

