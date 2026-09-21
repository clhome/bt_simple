// 验证 web/static/app/i18n.js 新增的 YfI18n.translateAny()
// 用最小 window/document 替身在 Node 里加载 i18n.js，注入插件字典后断言翻译结果。
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO = path.resolve(__dirname, '..', '..', '..');
const SRC = path.join(REPO, 'web', 'static', 'app', 'i18n.js');

const store = {};
const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  navigator: { language: 'en-US', userLanguage: 'en-US' },
  location: { href: 'http://localhost/', search: '', pathname: '/', hash: '' },
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  },
};
sandbox.window = sandbox;
sandbox.document = {
  readyState: 'complete',
  cookie: '',
  documentElement: { lang: '', setAttribute() {} },
  addEventListener() {},
  removeEventListener() {},
  querySelectorAll: () => [],
  querySelector: () => null,
  getElementById: () => null,
  createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, classList: { add() {}, remove() {} } }),
  createTextNode: () => ({}),
  body: { appendChild() {}, classList: { add() {}, remove() {} } },
  head: { appendChild() {} },
};

const ctx = vm.createContext(sandbox);
try {
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), ctx, { filename: SRC });
} catch (e) {
  console.log('加载 i18n.js 抛出异常（可忽略，只要 translateAny 已挂载）:', e.message);
}

const Yf = sandbox.window && sandbox.window.YfI18n;
if (!Yf || typeof Yf.translateAny !== 'function') {
  console.log('FAIL: window.YfI18n.translateAny 未导出');
  process.exit(1);
}
console.log('OK: translateAny 已导出');

// 注入模拟的「服务端直出」插件字典（键形态与真实语言包一致）
sandbox.window._pluginDicts = {
  docker: {
    '拉取失败:': 'Pull failed:',
    '删除容器': 'Delete container',
    '文件不存在': 'File not found',
  },
  mariadb: {
    '导入失败:': 'Import failed:',
    '删除容器': 'Supprimer le conteneur',
  },
  op_waf: {
    // 历史约定：部分键把分隔符后的空格也写进了键（值同样带尾随空格）
    '读取日志失败: ': 'Failed to read logs: ',
  },
};

function check(input, expect) {
  const got = Yf.translateAny(input);
  const ok = got === expect;
  console.log((ok ? '  PASS' : '  FAIL') + '  ' + JSON.stringify(input) + ' -> ' + JSON.stringify(got) + (ok ? '' : '  (期望 ' + JSON.stringify(expect) + ')'));
  return ok;
}

let all = true;
all = check('拉取失败:', 'Pull failed:') && all;                 // 精确命中
all = check('导入失败:', 'Import failed:') && all;               // 精确命中
all = check('删除容器', 'Delete container') && all;              // 同键冲突 -> 先到先得（docker 在前）
all = check('文件不存在', 'File not found') && all;
all = check('拉取失败: FileNotFoundError: x', 'Pull failed: FileNotFoundError: x') && all;  // 冒号前缀
all = check('导入失败: bad sql', 'Import failed: bad sql') && all;                          // 冒号前缀
all = check('未知错误: 无对应键', '未知错误: 无对应键') && all;      // 前缀无键 -> 原样
all = check('', '') && all;
all = check(null, null) && all;
all = check(' 拉取失败:', 'Pull failed:') && all;               // 首尾空白可容忍
// 键带尾随空格的历史约定：译文尾部空白必须去掉，不能与 rest 的前导空格叠加
all = check('读取日志失败: permission denied', 'Failed to read logs: permission denied') && all;
all = check('读取日志失败:', 'Failed to read logs:') && all;

// 字典数量变化后应自动重建索引（新插件加载）
sandbox.window._pluginDicts.redis = { '连接失败': 'Connection failed' };
all = check('连接失败', 'Connection failed') && all;

console.log(all ? '\nALL PASS' : '\nHAS FAILURE');
process.exit(all ? 0 : 1);
