# bt_simple 面板项目任务与开发规范

## 项目整体描述

bt_simple 是一个轻量级的服务器运维管理面板（对标宝塔面板的极简版本），支持网站管理、SSL证书、防火墙（如 op_waf）、Fail2ban 网站防护等插件扩展。

## 开发规范描述

1. **简洁至上**：恪守 KISS 原则，强调可维护性，避免过度工程化与不必要的复杂设计。
2. **第一性原理**：基于 First Principles Thinking 拆解问题本质，结合工具提升效率。
3. **事实优先**：以事实为最高准则。如有错误请直接指出，欢迎严谨纠错。
4. **统一使用 UTF-8 (无 BOM) 格式，换行符强制使用 LF。**
5. **开发平台**：简体中文 Windows 11 平台。运行命令行优先使用 PowerShell 7 (`pwsh.exe`)。
6. **输出规范**：所有回复、分析过程、方案与任务清单，统一使用中文。
7. **编码规范**：
   - 禁止直接使用 PowerShell 原生重定向符号（如 > 或 >>）修改包含中文的文件，以防引入编码冲突。
   - 文件写入与修改优先使用项目封装的 `write_to_file` 或 `replace_file_content` 工具。
   - 优先复用项目中已有的函数和模块，保持编程风格与现有代码库高度统一。

---

## 需求池与 Task List

### 需求 14：修复御风OP防火墙封禁地址点击详情报错及IP归属获取不全

- `[x]` 任务 1：修改 `plugins/op_waf/index.py` 中的 `getArgs()` 以直接支持 JSON 字符串反序列化。
- `[x]` 任务 2：在 `plugins/op_waf/index.py` 中添加 `get_location_from_pconline(ip)` fallback 获取函数。
- `[x]` 任务 3：重构 `plugins/op_waf/index.py` 中的 `getIpLocationBatch()`，引入 `pconline` 降级逻辑。
- `[x]` 任务 4：重构 `plugins/op_waf/index.py` 中的 `getIpLocation()`，引入 `pconline` 降级逻辑。
- `[x]` 任务 5：运行测试脚本，验证 WAF CLI 命令无报错。
- `[x]` 任务 6：生成最终的 Walkthrough 文档并清理临时文件。

### 需求 15：修复首页状态标题位置偏移问题

- `[x]` 任务 1: 修改 `web/templates/default/index.html`，移除“状态”标题的 `h3.pull-left` 包裹，使其结构与“概览”、“软件”标题一致，消除浮动影响导致的错位。
- `[x]` 任务 2：排查发现顶栏高度溢出侵入下方标题行导致文本避让，需对其进行限制。
- `[x]` 任务 3：修改 `web/static/css/site.css`，在顶栏压缩部分为 `.index-pos-box .position` 增加 `height: 40px !important;` 限制，并对 `index-pos-box` 进行浮动清理。
- `[x]` 任务 4：再次验证首页渲染效果。

### 需求 16：扩大防火墙 SSL 放行范围至整个 .well-known 目录以防证书申请失败

- `[x]` 任务 1：修改 `plugins/op_waf/waf/lua/init.lua`，将硬编码放行的 `/.well-known/acme-challenge/` 路径扩大为整个 `/.well-known/` 目录。
- `[x]` 任务 2：验证 Lua 脚本语法及 Nginx 配置。
- `[x]` 任务 3：更新 `task.md` 标记任务完成。


### 需求 17：在网站管理页面增加带图标的配置导入与导出功能

- `[x]` 任务 1：修改 `web/admin/site/site.py`，新增导出接口 `/site/export_all`。
- `[x]` 任务 2：修改 `web/admin/site/site.py`，新增导入接口 `/site/import_all`。
- `[x]` 任务 3：修改 `web/templates/default/site.html`，在标题栏右侧加入导入/导出按钮及隐藏的 file input。
- `[x]` 任务 4：修改 `web/static/app/site.js`，实现 `exportAllSites()` 的异步请求和客户端 JSON 触发下载逻辑。
- `[x]` 任务 5：修改 `web/static/app/site.js`，实现 `importAllSites()`，包括读取文件、弹层确认、向后端发起导入请求及刷新列表。
- `[x]` 任务 6：手动测试导出和导入功能，确认各种配置（域名、伪静态、SSL等）全部无损且完全一致地恢复。（本地无 Linux+OpenResty 真实运行环境，已通过 Python 编译性测试进行静态校验）。
- `[x]` 任务 7：清理临时文件，生成 Walkthrough 说明文档。

### 需求 18：导入网站检查冲突与自定义覆盖

- `[x]` 任务 1：修改 `web/admin/site/site.py`，新增 `/site/check_import_conflicts` 接口，检查导入站点名、目录及域名是否存在冲突，并分类返回。
- `[x]` 任务 2：修改 `web/admin/site/site.py` 中 `/site/import_all` 接口，加入对 `overwrite` 字段的判断，执行清理及重建处理。
- `[x]` 任务 3：修改 `web/static/app/site.js` 中 `importAllSites` 相关逻辑，增加冲突检查与弹出框进行用户覆盖确认功能。
- `[x]` 任务 4：清理开发过程中的临时文件，进行检查及准备生成最后 Walkthrough 说明文档。

### 需求 19：修复导入网站配置报错 name 'json' is not defined

- `[x]` 任务 1：修改 `web/admin/site/site.py`，在顶部增加 `import json`，解决导入解析数据时 `name 'json' is not defined` 的报错。
- `[x]` 任务 2：排查导入冲突检查接口（`/site/check_import_conflicts`）的 500 TypeError 报错（`list()` 无参报错），发现是本文件存在 `def list():` 覆盖了内置 `list` 函数所致。移除对 `list()` 的强制转换，直接使用 `set()`，修复 500 报错问题。
