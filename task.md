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
