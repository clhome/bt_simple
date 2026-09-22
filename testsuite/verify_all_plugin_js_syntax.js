const fs = require('fs');
const path = require('path');
const vm = require('vm');

const pluginsDir = path.resolve(__dirname, '../plugins');
const errors = [];
let totalChecked = 0;

function walk(dir) {
    const list = fs.readdirSync(dir);
    for (const item of list) {
        const p = path.join(dir, item);
        const stat = fs.statSync(p);
        if (stat.isDirectory()) {
            walk(p);
        } else if (item.endsWith('.js')) {
            checkJsFile(p);
        } else if (item.endsWith('.html')) {
            checkHtmlFile(p);
        }
    }
}

function checkJsFile(filePath) {
    totalChecked++;
    const code = fs.readFileSync(filePath, 'utf8');
    try {
        new vm.Script(code, { filename: filePath });
    } catch (e) {
        errors.push({
            file: path.relative(pluginsDir, filePath),
            type: 'JS',
            line: e.stack.split('\n')[0],
            message: e.message
        });
    }
}

function checkHtmlFile(filePath) {
    totalChecked++;
    const html = fs.readFileSync(filePath, 'utf8');
    const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
    let match;
    let index = 0;
    while ((match = scriptRegex.exec(html)) !== null) {
        index++;
        const code = match[1];
        if (!code.trim()) continue;
        try {
            new vm.Script(code, { filename: `${filePath}#script_${index}` });
        } catch (e) {
            errors.push({
                file: path.relative(pluginsDir, filePath),
                type: `HTML <script #${index}>`,
                message: e.message
            });
        }
    }
}

console.log('开始全面检查所有 38 个插件的 JS 语法...');
walk(pluginsDir);
console.log(`检查完成，共扫描文件/脚本: ${totalChecked}`);
if (errors.length > 0) {
    console.log(`发现 ${errors.length} 个语法错误：`);
    errors.forEach(err => {
        console.log(`  - [${err.type}] ${err.file}: ${err.message}`);
    });
} else {
    console.log('所有插件 JS 脚本语法全部校验通过！');
}
