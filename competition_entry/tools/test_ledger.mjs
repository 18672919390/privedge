import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require=createRequire(path.join(root,'privedge/web/package.json'));
const ts=require('typescript'), cache=new Map();
function load(file){
  if(cache.has(file))return cache.get(file);
  const exports={};cache.set(file,exports);
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{exports,require:n=>{
    if(!n.startsWith('.'))return require(n);
    const p=path.resolve(path.dirname(file),n);return load(fs.existsSync(p+'.ts')?p+'.ts':p+'.tsx');
  }},{filename:file});return exports;
}
const src=path.join(root,'privedge/web/src');
const {numberText,chainText,canDrill,budgetEmptyText,verificationText,rejectionSummary,budgetOption}=load(path.join(src,'ledgerDisplay.ts'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {DrillResult,AuditDetail}=load(path.join(src,'pages/LedgerAudit.tsx'));
let passed=0;function check(name,fn){fn();passed++;console.log('PASS',name);}
const before={total:10,head:'a',chain_ok:true,first_bad:null};
check('Zero and missing budget values remain distinct',()=>{assert.equal(numberText(0),'0');for(const x of [null,undefined,NaN,Infinity])assert.equal(numberText(x),'未提供');});
check('Empty ledger is not an audited-business success',()=>{assert.equal(chainText({...before,total:0}),'暂无业务记录');assert.equal(chainText(before),'完整');assert.equal(chainText({...before,chain_ok:false,first_bad:0}),'第 0 条断裂');});
check('Drill requires valid sequence and loaded idle ledger',()=>{assert.ok(canDrill(before,0,false,'',false));for(const n of [-1,10,0.5,NaN])assert.ok(!canDrill(before,n,false,'',false));for(const [v,l,e,b] of [[null,false,'',false],[{...before,total:0},false,'',false],[before,true,'',false],[before,false,'error',false],[before,false,'',true]])assert.ok(!canDrill(v,0,l,e,b));});
check('No window and missing window budget have different explanations',()=>{assert.match(budgetEmptyText(null),/尚无发布窗口/);assert.match(budgetEmptyText('W1'),/该窗口未提供/);});
check('Original ledger verification requires actual matching snapshot',()=>{assert.match(verificationText(before,{...before}),/均未改变/);assert.match(verificationText(before,{...before,head:'b'}),/不能确认/);assert.match(verificationText(before,{...before,total:11}),/不能确认/);assert.match(verificationText(before,{...before,chain_ok:false}),/复核异常/);});
check('Budget bars preserve per-source limits and missing values',()=>{const chart=budgetOption([{source_id:'a',spent:0,limit:4},{source_id:'Petaling Jaya@2018',spent:null,limit:7}]);assert.equal(chart.series[0].data[0],0);assert.equal(chart.series[0].data[1],null);assert.deepEqual(Array.from(chart.series[1].data),[4,7]);assert.equal(chart.series[1].type,'bar');assert.ok(chart.xAxis.max>7);assert.equal(chart.yAxis.axisLabel.formatter('Petaling Jaya@2018').replaceAll('\n',''),'Petaling Jaya@2018');});
check('Rejection groups count actual repeated reasons',()=>{const groups=rejectionSummary([{code:'SIG',reason:'签名失败'},{code:'SIG',reason:'签名失败'},{code:'UNKNOWN'}]);assert.equal(groups[0].count,2);assert.equal(groups[1].reason,'接口未提供中文解释');});
check('Copy drill exposes change, zero-index break and refusal reason',()=>{const s=renderToStaticMarkup(React.createElement(DrillResult,{drill:{edited_seq:0,field:'epsilon',from:2,to:0,chain_ok:false,first_bad:0,decision_state:'REFUSED',decision_reason:'LEDGER_CORRUPTED'}}));for(const t of ['修改内容','2','0','第 0 条','拒答','REFUSED','LEDGER_CORRUPTED','账本完整性校验失败'])assert.ok(s.includes(t),t);});
check('Unexpected drill success is not presented as refusal',()=>{const s=renderToStaticMarkup(React.createElement(DrillResult,{drill:{edited_seq:1,field:'epsilon',from:0,to:.5,chain_ok:true,first_bad:null,decision_state:'NORMAL'}}));assert.ok(s.includes('非预期'));assert.ok(!s.includes('LEDGER_CORRUPTED'));});
check('Audit detail preserves identity, hashes and Chinese reasons',()=>{const s=renderToStaticMarkup(React.createElement(AuditDetail,{record:{request_id:'test-only',at:'2026-10-16',target_region:'a',record_hash:'record-hash',ledger_head:'ledger-hash',inputs:['input-hash'],ledger_chain_ok:false,ledger_first_bad:0,admission:{accepted:['Petaling Jaya@2018'],rejected:[{source_id:'b',code:'SIGNATURE_INVALID',reason:'签名校验失败'}]},decision:{state:'DEGRADED',reasons:[{code:'TEST',reason:'测试降级原因'}],alerts:[]}}}));for(const t of ['Petaling Jaya@2018','SIGNATURE_INVALID','签名校验失败','record-hash','ledger-hash','input-hash','第 0 条断裂','测试降级原因'])assert.ok(s.includes(t),t);});
console.log(`${passed} ledger checks passed; controlled fixtures, not business evidence.`);

