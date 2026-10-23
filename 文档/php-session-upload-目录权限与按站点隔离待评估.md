# PHP session / upload 目录权限与「按站点隔离」待评估

> 状态：**第 1 部分（权限收紧）已交付**；**第 2 部分（按站点隔离）为「待评估」**，
> 判定为**产品决策级改动**，本轮**不硬改**，只留设计 / 风险 / 迁移说明。
>
> 一句话结论：现在共享 session/upload 目录是 **`1730` + `www:www`**（不再是 0777），
> 这解决了「任何本机用户都能读写别人 session」的问题；但**站点之间仍然互相可见**
> （同属 `www` 组），真正的按站点隔离需要动 `session.save_path` 的粒度，代价是
> **可能让现有用户的会话失效**，所以必须先决策再动手。

---

## 1. 现场（改之前长什么样）

面板把 PHP 的 session 与上传临时文件放在**每台机器上共享的两个目录**：

| 用途 | 路径 | 改前权限 |
| --- | --- | --- |
| session 存放 | `/www/server/php/tmp/session` | `0777` |
| 上传临时文件 | `/www/server/php/tmp/upload` | `0777` |

`0777` 意味着机器上**任何本地用户**（包括被入侵的低权限服务账号）都能：

- 读取站点 A 的 `sess_<id>` 文件 → 直接拿到别人的登录态（会话劫持）；
- 往里写 `sess_*` 文件 → 伪造会话；
- 删除/改名别人的 session 文件 → 让任意站点随机掉登录（拒绝服务）。

而 `session.save_path` 在三个渠道（`plugins/php/`、`plugins/php-apt/`、`plugins/php-yum/`）
里都是**每版本一个全局值**：同一个 PHP 版本下**所有站点共用一个目录**。

---

## 2. 已交付：权限收紧为 `1730` + `www:www`

### 2.1 权限位为什么是 `1730`

`1730` = `sticky(1)` + `owner rwx(7)` + `group -wx(3)` + `others ---(0)`：

- `others = 0`：非 `www` 组的用户连目录都进不去 → 堵掉上面那三类攻击的第一入口；
- `group = wx`（有写/进入、无读）：同组（`www`）进程仍能创建自己的 `sess_*` 文件、
  能按名字打开自己知道 id 的会话，但**列不出目录内容**——「读不到别人的 session id」
  是这里的关键；
- `sticky = 1`：即便同组，也只能删除/改名**自己创建**的文件（等价 `/tmp` 的语义），
  防止某个站点进程删掉别的站点的会话；
- `owner = www`：面板自身（以 `www` 跑）需要能清理过期 session，所以属主保留写权限。

### 2.2 幂等 + 存量修复（这条最容易做错）

只在新装时 `chmod` 是没用的：现场绝大多数机器是旧版本装出来的，目录**早就存在且是 0777**。
因此校准函数 `_hardenSharedPhpDirs()` 对**已存在的目录同样执行** `chown -R` + `chmod`：

1. 目录不存在 → 创建（失败则如实报错，不静默）；
2. 属主：`chown -R www:www <session> <upload>`（递归顺带修好存量 session 文件属主）；
3. 权限：`chmod 1730 <session> <upload>`（**无论新旧都覆盖写**）；
4. 成功与失败都写进返回的 `logs`（`session/upload 目录权限已校正为 1730` / 明确失败原因），
   不静默、不假成功。

两步都走 **argv 列表 + `shell=False`** 的 `execShellRc`，并**判真实退出码**；
`chmod 777` 在本插件里已清零。该路径挂在**两个入口**上：`initReplace()`（安装/重建配置）
与 `upgradeSelfHealing()`（升级自愈），避免「装好是 1730、重装一次又变回 777」。

**实现位置**：`plugins/php/index.py`（`SHARED_PHP_DIR_MODE` / `SHARED_PHP_DIR_MODE_BITS` /
`_chownSharedPhpDirs()` / `_chmodSharedPhpDirs()` / `_hardenSharedPhpDirs()`，
两个调用入口 `initReplace()` 与 `upgradeSelfHealing()`）。
**门禁用例**：`testsuite/test_php_session_dir_perm.py`（含「先造 0o777 → 校准后回读必须 0o1730」
的存量修复证明；Windows 上回读断言自动 skip 并改用静态断言）。

---

## 3. 待评估：按站点隔离（`session.save_path` 粒度）

### 3.1 为什么 `1730` 还不够

`1730` 挡住的是「机器上的**非 www** 用户」，挡不住「**同一个 www 用户下的另一个站点**」：

- 所有站点都由同一个 `www` 账号的 php-fpm pool 执行（现状是每版本一个 pool，
  `user = www` / `group = www`）；
- 同一个 pool 里的进程彼此是**同一个 UID**，`1730` 的组与 sticky 语义对它们不设防；
- 于是站点 B 的 PHP 代码仍然可以按已知 id 打开站点 A 的 `sess_<id>` ——
  只要它能猜/偷到 id（例如通过应用层缺陷），隔离就不成立。

真正的隔离只有两条路：**每站点独立 UID**（每站点独立 `pool`）或
**每站点独立 `session.save_path`**（站点级 php.ini 覆盖）。两条都会改粒度。

### 3.2 方案 A：每站点独立 php-fpm pool + 独立 UID（隔离最强）

- 每站点生成一个 `pool` 段（`pool` 名带站点名），`user` / `group` 为该站点专属系统账号；
- 每站点的 `session.save_path` / `upload_tmp_dir` 指向该站点专属目录（`1730` 同样适用，
  但此时「同 UID」问题已消失，属主就是该站点自己）；
- 站点目录属主 / `open_basedir` 同步收窄到该站点根。

代价与风险：

- **`pool` 数量随站点线性增长**：每个 `pool` 在 `pm = dynamic` 下有独立的
  `pm.max_children` 与常驻 `pm.start_servers` 进程（现模板 `start_servers = 5`），
  **内存占用按站点数叠加**，小内存 VPS 上可能起不来 —— 需要按站点数动态压 `pm.max_children`
  与 `pm.start_servers`（可考虑 `pm = ondemand`）；
- 每站点一个系统账号/组 → 账号数量膨胀，卸载站点时必须清理（漏清就是残留账号）；
- 站点之间不再共享 `www` 组的语义，任何「按组授权」的老逻辑都要复核；
- 站点目录属主需要改成站点专属账号（否则站点代码自己改不了自己的目录），
  备份 / 迁移工具要能带上站点账号 → 属主映射表。

### 3.3 方案 B：站点级 `session.save_path` 覆盖（隔离中等、改动小）

- 站点级 php.ini（或 vhost 的 `fastcgi_param` / `.user.ini`）把
  `session.save_path` 指到 `/www/server/php/tmp/session/<站点名>`（`1730` + `www:www`）；
- 不改 `pool` / UID，内存与账号数量不变。

代价与风险：

- **必须落在 pool 级 `php_admin_value`，不能靠应用自己改**：`session.save_path` 虽是
  `PHP_INI_ALL`（应用里 `ini_set()` 也能改），但那是"站点自愿"；面板要能强制并保证
  "站点改不回去"，唯一落点是 php-fpm pool 的 `php_admin_value[session.save_path]`
  （优先级最高，`ini_set()` 与 `.user.ini` 都覆盖不了）；
- **而 `php_admin_value` 是按 `pool` 生效的**：现状是「每版本一个 `pool`（`pool` 名 `www`）」，
  同一版本的所有站点共用一个 `pool` → 根本无法按站点区分。所以方案 B 实际也需要
  **每站点一个 `pool`**（只是 `user` / `group` 仍为 `www`，不换 UID）；
- 好消息：多 `pool` 的骨架已经在（`getFpmConfFile(version, pool)` /
  `phpFpmPoolReplace(version, pool)` 都是按 `pool` 参数化的，`socket` 也支持
  `/tmp/php-cgi-<ver>.<pool>.sock`），成本主要在**每个站点的 `pool` 编排与卸载清理**，
  而不是从零写；
- **同一个 `session.save_path` 语义变化会直接影响会话可见范围**：站点换目录后，
  **老会话文件留在旧目录，用户等于被强制踢下线（登出）** —— 这是本方案最大的用户体验代价，
  必须选低峰期并提前公告；
- `.user.ini` 由站点目录属主可写 → 站点自己可以改回共享目录，等于隔离可被自己绕过；
  所以**不能**用 `.user.ini` 作为落点（这也回到上面"必须 `php_admin_value`"那条）；
- 磁盘布局变化 → 备份/清理脚本（现在按 `/www/server/php/tmp/session` 扫过期 `sess_*`）
  必须递归到子目录，否则子目录里的过期会话永远不清。

### 3.4 方案 C：维持现状（`1730` + 组隔离）+ 应用层加固

- 不改 `session.save_path`，改为要求/建议用户站点使用**独立的 session 名**
  （`session.name` 各不相同）与 `session.cookie_httponly`、`SameSite`；
- 面板侧提供「检测同版本站点共用 session 目录」的提示。

代价：隔离等级不提升，只是降低被猜中的概率。**不建议**作为长期方案。

### 3.5 判定：待评估（本轮不动）

理由：三种方案都会改动**用户可感知的行为**（登出、站点账号、内存占用、磁盘布局），
属于产品决策而不是纯技术修补；且方案 B/A 的迁移一旦做错就是**全站用户掉登录**。
因此本轮只交付「不做隔离也必须做的那一半」（`1730` + 属主），把粒度问题显式登记为
**待评估项**，等产品侧确认后再按第 4 节的迁移步骤实施。

---

## 4. 若决策为「做」：迁移步骤（预先写好，降低实施风险）

1. **准备**：选定方案（A 或 B），确认目标机 `ulimit -u` / 内存余量能容纳新增 `pool`；
2. **灰度**：只对 1 个非关键站点启用新口径，观察 48 小时（登录态、上传、清理任务）；
3. **公告**：明确「本次变更会让在线用户**重新登录（登出）一次**」，选低峰执行；
4. **落地**：写新的 `session.save_path` / `pool` 配置 → `reload` php-fpm（不强杀）；
5. **兼容**：旧共享目录保留一段时间（只读），确认无站点再写入后再清理；
6. **清理脚本**：过期 session 清理改为**递归**扫描新目录树，且只删 `sess_*`；
7. **回滚**：配置回退到「每版本一个全局 `session.save_path`」+ 重新 `reload`；
   旧的 `sess_*` 文件未被删除，回滚后用户可继续使用原会话（这也是第 5 步要保留旧目录的原因）；
8. **收尾**：更新本文档状态（待评估 → 已实施）与门禁（新增「站点目录粒度」断言）。

---

## 5. 相关代码位置

| 关注点 | 位置 |
| --- | --- |
| session / upload 目录常量与路径推导 | `plugins/php/index.py`（`getServerDir() + '/tmp/session'`、`'/tmp/upload'`） |
| 权限三件套（`1730` / `0o1730` / chown / chmod） | `plugins/php/index.py`（`SHARED_PHP_DIR_MODE*`、`_chownSharedPhpDirs`、`_chmodSharedPhpDirs`、`_hardenSharedPhpDirs`） |
| 两个校准入口 | `initReplace()`、`upgradeSelfHealing()` |
| php-fpm `pool` 模板（当前每版本一个 pool，`user = www`） | `plugins/php/index.py` 的 pool 生成段 |
| 过期 session 清理 | `plugins/php/index.py`（`session_tmp` + `find ... -name 'sess_*'`） |
| 门禁 | `testsuite/test_php_session_dir_perm.py`（正式）/ `testsuite/test_php_session_perm.py`（别名模块，只转发不断言） |
