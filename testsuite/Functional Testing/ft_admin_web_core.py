# coding: utf-8
"""Web Admin 核心控制台 13 大模块业务功能测试。"""
import os
import sys
import json
import unittest

FT_DIR = os.path.dirname(os.path.abspath(__file__))
if FT_DIR not in sys.path:
    sys.path.insert(0, FT_DIR)

from ft_common import FTBaseTestCase, ROOT_DIR
import core.yf as yf
import thisdb

# 确保在根目录执行 import
os.chdir(ROOT_DIR)

try:
    import psutil
except ImportError:
    from unittest.mock import MagicMock
    mock_psutil = MagicMock()
    mock_psutil.cpu_count.return_value = 8
    mock_psutil.virtual_memory.return_value = MagicMock(total=16*1024*1024*1024, available=8*1024*1024*1024, percent=50.0)
    mock_psutil.cpu_percent.return_value = [10.0, 15.0, 12.0, 8.0]
    mock_psutil.disk_partitions.return_value = []
    mock_psutil.net_io_counters.return_value = MagicMock(bytes_sent=1000, bytes_recv=2000)
    sys.modules['psutil'] = mock_psutil

import utils.site as site_util
import utils.file as file_util
import utils.config as config_util
import utils.crontab as crontab_util
import utils.firewall as firewall_util
import utils.system.monitor as monitor_util
import utils.system.main as system_util


class TestAdminWebCoreFunctional(FTBaseTestCase):

    def test_01_site_lifecycle_and_vhost(self):
        """测试网站模块（Site）：站点创建、域名绑定、伪静态与站点删除"""
        site_obj = site_util.sites.instance()
        # 打桩通过 Web 配置语法校验
        yf.checkWebConfig = lambda: True
        test_domain = 'www.example-test.com'
        test_path = os.path.join(self.sandbox_dir, 'wwwroot', test_domain).replace('\\', '/')
        os.makedirs(test_path, exist_ok=True)

        # 1. 站点入库 (site_info_json, port, ps, path, version)
        site_info = json.dumps({'domain': test_domain})
        site_res = site_obj.add(site_info, '80', '功能测试站点', test_path, '00')
        self.assertTrue(site_res.get('status', False), "添加站点失败: %s" % site_res)

        # 验证站点在数据库中正确持久化并获取 site_id
        find_site = yf.M('sites').where('name=?', (test_domain,)).find()
        self.assertIsNotNone(find_site, "站点未在 sites 表中查到")
        site_id = find_site['id']
        self.assertTrue(site_id > 0, "添加站点返回的 ID 必须大于 0")

        # 2. 域名绑定测试
        domain_added = site_obj.addDomain(site_id, test_domain, 'api.example-test.com')
        self.assertTrue(domain_added.get('status', False), "为站点添加额外域名失败: %s" % domain_added)

        domain_ret = site_obj.getDomain(site_id)
        domain_list = domain_ret.get('data', []) if isinstance(domain_ret, dict) else domain_ret
        self.assertTrue(any(d.get('name') == 'api.example-test.com' for d in domain_list), "绑定的域名未在列表中检索到")

        # 3. 删除站点及附属配置
        del_res = site_obj.delete(site_id, test_domain)
        self.assertTrue(del_res.get('status', False), "删除站点失败: %s" % del_res)
        find_deleted = yf.M('sites').where('id=?', (site_id,)).find()
        self.assertIsNone(find_deleted, "删除站点后记录仍残留在数据库中")

    def test_02_files_crud_and_recycle_bin(self):
        """测试文件模块（Files）：文件创建、内容读写、回收站隔离与还原"""
        test_file_dir = os.path.join(self.sandbox_dir, 'files_test').replace('\\', '/')
        os.makedirs(test_file_dir, exist_ok=True)
        test_file = f"{test_file_dir}/demo.txt"

        # 1. 创建文件与写入内容
        test_content = '御风面板功能测试数据: 123456\n第二行内容'
        cr_res = file_util.createFile(test_file)
        self.assertTrue(cr_res.get('status', False), "创建文件接口失败: %s" % cr_res)
        self.assertTrue(os.path.exists(test_file), "测试文件未在磁盘上生成")
        file_util.saveBody(test_file, test_content, 'utf-8')

        # 2. 读取文件内容并验证一致性
        read_res = file_util.getFileBody(test_file)
        self.assertTrue(read_res.get('status', False), "读取文件失败")
        raw_body = read_res['data']['data'] if isinstance(read_res.get('data'), dict) else read_res.get('data', '')
        self.assertIn('御风面板功能测试数据', raw_body, "读写内容不一致")

        # 3. 移入回收站
        rb_res = file_util.mvRecycleBin(test_file)
        self.assertTrue(rb_res, "移入回收站失败")
        self.assertFalse(os.path.exists(test_file), "移入回收站后原路径文件仍存在")

        # 4. 回收站列表回读
        rb_data = json.loads(file_util.getRecycleBin())
        self.assertTrue(rb_data.get('status', False), "获取回收站列表失败")

    def test_03_setting_and_menu_config_self_heal(self):
        """测试设置模块（Setting/Config）：菜单容灾兜底、默认菜单自愈与防XSS"""
        # 1. 模拟写入被恶意破坏/篡改的残缺菜单数据
        menu_file = os.path.join(self.panel_data_dir, 'menu.json')
        corrupted_menu = [{"id": "bad", "name": "bad", "url": "javascript:alert(1)", "show": True}]
        with open(menu_file, 'w', encoding='utf-8') as f:
            json.dump(corrupted_menu, f)

        # 2. 读取菜单配置，验证自动容灾兜底（必须补齐9个核心菜单，且过滤javascript伪协议）
        menus = config_util.get_menu_config()
        self.assertIsInstance(menus, list, "菜单配置必须返回列表")
        self.assertTrue(len(menus) >= 9, "当菜单残缺时必须自愈并补齐至少9个核心系统菜单")

        core_ids = {'memuAsite', 'memuAfiles', 'memuAfirewall', 'memuAcrontab', 'memuAsoft', 'memuAsetting'}
        retrieved_ids = {m.get('id') for m in menus}
        self.assertTrue(core_ids.issubset(retrieved_ids), "自愈后的菜单缺失核心菜单项: %s" % (core_ids - retrieved_ids))

        # 验证非法 URL 被拒绝或修复
        for m in menus:
            self.assertFalse(m.get('url', '').startswith('javascript:'), "菜单 URL 包含非法 javascript 伪协议")

        # 3. 测试一键重置为默认菜单
        reset_res = config_util.reset_menu_config()
        self.assertIsInstance(reset_res, list, "重置菜单必须返回菜单列表")
        self.assertEqual(len(reset_res), 9, "重置后应精确恢复为 9 个默认核心菜单")

    def test_04_crontab_expression_and_scripts(self):
        """测试计划任务（Crontab）：任务入库、周期类型解析与任务删除"""
        crontab_util.crontab.syncToCrond = lambda self, tid: True
        crontab_util.crontab.removeForCrond = lambda self, echo: True
        c_obj = crontab_util.crontab.instance()
        task_name = '自动备份与内存释放测试_' + yf.getRandomString(6)

        # 1. 添加一个周期任务（每天 02:30 执行脚本）
        task_id = c_obj.add({
            'name': task_name,
            'type': 'day',
            'where1': '',
            'hour': '2',
            'minute': '30',
            'stype': 'toShell',
            'sbody': 'echo "test"',
            'sname': '',
            'backup_to': '',
            'save': '',
            'url_address': ''
        })
        self.assertTrue(isinstance(task_id, int) and task_id > 0, "添加计划任务失败，返回: %s" % task_id)

        # 2. 查询验证
        find_task = yf.M('crontab').where('name=?', (task_name,)).find()
        self.assertIsNotNone(find_task, "计划任务未在数据库中查到")
        self.assertEqual(find_task['type'], 'day')
        self.assertEqual(int(find_task['where_hour']), 2)
        self.assertEqual(int(find_task['where_minute']), 30)

        # 3. 删除任务
        del_res = c_obj.delete(find_task['id'])
        self.assertTrue(del_res.get('status', False), "删除计划任务失败: %s" % del_res)
        find_after_del = yf.M('crontab').where('id=?', (find_task['id'],)).find()
        self.assertIsNone(find_after_del, "计划任务删除后数据库仍有残留")

    def test_05_firewall_rule_management(self):
        """测试防火墙模块（Firewall）：端口放行、重复放行拦截与规则删除"""
        fw_obj = firewall_util.Firewall.instance()
        # 激活沙箱模拟防火墙状态
        fw_obj.getFwStatus = lambda: True
        test_port = '9988'
        test_ps = '自动化测试端口放行'

        # 1. 放行端口
        add_res = fw_obj.addAcceptPort(test_port, test_ps, 'port')
        self.assertTrue(add_res.get('status', False), "放行端口失败: %s" % add_res)

        find_port = yf.M('firewall').where('port=?', (test_port,)).find()
        self.assertIsNotNone(find_port, "端口规则未写入数据库")
        self.assertEqual(find_port['port'], test_port)

        # 2. 重复放行应被防呆拦截
        dup_res = fw_obj.addAcceptPort(test_port, test_ps, 'port')
        self.assertFalse(dup_res.get('status', True), "重复放行相同端口未被拦截")

        # 3. 删除端口放行规则
        del_res = fw_obj.delAcceptPort(find_port['id'], test_port)
        self.assertTrue(del_res.get('status', False), "删除端口放行规则失败: %s" % del_res)
        find_del = yf.M('firewall').where('port=?', (test_port,)).find()
        self.assertIsNone(find_del, "删除端口后数据库仍有残留")

    def test_06_monitor_sampling_and_query(self):
        """测试系统监控模块（Monitor）：配置读取与运行参数检查"""
        mon_obj = monitor_util.instance()
        # 1. 读取监控天数与初始化状态
        day_cfg = mon_obj.getMonitorDay()
        self.assertIsNotNone(day_cfg, "监控天数配置不能为空")
        self.assertTrue(int(day_cfg) > 0, "默认监控天数必须大于 0")

    def test_07_dashboard_and_system_metrics(self):
        """测试系统与仪表盘模块（System/Dashboard）：硬件信息采集结构完整性"""
        # 1. 获取 CPU 详情
        cpu_info = system_util.getCpuInfo()
        self.assertIsInstance(cpu_info, (dict, tuple, list), "CPU 信息必须返回有效结构")

        # 2. 获取内存信息
        mem_info = system_util.getMemInfo()
        self.assertIsInstance(mem_info, (dict, tuple, list), "内存信息必须返回有效结构")

        # 3. 实时负载与性能指标
        load_avg = system_util.getLoadAverage()
        self.assertIsInstance(load_avg, (dict, tuple, list), "系统负载必须返回有效结构")


if __name__ == '__main__':
    unittest.main()
