# 模板版本号：仅用于让 index.py 判断已安装的 config_local.py 是否需要刷新，勿手工修改
PGADMIN_LOCAL_TPL_VERSION = 5

LOG_FILE = '{$DATA_PATH}/pgadmin4/pgadmin4.log'
SQLITE_PATH = '{$DATA_PATH}/pgadmin4/pgadmin4.db'
SESSION_DB_PATH = '{$DATA_PATH}/pgadmin4/sessions'
STORAGE_DIR = '{$DATA_PATH}/pgadmin4/storage'
AZURE_CREDENTIAL_CACHE_DIR = '{$DATA_PATH}/pgadmin4/azurecredentialcache'
SERVER_MODE = True

# 反向代理适配：本插件用 Nginx 反代到 unix socket，
# 必须让 pgAdmin 信任 Nginx 透传的 X-Forwarded-* 头，
# 否则生成的跳转地址与 Cookie 判定会指向后端，登录成功后被打回登录页。
PROXY_X_HOST_COUNT = 1
PROXY_X_FOR_COUNT = 1
PROXY_X_PROTO_COUNT = 1
PROXY_X_PORT_COUNT = 1

# Session Cookie：纯 HTTP（非 HTTPS）访问时 secure 必须为 False，否则 Cookie 根本不会下发
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# flask-paranoid 会把会话与客户端 IP 绑定，客户端 IP 变化（移动网络、多出口 NAT）
# 会让已登录会话被判定失效并弹回登录页，故关闭。
# 代价：Cookie 一旦被窃取可直接复用，请配合 Nginx Basic Auth 与强口令使用。
ENHANCED_COOKIE_PROTECTION = False

# MAX_LOGIN_ATTEMPTS = 0 表示关闭“失败次数超限锁定账号”。
# 保持 0 的理由：pgAdmin 口令是 10 位随机串，外层还有 Nginx Basic Auth，
# 暴力破解不可行；而锁定态的表现恰恰就是“登录后弹回登录页”，极难排查。
# 需要恢复默认防护（3 次）时，删除本行即可。
MAX_LOGIN_ATTEMPTS = 0

# 邮箱校验：pgAdmin 默认 GLOBALLY_DELIVERABLE = True，会拒绝“域名不带点”或
# “特殊用途域名”的地址（foo@pgadmin、foo@local、foo@x.test …）。
# 登录链路 InternalAuthentication.validate() 的第一句就是 validate_email()，
# 邮箱不合法会被直接打回登录页（nginx 里表现为 POST /authenticate/login -> 302 -> /login），
# 与密码对不对无关；建账号时 create_user 也会因同一道校验失败。
# 若确实要用内网域名邮箱，取消下面两行注释（会放宽校验强度）。
# GLOBALLY_DELIVERABLE = False
# ALLOW_SPECIAL_EMAIL_DOMAINS = ['local', 'localhost', 'internal', 'lan', 'home', 'test']

# Cross-Origin-Opener-Policy（COOP）：pgAdmin v9.8+ 默认 same-origin（CVE-2025-9636）。
# 本插件通过 Nginx 在 HTTP 下反代，浏览器会因 origin 不可信而忽略 COOP 头，
# 且该头可能干扰 POST → 302 → GET 的登录跳转链路（窗口上下文隔离），
# 导致 Session Cookie 丢失、登录后弹回登录页。
# 设为 unsafe-none 禁用 COOP，外层有 Nginx Basic Auth 兜底安全。
CROSS_ORIGIN_OPENER_POLICY = "unsafe-none"
