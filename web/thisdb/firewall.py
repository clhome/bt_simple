# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks <midoks@163.com>
# ---------------------------------------------------------------------------------

import core.mw as mw

try:
    mw.M('firewall').execute('ALTER TABLE firewall ADD COLUMN status INTEGER DEFAULT 1', ())
except:
    pass

try:
    mw.M('firewall').execute('ALTER TABLE firewall ADD COLUMN type TEXT DEFAULT "port"', ())
except:
    pass

__FIELD = 'id,port,protocol,status,type,ps,add_time,update_time'

def getFirewallList(page=1, size=10, search_port='', search_ps='', stype='port'):
    start = (int(page) - 1) * (int(size))
    limit = str(start) + ',' + str(size)

    m = mw.M('firewall').field(__FIELD)
    
    where = ""
    params = []

    if stype:
        if stype == 'ip':
            where += "type IN ('address_allow', 'address_deny')"
        else:
            where += "type = ?"
            params.append(stype)
    
    if search_port:
        if where: where += " AND "
        if search_port.isdigit():
            search_port_int = int(search_port)
            # 精确匹配端口，或者匹配包含该端口的范围
            # 范围存储格式为 start:end
            where += "(port = ? OR (port LIKE '%:%' AND CAST(SUBSTR(port, 1, INSTR(port, ':') - 1) AS INTEGER) <= ? AND CAST(SUBSTR(port, INSTR(port, ':') + 1) AS INTEGER) >= ?))"
            params.extend([search_port, search_port_int, search_port_int])
        else:
            # IP 或者非纯数字搜索
            where += "port LIKE ?"
            params.append('%' + search_port + '%')
            
    if search_ps:
        if where: where += " AND "
        where += "ps LIKE ?"
        params.append('%' + search_ps + '%')

    if where:
        m = m.where(where, tuple(params))

    firewall_list = m.limit(limit).order('id desc').select()
    
    # 再次使用带条件的对象获取总数
    count_obj = mw.M('firewall')
    if where:
        count_obj = count_obj.where(where, tuple(params))
    count = count_obj.count()

    data = {}
    data['count'] = count
    data['list'] = firewall_list
    return data

def addFirewall(port, protocol='tcp', ps='备注', stype='port') -> bool:
    '''
    设置配置的值
    :port -> str 端口 (必填)
    :protocol -> str 协议 (可选|tcp,udp,tcp/udp)
    :ps -> str 备注 (可选)
    :stype -> str 类型 (可选|port,address_allow,address_deny)
    '''
    now_time = mw.formatDate()
    insert_data = {
        'port':port,
        'protocol':protocol,
        'status':1,
        'type':stype,
        'ps':ps,
        'add_time':now_time,
        'update_time':now_time,
    }
    mw.M('firewall').insert(insert_data)
    return True


def getFirewallCountByPort(port, stype='port'):
    return mw.M('firewall').where('port=? AND type=?',(port, stype)).count()


