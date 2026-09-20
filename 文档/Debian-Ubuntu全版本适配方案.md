# Debian / Ubuntu 全版本适配可行性方案

> 目标：让面板在 **Debian 10–14** 与 **Ubuntu 18.04–26.04** 共 10 个发行版上"装上就能用"，
> 且新增发行版时**只改清单、不改代码**。
>
> 编写日期：2026-09-20 ｜ 状态：待评审

---

## 一、目标支持矩阵

| 发行版 | 代号 | 面板本体 | OpenResty | PHP 源码编译 | PHP-APT | MySQL 源码编译 |
|---|---|---|---|---|---|---|
| Debian 10 | buster | ✅ | ✅ | 5.2–8.5 | ❌ 无 sury | 5.5–8.0 |
| Debian 11 | bullseye | ✅ | ✅ | 5.2–8.5 | ✅ | 5.5–8.4 |
| Debian 12 | bookworm | ✅ | ✅ | 5.2–8.5 | ✅ | 5.5–8.4 |
| **Debian 13** | **trixie** | **⚠️ 待修** | ✅ | 7.2–8.5 | ✅ | 5.7–9.x |
| Debian 14 | forky | ⚠️ 待验证 | ✅ | 待验证 | ✅ | 8.x–9.x |
| Ubuntu 18.04 | bionic | ✅ | ✅ | 5.2–7.4 | ✅ ondrej | 5.5–8.0 |
| Ubuntu 20.04 | focal | ✅ | ✅ | 5.2–8.5 | ✅ | 5.5–8.4 |
| Ubuntu 22.04 | jammy | ✅ | ✅ | 5.2–8.5 | ✅ | 5.5–8.4 |
| Ubuntu 24.04 | noble | ⚠️ 待修 | ✅ | 7.2–8.5 | ✅ | 8.0–9.x |
| Ubuntu 26.04 | resolute | ⚠️ 待验证 | ✅ | 待验证 | ✅ | 8.4–9.x |

**验收标准**：矩阵中每个 ✅ 单元格，必须由 CI 在对应容器里跑通「安装 → 起面板 → 装一个 Web 服务 → 装一个 PHP → 装一个 MySQL → 探活」全链路。

---

## 二、根因诊断

现状是「**按版本打补丁**」（patch-per-version），维护成本是 `发行版数 × 组件数 = 10 × 5 = 50` 个组合。证据：

| 位置 | 补丁形式 |
|---|---|
| `plugins/mysql/versions/5.5/install.sh:87` | 新增 `Install_dep_debain13()` |
| `plugins/mysql/versions/5.7/install.sh:88` | 新增 `Install_dep_debain13()` |
| `plugins/php/versions/72/install.sh:180` | `if VERSION_ID == "13"` |
| `plugins/php/versions/73/install.sh:180` | `if VERSION_ID == "13"` |
| `scripts/install/ubuntu.sh:139` | `if VERSION_ID == "22.04"` |
| `scripts/install/debian.sh:171` | `if VERSION_ID == "9"` 降级 requirements |

### 十个根因

| # | 根因 | 证据 | 后果 |
|---|---|---|---|
| R1 | 包清单硬编码、无版本感知 | `debian.sh:66-81`、`ubuntu.sh:57-71` | 新版本必崩 |
| R2 | 批量装失败后退化为逐包 | `debian.sh:32-37` | 掩盖问题，且慢 10 倍 |
| R3 | OS 事实重复解析约 20 处 | 全仓 `grep VERSION_ID` | 改一处漏十处 |
| R4 | codename 硬编码兜底 | `php-apt/install.sh:101` `\|\| echo "bookworm"` | Debian 13 会写错源 |
| R5 | 版本门槛散落各处 | `deploy.sh:328`、`php/index.py:1803` | 无法统一治理 |
| R6 | 依赖 `which` 命令 | 49 处调用 | Debian 13 直接失败 |
| R7 | Python 依赖无版本分档 | `version/` 只有 `r3.6~r3.8` | Python 3.13 未验证 |
| R8 | **`distutils` 已被 Python 3.12 移除** | `web/utils/system/update.py:34` | Debian 13 / Ubuntu 24.04 **静默失去更新检测** |
| R9 | **14 个死依赖** | 见 §6.3 | 无谓放大 3.13 兼容风险 |
| R10 | 无自动化验证 | `.github/workflows/*` 只有单 OS 手跑 | 回归靠人肉 |

> R8 特别说明：`from distutils.version import LooseVersion` 被 `try/except Exception` 包住，
> 不会崩，但会**永远返回 `none`**——即新版本永不提示。这是最隐蔽的一类故障。

---

## 三、核心思路

**从「枚举版本号」改为「探测能力」。**

不问"你是哪个版本"，改问"你有没有这个东西"。

三条设计原则：

- **P1 能力优先于版本号** — 能探测就不枚举。`libncurses5` 还是 `libncurses6`？让 apt 自己回答。
- **P2 声明式优于命令式** — 依赖写进清单文件，不写进 `if`。新增发行版 = 改数据。
- **P3 失败必须显式降级** — 缺包只降级不中断，但**必须打 WARN 并汇总**，不允许静默吞掉。

---

## 四、架构设计

```
scripts/
├── os_facts.sh        ← L1 新增：OS 事实唯一来源
├── os_caps.sh         ← L3 新增：能力矩阵
├── pkg_manifest.txt   ← L2 新增：声明式依赖清单
├── pkg_resolve.sh     ← L2 新增：清单解析 + 单事务安装
├── install/debian.sh  ← 改造：删掉 PACKAGES 数组，改调 L2
├── install/ubuntu.sh  ← 改造：同上（两文件趋同）
└── lib.sh             ← 改造：source L1，替换重复解析
```

### L1 — `scripts/os_facts.sh`：OS 事实唯一来源

替代全仓约 20 处 `cat /etc/*-release | grep VERSION_ID | awk ...`。

```bash
#!/bin/bash
# OS 事实唯一来源（只读、幂等、可重复 source）
[ "${YF_OS_FACTS_LOADED:-0}" = "1" ] && return 0
YF_OS_FACTS_LOADED=1

_yf_osrel=""
for _f in /etc/os-release /usr/lib/os-release; do
    [ -r "$_f" ] && { _yf_osrel="$_f"; break; }
done
_yf_get() { [ -n "$_yf_osrel" ] && sed -n "s/^$1=//p" "$_yf_osrel" 2>/dev/null | head -1 | tr -d '"'; }

OS_ID="${_yf_get ID}"
OS_VERSION_ID="${_yf_get VERSION_ID}"
OS_CODENAME="${_yf_get VERSION_CODENAME}"

# 老系统兜底（os-release 缺失 / 不完整）
if [ -z "$OS_ID" ]; then
    if   grep -Eqi 'Debian' /etc/issue 2>/dev/null; then OS_ID=debian
    elif grep -Eqi 'Ubuntu' /etc/issue 2>/dev/null; then OS_ID=ubuntu
    else OS_ID=unknown; fi
fi
[ -z "$OS_VERSION_ID" ] && OS_VERSION_ID=$(sed -n 's/.*VERSION_ID="\?\([^"]*\)"\?.*/\1/p' /etc/*-release 2>/dev/null | head -1)

# codename 兜底映射（老版本 os-release 常缺 VERSION_CODENAME）
if [ -z "$OS_CODENAME" ]; then
    case "${OS_ID}:${OS_VERSION_ID}" in
        debian:9)  OS_CODENAME=stretch;;  debian:10) OS_CODENAME=buster;;
        debian:11) OS_CODENAME=bullseye;; debian:12) OS_CODENAME=bookworm;;
        debian:13) OS_CODENAME=trixie;;   debian:14) OS_CODENAME=forky;;
        ubuntu:16.04) OS_CODENAME=xenial;;   ubuntu:18.04) OS_CODENAME=bionic;;
        ubuntu:20.04) OS_CODENAME=focal;;    ubuntu:22.04) OS_CODENAME=jammy;;
        ubuntu:24.04) OS_CODENAME=noble;;    ubuntu:26.04) OS_CODENAME=resolute;;
        *) OS_CODENAME="";;
    esac
fi

OS_MAJOR="${OS_VERSION_ID%%.*}"
OS_ARCH="$(uname -m)"
OS_BITS="$(getconf LONG_BIT)"
export OS_ID OS_VERSION_ID OS_CODENAME OS_MAJOR OS_ARCH OS_BITS

# ---- 谓词 ----
os_is_debian()    { [ "$OS_ID" = debian ]; }
os_is_ubuntu()    { [ "$OS_ID" = ubuntu ]; }
os_is_deb_family(){ [ "$OS_ID" = debian ] || [ "$OS_ID" = ubuntu ]; }
# 版本比较：os_ver_ge 12  → 当前 >= 12（同族内比较才有意义，先判族）
os_ver_ge() { [ "$(printf '%s\n%s\n' "$1" "$OS_VERSION_ID" | sort -V | head -1)" = "$1" ]; }
os_ver_lt() { ! os_ver_ge "$1"; }

# 命令探测（全仓替代 which）
has_cmd() { command -v "$1" >/dev/null 2>&1; }
```

**收益**：R3 归零；`php-apt` 的 codename 从 `lsb_release` 猜改为 `$OS_CODENAME`，修掉 R4。

### L2 — 声明式依赖清单 + 运行时解析

`scripts/pkg_manifest.txt`（节选，全量约 90 行）：

```
# 逻辑名|候选包名(逗号分隔，优先在前)|必需性|适用条件(bash 片段，可空)
build-base|build-essential|req|
cc|gcc|req|
cxx|g++|req|
cmake|cmake|req|
autoconf|autoconf|req|
automake|automake|req|
libtool|libtool|req|
bison|bison|req|
re2c|re2c|req|
flex|flex|req|
pkgconfig|pkg-config|req|
wget|wget|req|
curl|curl|req|
unzip|unzip|req|
tar|tar|req|
xz|xz-utils|req|
cron|cron|req|
bc|bc|req|
locales|locales|req|
which|which,debianutils|req|
# ↓ 这三条正是 Debian 13 的坑
ncurses|libncurses-dev,libncurses5-dev|opt|
pcre-dev|libpcre2-dev,libpcre3-dev|opt|
aio|libaio1t64,libaio1|opt|
aio-dev|libaio-dev|opt|
mecab|libmecab2|opt|
mm|libmm-dev|opt|
ldap-dev|libldap2-dev|opt|
jpeg-dev|libjpeg62-turbo-dev,libjpeg-dev|opt|
# ↓ 老系统专属，只在 Ubuntu < 20.04 / Debian < 11 生效
unwind|libunwind-dev|opt|
sasl|libsasl2-dev|opt|
# ↓ non-free，失败不报错
rar|rar|opt|unrar|unrar|opt|
recode|librecode-dev|opt|
```

`scripts/pkg_resolve.sh`：

```bash
#!/bin/bash
# 依赖解析 + 单事务安装（恢复 R2 的批量快路径）

# 一次性建索引，避免 90 次 apt-cache 调用
_yf_pkg_index() {
    local idx="${TMPDIR:-/tmp}/.yf_pkg_index"
    [ -s "$idx" ] || apt-cache pkgnames > "$idx" 2>/dev/null
    echo "$idx"
}
pkg_available() { grep -qxF "$1" "$(_yf_pkg_index)"; }
# resolve_pkg a b c → 输出第一个可用的候选
resolve_pkg() { local c; for c in "$@"; do pkg_available "$c" && { echo "$c"; return 0; }; done; return 1; }

yf_install_manifest() {
    local manifest="$1" resolved=() missing=()
    while IFS='|' read -r name cands need cond; do
        case "$name" in ''|\#*) continue;; esac
        [ -n "$cond" ] && ! eval "$cond" 2>/dev/null && continue
        local pick; pick=$(resolve_pkg ${cands//,/ })
        if   [ -n "$pick" ]; then resolved+=("$pick")
        elif [ "$need" = req ]; then missing+=("$name→[$cands]")
        fi
    done < "$manifest"

    # 必需包缺失必须显式告警（P3）
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "\e[1;31m[WARN] 必需依赖无法解析（可能影响后续编译）:\e[0m"
        printf '  - %s\n' "${missing[@]}"
    fi

    local uniq; uniq=$(printf '%s\n' "${resolved[@]}" | sort -u | tr '\n' ' ')
    local opts="--no-install-recommends -o Dpkg::Options::=--force-unsafe-io"
    echo "一次性安装 ${#resolved[@]} 个已解析依赖..."
    if ! apt-get install -y $opts $uniq; then
        echo "[WARN] 批量安装失败，逐包重试..."
        local p
        for p in $uniq; do apt-get install -y $opts "$p" || echo "  跳过: $p"; done
    fi
}
```

**关键改进**：所有包名**先验证存在**再进 apt，所以批量快路径不会再被一个不存在的包拖垮 —— 这同时修掉 R1 和 R2。

`scripts/install/debian.sh` / `ubuntu.sh` 改造后趋同：

```bash
curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
source ${rootPath}/os_facts.sh
source ${rootPath}/pkg_resolve.sh

apt-get update -y -o Acquire::Languages=none
yf_install_manifest ${rootPath}/pkg_manifest.txt
# 其余（locale / ufw / SSH 端口 / python-venv / curl 头链接）保持原样
```

两个文件从 ~150 行降到 ~60 行，且**内容基本一致**——Ubuntu/Debian 差异全部下沉到清单。

### L3 — `scripts/os_caps.sh`：能力矩阵

收敛 R5，把散落各处的版本门槛集中到一处。

```bash
#!/bin/bash
curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
source ${curPath}/os_facts.sh

cap_supported() {
    case "$1" in
      panel)     return 0;;                       # 全版本支持
      openresty) return 0;;                       # 自带 PCRE 8.45 + openssl_11，无外部依赖

      # PHP 5.2–5.6：需 openssl 1.0 自编译 + 老编译器容忍度
      php_old)   os_is_debian && os_ver_lt 13 && return 0
                 os_is_ubuntu && os_ver_lt 24.04 && return 0
                 return 1;;
      # PHP 7.0–7.4
      php_mid)   os_is_debian && os_ver_lt 14 && return 0
                 os_is_ubuntu && os_ver_lt 26.04 && return 0
                 return 1;;
      # MySQL 5.5：编译器要求最苛刻
      mysql55)   os_is_debian && os_ver_lt 13 && return 0
                 os_is_ubuntu && os_ver_lt 24.04 && return 0
                 return 1;;
      # MySQL 5.7：需 gcc ≤ 12
      mysql57)   os_is_debian && os_ver_lt 14 && return 0
                 os_is_ubuntu && os_ver_lt 26.04 && return 0
                 return 1;;
      # PHP-APT：sury(Debian) / ondrej(Ubuntu) 覆盖范围
      php_apt)   os_is_ubuntu && os_ver_ge 16.04 && return 0
                 os_is_debian && os_ver_ge 11 && os_ver_lt 15 && return 0
                 return 1;;
      *) return 1;;
    esac
}

# CLI：os_caps.sh php_old  → 退出码 0/1；os_caps.sh dump → 打印全部能力
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "$1" in
      dump) for c in panel openresty php_old php_mid mysql55 mysql57 php_apt; do
                cap_supported "$c" && echo "$c=1" || echo "$c=0"; done;;
      *)    cap_supported "$1";;
    esac
fi
```

调用方：

```bash
# shell 侧
source scripts/os_caps.sh
cap_supported php_old || { echo "当前系统不支持 PHP 5.x 源码编译"; exit 0; }
```

```python
# Python 侧（web/core/os_caps.py，进程内缓存一次）
import functools, subprocess

@functools.lru_cache(maxsize=1)
def _caps():
    out = subprocess.run(['bash', '/www/server/yufeng_panel/scripts/os_caps.sh', 'dump'],
                         capture_output=True, text=True).stdout
    return dict(l.split('=') for l in out.strip().splitlines() if '=' in l)

def capSupported(cap: str) -> bool:
    return _caps().get(cap) == '1'
```

替换掉现有的：
- `deploy.sh:328-334` 的 Debian/Ubuntu 硬编码门槛 → `cap_supported panel`
- `plugins/php/index.py:1803` 的 `int(sysId) > 10` → `capSupported('php_old')`
- `plugins/mysql/versions/5.5/install.sh:163-176` 的整段 `exit 0` → `cap_supported mysql55`

### L4 — 工具链自适应（干掉 `Install_dep_debain13`）

现在的写法是「Debian 13 → 装 gcc-12」，Debian 14 来了就得再加一个函数。改成**探测式**：

```bash
# 返回可用的 gcc 主版本号（空串表示用系统默认 gcc）
yf_pick_toolchain() {
    local want="${1:-12}" v
    # 1) 系统已有 → 直接复用
    for v in $want 13 11 10 9; do
        has_cmd "gcc-$v" && has_cmd "g++-$v" && { echo "$v"; return 0; }
    done
    # 2) apt 里可装的最新可用版本
    for v in $want 13 11 10; do
        if pkg_available "gcc-$v" && pkg_available "g++-$v"; then
            apt-get install -y "gcc-$v" "g++-$v" >/dev/null 2>&1 && { echo "$v"; return 0; }
        fi
    done
    # 3) 兜底系统默认
    has_cmd gcc && { echo ""; return 0; }
    apt-get install -y build-essential >/dev/null 2>&1 && { echo ""; return 0; }
    return 1
}

# 用法（替换 mysql/php 里所有 `which gcc` + Install_dep_debain13）
GCC_VER=$(yf_pick_toolchain 12)
if [ -n "$GCC_VER" ]; then WHERE_DIR_GCC="/usr/bin/gcc-$GCC_VER"; WHERE_DIR_GPP="/usr/bin/g++-$GCC_VER"
else WHERE_DIR_GCC="$(command -v gcc)"; WHERE_DIR_GPP="$(command -v g++)"; fi
```

**收益**：`Install_dep_debain13()` 可以直接删除；Debian 14 / Ubuntu 26.04 自动可用。

### L5 — `which` 依赖消除（R6）

两件事，先后有序：

1. **立刻**：`pkg_manifest.txt` 里加 `which|which,debianutils|req|` —— 一行修掉 Debian 13 的安装失败。
2. **系统性**：49 处 `` `which xxx` `` → `$(command -v xxx)`。批量替换规则：

```bash
# 示例：mysql/versions/5.7/install.sh
-  WHERE_DIR_GCC=`which gcc`
+  WHERE_DIR_GCC=$(command -v gcc)
```

优先处理编译链相关的 12 个文件（`mysql/versions/*`、`openresty/versions/*`、`php/versions/*`），
其余插件（redis / valkey / webstats）次之。

### L6 — Python 依赖分档（R7 / R8 / R9）

**步骤 1：删除死依赖。** 全仓 `grep` 确认零引用（测试除外）：

| 依赖 | 引用数 | 处理 |
|---|---|---|
| `flask-session==0.3.2` | 0 | 删除 |
| `flask-helper==0.19` | 0 | 删除 |
| `cache==1.0.3` | 0 | 删除 |
| `zmq==0.0.0` | 0 | 删除 |
| `flask-bcrypt==1.0.1` | 0（代码直接用 `bcrypt`） | 删除 |
| `flask-sockets==0.2.1` | 0 | 删除 |
| `whitenoise>5.3.0` | 0（`web/admin/__init__.py:91` 已注释） | 删除 |
| `supervisor` | 0 | 删除 |
| `SQLAlchemy` / `Flask-SQLAlchemy` | 0 | 删除 |
| `configparser==5.2.0` | 0（Python3 内置同名模块） | 删除 |
| `chardet` | 0 | 删除 |
| `brotli` / `zstd` / `zstandard` | 0（Flask-Compress 的可选加速器） | 删除（如需 br/zstd 压缩则保留） |
| `pyyaml` | 3 个文件在用 | **保留** |

> 一次删掉 14 个依赖，Python 3.13 的风险面直接缩小一大半。

**步骤 2：修 `distutils`（R8）。**

```python
# web/utils/system/update.py:34
-  from distutils.version import LooseVersion
-  if LooseVersion(new) > LooseVersion(now):
+  from packaging.version import Version
+  if Version(new) > Version(now):
```
`packaging` 已在 `requirements.txt` 中，无需新增依赖。

**步骤 3：补齐版本分档文件。** `lib.sh:252` 已有机制（`version/r${MAJOR}.${MINOR}.txt` 在基础
requirements 之后安装），但只有 `r3.6/r3.7/r3.8`。补齐：

- `version/r3.9.txt` / `r3.10.txt` / `r3.11.txt` / `r3.12.txt` / `r3.13.txt`
- 内容只需覆盖真正需要钉版的包：`gevent`、`cryptography`、`pyOpenSSL`、`Flask`、`Werkzeug`、`gunicorn`

同时把基础 `requirements.txt` 的语义从「钉死版本」改为「声明下界 + 已知破坏性上界」：

```
gevent>=24.10.0          # 3.13 wheel 支持
cryptography>=42.0.0
pyOpenSSL>=24.0.0
Werkzeug>=2.0,<4
Flask>=2.0
```

---

## 五、分阶段路线图

### Phase 0 — 止血（0.5 人天，零风险）

| 项 | 改动 | 文件 |
|---|---|---|
| P0-1 | 包清单加 `which` | `scripts/install/debian.sh`、`ubuntu.sh` |
| P0-2 | `distutils` → `packaging` | `web/utils/system/update.py:34` |
| P0-3 | codename 改用 `$OS_CODENAME` | `plugins/php-apt/install.sh:101` |
| P0-4 | 删 14 个死依赖 | `requirements.txt` |

**产出**：Debian 13 从「能装但慢 + 更新检测失效」变成「能装且功能完整」。

### Phase 1 — 结构化（1–2 人天）

| 项 | 改动 |
|---|---|
| P1-1 | 新增 `scripts/os_facts.sh` |
| P1-2 | 新增 `scripts/pkg_manifest.txt` + `scripts/pkg_resolve.sh` |
| P1-3 | `debian.sh` / `ubuntu.sh` 改为调用清单解析器 |
| P1-4 | `lib.sh`、各插件替换 `grep VERSION_ID` 为 `source os_facts.sh` |

**产出**：新增发行版 = 改清单，不改代码。

### Phase 2 — 能力化（2–3 人天）

| 项 | 改动 |
|---|---|
| P2-1 | 新增 `scripts/os_caps.sh` + `web/core/os_caps.py` |
| P2-2 | 收敛 `deploy.sh` / `php/index.py` / `mysql/versions/*` 的版本门槛 |
| P2-3 | 新增 `yf_pick_toolchain()`，删除 `Install_dep_debain13()` ×2 |
| P2-4 | 49 处 `which` → `command -v` |

**产出**：Debian 14 / Ubuntu 26.04 自动可用。

### Phase 3 — 验证体系（2–3 人天）

| 项 | 改动 |
|---|---|
| P3-1 | 新增 `test/os_matrix/smoke.sh`（容器内全链路探活） |
| P3-2 | 新增 `.github/workflows/os-matrix.yml`（10 镜像矩阵） |
| P3-3 | 新增 `scripts/selfcheck.sh`（线上自检，输出能力矩阵 + 解析结果） |
| P3-4 | `compatibility.md` 改为由 CI 结果自动生成 |

**总计：约 6–9 人天。**

---

## 六、验证体系

### 6.1 CI 矩阵

```yaml
name: OS Matrix
on: [workflow_dispatch, pull_request]
jobs:
  matrix-install:
    strategy:
      fail-fast: false
      matrix:
        image:
          - debian:10   # buster
          - debian:11   # bullseye
          - debian:12   # bookworm
          - debian:13   # trixie
          - debian:14-slim  # forky (testing)
          - ubuntu:18.04
          - ubuntu:20.04
          - ubuntu:22.04
          - ubuntu:24.04
          - ubuntu:26.04
    runs-on: ubuntu-latest
    container: ${{ matrix.image }}
    steps:
      - uses: actions/checkout@v4
      - name: 安装面板
        run: bash scripts/install.sh
      - name: 依赖解析自检
        run: bash scripts/selfcheck.sh --strict
      - name: 全链路冒烟
        run: bash test/os_matrix/smoke.sh
```

### 6.2 `smoke.sh` 断言项

1. 面板进程存活 + 端口 7200 可访问 `/login`
2. 依赖解析结果中 **必需包零缺失**
3. OpenResty 编译通过 + `nginx -t` 通过
4. 各装一个 PHP（老系统 7.2、新系统 8.3）并 `php-fpm -t` 通过
5. 各装一个 MySQL（老系统 5.7、新系统 8.0）并 `mysqladmin ping` 通过
6. `scripts/selfcheck.sh` 输出的能力矩阵与 `compatibility.md` 一致

### 6.3 `selfcheck.sh`（线上自检）

用户报障时只需跑一条命令，即可拿到：

```
OS: debian 13 (trixie) x86_64 64bit
Python: 3.13.5
能力: panel=1 openresty=1 php_old=0 php_mid=1 mysql55=0 mysql57=1 php_apt=1
依赖解析: 86 个候选命中 84，缺失必需包 0 个
  降级项: pcre-dev→libpcre2-dev, aio→libaio1t64, ncurses→libncurses-dev
```

---

## 七、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `apt-cache pkgnames` 在极老 apt 上输出差异 | 索引为空 → 全部判为缺失 | 回退：索引为空时改用 `apt-cache show <pkg>` 逐个探测 |
| 老 PHP（5.2–5.6）在 gcc-13+ 上编译失败 | 编译中断 | 能力矩阵限定 `php_old` 仅在老系统可用；工具链对老 PHP 固定要求 `≤ gcc-12` |
| 单个 apt 事务过大引发 dpkg 冲突 | 安装失败 | 保留逐包回退（已有），并补日志 |
| 用户已配置自定义源 / 钉版 | 解析结果与预期不符 | 解析器只读不写；仅在必需包缺失时告警，绝不擅自改源 |
| 改动面大，回归风险 | 老系统被改坏 | Phase 0 先行且独立可回滚；每阶段由 CI 矩阵守门 |
| `brotli`/`zstd` 若被 nginx 侧间接依赖 | 压缩能力下降 | 删除前确认：`grep -r brotli web/` 结果为 0，且压缩由 OpenResty 负责 |
| `debian:10` / `ubuntu:18.04` 镜像已归档 | CI 拉取失败 | 使用 `old-releases` 源或改用 `docker pull` 固定 digest 的自建镜像 |

---

## 八、本方案不改变的部分

- 现有目录结构、插件开发规范、`info.json` 约定
- 现有 fail-soft 行为（保留为最后兜底，只是不再当主路径）
- 现有 OpenSSL 自编译方案（`plugins/php/lib/openssl_10.sh` / `openssl_11.sh`）
- 前端 i18n 体系与 `test/` 临时文件约定

---

## 九、结论

**可行，且成本可控（约 6–9 人天）。**

核心不是"再为 Debian 13 打一个补丁"，而是把「版本枚举」换成「能力探测」：

- **Phase 0** 半天即可让 Debian 13 达到可用状态；
- **Phase 1 + 2** 之后，Debian 14 / Ubuntu 26.04 及以后的新版本**自动可用**，无需再写新分支；
- **Phase 3** 把回归验证从人肉变成 CI 守门。

建议先做 Phase 0 验证收益，再决定是否继续 Phase 1–3。
