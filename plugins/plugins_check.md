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

## 三、已知例外（有意保留，非遗漏）

1. **后端诊断日志**：`mariadb` / `mysql` 的 `执行结论: 数据库导入执行完毕！` 等由
   `index.py` 生成，同时被前端 `logText.indexOf(...)` 当作成功哨兵使用。
   翻译它会破坏哨兵判断，故保留为技术日志输出。
2. **代码内检测哨兵**：`mysql` 的 `rawData.indexOf('备份成功')`、`data_query` 的
   `errorMsg.indexOf('驱动')` 等，仅用于内部判断，不面向用户。
   检测器已显式排除 `indexOf/includes/startsWith/endsWith` 上下文。
3. **HTML 注释**：`yufeng_systemd` 的 `<!-- 极简模式区域 -->` 等，不进 DOM 文本。
4. **后端预留键（94 个）**：如 `拉取失败:`、`清空失败:`、`导入失败:`、`缺少必要参数:`。
   它们是插件 `.py` 里 `returnJson(False, '拉取失败: ' + e)` 这类
   「键 + 变量」消息的静态前缀。前端 `layer.msg` 拿到的是拼好的整串，
   静态扫描看不到完整引用，故保留待后端消息机制使用。
   判定规则见 `test/i18n_scripts/i18n_dead_keys.py` 与回归测试
   `TestNoDeadKeys`（键若是插件 `.py` 中文字面量的子串即视为预留）。
5. **zh-TW 用词差异**：636 条已是正体、仅用词与台湾习惯不同（如 `進程` vs `程序`）。
   如需统一，执行：
   `<venv-python> test/i18n_scripts/zh_tw_convert.py --apply --sort`（会连带重排键序）。

## 四、待办

- [ ] **动态 `pt()` 参数个数无法静态校验**：`pt(someVar, arg)` 形态需人工复核，
      现有正则只覆盖首参为字符串字面量的场景。
- [ ] **后端消息补键（38 处）**：`docker` 的 `获取镜像备份列表失败:`、`导出镜像失败:`、
      `镜像文件不存在:`、`导入镜像失败:`，`fail2ban` 的 `缺少必要参数:`、`部分IP封禁失败:`、
      `不支持的防护类型:` 等，`.py` 里有拼接型消息但语言包无对应前缀键，
      故 `translateAny` 的前缀匹配也命中不了。
- [ ] **后端消息结构化（可选）**：把 `returnJson(False, '拉取失败: ' + e)` 改为
      返回 `{msg_key, msg_args}`，由前端 `msgTpl` 渲染，可彻底摆脱字符串拼接。
- [ ] `plugins/docker/info.json` 缺少英文 `title` / `ps`（`test_plugins_i18n.py` 报错，历史遗留）
- [ ] `test_all_plugins_i18n_complete.py` 等用例硬编码「插件总数 38」，实际 37，需更新断言
- [ ] 全局语言包 `web/static/language/**` 的 CRLF / 键数不一致问题（本轮未涉及）
- [ ] `test/` 目录被 `.gitignore` 忽略，回归守卫 `test/test_plugins_i18n_upgrade.py`
      不会被提交；如需纳入 CI 需调整 `.gitignore` 或迁移到 `scripts/`
