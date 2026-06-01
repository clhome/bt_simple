# 第一处重大问题：你的插件路径和 OpenStar 实际路径不一致

你机器上执行：

```
cat /www/server/mdserver-web/data/web_conf/nginx/lua/access_by_lua_file/openstar_access.lua
```

返回：

```
没有那个文件或目录
```

说明：

### 你的插件根本没有成功挂载 Lua

而 OpenStar 原版要求的是：

```
init_by_lua_file /opt/openresty/openstar/init.lua;

init_worker_by_lua_file /opt/openresty/openstar/i_worker.lua;

access_by_lua_file /opt/openresty/openstar/access_all.lua;
```

这是我从你上传的源码中发现的：

```
conf/waf.conf
```

内容：

```
access_by_lua_file /opt/openresty/openstar/access_all.lua;
```

------

而你的宝塔插件却在生成：

```
web_conf/nginx/lua/access_by_lua_file/openstar_access.lua
```

这根本不是 OpenStar 原生路径。

------

# 第二处重大问题：OpenStar 安装目录不对

你执行：

```
ls -al /www/server/openstar/main.lua
```

不存在。

这是正常的。

因为你上传的 OpenStar 根本没有：

```
main.lua
```

只有：

```
access_all.lua
init.lua
i_worker.lua
header.lua
body.lua
log.lua
```

所以我现在可以确认：

### 你的插件适配的是另一个版本的 OpenStar

而不是你当前安装的版本。

------

# 第三处重大问题：黑名单实际上存储在共享内存

看源码：

```
init.lua
```

里面：

```
local allowIpList = stool.readfile(_basedir.."ip/allow.ip",true)
local denyIpList  = stool.readfile(_basedir.."ip/deny.ip",true)

ip_dict:safe_set(v,"deny",0)
```

启动时：

```
deny.ip
↓
加载
↓
ip_dict
```

后面请求判断的根本不是文件。

而是：

```
ngx.shared.ip_dict
```

------

# 第四处重大问题（我怀疑这是你现在的核心问题）

看看访问阶段：

```
access_all.lua
```

开头：

```
local remoteIp = ngx.var.remote_addr
```

然后：

```
base_msg.remoteIp = remoteIp
```

后面全部用：

```
remote_addr
```

进行匹配。

------

如果你的站点结构是：

```
Cloudflare
↓
CDN
↓
Nginx
↓
OpenStar
```

或者：

```
SLB
↓
Nginx
↓
OpenStar
```

那么：

```
ngx.var.remote_addr
```

拿到的是：

```
CDN节点IP
```

不是访客IP。

------

你把：

```
1.2.3.4
```

加入黑名单。

实际匹配：

```
104.x.x.x
```

当然不会拦截。

------

# 第五处重大问题：你的插件可能根本没触发 OpenStar 重载

OpenStar 的配置加载流程：

启动：

```
init.lua
```

↓

读取：

```
deny.ip
allow.ip
```

↓

写入：

```
ngx.shared.ip_dict
```

------

如果你后台改了：

```
deny.ip
```

但是没执行：

```
loadConfig()
```

或者：

```
systemctl reload openresty
```

那么：

```
ip_dict
```

里面还是旧数据。

------

# 现在最应该检查什么

## 1 查看 OpenStar 是否真正加载

执行：

```
grep access_by_lua_file -R /usr/local/openresty/nginx/conf
grep access_by_lua_file -R /www/server
```

看看有没有：

```
access_by_lua_file /opt/openresty/openstar/access_all.lua;
```

------

## 2 查看 OpenStar 是否在运行

执行：

```
curl http://127.0.0.1:5460/
```

正常应该返回：

```
{"code":"ok","msg":"openstar system"}
```

如果失败：

```
Connection refused
```

说明 OpenStar API 服务根本没起来。

------

## 3 查看黑名单是否真正进入共享内存

执行：

```
curl "http://127.0.0.1:5460/api/ip_dict?action=get&ip=all_ip"
```

应该返回：

```
{
  "1.2.3.4":"deny"
}
```

如果返回空：

```
{}
```

说明你的插件只是写文件，没有写入：

```
ngx.shared.ip_dict
```

------

## 4 查看 OpenStar 实际识别到的 IP

执行：

```
grep remote_addr /opt/openresty/openstar/access_all.lua
```

你会看到：

```
local remoteIp = ngx.var.remote_addr
```

然后临时加：

```
ngx.log(ngx.ERR,"REMOTE_IP=",remoteIp)
```

重载 OpenResty：

```
openresty -s reload
```

查看：

```
tail -f /opt/openresty/nginx/logs/error.log
```

访问一次网站。

就能看到 OpenStar 实际匹配的是哪个 IP。

------

从你上传的 OpenStar 源码来看，目前我最怀疑的不是黑名单逻辑，而是：

1. **你的宝塔插件适配错了 OpenStar 版本（70%概率）**
2. **OpenStar Lua 根本没有挂到 nginx（20%概率）**
3. **remote_addr 获取到的是代理IP（10%概率）**

如果你把你插件目录中的：

```
index.py
class/openstar.py
```

以及执行：

```
grep -R "access_by_lua_file" /www/server/mdserver-web/plugins/openstar
```

的结果发给我，我基本可以直接定位到为什么“保存黑名单成功，但永远不拦截”。



---

现在已经完全定位到问题了，而且不是黑名单逻辑的问题。

从日志里最关键的几行：

```
DEBUG ip_Mod ip: 172.17.11.248 _ip_v: deny config: true
```

说明：

✅ deny.ip 已加载成功

✅ ngx.shared.ip_dict 已加载成功

✅ access_all.lua 已执行

✅ 黑名单匹配成功

也就是说：

```
ip_dict:get("172.17.11.248")
```

返回了：

```
deny
```

------

然后又出现：

```
action_deny(): DEBUG denycode: 403 next_ctx.http_code: 403
```

说明：

OpenStar 已经决定：

```
return 403
```

了。

------

但是随后出现：

```
attempt to yield across C-call boundary
```

位置：

```
/www/server/openstar/access_all.lua:184
```

而调用栈：

```
[C]: in function 'dofile'
/www/server/web_conf/nginx/lua/access_by_lua_file.lua:6
```

这个才是真正的根因。

------

# 根因分析

你现在的挂载方式是：

```
local status, err = pcall(dofile, access_file)
```

也就是：

```
dofile("/www/server/openstar/access_all.lua")
```

在 `access_by_lua` 阶段执行。

而 OpenStar 的 `access_all.lua` 里面有：

```
ngx.exit()
```

或者：

```
ngx.redirect()
```

或者：

```
coroutine.yield()
```

之类会触发 Nginx Lua 协程切换的代码。

这些代码必须运行在：

```
access_by_lua_file /www/server/openstar/access_all.lua;
```

这样的原生入口中。

不能包一层：

```
pcall(dofile(...))
```

------

OpenResty 官方限制就是：

```
attempt to yield across C-call boundary
```

出现这个错误时：

说明 Lua 协程想退出，

但被：

```
pcall()
dofile()
```

包住了。

------

# 你日志证明了这一点

早期日志：

```
Failed to load openstar access:
/www/server/openstar/access_all.lua:184:
attempt to yield across C-call boundary
```

后面你直接引用：

```
access_by_lua_file /www/server/openstar/access_all.lua;
```

以后：

```
action_deny(): DEBUG denycode: 403
```

就正常了。

------

# 为什么你测试 127.0.0.1 没生效

因为你访问的是：

```
curl http://172.17.60.248
```

日志显示：

```
client: 172.17.60.248
```

所以 OpenStar 实际看到的是：

```
172.17.60.248
```

而不是：

```
127.0.0.1
```

因此：

```
127.0.0.1
```

黑名单当然匹配不到。

这不是 bug。

------

# 你的插件设计问题

你现在生成：

```
openstar_access.lua
```

内容：

```
local status, err = pcall(dofile, access_file)
```

这是错误的。

------

应该生成：

```
access_by_lua_file /www/server/openstar/access_all.lua;
```

直接交给 OpenResty。

不要再套：

```
pcall()
dofile()
```

------

# 建议修改

## 方案1（推荐）

直接修改：

```
makeOpDstRunLua()
```

不要生成：

```
/www/server/web_conf/nginx/lua/access_by_lua_file/openstar_access.lua
```

这种包装文件。

而是在：

```
access_by_lua_file
```

配置中直接写：

```
access_by_lua_file /www/server/openstar/access_all.lua;
```

------

## 方案2

如果必须保留包装层：

改成：

```
package.path = ...
package.cpath = ...

dofile("/www/server/openstar/access_all.lua")
```

不要：

```
pcall()
```

不要：

```
xpcall()
```

不要：

```
coroutine.wrap()
```

------

# 另外一个隐藏问题

你的日志里：

```
host_Mod_state: nil
```

说明：

```
host_dict
```

里面没有：

```
172.17.60.248
```

对应配置。

也就是说：

站点级配置并未加载。

虽然全局黑名单已经生效。

建议检查：

```
grep -n "host_Mod_state" /www/server/openstar/access_all.lua
```

以及：

```
grep -R "172.17.60.248" /www/server/openstar/conf_json
```

看看站点配置是否写入。

------

### 最终结论

从日志可以确定：

**OpenStar 实际已经工作了。**

证据：

```
_ip_v: deny
```

已经证明：

```
deny.ip
→ init.lua
→ ip_dict
→ access_all.lua
```

整个链路正常。

真正导致“黑名单不拦截”的原因是：

```
pcall(dofile(access_all.lua))
```

把 OpenResty 的协程上下文破坏了，

导致：

```
ngx.exit(403)
```

无法正常执行，抛出：

```
attempt to yield across C-call boundary
```

把这一层包装去掉后，黑名单拦截就会恢复正常。