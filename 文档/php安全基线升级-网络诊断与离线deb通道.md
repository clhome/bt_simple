# PHP 升级到安全基线：失败诊断与离线 deb 通道

> 适用范围：`plugins/php`（编译版）、`plugins/php-apt`（sury/发行版）、`plugins/php-yum`（Remi）
> 的「一键升级到安全基线」。基线表本身见 `web/core/php_sec_baseline.py`，
> 组件维护期口径见 [组件生命周期与安全响应政策.md](./组件生命周期与安全响应政策.md)。
>
> 状态：生效中。实现位置：`web/core/net_probe.py`、`web/core/php_deb_bundle.py`；
> 插件侧是 php-apt 内的 `upgradeToBaseline` 与 `_offlineUpgrade` 两个函数；
> 守卫 `testsuite/test_php_baseline_offline_and_net.py`（34 条）。

---

## 1. 现场：一条「改一天也改不好」的报错（2026-10-26，真机 172.17.60.248）

点「PHP8.4 升级到安全基线 8.4.27」，任务日志：

```
错误:1 https://mirror.sjtu.edu.cn/sury/php bookworm InRelease
  Certificate verification failed: The certificate is NOT trusted. The certificate
  issuer is unknown. The name in the certificate does not match the expected.
  Could not handshake: Error in the certificate verification. [IP: 111.186.58.212 443]
...
W: 部分索引文件下载失败。如果忽略它们，那将转而使用旧的索引文件。
升级了 0 个软件包，新安装了 0 个软件包，要卸载 0 个软件包，有 182 个软件包未被升级。

{"status": false, "msg": "升级失败: 升级后版本 8.4.25 仍低于基线 8.4.27，按失败处理
（apt 退出码 0），自动回退成功；apt 报告 0 upgraded / 0 newly installed
（源里没有比 8.4.25 更新的包），请检查 /etc/apt/sources.list 与 sury 源，
并确认 apt-get update 成功；手工回退请执行: apt-get install -y --allow-downgrades
php8.4-fpm=8.4.25-... php8.4-cli=8.4.25-... php8.4-common=8.4.25-..."}
```

三个真问题：

1. **诊断错位**：源配置完全正常。实测该机 `curl http://mirrors.tuna.tsinghua.edu.cn/`
   → `HTTP 302` + `Server: DrcomServer1.2` + `Location: http://172.17.1.121/1.htm`，
   `https://` 被换成网关自签证书（`CN=demotest.doctorcom.com`）。
   **本机外网被上网认证网关（Dr.COM）劫持**，报文却让用户「检查 sources.list 与 sury 源」。
2. **假回退**：一个包都没升（`before_pkg == after_pkg`）时回退是空操作，报文却写
   「自动回退成功」，还附一条「把当前版本再装一遍」的回退命令。
3. **没有出路**：编译版早有离线源码通道（`data/php_src/`），apt 渠道一条离线通道都没有，
   于是「内网机器永远升不动」。

另有一条容易踩的事实：**所有源都因证书失败时 `apt-get update` 仍以 0 退出**
（面板记录的 `refresh_rc` 就是 0），所以「只看退出码」永远不会触发诊断。

---

## 2. 现在怎么判、怎么修

### 2.1 诊断（`web/core/net_probe.py`）

升级前刷新索引失败（或输出里出现网关/证书指纹）时，面板会：

1. 从报错原文取包源 URL（取不到就读 `sources.list` / `.list` / `.sources` / `.repo`）；
2. 探一次明文 HTTP（**不跟随 302**、只走 IPv4）拿网关指纹；
3. 探一次严格校验的 TLS 拿证书结论；
4. 汇总成一句话 + 处置办法写进任务日志（`print` → 任务日志；同时写插件日志）。

判定类型：`captive_portal`（认证网关）、`tls_intercept`（中间人证书）、`dns`、`timeout`、
`refused`、`http_error`、`unknown`。前三类 + `timeout` 视为 `blocked`（换源没用）。

为什么只走 IPv4：镜像站普遍双栈，而内网机器常常没有 IPv6 出口 ——
`socket.create_connection` 的首个 IPv6 尝试就要吃掉整个探测超时（现场实测出现过
「手动 curl 能拿到 302，面板探测却什么都探不到」）。

诊断**永不抛异常**、**不 import `http.client` 于模块顶层**：本仓 `web/utils/email.py`
与标准库 `email` 同名，任何把 `web/utils` 放进 `sys.path` 的进程里，顶层
`import http.client` 会连锁 ImportError 把插件启动搞崩。

### 2.2 不再给假安心（`upgradeToBaseline`）

- 判据改为**语言无关**：`before_pkg == after_pkg` 即「本次未做任何改动」；
  正则只用于措辞（「明确报告无可用更新」/「没有升级任何包」）。
- `no_op` 时**不执行回退**、不给回退命令（回退是空操作，报「回退成功」就是骗人）。
- 报文里的处置来自诊断（含「浏览器打开 http://172.17.1.121/… 完成认证」），
  不再让用户去翻 sources.list。

### 2.3 离线 deb 通道（`web/core/php_deb_bundle.py`）

```
data/php_deb/<分支>/*.deb      ← 推荐：分支隔离（84 表示 8.4）
data/php_deb/*.deb            ← 平铺也认（同名文件以分支子目录优先）
```

面板把这些包现场做成一个**本地 apt 仓库**（自生成 `Packages` + `Packages.gz` + `Release`，
不依赖 `dpkg-dev`），并让 apt 只看这个仓库（覆盖 `sourcelist/sourceparts/lists/cache`）。

为什么不直接 `dpkg -i`：sury 的扩展包全部钉死 `php8.4-common (= 精确版本)`，
少一个包就会把系统解包到一半再失败（PHP 直接起不来）。所以流程是：

1. **预检**（不装任何东西）：核心包齐不齐、版本是否达基线、包内锚定依赖是否自洽、
   **已装但包外**的扩展包是否因 `=(旧版本)` 需要一起升；
   不通过就明确列出缺哪个包，一个文件都不动；
2. `apt-get update`（只用本地仓库）→ `apt-get -s install --only-upgrade`（**模拟**）；
   出现 `Remv`（卸载）或 `E:`（无解）立即中止；
3. 真跑 `apt-get install -y --only-upgrade`（显式 `--force-confold`，保留本地 conffile）；
4. 回读 dpkg 版本串判定成败；成功才重启 FPM。

> **离线包必须齐**：把该分支**所有已安装** `php<分支>-*` 包的新版本都放进去。
> 只有 `fpm/cli/common` 会在预检阶段被拒，并告知缺哪个扩展包（例：
> 「已装的 php8.3-bcmath 锚定 php8.3-common (= 8.3.33…)，离线包里是 8.3.36… ⇒
> 还需要 php8.3-bcmath 8.3.36… 的 .deb」）。
>
> 获取方式（有外网的机器上下载，再传到目标机的该目录）：
> `https://mirror.sjtu.edu.cn/sury/php/pool/main/p/php<版本>/...deb`，
> 或 `apt-get --print-uris --only-upgrade install php<分支>-{fpm,cli,common}` 拿到完整清单。

### 2.4 yum / Remi 渠道（`plugins/php-yum`）

同一套诊断口径（`yum makecache` 失败即诊断并写进任务日志），不再把
「网关劫持/无外网」说成「Remi 源配置错」；`no_op` 同样如实报
「本次未做任何改动」。Remi 仍只给人工回退命令（`yum downgrade` 在模块流下不可靠）。
离线 rpm 通道本轮**不做**（本地 rpm 仓库要 `createrepo`，且 Remi 的 `php*-php-*`
命名与 apt 不同，需要单独设计预检）；无外网的 RHEL 机器请改用编译版
（`data/php_src/` 离线源码通道）。

---

## 3. 真机验证记录（2026-10-26，172.17.60.248）

| 场景 | 结果 |
| --- | --- |
| 诊断（真实网络） | `captive_portal`：`HTTP 302 → http://172.17.1.121/1.htm…，Server: DrcomServer1.2，HTTPS 证书校验失败：self-signed certificate`，耗时 0.07s |
| apt 刷新失败时的任务日志 | 打印诊断 + 处置（「先完成上网认证」/「把 .deb 放进 data/php_deb/84/」），不再指向 sources.list |
| PHP 8.4（apt, 离线包齐） | 8.4.25 → **8.4.27**，15 个包，`php8.4-fpm` active |
| PHP 8.3（apt，第一次包不齐） | 预检拒绝并点名缺 `php8.3-bcmath`，系统**零改动**；补包后 8.3.33 → **8.3.36** |
| 同版本包再跑一次 | 模拟阶段即判「无需升级」，不动系统 |
| 已达标再点升级 | 直接返回「已达标（8.3.36 ≥ 基线 8.3.36），无需升级」 |

> 这台机器的外网仍被网关拦截（未认证），面板与 PHP 均正常。
> 若要让 apt **在线**升级，需先在该机完成上网认证，或把面板源指向内网镜像。
