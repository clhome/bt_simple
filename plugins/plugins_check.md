# 插件检查

> 最后更新：2026-09-21
> 本轮 i18n 升级范围：`plugins/*/lang/*.json`（六语言）、`plugins/*/js/*.js`、`plugins/*/index.html`、`web/static/app/{i18n,public}.js`
> 回归守卫：`test/test_plugins_i18n_upgrade.py`（15 项断言，全绿）
> 项目自带检查器 `test/i18n_scripts/i18n_plugin_check.py`：36 个插件**硬性失败项全部为 0**
> 升级方案与验收标准：`plugins/i18n_升级方案.md`

## 一、i18n 完成状态

|     | 插件名称        | i18n | 功能备注                             |
| --- | --------------- | ---- | ------------------------------------ |
| 1   | apache          | 完成 |                                      |
| 2   | clean           | 完成 | 2 处 `{0}` 占位符改 `{1}`（msgTpl）  |
| 3   | data_query      | 完成 | 补 15 个缺键；修多参 `pt()`；`操作说明` 补 `pt()` |
| 4   | docker          | 完成 | 修多参 `pt()`、句中拼接；`不超过总内存` 模板化 |
| 5   | fail2ban        | 完成 | 增加了 op 防火墙的联动；修 4 处多参 `pt()` |
| 6   | gitea           | 完成 | 修 2 处多参 `pt()`                    |
| 7   | jdk             | 完成 |                                      |
| 8   | linux_sys_opt   | 完成 | 2 处 `pt()` 前导空格失配修复         |
| 9   | mariadb         | 完成 | 补 3 个缺键、句中拼接模板化           |
| 10  | mongodb         | 完成 | 句中拼接模板化                        |
| 11  | mysql           | 完成 | 升级自愈未测试；一键备份并下载；补 4 个缺键 |
| 12  | ollama          | 完成 | 补 3 个缺键、拆分含 `<code>` 的拼接    |
| 13  | op_load_balance | 完成 | 分页计数模板化                        |
| 14  | op_waf          | 完成 | 提升可靠性、性能；修多参 `pt()`        |
| 15  | openresty       | 完成 |                                      |
| 16  | pg_docker       | 完成 | 7 处多参 `pt()` + `{0}` 占位符改 `{1}`（msgTpl） |
| 17  | pgadmin         | 完成 |                                      |
| 18  | php             | 完成 | 大版本无损升级单次自愈、三级容灾拉起、编译脚本语法修复；补 2 个缺键 |
| 19  | php-apt         | 完成 | 大版本无损升级自愈、/run/php 自愈、孤儿套接字清理；补 2 个缺键 |
| 20  | php-guard       | 完成 |                                      |
| 21  | php-yum         | 完成 | 大版本无损升级自愈、Remi 自愈、孤儿套接字清理；补 2 个缺键 |
| 22  | phpmyadmin      | 完成 |                                      |
| 23  | postgresql      | 完成 | 句中拼接模板化                        |
| 24  | pureftp         | 完成 | 状态文本拼接修复                      |
| 25  | python_yf       | 完成 |                                      |
| 26  | redis           | 完成 | 补 1 个缺键                          |
| 27  | rsyncd          | 完成 | 同步风险提示改 `{1}` 模板；补 1 个缺键 |
| 28  | sphinx          | 完成 |                                      |
| 29  | supervisor      | 完成 |                                      |
| 30  | swap            | 完成 | 补 1 个缺键（长段说明）               |
| 31  | task_manager    | 完成 | 流量 tooltip 四行改 `{1}` 模板        |
| 32  | valkey          | 完成 |                                      |
| 33  | varnish         | 完成 |                                      |
| 34  | webssh          | 完成 |                                      |
| 35  | webstats        | 完成 | 蜘蛛 tooltip 改 `{1}` 模板；补 1 个缺键 |
| 36  | yufeng_systemd  | 完成 |                                      |

## 二、本轮修复的问题类型

| 类型 | 说明 | 规模 |
| ---- | ---- | ---- |
| **多参 `pt()` 失效** | `pt('…{1}…', arg)` —— `pt()` 只接受 1 个参数，第二参被静默丢弃，用户看到字面 `{1}` / `%s` | 15 处（fail2ban 4、gitea 2、pg_docker 7、op_waf 1、data_query 1） |
| **`{0}` 起始占位符** | `msgTpl()` 从 `{1}` 起替换，`{0}` 永远填不上 | 9 键（pg_docker 7、clean 2） |
| **`pt()` 实参首尾空白失配** | `pt(" (当前未设置)")` 与键 `(当前未设置)` 差一个空格，查表落空 | 2 处（linux_sys_opt） |
| **`msgTpl()` 未包 `pt()`** | 确认框标题/正文永远是中文 | 13 处 |
| **句中拼接** | `'中文A' + 变量 + '中文B'` 违反 `{n}` 模板化红线，德/法/意语序错乱 | 31 处 → 0 |
| **`pt()` 字面量缺键** | 包了 `pt()` 但语言包无键，等于没翻 | 37 个键 |
| **DOM 白名单缺键** | `translatePluginDOM` 会翻但无键，永远显示中文 | 1 个键 |
| **脏键** | 键里混入 HTML / JS 拼接 / 属性赋值 / 转义序列等代码片段 | 133 → 0 |
| **死键** | 源码已无任何引用的键（含 36 份页脚重复键） | 320 个 → 0 |
| **碎片脏键 `参数:(` / `)没有!`** | 27 个插件的 `checkArgs()` 用 `'参数:(' + ck[i] + ')没有!'` 拼接，产生两个无法独立翻译的脏键；改为 `'缺少必要参数: ' + ck[i]` | 54 → 0 |
| **动态 `pt()` 多参失效** | `op_waf` 的 `wafMsg()` 写 `pt(WAF_MSG_PATTERNS[i][1], m[1])`——首参非字面量，正则扫不到，用户看到字面 `{1}` | 1 处 → 0 |
| **后端消息恒中文** | `returnJson` 的中文消息由 `layer.msg` 直出，`t()` 只查全局字典，从不查插件字典 | 可翻译率 0% → **87%（812/929）** |
| **zh-TW 简体残留** | zh-TW 值中混入真简体字 | 262 条 → 0 |
| **译文含 HTML** | `web/core/i18n.py:assert_no_html_in_translations()` 硬红线 | 12 → 0 |
| **动态首参多参 `pt()` 漏检** | `fail2ban/js/fail2ban.js:49` 的 `pt(F2B_MSG_PATTERNS[i][1], m[1])`——首参非字面量，正则方案扫不到，6 条防护消息显示字面 `{1}`；改为 `msgTpl(pt(…), [m[1]])` | 1 处 → 0（新增括号配对检测器 `check_pt_argc.js`） |
| **后端消息契约不统一** | 27 条缺前缀键、7 条无冒号分隔（`'数据库用户[' + name + ']不存在!'`）、4 条前缀含 HTML；统一为「`<可翻译前缀>: <动态参数>`」并补键 | 38 处 → 0（959 条后端中文消息 100% 可查键） |
| **全局语言包 zh-TW 简体残留** | 递归审计 `web/static/language/zh-TW/**`（9341 叶子/语言） | 2901 条 → 0 |
| **全局语言包 CRLF** | `web/static/language/**` 内混用 CRLF / LF | 46 文件 → 0 |
| **品牌键被扁平旧键遮蔽** | `plugins.docker.title` 等 206 个逻辑键被 `template.soft.json` 里的扁平残留键覆盖（错误机翻值生效） | 412 个值 → 已修正 |

## 三、已知例外（有意保留，非遗漏）

1. **后端诊断日志**：`mariadb` / `mysql` 的 `执行结论: 数据库导入执行完毕！` 等由
   `index.py` 生成，同时被前端 `logText.indexOf(...)` 当作成功哨兵使用。
   翻译它会破坏哨兵判断，故保留为技术日志输出。
2. **代码内检测哨兵**：`mysql` 的 `rawData.indexOf('备份成功')`、`data_query` 的
   `errorMsg.indexOf('驱动')` 等，仅用于内部判断，不面向用户。
   检测器已显式排除 `indexOf/includes/startsWith/endsWith` 上下文。
3. **HTML 注释**：`yufeng_systemd` 的 `<!-- 极简模式区域 -->` 等，不进 DOM 文本。
4. **后端预留键（26 个）**：如 `拉取失败:`、`清空失败:`、`导入失败:`、`缺少必要参数:`。
   它们是插件 `.py` 里 `returnJson(False, '拉取失败: ' + e)` 这类
   「键 + 变量」消息的静态前缀。前端 `layer.msg` 拿到的是拼好的整串，
   静态扫描看不到完整引用，故保留待后端消息机制使用。
   判定规则见 `test/i18n_scripts/i18n_dead_keys.py` 与回归测试
   `TestNoDeadKeys`（键若是插件 `.py` 中文字面量的子串即视为预留）。
   全库实测：26 个死键**全部**属于此类，孤儿死键 0 个。
5. **zh-TW 用词差异**：636 条已是正体、仅用词与台湾习惯不同（如 `進程` vs `程序`）。
   如需统一，执行：
   `<venv-python> test/i18n_scripts/zh_tw_convert.py --apply --sort`（会连带重排键序）。

## 四、遗留问题闭环（本轮升级）

升级方案见 `plugins/i18n_遗留问题升级方案.md`。7 项待办全部闭环：

| # | 待办 | 处置 | 证据 |
| --- | ---- | ---- | ---- |
| 1 | 动态 `pt()` 参数个数无法静态校验 | 新增括号配对检测器（能处理动态首参、跨行、嵌套括号、注释、模板串、正则歧义）；顺带抓出并修掉 `fail2ban.js:49` 真 bug | `scripts/verify_i18n.py --check pt-argc` 0 违规；自证夹具 6 处全中 |
| 2 | 后端消息补键（38 处） | 分三类：A 类 27 条纯补键；B 类 7 条重构源码使其符合冒号前缀契约；C 类 4 条拆 HTML 为结构性拼接 | `--check backend-msg-key` 0 未命中（959 条消息） |
| 3 | 后端消息结构化（可选） | **不采用**。改为统一「`<可翻译前缀>: <动态参数>`」契约，由 `YfI18n.translateAny()` 的前缀匹配兜底；零破坏、零前端改动 | `translateAny()` 三层匹配 + 回归测试 `TestBackendMessageFallback` |
| 4 | `plugins/docker/info.json` 缺英文 title/ps | 归因纠正：`info.json` 按仓库约定本就单语言（36 个插件一致）。真因是**扁平旧键遮蔽** `plugins.docker.title` | `test_plugins_i18n.py` 由 FAIL → **OK** |
| 5 | 测试硬编码「插件总数 38」 | 改为从文件系统推导。口径厘清：`plugins/` 下 37 个目录，其中 `待审核/` 无 `lang/`，故 i18n 插件数为 **36** | `test_all_plugins_i18n_complete` / `test_all_38_plugins_deep_i18n` / `test_all_plugins_ui` 全 OK |
| 6 | 全局语言包 CRLF / 键数不一致 | 递归审计 + opencc `s2twp` 转换 + CRLF 归一 + 补齐 zh-CN 缺失叶子键 | `web/static/language/**` CRLF 文件 0 个；`test_all_foreign_languages_complete` OK |
| 7 | `test/` 被 gitignore，守卫不入库 | 采用方案 C：守卫收敛为 **自包含单文件** `scripts/verify_i18n.py`（生产目录、被跟踪），检测逻辑与自证夹具全部内嵌，不依赖 `test/` | CI workflow 已接入；`test/` 模拟缺失下自证仍全绿 |

> 待办 7 的关键设计：`test/` 被 `.gitignore:202 /test` 整目录忽略，若门禁去读
> `test/` 下的夹具，CI 检出后会「静默跳过」自证——只跳过、不报错的守卫会制造
> 「永远全绿」的假象。故夹具**内嵌**进脚本，`test/` 缺失时对应项打印 `[SKIP]`
> 而非静默通过。

## 五、门禁与回归

### 5.1 CI 门禁（9 项）

```bash
python scripts/verify_i18n.py            # 全部门禁，退出码 0/1
python scripts/verify_i18n.py --verbose  # 附失败明细
python scripts/verify_i18n.py --self-test  # 校验检测器本身（已知答案）
```

| 检查名 | 含义 |
| ------ | ---- |
| `plugin-key-parity` | 插件六语言键集完全一致 |
| `global-key-parity` | 全局语言包六语言叶子路径完全一致 |
| `no-html` | 译文不含 HTML（白名单除外） |
| `dirty-keys` | 语言包无「代码型脏键」 |
| `pt-argc` | 无多参 `pt()` / `_t()` 调用 |
| `msgtpl-pt` | 所有 `msgTpl(` 首参必须含 `pt(` |
| `no-zero-placeholder` | 无 `{0}` 占位符 |
| `backend-msg-prefix` | 后端消息「可翻译前缀」不含 HTML |
| `backend-msg-key` | 后端中文消息能查到语言包键 |

CI workflow：`.github/workflows/i18n-check.yml`（独立文件，不改上游 7 个构建/发布 workflow）。
Python 3.10 与 3.13 均已实测通过。

### 5.2 本地重守卫

`test/test_plugins_i18n_upgrade.py`（27 项，标准库 `unittest`）——比门禁更细，
含 DOM 白名单覆盖、`translateAny` 行为、红线检测器自证等。因 `test/` 被忽略，
**仅本地运行**，不进仓库。

```bash
python -m unittest test.test_plugins_i18n_upgrade -v
```

### 5.3 当前回归基线

| 用例 | 结果 |
| ---- | ---- |
| `test_plugins_i18n_upgrade`（27 项） | **OK** |
| `test_plugins_i18n` | **OK**（原 FAIL：docker 英文标题） |
| `test_all_plugins_i18n_complete` | **OK** |
| `test_all_38_plugins_deep_i18n` | **OK** |
| `test_all_plugins_ui` | **OK** |
| `test_all_plugins_js_syntax` | **OK** |
| `test_all_python_syntax` | **OK** |
| `test_all_foreign_languages_complete` | **OK** |
| `test_crlf_and_sh_syntax` | **FAIL（既有基线，非本轮引入）**：90 个文件在 HEAD 里就以 CRLF 提交，分布 `plugins/*/versions/**`、`web/**/*.py`、`参考/**`、`scripts/tools/`、`test/`（被忽略）。语言包部分已清零 |

> `test_crlf_and_sh_syntax` 的剩余 90 个文件属**仓库既有状态**（`git cat-file` 验证
> HEAD blob 本身含 CRLF），需单独一次「换行符归一」提交，与 i18n 治理解耦，
> 以免混入本次改动、干扰 review 与回滚。

