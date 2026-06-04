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
            if llen == 0 then
                return true
            end

            local db = self:initDB()

            db:exec([[BEGIN TRANSACTION]])

            local stmt2 = db:prepare[[INSERT INTO logs(time, ip, domain, server_name, method, status_code, uri, user_agent, rule_name, reason) 
                VALUES(:time, :ip, :domain, :server_name, :method, :status_code, :uri, :user_agent, :rule_name, :reason)]]

            if not stmt2 then
                self:D("waf timer db:prepare fail!:"..tostring(stmt2))
                return false
            end

            for i=1,llen do
                local data, _ = ngx.shared.waf_limit:lpop('waf_limit_logs')
                -- self:D("waf_limit_logs:"..data)
                if not data then
                    break
                end

                local info = json.decode(data)
        
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
                    return false
                end
                stmt2:reset() 
            end

            local res, err = db:execute([[COMMIT]])
            if db and db:isopen() then
                db:close()
            end
        end)

        if not ok then
            ngx.log(ngx.ERR, "timer_every_import_data pcall fail: ", tostring(err))
        end
    end
    ngx.timer.every(0.5, timer_every_import_data)
end

function _M.initDB(self)
    local path = log_dir .. "/waf.db"
    local db, err = sqlite3.open(path)

    if err then
        self:D("initDB err:"..tostring(err))
        return nil
    end

    db:exec([[PRAGMA synchronous = 0]])
    db:exec([[PRAGMA cache_size = 8000]])
    db:exec([[PRAGMA page_size = 32768]])
    db:exec([[PRAGMA journal_mode = wal]])
    db:exec([[PRAGMA journal_size_limit = 1073741824]])
    return db
end

function _M.clean_log(self)
    local db = self:initDB()
    local now_date = os.date("*t")
    local save_day = 90
    local save_date_timestamp = os.time{year=now_date.year,
        month=now_date.month, day=now_date.day-save_day, hour=0}
    -- delete expire data
    db:exec("DELETE FROM web_logs WHERE time<"..tostring(save_date_timestamp))
end

function _M.log(self, args, rule_name, reason)

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
        
        -- Reset the score to avoid redundant logging
        self:dict_set("waf_limit", key, 0, 86400)
    end
end


local function write_file_clear(filename, body)
    fp = io.open(filename,'w')
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
    n = 0
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
    n = 0
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
    iparr = self:split(ipstr,'.')
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
    result = {}
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
    f = self.rpath .. name .. '.json'
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
    new_rules = {}
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
    fp = io.open(filename,'ab')
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
    local total = ngx.shared.waf_limit:get(total_path)
    if not total then
        return false
    end
    return self:write_file_clear(total_path,total)
end

function _M.stats_total(self, name, rule)
    local server_name = self.params['server_name']
    local total_path = cpath .. 'total.json'
    local total = ngx.shared.waf_limit:get(total_path)

    if not total then
        local tbody = self:read_file_body(total_path)
        total = json.decode(tbody)
    else
        total = json.decode(total)
    end

    if not total then return false end

    -- 开始计算
    if not total['sites'] then total['sites'] = {} end
    if not total['sites'][server_name] then total['sites'][server_name] = {} end
    if not total['sites'][server_name][name] then total['sites'][server_name][name] = 0 end
    if not total['rules'] then total['rules'] = {} end
    if not total['rules'][name] then total['rules'][name] = 0 end
    if not total['total'] then total['total'] = 0 end
    total['total'] = total['total'] + 1
    total['sites'][server_name][name] = total['sites'][server_name][name] + 1
    total['rules'][name] = total['rules'][name] + 1

    self:dict_set("waf_limit", total_path,json.encode(total))

    -- 异步执行
    -- 现在改再init_workder.lua 定时执行
    -- ngx.timer.every(3, timer_stats_total_log)
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



function _M.is_ngx_match_orgin(self,rule, match, sign)
    if ngx_match(ngx.unescape_uri(match), rule, "isjo") then
        error_rule = rule .. ' >> ' .. sign .. ':' .. match
        return true
    end
    return false
end


function _M.ngx_match_string(self, rule, content,sign)
    local t = self:is_ngx_match_orgin(rule, content, sign)
    if t then
        return true
    end
  
    return false
end

function _M.ngx_match_list(self, rules, content)
    local args_type  = type(content)
    for i,rule in ipairs(rules)
    do
        if rule[1] == 1 then
            if args_type == 'string' then
                -- self:D("string: "..tostring(rule[2])..":".. tostring(content)..":"..tostring(rule[3]))
                local t = self:is_ngx_match_orgin(rule[2], content, rule[3])
                if t then
                    return true
                end
            end

            if args_type == 'table' then
                for _,arg_v in pairs(content) do
                    -- self:D("table : "..tostring(rule[2])..":".. tostring(arg_v)..":"..tostring(rule[3]))
                    local t = self:is_ngx_match_orgin(rule[2], arg_v, rule[3])
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
    
    local penalty_points = 50
    if name == 'cc' then penalty_points = 10
    elseif name == 'user_agent' then penalty_points = 20
    elseif name == 'scan' then penalty_points = 30
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

    if config['log'] ~= true or self:is_site_config('log') ~= true then return false end
    local method = params['method']
    if error_rule then 
        rule = error_rule
        error_rule = nil
    end

    local count = ngx.shared.waf_drop_ip:get(ip)
    -- self:D("write_log; count:" ..tostring(count).. ",retry:" .. tostring(retry) )
    if (count > retry and name ~= 'cc') then
        local safe_count,_ = ngx.shared.waf_drop_sum:get(ip)
        if not safe_count then
            self:dict_set("waf_drop_sum", ip, 1, 86400)
            safe_count = 1
        else
            self:dict_incr("waf_drop_sum", ip, 1)
        end
        local lock_time = retry_time * safe_count
        if lock_time > 86400 then lock_time = 86400 end

        retry_times = retry + 1
        self:dict_set("waf_drop_ip", ip, retry_times, lock_time)

        local reason = retry_cycle .. '秒以内累计超过'..retry..'次以上非法请求,封锁'.. lock_time ..'秒'
        self:log(params, name, reason)
    elseif name ~= 'cc' then
        self:log(params, name, rule)
    end
    
    self:stats_total(name, rule)
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
    local cpu_line = fp:read()
    fp:close()

    local list = ngx_re.split(cpu_line," ")
    table.remove(list,1)
    table.remove(list,1)

    local idie = list[4]
    for i,v in pairs(list)
    do
        cpu_total = cpu_total + v
    end

    local use_percent = tonumber(100-(idie/cpu_total)*100)
    return cpu_total,idie,use_percent
end

function _M.get_cpu_percent(self)
    local cpu_total,idie,use_percent = self:get_cpu_stat()
    ngx.sleep(2)
    local cpu_total2,idie2,use_percent2 = self:get_cpu_stat()
    local cpu_usage_percent = tonumber(100-(((idie2-idie)/(cpu_total2-cpu_total))*100))
    return cpu_usage_percent
end


function _M.return_post_data(self)
    if method ~= "POST" then return false end
    content_length = tonumber(self.params["request_header"]['content-length'])
    if not content_length then return false end
    max_len = 2560 * 1024000
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
