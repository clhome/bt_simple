#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
LANG=en_US.UTF-8

USER=$(who | sed -n "2,1p" |awk '{print $1}')
DEV="/Users/${USER}/Desktop/yfdev"


mkdir -p $DEV
mkdir -p $DEV/wwwroot
mkdir -p $DEV/server
mkdir -p $DEV/wwwlogs
mkdir -p $DEV/backup/database
mkdir -p $DEV/backup/site

# install brew
which brew
if [ "$?" != "0" ];then
	/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
	brew install python@2
	brew install mysql
fi

brew install pv
brew install libzip bzip2 gcc openssl re2c cmake
brew install librdkafka
brew install coreutils libxml2 xml2
brew install md5sum libevent pidof bison
brew install pcre2 libxpm libelf
brew install automake icu4c libmemcached

if [ ! -d $DEV/server/yufeng_panel ]; then
	wget -O /tmp/master.zip https://codeload.github.com/clhome/bt_simple/zip/master
	cd /tmp && unzip /tmp/master.zip
	mv /tmp/bt_simple-master $DEV/server/yufeng_panel
	rm -f /tmp/master.zip
	rm -rf /tmp/bt_simple-master
fi

if [ ! -d $DEV/server/lib ]; then
	# lib.sh 装不上 Python 依赖会 exit 1；不显式退出的话后续命令会把退出码变回 0
	cd $DEV/server/yufeng_panel/scripts && bash lib.sh || exit 1
fi  

chmod 755 $DEV/server/yufeng_panel/data
if [ -f $DEV/server/yufeng_panel/bin/activate ];then
    cd $DEV/server/yufeng_panel && python3 -m venv $DEV/server/yufeng_panel
    source $DEV/server/yufeng_panel/bin/activate
    pip3 install -r $DEV/server/yufeng_panel/requirements.txt
else
	cd $DEV/server/yufeng_panel && pip3 install -r $DEV/server/yufeng_panel/requirements.txt
fi


cd $DEV/server/yufeng_panel && ./cli.sh start
cd $DEV/server/yufeng_panel && ./cli.sh stop

sleep 5
cd $DEV/server/yufeng_panel && ./scripts/init.d/yf default
cd $DEV/server/yufeng_panel && ./cli.sh debug