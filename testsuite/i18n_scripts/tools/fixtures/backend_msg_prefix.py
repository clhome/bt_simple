# -*- coding: utf-8 -*-
"""backend-msg-prefix 检测器的自证夹具（不参与运行，仅供 verify_i18n.py --self-test 使用）。

契约：前端 YfI18n.translateAny() 用「消息首个冒号（含）前缀」查语言包，
      所以前缀必须纯文本；HTML 只能出现在前缀之后。

本文件刻意混入 3 处违规写法（BAD）与 6 处合规写法（GOOD），
用于证明检测器既不漏报也不误报。
"""


def bad_samples():
    # BAD-1：HTML 落在前缀内部（首冒号在 URL 里/前缀里）
    return yf.returnJson(False, 'ERROR: 配置出错<br><a style="color:red;">' + err + '</a>')
    # BAD-2：<br> 位于冒号之前
    return yf.returnJson(False, 'MySQLdb组件缺失! <br>进入SSH命令行输入: pip install x')
    # BAD-3：整条消息就是 HTML（无冒号，前缀 = 全文）
    return yf.returnJson(False, '<b>出错了</b>')


def good_samples():
    # GOOD-1：前缀纯文本，HTML 在前缀之后
    return yf.returnJson(False, '配置出错: ' + '<span style="color:red;">' + err + '</span>')
    # GOOD-2：<br> 挪到冒号之后
    return yf.returnJson(False, 'MySQLdb组件缺失! 进入SSH命令行输入: <br>pip install x')
    # GOOD-3：纯文本、无 HTML
    return yf.returnJson(True, '设置成功')
    # GOOD-4：f-string 前缀
    return yf.returnJson(False, f"扫描发生异常: {str(e)}")
    # GOOD-5：URL 里的冒号在动态部分，前缀仍是纯文本
    return yf.returnJson(False, '请先安装初始化，默认地址: http://' + ip + ':3000')
    # GOOD-6：第二个实参不是字面量，跳过
    return yf.returnJson(False, str(e), {'a': 1})
