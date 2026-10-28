# 任务：核对并修复《御风面板 bt_simple 问题报告与修改指引_2026-10-26》

## 任务口径
- 报告基线：`master@a3188297`；本次核对基线：**工作区 HEAD `1c600103a`**（比报告基线多 4 个提交）。
- 要求：① 逐条核对「问题是否真实存在」；② 真实存在的逐条修复；③ 每修完一条在本文档打勾。
- 判定规则：**代码可查**（读文件即证）+ **外部事实**（curl 实测 HTTP 状态）+ **本地真跑**
  （WSL Debian 里跑 bash/下载/安装脚本，能跑通的就真跑，不靠「看代码像是对的」）。
- 报告里错的/过期的部分单独记（见「核对结论」里的「报告错误」列），不照抄。

## 核对结论（先给结论，再逐条修）

| 编号 | 报告结论 | 核对结论 | 依据 |
|---|---|---|---|
| P1-1 | 安装器未固化 /www 权限 | **真实** | `scripts/install.sh:443-447`、`scripts/install_dev.sh:389-393` 只有 mkdir，全仓对 /www 无任何 chmod/chown（`grep chmod scripts/install*.sh` 零命中） |
| P1-2 | openresty 模块路径漂移必失败 | **真实，且比报告更严重** | 实测 `refs/heads/master.tar.gz` 返回 200，但包内顶层目录是 `ngx_cache_purge-main/`（`git ls-remote` 显示上游**已无 master 分支**）；`yf_nginx_addon_fetch` 只判 `$_name`（-master）→ 必判「解压后缺 config」→ 删掉重试 → 只能靠 git clone 兜底。另两个模块（nginx-http-concat、ngx_http_substitutions_filter_module）实测仍是 `-master/`，无漂移 |
| P1-3 | docker 假成功（4 重机制） | **真实** | `plugins/docker/install.sh`：`curl \| bash` 无 pipefail、`systemctl start/enable` 不看退出码、成功门 `[ -d $serverPath/docker ]` 恒真、pip 段不看 rc |
| P1-4 | apache 四层叠加假成功 | **真实**（报告有一处外行错误） | 实测 `downloads.apache.org`：`apr-1.7.6.tar.bz2` = **200（仍在，报告说 404 是错的）**、`apr-util-1.6.3` = 404、`httpd-2.4.66` = 404 → 安装仍必失败。目录守卫 `[ -d $serverPath/apache ]`、wget 无校验、configure 与 make 不链、结尾无条件 completed、清理 typo 全部属实 |
| P1-5A | cmake 与 make 不在同一链 | **真实** | mariadb `versions/11.4/install.sh:95-96`、mysql `versions/8.0/install.sh:203-204`、apache `versions/2.4/install.sh:141-146`；**实际波及 16 个 mariadb + 13 个 mysql 版本脚本**（29 处） |
| P1-5B | 扩展脚本失败路径 return 0 | **真实** | 42 个 `plugins/php/versions/common/*.sh` 是 `echo "ERROR!"` + 裸 `return`（返回上一条 echo 的 0），另有 phalcon/swoole 的等待循环超时裸 return、openssl 委托后裸 return；调用链 `_yf_php_ext`（子 shell 返回脚本退出码）→ `yf_require_step` 记成功 |
| P1-5C | 外层不查版本脚本退出码 | **真实，但不是「全部插件」** | apache/mariadb/mysql/ollama/postgresql 共 5 个外层 `install.sh` 不查 `$?`；**openresty 外层本来就查了**（`if [ "$?" != "0" ]`），php-apt/php-yum 走 `yf_require_step` —— 报告这里说的不准 |
| P1-6 | libedit 404 → readline 全缺 | **真实** | 实测 GitHub release 资产 **404**、`thrysoee.dk/editline/libedit-20230828-3.1.tar.gz` **200（534072 字节，与报告一致）**；`plugins/php/lib/libedit.sh` 下载不判、tar/configure/make 全无 `||exit` |
| P2-1 | jdk 插件为空安装 | **真实**（报告漏了一条关键事实） | `plugins/jdk/install.sh:20-26` 只有 mkdir + `echo '安装完成'`；但 `plugins/jdk/index.py` **已有**完整的 JDK 下载安装实现（`install_jdk`）与页面入口，所以正确修法是让 install.sh 真装一个 LTS，**不是**下架插件 |
| P2-2 | 已装插件服务起不来无巡检告警 | **部分成立，报告描述过重** | 面板已有 `panel_task.py::panelPluginStatusCheck_step`（90s）→ `web/utils/plugin.py::autoCachePluginStatus` 会跑各插件 `index.py status` 并把 start/stop 落库；**缺的是崩溃循环（crash loop）识别 + 最近失败原因**，不是「完全无巡检」 |
| P2-3 | mysql 依赖钉死 18.04 分支 | **真实** | `plugins/mysql/versions/8.0/install.sh:147-150`；外部佐证：MySQL 自己的 cmake 报错就写着「Debian/Ubuntu: apt install libtirpc-dev」，24.04 上 glibc 已移除 Sun RPC（宝塔论坛同类报障可查） |
| P2-4 | mongosh 拖垮服务端安装 | **真实** | `plugins/mongodb/install.sh:204-210`：`wget ... \|\| exit 1` 在「建用户 / version.pl / 服务注册」之前 |
| 次要-1 | phpmyadmin 版本漂移 | **真实** | `install.sh` 写死 `VER=5.2.3` 且不读 `$2`；`info.json` 却声明 versions = 4.4.15/4.9.11/5.2.1（三个都对不上） |
| 次要-2 | op_load_balance 依赖顺序 | **不是 bug（报告自己也这么说）** | 现实现已诚实失败（`index.py start` 非 ok 即 exit 1）；只补「前置提示更早」 |
| 次要-3 | mysql 下载无校验 | **真实** | md5 整段注释、`wget --tries=3` 不看 rc、守卫只判文件存在 |
| PHP 两行 | yf_make_jobs 无参在 set -u 下崩 | **真实，已在 HEAD 复现** | `plugins/php/install.sh:13` 有 `set -euo pipefail` + ERR trap；`scripts/lib_make_jobs.sh:82` 是 `local target_ver="$1"`；本地 bash 最小复现：`[ERRTRAP] _yf_jobs=$(yf_make_jobs ...)` rc=1。**注意：HEAD 上那句 `2>/dev/null \|\| echo ""` 挡不住**（trap 在父 shell 触发后 exit 1） |

不计入修复（报告「历史遗留未落地项」章节自述为待立项/待拍板）：宝塔对标三缺口、Actions 门禁、战略四项。

---

## 修复清单（全部已打勾）

### P1（必须修）
- [x] **P1-1** `/www` 权限固化：`scripts/install.sh` + `scripts/install_dev.sh` 各加 `yf_ensure_www_perms`
      （chmod 755 七个目录 + **以 www 身份回读** `test -r/-x`，失败即 die/exit 1；两份函数逐字一致，有用例钉住）
- [x] **P1-5B** 失败透传：42 个 `plugins/php/versions/common/*.sh` 的失败路径改 `return 1` + stderr 打 `ERROR`；
      phalcon/swoole 等待超时改 `return 1`；openssl 委托改 `return $?`；`readline.sh` 接住 libedit 失败；
      `yf_require_step` 结尾 `return 0` → `return ${_rc}`
- [x] **P1-5C** 外层退出码透传：新增 `scripts/lib_version_step.sh::yf_version_step`（`sh -x` 跑版本脚本 → 原样返回 rc → 非 0 打可定位 [ERROR]），
      接入 apache / mariadb / mysql / ollama / postgresql（openresty 已自查、php-apt/php-yum 走 `yf_require_step`，未重复改）
- [x] **P1-6** libedit：换官方源 `thrysoee.dk`（GitHub release 保留为备用）→ 多源轮询 → 逐源校验
      「非空 + `tar -tzf` + 包内 `libedit-<ver>/configure`」→ `configure && make && make install` → 回读 `include/histedit.h` + `lib/pkgconfig/libedit.pc`，任一步失败 exit 1
- [x] **P1-2** nginx 附加模块：`yf_nginx_addon_fetch` 解压**前**读出包内实际顶层目录、解压后归一化回 `$_name`
      （不依赖上游分支叫什么；顺带把非法顶层名挡在解压之前，防 archive-slip）
- [x] **P1-4** apache：三个源码包换 `archive.apache.org`（实测均 200）+ `yf_apache_fetch`（curl 优先/wget 兜底、
      `tar -tjf` 验可解压、失败删包）+ APR/APR-util/httpd 全部 `configure && make && make install` 链式 +
      结尾回读 `httpd/bin/httpd` 才打印 completed + 幂等守卫改判二进制（残留目录先清后装）+ 清理 typo（`httpd-${VERSION}`）
- [x] **P1-5A** mariadb（16 个版本）+ mysql（13 个版本）共 29 处：cmake 参数块末行补 `&& \`，与 `make` 同一条链，
      失败进 `exit 1` 分支（mysql 5.6 里 `&& \` 与 `make` 之间夹了空行会把链打断，已一并修掉）
- [x] **P1-3** docker：`curl | bash` → 先落盘、验「非空 + 以 `#!` 开头」再执行；引擎回读 `command -v docker`；
      服务回读 `systemctl is-active`；daemon 回读 `docker info`（10×2s 重试）；pip 段判 rc + `import docker` 回读；
      `version.pl` 与「安装成功」只在全部回读通过后写
- [x] **PHP 两行修复**：`yf_make_jobs "${type}"` + `local target_ver="${1:-}"`（WSL 实测两种调用形态都不再触发 ERR trap）

### P2（应当修）
- [x] **P2-3** mysql：apt 构建依赖（libudev-dev / libtirpc-dev / libssl-dev）从 18.04 分支放开到**全部 ubuntu**，
      `apt install` 失败先 `apt-get update` 重试一次，仍失败即 exit 1；18.04 专属项（gssglue / ppa 工具链 / gcc-11）留在原分支
- [x] **次要-3** mysql：新增 `scripts/lib_src_fetch.sh::yf_src_fetch`（非空 + `gzip -t` + `tar -tzf` + 包内顶层目录名匹配，
      失败删包返回非 0），mysql 8.0 接入；解压失败也删包 exit 1
- [x] **P2-4** mongodb：mongosh 收进 `_yf_install_mongosh()` 并走 `yf_optional_step`（失败记 missing、不中止），
      失败删掉 0 字节残留；`Install_app` 里接上 `yf_install_report_init/finish`，missing 清单落盘
- [x] **P2-1** jdk：`Install_jdk` 真装 LTS（21→17→11 依次尝试）——镜像目录现取最新包（不写死会 404 的全量文件名）、
      `tar -tzf` 验包、**官方 sha256 强校验**（取不到时明说降级）、`--strip-components=1` 解压到 `<server>/jdk/jdk-<N>`、
      回读 `bin/java -version` 才打印安装完成；已装则幂等跳过
- [x] **次要-1** phpmyadmin：接版本参数 `$2`（缺省 5.2.3、白名单校验），`.tar.xz` → `.tar.gz` 回退（4.x 早期没有 xz），
      解压后校验目录存在，失败 exit 1
- [x] **次要-2** op_load_balance：`mkdir` **之前**先判 `<server>/openresty`，缺依赖直接打「请先安装 OpenResty」并 exit 1
      （不再留半个插件目录）
- [x] **P2-2** 服务存活巡检 v1：
      新增零依赖纯函数模块 `web/core/service_patrol.py`（`parse_systemctl_show` / `crash_loop_decision` /
      `extract_journal_reason` / `pick_unit_for_plugin` / `build_alarm` / `patrol` / 快照读写），
      `panel_task.py::servicePatrol_step` 每 **300s** 只读巡检 `systemctl show`（ActiveState/SubState/Result/NRestarts/ExecMainStatus）
      + `journalctl -u <unit> -n 20 -o cat`，结果落 `data/service_patrol.json`，新告警写面板日志；
      `web/utils/plugin.py::annotateServiceAlarms` 把它挂到软件列表条目上，`soft.js` 在插件名旁打红色徽标
      （tooltip = 状态标签 + 最近失败原因 + unit 名），文案走 i18n（6 语言 lan.js/template.json/template.soft.json）。
      **刻意不自动重启**（重启会盖住根因，根因就在采集到的那条 journal 里）

### 收尾
- [x] 新增守卫用例 `testsuite/test_install_fake_success_guards.py`（28 项：静态契约 + 5 处真跑 bash + P2-2 纯函数行为）
- [x] 全量门禁通过：`python testsuite/run_all.py` → **300 个模块 / 3922 个 test 方法 / 0 隔离 / 全绿**

---

## 验证记录（不是「看起来对」，是真跑过）

| 项 | 验证方式 | 结果 |
|---|---|---|
| 外部事实 | curl 实测 | `ngx_cache_purge` 无 master 分支（`git ls-remote`）且 master.tar.gz 解出 `-main/`；`downloads.apache.org`：apr=200 / apr-util=404 / httpd=404；`archive.apache.org` 三个均 200；libedit GitHub release=404、thrysoee=200（534072B） |
| P1-2 | WSL 真跑 `yf_nginx_addon_fetch`（真下载） | 分支改名场景 → 「包内目录名与预期不同（ngx_cache_purge-main vs -master），已归一化」→ `[OK] 模块就绪`；幂等重跑 0 次下载；半成品目录先清后建；坏 URL → rc=1 且不留残留目录 |
| P1-4 | WSL 真跑 apache 版本脚本（真下载 3 个包） | 预埋 0 字节 apr 包 → 被判「损坏」删除并重下（899670B）；apr-util/httpd 从 archive 下载成功；configure 失败（本机无 gcc）→ `[apache][ERROR] APR 编译安装失败` + rc=1，**没有**打印 completed、**没有**留下 apache 安装目录 |
| P1-6 | WSL 真跑下载+校验函数 | 官方源 534072B 通过 `tar -tzf` 与 `libedit-*/configure` 双重校验；坏 URL → rc=1 且不留文件 |
| P1-5A | WSL `sh -n`（dash）+ 语义实验 | 29 个脚本 dash 解析全过；`false && \` + 空行 + `make` 的实验证明「空行会打断链」（已修掉 mysql 5.6 的这处） |
| P1-5B/C | 用例真跑 bash | `yf_require_step "x" false` → 非 0 退出且不继续；`yf_version_step` 对 exit 7 的脚本原样返回 7 |
| P1-3 | WSL 真跑 docker 安装脚本（源改 404 / HTML 页） | 两种情况都 `rc=1`、**不打印「安装Docker插件成功」**、**不写 version.pl**；pip3 缺失场景同样 exit 1 |
| P2-4 | WSL 真跑 mongosh 函数（源改 403） | `yf_optional_step` 返回 0（不中止）、`YF_LAST_STEP_RC=1`、missing 清单 1 条、0 字节残留被删 |
| P2-1 | WSL 真装 JDK21（真下载 198MB） | 装出 `jdk-21`、`java -version` = `openjdk version "21.0.13" 2026-10-20 LTS`、写 version.pl、rc=0；二次运行幂等跳过 |
| PHP 两行 | bash 真跑（set -euo pipefail + ERR trap） | 修复前 rc=1 且 ERR trap 触发；修复后无参与带参两种调用都输出 `SURVIVED` |
| P2-2 | 用例（假 runner，不碰真 systemd） | 519 次重启的 gitea → `crash_loop` 且进告警；active 的 redis 不进告警；journal 里 CHDIR 失败被提取为 reason；快照写读一致；「刚停」告警、「长期停用」不告警 |

## 已知残留（本轮未做，超出报告范围但已确认同源）
- `plugins/mysql/versions/{5.5,5.6,5.7,8.2,8.3,8.4,9.0,9.1,9.2,9.3,9.4,9.7}` 与 mariadb 各版本的**下载段**
  仍是老的 `wget --tries=3` 形状（本轮只把报告点名的 **mysql 8.0** 换成了 `yf_src_fetch`）。
  获取器已就位，后续把每个版本脚本的下载行替换成 `yf_src_fetch` 即可，属机械改造。
- 报告「历史遗留未落地项」（宝塔三缺口、Actions 门禁、战略四项）按报告自述属待立项/待拍板，本轮不动。

---

# 追加任务（2026-10-26 ~ 10-27）：计划任务两个前端/执行相关缺陷

## 目标
1. 计划任务列表点「日志」报 `Uncaught SyntaxError: missing ) after argument list` + `console.fail is not a function`，日志弹窗打不开。
2. 计划任务点「执行」时被自己设的「执行时段限制 / 日期类型限制」挡住，日志只写
   `跳过执行：未到允许的开始时间(0900)`，看起来像按钮失灵。**手动执行必须立刻跑**。

## 拆解与结论

### 缺陷 1：行内 JS 拼串（P0，日志/删除点不动）
- [x] 真 Chrome 复现定死根因：`getCronData()` 拼的是
      `'<a href="javascript:getLogs(\'' + id + ", '" + name + '\');"'` → 生成
      `getLogs('437, 'test')`（id 被包进字符串，收尾引号丢了）。**与任务名无关，每一行都炸**；
      `planDel` 同一拼法 → 删除同样废。报错位置 `:1:9` 与现场截图一致。
- [x] 行内操作（执行/编辑/日志/删除/启停）改为 `data-cron-act/-id/-name` + 事件委派
      （`$(document).off('click.cronRowAct').on(...)`，pjax 重进不叠加），删除 `cronEscJs`。
- [x] 日志弹窗「执行任务」改 `#cron_log_run` + `success` 里闭包绑定；弹窗任务名 `cronEsc` 转义。
- [x] `plugins/yufeng_systemd/js/yufeng_systemd.js::window.onerror`：`console.fail`（不存在）→
      `console.error` + 去重 + 转义后非阻塞提示（原来处理器自己抛 TypeError，把真错吞了）。
- [x] 守卫：`testsuite/test_crontab_frontend_inline_js.py` + `testsuite/js/crontab_row_actions_probe.js`
      （jsdom 真解析 HTML、真触发委派点击；7 类畸形任务名，310 条断言）。

### 缺陷 2：手动执行被时段/日期限制挡住（P1，点了等于没点）
- [x] `web/utils/crontab.py`：`getShell()` 把「执行时段限制」「日期类型限制」收进
      `gate_checks`，统一包成 `if [ "${YF_CRON_FORCE:-0}" = "1" ]; then … else <gate> fi`；
      脚本头加能力标记 `#YF_CRON_FORCE_SUPPORTED`。
- [x] `startTask()`：`Popen(..., env=YF_CRON_FORCE=1)`（sh 兜底路径同样带开关），
      cron 触发不带该变量 → 判定照旧。
- [x] 存量脚本自愈：`_ensure_force_run_script()` 发现脚本没有能力标记就重生一次（原子替换，
      不影响正在跑的那一份），升级后不必让用户重新保存任务。
- [x] 顺带修掉假成功：脚本生成不出来时（如历史任务 echo 未过白名单）改为明确失败
      （`sync_reason` / `crontab.py_msg_77c6a9`），不再返回「已执行」；
      停用中的任务点执行也能跑（`_prepare_manual_run_script()` 只生成脚本、不碰系统 crontab）。
- [x] 守卫：`testsuite/test_crontab_manual_run_force.py`（9 项，含 4 项**真 bash 跑真脚本**：
      不带开关 → 仍跳过；带开关 → 真跑；日期限制同样跳过且不发节日接口请求）。

## 验证
- 真 Chrome headless：4 种任务名（含 `[系统任务] "/root/.acme.sh/acme.sh" --cron …`）
  → 日志弹窗打开、`runBtnInlineOnclick=null`、`startTaskCalls=[{"data":"id=2"}]`、`errors=[]`。
- 真 bash：同一份脚本，`YF_CRON_FORCE=1` → `RAN_OK`；不设 → `跳过执行：未到允许的开始时间`。
- 全量门禁：`python testsuite/run_all.py` → **312 模块 / 4113 个 test 方法 / 0 隔离 / 全绿**。

---

# 追加任务（2026-10-27）：MySQL/MariaDB「安装完就提示数据库密码错误」

## 现场
MySQL 5.7 装完，点「性能优化」/「当前状态」：
```
[orm] query 连接失败: (1045, "Access denied for user 'root'@'127.0.0.1' (using password: YES)")
sql=show global status
→ 数据库密码错误,在管理列表-点击【修复】!
```
点【修复】也修不好。

## 结论：**是共性 bug**（mysql 与 mariadb 两个插件、5.5/5.6/5.7/8.x/9.x 全部命中）

- [x] 真机复现（WSL Debian + MariaDB 10.11，`test/probe_root_hosts.sh`）：
      `mariadb-install-db` 建的是 `root@localhost` / `root@127.0.0.1` / `root@::1`
      三条**各自独立口令**；面板只 ALTER `root@localhost` →
      ```
      5. socket + 新口令 → socket-ok
      6. TCP 127.0.0.1 + 新口令 → ERROR 1045 (28000): Access denied for user 'root'@'127.0.0.1' (using password: YES)
      ```
      与用户报错逐字一致。
- 根因三条叠加：
  1. `getShell`/初始化 SQL 只写 `root@localhost`；
  2. 插件 my.cnf 全带 `skip_name_resolve=1` → `127.0.0.1` 不反解成 localhost，
     必须匹配独立的 `root@127.0.0.1` 账户；
  3. 面板 ORM 在 **socket 文件不存在**时静默退回 TCP（`web/core/orm.py`）。
- 第二处硬伤：所有写入步骤**不检查执行结果**，失败也 `_saveRootPwd(pwd)`
  → 面板记新口令、库里还是旧（空）口令 → 永久 1045；【修复】走的又是同一套单 host 逻辑。

## 修复
- [x] 新增 `web/core/db_root.py`（mysql/mariadb 共用唯一实现）：
      `build_set_root_sql()` 幂等覆盖 **localhost / 127.0.0.1 / ::1**
      （5.5/5.6 用 `GRANT ... IDENTIFIED BY`；5.7+/MariaDB 用
      `CREATE USER IF NOT EXISTS` + `ALTER USER` + `GRANT`，开头先 `FLUSH PRIVILEGES`
      以适配 `--skip-grant-tables`）；`apply_root_pwd()` 执行后**真连一次库验证**。
- [x] mysql 插件：`initMysqlPwd` / `initMysql8Pwd` / `resetDbRootPwd` / `setRootPwd` /
      `setRootPwdForce` 全部改走共享实现；**验证通过才 `_saveRootPwd`**；
      `fixDbAccess` 失败不再回「修复成功」；固定 `sleep` 换成探活（`_waitDbReady`）。
      顺带删掉 8.x 那条「先把口令设成字面量 `root` 再用 `-proot` 执行 ALTER」的怪操作。
- [x] mariadb 插件：`initMariaDbPwd` / `resetDbRootPwd` / `setRootPwd` 同样改走共享实现。
- [x] `web/core/orm.py`：socket 文件不存在而退回 TCP 时记一条日志（同一路径只告警一次），
      现场再遇到能直接看出「为什么走了 TCP」，而不是只看到密码错误。
- [x] 转义单一来源：`_mysqlSqlLiteral` / `_mysqlOptionValue` 改为委托
      `db_root.sql_literal` / `db_root.option_escape`（避免两份循环漂移）。

## 验证
- 真 MariaDB（`test/verify_db_root_pwd.sh`）：无凭证写入 → socket+TCP 双验证通过；
  幂等重跑；轮换口令（旧口令作凭证）、旧口令随即失效；
  特殊字符口令 `p'a\b;"c`d$e` 可写入并连上；错误口令判失败。
- 新增 `testsuite/test_db_root_pwd_matrix.py`（18 项：SQL 矩阵 / 判定矩阵 / 插件静态断言）。
- 更新 `testsuite/test_mysql_root_pwd_safety.py` 以匹配「写入搬到 db_root」的新结构
  （口令不进 argv、日志打码、5.6 走旧语法）。
- 全量门禁：`python testsuite/run_all.py` → **313 模块 / 4131 个 test 方法 / 0 隔离 / 全绿**。

## 用户侧自助排查（升级后）
```bash
ls -l /www/server/mysql/mysql.sock          # 不存在 → 面板会走 TCP
mysql -uroot -p'<面板里的口令>' -h 127.0.0.1 -e 'select 1'   # 报 1045 → 旧版单 host 缺陷
```
升级后点一次【修复】（改口令/重置）即会补齐 `root@127.0.0.1`、`root@::1` 并验证。

---

# 追加任务（2026-10-27）：核对《问题报告与修改指引（0cdc966）》遗留项

报告基线 `0cdc966`，核对基线 **HEAD `cb27cb288`（比报告多 16 个提交）**。
逐条核 + 能真跑的真跑（WSL Debian + 真 bash，断网用 `http_proxy=127.0.0.1:1`）。

## 核对结论

| 报告条目 | 现状 | 处理 |
|---|---|---|
| P1-新 php-yum 在 Ubuntu 假成功 | **仍存在** | 已修 |
| P1-新 redis/sphinx 空版本 exit 0 | **仍存在** | 已修 |
| P1-新 php85 curl 扩展「产物缺失」 | **根因已由 8bc4fd868 修掉**（63 个扩展脚本全部改 `php-config --extension-dir`），但**失败会被 common.sh 吞掉** | 已修（退出码透传） |
| P1-新 php 扩展构建依赖不自带 | **仍存在**（mac 侧有 brew 分支，Linux 侧不检查 libcurl） | 已修（探测 + 自动装 + 可照抄命令） |
| P2 phpmyadmin 版本未接线 | **仍存在，且根因与报告写的不一样** | 已修 |
| 次要 mysql classic.cnf 缺口 | **已修**（`initDreplace` 幂等补 classic.cnf/gtid.cnf） | 无需再改，补守卫 |
| 待办 次要 mysql 下载无校验 | 部分（有大小 + `file` 魔数） | 已加强（xz/gzip 完整性 + sha256 + 产物回读） |
| 待办 P2-2 服务崩溃无告警 | **未复现**（本轮无崩溃场景） | 未动，需补复现场景再定级 |

## 逐条修复

- [x] **php-yum**：新增平台闸门（无 `yum/dnf` 立即失败并指明该用 PHP[APT]）；7 个
      `versions/*/install.sh` 的 yum 失败改为 `exit 1`（原来是判 `$?` 后不建目录就返回 0）；
      EPEL 从「可选缺失」改为必需步骤；新增**产物闸门**（`$serverPath/php-yum/<ver>` 必须存在）；
      fpm 未 active 时不再打印「start ok」而是失败。EPEL/Remi 段只在真有 yum/dnf 的机器上执行
      （否则 Debian 上连 uninstall 都会被 rpm 缺失打断）。
- [x] **redis / sphinx**：动作白名单（空参数不再落到「卸载」分支）+ 版本 fail-fast
      （sphinx 只接受 info.json 里的 8 个版本）；下载/解压/编译失败即 `exit 1`；
      sphinx 不再先 `mkdir $serverPath/sphinx`（那正是「目录在=已装好」的假象），
      改为 **staging 目录 + searchd 二进制回读**后再落正式目录；成功文案移到回读之后。
- [x] **phpmyadmin 版本接线**：根因是 **bash 函数有自己的位置参数** —— `VER="${2:-}"` 写在
      `Install_phpmyadmin()` 里、调用处无参 → 函数内 `$2` 恒空 → 永远退回 5.2.3。
      改为脚本层 `SCRIPT_VER="${2:-}"`；另加动作白名单、产物回读（含 index.php 的两种布局）、
      `version.pl` 回读一致性校验；面板侧启动失败只 WARN。
- [x] **php 扩展退出码**：`plugins/php|php-apt|php-yum/versions/common.sh` 三份全部透传
      扩展脚本退出码（原来跑完 bash 只 echo 调试行就 exit 0 → 面板永远显示「安装扩展成功」）；
      脚本缺失 → 非 0。
- [x] **php 扩展依赖**：新增 `plugins/php/versions/common/php_ext_deps.sh`
      （`yf_pkgconfig_has` / `yf_ext_ensure_pkgconfig`）；`curl.sh` 编译前确保 libcurl 开发包
      （Debian 装 `libcurl4-openssl-dev/-gnutls-dev`，RHEL 装 `libcurl-devel`），
      补不上就带可照抄命令失败；`configure`/`make` 失败即 `return 1`；
      `readline.sh` 增加 `pkg-config libedit` 回读（避免只留一句含糊的 were not met）。
- [x] **mysql 下载校验**：补 xz/gzip 完整性校验（截断包当轮切节点）、sha256 记录 +
      有官方 `.sha256` 时严格比对、解压后回读 `bin/mysqld`。

## 验证

- 真跑（WSL Debian）：`php-yum install 82` → rc=1 且提示「没有 yum/dnf…改用 PHP[APT]」；
  `php-yum uninstall 82` → rc=0（不再被 rpm 缺失打断）；
  `redis install`（无版本）→ rc=1；`sphinx install`（无版本 / 9.9.9）→ rc=1；
  `redis install 4.0.14` → 通过版本闸门，断网时明确报「下载失败」；
  `common.sh 85 install fakeext`（脚本 exit 3）→ rc=3；`nosuchext` → rc=1；
  `phpmyadmin install 5.2.1` → 日志开头即「准备安装 phpMyAdmin 5.2.1」（修复前是 5.2.3）。
- 新增守卫：`testsuite/test_report_0cdc966_fixes.py`（20 项，含 6 项真跑）。
- 全量门禁：`python testsuite/run_all.py` → **314 模块 / 4151 个 test 方法 / 0 隔离 / 全绿**。

## 未处理（需产品/环境配合）

- **P2-2 服务崩溃无告警**：本轮无复现场景，未复测；需先补 kill 服务进程的复现脚本再定级。
- **mysql 分发包的「官方 sha256 基线」**：仓库里没有权威校验值，当前做的是「记录 + 有 .sha256 就比对 +
  完整性校验 + 产物回读」；若要做固定值强校验，需要按版本/架构维护一张表（属产品决策）。

---

# 追加任务（2026-10-27 二次）：MySQL 5.7 装完仍报「数据库密码错误」+「日志」页 500

## 现场

```
[orm] socket 文件不存在（/www/server/mysql/mysql.sock），退回 TCP 连接 localhost:3306
[orm] query 连接失败: (1045, "Access denied for user 'root'@'127.0.0.1' (using password: YES)")
→ 数据库密码错误,在管理列表-点击【修复】!
点「日志」：
FileNotFoundError: [Errno 2] No such file or directory: '/www/server/mysql/data'
```

## 根因（本轮新发现，上一轮的「全 host 写口令」修不到这一类）

`getMysqldPid()` 取的是**机器上任意 mysqld**。如果机器上另有系统装的 MySQL/MariaDB
占着 3306（apt/yum 装过、或以前装过别家面板），面板会：

1. 把**别人的**实例当成自己的（`status()` → start，`initd_install` 也认这个 unit）；
2. 所有 SQL 打到别人的库 → 口令不同 → `1045 root@127.0.0.1`，而【修复】还会去
   停别人的实例、加 skip-grant-tables、改**别人**的 root 口令（破坏系统库）；
3. 自己的 `/www/server/mysql/data` 从未初始化 → 「日志」页 `listdir` 直接 500。

WSL 上已复现同形：系统 `mariadbd`（datadir=/var/lib/mysql）与临时实例并存时，
`/proc` 里能看到两个 mariadbd，而旧代码无法区分。

## 修复

- [x] `plugins/mysql/index.py` 新增**实例归属判定**（只读 `/proc`，不启子进程）：
      `_procAvailable()` / `getRunningMysqldProcs()`（按 **exe 基名** 认 mysqld/mariadbd，
      不用 cmdline 子串——`bash -c "... mariadbd ..."` 会误判）/ `instanceOwnership()`
      → `ok | not_running | foreign_only | mixed | datadir_missing`，附中文处置建议。
- [x] `runInfo`（性能优化/当前状态）先判归属：foreign/mixed/数据目录缺失 → 直接报
      「实例异常: …」并给出「先停掉冲突实例」的步骤，**不再**诱导用户白点【修复】。
- [x] `fixDbAccess`（【修复】）拒绝 foreign/mixed：不再停用并改写别人的 root 口令；
      修复成功后追加 `selfCheck()`，不通过不谎报「修复成功」。
- [x] `selfCheck()` + `index.py self_check`：归属 → 数据目录 → socket/TCP 连通性，
      用退出码表达结果。
- [x] `binLog` / `binLogList`：数据目录缺失返回可读错误（不再 traceback 500）。
- [x] `getSocketFile()`：配置里的 socket 不存在时，采信**本插件自己**那个 mysqld 的
      `--socket=`（别人的 socket 绝不用）；避免因 unit 与 my.cnf 不一致而退化到 TCP。
- [x] `plugins/mysql/install.sh`：装完跑 `self_check`，不通过即 `exit 1` 并提示端口冲突。
- [x] mariadb 同步最小加固：`runInfo` 判数据目录；`install.sh` 装后校验 `data/mysql`。
- [x] i18n：新增 `实例异常:` / `数据目录不存在:` / `连接自检失败:` / `自检通过` /
      `修复失败: 实例异常（端口可能被其他 MySQL/MariaDB 占用）` 六语言键。

## 验证

- 真机（WSL Debian，系统 mariadbd + 临时实例并存）：
  `getRunningMysqldProcs()` 正确列出 2 个 mariadbd（bash 进程不再误入），
  `instanceOwnership()` → `foreign_only`，`runInfo` 返回
  「实例异常: 本机正在运行的 mysqld/mariadbd 不是本面板的实例…先停掉它…再重装本插件」。
- 新增守卫：`testsuite/test_mysql_instance_ownership.py`（16 项：5 种归属状态、
  runInfo/fixDbAccess 拒绝 foreign、binLog 降级、socket 只认自己人、install 自检接线）。
- 全量门禁：**315 模块 / 4167 个 test 方法 / 0 隔离 / 全绿**。

## 现场处置建议（升级后）

```bash
systemctl status mysql mariadb 2>/dev/null     # 看 3306 到底是谁在听
ss -lntp | grep 3306
```
若是系统装的实例：`systemctl stop mysql mariadb && apt remove --purge mysql-server mariadb-server`
（或直接 `systemctl disable --now`），再到面板重装本插件的 MySQL。

---

# 追加任务（2026-10-27 三次）：卸载不彻底 → 端口被占 → 重装后「密码错误」

## 现场（用户实测）

```
ss -lntp | grep 3306
LISTEN 0 80 *:3306 *:* users:(("mysqld",pid=4156983,fd=31))
systemctl status mysql
  Active: active (running) since Thu 2026-10-08 12:05:55 CST; 2 weeks 5 days ago
  `-4156983 /www/server/mysql/bin/mysqld --defaults-file=/www/server/mysql/etc/my.cnf
```

3306 上的进程 **就是本面板的** `/www/server/mysql/bin/mysqld`，但已跑了 2 周 5 天，
而 `/www/server/mysql/data` 却不存在 —— 「程序文件/数据目录都删了，进程还活着」。

## 结论：是卸载不彻底导致的（用户判断正确）

- `plugins/mysql/versions/*/install.sh` 的 `Uninstall_mysql()` 只有 `rm -rf $serverPath/mysql`；
  外层 `install.sh` 的 `-fast` 分支同样只 `rm -rf`；`initdUinstall()` 只 `disable` **不 stop**。
- 于是 mysqld 带着**已删除的 datadir/socket/程序文件**继续占着 3306。
- 再装时：`start()` 先看 `status()` → `getMysqldPid()` 命中这个僵尸 → 直接 `return 'ok'`，
  **初始化被整段跳过**（`mysqld --initialize-insecure` 从不执行）→ `/www/server/mysql/data` 永远不存在；
  面板 ORM 找不到 socket → 退回 TCP → 连到僵尸 → 口令与前次不同 → 1045「数据库密码错误」。
  上一轮修的「全 host 写口令」与「实例归属」都解释不了 root@127.0.0.1，因为对方根本不是活着的实例配置。

## 修复

- [x] `stopAndKill()`（mysql / mariadb）+ `cleanStale()`：停服务 → 按 **exe 归属**杀（TERM→KILL，
      只杀自己人）→ 删 unit → 清 socket → **回读**是否还有残留（并区分「别人的实例」）。
- [x] `initdUinstall()`：`systemctl stop` 之后再 `disable`（mysql + mariadb）。
- [x] 各 `versions/*/install.sh` 的 `Uninstall_mysql()`：先 `stop_and_kill` +
      `pgrep -f "^<server>/mysql/bin/mysqld"` 兜底 TERM/KILL，再 `rm -rf`。
- [x] 外层 `install.sh`：卸载分支先 `stop_and_kill` 再删目录（fast 与编译版都覆盖），
      卸载后二次回读并告警；安装分支先 `clean_stale`（只清僵尸，不动健康实例，
      健康实例仍走「平滑升级」）。
- [x] `instanceOwnership()` 新增 **`stale_ours`**：`/proc/<pid>/exe` 带 ` (deleted)` 的
      我们自己进程就是「卸载残留」。之前它会被误判成「别人的实例」→ 既不敢杀也不敢重装。
- [x] `status()` 遇 `stale_ours` 返回 `stop`；`start()` 先清理僵尸再走正常启动（初始化不再被跳过）；
      `stop()` 额外补一刀；`runInfo` 给出「上次卸载/升级残留」的处置说明；
      `fixDbAccess` 数据目录缺失时提示「先卸载再重装」。
- [x] `/proc` 扫描加 2 秒 TTL 缓存（`status()` 高频调用，避免每次 readlink 上百个 pid）。

## 验证

- 真机（WSL，用真 mariadbd 复制成 `<server>/mysql/bin/mysqld` 起实例）：
  1) 运行中 → `instanceOwnership()` = `ok`；
  2) 删掉整个目录（模拟旧卸载）→ `stale_ours`，`status()` = `stop`，
     `runInfo` = 「本插件的 mysqld 是上次卸载/升级残留…」；
  3) `stopAndKill()` → 「卸载清理完成」，归属变 `not_running`，进程消失；
  4) 跑真 `versions/5.7/install.sh uninstall`（含 pgrep 兜底路径）→ rc=0，
     **进程 GONE、目录已删**（修复前这里是 ALIVE）。
- 新增守卫：`testsuite/test_mysql_instance_ownership.py` 扩到 27 项
  （stale 识别 / status / runInfo / start 清理 / clean_stale 不误伤健康实例 /
  卸载先停后删 / initdUinstall 必须 stop / mariadb 同款）。
- 全量门禁：**315 模块 / 4178 个 test 方法 / 0 隔离 / 全绿**。

## 现场处置（升级后）

面板里对这个 MySQL 点一次【卸载】（新版会先杀掉 4156983 再删目录），然后重新安装；
若懒得卸载，也可以直接 `systemctl stop mysql && kill -9 4156983`，再重装。

---

# 追加任务（2026-10-27 四次）：同类问题普查 —— 其它插件卸载是否也「只删目录不停进程」

## 普查方法

写扫描脚本逐个读 36 个插件的卸载入口（`Uninstall_*()` / `action == uninstall` 分支），
看四件事：有没有 `stop`、有没有按进程归属 `kill/pgrep`、有没有删 systemd unit、
`rm -rf 安装目录` 是否发生在「停进程」之后。

## 结论

| 插件 | 卸载现状 | 判定 |
|---|---|---|
| mysql / mariadb | 已修（`stop_and_kill` + 各版本脚本 pgrep 兜底） | ✅ |
| redis / valkey / gitea / pureftp / rsyncd / supervisor / sphinx / postgresql / openresty / apache | 只有 `systemctl stop <unit>` + `initd stop` | ⚠️ **同款风险**：进程不是该 unit 起的（上次卸载删了 unit / 手工启动）就杀不掉 |
| **mongodb** | `rm -rf $serverPath/mongodb` 写在 `systemctl stop mongodb` **之前** | ❌ **确定性缺陷**（比 mysql 还直接） |
| **pg_docker** | 只 `rm -rf`，compose 起的 `pg-<inst>` 容器照跑并占端口 | ❌ 确定性缺陷 |
| **php-fpm（16 个版本脚本）** | `init.d/phpNN stop` 后 `rm -rf` | ⚠️ 同款风险 |
| docker | 故意只删插件目录、保留宿主机引擎与容器（注释里写明） | ✅ 设计如此，不改 |
| clean / swap / jdk / phpmyadmin / webssh / webstats / data_query / task_manager / linux_sys_opt / op_* / ollama / python_yf / yufeng_systemd / php-guard / php-apt / php-yum / phpmyadmin | 无常驻的本插件进程（或管理的是别的服务） | ✅ 不适用 |

## 修复

- [x] 新增共享库 `scripts/lib_service_stop.sh`（纯函数，可安全 source）：
      `yf_svc_stop_units`（systemctl / service / init.d 三路）、
      **`yf_kill_by_exe_prefix <dir>`**（只杀 `/proc/<pid>/exe` 位于该目录下的进程，TERM→KILL，
      且对 ` (deleted)` 后缀做了归一化 → 能杀「程序文件已删的僵尸」；
      对 `/`、空串、`/usr`、`/bin`、`/var` 等危险前缀**拒绝执行**）、
      `yf_svc_rm_units`、`yf_svc_force_stop`（组合 + 回读）。
- [x] 11 个 daemon 插件的卸载入口在 `rm -rf` **之前**调用 `yf_svc_force_stop`：
      redis / valkey / mongodb / gitea / pureftp / rsyncd / supervisor / sphinx /
      postgresql / openresty / apache（mongodb 的「先删后停」顺序一并纠正）。
- [x] php 16 个版本脚本的 `Uninstall_php()`：`yf_svc_force_stop "$serverPath/php/<ver>" php<ver>`
      + initd stop 兜底。
- [x] mariadb 18 个版本脚本的 `Uninstall_app()`：同上（+ pgrep 兜底）。
- [x] pg_docker：卸载先按 `instances.json` `docker rm -f pg-<inst>`，再按 compose label
      兜底清理残留容器，最后删目录（数据卷不动）。

## 验证（真跑）

- 共享库单测（WSL + 真 mariadbd 冒充）：把 mariadbd 复制成 `<dir>/bin/svc` 起实例，
  **删掉可执行文件**后再调 `yf_kill_by_exe_prefix <dir>` → 该进程被杀（GONE）；
  目录外 `/usr/sbin/mariadbd` 起的实例 **不受影响**（ALIVE）。
- 端到端：真跑 `plugins/redis/install.sh uninstall`（假 redis-server 同上手法）→
  日志出现 `[svc] 残留进程已清理: <pid>`，rc=0，进程 GONE、目录已删。
- 守卫：`testsuite/test_uninstall_service_stop.py`（8 项：库 API / 危险前缀 /
  真跑「只杀自己人」/ 各插件调用点早于 rm -rf / unit 名正确 / 版本脚本 / pg_docker 容器）。
- 全量门禁：**316 模块 / 4186 个 test 方法 / 0 隔离 / 全绿**。

## 仍未覆盖（如实记录）

- **「启动/状态判定」侧的同族问题**：各插件的 `status()` 多数按「进程名/pgrep」判断，
  机器上若另有同名服务在跑，仍可能误判「已在运行」。这属于「连的是谁」那一类，
  mysql 已用 `instanceOwnership()` 解决；其余插件要逐个改，风险与工作量都大，
  本轮只做「卸载不彻底」这一条（用户报的正是它）。

---

# 追加任务（2026-10-27 五次）：GitHub Actions `install Mysql56` 编译失败（OpenSSL 接线）

## 现场（CI，ubuntu-22.04）

```
CMake Error at cmake/ssl.cmake:66 (MESSAGE):
  Please install the appropriate openssl developer package.
Wrong option or path for WITH_SSL=/www/server/lib/openssl11.
```

## 根因（两处叠加 + 两个同族问题）

1. **脚本名写错**：`plugins/mysql/versions/5.6/install.sh` 调 `openssl10.sh`，
   仓库里的文件叫 `openssl_10.sh` → 自建 OpenSSL **从未执行**，且没判返回值。
2. **版本张冠李戴**：5.6 把 `WITH_SSL` 指向 `lib/openssl11`（那是 5.7 用的 1.1），
   对 5.6 既不兼容（只支持 1.0.x 或自带 yaSSL），目录也不存在。
3. **`openssl_10.sh` 装错地方**：只写了 `--openssldir`（配置目录）没写 `--prefix`，
   OpenSSL 被装进 `/usr/local`；`lib/openssl10` 下没有 include/lib 但**目录存在**
   → 之后永远跳过重装 → 依赖它的编译（MySQL 5.5/5.6、PHP 7.0）永久报
   「Wrong option or path」。
4. 三个 openssl 自建脚本（`openssl.sh` / `openssl_10.sh` / `openssl_11.sh`）：
   判存只看目录、失败不返回非 0、OpenSSL 1.0.2 在 gcc>=10 上缺 `-fcommon`。

## 修复

- [x] **MySQL 5.6 默认不指定 `WITH_SSL`** → 用它自带的 bundled yaSSL（与 5.5 同路子，
      不依赖系统 OpenSSL，ubuntu-22.04 上可编过）；需要 TLS1.2 时显式开
      `YF_MYSQL56_CUSTOM_SSL=1`（走修好的 openssl_10.sh + 回读 ssl.h）。
- [x] `openssl_10.sh`：`--prefix=${SERVER_ROOT}/openssl10` + `--openssldir=.../ssl`，
      `-fcommon`（CFLAGS + config 参数双保险），判存改成「ssl.h + libssl 都在」，
      下载/解压/config/make/install 每步失败即 `exit 1`，**装后回读**。
- [x] `openssl_11.sh` / `openssl.sh`：同样把「目录存在」改成「装好了」+ 装后回读 + 失败非 0。

## 验证

- 新增守卫 `testsuite/test_mysql_openssl_wiring.py`（9 项）：
  ① 全仓扫描「`bash .../plugins/php/lib/xxx.sh`」引用的脚本**必须存在**（专治脚本名打错）；
  ② 5.6 不得出现 `openssl11`、`WITH_SSL` 必须在 `YF_MYSQL56_CUSTOM_SSL` 开关内；
  ③ 三个 openssl 自建脚本都必须有 `_yf_ossl_ready` 回读 + 非 0 退出；
  ④ `openssl_10.sh` 必须用 `--prefix` 且带 `-fcommon`。
  旧代码上跑该用例 **7 项红**（证明能抓住本次缺陷），新代码全绿。
- 全量门禁：**317 模块 / 4195 个 test 方法 / 0 隔离 / 全绿**。

## 说明（为什么 5.6 不用自建 OpenSSL 1.1）

MySQL 5.6 只能链接 OpenSSL 1.0.x；1.1/3.x 的 API 与结构体不兼容。
要 TLS1.2 就得编 1.0.2（本次已修好 `openssl_10.sh` 的路径与 `-fcommon`）。
默认走 yaSSL 是为了「不联网、不额外编译也能装成功」，与 5.5 的历史行为一致。

---

# 追加任务（2026-10-27 六次）：OpenSSL 接线的**全版本**复查（mysql / mariadb / php）

## 逐版本核对结论

| 版本 | 自建脚本 | WITH_SSL 目标 | 结论 |
|---|---|---|---|
| mysql 5.5 | （Debian 13 分支）| lib/openssl10 | ❌ **假成功**：该分支 `exit 0`，面板显示装好但什么都没装 → 已改 `exit 1` 并删掉无意义的 openssl 预编译 |
| mysql 5.6 | openssl_10.sh | yaSSL（默认）/ openssl10 | ✅ 上一轮已修 |
| mysql 5.7 | openssl_11.sh | lib/openssl11 | ⚠️ 版本正确，但**缺失败中止 + 回读 + 空值保护** → 已加固 |
| mysql 8.0~9.7（10 个） | openssl.sh | lib/openssl | ⚠️ 同上 → 已加固 |
| mariadb 10.6~12.1（16 个） | 无 | **不设 WITH_SSL**（MariaDB 自带 bundled wolfSSL） | ✅ 无此问题 |
| php 5.2~5.6 | 无 | 走系统/patch | ✅ |
| php 7.0 | openssl_10.sh | lib/openssl10 | ⚠️ 缺失败中止/回读 → 已加固 |
| php 7.1~8.3（9 个） | openssl_11.sh | lib/openssl11 | ⚠️ 同上 → 已加固 |
| php 8.4 / 8.5 | 无 | `--with-openssl`（系统库，Ubuntu 22.04 = 3.0） | ✅ 版本兼容 |

## 本轮改动

- [x] **mysql 5.7 / 8.x / 9.x（11 个）**：`openssl version` 空值兜底（无 openssl 时
      `[ "" -ge "3" ]` 会打 `integer expression expected`）、自建调用失败即 `exit 1`、
      装后回读 `include/openssl/ssl.h`、`PKG_CONFIG_PATH` 改为追加而不是覆盖。
- [x] **mysql 5.5**：Debian 13 分支由 `exit 0`（假成功）改为 `exit 1` 并给出替代版本建议。
- [x] **php 7.0~8.3（9 个）**：同样的「失败中止 + 回读 ssl.h」（这些脚本原来失败会继续
      `./configure --with-openssl=<空目录>`，最后只留一句含糊的
      `Package requirements (openssl) were not met`）。
- [x] 修正一处自己引入的缺陷：批量替换时把守卫自身那行
      `_ossl_dir="${serverPath}/lib/opensslXX"` 也替换成了 `_ossl_dir="${_ossl_dir}"`
      （自引用）—— 由新增用例 `_ossl_dir 自引用` 抓到后修好。

## 验证

- 新增 `testsuite/test_db_ssl_version_matrix.py`（9 项）：版本↔OpenSSL 兼容矩阵
  （5.5/5.6 只许 1.0.x 或 yaSSL、5.7 只许 1.1、8.x/9.x 只许 3.x；PHP 7.0 只许 1.0.x、
  7.1~8.3 只许 1.1、8.4/8.5 不自建）、构建脚本存在性、失败中止、ssl.h 回读、
  版本探测空值兜底、5.5 不得假成功、MariaDB 必须保持 bundled。
  旧代码上 4 项红（证明能抓住），新代码全绿。
- 全量门禁：**318 模块 / 4204 个 test 方法 / 0 隔离 / 全绿**。

## 说明（为什么 MariaDB 不动）

MariaDB 10.6+ 的 CMake 默认 `-DWITH_SSL=bundled`（自带 wolfSSL），本来就不吃系统
OpenSSL，因此不存在「系统 OpenSSL 3.x 与新版本不兼容」的问题；显式去指系统/自建
反而会引入与 MySQL 5.6 同类的版本错配风险，所以本用例直接把「MariaDB 不得出现
WITH_SSL / lib/openssl」写成了断言。

---

# 追加任务（2026-10-27 七次）：CI 两个红 —— MySQL 5.6 仍编不过 + 门禁缺 jsdom

## 一、`install Mysql56` 第三次红：`WITH_SSL=system`

```
-- CRYPTO_LIBRARY = /usr/lib/x86_64-linux-gnu/libcrypto.so
-- OPENSSL_MAJOR_VERSION =
CMake Error: Cannot find appropriate system libraries for WITH_SSL=system.
```

**上一轮我判断错了**：以为「不指定 `WITH_SSL`」= 用自带 yaSSL。下载 `mysql-5.6.51.tar.gz` 实查后确认：

- `extra/yassl` **不存在**（5.6.51 已移除 bundled yaSSL）；
- `cmake/ssl.cmake` 只认 `system` / `yes` / `<path>` 三种值 —— `bundled` 会直接报
  「Wrong option or path for WITH_SSL=bundled」；
- 不指定时默认 `WITH_SSL=system` → OpenSSL 3.x 的发行版上必然失败。

**结论：5.5/5.6 在 OpenSSL 3.x 上只有一条路 —— 自建 OpenSSL 1.0.x 再 `-DWITH_SSL=<path>`。**
两个版本都改成**默认自建 OpenSSL 1.0.2**（`openssl_10.sh` 内有判存，已装过的机器直接跳过）。

顺带核对 `-fcommon` 的传递方式（下载 1.0.2u 的 `Configure` 逐行确认）：
**1.0.2 的 Configure 不读 `CFLAGS` 环境变量**（只读 CC/RANLIB/AR/PERL/MAKE），
而是把任何 `-*` 命令行参数原样并进 cflags（`$flags.=$_` → `$cflags="$flags$cflags"`）。
所以 `-fcommon` **必须作为 `./config` 的参数**；只 export CFLAGS 在 1.0.2 上是空操作
（中途我改错过一次，靠新增断言 `./config -fcommon` 抓住）。

## 二、门禁红：`test_crontab_frontend_inline_js` 缺 jsdom

```
Error: Cannot find module 'jsdom'
```

CI 只装 Python 依赖，没有 `node_modules`。原夹具 `require('jsdom')` 直接失败。

**修法：拆两层，彻底去掉第三方 node 依赖**

- `testsuite/js/crontab_row_actions_probe.js`：只用 node 内置 `vm` 跑 `crontab.js`，
  输出**生成的 HTML 字符串** + 委派点击的实参；不再 require 任何模块；
- `testsuite/test_crontab_frontend_inline_js.py`：用标准库 `html.parser` 做**真实
  HTML 解析**（属性实体解码、引号截断按浏览器语义），断言行内链接无参数化 JS、
  `data-cron-*` 能原样回读；再把解析出的属性通过环境变量喂回 node，验证委派实参。

关键能力没丢：任务名带双引号时「HTML 属性被截断」正是靠 `html.parser` 抓出来的
（正则做不到这点）。用例从 5 项扩到 8 项（源码层 / 渲染 / 委派实参 / 弹窗 / 空 id）。

## 验证

- 本地**删掉 `node_modules`** 后重跑该用例 → 8 项全绿（证明真的不再依赖 jsdom）。
- 新增/更新守卫：`test_mysql_openssl_wiring.py`（5.6 不得出现 `-DWITH_SSL=bundled`、
  必须默认自建 1.0.2）、`test_db_ssl_version_matrix.py`（5.5/5.6 不得写 bundled）、
  `./config -fcommon` 必须存在。
- 全量门禁：**318 模块 / 4208 个 test 方法 / 0 隔离 / 全绿**。

---

# 追加任务（2026-10-27 八次）：MySQL 5.7 及以上是否有同类问题 —— 实测后改为「优先系统 OpenSSL」

## 实测（下载各版本源码，真跑 cmake 配置）

| 版本 | 源码里的判据 | 与系统 OpenSSL 3.0.22 的实测结果 |
|---|---|---|
| mysql 5.6.51 | `cmake/ssl.cmake` 只认 `system`/`yes`/`<path>`；**`extra/yassl` 不存在** | `system` → 失败（只接受 1.0.x 库） |
| mysql 5.7.44 | `(OPENSSL_MAJOR_VERSION STREQUAL "1" OR "3")` 都算找到 | **`-DWITH_SSL=system` 通过**（`OPENSSL_VERSION (system) is 3.0.22`） |
| mysql 8.0.46 | `MIN_OPENSSL_VERSION_REQUIRED = "1.0.0"` | **`-DWITH_SSL=system` 通过**（同上） |

（两次都停在 `cmake/readline.cmake`，那是缺 libedit/ncurses 开发包，与 SSL 无关。）

## 结论：5.7 及以上**没有** 5.6 那两处错，但有「白编一次 OpenSSL」的浪费

上一轮我写进记忆的「5.7 只到 OpenSSL 1.1」**是错的** —— 5.7.44 的 ssl.cmake 明确接受
major 3。所以「系统 >=3 就自建 1.1 / 3.x」不是必须的：

- 每次安装多花 3~15 分钟编译 OpenSSL；
- 多一个「openssl release 下载失败」的失败面；
- 用官方未测试过的组合（如 8.0.46 + OpenSSL 3.5.2）。

## 修复

- [x] 新增共享选择器 `plugins/php/lib/openssl_pick.sh`：
      `yf_openssl_system_version` / `yf_openssl_version_ge`（**支持 `1.0.2u` 这类带字母后缀的归一化**）/
      `yf_openssl_system_usable` / `yf_openssl_build_dir`（自建 1.1 或 3.x，失败 exit 1 + 回读 ssl.h）。
- [x] **5.7 / 8.0~9.7（11 个）**：改为「系统 OpenSSL 能用就用 `-DWITH_SSL=system`，
      缺开发包或版本过旧才自建」。
- [x] **5.5 / 5.6 保持不变**（只支持 OpenSSL 1.0.x，必须自建 1.0.2）。
- [x] 守卫：`test_db_ssl_version_matrix.py` 新增「5.7+ 必须优先系统库 + 必须有自建兜底」、
      `test_mysql_openssl_wiring.py` 新增选择器 API/归一化断言。

## 验证

- 选择器真跑（WSL）：`1.0.2u >= 1.0.2` → YES、`3.0.22 >= 1.0.0` → YES、
  `1.0.1 >= 1.0.2` → NO、`LibreSSL` → NO、`system usable(9.9.9)` → NO。
- 全量门禁：**318 模块 / 4210 个 test 方法 / 0 隔离 / 全绿**。

## 收益

CI 的 mysql57 / mysql80 job 不再编译 OpenSSL（省 5~15 分钟/次），
也把「openssl-1.1.1w / 3.5.2 下载失败」这一类偶发红一并消掉。5.5/5.6 仍走自建（无法避免）。

---

# 追加任务（2026-10-27 九次）：MySQL 安装最低从 5.7 开始（下架 5.5 / 5.6）

## 用户口径

`MySQL` 安装**直接去掉 5.5、5.6**，最低从 5.7 开始。

## 依据（同日实测）

5.5 / 5.6 上游已 EOL，且它们的 `cmake/ssl.cmake` **只认 OpenSSL 1.0.x**
（5.6.51 还移除了自带 yaSSL）→ 在 OpenSSL 3.x 的发行版上必须自建 OpenSSL 1.0.2
才能编译（每次多 3~15 分钟 + 一个下载失败面）。而 5.7.44 / 8.0.46 的 CMake
**都接受系统 OpenSSL 3.x**（实测 3.0.22 通过），没有这个负担。

## 改动（对齐 PHP `PHP_MIN_INSTALL_BRANCH` 的既有口径）

- [x] **安装入口**：`plugins/mysql/info.json` 的 `versions` 与 `todo_versions`
      去掉 5.5 / 5.6，最低 5.7。
- [x] **接口层**：`web/utils/plugin.py` 新增 `MYSQL_MIN_INSTALL_BRANCH = '5.7'` +
      `_mysql_branch_of()` / `_mysql_is_eol_branch()`，在 `install()` 里拦一道
      （前端看不到 ≠ 接口调不到），返回 i18n 键 `plugin.mysql_eol_branch_install`
      （带最低版本号）。不拼中文，外语界面不漏翻。
- [x] **卸载能力必须保留**：`plugins/mysql/versions/{5.5,5.6}/install.sh` 与
      `conf/my5.{5,6}.cnf` **都不删** —— 已装用户还要能卸载、能看回原配置模板。
      「装得上、卸不掉」是比「不支持安装」更坏的状态。
- [x] **兜底版本**：`plugins/mysql/index.py` 里读不到 `version.pl` 时
      原为 `5.6`，改为 `5.7`（面板最老的受支持版本）。
- [x] **CI**：删除 `python-app-mysql55.yml` / `python-app-mysql56.yml`
      （留着就等于声明「支持安装 5.5/5.6」，手动跑必然红）；
      `test_ci_workflows_hardening.py` 的 `HEAVY_WORKFLOWS` 同步收窄。
- [x] **i18n**：新增 `plugin.mysql_eol_branch_install`（6 语言 × `lan.js` /
      `template.json` / `template.soft.json`，共 18 处）。
- [x] **文档**：`README.md` 的「已知限制」表改成「已下架」；`compatibility.md` 的
      MySQL 兼容性表把 5.5/5.6 两列划掉，并加「历史测试结果 ≠ 当前支持」的说明。

## 验证

- 新增守卫 `testsuite/test_mysql_min_install_branch.py`（8 项）：
  `info.json` 首版必须是 5.7、不得含 5.5/5.6；`todo_versions` 同样干净；
  两个旧 workflow 已删、5.7 的保留；`_mysql_is_eol_branch` 对
  5.5/5.6/5.6.51 为真、对 5.7/8.0/9.7/空值为假；`install()` 必须返回 i18n 键；
  **5.5/5.6 的卸载脚本与配置模板必须仍在**；兜底版本不再是 5.6。
  旧代码上 5 项失败 + 1 错误，新代码全绿。
- 全量门禁：**319 模块 / 4218 个 test 方法 / 0 隔离 / 全绿**。

## 影响面

- **新装**：商店里 MySQL 只剩 5.7 / 8.0 / 8.2 / 8.3 / 8.4 / 9.0~9.7；
  手工调 `/plugins/install` 传 5.5/5.6 会被拒并提示最低 5.7。
- **已装 5.5/5.6 的机器**：完全不受影响 —— 管理/卸载照旧（`setup_version` 读
  `server/mysql/version.pl`，与 `info.json` 的 versions 无关），「更新」按钮照旧指向最新版。

---

# 追加任务（2026-10-27 十次）：MySQL 只留 LTS + 已下架版本一键升级到同系列 LTS

## 一、安装列表只留 LTS（用户 2026-10-27 定）

| 版本 | 类型（官方口径） | 处理 |
|---|---|---|
| 5.5 / 5.6 | 早已 EOL | 下架（上一轮已做） |
| **8.2 / 8.3** | **Innovation**（只支持到下个 Innovation 发布） | 下架 |
| **9.0 ~ 9.4** | **Innovation** | 下架 |
| 5.7 | LTS（已 EOL 但用户要求保留为地板） | 保留 |
| **8.0** | LTS | 保留 |
| **8.4** | **LTS** ✅（官方文档：`8.4.0 LTS`、`mysql-8.4-lts`） | 保留 |
| **9.7** | **LTS** ✅（官方文档：`9.7.x LTS`、`mysql-9.7-lts-community`） | 保留 |

`plugins/mysql/info.json` → `versions: ['5.7','8.0','8.4','9.7']`，`todo_versions` 同步。
**版本脚本全部保留**（已装用户卸载 + 升级中转/回滚要用）。

## 二、已下架版本 → 同系列 LTS 一键升级（用户可选）

- [x] **目标版本计算**：`web/utils/plugin.py::mysql_eol_upgrade_target(installed, available)`
      —— 只给**同主版本**的最高可用版本：
      5.5/5.6→5.7、8.2/8.3→8.4、9.0~9.4→9.7；已是 LTS 或同主版本无可用版本 → 空。
      跨主版本（5.x→8.x/9.x）**不给建议**（MySQL 数据字典跨主版本不兼容）。
- [x] **列表字段**：`makePluginInfo` / `refreshDynamicStatus` 两处都算 `eol_upgrade_to`。
- [x] **前端**：`soft.js`
      ① 「更新」判断从「versions 最后一项」改为「**同主版本最高可用版本**」
         —— 顺带修掉「8.0 用户永远看不到更新到 8.4」的老问题；
      ② 有 `eol_upgrade_to` 时显示红标「已下架」+ 「升级到 X」（复用 `softUpdate` 的确认弹窗，
         升不升由用户决定）。
- [x] **真升级**（关键）：`plugins/mysql/install.sh` 原来在「已装 mysql」时**无条件自愈 + exit 0**，
      面板点「更新」根本不换二进制。现在分两支：
      * 已装版本 == 目标版本 → 只自愈（原行为）；
      * 已装版本 != 目标版本 → `_yf_mysql_upgrade()`：
        **① 停服务 → ② 备份 `server/mysql`（含 data，先查磁盘空间）→ ③ 旧目录改名保留
        （`.mysql_prev_<ts>`）→ ④ 装目标版本 → ⑤ 回填 data（mv，省时省空间）→
        ⑥ 启动 + mysql_upgrade + initd + self_check → ⑦ 任一步失败则自动回滚（旧目录换回来 + 重启旧版本）**。
      * 跨主版本直接拒绝；未带 `YF_MYSQL_ALLOW_UPGRADE=1`（面板升级入口会带）也拒绝，防误点。
- [x] `plugins/mysql/index.py` 新增 `mysql_upgrade` 命令入口（5.7 需要；8.0+ 由 mysqld 自动升级）。
- [x] i18n：`soft.eol_version` / `eol_version_tip` / `eol_upgrade_tip`（6 语言 × 3 文件）。

## 验证

- 新增 `testsuite/test_mysql_lts_upgrade.py`（16 项）：
  LTS 列表逐项核对、Innovation 版本彻底移除、版本脚本仍在、
  升级目标映射（含「跨主版本不给建议」）、install.sh 的分支/备份先于改目录/回滚/磁盘检查、
  后端字段与前端接线、i18n key 存在；
  **真跑 shell 两段**：备份→改名→回填 data（数据标记完好）、安装失败→回滚（版本与数据都回到原样）。
- 升级流程里的 7 处 `|| true` 改为「显式 if + WARN」（棘轮不许新增吞失败写法）。
- 全量门禁：**320 模块 / 4234 个 test 方法 / 0 隔离 / 全绿**。

## 已知边界（如实记录）

- 5.5/5.6 → 5.7 官方只承诺「5.5→5.6→5.7 逐级」，面板允许直接升（会打印提示），
  失败自动回滚；是否接受该风险由用户决定（这正是用户要求的「升级权限交给客户」）。
- 升级过程会**完整备份**，因此需要与 `server/mysql` 同量级的空闲空间（脚本会先检查并明确报错）。
- 升级**不迁移**用户自定义的 `my.cnf`（新版本用新模板，旧参数在新版本可能非法导致起不来）；
  原 `my.cnf` 在备份包与 `.mysql_prev_*` 目录里，可手工取回。
