/**
 * 御风面板 —— 面板 SSL 访问地址展示（本地自签 / 自贴证书 / ACME 共用）
 *
 * 后端 /setting/set_panel_local_ssl、/setting/save_panel_ssl、
 * /setting/apply_panel_acme_ssl 统一返回：
 *
 *     { url: '首选地址', urls: [ {type:'domain|lan|wan|local', host:'...', url:'https://...'} ] }
 *
 * 显示「内网 / 外网 / 绑定域名」多条地址，每一行点击都能复制对应地址
 * （只给一个地址时，另一侧网络环境的用户会打不开面板 —— 这是实战踩过的坑）。
 * 同时兼容旧版纯字符串返回值，避免升级期间前后端版本不一致时白屏。
 *
 * 依赖：jQuery、layer、window.t()（i18n）。全部缺失时降级为纯 DOM + 无提示。
 */
(function (window, document) {
    'use strict';

    // 地址类型 -> [i18n 键, 中文兜底]
    var TYPE_LABEL = {
        domain: ['config.ssl_access_domain', '绑定域名'],
        lan: ['config.ssl_access_lan', '内网地址'],
        wan: ['config.ssl_access_wan', '外网地址'],
        local: ['config.ssl_access_local', '本机地址']
    };

    function t(key, def) {
        try {
            if (typeof window.t === 'function') {
                var v = window.t(key, def);
                if (v) {
                    return v;
                }
            }
        } catch (e) {
            // i18n 引擎尚未加载：回退到中文兜底文案，不能因此阻断弹窗渲染
            return def;
        }
        return def;
    }

    function esc(str) {
        return String(str === undefined || str === null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // 回环地址复制出去在别的机器上打不开：替换成当前访问用的主机名（沿用旧弹窗行为）
    function fixLoopback(url) {
        if (!url || typeof url !== 'string') {
            return url || '';
        }
        if (url.indexOf('127.0.0.1') === -1 && url.indexOf('0.0.0.0') === -1) {
            return url;
        }
        var host = (window.location && window.location.hostname) || '';
        if (!host || host === '127.0.0.1' || host === '0.0.0.0') {
            return url;
        }
        return url.replace(/127\.0\.0\.1|0\.0\.0\.0/, host);
    }

    /**
     * 归一化后端返回值（新格式对象 / 旧格式字符串都能吃）。
     * @returns {{url: string, urls: Array<{type:string, host:string, url:string}>}}
     */
    function normalize(data) {
        var url = '';
        var raw = [];
        if (typeof data === 'string') {
            url = data;
        } else if (data && typeof data === 'object') {
            url = data.url || '';
            if (Object.prototype.toString.call(data.urls) === '[object Array]') {
                raw = data.urls;
            }
        }

        var out = [];
        var seen = {};
        for (var i = 0; i < raw.length; i++) {
            var item = raw[i] || {};
            if (!item.url || seen[item.url]) {
                continue;
            }
            seen[item.url] = true;
            out.push({
                type: TYPE_LABEL[item.type] ? item.type : 'local',
                host: item.host || '',
                url: fixLoopback(String(item.url))
            });
        }
        url = fixLoopback(url);
        if (!out.length && url) {
            out.push({ type: 'local', host: '', url: url });
        }
        if (!url && out.length) {
            url = out[0].url;
        }
        return { url: url, urls: out };
    }

    function typeLabel(type) {
        var pair = TYPE_LABEL[type] || TYPE_LABEL.local;
        return t(pair[0], pair[1]);
    }

    /**
     * 地址列表 HTML：每行 = 类型徽标 + 可点击复制的地址 + “复制”提示。
     */
    function urlsHtml(data) {
        var state = normalize(data);
        var copyTip = t('config.copy_the_address', '复制地址');
        var html = '';
        if (!state.urls.length) {
            return html;
        }
        html += '<div class="yf-ssl-url-list">';
        for (var i = 0; i < state.urls.length; i++) {
            var it = state.urls[i];
            html += '<div class="yf-ssl-url-row" data-url="' + esc(it.url) + '" title="' + esc(copyTip) + '"' +
                ' style="display:flex;align-items:center;gap:8px;background:#f8f9fa;' +
                'border:1px dashed #20a53a;border-radius:6px;padding:8px 10px;margin-bottom:8px;' +
                'cursor:pointer;word-break:break-all;transition:background .2s;">' +
                '<span style="flex:0 0 auto;background:#20a53a;color:#fff;font-size:12px;' +
                'line-height:18px;padding:0 8px;border-radius:9px;">' + esc(typeLabel(it.type)) + '</span>' +
                '<span style="flex:1 1 auto;color:#20a53a;font-weight:bold;font-size:13px;">' +
                esc(it.url) + '</span>' +
                '<span style="flex:0 0 auto;color:#8c8c8c;font-size:12px;">' + esc(copyTip) + '</span>' +
                '</div>';
        }
        html += '</div>';
        return html;
    }

    /**
     * 「首次访问自签证书」操作步骤 HTML（内网/外网两条地址都适用的同一套步骤）。
     */
    function stepsHtml() {
        var lines = [
            t('config.ssl_step_open_any', '1. 点击上方任一地址访问（内网用内网地址，外网用外网地址）'),
            t('config.ssl_step_cert_warning', '2. 浏览器提示「您的连接不是私密连接」属于自签证书的正常现象'),
            t('config.ssl_step_click_advanced', '3. 点击【高级】'),
            t('config.ssl_step_click_continue', '4. 点击【继续前往 xx.xx.xx.xx（不安全）】')
        ];
        var html = '<div class="yf-ssl-steps" style="background:#fffbe6;border:1px solid #ffe58f;' +
            'border-radius:6px;padding:10px 12px;text-align:left;font-size:12px;color:#8c6b00;' +
            'line-height:18px;margin-bottom:16px;">' +
            '<div style="font-weight:700;margin-bottom:4px;color:#ad6800;">' +
            esc(t('config.ssl_first_visit_title', '首次访问自签证书地址（必看）')) + '</div>';
        for (var i = 0; i < lines.length; i++) {
            html += '<div>' + esc(lines[i]) + '</div>';
        }
        html += '</div>';
        return html;
    }

    function toast(msg, icon) {
        if (window.layer && typeof window.layer.msg === 'function') {
            window.layer.msg(msg, { icon: icon || 1, time: 1200 });
        }
    }

    /**
     * 复制文本：优先 Clipboard API，失败回退 execCommand（内网 http 页面没有
     * navigator.clipboard，必须保留回退路径，否则「点击复制」静默失效）。
     */
    function copy(text) {
        if (!text) {
            return;
        }
        var okMsg = t('config.copied_successfully', '复制成功！');
        var failMsg = t('config.copy_failed_please_the', '复制失败，请手动选择复制');

        function fallback() {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.top = '0';
            ta.style.left = '0';
            ta.style.width = '2em';
            ta.style.height = '2em';
            ta.style.padding = '0';
            ta.style.border = 'none';
            ta.style.outline = 'none';
            ta.style.boxShadow = 'none';
            ta.style.background = 'transparent';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            var ok = false;
            try {
                ok = document.execCommand('copy');
            } catch (e) {
                ok = false;
            }
            document.body.removeChild(ta);
            toast(ok ? okMsg : failMsg, ok ? 1 : 2);
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                toast(okMsg, 1);
            }).catch(function () {
                fallback();
            });
        } else {
            fallback();
        }
    }

    /**
     * 给地址行挂上「点击即复制」。用事件委托：弹窗内容可能是重新渲染的。
     * @param {string|jQuery} box 容器选择器
     */
    function bindCopy(box) {
        var $ = window.jQuery;
        if (!$) {
            return;
        }
        function install() {
            $(box).off('click.yfssl', '.yf-ssl-url-row')
                .on('click.yfssl', '.yf-ssl-url-row', function () {
                    copy($(this).attr('data-url') || '');
                })
                .off('mouseenter.yfssl mouseleave.yfssl', '.yf-ssl-url-row')
                .on('mouseenter.yfssl', '.yf-ssl-url-row', function () {
                    $(this).css('background', '#eef9ef');
                })
                .on('mouseleave.yfssl', '.yf-ssl-url-row', function () {
                    $(this).css('background', '#f8f9fa');
                });
        }
        install();
    }

    /**
     * 重启后要跳转的地址：优先「与当前访问同主机」的那条（内网访问就留在内网，
     * 避免被踢到公网/NAT 回环），否则用后端给的首选地址。
     */
    function pickTarget(data) {
        var state = normalize(data);
        var host = ((window.location && window.location.hostname) || '').toLowerCase();
        if (host) {
            for (var i = 0; i < state.urls.length; i++) {
                var u = state.urls[i].url || '';
                var m = u.match(/^https?:\/\/([^:\/]+)/i);
                if (m && m[1].toLowerCase() === host) {
                    return u;
                }
            }
        }
        return state.url;
    }

    window.YfPanelSsl = {
        normalize: normalize,
        urlsHtml: urlsHtml,
        stepsHtml: stepsHtml,
        bindCopy: bindCopy,
        pickTarget: pickTarget,
        copy: copy,
        typeLabel: typeLabel
    };
})(window, document);
