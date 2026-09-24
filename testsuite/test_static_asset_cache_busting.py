# -*- coding: utf-8 -*-
"""
回归测试：静态资源缓存击穿（Dashboard 样式丢失根因）

背景：
    layout.html 曾用写死的 `?v={{config.version}}&t=20260527` 做缓存击穿，
    但 config.version 自 1.1.18(2026-05-20) 起未变，t 令牌自 2026-05-27 起未变；
    后端又对所有 /static/ 下发 `Cache-Control: public, max-age=604800, immutable`。
    于是 site.css 在 2026-09-15 追加首页轻拟态样式后 URL 仍未变，
    浏览器 7 天内继续命中旧 CSS ⇒ “Dashboard 样式丢失，刷新才恢复”。

修复：
    1. `web/utils/config.py::getAssetVersion(rel_path)` 基于文件 mtime+size 生成指纹；
    2. `inject_global_variables` 暴露模板全局 `asset_v`；
    3. 模板中的本地核心 CSS/JS 使用 `&t={{ asset_v(...) }}` 替代写死令牌。

本测试锁死上述契约，防止写死令牌回归。
"""

import os
import sys
import time
import importlib.util
import unittest
from unittest.mock import MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
STATIC_DIR = os.path.join(WEB_DIR, 'static')
CONFIG_PY = os.path.join(WEB_DIR, 'utils', 'config.py')

# config.py 顶层会 import core.yf / thisdb，测试环境用 mock 兜底
for mod in ['core', 'core.yf', 'thisdb', 'psutil', 'flask']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


def load_config_module():
    spec = importlib.util.spec_from_file_location('yf_utils_config', CONFIG_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStaticAssetCacheBusting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = load_config_module()

    def test_01_get_asset_version_matches_stat(self):
        """测试 1: 指纹应等于文件 mtime+size，且缺失文件回退为 '0'"""
        for rel in ['css/site.css', 'app/index.js', 'app/soft.js', 'app/public.js']:
            token = self.config.getAssetVersion(rel)
            self.assertNotEqual(token, '0', f'{rel} 应返回有效指纹')
            st = os.stat(os.path.join(STATIC_DIR, rel))
            self.assertEqual(token, '%x%x' % (int(st.st_mtime), st.st_size),
                             f'{rel} 指纹算法不一致')
        self.assertEqual(self.config.getAssetVersion('__not_exist__.css'), '0')

    def test_02_fingerprint_changes_on_file_change(self):
        """测试 2: 文件大小/mtime 变化必须导致指纹变化（缓存失效）"""
        probe = os.path.join(STATIC_DIR, '__cache_probe__.txt')
        try:
            with open(probe, 'w', encoding='utf-8') as f:
                f.write('a')
            # 绕过 30s 进程内缓存
            self.config._asset_version_cache.clear()
            first = self.config.getAssetVersion('__cache_probe__.txt')
            time.sleep(0.01)
            with open(probe, 'w', encoding='utf-8') as f:
                f.write('abcdef')
            self.config._asset_version_cache.clear()
            second = self.config.getAssetVersion('__cache_probe__.txt')
            self.assertNotEqual(first, second, '文件变化后指纹必须变化')
        finally:
            try:
                os.remove(probe)
            except OSError:
                pass

    def test_03_templates_use_dynamic_token(self):
        """测试 3: 模板禁止写死缓存令牌，必须使用 asset_v 动态指纹"""
        checks = {
            'layout.html': ["asset_v('css/site.css')", "asset_v('app/public.js')"],
            'index.html': [
                "asset_v('app/index.js')", "asset_v('app/soft.js')",
                "asset_v('app/site.js')", "asset_v('js/echarts.min.js')",
            ],
            'monitor.html': ["asset_v('app/control.js')", "asset_v('js/echarts.min.js')"],
            'soft.html': ["asset_v('app/soft.js')"],
            'site.html': ["asset_v('app/site.js')"],
            'files.html': ["asset_v('app/files.js')"],
            'firewall.html': ["asset_v('app/firewall.js')"],
            'crontab.html': ["asset_v('app/crontab.js')"],
            'logs.html': ["asset_v('app/logs.js')"],
            'setting.html': ["asset_v('app/config.js')"],
        }
        for name, needles in checks.items():
            path = os.path.join(WEB_DIR, 'templates', 'default', name)
            with open(path, encoding='utf-8') as f:
                content = f.read()
            for needle in needles:
                self.assertIn(needle, content, f'{name} 缺少动态指纹 {needle}')

        # 旧的写死令牌必须彻底消失
        with open(os.path.join(WEB_DIR, 'templates', 'default', 'layout.html'), encoding='utf-8') as f:
            layout = f.read()
        self.assertNotIn('t=20260527', layout, 'layout.html 仍残留写死的 t=20260527')
        self.assertNotIn('t=20260908', layout, 'layout.html 仍残留写死的 t=20260908')

    def test_04_context_processor_exposes_asset_v(self):
        """测试 4: 上下文处理器必须注入 asset_v"""
        init_py = os.path.join(WEB_DIR, 'admin', '__init__.py')
        with open(init_py, encoding='utf-8') as f:
            code = f.read()
        self.assertIn('asset_v=asset_v', code, '上下文处理器未注入 asset_v')
        self.assertIn('getAssetVersion', code, '未引用 getAssetVersion')

    def test_05_pjax_document_write_guarded(self):
        """测试 5: Pjax 会重跑内联脚本，echarts 兜底不得裸用 document.write"""
        for name in ['index.html', 'monitor.html']:
            path = os.path.join(WEB_DIR, 'templates', 'default', name)
            with open(path, encoding='utf-8') as f:
                content = f.read()
            self.assertIn("document.readyState === 'loading'", content,
                          f'{name} 缺少 document.write 解析阶段守卫')
            self.assertIn('document.head.appendChild(s)', content,
                          f'{name} 缺少非解析阶段的 DOM 追加兜底')


if __name__ == '__main__':
    unittest.main(verbosity=2)
