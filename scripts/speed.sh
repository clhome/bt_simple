#!/bin/bash
# ==========================================================
# 御风面板 (BT-Simple) 服务器测速脚本
# ==========================================================
export LANG=en_US.UTF-8

echo "=========================================================="
echo "          御风面板 (BT-Simple) 服务器测速工具"
echo "=========================================================="
echo " 开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "----------------------------------------------------------"
echo " [1] 系统基本信息"

# 获取 CPU 型号
cpu_model=$(grep -m1 'model name' /proc/cpuinfo | awk -F: '{print $2}' | sed 's/^[ \t]*//;s/[ \t]*$//')
if [ -z "$cpu_model" ]; then
    cpu_model=$(lscpu | grep 'Model name' | awk -F: '{print $2}' | sed 's/^[ \t]*//;s/[ \t]*$//')
fi
if [ -z "$cpu_model" ]; then
    cpu_model="未知 CPU"
fi

# CPU 核心数
cpu_cores=$(grep -c 'processor' /proc/cpuinfo)
if [ "$cpu_cores" -eq 0 ]; then
    cpu_cores="未知"
fi

# 内存大小
mem_total=$(free -m 2>/dev/null | awk '/Mem:/{print $2}')
if [ -z "$mem_total" ]; then
    mem_total="未知"
else
    mem_total="${mem_total} MB"
fi

# 硬盘使用情况
disk_total=$(df -h / 2>/dev/null | awk 'NR==2{print $2}')
disk_used=$(df -h / 2>/dev/null | awk 'NR==2{print $3}')
disk_avail=$(df -h / 2>/dev/null | awk 'NR==2{print $4}')
if [ -z "$disk_total" ]; then
    disk_total="未知"
    disk_used="未知"
    disk_avail="未知"
fi

# 操作系统
os_info=""
if [ -f /etc/redhat-release ]; then
    os_info=$(cat /etc/redhat-release)
elif [ -f /etc/os-release ]; then
    os_info=$(grep 'PRETTY_NAME' /etc/os-release | cut -d'"' -f2)
elif [ -f /etc/issue ]; then
    os_info=$(cat /etc/issue | head -n1)
fi
if [ -z "$os_info" ]; then
    os_info=$(uname -s)
fi

echo " CPU 型号: $cpu_model ($cpu_cores 核)"
echo " 物理内存: $mem_total"
echo " 硬盘分区: 根分区共 $disk_total, 已用 $disk_used, 剩余 $disk_avail"
echo " 操作系统: $os_info"
echo " 系统架构: $(uname -m)"
echo " 内核版本: $(uname -r)"

echo "----------------------------------------------------------"
echo " [2] 磁盘 I/O 读写性能测试"
echo " 正在进行磁盘写入测试 (写入 512MB 数据)..."

# 写入测试
dd_write_result=$(dd if=/dev/zero of=./speed_test_io_temp bs=1M count=512 conv=fdatasync 2>&1)
write_speed=$(echo "$dd_write_result" | tail -n 1 | awk -F, '{print $NF}' | sed 's/^[ \t]*//;s/[ \t]*$//')
if [ -z "$write_speed" ]; then
    write_speed=$(echo "$dd_write_result" | tail -n 1 | awk '{print $(NF-1), $NF}')
fi
echo " 磁盘写入速度: $write_speed"

# 尝试清除系统缓存（如果具有 root 权限）
if [ $(id -u) -eq 0 ]; then
    sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
fi

echo " 正在进行磁盘读取测试 (读取 512MB 数据)..."
# 读取测试
dd_read_result=$(dd if=./speed_test_io_temp of=/dev/null bs=1M count=512 2>&1)
read_speed=$(echo "$dd_read_result" | tail -n 1 | awk -F, '{print $NF}' | sed 's/^[ \t]*//;s/[ \t]*$//')
if [ -z "$read_speed" ]; then
    read_speed=$(echo "$dd_read_result" | tail -n 1 | awk '{print $(NF-1), $NF}')
fi
echo " 磁盘读取速度: $read_speed"

# 清理临时文件
rm -f ./speed_test_io_temp

echo "----------------------------------------------------------"
echo " [3] 网络下载速度测试 (多区域节点)"

# 测速函数
test_download() {
    local node_name=$1
    local download_url=$2
    echo "  -> 节点: ${node_name} ... 正在测试"
    
    # 限制下载时间最大 8 秒，并丢弃下载的内容
    local res=$(curl -L -s -o /dev/null -w "%{speed_download}" --connect-timeout 4 -m 8 "$download_url" 2>/dev/null)
    
    # 判断是否成功下载
    if [ -z "$res" ] || [ $(echo "$res" | awk '{print ($1 == 0 ? "yes" : "no")}') = "yes" ]; then
        echo "  -> 节点: ${node_name} ... 连接超时或失败"
    else
        local speed_mbps=$(echo "$res" | awk '{print sprintf("%.2f", $1 * 8 / 1024 / 1024)}')
        echo "  -> 节点: ${node_name} ... ${speed_mbps} Mbps"
    fi
}

# 测试不同的云节点
test_download "阿里云杭州镜像源" "https://mirrors.aliyun.com/debian/ls-lR.gz"
test_download "腾讯云南京镜像源" "https://mirrors.cloud.tencent.com/debian/ls-lR.gz"
test_download "华为云深圳镜像源" "https://mirrors.huaweicloud.com/debian/ls-lR.gz"

echo "----------------------------------------------------------"
echo "  -> 分割线: 境外测试节点"

test_download "美国官方节点" "http://ftp.us.debian.org/debian/ls-lR.gz"
test_download "英国官方节点" "http://ftp.uk.debian.org/debian/ls-lR.gz"
test_download "德国官方节点" "http://ftp.de.debian.org/debian/ls-lR.gz"
test_download "日本官方节点" "http://ftp.jp.debian.org/debian/ls-lR.gz"

echo "----------------------------------------------------------"
echo " 测速完毕！所有临时文件已清理。"
echo " 结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="
