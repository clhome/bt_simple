# jQuery 1.12.4 → 3.7.1 升级方案

> **项目**: bt_simple 面板管理系统
> **目标**: 将 jQuery 从 1.12.4 升级到 3.7.1，解决安全漏洞和性能问题
> **策略**: 静态扫描自动修复 + 运行时验证收尾 (两阶段组合)

---

## 一、升级动因

| 维度     | jQuery 1.12.4 (当前)                    | jQuery 3.7.1 (目标)                |
| -------- | --------------------------------------- | ---------------------------------- |
| 安全性   | 存在 XSS (CVE-2020-11022/11023) 等漏洞 | 已全部修复                         |
| 性能     | Sizzle 选择器引擎较慢                   | 原生 `querySelectorAll` 优先，更快 |
| 维护状态 | 已停止维护                              | 社区活跃维护                       |
| 体积     | ~97KB min                               | ~88KB min (slim 版仅 ~72KB)        |

---

## 二、项目依赖全景分析

### 2.1 jQuery 引入方式

| 文件 | 引入方式 | 说明 |
|------|----------|------|
| `layout.html` | CDN + 本地回退 | CDN 地址 `cdn.staticfile.org/jquery/1.12.4/jquery.min.js`；本地 `/static/js/jquery-1.12.4.min.js` |
| `login.html` | 仅本地 | 登录页独立引入 `/static/js/jquery-1.12.4.min.js` |

### 2.2 依赖的 jQuery 插件清单

| 插件                    | 版本   | jQuery 3.7.1 兼容性 | 风险等级 | 处理方案                                                |
| ----------------------- | ------ | -------------------- | -------- | ------------------------------------------------------- |
| **Bootstrap**           | 3.3.5  | ⚠️ 需升级             | 中       | 升级到 3.4.1 (最后支持 jQuery 3.x 的 BS3 版本)          |
| **jQuery UI**           | 1.12.1 | ✅ 兼容               | 低       | 1.12.1 已支持 jQuery 3.x，无需升级                      |
| **Layer (弹层)**        | 3.x    | ⚠️ 可能有问题         | 中       | 内部可能使用废弃 API，需运行时验证                      |
| **jQuery Cookie**       | 1.4.1  | ✅ 兼容               | 低       | 无已知兼容问题                                          |
| **jQuery Fly**          | 1.0.0  | ✅ 兼容               | 低       | 代码简单，无废弃 API 使用                               |
| **jQuery Dragsort**     | 0.5.2  | ⚠️ 需验证             | 中       | 老旧插件，可能使用已移除 API，需运行时测试              |
| **jQuery Contextify**   | 1.0.7  | ⚠️ 需验证             | 中       | 右键菜单插件，需运行时测试                              |
| **jQuery QRCode**       | 0.18.0 | ✅ 兼容               | 低       | 无已知兼容问题                                          |
| **Validform**           | 5.3.2  | ⚠️ 高风险             | 高       | 2013年停更，很可能使用大量废弃 API，需重点运行时验证    |
| **LayDate**             | 5.0.9  | ✅ 兼容               | 低       | 有独立 DOM 引擎，不强依赖 jQuery                        |
| **xm-select**           | -      | ⚠️ 需验证             | 中       | 需确认是否依赖 jQuery                                   |

### 2.3 项目代码中的废弃 API 使用统计

通过静态扫描，当前项目代码中使用了以下**在 jQuery 3.x 中废弃或行为变更**的 API：

| 废弃 API | 替换方案 | 出现位置 | 次数 |
|----------|----------|----------|------|
| `$.parseJSON()` | `JSON.parse()` | `index.js`, `public.js` | ~8 处 |
| `$.trim()` | `String.prototype.trim()` | `setting.html`, `soft.js` | ~4 处 |
| `.bind()` | `.on()` | `site.js`, `public.js`, `files.js` | ~3 处 |
| `.unbind()` | `.off()` | `site.js`, `public.js`, `index.js`, `config.js`, `crontab.js` | ~18 处 |
| `$(document).ready()` | `$(function(){})` | `layout.html` | 1 处 |
| `$.globalEval()` | 行为变更(异步) | `layout.html` Pjax 逻辑 | 1 处 |

> **注意**: `.bind()`/`.unbind()` 在 3.x 中仍可用但已废弃，会在未来版本移除。建议一并替换。

---

## 三、升级流程 (四阶段)

### 阶段 1：静态扫描与自动修复 ⏱ 预计 1 天

> 目标：利用脚本自动修复所有**可确定性替换**的废弃 API

#### 1.1 编写静态扫描修复脚本

创建 `scripts/jq_migrate_scan.py` (Python 脚本，避免引入 Node.js 依赖)：

```python
"""
jQuery 废弃 API 静态扫描与自动修复脚本

功能：
1. 扫描 web/ 目录下所有 .js 和 .html 文件
2. 检测已知的废弃 jQuery API
3. 生成修改报告 (--report 模式)
4. 自动替换 (--fix 模式，会先备份原文件)
"""
```

**替换规则表 (脚本核心逻辑)**:

```
# 安全的确定性替换 (--fix 可自动执行)
$.parseJSON(x)        → JSON.parse(x)
$.trim(x)             → (x).trim()    # 需注意 x 为变量时加括号
.bind('event', fn)    → .on('event', fn)
.unbind('event')      → .off('event')
.unbind()             → .off()
.delegate(sel, ev, fn)→ .on(ev, sel, fn)
.undelegate()         → .off()
.size()               → .length

# 需人工审查的替换 (--report 仅标记，不自动改)
$(document).ready(fn) → $(fn)          # 语义等价但需确认上下文
$.globalEval()        → 3.x 行为变更(异步)，需单独处理
```

#### 1.2 执行扫描

```bash
# 先以报告模式运行，查看待修改项
python scripts/jq_migrate_scan.py --report

# 确认无误后，执行自动修复（会在同目录生成 .bak 备份）
python scripts/jq_migrate_scan.py --fix

# 用 git diff 逐一审查修改
git diff --stat
git diff web/static/app/
```

#### 1.3 手动修复标记项

- `$.globalEval()` — 项目 Pjax 逻辑中用于执行动态加载的内联脚本，在 jQuery 3.x 中行为变为**异步**。需要改为手动创建 `<script>` 标签注入 DOM 的方式。详见第四节。
- 第三方插件中的废弃 API — 若插件为 min.js 且无法修改源码，则依赖 Migrate 插件兜底。

---

### 阶段 2：引入 jQuery 3.7.1 + Migrate 插件 ⏱ 预计 1-2 天

#### 2.1 下载所需文件

```
static/js/jquery-3.7.1.js            # 开发版（带完整报错信息）
static/js/jquery-3.7.1.min.js        # 生产版
static/js/jquery-migrate-3.4.1.js    # 迁移兼容插件（开发版）
static/js/jquery-migrate-3.4.1.min.js # 迁移兼容插件（生产版）
```

> **关键说明**: 本项目从 1.12.4 直接升到 3.7.1，不需要 jquery-migrate-1.x。
> Migrate 1.x 用于 jQuery 1.x → 2.x 的过渡，Migrate 3.x 用于 jQuery 1.x/2.x → 3.x 的过渡。
> **jquery-migrate-3.4.1 可以直接从 1.x 迁移到 3.x**，无需中间步骤。

#### 2.2 修改引入模板

**`layout.html` 修改**:

```html
<!-- jQuery -->
{% if data['use_cdn'] == 'yes' %}
<script src="https://cdn.staticfile.org/jquery/3.7.1/jquery.min.js"></script>
<script>window.jQuery || document.write('<script src="/static/js/jquery-3.7.1.min.js"><\/script>')</script>
{% else %}
<script src="/static/js/jquery-3.7.1.js"></script>  <!-- 开发阶段用未压缩版 -->
{% endif %}

<!-- jQuery Migrate（开发阶段必须引入，生产环境移除） -->
<script src="/static/js/jquery-migrate-3.4.1.js"></script>
```

**`login.html` 修改**:

```html
<script type="text/javascript" src="/static/js/jquery-3.7.1.js?v={{config.version}}"></script>
<script src="/static/js/jquery-migrate-3.4.1.js"></script>
```

#### 2.3 升级 Bootstrap 3.3.5 → 3.4.1

Bootstrap 3.3.5 不兼容 jQuery 3.x，**必须同步升级到 3.4.1**：

```
static/js/bootstrap.min.js           # 替换为 Bootstrap 3.4.1
static/bootstrap-3.3.5/              # CSS 需要同步升级为 3.4.1（目录重命名为 bootstrap-3.4.1）
```

> Bootstrap 3.4.1 是 BS3 系列最终版本，官方已明确支持 jQuery 3.x。

#### 2.4 运行项目，观察控制台

1. 启动后端服务
2. 逐页访问所有功能页面
3. 打开 F12 控制台，关注 **黄色 `JQMIGRATE` 警告**
4. 记录所有警告信息，逐一修复

---

### 阶段 3：浏览器自动化回归测试 ⏱ 预计 1-2 天

> 目标：用 Playwright 自动遍历所有页面，捕获 JQMIGRATE 警告和 JS 报错

#### 3.1 创建自动化测试脚本

创建 `scripts/jq_migrate_test.py`：

```python
"""
jQuery 升级回归测试脚本 (基于 Playwright)

功能：
1. 自动登录面板
2. 遍历所有菜单页面（通过分析 layout.html 中的菜单链接）
3. 捕获控制台中的 JQMIGRATE 警告和 JS Error
4. 生成结构化测试报告 (JSON + 可读文本)

依赖：
  pip install playwright
  playwright install chromium
"""
```

**测试报告输出示例**:

```json
{
  "summary": {
    "pages_tested": 12,
    "total_warnings": 5,
    "total_errors": 0,
    "pass": true
  },
  "pages": [
    {
      "url": "/index",
      "warnings": [],
      "errors": [],
      "status": "PASS"
    },
    {
      "url": "/files",
      "warnings": [
        "JQMIGRATE: jQuery.fn.bind() is deprecated"
      ],
      "errors": [],
      "status": "WARN"
    }
  ]
}
```

#### 3.2 页面路由清单

测试需覆盖的所有前端页面路径：

| 页面 | URL | 核心 JS | 重点验证 |
|------|-----|---------|----------|
| 首页/仪表盘 | `/` | `index.js` | ECharts 图表、`$.parseJSON` |
| 网站管理 | `/site` | `site.js` | `.bind()`/`.unbind()` |
| 文件管理 | `/files` | `files.js` | jQuery UI 拖拽、右键菜单 (contextify) |
| 计划任务 | `/crontab` | `crontab.js` | `.unbind()` |
| 防火墙 | `/firewall` | `firewall.js` | — |
| 软件管理 | `/soft` | `soft.js` | `$.trim()` |
| 日志 | `/logs` | `logs.js` | — |
| 监控 | `/monitor` | — | — |
| 面板设置 | `/setting` | `config.js` + 内联 | `.unbind()`、`$.trim()`、`$.post()` |
| 登录页 | `/login` | 内联 | Validform 表单验证 |

#### 3.3 第三方插件专项测试

以下插件需要**手工或半自动化**重点测试：

| 插件 | 测试要点 | 操作步骤 |
|------|----------|----------|
| **Validform 5.3.2** | 表单验证是否正常触发 | 登录页输入非法值→提交→验证错误提示是否显示 |
| **Layer 弹层** | 弹窗、确认框、loading | 操作任意功能→观察 layer.open/layer.confirm/layer.load |
| **jQuery UI** | 拖拽排序、对话框 | 文件管理页→拖拽文件→右键菜单 |
| **jQuery Dragsort** | 菜单拖拽排序 | 面板设置→菜单排序 |
| **xm-select** | 下拉多选 | 涉及多选的页面操作 |

---

### 阶段 4：清理与投产 ⏱ 预计 0.5-1 天

#### 4.1 移除 Migrate 插件

当阶段 3 的测试报告中：
- ✅ `total_warnings == 0`
- ✅ `total_errors == 0`

即可移除 Migrate 插件。

#### 4.2 切换到生产版本

```html
<!-- 最终生产配置 -->
<script src="/static/js/jquery-3.7.1.min.js"></script>
<!-- 不再需要 jquery-migrate -->
```

#### 4.3 清理文件

- [ ] 删除 `static/js/jquery-1.12.4.min.js`
- [ ] 删除 `static/js/jquery-migrate-3.4.1.js` 和 `.min.js`
- [ ] 删除 `static/js/jquery-3.7.1.js` (未压缩开发版)
- [ ] 删除扫描脚本生成的 `.bak` 备份文件
- [ ] 更新 CDN 回退地址（layout.html 中的 `cdn.staticfile.org/jquery/1.12.4/` 改为 `3.7.1`）
- [ ] 更新 Bootstrap CDN 地址为 3.4.1

#### 4.4 回归验证

再次运行阶段 3 的自动化测试脚本，确认纯净 jQuery 3.7.1 下零报错。

---

## 四、`$.globalEval()` 专项处理方案

`layout.html` 的 Pjax 逻辑中使用了 `$.globalEval()` 来执行动态加载的内联脚本：

```javascript
// 当前代码 (layout.html 约第 441 行)
$.globalEval(s.text);
```

**jQuery 3.x 变更**: `$.globalEval()` 改为**异步执行**（通过动态创建 `<script>` 标签），这意味着多段内联脚本的执行顺序可能被打乱。

**推荐修复方案** — 改用原生 DOM 方式同步执行：

```javascript
function runInlineScripts() {
    inlineScripts.forEach(function(s) {
        try {
            // 使用原生 script 注入 (同步执行，推荐)
            var script = document.createElement('script');
            script.text = s.text;
            document.head.appendChild(script).parentNode.removeChild(script);
        } catch(e) {
            console.error("Inline script error:", e);
        }
    });
}
```

> 此方式最接近 jQuery 1.x 中 `$.globalEval()` 的原始行为，且不依赖 jQuery。

---

## 五、回滚预案

如果升级后出现无法快速解决的严重问题：

1. **Git 回退**: 所有变更在独立分支进行，随时可回退到 `main` 分支
2. **文件回退**: 保留 `jquery-1.12.4.min.js`，模板中恢复引用即可
3. **渐进式回退**: 重新启用 Migrate 插件兜底，降低紧迫性

```bash
# 快速回退命令
git checkout main -- web/templates/default/layout.html
git checkout main -- web/templates/default/login.html
git checkout main -- web/static/js/
```

---

## 六、升级检查清单

### 准备阶段
- [ ] 创建 `feature/jquery-upgrade` 分支
- [ ] 下载 jQuery 3.7.1 (开发版+生产版)
- [ ] 下载 jQuery Migrate 3.4.1 (开发版+生产版)
- [ ] 下载 Bootstrap 3.4.1 (JS + CSS)
- [ ] 备份当前所有 JS 文件

### 阶段 1：静态扫描
- [ ] 编写 `jq_migrate_scan.py` 扫描脚本
- [ ] 以 `--report` 模式运行，审查报告
- [ ] 以 `--fix` 模式运行自动修复
- [ ] `git diff` 逐一审查所有自动修改
- [ ] 手动修复 `$.globalEval()` 相关逻辑

### 阶段 2：引入新版 jQuery
- [ ] 修改 `layout.html` 引入 jQuery 3.7.1 + Migrate
- [ ] 修改 `login.html` 引入 jQuery 3.7.1 + Migrate
- [ ] 替换 Bootstrap 3.3.5 → 3.4.1 (JS + CSS)
- [ ] 手动冒烟测试 (登录→首页→各页面快速点击)
- [ ] 修复控制台中的 JQMIGRATE 警告

### 阶段 3：自动化回归测试
- [ ] 编写 `jq_migrate_test.py` 测试脚本
- [ ] 运行全量页面回归测试
- [ ] 第三方插件专项手工测试 (Validform、Layer、jQuery UI)
- [ ] 修复所有测试发现的问题

### 阶段 4：清理投产
- [ ] 移除 Migrate 插件
- [ ] 切换到生产版 jQuery 3.7.1.min.js
- [ ] 更新 CDN 地址
- [ ] 删除旧版文件和备份
- [ ] 最终回归测试确认零报错
- [ ] 合并到 main 分支

---

## 七、预计工时

| 阶段 | 任务 | 预计工时 |
|------|------|----------|
| 阶段 1 | 静态扫描脚本编写 + 自动修复 + 审查 | 1 天 |
| 阶段 2 | 引入新版 jQuery + 基础适配 | 1-2 天 |
| 阶段 3 | 自动化测试 + 插件专项测试 + 修复 | 1-2 天 |
| 阶段 4 | 清理 + 投产 | 0.5 天 |
| **总计** | | **3.5-5.5 天** |
