import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require=createRequire(path.join(root,'privedge/web/package.json'));
const ts=require('typescript'), cache=new Map(), resources={};
let stateOverrides=null;
function load(file){
  if(cache.has(file))return cache.get(file);
  const exports={};cache.set(file,exports);
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{exports,require:n=>{
    if(n.endsWith('.css'))return {};
    if(n==='react')return {...require('react'),useState:initial=>stateOverrides ? [stateOverrides.shift(),()=>{}] : require('react').useState(initial)};
    if(n.endsWith('/useJSONResource'))return {useJSONResource:url=>resources[url]??{loading:false,error:'',data:null,retry(){}}};
    if(!n.startsWith('.'))return require(n);
    const p=path.resolve(path.dirname(file),n);return load(fs.existsSync(p+'.ts')?p+'.ts':p+'.tsx');
  }},{filename:file});return exports;
}
const src=path.join(root,'privedge/web/src');
const {meanText,intervalText,hasChartValues,selectedCells}=load(path.join(src,'experimentDisplay.ts'));
const {A8Comparison,A8Results,Score}=load(path.join(src,'components/A8Comparison.tsx'));
const {Experiments,EvidenceSlot}=load(path.join(src,'pages/Experiments.tsx'));
const {StrictA8Status}=load(path.join(src,'components/StrictA8Status.tsx'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
let count=0;function check(name,fn){fn();count++;console.log('PASS',name);}
check('zero and absent mean differ',()=>{assert.equal(meanText(0),'0.0000');for(const v of [null,undefined,NaN,Infinity])assert.equal(meanText(v),'未提供');});
check('interval bounds must be finite ordered pairs',()=>{assert.equal(intervalText([0,0]),'[0.0000, 0.0000]');for(const v of [null,[],[1],[1,0],[0,NaN],[0,1,2]])assert.equal(intervalText(v),'区间未提供');});
check('absent interval does not erase mean',()=>{const html=render(Score,{value:0});assert.match(html,/0.0000/);assert.match(html,/区间未提供/);});
check('zero-valued chart remains available',()=>{assert.equal(hasChartValues({series:[{data:[null,0]}]}),true);assert.equal(hasChartValues({series:[{data:[undefined,NaN]}]}),false);});
check('epsilon and scenario require exact match',()=>{assert.equal(selectedCells([{epsilon:1,scenario:'clean'},{epsilon:2,scenario:'attack'}],2,'clean').length,0);});
check('resource loading error missing success are separate',()=>{
  for(const [props,pattern] of [[{loading:true},/正在读取/],[{error:'503'},/加载失败/],[{available:false},/当前条件未提供/],[{available:true},/content/]])assert.match(render(EvidenceSlot,{loading:false,error:'',available:false,retry(){},children:'content',...props}),pattern);
});
const endpoints=['/api/evidence','/api/evidence/a8','/api/evidence/a8/descriptive','/api/prereg'];
const payload={};
const baseURL = process.env.E31_TEST_BASE_URL || 'http://127.0.0.1:8766';
for(const endpoint of endpoints){const r=await fetch(baseURL+endpoint);assert.ok(r.ok);payload[endpoint]=await r.json();}
if(process.env.E31_TEST_LOG_DIR)fs.writeFileSync(path.join(process.env.E31_TEST_LOG_DIR,'experiments-real-api.json'),JSON.stringify(payload,null,2));
const descriptive=payload['/api/evidence/a8/descriptive'];
const documentCount=payload['/api/prereg'].length;
check('Every original method definition and evidence limitation remains visible',()=>{
 for(const dataset of Object.values(descriptive.datasets)){
  const html=render(A8Results,{selected:dataset,epsilon:2,scenario:'clean'});
  for(const definition of dataset.methods.map(method=>method.definition))assert.ok(html.includes(renderToStaticMarkup(React.createElement('span',null,definition)).slice(6,-7)),definition);
  assert.ok(dataset.limitations.length>0);
  for(const limitation of dataset.limitations)assert.ok(html.includes(renderToStaticMarkup(React.createElement('span',null,limitation)).slice(6,-7)),limitation);
 }
});
check('Descriptive heading stays concise without a disclaimer paragraph',()=>{
 stateOverrides=[descriptive,'',0,2,'clean'];
 const html=render(A8Comparison,{datasetName:'meituan_trd',selectDataset(){}});stateOverrides=null;
 assert.ok(html.includes('四方法对照 · 描述性结果'));
 assert.ok(!html.includes('不是先定方案、后看结果的确认性结论'));
});
check('54 real condition groups match API means intervals and applicability',()=>{
  let groups=0;
  for(const dataset of Object.values(descriptive.datasets))for(const epsilon of [1,2])for(const scenario of new Set(dataset.cells.map(c=>c.scenario))){
    const html=render(A8Results,{selected:dataset,epsilon,scenario});
    const cells=dataset.cells.filter(c=>c.epsilon===epsilon&&c.scenario===scenario);assert.equal(cells.length,4);
    for(const cell of cells)for(const key of ['ndcg','recall','attack_success']){assert.ok(html.includes(meanText(cell[key])));assert.ok(html.includes(intervalText(cell[key+'_ci95'])));}
    assert.ok(html.includes(dataset.source_run_id));assert.ok(html.includes(dataset.provenance.source_results_sha256));
    assert.equal((html.match(/不适用（基线无三态）/g)||[]).length,3);groups++;
  }
  assert.equal(groups,54);
});
check('missing cells never borrow another condition or imply baseline applicability',()=>{const d={...descriptive.datasets.meituan_trd,cells:[]};const html=render(A8Results,{selected:d,epsilon:1,scenario:'clean'});assert.match(html,/当前 ε 与场景未提供/);assert.ok(!html.includes('不适用（基线无三态）'));assert.ok(!html.includes('0.0000'));});
for(const endpoint of endpoints)resources[endpoint]={loading:false,error:'',data:payload[endpoint],retry(){}};
check('strict NOT_RUN is isolated and has no stray zero',()=>{const html=render(StrictA8Status,{datasetName:'meituan_trd'});assert.match(html,/NOT_RUN/);assert.ok(!html.includes('</p>0'));assert.ok(!html.includes('查看严格登记详情'));});
check('missing utility leaves formal overhead attacks and documents available',()=>{resources['/api/evidence'].data={...payload['/api/evidence'],utility:{}};const html=render(Experiments,{datasetName:'meituan_trd',selectDataset(){}});for(const v of ['formal_v1','overhead_v1','security_v2',`${documentCount} 份文档`])assert.ok(html.includes(v),v);assert.match(html,/当前条件未提供/);});
check('ordinary evidence failure leaves document resource visible',()=>{resources['/api/evidence']={loading:false,error:'controlled 503',data:null,retry(){}};const html=render(Experiments,{datasetName:'meituan_trd',selectDataset(){}});assert.match(html,/controlled 503/);assert.ok(html.includes(`${documentCount} 份文档`));assert.match(html,/四方法对照 · 描述性结果/);assert.ok(!html.includes('不是先定方案、后看结果的确认性结论'));});
check('document failure leaves evidence available',()=>{resources['/api/evidence']={loading:false,error:'',data:payload['/api/evidence'],retry(){}};resources['/api/prereg']={loading:false,error:'controlled documents 503',data:null,retry(){}};const html=render(Experiments,{datasetName:'meituan_trd',selectDataset(){}});assert.match(html,/重试文档/);assert.match(html,/utility_v1_meituan_trd/);});
check('invalid and unregistered descriptive states never assert successful verification',()=>{
  for(const status of ['INVALID','NOT_REGISTERED']){
    stateOverrides=[{status,datasets:{meituan_trd:{status,reason:'controlled status'}}},'',0,2,'clean'];
    const html=render(A8Comparison,{datasetName:'meituan_trd',selectDataset(){}});stateOverrides=null;
    assert.ok(html.includes(status));assert.ok(html.includes(status==='INVALID'?'描述性证据核验失败':'尚未登记描述性结果'));assert.ok(!html.includes('历史原始结果已核验'));assert.ok(!html.includes('score-mean'));
  }
});
check('partial strict registration preserves method statuses and reasons',()=>{
  resources['/api/evidence/a8']={loading:false,error:'',data:{status:'PARTIAL',datasets:{meituan_trd:{status:'PARTIAL',methods:[{name:'methodA',status:'NOT_APPLICABLE',reason:'controlled scope'},{name:'methodB',status:'INVALID',reason:'controlled missing artifact'}]}}},retry(){}};
  const html=render(StrictA8Status,{datasetName:'meituan_trd'});for(const value of ['部分登记','不适用','登记核验失败','controlled scope','controlled missing artifact'])assert.ok(html.includes(value));
});
console.log(`${count} experiment checks passed; includes 54 real API condition groups. Synthetic missing/failure cases are controlled tests, not evidence.`);
