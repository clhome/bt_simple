/**
 * 御风面板 —— 弹窗（layer）尺寸自适应兜底层
 *
 * ## 为什么需要
 *
 * 全站弹窗都写死了像素尺寸（`area: ['480px', '280px']` 之类）。中文短语在 280px
 * 高里放得下，同一条文案翻成英文/德文/法文后行数翻倍（例：「关闭SSL证书」确认框，
 * 英文提示 3 行 + 输入框，280px 直接切掉输入框，用户以为弹窗坏了）。
 *
 * 逐个改调用点既改不完（42 处 `area`）也防不住以后新写的弹窗，所以在 layer 之上
 * 加一层**统一归一化**：
 *
 *   1. 宽度：`min(配置值, 94vw)`，下限 300px —— 小屏笔记本/平板不再横向溢出；
 *   2. 高度：非 iframe 且配置高度 < 500px 的弹窗一律改成 `'auto'`
 *      （这类都是文本/确认框，内容多高就多高，从此不会切字）；
 *      配置高度 >= 500px 的保留（多是带内部滚动区的表格/表单），只夹到 88vh；
 *   3. 打开后再校正一次：超宽则收窄（同时把 auto 高度重算），超高则压到 88vh，
 *      由 layer 自身的内容区滚动兜底，绝不会出现「按钮跑到屏幕外」；
 *   4. 长标题自动换行（超过 20 字符才动，短标题观感不变）；
 *   5. 注入一条 CSS：内容区 `word-break: break-word`，长 URL / 长单词不会撑破弹窗。
 *
 * ## 逃生口
 *
 * 真的需要固定尺寸的弹窗（例如 iframe 页、带设计稿的布局），在 `layer.open({...})`
 * 里加 `yfAdaptive: false` 即可完全绕过本层。
 *
 * 该脚本必须在 layer 之后、业务脚本之前加载（layout.html 里紧跟 layer.js）。
 */
(function (window, document) {
    'use strict';

    var layer = window.layer;
    if (!layer || typeof layer.open !== 'function') {
        return;  // layer 没加载（或已降级）时不接管，保持原生行为
    }
    if (layer.__yfAdaptivePatched) {
        return;
    }
    layer.__yfAdaptivePatched = true;

    var MIN_WIDTH = 300;        // 再窄按钮就挤成一行放不下
    var SMALL_HEIGHT = 500;     // 低于此高度的固定弹窗 = 文本/确认框 → 高度改为 auto
    var MAX_WIDTH_RATIO = 0.94; // 视口宽度的上限比例
    var MAX_HEIGHT_RATIO = 0.88;// 视口高度的上限比例（留出标题栏与浏览器 UI 空间）
    var TITLE_WRAP_CHARS = 20;  // 标题超过该长度才允许换行

    function viewportWidth() {
        return window.innerWidth || (document.documentElement && document.documentElement.clientWidth) || 1024;
    }

    function viewportHeight() {
        return window.innerHeight || (document.documentElement && document.documentElement.clientHeight) || 768;
    }

    function maxWidth() {
        return Math.round(viewportWidth() * MAX_WIDTH_RATIO);
    }

    function maxHeight() {
        return Math.round(viewportHeight() * MAX_HEIGHT_RATIO);
    }

    /** '480px' / 480 → 480；'auto' / '85%' / 'inherit' → null */
    function pxValue(v) {
        if (typeof v === 'number' && isFinite(v)) {
            return v;
        }
        if (typeof v === 'string' && /^\d+(\.\d+)?px$/i.test(v.trim())) {
            return parseFloat(v);
        }
        return null;
    }

    function clampWidth(v) {
        var upper = maxWidth();
        var lower = Math.min(MIN_WIDTH, upper);
        return Math.max(Math.min(v, upper), lower);
    }

    function isIframe(opts) {
        return !!(opts && (opts.type === 2 || opts.type === '2'));
    }

    /**
     * 归一化 `area`。返回新数组（不改调用方对象）。
     * 只处理「px 写死」的维度：百分比 / auto / 缺省一概不动（那是布局弹窗的本意）。
     */
    function normalizeArea(area, opts) {
        if (!area || typeof area === 'string' || typeof area.length !== 'number' || !area.length) {
            return area;
        }
        var out = [];
        var wPx = pxValue(area[0]);
        out[0] = (wPx === null) ? area[0] : (clampWidth(wPx) + 'px');

        if (area.length < 2 || area[1] === undefined || area[1] === null || area[1] === '') {
            return out;
        }

        var hPx = pxValue(area[1]);
        if (hPx === null) {
            out[1] = area[1];
            return out;
        }
        if (!isIframe(opts) && hPx < SMALL_HEIGHT) {
            // 文本/确认框：高度交给内容，翻译再长也不会被切掉
            out[1] = 'auto';
            return out;
        }
        out[1] = Math.max(Math.min(hPx, maxHeight()), 160) + 'px';
        return out;
    }

    function injectCss() {
        if (document.getElementById('yfAdaptiveDialogCss')) {
            return;
        }
        var style = document.createElement('style');
        style.id = 'yfAdaptiveDialogCss';
        style.type = 'text/css';
        style.appendChild(document.createTextNode(
            '.layui-layer .layui-layer-content{word-break:break-word;overflow-wrap:anywhere;}' +
            '.layui-layer.yf-adaptive-title .layui-layer-title{white-space:normal;height:auto;' +
            'line-height:20px;padding-top:10px;padding-bottom:10px;}' +
            '.layui-layer .layui-layer-btn{padding-bottom:12px;}'
        ));
        var head = document.head || document.getElementsByTagName('head')[0];
        if (head) {
            head.appendChild(style);
        }
    }

    function tuneTitle(layero) {
        if (!layero || typeof layero.find !== 'function') {
            return;
        }
        var $title = layero.find('.layui-layer-title');
        if (!$title.length) {
            return;
        }
        var text = ($title.text() || '').trim();
        if (text.length > TITLE_WRAP_CHARS) {
            layero.addClass('yf-adaptive-title');
        }
    }

    /**
     * 打开后校正：超宽收窄（auto 高度的同时重算），超高压缩到 88vh（内容区自己滚）。
     */
    function fit(layero, index, allowAutoHeight) {
        if (!layero || !layero.length || typeof layero.outerWidth !== 'function') {
            return;
        }
        var limitW = maxWidth();
        if (layero.outerWidth() > limitW) {
            var size = { width: limitW + 'px' };
            if (allowAutoHeight) {
                size.height = 'auto';
            }
            layer.style(index, size);
        }
        var limitH = maxHeight();
        if (layero.outerHeight() > limitH) {
            layer.style(index, { height: limitH + 'px' });
        }
    }

    var rawOpen = layer.open;
    layer.open = function (opts) {
        if (!opts || typeof opts !== 'object' || opts.yfAdaptive === false) {
            return rawOpen.apply(layer, arguments);
        }

        var prepared = {};
        for (var k in opts) {
            if (Object.prototype.hasOwnProperty.call(opts, k)) {
                prepared[k] = opts[k];
            }
        }
        prepared.area = normalizeArea(opts.area, opts);
        // 高度「由内容决定」的情况：显式 'auto'、只给了宽度、或压根没给 area。
        // 这类弹窗在收窄宽度后必须把高度也交回内容，否则文字重新换行后高度不会变，
        // 底部就又被切掉（正是本次要根除的毛病）。iframe 例外：auto 会让高度塌成 0。
        var areaIsArray = prepared.area && typeof prepared.area === 'object' &&
            typeof prepared.area.length === 'number';
        var autoHeight = !isIframe(opts) &&
            (!areaIsArray || prepared.area.length < 2 ||
             String(prepared.area[1]).toLowerCase() === 'auto');

        var userSuccess = opts.success;
        prepared.success = function (layero, index) {
            injectCss();
            tuneTitle(layero);
            fit(layero, index, autoHeight);
            if (typeof userSuccess === 'function') {
                userSuccess.apply(this, arguments);
            }
            // 业务 success 里常会再填内容（表格/列表），下一帧再量一次
            if (typeof window.requestAnimationFrame === 'function') {
                window.requestAnimationFrame(function () {
                    fit(layero, index, autoHeight);
                });
            }
        };

        return rawOpen.call(layer, prepared);
    };

    // 供用例/页面显式复算（例如内容异步变化后手动校正）
    window.YfAdaptiveDialog = {
        normalizeArea: normalizeArea,
        fit: fit,
        isIframe: isIframe,
        limits: function () {
            return { width: maxWidth(), height: maxHeight() };
        }
    };
})(window, document);
