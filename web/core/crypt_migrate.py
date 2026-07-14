# coding=utf-8

import os
import json
import core.yf as yf
import thisdb

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
        decrypted = yf.deDoubleCrypt('mdserver-web', two_step['secret'])
        if decrypted and decrypted != two_step['secret']:
            two_step['secret'] = yf.enDoubleCrypt('mdserver-web', decrypted)
            thisdb.setOption('two_step_verification', json.dumps(two_step))
            
    # 2. 迁移邮件通知
    notify_email = thisdb.getOptionByJson('notify_email', default={'open': False}, type='notify')
    if 'cfg' in notify_email:
        decrypted = yf.deDoubleCrypt('email', notify_email['cfg'])
        if decrypted and decrypted != notify_email['cfg']:
            notify_email['cfg'] = yf.enDoubleCrypt('email', decrypted)
            thisdb.setOption('notify_email', json.dumps(notify_email), type='notify')
            
    # 3. 迁移 TG Bot 通知
    notify_tgbot = thisdb.getOptionByJson('notify_tgbot', default={'open': False}, type='notify')
    if 'cfg' in notify_tgbot:
        decrypted = yf.deDoubleCrypt('tgbot', notify_tgbot['cfg'])
        if decrypted and decrypted != notify_tgbot['cfg']:
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
                    decrypted = yf.deDoubleCrypt('mdserver-web', rdata)
                    if decrypted and decrypted != rdata:
                        enstr = yf.enDoubleCrypt('mdserver-web', decrypted)
                        yf.writeFile(info_file, enstr)
                except:
                    pass
                    
    yf.writeFile(flag_file, '1')
    yf.writeLog('安全机制', '敏感数据安全加密迁移完成。')
