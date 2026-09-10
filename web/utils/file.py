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
try:
    import pwd
except ImportError:
    pwd = None
import time
import shutil
import json
import base64

import core.yf as yf
import thisdb

def uploadSegment(path,name,size,start,dir_mode,file_mode,b64_data,upload_files):
    if not yf.fileNameCheck(name):
        return yf.returnData(False, 'file.py_msg_4472a5')

    # 防路径逃逸与非法文件名
    clean_name = os.path.basename(name.replace('\\', '/')).strip()
    if not clean_name or clean_name != name or '/' in name or '\\' in name or '..' in name:
        return yf.returnData(False, 'file.py_msg_302ba9')

    if path == '/':
        return yf.returnData(False, 'file.py_msg_4d44b7')

    if name.find('./') != -1 or path.find('./') != -1:
        return yf.returnData(False, 'file.py_msg_302ba9')

    abs_path = os.path.abspath(path)
    target_file = os.path.abspath(os.path.join(abs_path, clean_name))
    if not target_file.startswith(abs_path + os.sep) and target_file != os.path.join(abs_path, clean_name):
        return yf.returnData(False, 'file.py_msg_302ba9')

    if not os.path.exists(abs_path):
        os.makedirs(abs_path, 493)
        if not dir_mode != '' or not file_mode != '':
            setMode(abs_path)

    save_path = os.path.join(abs_path, clean_name + '.' + str(int(size)) + '.upload.tmp')
    d_size = 0
    if os.path.exists(save_path):
        d_size = os.path.getsize(save_path)

    if d_size != int(start):
        return yf.returnData(True, 'size', d_size)

    f = open(save_path, 'ab')
    if b64_data == '1':
        b64_data = base64.b64decode(b64_data)
        f.write(b64_data)
    else:
        for tmp_f in upload_files:
            f.write(tmp_f.read())

    f.close()
    f_size = os.path.getsize(save_path)
    if f_size != int(size):
        return yf.returnData(True, 'size', f_size)

    new_name = os.path.join(path, name)
    if os.path.exists(new_name):
        if new_name.find('.user.ini') != -1:
            yf.execShell("chattr -i " + new_name)
        try:
            os.remove(new_name)
        except Exception as _e:
            yf.deleteFile(new_name)

    os.renames(save_path, new_name)

    if dir_mode != '' and dir_mode != '':
        mode_tmp1 = dir_mode.split(',')
        yf.setMode(path, mode_tmp1[0])
        yf.setOwn(path, mode_tmp1[1])
        mode_tmp2 = file_mode.split(',')
        yf.setMode(new_name, mode_tmp2[0])
        yf.setOwn(new_name, mode_tmp2[1])
    else:
        setMode(new_name)

    msg = yf.getInfo('上传文件[{1}] 到 [{2}]成功!', (new_name, path))
    yf.writeLog('文件管理', msg)
    return yf.returnData(True, 'file.py_msg_34da7e', f_size)


def mvFile(sfile, dfile):
    if not checkFileName(dfile):
        return yf.returnData(False, 'file.py_msg_4472a5')
    if not os.path.exists(sfile):
        return yf.returnData(False, 'file.py_msg_e0fb06')

    if not checkDir(sfile):
        return yf.returnData(False, 'FILE_DANGER')


    try:
        pass
    except Exception as e:
        raise e

    try:
        shutil.move(sfile, dfile)
        msg = yf.getInfo('移动或重名命文件[{1}]到[{2}]成功!', (sfile, dfile,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'file.py_msg_fbe5a8')
    except Exception as e:
        return yf.returnData(False, 'utils.py_msg_5647ea', None, str(e))

def unzip(sfile, dfile, stype, path):
    if dfile == '' or dfile == '/':
        return yf.returnData(False, 'file.py_msg_960516')

    if not os.path.exists(sfile):
        return yf.returnData(False, 'file.py_msg_e0fb06')

    try:
        tmps = yf.getPanelDir() + '/logs/panel_exec.log'
        q_path = yf.shlexQuote(path)
        q_dfile = yf.shlexQuote(dfile)
        q_tmps = yf.shlexQuote(tmps)
        if stype == 'zip':
            q_sfile = yf.shlexQuote(sfile)
            yf.execShell("cd " + q_path + " && unzip -o -d " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1 &")
        else:
            sfiles = ' '.join(yf.shlexQuote(sf) for sf in sfile.split(',') if sf)
            yf.execShell("cd " + q_path + " && tar -zxvf " + sfiles + " -C " + q_dfile + " > " + q_tmps + " 2>&1 &")

        if os.path.exists(dfile):
            if dfile.startswith("/www/wwwroot"):
                setFileAccept(dfile)
        yf.writeLog("文件管理", '文件[{1}]解压[{2}]成功!', (sfile, dfile))
        return yf.returnData(True, 'file.py_msg_f0f920')
    except Exception as _e:
        return yf.returnData(False, 'file.py_msg_f43013')

def uncompress(sfile, dfile, path):
    if dfile == '' or dfile == '/':
        return yf.returnData(False, 'file.py_msg_960516')

    if not os.path.exists(sfile):
        return yf.returnData(False, 'file.py_msg_e0fb06')

    filename = os.path.basename(sfile)
    extension = os.path.splitext(filename)[-1]
    extension = extension.strip('.')

    tar_gz = 'tar.gz'
    tar_gz_len = len(tar_gz)
    suffix_gz = sfile[-tar_gz_len:]
    if suffix_gz == tar_gz:
        extension = suffix_gz

    if not extension in ['tar.gz', 'gz', 'zip', 'rar', '7z', 'xz','bz2']:
        return yf.returnData(False, 'file.py_msg_067d29')

    if extension == 'rar' and not yf.checkBinExist('rar'):
        return yf.returnData(False, 'file.py_msg_366e5e')
    if extension == '7z' and not yf.checkBinExist('7z'):
        return yf.returnData(False, 'file.py_msg_a8d259')

    q_path = yf.shlexQuote(path)
    q_dfile = yf.shlexQuote(dfile)
    q_sfile = yf.shlexQuote(sfile)
    q_tmps = yf.shlexQuote(yf.getPanelDir() + '/logs/panel_exec.log')
    cmd = "cd " + q_path + " "
    try:
        if extension == 'zip':
            cmd += "&& unzip -o -d " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == 'tar.gz':
            cmd += "&& tar -zxvf " + q_sfile + " -C " + q_dfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == 'gz':
            cmd += "&& gunzip -k " + q_sfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == 'rar':
            cmd += "&& unrar x " + q_sfile + " " + q_dfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == '7z':
            cmd += "&& 7z x " + q_sfile + " -r -o" + q_dfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == 'xz':
            cmd += "&& tar -Jxvf " + q_sfile + " -C " + q_dfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)
        elif extension == 'bz2':
            cmd += "&& tar -xjvf " + q_sfile + " -C " + q_dfile + " > " + q_tmps + " 2>&1 &"
            yf.execShell(cmd)

        if os.path.exists(dfile):
            if dfile.startswith("/www/wwwroot"):
                setFileAccept(dfile)
        yf.writeLog("文件管理", '文件[{1}]解压[{2}]成功!', (sfile, dfile,))
        return yf.returnData(True, 'file.py_msg_f0f920')
    except Exception as e:
        return yf.returnData(False, 'utils.py_msg_0443ac', None, str(e))

def setBatchData(path, stype, access, user, data):
    from admin import session
    if stype == '1' or stype == '2':
        session['selected'] = {
            'path': path,
            'type': stype,
            'access': access,
            'user': user,
            'data': data
        }
        return yf.returnData(True, 'file.py_msg_00c89e')
    elif stype == '3':
        for key in json.loads(data):
            try:
                filename = path + '/' + key
                if not checkDir(filename):
                    return yf.returnData(False, 'FILE_DANGER')
                
                # 使用原生 Python 操作替换 os.system
                mode = int(access, 8)
                for root, dirs, files in os.walk(filename):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), mode)
                        shutil.chown(os.path.join(root, d), user, user)
                    for f in files:
                        os.chmod(os.path.join(root, f), mode)
                        shutil.chown(os.path.join(root, f), user, user)
                os.chmod(filename, mode)
                shutil.chown(filename, user, user)
            except Exception as _e:
                continue
        yf.writeLog('文件管理', '批量设置权限成功!')
        return yf.returnData(True, 'file.py_msg_fcc159')
    else:
        recycle_bin = thisdb.getOption('recycle_bin')
        is_recycle = False
        if recycle_bin == 'open':
            is_recycle = True
        data = json.loads(data)
        l = len(data)
        i = 0
        failed_files = []
        for key in data:
            try:
                filename = path + '/' + key
                topath = filename
                if not os.path.exists(filename):
                    continue

                i += 1
                yf.writeSpeed(key, i, l)
                if os.path.isdir(filename):
                    if not checkDir(filename):
                        return yf.returnData(False, 'file.py_msg_27af9b')
                    if is_recycle:
                        if not mvRecycleBin(topath):
                            failed_files.append(filename)
                    else:
                        shutil.rmtree(filename)
                        if os.path.exists(filename):
                            failed_files.append(filename)
                else:
                    if key == '.user.ini':
                        try:
                            import subprocess
                            subprocess.run(['chattr', '-i', filename], timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception:
                            pass
                    if is_recycle:
                        if not mvRecycleBin(topath):
                            failed_files.append(filename)
                    else:
                        os.remove(filename)
                        if os.path.exists(filename):
                            failed_files.append(filename)
            except Exception as _e:
                failed_files.append(filename)
                continue
            yf.writeSpeed(None, 0, 0)
            
        if failed_files:
            occ = getOccupyingProcess(failed_files[0])
            msg = '部分文件/目录删除失败，例如: ' + failed_files[0].split('/')[-1]
            if occ:
                msg += '，' + occ
            return yf.returnData(False, msg)
            
        yf.writeLog('文件管理', '批量删除成功!')
        return yf.returnData(True, 'file.py_msg_856956')

def batchPaste(path, stype):
    from admin import session
    if not checkDir(path):
        return yf.returnData(False, 'file.py_msg_27af9b')
    i = 0
    myfiles = json.loads(session['selected']['data'])
    l = len(myfiles)
    if stype == '1':
        for key in myfiles:
            i += 1
            yf.writeSpeed(key, i, l)
            try:

                sfile = session['selected'][
                    'path'] + '/' + key
                dfile = path + '/' + key

                if os.path.isdir(sfile):
                    shutil.copytree(sfile, dfile)
                else:
                    shutil.copyfile(sfile, dfile)
                stat = os.stat(sfile)
                os.chown(dfile, stat.st_uid, stat.st_gid)
            except Exception as _e:
                continue
        msg = yf.getInfo('从[{1}]批量复制到[{2}]成功',(session['selected']['path'], path,))
        yf.writeLog('文件管理', msg)
    else:
        for key in myfiles:
            try:
                i += 1
                yf.writeSpeed(key, i, l)

                sfile = session['selected'][
                    'path'] + '/' + key
                dfile = path + '/' + key

                shutil.move(sfile, dfile)
            except Exception as _e:
                continue
        msg = yf.getInfo('从[{1}]批量移动到[{2}]成功',(session['selected']['path'], path,))
        yf.writeLog('文件管理', msg)
    yf.writeSpeed(None, 0, 0)
    errorCount = len(myfiles) - i
    del(session['selected'])
    msg = yf.getInfo('批量操作成功[{1}],失败[{2}]', (str(i), str(errorCount)))
    return yf.returnData(True, msg)


def zip(sfile, dfile, stype, path):
    tmps = yf.getPanelDir() + '/logs/panel_exec.log'
    q_path = yf.shlexQuote(path)
    q_dfile = yf.shlexQuote(dfile)
    q_tmps = yf.shlexQuote(tmps)
    if sfile.find(',') == -1:
        q_sfile = yf.shlexQuote(sfile)
        if stype == 'zip':
            yf.execShell("cd " + q_path + " && zip " + q_dfile + " -r " + q_sfile + " > " + q_tmps + " 2>&1")
        elif stype == '7z':
            if not yf.checkBinExist('7z'):
                return yf.returnData(False, 'file.py_msg_c2cd54')
            yf.execShell("cd " + q_path + " && 7z a " + q_dfile + " -r " + q_sfile + " > " + q_tmps + " 2>&1")
        elif stype == 'tar_gz':
            yf.execShell("cd " + q_path + " && tar -zcvf " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1")
        elif stype == 'xz':
            cmd = "cd " + q_path + " && tar -cJf " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1"
            yf.execShell(cmd)
        elif stype == 'rar':
            if not yf.checkBinExist('rar'):
                return yf.returnData(False, 'file.py_msg_4ba9f0')
            yf.execShell("cd " + q_path + " && rar a " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1")
        elif stype == 'bz2':
            yf.execShell("cd " + q_path + " && tar -cjvf " + q_dfile + " " + q_sfile + " > " + q_tmps + " 2>&1")
        else:
            return yf.returnData(False, 'file.py_msg_05b0c9')
        yf.writeLog("文件管理", '文件[{1}]压缩[{2}]成功!', (sfile, dfile))
    else:
        sfiles = []
        for sf in sfile.split(','):
            if not sf:
                continue
            if not os.path.exists(sf):
                return yf.returnData(False, 'file.py_msg_e0fb06')
            rel = sf.replace(path + '/', '')
            sfiles.append(yf.shlexQuote(rel))
        sfiles_str = ' '.join(sfiles)

        if stype == 'zip':
            yf.execShell("cd " + q_path + " && zip " + q_dfile + " -r " + sfiles_str + " > " + q_tmps + " 2>&1")
        elif stype == '7z':
            if not yf.checkBinExist('7z'):
                return yf.returnData(False, 'file.py_msg_c2cd54')
            yf.execShell("cd " + q_path + " && 7z a " + q_dfile + " -r " + sfiles_str + " > " + q_tmps + " 2>&1")
        elif stype == 'tar_gz':
            yf.execShell("cd " + q_path + " && tar -zcvf " + q_dfile + " " + sfiles_str + " > " + q_tmps + " 2>&1")
        elif stype == 'xz':
            yf.execShell("cd " + q_path + " && tar -cJf " + q_dfile + " " + sfiles_str + " > " + q_tmps + " 2>&1")
        elif stype == 'rar':
            if not yf.checkBinExist('rar'):
                return yf.returnData(False, 'file.py_msg_4ba9f0')
            yf.execShell("cd " + q_path + " && rar a " + q_dfile + " " + sfiles_str + " > " + q_tmps + " 2>&1")
        else:
            return yf.returnData(False, 'file.py_msg_05b0c9')
        yf.writeLog("文件管理", '文件[{1}]压缩[{2}]成功!', (sfile, dfile))

    if os.path.exists(dfile):
        setFileAccept(dfile)
    return yf.returnData(True, 'file.py_msg_f0f920')

def getAccess(filename):
    data = {}
    try:
        stat = os.stat(filename)
        data['chmod'] = str(oct(stat.st_mode)[-3:])
        data['chown'] = pwd.getpwuid(stat.st_uid).pw_name
    except Exception as _e:
        data['chmod'] = 755
        data['chown'] = 'www'
    return data

def copyDir(src_file, dst_file):
    if not os.path.exists(src_file):
        return yf.returnData(False, 'file.py_msg_639dba')

    if os.path.exists(dst_file):
        return yf.returnData(False, 'file.py_msg_db3560')

    try:
        shutil.copytree(src_file, dst_file)
        stat = os.stat(src_file)
        os.chown(dst_file, stat.st_uid, stat.st_gid)
        msg = yf.getInfo('复制目录[{1}]到[{2}]成功!', (src_file, dst_file))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'file.py_msg_9b0c62')
    except Exception as _e:
        return yf.returnData(False, 'file.py_msg_175fe9')

def copyFile(src_file, dst_file):
    if src_file == dst_file:
        return yf.returnJson(False, 'file.py_msg_58a046')

    if not os.path.exists(src_file):
        return yf.returnJson(False, 'file.py_msg_e0fb06')

    if os.path.isdir(src_file):
        return copyDir(src_file, dst_file)

    try:
        shutil.copyfile(src_file, dst_file)
        msg = yf.getInfo('复制文件[{1}]到[{2}]成功!', (src_file, dst_file,))
        yf.writeLog('文件管理', msg)
        stat = os.stat(src_file)
        os.chown(dst_file, stat.st_uid, stat.st_gid)
        return yf.returnData(True, 'file.py_msg_e79b89')
    except Exception as _e:
        return yf.returnData(False, 'file.py_msg_72a3a6')

def setFileAccept(filename):
    import pwd as _pwd
    try:
        if not os.path.exists(filename):
            return
        if yf.getOs() == 'darwin':
            user = yf.execShell("who | sed -n '2, 1p' |awk '{print $1}'")[0].strip() or 'www'
            auth_user = user
            auth_group = 'staff'
        else:
            auth_user = 'www'
            auth_group = 'www'
        try:
            uid = _pwd.getpwnam(auth_user).pw_uid
            gid = _pwd.getpwnam(auth_group).pw_gid
        except Exception:
            try:
                uid = _pwd.getpwnam('www').pw_uid
                gid = _pwd.getpwnam('www').pw_gid
            except Exception:
                uid = gid = 0
        for root, dirs, files in os.walk(filename):
            for d in dirs:
                try:
                    os.chown(os.path.join(root, d), uid, gid)
                    os.chmod(os.path.join(root, d), 0o755)
                except Exception:
                    pass
            for f in files:
                try:
                    os.chown(os.path.join(root, f), uid, gid)
                    os.chmod(os.path.join(root, f), 0o755)
                except Exception:
                    pass
        try:
            os.chown(filename, uid, gid)
            os.chmod(filename, 0o755)
        except Exception:
            pass
    except Exception:
        pass

def createFile(file_path):
    try:
        if not checkFileName(file_path):
            return yf.returnData(False, 'file.py_msg_4472a5')
        if os.path.exists(file_path):
            return yf.returnData(False, 'file.py_msg_2311cd')
        _path = os.path.dirname(file_path)
        if not os.path.exists(_path):
            os.makedirs(_path)
        open(file_path, 'w+').close()
        setFileAccept(file_path)
        msg = yf.getInfo('创建文件[{1}]成功!', (file_path,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'file.py_msg_673293')
    except Exception as e:
        return yf.returnData(True, 'utils.py_msg_f22f69', None, str(e))

def createDir(path):
    try:
        if not checkFileName(path):
            return yf.returnData(False, 'file.py_msg_e89037')
        if os.path.exists(path):
            return yf.returnData(False, 'file.py_msg_db3560')
        os.makedirs(path)
        setFileAccept(path)
        msg = yf.getInfo('创建目录[{1}]成功!', (path,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'file.py_msg_f50f32')
    except Exception as e:
        print(e)
        return yf.returnData(False, 'file.py_msg_7c6668')

# 检查敏感目录
def checkDir(path):
    path = path.replace('//', '/')
    if path[-1:] == '/':
        path = path[:-1]

    sense_dir = ('',
        '/',
        '/*',
        '/www',
        '/root',
        '/boot',
        '/bin',
        '/etc',
        '/home',
        '/dev',
        '/sbin',
        '/var',
        '/usr',
        '/tmp',
        '/sys',
        '/proc',
        '/media',
        '/mnt',
        '/opt',
        '/lib',
        '/srv',
        '/selinux',
        '/www/server',
        yf.getRootDir())
    return not path in sense_dir

def getFileBody(path):
    if not os.path.exists(path):
        return yf.returnData(False, 'file.py_msg_d9523e', (path,))

    if os.path.getsize(path) > 2097152:
        return yf.returnData(False, 'file.py_msg_b50947')

    if os.path.isdir(path):
        return yf.returnData(False, 'file.py_msg_92c109')

    fp = open(path, 'rb')
    data = {}
    data['status'] = True
    if fp:
        srcBody = fp.read()
        fp.close()

        encoding_list = ['utf-8', 'GBK', 'BIG5']
        for el in encoding_list:
            try:
                data['encoding'] = el
                data['data'] = srcBody.decode(data['encoding'])
                break
            except Exception as ex:
                if el == 'BIG5':
                    return yf.returnData(False, 'utils.py_msg_f48da9', None, str(ex))
    else:
        return yf.returnData(False, 'file.py_msg_aaad51')
    return yf.returnData(True, 'OK', data)

def saveBody(path, data, encoding):
    if not os.path.exists(path):
        return yf.returnData(False, 'file.py_msg_d9523e')
    try:
        if encoding == 'ascii':
            encoding = 'utf-8'

        data = data.encode(encoding, errors='ignore').decode(encoding)
        fp = open(path, 'w+', encoding=encoding)
        fp.write(data)
        fp.close()

        if path.find("web_conf") > 0:
            yf.restartWeb()
        yf.writeLog('文件管理', '文件[{1}]保存成功', (path,))
        return yf.returnData(True, 'file.py_msg_24c6ab')
    except Exception as ex:
        return yf.returnData(False, 'utils.py_msg_35752c', None, str(ex))


def sortFileList(path, ftype = 'mtime', sort = 'desc'):
    flist = os.listdir(path)
    
    def safe_mtime(f):
        try: return os.lstat(os.path.join(path, f)).st_mtime
        except Exception as _e: return 0
        
    def safe_size(f):
        try: return os.lstat(os.path.join(path, f)).st_size
        except Exception as _e: return 0

    if ftype == 'mtime':
        if sort == 'desc':
            flist = sorted(flist, key=safe_mtime, reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=safe_mtime, reverse=False)

    if ftype == 'size':
        if sort == 'desc':
            flist = sorted(flist, key=safe_size, reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=safe_size, reverse=False)

    if ftype == 'fname':
        if sort == 'desc':
            flist = sorted(flist, key=lambda f: os.path.join(path,f), reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=lambda f: os.path.join(path,f), reverse=False)
    return flist

def sortAllFileList(path, ftype = 'mtime', sort = 'desc', search = '', limit = 3000, max_depth = 3):
    count = 0
    flist = []
    base_depth = path.rstrip(os.sep).count(os.sep)
    for d_list in os.walk(path, topdown=True, followlinks=False):
        cur_depth = d_list[0].rstrip(os.sep).count(os.sep) - base_depth
        if cur_depth > max_depth:
            d_list[1][:] = []
            continue
        # 防止符号链接目录被误展开
        d_list[1][:] = [d for d in d_list[1] if not os.path.islink(os.path.join(d_list[0], d))]
        if count >= limit:
            break
        for d in d_list[1]:
            if count >= limit:
                break
            if d.lower().find(search) != -1:
                filename = d_list[0] + '/' + d
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)
        for f in d_list[2]:
            if count >= limit:
                break
            if f.lower().find(search) != -1:
                filename = d_list[0] + '/' + f
                if os.path.islink(filename):
                    continue
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)

    def safe_mtime(f):
        try: return os.lstat(f).st_mtime
        except Exception as _e: return 0

    def safe_size(f):
        try: return os.lstat(f).st_size
        except Exception as _e: return 0

    if ftype == 'mtime':
        if sort == 'desc':
            flist = sorted(flist, key=safe_mtime, reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=safe_mtime, reverse=False)

    if ftype == 'size':
        if sort == 'desc':
            flist = sorted(flist, key=safe_size, reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=safe_size, reverse=False)
    return flist

def _adaptive_file_limits(requested_size, requested_limit):
    """依据本机资源连续推导分页/扫描上限，低配收缩、高配放大"""
    try:
        from core.resources import get_dir_list_limits
        max_page, max_scan = get_dir_list_limits()
    except Exception:
        max_page, max_scan = 100, 3000
    size = min(int(requested_size or 10), max_page)
    limit = min(int(requested_limit or 3000), max_scan)
    return size, limit, (requested_size > max_page or requested_limit > max_scan)


def getAllDirList(path, page=1, size=10, order = '', search=None):
    if page < 1:
        page = 1

    data = {}
    dirnames = []
    filenames = []

    max_limit = 3000
    # 资源自适应：低配缩限防止 node_modules 类目录阻塞单核
    try:
        from core.resources import get_dir_list_limits
        _, adaptive_scan = get_dir_list_limits()
        max_limit = min(max_limit, adaptive_scan)
    except Exception:
        pass
    order_split = order.split(' ')
    if len(order_split) < 2:
        flist = sortAllFileList(path, order_split[0],'',search, max_limit)
    else:
        flist = sortAllFileList(path, order_split[0], order_split[1], search, max_limit)

    count = len(flist)
    # 自适应分页：低配每页更小，减少单次 stat 数量
    try:
        from core.resources import get_dir_list_limits
        max_page, _ = get_dir_list_limits()
        if size > max_page:
            size = max_page
    except Exception:
        pass
    start = (page - 1) * size
    end = start + size
    if end > count:
        end = count

    plist = flist[start:end]
    for dst_file in plist:
        if not os.path.exists(dst_file):
            continue
        stat = yf.getFileStatsDesc(dst_file, path)
        if os.path.isdir(dst_file):
            dirnames.append(stat)
        else:
            filenames.append(stat)

    data['count'] = count
    data['dir'] = dirnames
    data['files'] = filenames
    data['path'] = path.replace('//', '/')
    # 告知前端是否因资源限制被截断，便于分页提示
    try:
        from core.resources import get_dir_list_limits
        _, a_scan = get_dir_list_limits()
        if count >= a_scan:
            data['truncated'] = True
    except Exception:
        pass
    return data

def getDirList(path, page=1, size=10, order = '', search=None):
    # 资源自适应分页上限
    try:
        from core.resources import get_dir_list_limits
        max_page, _ = get_dir_list_limits()
        if int(size) > max_page:
            size = max_page
    except Exception:
        pass
    if page < 1:
        page = 1

    data = {}
    dirnames = []
    filenames = []

    try:
        with os.scandir(path) as it:
            raw_entries = [e for e in it if e.name not in ('.', '..')]
    except Exception:
        raw_entries = []

    if search:
        search_lower = str(search).lower()
        entries = [e for e in raw_entries if search_lower in e.name.lower()]
    else:
        entries = raw_entries

    count = len(entries)

    order_split = order.strip().split() if order else []
    ftype = order_split[0] if len(order_split) > 0 else 'mtime'
    sort_dir = order_split[1] if len(order_split) > 1 else 'desc'
    reverse = (sort_dir == 'desc')

    if ftype == 'mtime':
        def _safe_mtime(e):
            try:
                return e.stat().st_mtime
            except Exception as _e:
                return 0
        entries.sort(key=_safe_mtime, reverse=reverse)
    elif ftype == 'size':
        def _safe_size(e):
            try:
                return e.stat().st_size
            except Exception as _e:
                return 0
        entries.sort(key=_safe_size, reverse=reverse)
    elif ftype == 'fname':
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)
    else:
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)

    start = (page - 1) * size
    end = min(start + size, count)
    plist = entries[start:end]

    for entry in plist:
        abs_file = entry.path
        if not os.path.exists(abs_file):
            continue

        stats = yf.getFileStatsDesc(abs_file, path)
        try:
            is_dir = entry.is_dir()
        except Exception as _e:
            is_dir = os.path.isdir(abs_file)

        if is_dir:
            dirnames.append(stats)
        else:
            filenames.append(stats)

    data['count'] = count
    data['dir'] = dirnames
    data['files'] = filenames
    data['path'] = path.replace('//', '/')
    return data

# 检测文件名
def checkFileName(filename):
    nots = ['\\', '&', '*', '|', ';']
    if filename.find('/') != -1:
        filename = filename.split('/')[-1]
    for n in nots:
        if n in filename:
            return False
    return True


# 获取目录大小（followlinks=False + 超时熔断，1C1G不阻塞）
def getDirSize(filePath, size=0, _max_walk_files=50000):
    if not os.path.exists(filePath):
        return 0
    if not os.path.isdir(filePath):
        try:
            return os.path.getsize(filePath)
        except Exception:
            return 0
    walked = 0
    for root, dirs, files in os.walk(filePath, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for f in files:
            if walked >= _max_walk_files:
                return size
            fp = os.path.join(root, f)
            if os.path.islink(fp):
                continue
            try:
                size += os.path.getsize(fp)
            except Exception as _e:
                pass
            walked += 1
    return size

# 字节单位格式化(与前端 toSize 保持完全一致)
def formatFileSize(size):
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    size = float(size) if size else 0.0
    for i, u in enumerate(units):
        if size < 1024:
            if i == 0:
                return f"{int(size)} {u}"
            return f"{size:.2f} {u}"
        size = size / 1024.0
    return f"{size:.2f} PB"

# 获取目录大小(bash/实际字节数) — 超大目录 timeout 3s 熔断
def getDirSizeByBash(path):
    if not os.path.exists(path):
        return '0 B'
    try:
        out, err = yf.execShell('timeout 3 du -sb ' + yf.shlexQuote(path))
        if out and not err:
            parts = out.strip().split()
            if parts and parts[0].isdigit():
                return formatFileSize(int(parts[0]))
    except Exception:
        pass
    try:
        import subprocess as _sp
        r = _sp.run(['du', '-sb', path], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout:
            parts = r.stdout.strip().split()
            if parts and parts[0].isdigit():
                return formatFileSize(int(parts[0]))
    except Exception:
        pass
    try:
        size = getDirSize(path)
        return formatFileSize(size)
    except Exception:
        return '0 B'

# 计算文件数量
def getCount(path, search = None):
    i = 0
    for name in os.listdir(path):
        if name == '.' or name == '..':
            continue
        if search:
            if name.lower().find(search) == -1:
                continue
        i += 1
    return i

# 获取文件权限
def getAccess(fname):
    data = {}
    try:
        stat = os.stat(fname)
        data['chmod'] = str(oct(stat.st_mode)[-3:])
        data['chown'] = pwd.getpwuid(stat.st_uid).pw_name
    except Exception as e:
        # print(e)
        data['chmod'] = 755
        data['chown'] = 'www'
    return data

def setFileAccess(filename,user,access):
    sall = '-R'
    try:
        if not checkDir(filename):
            return yf.returnData(False, 'file.py_msg_e28c2c')

        if not os.path.exists(filename):
            return yf.returnData(False, 'file.py_msg_e0fb06')

        # 使用原生 Python 操作替换 os.system
        mode = int(access, 8)
        for root, dirs, files in os.walk(filename):
            for d in dirs:
                os.chmod(os.path.join(root, d), mode)
                shutil.chown(os.path.join(root, d), user, user)
            for f in files:
                os.chmod(os.path.join(root, f), mode)
                shutil.chown(os.path.join(root, f), user, user)
        os.chmod(filename, mode)
        shutil.chown(filename, user, user)

        msg = yf.getInfo('设置[{1}]权限为[{2}]所有者为[{3}]', (filename, access, user,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'common.set_success')
    except Exception as e:
        return yf.returnData(False, 'utils.py_msg_faaec9', None, str(e))

def getSysUserList():
    pwd_file = '/etc/passwd'
    if os.path.exists(pwd_file):
        content = yf.readFile(pwd_file)
        clist = content.split('\n')
        sys_users = []
        for line in clist:
            if line.find(":")<0:
                continue
            lines = line.split(":",1)
            sys_users.append(lines[0])
        return sys_users
    return ['root','mysql','www']

def getOccupyingProcess(path):
    try:
        # 优先 psutil 轻量探测（零 fork，比 lsof +D 快且不阻塞单核）
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                try:
                    flist = proc.info.get('open_files') or []
                    for f in flist:
                        fp = f.path if hasattr(f, 'path') else str(f)
                        if fp == path or fp.startswith(path + os.sep):
                            return "被进程 %s (PID: %s) 占用" % (proc.info.get('name') or proc.pid, proc.info.get('pid'))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        # 回退 lsof，带 2s 超时防止大目录阻塞（仅对文件用 lsof 单文件，目录不再 +D 遍历）
        try:
            import subprocess
            import shlex
            if os.path.isdir(path):
                # 目录场景 lsof +D 极易阻塞，1C1G 上直接返回通用提示而非阻塞 5s
                try:
                    from core.resources import is_low as _is_low
                    if _is_low():
                        return "(目录被占用，请检查是否有进程正在使用该目录)"
                except Exception:
                    pass
                cmd = ['lsof', path]
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
            else:
                out, _ = yf.execShell("lsof '%s' 2>/dev/null" % path.replace("'", "'\\''"))
            if out:
                lines = out.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        return "被进程 " + parts[0] + " (PID: " + parts[1] + ") 占用"
        except Exception:
            pass
        # 最后回退 fuser
        try:
            out2, _ = yf.execShell("fuser -v '%s' 2>&1" % path.replace("'", "'\\''"))
            if out2:
                for line in out2.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 4 and parts[1].isdigit():
                        return "被进程 " + parts[3] + " (PID: " + parts[1] + ") 占用"
        except Exception:
            pass
        import platform
        if platform.system() == 'Windows':
            return "(当前为Windows开发环境，未配置lsof命令，暂无法展示具体锁死进程)"
        return "(未检测到具体占用进程，可能是权限不足或隐藏系统进程占用)"
    except Exception:
        pass
    return "(请检查目录/文件权限或是否被占用)"

def fileDelete(path):
    if not os.path.exists(path):
        return yf.returnData(False, 'file.py_msg_e0fb06')

    try:
        import subprocess as _sp
        _sp.run(['chattr', '-i', path], timeout=2, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception:
        pass

    try:
        recycle_bin = thisdb.getOption('recycle_bin')
        if recycle_bin == 'open':
            if mvRecycleBin(path):
                return yf.returnData(True, 'file.py_msg_6cae10')
            occ = getOccupyingProcess(path)
            msg = '移动到回收站失败!'
            if occ:
                msg += ' ' + occ
            return yf.returnData(False, msg)
            
        os.remove(path)
        if os.path.exists(path):
            occ = getOccupyingProcess(path)
            msg = '删除文件失败!'
            if occ:
                msg += ' ' + occ
            return yf.returnData(False, msg)
            
        yf.writeLog('文件管理', yf.getInfo('删除文件[{1}]成功!', (path,)))
        return yf.returnData(True, 'file.py_msg_373ef8')
    except Exception as e:
        occ = getOccupyingProcess(path)
        msg = '删除文件失败!'
        if occ:
            msg += ' ' + occ
        return yf.returnData(False, msg)

def dirDelete(path):
    if not os.path.exists(path):
        return yf.returnData(False, 'file.py_msg_639dba')

    try:
        import subprocess as _sp
        _sp.run(['chattr', '-R', '-i', path], timeout=3, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception:
        pass

    try:
        recycle_bin = thisdb.getOption('recycle_bin')
        if recycle_bin == 'open':
            if mvRecycleBin(path):
                return yf.returnData(True, 'file.py_msg_6cae10')
            occ = getOccupyingProcess(path)
            msg = '移动到回收站失败!'
            if occ:
                msg += ' ' + occ
            return yf.returnData(False, msg)
            
        if not yf.removeDir(path) or os.path.exists(path):
            occ = getOccupyingProcess(path)
            msg = '删除目录失败!'
            if occ:
                msg += ' ' + occ
            return yf.returnData(False, msg)
            
        yf.writeLog('文件管理', '删除{1}成功！', (path,))
        return yf.returnData(True, 'file.py_msg_373ef8')
    except Exception as _e:
        occ = getOccupyingProcess(path)
        msg = '删除目录失败!'
        if occ:
            msg += ' ' + occ
        return yf.returnData(False, msg)

# 关闭
def toggleRecycleBin():
    recycle_bin = thisdb.getOption('recycle_bin')
    if recycle_bin == 'open':
        thisdb.setOption('recycle_bin','close')
        yf.writeLog('文件管理', '已关闭回收站功能!')
        return yf.returnData(True, 'file.py_msg_e7e158')
    else:
        thisdb.setOption('recycle_bin','open')
        yf.writeLog('文件管理', '已开启回收站功能!')
        return yf.returnData(True, 'file.py_msg_92f782')

def getRecycleBin():
    rb_dir = yf.getRecycleBinDir()
    recycle_bin = thisdb.getOption('recycle_bin')

    data = {}
    data['dirs'] = []
    data['files'] = []
    data['status'] = False
    if recycle_bin == 'open': 
        data['status'] = True
    
    for file in os.listdir(rb_dir):
        try:
            tmp = {}
            fname = rb_dir+'/'+ file
            tmp1 = file.replace('_mw_', '_yf_').split('_yf_')
            tmp2 = tmp1[len(tmp1) - 1].split('_t_')
            tmp['rname'] = file
            tmp['dname'] = file.replace('_mw_', '/').replace('_yf_', '/').split('_t_')[0]
            tmp['name'] = tmp2[0]
            tmp['time'] = int(float(tmp2[1]))
            if os.path.islink(fname):
                filePath = os.readlink(fname)
                link = ' -> ' + filePath
                if os.path.exists(filePath):
                    tmp['size'] = os.path.getsize(filePath)
                else:
                    tmp['size'] = 0
            else:
                tmp['size'] = os.path.getsize(fname)
            if os.path.isdir(fname):
                data['dirs'].append(tmp)
            else:
                data['files'].append(tmp)
        except Exception as e:
            continue

    return yf.returnJson(True, 'OK', data)

def delRecycleBin(path):
    rb_dir = yf.getRecycleBinDir()
    rb_file = rb_dir + '/' + path
    if os.path.isdir(rb_file):
        import shutil
        shutil.rmtree(rb_file)
    else:
        os.remove(rb_file)

    tfile = path.replace('_mw_', '/').replace('_yf_', '/').split('_t_')[0]
    msg = yf.getInfo('已彻底从回收站删除[{1}]!', (tfile,))
    yf.writeLog('文件管理', msg)
    return yf.returnJson(True, msg)

# 移动到回收站
def mvRecycleBin(path):
    rb_dir = yf.getRecycleBinDir()
    rb_file = rb_dir + '/' + path.replace('/', '_yf_') + '_t_' + str(time.time())
    try:
        import shutil
        shutil.move(path, rb_file)
        yf.writeLog('文件管理', yf.getInfo('移动[{1}]到回收站成功!', (path,)))
        return True
    except Exception as e:
        yf.writeLog('文件管理', yf.getInfo('移动[{1}]到回收站失败!', (path,)))
        return False

# 回收站文件恢复
def reRecycleBin(path):
    rb_dir = yf.getRecycleBinDir()
    dst_file = path.replace('_mw_', '/').replace('_yf_', '/').split('_t_')[0]
    try:
        import shutil
        shutil.move(rb_dir + '/' + path, dst_file)
        msg = yf.getInfo('移动文件[{1}]到回收站成功!', (dst_file,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(True, 'file.py_msg_f85ba7')
    except Exception as e:
        msg = yf.getInfo('从回收站恢复[{1}]失败!', (dst_file,))
        yf.writeLog('文件管理', msg)
        return yf.returnData(False, 'file.py_msg_6d3445')


def closeRecycleBin():
    rb_dir = yf.getRecycleBinDir()
    try:
        import subprocess as _sp
        _sp.run(['chattr', '-R', '-i', rb_dir], timeout=3, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception:
        pass
    rlist = os.listdir(rb_dir)
    i = 0
    l = len(rlist)
    for name in rlist:
        i += 1
        path = rb_dir + '/' + name
        yf.writeSpeed(name, i, l)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    yf.writeSpeed(None, 0, 0)
    yf.writeLog('文件管理', '已清空回收站!')
    return yf.returnJson(True, 'file.py_msg_d88584')


# 设置文件和目录权限
def setMode(path):
    s_path = os.path.dirname(path)
    p_stat = os.stat(s_path)
    os.chown(path, p_stat.st_uid, p_stat.st_gid)
    os.chmod(path, p_stat.st_mode)


def closeLogs():
    log_file = yf.getLogsDir()
    _base = yf.getFatherDir()
    if log_file.startswith(_base) and os.path.isdir(log_file):
        for name in os.listdir(log_file):
            p = os.path.join(log_file, name)
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except Exception:
                pass
    yf.opWeb('reload')
    yf.writeLog('文件管理', '网站日志已被清空!')
    tmp = getDirSizeByBash(log_file)
    return yf.returnData(True, tmp)
