# coding: utf-8
"""MariaDB 插件卸载前检查与卸载流程守卫测试（P1-1, P1-2, P1-3, P1-4, P2-5）。

验证：
1. 卸载前环境检查（uninstallPreInspection）：正常停止时返回 'ok'；服务停止失败或有残留进程时
   绝不返回 'ok'（阻断假卸载），且严禁提前移除首页图标（removeIndex）；
2. 与 MySQL 插件卸载检查逻辑严格对齐；
3. install.sh 具备 serverPath 严格白名单校验（/www/server）防止系统目录越界误删；
4. install.sh 卸载具备幂等性（重复卸载已干净的实例安全退出，不误报错误）；
5. install.sh 卸载后强制回读残留进程，若有进程存活必须 exit 1 失败退出；
6. version.pl 版本号回读具备严格数字与点号白名单正则校验，防御路径穿越。
"""
import ast
import io
import os
import unittest
from unittest.mock import MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARIADB_IDX = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')
MARIADB_INSTALL_SH = os.path.join(ROOT, 'plugins', 'mariadb', 'install.sh')
MYSQL_IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


class TestMariadbUninstall(unittest.TestCase):

    def test_01_uninstall_pre_inspection_structure(self):
        """卸载前检查函数存在，且成功分支返回 'ok'，不含死胡同拦截文案。"""
        src = _read(MARIADB_IDX)
        tree = ast.parse(src)

        fn_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'uninstallPreInspection':
                fn_node = node
                break

        self.assertIsNotNone(fn_node, 'plugins/mariadb/index.py 缺少 uninstallPreInspection 函数')

        # 检查 AST 中不再包含「请手动删除」字样
        for sub in ast.walk(fn_node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                self.assertNotIn('请手动删除', sub.value,
                                 'uninstallPreInspection 仍残留拦截文案，导致无法正常卸载')

        # 检查包含成功 return 'ok'
        return_values = [ret.value.value for ret in ast.walk(fn_node)
                         if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Constant)]
        self.assertIn('ok', return_values, 'uninstallPreInspection 必须包含成功返回 ok 的分支')

        # 检查调用了必要清理流程
        calls = [n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, 'attr', '')
                 for n in ast.walk(fn_node) if isinstance(n, ast.Call)]
        self.assertIn('initdUinstall', calls, 'uninstallPreInspection 未调用 initdUinstall 注销自启')
        self.assertIn('cleanOrphanSockets', calls, 'uninstallPreInspection 未调用 cleanOrphanSockets 清理孤儿套接字')
        self.assertIn('removeIndex', calls, 'uninstallPreInspection 未调用 removeIndex 清理首页图标')

    def test_02_uninstall_pre_inspection_execution(self):
        """沙箱执行 uninstallPreInspection：停止成功返回 ok；停止失败拒绝返回 ok 且不移图标。"""
        src = _read(MARIADB_IDX)
        tree = ast.parse(src)

        fn_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'uninstallPreInspection':
                fn_node = node
                break

        mod_tree = ast.Module(body=[fn_node], type_ignores=[])
        compiled = compile(mod_tree, filename='<test_mariadb_uninstall>', mode='exec')

        mock_stop = MagicMock(return_value='ok')
        mock_status = MagicMock(return_value='stop')
        mock_initd_uninstall = MagicMock(return_value='ok')
        mock_clean_sockets = MagicMock()
        mock_exec_shell = MagicMock(return_value=('', ''))
        mock_log = MagicMock()
        mock_yf = MagicMock()
        mock_yf.execShell = mock_exec_shell

        mock_plugin = MagicMock()
        mock_remove_index = MagicMock(return_value={'status': True})
        mock_plugin.instance.return_value.removeIndex = mock_remove_index
        mock_get_plugin_name = MagicMock(return_value='mariadb')
        mock_get_server_dir = MagicMock(return_value='/www/server/mariadb')
        mock_stop_and_kill = MagicMock(return_value='ok')

        env = {
            'stop': mock_stop,
            'status': mock_status,
            'initdUinstall': mock_initd_uninstall,
            'cleanOrphanSockets': mock_clean_sockets,
            'stopAndKill': mock_stop_and_kill,
            'getServerDir': mock_get_server_dir,
            'yf': mock_yf,
            '_log': mock_log,
            'getPluginName': mock_get_plugin_name,
            'os': os,
        }

        import sys
        fake_plugin_module = MagicMock()
        fake_plugin_module.plugin = mock_plugin

        with patch.dict(sys.modules, {'utils.plugin': fake_plugin_module}), \
             patch('os.path.isdir', return_value=False):
            exec(compiled, env)
            fn = env['uninstallPreInspection']

            # 场景 1：服务成功停止且无残留 -> 正常返回 'ok' 并清理自启和图标
            result = fn('11.4')
            self.assertEqual(result, 'ok', '服务停止成功时必须返回 ok')
            mock_stop.assert_called_with('11.4')
            mock_initd_uninstall.assert_called_once()
            mock_clean_sockets.assert_called_once()
            mock_remove_index.assert_called_with('mariadb', '11.4')

            # 场景 2：服务停止失败（status 仍为 start）-> 拒绝返回 ok，绝不调用 removeIndex
            mock_initd_uninstall.reset_mock()
            mock_remove_index.reset_mock()
            mock_status.return_value = 'start'
            err_result = fn('11.4')
            self.assertNotEqual(err_result, 'ok', '服务未能停止时严禁返回 ok')
            self.assertIn('无法安全卸载', err_result)
            mock_remove_index.assert_not_called()
            mock_initd_uninstall.assert_not_called()

    def test_03_main_version_arg_preference(self):
        """__main__ 入口在提供 sys.argv[2] 时应优先选用传入的版本号。"""
        src = _read(MARIADB_IDX)
        self.assertIn('if len(sys.argv) > 2 and sys.argv[2]:', src,
                      '__main__ 未优先解析 sys.argv[2] 传入的版本号')

    def test_04_install_sh_uninstall_guards_and_idempotence(self):
        """install.sh 卸载分支具备严格的 serverPath 校验、幂等性支持与残留自检。"""
        sh_content = _read(MARIADB_INSTALL_SH)

        # 1. 严格 serverPath 白名单断言（/www/server）
        self.assertIn('[ "${serverPath}" != "/www/server" ]', sh_content,
                      '缺少 serverPath 必须为 /www/server 的安全白名单断言')

        # 2. 幂等性保护（目录不存在时正常返回，不报错中断）
        self.assertIn('已处于已卸载状态', sh_content,
                      '缺少目录已被删干净时的幂等放行逻辑')

        # 3. 卸载后残留自检回读：残留 mariadbd 时 exit 1
        self.assertIn('stop_and_kill', sh_content)
        self.assertIn('卸载后自检发现仍有 mariadbd 残留，卸载失败', sh_content)
        self.assertIn('exit 1', sh_content)

        # 4. version.pl 版本号格式正则白名单校验（防御路径穿越）
        self.assertIn('^[0-9]+(\.[0-9]+)*$', sh_content,
                      '缺少针对 version.pl 的版本号正则严格白名单校验')

    def test_05_alignment_with_mysql_uninstall(self):
        """验证 MariaDB 与 MySQL 在 uninstallPreInspection 上行为严格对齐。"""
        mysql_src = _read(MYSQL_IDX)
        mariadb_src = _read(MARIADB_IDX)

        # 两者都不含「请手动删除」
        self.assertNotIn('请手动删除', mariadb_src.split('def uninstallPreInspection')[1].split('def ')[0])
        self.assertNotIn('请手动删除', mysql_src.split('def uninstallPreInspection')[1].split('def ')[0])

        # 两者在 uninstallPreInspection 正常分支均 return 'ok'
        self.assertIn("return 'ok'", mariadb_src.split('def uninstallPreInspection')[1].split('def ')[0])
        self.assertIn("return 'ok'", mysql_src.split('def uninstallPreInspection')[1].split('def ')[0])

        # 两者均在服务未停止时阻断（无法安全卸载）
        self.assertIn('无法安全卸载', mariadb_src.split('def uninstallPreInspection')[1].split('def ')[0])
        self.assertIn('无法安全卸载', mysql_src.split('def uninstallPreInspection')[1].split('def ')[0])


if __name__ == '__main__':
    unittest.main()
