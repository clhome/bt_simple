# fail2ban 与 op_waf 功能重合分析与联动方案

- 分析对象：`plugins/fail2ban`（御风F2B防火墙 v1.2.0）、`plugins/op_waf`（御风OP防火墙 v1.5）
- 分析日期：2026-09-21
- 结论：**两者存在真实功能重合（集中在 Web 防护面），但整体是纵深防御的两个不同层级——不建议整合，建议「边界划分 + 单向联动」**

---

## 一、结论速览

| 问题 | 结论 |
|---|---|
| 是否有功能重合？ | **有**，集中在「Web CC 防护 / 恶意扫描 / IP 黑名单 / 封禁历史 / 归属地查询」5 处 |
| 是否重复造轮子？ | **不是**。两者层级、范围、封禁手段、依赖完全不同，各自有对方做不到的能力 |
| 是否需要联动？ | **需要**，且收益明显（解决 op_waf 封禁易失、黑名单割裂、状态不一致） |
| 是否整合成一个插件？ | **不建议**。技术栈/依赖/故障域/生命周期均不可合并，且与产品定位冲突 |
| 推荐的折中 | 插件**保持独立**，在**面板编排层**做一个「安全中心」聚合入口 |

---

## 二、两者定位对比（均有代码证据）

| 维度 | fail2ban | op_waf |
|---|---|---|
| 防护层级 | **内核层 L3/L4** | **应用层 L7** |
| 检测时机 | 日志**事后**分析（轮询日志文件） | 请求期**实时**判定（`access_by_lua`） |
| 防护范围 | **全服务器**：SSH/FTP/MySQL/邮件/Redis + Web | **仅 Web 站点** |
| 封禁手段 | `fail2ban-client set <jail> banip` → **iptables/ipset** | `ngx.shared.waf_drop_ip` → nginx 返回 444 / 挑战页 |
| 封禁持久性 | **持久**（iptables 规则 + sqlite `bans` 表） | **易失**（nginx 共享内存，reload/restart 即清空） |
| 封禁力度 | 严格模式下 `banaction_allports` → **全端口阻断** | 仅阻断被 WAF 覆盖的 Web 请求 |
| 运行依赖 | 仅 OS 的 `fail2ban` 包 | **OpenResty + luajit + MaxMindDB**（需先装 openresty） |
| 规则能力 | `failregex` 单行正则 | 多维特征（URL/参数/Cookie/UA/SSRF/漏洞库）+ **信誉分系统** |
| 站点感知 | 无（仅按 `logpath` 通配） | 有（`site_cb` hook，站点增删改自动 reload） |
| 地区限制 | ❌ | ✅（`area_limit.json` + mmdb） |
| 蜜罐 / 爬虫 / CDN / 可信代理 | ❌ | ✅ |
| 归属地数据源 | `ip-api.com/batch`（**语言跟随面板**） | `ip-api.com/batch`（**硬编码 `lang=zh-CN`**） |

### 产品设计意图（已有明文）

`文档/御风面板说明书/说明书.md:801`：

> 通过 fail2ban **内核层 iptables 物理隔离机制**阻断 SSH 暴力破解；通过基于 Lua 引擎构建的 **op_waf 零侵入式网关防火墙**过滤 SQL 注入与 CC 攻击；……最终构筑了"**网络层 - 内核层 - 应用层**"的三维纵深防御基准。

即：**分层是官方设计**。但说明书只把 fail2ban 定位在「SSH 暴力破解（内核层）」，并未提及它的「网站防护」功能——说明 fail2ban 的 `global-cc` / `global-scan` 是**后期新增、且越界进入了 op_waf 的职责范围**。这正是重合的来源。

---

## 三、功能重合矩阵

| 能力 | fail2ban | op_waf | 判定 |
|---|---|---|---|
| SSH / FTP / MySQL / 邮件 / Redis 防护 | ✅ | ❌ | 互补 |
| SQL 注入 / XSS / 木马 / SSRF 规则 | ❌ | ✅ | 互补 |
| 地区限制 / 爬虫管理 / 蜜罐 / CDN / 可信代理 | ❌ | ✅ | 互补 |
| **Web CC 防护** | ✅ `global-cc` | ✅ `cc` + `retry` + 信誉分 | **重合** |
| **恶意扫描拦截** | ✅ `global-scan` | ✅ `scan` + `scan_black.json` | **重合** |
| **IP 黑名单** | ✅ `black_list.json` → iptables | ✅ `ip_black.json` → nginx | **重合（两套并存）** |
| **封禁列表 / 历史** | ✅ 防护历史 | ✅ 封锁历史 + 封禁地址 | **重合（两个入口）** |
| **IP 归属地查询** | ✅ | ✅ | **重合（同一数据源）** |
| 服务状态 / 全局开关 | ✅ 严格模式 | ✅ `setObjOpen` | 部分重合 |

---

## 四、重合带来的实际风险（有代码证据）

### 4.1 双重封禁 + 解封状态不一致 ⚠️ 最严重

op_waf 对 CC 与扫描命中统一返回 **444**（`waf/config.json`）：

```json
"cc":   { "status": 444, "limit": 120, "cycle": 60, "endtime": 300, "open": true },
"scan": { "status": 444, "open": true }
```

而 fail2ban 的 `global-scan` 过滤器**正好匹配 444**（`plugins/fail2ban/index.py:780-781`）：

```
failregex = ^<HOST> \-.*"(?:GET|POST|HEAD).*" (400|401|403|404|444|500|502|503)
```

**后果**：op_waf 在 Web 层拦下的攻击 IP，其 444 响应会写进站点访问日志 → fail2ban 二次捕获 → 在 **iptables 层全端口封禁**（严格模式 `banaction_allports`）。

- 好处：意外的纵深效果
- 坏处：这是**偶然级联而非设计**。用户在 op_waf 里点了"解封"，IP 却仍躺在 iptables 黑名单里 → 「为什么解封了还是访问不了」的困惑

### 4.2 两套黑名单各管一段，互不同步

| 添加位置 | 生效范围 | 另一侧是否知晓 |
|---|---|---|
| fail2ban「IP黑名单」 | 全端口（iptables） | ❌ 不知道 |
| op_waf「封禁地址」 | 仅 Web（nginx） | ❌ 不知道 |

用户必须**在两处各加一次**，且删除时同样要删两次，否则留下"幽灵封禁"。

### 4.3 两个封禁历史入口，统计口径必然打架

- fail2ban：sqlite `bans` 表（持久，含 `timeofban`/`bantime`）
- op_waf：nginx 共享内存 `ngx.shared.waf_drop_ip`（**易失**，含 `reputation_score:` / `404_warning:` 计数器）

同一攻击者会同时出现在两个列表，条数、时间、时长都对不上。

### 4.4 归属地显示不一致（同一数据源、不同语言策略）

两者都调 `ip-api.com/batch`，但：

- fail2ban：`IP_API_LANG_MAP` → **跟随面板语言**（zh-TW 回落 zh-CN）
- op_waf：`index.py:1755` **硬编码** `'http://ip-api.com/batch?lang=zh-CN'`

→ 英文/德文面板下，同一 IP 在 fail2ban 显示 `Berlin, Germany`，在 op_waf 显示中文地名。
（这本身也是 op_waf 的一个独立 i18n 缺陷。）

### 4.5 默认阈值叠加导致「误伤后果不对等」

| | 默认阈值 | 触发后果 |
|---|---|---|
| fail2ban `global-cc` | `maxretry=60` / `findtime=60` | **iptables 全端口封禁 86400s** |
| op_waf `cc` | `limit=120` / `cycle=60` | nginx 返回 444（仅 Web） |

两者同时开启时，任何超过 **60 请求/分钟**的合法客户端（CDN 回源、搜索引擎抓取、企业出口 NAT 后多人共用同一公网 IP）会被 **iptables 全端口封禁一天**——包括切断其 SSH。
op_waf 只会给它一个挑战页。**同一行为，两种严重程度，且更重的那个来自阈值更低的 fail2ban。**

---

## 五、为什么「不建议整合成一个插件」

| 理由 | 说明 |
|---|---|
| **技术栈不可合并** | Python + OS 守护进程 + iptables ↔ nginx Lua + luajit + 共享内存。物理上无法合成一个进程 |
| **依赖爆炸** | op_waf 需要 OpenResty/luajit/MaxMindDB；fail2ban 只需一个系统包。整合后「只想防 SSH 爆破」的用户被迫安装 OpenResty |
| **故障域扩大** | 现在 op_waf 的 Lua 报错不影响 iptables 防护；整合后 nginx 配置错误会连内核层防护一起失效 |
| **生命周期不同** | op_waf 依赖 `site_cb` hook（站点增删改联动），fail2ban 与站点完全无关。整合会让 fail2ban 被动依赖站点模块 |
| **升级/卸载耦合** | 一个插件升级失败会波及另一个；卸载任一都会留下半残状态 |
| **与产品定位冲突** | 说明书已把「内核层 / 应用层」分层作为核心卖点，整合等于自毁「三维纵深防御」叙事 |
| **职责边界清晰更利于排障** | 出问题时能快速定位是内核层还是应用层，合并后无法区分 |

> 如果产品上确实希望「一个入口」，正确做法是在**面板编排层**做聚合 UI（见 6.5），而不是把两个插件物理合并。

---

## 六、建议方案（按优先级）

### P0 — 边界划分（零风险，建议先做）

1. 明确分工并写进两者 UI 的功能介绍：
   - **op_waf** = Web 应用层防护（L7）：CC、扫描、注入、地区、爬虫、蜜罐
   - **fail2ban** = 系统服务 + 内核层封禁（L3/L4）：SSH/FTP/MySQL/邮件/Redis，以及**统一的全端口封禁执行**
2. 当**两者同时安装**时，在 fail2ban「网站防护」页给出醒目提示，或**默认不勾选** `global-cc` / `global-scan`，引导用户把 Web 层交给 op_waf
3. 可选：在 fail2ban 侧检测到 op_waf 已安装时，把「网站防护」页置灰并提示「已由御风OP防火墙接管」

### P1 — 单向联动：op_waf → fail2ban（收益最大）

- **动因**：op_waf 的封禁存在 nginx 共享内存里，reload/restart 即丢失；且只挡 Web 请求，攻击者换协议（如直连 SSH）仍可继续
- **方案**：op_waf 命中「信誉分扣满 / CC 超限 / 扫描规则」时，除返回 444 外，**回调面板接口**请求 fail2ban 下发 iptables 持久封禁
- **实现要点**：
  - fail2ban 暴露一个**仅允许本机调用**的内部接口（校验来源 IP + 共享令牌）
  - 支持带 `source` 标签（如 `from=op_waf`）与自定义封禁时长，便于在 fail2ban 侧区分来源与审计
  - 复用现有 `yf-manual` 永久封禁 jail 或新建 `op-waf` 联动 jail（`bantime` 由 op_waf 传入）
  - Lua 侧走 `ngx.location.capture` 调本机接口，避免阻塞主请求（或用 `ngx.timer.at` 异步）
- **收益**：一次封禁 = Web 层即时拦截 + 内核层持久阻断，且 nginx 重启后依然有效

### P1 — 黑名单双向同步

- 建议由**面板统一维护一份主黑名单**，两个插件各自从它渲染自己的格式，避免双写冲突：
  - → fail2ban：`black_list.json` + `yf-manual` jail
  - → op_waf：`waf/rule/ip_black.json` + reload
- 在任一侧增删 IP，另一侧自动跟随；删除时两边同时清除，杜绝"幽灵封禁"

### P2 — 统一封禁历史视图

- 面板级聚合：fail2ban sqlite `bans` + op_waf `/get_waf_drop_ip`，**标注来源**（内核层 / 应用层）
- **单点解封**：在聚合视图解封 → 同时下发到两侧（这是解决 4.1 困惑的关键）

### P2 — 统一归属地数据源与语言策略

- 抽成公共函数（如 `web/utils/ip_location.py`），两个插件共用，避免重复实现与缓存割裂
- 修正 op_waf 硬编码 `lang=zh-CN`，改为跟随面板语言（对齐 fail2ban 的 `IP_API_LANG_MAP`）

### 不建议做

- ❌ 合并成一个插件
- ❌ 让 fail2ban 依赖 OpenResty
- ❌ 让 op_waf 直接操作 iptables（会绕过 fail2ban 的封禁数据库，导致状态更加割裂；应通过 fail2ban 统一执行）

---

## 七、一句话总结

> fail2ban 是**内核层的封禁执行者**（持久、全端口、覆盖非 Web 服务），op_waf 是**应用层的实时拦截者**（精细、多维、覆盖 L7 攻击）。
> 两者的正确关系是**「op_waf 负责发现，fail2ban 负责持久封禁」**——即把 op_waf 作为 fail2ban 的高质量威胁情报来源，而不是各自维护一套封禁。
> **保持两个插件独立，通过单向联动 + 黑名单统一 + 历史聚合打通，而不是物理合并。**

---

## 八、落地实现与性能验收（已实施）

### 8.1 两侧唯一契约

联动**不引入任何 RPC / 端口 / 鉴权面**，两侧唯一的耦合点是一个纯文本文件：

| 项 | 值 |
|---|---|
| spool 绝对路径 | `<serverDir>/op_waf/logs/ban_spool.log` |
| 相对常量 | fail2ban `OP_WAF_SPOOL_REL` == op_waf `BAN_SPOOL_REL` == `logs/ban_spool.log` |
| 行格式 | `%Y-%m-%d %H:%M:%S op_waf[ban] WARNING Ban <IP> ttl=<秒> reason=<原因>` |
| jail 名 | `op-waf`（fail2ban 侧，`backend = polling`，`pollinterval = 2`） |
| 联动开关 | **spool 文件是否存在**（创建 = 开启，删除 = 关闭） |

由此得到一条很强的性质：**只安装其中一个插件时，对端的一切都不存在，联动在物理上不可能被触发**——约束 A 是靠结构保证的，而不是靠防御性代码兜出来的。

### 8.2 切断 444 意外级联（本次最关键的修复）

op_waf 对 CC / 扫描命中返回 **444**；而 fail2ban 原有的 `global-scan` failregex 会匹配 444。两者同时开启时，op_waf 的应用层拦截会被 fail2ban 二次捕获并**升级为 iptables 全端口 86400 秒封禁**，导致 op_waf 侧解封后 IP 仍访问不了。

新增的 `filter.d/op-waf.conf` **刻意只匹配 op_waf 主动写入的情报行**，failregex 中不含任何 HTTP 状态码：

```
failregex = ^.*op_waf\[ban\]\s+WARNING\s+Ban\s+<HOST>(?:\s+ttl=\d+)?(?:\s+reason=.*)?\s*$
```

已用真实样本回归验证：4xx/5xx 访问日志行（含 `444`）**全部不匹配**，情报行全部匹配。

### 8.3 性能：请求路径零同步阻塞

**op_waf 侧（Lua，请求路径）**

| 环节 | 开销 |
|---|---|
| 开关关闭时 | `push_ban_sync` 首行返回，**1 次 table 取值**，无 dict 操作 |
| 开关开启时 | 1 次 `dict:llen` + 1 次 `dict:rpush`，**仅在「真实封禁事件」触发**（非每请求） |
| 文件 IO | **完全不发生在请求路径**：全部由 `ngx.timer.every(2, ...)` 在 light thread 批量完成 |
| 队列保护 | 上限 5000 条，超出即丢弃并累加 `ban_sync_drop` 计数，共享内存不会被拖垮 |
| 队列隔离 | 封禁队列 `waf_ban_sync` 与日志队列分离，日志降级丢弃**不会**拖累封禁情报 |
| timer 归属 | 仅 `ngx.worker.id() == 0` 注册，多 worker 不会重复写同一文件；回调 `pcall` 包裹 |

**fail2ban 侧（Python，接收）**

| 环节 | 开销 |
|---|---|
| spool 探测 | 进程内 30s TTL 缓存，缓存命中时 **0 次 stat**（已断言） |
| 轮询读取 | `backend = polling` + `pollinterval = 2`，每 2 秒 1 次 `stat()`；情报写入频率极低（仅封禁事件） |
| jail 同步 | `sync_op_waf_jail` 幂等：jail.local 内容未变化时**不写盘、不 reload**（reload 会重建整个 filter 链，代价不低） |
| 未联动时 | 不产生任何跨插件子进程调用（已断言） |
| 状态查询 | `op_waf_link_status` 在配置就绪时为**纯只读**（已断言） |

### 8.4 验收结果

| 验收项 | 结果 |
|---|---|
| 联动专项测试 `test/test_f2b_op_waf_link.py` | **70 项全部通过**（对端缺失降级 / spool 白名单 / jail 生成与撤销 / 幂等性 / Lua 语法与性能结构 / 六语言一致性） |
| fail2ban 既有回归 | `test_fail2ban_plugin.py` 59 项、`test_fail2ban_stability.py` 6 项，全部通过 |
| op_waf 既有回归 | P0 安全 / P1 可靠性性能 / P2 优化 / spider，全部通过 |
| 全库语法 | `test_all_python_syntax.py`、`test_all_plugins_js_syntax.py`，全部通过 |
| 插件运行时 i18n | `test_plugin_runtime_i18n.py`：1314 条菜单项 100% 覆盖、0 未翻译 |
| 六语言键集 | fail2ban 172 键 × 6 语言、op_waf 720 键 × 6 语言，**键集完全一致，0 缺失 / 0 多余 / 0 空值 / 0 译文含 HTML** |
| zh-TW 简体残留 | 0 条可转换项（同形字除外） |
| 编码规范 | 全部改动文件 UTF-8 无 BOM、LF 行尾；各语言包缩进保持原状（fail2ban=4，op_waf=1） |

### 8.5 联动状态一览（用户视角）

- **只装 fail2ban**：行为与引入联动前 **100% 一致**，无任何新增文件、无新增 jail。
- **只装 op_waf**：行为不变；「全局配置」页的联动开关在未检测到 F2B 时**直接拒绝开启**并提示，不会产生无人消费的垃圾文件。
- **两者都装但未开联动**：op_waf 默认不再重复接管 Web 层（仅影响初始化默认值，已保存配置一律不动），用户可一键停用重复的 `global-cc` / `global-scan`。
- **两者都装且开启联动**：op_waf 应用层发现 → 内核层持久封禁；两侧 UI 解封均带「会同时解除内核层与应用层封禁」的明确提示，并在任一侧解封时自动同步对端（`silent` 参数打断双向递归）。

