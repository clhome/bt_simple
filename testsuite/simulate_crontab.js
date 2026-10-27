const fs = require('fs');
const path = require('path');

global.window = global;
global.document = {
    cookie: '',
    addEventListener: () => {},
    querySelectorAll: () => []
};
global.localStorage = {
    getItem: () => 'en',
    setItem: () => {}
};

const lanJs = fs.readFileSync(path.join(__dirname, '../web/static/language/en/lan.js'), 'utf-8');
eval(lanJs);
global.lan = lan;
window.lan = lan;

const i18nJs = fs.readFileSync(path.join(__dirname, '../web/static/app/i18n.js'), 'utf-8');
eval(i18nJs);

let ptimeHtml = '';
global.$ = function(selector) {
    return {
        html: function(val) {
            if (val === undefined) return ptimeHtml;
            ptimeHtml = val;
            return this;
        },
        append: function(val) {
            ptimeHtml += val;
            return this;
        },
        on: function() { return this; },
        // 行内操作改成了事件委派（$(document).off(...).on(...)），stub 必须支持链式 off
        off: function() { return this; },
        removeAttr: function() { return this; },
        val: function() { return ''; }
    };
};
global.getselectname = function() {};

const crontabJs = fs.readFileSync(path.join(__dirname, '../web/static/app/crontab.js'), 'utf-8');
eval(crontabJs);

console.log("=== 1. Testing toWeek() + toHour() + toMinute() in EN ===");
toWeek();
toHour();
toMinute();
console.log(ptimeHtml);

console.log("\n=== 2. Testing toMinuteN() in EN ===");
closeOpt();
toMinuteN();
console.log(ptimeHtml);

console.log("\n=== 3. Testing getDayTypeText ===");
console.log("day_type 0:", JSON.stringify(getDayTypeText('0')));
console.log("day_type 1:", JSON.stringify(getDayTypeText('1')));
console.log("day_type 2:", JSON.stringify(getDayTypeText('2')));
console.log("day_type 3:", JSON.stringify(getDayTypeText('3')));
