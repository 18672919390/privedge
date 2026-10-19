import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'privedge/web/package.json'));
const React=require('react'), {renderToStaticMarkup}=require('react-dom/server'), ts=require('typescript');
const cache=new Map();
function load(filename){
 if(cache.has(filename))return cache.get(filename);
 const source=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const exports={};cache.set(filename,exports);
 vm.runInNewContext(source,{exports,require:name=>{
  if(name.endsWith('.css'))return {};
  if(name==='react')return {...React,useLayoutEffect:React.useEffect};
  if(!name.startsWith('.'))return require(name);
  const file=path.resolve(path.dirname(filename),name);return load(fs.existsSync(file+'.ts')?file+'.ts':file+'.tsx');
 }},{filename});return exports;
}
const exports=load(path.join(root,'privedge/web/src/pages/Overview.tsx'));
const checks=[];
function check(name,fn){try{fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:String(e)});}}
const html=renderToStaticMarkup(React.createElement(exports.Overview,{go:()=>{}}));
check('Overview renders without a resource hook or network environment',()=>assert.match(html,/多源摘要可信交换架构/));
check('Trusted exchange remains the main line without restoring old metric panels',()=>{
 assert.match(html,/PrivEdge面向多源 LDP 摘要的抗投毒可信交换/);
 for(const text of ['实验摘要','可证明的保证','开始冷启动预测','进入攻防实验室']) assert.ok(!html.includes(text),text);
});
check('Architecture is explicitly a same-process demonstration with an application example',()=>{
 for(const text of ['同进程中模拟','新区域 Top-10 选品只是应用例子','不代表已部署独立设备上的分布式系统','不等于经营收益已验证','无攻击时不宣称比简单平均更准'])assert.ok(html.includes(text),text);
});
check('Theorem scope includes the corrected majority, valid input and limited conclusion',()=>{
 for(const text of ['n≥3','f &lt; (n−1)/2','每源只准入一份摘要','无上下文融合','摘要须非空','类别不重复','方差正且有限','κ≥1','截尾下限为 0','不保证已有类别名次不变','不保证 Top-k 稳定或预测准确','W=w','相同样本量不能单独推出这一条件'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('(n+1)/2'));
});
check('Protocol starts collapsed and preserves its eleven ordered messages',()=>{
 assert.match(html,/<details class="exchange-protocol">/);
 assert.equal((html.match(/class="protocol-step protocol-/g)||[]).length,11);
 assert.ok(html.indexOf('检查窗口预算，通过后追加哈希链')<html.indexOf('登记成功后，发送签名摘要'));
});
check('Per-summary rejection and three-state meaning remain explicit',()=>{
 assert.match(html,/拒收该摘要并记录原因/);
 assert.match(html,/三态表示检查结论，不代表准确度/);
});
check('Guide presets and feature actions only request navigation, never start work',()=>{
 const destinations=[];const tree=exports.Overview({go:value=>destinations.push(value)});
 const walk=node=>{if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(walk);return;}if(node.type==='button')node.props.onClick();walk(node.props?.children);};
 walk(tree);assert.deepEqual(destinations,['demo-normal','demo-hijack','demo-tamper','ledger','experiments']);
});
console.log(JSON.stringify({checks,passed:checks.filter(c=>c.passed).length,total:checks.length},null,2));
if(checks.some(c=>!c.passed))process.exitCode=1;
