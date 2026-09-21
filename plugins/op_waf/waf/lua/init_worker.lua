local waf_root = "{$WAF_ROOT}"

-- local waf_cpath = waf_root.."/waf/lua/?.lua;"..waf_root.."/waf/conf/?.lua;"..waf_root.."/waf/html/?.lua;"
-- local waf_sopath = waf_root.."/waf/conf/?.so;"
-- if not package.path:find(waf_cpath) then
--     package.path = waf_cpath  .. package.path
-- end

-- if not package.cpath:find(waf_sopath) then
--     package.cpath = waf_sopath .. package.cpath
-- end

local json = require "cjson"

local __WAF_C = require "waf_common"
local WAF_C = __WAF_C:getInstance()

local waf_config = require "waf_config"
local waf_site_config = require "waf_site"
WAF_C:setConfData(waf_config, waf_site_config)
WAF_C:setDebug(false)

-- C:D("init worker"..tostring(ngx.worker.id()))

local function waf_timer_stats_total_log(premature)
    local ok, err = pcall(function()
        WAF_C:timer_stats_total()
    end)
    if not ok then ngx.log(ngx.ERR, "waf_timer_stats_total_log err: ", err) end
end

local function waf_clean_expire_data(premature)
    local ok, err = pcall(function()
        WAF_C:clean_log()
    end)
    if not ok then ngx.log(ngx.ERR, "waf_clean_expire_data err: ", err) end
end

-- 御风F2B防火墙情报联动：批量把封禁情报落盘。
-- 放在 timer（light thread）里执行，因此允许阻塞式文件 IO，
-- 而请求路径只做一次 rpush —— 这是「实时防火墙不因联动而变慢」的关键。
-- 独立 timer、独立队列，与日志/统计任务互不干扰、互不拖累。
local function waf_flush_ban_sync(premature)
    local ok, err = pcall(function()
        WAF_C:flush_ban_sync()
    end)
    if not ok then ngx.log(ngx.ERR, "waf_flush_ban_sync err: ", err) end
end

WAF_C:dict_set("waf_limit", "cpu_usage", 0, 10)
function waf_timer_every_get_cpu(premature)
    local ok, err = pcall(function()
        if WAF_C:file_exists('/proc/stat') then
            local lua_cpu_percent = WAF_C:get_cpu_percent()
            -- WAF_C:D("lua_cpu_percent:"..tostring(lua_cpu_percent))
            WAF_C:dict_set("waf_limit", "cpu_usage", math.floor(lua_cpu_percent), 10)
        else
            local cpu_percent = WAF_C:read_file_body(waf_root.."/cpu.info")
            -- WAF_C:D("cpu_usage:"..tostring(cpu_percent ))
            if cpu_percent then
                WAF_C:dict_set("waf_limit", "cpu_usage", tonumber(cpu_percent), 10)
            else
                WAF_C:dict_set("waf_limit", "cpu_usage", 0, 10)
            end
        end
    end)
    if not ok then ngx.log(ngx.ERR, "waf_timer_every_get_cpu err: ", err) end
end

if ngx.worker.id() == 0 then

    ngx.timer.every(15, waf_timer_every_get_cpu)
    -- 异步执行
    ngx.timer.every(30, waf_timer_stats_total_log)
    ngx.timer.every(3600, waf_clean_expire_data)
    -- 启动时延迟 5 秒执行一次初始过期数据清理
    ngx.timer.at(5, waf_clean_expire_data)
    -- 御风F2B防火墙情报联动落盘：2 秒一次；队列为空时开销仅一次 llen（共享内存原子读）
    ngx.timer.every(2, waf_flush_ban_sync)

    WAF_C:cron()
end