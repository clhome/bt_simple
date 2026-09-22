
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');

        // 模拟精简 DOM 环境
        const sandbox = {
            window: {},
            location: { pathname: '/', search: '', hash: '', href: 'http://127.0.0.1:8888/' },
            document: {
                readyState: 'complete',
                cookie: '',
                location: { pathname: '/', search: '', hash: '', href: 'http://127.0.0.1:8888/' },
                addEventListener: () => {},
                querySelectorAll: () => []
            },
            navigator: { language: 'en-US' },
            console: console,
            setTimeout: (fn) => fn()
        };
        sandbox.window = sandbox;
        sandbox.window.location = sandbox.location;
        sandbox.window.document = sandbox.document;

        // 模拟 jQuery
        function createFakeJQuery() {
            function $(selector) {
                if (typeof selector === 'function') {
                    selector();
                    return;
                }
                if (selector && typeof selector === 'object' && selector.__isElem) {
                    return selector;
                }
                return {
                    find: (sub) => $(sub),
                    closest: () => $({}),
                    each: function(cb) {
                        if (selector === '.bt-w-menu p') {
                            const sampleMenus = ['服务', '自启动', '容器列表', '镜像列表', '镜像导出', 'docker目录', '加速器', 'IP地址池', '仓库'];
                            sampleMenus.forEach((text) => {
                                let orig = text;
                                let current = text;
                                const elem = {
                                    __isElem: true,
                                    text: (newVal) => {
                                        if (newVal !== undefined) current = newVal;
                                        return current;
                                    },
                                    attr: (name, val) => {
                                        if (val !== undefined) orig = val;
                                        return orig;
                                    }
                                };
                                cb.call(elem);
                                if (/[\u4e00-\u9fa5]/.test(current)) {
                                    throw new Error("Untranslated menu found in DOM: " + current);
                                }
                            });
                        }
                    },
                    text: () => '',
                    attr: () => '',
                    trigger: () => {},
                    length: 1
                };
            }
            $.ajax = function(opts) {
                if (opts.url.includes('lang/en.json')) {
                    const filePath = path.resolve('plugins/docker/lang/en.json');
                    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
                    opts.success(data);
                }
            };
            return $;
        }

        sandbox.$ = createFakeJQuery();
        sandbox.window.$ = sandbox.$;
        vm.createContext(sandbox);

        // 加载并执行 i18n.js
        const i18nCode = fs.readFileSync('web/static/app/i18n.js', 'utf8');
        vm.runInContext(i18nCode, sandbox);

        // 设置当前语言为英文
        sandbox.YfI18n.setLanguage('en', false);

        // 测试创建 Docker 翻译器
        const pt = sandbox.YfI18n.createPluginTranslator('docker');
        
        // 验证 Docker 说明文案全部为纯正英文
        const testPhrases = [
            '御风Docker管理器 - 产品说明',
            '核心定位：',
            '极速拉取：',
            '便捷配置：',
            '资源管控：',
            '批量运维：',
            '本插件致力于提供比原生更加极速、稳定、易用的 Docker 容器与镜像管理体验。'
        ];

        for (const phrase of testPhrases) {
            const translated = pt(phrase);
            if (/[\u4e00-\u9fa5]/.test(translated)) {
                console.error(`Phrase '${phrase}' still has Chinese in translated: '${translated}'`);
                process.exit(1);
            }
        }

        // 测试 translatePluginDOM
        sandbox.YfI18n.translatePluginDOM({}, 'docker');
        console.log("Runtime simulation passed! 0 Chinese characters detected.");
        