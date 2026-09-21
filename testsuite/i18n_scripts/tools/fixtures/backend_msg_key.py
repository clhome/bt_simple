# -*- coding: utf-8 -*-
"""backend-msg-key 检测器的「已知答案」夹具。

配套自证逻辑（scripts/verify_i18n.py: self_test）用固定键集调用
_scan_backend_msg_keys()，期望恰好命中 5 处。夹具同时覆盖「必须放过」的
合法写法与「必须抓到」的漏翻写法，用来证明检测器既不漏报也不误报。

固定键集（在 self_test 中硬编码，见 EXPECT_KEYS）：
    扫描完成
    获取日志失败:
    读取日志失败:          <- 故意带尾随空格，验证「尾随空格容错」分支
    操作失败:

注意：EXPECT_MISS_LINES 用 returnJson( 所在行号（1-based），
与 _scan_backend_msg_keys 的报告口径一致。
"""

# 期望「能查到键」的调用点行号
EXPECT_OK_LINES = [27, 32, 37, 42, 47, 52]

# 期望「查不到键」的调用点行号
EXPECT_MISS_LINES = [57, 62, 67, 73, 78]


def ok_exact():
    # L27: 整串精确命中
    return yf.returnJson(True, '扫描完成', {})


def ok_colon_prefix():
    # L32: 冒号前缀命中（动态部分在冒号之后）
    return yf.returnJson(False, '获取日志失败: ' + str(e))


def ok_colon_no_space():
    # L37: 冒号后无空格，走「前缀 + 空格」容错分支
    return yf.returnJson(False, '获取日志失败:' + str(e))


def ok_trailing_space_key():
    # L42: 键本身带尾随空格（'读取日志失败: '），消息里的空格属于动态部分
    return yf.returnJson(False, '读取日志失败: ' + str(e))


def ok_colon_prefixed_fstring():
    # L47: f-string，冒号前缀仍是键
    return yf.returnJson(False, f'操作失败: {res["error"]}')


def ok_non_chinese():
    # L52: 无中文（纯英文消息）——不在检查范围内，必须放过
    return yf.returnJson(False, 'Permission denied')


def bad_no_colon_split():
    # L57: 无冒号，中文被变量夹断 -> 无法前缀匹配
    return yf.returnJson(True, f'清理完成！已释放 {freed} 磁盘空间')


def bad_prefix_missing():
    # L62: 有冒号，但前缀不是键
    return yf.returnJson(False, '扫描发生异常: ' + str(e))


def bad_colon_too_far():
    # L67: 冒号位置 > 40，运行时前缀匹配不生效（i18n.js: ci <= 40）
    return yf.returnJson(False,
                         '这是一条特别长的前缀用来把冒号推到四十个字符之后从而无法匹配: ' + x)


def bad_exact_missing():
    # L73: 无冒号且整串不是键
    return yf.returnJson(False, '请不要输入以下特殊字符 " ~ ~ / = "')


def bad_chinese_after_colon():
    # L78: 中文全在冒号之后（前缀 'ERROR:' 无中文，取到的键毫无意义）
    return yf.returnJson(False, 'ERROR: 配置出错<br>' + detail)
