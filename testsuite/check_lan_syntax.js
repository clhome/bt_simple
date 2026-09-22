const fs = require('fs');
const path = require('path');
const vm = require('vm');

const langDir = path.resolve(__dirname, '../web/static/language');
const langs = ['zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it'];

let hasError = false;

langs.forEach(lang => {
    const filePath = path.join(langDir, lang, 'lan.js');
    if (!fs.existsSync(filePath)) {
        console.error(`[MISSING] ${filePath} does not exist`);
        hasError = true;
        return;
    }
    const content = fs.readFileSync(filePath, 'utf8');
    try {
        const script = new vm.Script(content, { filename: `${lang}/lan.js` });
        const context = vm.createContext({ window: {} });
        script.runInContext(context);
        console.log(`[PASS] ${lang}/lan.js parsed successfully!`);
    } catch (e) {
        console.error(`[SYNTAX ERROR] in ${lang}/lan.js:`, e.message);
        hasError = true;
    }
});

process.exit(hasError ? 1 : 0);
