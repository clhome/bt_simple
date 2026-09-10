# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import sys
import re
import time
import math
import psutil
import json

import core.yf as yf

def versionDiff(now, new):
    '''
        test 测试
        new 有新版本
        none 没有新版本
    '''
    try:
        new = str(new).lstrip('v')
        now = str(now).lstrip('v')
        new_list = new.split('.')
        if len(new_list) > 3:
            return 'test'

        from distutils.version import LooseVersion
        if LooseVersion(new) > LooseVersion(now):
            return 'new'
    except Exception as _e:
        pass
    return 'none'

def getServerInfo():
    import urllib.request
    import ssl

    api_url = 'https://api.github.com/repos/clhome/bt_simple/releases/latest'

    # 步骤1: 直连 GitHub API（境外服务器通常可用）
    # 境内机器直连 API 常常超时或阻断，将超时缩短为 3 秒，让其尽快降级到代理
    try:
        context = ssl._create_unverified_context()
        req = urllib.request.urlopen(api_url, context=context, timeout=3)
        result = req.read().decode('utf-8')
        version = json.loads(result)
        return version
    except Exception:
        pass

    # 步骤2: 直连 API 失败（中国境内常见），改用代理轮询获取 releases 信息
    # 注意：GitHub 代理站不支持代理 api.github.com（会返回 403），
    # 但支持代理 github.com 的普通页面，利用 releases/latest 的 302 重定向获取最新 tag，
    # 再通过代理获取 raw.githubusercontent.com 上的 release body。
    try:
        return _getServerInfoViaProxy()
    except Exception:
        pass

    return None


def _getServerInfoViaProxy():
    """通过代理站获取远程版本信息（API 代理不可用时的降级方案）"""
    tag_name = None
    body = ''

    # 通过 curl 跟随重定向获取最新 tag（releases/latest 会 302 到 /tag/vX.Y.Z）
    latest_url = 'https://github.com/clhome/bt_simple/releases/latest'
    
    # 构造代理列表：优先使用系统测速最优的代理，其次轮询其他代理，最后再尝试直连
    fastest_proxy = yf.getGithubProxy()
    proxy_list = [fastest_proxy]
    for p in yf._GITHUB_PROXY_LIST:
        if p != fastest_proxy and p != "":
            proxy_list.append(p)
    if fastest_proxy != "":
        proxy_list.append("") # 如果最优代理不是直连，则将直连作为兜底方案

    for proxy in proxy_list:
        try:
            full_url = yf._makeGithubProxyUrl(proxy, latest_url)
            # -Ls: 跟随重定向并静默, -o /dev/null: 不保存内容, -w: 输出最终 URL。超时设为 5 秒加速重试
            cmd = 'curl -Ls -o /dev/null -w "%{{url_effective}}" -m 5 "{}"'.format(full_url)
            out, _ = yf.execShell(cmd)
            final_url = out.strip()
            if '/tag/' in final_url:
                tag_name = final_url.split('/tag/')[-1].strip()
                break
        except Exception:
            continue

    if not tag_name:
        return None

    # 通过代理获取 release body
    # 代理通常不支持 api.github.com，但支持 raw.githubusercontent.com
    raw_md_url = 'https://raw.githubusercontent.com/clhome/bt_simple/' + tag_name + '/RELEASE_TEMPLATE.md'
    for proxy in proxy_list:
        try:
            full_url = yf._makeGithubProxyUrl(proxy, raw_md_url)
            cmd = 'curl -s -m 5 "{}"'.format(full_url)
            out, _ = yf.execShell(cmd)
            # 如果成功获取到内容（不是 404）
            if out and len(out) > 50 and '404: Not Found' not in out:
                return {
                    'tag_name': tag_name,
                    'name': 'Release ' + tag_name,
                    'body': out.strip()
                }
        except Exception:
            continue

    # 如果 release body 获取失败，提供默认的 Markdown 提示
    default_body = "> ⚠️ 受限于当前网络环境，无法直接获取更新日志。\n\n"
    default_body += "请点击下方链接前往 GitHub 查看详细内容：\n\n"
    default_body += "[👉 查看 {} 更新说明](https://github.com/clhome/bt_simple/releases/tag/{})".format(tag_name, tag_name)

    return {
        'tag_name': tag_name,
        'name': 'Release ' + tag_name,
        'body': default_body
    }

def backup_panel():
    import time
    panel_dir = yf.getPanelDir()
    backup_dir = '/www/backup/panel'
    if not os.path.exists(backup_dir):
        yf.makeDirs(backup_dir)
    
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    version_file = panel_dir + '/.version'
    version = 'unknown'
    if os.path.exists(version_file):
        version = yf.readFile(version_file).strip()
    
    backup_file = f"{backup_dir}/bt_simple_{version}_{timestamp}.tar.gz"
    
    # 备份 web, panel_task.py, panel_tools.py 等核心文件，以及重要的安全配置文件
    cmd = f"cd {panel_dir} && tar -czf {backup_file} web panel_task.py panel_tools.py cli.sh version.py requirements.txt data/.crypt_salt 2>/dev/null || tar -czf {backup_file} web panel_task.py panel_tools.py cli.sh version.py requirements.txt"
    yf.execShell(cmd)
    
    if os.path.exists(backup_file):
        return True, f"备份成功: {backup_file}"
    return False, "备份失败"

def rollback_panel(backup_file=None):
    """回滚面板至指定快照备份或最新快照"""
    import glob
    panel_dir = yf.getPanelDir()
    backup_dir = '/www/backup/panel'
    
    if not backup_file:
        if not os.path.exists(backup_dir):
            return False, "未找到任何备份目录"
        archives = sorted(glob.glob(os.path.join(backup_dir, 'bt_simple_*.tar.gz')), reverse=True)
        if not archives:
            return False, "未找到任何历史快照备份"
        backup_file = archives[0]
        
    if not os.path.exists(backup_file):
        return False, f"备份文件不存在: {backup_file}"
        
    # 解压快照覆盖回面板目录
    cmd = f"tar -xzf {backup_file} -C {panel_dir}"
    yf.execShell(cmd)
    
    yf.restartPanel()
    return True, f"已成功回滚至快照: {os.path.basename(backup_file)}"

def verify_zip_integrity(zip_path):
    """验证 zip 文件结构的完整性，检测文件是否损坏或截断"""
    import zipfile
    if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 1024:
        return False, "升级包文件不存在或文件过小"
    try:
        if not zipfile.is_zipfile(zip_path):
            return False, "文件不是有效的 ZIP 格式压缩包"
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                return False, f"ZIP 压缩包损坏，损坏文件: {bad_file}"
        return True, "ZIP 完整性校验通过"
    except Exception as e:
        return False, f"ZIP 校验异常: {str(e)}"

def verify_sha256(file_path, expected_hash):
    """计算文件的 SHA-256 哈希值并与期望值比对"""
    import hashlib
    if not os.path.exists(file_path):
        return False, "待校验文件不存在"
    expected_hash = str(expected_hash).strip().lower()
    if not expected_hash:
        return True, "未指定期望哈希值，跳过校验"
    try:
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        calc_hash = sha256.hexdigest().lower()
        if calc_hash == expected_hash:
            return True, f"SHA-256 校验通过 ({calc_hash})"
        else:
            return False, f"SHA-256 校验不匹配！期望: {expected_hash}, 实际: {calc_hash}"
    except Exception as e:
        return False, f"哈希计算异常: {str(e)}"

def updateServer(stype, version='', step='all'):
    import config
    # 更新服务
    try:
        if not yf.isRestart():
            return yf.returnData(False, 'system.py_msg_0322b3')

        version_new_info = getServerInfo()
        if version_new_info is None:
            return yf.returnData(False, 'system.py_msg_e01968')

        version_now = config.APP_VERSION
        # 使用 tag_name 替代 name，确保版本号和 tag 一致
        new_ver = version_new_info['tag_name']
        if stype == 'check':
            diff = versionDiff(version_now, new_ver)
            if diff == 'new':
                return yf.returnData(True, 'system.py_msg_972d4e', new_ver)
            elif diff == 'test':
                return yf.returnData(True, 'system.py_msg_857da3', new_ver)
            else:
                return yf.returnData(False, 'system.py_msg_19420b')

        if stype == 'info':
            diff = versionDiff(version_now, new_ver)
            data = {}
            data['version'] = new_ver
            data['content'] = version_new_info['body']
            data['speed_name'] = yf.getGithubProxyName()
            return yf.returnData(True, 'system.py_msg_efa59f', data)

        if stype == 'update':
            if version == '':
                return yf.returnData(False, 'system.py_msg_988b58')

            toPath = yf.getPanelDir() + '/temp'
            panel_dir = yf.getPanelDir()

            # 1. 下载阶段
            if step == 'download' or step == 'all':
                if not os.path.exists(toPath):
                    yf.makeDirs(toPath)

                originalUrl = "https://github.com/clhome/bt_simple/archive/refs/tags/" + version + ".zip"
                dist_yf = toPath + '/yf.zip'
                # 强制重新下载
                if os.path.exists(dist_yf): yf.deleteFile(dist_yf)
                
                # 使用带轮询降级机制的下载函数，设置期望最小大小为 1MB (1048576 bytes)，超时设置长一点
                download_status = yf.githubDownload(originalUrl, dist_yf, timeout=20, min_size=1048576)
                
                if not download_status or not os.path.exists(dist_yf):
                    return yf.returnData(False, 'system.py_msg_eb2036')

                # 升级包结构完整性前置校验（防截断与损坏包）
                valid_zip, zip_err = verify_zip_integrity(dist_yf)
                if not valid_zip:
                    yf.deleteFile(dist_yf)
                    return yf.returnData(False, f"升级包完整性校验失败: {zip_err}")

                # 供应链防投毒检测：若 Release body 中附带 sha256 校验和声明，严格比对
                import re
                release_body = str(version_new_info.get('body', ''))
                sha256_match = re.search(r'sha256\s*[:=]\s*([a-fA-F0-9]{64})', release_body)
                if sha256_match:
                    expected_sha = sha256_match.group(1)
                    sha_ok, sha_msg = verify_sha256(dist_yf, expected_sha)
                    if not sha_ok:
                        yf.deleteFile(dist_yf)
                        return yf.returnData(False, f"供应链安全拦截：{sha_msg}")

                # 解压（优先 Python zipfile 零 fork，低配防 OOM；回退 unzip）
                try:
                    import zipfile
                    with zipfile.ZipFile(dist_yf, 'r') as zf:
                        zf.extractall(toPath)
                except Exception:
                    yf.safeExecShell(['unzip', '-o', dist_yf, '-d', toPath], timeout=90)
                if step == 'download':
                    return yf.returnData(True, 'system.py_msg_f00995')

            # 2. 备份阶段
            if step == 'backup':
                status, msg = backup_panel()
                return yf.returnData(status, msg)

            # 3. 安装阶段
            if step == 'install' or step == 'all':
                # 升级覆盖前强制执行核心快照备份，确保出现异常可立即回滚自愈
                backup_status, backup_msg = backup_panel()
                if not backup_status and step == 'all':
                    print("Update pre-install backup warning:", backup_msg)

                # 兼容带 v 和不带 v 的版本号目录名
                v_version = version if version.startswith('v') else 'v' + version
                no_v_version = version[1:] if version.startswith('v') else version
                
                src_path = ""
                if os.path.exists(toPath + '/bt_simple-' + v_version):
                    src_path = toPath + '/bt_simple-' + v_version
                elif os.path.exists(toPath + '/bt_simple-' + no_v_version):
                    src_path = toPath + '/bt_simple-' + no_v_version
                
                if src_path == "":
                    # 尝试查找解压出的任何目录
                    import glob
                    dirs = glob.glob(toPath + '/bt_simple-*')
                    if dirs:
                        src_path = dirs[0]
                    else:
                        return yf.returnData(False, 'system.py_msg_ac67c4')

                # 执行代码覆盖
                yf.execShell('cp -rf ' + src_path + '/* ' + panel_dir)
                
                # 清理临时文件
                yf.removeDir(src_path)
                yf.removeDir(toPath + '/yf.zip')
                
                # 自动写入版本号到 .version 文件
                version_path = panel_dir + '/.version'
                yf.writeFile(version_path, version)

                update_env = f'''
#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
P_VER=`python3 -V | awk '{{print $2}}'`
if [ ! -f {panel_dir}/bin/activate ];then
    cd {panel_dir} && python3 -m venv .
    cd {panel_dir} && source bin/activate
else
    cd {panel_dir} && source bin/activate
fi
cn=$(curl -fsSL -m 10 http://ipinfo.io/json | grep "\\"country\\": \\"CN\\"")
PIPSRC="https://pypi.python.org/simple"
if [ ! -z "$cn" ];then
    PIPSRC="https://pypi.tuna.tsinghua.edu.cn/simple"
fi
cd {panel_dir} && pip3 install -r requirements.txt -i $PIPSRC
P_VER_D=`echo "$P_VER"|awk -F '.' '{{print $1}}'`
P_VER_M=`echo "$P_VER"|awk -F '.' '{{print $2}}'`
NEW_P_VER=${{P_VER_D}}.${{P_VER_M}}
if [ -f {panel_dir}/version/r${{NEW_P_VER}}.txt ];then
    cd {panel_dir} && pip3 install -r version/r${{NEW_P_VER}}.txt -i $PIPSRC
fi
'''
                # 环境更新脚本落盘后以 shell 执行（面板路径来自程序内部，无用户输入）
                env_script = toPath + '/yf_env_update.sh'
                yf.writeFile(env_script, update_env)
                yf.safeExecShell(['bash', env_script], timeout=600)
                yf.restartPanel()
                return yf.returnData(True, 'system.py_msg_f9fd8e')

        return yf.returnData(False, 'system.py_msg_5b8e2d')
    except Exception as ex:
        return yf.returnData(False, 'utils.py_msg_35a520', None, str(ex))




