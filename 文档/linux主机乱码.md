## debian/ubuntu 乱码

> **文档目的：** 将 Linux 系统默认语言修复为标准的英文 UTF-8 环境，同时保持对中文字符集的完美兼容，彻底解决终端、脚本提示、彩色控制字符显示的乱码问题。

### 0.首先用locale检查语言是否正确

默认正确，则跳过

```sh
root@debian:~# locale
LANG=en_US.UTF-8
LANGUAGE=en_US:en
LC_CTYPE="en_US.UTF-8"
LC_NUMERIC="en_US.UTF-8"
LC_TIME="en_US.UTF-8"
LC_COLLATE="en_US.UTF-8"
LC_MONETARY="en_US.UTF-8"
LC_MESSAGES="en_US.UTF-8"
LC_PAPER="en_US.UTF-8"
LC_NAME="en_US.UTF-8"
LC_ADDRESS="en_US.UTF-8"
LC_TELEPHONE="en_US.UTF-8"
LC_MEASUREMENT="en_US.UTF-8"
LC_IDENTIFICATION="en_US.UTF-8"
LC_ALL=
root@debian:~# 
```

下面情况会导致有乱码出现

```sh
root@debian:~# locale                                                                                                                                                                                                 
LANG=C
LANGUAGE=C
LC_CTYPE="C"
LC_NUMERIC="C"
LC_TIME="C"
LC_COLLATE="C"
LC_MONETARY="C"
LC_MESSAGES="C"
LC_PAPER="C"
LC_NAME="C"
LC_ADDRESS="C"
LC_TELEPHONE="C"
LC_MEASUREMENT="C"
LC_IDENTIFICATION="C"
LC_ALL=
```



### 1. 彻底启用系统语言包支持

Debian 系统的语言包生成依赖于 `/etc/locale.gen` 配置文件。首先需要解除对英文和中文语言包的注释：

Bash

```sh
# 解除英文 UTF-8 语言包的注释
sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen

# 解除中文 UTF-8 语言包的注释（确保系统能正常识别和显示中文）
sed -i 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen
```

### 2. 编译并生成语言包

确保环境管理器已安装，并根据刚才修改的配置文件，在底层重新编译生成对应的本地化文件：

Bash

```sh
# 确保本地化管理工具已安装
apt-get update && apt-get install -y locales

# 触发系统重新生成语言包
locale-gen
```

> **预期输出：**
>
> 
>
> ```sh
> Generating locales (this might take a while)...
>   en_US.UTF-8... done
>   zh_CN.UTF-8... done
> Generation complete.
> ```

### 3. 设定系统默认语言为全局英文 (UTF-8)

将全局环境变量写入系统配置文件，将其固定为默认英文环境：

Bash

```sh
# 设置全局默认语言为英文 UTF-8
update-locale LANG=en_US.UTF-8 LANGUAGE=en_US:en
```

### 4. 使配置立即生效与验证

无需重启整台服务器，直接刷新当前会话的语言配置文件：

Bash

```sh
# 刷新当前 shell 会话
source /etc/default/locale

# 验证当前环境
locale
```

