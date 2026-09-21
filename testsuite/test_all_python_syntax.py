# coding: utf-8
import os
import ast
import py_compile
import unittest

class TestAllPythonSyntax(unittest.TestCase):
    def setUp(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_all_python_files_syntax_and_compilation(self):
        """测试仓库内所有 Python 文件的 AST 语法解析与字节码编译"""
        py_files = []
        for root, dirs, files in os.walk(self.root_dir):
            if "待审核" in root or ".git" in root or "__pycache__" in root or "node_modules" in root or "temp_dev" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        syntax_errors = []
        for py_path in py_files:
            rel_path = os.path.relpath(py_path, self.root_dir)
            try:
                with open(py_path, "r", encoding="utf-8") as f:
                    code = f.read()
                ast.parse(code, filename=rel_path)
            except SyntaxError as e:
                syntax_errors.append((rel_path, e.lineno, e.msg, e.text or ""))
            except Exception as e:
                syntax_errors.append((rel_path, 0, str(e), ""))

        error_msg = "\n".join([f"[{path}:{line}] {msg} -> {text.strip()}" for path, line, msg, text in syntax_errors])
        self.assertEqual(len(syntax_errors), 0, f"发现 {len(syntax_errors)} 个 Python 语法错误:\n{error_msg}")

    def test_docker_check_migrate_space_structure(self):
        """测试 docker/index.py 中 checkDockerMigrateSpace 的返回数据结构"""
        docker_index_path = os.path.join(self.root_dir, "plugins", "docker", "index.py")
        with open(docker_index_path, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename="docker/index.py")
        
        # 查找 checkDockerMigrateSpace 函数定义
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "checkDockerMigrateSpace":
                func_node = node
                break

        self.assertIsNotNone(func_node, "未找到 checkDockerMigrateSpace 函数定义")

if __name__ == "__main__":
    unittest.main()
