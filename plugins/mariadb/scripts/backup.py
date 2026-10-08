# coding: utf-8
#-----------------------------
# 网站备份工具
#-----------------------------

import sys
import os
import re
import subprocess
import time

# 用 __file__ 反推面板根（cwd 无关），把 <panel>/web 加入 sys.path 后再 import core.yf。
# 历史实现把 `os.chdir(yf.getPanelDir())` 写在 `import core.yf as yf` 之前，
# Linux 下必然 NameError，备份脚本一启动就崩 → 数据库备份功能完全不可用。
web_dir = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))) + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import core.db as db


class backupTools:

    def backupDatabase(self, name, count):
        db_path = yf.getServerDir() + '/mariadb'
        db_sock = yf.getServerDir() + '/mariadb/'
        db_name = 'mysql'
        name = yf.M('databases').dbPos(db_path, 'mysql').where(
            'name=?', (name,)).getField('name')
        startTime = time.time()
        if not name:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]不存在!"
            print("★[" + endDate + "] " + log)
            print(
                "----------------------------------------------------------------------------")
            return

        backup_path = yf.getBackupDir() + '/database/mariadb'
        if not os.path.exists(backup_path):
            yf.makeDirs(backup_path)

        version_prefix = 'mariadb104'
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
            "id=?", (1,)).getField('mysql_root') or ''

        my_conf_path = db_path + '/etc/my.cnf'
        content = yf.readFile(my_conf_path)
        rep = r"\[mysqldump\]\nuser=root"
        sea = "[mysqldump]\n"
        subStr = sea + "user=root\npassword=" + mysql_root + "\n"
        content = content.replace(sea, subStr)
        if len(content) > 100:
            yf.writeFile(my_conf_path, content)

        # yf.execShell(db_path + "/bin/mysqldump --defaults-file=" + my_conf_path + " --opt --default-character-set=utf8 " +
        #              name + " | gzip > " + filename)

        # yf.execShell(db_path + "/bin/mysqldump --defaults-file=" + my_conf_path + " --skip-lock-tables --default-character-set=utf8 " +
        #              name + " | gzip > " + filename)

        # 不再用 `mariadb-dump | gzip > file`：dump 非零退出（如二进制缺失）时 gzip 仍返回 0，
        # 只判 os.path.exists(filename) 会把 0 字节产物当「备份成功」（假成功）。
        # 改成 argv 列表 + 显式判退出码 + 产物大小（与 index.py::dumpMysqlData 同口径）。
        dump_bin = db_path + '/bin/mariadb-dump'
        if not os.path.exists(dump_bin):
            dump_bin = db_path + '/bin/mysqldump'
        raw_file = filename[:-3] if filename.endswith('.gz') else filename + '.raw'
        rc = 1
        try:
            with open(raw_file, 'wb') as _fo:
                _p = subprocess.Popen([dump_bin, '--defaults-file=' + my_conf_path,
                                       '--single-transaction', '--quick',
                                       '--default-character-set=utf8', name],
                                      stdout=_fo, stderr=subprocess.PIPE)
                _p.communicate(timeout=3600)
                rc = _p.returncode
        except Exception:
            rc = 1
        if rc == 0:
            rc2, _o, _e = yf.execShellRc(['gzip', '-f', raw_file], shell=False)
            if rc2 != 0:
                rc = 1
        elif os.path.exists(raw_file):
            yf.deleteFile(raw_file)

        # 无论成败都把 my.cnf 里的临时 root 密码还原（历史实现只在成功路径还原，
        # 失败 return 会把明文 root 密码留在 my.cnf 里）。
        mycnf = yf.readFile(db_path + '/etc/my.cnf')
        mycnf = mycnf.replace(subStr, sea)
        if len(mycnf) > 100:
            yf.writeFile(db_path + '/etc/my.cnf', mycnf)

        if rc != 0 or not os.path.exists(filename) or os.path.getsize(filename) < 32:
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

        yf.M('backup').add('type,name,pid,filename,addtime,size', (3, os.path.basename(
            filename), pid, filename, endDate, os.path.getsize(filename)))
        log = "数据库[" + name + "]备份成功,用时[" + str(round(outTime, 2)) + "]秒"
        yf.writeLog('计划任务', log)
        print("★[" + endDate + "] " + log)
        print("|---保留最新的[" + count + "]份备份")
        print("|---文件名:" + filename)

        # 清理多余备份
        backups = yf.M('backup').where(
            'type=? and pid=?', ('3', pid)).field('id,filename').select()

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                yf.deleteFile(backup['filename'])
                yf.M('backup').where('id=?', (backup['id'],)).delete()
                num -= 1
                print("|---已清理过期备份文件：" + backup['filename'])
                if num < 1:
                    break

    def backupDatabaseAll(self, save):
        db_path = yf.getServerDir() + '/mariadb'
        db_name = 'mysql'
        databases = yf.M('databases').dbPos(
            db_path, db_name).field('name').select()
        for database in databases:
            self.backupDatabase(database['name'], save)


if __name__ == "__main__":
    backup = backupTools()
    type = sys.argv[1]
    if type == 'database':
        if sys.argv[2] == 'ALL':
            backup.backupDatabaseAll(sys.argv[3])
        else:
            backup.backupDatabase(sys.argv[2], sys.argv[3])
