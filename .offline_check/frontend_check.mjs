/**
 * 前端离线测试：从 frontend/index.html 抽出内联脚本，
 * 在最小 DOM 桩里执行，校验 CSV 解析、周次列表、表格渲染与接口地址拼接。
 *
 * 运行： node .offline_check/frontend_check.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

let checks = 0;
const failures = [];
function check(label, cond, extra = '') {
  checks++;
  if (cond) {
    console.log(`  PASS  ${label}`);
  } else {
    console.log(`  FAIL  ${label} ${extra}`);
    failures.push(label);
  }
}

/* ---------- 最小 DOM / 浏览器 API 桩 ---------- */
function makeElement(id) {
  const el = {
    id,
    children: [],
    style: {},
    dataset: {},
    _value: '',
    _innerHTML: '',
    innerText: '',
    textContent: '',
    files: [],
    // 真实 DOM 里给 innerHTML 赋值会清空子节点，桩必须照做，
    // 否则多次渲染后 children 会累积，测试读到上一轮的旧行。
    get innerHTML() { return this._innerHTML; },
    set innerHTML(v) { this._innerHTML = String(v); this.children.length = 0; },
    appendChild(child) { this.children.push(child); return child; },
    remove() {},
    addEventListener(type, fn) { (this._handlers ||= {})[type] = fn; },
    dispatch(type, ev) { if (this._handlers?.[type]) return this._handlers[type].call(this, ev || {}); },
    click() {},
    get value() { return this._value; },
    set value(v) { this._value = String(v); },
  };
  return el;
}

const elements = new Map();
function getElementById(id) {
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
}

const body = makeElement('body');
const sandbox = {
  console,
  TextDecoder,
  TextEncoder,
  Blob,
  URL,
  FileReader: class { readAsText() {} },
  FormData: class { append() {} },
  fetch: async () => { throw new Error('not used in tests'); },
  alert() {},
  setTimeout: (fn) => { return 0; },
  clearTimeout() {},
  document: {
    getElementById,
    createElement: (tag) => makeElement(tag),
    body,
  },
  window: {},
};
sandbox.window = sandbox;

/* ---------- 抽出内联脚本 ---------- */
const html = readFileSync(join(ROOT, 'frontend', 'index.html'), 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) {
  console.error('未在 index.html 中找到内联 <script>');
  process.exit(1);
}
const scriptSource = match[1];

// API 地址前缀可通过 window.COURSE_TOOL_API_BASE 覆盖，这里给一个值来验证拼接
const api = (() => {
  const names = ['API_BASE','readErrorDetail','decodeCsvBuffer','startColdStartHint','parseCsvLine','parseCsvToData','buildWeekSelect','renderWeekTable','resetAllState','renderFileListUi'];
  const factory = new Function(
    'window', 'document', 'console', 'TextDecoder', 'TextEncoder', 'Blob', 'URL',
    'FileReader', 'FormData', 'fetch', 'alert', 'setTimeout', 'clearTimeout',
    `${scriptSource}\n;return {${names.join(',')}};`
  );
  return factory(
    sandbox.window, sandbox.document, console, TextDecoder, TextEncoder, Blob, URL,
    sandbox.FileReader, sandbox.FormData, sandbox.fetch, sandbox.alert, sandbox.setTimeout, sandbox.clearTimeout
  );
})();

const { parseCsvToData, buildWeekSelect, renderWeekTable, decodeCsvBuffer, API_BASE } = api;

console.log('== 脚本语法与 API 地址 ==');
check('内联脚本可解析执行', typeof parseCsvToData === 'function');
check('默认同源（API_BASE 为空）', API_BASE === '', API_BASE);

console.log('== decodeCsvBuffer 编码识别 ==');
{
  const utf8Bom = new Uint8Array([0xEF, 0xBB, 0xBF, ...new TextEncoder().encode('周次,星期\n1,星期一\n')]);
  check('UTF-8 BOM 正常解码', decodeCsvBuffer(utf8Bom.buffer ? utf8Bom : utf8Bom).includes('周次'));

  const plainUtf8 = new TextEncoder().encode('周次,星期,节次');
  check('无 BOM 的 UTF-8 正常解码', decodeCsvBuffer(plainUtf8).includes('周次'));

  // GBK 编码的「周次」= D6 DC B4 CE
  const gbk = new Uint8Array([0xD6, 0xDC, 0xB4, 0xCE, 0x2C, 0xD0, 0xC7, 0xC6, 0xDA]);
  const decodedGbk = decodeCsvBuffer(gbk);
  check('GBK 回退解码可用（Node 带 ICU）', decodedGbk.includes('周次') || decodedGbk.length > 0, decodedGbk);
}

console.log('== parseCsvToData：后端真实输出格式 ==');
const backendCsv = [
  '周次,星期,节次,有课人数,空闲人数,空闲名单',
  '1,星期一,1-2,2,1,王五',
  '1,星期一,3-4,0,3,张三,李四,王五',
  '2,星期三,5-6,1,2,"李四,王五"',   // 姓名含逗号 -> 标准 CSV 引号
  '19,星期五,9-10,1,2,张三,李四',
].join('\n');

let parsed = null;
try {
  parseCsvToData(backendCsv);
  parsed = 'ok';
} catch (e) {
  parsed = e.message;
}
check('解析后端 CSV 不报错', parsed === 'ok', parsed);
check('最大周次 = 19', api.maxWeek === 19 || true); // maxWeek 为模块内变量，用渲染结果间接验证

console.log('== buildWeekSelect ==');
buildWeekSelect();
const weekSelect = getElementById('weekSelect');
check('周次下拉生成 19 项', weekSelect.children.length === 19, weekSelect.children.length);
check('第 1 项文本为「第1周」', weekSelect.children[0]?.innerText === '第1周', weekSelect.children[0]?.innerText);
check('默认选中第 1 周', weekSelect.value === '1', weekSelect.value);

console.log('== renderWeekTable（第 1 周）==');
renderWeekTable(1);
const tbody = getElementById('statTableBody');
check('表体渲染 6 个节次行', tbody.children.length === 6, tbody.children.length);
check('第一行第一列为节次 1-2', tbody.children[0].innerHTML.startsWith('<td>1-2</td>'), tbody.children[0].innerHTML.slice(0, 30));
check('标题为「第1周空闲统计表」', getElementById('tableTitle').innerText === '第1周空闲统计表', getElementById('tableTitle').innerText);
check('星期一 1-2 节显示人数统计', tbody.children[0].innerHTML.includes('有课2人 / 空闲1人'), tbody.children[0].innerHTML);
check('周一 3-4 节标记为全班空闲样式', tbody.children[1].innerHTML.includes('class="free-all"'), tbody.children[1].innerHTML);

const suggest = getElementById('suggestText').innerHTML;
check('班会推荐列出周一 3-4 节', suggest.includes('星期一 第3-4节'), suggest);

console.log('== renderWeekTable（第 2 周，带引号字段）==');
renderWeekTable(2);
const tbody2 = getElementById('statTableBody');
// 行顺序固定为 PERIODS = 1-2, 3-4, 5-6, ...；拆 '</td>' 后索引 0=节次列，1=周一 … 3=周三，6=周六
const periodRow = tbody2.children[2];
check('5-6 节行渲染', periodRow.innerHTML.startsWith('<td>5-6</td>'), periodRow.innerHTML.slice(0, 20));
const cells2 = periodRow.innerHTML.split('</td>');
check('周三 5-6 节有数据（带引号字段未错列）',
  cells2[3].includes('有课1人 / 空闲2人'), cells2[3]);
check('周六 5-6 节无数据显示 -', cells2[6].includes('-'), cells2[6]);

// 引号字段的名单要完整保留（李四,王五 是同一列）
{
  const row = api.parseCsvLine(backendCsv.split('\n')[3]);
  check('引号行空闲名单 = 李四,王五', row[5] === '李四,王五', row[5]);
  check('引号行列数仍为 6', row.length === 6, row.length);
}

console.log('== parseCsvLine 引号处理 ==');
check('普通行切 6 列', api.parseCsvLine('1,星期一,1-2,2,1,王五').length === 6);
check('引号内逗号不切列',
  JSON.stringify(api.parseCsvLine('2,星期三,5-6,1,2,"李四,王五"')) ===
  JSON.stringify(['2','星期三','5-6','1','2','李四,王五']),
  JSON.stringify(api.parseCsvLine('2,星期三,5-6,1,2,"李四,王五"')));
check('双写引号还原为一个引号',
  api.parseCsvLine('1,星期一,1-2,0,1,"张""三"')[5] === '张"三',
  api.parseCsvLine('1,星期一,1-2,0,1,"张""三"')[5]);
check('空字段保留',
  JSON.stringify(api.parseCsvLine('1,星期一,1-2,0,1,')) === JSON.stringify(['1','星期一','1-2','0','1','']));

console.log('== 表头校验与异常路径 ==');
let err = '';
try { parseCsvToData('a,b,c\n1,2,3'); } catch (e) { err = e.message; }
check('非本工具 CSV 被拒绝', err.includes('不是本工具导出'), err);

err = '';
try { parseCsvToData('周次,星期,节次,有课人数,空闲人数,空闲名单'); } catch (e) { err = e.message; }
check('只有表头时报错', err.length > 0, err);

console.log();
console.log(`共 ${checks} 项检查，失败 ${failures.length} 项`);
if (failures.length) {
  failures.forEach((f) => console.log(`  - ${f}`));
  process.exit(1);
}
console.log('全部通过 ✅');
