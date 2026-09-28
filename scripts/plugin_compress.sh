#!/bin/bash

###
### 插件压缩
###
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
LANG=en_US.UTF-8
is64bit=`getconf LONG_BIT`
curPath=`pwd`
rootPath=$(dirname "$curPath")

startTime=`date +%s`
PLUGIN_NAME='abkill'

#echo $rootPath/plugins/$PLUGIN_NAME
mkdir -p $rootPath/scripts/tmp
# 排除开发期产物：i18n 回滚快照（*.i18n.bak，单插件可达上百 KB）与 Python 缓存，
# 否则它们会随插件包一起下发给用户（plugin_compress.sh 是 `zip -r ./*`）。
cd $rootPath/plugins/$PLUGIN_NAME && zip -r $rootPath/scripts/tmp/${PLUGIN_NAME}_${startTime}.zip ./* \
    -x "*/__pycache__/*" -x "*.pyc" -x "*.i18n.bak" -x "*.bak" -x "*.orig" \
    > /tmp/t.log 2>&1

endTime=`date +%s`
((outTime=($endTime-$startTime)))
echo -e "Time consumed:\033[32m $outTime \033[0msecs.!"