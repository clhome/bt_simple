# coding: utf-8
#-----------------------------
# 网站备份工具
#-----------------------------

import sys
import os
import re
import shlex
import time

if sys.platform != 'darwin':
    os.chdir('/www/server/yufeng_panel')

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import core.db as db


class backupTools:

    def backupSite(self, name, count, echo=None):
        exclude_dir_cmd = self.makeExcludeDirCmd(echo)

        sql = db.Sql()
        path = sql.table('sites').where('name=?', (name,)).getField('path')
        startTime = time.time()
        if not path:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "网站[" + name + "]不存在!"
            print("★[" + endDate + "] " + log)
            print(
                "----------------------------------------------------------------------------")
            return

        backup_path = yf.getBackupDir() + '/site'
        if not os.path.exists(backup_path):
            yf.makeDirs(backup_path)

        filename = backup_path + "/web_" + name + "_" + \
            time.strftime('%Y%m%d_%H%M%S', time.localtime()) + '.tar.gz'

        cmd = "cd " + shlex.quote(os.path.dirname(path)) + " && tar zcvf " + \
            shlex.quote(filename) + exclude_dir_cmd + " " + \
            shlex.quote(os.path.basename(path)) + " > /dev/null"

        # 备份对象与排除目录都可能来自面板入参（站点名/目录名/排除目录），
        # 一律 shlex 转义后用 bash -c 执行，并检查退出码。
        rc, _out, _err = yf.execShellRc(['bash', '-c', cmd], shell=False, timeout=3600)

        endDate = time.strftime('%Y/%m/%d %X', time.localtime())
        if rc != 0 or not os.path.exists(filename):
            log = "网站[" + name + "]备份失败!"
            print("★[" + endDate + "] " + log)
            print("----------------------------------------------------------------------------")
            return

        outTime = time.time() - startTime
        pid = sql.table('sites').where('name=?', (name,)).getField('id')
        sql.table('backup').add('type,name,pid,filename,add_time,size', ('0', os.path.basename(
            filename), pid, filename, endDate, os.path.getsize(filename)))
        log = "网站[" + name + "]备份成功,用时[" + str(round(outTime, 2)) + "]秒"
        yf.writeLog('计划任务', log)
        print("★[" + endDate + "] " + log)
        print("|---保留最新的[" + count + "]份备份")
        print("|---文件名:" + filename)

        # 清理多余备份
        backups = sql.table('backup').where(
            'type=? and pid=?', ('0', pid)).field('id,filename').select()

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                yf.deleteFile(backup['filename'])
                sql.table('backup').where('id=?', (backup['id'],)).delete()
                num -= 1
                print("|---已清理过期备份文件：" + backup['filename'])
                if num < 1:
                    break

    def getConf(self, mtype='mysql'):
        path = yf.getServerDir() + '/' + mtype + '/etc/my.cnf'
        return path

    def recognizeDbMode(self, mtype='mysql'):
        conf = self.getConf(mtype)
        con = yf.readFile(conf)
        rep = r"!include %s/(.*)?\.cnf" % (yf.getServerDir() +'/'+ mtype +"/etc/mode",)
        mode = 'none'
        try:
            data = re.findall(rep, con, re.M)
            mode = data[0]
        except Exception as e:
            pass
        return mode

     # 数据库密码处理
    def mypass(self, act, root):
        conf_file = self.getConf('mysql')
        # 参数化执行，避免把 conf_file 拼进 shell
        yf.execShellRc(['sed', '-i', '/user=root/d', conf_file], shell=False)
        yf.execShellRc(['sed', '-i', '/password=/d', conf_file], shell=False)
        if act:
            mycnf = yf.readFile(conf_file)
            src_dump = "[mysqldump]\n"
            if not mycnf:
                return False
            # 口令里的 \\ " 与换行会破坏 my.cnf 结构（甚至注入新配置项）
            safe_root = str(root).replace('\\', '\\\\').replace(
                '"', '\\"').replace('\n', '').replace('\r', '')
            sub_dump = src_dump + 'user=root\npassword="%s"\n' % safe_root
            mycnf = mycnf.replace(src_dump, sub_dump)
            if len(mycnf) > 100:
                yf.writeFile(conf_file, mycnf)
            return True
        return True

    def backupDatabase(self, name, count):
        db_path = yf.getServerDir() + '/mysql'
        db_name = 'mysql'
        # 保留调用方传进来的库名：下面 `name` 会被「查库结果」覆盖，查不到时它是 None，
        # 直接拼进日志会 TypeError: can only concatenate str (not "NoneType") to str
        # （与 backupSite 的 `path` 分支同族，但那边没覆盖 name 所以侥幸不炸）。
        # mongodb 插件自己的 scripts/backup.py 已用同样写法修过，这里是单侧漂移。
        req_name = str(name)
        name = yf.M('databases').dbPos(db_path, 'mysql').where(
            'name=?', (name,)).getField('name')
        startTime = time.time()
        if not name:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + req_name + "]不存在!"
            print("★[" + endDate + "] " + log)
            print(
                "----------------------------------------------------------------------------")
            return

        backup_path = yf.getBackupDir() + '/database'
        if not os.path.exists(backup_path):
            yf.makeDirs(backup_path)

        version_prefix = 'mysql57'
        version_file = db_path + '/version.pl'
        if os.path.exists(version_file):
            ver = yf.readFile(version_file).strip()
            parts = ver.split('.')
            if len(parts) >= 2:
                version_prefix = parts[0] + parts[1]
            elif len(parts) == 1:
                version_prefix = parts[0]
            
            if 'mariadb' in db_path:
                version_prefix = 'mariadb' + version_prefix
            else:
                version_prefix = 'mysql' + version_prefix
        else:
            if 'mariadb' in db_path:
                version_prefix = 'mariadb104'
            else:
                version_prefix = 'mysql57'

        filename = backup_path + "/" + version_prefix + "_" + name + "_" + \
            time.strftime('%Y%m%d_%H%M%S', time.localtime()) + ".sql.gz"

        mysql_root = yf.M('config').dbPos(db_path, db_name).where(
            "id=?", (1,)).getField('mysql_root')

        my_cnf = self.getConf('mysql')

        # 开启一致性事务 会lock表
        option = ''
        mode = self.recognizeDbMode('mysql')
        if mode == 'gtid':
            option = ' --set-gtid-purged=off '

        # skip-opt 不会lock表
        # --skip-opt --create-options
        cmd = db_path + "/bin/mysqldump --defaults-file=" + shlex.quote(my_cnf) + " " + option + \
            " --single-transaction -q --default-character-set=utf8mb4 " + shlex.quote(name) + \
            " | gzip > " + shlex.quote(filename)
        # 库名/路径都来自面板数据，一律转义；`| gzip >` 失败时也会留下文件，
        # 所以必须同时看退出码（只看 os.path.exists 会把失败的备份当成功）。
        self.mypass(True, mysql_root)
        try:
            rc, _out, _err = yf.execShellRc(['bash', '-c', cmd], shell=False, timeout=3600)
            ok = (rc == 0 and os.path.exists(filename))
        finally:
            # 无论成败都必须把 my.cnf 里临时写入的 root 口令清掉
            self.mypass(False, mysql_root)

        if not ok:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]备份失败!"
            print("★[" + endDate + "] " + log)
            print(
                "----------------------------------------------------------------------------")
            return

        endDate = time.strftime('%Y/%m/%d %X', time.localtime())
        outTime = time.time() - startTime
        pid = yf.M('databases').dbPos(db_path, db_name).where(
            'name=?', (name,)).getField('id')

        yf.M('backup').add('type,name,pid,filename,add_time,size', (1, os.path.basename(
            filename), pid, filename, endDate, os.path.getsize(filename)))
        log = "数据库[" + name + "]备份成功,用时[" + str(round(outTime, 2)) + "]秒"
        yf.writeLog('计划任务', log)
        print("★[" + endDate + "] " + log)
        print("|---保留最新的[" + count + "]份备份")
        print("|---文件名:" + filename)

        # 清理多余备份
        backups = yf.M('backup').where(
            'type=? and pid=?', ('1', pid)).field('id,filename').select()

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                yf.deleteFile(backup['filename'])
                yf.M('backup').where('id=?', (backup['id'],)).delete()
                num -= 1
                print("|---已清理过期备份文件：" + backup['filename'])
                if num < 1:
                    break

    def backupSiteAll(self, save):
        sites = yf.M('sites').field('name').select()
        for site in sites:
            self.backupSite(site['name'], save)

    def backupDatabaseAll(self, save):
        db_path = yf.getServerDir() + '/mysql'
        db_name = 'mysql'
        databases = yf.M('databases').dbPos(
            db_path, db_name).field('name').select()
        for database in databases:
            self.backupDatabase(database['name'], save)

    def findPathName(self, path, filename):
        f = os.scandir(path)
        l = []
        for ff in f:
            if ff.name.find(filename) > -1:
                l.append(ff.name)
        return l

    def makeExcludeDirCmd(self,echo):
        exclude_dirs = []
        crontab_list = yf.M('crontab').where('echo=?', (echo,)).field('attr').find()
        if crontab_list:
            attr = crontab_list['attr']
            if attr != "":
                ed_arrs = attr.split("\n")
                for ed in ed_arrs:
                    exclude_dirs.append(ed.strip())


        cmd = ""
        for v in exclude_dirs:
            v = (v or '').strip()
            if not v:
                continue
            # 排除目录来自 crontab.attr（面板可填），必须转义后再进 tar 命令行
            cmd += " --exclude=" + shlex.quote(v)
        return cmd

    def backupPath(self, path, count, echo=None):

        exclude_dir_cmd = self.makeExcludeDirCmd(echo)
        # print(exclude_dir_cmd)
        yf.echoStart('备份')

        backup_path = yf.getBackupDir() + '/path'
        if not os.path.exists(backup_path):
            yf.makeDirs(backup_path)

        dirname = os.path.basename(path)
        fname = 'path_{}_{}.tar.gz'.format(
            dirname, yf.formatDate("%Y%m%d_%H%M%S"))
        dfile = os.path.join(backup_path, fname)

        p_size = yf.getPathSize(path)
        stime = time.time()

        cmd = "cd " + shlex.quote(os.path.dirname(path)) + " && tar zcvf " + \
            shlex.quote(dfile) + exclude_dir_cmd + " " + shlex.quote(dirname) + \
            " 2>/tmp/backup_err.log 1> /dev/null"
        rc, _out, _err = yf.execShellRc(['bash', '-c', cmd], shell=False, timeout=3600)

        if rc != 0 or not os.path.exists(dfile):
            yf.echoInfo('目录备份失败：' + path)
            yf.echoEnd('备份')
            return

        tar_size = os.path.getsize(dfile)

        yf.echoInfo('备份目录：' + path)
        yf.echoInfo('目录已备份到：' + dfile)
        yf.echoInfo("目录大小：{}".format(yf.toSize(p_size)))
        yf.echoInfo("开始压缩文件：{}".format(yf.formatDate(times=stime)))
        yf.echoInfo("文件压缩完成，耗时{:.2f}秒，压缩包大小：{}".format(
            time.time() - stime, yf.toSize(tar_size)))
        yf.echoInfo('保留最新的备份数：' + count + '份')

        backups = self.findPathName(backup_path, 'path_{}'.format(dirname))
        num = len(backups) - int(count)
        backups.sort()
        if num > 0:
            for backup in backups:
                abspath_bk = backup_path + "/" + backup
                yf.deleteFile(abspath_bk)
                yf.echoInfo("已清理过期备份文件：" + abspath_bk)
                num -= 1
                if num < 1:
                    break

        yf.echoEnd('备份')

if __name__ == "__main__":
    backup = backupTools()
    stype = sys.argv[1]
    if stype == 'site':
        if sys.argv[2] == 'ALL':
            backup.backupSiteAll(sys.argv[3])
        else:
            backup.backupSite(sys.argv[2], sys.argv[3], sys.argv[4])
    elif stype == 'database':
        if sys.argv[2] == 'ALL':
            backup.backupDatabaseAll(sys.argv[3])
        else:
            backup.backupDatabase(sys.argv[2], sys.argv[3])
    elif stype == 'path':
        backup.backupPath(sys.argv[2], sys.argv[3], sys.argv[4])
