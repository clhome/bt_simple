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
import logging

_log = logging.getLogger('yf.system.update')

#: 合法升级版本号的形状（GitHub tag）：字母数字与 . _ -，最长 64，必须以数字开头。
_UPDATE_VERSION_RE = re.compile(r'^v?[0-9][0-9A-Za-z._-]{0,63}$')


def isAllowedUpdateVersion(version, remote_tag):
    """升级目标版本是否放行：形状合法，且就是本次检测到的那个 tag。

    为什么必须收紧：``version`` 会被拼进下载 URL（``yf.githubDownload`` 再把它拼进
    wget 的 shell 命令）以及 ``temp/bt_simple-<version>`` 目录名。未校验时任意值
    = root 权限命令注入（``"; touch /x; echo "``）或路径穿越（``..`` 让安装阶段的
    拷贝/删除打到面板目录之外）。面板的升级入口只会传本次检测到的 tag，
    其它取值没有合法用途。
    """
    version = str(version).strip()
    if not _UPDATE_VERSION_RE.match(version):
        return False
    if not remote_tag:
        return False
    return version.lstrip('v') == str(remote_tag).strip().lstrip('v')


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

        # distutils 已在 Python 3.12 中移除，优先使用 packaging.version；
        # packaging 缺失时退回 distutils（Python < 3.12）；若均缺失则采用纯 Python 元组兜底
        is_greater = False
        try:
            from packaging.version import Version
            is_greater = Version(new) > Version(now)
        except Exception:
            try:
                from distutils.version import LooseVersion as Version
                is_greater = Version(new) > Version(now)
            except Exception:
                def _parse_v(v):
                    parts = []
                    for seg in re.split(r'(\d+)', str(v)):
                        if seg.isdigit():
                            parts.append((0, int(seg)))
                        elif seg:
                            parts.append((1, seg))
                    return tuple(parts)
                is_greater = _parse_v(new) > _parse_v(now)

        if is_greater:
            return 'new'
    except Exception as _e:
        _log.debug('[update] 版本号比较失败: %s', _e)
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
    except Exception as _e:
        _log.debug('[update] 解析版本信息失败: %s', _e)

    # 步骤2: 直连 API 失败（中国境内常见），改用代理轮询获取 releases 信息
    # 注意：GitHub 代理站不支持代理 api.github.com（会返回 403），
    # 但支持代理 github.com 的普通页面，利用 releases/latest 的 302 重定向获取最新 tag，
    # 再通过代理获取 raw.githubusercontent.com 上的 release body。
    try:
        return _getServerInfoViaProxy()
    except Exception as _e:
        _log.debug('[update] 代理获取版本信息失败: %s', _e)

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
    yf.execShell(cmd, timeout=yf.EXEC_ARCHIVE_TIMEOUT)
    
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
        
    # 解压快照覆盖回面板目录（列表传参：快照路径不参与 shell 解析）
    yf.safeExecShell(['tar', '-xzf', backup_file, '-C', panel_dir], timeout=300)
    
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


# ---------------------------------------------------------------------------------
# 面板自升级的供应链闸门（fail-closed）
# ---------------------------------------------------------------------------------
# 历史实现是 fail-open：Release body 里**恰好写了** `sha256:` 才比对哈希，没写就
# 跳过全部完整性校验；全流程无签名验证；下载还显式跳过了 TLS 证书校验；解压用裸
# `extractall`（无成员校验，面板以 root 运行 → 恶意包可写到目标目录之外）。
# 下面四件事全部收敛到「不过就拒绝 + 删包 + 一个文件都不落地」：
#   1. Release body 必须声明 sha256（缺声明 = 发布流程不完整 → 拒绝升级）；
#   2. 必须带 SHA256SUMS + SHA256SUMS.minisig，并用 repo 自带验签器**子进程**验签；
#   3. 下载不再降级到不校验证书（见 core/yf/github.py）；
#   4. 解压前必须过 safeArchiveCheck（成员名校验）。

#: 发布验签器与发布公钥（随发布包下发；面板内**不**复制验签逻辑，只调用这一份）
RELEASE_VERIFIER_REL = os.path.join('scripts', 'tools', 'yf_release_verify.py')
RELEASE_PUBKEY_REL = os.path.join('keys', 'yf-release.pub')


def _resolve_release_asset(rel_path):
    """定位随发布包下发的验签资产（验签器 / 公钥）：面板目录优先，其次仓库开发目录。

    两个位置都没有就返回空串 —— 调用方必须据此**拒绝升级**：
    「找不到验签器」绝不能等价于「不需要验签」。
    """
    candidates = []
    try:
        panel_dir = yf.getPanelDir()
    except Exception as e:
        _log.warning('[update] 取面板目录失败: %s', e)
        panel_dir = ''
    if panel_dir:
        candidates.append(os.path.join(panel_dir, rel_path))
    # web/utils/system/update.py -> 仓库根（开发/测试态）
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.normpath(os.path.join(here, os.pardir, os.pardir, os.pardir, rel_path)))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ''


def _release_body_sha256(body):
    """从 Release body 取 sha256 声明；**没写就返回空串**，由调用方拒绝升级。"""
    release_body = str(body or '')
    sha256_match = re.search(r'sha256\s*[:=]\s*([a-fA-F0-9]{64})', release_body)
    if not sha256_match:
        return ''
    return sha256_match.group(1).strip().lower()


def _run_release_verifier(dist_yf, sums_path, sig_path, pubkey_path, verifier_path, timeout=120):
    """子进程调用 scripts/tools/yf_release_verify.py 验签，返回 (ok, msg)。

    故意走子进程而不是 import：验签器的唯一实现只能有一份（deploy.sh 里那份与本文件
    由 test_release_signature.py 逐字节锁定），面板侧绝不复制一份平行实现。
    退出码 0 才算通过；其它任何情况（含无法执行）一律失败。
    """
    import subprocess
    # 参数以 argv 列表直接展开：不经 shell、也不落成「裸变量进 shell 函数」的形态
    # （testsuite/test_shell_concat_ratchet.py 的 bare_variable 规则会拦住后者）
    try:
        proc = subprocess.run(
            [sys.executable, verifier_path,
             '--pubkey', pubkey_path, '--sums', sums_path,
             '--sig', sig_path, '--file', dist_yf, '--quiet'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except Exception as e:
        return False, '发布签名校验无法执行：%s' % e
    if proc.returncode == 0:
        return True, '发布签名校验通过'
    detail = (proc.stderr or proc.stdout or b'').decode('utf-8', 'replace').strip()
    return False, '发布签名校验失败(exit=%s)：%s' % (proc.returncode, detail or '验签器无输出')


def _verify_release(dist_yf, body, sums_path, sig_path, pubkey_path=None, verifier_path=None):
    """升级包「完整性 + 发布签名」的唯一闸门，返回 (ok, msg)。

    fail-closed 四道关卡，任一不过都返回 False：
      1. Release body 必须声明 sha256（缺声明 → 拒绝升级）；
      2. SHA256SUMS / SHA256SUMS.minisig 必须存在；
      3. 用 repo 自带验签器（子进程）验签 + 比对清单里的哈希；
      4. body 声明的 sha256 必须等于升级包实际哈希（双重锚定）。
    """
    # 1. sha256 声明是**必备项**（旧实现「没写就跳过」已删除）
    expected_sha = _release_body_sha256(body)
    if not expected_sha:
        return False, '发布流程缺少 sha256，拒绝升级'

    if not dist_yf or not os.path.isfile(dist_yf):
        return False, '升级包不存在，拒绝升级'

    # 2. 签名清单与签名缺一不可
    if not sums_path or not os.path.isfile(sums_path):
        return False, '缺少发布校验清单 SHA256SUMS，拒绝升级'
    if not sig_path or not os.path.isfile(sig_path):
        return False, '缺少发布签名 SHA256SUMS.minisig，拒绝升级'

    # 3. 验签器 / 公钥缺失同样拒绝（不许「没法校验就当通过」）
    if not verifier_path or not os.path.isfile(verifier_path):
        verifier_path = _resolve_release_asset(RELEASE_VERIFIER_REL)
    if not verifier_path or not os.path.isfile(verifier_path):
        return False, '缺少发布验签器 yf_release_verify.py，拒绝升级'
    if not pubkey_path or not os.path.isfile(pubkey_path):
        pubkey_path = _resolve_release_asset(RELEASE_PUBKEY_REL)
    if not pubkey_path or not os.path.isfile(pubkey_path):
        return False, '缺少发布公钥 yf-release.pub，拒绝升级'

    ok, msg = _run_release_verifier(dist_yf, sums_path, sig_path, pubkey_path, verifier_path)
    if not ok:
        return False, msg

    # 4. body 声明的 sha256 与实测哈希必须一致
    sha_ok, sha_msg = verify_sha256(dist_yf, expected_sha)
    if not sha_ok:
        return False, '发布声明 sha256 与升级包不符，拒绝升级：%s' % sha_msg

    return True, '升级包完整性与发布签名校验通过'


def _extract_upgrade_package(dist_yf, toPath):
    """解压升级包：**先** safeArchiveCheck 成员名校验，再解压。返回 (ok, msg)。

    为什么必须先校验：面板以 root 运行，成员名写成 `../evil.txt` 或绝对路径时，
    裸 extractall 会把文件写到 toPath 之外（root 任意文件写）。校验不过直接返回失败，
    一个文件都不落地。
    """
    try:
        import utils.file as file_utils
        check_ok, check_code = file_utils.safeArchiveCheck(dist_yf, toPath, 'zip')
    except Exception as e:
        # 校验都无法执行时同样拒绝（fail closed）
        return False, '升级包成员校验无法执行，拒绝解压：%s' % e
    if not check_ok:
        return False, '升级包含越界/非法成员，拒绝解压（%s）' % check_code

    # 解压（优先 Python zipfile 零 fork，低配防 OOM；回退 unzip）
    try:
        import zipfile
        with zipfile.ZipFile(dist_yf, 'r') as zf:
            zf.extractall(toPath)
        return True, '升级包解压完成'
    except Exception as e:
        _log.warning('[update] python 解压失败，回退 unzip: %s', e)
    yf.safeExecShell(['unzip', '-o', dist_yf, '-d', toPath], timeout=90)
    return True, '升级包解压完成'


def _cleanup_upgrade_temp(*paths):
    """拒绝升级时清掉已下载的文件（包 / 清单 / 签名），不留可被后续步骤复用的残留。"""
    for path in paths:
        try:
            if path and os.path.exists(path):
                yf.deleteFile(path)
        except Exception as e:
            _log.warning('[update] 清理升级临时文件失败 %s: %s', path, e)

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

            if not isAllowedUpdateVersion(version, new_ver):
                return yf.returnData(False, 'system.py_msg_7f876a')

            toPath = yf.getPanelDir() + '/temp'
            panel_dir = yf.getPanelDir()

            # 1. 下载阶段
            if step == 'download' or step == 'all':
                if not os.path.exists(toPath):
                    yf.makeDirs(toPath)

                originalUrl = "https://github.com/clhome/bt_simple/archive/refs/tags/" + version + ".zip"
                dist_yf = toPath + '/yf.zip'
                sums_yf = toPath + '/SHA256SUMS'
                sig_yf = toPath + '/SHA256SUMS.minisig'
                # 强制重新下载
                if os.path.exists(dist_yf): yf.deleteFile(dist_yf)
                if os.path.exists(sums_yf): yf.deleteFile(sums_yf)
                if os.path.exists(sig_yf): yf.deleteFile(sig_yf)
                
                # 使用带轮询降级机制的下载函数，设置期望最小大小为 1MB (1048576 bytes)，超时设置长一点
                download_status = yf.githubDownload(originalUrl, dist_yf, timeout=20, min_size=1048576)
                
                if not download_status or not os.path.exists(dist_yf):
                    return yf.returnData(False, 'system.py_msg_eb2036')

                # 升级包结构完整性前置校验（防截断与损坏包，保留为签名校验前的结构闸）
                valid_zip, zip_err = verify_zip_integrity(dist_yf)
                if not valid_zip:
                    _cleanup_upgrade_temp(dist_yf, sums_yf, sig_yf)
                    yf.writeFileLog('panel upgrade refused: zip integrity check failed: %s' % zip_err)
                    return yf.returnData(False, f"升级包完整性校验失败: {zip_err}")

                # 供应链防投毒闸门（fail-closed）：body 必须声明 sha256，且必须过 Ed25519 验签。
                # 旧实现在这里「body 没写 sha256 就跳过全部校验」，是本次要堵的 fail-open。
                release_body = str(version_new_info.get('body', ''))

                # 1) Release body 必须声明 sha256（缺声明 → 删包 + 拒绝，绝不继续往下走）
                if not _release_body_sha256(release_body):
                    _cleanup_upgrade_temp(dist_yf, sums_yf, sig_yf)
                    yf.writeFileLog('panel upgrade refused: release body of %s has no sha256 declaration' % version)
                    return yf.returnData(False, '发布流程缺少 sha256，拒绝升级')

                # 2) 下载发布签名清单 SHA256SUMS + SHA256SUMS.minisig（缺任一 → 拒绝）
                asset_base = "https://github.com/clhome/bt_simple/releases/download/" + version
                sums_ok = yf.githubDownload(asset_base + '/SHA256SUMS', sums_yf, timeout=20, min_size=0)
                sig_ok = yf.githubDownload(asset_base + '/SHA256SUMS.minisig', sig_yf, timeout=20, min_size=0)
                if not sums_ok or not sig_ok or not os.path.exists(sums_yf) or not os.path.exists(sig_yf):
                    _cleanup_upgrade_temp(dist_yf, sums_yf, sig_yf)
                    yf.writeFileLog('panel upgrade refused: missing SHA256SUMS/SHA256SUMS.minisig')
                    return yf.returnData(False, '未取得发布签名清单（SHA256SUMS/SHA256SUMS.minisig），拒绝升级')

                # 3) Ed25519 验签 + 哈希比对（验签器走子进程，不在面板内复制验签逻辑）
                verify_ok, verify_msg = _verify_release(dist_yf, release_body, sums_yf, sig_yf)
                if not verify_ok:
                    _cleanup_upgrade_temp(dist_yf, sums_yf, sig_yf)
                    yf.writeFileLog('panel upgrade refused: %s' % verify_msg)
                    return yf.returnData(False, verify_msg)

                # 4) 解压前过 safeArchiveCheck（成员名校验），不过就删包、不落地任何文件
                extract_ok, extract_msg = _extract_upgrade_package(dist_yf, toPath)
                if not extract_ok:
                    _cleanup_upgrade_temp(dist_yf, sums_yf, sig_yf)
                    yf.writeFileLog('panel upgrade refused: %s' % extract_msg)
                    return yf.returnData(False, extract_msg)

                # 验签与解压都完成后，签名清单不再需要
                _cleanup_upgrade_temp(sums_yf, sig_yf)
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
                    yf.writeFileLog("Update pre-install backup warning: " + str(backup_msg))

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

                # 执行代码覆盖：走 shutil 不经 shell（src_path 的目录名来自解压包，
                # 拼 shell 会被目录名里的元字符注入），且失败必须如实报错并回滚——
                # 否则面板停在「半新半旧」状态却回报“安装更新成功”。
                import shutil
                try:
                    shutil.copytree(src_path, panel_dir, dirs_exist_ok=True, symlinks=True)
                except Exception as copy_ex:
                    yf.writeFileLog('panel upgrade copy failed: %s -> %s' % (src_path, copy_ex))
                    if backup_status:
                        rollback_panel()
                        return yf.returnData(False, 'system.py_msg_339e87')
                    return yf.returnData(False, 'system.py_msg_fac254')

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

                # 自动检查并清理历史废弃插件（如 system_safe）
                try:
                    from admin.setup.cleanup import cleanup_legacy_plugins
                    cleanup_legacy_plugins()
                except Exception as e:
                    yf.writeFileLog("cleanup_legacy_plugins error: " + str(e))

                yf.restartPanel()
                return yf.returnData(True, 'system.py_msg_f9fd8e')

        return yf.returnData(False, 'system.py_msg_5b8e2d')
    except Exception as ex:
        return yf.returnData(False, 'utils.py_msg_35a520', None, str(ex))




