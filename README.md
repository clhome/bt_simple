<p align="center">
  <img src="https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/yflogo.webp" width="360" />
  <h3 align="center">Yufeng Panel (BtSimple)</h3>
  <p align="center">A lightweight, security-hardened Linux server management panel built with Python</p>
  <p align="center">
    <b>English</b> | <a href="README_cn.md">Chinese (Simplified)</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/License-Apache--2.0-green.svg" />
    <img src="https://img.shields.io/badge/Python-3.7+-blue.svg" />
    <img src="https://img.shields.io/badge/OS-Linux-orange.svg" />
  </p>
</p>

---

## 🚀 Introduction

> 💡 **Beginner's Guide**: If you are new to Linux servers and panel operations, we strongly recommend reading our [📖 Illustrated User & Operations Manual (Chinese)](文档/御风面板说明书/说明书.md).

**Yufeng Panel (BtSimple)** is a fully open-source, lightweight Linux server management panel originated from the [mdserver-web](https://github.com/midoks/mdserver-web) project. Adhering to the **KISS (Keep It Simple, Stupid)** principle, it strips away redundant features and bloatware, focusing squarely on core website management, database operations, and system security hardening.

This project has undergone comprehensive security audits and deep performance optimizations over the original codebase, aiming to deliver a robust, highly transparent, and resource-efficient server administration platform.

![Login Page](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260630174158629.png)

### Core Features

- **Lightweight & High Efficiency**: Compared to traditional panels, BtSimple consumes minimal system resources and is perfectly suited for small-memory VPS environments.

![Dashboard](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/index.webp)

- **Security Hardening**:
  - **Source-Level Security Audit & Backdoor Removal**: Systematic audit of all source code and dangerous calls. Known backdoor or supply-chain poisoning vectors have been completely removed, ensuring no covert remote control channels exist. Note that this is **not zero network dependency**: operations like updates, environment provisioning, and metadata queries contact external endpoints as detailed in the "Functional Outbound Network Request List" below.
  - **Python Critical Dependencies Hardening**: Lower bounds for essential packages in `requirements.txt` have been tightened (e.g., `paramiko>=3.4.0` against SSH Terrapin / CVE-2023-48795), CVE mitigation lower bounds enforced across all dependencies, and obsolete dead dependencies (such as legacy `chardet`) completely removed.
  - **Smart Mirror Acceleration for Mainland China**: Rebuilt plugin and third-party compilation scripts to support "Global Official Upstream Direct Connection + Domestic Smart Mirror Acceleration (`mirror.ghproxy.com`)", eliminating the need for manual large-file uploads and providing ultra-fast installation across diverse network conditions.
  - Upgraded password storage hashing algorithm to `bcrypt`.
  - **Enforced Minimum TLS 1.2 for HTTPS**: When panel HTTPS is enabled, Gunicorn's `ssl_context` explicitly sets `minimum_version = TLSv1_2` (`web/setting.py`), rejecting legacy insecure SSL/TLS negotiations.
  - Intelligent IP ban mechanism against brute-force attacks; Fail2ban upgraded with **global site protection** and **strict validation mode**.
  - CSRF protection (dual Token and Referer validation) and path traversal blacklist detection (with extra verification on archive member unpacking and critical endpoints); Yufeng OP Firewall features **full-domain honeypot bait blocking** that triggers physical blocking upon keyword matching under any directory.
  - **Double Confirmation on Uninstallation & Deletion**: Software uninstallation and MySQL database deletion require typing the resource name for secondary confirmation. **Plugin uninstallation defaults to "Pack and backup core data before uninstalling"** (can be manually unchecked). MySQL database deletion does not automatically back up (please use the panel's backup feature beforehand) to minimize accidental data loss risks.

  ![Security](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260630174852542.png)

- **Scheduled Tasks Deep Refactoring**:
  - **Modal-Based Management**: Task creation and editing moved to clean modals.
  - **Import / Export**: Supports JSON-based backup and cross-platform migration of cron jobs.
  - **Smart Scheduling Policies**: Supports cloud date constraints such as stock trading days, working days, and statutory holidays.
  - **Log Viewer Enhancements**: Dynamically expandable log box height, 5-second auto-refresh, automatic log popup upon task execution, and friendly empty-state display.
  - **Efficient Operations**: Supports fuzzy search, dynamic multi-field sorting, and real-time execution timestamp persistence.

  ![Cron](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260605163440643.png)

- **File Manager UX Optimization**:
  - **Multi-Tab Support**: Browser-style concurrent multi-directory browsing with local tab state persistence.

  ![Multi-Tab](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260605164326823.png)
  - **Full-Screen Drag & Drop**: Deep support for recursive file and folder drag-and-drop upload, preserving directory structures automatically.
  - **Pre-Upload Inspection List**: Detailed statistics presented before upload, prominent `(Will Overwrite)` alerts for matching names, and precise side-by-side file size comparisons (e.g., `18.1KB <= 17.56KB`).

  ![File Manager](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260605164605516.png)

- **Dashboard Extreme Loading & Core Dependency Refactoring**:
  - **On-Demand Lazy Loading**: Stripped the 336KB global ECharts bundle from global loading; it is now dynamically loaded only when rendering the dashboard and monitoring pages, drastically reducing initial page weight and HTTP requests.
  - **Core Dependency Modernization**: Fully upgraded to production minified jQuery 3.7.1, completely purging legacy jQuery 1.12.4 and Migrate compatibility scripts; upgraded CodeMirror to 5.65.16, resolving markdown editor initialization failures and `t.lookAhead is not a function` runtime errors.
  - **High-Speed CDN & Font Declaration Overhaul**: Core common styles and scripts hosted via Staticfile CDN for improved access speed on high-latency hosts; rewritten Glyphicons Halflings font declarations with `font-display: block` to eliminate font loading warnings on slow connections.
  - **Automatic Dual Local Fallback**: Zero-latency fallback mechanism using CSS `onerror` and JS global variable checks. If CDN access is blocked or fails, static assets automatically fall back to local server files within tens of milliseconds, guaranteeing full usability in offline, air-gapped, or intranet environments.

- **High-Frequency Monitoring Zero-Blocking & API Performance Breakthroughs**:
  - **Non-Blocking Zero-Hang Architecture**: Completely refactored `getCpuInfo` to eliminate the synchronous `psutil` blocking bug that previously stalled worker threads for a full 1.0 second, speeding up dashboard API response by over 10x (author benchmark, environment-dependent; see `scripts/bench/README.md`).
  - **Mathematical Average Calculation**: Leveraged the principle that "total CPU utilization equals the arithmetic mean of individual cores" to eliminate a redundant, conflicting `psutil.cpu_percent` syscall.
  - **Network IO Counter O(1) Loop Hoisting**: Hoisted repeated `psutil.net_io_counters(pernic=True)` syscalls out of interface loops in `stats.py`, reducing resource overhead from O(N) to O(1) on complex multi-NIC or containerized hosts.
  - **High-Frequency API Performance**: Introduced incremental caching, multi-threaded concurrency, and dynamic property pagination lazy loading: App Store list API (`/plugins/list`) response time dropped from **800ms to 9ms**; batch plugin status execution (`/plugins/run_batch`) parallelized from **400ms to 160ms**; SSH terminal management response latency drastically reduced. *(Benchmark figures reflect author local tests; reproducible scripts located at `scripts/bench/README.md`.)*
  - **Instant Load for Dashboard Status**: Dashboard "Load Status" defaults to 0% and eliminates flickering "Loading..." overlays, delivering a snappy, seamless user experience.

- **High-Fidelity Visual & Micro-Interaction Polish**:
  - **Frosted Glassmorphism**: Dashboard Status, Overview, Software, and Traffic/IO cards enhanced with premium Glassmorphism, `backdrop-filter`, and soft ambient lighting.
  - **Physics-Inspired Elastic Micro-Interactions**: Software grid icons and overview widgets feature hover float elevation with rounded corners, and active depression `scale(0.96)` with bezier curves. The dashboard layout is compactly optimized to fit within a single screen across most resolutions without redundant scrollbars.
  - **Lightning-Fast Global Menu Customization**: Dynamic left sidebar menu toggle and drag-and-drop reordering. Built upon an in-memory process cache + JSON persistence architecture rather than heavy database lookups, ensuring personalized navigation with **zero disk I/O** on page refreshes.
  - **Update Dialog & Interaction Polish**: Fixed unclickable close button in the panel update modal, aligned markdown changelog lists using flexbox, introduced a global loading spinner during update checks, and resolved label ID collisions in firewall settings.

  ![System Details](https://raw.githubusercontent.com/clhome/bt_simple/master/文档/御风面板说明书/说明书.assets/image-20260630174623767.png)

- **Software Management & Website Configuration Enhancements**:
  - **Expanded Software Grid**: Dashboard software grid expanded from 4 columns to `col-lg-2` (6 icons per row), increasing maximum display capacity from 12 to 18 icons.
  - **Official Curated Ecosystem vs. Isolated Third-Party Plugins**: Display logic redesigned to present official certified plugins by default. A top-right settings gear modal allows toggling third-party or custom plugins with prominent `(Third-Party)` warning badges, maintaining ecosystem purity without sacrificing extensibility.
  - **Enriched Website Details & One-Click Takeover / Restore**: Website tables now display daily traffic estimations, active PHP versions, and SSL certificate validity days remaining. Added "Website List Migration & Restore", supporting automated scanning of backup `site.db` paths or manual path input, with asynchronous background reading and unbuffered real-time streaming web logs for seamless site takeover.
  - **90-Day Free Panel SSL**: Panel SSL fully adapted for 90-day free automated certificate issuance via Let's Encrypt / ACME, with automatic bridge site creation, seamless ACME HTTP challenge validation, certificate installation, and panel restarts.
  - **Double-Check Protection & Package Cache Cleaner**: Secondary name confirmation enforced on plugin uninstallation with **"Pack and backup core data to `/www/backup` before uninstalling" enabled by default**; added one-click package cache cleaner to reclaim disk space.
  - **PHP Process Force-Kill & Mirror Adaptation**: Added "Force Kill Process" in PHP management to quickly reclaim resources during deadlocks or high-load freezes; Docker and related plugin installation scripts adapted for Aliyun, Tsinghua, and other domestic mirrors for fault tolerance.

- **Docker Container Smart Disaster Recovery Management**:
  - Fixed multiple command injection vulnerabilities; added visual Mirror accelerator management. Pioneered an **automatic node failover retry** mechanism on image pull failures, ensuring rapid container deployment under constrained networks while intercepting false-positive errors.

- **All-in-One Management**: Pre-integrated environments including OpenResty, MySQL, PHP, Redis, MongoDB, and more.
- **Modular Plugin Architecture**: Highly decoupled functionality, installed on demand, supporting custom plugin development.
- **Broad Compatibility**: Seamless one-click migration from **mdserver-web** or **Baota Panel (BT.CN)**.

### Functional Outbound Network Request List

The panel is **not zero network dependency**. The outbound requests listed below are functional (updates, environment provisioning, metadata queries). There are no telemetry backdoors or remote control channels in the codebase. However, **environments with strict egress controls, air-gapped networks, or intranet deployments should review each item prior to deployment**. Egress switches are provided in the panel settings: "Disable Third-Party Outbound Requests" (`disable_ext_net`, **default `no` = enabled**); when disabled, external queries gracefully return fallback values without making network calls. Installation telemetry can be disabled by setting `YF_NO_TELEMETRY=1`.

| Scenario | Destination / Target | Description |
| --- | --- | --- |
| Panel Installation / Updates | `panel.yftec.top`, `raw.githubusercontent.com`, `gh-proxy.org` / `mirror.ghproxy.com` | `deploy.sh` pulls release archives and code; critical artifacts are verified via Ed25519 signatures |
| Runtime Environment / Plugin Installation | Official distribution repositories, Aliyun / Tsinghua mirrors, Remi / sury / ondrej third-party repositories | Accessed on demand when installing PHP, MySQL, OpenResty, etc. |
| Frontend Static Assets | Staticfile CDN | Core JS/CSS loads from CDN with automatic fallback to local server static files (**offline / LAN compatible**) |
| Scheduled Tasks Holiday / Workday Policy | `timor.tech` Holiday API | Accessed only when cloud-based holiday calendar policies are configured |
| Login Logs / Probe IP Geolocation | `ip-api.com`, `whois.pconline.com.cn`, `ipinfo.io` | Queries client IP geolocation with multi-channel automatic fallback; failures do not impact authentication |
| Installation Complete Notice | `www.yftec.top` Counter API | Single request upon installation completion to retrieve "User #N" count; transmits standard browser headers without any server or panel data (origin IP visible to server). Disable with `YF_NO_TELEMETRY=1`. |

---

## 🐧 System Compatibility

> For the detailed per-component validation matrix (Panel / OpenResty / PHP versions / MySQL versions), refer to [`compatibility.md`](compatibility.md).

### ✅ Verified & Supported

| Distribution Family | Verified Versions | Panel | OpenResty | PHP | MySQL |
| --- | --- | --- | --- | --- | --- |
| Debian | 10 / 11 / 12 | ✅ | ✅ | ✅ | ✅ |
| Ubuntu | 18.04 / 20.04 / 22.04 / 24.04 | ✅ | ✅ | ✅ | ✅ |
| CentOS | 7.9 / 8.4 / 8 Stream / 9 Stream | ✅ | ✅ | ✅ | ✅ |
| AlmaLinux | 9 | ✅ | ✅ | ✅ | ✅ |
| RockyLinux | 8.6 | ✅ | ✅ | ✅ | ✅ |
| Fedora | 31 / 32 | ✅ | ✅ | ✅ | ✅ |
| Arch Linux | rolling | ✅ | ✅ | ✅ | ✅ |
| openSUSE | 15.4 | ✅ | ✅ | ✅ | ✅ |
| openEuler | 22.03 | ✅ | ✅ | ✅ | ✅ |
| Amazon Linux | Detection & installation adapted | ✅ | ✅ | ✅ | ✅ |
| Anolis OS | Mapped to RHEL branch | ✅ | ✅ | ✅ | ✅ |

> Debian derivatives like Deepin and Raspbian automatically follow the Debian branch via `ID_LIKE=debian`.

### ⚠️ Pending Adaptation / Unverified

The panel **can be installed and run** on the following distributions, but known gaps exist and they have not yet been fully included in the official validation matrix.

#### Debian 13 (trixie) — Installable, with 5 system package gaps adapted

| Gap / Area | File Location | Status & Description |
| --- | --- | --- |
| `libncurses5` / `libncurses5-dev` | ~~`scripts/install/debian.sh:69`~~ ✅ | Adapted: Debian 13 branch switches to `libncurses-dev` |
| `libpcre3` / `libpcre3-dev` | ~~`scripts/install/debian.sh:73`~~ ✅ | Adapted: Debian 13 branch switches to `libpcre2-dev` |
| `libaio1` | ~~`scripts/install/debian.sh:69`~~ ✅ | Adapted: Debian 13 branch switches to `libaio1t64` (symlink fallback preserved) |
| `which` Command Dependency | ~49 calls across repository ✅ | Adapted: Debian 13 explicitly installs `which` package (idempotent) |
| Panel Update Detection | ~~`web/utils/system/update.py:34`~~ ✅ | Adapted: Prefers `packaging.version`, falls back to `distutils` |
| Python 3.13 Dependency Branching | `requirements.txt` / `version/` ✅ | Adapted: Added `version/r3.13.txt`; 14 zero-reference legacy dependencies scheduled for cleanup |
| MySQL Non-LTS Versions | `plugins/mysql/info.json` | **Delisted** (2026-10-27): 5.5/5.6 (EOL) and 8.2/8.3/9.0~9.4 (Innovation short-term releases) are no longer offered; only LTS releases are retained (5.7 / 8.0 / 8.4 / 9.7). Existing installations can upgrade to corresponding LTS with one click |
| MariaDB Non-LTS Versions | `plugins/mariadb/info.json` | **Delisted** (2026-10-27): Only LTS releases retained (10.6 / 10.11 / 11.4 / 11.8). Rolling short-term versions (10.7~10.9, 11.0~11.3, 11.5~11.7, 12.x non-LTS) delisted; existing installations can upgrade to nearest series LTS |
| Redis Version Selection | `plugins/redis/info.json` | **Converged into 3 series** (2026-10-28): Redis 7.2 (Default recommended) / 8.2 (LTS) / 6.2 (Lightweight). 12 patch versions removed from UI; panel automatically resolves chosen series to **its latest patch release** (e.g., 7.2 → 7.2.17) |
| PHP 5.2–5.6 Source Compilation | `plugins/php/versions/5{2..6}/install.sh` ✅ | Adapted: Debian 13 explicitly identifies non-support and exits gracefully |
| Docker Images | `docker/Dockerfile.debian13` ✅ | Adapted: Added `debian:13-slim` variant, retaining 12 as base |

> **MySQL Version Policy (2026-10-27)**: Installation catalog retains only **LTS** releases: `5.7`, `8.0`, `8.4`, and `9.7` (both 8.4 and 9.7 are official LTS; 8.2/8.3/9.0~9.4 are Innovation short-term releases supported only until the next innovation release, unsuitable for production; 5.5/5.6 are long EOL and require OpenSSL 1.0.x which fails to build against OpenSSL 3.x).
>
> **Existing installations remain unaffected with one-click upgrade options**: The App Store marks delisted versions with a red "Delisted" badge and provides an "Upgrade to X" button (where X is the **same major branch LTS**: 5.5/5.6 → 5.7, 8.2/8.3 → 8.4, 9.0~9.4 → 9.7). Upgrading is optional. Clicking upgrade triggers `install.sh` to **first perform a full backup of `server/mysql` (including data)**. If backup fails, the upgrade halts immediately. If the new version fails to start or self-check, it **automatically rolls back** (restoring the previous directory). Cross-major version upgrades (5.x → 8.x/9.x) are refused due to data dictionary incompatibilities.
>
> Test guards: `testsuite/test_mysql_min_install_branch.py`, `testsuite/test_mysql_lts_upgrade.py`.

> **MariaDB Version Policy (2026-10-27)**: Installation catalog retains only **LTS** releases: `10.6`, `10.11`, `11.4`, and `11.8` (verified via MariaDB REST API `downloads.mariadb.org/rest-api/mariadb/`). Delisted short-term releases provide **one-click upgrades** to the closest LTS: 10.7~10.9 → 10.11, 11.0~11.3 → 11.4, 11.5~11.7 → 11.8. MariaDB 10.6 maintenance ended on **2026-07-06**; the panel flags it as "Maintenance Ended" and suggests upgrading to 10.11.
>
> Test guards: `testsuite/test_mariadb_lts_upgrade.py`.

> **Redis Version Policy (2026-10-28)**: Redis catalog consolidated into **3 series**: `7.2` (Classic stable / Open-source license / Production default), `8.2` (LTS / Long-term evolution), and `6.2` (Minimal lightweight / Suitable for 512MB RAM).
>
> **Series-to-Patch Resolution**: Handled dynamically during installation (`web/core/redis_release_index.py`: crawls `download.redis.io/releases/` with 12h cache and fallback table; resolves 7.2 → `7.2.17`, 8.2 → `8.2.11`, 6.2 → `6.2.24`). Upstream patch releases require zero frontend changes.
>
> **Safe Upgrades**: Same major version upgrades supported (`7.2.13` → upgrade to `7.2.17`; legacy `7.0.15`/`6.0.20`/`8.0.6` marked "Delisted" with upgrade paths). Upgrades perform: stop service → backup data + config (verifying disk space) → compile to temp prefix → replace binaries → start & verify `redis-server -v` → **auto rollback on any failure**. Downgrades are rejected to protect RDB/AOF compatibility.
>
> Test guards: `testsuite/test_redis_version_series.py` (47 items).

> **Completed Adaptations**: MySQL 5.7 / 8.x (`Install_dep_debain13()` uses gcc-12 toolchain), PHP 7.2 / 7.3 (reentrancy patch injected), Swap plugin (switched to `shutil.which`).

#### Debian 14 (forky) / Ubuntu 26.04 (resolute)

Contains all Debian 13 considerations, plus:

| Missing Item | Location | Description |
| --- | --- | --- |
| Toolchain adaptation | `plugins/mysql/versions/*/install.sh` | Currently only hardcoded `Install_dep_debain13()`; newer versions lack dedicated branches |
| t64 Library Rename | `scripts/install/ubuntu.sh:60` | Same `libaio1` → `libaio1t64` transition |
| Third-Party Repository Verification | `plugins/php-apt/install.sh:101` | sury (Debian) / ondrej (Ubuntu) coverage on newest versions unverified |

#### CentOS / AlmaLinux / Rocky 10 (EL10)

| Missing Item | Location | Description |
| --- | --- | --- |
| Remi Repository Hardcoded el9 | `scripts/install/rhel.sh:52` | Exact match on `VERSION_ID == "9"`; EL10 does not automatically install Remi repository |
| EPEL / Remi el10 Availability | — | Awaiting confirmation of official el10 package availability |
| Package List Branching | `scripts/install/rhel.sh:170+` | Uses `VERSION_ID >= 8`; package name changes in el10 not yet addressed |

#### Fedora 33+ / openEuler 24.x and Newer

| Missing Item | Description |
| --- | --- |
| Validation Matrix Coverage | `compatibility.md` currently covers Fedora 31/32 and openEuler 22.03 |
| Third-Party Repositories | `plugins/php-yum/install.sh:73` dynamically constructs Remi URLs, but newer Fedora releases are unverified |

#### Alpine Linux

| Missing Item | Location | Description |
| --- | --- | --- |
| OS Identification | `scripts/getos.sh` | Lacks `Alpine` branch; identified as `unknow` |
| Plugin Ecosystem | `scripts/install/alpine.sh` | Base script exists, but PHP / MySQL / OpenResty plugins unverified |

#### Aliyun / Alibaba Cloud Linux

| Missing Item | Location | Description |
| --- | --- | --- |
| Missing Installation Script | `scripts/install/` | `getos.sh:25` outputs `OSNAME=aliyun`, but **`aliyun.sh` is missing**, causing installation failure |
| Inconsistent Detection | `scripts/install.sh` | Main installer lacks an `Aliyun` branch |

> Alibaba Cloud: Systems based on Anolis are mapped to RHEL and work normally. If `/etc/os-release` specifies `ID=alinux` or `ID=aliyun`, `scripts/install/aliyun.sh` should be created (or symlinked to `rhel.sh`).

### ❌ Explicitly Unsupported (EOL)

| Distribution | Enforced Location | Description |
| --- | --- | --- |
| CentOS 6 and older | `deploy.sh:314` | Explicitly rejected |
| Debian 9 and older | `deploy.sh:330` | Explicitly rejected (Requires ≥ Debian 10) |
| Ubuntu 16.04 and older | `deploy.sh:322` | Explicitly rejected (Requires ≥ Ubuntu 16) |
| 32-bit Architectures | `deploy.sh:283` | 64-bit systems only |

### ⏳ Python <3.9 Deprecation Schedule

Python <3.9 branches (preserved for compatibility with CentOS 7, Debian 10, etc.) are maintained as **transitional compatibility** and are scheduled for **End of Life on 2027-06-30**: all `python_version < '3.9'` dependency branches in `requirements.txt` (flask, Werkzeug, pyOpenSSL, cryptography) will be removed. CentOS 7 and Debian 10 upstream are both EOL with no security patches. Users on Python <3.9 are urged to upgrade to **Python ≥3.9** prior to this date.

### 🧭 Architectural Direction on Compatibility

The common root cause of version gaps is the "patch-per-version" approach (`Install_dep_debain13()`, `VERSION_ID == "13"`). The comprehensive upgrade strategy is outlined in [`文档/Debian-Ubuntu全版本适配方案.md`](文档/Debian-Ubuntu全版本适配方案.md): shifting from "version enumeration" to "capability detection" using declarative dependency manifests + runtime resolution.

---

## 🆕 Latest Updates

> Note: Performance metrics and speedup multiples below reflect **author local benchmarks under specific test environments** and vary by hardware specifications and dataset sizes. Reference benchmarks in `scripts/bench/README.md`.

- **Plugin Upgrades**: Upgraded "Yufeng OP Firewall 1.5 (Enterprise Web Application Firewall)" with deep performance optimization:
  - **80%+ Disk I/O Reduction**: Rebuilt asynchronous SQLite batch persistence (3-second batching + automatic handle recycling), optimized expired log cleanup frequencies, and eliminated disk lock contention.
  - **90%+ CC Protection CPU Drop**: Replaced pure Lua calculation with OpenResty native C-level MD5 request fingerprints, maintaining multi-dimensional IP, Subnet, URI, UA, and Cookie rate-limiting while drastically freeing CPU cycles.
  - **Kernel-Level Stability**: Fixed memory allocations and linked-list deallocations in GeoIP / MaxMindDB FFI pointers, eliminating OpenResty worker segfaults.
  - **Honeypot Fast-Path Filtering**: Optimized honeypot path matching for high-throughput regular traffic.
- **New Feature**: "Recent Login Logs" & Security Audit System on Dashboard:
  ![login_log](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/login_log.webp)
  - **Full-Link Login Tracking**: Records Web panel (regular login, 2FA, security entrance) and SSH terminal login events (successes and failures).
  - **Intelligent IP Geolocation**: Multi-channel geolocation resolution with local anti-pollution caching, displaying locations and method badges.
  - **Multi-Dimensional Audit Modal**: Layer modal offering multi-condition filtering by method (Web/SSH) and status (Success/Failure) with pagination.
  - **Client Timezone Adaptation & SWR Instant Load**: Formatted to browser timezone; uses 60s session-level SWR caching for 0ms flicker-free tab switches.
- **New Plugin**: "Yufeng Python Multi-Version Manager 1.0", built on `uv` for fast, non-intrusive Python version and virtual environment management. One-click multi-version installation with total environment isolation; automated `.venv` creation using project names as terminal prompts; anti-deletion safeguards.
  ![python](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/python.webp)
- **New Plugin**: "PostgreSQL Containerized Management Plugin 1.0", offering one-click deployment of Docker-isolated PostgreSQL instances with dynamic public/private network boundaries (0.0.0.0 / 127.0.0.1 toggle), automated daily/weekly lock-free hot backups, and manual restore.
  ![pg_docker](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/pg_docker.webp)
- **Plugin Update**: Completed "Yufeng Linux System Optimization Plugin 1.0" with enhanced visual feedback.

![System Optimization](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/linux_sys_opt.webp)

- **Feature Optimizations**:
  - Docker plugin storage control: visual breakdown of root directory, images, and container storage; one-click Docker data directory hot migration with disk space pre-checks and rollback.
    ![docker migration](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/一键迁移docker目录.webp)
  - PostgreSQL container plugin (`pg_docker`): added "Modify Configuration" supporting random password generation, database password and host port modification with automatic container restart; conflict pre-detection on port changes; live CPU and memory metrics in instance lists.
  - Scheduled task logs now display corresponding task names; improved file manager rendering of long filenames and symlinks; added "Copy Full Path" in file menus.
- **Bug Fixes**: Fixed parsing errors during Docker image retrieval.
- **Hardware Monitoring & Connectivity**: Added GPU status on dashboard and system monitoring; SSH key management; fixed SSH terminal compatibility on newer Ubuntu releases; enhanced SSH and ping probe robustness.
- **Security & Core Optimization**: Salt machine fingerprint binding; refactored file listing sorting using `os.lstat()` to prevent symlink cycle crashes (HTTP 500); deployment script refinements.
- **Critical Fixes**: Fixed 2FA verification bugs, resolved duplicate dependency installations during Baota migration, and corrected legacy config read issues on initial MySQL installations.

---

## 🛠️ Usage & Installation

### 1. One-Click Installation / Migration

#### Dedicated Server Installation (Recommended)

Single command to install, upgrade, or migrate. Automatically detects geographic region and routes to the fastest mirror:

```bash
curl https://panel.yftec.top/deploy.sh | bash
```

#### GitHub Direct Installation

If the dedicated server is temporarily unreachable, install directly via GitHub:

```bash
curl https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash
```

#### 🇨🇳 Mainland China Mirror Proxy

If GitHub is inaccessible from your server, use the domestic proxy mirror:

```bash
curl https://gh-proxy.org/https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash
```

#### 🔐 Pre-Installation Verification (Strongly Recommended)

`deploy.sh` executes with **root** privileges. Verify its SHA256 hash before executing to ensure transport integrity:

```bash
# 1) Download script without executing
curl -fsSLo deploy.sh https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh
# 2) Calculate local SHA256
sha256sum deploy.sh
# 3) Compare against deploy.sh.sha256 from the matching release; execute only if identical
bash deploy.sh
```

Expected hash source: Each project Release includes `deploy.sh.sha256` (generated by the release workflow alongside `SHA256SUMS` and signatures). Always download from the official GitHub Release corresponding to your target version; do not trust third-party mirror hashes.

> The installation pipeline enforces fail-closed verification: `deploy.sh` prioritizes **signed** release archives verified with Ed25519 signatures. If signature verification fails or the public key is missing, installation halts. Only in verified signature-free environments should validation be bypassed with `YF_REQUIRE_SIGNATURE=0 bash deploy.sh` (logged to `/var/log/bt_simple_deploy.log`).

#### Smooth Migration & Seamless Data Takeover from Baota Panel (BT.CN) 🚀

BtSimple offers maximum compatibility for Baota Panel users, ensuring migration is safe, clean, and capable of immediately taking over existing databases and site data:

1. **Intelligent Environment Analysis**: Before stopping Baota services, the deployment script scans and records installed versions of `MySQL`, `Redis`, `OpenResty`, `PHP`, and `PostgreSQL`, and installs necessary restore utilities like `zstd` and `unzip`.
2. **Safe Isolation & Conflict Prevention**: Halts old MySQL services completely to avoid lock conflicts; isolates conflicting physical directories into backups (e.g., `mysql_bt_bak`); removes blocking `user.ini` files and restores them via internal mechanisms.
3. **Automatic Website List Import**: Scans and parses old Baota databases, automatically importing site records (names, paths, notes, creation dates) into BtSimple's database.
4. **MySQL Database Migration**:
   The migration script creates an automated database backup. To ensure data integrity, **the source and target MySQL versions must be identical**. Migration can be executed via [Panel Settings -> Database Migration] or via the CLI:
   *Caution: Migration will overwrite current database contents. Proceed carefully.*

   ```bash
   bs migrate_restore
   # Or run `bs` interactive CLI and select option (30) "Restore Baota software data (Migration Takeover)"
   ```

### 2. Backup and Rollback

Security and stability are fundamental to BtSimple. Always backup critical data before major updates or migrations.

#### Manual Backup (Recommended)

```bash
# Backup panel database and configuration files
tar -czf /www/backup/bt_simple_data_$(date +%Y%m%d).tar.gz /www/server/yufeng_panel/data
```

#### Automated Panel Database Backup and Restore

The panel database `data/panel.db` (containing sites, users, scheduled tasks, and settings) is **automatically backed up daily** by the task daemon, retaining the latest 14 snapshots:

- Backup Directory: `/www/backup/panel_db/` (located under the panel's configured `backup_path`, alongside `site` and `database` backups).
- Filename Pattern: `panel_db_YYYYmmdd_HHMMSS.db`. Older backups exceeding retention are automatically purged.
- Generates consistent snapshots via SQLite Online Backup API (**not** a raw file copy, preventing corrupted transactions in WAL mode).
- Manual trigger: `python3 panel_task.py backup_panel_db` (non-zero exit on failure).

Restoration Procedure (**panel must be stopped before replacing**):

```bash
bs stop                                                      # 1. Stop panel and task daemon
cd /www/server/yufeng_panel/data                             # 2. Remove old WAL/SHM files to prevent
rm -f panel.db-wal panel.db-shm panel.db-journal             #    replaying stale transactions into new DB
mv panel.db panel.db.broken                                  # 3. Preserve broken DB (recommended)
cp /www/backup/panel_db/panel_db_20260101_030000.db panel.db # 4. Overwrite with backup snapshot
chown www:www panel.db                                       #    Ensure correct ownership
bs start                                                     # 5. Start panel and verify data
```

> The backup snapshot is self-consistent; **do not** combine it with stale `-wal` files. Retaining old `-wal`/`-shm` files may result in data regression or `database disk image is malformed` errors.

#### One-Click Rollback (via Deployment Script)

If compatibility issues arise after migration, quickly restore previous panel states:

```bash
# Rollback to pre-migration mdserver-web state
bash deploy.sh rollback_mw

# Rollback to pre-migration Baota Panel state
bash deploy.sh rollback_bt
```

#### One-Click Uninstallation

To remove the panel (website files are preserved):

```bash
# Option 1: Via deployment script
bash deploy.sh uninstall

# Option 2: Via system command
bs uninstall
```

### 3. Command Line Interface (CLI)

The panel includes the powerful `bs` CLI (fully compatible with alias `mw`) for rapid terminal operations:

- `bs default`: View default panel login credentials and URL.
- `bs stop / start / restart`: Service lifecycle management.
- `bs update`: Check for and apply panel updates.

```sh
root@debian:/root# bs
========================bs_simple cli tools==========================
(1)    Restart Panel Service            (2)    Stop Panel Service
(3)    Start Panel Service              (4)    Reload Panel Service
(5)    Modify Panel IP                  (6)    Modify Panel Port
(7)    Disable Security Entrance        (9)    Force Kill All Tasks (Fix Stalled)
(10)   View Panel Default Info          (11)   Modify Panel Password
(12)   Modify Panel Username            (13)   Show Panel Error Log
(14)   Disable Panel Access             (15)   Enable Panel Access
(20)   Disable BasicAuth                (21)   Unbind Domain Name
(22)   Unbind Panel SSL                 (23)   Enable IPv6 Support
(24)   Disable IPv6 Support             (25)   Open Firewall SSH Port
(26)   Disable Two-Factor Auth (2FA)    (27)   View Firewall Status
(28)   Auto-Sync Firewall Ports         (29)   Auto-Sync Site Configuration
(100)  Show PHP 5.2 in Store            (101)  Hide PHP 5.2 in Store
(200)  Switch Linux Package Mirrors     (201)  Simple Speed Test
(202)  SSH Terminal Management          (30)   Restore Baota Data (Takeover)
(0)    Cancel
========================================================================
Please enter command number:
```

### 4. Plugin Lossless Upgrade & Version Self-Healing Engine

To resolve configuration incompatibilities, missing table columns, PID misdetections, daemon deadlocks, and missing dynamic libraries during version upgrades, BtSimple introduces a **"Major Version Transition Single-Pass Self-Healing Migration"** engine across core plugins (MySQL, MariaDB, Redis, PHP, PHP-APT, PHP-YUM, etc.):

- **Fully Automated (Zero Manual Intervention)**: When upgrading from legacy branches (e.g., `master` 1.x) to modern releases (e.g., `i18n` 2.x), accessing the panel, refreshing status probes, or starting services automatically triggers a single-pass self-healing routine. It patches SQLite schemas (e.g., adding `rw` permission columns), calibrates Systemd services and PID paths, injects complete dynamic library paths (`LD_LIBRARY_PATH`), repairs runtime directories (e.g., `/run/php`), and clears orphaned sockets. Once completed, a persistent version marker is recorded, ensuring **0ms performance overhead** on subsequent requests.
- **CLI Manual Inspection & Self-Healing**:
  To execute upgrade checks and environment self-healing directly from the terminal after pulling code:

  ```bash
  # MySQL Plugin: Check version upgrade and run single-pass self-healing
  python3 plugins/mysql/index.py check_plugin_upgrade
  # Or generate a full environment self-healing report
  python3 plugins/mysql/index.py upgrade_self_healing
  
  # MariaDB Plugin: Check version upgrade and run single-pass self-healing
  python3 plugins/mariadb/index.py check_plugin_upgrade
  # Or generate a full environment self-healing report
  python3 plugins/mariadb/index.py upgrade_self_healing
  
  # Redis Plugin: Check version upgrade and self-heal (systemd calibration, conflict cleanup, PID repair)
  python3 plugins/redis/index.py check_plugin_upgrade
  # Or generate a full environment self-healing report
  python3 plugins/redis/index.py upgrade_self_healing
  
  # PHP Source Plugin: Version upgrade check & self-healing (failover recovery, library hardening, socket cleanup)
  python3 plugins/php/index.py check_plugin_upgrade
  # Or trigger self-healing for all / specific version (e.g., 74, 80, 81)
  python3 plugins/php/index.py upgrade_self_healing
  
  # PHP-APT Plugin (Debian/Ubuntu): Runtime environment repair, reset systemd failed states, clear orphan sockets
  python3 plugins/php-apt/index.py check_plugin_upgrade
  python3 plugins/php-apt/index.py upgrade_self_healing
  
  # PHP-YUM Plugin (RHEL/CentOS/Rocky): Remi runtime repair, reset systemd failed states, clear orphan sockets
  python3 plugins/php-yum/index.py check_plugin_upgrade
  python3 plugins/php-yum/index.py upgrade_self_healing
  ```

- **Zero-Touch Production Data & Configuration Safeguards**:
  - MySQL / MariaDB: When system or user databases exist, **emptying or renaming data directories (e.g., `/www/server/mysql/data`) is strictly prohibited**;
  - Redis: When an existing configuration file is present, **overwriting `redis.conf` is strictly prohibited, preserving 100% of custom passwords, ports, and parameters**;
  - PHP Family: Self-healing **never overwrites user `php.ini`, `php-fpm.conf`, or pool configurations, keeping compiled extensions fully operational**.

---

## 👨‍💻 Development Guide

BtSimple welcomes contributions from developers. The architecture is straightforward and easy to navigate.

### Directory Structure

- `web/`: Panel frontend assets and backend application logic (built with Flask).
- `plugins/`: Storage directory for all plugins. Each plugin contains independent shell scripts and UI configurations.
- `scripts/`: Installation, uninstallation, maintenance, and utility scripts.

### Plugin Development Workflow

1. Create a new plugin folder referencing `plugins/simple-plugin`.
2. Author `info.json` defining plugin metadata and supported operations.
3. Write `install.sh` implementing automated installation and uninstallation logic.
4. Write `index.py` handling plugin backend logic and service lifecycle hooks.

### Plugin Major Version Migration Pipeline

When modifying configurations, altering SQLite schemas (adding/removing columns), or reloading Systemd daemons in plugins, adopt the **Single-Pass Self-Healing Migration Pattern** aligned with MySQL/MariaDB to avoid redundant checks on every API call:

1. **Define Plugin Version and Marker File**:
   ```python
   CURRENT_PLUGIN_VERSION = '2.0'
   
   def getPluginVersionFile():
       return getPluginDir() + '/plugin_version.pl'
   ```
2. **Register Migration Pipeline**:
   ```python
   def _migrate_1_to_2(version=''):
       # Execute database ALTER TABLE, config calibrations, etc.
       return upgradeSelfHealing(version)
   
   # Migration pipeline: (target_version, migration_function)
   # Future steps (e.g., 2.1, 3.0) can be appended sequentially
   PLUGIN_MIGRATION_STEPS = [
       ('2.0', _migrate_1_to_2),
       # ('3.0', _migrate_2_to_3),
   ]
   ```
3. **Implement Upgrade Check Function `checkPluginUpgrade`**:
   - Read installed version; if `installed_version < target_version`, execute pipeline steps sequentially;
   - Atomically persist the new version number upon success, ensuring execution runs **only once per upgrade**;
   - Invoke in `status()` entrypoints, initialization routines, and `install.sh` upgrade branches.

### Coding Principles

- **Keep It Simple**: Avoid premature abstraction and over-engineering.
- **Fact-First**: Verify thoroughly with test suites before submitting PRs.
- **Security First**: Always sanitize shell commands using the built-in `yf.shlex_quote` utility.

---

## 📝 Pros & Cons Summary

### Advantages

- **High Transparency**: Open-source with clean, readable code; administrators maintain full visibility over server operations.
- **Outstanding Performance**: Built with native Python, free from unnecessary background polling daemons, delivering near-instant responses.
- **Smooth Migration**: The industry's smoothest transition path from legacy mdserver-web and Baota Panel (BT.CN).
- **Hardened Security**: Systematically audited and patched against known vulnerabilities, offering enterprise-grade baseline protection.

### Limitations

- **Ecosystem Breadth**: Fewer total plugins compared to long-standing commercial panels, though covering 90%+ of standard server administration needs.

---

## 🌟 Future Roadmap

1. **Cache Strategy Optimization**: Implement higher-efficiency persistent caching to further accelerate UI responses under concurrency.
2. **Deep Monitoring Enhancements**: Finer-grained resource monitoring metrics, trends, and automated anomaly alert notifications.
3. **App Store Expansion**: Enhanced native support for Node.js, Go, and advanced Docker application templates.
4. **Automated Static Security Audits**: Integrate stricter static security analyzers into CI/CD for continuous vulnerability prevention.

---

**Yufeng Panel (BtSimple)** is dedicated to bringing transparency, security, and simplicity back to Linux server management. Thank you to all our users and contributors!

[English Documentation](README.md) | [Chinese Documentation](README_cn.md) | [GitHub Repository](https://github.com/clhome/bt_simple) | [📖 Beginner's Manual (Chinese)](文档/御风面板说明书/说明书.md) | [Wiki Documentation](https://github.com/clhome/bt_simple/wiki)

