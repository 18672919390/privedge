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
const {topologyLayout,boxesOverlap}=load(path.join(src,'topologyLayout.ts'));
const {executionCounts,decimalText}=load(path.join(src,'predictionDisplay.ts'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {ResultPanel,ExecutionStages,RunSummary}=load(path.join(src,'pages/ColdStart.tsx'));
let passed=0;function check(name,fn){fn();passed++;console.log('PASS',name);}
const sets=[Array.from({length:11},(_,i)=>`商圈${i}`),['MG@W2017','MG@W2018','RJ@W2017','RJ@W2018','SP@W2017','SP@W2018'],['Istanbul@2013','Istanbul@2018','Jakarta@2013','Kuwait City@2018','New York@2013','Petaling Jaya@2013','Petaling Jaya@2018']];
for(const ids of sets)check(`All ${ids.length} target choices: circular positions and clear labels`,()=>{
  for(const target of ids){
    const sources=ids.filter(x=>x!==target),l=topologyLayout(target,sources);
    assert.ok(l.size>=640);
    const labels=[...l.nodes.map(n=>n.label),l.targetLabel];
    const circles=[...l.nodes.map(n=>({x:n.x-23,y:n.y-23,width:46,height:46})),{x:-39,y:-39,width:78,height:78}];
    l.nodes.forEach(n=>{assert.ok(Math.abs(Math.hypot(n.x,n.y)-l.radius)<1e-8);assert.equal(n.lines.join(''),n.id);});
    labels.forEach((a,i)=>{labels.forEach((b,j)=>{if(j>i)assert.ok(!boxesOverlap(a,b));});circles.forEach(b=>assert.ok(!boxesOverlap(a,b)));assert.ok(a.x>=-l.extent&&a.y>=-l.extent&&a.x+a.width<=l.extent&&a.y+a.height<=l.extent);});
  }
});
check('Empty and single-source topology terminates',()=>{assert.equal(topologyLayout('目标',[]).nodes.length,0);assert.equal(topologyLayout('目标',['A']).nodes.length,1);});
check('Long unbroken labels remain complete',()=>{const name='超长区域名称'.repeat(12);const l=topologyLayout(name,[name+'2','b']);assert.equal(l.nodes[0].lines.join(''),name+'2');});
const events=[{type:'collect',source:'a'},{type:'collect',source:'a'},{type:'collect',source:'unknown'},{type:'release',source:'a'},{type:'ledger',source:'a'},{type:'ledger',source:'a'},{type:'reject',source_id:'a'},{type:'admit',source:'a'},{type:'admit',source:'b'}];
check('Stage counts deduplicate, ignore unknown sources and preserve refusal',()=>{const c=executionCounts(events,['a','b']);assert.equal(c.collected,1);assert.equal(c.ledger,1);assert.equal(c.accepted,1);assert.equal(c.rejected,1);assert.equal(c.decision,false);});
check('Decision event and full response are distinct',()=>{
 const render=complete=>renderToStaticMarkup(React.createElement(ExecutionStages,{events:[{type:'decision'}],sources:['a'],complete,running:!complete,error:''}));
 assert.match(render(false),/已形成结论/);assert.match(render(true),/结果已返回/);
});
check('Missing metrics are not zero',()=>{assert.equal(decimalText(null),'未提供');assert.equal(decimalText(undefined),'未提供');assert.equal(decimalText(0),'0.000');});
const fixture={dataset:'test',target:'A',epsilon:2,top_m:40,seed:42,run_id:'test-only-42',window:'TEST',attack:'none',attack_name:'无攻击',elapsed_ms:0,request_snapshot:{users:5000},decision:{state:'REFUSED',method:'test',agreement:0,reasons:[{code:'TEST_REFUSAL',reason:'受控测试原因'}],alerts:[{code:'TEST_ALERT',reason:'受控测试告警'}],top_k_named:[]},evaluation:{privedge:{recall:0,ndcg:null},note:'测试专用'},sources:[],audit:{request_id:'test',record_hash:'abc',ledger_head:'def',ledger_chain_ok:true}};
check('Refused empty output separates reason, alert and offline zero',()=>{const s=renderToStaticMarkup(React.createElement(ResultPanel,{result:fixture}));for(const t of ['降级／拒答原因','附加告警','受控测试原因','受控测试告警','空输出的离线评分','未提供','0%'])assert.ok(s.includes(t),t);});
check('All states keep full long category names',()=>{for(const state of ['NORMAL','DEGRADED','REFUSED']){const name='arts_and_craftmanship_'.repeat(12);const r={...fixture,decision:{...fixture.decision,state,top_k_named:[{category:1,name,support:0}]}};const s=renderToStaticMarkup(React.createElement(ResultPanel,{result:r}));assert.ok(s.includes(name));assert.ok(s.includes(state));}});
check('Compact summary uses completed result and omits duplicate reasons',()=>{const s=renderToStaticMarkup(React.createElement(RunSummary,{result:fixture,compact:true}));for(const t of ['test-only-42','TEST','42','5,000','名用户上限'])assert.ok(s.includes(t),t);assert.ok(!s.includes('受控测试原因'));});
console.log(`${passed} prediction checks passed; controlled fixtures, not business evidence.`);
