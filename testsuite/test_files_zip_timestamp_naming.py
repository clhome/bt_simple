# -*- coding: utf-8 -*-
"""
验证文件管理器压缩默认命名重构与重名递增防冲突自动化测试套件
测试目标：
1. 压缩文件名由随机字符串重构为当前时间戳（yyMMddHHmmss，12位纯数字）
2. 基础命名格式为：fileName + timeStr + ext（例如 test1261102174353.tar.gz）
3. 重名递增机制：若基础文件名已存在追加 -01，若 -01 也存在则递增为 -02、-03 等
4. 压缩类型扩展名完整映射：tar_gz -> .tar.gz, zip -> .zip, rar -> .rar, 7z -> .7z, xz -> .xz, bz2 -> .tar.bz2
5. 静态断言：zip 函数体内已彻底移除 getRandomString
"""
import os
import sys
import re
import json
import unittest
import subprocess

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FILES_JS = os.path.join(BASE_DIR, "web", "static", "app", "files.js")


class TestFilesZipTimestampNaming(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.isfile(FILES_JS), "web/static/app/files.js 不存在")
        with open(FILES_JS, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_01_static_zip_no_get_random_string(self):
        """测试 files.js 中 zip 函数已彻底移除 getRandomString 随机串并使用下划线拼接时间戳"""
        # 截取 zip 函数实现
        m_zip = re.search(r'function\s+zip\s*\([^\)]*\)\s*\{([\s\S]*?)\n\}\s*\n\s*//解压目录', self.content)
        self.assertTrue(m_zip, "未找到 zip 函数完整定义")
        zip_body = m_zip.group(1)
        self.assertNotIn('getRandomString', zip_body, "zip 函数中仍残留 getRandomString 调用！")
        self.assertIn('getCompressTimeString', zip_body, "zip 函数未调用 getCompressTimeString")
        self.assertIn("fileName + '_' + timeStr", zip_body, "zip 函数未采用 fileName + '_' + timeStr 格式命名")
        self.assertIn('getCompressExt', zip_body, "zip 函数未调用 getCompressExt")
        self.assertIn('resolveCompressFileName', zip_body, "zip 函数未调用 resolveCompressFileName")

    def test_02_static_helper_functions_exist(self):
        """测试 files.js 中声明了完备的压缩时间戳与防重名辅助函数"""
        self.assertIn('function getCompressTimeString', self.content)
        self.assertIn('function getCompressExt', self.content)
        self.assertIn('function getCompressFileNameWithIndex', self.content)
        self.assertIn('function findAvailableCompressIndex', self.content)
        self.assertIn('function resolveCompressFileName', self.content)

    def test_03_js_runtime_functions(self):
        """通过 Node.js 运行时执行 files.js 中的相关函数并进行严谨断言"""
        js_code = r'''
const fs = require('fs');
const filesJsPath = process.argv[1];
const content = fs.readFileSync(filesJsPath, 'utf8');

// 截取 files.js 中新增加的压缩辅助工具函数块
const markerStart = '// 获取压缩包时间戳格式';
const markerEnd = '// 导出至 window 方便全局调用及自动化测试';
const startIdx = content.indexOf(markerStart);
const endIdx = content.indexOf(markerEnd);
if (startIdx === -1 || endIdx === -1) {
    throw new Error('未在 files.js 中定位到压缩时间戳与重命名核心函数块');
}
const funcSnippet = content.substring(startIdx, endIdx);

// 构造沙箱环境
const createMock = () => {
    const fn = function() { return createMock(); };
    return new Proxy(fn, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (prop === 'length') return 0;
            if (prop === 'val') return () => '/www/wwwroot';
            return createMock();
        },
        set: (target, prop, value) => {
            target[prop] = value;
            return true;
        },
        apply: () => createMock()
    });
};
const $ = createMock();
const window = {
    currentFiles: [],
    $: $
};
global.window = window;
global.$ = $;

const evalCode = `
${funcSnippet}
global.getCompressTimeString = getCompressTimeString;
global.getCompressExt = getCompressExt;
global.getCompressFileNameWithIndex = getCompressFileNameWithIndex;
global.findAvailableCompressIndex = findAvailableCompressIndex;
global.resolveCompressFileName = resolveCompressFileName;
`;
eval(evalCode);

const results = {};

// 1. 测试时间戳格式 (yyMMddHHmmss 12位纯数字)
const ts = global.getCompressTimeString();
results.ts = ts;
results.tsValid = /^\d{12}$/.test(ts);

// 2. 测试扩展名映射
const extMap = {
    'tar_gz': global.getCompressExt('tar_gz'),
    'zip': global.getCompressExt('zip'),
    'rar': global.getCompressExt('rar'),
    'gz': global.getCompressExt('gz'),
    '7z': global.getCompressExt('7z'),
    'xz': global.getCompressExt('xz'),
    'bz2': global.getCompressExt('bz2')
};
results.extMap = extMap;

// 3. 测试文件重命名递增格式
const base = 'test1_261102174353';
const ext = '.tar.gz';
results.fn_0 = global.getCompressFileNameWithIndex(base, 0, ext);
results.fn_1 = global.getCompressFileNameWithIndex(base, 1, ext);
results.fn_2 = global.getCompressFileNameWithIndex(base, 2, ext);
results.fn_10 = global.getCompressFileNameWithIndex(base, 10, ext);

// 4. 测试 findAvailableCompressIndex 查找逻辑
const existsSet = new Set();
results.idx_first = global.findAvailableCompressIndex(base, ext, existsSet); // 应该是 0

existsSet.add(base + ext); // 模拟存在 test1_261102174353.tar.gz
results.idx_after_base = global.findAvailableCompressIndex(base, ext, existsSet); // 应该是 1

existsSet.add(base + '-01' + ext); // 模拟存在 test1_261102174353-01.tar.gz
results.idx_after_01 = global.findAvailableCompressIndex(base, ext, existsSet); // 应该是 2

existsSet.add(base + '-02' + ext); // 模拟存在 test1_261102174353-02.tar.gz
results.idx_after_02 = global.findAvailableCompressIndex(base, ext, existsSet); // 应该是 3

// 5. 测试 resolveCompressFileName 针对真实存在的后端文件进行递增校准
$.post = function(url, data, cb) {
    // 模拟服务端返回存在 test1_261102174353.tar.gz
    if (typeof cb === 'function') {
        cb({
            status: true,
            data: [
                { filename: base + ext }
            ]
        });
    }
    return { fail: function() {} };
};

let callbackResult = null;
const initName = global.resolveCompressFileName('/www/wwwroot', base, 'tar_gz', function(finalName, finalIdx) {
    callbackResult = { finalName, finalIdx };
});
results.initName = initName;
results.callbackResult = callbackResult;

console.log(JSON.stringify(results));
'''
        # 运行 Node.js 脚本
        cmd = ['node', '-e', js_code, FILES_JS]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(p.returncode, 0, f"Node.js 运行失败: {p.stderr}")

        data = json.loads(p.stdout.strip())

        # 断言 1：时间戳必须为 12 位纯数字
        self.assertTrue(data.get('tsValid'), f"时间戳格式不正确: {data.get('ts')}")
        self.assertEqual(len(data.get('ts')), 12, "时间戳长度必须为12位")

        # 断言 2：扩展名映射完整且准确
        exts = data.get('extMap', {})
        self.assertEqual(exts.get('tar_gz'), '.tar.gz')
        self.assertEqual(exts.get('zip'), '.zip')
        self.assertEqual(exts.get('rar'), '.rar')
        self.assertEqual(exts.get('gz'), '.gz')
        self.assertEqual(exts.get('7z'), '.7z')
        self.assertEqual(exts.get('xz'), '.xz')
        self.assertEqual(exts.get('bz2'), '.tar.bz2')

        # 断言 3：文件名格式化（无后缀 -> -01 -> -02 -> -10）
        self.assertEqual(data.get('fn_0'), 'test1_261102174353.tar.gz')
        self.assertEqual(data.get('fn_1'), 'test1_261102174353-01.tar.gz')
        self.assertEqual(data.get('fn_2'), 'test1_261102174353-02.tar.gz')
        self.assertEqual(data.get('fn_10'), 'test1_261102174353-10.tar.gz')

        # 断言 4：递增序号查找逻辑
        self.assertEqual(data.get('idx_first'), 0, "无冲突时序号应为 0")
        self.assertEqual(data.get('idx_after_base'), 1, "基础文件冲突时序号应递增为 1 (-01)")
        self.assertEqual(data.get('idx_after_01'), 2, "-01 文件冲突时序号应递增为 2 (-02)")
        self.assertEqual(data.get('idx_after_02'), 3, "-02 文件冲突时序号应递增为 3 (-03)")

        # 断言 5：resolveCompressFileName 针对已存在文件返回正确的 -01
        cb = data.get('callbackResult') or {}
        self.assertEqual(cb.get('finalName'), 'test1_261102174353-01.tar.gz')
        self.assertEqual(cb.get('finalIdx'), 1)

    def test_04_js_runtime_multiple_collisions_and_fallback(self):
        """测试多次连续冲突（基础名、-01、-02均冲突）时自动递增到 -03 以及 zip 格式命名"""
        js_code = r'''
const fs = require('fs');
const filesJsPath = process.argv[1];
const content = fs.readFileSync(filesJsPath, 'utf8');

const markerStart = '// 获取压缩包时间戳格式';
const markerEnd = '// 导出至 window 方便全局调用及自动化测试';
const startIdx = content.indexOf(markerStart);
const endIdx = content.indexOf(markerEnd);
const funcSnippet = content.substring(startIdx, endIdx);

const createMock = () => {
    const fn = function() { return createMock(); };
    return new Proxy(fn, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (prop === 'length') return 0;
            if (prop === 'val') return () => '/www/wwwroot';
            return createMock();
        },
        set: (target, prop, value) => {
            target[prop] = value;
            return true;
        },
        apply: () => createMock()
    });
};
const $ = createMock();
const base = 'test1_261102174353';
const ext = '.tar.gz';

// 模拟同时存在 base, base-01, base-02 三个文件
$.post = function(url, data, cb) {
    if (typeof cb === 'function') {
        cb({
            status: true,
            data: [
                { filename: base + ext },
                { filename: base + '-01' + ext },
                { filename: base + '-02' + ext }
            ]
        });
    }
    return { fail: function() {} };
};

const window = {
    currentFiles: [],
    $: $
};
global.window = window;
global.$ = $;

eval(funcSnippet);

let callbackResult = null;
resolveCompressFileName('/www/wwwroot', base, 'tar_gz', function(finalName, finalIdx) {
    callbackResult = { finalName, finalIdx };
});

// 测试 zip 格式命名
let zipCallbackResult = null;
resolveCompressFileName('/www/wwwroot', base, 'zip', function(finalName, finalIdx) {
    zipCallbackResult = { finalName, finalIdx };
});

console.log(JSON.stringify({ callbackResult, zipCallbackResult }));
'''
        cmd = ['node', '-e', js_code, FILES_JS]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(p.returncode, 0, f"Node.js 运行失败: {p.stderr}")

        data = json.loads(p.stdout.strip())
        cb = data.get('callbackResult') or {}
        self.assertEqual(cb.get('finalName'), 'test1_261102174353-03.tar.gz', "当基础名、-01、-02均存在时，应递增至 -03")
        self.assertEqual(cb.get('finalIdx'), 3)

        zip_cb = data.get('zipCallbackResult') or {}
        self.assertEqual(zip_cb.get('finalName'), 'test1_261102174353.zip', "zip格式无冲突时应为 test1_261102174353.zip")
        self.assertEqual(zip_cb.get('finalIdx'), 0)


if __name__ == '__main__':
    unittest.main()
