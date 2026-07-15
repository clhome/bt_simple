# coding: utf-8
# +-----------------------------------------------------------------------------------
# | YF Linux
# +-----------------------------------------------------------------------------------
# | Copyright (c) 2015-2099 MW(http://github.com/midoks/mdserver) All rights reserved.
# +-----------------------------------------------------------------------------------
# | Author: midoks/yftec
# +-----------------------------------------------------------------------------------

#------------------------------
# API-Demo of Python
#------------------------------
import time
import hashlib
import sys
import os
import json


class yfApi:
    # 示例面板地址和密钥，使用时请替换为您自己的真实面板地址和接口密钥
    __YF_PANEL = 'http://127.0.0.1:7200/'
    __YF_APP_ID = 'exampleAppId'
    __YF_APP_SERECT = 'exampleAppSecret'
    
    # 如果希望管理多台面板，可以在实例化对象时，将面板地址与密钥传入
    def __init__(self, panel_url=None, app_id=None, app_serect=None):
        if panel_url:
            self.__YF_PANEL = panel_url
            self.__YF_APP_ID = app_id
            self.__YF_APP_SERECT = app_serect

    def post(self, endpoint, request_data):
        import requests
        url = self.__YF_PANEL + endpoint  
        post_data = requests.post(url, data=request_data, headers={
            'app-id':self.__YF_APP_ID,
            'app-secret':self.__YF_APP_SERECT
        })
        try:
            return post_data.json()
        except Exception as e:
            return post_data.text
    # 鍙栭潰鏉挎棩蹇?
    def getLogs(self):
        result = self.post('/task/count',{'limit':10,'p':1})
        return result


if __name__ == '__main__':
    # 瀹炰緥鍖朚W-API瀵硅薄
    api = yfApi()

    # 璋冪敤get_logs鏂规硶
    rdata = api.getLogs()

    # 鎵撳嵃鍝嶅簲鏁版嵁
    print(rdata)
