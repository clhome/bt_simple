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
    local uri = tostring(ngx.unescape_uri(ngx.var.uri))
    local ext = string.match(uri, "%.([^%.]+)$")
    if ext then
        ext = string.lower(ext)
    end
    local skip = false
    if ext then
        local static_exts = {
            jpg = true, jpeg = true, png = true, gif = true, webp = true,
            ico = true, woff = true, woff2 = true, ttf = true, svg = true,
            css = true, js = true, map = true
        }
        if static_exts[ext] then
            skip = true
        end
    end

    if not skip then
        local ip = C:get_real_ip(server_name)
        local uri_hash = ngx.md5(uri)
        local uri_key = "404:uri:" .. ip .. ":" .. uri_hash
        local is_seen = ngx.shared.waf_limit:get(uri_key)
        
        if not is_seen then
            ngx.shared.waf_limit:set(uri_key, 1, 300)
            
            local count_1m_key = "404:count:1m:" .. ip
            local count_5m_key = "404:count:5m:" .. ip
            
            local count_1m = ngx.shared.waf_limit:get(count_1m_key)
            if count_1m then
                ngx.shared.waf_limit:incr(count_1m_key, 1)
                count_1m = count_1m + 1
            else
                ngx.shared.waf_limit:set(count_1m_key, 1, 60)
                count_1m = 1
            end
            
            local count_5m = ngx.shared.waf_limit:get(count_5m_key)
            if count_5m then
                ngx.shared.waf_limit:incr(count_5m_key, 1)
                count_5m = count_5m + 1
            else
                ngx.shared.waf_limit:set(count_5m_key, 1, 300)
                count_5m = 1
            end
            
            if count_5m >= 150 then
                C:dict_set("waf_drop_ip", ip, 1, 5400)
                if count_5m == 150 then
                    local reason = '5分钟内产生超过150次独立404错误,封锁5400秒'
                    local params = {
                        server_name = server_name,
                        ip = ip,
                        request_header = ngx.req.get_headers(),
                        uri = uri,
                        method = ngx.req.get_method(),
                        request_uri = tostring(ngx.var.request_uri),
                        status_code = status,
                        user_agent = ngx.var.http_user_agent,
                        time = ngx.time()
                    }
                    C:log(params, 'scan', reason)
                    C:stats_total('scan', reason)
                end
            elseif count_1m >= 30 then
                local warn_key = "404_warning:" .. ip
                if not ngx.shared.waf_limit:get(warn_key) then
                    ngx.shared.waf_limit:set(warn_key, 1, 300)
                    local reason = '1分钟内产生超过30次独立404错误,触发警告页面'
                    local params = {
                        server_name = server_name,
                        ip = ip,
                        request_header = ngx.req.get_headers(),
                        uri = uri,
                        method = ngx.req.get_method(),
                        request_uri = tostring(ngx.var.request_uri),
                        status_code = status,
                        user_agent = ngx.var.http_user_agent,
                        time = ngx.time()
                    }
                    C:log(params, 'scan', reason)
                    C:stats_total('scan', reason)
                end
            end
        end
    end
end
