# coding: utf-8
"""MariaDB 插件卸载前检查与卸载流程守卫测试。

防止卸载环境检查被硬编码拦截（用户无法正常卸载、被迫只能强制删除），
并保证与 MySQL 插件卸载口径对齐（注销自启、清理套接字、移除图标、卸载脚本兜底与回读）。
"""
import ast
import io
import os
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARIADB_IDX = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')
MARIADB_INSTALL_SH = os.path.join(ROOT, 'plugins', 'mariadb', 'install.sh')
MYSQL_IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


class TestMariadbUninstall(unittest.TestCase):

    def test_01_uninstall_pre_inspection_returns_ok_not_manual_rm(self):
        """卸载前检查必须返回 'ok'，绝不能提示请手动删除或拦截普通卸载。"""
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

        # 检查返回值必须恒为 'ok'
        return_nodes = [n for n in ast.walk(fn_node) if isinstance(n, ast.Return)]
        self.assertTrue(len(return_nodes) > 0, 'uninstallPreInspection 必须有 return 语句')
        for ret in return_nodes:
            self.assertIsInstance(ret.value, ast.Constant, '返回值必须是常量')
            self.assertEqual(ret.value.value, 'ok', 'uninstallPreInspection 返回值必须为 ok')

        # 检查是否调用了 initdUinstall 与 removeIndex
        calls = [n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, 'attr', '')
                 for n in ast.walk(fn_node) if isinstance(n, ast.Call)]
        self.assertIn('initdUinstall', calls, 'uninstallPreInspection 未调用 initdUinstall 注销自启')
        self.assertIn('cleanOrphanSockets', calls, 'uninstallPreInspection 未调用 cleanOrphanSockets 清理孤儿套接字')
        self.assertIn('removeIndex', calls, 'uninstallPreInspection 未调用 removeIndex 清理首页图标')

    def test_02_uninstall_pre_inspection_execution(self):
        """沙箱执行 uninstallPreInspection 函数，验证其返回 'ok' 且调用必要流程。"""
        src = _read(MARIADB_IDX)
        tree = ast.parse(src)

        fn_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'uninstallPreInspection':
                fn_node = node
                break

        # 将函数 AST 编译成可执行 code
        mod_tree = ast.Module(body=[fn_node], type_ignores=[])
        compiled = compile(mod_tree, filename='<test_mariadb_uninstall>', mode='exec')

        mock_stop = MagicMock(return_value='ok')
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

        env = {
            'stop': mock_stop,
            'initdUinstall': mock_initd_uninstall,
            'cleanOrphanSockets': mock_clean_sockets,
            'yf': mock_yf,
            '_log': mock_log,
            'getPluginName': mock_get_plugin_name,
        }

        # 捕获函数内部的 `from utils.plugin import plugin as YfPlugin`
        import sys
        fake_plugin_module = MagicMock()
        fake_plugin_module.plugin = mock_plugin
        with unittest.mock.patch.dict(sys.modules, {'utils.plugin': fake_plugin_module}):
            exec(compiled, env)
            fn = env['uninstallPreInspection']
            result = fn('11.4')

        self.assertEqual(result, 'ok', '沙箱中调用 uninstallPreInspection 必须返回 ok')
        mock_stop.assert_called_with('11.4')
        mock_initd_uninstall.assert_called_once()
        mock_clean_sockets.assert_called_once()
        self.assertTrue(mock_exec_shell.called, '必须调用 execShell 清理 socket 文件')
        mock_remove_index.assert_called_with('mariadb', '11.4')

    def test_03_main_version_arg_preference(self):
        """__main__ 入口在提供 sys.argv[2] 时应优先选用传入的版本号。"""
        src = _read(MARIADB_IDX)
        self.assertIn('if len(sys.argv) > 2 and sys.argv[2]:', src,
                      '__main__ 未优先解析 sys.argv[2] 传入的版本号')

    def test_04_install_sh_uninstall_guards(self):
        """install.sh 在 action==uninstall 时不应因缺少 versions 目录退出，且具备兜底与回读。"""
        sh_content = _read(MARIADB_INSTALL_SH)

        # 卸载时不被缺少安装脚本拦截
        self.assertIn('[ "${action}" != "uninstall" ] && [ "${is_fast}" == "false" ] && [ ! -d "${curPath}/versions/${type}" ]',
                      sh_content,
                      '缺少安装脚本的检查应仅在非卸载时生效')

        # 卸载分支具备 rm -rf 兜底与 stop_and_kill 回读
        self.assertIn('stop_and_kill', sh_content)
        self.assertIn('rm -rf "${serverPath}/mariadb"', sh_content)
        self.assertIn('exit 0', sh_content)

    def test_05_alignment_with_mysql_uninstall(self):
        """验证 MariaDB 与 MySQL 在 uninstallPreInspection 上行为对齐。"""
        mysql_src = _read(MYSQL_IDX)
        mariadb_src = _read(MARIADB_IDX)

        # 两者都不含「请手动删除」
        self.assertNotIn('请手动删除', mariadb_src.split('def uninstallPreInspection')[1].split('def ')[0])
        self.assertNotIn('请手动删除', mysql_src.split('def uninstallPreInspection')[1].split('def ')[0])

        # 两者在 uninstallPreInspection 结尾均 return 'ok'
        self.assertIn("return 'ok'", mariadb_src.split('def uninstallPreInspection')[1].split('def ')[0])
        self.assertIn("return 'ok'", mysql_src.split('def uninstallPreInspection')[1].split('def ')[0])


if __name__ == '__main__':
    unittest.main()
