import json
import os
import re
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
LANG_DIR = 'plugins/op_waf/lang'

print("=" * 70)
print("开始执行御风 OP 防火墙 (op_waf) 全量多语言 V2 自动化回归测试套件")
print("=" * 70)

# 测试项 1: 验证 6 国语言包文件规范及合法性
print("\n[测试项 1] 验证 6 国语言包文件规范（无 BOM、LF 换行、完全对称）...")
dicts = {}
for lang in LANGS:
    path = os.path.join(LANG_DIR, f"{lang}.json")
    assert os.path.exists(path), f"文件不存在: {path}"
    
    with open(path, 'rb') as f:
        raw = f.read()
        assert not raw.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM: {path}"
        assert b'\r\n' not in raw, f"换行符包含 CRLF: {path}"
    
    with open(path, 'r', encoding='utf-8') as f:
        try:
            dicts[lang] = json.load(f)
        except Exception as e:
            raise AssertionError(f"JSON 语法解析失败: {path}, 错误: {e}")

base_keys = set(dicts['zh-CN'].keys())
print(f"zh-CN 词条基准总数: {len(base_keys)}")

for lang in LANGS:
    cur_keys = set(dicts[lang].keys())
    assert len(cur_keys) == len(base_keys), f"{lang} 词条数 ({len(cur_keys)}) 与 zh-CN ({len(base_keys)}) 不一致!"
    diff = base_keys - cur_keys
    assert not diff, f"{lang} 缺少词条: {diff}"
    print(f"  ✓ {lang}.json 验证通过 (词条数: {len(cur_keys)})")

# 测试项 2: 核心词条多语言覆盖率与外语中文泄漏断言
print("\n[测试项 2] 验证本次修复的重点词条多语言完整性与质量...")

# 重点词条组定义
test_groups = {
    "用户图 1 关注点 (Dashboard 性能损耗说明)": [
        "网站防火墙会使nginx有一定的性能损失（&lt;5% 10C静态并发测试结果）",
    ],
    "用户图 2 关注点 (Global 其它非通用过滤及防护项)": [
        "其它非通用过滤",
        "智能蜘蛛识别与伪造拦截",
        "过虑CC攻击"
    ],
    "蜘蛛白名单新增交互条目": [
        "IP / 网段 (CIDR)",
        "共",
        "删除确认",
        "同步失败!",
        "同步成功!",
        "备注 (如 字节跳动)",
        "无备注",
        "暂无规则",
        "添加失败!"
    ],
    "区域封锁 (Regional) 与地区条目": [
        "所有站点",
        "中国大陆以外的地区(包括[港,澳,台])",
        "中国大陆(不包括[港,澳,台])",
        "中国大陆以外的地区(包括[中国特别行政区:港,澳,台])",
        "中国大陆(不包括[中国特别行政区:港,澳,台])",
        "海外",
        "中国",
        "香港",
        "澳门",
        "台湾",
        "中国香港",
        "中国澳门",
        "中国台湾"
    ],
    "后端 API 消息条目": [
        "内置规则文件不存在!",
        "指定的索引不存在!",
        "日期参数格式错误!",
        "模式不支持，仅支持 downgrade 或 block",
        "站点名称包含非法字符!",
        "获取成功!",
        "规则文件不存在!",
        "规则文件为空!",
        "该 IP/网段 已存在!",
        "非法访问路径!",
        "删除失败: ",
        "同步成功，当前共 ",
        "读取日志失败: "
    ]
}

for group_name, keys in test_groups.items():
    print(f"\n  检查 {group_name} ({len(keys)} 个词条)...")
    for k in keys:
        for lang in ['en', 'de', 'fr', 'it']:
            trans = dicts[lang].get(k)
            assert trans, f"[{lang}] 缺失翻译: {k}"
            # 确保外语翻译中不含汉字（CIDR、URL等英文符号除外）
            chinese_in_trans = re.findall(r'[\u4e00-\u9fa5]', trans)
            assert not chinese_in_trans, f"[{lang}] 翻译依然包含中文: '{k}' -> '{trans}'"
    print(f"  ✓ {group_name} 在英/德/法/意 4 国语言下 100% 翻译就绪且无中文汉字残留")

# 测试项 3: 前端 JS 代码集成与语法断言
print("\n[测试项 3] 验证前端代码国际化逻辑集成...")
with open('plugins/op_waf/js/op_waf.js', 'r', encoding='utf-8') as f:
    js_content = f.read()

# 验证 op_waf.js 核心改动
assert "pt('其它') + '</td><td>'+ pt(rdata.other.ps)" in js_content, "op_waf.js 缺少 pt(rdata.other.ps)"
assert "if (index == 'allsite') index = pt('所有站点');" in js_content, "op_waf.js 缺少 pt('所有站点')"
assert "if (index == '海外') index = pt('中国大陆以外的地区(包括[港,澳,台])');" in js_content, "op_waf.js 缺少 海外 国际化"
assert "if (index == '中国') index = pt('中国大陆(不包括[港,澳,台])');" in js_content, "op_waf.js 缺少 中国 国际化"
assert "str.push(pt(index));" in js_content, "op_waf.js 缺少 str.push(pt(index))"
assert "name:pt(tval),value:tval" in js_content, "op_waf.js 缺少 name:pt(tval)"
print("  ✓ op_waf.js 前端包裹与国际化逻辑断言通过")

# 验证 public.js 改动
with open('web/static/app/public.js', 'r', encoding='utf-8') as f:
    pub_content = f.read()
assert "t('public.save_1', '保存')" in pub_content, "public.js 缺少 t('public.save_1')"
assert "t('public.refresh_1', '刷新')" in pub_content, "public.js 缺少 t('public.refresh_1')"
assert "t('public.edit_online', '在线编辑')" in pub_content, "public.js 缺少 t('public.edit_online')"
assert "t('public.auto_refresh', '自动刷新')" in pub_content, "public.js 缺少 t('public.auto_refresh')"
print("  ✓ public.js 在线编辑弹窗多语言 fallback 断言通过")

# 运行 node -c 语法校验
res_js = subprocess.run(["node", "-c", "plugins/op_waf/js/op_waf.js"], capture_output=True, text=True)
assert res_js.returncode == 0, f"op_waf.js 语法错误: {res_js.stderr}"
print("  ✓ op_waf.js node 语法检查通过")

res_pub = subprocess.run(["node", "-c", "web/static/app/public.js"], capture_output=True, text=True)
assert res_pub.returncode == 0, f"public.js 语法错误: {res_pub.stderr}"
print("  ✓ public.js node 语法检查通过")

# 测试项 4: 模拟 index.py 对旧版本响应模板的自动检测与平滑升级机制
print("\n[测试项 4] 验证后端 index.py 旧版本拦截模板自愈与平滑升级机制...")
with open('plugins/op_waf/index.py', 'r', encoding='utf-8') as f:
    py_content = f.read()

assert "'waf-i18n' not in content_old or '熠风' in content_old" in py_content, "index.py 缺少旧模板检测条件"
assert "bak_path = path + \".wafbak\"" in py_content, "index.py 缺少旧模板自动备份"
assert "yf.writeFile(path, yf.readFile(plugin_src))" in py_content, "index.py 缺少新模板覆盖逻辑"

# 验证所有内置 html 文件均包含 waf-i18n 与衢州御风科技出品署名
html_files = ['get', 'post', 'safe_js', 'user_agent', 'cookie', 'other']
for h in html_files:
    h_path = os.path.join('plugins/op_waf/waf/html', f"{h}.html")
    assert os.path.exists(h_path), f"模板不存在: {h_path}"
    with open(h_path, 'r', encoding='utf-8') as f:
        h_text = f.read()
    assert "<!-- waf-i18n -->" in h_text, f"{h}.html 缺少 waf-i18n 国际化脚本"
    assert "衢州御风科技有限公司" in h_text, f"{h}.html 出品署名不正确"
    assert "衢州熠风科技有限公司" not in h_text, f"{h}.html 仍残留旧公司名'熠风'"

print("  ✓ 6 套拦截响应 HTML 模板均已配备 waf-i18n 与正确的御风科技署名，升级引擎逻辑闭环")

print("\n" + "=" * 70)
print("恭喜！御风 OP 防火墙 (op_waf) 全量多语言 V2 自动化回归测试 100% 通过！")
print("=" * 70)
