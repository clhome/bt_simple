# coding=utf-8

import os
import json
import core.mw as mw
import thisdb

def migrate_encrypted_data():
    """
    一次性将旧密钥加密的数据迁移到新密钥。
    解密（利用自动降级机制）后重新加密（利用新机制）。
    """
    flag_file = mw.getPanelDataDir() + '/.crypt_migrated'
    if os.path.exists(flag_file):
        return

    mw.writeLog('安全机制', '开始执行敏感数据安全加密迁移...')
    
    # 1. 迁移二步验证
    two_step = thisdb.getOptionByJson('two_step_verification', default={'open': False})
    if 'secret' in two_step:
        decrypted = mw.deDoubleCrypt('mdserver-web', two_step['secret'])
        if decrypted and decrypted != two_step['secret']:
            two_step['secret'] = mw.enDoubleCrypt('mdserver-web', decrypted)
            thisdb.setOption('two_step_verification', json.dumps(two_step))
            
    # 2. 迁移邮件通知
    notify_email = thisdb.getOptionByJson('notify_email', default={'open': False}, type='notify')
    if 'cfg' in notify_email:
        decrypted = mw.deDoubleCrypt('email', notify_email['cfg'])
        if decrypted and decrypted != notify_email['cfg']:
            notify_email['cfg'] = mw.enDoubleCrypt('email', decrypted)
            thisdb.setOption('notify_email', json.dumps(notify_email), type='notify')
            
    # 3. 迁移 TG Bot 通知
    notify_tgbot = thisdb.getOptionByJson('notify_tgbot', default={'open': False}, type='notify')
    if 'cfg' in notify_tgbot:
        decrypted = mw.deDoubleCrypt('tgbot', notify_tgbot['cfg'])
        if decrypted and decrypted != notify_tgbot['cfg']:
            notify_tgbot['cfg'] = mw.enDoubleCrypt('tgbot', decrypted)
            thisdb.setOption('notify_tgbot', json.dumps(notify_tgbot), type='notify')
            
    # 4. 迁移 SSH 主机信息
    ssh_host_dir = mw.getServerDir() + '/webssh/host'
    if os.path.exists(ssh_host_dir):
        for host in os.listdir(ssh_host_dir):
            info_file = ssh_host_dir + '/' + host + '/info.json'
            if os.path.exists(info_file):
                try:
                    rdata = mw.readFile(info_file)
                    decrypted = mw.deDoubleCrypt('mdserver-web', rdata)
                    if decrypted and decrypted != rdata:
                        enstr = mw.enDoubleCrypt('mdserver-web', decrypted)
                        mw.writeFile(info_file, enstr)
                except:
                    pass
                    
    mw.writeFile(flag_file, '1')
    mw.writeLog('安全机制', '敏感数据安全加密迁移完成。')
