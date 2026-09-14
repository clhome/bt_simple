const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

// Usage: node ast_transform_i18n.js <filePath> <sectionName> <prefix> <dictOutputPath>
const args = process.argv.slice(2);
if (args.length < 4) {
    console.error('Usage: node ast_transform_i18n.js <filePath> <sectionName> <prefix> <dictOutputPath>');
    process.exit(1);
}

const [filePath, sectionName, prefix, dictOutputPath] = args;
console.log(`Processing ${filePath} for section [${sectionName}] with prefix [${prefix}]...`);

const code = fs.readFileSync(filePath, 'utf-8');

const ast = parser.parse(code, {
    sourceType: 'script',
    allowReturnOutsideFunction: true,
});

const dictionary = {};
let keyCounter = 1;

function containsChinese(str) {
    return /[\u4e00-\u9fa5]/.test(str);
}

traverse(ast, {
    StringLiteral(p) {
        // Skip if this string is an object property key: { "中文": 123 } or { 中文: 123 }
        if (p.parentPath.isObjectProperty() && p.parentPath.node.key === p.node) {
            return;
        }
        // Skip if this string is part of an import/export or require
        if (p.parentPath.isImportDeclaration() || p.parentPath.isExportNamedDeclaration()) {
            return;
        }
        // Skip if already wrapped in (lan && lan.section && lan.section.key || '')
        if (p.parentPath.isLogicalExpression() && p.parentPath.node.operator === '||') {
            const left = p.parentPath.node.left;
            if (left && left.type === 'LogicalExpression') {
                return;
            }
        }

        const value = p.node.value;
        if (containsChinese(value)) {
            const key = prefix + keyCounter++;
            dictionary[key] = value;

            const lanIdent = t.identifier('lan');
            const secIdent = t.identifier(sectionName);
            const keyIdent = t.identifier(key);

            const lanSec = t.memberExpression(lanIdent, secIdent);
            const lanSecKey = t.memberExpression(lanSec, keyIdent);

            const lanAndLanSec = t.logicalExpression('&&', lanIdent, lanSec);
            const fullLanCheck = t.logicalExpression('&&', lanAndLanSec, lanSecKey);

            const fallback = t.stringLiteral('');
            const replacement = t.logicalExpression('||', fullLanCheck, fallback);
            replacement.extra = { parenthesized: true };

            p.replaceWith(replacement);
            p.skip();
        }
    }
});

const output = generate(ast, {
    retainLines: false,
    compact: false,
    quotes: 'single',
}, code);

fs.writeFileSync(filePath, output.code, 'utf-8');
fs.writeFileSync(dictOutputPath, JSON.stringify(dictionary, null, 2), 'utf-8');

console.log(`Successfully transformed ${filePath}. Extracted ${Object.keys(dictionary).length} phrases to ${dictOutputPath}`);
