import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
LANG_DIR = 'plugins/op_waf/lang'

print("=" * 60)
print("开始执行御风 OP 防火墙 (op_waf) 全量多语言自动化回归测试")
print("=" * 60)

# 1. 验证语言包 JSON 语法与文件规范
print("\n[测试项 1] 验证 6 国语言包文件规范及合法性...")
dicts = {}
for lang in LANGS:
    path = os.path.join(LANG_DIR, f"{lang}.json")
    assert os.path.exists(path), f"文件不存在: {path}"
    
    with open(path, 'rb') as f:
        raw = f.read()
        assert not raw.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM: {path}"
        assert b'\r\n' not in raw, f"换行符不是 LF: {path}"
    
    with open(path, 'r', encoding='utf-8') as f:
        try:
            dicts[lang] = json.load(f)
        except Exception as e:
            raise AssertionError(f"JSON 语法解析失败: {path}, 错误: {e}")

base_keys = set(dicts['zh-CN'].keys())
print(f"zh-CN 词条总数: {len(base_keys)}")

for lang in LANGS:
    cur_keys = set(dicts[lang].keys())
    assert len(cur_keys) == len(base_keys), f"{lang} 词条数 ({len(cur_keys)}) 与 zh-CN ({len(base_keys)}) 不一致!"
    diff = base_keys - cur_keys
    assert not diff, f"{lang} 缺少词条: {diff}"
    print(f"  ✓ {lang}.json 验证通过 (词条数: {len(cur_keys)})")

# 2. 针对用户截图 1~6 处的重点词条进行多语言覆盖率与翻译正确性断言
print("\n[测试项 2] 针对用户反馈的三张截图 6 处关键位置进行断言...")

# 标注 1: Function 介绍页
intro_keys = [
    '🛡️ 御风 OP 安全防护引擎 V1.0',
    '深度优化的高性能 Web 应用防火墙，为您提供企业级安全防护，拦截各类复杂渗透攻击，全方位守护站点安全。',
    '基础防御体系',
    '作为一款轻量级却功能强大的 WAF，已全面具备以下传统防护能力：',
    '常见渗透防护：',
    '有效拦截常见的 SQL 注入、XSS 跨站脚本攻击、一句话木马上传等。',
    '恶意扫描器拦截：',
    '自动识别并阻断各类常见扫描器（如 sqlmap, awvs 等）的恶意探测。',
    '多维度特征过滤：',
    '支持从 URL、GET/POST 参数、Cookie、User-Agent 等多个 HTTP 维度进行精准特征匹配。',
    '攻克传统 WAF 痛点 (核心进化)',
    '针对现代互联网复杂多变的攻击手法，我们进行了深度的针对性底层优化：',
    '智能动态信誉系统：',
    '首创阶梯式信誉扣分机制（满分100分，',
    '所有违规扣分在 24 小时内累计计算',
    '）。短期频控（例如违规6次封禁3分钟）与长效信誉系统（分数扣满直接拉黑24小时）完美联动。这种组合防御既提供了极高的容错率防误伤，又对持续跨周期渗透的黑产实现致命“连坐”封锁。',
    '高级防御',
    '拦截类型',
    '单次违规扣分',
    '24小时内累计触发 封杀条件',
    'CC 攻击频控拦截',
    '- 5 分',
    '累计违规 20 次',
    'User-Agent (伪造浏览器/爬虫)',
    '- 10 分',
    '累计违规 10 次',
    '恶意扫描器拦截 (Scan)',
    '- 15 分',
    '累计违规 7 次',
    '核心攻击检测 (SQL注入/XSS等)',
    '- 15 分',
    '累计违规 7 次',
    '高危蜜罐探测 (Honeypot)',
    '- 100 分',
    '1 次 (零容忍秒封)',
    '自动化高危蜜罐探测：',
    '防御不再是被动挨打！内置并支持自定义诱导性敏感路径（如',
    '）。一旦扫描器或黑客尝试触碰这些虚假目标，信誉分瞬间归零，零容忍立刻封禁24小时，将攻击扼杀于摇篮之中。',
    '主动防御',
    '真实客户端追踪：',
    '引入',
    '机制严密校验可信代理池，防范 CDN 场景下的',
    '伪造欺骗，精准锁定攻击者真实物理源。',
    'JSON 深度解析拦截：',
    '突破传统正则在复杂 API 接口下的盲区，支持最高 10 层深度的 JSON Body 提取与审查，让深层嵌套攻击无处遁形。',
    '精准封禁与极速解封：',
    '重构底层拦截字典逻辑，彻底剥离“观察期IP”与“真实封杀IP”。面板实时展示真实确凿的拦截名单，并提供即时的一键释放清零功能，状态同步瞬间直达底层引擎。',
    '极致性能优化',
    'IP 匹配引擎革命：',
    '彻底废弃低效的线性循环遍历，全量引入基于 Radix Tree 的',
    '算法引擎。即使面对十万乃至百万级海量黑IP库，也能在极微秒（µs）级别完成高速匹配，完全消除庞大规则库带来的性能损耗。',
    '算力飞跃',
    'PCRE JIT 正则加速：',
    '全局正则表达式启用了 JIT (即时编译) 和编译缓存，在百万级并发 QPS 场景下极大降低 CPU 计算开销。',
    '大文件流式截断防 OOM：',
    '智能识别大文件上传特征，仅提取关键前 64KB 进行恶意样本比对，从物理根源上彻底杜绝读取超大文件导致 Nginx 内存暴涨崩溃的隐患。',
    '防共享内存雪崩：',
    '优化大流量下的并发写入与读取逻辑，在遭遇每秒数万次海量 CC 或恶意扫描时，有效防止共享字典（Dict）爆满导致的规则失效瘫痪。',
    '衢州御风科技给您的安心承诺',
    '本次御风OP防火墙基于大量实战攻防经验，进行了多维度底层安全与性能优化。我们充分考虑了各种可能拖垮服务或被绕过的边缘场景。所有规则对您站点的常规业务',
    '零侵入',
    '，保证低延迟与高可用。您可以放心开启各项防御功能，享受丝滑且坚固的安全防线！',
]

# 标注 2、4: 全局右下角出品署名
footer_keys = [
    '衢州御风科技有限公司 出品',
    '衢州御风科技有限公司出品'
]

# 标注 3: Global 表格防护项描述
global_desc_keys = [
    '强制安全校验',
    '过滤uri、uri参数中常见sql注入、xss等攻击',
    '过滤POST参数中常见sql注入、xss等攻击',
    '通常用于过滤浏览器、蜘蛛及一些自动扫描器',
    '过滤利用Cookie发起的渗透攻击',
    '过滤常见扫描测试工具的渗透测试',
    '自动蜜罐防护，拦截自动扫描器和嗅探脚本'
]

# 标注 5: Serve 操作说明
serve_instruction_keys = [
    '💡 服务操作说明',
    '服务操作说明',
    '重启',
    '重载配置',
    '：仅重新启动底层的 Nginx 进程。适合服务假死时的快速恢复，或者测试您手动修改的底层 Lua 脚本。',
    '仅重新启动底层的 Nginx 进程。适合服务假死时的快速恢复，或者测试您手动修改的底层 Lua 脚本。',
    '：重新将面板的所有 JSON 规则编译为 Lua 脚本并重启 Nginx。若您通过 SSH 手动修改了配置，请务必点击此按钮以完整生效。（注：日常在面板中修改规则会自动重载，无需手动点击）',
    '重新将面板的所有 JSON 规则编译为 Lua 脚本并重启 Nginx。若您通过 SSH 手动修改了配置，请务必点击此按钮以完整生效。（注：日常在面板中修改规则会自动重载，无需手动点击）'
]

# 标注 6: Serve 核心规则统计
serve_stat_keys = [
    '🛡️ 核心过滤规则统计',
    '核心过滤规则统计',
    'GET 参数过滤规则',
    'POST 参数过滤规则',
    'Cookie 过滤规则',
    'URL 过滤规则',
    'User-Agent 过滤规则',
    '条'
]

all_check_groups = {
    "标注 1 (Function 介绍页词条)": intro_keys,
    "标注 2 & 4 (右下角出品水印)": footer_keys,
    "标注 3 (Global 页面描述)": global_desc_keys,
    "标注 5 (Serve 服务操作说明)": serve_instruction_keys,
    "标注 6 (Serve 核心规则统计)": serve_stat_keys
}

for group_name, keys in all_check_groups.items():
    print(f"\n  检查 {group_name} ({len(keys)} 个词条)...")
    for k in keys:
        for lang in ['en', 'de', 'fr', 'it']:
            trans = dicts[lang].get(k)
            assert trans, f"[{lang}] 缺失翻译: {k}"
            # 确保外语翻译中不含汉字
            chinese_in_trans = re.findall(r'[\u4e00-\u9fa5]', trans)
            assert not chinese_in_trans, f"[{lang}] 翻译依然包含中文: {k} -> {trans}"
    print(f"  ✓ {group_name} 在英/德/法/意 4 国语言下全部翻译就绪且 100% 无中文残留")

# 3. 检查前端代码渲染集成
print("\n[测试项 3] 验证前端静态文件代码集成...")
with open('plugins/op_waf/index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# 验证 index.html
assert 'var pt = (window.YfI18n' in html_content, "index.html 缺少 pt 定义"
assert 'updateYufengFooter()' in html_content, "index.html 缺少 updateYufengFooter 调用"
assert "data-i18n=\"衢州御风科技有限公司 出品\"" in html_content, "#yufeng-footer 缺少 data-i18n"
assert "pt('💡 服务操作说明')" in html_content, "renderWafAdditionalContent 缺少 pt('💡 服务操作说明')"
assert "pt('GET 参数过滤规则')" in html_content, "renderWafAdditionalContent 缺少 pt('GET 参数过滤规则')"
assert "pt('条')" in html_content, "renderWafAdditionalContent 缺少 pt('条')"
assert "pt('🛡️ 御风 OP 安全防护引擎 V1.0')" in html_content, "wafIntro 缺少 pt('🛡️ 御风 OP 安全防护引擎 V1.0')"
assert "pt('智能动态信誉系统：')" in html_content, "wafIntro 缺少信誉系统 pt 包裹"
print("  ✓ index.html 多语言动态渲染语法校验通过")

with open('plugins/op_waf/js/op_waf.js', 'r', encoding='utf-8') as f:
    js_content = f.read()

# 验证 op_waf.js
assert 'pt(rdata.safe_verify.ps)' in js_content, "op_waf.js 缺少 pt(rdata.safe_verify.ps)"
assert 'pt(rdata.get.ps)' in js_content, "op_waf.js 缺少 pt(rdata.get.ps)"
assert 'pt(rdata.post.ps)' in js_content, "op_waf.js 缺少 pt(rdata.post.ps)"
assert "pt(rdata['user-agent'].ps)" in js_content, "op_waf.js 缺少 pt(rdata['user-agent'].ps)"
assert 'pt(rdata.cookie.ps)' in js_content, "op_waf.js 缺少 pt(rdata.cookie.ps)"
assert 'pt(rdata.scan.ps)' in js_content, "op_waf.js 缺少 pt(rdata.scan.ps)"
assert "pt('您真的要删除这条过滤规则吗？')" in js_content, "removeRule 确认文案缺少 pt"
assert "pt(\"CDN增强检测 - 可信代理设置\")" in js_content, "CDN设置标题缺少 pt"
assert "pt(\"导出数据\")" in js_content, "导出数据标题缺少 pt"
assert "pt('局域网/保留地址')" in js_content, "IP归属保留地址缺少 pt"
print("  ✓ op_waf.js 多语言包裹及防护项描述校验通过")

# 4. 运行 node 语法检查
print("\n[测试项 4] 运行 JavaScript 语法合法性检验...")
res = subprocess.run(["node", "-c", "plugins/op_waf/js/op_waf.js"], capture_output=True, text=True)
assert res.returncode == 0, f"op_waf.js 存在语法错误: {res.stderr}"
print("  ✓ op_waf.js 经过 node -c 语法检查，完全合法！")

print("\n" + "=" * 60)
print("所有 4 项自动化多语言回归测试全部通过 (100% PASS)！")
print("=" * 60)
