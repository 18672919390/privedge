import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require=createRequire(path.join(root,'privedge/web/package.json'));
const ts=require('typescript'),cache=new Map();
function load(file){
 if(cache.has(file))return cache.get(file);
 const exports={};cache.set(file,exports);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,{exports,AbortController,document:{createElement:()=>({getContext:()=>null})},require:n=>{if(!n.startsWith('.'))return require(n);const p=path.resolve(path.dirname(file),n);return load(fs.existsSync(p+'.ts')?p+'.ts':p+'.tsx');}},{filename:file});return exports;
}
const src=path.join(root,'privedge/web/src');
const {SweepSession}=load(path.join(src,'sweepSession.ts'));
const {attackSuccessText,scoreValue,rejectionGroups,DEFENCES}=load(path.join(src,'attackDisplay.ts'));
const {AttackLab,AttackResults,AttackSummary,SweepResults,InterceptionRecords}=load(path.join(src,'pages/AttackLab.tsx'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
let passed=0;async function check(name,fn){await fn();passed++;console.log('PASS',name);}
const request={dataset:'test',target:'A',epsilon:1,top_m:20,users:5000,attack:'hijack',attackers:1,beta:.1,seed:20260929};
const fixture={...request,run_id:'controlled-fixture-1',window:'TEST',attack_name:'受控测试攻击',attackers:['B'],attack_targets:[{category:1,name:'测试攻击目标'}],request_snapshot:request,decision:{state:'REFUSED',method:'test',agreement:0,reasons:[{code:'TEST_REASON',reason:'受控拒答原因'}],alerts:[],top_k_named:[]},baseline:{method:'test',top_k_named:[]},evaluation:{baseline:{recall:0,ndcg:0,attack_success:0},privedge:{recall:0,ndcg:0,attack_success:null}},events:[],sources:[],audit:{},elapsed_ms:0};
await check('Zero, null and protocol inapplicability remain distinct',()=>{assert.equal(attackSuccessText(0,fixture),'0%');assert.equal(attackSuccessText(null,fixture),'未提供');assert.equal(attackSuccessText(null,{attack_targets:[]}), '不适用');assert.equal(scoreValue({ndcg:null},'ndcg'),null);assert.equal(scoreValue({ndcg:0},'ndcg'),0);assert.equal(scoreValue({ndcg:NaN},'ndcg'),null);});
await check('Empty attacked output is not mislabelled protocol N/A',()=>{const s=render(AttackResults,{result:fixture});assert.match(s,/已定义攻击目标/);assert.match(s,/PrivEdge 未提供/);assert.match(s,/本次检查结论为拒答/);assert.ok(!s.includes('PrivEdge 不适用'));});
await check('Protocol N/A and long category names remain readable',()=>{const name='long_category_name_'.repeat(20);const r={...fixture,attack:'tamper',attack_targets:[],baseline:{top_k_named:[{name,category:1}]}};const s=render(AttackResults,{result:r});assert.ok(s.includes(name));assert.match(s,/本次效果对比（准入与完整性）/);assert.match(s,/攻击摘要拦截率/);assert.match(s,/其中被拒收/);assert.match(s,/AS 不适用/);});
await check('Identical rejection messages preserve count',()=>{const e={type:'reject',code:'EQUIVOCATION',reason:'同源多摘要',t_ms:0};const g=rejectionGroups([e,e,{...e,reason:'另一真实说明'}]);assert.equal(g.length,2);assert.equal(g[0].count,2);assert.equal(g[1].count,1);});
await check('Ledger and replay prerequisite messages survive without gateway rejection',()=>{for(const attack of ['budget_burn','replay','equivocation']){const s=render(InterceptionRecords,{result:{...fixture,attack,events:[{type:'attack',t_ms:2,source:'B',detail:'后端真实说明 TEST_DETAIL'}]}});assert.match(s,/后端真实说明 TEST_DETAIL/);assert.match(s,/无网关拒收记录/);}});
await check('Summary is bound to completed response and request snapshot',()=>{const s=render(AttackSummary,{result:fixture,datasetTitle:'测试数据'});for(const t of ['controlled-fixture-1','TEST','20260929','5,000','返回的攻击来源','登记统计结果请在实验中心查看'])assert.ok(s.includes(t),t);});
await check('Attack page renders the reviewed leave-one-out majority and full scope',()=>{
 const dataset={name:'test',title:'受控数据',servers:['A','B','C','D','E','F','G','H'].map(id=>({id,users:5000})),attacks:{hijack:'权重劫持'}};
 const html=render(AttackLab,{dataset});
 for(const text of ['n≥3','f &lt; (n−1)/2','按通过准入的不同来源计','无上下文融合','每源只准入一份摘要','不保证 Top-k 稳定或预测准确'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('(n+1)/2'));
});
await check('Negative clipping and three-state text do not claim counterfactual equivalence or accuracy',()=>{
 assert.match(DEFENCES.negative.detail,/单源贡献非负/);assert.ok(!DEFENCES.negative.detail.includes('等同于不发布'));
 assert.match(render(AttackSummary,{result:fixture,datasetTitle:'测试数据'}),/不表示预测准确度等级/);
});
const sweepProps={rows:[],snapshot:request,datasetTitle:'测试',total:10,running:true,activeName:'首项',error:'',retry(){}};
await check('Sweep appears before first result and has no invented stream',()=>{const s=render(SweepResults,sweepProps);assert.match(s,/0\/10/);assert.match(s,/等待首项/);assert.ok(!s.includes('执行日志'));});
await check('Partial sweep failure keeps rows, reason, run identity and retry',()=>{const s=render(SweepResults,{...sweepProps,rows:[fixture],running:false,error:'第二项失败；从首项重试'});for(const t of ['1/10','controlled-fixture-1','TEST_REASON','受控拒答原因','重新巡检','第二项失败'])assert.ok(s.includes(t),t);});
const tick=()=>new Promise(r=>setImmediate(r));
function recorder(){const calls=[];return {calls,callbacks:{active:a=>calls.push(['active',a]),row:r=>calls.push(['row',r.attack]),error:(a,n)=>calls.push(['error',a,n]),finish:()=>calls.push(['finish'])}};}
await check('Sweep keeps order, snapshot parameters and fixed seed',async()=>{const session=new SweepSession(),rec=recorder(),sent=[];await session.run(request,['mga','hijack'],async(r)=>{sent.push(r);return {...fixture,attack:r.attack};},rec.callbacks);assert.deepEqual(sent.map(r=>r.attack),['mga','hijack']);assert.ok(sent.every(r=>r.seed===20260929&&r.target==='A'));assert.deepEqual(rec.calls,[['active','mga'],['row','mga'],['active','hijack'],['row','hijack'],['finish']]);});
await check('Failure retains completed rows and stops later attacks',async()=>{const rec=recorder();await new SweepSession().run(request,['mga','hijack','tamper'],async(r)=>{if(r.attack==='hijack')throw Error('controlled');return {...fixture,attack:r.attack};},rec.callbacks);assert.deepEqual(rec.calls,[['active','mga'],['row','mga'],['active','hijack'],['error','hijack',1],['finish']]);});
await check('Cancelled late success cannot append or finish a newer run',async()=>{const session=new SweepSession(),old=recorder(),fresh=recorder();let resolve;const p=session.run(request,['mga','hijack'],()=>new Promise(r=>resolve=r),old.callbacks);await tick();await session.run(request,['tamper'],async()=>({...fixture,attack:'tamper'}),fresh.callbacks);resolve(fixture);await p;assert.deepEqual(old.calls,[['active','mga']]);assert.deepEqual(fresh.calls,[['active','tamper'],['row','tamper'],['finish']]);});
await check('Cancelled late rejection cannot replace current error state',async()=>{const session=new SweepSession(),rec=recorder();let reject;const p=session.run(request,['mga'],()=>new Promise((_,r)=>reject=r),rec.callbacks);session.cancel();reject(Error('late failure'));await p;assert.deepEqual(rec.calls,[['active','mga']]);});
await check('Abort signal is delivered and retry starts from first item',async()=>{const session=new SweepSession(),rec=recorder();let resolve,signal;const p=session.run(request,['mga','hijack'],(_,s)=>{signal=s;return new Promise(r=>resolve=r)},rec.callbacks);session.cancel();assert.equal(signal.aborted,true);resolve(fixture);await p;const sent=[];await session.run(request,['mga','hijack'],async r=>{sent.push(r.attack);return {...fixture,attack:r.attack}},recorder().callbacks);assert.deepEqual(sent,['mga','hijack']);});
console.log(`${passed} attack checks passed; controlled fixtures are not business evidence.`);
