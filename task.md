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
