# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import json
import core.yf as yf

# 内存缓存，避免频繁读取 SQLite
_option_cache = {}

def getOption(name, type='common', default=None) -> str:
    '''
    获取配置的值
    :name -> str 名称 (必填)
    :type -> str 类型 (可选|默认common)
    :default -> str 默认值 (可选)
    '''
    cache_key = f"{type}:{name}"
    if cache_key in _option_cache:
        return _option_cache[cache_key]

    data = yf.M('option').field('name').where('name=? and type=?', (name, type,)).getField('value')
    if data is None:
        return default
    _option_cache[cache_key] = data
    return data


def getOptionByJson(name, type='common', default=None) -> object:
    '''
    获取配置的值,返回对象类型
    :name -> str 名称 (必填)
    :type -> str 类型 (可选|默认common)
    :default -> str 默认值 (可选)
    '''
    cache_key = f"{type}:{name}:json"
    if cache_key in _option_cache:
        return _option_cache[cache_key]

    data = yf.M('option').field('name').where('name=? and type=?', (name, type,)).getField('value')
    if data is None:
        return default
    try:
        val = json.loads(data)
    except:
        val = default
    _option_cache[cache_key] = val
    return val

def setOption(name, value, type='common') -> bool:
    '''
    设置配置的值
    :name -> str 名称 (必填)
    :value -> object值 (必填)
    :type -> str 类型 (可选|默认common)
    '''
    # 清理和同步缓存
    cache_key = f"{type}:{name}"
    json_cache_key = f"{type}:{name}:json"
    if cache_key in _option_cache:
        del _option_cache[cache_key]
    if json_cache_key in _option_cache:
        del _option_cache[json_cache_key]

    data = yf.M('option').field('name,type,value').where('name=? and type=?', (name, type,)).find()
    if data is not None:
        yf.M('option').field('name').where('name=? and type=?', (name, type,)).setField('value', value)
        _option_cache[cache_key] = str(value)
        return True
    add_option = {
        'name': name,
        'type': type,
        'value': value
    }
    res = yf.M('option').insert(add_option)
    if res:
        _option_cache[cache_key] = str(value)
    return res