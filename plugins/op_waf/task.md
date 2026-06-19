# op_waf 项目任务与开发规范

## 项目整体描述
op_waf 是基于 OpenResty 和 Lua 编写的 WAF（Web Application Firewall）插件，集成在面板中。它通过拦截恶意请求、限制 CC 攻击、IP 黑白名单过滤等机制，提供对 Web 站点的安全防护。包含在 Nginx 请求阶段的各种规则匹配以及后端的日志落盘（SQLite）。

## 开发规范描述
1. **简洁至上**：恪守 KISS 原则，强调可维护性，避免过度工程化与不必要的复杂设计。
2. **第一性原理**：基于 First Principles Thinking 拆解问题本质，结合工具提升效率。
3. **事实优先**：以事实为最高准则。
4. **渐进式推进**：通过多轮对话逐步明确需求，在任何设计或编码前，必须完成充分调研与问题澄清。
5. **结构化流程**：严格遵循「构思方案 → 审核确认 → 任务拆解 → 实施执行」的流程。
6. **编码规范**：
   - 统一使用 UTF-8 (无 BOM) 格式。
   - 尽量避免直接使用 PowerShell 修改包含中文的文件，使用内置工具（write_to_file/replace_file_content）以保持编码正确。
   - 不要重复造轮子，尽量使用已有函数，保持编程风格统一。

---

## 需求池与 Task List

### 需求 1：优化 IP 匹配性能 (引入 lua-resty-ipmatcher)
- `[x]` 调研确认 IP 规则存储方式（目前使用的是 json/lua 文件，而非 SQLite）。
- `[x]` 编写 `Implementation Plan` 并与用户确认设计方案。
- `[x]` 在 Lua 中引入并初始化 `lua-resty-ipmatcher`。
- `[x]` 编写工具函数，将现有的 `[[start_ip], [end_ip]]` 或单 IP 转换为 CIDR 格式并输入给 `ipmatcher`。
- `[x]` 替换 `waf_common.lua` 和 `init.lua` 中的旧有线性扫描逻辑。
- `[x]` 实现通过 `ngx.shared.DICT` 进行的心跳或版本检测（预留了 `cache_key .. "_version"` 机制）。

### 需求 2：404 封锁策略容易误伤 (中危)
- `[x]` 在 `log.lua` 中增加对常见静态资源后缀（png, jpg, js, css, woff 等）的过滤。
- `[x]` 实现基于 `URI Hash` 的去重逻辑，防止对同一缺失资源的重试导致阈值虚高。
- `[x]` 构建二级报警机制：
  - 1 分钟内 30 次独立 404 -> 触发 5 分钟的警告拦截页面。
  - 5 分钟内 150 次独立 404 -> 直接拉黑 90 分钟（无提示）。
- `[x]` 编写并集成独立的警告页面 HTML 模板。

### 需求 3：动态信誉系统 (高危)
- `[x]` 设计并建立信誉积分池（`ngx.shared.DICT`中维护）。
- `[x]` 实现基于拦截分类的赋权扣分（例如 CC 扣 10 分，UA 异常扣 20 分，注入扣 50 分）。
- `[x]` 信誉归零时直接调用长效拉黑机制（24小时）并记录独立日志，替代有冲突的 SQLite 写操作。

### 需求 4：自动蜜罐 (中危)
- `[x]` 在全局配置中增加“蜜罐”选项，支持用户自定义路径。
- `[x]` 在拦截处理生命周期中增加蜜罐触发检测。
- `[x]` 与信誉系统对接，触碰蜜罐即扣 100 分秒封。设计并建立信誉积分池（`ngx.shared.DICT`中维护）。

### 需求 5：增加面板界面的“封禁地址”管理及一键释放功能
- `[x]` 增强 Nginx `remove_waf_drop_ip` 接口，同时删除信誉分和警告状态等历史污点。
- `[x]` 在 `index.py` 中增加获取被封禁 IP 列表的后端 API (`getDropIpList`)。
- `[x]` 在 `index.py` 中增加获取被封禁 IP 最近日志的后端 API (`getDropIpLogs`)。
- `[x]` 在 `index.py` 中增加释放被封禁 IP 的后端 API (`removeDropIp`)。
- `[x]` 修改 `index.html`，在左侧菜单栏添加“封禁地址”入口。
- `[x]` 在 `js/op_waf.js` 中编写相应的渲染逻辑、弹窗逻辑和释放逻辑。

### 需求 6：优化服务面板交互体验
- `[x]` 在 `index.html` 的服务操作按钮下方，添加关于“重启”和“重载配置”的优雅说明文字。

### 需求 7：防火墙自动放行 SSL 证书申请
- `[x]` 在 `init.lua` 的 `run_app_waf()` 中，所有规则检测之前硬编码放行 `/.well-known/acme-challenge/` 路径，确保 ACME HTTP-01 验证不受 WAF 拦截。

### 需求 8：封禁地址列表增加IP归属及缓存机制
- `[x]` 后端 `index.py` 新增 `getIpLocationBatch` 代理接口。
- `[x]` 后端 `index.py` 新增 `getIpLocation` 代理接口 (单IP查询)。
- `[x]` 前端 `js/op_waf.js` 修改 `wafDropIpList` 表头与布局，增加“IP归属”列。
- `[x]` 前端 `js/op_waf.js` 实现基于 LocalStorage 缓存与批量分片的IP归属获取和渲染逻辑。

### 需求 9：修复恶意 URI 绕过蜜罐问题
- `[x]` 在 `init.lua` 中，修改 `waf_honeypot` 函数以支持对 URI 斜杠的归一化，并放宽路径匹配条件为包含匹配。
- `[x]` 在 `waf/rule/url.json` 中，放宽对敏感文件探测规则的首部限制，允许匹配子目录中的请求。

### 需求 10：修复加入黑名单时 JSON 加载报错问题
- `[x]` 在 `index.py` 的 `autoMakeLuaConfSingle` 和 `autoMakeLuaImportSingle` 方法中增加对读取内容为空或为布尔值（文件不存在）的防御性处理，避免 `json.loads` 抛出 `TypeError` 异常。

### 需求 11：修复黑白名单重复添加的问题
- `[x]` 在 `index.py` 的 `addIpBlack` 和 `addIpWhite` 接口中，增加对传入 IP 规则是否已存在于列表中的校验，拦截重复添加并返回提示信息。

### 需求 12：优化拦截日志详情的“永久拉黑”交互体验
- `[x]` 修改 `op_waf.js` 中的日志详情弹窗逻辑，取消直接点击 IP 即拉黑的隐藏操作。
- `[x]` 在 IP 地址右侧新增红色的“永久拉黑”文字按钮。
- `[x]` 点击“永久拉黑”后弹出专业且详细的二次确认对话框，告知操作影响及后续如何解封（全局配置 ➔ IP黑名单）。

### 需求 13：修复面板 UI 布局与滚动条显示问题
- `[x]` 在 `index.html` 中优化整体 CSS 布局：固定外部容器 `.bt-w-main` 高度，并将滚动条限制在内容区域 `.bt-w-con` 内。彻底解决页面内容过多时滚动条会带动左侧菜单一起滚动，导致左侧下方留白的视觉 Bug。
- `[x]` 为全局页脚水印“衢州御风科技有限公司 出品”添加了 CSS 事件穿透 (`pointer-events: none;`) 并增加半透明白底背景。现在它不仅能完美悬浮在右下角，即便覆盖在如“设置”等按钮上方时，依然能正常阅读，并且鼠标点击动作会直接穿透水印作用于底下的按钮，完美解决了遮挡按键无法点击的问题。

### 需求 14：修复御风OP防火墙封禁地址点击详情报错及IP归属获取不全
- `[x]` 任务 1：修改 `plugins/op_waf/index.py` 中的 `getArgs()` 以直接支持 JSON 字符串反序列化。
- `[x]` 任务 2：在 `plugins/op_waf/index.py` 中添加 `get_location_from_pconline(ip)` fallback 获取函数。
- `[x]` 任务 3：重构 `plugins/op_waf/index.py` 中的 `getIpLocationBatch()`，引入 `pconline` 降级逻辑。
- `[x]` 任务 4：重构 `plugins/op_waf/index.py` 中的 `getIpLocation()`，引入 `pconline` 降级逻辑。
- `[x]` 任务 5：运行测试脚本，验证 WAF CLI 命令无报错。
- `[x]` 任务 6：生成最终的 Walkthrough 文档并清理临时文件。

### 需求 15：修复服务首屏操作说明及规则统计由于前端竞态导致偶尔不显示的问题
- `[x]` 任务 7：在 `plugins/op_waf/index.html` 中注入 `window.pluginSetService` 劫持函数。
- `[x]` 任务 8：在 `plugins/op_waf/index.html` 中剥离并提取 `renderWafAdditionalContent()` 渲染函数。
- `[x]` 任务 9：在 `plugins/op_waf/index.html` 中简化 `renderWafService()`，移去 `setTimeout`。
- `[x]` 任务 10：重新验证页面显示和功能，更新 task.md 与 walkthrough.md。

### 需求 16：扩大 SSL 放行范围至整个 .well-known 目录
- `[x]` 任务 1：修改 `plugins/op_waf/waf/lua/init.lua`，将硬编码放行的 `/.well-known/acme-challenge/` 路径扩大为整个 `/.well-known/` 目录。
- `[x]` 任务 2：验证 Lua 脚本语法及 Nginx 配置。
- `[x]` 任务 3：更新 `task.md` 标记任务完成。

