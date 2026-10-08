# coding=utf-8

import os
import json
import core.yf as yf
import thisdb


def _decrypt_old(key, value):
    """用旧密钥解密；**解不开返回 None**。

    为什么不能直接用 `yf.deDoubleCrypt` 的返回值判断「要不要迁移」：
    `deDoubleCrypt` 解不开时会**原样返回入参**（而且已经被 encode 成 bytes），
    于是 `decrypted != value` 恒为真（bytes vs str），调用方会把**密文本身**
    再加密一层。实测（真机库副本）：`.crypt_migrated` 标记文件丢失后连跑两次
    `migrate_encrypted_data`，two_step_verification 的 secret 从
    `gAAAAABqxum9...` 变成 `gAAAAABqxwz4zVQ7...` 再变成 `gAAAAABqxwz4hdkN...`
    —— 每跑一次多一层密文，用户二步验证/通知口令再也解不开。
    数据迁移必须幂等（用户可能从旧备份恢复库、或上次迁移被中断），所以这里
    显式区分「解不开」与「解出来与原文不同」。
    """
    if not value:
        return None
    try:
        out = yf.deDoubleCrypt(key, value)
    except Exception as _e:
        yf.writeFileLog('[crypt_migrate] 解密失败 %s: %s' % (key, _e))
        return None
    if not isinstance(out, str) or out == value:
        return None
    return out


def migrate_encrypted_data():
    """
    一次性将旧密钥加密的数据迁移到新密钥。
    解密（利用自动降级机制）后重新加密（利用新机制）。
    """
    flag_file = yf.getPanelDataDir() + '/.crypt_migrated'
    if os.path.exists(flag_file):
        return

    yf.writeLog('安全机制', '开始执行敏感数据安全加密迁移...')
    
    # 1. 迁移二步验证
    two_step = thisdb.getOptionByJson('two_step_verification', default={'open': False})
    if 'secret' in two_step:
        decrypted = _decrypt_old('mdserver-web', two_step['secret'])
        if decrypted:
            # 重加密必须用**读取方相同的 key**：读侧统一是 'mdserver-web'
            # （admin/dashboard/login.py 与 admin/setting/secondary_verifiy.py）。
            # 旧实现写 'yufeng_panel'，而 deDoubleCrypt 只会试 key+salt 与 key，
            # 于是迁移后二次验证的 secret 谁都解不开 —— 开了 2FA 的帐号直接登不进去。
            two_step['secret'] = yf.enDoubleCrypt('mdserver-web', decrypted)
            thisdb.setOption('two_step_verification', json.dumps(two_step))
            
    # 2. 迁移邮件通知
    notify_email = thisdb.getOptionByJson('notify_email', default={'open': False}, type='notify')
    if 'cfg' in notify_email:
        decrypted = _decrypt_old('email', notify_email['cfg'])
        if decrypted:
            notify_email['cfg'] = yf.enDoubleCrypt('email', decrypted)
            thisdb.setOption('notify_email', json.dumps(notify_email), type='notify')
            
    # 3. 迁移 TG Bot 通知
    notify_tgbot = thisdb.getOptionByJson('notify_tgbot', default={'open': False}, type='notify')
    if 'cfg' in notify_tgbot:
        decrypted = _decrypt_old('tgbot', notify_tgbot['cfg'])
        if decrypted:
            notify_tgbot['cfg'] = yf.enDoubleCrypt('tgbot', decrypted)
            thisdb.setOption('notify_tgbot', json.dumps(notify_tgbot), type='notify')
            
    # 4. 迁移 SSH 主机信息
    ssh_host_dir = yf.getServerDir() + '/webssh/host'
    if os.path.exists(ssh_host_dir):
        for host in os.listdir(ssh_host_dir):
            info_file = ssh_host_dir + '/' + host + '/info.json'
            if os.path.exists(info_file):
                try:
                    rdata = yf.readFile(info_file)
                    decrypted = _decrypt_old('mdserver-web', rdata)
                    if decrypted:
                        # 同二步验证：读侧（utils/ssh/ssh_terminal.py::getSshInfo）用的是
                        # 'mdserver-web'，写侧必须一致，否则迁移后 json.loads 直接炸。
                        enstr = yf.enDoubleCrypt('mdserver-web', decrypted)
                        yf.writeFile(info_file, enstr)
                except Exception as _e:
                    yf.writeFileLog('[crypt_migrate] 回写加密串失败: %s' % _e)
                    
    yf.writeFile(flag_file, '1')
    yf.writeLog('安全机制', '敏感数据安全加密迁移完成。')
