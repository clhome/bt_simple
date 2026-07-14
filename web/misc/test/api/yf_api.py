# coding: utf-8
# +-----------------------------------------------------------------------------------
# | YF Linux闈㈡澘
# +-----------------------------------------------------------------------------------
# | Copyright (c) 2015-2099 MW(http://github.com/midoks/mdserver) All rights reserved.
# +-----------------------------------------------------------------------------------
# | Author: midoks
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
    __YF_PANEL = 'http://154.12.53.90:51377/'
    __YF_APP_ID = 'yhYkxGssPD'
    __YF_APP_SERECT = 'ErmBdr563eJ5GMM5sWbc'
    
    # 濡傛灉甯屾湜澶氬彴闈㈡澘锛屽彲浠ュ湪瀹炰緥鍖栧璞℃椂锛屽皢闈㈡澘鍦板潃涓庡瘑閽ヤ紶鍏?
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
