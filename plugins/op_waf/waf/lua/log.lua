local json = require "cjson"
local __WAF = require "waf_common"
local C = __WAF:getInstance()

local config = require "waf_config"
local site_config = require "waf_site"
local config_domains = require "waf_domains"

C:setConfData(config, site_config)
local server_name = C:get_sn(config_domains)

local status = ngx.status
if status == 404 then
    local ip = C:get_real_ip(server_name)
    local count_key = ip .. "_404_count"
    local count, err = ngx.shared.waf_limit:get(count_key)
    
    if count then
        if count >= 10 then
            -- 封禁IP 30分钟 (1800s)
            C:dict_set("waf_drop_ip", ip, 1, 1800)
            local reason = '1分钟内产生超过10次404错误,封锁1800秒'
            
            -- Write log only once when threshold is hit
            if count == 10 then
                local params = {
                    server_name = server_name,
                    ip = ip,
                    request_header = ngx.req.get_headers(),
                    uri = tostring(ngx.unescape_uri(ngx.var.uri)),
                    method = ngx.req.get_method(),
                    request_uri = tostring(ngx.var.request_uri),
                    status_code = status,
                    user_agent = ngx.var.http_user_agent,
                    time = ngx.time()
                }
                C:log(params, 'scan', reason)
            end
        end
        C:dict_incr("waf_limit", count_key, 1)
    else
        C:dict_set("waf_limit", count_key, 1, 60)
    end
end
