// 任务队列「有任务结束」联动探针（jsdom 不需要：只抽出纯函数在 vm 里跑）
//
// 被 testsuite/test_plugin_update_linkage.py 调用：
//   node testsuite/js/task_idle_watcher_probe.js
//
// 验证 public.js 里的 yfWatchTaskIdle：
//   1. 计数**下降**才派发 yf:tasks-changed（任务结束）；
//   2. 计数不变 / 上升 一律不派发；
//   3. 短时间内的连续下降合并成一次事件（800ms 防抖）。
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PUB = path.join(__dirname, '..', '..', 'web', 'static', 'app', 'public.js');
const src = fs.readFileSync(PUB, 'utf8');

function extract(startMarker, endFnName) {
  const s = src.indexOf(startMarker);
  if (s < 0) throw new Error('未找到 ' + startMarker);
  const f = src.indexOf('function ' + endFnName, s);
  if (f < 0) throw new Error('未找到 function ' + endFnName);
  // 从函数名开始做花括号配对，取出完整函数体
  let i = src.indexOf('{', f);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const c = src[j];
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) return src.slice(s, j + 1);
    }
  }
  throw new Error('函数未闭合: ' + endFnName);
}

const block = extract('window.__yfTaskCountWatcher', 'yfWatchTaskIdle');

const events = [];
const sandbox = {
  window: {
    __yfTaskCountWatcher: { last: null, timer: null },
    dispatchEvent: function (ev) { events.push(ev && ev.type); }
  },
  CustomEvent: function (type) { this.type = type; },
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  parseInt: parseInt,
  isNaN: isNaN,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(block, sandbox);

const watch = sandbox.yfWatchTaskIdle;
const results = [];

function check(name, cond) {
  results.push({ name: name, ok: !!cond });
}

// 1) 首次调用只建立基线，不派发
watch(3);
check('首次计数不派发', events.length === 0);

// 2) 计数不变 / 上升不派发
watch(3);
watch(5);
check('计数不变或上升不派发', events.length === 0);

// 3) 连续下降合并成一次（防抖）
watch(2);
watch(1);
watch(0);

setTimeout(function () {
  check('计数下降派发一次', events.length === 1);
  check('事件名正确', events[0] === 'yf:tasks-changed');

  // 4) 再次下降 → 再派发一次
  watch(0);
  watch(-1); // 非法值忽略
  check('非法计数忽略', events.length === 1);

  setTimeout(function () {
    // 先恢复到一个基线，再下降
    watch(2);
    watch(1);
    setTimeout(function () {
      check('第二次下降再派发一次', events.length === 2);
      const failed = results.filter(function (r) { return !r.ok; });
      results.forEach(function (r) {
        console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name);
      });
      console.log('RESULT=' + (failed.length === 0 ? 'OK' : 'FAILED'));
      process.exit(failed.length === 0 ? 0 : 1);
    }, 1000);
  }, 1000);
}, 1000);
