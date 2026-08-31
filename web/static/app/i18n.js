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
        'source_code': '源码'
    };

    /**
     * 翻译函数 t(key, args, defaultText)
     * 支持模块点号寻址，如 "index.memre", "public.success", "files.file_name"
     * 自动支持大小写容错（如 FILES.FILE_NAME -> files.file_name）与默认文本回退
     */
    function t(key, args, defaultText) {
        if (!key || typeof key !== 'string') return '';

        // 如果第二个参数直接传了默认文本字符串，如 t('files.new', '新建')
        if (typeof args === 'string' && defaultText === undefined) {
            defaultText = args;
            args = null;
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
            if (args && Array.isArray(args)) {
                var argMap = {};
                for (var j = 0; j < args.length; j++) {
                    argMap[j] = args[j];
                    if (argMap[j + 1] === undefined) {
                        argMap[j + 1] = args[j];
                    }
                }
                val = val.replace(/\{(\d+)\}/g, function(match, num) {
                    var arg = argMap[parseInt(num, 10)];
                    return arg !== undefined ? arg : match;
                });
            }
            return val;
        }

        // 4. 如果在 lan 中没有找到，尝试调用 lan.get
        if (window.lan && typeof window.lan.get === 'function') {
            var getVal = window.lan.get(key, args || []);
            if (getVal && getVal !== key && getVal !== normalizedKey.toLowerCase()) {
                return getVal;
            }
        }

        // 5. 优先使用传入的默认文本（defaultText）
        if (defaultText && typeof defaultText === 'string') {
            return defaultText;
        }

        // 6. 兜底字典匹配
        var cleanKey = parts[parts.length - 1].toLowerCase();
        // 去除尾部无意义的序号后缀，如 file_name_2 -> file_name
        cleanKey = cleanKey.replace(/_\d+$/, '');
        if (FALLBACK_MAP[cleanKey]) {
            return FALLBACK_MAP[cleanKey];
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

    /**
     * 创建插件专属的 i18n 翻译函数
     * @param {string} pluginName 插件名
     * @returns {function} pt(key, ...args) 函数
     */
    function createPluginTranslator(pluginName) {
        if (!_pluginDicts[pluginName]) {
            var lang = _currentLang || 'zh-CN';
            // 同步请求当前语言包
            window.$.ajax({
                url: '/plugins/file?name=' + pluginName + '&f=lang/' + lang + '.json',
                dataType: 'json',
                async: false,
                success: function(data) {
                    _pluginDicts[pluginName] = data || {};
                },
                error: function() {
                    // 失败则回退到中文
                    if (lang !== 'zh-CN') {
                        window.$.ajax({
                            url: '/plugins/file?name=' + pluginName + '&f=lang/zh-CN.json',
                            dataType: 'json',
                            async: false,
                            success: function(data) {
                                _pluginDicts[pluginName] = data || {};
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
        }

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
        createPluginTranslator: createPluginTranslator,
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
