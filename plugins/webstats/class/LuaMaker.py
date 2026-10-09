import sys
import os


def _escapeLuaString(s):
    """转义 Lua 字符串里的反斜杠/引号/控制字符。

    不转义时：值里一个真实换行就让生成的 lua 文件语法错误
    （luajit: unfinished string near ...），而该文件被 openresty include，
    reload/重启直接失败；正则里的 ``\\d`` 也会被 Lua 当成非法转义。
    """
    out = []
    for ch in str(s):
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 0x20 or ord(ch) == 0x7f:
            out.append('\\%d' % ord(ch))
        else:
            out.append(ch)
    return ''.join(out)


class LuaMaker:
    """
    lua 处理器
    """
    @staticmethod
    def makeLuaTable(table):
        """
        table 转换为 lua table 字符串
        """
        _tableMask = {}
        _keyMask = {}

        def analysisTable(_table, _indent, _parent):
            if isinstance(_table, tuple):
                _table = list(_table)
            if isinstance(_table, list):
                _table = dict(zip(range(1, len(_table) + 1), _table))
            if isinstance(_table, dict):
                _tableMask[id(_table)] = _parent
                cell = []
                thisIndent = _indent + "    "
                for k in _table:
                    if sys.version_info[0] == 2:
                        if type(k) not in [int, float, bool, list, dict, tuple]:
                            k = k.encode()

                    if not (isinstance(k, str) or isinstance(k, int) or isinstance(k, float)):
                        return
                    key = isinstance(
                        k, int) and "[" + str(k) + "]" or "[\"" + _escapeLuaString(k) + "\"]"
                    if _parent + key in _keyMask.keys():
                        return
                    _keyMask[_parent + key] = True
                    var = None
                    v = _table[k]
                    if sys.version_info[0] == 2:
                        if type(v) not in [int, float, bool, list, dict, tuple]:
                            v = v.encode()
                    if isinstance(v, str):
                        var = "\"" + _escapeLuaString(v) + "\""
                    elif isinstance(v, bool):
                        var = v and "true" or "false"
                    elif isinstance(v, int) or isinstance(v, float):
                        var = str(v)
                    else:
                        var = analysisTable(v, thisIndent, _parent + key)
                    cell.append(thisIndent + key + " = " + str(var))
                lineJoin = ",\n"
                return "{\n" + lineJoin.join(cell) + "\n" + _indent + "}"
            else:
                pass
        return analysisTable(table, "", "root")
