LOG_FILE = '{$DATA_PATH}/pgadmin4/pgadmin4.log'
SQLITE_PATH = '{$DATA_PATH}/pgadmin4/pgadmin4.db'
SESSION_DB_PATH = '{$DATA_PATH}/pgadmin4/sessions'
STORAGE_DIR = '{$DATA_PATH}/pgadmin4/storage'
AZURE_CREDENTIAL_CACHE_DIR = '{$DATA_PATH}/pgadmin4/azurecredentialcache'
SERVER_MODE = True

# 跨域策略：设置为 unsafe-none，彻底消除在非 HTTPS / 局域网 / 公网 IP 下浏览器 Untrustworthy Origin 报警与阻断
CROSS_ORIGIN_OPENER_POLICY = 'unsafe-none'

# 反向代理适配：信任来自 Nginx 反向代理透传的真实 Header
PROXY_X_HOST_COUNT = 1
PROXY_X_FOR_COUNT = 1
PROXY_X_PROTO_COUNT = 1
PROXY_X_PORT_COUNT = 1

# 禁用客户端 IP 增强 Cookie 绑定，防止反代及动态 IP 下 Session 校验失败导致登录死循环
ENHANCED_COOKIE_PROTECTION = False

# Session Cookie 配置：确保在纯 HTTP 访问环境下正常持久化
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# 禁用登录失败次数超限锁死账户功能（设为 0），杜绝因重试或网络抖动将账户隐式锁定陷入循环重定向
MAX_LOGIN_ATTEMPTS = 0

# CSRF 保护降级：在 Nginx Basic Auth 已提供第一层认证的前提下，
# 禁用 Flask-WTF CSRF 检查，彻底消除反代环境下 token 不匹配导致的登录失败
WTF_CSRF_ENABLED = False
WTF_CSRF_CHECK_DEFAULT = False