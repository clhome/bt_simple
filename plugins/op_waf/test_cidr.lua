local function ip2num(ip_arr)
    local n = ip_arr[1] * 16777216 + ip_arr[2] * 65536 + ip_arr[3] * 256 + ip_arr[4]
    return n
end

local function num2ip(n)
    local d = n % 256
    n = math.floor(n / 256)
    local c = n % 256
    n = math.floor(n / 256)
    local b = n % 256
    n = math.floor(n / 256)
    local a = n % 256
    return a .. "." .. b .. "." .. c .. "." .. d
end

local function range2cidrs(start_num, end_num)
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
        table.insert(cidrs, num2ip(start_num) .. "/" .. max_size)
        start_num = start_num + size
    end
    return cidrs
end

local arr1 = {192, 168, 1, 1}
local arr2 = {192, 168, 1, 255}
local cidrs = range2cidrs(ip2num(arr1), ip2num(arr2))
for i, v in ipairs(cidrs) do
    print(v)
end
