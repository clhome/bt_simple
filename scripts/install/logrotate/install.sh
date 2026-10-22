#!/bin/bash
# =============================================================================
# 御风面板 —— gunicorn 日志轮转下发（整改项 P1-9.2）
#
# 背景：`web/setting.py` 只把 gunicorn 的输出指到 `logs/panel.log` /
# `logs/panel_error.log`，仓库里没有任何轮转配置 —— 长期运行每天都在涨，
# 小盘 VPS 迟早被面板自己的日志塞满（写满根分区 → 面板、数据库一起挂）。
#
# 做法：把同目录下的模板 `logrotate/yf-panel` 渲染成 /etc/logrotate.d/yf-panel。
# 选 logrotate 而不是「在 setting.py 里接管轮转」的理由见报告，一句话：
# 轮转是**系统级**职责（时间点、保留份数、压缩、与 logrotate.timer 联动），
# 塞进 gunicorn 配置还得自己写定时器与并发锁，反而更容易出问题。
#
# 调用点（两处，都是「幂等 + 非阻断」）：
#   1. deploy.sh 的 install_logrotate_conf()：全新安装 / 从其它面板迁移时下发；
#   2. cli.sh 的 yf_start()：每次面板启动时自愈一遍 —— 覆盖「面板内自升级」
#      这条不会执行 deploy.sh 的路径，也让被手工删掉的配置能自动回来。
#
# 失败语义（不要改成静默）：任何一步失败都打 [WARN]/[ERROR] 并追加一行到
# `<面板目录>/logs/logrotate_install.log`；返回码 0=已就绪或已明确跳过，
# 1=真的失败了（模板缺失 / 写不进去）。调用方据此告警，但**不中断安装**：
# 缺 logrotate 的最小系统仍应能用面板，只是日志需要自行管理。
#
# 测试友好：YF_LOGROTATE_TARGET_DIR 可改写入目录（默认 /etc/logrotate.d），
# YF_PANEL_DIR 可改面板目录，用具例可以在临时目录里验证渲染结果。
# =============================================================================

set -u

# ---- 面板目录：优先环境变量，其次按脚本位置推断（scripts/install/logrotate/）----
if [ -n "${YF_PANEL_DIR:-}" ]; then
    PANEL_DIR="${YF_PANEL_DIR}"
else
    SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
    PANEL_DIR=$(cd "${SCRIPT_DIR}/../../.." && pwd)
fi

TEMPLATE="${PANEL_DIR}/scripts/install/logrotate/yf-panel"
TARGET_DIR="${YF_LOGROTATE_TARGET_DIR:-/etc/logrotate.d}"
TARGET="${TARGET_DIR}/yf-panel"
REPORT_LOG="${PANEL_DIR}/logs/logrotate_install.log"

log_line() {
    printf '%s\n' "$1"
    if [ -d "${PANEL_DIR}/logs" ]; then
        printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${REPORT_LOG}" 2>/dev/null || true
    fi
}

warn() {
    log_line "[WARN] logrotate: $1"
}

die() {
    log_line "[ERROR] logrotate: $1"
    exit 1
}

# ---- 0. 只处理 Linux：macOS / 其它平台没有 /etc/logrotate.d，明确跳过而不是假装成功 ----
if [ -z "${YF_LOGROTATE_TARGET_DIR:-}" ]; then
    case "$(uname -s 2>/dev/null)" in
        Linux) : ;;
        *) warn "当前平台不是 Linux（$(uname -s 2>/dev/null)），跳过日志轮转配置；请自行管理 logs/panel*.log 的清理"; exit 0 ;;
    esac
fi

# ---- 1. 模板必须存在：这是发布包缺文件的信号，必须报错而不是悄悄跳过 ----
if [ ! -f "${TEMPLATE}" ]; then
    die "缺少模板 ${TEMPLATE}（发布包不完整，或面板目录判断错误）"
fi

# ---- 2. 目标目录：不存在说明系统没装 logrotate，告警跳过（非阻断）----
if [ ! -d "${TARGET_DIR}" ]; then
    warn "系统上不存在 ${TARGET_DIR}（未安装 logrotate？），跳过；建议 apt/yum 安装 logrotate 后重跑本脚本"
    exit 0
fi

# ---- 3. 渲染：只替换 __PANEL_DIR__，其它内容原样下发 ----
RENDERED=$(mktemp 2>/dev/null) || die "无法创建临时文件"
trap 'rm -f "${RENDERED}"' EXIT

if ! sed "s|__PANEL_DIR__|${PANEL_DIR}|g" "${TEMPLATE}" > "${RENDERED}"; then
    die "渲染模板失败：${TEMPLATE}"
fi
if grep -q '__PANEL_DIR__' "${RENDERED}"; then
    die "渲染后仍有 __PANEL_DIR__ 占位符（面板路径含特殊字符？）：${PANEL_DIR}"
fi

# ---- 4. 幂等：内容相同就不动文件（避免每次启动都改 mtime 让人误以为被改过）----
if [ -f "${TARGET}" ] && cmp -s "${RENDERED}" "${TARGET}"; then
    log_line "[OK] logrotate: 配置已是最新（${TARGET}）"
    exit 0
fi

# ---- 5. 落盘：先写同目录临时文件再原子 mv，避免半截配置被 logrotate 读到 ----
if ! install -m 0644 "${RENDERED}" "${TARGET}.yf-new" 2>/dev/null; then
    die "写入失败（需要 root 权限）：${TARGET}.yf-new"
fi
if ! mv -f "${TARGET}.yf-new" "${TARGET}" 2>/dev/null; then
    rm -f "${TARGET}.yf-new" 2>/dev/null
    die "安装失败（需要 root 权限）：${TARGET}"
fi

# ---- 6. 语法自检：logrotate -d 是 dry-run，只解析配置，不轮转任何文件 ----
if command -v logrotate >/dev/null 2>&1; then
    if logrotate -d "${TARGET}" >/dev/null 2>&1; then
        log_line "[OK] logrotate: 已安装 ${TARGET}（daily / rotate 14 / compress / copytruncate，logrotate -d 校验通过）"
    else
        warn "已写入 ${TARGET}，但 logrotate -d 校验未通过，请手工检查该文件"
    fi
else
    log_line "[OK] logrotate: 已安装 ${TARGET}（未找到 logrotate 命令，跳过 -d 校验）"
fi

exit 0
