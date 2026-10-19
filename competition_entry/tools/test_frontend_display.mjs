import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(root, 'privedge/web/package.json'));
const ts = require('typescript');
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  vm.runInNewContext(source, { exports, require: name => name.startsWith('.')
    ? load(path.resolve(path.dirname(file), name + '.ts')) : require(name) }, {filename: file});
  cache.set(file, exports);
  return exports;
}
const p = load(path.join(root, 'privedge/web/src/presentation.ts'));
const common = load(path.join(root, 'privedge/web/src/components/common.tsx'));
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const checks = [];
function check(name, fn) { try { fn(); checks.push({name, passed:true}); } catch(e) { checks.push({name, passed:false, error:String(e)}); } }
check('Zero count stays zero', () => assert.equal(p.countText(0), '0'));
check('Missing count is explicit', () => assert.equal(p.countText(null), '未提供'));
check('Missing attack metric remains null', () => assert.equal(p.metricValue(null), null));
check('Zero attack metric remains zero', () => assert.equal(p.metricValue(0), 0));
check('Absent A8 baseline cell is missing, not inapplicable', () => assert.equal(p.refusalText('average'), '未提供'));
check('Baseline without three-state is inapplicable', () => assert.equal(p.refusalText('average',{refusal_rate:null}), '不适用（基线无三态）'));
check('Missing PrivEdge refusal rate stays missing', () => assert.equal(p.refusalText('privedge',{refusal_rate:null}), '未提供'));
check('Zero PrivEdge refusal rate stays zero', () => assert.equal(p.refusalText('privedge',{refusal_rate:0}), '0.0%'));
check('Different source limits fit chart', () => assert.ok(p.budgetScale([{spent:2,limit:4},{spent:6,limit:8}]) > 8));
check('Over-limit values are not clipped', () => assert.ok(p.budgetScale([{spent:9,limit:4}]) > 9));
check('Log follows at bottom', () => assert.equal(p.followsLog(1000,600,400), true));
check('Log stops following when reading earlier events', () => assert.equal(p.followsLog(1000,200,400), false));
check('Refused empty table explains refusal', () => {
  const html = renderToStaticMarkup(React.createElement(common.TopList,{items:[],state:'REFUSED'}));
  assert.match(html,/拒答/); assert.match(html,/colSpan="4"/i);
});
check('Baseline empty table uses three columns', () => {
  const html = renderToStaticMarkup(React.createElement(common.TopList,{items:[],showSupport:false}));
  assert.match(html,/colSpan="3"/i);
});
check('Chinese state keeps original code', () => {
  const html = renderToStaticMarkup(React.createElement(common.StateBadge,{state:'REFUSED'}));
  assert.match(html,/拒答/); assert.match(html,/REFUSED/);
});
check('Full hash can be inspected', () => {
  const hash = '1234567890abcdef'.repeat(4);
  const html = renderToStaticMarkup(React.createElement(common.HashValue,{value:hash}));
  assert.match(html,/<details/); assert.ok(html.includes(hash));
});
const { chartRows } = load(path.join(root, 'privedge/web/src/chartData.ts'));
check('Chart table preserves zero and missing cells separately', () => {
  const table = chartRows({xAxis:{data:['zero','missing','absent']},series:[{name:'指标',type:'bar',data:[0,null]}]});
  assert.equal(table.rows[0][1],0); assert.equal(table.rows[1][1],null); assert.equal(table.rows[2][1],null);
});
check('Chart table keeps source precision and category order', () => {
  const table = chartRows({xAxis:{name:'ε',data:['2','1']},series:[{name:'Recall',type:'line',data:[0.123456789,1]}]});
  assert.equal(table.headers.join('|'),'ε|Recall'); assert.equal(table.rows[0][0],'2'); assert.equal(table.rows[0][1],0.123456789);
});
check('Chart table never invents values for invalid numeric inputs', () => {
  const table = chartRows({xAxis:{data:['a','b','c']},series:[{type:'line',data:[NaN,Infinity,'0.5']}]});
  assert.ok(table.rows.every(row=>row[1]===null));
});
check('Topology requires its own state table', () => assert.equal(chartRows({series:[{type:'graph',data:[]}]}),null));
check('Chart table includes each defense series without transposing', () => {
  const table = chartRows({xAxis:{data:['攻击']},series:[{name:'基线',type:'bar',data:[1]},{name:'PrivEdge',type:'bar',data:[0]}]});
  assert.equal(table.headers.join('|'),'类别|基线|PrivEdge'); assert.equal(table.rows[0].join('|'),'攻击|1|0');
});
check('Section cards default to h2 and support nested h3', () => {
  assert.match(renderToStaticMarkup(React.createElement(common.Card,{title:'数据'},'正文')),/<h2>数据<\/h2>/);
  assert.match(renderToStaticMarkup(React.createElement(common.Card,{title:'明细',headingLevel:3},'正文')),/<h3>明细<\/h3>/);
});
console.log(JSON.stringify({checks, passed:checks.filter(c=>c.passed).length, total:checks.length},null,2));
if (checks.some(c=>!c.passed)) process.exitCode = 1;
