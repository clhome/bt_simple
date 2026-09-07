/**
 * 御风面板 (bt_simple) 前端 i18n 国际化核心引擎
 * 支持 6 种语言：zh-CN, zh-TW, en, fr, de, it
 * 包含浏览器语言自动匹配、Cookie/localStorage 智能持久化与旧版 lan 兼容
 */

(function(window, document) {
    'use strict';

    var SUPPORTED_LANGUAGES = [
        { code: 'zh-CN', name: '简体中文', nativeName: '简体中文' },
        { code: 'zh-TW', name: '繁体中文', nativeName: '繁體中文' },
        { code: 'en',    name: 'English',  nativeName: 'English' },
        { code: 'fr',    name: 'Français', nativeName: 'Français' },
        { code: 'de',    name: 'Deutsch',  nativeName: 'Deutsch' },
        { code: 'it',    name: 'Italiano', nativeName: 'Italiano' }
    ];

    var SUPPORTED_CODES = SUPPORTED_LANGUAGES.map(function(l) { return l.code; });
    var DEFAULT_LANG = 'zh-CN';

    // 语言代码智能映射规则
    var LANG_MAP = {
        'zh': 'zh-CN',
        'zh-cn': 'zh-CN',
        'zh-sg': 'zh-CN',
        'zh-hans': 'zh-CN',
        'zh-tw': 'zh-TW',
        'zh-hk': 'zh-TW',
        'zh-mo': 'zh-TW',
        'zh-hant': 'zh-TW',
        'en': 'en',
        'en-us': 'en',
        'en-gb': 'en',
        'en-ca': 'en',
        'en-au': 'en',
        'fr': 'fr',
        'fr-fr': 'fr',
        'fr-ca': 'fr',
        'fr-be': 'fr',
        'fr-ch': 'fr',
        'de': 'de',
        'de-de': 'de',
        'de-at': 'de',
        'de-ch': 'de',
        'it': 'it',
        'it-it': 'it',
        'it-ch': 'it'
    };

    /**
     * 读取指定 Cookie
     */
    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
        return match ? decodeURIComponent(match[3]) : null;
    }

    /**
     * 写入 Cookie
     */
    function setCookie(name, value, days) {
        days = days || 365;
        var expires = new Date(Date.now() + days * 864e5).toUTCString();
        document.cookie = name + '=' + encodeURIComponent(value) + '; expires=' + expires + '; path=/; SameSite=Lax';
    }

    /**
     * 归一化语言代码
     */
    function normalizeLang(lang) {
        if (!lang || typeof lang !== 'string') return null;
        var clean = lang.trim().toLowerCase();
        if (LANG_MAP[clean]) return LANG_MAP[clean];
        var prefix = clean.split('-')[0].split('_')[0];
        if (LANG_MAP[prefix]) return LANG_MAP[prefix];
        return null;
    }

    /**
     * 自动检测客户端语言偏好
     * 优先级：URL参数 > Cookie > localStorage > 服务器注入语言 > 浏览器语言 > 默认zh-CN
     */
    function detectLanguage() {
        // 1. URL 参数
        try {
            var urlParams = new URLSearchParams(window.location.search);
            var urlLang = normalizeLang(urlParams.get('lang'));
            if (urlLang && SUPPORTED_CODES.indexOf(urlLang) !== -1) {
                return urlLang;
            }
        } catch (e) {}

        // 2. Cookie (yf_lang)
        var cookieLang = normalizeLang(getCookie('yf_lang'));
        if (cookieLang && SUPPORTED_CODES.indexOf(cookieLang) !== -1) {
            return cookieLang;
        }

        // 3. localStorage (yf_lang)
        try {
            var storedLang = normalizeLang(localStorage.getItem('yf_lang'));
            if (storedLang && SUPPORTED_CODES.indexOf(storedLang) !== -1) {
                return storedLang;
            }
        } catch (e) {}

        // 4. 服务器模板注入语言
        if (window._SERVER_LANG) {
            var serverLang = normalizeLang(window._SERVER_LANG);
            if (serverLang && SUPPORTED_CODES.indexOf(serverLang) !== -1) {
                return serverLang;
            }
        }

        // 5. 浏览器本地语言列表
        var browserLangs = navigator.languages || [navigator.language || navigator.userLanguage || ''];
        for (var i = 0; i < browserLangs.length; i++) {
            var detected = normalizeLang(browserLangs[i]);
            if (detected && SUPPORTED_CODES.indexOf(detected) !== -1) {
                return detected;
            }
        }

        // 6. 默认语言
        return DEFAULT_LANG;
    }

    var _currentLang = detectLanguage();
    // 首次自动将检测结果同步至 Cookie 与 localStorage，确保前后端一致
    setCookie('yf_lang', _currentLang);
    try {
        localStorage.setItem('yf_lang', _currentLang);
    } catch (e) {}

    // 常用键名内置兜底中文字典，确保即使未加载语言包也不会在界面泄露 files. / FILES. 前缀或覆盖品牌名称
    var FALLBACK_MAP = {
        'file_name': '文件名',
        'size': '大小',
        'last_modified': '修改时间',
        'permissions': '权限',
        'owner': '所有者',
        'operations': '操作',
        'calculate': '计算',
        'copy_path': '复制路径',
        'copy': '复制',
        'cut': '剪切',
        'rename': '重命名',
        'compress': '压缩',
        'unzip': '解压',
        'edit': '编辑',
        'preview': '预览',
        'download': '下载',
        'delete': '删除',
        'new': '新建',
        'create_new_folder': '新建目录',
        'create_new_blank_file': '新建空白文件',
        'back_parent': '返回上一级',
        'per_page': '每页',
        'item': '条',
        'get': '获取',
        'recycle_bin': '文件回收站',
        'upload': '上传',
        'remote_download': '远程下载',
        'brand_panel': '御风面板',
        'brand_title': '御风面板',
        'brand_company': '御风科技',
        'ip_privacy_check': 'IP隐私安全检测',
        'tools_box': '御风工具箱',
        'company_signature': '衢州御风科技有限公司出品',
        'source_code': '源码',
        'message_box': '消息盒子',
        'task_list': '任务列表',
        'message_list': '消息列表',
        'execution_log': '执行日志',
        'execution_log_1': '执行日志',
        'memory': '内存:',
        'memory_1': '内存:',
        'uplink': '上行:',
        'downstream': '下行:',
        'task_name': '任务名称',
        'task_time': '添加时间',
        'task_tip_read': '标记已读',
        'task_tip_all': '全部已读',
        'if_task_has_not': '若任务长时间未执行，请尝试在首页点【重启面板】来重置任务队列',
        'there_are_currently_no': '当前没有任务!',
        'retrieving_logs': '正在获取日志...',
        'completed': '已完成',
        'done': '已完成',
        'time_taken': '耗时[',
        'processing_1': '处理中',
        'waiting_1': '等待中',
        'installing_1': '安装中',
        'installing_2': '正在安装',
        'scanning': '正在扫描',
        'downloading': '下载中',
        'del': '删除',
        'close': '关闭',
        'confirm': '确定',
        'cancel': '取消',
        'info': '信息',
        'do_you_want_to': '是否要退出御风面板?',
        'scan': '扫描',
        'pre': '百分比(%)',
        'loading': '正在获取...',
        'loading_1': '正在获取服务状态...'
    };

    // 确保 window.lan 及各常用命名空间安全存在，避免历史调用短路
    window.lan = window.lan || {};
    window.lan.public = window.lan.public || {};
    window.lan.files = window.lan.files || {};

    // 增强 window.lan.get：当内置 msgs 缺失时自动回退至 t() 函数解析
    var origLanGet = window.lan.get;
    window.lan.get = function(key, args) {
        var res = '';
        if (typeof origLanGet === 'function') {
            try {
                res = origLanGet(key, args || []);
            } catch (e) {}
        }
        if (res && typeof res === 'string' && res.trim() !== '') {
            return res;
        }
        if (window._inLanGet) {
            return res || '';
        }
        window._inLanGet = true;
        try {
            var argList = Array.isArray(args) ? args : (args !== undefined ? [args] : []);
            var fallback = t('files.' + key, argList) || t('public.' + key, argList);
            if (fallback && fallback !== key && fallback !== ('files.' + key) && fallback !== ('public.' + key)) {
                return fallback;
            }
        } finally {
            window._inLanGet = false;
        }
        return res || '';
    };

    /**
     * 翻译函数 t(key, args, defaultText)
     * 支持模块点号寻址，如 "index.memre", "public.success", "files.file_name"
     * 自动支持大小写容错（如 FILES.FILE_NAME -> files.file_name）与默认文本回退
     */
    function t(key, args, defaultText) {
        if (!key || typeof key !== 'string') return '';

        // 参数归一化：支持 t(key, defaultText)、t(key, argsArray, defaultText) 以及变长参数 t(key, arg1, arg2, arg3...)
        var argList = null;
        if (Array.isArray(args)) {
            argList = args;
        } else if (arguments.length > 2 && typeof args !== 'string') {
            // 变长参数调用，如 t(key, 38, 3, 46)
            argList = Array.prototype.slice.call(arguments, 1);
            defaultText = undefined;
        } else if (typeof args === 'string' && defaultText === undefined) {
            defaultText = args;
            args = null;
        } else if (args !== undefined && args !== null) {
            argList = [args];
        }

        var normalizedKey = key.trim();
        var parts = normalizedKey.split('.');
        var val = window.lan;

        // 1. 尝试原始路径寻址
        for (var i = 0; i < parts.length; i++) {
            if (val && typeof val === 'object' && parts[i] in val) {
                val = val[parts[i]];
            } else {
                val = null;
                break;
            }
        }

        // 2. 若未找到，尝试全小写路径寻址（如 FILES.FILE_NAME -> lan.files.file_name）
        if (val === null || val === undefined) {
            var lowerParts = normalizedKey.toLowerCase().split('.');
            var lowerVal = window.lan;
            for (var k = 0; k < lowerParts.length; k++) {
                if (lowerVal && typeof lowerVal === 'object' && lowerParts[k] in lowerVal) {
                    lowerVal = lowerVal[lowerParts[k]];
                } else {
                    lowerVal = null;
                    break;
                }
            }
            if (lowerVal !== null && lowerVal !== undefined) {
                val = lowerVal;
            }
        }

        // 3. 处理字符串模板与插值参数
        if (typeof val === 'string') {
            if (argList && argList.length > 0) {
                var hasZero = val.indexOf('{0}') > -1;
                val = val.replace(/\{(\d+)\}/g, function(match, num) {
                    var n = parseInt(num, 10);
                    if (hasZero) {
                        return (n >= 0 && n < argList.length) ? argList[n] : match;
                    } else {
                        if (n >= 1 && n <= argList.length) return argList[n - 1];
                        if (n >= 0 && n < argList.length) return argList[n];
                    }
                    return match;
                });
            }
            return val;
        }

        // 4. 如果在 lan 中没有找到，且为单个简单 key，尝试调用 lan.get
        if (parts.length === 1 && !window._inLanGet && window.lan && typeof window.lan.get === 'function') {
            var getVal = window.lan.get(key, args || []);
            if (getVal && getVal !== key && getVal !== normalizedKey.toLowerCase()) {
                return getVal;
            }
        }

        // 5. 优先使用传入的默认文本（defaultText）
        if (defaultText && typeof defaultText === 'string') {
            return defaultText;
        }

        // 6. 兜底字典匹配（仅当为中文或繁体中文，或无其他回退时使用）
        var rawKey = parts[parts.length - 1].toLowerCase();
        var cleanKey = rawKey.replace(/_\d+$/, '');
        if (_currentLang === 'zh-CN') {
            if (FALLBACK_MAP[rawKey]) return FALLBACK_MAP[rawKey];
            if (FALLBACK_MAP[cleanKey]) return FALLBACK_MAP[cleanKey];
        }

        // 7. 若仍未匹配，绝不泄露带点号的前缀 key（如 public.xxx, bt.xxx），返回空字符串以支持 || 运算短路
        if (parts.length > 1) {
            return '';
        }

        return key;
    }


    /**
     * 切换语言
     */
    function setLanguage(lang, reload) {
        if (reload === undefined) reload = true;
        var normalized = normalizeLang(lang) || DEFAULT_LANG;
        _currentLang = normalized;

        setCookie('yf_lang', normalized, 365);
        try {
            localStorage.setItem('yf_lang', normalized);
        } catch (e) {}

        // 同步给后端设置接口
        if (window.$ && typeof window.$.post === 'function') {
            window.$.post('/setting/set_language', { lang: normalized });
        }

        if (reload) {
            window.location.reload();
        } else {
            translateDOM();
            if (window.$) {
                window.$(document).trigger('yf:langChanged', [normalized]);
            }
        }
    }

    /**
     * 自动翻译 DOM 元素中的 [data-i18n]
     */
    function translateDOM(root) {
        root = root || document;
        var elements = root.querySelectorAll('[data-i18n]');
        for (var i = 0; i < elements.length; i++) {
            var el = elements[i];
            if (el.getAttribute('data-i18n-lang') === _currentLang) {
                continue; // 避免对已用当前语言翻译过的节点进行重复翻译
            }
            var key = el.getAttribute('data-i18n');
            var attr = el.getAttribute('data-i18n-attr');
            var translated = t(key);
            if (translated && translated !== key) {
                if (attr) {
                    el.setAttribute(attr, translated);
                } else if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
                    el.value = translated;
                } else {
                    el.textContent = translated;
                }
                el.setAttribute('data-i18n-lang', _currentLang);
            }
        }
    }

    var _pluginDicts = {};
    var PLUGIN_CACHE_PREFIX = 'yf_plang_';

    /**
     * 从 localStorage 读取插件语言包缓存
     */
    function getPluginDictFromStorage(pluginName, lang) {
        try {
            var cached = localStorage.getItem(PLUGIN_CACHE_PREFIX + pluginName + '_' + lang);
            if (cached) {
                return JSON.parse(cached);
            }
        } catch (e) {}
        return null;
    }

    /**
     * 将插件语言包写入 localStorage 缓存
     */
    function setPluginDictToStorage(pluginName, lang, dict) {
        try {
            localStorage.setItem(PLUGIN_CACHE_PREFIX + pluginName + '_' + lang, JSON.stringify(dict));
        } catch (e) {}
    }

    /**
     * 自动翻译插件弹窗 DOM 结构（左侧侧边栏菜单、底部版权署名等）
     * 采用精确定向选择器，消除全量 DOM 暴力扫描与强制重排
     * @param {HTMLElement|jQuery} container 弹窗容器或 DOM 根节点
     * @param {string} pluginName 插件名
     */
    function translatePluginDOM(container, pluginName) {
        if (!container || !window.$) return;
        var $con = window.$(container);

        // 安全防护：绝不对全局 body 或 html 执行模糊扫描
        var isGlobalBody = false;
        if ($con[0] && ($con[0].tagName === 'BODY' || $con[0].tagName === 'HTML')) {
            isGlobalBody = true;
        } else if (typeof $con.is === 'function' && ($con.is('body') || $con.is('html'))) {
            isGlobalBody = true;
        }
        if (isGlobalBody) {
            $con = $con.find('.layui-layer:visible, .bt-w-main:visible');
            if ($con.length === 0) return;
        }

        var pt = createPluginTranslator(pluginName);

        // 1. 精准定向翻译左侧菜单项 .bt-w-menu p
        $con.find('.bt-w-menu p').each(function() {
            var $p = window.$(this);
            var orig = $p.attr('data-i18n-orig');
            if (!orig) {
                orig = $p.text().trim();
                if (orig) {
                    $p.attr('data-i18n-orig', orig);
                }
            }
            if (orig) {
                var trans = pt(orig);
                if (trans && trans !== orig) {
                    $p.text(trans);
                }
            }
        });

        // 2. 精确定位底部出品署名与品牌版权（仅在底部固定容器或直接子块中排查，不递归全树）
        var $footers = $con.find('.plugin-copyright, div[style*="pointer-events"], .bt-form > div:last-child, .bt-w-con > div:last-child');
        if ($footers.length === 0) {
            $footers = $con.children('div').add($con.find('.bt-w-con').children('div'));
        }
        $footers.each(function() {
            var $el = window.$(this);
            var txt = $el.text().trim();
            if (txt.indexOf('衢州御风科技有限公司 出品') !== -1 || txt.indexOf('衢州御風科技有限公司 出品') !== -1) {
                var orig = $el.attr('data-i18n-orig') || '衢州御风科技有限公司 出品';
                $el.attr('data-i18n-orig', orig);
                var trans = pt(orig);
                if (trans && trans !== orig) {
                    $el.text(trans);
                }
            }
        });

        // 3. 通用 DOM [data-i18n] 翻译
        if ($con[0]) {
            translateDOM($con[0]);
        }
    }

    /**
     * 异步预加载插件语言包
     * @param {string} pluginName 插件名
     * @param {function} callback 完成后的回调
     */
    function loadPluginLangAsync(pluginName, callback) {
        var lang = _currentLang || 'zh-CN';
        if (_pluginDicts[pluginName]) {
            if (typeof callback === 'function') callback(_pluginDicts[pluginName]);
            return;
        }

        var localCached = getPluginDictFromStorage(pluginName, lang);
        if (localCached) {
            _pluginDicts[pluginName] = localCached;
            if (typeof callback === 'function') callback(localCached);
            return;
        }

        if (window.$) {
            window.$.ajax({
                url: '/plugins/file?name=' + pluginName + '&f=lang/' + lang + '.json',
                dataType: 'json',
                async: true,
                success: function(data) {
                    var dict = data || {};
                    _pluginDicts[pluginName] = dict;
                    setPluginDictToStorage(pluginName, lang, dict);
                    if (typeof callback === 'function') callback(dict);
                },
                error: function() {
                    if (lang !== 'zh-CN') {
                        window.$.ajax({
                            url: '/plugins/file?name=' + pluginName + '&f=lang/zh-CN.json',
                            dataType: 'json',
                            async: true,
                            success: function(data) {
                                var dict = data || {};
                                _pluginDicts[pluginName] = dict;
                                setPluginDictToStorage(pluginName, lang, dict);
                                if (typeof callback === 'function') callback(dict);
                            },
                            error: function() {
                                _pluginDicts[pluginName] = {};
                                if (typeof callback === 'function') callback({});
                            }
                        });
                    } else {
                        _pluginDicts[pluginName] = {};
                        if (typeof callback === 'function') callback({});
                    }
                }
            });
        }
    }

    /**
     * 创建插件专属的 i18n 翻译函数
     * 支持二级缓存（Memory + localStorage），命中缓存 0ms 直出
     * @param {string} pluginName 插件名
     * @returns {function} pt(key, ...args) 函数
     */
    function createPluginTranslator(pluginName) {
        var lang = _currentLang || 'zh-CN';

        if (!_pluginDicts[pluginName]) {
            // 1. 优先尝试从 localStorage 读取（0ms）
            var localCached = getPluginDictFromStorage(pluginName, lang);
            if (localCached) {
                _pluginDicts[pluginName] = localCached;
            } else if (window.$) {
                // 2. 首次未命中缓存时同步保底拉取，并立即持久化至 localStorage
                window.$.ajax({
                    url: '/plugins/file?name=' + pluginName + '&f=lang/' + lang + '.json',
                    dataType: 'json',
                    async: false,
                    success: function(data) {
                        var dict = data || {};
                        _pluginDicts[pluginName] = dict;
                        setPluginDictToStorage(pluginName, lang, dict);
                    },
                    error: function() {
                        if (lang !== 'zh-CN') {
                            window.$.ajax({
                                url: '/plugins/file?name=' + pluginName + '&f=lang/zh-CN.json',
                                dataType: 'json',
                                async: false,
                                success: function(data) {
                                    var dict = data || {};
                                    _pluginDicts[pluginName] = dict;
                                    setPluginDictToStorage(pluginName, lang, dict);
                                },
                                error: function() {
                                    _pluginDicts[pluginName] = {};
                                }
                            });
                        } else {
                            _pluginDicts[pluginName] = {};
                        }
                    }
                });
            } else {
                _pluginDicts[pluginName] = {};
            }
        }

        // 返回高性能翻译闭包
        return function(key) {
            var dict = _pluginDicts[pluginName];
            var msg = (dict && dict[key]) ? dict[key] : key;
            if (arguments.length > 1) {
                for (var i = 1; i < arguments.length; i++) {
                    msg = msg.replace('{' + i + '}', arguments[i]);
                }
            }
            return msg;
        };
    }

    // 暴露全局 API
    var YfI18n = {
        detect: detectLanguage,
        getCurrentLang: function() { return _currentLang; },
        getSupportedLanguages: function() { return SUPPORTED_LANGUAGES.slice(); },
        getSupportedCodes: function() { return SUPPORTED_CODES.slice(); },
        setLanguage: setLanguage,
        translateDOM: translateDOM,
        translatePluginDOM: translatePluginDOM,
        createPluginTranslator: createPluginTranslator,
        loadPluginLangAsync: loadPluginLangAsync,
        t: t
    };

    window.YfI18n = YfI18n;
    window.t = t;

    // DOM 加载就绪后自动执行一次扫描翻译
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            translateDOM();
        });
    } else {
        translateDOM();
    }

})(window, document);
