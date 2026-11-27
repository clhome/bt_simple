# OpenResty 1.31.9.1 升级支持 + 御风软件版本在线同步（综合脚本）

## 背景

2026-11-27 上游发布 **OpenResty 1.31.9.1**（nginx core 1.31.8 → 1.31.9，含 10 项安全修复：
HTTP/2、HTTP/3 内存破坏与 UAF、resolver/mail proxy UAF、`try_files`+`alias` 溢出等）。
面板现状：`plugins/openresty/versions/` 最高只有 `1.31.1`，`info.json` 版本清单也止于
`1.31.1`，已装用户既看不到「有新版本」，也没有可执行的升级入口。

同时，上游发补丁版的节奏远快于面板发版：每次都要人工复制一份 300 行的版本安装脚本，
漏同步一次就等于把安全修复漏掉。故本次把「版本情报」和「版本可安装性」一起做成可自动化。

## 用户口径（2026-11-27 确认）

1. 自动更新边界 = **只更新清单 + 自动生成安装脚本**，绝不自动升级线上服务；
2. 升级提示位置 = 软件商店「更新」徽标 + OpenResty 服务页顶部提示条 + 首页卡片角标；
3. 夜间任务 = **统一系统任务**（`[勿删]御风软件版本在线同步`），一次同步 JDK + OpenResty，
   并平滑迁移掉历史 `[勿删]御风JDK在线版本同步`（不留两条重复任务）；
4. `info.json` 版本清单 = 只保留近两代 + 新版（`1.31.1`、`1.31.9.1`）。

## 任务拆解与进度 (Task List)

- [x] **任务 1：1.31.9.1 可安装（构建配方唯一真源）**
  - [x] 1.1 新增 `plugins/openresty/versions/common/openresty_build.sh`：把原 `1.31.1/install.sh`
        的 300 行配方收敛为共享实现（含源码双通道获取、OpenSSL/jemalloc/brotli/zstd 依赖、
        Makefile OpenSSL `gmake clean` 兼容修补、按脚本位置解析路径而非 `pwd`）
  - [x] 1.2 `--with-http_v3_module` 由「硬编码 `1.31.1`」改为数值比较（`>= 1.31.1` 自动继承）
  - [x] 1.3 新增 `versions/1.31.9.1/install.sh`（薄封装，`YF_OPENRESTY_VERSION=1.31.9.1`）
  - [x] 1.4 `versions/1.31.1/install.sh` 改为同一薄封装（`VERSION=1.31.1.1`，保留三段目录名）
  - [x] 1.5 `install.sh` 的 `version.pl` 回填改为「不覆盖版本脚本写的完整上游号」，
        让 `1.31.1.1` / `1.31.1.2` 这类同系列补丁版在面板里可区分
  - [x] 1.6 `info.json` 版本清单 → `["1.31.1", "1.31.9.1"]`；面板初始化推荐版本 → `1.31.9.1`

- [x] **任务 2：在线版本索引（`web/core/openresty_release_index.py`）**
  - [x] 2.1 解析 `openresty.org/en/download.html`：只认 4 段正式版包名（排除 `ngx_openresty-*`、`-rc*`）
  - [x] 2.2 数值比较 / 三段历史号兼容（`1.31.1` 与 `1.31.1.1` 视为同版本，不反复提示）
  - [x] 2.3 缓存 `data/openresty_release_index.json`（12h TTL）+ 内置兜底表 + 抓取失败留痕
  - [x] 2.4 `ensure_version_script()`：按统一模板生成 `versions/<ver>/install.sh`，已存在绝不覆盖
  - [x] 2.5 `panel_hint()`：离线提示（软件列表/首页/插件页共用），附 changelog 链接与「情报日期」

- [x] **任务 3：升级提示三处落地**
  - [x] 3.1 后端：`plugin.py::_onlineApplyVersionHint()` 挂 `online_update_to` / `online_update`
  - [x] 3.2 软件商店：`soft.js` 增加「升级到 1.31.9.1」入口 + 红色「更新」徽标（计入可更新计数）
  - [x] 3.3 首页卡片：`/plugins/index_list` 带 `online_update_to`，`soft.js` 渲染「新版本」角标
  - [x] 3.4 OpenResty 服务页：`index.html` 黄条容器 + `js/openresty.js` 渲染/一键升级（DOM 文本渲染，防注入）
  - [x] 3.5 `index.py::versionInfo()` 新增 `version_info` 回调（离线，读缓存），并顺手补齐安装脚本
  - [x] 3.6 `plugin.py::install()` 对 openresty 下发安装前确保版本脚本存在，缺失则明确报错而不是假成功

- [x] **任务 4：统一版本同步任务（替换 JDK 单任务）**
  - [x] 4.1 新增 `web/core/version_sync.py`：按「版本源」注册（JDK 复用 `get_online_jdks`，OpenResty 走索引模块）
  - [x] 4.2 新增 `scripts/version_sync.py`：`run [--only]` / `add` / `remove` / `status`
  - [x] 4.3 `ensure_task()`：同名任务只校正脚本；否则把历史 JDK 任务改名迁移（保留 id/周期）；都没有才新建
  - [x] 4.4 触发点：首页 `getIndexList()`、OpenResty `version_info`、JDK 插件 `_ensure_crontab_task`（6h 节流）
  - [x] 4.5 `plugins/jdk/tool_task.py`：`createBgTask()` 委托统一引擎；`removeBgTask()` 只清历史 JDK 任务
  - [x] 4.6 计划任务名称翻译：`crontab.py::humanTaskName` + `crontab.js::translateTaskName` + 6 语言包

- [x] **任务 5：国际化**
  - [x] 5.1 插件语言包 6 语言新增 8 个键（提示条/升级按钮/确认文案），Key 集合 100% 对齐
  - [x] 5.2 Web 语言包 6 语言新增 4 个键（任务名、首页角标、上游提示、脚本缺失），
        并由 `scripts/tools/export_lang_carriers.py --apply` 派生 `.json` 载体

- [x] **任务 6：质量门禁**
  - [x] 6.1 新增 `testsuite/test_openresty_version_sync.py`（14 个用例：解析/比较/缓存/生成脚本/成品一致性/任务迁移/多源汇总/DB 列名归一化）
  - [x] 6.2 `bash -n` / `sh -n` 校验全部改动脚本；`node --check` 校验改动 JS
  - [x] 6.3 运行 `python testsuite/run_all.py`（356 模块 / 4578 用例 + 4 项静态门禁，全绿）
  - [x] 6.4 清理临时文件，确认工作区无残留
  - [x] 6.5 顺带修掉同族既有缺陷（本轮实测发现）：
        - `web/core/db.py::save()` 的真实签名是 `save('col1,col2',(v1,v2))`，而
          `web/admin/setup/init_cron.py` 的 ACME 自愈与旧 JDK `tool_task` 的「平滑升级」
          都写成了 `save({...})` → 每次静默 TypeError，自愈从未生效；两处均改为列名+值
        - 面板 DB 多列查询会给后续列名带前导空格（`{'id':..,' sbody':..}`），
          导致 `row.get('sbody')` 恒为 None；统一在读取处 strip 列名
        - 对应用例的 DB mock 同步改为真实签名（`test_ssl_status_and_cron_fix`）

## 结论与后续

- 上游发新补丁版后：夜间任务抓到 → 自动生成 `versions/<ver>/install.sh` → 软件商店/首页/插件页
  立刻出现「升级到 x.y.z」，用户点击即走原有安装任务流程（停服 → 编译 → 启动）。
- 若要扩展第三个版本源（如 PHP/Redis），只改 `web/core/version_sync.py` 的 `SOURCES` 注册表。
- 历史版本目录（1.17.8 … 1.29.2）仍保留在磁盘上（只从 `info.json` 清单移除），
  已装用户仍可正常卸载；不删除是为了避免「装得上、卸不掉」。

---

## 追加任务：GitHub 测速探针改造（2026-11-27，用户真机日志触发）

**现象**：点 OpenResty 升级，日志出现
`正在测速节点: ... +++ curl ... https://gh.ddlc.top/https://github.com/clhome/bt_simple/archive/refs/heads/master.tar.gz`，
看起来像在下载整包御风面板。

**定位**：不是下载面板包，是 `scripts/github_download.sh::_gh_get_best_proxy()` 给 9 个
GitHub 加速节点测速，样本 URL 被硬编码成面板仓库整仓归档（`curl -m 5 -o /dev/null`，
只跑 5 秒）。但旧实现确有 4 个真问题：

1. 每节点白下最多 5 秒数据（1.6MB/s ≈ 8MB/节点，9 节点 ≈ 70MB）；
2. 样本是 codeload **动态打包**的 tar.gz，慢且计入归档限流；
3. 样本（归档）与真实目标（release 资产）不同源，选点偏差；
4. `_gh_check_direct()` 只定义从未调用（死代码）；结果只活在进程环境变量里，
   每个安装任务都要重测。

**改造（B+C 方案）**：

- [x] 1. 探针改为面板 release 固定资产 + `-r 0-524287`（≤512KB/节点，不再触发动态打包）
- [x] 2. 官方直连先单独测，达到 3MB/s 阈值直接收工（复活 `_gh_check_direct`）
- [x] 3. 测速结果落盘缓存 30 分钟（`${TMPDIR:-/tmp}/.yf_gh_proxy_speed`，可用
      `YF_GH_SPEED_CACHE` 覆盖）；最佳节点下载失败时立即作废缓存
- [x] 4. 其余代理并行探测（临时文件汇总，tie-break 与原实现一致）；无 `mktemp` 时退回串行
- [x] 5. 面板侧同源对齐：`web/core/yf/__init__.py` 的后台测速同样改成 release 资产 + Range
- [x] 6. 守卫用例：`testsuite/test_github_download_optimization.py` 新增 4 例
      （探针不许回到整仓归档 / 缓存命中零探针 / 并行取最快且记录死节点 / 直连达标跳过代理）
- [x] 7. `bash -n` + 全量门禁（356 模块 / 4582 用例）全绿

---

## 追加任务：升级完成后首页/软件商店自动刷新（2026-11-27 用户反馈）

**现象**：OpenResty 升级完成（后台编译结束、`version.pl` 已是 1.31.9.1）后，首页卡片仍显示
「新版本」角标，要等一段时间（甚至重启面板）才消失，用户误以为升级没生效。

**根因（两层，缺一不可）**：

1. **服务端**：`/plugins/index_list`（首页）直接返回 `getStaticPluginList()` 的**进程级缓存快照**，
   其中 `setup_version` / `online_update_to` 是「构建缓存那一刻」算出来的；而软件商店页
   （`getList`）每次请求都会 `refreshDynamicStatus` 重算 —— 所以商店页正常、首页卡住，
   且多 worker 时表现随机（命中哪个 worker 的旧缓存）。
2. **前端**：任务结束后没有任何触发点让首页重新拉 `/plugins/index_list`，只有手动刷新/重载。

**改造**：

- [x] 1. `web/utils/plugin.py::getIndexList()` 每请求 `refreshDynamicStatus()` 重算已装状态与在线提示
- [x] 2. `plugin.install()` 提交后清 `__plugin_list_static_cache`（同 worker 立即失效）
- [x] 3. `public.js`：`yfWatchTaskIdle()`（任务计数**下降**=有任务结束，800ms 防抖）→ 派发
      `yf:tasks-changed`；监听器清首屏 localStorage 缓存并重拉 `getSList` / `indexListHtml`
- [x] 4. 首页 3s 轮询的 `net.task_count` 也喂给该监听器（`index.js`），非首页 6s 的 `getTaskCount` 同理
- [x] 5. OpenResty 服务页：提交升级后 60s 轮询 `version_info`，版本变化 → 关黄条 + 提示
      「OpenResty 已升级到 x」（45 分钟封顶，成功即停止轮询）+ 刷新首页卡片/商店列表
- [x] 6. 新增 `testsuite/test_plugin_update_linkage.py`（8 例，含 jsdom 无关的 node 行为探针
      `testsuite/js/task_idle_watcher_probe.js`：下降派发/不变不派发/防抖合并/非法值忽略）
- [x] 7. 顺带修掉两处用例的环境性假红：`test_files_delete_modal_i18n` 的极简 window 沙盒
      （`public.js` 里补 `addEventListener` 能力判断）；`test_github_download_optimization::test_04`
      用 `curl(){ printf '404'; }` 固定返回，不再受真实代理波动影响
- [x] 8. 全量门禁：357 模块 / 4590 用例 / 4 项静态门禁 全绿

---

## 追加任务：OpenResty 大版本（1.x → 2.x）升级的提前适配（2026-11-27）

**背景**：新版本检测上线后，若上游从 1.x 跳到 2.x，原来有三处会「看起来正常、实际有问题」：

1. 严格解析只认 4 段版本号；上游若改成 `2.0.0`（三段）/`2.0.1.1-lts`/`-rc1`，会因为页面还有旧的
   1.31.x 而**解析成功但漏掉大版本**（不报错）；
2. `checkSetupTask()` / `refreshDynamicStatus()` 只用 `info.json.versions` 匹配任务标题 →
   `安装[openresty-2.0.0.1]` 不显示「正在安装」，用户可能重复提交（脚本锁会挡，但体验差）；
3. 安装下拉与面板初始化推荐版本都来自 `info.json.versions`（快照）→ 能升级到 2.x，但**新装选不到 2.x**；
   跨大版本升级也没有「先备份」提示。

**改造（已验收）**：

- [x] 1. `openresty_release_index.parse_listing_unsupported()`：收集「像 OpenResty 包但版本号不合规」的条目
      （排除 `ngx_openresty-*`），`refresh()/sync_versions()` 透传；夜间同步任务打印
      `[WARN] 上游出现无法识别的版本号，面板未采信: …`（不再静默漏大版本）
- [x] 2. `plugin.py::_appendOnlineVersion()`：把在线索引的最新正式版**并入 `versions`**
      （数值比较、幂等、绝不降级、只对 openresty），并在 `makePluginInfo()` 与
      `refreshDynamicStatus()` 两处调用 → 安装下拉、初始化推荐版本、任务状态匹配三者对齐
- [x] 3. `plugin.py::_openresty_recommended_version()`：面板初始化推荐版本改为「离线索引最新（回退 1.31.9.1）」
- [x] 4. 跨大版本文案：软件商店 tooltip/确认框（`soft.cross_major_tip`，6 语言）+
      OpenResty 服务页黄条与确认框（插件语言包 6 语言）
- [x] 5. 守卫用例：`testsuite/test_openresty_version_sync.py` 新增 4 例（无法识别格式告警 + 日志透传、
      versions 合并幂等/不降级、2.x 提示与任务匹配、跨大版本文案与 6 语言键）
- [x] 6. 性能复核：`getIndexList` 仍为 ~2.1–2.3ms（合并索引只是一次小 JSON 读取）
- [x] 7. 全量门禁：**357 模块 / 4594 用例 / 4 项静态门禁 全绿**

**仍只能等 2.x 真发布再做的事**：`openresty_build.sh` 的 configure 选项/附加模块 master 分支/OpenSSL 版本
与 2.x 的实际兼容性（编译失败会显式 exit 1，不会假成功），以及 2.x 的 changelog 页规则。

---

## 追加任务：升级后起不来 / 装错目录的适配与自愈（2026-11-27 真机两例）

**现场**：一台升级后正常，另一台起不来，日志：
```
nginx: [emerg] open() "/www/server/web_conf/php/conf/enable-php-apt7.1.conf"
       failed (2: No such file or directory) in .../qouzhou.qzuiouio.com.conf:23
nginx: configuration file /www/server/openresty/nginx/conf/nginx.conf test failed
```

**同时发现第二个更严重的 bug**：构建脚本把面板根当成了 `serverPath`（少算一层），
二进制实际装到 `<面板根>/openresty`，面板却看 `<serverPath>/openresty`
→ 表现是「version.pl 写着 1.31.9.1，实际跑的还是旧二进制」，另一台“成功”的机器
很可能是这种情况（需要用 `nginx -v` 核实）。

**改造**：

- [x] 1. **路径修正**（`versions/common/openresty_build.sh`）：`serverPath = dirname(面板根)`，
      `rootPath = 面板根`，与 `yf.getServerDir()` 对齐；并加历史误装目录告警
- [x] 2. **幂等判定加二进制复核**：`version.pl` 相同也要 `nginx -v` 版本对得上才“已安装”，
      否则强制重编（修「装错目录/编译失败却写了版本号」的永远修不好）
- [x] 3. **启动路径接入 PHP 占位自愈**：`restyOp()` / `restyOp_restart()` 改用
      `yf.checkWebConfig()`（扫 vhost 补 `enable-php-*.conf` stub → 该站点 .php 返回 503，
      不再拖垮全局；再按 `nginx -t` 报错动态补，最多 5 次）
- [x] 4. **启动复核**：systemctl 返回 0 不等于起来了 → 以 pid + 进程存活为准（`status()`），
      否则报「已下发启动命令但进程未保持运行」并附 journalctl/error.log
- [x] 5. **升级前预检**（`install.sh` + `index.py conf_precheck`）：停服前先自愈+语法检查；
      升级场景预检不通过则**中止升级**（现有服务保持运行）
- [x] 6. **失败自动回滚**：新二进制起不来 → 恢复 `nginx.bak` + 还原 `version.pl` 并重启，
      回滚成功也如实把任务标记为失败（不会假装成功）
- [x] 7. **版本记录 vs 二进制交叉核对**：`version_info` 增加 `binary_version` /
      `version_mismatch`，服务页黄条提示「记录为 X，实际二进制 Y，请重新安装」
- [x] 8. 新增 `testsuite/test_openresty_start_selfheal.py`（11 例：stub 内容/扫描修复、
      启动路径接线、预检顺序、回滚、路径推导真跑、二进制复核、版本不一致提示 + 6 语言）
- [x] 9. 全量门禁：**358 模块 / 4605 用例 / 4 项静态门禁 全绿**

**两台上线机型的恢复步骤**（写进交付说明）：
1. 先 `.../openresty/nginx/sbin/nginx -v` 核实真实版本（别只看面板）；
2. 部署新代码后在软件商店点一次「更新/重装」— 路径已修正、缺失 PHP 占位会被自动补；
3. 运行正常后手工删除历史误装目录 `<面板根>/openresty` 与 `<面板根>/source/openresty`。
