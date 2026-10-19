// Engineering checks with controlled fixtures. No statistical experiment or server is started.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'privedge/web/package.json'));
const ts=require('typescript'), React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const src=path.join(root,'privedge/web/src');
function loader(mocks={}) {
 const cache=new Map();
 return function load(file) {
  if(cache.has(file))return cache.get(file);
  const exports={};cache.set(file,exports);
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{exports,AbortController,setTimeout,clearTimeout,console,require:n=>{
   if(mocks[n])return mocks[n];if(n.endsWith('.css'))return {};
   if(!n.startsWith('.'))return require(n);
   const p=path.resolve(path.dirname(file),n);if(mocks[p])return mocks[p];
   return load(fs.existsSync(p+'.ts')?p+'.ts':p+'.tsx');
  }},{filename:file});return exports;
 };
}
const load=loader();
const {parseSeed,resolvedRequest,requestMatches,transferNormal,sessionKey}=load(path.join(src,'demoSession.tsx'));
const {attackFraction}=load(path.join(src,'attackDisplay.ts'));
const {publicRun,publicDrill,publicA8,publicIdentity,evidenceEnvelope}=load(path.join(src,'evidenceExport.ts'));
const {RunActions}=load(path.join(src,'components/RunActions.tsx'));
const {StateExplanation}=load(path.join(src,'components/common.tsx'));
const request={dataset:'test',target:'A',epsilon:1,top_m:20,users:5000,attack:'none',attackers:1,beta:.1,seed:null};
const identity={release_id:'controlled',application_version:'0.0.test',source_fingerprint_sha256:'a'.repeat(64),fingerprint_file_count:2,fingerprint_scope:'controlled fixture',data_sha256:{'meituan_trd/domain.json':'b'.repeat(64)}};
const fixture={...request,seed:42,run_id:'controlled-fixture',window:'TEST',attackers:[],attack_name:'无攻击',attack_targets:[{category:1,name:'one'},{category:2,name:'two'},{category:3,name:'three'}],request_snapshot:request,
 decision:{state:'REFUSED',method:'controlled',agreement:0,reasons:[{code:'INSUFFICIENT_CANDIDATES',reason:'候选不足'}],alerts:[],top_k_named:[{category:1,name:'one'}]},
 baseline:{method:'controlled',top_k_named:[]},evaluation:{note:'controlled',baseline:{recall:0,ndcg:0,attack_success:0},privedge:{recall:0,ndcg:0,attack_success:1/3},truth_top10:[]},sources:[],events:[],audit:{request_id:'test',ledger_head:'head',record_hash:'hash',ledger_chain_ok:true},elapsed_ms:1};
const checks=[];
async function check(name,fn){try{await fn();checks.push({name,passed:true});console.log('PASS',name);}catch(error){checks.push({name,passed:false,error:String(error)});console.error('FAIL',name,error);}}
await check('Seed distinguishes blank, zero and exact integer limits',()=>{
 assert.equal(parseSeed('').value,null);assert.equal(parseSeed('  ').value,null);assert.equal(parseSeed('0').value,0);assert.equal(parseSeed('9007199254740991').value,9007199254740991);
 for(const invalid of ['-1','1.2','NaN','Infinity','1e3','9007199254740992','abc'])assert.ok(parseSeed(invalid).error,invalid);
});
await check('Replay resolves actual seed and original users instead of edited draft',()=>{
 const replay=resolvedRequest(fixture);assert.equal(replay.seed,42);assert.equal(replay.users,5000);assert.equal(request.seed,null);
 assert.equal(requestMatches({...request,seed:42},fixture),true);assert.equal(requestMatches({...request,epsilon:2},fixture),false);assert.equal(resolvedRequest({...fixture,request_snapshot:undefined}),null);
});
await check('Transfer carries matching normal conditions while retaining chosen attack',()=>{
 const next=transferNormal(fixture,{...request,attack:'tamper',epsilon:4,beta:.2,attackers:2});
 assert.equal(next.seed,42);assert.equal(next.epsilon,1);assert.equal(next.attack,'tamper');assert.equal(next.beta,.2);assert.equal(next.attackers,2);
 assert.equal(transferNormal(fixture,{...request,dataset:'other'}),null);assert.equal(transferNormal({...fixture,request_snapshot:{...request,attack:'hijack'}},request),null);
 assert.notEqual(sessionKey('A','attack'),sessionKey('A','coldstart'));assert.notEqual(sessionKey('A','attack'),sessionKey('B','attack'));
});
await check('AS denominator deduplicates targets and numerator deduplicates returned partial candidates',()=>{
 const result=attackFraction(1/3,{attack_targets:[...fixture.attack_targets,fixture.attack_targets[0]]},[{category:1},{category:1},{category:9}]);
 assert.equal(result.hits,1);assert.equal(result.total,3);assert.equal(result.text,'1/3（33.3%）');assert.equal(result.mismatch,false);
 assert.equal(attackFraction(0,fixture,fixture.decision.top_k_named).mismatch,true);
});
await check('AS consistency accepts four-decimal rounding without hiding a real discrepancy',()=>{
 const one=[{category:1}],two=[{category:1},{category:2}];
 assert.equal(attackFraction(.3333,fixture,one).mismatch,false);
 assert.equal(attackFraction(.6667,fixture,two).mismatch,false);
 assert.equal(attackFraction(1/3,fixture,one).mismatch,false);
 assert.equal(attackFraction(.3332,fixture,one).mismatch,true);
 assert.equal(attackFraction(.6666,fixture,two).mismatch,true);
 assert.equal(attackFraction(0,fixture,one).mismatch,true);
 assert.equal(attackFraction(.3333,fixture,one).text,'1/3（33.3%）');
});
await check('Protocol N/A, missing metric, zero and refused partial output stay distinct',()=>{
 assert.equal(attackFraction(null,{attack_targets:[]},[]).text,'不适用');assert.equal(attackFraction(null,fixture,[]).text,'未提供');assert.equal(attackFraction(0,fixture,[]).text,'0/3（0.0%）');
 const html=renderToStaticMarkup(React.createElement(StateExplanation,{state:'REFUSED',count:1}));assert.match(html,/保留 1 个部分候选/);assert.ok(!html.includes('停止输出'));
});
await check('Retained output explicitly separates draft and running request from completed snapshot',()=>{
 const html=renderToStaticMarkup(React.createElement(RunActions,{completed:{result:fixture,identity:null,savedAt:'TEST'},draft:{...request,epsilon:2},busy:true,replay(){},clear(){}}));
 for(const text of ['当前参数尚未运行','新请求执行中','controlled-fixture','未获得本次程序版本','清空本页不清账本'])assert.ok(html.includes(text),text);
});
await check('Single export preserves exact nulls and partial refusal while stripping nested new secret fields',()=>{
 const secret='CONTROLLED_SECRET_MUST_NOT_EXPORT';
 const value={...fixture,private_key:secret,request_snapshot:{...request,password:secret},decision:{...fixture.decision,private_key:secret,reasons:[{code:'X',reason:'test',token:secret}]},sources:[{source:'B',users:3,fake_users:1,removed_reports:2,bad:true,private_key:secret}],events:[{type:'start',t_ms:0,seed:42,private_key:secret}],evaluation:{...fixture.evaluation,privedge:{recall:0,ndcg:null,attack_success:null,secret}}};
 const clean=publicRun(value), text=JSON.stringify(clean);assert.ok(!text.includes(secret));assert.equal(clean.decision.top_k_named.length,1);assert.equal(clean.evaluation.privedge.ndcg,null);assert.equal(clean.evaluation.privedge.attack_success,null);assert.equal(clean.seed,42);
 assert.equal(fixture.decision.top_k_named.length,1);
});
await check('Ledger export omits registry, keeps before/after and incomplete verification',()=>{
 const before={total:1,head:'a',chain_ok:true,first_bad:null,latest_window:'W',latest_budget:[],registry:[{private_key:'SECRET'}],entries:[]};
 const payload=publicDrill('test',{edited_seq:0,field:'epsilon',from:1,to:2,chain_ok:false,first_bad:0,decision_state:'REFUSED',decision_reason:'LEDGER_CORRUPTED'},{before,pending:false,error:'controlled read failed'});
 const s=JSON.stringify(payload);assert.ok(!s.includes('SECRET'));assert.ok(!Object.hasOwn(payload.original.before,'registry'));assert.equal(payload.original.after,null);assert.equal(payload.original.error,'controlled read failed');
});
await check('Version export is explicit when unavailable and filters absolute/private paths',()=>{
 const clean=publicIdentity({...identity,private_key:'SECRET',data_sha256:{...identity.data_sha256,'C:\\secret':'b'.repeat(64),'meituan_trd/password':'b'.repeat(64)}});
 assert.equal(Object.keys(clean.data_sha256).length,1);assert.ok(!JSON.stringify(clean).includes('SECRET'));assert.equal(publicIdentity(null).status,'UNAVAILABLE');
 const envelope=evidenceEnvelope('single',publicRun(fixture),null,'controlled-time');assert.equal(envelope.exported_at,'controlled-time');assert.match(envelope.scope_note,/不是包签名/);
});
await check('Historical export selects one condition, preserves precision/limits and never claims strict READY',()=>{
 const cell={method:'m',epsilon:1,scenario:'clean',top_m:20,sample_count:5,ndcg:.123456789,ndcg_ci95:[.1,.2],attack_success:null,seeds:[101]};
 const data={status:'DESCRIPTIVE',methods:[{id:'m',name:'method',definition:'scope'}],cells:[cell,{...cell,epsilon:2,ndcg:.9}],limitations:['historical limit'],provenance:{historical_preregistration_bound:false,source_results_sha256:'c'.repeat(64),private_key:'SECRET'}};
 const exported=publicA8(data,'test',1,'clean');assert.equal(exported.cells.length,1);assert.equal(exported.cells[0].ndcg,.123456789);assert.equal(exported.cells[0].attack_success,null);assert.equal(exported.provenance.historical_preregistration_bound,false);assert.ok(!JSON.stringify(exported).includes('SECRET'));assert.equal(exported.selection.dataset,'test');assert.ok(!Object.hasOwn(exported,'strict_status'));
});

// Exercise the actual hook with deterministic state/effect storage and fake transport.
function runnerHarness(captureIdentity=async()=>identity) {
 const values=[],effects=[];let index=0;const streams=[],completed=[];
 const hooks={...React,useState(initial){const id=index++;if(!(id in values))values[id]=typeof initial==='function'?initial():initial;return [values[id],next=>{values[id]=typeof next==='function'?next(values[id]):next;}];},
  useRef(initial){const id=index++;if(!(id in values))values[id]={current:initial};return values[id];},
  useCallback(fn){index++;return fn;},useEffect(fn){const id=index++;if(!(id in values)){values[id]=true;effects.push(fn());}},
  useContext(){return {captureIdentity};}};
 const fakeApi={runStream(request,onEvent,onResult,onError){const row={request,onEvent,onResult,onError,cancelled:false};streams.push(row);return ()=>{row.cancelled=true;};}};
 const local=loader({'react':hooks,[path.join(src,'api')]:fakeApi});
 const useRunner=local(path.join(src,'pages/ColdStart.tsx')).useRunner;
 return {streams,completed,render(){index=0;return useRunner({},value=>completed.push(value));},unmount(){effects.forEach(fn=>fn?.());}};
}
await check('Cancel while awaiting version prevents a request from starting later',async()=>{
 let release;const h=runnerHarness(()=>new Promise(resolve=>release=resolve));let runner=h.render();const pending=runner.start(request);runner=h.render();assert.equal(runner.running,true);runner.reset();release(identity);await pending;
 assert.equal(h.streams.length,0);assert.equal(h.render().running,false);assert.equal(h.completed.length,0);
});
await check('Old stream events/results/errors cannot overwrite a newer request or stored completion',async()=>{
 const h=runnerHarness();let runner=h.render();await runner.start(request);runner=h.render();await runner.start({...request,epsilon:2});
 assert.equal(h.streams[0].cancelled,true);
 h.streams[0].onEvent({type:'attack',t_ms:0,source:'OLD'});h.streams[0].onResult({...fixture,run_id:'old'});h.streams[0].onError('late error');
 assert.equal(h.completed.length,0);assert.equal(h.render().events.length,0);assert.equal(h.render().error,'');
 h.streams[1].onEvent({type:'start',t_ms:1});h.streams[1].onResult({...fixture,epsilon:2,run_id:'new'});
 assert.equal(h.completed.length,1);assert.equal(h.completed[0].result.run_id,'new');assert.equal(h.completed[0].result.request_snapshot.epsilon,2);assert.equal(h.completed[0].result.request_snapshot.seed,42);assert.equal(h.completed[0].identity.release_id,'controlled');
 assert.equal(h.render().running,false);assert.equal(h.render().events.length,1);
});
await check('Unmounted hook suppresses late completions and stores no new evidence',async()=>{
 const h=runnerHarness();await h.render().start(request);h.unmount();h.streams[0].onResult(fixture);h.streams[0].onError('late');assert.equal(h.completed.length,0);assert.equal(h.streams[0].cancelled,true);
});
const report={purpose:'Controlled engineering checks, not statistical evidence',passed:checks.filter(c=>c.passed).length,total:checks.length,checks};
console.log(JSON.stringify(report,null,2));
if(process.env.E34_UI_TEST_REPORT)fs.writeFileSync(process.env.E34_UI_TEST_REPORT,JSON.stringify(report,null,2));
if(report.passed!==report.total)process.exitCode=1;
