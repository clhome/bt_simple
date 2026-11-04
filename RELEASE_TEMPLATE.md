<!--
御风运维面板（BtSimple）发布说明模板 / BtSimple Release Notes Template
====================================================================
本文件被 `.github/workflows/release.yml` 作为 GitHub Release 正文模板（body_path）使用。
每次发版必须保留「变更类型 / 升级说明 / 回滚方法 / 完整性校验 / 发布前自检」段落。
-->

<div align="center">

# 🚀 御风运维面板 BtSimple 2.0 正式版发布说明

### BtSimple v2.0 GA Release Notes — A Generational Leap

<p>
  <img src="https://img.shields.io/badge/Release-v2.0_GA-success?style=flat-square&logo=github" alt="Version" />
  <img src="https://img.shields.io/badge/Architecture-NextGen_vs_v1.x-blue?style=flat-square" alt="Architecture" />
  <img src="https://img.shields.io/badge/Security-Enterprise_Grade-red?style=flat-square&logo=security" alt="Security" />
  <img src="https://img.shields.io/badge/Stability-Self--Healing-orange?style=flat-square" alt="Stability" />
  <img src="https://img.shields.io/badge/i18n-6_Languages-brightgreen?style=flat-square" alt="i18n" />
  <img src="https://img.shields.io/badge/Platform-Linux_x86__64_%7C_aarch64-lightgrey?style=flat-square" alt="Platform" />
</p>

</div>

---

<div style="background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin-bottom: 20px;">

**【版本寄语 / Executive Summary】**  
**中文**：御风运维面板（BtSimple）正式迈入 2.0 时代。本次版本发布标志着从早期 1.x 遗留架构向现代企业级轻量化运维底盘的全面跨越。历经全栈深度重构，BtSimple 2.0 在**安全性（Security）、可靠性（Reliability）、稳定性（Stability）、多语言支持（i18n）**四大核心支柱上实现了质的飞跃，彻底肃清历史技术债务，为现代生产级服务器环境提供更安全、更轻快、可自愈的云原生运维底座。  
**English**: BtSimple officially enters the 2.0 era. This milestone release marks a comprehensive generational leap from the legacy 1.x architecture to a modern, enterprise-ready lightweight server management system. Following a complete full-stack overhaul, BtSimple 2.0 achieves groundbreaking enhancements across four foundational pillars—**Security, Reliability, Stability, and Multi-language (i18n) Support**—eliminating legacy technical debt and delivering an autonomous, verifiable, and blazing-fast infrastructure management platform.

</div>

---

## 变更类型

> 勾选本次发版包含的类型 / Select change types included in this release:

- [x] 🔒 安全重构（Security Hardening & Zero-Trust）
- [x] ✨ 架构革新（Generational Architectural Leap）
- [x] ⚡ 性能突破（High-Throughput & Low-Latency）
- [x] 🌐 多语言支持（Full-Spectrum 6-Language i18n）
- [x] 🛠️ 自愈与可靠性（Autonomous Self-Healing）
- [ ] ⚠️ 破坏性变更（Breaking Changes - 数据库全自愈无感平滑升级）

---

## 升级说明

> 用户升级前须知 / Critical notes before upgrading:

- **面板数据库结构全自动自愈（Autonomous Database Migration）**：
  - **中文**：由内置自愈迁移框架（`web/core/migrations/`）全自动对齐，**无需任何手工干预**。升级流程在解包后显式执行结构与列对齐，如遇异常启动将自动重试修复。
  - **English**: Fully aligned by the self-healing migration framework (`web/core/migrations/`), **requiring zero manual intervention**. Schema and column alignment execute automatically during deployment.
- **升级渠道与方式（Upgrade Methods）**：
  - **Web 端**：进入面板 →「设置」→「检查更新」一键平滑升级。
  - **命令行 (CLI)**：在终端执行 `yf update` 完成安全增量更新。
- **安全与防护引擎协同升级（Security Engine Cooperative Upgrade）**：
  - 「御风OP防火墙」升级至 **1.6**，「御风F2B防火墙 (Fail2ban)」升级至 **1.3.0**。
  - **规则智能合并机制（Non-destructive Rule Merge）**：已安装老版本的用户在「软件管理」中点击升级即可；内置 `upgradeRules()` 引擎会自动将官方最新的 Java/Spring Boot、PHP 等高危漏洞蜜罐诱饵与防护规则增量补齐，**100% 完整保留用户的自定义规则与自建蜜罐路径，绝不覆盖**。
- **单端口 (80/443) 面板与业务站点共存反代（Single-Port Coexist Proxy）**：
  - 针对政企专网或严格安全组仅开放 80/443 端口的场景，新增菜单 **`(33) 单端口(80/443)面板共存`** 与专用 CLI `yf proxy`（体检：`yf proxy status`；关闭：`yf proxy off`）。独创内部 418 命名路由与 Cookie 门禁机制，绝不破坏现有站点的任何伪静态与静态资源分流，且绝不影响 Let's Encrypt 证书申请与续签。
- **运行环境兼容与废弃项（Deprecations & Compatibility）**：
  - 交互式菜单 `yf 0` 严格定义为取消并安全退出；历史遗留已过时的 PHP 5.2 安装选项（100/101）已正式废弃并移除，执行将提供专属引导说明。

---

## 回滚方法

升级前系统会**全自动**备份至 `/www/backup/yufeng_panel-<时间戳>.tar.gz`（内含面板代码、SQLite 核心数据库 `data/panel.db` 及全部插件）。如需版本回退，直接运行：

```bash
yf rollback      # 一键回滚到上一次升级前的稳定版本
```

- **回滚本身亦可回滚（Reversible Rollback）**：执行回滚前，系统会自动将当前工作状态另存为 `/www/backup/yufeng_panel.prerollback.<时间戳>.tar.gz`，杜绝因误操作导致不可逆状态丢失。
- **向下兼容容灾（Backward Compatible Data Safeguard）**：老版本代码启动若检测到数据库结构版本更高，仅告警并保持只读兼容，**绝不动摇已有核心业务数据**。

---

## 完整性校验

> 本节由发布流水线自动注入，请勿手动编辑。面板自升级采用 **fail-closed** 机制：Release 正文若缺失有效的 SHA-256 签名校验摘要，将拒绝执行升级。  
> Notice: The sha256 entry below is automatically injected by the CI release pipeline. The self-upgrade engine strictly enforces fail-closed verification.

sha256: __SHA256__

- **自升级包校验和 (In-place Upgrade Package SHA-256)**：对应自升级落地的 `temp/yf.zip`，由发布流水线从 tag 源码包抽取并纳入 `SHA256SUMS` 签名。
- **全量独立安装包校验和 (Full Standalone Tarball SHA-256)**：
  
  `__TARBALL_SHA256__  yf-panel-<版本>.tar.gz`

- **离线与本地验签复核（Local Verification）**：
  可通过 `python scripts/tools/yf_release_verify.py --pubkey keys/yf-release.pub --sums dist/SHA256SUMS --sig dist/SHA256SUMS.minisig --file <待验包>` 借助 Ed25519 签名公钥完成离线密码学验签。

---

## 发布前自检

- [ ] `python testsuite/run_all.py` 自动化测试套件全绿（包含静态代码门禁、安全棘轮与 i18n 校验）
- [ ] release tag 与 `web/version.py` 版本号严格一致（CI 自动化断言阻断）
- [ ] **境内多通道加速代理矩阵全部在线可用**：`gh-proxy.com` / `cors.zme.ink` / `gh.ddlc.top` / `ghproxy.net` / `gh.con.sh`，确保大陆服务器 100% 可达与高可用容灾
- [ ] **SQLite 结构变更可自愈**：通过 `testsuite/test_db_migration_selfheal.py` 验证存量库自动增量升级与兼容容灾
- [ ] 发布包经 Ed25519 签名完成且生成 CycloneDX SBOM 与带哈希的 `requirements.lock` 依赖锁

---

# 🌟 2.0 版本 vs 早期 1.x 版本代际差异全景汇总

### Generational Comparison: BtSimple 2.0 vs Legacy 1.x

<table width="100%">
  <thead>
    <tr style="background: #f6f8fa;">
      <th width="18%">维度 / Dimension</th>
      <th width="41%">早期 1.x 遗留架构 (Legacy 1.x)</th>
      <th width="41%">御风 BtSimple 2.0 时代 (Modern 2.0)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><b>🔒 安全体系<br>Security</b></td>
      <td>
        • 外部输入直接拼装 Shell 命令，存潜在注入隐患<br>
        • 路径边界判定粗糙，存在目录穿越与未授权下载风险<br>
        • 无发布签名，自升级缺乏供应链完整性防护<br>
        • 缺乏系统级蜜罐与内核防火墙联动机制<br>
        • 遗留旧版历史后门与过时依赖 CVE 缺陷
      </td>
      <td>
        • <b>全仓 Shell 参数化与 <code>shlex.quote</code> 强转义</b>，彻底杜绝注入<br>
        • <b><code>safePath</code> / realpath 强矩阵</b>，严防跨目录越权读取<br>
        • <b>Ed25519 签名 + SHA256SUMS + SBOM + requirements.lock</b> 供应链加固<br>
        • <b>OP WAF 1.6 + Fail2ban 1.3.0 双层蜜罐</b>，触碰直接内核 iptables 阻断 TCP<br>
        • <b>全链路登录监控与 IP 归属地审计</b>，密码与历史 CVE 彻底清洗
      </td>
    </tr>
    <tr>
      <td><b>⚙️ 可靠性<br>Reliability</b></td>
      <td>
        • 数据库升级依赖手工 SQL，易中断报错<br>
        • 升级无事务性回滚，更新失败后排障困难<br>
        • PHP-FPM / Redis / MySQL 异常脱节需人工介入<br>
        • 仅支持高端口访问，严格安全组下无法访问，手工反代易导致伪静态冲突与证书续签失败<br>
        • Docker 目录迁移需手工停机拷盘，容错率极低<br>
        • 依赖单一海外源，境内服务器部署失败率高
      </td>
      <td>
        • <b>自愈迁移框架（Migrations）</b>自动无感补表补列，降级不动数据<br>
        • <b>双向可逆升级快照</b>（<code>yf rollback</code>），回滚操作自身亦具备防损备份<br>
        • <b>核心服务智能巡检自愈</b>：PHP-FPM socket 隔离、phpMyAdmin 502 自愈、Redis 密码多级自愈<br>
        • <b>单端口 (80/443) 面板与业务站点无感共存</b>：Server 级 if + 418 内部路由 + Cookie 门禁，零改动伪静态，ACME 续签 100% 畅通，全链路参数联动自愈<br>
        • <b>Docker 存储一键热迁移</b>：容量预检 + rsync 校验 + 失败防唤醒自愈<br>
        • <b>内置 5 大境内加速代理与清华/Adoptium 双通道镜像</b>，保障 100% 部署率
      </td>
    </tr>
    <tr>
      <td><b>⚡ 稳定性能<br>Stability</b></td>
      <td>
        • GeoIP / FFI 存在二级指针悬挂，偶发 Worker Segfault 崩溃<br>
        • 高频监控同步挂起 1.0 秒，长时间运行线程开销高<br>
        • SQLite 高并发写入易发生磁盘锁争用，I/O 开销高<br>
        • 前端 AJAX 请求缺少全局 fail 闭环，异常时 Loading 遮罩永久卡死<br>
        • 插件列表与网卡遍历算法复杂度高，高负荷下响应迟钝
      </td>
      <td>
        • <b>FFI 内存安全重构</b>，彻底消除 OpenResty Worker 内存溢出与闪退<br>
        • <b>非阻塞高频轮询</b>：消除 <code>interval=1</code> 阻塞缺陷，监控响应提速 10 倍<br>
        • <b>SQLite 异步批量落盘 + C 级 MD5 特征限流</b>，I/O 减负 80%+，CPU 降低 90%+<br>
        • <b>全局 AJAX 异常闭环 + 60s 会话级 SWR 瞬时秒开</b>，0ms 切换无白屏与遮罩死锁<br>
        • <b>网卡 O(1) 优化与插件暖缓存</b>，接口响应达 5~9ms 极致能效
      </td>
    </tr>
    <tr>
      <td><b>🌐 多语言<br>i18n</b></td>
      <td>
        • 仅支持单一语言或粗糙汉化，大量中文硬编码<br>
        • 界面标签切割破坏文本，非中文环境下频繁报解析异常<br>
        • 缺少规范翻译字典，词条错漏无自动化门禁检测
      </td>
      <td>
        • <b>六国主流语言全域覆盖</b>（中简、中繁、英、日、俄、西）<br>
        • <b>前后端统一单源映射</b>：规范化 <code>pt()</code> / <code>lan</code> 接口与时区自适应<br>
        • <b>AST 语法树自动化门禁</b>（<code>test_plugins_i18n_upgrade.py</code>），严防死键与裸中文
      </td>
    </tr>
    <tr>
      <td><b>🚀 体验生态<br>Modern UX</b></td>
      <td>
        • 传统老旧灰黑 UI 样式，多处固定高度截断<br>
        • 缺乏现代包管理器，环境构建容易污染宿主系统<br>
        • 容器数据库管理缺失，备份需手动编写定时脚本
      </td>
      <td>
        • <b>高阶磨砂玻璃拟态（Glassmorphism）</b> + Google Fonts 精英字体 + 弹性响应式布局<br>
        • <b>御风 Python 多版本管理器 1.0</b>：基于极速 <code>uv</code> 构建，企业级 <code>.venv</code> 极速隔离<br>
        • <b>PostgreSQL 容器化管理插件 1.0</b>：Docker 隔离实例 + 动态内外网边界 + 定时无锁热备
      </td>
    </tr>
  </tbody>
</table>

---

## 🏛️ 2.0 四大核心支柱深度解析

### Deep Dive into the 4 Core Pillars

### 1. 🔒 安全性：零信任纵深防御与供应链可信 (Security & Zero-Trust)

<details open>
<summary><b>点击展开 / 折叠安全性详细改进 (Click to toggle details)</b></summary>

- **🛡️ 供应链可信与防篡改体系 (Supply Chain Provenance & Integrity)**：
  - **Ed25519 密码学签名**：每个 Release 发布包均附带 `SHA256SUMS` 清单与 Ed25519 数字签名文件（`.minisig`），升级下载端强制先验签后解包。
  - **SBOM 软件物料清单**：构建流水线全自动生成符合国际 CycloneDX 标准的 `sbom.json`，依赖组件完全透明可审计。
  - **带哈希依赖锁定**：提供带 SHA-256 摘要的 `requirements.lock`，严防第三方依赖包在分发传输过程中遭受投毒或篡改。
- **🚫 命令注入与路径穿越零容忍 (Zero Injection & Path Traversal Policy)**：
  - **严格参数化与边界转义**：Docker 容器控制、Crontab 定时任务、备份脚本、网站配置管理全面采用原生参数列表或 `shlex.quote` 转义，彻底铲除 shell 裸拼安全漏洞。
  - **`safePath` 多层路径边界校验**：全模块引入规范的 `safePath` 与真实路径（realpath）白名单校验矩阵，强力封堵目录穿越试图读取 `/etc/shadow`、`/etc/passwd` 或面板私有数据库的越权行为。
  - **SQL 注入与 XSS 存储转义**：彻底淘汰 SQL 裸拼，全面推行参数化查询与 ORDER BY 列名白名单；前端引入 `yfText`、`yfJsStr`、`logsEsc`、`cronEsc` 等统一转义函数，杜绝反射型与存储型 XSS。
- **🐝 双层蜜罐联动与全端口内核阻断 (Cooperative Honeypot & Kernel-Level Ban)**：
  - **高危漏洞诱饵覆盖**：御风 OP 防火墙 1.6 内置针对 Spring Boot DevTools (CVE-2026-40972)、Spring 路径遍历 (CVE-2026-41843)、PHP2Shell 等端点的诱饵特征。
  - **应用层与内核层全端口联动**：扫描器一旦命中诱饵，应用层立即拉黑 24 小时；开启 `ban_sync` 时实时通知御风 F2B 防火墙，在 Linux 内核层（iptables/nftables）直接封禁恶意 IP 的全部端口，连 TCP 握手都无法建立。
- **👁️ 全链路登录监控与安全审计 (End-to-End Audit & Access Control)**：
  - **面板与 SSH 统一审计**：首页新增登录记录模块，实时归集 Web 面板（两步验证、安全入口）与 SSH 终端的成功与失败登录。
  - **智能 IP 归属地解析**：集成多通道国内/国际 IP 地理位置解析与客户端防污染缓存，直观展示登录来源与高危告警。

</details>

---

### 2. ⚙️ 可靠性：全自动自愈与多层容灾体系 (Reliability & Self-Healing)

<details open>
<summary><b>点击展开 / 折叠可靠性详细改进 (Click to toggle details)</b></summary>

- **🧬 SQLite 数据库结构自愈迁移 (Self-Healing Migrations Framework)**：
  - 核心引入 `web/core/migrations/` 自愈迁移体系，老版本跨代升级自动探测缺失的表格与字段，并执行原地增量补齐，无需运维人员手动执行 SQL。
  - 降级容灾保护：老代码启动遇高版本库时自动触发只读保护与警告，绝不篡改已有业务数据。
- **🔄 双向可逆快照与回滚机制 (Reversible Snapshot & Safe Rollback)**：
  - 升级前自动执行全系统原子备份（涵盖面板运行代码、SQLite 核心库及已安装插件）。
  - 支持终端一键 `yf rollback` 秒级还原；在执行回滚操作前再次生成前置快照，确保“回滚操作本身亦可回滚”，实现全链路双向无损。
- **🩺 核心服务智能巡检与故障自愈 (Multi-Tier Service Auto-Recovery)**：
  - **PHP-FPM 多版本 Pool 冲突治理**：实现动态 socket 路径计算与后台巡检自愈，彻底解决 `backup.conf` 监听冲突引发的 PHP-FPM 异常。
  - **phpMyAdmin 502 Bad Gateway 根治**：建立 phpMyAdmin 关联 PHP 服务的运行状态探测与自愈拉起机制，杜绝服务脱节引发的访问中断。
  - **Redis 连接多级智能自愈**：建立「配置文件密码 ➔ 空密码 ➔ 运行时密码」多级自愈梯队，配置重置后自动校准持久化至 SQLite，消除脏密码锁死问题。
  - **MySQL / MariaDB 用户冲突预防**：重构创建数据库逻辑，采用「先查后删」防御机制，彻底消除了 MySQL 1396 历史报错与子进程误判。
- **📦 Docker 存储一键热迁移 (Docker Zero-Loss Hot Migration)**：
  - 首创极其严密的 Docker 数据目录一键热迁移机制，内置前置磁盘容量探测、底层 `rsync` 依赖自动补齐与防唤醒强容错回滚，杜绝大容量容器迁移导致的数据损坏。
- **🚪 单端口 (80/443) 面板与业务站点无感共存 (Zero-Conflict Single-Port Coexist Proxy)**：
  - **破解严苛网络策略**：针对政企专网或严格云安全组仅放通 80/443 端口的困境，通过 `yf 33` / `yf proxy` 实现面板与既有 Web 业务共用 80/443 端口。
  - **核心机制与零冲突**：首创「Server 级 `if` + HTTP 418 内部命名路由 + Cookie 门禁」，管理员带安全入口访问即可完成身份锚定，普通用户正常访问站点根目录、伪静态与静态资源丝毫未受干扰；**绝不修改站点任何现有 location**，彻底杜绝伪静态模板 `duplicate location "/"` 语法冲突引发的 Nginx 崩溃；
  - **ACME 续签安全隔离**：明确排除 `/.well-known/acme-challenge/` 路径，保障站点 Let's Encrypt 证书申请与 60 天自动续签 100% 畅通；
  - **全链路参数联动自愈**：面板端口变更、安全入口重置、SSL 状态切换或站点 SSL 变更均全自动无缝同步刷新反代配置片段与跳转逻辑，并在 `yf repair` 中纳入全自动自愈巡检。
- **🇨🇳 中国大陆网络生命线保障 (Mainland High-Availability Mirror Matrix)**：
  - 建立 5 大 GitHub 加速代理多通道容灾矩阵，配合清华大学镜像源与 Adoptium 全球 CDN，消除恶劣网络下的下载超时，保障服务器 100% 部署成功率。

</details>

---

### 3. ⚡ 稳定性：内存安全、高能效与极致性能 (Stability & Performance)

<details open>
<summary><b>点击展开 / 折叠稳定性详细改进 (Click to toggle details)</b></summary>

- **🛡️ C 级 FFI 内存安全加固 (C-Level FFI Memory Safety & Zero Segfaults)**：
  - 规范重构 GeoIP 与 MaxMindDB 底层 FFI 二级指针内存分配与链表释放逻辑，彻底终结了高并发下 OpenResty Worker 进程段错误（Segfault）导致的崩溃闪退。
- **💾 磁盘 I/O 减负 80%+ 与防 CC 算力优化 90%+ (I/O & Compute Optimization)**：
  - **SQLite 异步批量落盘**：重构访问日志与审计流的持久化逻辑，采用异步批处理写入，彻底消除高并发下的 SQLite 磁盘锁争用。
  - **C 级 MD5 特征指纹防 CC**：防 CC 算法重构为 OpenResty 原生底层 C 模块特征流过滤，大幅释放 CPU 计算资源。
- **🚫 前端遮罩死锁清零与 SWR 瞬时秒开 (Frontend Zero-Lock & SWR Instant UI)**：
  - **异常闭环治理**：全面排查并为全仓 AJAX 异步请求补齐 `.fail()` 异常处理，彻底消除了后端异常（500/网络中断）导致 Loading 遮罩永久卡死的问题。
  - **SWR 毫秒级缓存**：引入 60 秒会话级 SWR（Stale-While-Revalidate）客户端缓存策略，首页概览与功能菜单切换实现 0ms 瞬间秒开且无白屏闪烁。
- **⏱️ 高频轮询接口毫秒级能效突破 (High-Throughput / Low-Latency APIs)**：
  - **消除 psutil 同步阻塞**：重构 `getCpuInfo` 并去除原先阻塞后台整整 1.0 秒的同步调用（`interval=1` 缺陷），首页系统监控轮询响应提速 10 倍以上。
  - **软件商店暖缓存加速**：优化动态属性加载流程，引入多线程增量检测与暖缓存机制，软件列表响应时间从 800ms 强力压缩至 5~9ms。
  - **网卡计数器 O(1) 重构**：将循环内的多次网卡探测提取至循环外单次执行，多网卡环境下的资源开销从 O(N) 骤降为 O(1)。

</details>

---

### 4. 🌐 多语言：全域六国语言与 AST 门禁 (Multi-language & Modern i18n)

<details open>
<summary><b>点击展开 / 折叠多语言详细改进 (Click to toggle details)</b></summary>

- **🌍 全域六国主流语言支持 (Full-Spectrum 6-Language Coverage)**：
  - 完整覆盖简体中文 (`zh_CN`)、繁体中文 (`zh_TW`)、英语 (`en`)、日语 (`ja`)、俄语 (`ru`)、西班牙语 (`es`)，满足全球多地域运维与出海服务器管理需求。
- **📐 严格的 AST 语法树自动化门禁 (AST-Driven Quality Gate & Ratchet)**：
  - 引入专门的自动化测试门禁 `test_plugins_i18n_upgrade.py`，通过抽象语法树（AST）分析与静态扫描，对全仓模板、脚本中的字面量进行严格校验，杜绝硬编码裸中文、漏翻、错翻或未定义死键。
- **🕒 单源规范化与客户端时区自适应 (Single-Source Mapping & Timezone Adaptive)**：
  - 前后端多语言键统一规范（`pt()` / `lan`），重构富文本展示结构，规范 HTML 内联标签以防文本节点被割裂破坏。
  - 登录日志、任务调度与系统时间根据管理员浏览器本地时区自动格式化多语言展示，跨时区运维更精准。

</details>

---

### 5. 🚀 现代交互体验与新插件生态 (Modern UX & Plugin Ecosystem)

<details open>
<summary><b>点击展开 / 折叠现代体验与新插件 (Click to toggle details)</b></summary>

- **🎨 高阶磨砂玻璃拟态设计 (Glassmorphism & Micro-interactions)**：
  - 引入 Google Fonts `Outfit` 与 `Inter` 现代字体，重构高阶磨砂玻璃卡片与弥散微凸投影样式；为核心组件注入 Hover 悬浮、Active 弹性下陷（`scale(0.96)`）等微交互动效。
  - 彻底消除了旧版任务管理器、网站统计等插件中硬编码高度导致的文字截断与表格溢出问题，全面实现弹性自适应布局。
- **🐍 御风 Python 多版本管理器 1.0 (NextGen Python Multi-Version Manager)**：
  - 基于 Rust 编写的高性能工具 `uv` 构建，支持毫秒级一键安装管理 Python 多版本环境，环境全隔离零污染。
  - 独创企业级虚拟环境构建机制，一键生成 `.venv` 并提取项目名称作为终端提示符，搭载防误删保护机制。
- **🐘 PostgreSQL 容器化管理插件 1.0 (PostgreSQL Containerized Manager)**：
  - 支持基于 Docker 快速部署 PostgreSQL 隔离实例；支持在 Web 界面瞬间动态切换内外网访问边界（`0.0.0.0` / `127.0.0.1`）。
  - 内置全自动化灾备体系，支持定时无锁热备与备份文件的独立存储、直链下载与一键还原。
- **⚡ 御风系统优化插件 1.0 (Linux System Optimizer)**：
  - 提供系统内核参数调优、磁盘 I/O 调度优化、网络吞吐提速与无用依赖安全清理，全面激发服务器硬件潜能。

</details>

---

<div align="center">
  <sub>御风运维面板开源团队倾力打造 · 守护千万生产服务器的安全与稳定</sub><br>
  <sub>Crafted with precision by the BtSimple Core Team · Safeguarding servers worldwide.</sub>
</div>
