#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

version=$1

if [ "$version" == '5.6' ] || [ "$version" == '56' ]; then
	echo '20131226'
elif [ "$version" == '7.0' ] || [ "$version" == '70' ]; then
	echo '20151012'
elif [ "$version" == '7.1' ] || [ "$version" == '71' ]; then
	echo '20160303'
elif [ "$version" == '7.2' ] || [ "$version" == '72' ]; then
	echo '20170718'
elif [ "$version" == '7.3' ] || [ "$version" == '73' ]; then
	echo '20180731'
elif [ "$version" == '7.4' ] || [ "$version" == '74' ]; then
	echo '20190902'
elif [ "$version" == '8.0' ] || [ "$version" == '80' ]; then
	echo '20200930'
elif [ "$version" == '8.1' ] || [ "$version" == '81' ]; then
	echo '20210902'
elif [ "$version" == '8.2' ] || [ "$version" == '82' ]; then
	echo '20220829'
elif [ "$version" == '8.3' ] || [ "$version" == '83' ]; then
	echo '20230831'
elif [ "$version" == '8.4' ] || [ "$version" == '84' ]; then
	echo '20240924'
elif [ "$version" == '8.5' ] || [ "$version" == '85' ]; then
	echo '20250925'
fi