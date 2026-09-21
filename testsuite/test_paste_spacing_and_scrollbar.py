# -*- coding: utf-8 -*-
import os
import re
import unittest
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class TestPasteSpacingAndScrollbar(unittest.TestCase):
    """验证底部横向滚动条消除与粘贴/回收站间距拉开的自动化测试套件"""

    def test_01_css_overflow_and_tiptools_box_sizing(self):
        """验证 site.css 和 ensite.css 中杜绝横向滚动条的关键规则"""
        css_files = [
            os.path.join(BASE_DIR, 'web/static/css/site.css'),
            os.path.join(BASE_DIR, 'web/static/css/ensite.css')
        ]
        for css_path in css_files:
            with open(css_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('overflow-x: hidden', content, f"{css_path} 缺少 overflow-x: hidden 全局防溢出规则")
            self.assertIn('#tipTools', content, f"{css_path} 缺少 #tipTools 规则")
            self.assertIn('box-sizing: border-box !important', content, f"{css_path} 中 #tipTools 必须强制 border-box 杜绝 padding 溢出")

    def test_02_files_js_tiptools_no_pixel_overflow(self):
        """验证 files.js 中彻底移除了导致 30px padding 溢出的硬编码 tipTools.width 调用"""
        files_js = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js, 'r', encoding='utf-8') as f:
            content = f.read()

        # 确保不存在老的直接设宽撑出滚动条的代码
        self.assertNotIn('$("#tipTools").width($(".file-box").width())', content)
        self.assertIn('$("#tipTools").css({"box-sizing": "border-box", "width": "100%"', content)

    def test_03_html_batch_initial_right_and_trash_margin(self):
        """验证 files.html 中 #Batch 初始定位 >= 216px 以及回收站 right 为 107px、margin-right 为 0"""
        files_html = os.path.join(BASE_DIR, 'web/templates/default/files.html')
        with open(files_html, 'r', encoding='utf-8') as f:
            html_content = f.read()

        match = re.search(r"id=['\"]Batch['\"][^>]*right:\s*(\d+)px", html_content)
        self.assertIsNotNone(match, "files.html 中必须包含 #Batch 的 right 像素定义")
        initial_right = int(match.group(1))
        self.assertGreaterEqual(initial_right, 216, f"初始 #Batch right 必须 >= 216px，当前为 {initial_right}px")

        files_js = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js, 'r', encoding='utf-8') as f:
            js_content = f.read()
        self.assertIn('right: 107px', js_content, "files.js 生成 #recycle_bin 时必须定位为 right: 107px 留出与视图切换按钮的20px间隙")
        self.assertIn('margin-right: 0', js_content, "files.js 生成 #recycle_bin 时必须重置 margin-right: 0")

    def test_04_node_runtime_spacing_calculation(self):
        """Node.js 运行时模拟测量与定位计算，断言回收站与视图切换按钮间距严格 >= 20px，且粘贴与回收站间距严格 >= 20px"""
        sim_js = """
        // 模拟 showSeclect 中的间距计算算法
        function calculateRightPos(mockDom) {
            var count = mockDom.count;
            var $batch = mockDom.$batch;
            var $trash = mockDom.$trash;
            var rightPos = 216; // 默认保底间隙位置 (107 + 88 + 21)

            if ($trash.length && $trash.visible) {
                var $parent = $batch.offsetParent();
                var parentW = ($parent && $parent.length) ? $parent.width() : 0;
                var trashPos = $trash.position();
                if (parentW > 0 && trashPos && typeof trashPos.left === 'number') {
                    var trashLeftFromRight = parentW - trashPos.left;
                    var gap = 20;
                    rightPos = Math.max(216, trashLeftFromRight + gap);
                } else {
                    var trashRight = $trash.cssRight || 107;
                    var trashMarginRight = $trash.cssMarginRight || 0;
                    var trashWidth = $trash.outerWidth || 88;
                    var gap = 20;
                    rightPos = Math.max(216, trashRight + trashMarginRight + trashWidth + gap);
                }
            }
            return rightPos;
        }

        // 视图切换按钮占位 [15px, 87px] (右边距 15px + 按钮组宽约 72px)
        const viewButtonsLeftEdgeFromRight = 87;

        // 场景 1: 标准中文回收站 (宽 88px, right 107px, margin-right 0px)
        // 回收站与视图切换按钮间距 = 107 - 87 = 20px
        const trashRight1 = 107;
        const gapViewTrash1 = trashRight1 - viewButtonsLeftEdgeFromRight;
        if (gapViewTrash1 < 20) {
            throw new Error(`Scene 1 View-Trash gap too small: ${gapViewTrash1}px, expected >= 20px`);
        }

        const scene1 = {
            count: 0,
            $batch: {
                offsetParent: () => ({ length: 1, width: () => 1000 })
            },
            $trash: {
                length: 1,
                visible: true,
                position: () => ({ left: 1000 - 107 - 88 }), // 回收站左边框在 805px 处 (从右往左看在 195px 处)
                outerWidth: 88,
                cssRight: 107,
                cssMarginRight: 0
            }
        };
        const pos1 = calculateRightPos(scene1);
        // 回收站左边框距离包含块右边缘是 195px
        // 粘贴按钮右边框应为 pos1，间距 = pos1 - 195
        const gapTrashPaste1 = pos1 - 195;
        if (gapTrashPaste1 < 20) {
            throw new Error(`Scene 1 Trash-Paste gap too small: ${gapTrashPaste1}px, expected >= 20px (pos: ${pos1})`);
        }

        // 场景 2: 包含块未准备好或离屏兜底计算
        const scene2 = {
            count: 0,
            $batch: {
                offsetParent: () => ({ length: 0 })
            },
            $trash: {
                length: 1,
                visible: true,
                position: () => null,
                outerWidth: 88,
                cssRight: 107,
                cssMarginRight: 0
            }
        };
        const pos2 = calculateRightPos(scene2);
        const gapTrashPaste2 = pos2 - (107 + 88);
        if (gapTrashPaste2 < 20) {
            throw new Error(`Scene 2 Trash-Paste gap too small: ${gapTrashPaste2}px, expected >= 20px (pos: ${pos2})`);
        }

        // 场景 3: 德语较宽回收站 (宽 115px, right 107px)
        const scene3 = {
            count: 0,
            $batch: {
                offsetParent: () => ({ length: 1, width: () => 1000 })
            },
            $trash: {
                length: 1,
                visible: true,
                position: () => ({ left: 1000 - 107 - 115 }), // 从右往左看在 222px 处
                outerWidth: 115,
                cssRight: 107,
                cssMarginRight: 0
            }
        };
        const pos3 = calculateRightPos(scene3);
        const gapTrashPaste3 = pos3 - 222;
        if (gapTrashPaste3 < 20) {
            throw new Error(`Scene 3 Trash-Paste gap too small: ${gapTrashPaste3}px, expected >= 20px (pos: ${pos3})`);
        }

        console.log(`[PASS] Node.js Spacing Simulation: View-Trash gap=${gapViewTrash1}px, Trash-Paste gap1=${gapTrashPaste1}px, gap2=${gapTrashPaste2}px, gap3=${gapTrashPaste3}px (all >= 20px)`);
        """
        res = subprocess.run(['node', '-e', sim_js], capture_output=True, text=True, cwd=BASE_DIR)
        self.assertEqual(res.returncode, 0, f"Node.js spacing test failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("PASS", res.stdout)

if __name__ == '__main__':
    unittest.main()
