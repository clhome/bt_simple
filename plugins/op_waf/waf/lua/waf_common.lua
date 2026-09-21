local waf_root = "{$WAF_ROOT}"
local waf_cpath = waf_root.."/waf/lua/?.lua;"..waf_root.."/waf/conf/?.lua;"..waf_root.."/waf/html/?.lua;"
local waf_sopath = waf_root.."/waf/conf/?.so;"

if not package.path:find(waf_cpath) then
    package.path = waf_cpath  .. package.path
end

if not package.cpath:find(waf_sopath) then
    package.cpath = waf_sopath .. package.cpath
end

local setmetatable = setmetatable
local _M = { _VERSION = '0.02' }
local mt = { __index = _M }

local json = require "cjson"
local sqlite3 = require "lsqlite3"

local ngx_re = require "ngx.re"
local ngx_match = ngx.re.find

local debug_mode = false

local cpath = waf_root.."/waf/"
local log_dir = waf_root.."/logs/"
local resty_sha256 = require "resty.sha256"
local str = require "resty.string"
local bit = require "bit"

function _M.hmac_sha256(self, key, text)
    local block_size = 64
    if #key > block_size then
        local s = resty_sha256:new()
        s:update(key)
        key = s:final()
    end
    key = key .. string.rep(string.char(0), block_size - #key)
    local o_key_pad_tb = {}
    local i_key_pad_tb = {}
    for i=1, block_size do
        table.insert(o_key_pad_tb, string.char(bit.bxor(string.byte(key, i), 0x5c)))
        table.insert(i_key_pad_tb, string.char(bit.bxor(string.byte(key, i), 0x36)))
    end
    local o_key_pad = table.concat(o_key_pad_tb)
    local i_key_pad = table.concat(i_key_pad_tb)
    local s1 = resty_sha256:new()
    s1:update(i_key_pad)
    s1:update(text)
    local inner_hash = s1:final()
    
    local s2 = resty_sha256:new()
    s2:update(o_key_pad)
    s2:update(inner_hash)
    return str.to_hex(s2:final())
end

local rpath = cpath.."/rule/"

local ipmatcher
pcall(function()
    ipmatcher = require("resty.ipmatcher")
end)

function _M.ip2num(self, ip_arr)
    return ip_arr[1] * 16777216 + ip_arr[2] * 65536 + ip_arr[3] * 256 + ip_arr[4]
end

function _M.num2ip(self, n)
    local d = n % 256
    n = math.floor(n / 256)
    local c = n % 256
    n = math.floor(n / 256)
    local b = n % 256
    n = math.floor(n / 256)
    local a = n % 256
    return a .. "." .. b .. "." .. c .. "." .. d
end

function _M.range2cidrs(self, start_num, end_num)
    local cidrs = {}
    while start_num <= end_num do
        local max_size = 32
        while max_size > 0 do
            local bits = 32 - (max_size - 1)
            local mask = math.pow(2, bits)
            local rem = start_num % mask
            if rem ~= 0 then
                break
            end
            if start_num + mask - 1 > end_num then
                break
            end
            max_size = max_size - 1
        end
        local size = math.pow(2, 32 - max_size)
        table.insert(cidrs, self:num2ip(start_num) .. "/" .. max_size)
        start_num = start_num + size
    end
    return cidrs
end

local cached_matchers = {}

function _M.get_ipmatcher(self, rules, cache_key)
    if not ipmatcher then
        return nil
    end
    
    local version_key = cache_key .. "_version"
    local current_version = ngx.shared.waf_limit and ngx.shared.waf_limit:get(version_key) or 0
    
    if cached_matchers[cache_key] and cached_matchers[cache_key].version == current_version then
        return cached_matchers[cache_key].matcher
    end
    
    local ips = {}
    for _, rule in ipairs(rules) do
        if type(rule) == "string" then
            table.insert(ips, rule)
        elseif type(rule) == "table" then
            if type(rule[1]) == "number" and type(rule[2]) == "string" then
                if rule[1] == 1 then
                    table.insert(ips, rule[2])
                end
            elseif type(rule[1]) == "string" then
                table.insert(ips, rule[1])
            elseif type(rule[1]) == "table" and type(rule[2]) == "table" then
                local start_num = self:ip2num(rule[1])
                local end_num = self:ip2num(rule[2])
                local cidrs = self:range2cidrs(start_num, end_num)
                for _, cidr in ipairs(cidrs) do
                    table.insert(ips, cidr)
                end
            end
        end
    end
    
    local matcher, err = ipmatcher.new(ips)
    if matcher then
        cached_matchers[cache_key] = { matcher = matcher, version = current_version }
    else
        self:D("ipmatcher create error: " .. tostring(err))
    end
    return matcher
end

function _M.new(self)

    local self = {
        waf_root = waf_root,
        cpath = cpath,
        rpath = rpath,
        logdir = log_dir,
        config = '',
        site_config = '',
        server_name = '',
        global_tatal = nil,
        params = nil,
    }
    return setmetatable(self, mt)
end


-- function _M.getInstance(self)
--     if rawget(self, "instance") == nil then
--         rawset(self, "instance", self.new())
--     end
--     assert(self.instance ~= nil)
--     return self.instance
-- end

function _M.getInstance(self)
    if self.instance == nil then
        self.instance = self:new()
    end
    assert(self.instance ~= nil)
    return self.instance
end

-- 后台任务
function _M.cron(self)
    
    local timer_every_import_data = function(premature)
        local ok, err = pcall(function()
            local llen, _ = ngx.shared.waf_limit:llen('waf_limit_logs')
            if not llen or llen == 0 then
                return true
            end

            local db = self:initDB()
            if not db then
                return false
            end

            db:exec([[BEGIN TRANSACTION]])

            local stmt2 = db:prepare[[INSERT INTO logs(time, ip, domain, server_name, method, status_code, uri, user_agent, rule_name, reason) 
                VALUES(:time, :ip, :domain, :server_name, :method, :status_code, :uri, :user_agent, :rule_name, :reason)]]

            if not stmt2 then
                self:D("waf timer db:prepare fail!:"..tostring(stmt2))
                if db:isopen() then db:close() end
                return false
            end

            local max_batch = math.min(llen, 200)
            for i=1, max_batch do
                local data, _ = ngx.shared.waf_limit:lpop('waf_limit_logs')
                if not data then
                    break
                end

                local ok_decode, info = pcall(json.decode, data)
                if ok_decode and info then
                    stmt2:bind_names{
                        time=info["time"],
                        ip=info["ip"],
                        domain=info["server_name"],
                        server_name=info["server_name"],
                        method=info["method"],
                        status_code=info["status_code"],
                        user_agent=info["user_agent"],
                        uri=info["request_uri"],
                        rule_name=info['rule_name'],
                        reason=info['reason']
                    }

                    local res, err = stmt2:step()
                    if tostring(res) == "5" then
                        self:D("waf the step database connection is busy, so it will be stored later.")
                        ngx.shared.waf_limit:lpush('waf_limit_logs', data)
                        break
                    end
                    stmt2:reset() 
                end
            end

            if stmt2 then stmt2:finalize() end

            local res, err = db:execute([[COMMIT]])
            if db and db:isopen() then
                db:close()
            end
        end)

        if not ok then
            ngx.log(ngx.ERR, "timer_every_import_data pcall fail: ", tostring(err))
        end
    end
    ngx.timer.every(3, timer_every_import_data)
end

function _M.initDB(self)
    local path = log_dir .. "/waf.db"
    local db, err = sqlite3.open(path)

    if err then
        self:D("initDB err:"..tostring(err))
        return nil
    end

    db:busy_timeout(3000)
    db:exec([[PRAGMA synchronous = 0]])
    db:exec([[PRAGMA cache_size = 8000]])
    db:exec([[PRAGMA page_size = 32768]])
    db:exec([[PRAGMA journal_mode = wal]])
    db:exec([[PRAGMA journal_size_limit = 1073741824]])
    return db
end

function _M.clean_log(self)
    local db = self:initDB()
    if not db then return false end
    local now_date = os.date("*t")
    local save_day = 90
    local save_date_timestamp = os.time{year=now_date.year,
        month=now_date.month, day=now_date.day-save_day, hour=0}
    -- delete expire data from logs table
    db:exec("DELETE FROM logs WHERE time<"..tostring(save_date_timestamp))
    if db and db:isopen() then
        db:close()
    end
end

function _M.log(self, args, rule_name, reason)

    -- Ensure lazy-loaded fields required by the database are materialized
    local _ = args.time
    local _ = args.ip
    local _ = args.server_name
    local _ = args.method
    local _ = args.status_code
    local _ = args.user_agent
    local _ = args.request_uri

    args["rule_name"] = rule_name
    args["reason"] = reason

    local push_data = json.encode(args)

    local llen, err = ngx.shared.waf_limit:llen("waf_limit_logs")
    if llen and llen >= 50000 then
        -- Drop log if queue is too large
        self:dict_incr("waf_limit", "logs_drop_count", 1, 0)
        return true
    end

    ngx.shared.waf_limit:rpush("waf_limit_logs", push_data)
    -- self:D("push_data:"..push_data)

    -- local db = self:initDB()

    -- local stmt2 = db:prepare[[INSERT INTO logs(time, ip, domain, server_name, method, status_code, uri, user_agent, rule_name, reason) 
    --     VALUES(:time, :ip, :domain, :server_name, :method, :status_code, :uri, :user_agent, :rule_name, :reason)]]

    -- db:exec([[BEGIN TRANSACTION]])

    -- stmt2:bind_names{
    --     time=args["time"],
    --     ip=args["ip"],
    --     domain=args["server_name"],
    --     server_name=args["server_name"],
    --     method=args["method"],
    --     status_code=args["status_code"],
    --     user_agent=args["user_agent"],
    --     uri=args["request_uri"],
    --     rule_name=rule_name,
    --     reason=reason
    -- }

    -- local res, err = stmt2:step()
    -- -- self:D("LOG[1]:"..tostring(res)..":"..tostring(err))

    -- if tostring(res) == "5" then
    --     self.D("waf the step database connection is busy, so it will be stored later.")
    --     return false
    -- end
    -- stmt2:reset()

    -- local res, err = db:execute([[COMMIT]])
    -- -- self:D("LOG[2]:"..tostring(res)..":"..tostring(err))
    -- if db and db:isopen() then
    --     db:close()
    -- end
    -- return true
end


function _M.setDebug(self, mode)
    debug_mode = false
end

function _M.dict_set(self, dict_name, key, value, exptime)
    local dict = ngx.shared[dict_name]
    if dict then
        exptime = exptime or 0
        local ok, err = dict:set(key, value, exptime)
        if not ok then
            ngx.log(ngx.ERR, "shared dict ["..tostring(dict_name).."] set error: ", tostring(err))
        end
        return ok
    end
    return false
end

function _M.dict_incr(self, dict_name, key, value, init, init_ttl)
    local dict = ngx.shared[dict_name]
    if dict then
        local ok, err = dict:incr(key, value, init, init_ttl)
        if not ok then
            ngx.log(ngx.ERR, "shared dict ["..tostring(dict_name).."] incr error: ", tostring(err))
        end
        return ok
    end
    return false
end


-- 调试方式
function _M.D(self, msg)
    if not debug_mode then return true end

    local _msg = ''
    if type(msg) == 'table' then
        _msg = _msg.."args->\n"
        for key, val in pairs(msg) do
            _msg = _msg..tostring(key)..':'..tostring(val).."\n"
        end
    elseif type(msg) == 'string' then
        _msg = msg
     elseif type(msg) == 'nil' then
        _msg = 'nil'
    else
        _msg = msg
    end

    local fp = io.open(waf_root.."/debug.log", "ab")
    if fp == nil then
        return nil
    end

    -- local localtime = os.date("%Y-%m-%d %H:%M:%S")
    local localtime = ngx.localtime()
    if server_name then
        fp:write(tostring(_msg) .. "\n")
    else
        fp:write(localtime..":"..tostring(_msg) .. "\n")
    end

    fp:flush()
    fp:close()
    return true
end

function _M.is_working(self,sign)
    local work_status = ngx.shared.waf_limit:get(sign.."_working")
    if work_status ~= nil and work_status == true then
        return true 
    end
    return false
end

function _M.lock_working(self, sign)
    local working_key = sign.."_working"
    self:dict_set("waf_limit", working_key, true, 60)
end

function _M.unlock_working(self, sign)
    local working_key = sign.."_working"
    self:dict_set("waf_limit", working_key, false)
end

function _M.add_reputation_penalty(self, ip, points, reason)
    if not ip or ip == "unknown" then return end
    
    local key = "reputation_score:" .. ip
    local current_score = ngx.shared.waf_limit:get(key)
    
    if not current_score then
        self:dict_set("waf_limit", key, points, 86400)
        current_score = points
    else
        ngx.shared.waf_limit:incr(key, points)
        current_score = current_score + points
    end
    
    if current_score >= 100 then
        local drop_key = ip
        self:dict_set("waf_drop_ip", drop_key, 999, 86400)
        local params = self.params or {ip = ip}
        self:log(params, 'scan', "信誉归零，触发自动拉黑 24 小时 (" .. reason .. ")")
        -- 御风F2B防火墙情报联动：信誉归零是最高级别威胁，同步交给内核层持久封禁
        self:push_ban_sync(ip, 86400, "reputation:" .. tostring(reason))
        
        -- Reset the score to avoid redundant logging
        self:dict_set("waf_limit", key, 0, 86400)
    end
end


-- ============================================================
-- 御风F2B防火墙（fail2ban）情报联动 —— 生产侧
-- ============================================================
-- 架构：本插件（应用层 L7）负责**发现**，fail2ban（内核层 L3/L4）负责**持久封禁**。
-- 两侧唯一契约是 spool 文件的文本格式，无模块依赖、无端口依赖、无鉴权面。
--
-- 性能设计（实时防火墙，攻击强度不可预估）：
--   1. 请求路径只多一次 rpush，且**仅在「真实封禁发生」时**触发，不是每个请求；
--   2. 真正的文件 IO 全部由 init_worker 的 ngx.timer 在 light thread 中批量完成，
--      请求路径零阻塞、零文件句柄、零网络调用；
--   3. 情报队列与日志队列 waf_limit_logs **分离**：日志队列满时会降级丢弃，
--      但绝不会拖累封禁情报（情报的价值高于日志）；
--   4. 开关关闭时 push_ban_sync 首行即返回，开销仅一次 table 取值。
local BAN_SYNC_QUEUE = "waf_ban_sync"
local BAN_SYNC_MAX = 5000                     -- 队列上限，防对端长期不可用时无限膨胀
local BAN_SYNC_BATCH = 200                    -- 单次 timer 最多落盘条数
local BAN_SYNC_SPOOL_MAX = 4 * 1024 * 1024    -- spool 上限 4MB，超出则截断重建


-- 廉价的 IP 形态校验：只拦明显垃圾数据，权威校验交给 fail2ban 侧的 safe_ip()
local function is_ip_like(ip)
    if type(ip) ~= "string" or #ip < 7 or #ip > 45 then return false end
    if string.find(ip, "^%d+%.%d+%.%d+%.%d+$") then return true end
    if string.find(ip, ":", 1, true) and string.find(ip, "^[%x:%.]+$") then return true end
    return false
end


-- 入队一条封禁情报（在请求路径中调用，必须极快）
function _M.push_ban_sync(self, ip, ttl, reason)
    local bs = self.config and self.config['ban_sync']
    if not bs or bs['open'] ~= true then return false end
    if not is_ip_like(ip) then return false end

    local dict = ngx.shared.waf_limit
    if not dict then return false end

    local llen = dict:llen(BAN_SYNC_QUEUE)
    if llen and llen >= BAN_SYNC_MAX then
        -- 对端长期不可用：丢弃并计数，避免无界增长拖垮共享内存
        dict:incr("ban_sync_drop", 1, 0)
        return false
    end

    local ok, item = pcall(json.encode, {
        ip = ip,
        ttl = tonumber(ttl) or 0,
        reason = string.sub(tostring(reason or ""), 1, 120),
        ts = ngx.time(),
    })
    if not ok or not item then return false end

    dict:rpush(BAN_SYNC_QUEUE, item)
    return true
end


-- 批量出队并追加写入 spool（只在 ngx.timer 的 light thread 中调用）
function _M.flush_ban_sync(self)
    local bs = self.config and self.config['ban_sync']
    if not bs or bs['open'] ~= true then return 0 end

    local dict = ngx.shared.waf_limit
    if not dict then return 0 end

    local llen = dict:llen(BAN_SYNC_QUEUE)
    if not llen or llen == 0 then return 0 end

    local batch = llen
    if batch > BAN_SYNC_BATCH then batch = BAN_SYNC_BATCH end

    -- 同批按 IP 去重：同一 IP 在一批里只写一行，减少 fail2ban 侧无谓解析
    local seen, items = {}, {}
    for _ = 1, batch do
        local raw = dict:lpop(BAN_SYNC_QUEUE)
        if not raw then break end
        local ok, info = pcall(json.decode, raw)
        if ok and info and info['ip'] and not seen[info['ip']] then
            seen[info['ip']] = true
            items[#items + 1] = info
        end
    end
    if #items == 0 then return 0 end

    local path = log_dir .. "ban_spool.log"

    -- 尺寸保护：超过上限时截断重建。
    -- fail2ban 检测到文件被截断会从头部重读，而重放旧封禁是幂等的
    -- （已封禁的 IP 不会被重复封禁），因此这一步是安全的。
    local fh = io.open(path, "r")
    if fh then
        local size = fh:seek("end")
        fh:close()
        if size and size > BAN_SYNC_SPOOL_MAX then
            local trunc = io.open(path, "w")
            if trunc then trunc:close() end
        end
    end

    local fp = io.open(path, "a")
    if not fp then
        -- 写不进去（权限 / 磁盘满）：原样放回队列尾部等待重试，绝不丢情报
        for i = #items, 1, -1 do
            local ok, raw = pcall(json.encode, items[i])
            if ok and raw then dict:lpush(BAN_SYNC_QUEUE, raw) end
        end
        ngx.log(ngx.ERR, "op_waf ban_sync: cannot open spool file ", path)
        return 0
    end

    local now = ngx.localtime()
    local lines = {}
    for i = 1, #items do
        local info = items[i]
        lines[i] = string.format(
            "%s op_waf[ban] WARNING Ban %s ttl=%d reason=%s",
            now, info['ip'], tonumber(info['ttl']) or 0,
            tostring(info['reason'] or "op_waf"))
    end

    fp:write(table.concat(lines, "\n") .. "\n")
    fp:flush()
    fp:close()
    return #lines
end


local function write_file_clear(filename, body)
    local fp = io.open(filename,'w')
    if fp == nil then
        return nil
    end
    fp:write(body)
    fp:flush()
    fp:close()
    return true
end

function _M.setConfData( self, config, site_config )
    self.config = config
    self.site_config = site_config

end


function _M.setParams( self, params )
    self.params = params
end

function _M.count_size(data)
    local count=0
    if type(data)~="table" then return count end 
    for k,v in pairs(data) 
    do
        count=count+1
    end 
    return count
end 


function _M.is_min(self, ip1, ip2)
    local n = 0
    for _,v in ipairs({1,2,3,4})
    do
        if ip1[v] == ip2[v] then
            n = n + 1
        elseif ip1[v] > ip2[v] then
            break
        else
            return false
        end
    end
    return true
end

function _M.is_max(self,ip1,ip2)
    local n = 0
    for _,v in ipairs({1,2,3,4})
    do
        if ip1[v] == ip2[v] then
            n = n + 1
        elseif ip1[v] < ip2[v] then
            break
        else
            return false
        end
    end
    return true
end

function _M.split(self, str,reps )
    local rsList = {}
    string.gsub(str,'[^'..reps..']+',function(w)
        table.insert(rsList,w)
    end)
    return rsList
end

function _M.arrip(self, ipstr)
    if ipstr == 'unknown' then return {0,0,0,0} end
    if string.find(ipstr,':') then return ipstr end
    local iparr = self:split(ipstr,'.')
    iparr[1] = tonumber(iparr[1])
    iparr[2] = tonumber(iparr[2])
    iparr[3] = tonumber(iparr[3])
    iparr[4] = tonumber(iparr[4])
    return iparr
end


function _M.compare_ip(self,ips)
    local ip = self.params["ip"]
    local ipn = self.params["ipn"]
    if ip == 'unknown' then return true end
    if string.find(ip,':') then return false end
    if not self:is_max(ipn,ips[2]) then return false end
    if not self:is_min(ipn,ips[1]) then return false end
    return true
end



function _M.to_json(self, msg)
    return json.encode(msg)
end

function _M.return_state(status,msg)
    local result = {}
    result['status'] = status
    result['msg'] = msg
    return result
end

function _M.return_message(self, status, msg)
    ngx.header.content_type = "application/json"
    local data = self:return_state(status, msg)
    ngx.say(json.encode(data))
    ngx.exit(200)
end

function _M.return_html(self, status, html)
    ngx.header.content_type = "text/html"
    ngx.header.Cache_Control = "no-cache"
    status = tonumber(status)

    -- self:D("return_html:"..tostring(status))
    if status == 200 then
        ngx.say(html)
    end
    ngx.exit(status)
end

function _M.read_file_body(self, filename)
    local fp = io.open(filename, 'r')
    if fp == nil then
        return nil
    end
    local fbody = fp:read("*a")
    fp:close()
    if fbody == '' then
        return nil
    end
    return fbody
end

function _M.read_file(self, name)
    local f = self.rpath .. name .. '.json'
    local fbody = self:read_file_body(f)
    if fbody == nil then
        return {}
    end

    local data = json.decode(fbody)
    return data
end

function _M.file_exists(self,path)
  local file = io.open(path, "rb")
  if file then file:close() end
  return file ~= nil
end


function _M.select_rule(self, rules)
    if not rules then return {} end
    local new_rules = {}
    for i,v in ipairs(rules)
    do 
        if v[1] == 1 then
            table.insert(new_rules,v[2])
        end
    end
    return new_rules
end

function _M.read_file_table( self, name )
    return self:select_rule(self:read_file(name))
end


function _M.read_file_body_decode(self, name)
    return json.decode(self:read_file_body(name))
end

function _M.write_file(self, filename, body)
    local fp = io.open(filename,'ab')
    if fp == nil then
        return nil
    end
    fp:write(body)
    fp:flush()
    fp:close()
    return true
end

function _M.write_file_clear(self, filename, body)
    return write_file_clear(filename, body)
end

function _M.write_to_file(self, logstr)
    local server_name = self.params['server_name']
    local filename = self.logdir .. '/' .. server_name .. '_' .. ngx.today() .. '.log'
    self:write_file(filename, logstr)
    return true
end

-- 是否文件迁入数据库中
function  _M.is_migrating(self)
    local migrating = self.waf_root +"/migrating"
    local file = io.open(migrating, "rb")
    if file then return true end
    return false
end


function _M.continue_key(self,key)
    key = tostring(key)
    if string.len(key) > 64 then return false end;
    local keys = { "content", "contents", "body", "msg", "file", "files", "img", "newcontent" }
    for _,k in ipairs(keys)
    do
        if k == key then return false end;
    end
    return true;
end


function _M.array_len(self, arr)
    if not arr then return 0 end
    local count = 0
    for _,v in ipairs(arr)
    do
        count = count + 1
    end
    return count
end

function _M.is_ipaddr(self, client_ip)
    local cipn = self:split(client_ip,'.')
    if self:array_len(cipn) < 4 then return false end
    for _,v in ipairs({1,2,3,4})
    do
        local ipv = tonumber(cipn[v])
        if ipv == nil then return false end
        if ipv > 255 or ipv < 0 then return false end
    end
    return true
end

-- 定时异步同步统计信息
function _M.timer_stats_total(self)
    local total_path = self.cpath .. 'total.json'
    local total = nil
    local total_cached = ngx.shared.waf_limit:get(total_path)
    if total_cached then
        local ok, data = pcall(json.decode, total_cached)
        if ok and type(data) == 'table' then
            total = data
        end
    end

    if not total then
        local tbody = self:read_file_body(total_path)
        if tbody then
            local ok, data = pcall(json.decode, tbody)
            if ok and type(data) == 'table' then
                total = data
            end
        end
    end

    if not total then
        total = {
            total = 0,
            today_date = ngx.today(),
            today_total = 0,
            rules = {},
            sites = {}
        }
    end

    -- 检查并合并共享内存中的原子增量
    local inc_total = ngx.shared.waf_limit:get("stat:inc:total")
    if inc_total and inc_total > 0 then
        ngx.shared.waf_limit:incr("stat:inc:total", -inc_total)
        total['total'] = (total['total'] or 0) + inc_total

        local today = ngx.today()
        if not total['today_date'] or total['today_date'] ~= today then
            total['today_date'] = today
            total['today_total'] = 0
        end

        local inc_today = ngx.shared.waf_limit:get("stat:inc:today:" .. today)
        if inc_today and inc_today > 0 then
            ngx.shared.waf_limit:incr("stat:inc:today:" .. today, -inc_today)
            total['today_total'] = (total['today_total'] or 0) + inc_today
        end

        -- 提取所有规则增量
        if not total['rules'] then total['rules'] = {} end
        local rule_keys = {"args", "url", "scan", "post", "cookie", "user_agent", "cc", "spider", "upload_ext", "upload_mime", "upload_header", "xxe", "ssrf"}
        for _, rname in ipairs(rule_keys) do
            local inc_r = ngx.shared.waf_limit:get("stat:inc:rule:" .. rname)
            if inc_r and inc_r > 0 then
                ngx.shared.waf_limit:incr("stat:inc:rule:" .. rname, -inc_r)
                total['rules'][rname] = (total['rules'][rname] or 0) + inc_r
            end
        end

        -- 提取站点增量
        local site_keys = ngx.shared.waf_limit:get_keys(0)
        if site_keys then
            if not total['sites'] then total['sites'] = {} end
            for _, sk in ipairs(site_keys) do
                local prefix = "stat:inc:site:"
                if string.sub(sk, 1, #prefix) == prefix then
                    local rest = string.sub(sk, #prefix + 1)
                    local parts = self:split(rest, ':')
                    if #parts >= 2 then
                        local s_name = parts[1]
                        local r_name = parts[2]
                        local inc_s = ngx.shared.waf_limit:get(sk)
                        if inc_s and inc_s > 0 then
                            ngx.shared.waf_limit:incr(sk, -inc_s)
                            if not total['sites'][s_name] then total['sites'][s_name] = {} end
                            total['sites'][s_name][r_name] = (total['sites'][s_name][r_name] or 0) + inc_s
                        end
                    end
                end
            end
        end

        local encoded = json.encode(total)
        self:dict_set("waf_limit", total_path, encoded)
        return self:write_file_clear(total_path, encoded)
    end
    return true
end

function _M.stats_total(self, name, rule)
    local server_name = (self.params and self.params['server_name']) or ngx.var.server_name or 'unknown'
    local today = ngx.today()

    -- 采用原子累加，拦截主路径毫秒级耗时降至纳秒级，零 GC 停顿
    self:dict_incr("waf_limit", "stat:inc:total", 1, 0)
    self:dict_incr("waf_limit", "stat:inc:today:" .. today, 1, 0)
    self:dict_incr("waf_limit", "stat:inc:rule:" .. name, 1, 0)
    self:dict_incr("waf_limit", "stat:inc:site:" .. server_name .. ":" .. name, 1, 0)
end


-- 获取配置域名
function _M.get_sn(self, config_domains)
    local request_name = ngx.var.server_name
    local cache_name = ngx.shared.waf_limit:get(request_name)
    if cache_name then return cache_name end

    for _,v in ipairs(config_domains)
    do
        for _,cd_name in ipairs(v['domains'])
        do
            if request_name == cd_name then
                self:dict_set("waf_limit", request_name,v['name'],86400)
                return v['name']
            end
        end
    end
    return "unset"
end

function _M.get_random(self,n) 
    math.randomseed(ngx.time())
    local t = {
        "0","1","2","3","4","5","6","7","8","9",
        "a","b","c","d","e","f","g","h","i","j",
        "k","l","m","n","o","p","q","r","s","t",
        "u","v","w","x","y","z",
        "A","B","C","D","E","F","G","H","I","J",
        "K","L","M","N","O","P","Q","R","S","T",
        "U","V","W","X","Y","Z",
    }    
    local s = ""
    for i =1, n do
        s = s .. t[math.random(#t)]
    end
    return s
end



function _M.is_ngx_match_orgin(self, rule, match, sign, unescaped)
    if not match then return false end
    if type(match) ~= "string" then
        match = tostring(match)
    end
    local target = unescaped or ngx.unescape_uri(match)
    if ngx_match(target, rule, "isjo") then
        if self.params then
            self.params.error_rule = rule .. ' >> ' .. sign .. ':' .. match
        end
        return true
    end
    return false
end


function _M.ngx_match_string(self, rule, content, sign)
    local unescaped = content and type(content) == "string" and ngx.unescape_uri(content) or nil
    local t = self:is_ngx_match_orgin(rule, content, sign, unescaped)
    if t then
        return true
    end
  
    return false
end

function _M.ngx_match_list(self, rules, content)
    local args_type = type(content)
    if args_type == 'string' then
        -- 外部仅解码一次，所有规则复用
        local unescaped = ngx.unescape_uri(content)
        for _, rule in ipairs(rules) do
            if rule[1] == 1 then
                local t = self:is_ngx_match_orgin(rule[2], content, rule[3], unescaped)
                if t then
                    return true
                end
            end
        end
    elseif args_type == 'table' then
        -- 预先一次性批量解码 table 中的 values，消除循环内的重复调用
        local prepared = {}
        for _, arg_v in pairs(content) do
            local raw = type(arg_v) == "table" and table.concat(arg_v, ", ") or tostring(arg_v)
            table.insert(prepared, { raw = raw, unescaped = ngx.unescape_uri(raw) })
        end

        for _, rule in ipairs(rules) do
            if rule[1] == 1 then
                for _, item in ipairs(prepared) do
                    local t = self:is_ngx_match_orgin(rule[2], item.raw, rule[3], item.unescaped)
                    if t then
                        return true
                    end
                end
            end
        end
    end
    return false
end

function _M.is_ngx_match_ua(self, rules, content)
    -- ngx.header.content_type = "text/html"
    for i,rule in ipairs(rules)
    do
        -- 开启的规则，才匹配。
        if rule[1] == 1 then
            local t = self:is_ngx_match_orgin(rule[2], content, rule[3])
            if t then
                return true
            end
        end
    end
    return false
end

function _M.is_ngx_match_post(self, rules, content)
    for i,rule in ipairs(rules)
    do
        -- 开启的规则，才匹配。
        if rule[1] == 1 then
            local t = self:is_ngx_match_orgin(rule[2],content, rule[3])
            if t then
                return true
            end
        end
    end
    return false
end


function _M.write_log(self, name, rule)
    local config = self.config
    local params = self.params

    local ip = params['ip']
    local ngx_time = ngx.time()
    
    local penalty_points = 10
    if name == 'cc' then penalty_points = 5
    elseif name == 'user_agent' then penalty_points = 10
    elseif name == 'scan' then penalty_points = 15
    elseif name == 'args' or name == 'url' or name == 'post' or name == 'cookie' then penalty_points = 15
    end
    self:add_reputation_penalty(ip, penalty_points, "触发防线: " .. name)
    
    local retry = config['retry']['retry']
    local retry_time = config['retry']['retry_time']
    local retry_cycle = config['retry']['retry_cycle']
    
    local count = ngx.shared.waf_drop_ip:get(ip)
    if count then
        self:dict_incr("waf_drop_ip", ip, 1)
    else
        self:dict_set("waf_drop_ip", ip, 1, retry_cycle)
    end

    -- 统计必须在日志开关检查之前执行，确保拦截计数不受日志配置影响
    self:stats_total(name, rule)

    if config['log'] ~= true or self:is_site_config('log') ~= true then return false end
    local method = params['method']
    if self.params and self.params.error_rule then 
        rule = self.params.error_rule
        self.params.error_rule = nil
    end

    local count = ngx.shared.waf_drop_ip:get(ip)
    -- self:D("write_log; count:" ..tostring(count).. ",retry:" .. tostring(retry) )
    if count and count >= 900 then
        self:log(params, name, rule)
    elseif (count > retry and name ~= 'cc') then
        local safe_count,_ = ngx.shared.waf_drop_sum:get(ip)
        if not safe_count then
            self:dict_set("waf_drop_sum", ip, 1, 86400)
            safe_count = 1
        else
            self:dict_incr("waf_drop_sum", ip, 1)
        end
        local lock_time = retry_time * safe_count
        if lock_time > 86400 then lock_time = 86400 end

        local retry_times = retry + 1
        self:dict_set("waf_drop_ip", ip, retry_times, lock_time)

        local reason = retry_cycle .. '秒以内累计超过'..retry..'次以上非法请求,封锁'.. lock_time ..'秒'
        self:log(params, name, reason)
        -- 御风F2B防火墙情报联动：恶意请求累计升级为真实封禁，同步交给内核层
        self:push_ban_sync(ip, lock_time, name .. ':' .. tostring(rule))
    elseif name ~= 'cc' then
        self:log(params, name, rule)
    end
end


function _M.is_trusted_proxy(self, ip, trusted_proxies)
    if not trusted_proxies then return false end
    for _, proxy in ipairs(trusted_proxies) do
        if proxy == ip then return true end
        -- Basic /8 subnet matching for example (e.g. 10.0.0.0/8)
        if string.find(proxy, "/", 1, true) then
            local p_parts = self:split(proxy, '/')
            local p_ip = p_parts[1]
            local p_mask = tonumber(p_parts[2])
            if p_mask == 8 then
                local pipn = self:split(p_ip, '.')
                local cipn = self:split(ip, '.')
                if pipn[1] == cipn[1] then return true end
            end
            -- Additional subnet logic could be added here
        end
    end
    return false
end

function _M.get_real_ip(self, server_name)
    local client_ip = ngx.var.remote_addr
    local site_config = self.site_config
    local is_trusted = false
    local has_trusted_proxy_config = false
    
    if self.config and self.config['trusted_proxy'] and #self.config['trusted_proxy'] > 0 then
        has_trusted_proxy_config = true
        if self:is_trusted_proxy(client_ip, self.config['trusted_proxy']) then
            is_trusted = true
        end
    end

    if site_config[server_name] then
        local cdn_enhanced_open = self.config['cdn_enhanced'] and self.config['cdn_enhanced']['open']
        if is_trusted or (not cdn_enhanced_open and site_config[server_name]['cdn']) then
            local request_header = ngx.req.get_headers()
            for _,v in ipairs(site_config[server_name]['cdn_header'])
            do
                if request_header[v] ~= nil and request_header[v] ~= "" then
                    local header_tmp = request_header[v]
                    if type(header_tmp) == "table" then header_tmp = header_tmp[1] end
                    client_ip = self:split(header_tmp,',')[1]
                    -- return client_ip
                    break;
                end
            end 
        end
    end
    

    -- ipv6
    if type(client_ip) == 'table' then client_ip = "" end
    if client_ip ~= "unknown" and ngx.re.match(client_ip,"^([a-fA-F0-9]*):", "jo") then
        return client_ip
    end

    -- ipv4
    if not ngx.re.match(client_ip,"\\d+\\.\\d+\\.\\d+\\.\\d+", "jo") or not self:is_ipaddr(client_ip) then
        client_ip = ngx.var.remote_addr
        if client_ip == nil then
            client_ip = "unknown"
        end
    end
    return client_ip
end


function _M.is_site_config(self,cname)
    local site_config = self.site_config
    if site_config[server_name] ~= nil then
        if cname == 'cc' then
            return site_config[server_name][cname]['open']
        else
            return site_config[server_name][cname]
        end
    end
    return true
end

function _M.get_boundary(self)
    local header = self.params["request_header"]["content-type"]
    if not header then return nil end
    if type(header) == "table" then
        header = header[1]
    end

    local m = string.match(header, ";%s*boundary=\"([^\"]+)\"")
    if m then
        return m
    end
    return string.match(header, ";%s*boundary=([^\",;]+)")
end


function _M.is_key(self, arr, key)
    for _,v in ipairs(arr) do
        if v == key then
            return true
        end
    end
    return false
end

function _M.get_cpu_stat(self)
    local cpu_total = 0
    local fp = io.open('/proc/stat','r')
    if not fp then return 0, 0, 0 end
    local cpu_line = fp:read()
    fp:close()
    if not cpu_line then return 0, 0, 0 end

    local list = ngx_re.split(cpu_line," ")
    table.remove(list,1)
    table.remove(list,1)

    local idie = tonumber(list[4]) or 0
    for i,v in pairs(list)
    do
        cpu_total = cpu_total + (tonumber(v) or 0)
    end

    local use_percent = 0
    if cpu_total > 0 then
        use_percent = tonumber(100-(idie/cpu_total)*100)
    end
    return cpu_total,idie,use_percent
end

local last_cpu_tick_total = nil
local last_cpu_tick_idle = nil

function _M.get_cpu_percent(self)
    local cpu_total, idie, use_percent = self:get_cpu_stat()
    if cpu_total == 0 then return 0 end

    if not last_cpu_tick_total then
        last_cpu_tick_total = cpu_total
        last_cpu_tick_idle = idie
        return use_percent
    end

    local delta_total = cpu_total - last_cpu_tick_total
    local delta_idle = idie - last_cpu_tick_idle
    last_cpu_tick_total = cpu_total
    last_cpu_tick_idle = idie

    if delta_total <= 0 then return 0 end
    local cpu_usage_percent = tonumber(100 - ((delta_idle / delta_total) * 100))
    if cpu_usage_percent < 0 then cpu_usage_percent = 0 end
    if cpu_usage_percent > 100 then cpu_usage_percent = 100 end
    return cpu_usage_percent
end


function _M.return_post_data(self)
    local method = self.params and self.params['method'] or ngx.req.get_method()
    if method ~= "POST" then return false end
    local content_length = tonumber(self.params["request_header"]['content-length'])
    if not content_length then return false end
    local max_len = 2560 * 1024000
    if content_length > max_len then return false end
    local boundary = self:get_boundary()
    if boundary then
        ngx.req.read_body()
        local data = ngx.req.get_body_data()
        if not data then return false end
        local tmp = ngx.re.match(data,[[filename=\"(.+)\.(.*)\"]], "jo")
        if not tmp then return false end
        if not tmp[2] then return false end
        return tmp[2]
        
    end
    return false
end


function _M.t(self)
    ngx.say(',,,')
end

return _M
