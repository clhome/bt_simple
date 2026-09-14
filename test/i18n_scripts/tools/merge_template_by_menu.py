# coding: utf-8
"""
v2: 正确处理两种散文件形态
 - 形态A (section 散文件): template.site.json = {H1:..., H2:...}  对应 tmpl["site"] = {H1:..., H2:...}  -> 直接相等
 - 形态B (flat 单键散文件): template.day.json = "日"  对应 tmpl["day"] = "日"  -> 值相等，需包装为 {day: "日"} 归入菜单
 - 形态C (空): {} 或 {k:{}} -> 丢弃
产出: 每语言 9 个 template.<menu>.json + 1 个 template.json 兼容垫片
"""
import json, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web", "static", "language")

MENU_SECTIONS = {
    "index":    ["index", "dashboard", "menu", "auth", "login", "close", "admin", "task"],
    "site":     ["site", "database", "ftp"],
    "files":    ["files", "file", "upload"],
    "security": ["firewall", "ssh"],
    "crontab":  ["crontab"],
    "monitor":  ["control", "system"],
    "logs":     ["logs"],
    "soft":     ["soft", "plugins", "plugin", "jdk", "python_yf"],
    "setting":  ["config", "setting", "common", "public", "utils"],
}

MENU_FLAT = {
    "index": ["yufeng_panel_btsimple","quzhou_yufeng_technology_co","quzhou_yufeng_technology_yftec","proudly_presented_by","retrieving_panel_resource_usage","yufeng_panel_current_server","memory","failed_to_retrieve_resources","loading_instructions","all_rights_reserved_admin","public_auto_str_127","public_auto_str_128","public_auto_str_143"],
    "files": ["search_content","previous","next","replace_with","replace_current","replace_all","replace","all_1","sky","day"],
    "crontab": ["day_limit","day_none","day_stock","day_workday","day_holiday","no_limit","stock_day","work_day","holiday","date_limit","start_time","end_time","execute_time"],
}
SECTION_TO_MENU = {s:m for m,secs in MENU_SECTIONS.items() for s in secs}
FLAT_TO_MENU = {k:m for m,ks in MENU_FLAT.items() for k in ks}

def is_empty_dict(v):
    return isinstance(v, dict) and len(v)==0

def drop_empty(obj):
    if isinstance(obj, dict):
        out={}
        for k,v in obj.items():
            if is_empty_dict(v):
                continue
            if isinstance(v, dict):
                v2=drop_empty(v)
                if not v2:
                    continue
                out[k]=v2
            else:
                out[k]=v
        return out
    return obj

def do_lang(lang_dir):
    tmpl_path=os.path.join(lang_dir,"template.json")
    with open(tmpl_path,"r",encoding="utf-8") as f:
        tmpl=json.load(f)

    buckets={m:{} for m in MENU_SECTIONS}

    # 1) template.json 顶级分配
    unassigned={}
    for k,v in tmpl.items():
        if is_empty_dict(v):
            continue
        if isinstance(v,str) and k in FLAT_TO_MENU:
            buckets[FLAT_TO_MENU[k]][k]=v
        elif k in SECTION_TO_MENU:
            buckets[SECTION_TO_MENU[k]][k]=v
        elif isinstance(v,str) and k not in FLAT_TO_MENU:
            # 未归类的 flat str 兜底进 setting
            buckets["setting"][k]=v
        elif isinstance(v,dict) and k not in SECTION_TO_MENU:
            buckets["setting"][k]=v
        else:
            unassigned[k]=v
    for k,v in unassigned.items():
        buckets["setting"][k]=v

    # 2) 散文件: 仅校验并删除冗余/空，内容已在 tmpl 中无需二次合并（避免重复展开）
    removed=0
    for fn in sorted(os.listdir(lang_dir)):
        if not (fn.startswith("template.") and fn.endswith(".json")):
            continue
        if fn=="template.json":
            continue
        name=fn[len("template."):-len(".json")]
        # 9 主菜单文件在重建前若已存在（幂等二次跑）直接删
        if name in buckets:
            os.remove(os.path.join(lang_dir, fn))
            removed+=1
            continue
        path=os.path.join(lang_dir, fn)
        try:
            data=json.load(open(path,"r",encoding="utf-8"))
        except Exception:
            os.remove(path); removed+=1; continue
        # 包装形态B 的字符串为 dict 便于比较
        if isinstance(data, str):
            data_wrapped={name: data}
        else:
            data_wrapped=data
        # 空
        if not data_wrapped or all(is_empty_dict(v) for v in data_wrapped.values()):
            os.remove(path); removed+=1; continue
        # 冗余判定：section 散文件内容 == tmpl 对应 section
        if name in tmpl and isinstance(tmpl[name], dict) and isinstance(data, dict) and data==tmpl[name]:
            os.remove(path); removed+=1; continue
        if name in tmpl and isinstance(tmpl[name], str) and data==tmpl[name]:
            os.remove(path); removed+=1; continue
        if name in tmpl and isinstance(tmpl[name], str) and data_wrapped=={name: tmpl[name]}:
            os.remove(path); removed+=1; continue
        # 非冗余的散文件（理论上不应出现，因 template.json 已是全集） -> 并入对应菜单
        if name in SECTION_TO_MENU:
            sec=buckets[SECTION_TO_MENU[name]].setdefault(name,{})
            if isinstance(data, dict):
                for kk,vv in data.items():
                    if is_empty_dict(vv): continue
                    sec.setdefault(kk, vv)
            os.remove(path); removed+=1
        elif name in FLAT_TO_MENU:
            buckets[FLAT_TO_MENU[name]].setdefault(name, data if isinstance(data,str) else data.get(name, data))
            os.remove(path); removed+=1
        else:
            # 未知 -> setting
            if isinstance(data, dict):
                for kk,vv in data.items():
                    if is_empty_dict(vv): continue
                    buckets["setting"].setdefault(kk, vv)
            elif isinstance(data, str):
                buckets["setting"].setdefault(name, data)
            os.remove(path); removed+=1

    # 3) 写 9 主菜单文件
    for menu, data in buckets.items():
        clean=drop_empty(data)
        out=os.path.join(lang_dir, f"template.{menu}.json")
        json.dump(clean, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

    # 4) 重建兼容垫片 template.json
    merged={}
    for menu in MENU_SECTIONS:
        merged.update(json.load(open(os.path.join(lang_dir, f"template.{menu}.json"),"r",encoding="utf-8")))
    json.dump(merged, open(tmpl_path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    return removed, buckets, merged

def main():
    root=os.path.abspath(ROOT)
    for lang in sorted(os.listdir(root)):
        lang_dir=os.path.join(root, lang)
        if not os.path.isdir(lang_dir): continue
        removed, buckets, merged = do_lang(lang_dir)
        files=sorted([f for f in os.listdir(lang_dir) if f.startswith("template.")])
        sizes={f: os.path.getsize(os.path.join(lang_dir,f))//1024 for f in files}
        print(f"[{lang}] removed={removed} files={len(files)} merged_keys={len(merged)}")
        for f,kb in sizes.items():
            print(f"  {f:30} {kb:4}KB")
if __name__=="__main__":
    main()
