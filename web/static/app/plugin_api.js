/**
 * 御风面板 (bt_simple) - 插件统一 API 共用核心库
 * 封装并规范化所有插件的前端通信逻辑，提供安全的共用函数
 */

(function(window, document) {
    'use strict';

    var YfPlugin = {};

    /**
     * 将字符串参数解析为对象
     * 代替原有的 str2Obj 和 toArrayObject，消除冗余
     * @param {string|object} args 
     * @returns {string} JSON 格式字符串
     */
    YfPlugin.parseArgs = function(args) {
        if (!args) return "{}";
        if (typeof args === 'object') return JSON.stringify(args);
        if (typeof args === 'string') {
            try {
                // 尝试直接解析
                var obj = JSON.parse(args);
                return JSON.stringify(obj);
            } catch (e) {
                // 降级为查询字符串解析
                var data = {};
                var kv = args.split('&');
                for (var i = 0; i < kv.length; i++) {
                    var v = kv[i].split('=');
                    if (v.length === 2) {
                        data[decodeURIComponent(v[0])] = decodeURIComponent(v[1]);
                    }
                }
                return JSON.stringify(data);
            }
        }
        return "{}";
    };

    /**
     * 为指定插件创建一套标准的 API 请求工厂方法
     * @param {string} pluginName 插件名
     * @returns {object} API 对象
     */
    YfPlugin.createApi = function(pluginName) {
        // 使用 i18n 引擎进行 loading 翻译
        var pt = (window.YfI18n && YfI18n.createPluginTranslator) ? YfI18n.createPluginTranslator(pluginName) : function(k) { return k; };

        function _basePost(url, method, version, args, callback, silent) {
            var loadT = null;
            if (!silent) {
                var loadingText = pt('loading');
                if (loadingText === 'loading') loadingText = '正在获取...';
                loadT = layer.msg(loadingText, { icon: 16, time: 0, shade: 0.3 });
            }

            var req_data = {
                name: pluginName,
                func: method
            };
            if (version) req_data.version = version;
            if (args) req_data.args = YfPlugin.parseArgs(args);

            window.$.post(url, req_data, function(data) {
                if (!silent && loadT) layer.close(loadT);
                if (data.msg) {
                    data.msg = pt(data.msg);
                }

                if (!data.status) {
                    layer.msg(data.msg, { icon: 0, time: 2000, shade: [0.3, '#000'] });
                    return;
                }

                if (typeof callback === 'function') {
                    callback(data);
                }
            }, 'json').fail(function(xhr) {
                if (!silent && loadT) layer.close(loadT);
                layer.msg('请求失败: ' + xhr.status, { icon: 0, time: 2000, shade: [0.3, '#000'] });
            });
        }

        function _parseCallArgs(argsArray) {
            var method = argsArray[0];
            var version = null;
            var args = {};
            var callback = null;

            if (argsArray.length === 2) {
                if (typeof argsArray[1] === 'function') {
                    callback = argsArray[1];
                } else {
                    args = argsArray[1];
                }
            } else if (argsArray.length === 3) {
                if (typeof argsArray[2] === 'function') {
                    args = argsArray[1];
                    callback = argsArray[2];
                } else {
                    version = argsArray[1];
                    args = argsArray[2];
                }
            } else if (argsArray.length >= 4) {
                version = argsArray[1];
                args = argsArray[2];
                callback = argsArray[3];
            }
            return { method: method, version: version, args: args, callback: callback };
        }

        return {
            /**
             * 标准请求 (带 Loading)
             * 支持:
             * - post(method, callback)
             * - post(method, args, callback)
             * - post(method, version, args, callback)
             */
            post: function() {
                var p = _parseCallArgs(arguments);
                _basePost('/plugins/run', p.method, p.version, p.args, p.callback, false);
            },
            
            /**
             * 静默请求 (无 Loading)
             */
            postSilent: function() {
                var p = _parseCallArgs(arguments);
                _basePost('/plugins/run', p.method, p.version, p.args, p.callback, true);
            },

            /**
             * Callback 端点请求 (带 Loading)
             */
            postCallback: function() {
                var p = _parseCallArgs(arguments);
                _basePost('/plugins/callback', p.method, p.version, p.args, p.callback, false);
            },

            /**
             * Promise 版本 (async/await)
             */
            postAsync: function() {
                var p = _parseCallArgs(arguments);
                return new Promise(function(resolve, reject) {
                    _basePost('/plugins/run', p.method, p.version, p.args, function(data) {
                        resolve(data);
                    }, false);
                });
            }
        };
    };

    /**
     * 标准化的危险操作确认弹窗
     * @param {string} msg 提示消息
     * @param {function} onConfirm 确认后的回调函数
     */
    YfPlugin.confirm = function(msg, onConfirm) {
        var t = window.t || function(k) { return k; };
        var translatedMsg = t(msg) !== msg ? t(msg) : msg;
        layer.confirm(translatedMsg, {
            btn: [t('public.confirm') || '确认', t('public.cancel') || '取消'],
            icon: 0,
            title: t('public.warning') || '警告'
        }, function(index) {
            layer.close(index);
            if (typeof onConfirm === 'function') onConfirm();
        });
    };

    /**
     * 获取插件 info.json 的多语言展示信息
     * 辅助面板核心软件列表进行国际化渲染
     */
    YfPlugin.getPluginInfo = function(pluginName) {
        if (!window.YfI18n || !window.YfI18n.createPluginTranslator) return null;
        var pt = YfI18n.createPluginTranslator(pluginName);
        return {
            title: pt('plugin_title'),
            ps: pt('plugin_ps'),
            type: pt('plugin_type')
        };
    };

    window.YfPlugin = YfPlugin;

})(window, document);
