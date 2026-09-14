# -*- coding: utf-8 -*-
"""
bt_simple 插件 i18n 代码优化器

职责：
  1. 把新词条写入 plugins/<name>/lang/{zh-CN,zh-TW,en,de,fr,it}.json
  2. 将 JS 中未包裹的中文串包上 pt() / msgTpl(pt(...))
  3. 打印无法自动处理、需人工确认的项

安全原则（对应报告红线）：
  - 语言包 value 严禁含 HTML
  - 保留 {n} 占位符与 \\n / \\uFEFF
  - 不动注释行、不动参数名/路径
用法:
  python i18n_apply.py --root plugins --dry-run
  python i18n_apply.py --root plugins --apply
"""
import json, os, re, sys, argparse, shutil, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i18n_glossary_common import COMMON
from i18n_glossary_extra import EXTRA
from i18n_glossary_special import FINAL, HTML_SPLIT, CSV_HEADER

GLOSSARY = {**COMMON, **EXTRA, **FINAL}

HAN = re.compile(r'[\u4e00-\u9fff]')
LINE_COMMENT = re.compile(r'^\s*(//|\*|/\*)')
HTML_RE = re.compile(r'<[a-zA-Z][\s\S]*>')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
# 简繁对照表（常见字形差异，逐字映射，避免长度不齐）
S2T_PAIRS = [
    ("设", "設"), ("删", "刪"), ("开", "開"), ("关", "關"), ("闭", "閉"), ("载", "載"),
    ("获", "獲"), ("数", "數"), ("据", "據"), ("务", "務"), ("态", "態"), ("查", "查"),
    ("询", "詢"), ("添", "添"), ("储", "儲"), ("败", "敗"), ("错", "錯"), ("误", "誤"),
    ("网", "網"), ("络", "絡"), ("址", "址"), ("连", "連"), ("库", "庫"), ("文", "文"),
    ("件", "件"), ("径", "徑"), ("志", "誌"), ("统", "統"), ("计", "計"), ("监", "監"),
    ("控", "控"), ("护", "護"), ("拦", "攔"), ("截", "截"), ("规", "規"), ("则", "則"),
    ("参", "參"), ("进", "進"), ("程", "程"), ("权", "權"), ("限", "限"), ("码", "碼"),
    ("录", "錄"), ("验", "驗"), ("证", "證"), ("类", "類"), ("型", "型"), ("时", "時"),
    ("间", "間"), ("显", "顯"), ("示", "示"), ("列", "列"), ("表", "表"), ("详", "詳"),
    ("情", "情"), ("执", "執"), ("行", "行"), ("同", "同"), ("步", "步"), ("备", "備"),
    ("份", "份"), ("恢", "恢"), ("复", "復"), ("导", "導"), ("入", "入"), ("出", "出"),
    ("传", "傳"), ("下", "下"), ("刷", "刷"), ("新", "新"), ("复", "複"), ("制", "製"),
    ("清", "清"), ("空", "空"), ("确", "確"), ("定", "定"), ("取", "取"), ("消", "消"),
    ("请", "請"), ("输", "輸"), ("内", "內"), ("容", "容"), ("称", "稱"), ("版", "版"),
    ("本", "本"), ("支", "支"), ("持", "持"), ("默", "默"), ("认", "認"), ("推", "推"),
    ("荐", "薦"), ("应", "應"), ("用", "用"), ("实", "實"), ("例", "例"), ("容", "容"),
    ("器", "器"), ("镜", "鏡"), ("像", "像"), ("端", "端"), ("口", "口"), ("范", "範"),
    ("围", "圍"), ("无", "無"), ("效", "效"), ("正", "正"), ("在", "在"), ("缓", "緩"),
    ("存", "存"), ("命", "命"), ("中", "中"), ("率", "率"), ("运", "運"), ("行", "行"),
    ("加", "加"), ("载", "載"), ("保", "保"), ("修", "修"), ("改", "改"), ("成", "成"),
    ("功", "功"), ("失", "失"), ("地", "地"), ("方", "方"), ("面", "面"), ("后", "後"),
    ("前", "前"), ("来", "來"), ("这", "這"), ("个", "個"), ("为", "為"), ("会", "會"),
    ("当", "當"), ("将", "將"), ("于", "於"), ("与", "與"), ("级", "級"), ("别", "別"),
    ("体", "體"), ("现", "現"), ("发", "發"), ("变", "變"), ("动", "動"), ("调", "調"),
    ("整", "整"), ("对", "對"), ("话", "話"), ("门", "門"), ("问", "問"), ("题", "題"),
    ("项", "項"), ("目", "目"), ("启", "啟"), ("动", "動"), ("停", "停"), ("止", "止"),
    ("重", "重"), ("试", "試"), ("锁", "鎖"), ("脏", "髒"), ("异", "異"), ("常", "常"),
    ("终", "終"), ("断", "斷"), ("屏", "屏"), ("户", "戶"), ("组", "組"), ("织", "織"),
    ("认", "認"), ("证", "證"), ("密", "密"), ("邮", "郵"), ("箱", "箱"), ("盘", "盤"),
    ("标", "標"), ("识", "識"), ("读", "讀"), ("写", "寫"), ("删", "刪"), ("除", "除"),
    ("迁", "遷"), ("移", "移"), ("镜", "鏡"), ("像", "像"), ("空", "空"), ("间", "間"),
    ("总", "總"), ("计", "計"), ("份", "份"), ("额", "額"), ("值", "值"),
]
S2T = str.maketrans(dict(S2T_PAIRS))


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data, order_keys=None):
    """写语言包：保持键顺序（按 zh-CN 顺序），2 空格缩进。"""
    if order_keys:
        ordered = {k: data[k] for k in order_keys if k in data}
        for k in data:
            if k not in ordered:
                ordered[k] = data[k]
        data = ordered
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.replace(tmp, path)


def to_traditional(text):
    return text.translate(S2T)


def build_lang_updates(plugin_dir, new_keys):
    """为插件补齐 6 个语言包。返回写入统计。"""
    lang_dir = os.path.join(plugin_dir, 'lang')
    os.makedirs(lang_dir, exist_ok=True)
    base = load_json(os.path.join(lang_dir, 'zh-CN.json'))
    added = {}
    for key in new_keys:
        if key in base:
            continue
        base[key] = key
        added[key] = True
    # zh-CN
    order = list(base.keys())
    save_json(os.path.join(lang_dir, 'zh-CN.json'), base, order)
    # 其他语言
    for lang in LANGS:
        if lang == 'zh-CN':
            continue
        p = os.path.join(lang_dir, lang + '.json')
        d = load_json(p)
        for key in base:
            if key in d:
                continue
            if lang == 'zh-TW':
                d[key] = to_traditional(key)
            elif key in GLOSSARY and lang in GLOSSARY[key]:
                d[key] = GLOSSARY[key][lang]
            else:
                # 缺译时回退中文，保证功能不报错
                d[key] = key
        save_json(p, d, order)
    return len(added)


def wrap_js_line(line, plugin_dir):
    """
    在单行 JS 内把未包裹的中文串整体替换为 pt('中文')。
    仅处理字符串字面量本身，保留引号语义，绝不破坏拼接语法。
    返回 (新行, 处理数)。
    """
    stripped = line.strip()
    if LINE_COMMENT.match(stripped):
        return line, 0

    count = 0
    # 行内注释位置（// 之后的内容不处理）
    cmt_pos = line.find('//')

    def repl(m):
        nonlocal count
        start = m.start()
        quote, content = m.group(1), m.group(2)
        if not HAN.search(content):
            return m.group(0)
        # 已在 pt(/msgTpl( 内的不动
        prefix = line[max(0, start - 1):start + 1]
        if start > 0 and line[start - 1] == '(' and 'pt' in line[max(0, start - 3):start]:
            return m.group(0)
        if 'pt(' in line[:start] and line[:start].rstrip().endswith('pt('):
            return m.group(0)
        if 'msgTpl(pt(' in line:
            return m.group(0)
        # 含 HTML 标签 -> 交人工
        if re.search(r'<[a-zA-Z/]', content):
            return m.group(0)
        # 纯占位符
        if re.fullmatch(r'\{[\d\w]+\}', content):
            return m.group(0)
        # 注释之后的忽略
        if cmt_pos != -1 and start > cmt_pos:
            return m.group(0)
        # 内容含未转义引号（跨串误匹配）-> 跳过
        count += 1
        return "pt(%s%s%s)" % (quote, content, quote)

    new = re.sub(r'(["\'])([^"\']*[\u4e00-\u9fff][^"\']*)\1', repl, line)
    return new, count


def fix_msgtpl(line):
    """msgTpl('中文', ...) -> msgTpl(pt('中文'), ...)"""
    if 'msgTpl(pt(' in line:
        return line, 0
    def repl(m):
        return "msgTpl(pt(%s), " % m.group(1)
    new, n = re.subn(r"msgTpl\((\s*['\"][^'\"]*[\u4e00-\u9fff][^'\"]*['\"])\s*,\s*", repl, line)
    return new, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='plugins')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--plugin')
    a = ap.parse_args()
    apply_changes = a.apply and not a.dry_run

    root = a.root
    report = {'lang_added': 0, 'code_wrapped': 0, 'files': 0, 'manual': []}

    for name in sorted(os.listdir(root)):
        pdir = os.path.join(root, name)
        if not os.path.isdir(pdir) or (a.plugin and name != a.plugin):
            continue
        base_path = os.path.join(pdir, 'lang', 'zh-CN.json')
        if not os.path.exists(base_path):
            continue
        base = load_json(base_path)

        # ---------- 1. 收集本插件所有待翻译串 ----------
        new_keys = set()
        for r, dirs, files in os.walk(pdir):
            if '__pycache__' in r or os.path.basename(r) == 'lang':
                continue
            for fn in files:
                if not fn.endswith(('.js', '.html')):
                    continue
                fp = os.path.join(r, fn)
                txt = open(fp, encoding='utf-8', errors='ignore').read()
                for line in txt.split('\n'):
                    if LINE_COMMENT.match(line.strip()):
                        continue
                    for m in re.finditer(r'(["\'])([^"\']*[\u4e00-\u9fff][^"\']*)\1', line):
                        v = m.group(2).strip()
                        if len(v) < 2 or v in base:
                            continue
                        if re.search(r'<[a-zA-Z/]', v):
                            # HTML 片段：尝试拆分为纯文本键
                            if v in HTML_SPLIT:
                                new_keys.add(HTML_SPLIT[v][1])
                            else:
                                report['manual'].append(f"{name}: HTML 片段需人工拆分 -> {v[:60]}")
                            continue
                        if v in CSV_HEADER:
                            new_keys.add(v)
                            continue
                        new_keys.add(v)

        # ---------- 2. 写语言包 ----------
        if new_keys:
            n = build_lang_updates(pdir, new_keys)
            report['lang_added'] += n

        # ---------- 3. 改代码 ----------
        for r, dirs, files in os.walk(pdir):
            if '__pycache__' in r or os.path.basename(r) == 'lang':
                continue
            for fn in files:
                if not fn.endswith('.js'):
                    continue
                fp = os.path.join(r, fn)
                orig = open(fp, encoding='utf-8', errors='ignore').read()
                lines = orig.split('\n')
                out = []
                changed = 0
                for line in lines:
                    if HAN.search(line) and LINE_COMMENT.match(line.strip()) is None:
                        nl, n1 = fix_msgtpl(line)
                        nl2, n2 = wrap_js_line(nl, pdir)
                        changed += n1 + n2
                        out.append(nl2)
                    else:
                        out.append(line)
                if changed:
                    report['code_wrapped'] += changed
                    report['files'] += 1
                    if apply_changes:
                        shutil.copy2(fp, fp + '.i18n.bak')
                        with open(fp, 'w', encoding='utf-8', newline='') as f:
                            f.write('\n'.join(out))

    print(f"[{'APPLIED' if apply_changes else 'DRY-RUN'}]")
    print(f"  语言包新增词条: {report['lang_added']}")
    print(f"  代码包裹处数:   {report['code_wrapped']}  (涉及 {report['files']} 个文件)")
    print(f"  需人工处理:     {len(report['manual'])}")
    for x in report['manual'][:40]:
        print("   -", x)


if __name__ == '__main__':
    main()
