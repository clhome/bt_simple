# coding:utf-8

import sys
import io
import os
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.linux_sys_opt')

#: 本插件写入的内核参数文件（install.sh 卸载时按同一路径删除）
SYSCTL_CONF = '/etc/sysctl.d/99-yufeng-server.conf'
#: THP 开关/整理策略（写入 never 后按此路径回读校验）
THP_ENABLED = '/sys/kernel/mm/transparent_hugepage/enabled'
THP_DEFRAG = '/sys/kernel/mm/transparent_hugepage/defrag'
#: 状态面板展示的内核参数（界面字段名 -> sysctl 键），顺序即界面展示顺序
STATUS_KEYS = (
    ('vm_swappiness', 'vm.swappiness'),
    ('vm_dirty_background_ratio', 'vm.dirty_background_ratio'),
    ('vm_dirty_ratio', 'vm.dirty_ratio'),
    ('net_core_somaxconn', 'net.core.somaxconn'),
    ('vm_max_map_count', 'vm.max_map_count'),
    ('fs_file_max', 'fs.file-max'),
    ('net_ipv4_tcp_tw_reuse', 'net.ipv4.tcp_tw_reuse'),
    ('net_ipv4_ip_local_port_range', 'net.ipv4.ip_local_port_range'),
    ('net_ipv4_tcp_max_syn_backlog', 'net.ipv4.tcp_max_syn_backlog'),
    ('net_ipv4_tcp_max_tw_buckets', 'net.ipv4.tcp_max_tw_buckets'),
)

def getPluginName():
    return 'linux_sys_opt'

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

def get_mem_mb():
    try:
        mem = yf.readFile('/proc/meminfo')
        if mem:
            import re
            m = re.search(r'MemTotal:\s+(\d+)\s+kB', mem)
            if m:
                return int(m.group(1)) // 1024
    except Exception as _e:
        _log.debug('[linux_sys_opt] get_mem_mb 异常已忽略: %s', _e)
    return 2048


def read_sysctl(key):
    """读取内核参数当前生效值；读不到返回 ''。

    优先直读 /proc/sys：不必为每个参数各起一个 shell 进程（状态面板一次要读 10 个），
    也不存在把参数名拼进命令行的问题。取不到时才回退 `sysctl -n`（仍做 shell 转义）。
    """
    val = yf.readFile('/proc/sys/' + str(key).replace('.', '/'))
    if isinstance(val, str) and val.strip() != '':
        return val.strip()

    rc, out, _err = yf.execShellRc('sysctl -n ' + yf.shlexQuote(key))
    if rc == 0 and str(out).strip() != '':
        return ' '.join(str(out).split())
    return ''


def _first_line(text):
    """取命令输出的第一行（错误消息只留摘要，避免把整段 stderr 回给界面）。"""
    lines = [x.strip() for x in str(text or '').splitlines() if x.strip()]
    return lines[0] if lines else ''


def get_status():
    data = {}

    for field, key in STATUS_KEYS:
        val = read_sysctl(key)
        # 归一化空白：ip_local_port_range 等参数不同内核版本用 tab/空格分隔
        data[field] = ' '.join(val.split()) if val else '未设置'

    # THP
    thp_enabled = "未知"
    thp_raw = yf.readFile(THP_ENABLED)
    if isinstance(thp_raw, str) and thp_raw.strip() != '':
        thp_enabled = thp_raw.strip()
    data['thp_enabled'] = thp_enabled

    data['mem_mb'] = get_mem_mb()

    return yf.returnJson(True, "ok", data)


def _tuning_conf(mem_mb):
    """按内存阶梯生成配置内容与「期望生效值」。

    返回 (配置文件内容, {sysctl键: 期望值})。文件内容与历史版本逐字节一致
    （保证已部署机器重复点击不产生配置漂移）。
    """
    if mem_mb <= 2048:
        somaxconn = 1024
        syn_backlog = 2048
        tw_buckets = 5000
        file_max = 1048576
    elif mem_mb <= 8192:
        somaxconn = 4096
        syn_backlog = 8192
        tw_buckets = 20000
        file_max = 2097152
    else:
        somaxconn = 8192
        syn_backlog = 16384
        tw_buckets = 50000
        file_max = 6553500

    groups = (
        ('降低 Swap 换出倾向', (('vm.swappiness', '10'),)),
        ('脏页平滑刷盘', (('vm.dirty_background_ratio', '5'), ('vm.dirty_ratio', '10'))),
        ('适度提高 TCP 监听队列上限', (('net.core.somaxconn', str(somaxconn)),)),
        ('增加进程可拥有的最大 VMA 数量', (('vm.max_map_count', '262144'),)),
        ('系统级最大文件描述符数量', (('fs.file-max', str(file_max)),)),
        ('TIME_WAIT socket 复用', (('net.ipv4.tcp_tw_reuse', '1'),)),
        ('扩大向外连接的端口范围', (('net.ipv4.ip_local_port_range', '1024 65000'),)),
        ('应对高并发与 SYN 攻击', (('net.ipv4.tcp_max_syn_backlog', str(syn_backlog)),)),
        ('限制最大 TIME_WAIT 数量，省内存', (('net.ipv4.tcp_max_tw_buckets', str(tw_buckets)),)),
    )

    lines = ['']
    expect = {}
    for idx, (title, items) in enumerate(groups, 1):
        lines.append('# %d. %s' % (idx, title))
        for key, val in items:
            lines.append('%s = %s' % (key, val))
            expect[key] = val
    return '\n'.join(lines) + '\n', expect


def _write_thp_never():
    """禁用 THP（含 RHEL tuned 与 Debian systemd 两条落地路径）；返回未生效项。"""
    failed = []

    for path in (THP_ENABLED, THP_DEFRAG):
        if not os.path.exists(path):
            continue
        rc, _out, err = yf.execShellRc('echo never > ' + yf.shlexQuote(path))
        cur = yf.readFile(path)
        got = cur.strip() if isinstance(cur, str) else ''
        if rc != 0 or '[never]' not in got:
            failed.append('%s(%s)' % (path, _first_line(err) or '实际值 %s' % (got or '读取失败')))

    # CentOS/RHEL tuned
    rc, _out, _err = yf.execShellRc('command -v tuned-adm')
    if rc == 0:
        tuned_conf = """
[main]
summary=Universal server profile with disabled THP
include=throughput-performance

[vm]
transparent_hugepages=never
"""
        if not yf.writeFile('/etc/tuned/no-thp-universal/tuned.conf', tuned_conf):
            failed.append('/etc/tuned/no-thp-universal/tuned.conf(写入失败)')
        rc_tuned, _out_t, err_t = yf.execShellRc('tuned-adm profile no-thp-universal')
        if rc_tuned != 0:
            failed.append('tuned-adm profile(%s)' % (_first_line(err_t) or 'rc=%s' % rc_tuned))

    # Debian/Ubuntu Systemd
    systemd_conf = """
[Unit]
Description=Disable Transparent Huge Pages (THP) for Database and Web Engines
After=sysinit.target local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled && echo never > /sys/kernel/mm/transparent_hugepage/defrag'

[Install]
WantedBy=basic.target
"""
    unit_path = '/etc/systemd/system/disable-thp.service'
    if not yf.writeFile(unit_path, systemd_conf):
        failed.append('%s(写入失败)' % unit_path)
        return failed

    rc_reload, _out_r, err_r = yf.execShellRc('systemctl daemon-reload')
    if rc_reload != 0:
        failed.append('systemctl daemon-reload(%s)' % (_first_line(err_r) or 'rc=%s' % rc_reload))
    rc_enable, _out_e, err_e = yf.execShellRc('systemctl enable --now disable-thp.service')
    if rc_enable != 0:
        failed.append('systemctl enable disable-thp.service(%s)' % (_first_line(err_e) or 'rc=%s' % rc_enable))

    return failed


def apply_opt():
    conf, expect = _tuning_conf(get_mem_mb())

    if not yf.writeFile(SYSCTL_CONF, conf):
        return yf.returnJson(False, '内核参数配置文件写入失败:', SYSCTL_CONF)

    # `sysctl --system` 最后读取 /etc/sysctl.conf（procps 的固定读取顺序），会覆盖本插件的
    # drop-in：真机实测本文件写 net.core.somaxconn = 4096，命令跑完实际生效仍是
    # /etc/sysctl.conf 的 1024 —— 界面「一键优化」报成功、紧接着状态页仍显示 ✗。
    # 因此 --system 之后再显式套用一次本文件（界面承诺「应用后立即生效」），并逐个回读校验，
    # 只有全部达标才报成功。
    yf.execShellRc('sysctl --system')
    rc_own, _out_own, err_own = yf.execShellRc('sysctl -p ' + yf.shlexQuote(SYSCTL_CONF))

    failed = []
    for key, val in expect.items():
        cur = ' '.join(read_sysctl(key).split())
        if cur != val:
            failed.append('%s(期望 %s, 实际 %s)' % (key, val, cur or '读取失败'))
    if rc_own != 0:
        failed.append('sysctl -p %s(rc=%s %s)' % (SYSCTL_CONF, rc_own, _first_line(err_own)))

    failed = failed + _write_thp_never()

    if failed:
        detail = '; '.join(failed)
        _log.warning('[linux_sys_opt] 内核优化未完全生效: %s', detail)
        return yf.returnJson(False, '部分优化项未生效:', detail)

    return yf.returnJson(True, "全平台内核优化配置已成功生效！")


if __name__ == "__main__":
    func = sys.argv[1] if len(sys.argv) > 1 else ''
    if func == 'status':
        print('start')
    elif func == 'start':
        print('ok')
    elif func == 'stop':
        print('ok')
    elif func == 'restart':
        print('ok')
    elif func == 'reload':
        print('ok')
    elif func == 'get_status':
        print(get_status())
    elif func == 'apply_opt':
        print(apply_opt())
    else:
        print('error')
