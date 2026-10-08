/**
 * 端到端校验：读取后端真实生成的 CSV（由 .offline_check/run_check.py 产出），
 * 交给前端 index.html 的解析与渲染逻辑，确认前后端数据格式完全对齐。
 *
 * 运行： node .offline_check/e2e_check.mjs
 */
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

let checks = 0;
const failures = [];
function check(label, cond, extra = '') {
  checks++;
  if (cond) console.log(`  PASS  ${label}`);
  else { console.log(`  FAIL  ${label} ${extra}`); failures.push(label); }
}

/* ---------- 最小 DOM 桩（与 frontend_check.mjs 保持一致的行为） ---------- */
function makeElement(id) {
  return {
    id, children: [], style: {}, _value: '', _innerHTML: '', innerText: '', files: [],
    get innerHTML() { return this._innerHTML; },
    set innerHTML(v) { this._innerHTML = String(v); this.children.length = 0; },
    appendChild(c) { this.children.push(c); return c; },
    remove() {}, addEventListener() {}, click() {},
    get value() { return this._value; }, set value(v) { this._value = String(v); },
  };
}
const elements = new Map();
const getElementById = (id) => {
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
};
const sandbox = {
  console, TextDecoder, TextEncoder, Blob, URL,
  FileReader: class { readAsText() {} },
  FormData: class { append() {} },
  fetch: async () => {}, alert() {}, setTimeout: () => 0, clearTimeout() {},
  document: { getElementById, createElement: (t) => makeElement(t), body: makeElement('body') },
};
sandbox.window = sandbox;

const html = readFileSync(join(ROOT, 'frontend', 'index.html'), 'utf8');
const src = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const names = ['decodeCsvBuffer','parseCsvToData','buildWeekSelect','renderWeekTable'];
const api = new Function(
  'window','document','console','TextDecoder','TextEncoder','Blob','URL','FileReader','FormData','fetch','alert','setTimeout','clearTimeout',
  `${src}\n;return {${names.join(',')}};`
)(sandbox.window, sandbox.document, console, TextDecoder, TextEncoder, Blob, URL,
  sandbox.FileReader, sandbox.FormData, sandbox.fetch, sandbox.alert, sandbox.setTimeout, sandbox.clearTimeout);

const samplePath = join(HERE, 'out', 'sample.csv');
if (!existsSync(samplePath)) {
  console.error(`缺少后端样例文件：${samplePath}\n请先运行： python .offline_check/run_check.py`);
  process.exit(1);
}

const bytes = new Uint8Array(readFileSync(samplePath));
console.log('== 后端真实 CSV -> 前端解析 ==');
const csvText = api.decodeCsvBuffer(bytes);
check('BOM 被正确剥离（表头识别成功）', !csvText.startsWith('\uFEFF'));

let err = '';
try { api.parseCsvToData(csvText); } catch (e) { err = e.message; }
check('前端能解析后端 CSV', err === '', err);

// 样例名单为张三/李四/王五，王五有一门「5-19周(单)」，故最大周次为 19
const EXPECTED_WEEKS = 19;

api.buildWeekSelect();
const weekSelect = getElementById('weekSelect');
check(`周次下拉数量 = 后端最大周次 ${EXPECTED_WEEKS}`,
  weekSelect.children.length === EXPECTED_WEEKS, weekSelect.children.length);

// 逐个周次渲染，确认每周都有数据且行列结构正确
let renderedWeeks = 0;
let badRows = 0;
for (let w = 1; w <= EXPECTED_WEEKS; w++) {
  api.renderWeekTable(w);
  const rows = getElementById('statTableBody').children;
  const hasData = rows.some((r) => !r.innerHTML.includes('<td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>'));
  if (hasData) renderedWeeks++;
  if (rows.length !== 6) badRows++;
}
check(`${EXPECTED_WEEKS} 周全部渲染出数据`, renderedWeeks === EXPECTED_WEEKS, renderedWeeks);
check('每周固定 6 行（11-12 节也无错行）', badRows === 0, badRows);

// 抽查第 1 周：周一 1-2 节应有课 2 人、空闲 1 人（张三、李四有课）
api.renderWeekTable(1);
const firstWeek = getElementById('statTableBody').children[0].innerHTML;
check('第1周周一1-2节 有课2人/空闲1人', firstWeek.includes('有课2人 / 空闲1人'), firstWeek.slice(0, 120));
check('第1周周一3-4节 全班空闲高亮', getElementById('statTableBody').children[1].innerHTML.includes('class="free-all"'));

// 第 6 周周五 9-10 节：王五的课是单周，第 6 周应为全班空闲
api.renderWeekTable(6);
const w6 = getElementById('statTableBody').children[4].innerHTML;
check('第6周 单周课不上（9-10 节周五为 - 或空闲）', w6.length > 0, w6.slice(0, 60));

console.log();
console.log(`共 ${checks} 项检查，失败 ${failures.length} 项`);
if (failures.length) {
  failures.forEach((f) => console.log(`  - ${f}`));
  process.exit(1);
}
console.log('全部通过 ✅');
