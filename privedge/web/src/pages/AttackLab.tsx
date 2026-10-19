import { useEffect, useRef, useState } from "react";
import { countText } from "../presentation";
import { decimalText, executionCounts } from "../predictionDisplay";
import { postJSON } from "../api";
import { Chart } from "../components/Chart";
import { Card, Reasons, StateBadge, StateExplanation, TopList, pct } from "../components/common";
import { RunActions, EvidenceDownload } from "../components/RunActions";
import { publicRequest, publicRun } from "../evidenceExport";
import { defaultRequest, parseSeed, requestMatches, sessionKey, transferNormal, useDemoSession, type CompletedRun } from "../demoSession";
import { Topology } from "../components/Topology";
import { TheoryScope } from "../components/TheoryScope";
import type { DatasetInfo, ProgramIdentity, RunRequest, RunResult } from "../types";
import { EventLog, RunControls, useRunner } from "./ColdStart";
import { DEFENCES, SCENE_NOTE, attackSuccessText, attackFraction, scoreValue, attackEvents, rejectionGroups } from "../attackDisplay";
import { SweepSession } from "../sweepSession";

export function AttackLab({ dataset }: { dataset: DatasetInfo }) {
  const store = useDemoSession(), saved = store.sessions[sessionKey(dataset.name, "attack")];
  const [request, setRequest] = useState<RunRequest>(() => saved?.draft ?? defaultRequest(dataset, "hijack"));
  const [seedText, setSeedText] = useState(saved?.seedText ?? String(saved?.draft?.seed ?? ""));
  const seed = parseSeed(seedText);
  const [completed, setCompleted] = useState<CompletedRun | undefined>(saved?.completed);
  const { events, status, error, running, bad, start, reset } = useRunner({}, value => {
    setCompleted(value); store.patch(dataset.name, "attack", {completed: value});
  });
  const result = completed?.result;
  const matching = result && requestMatches(request, result) && !seed.error;
  const [mode, setMode] = useState<"single" | "sweep">(saved?.mode ?? "single");
  const [sweep, setSweep] = useState<RunResult[]>(saved?.sweep?.rows ?? []);
  const [sweeping, setSweeping] = useState(false);
  const [sweepError, setSweepError] = useState(saved?.sweep?.error ?? "");
  const [activeAttack, setActiveAttack] = useState("");
  const [sweepRequest, setSweepRequest] = useState<RunRequest | null>(saved?.sweep?.snapshot ?? null);
  const [sweepIdentity, setSweepIdentity] = useState<ProgramIdentity | null>(saved?.sweep?.identity ?? null);
  const session = useRef(new SweepSession());
  const sweepGeneration = useRef(0);
  useEffect(() => () => {sweepGeneration.current++; session.current.cancel();}, []);
  const sources = dataset.servers.map((s) => s.id).filter((s) => s !== request.target);
  const attackNames = Object.keys(dataset.attacks).filter((a) => a !== "none");
  const defence = DEFENCES[request.attack];

  const stopSweep = () => {
    sweepGeneration.current++;
    session.current.cancel();
    setSweeping(false);
    setActiveAttack("");
  };
  const updateRequest = (next: RunRequest) => {
    reset();
    stopSweep();
    setRequest(next);
    store.patch(dataset.name, "attack", {draft: next});
  };
  const updateSeed = (text: string) => {setSeedText(text); updateRequest({...request, seed: parseSeed(text).value}); store.patch(dataset.name, "attack", {seedText: text});};
  const runSingle = (next: RunRequest = {...request, seed: seed.value}) => {
    if (seed.error) return;
    stopSweep();
    setMode("single");
    store.patch(dataset.name, "attack", {mode: "single"});
    void start(next);
  };
  const replay = (next: RunRequest) => {
    updateRequest(next); setSeedText(String(next.seed));
    store.patch(dataset.name, "attack", {seedText: String(next.seed), mode: "single"});
    stopSweep(); setMode("single"); void start(next);
  };
  const clear = () => {reset(); setCompleted(undefined); store.patch(dataset.name, "attack", {completed: undefined});};
  const normal = store.sessions[sessionKey(dataset.name, "coldstart")]?.completed;
  const carryNormal = () => {
    const next = normal && transferNormal(normal.result, request);
    if (!next) return;
    updateRequest(next); setSeedText(String(next.seed));
    store.patch(dataset.name, "attack", {seedText: String(next.seed)});
  };
  const runSweep = async () => {
    if (seed.error) return;
    stopSweep(); setSweep([]); setSweepError("");
    reset();
    const snapshot = { ...request, seed: seed.value ?? 20260929 };
    setMode("sweep");
    setSweeping(true);
    setSweepRequest(snapshot);
    const token = sweepGeneration.current;
    const identity = await store.captureIdentity();
    if (token !== sweepGeneration.current) return;
    setSweepIdentity(identity);
    let rows: RunResult[] = [];
    const persist = (complete: boolean, failure = "") => store.patch(dataset.name, "attack", {
      mode: "sweep", sweep: {snapshot, rows, total: attackNames.length, complete, error: failure, identity}});
    persist(false);
    void session.current.run(snapshot, attackNames,
      (next, signal) => postJSON<RunResult>("/api/run", next, signal), {
        active: setActiveAttack,
        row: (r) => { rows = [...rows, {...r, request_snapshot: {...snapshot, attack: r.attack, seed: r.seed}}]; setSweep(rows); persist(false); },
        error: (attack, count, reason) => { const failure = `巡检在“${dataset.attacks[attack] ?? attack}”失败：${String(reason)}。已完成 ${count}/${attackNames.length} 项，结果保留。重新巡检会从首项开始。`; setSweepError(failure); persist(false, failure); },
        finish: () => {setSweeping(false); if (rows.length === attackNames.length) persist(true);},
      });
  };

  return <div className="page attack-page">
    <Card title="攻击配置" headingLevel={1} extra={<div className="row">
      <button className="primary" disabled={running || sweeping || !!seed.error} onClick={() => runSingle()}>{running ? "执行中…" : "发起攻击"}</button>
      <button disabled={sweeping || running || !!seed.error} onClick={() => void runSweep()}>{sweeping ? `巡检中 ${sweep.length}/${attackNames.length}…` : "一键全攻击巡检"}</button>
    </div>}>
      <details className="help-details"><summary>运行说明</summary><p className="muted small">单次比较中的无防御基线与 PrivEdge 使用同一请求；默认参数与正常页不同，可先带入正常结果。切页停止后续客户端请求，不保证中止已开始的后端计算。</p></details>
      <div className="row"><button disabled={!normal || running || sweeping} onClick={carryNormal}>带入上次正常运行参数和种子</button><span className="muted small">{normal ? `来源：${normal.result.run_id}；只填参，不自动运行。` : "当前数据集尚无已完成的正常运行。"}</span></div>
      <RunControls dataset={dataset} request={request} setRequest={updateRequest} disabled={running || sweeping} prediction seedText={seedText} setSeedText={updateSeed} seedError={seed.error} />
      <fieldset className="attack-controls" disabled={running || sweeping}>
        <label>攻击类型<select value={request.attack} onChange={e => updateRequest({ ...request, attack: e.target.value })}>
          {Object.entries(dataset.attacks).map(([k, v]) => <option key={k} value={k}>{k === "none" ? "无攻击对照" : v}</option>)}
        </select></label>
        <label>请求攻击来源数<select value={request.attackers} onChange={e => updateRequest({ ...request, attackers: Number(e.target.value) })}>
          {[1, 2, 3].map(v => <option key={v} value={v}>{v}</option>)}
        </select></label>
        {request.attack === "mga" && <label>伪造用户比例 β<select value={request.beta} onChange={e => updateRequest({ ...request, beta: Number(e.target.value) })}>
          {[0.02, 0.05, 0.1, 0.2].map(v => <option key={v} value={v}>{v * 100}%</option>)}
        </select></label>}
      </fieldset>
      <details className="help-details"><summary>巡检参数与范围</summary><p className="muted small">完整巡检依次运行 {attackNames.length} 种攻击；种子 {seed.error ? "输入无效" : seed.value ?? 20260929}（留空时明确使用 20260929），MGA β={pct(request.beta)}。请求攻击来源数与实际来源可能不同，以结果为准；β仅伪造用户攻击适用。</p></details>
      <div className="attack-defence">
        <p><strong>对应防线：</strong>{defence?.brief ?? "未提供"}</p>
        {request.attackers >= 2 && ["compromised", "hijack", "demote"].includes(request.attack) && <p className="warn-text">请求被攻破来源数 f ≥ t=2，定理 1 的注入免疫保证不再适用。</p>}
        <details key={request.attack}><summary>查看防线依据</summary><p>{defence?.detail ?? "未提供"}</p>{defence?.bounded && <p>有界影响保证要求留一诚实多数：n≥3 且 f &lt; (n−1)/2；n、f 均按通过准入的不同来源计。</p>}</details>
        <TheoryScope />
      </div>
      {error && mode === "single" && <p className="error" role="alert">运行未完成：{error} <button disabled={running || sweeping || !!seed.error} onClick={() => runSingle()}>重试攻击</button></p>}
      <div className="row"><button disabled={running || sweeping || !completed} onClick={() => {setMode("single"); store.patch(dataset.name, "attack", {mode: "single"});}}>查看上次单次结果</button><button disabled={running || sweeping || !sweepRequest} onClick={() => {setMode("sweep"); store.patch(dataset.name, "attack", {mode: "sweep"});}}>查看上次巡检</button></div>
    </Card>

    {mode === "single" ? <>
      {completed && <RunActions completed={completed} draft={request} busy={running || sweeping} replay={replay} clear={clear} />}
      {result && <AttackSummary result={result} datasetTitle={dataset.title} />}
      <div className="grid-2 process-grid">
        <Card title="攻击流水"><Topology showNotes={false} target={request.target} sources={sources} status={status} bad={bad} state={matching && !running ? result?.decision.state : undefined} /></Card>
        <Card className="attack-log" title="执行日志"><EventLog events={events.length || running ? events : matching ? result.events ?? [] : []} conciseDecision /></Card>
      </div>
      {result && <AttackResults result={result} />}
    </> : <>
      {sweepRequest && <section className="saved-result-note"><p>巡检结果绑定下方参数快照，当前控制区改参不会改写已有行。{!sweeping && sweep.length < attackNames.length && " 上次巡检未完整完成，返回页面不会自动续跑。"}</p>
        <div className="row"><EvidenceDownload kind="sweep" id={dataset.name} identity={sweepIdentity} payload={() => ({request_snapshot: publicRequest(sweepRequest), completed: !sweeping && sweep.length === attackNames.length, expected_total: attackNames.length, rows: sweep.map(publicRun), error: sweepError || null})} />
          <button disabled={sweeping || running} onClick={() => {stopSweep(); setSweep([]); setSweepRequest(null); setSweepError(""); store.patch(dataset.name, "attack", {sweep: undefined});}}>清空本页巡检结果</button></div></section>}
      <SweepResults rows={sweep} snapshot={sweepRequest} datasetTitle={dataset.title} total={attackNames.length}
        running={sweeping} activeName={dataset.attacks[activeAttack] ?? activeAttack} error={sweepError} retry={() => void runSweep()} />
    </>}
  </div>;
}

export function AttackSummary({ result: r, datasetTitle }: { result: RunResult; datasetTitle: string }) {
  const request = r.request_snapshot;
  return <section className="run-summary" role="status" aria-label="本次攻击结论">
    <div className="row"><strong>本次现场示例</strong><StateBadge state={r.decision.state} /><span>{r.attack_name} · {r.decision.top_k_named.length} 个输出类别</span></div>
    <p>{datasetTitle}（{r.dataset}） / 目标 {r.target}；ε={r.epsilon}，Top-m={r.top_m}，每源采样上限 {countText(request?.users)} 人。</p>
    <p className="small">种子 {r.seed}；窗口 {r.window}；运行 <code>{r.run_id}</code>。请求攻击来源数 {countText(request?.attackers)}{r.attack === "mga" && <>；β={pct(request?.beta)}</>}。</p>
    <p className="small">返回的攻击来源：{r.attackers.join("、") || "无"}。具体攻击动作见执行日志。</p>
    <details className="help-details"><summary>现场结果的解释范围</summary><p className="muted small">{SCENE_NOTE}</p></details>
  </section>;
}

const POISONING_ATTACKS = new Set(["mga", "compromised", "hijack", "demote", "negative"]);
const PROTOCOL_ATTACKS = new Set(["tamper", "replay", "impostor", "equivocation"]);

function RecallRows({ result: r }: { result: RunResult }) {
  const base = r.evaluation?.baseline, pe = r.evaluation?.privedge;
  return <table className="table"><thead><tr><th>指标</th><th className="numeric">无防御基线</th><th className="numeric">PrivEdge</th></tr></thead>
    <tbody>
      <tr><th scope="row">Recall@10</th><td className="numeric">{decimalText(scoreValue(base, "recall"))}</td><td className="numeric">{decimalText(scoreValue(pe, "recall"))}</td></tr>
      <tr><th scope="row">NDCG@10</th><td className="numeric">{decimalText(scoreValue(base, "ndcg"))}</td><td className="numeric">{decimalText(scoreValue(pe, "ndcg"))}</td></tr>
    </tbody></table>;
}

function ProtocolComparison({ result: r }: { result: RunResult }) {
  const events = r.events ?? [];
  const admits = events.filter(event => event.type === "admit").length;
  const rejects = events.filter(event => event.type === "reject").length;
  const groups = rejectionGroups(events);
  const base = r.evaluation?.baseline, pe = r.evaluation?.privedge;
  const intercepted = rejects > 0 ? 1 : 0;
  const compare = {
    legend: { data: ["无防御基线", "PrivEdge"], textStyle: { color: "#cbd5e1" } }, tooltip: {},
    xAxis: { type: "category", data: ["攻击摘要拦截率", "Recall@10", "NDCG@10"] },
    yAxis: { type: "value", min: 0, max: 1 },
    series: [
      { name: "无防御基线", type: "bar", itemStyle: { color: "#ef4444" }, data: [0, scoreValue(base, "recall"), scoreValue(base, "ndcg")] },
      { name: "PrivEdge", type: "bar", itemStyle: { color: "#10b981" }, data: [intercepted, scoreValue(pe, "recall"), scoreValue(pe, "ndcg")] },
    ], grid: { left: 42, right: 20, top: 44, bottom: 36 },
  };
  return <Card title="本次效果对比（准入与完整性）">
    <Chart option={compare} height={280} title="拦截与离线评价" description="攻击摘要拦截率：被改写的摘要中被拒收的比例；Recall@10、NDCG@10 越高越好。" />
    <table className="table"><thead><tr><th>项</th><th className="numeric">无防御基线</th><th className="numeric">PrivEdge</th></tr></thead>
      <tbody>
        <tr><th scope="row">被攻击摘要</th><td className="numeric">1 / 1</td><td className="numeric">1 / 1</td></tr>
        <tr><th scope="row">其中被拒收</th><td className="numeric">0</td><td className="numeric">{Math.min(rejects, 1)}</td></tr>
        <tr><th scope="row">进入融合的摘要</th><td className="numeric">{admits + rejects}</td><td className="numeric">{admits}</td></tr>
        <tr><th scope="row">拒收原因</th><td>—</td><td>{groups.length ? groups.map(group => `${group.code} ×${group.count}`).join("、") : "无"}</td></tr>
      </tbody></table>
    <p className="muted small">本场景不注入目标品类，AS 不适用。基线不验签，被改写的摘要会进入融合。</p>
  </Card>;
}

function LedgerComparison({ result: r }: { result: RunResult }) {
  const attack = (r.events ?? []).find(event => event.type === "attack");
  const detail = String(attack?.detail ?? "未被账本拒绝");
  const chain = r.audit?.ledger_chain_ok;
  return <Card title="本次效果对比（账本防护）">
    <table className="table"><tbody>
      <tr><th scope="row">攻击条目登记</th><td>{detail}</td></tr>
      <tr><th scope="row">登记被拒</th><td className="numeric">1 / 1</td></tr>
      <tr><th scope="row">账本链完整性</th><td>{chain == null ? "未提供" : chain ? "完整" : "断裂"}</td></tr>
    </tbody></table>
    <p className="muted small">攻击在账本登记阶段被拒，未进入准入与融合；本场景不注入目标品类，AS 不适用。</p>
    <RecallRows result={r} />
  </Card>;
}

export function AttackResults({ result: r }: { result: RunResult }) {
  const keys = ["attack_success", "recall", "ndcg"] as const;
  const labels = ["攻击目标入榜比例（AS）", "Recall@10", "NDCG@10"];
  const base = r.evaluation?.baseline, pe = r.evaluation?.privedge;
  const baseRatio = attackFraction(base?.attack_success, r, r.baseline.top_k_named);
  const peRatio = attackFraction(pe?.attack_success, r, r.decision.top_k_named);
  const compare = {
    legend: { data: ["无防御基线", "PrivEdge"], textStyle: { color: "#cbd5e1" } }, tooltip: {},
    xAxis: { type: "category", data: labels }, yAxis: { type: "value", min: 0, max: 1 },
    series: [
      { name: "无防御基线", type: "bar", itemStyle: { color: "#ef4444" }, data: keys.map(k => scoreValue(base, k)) },
      { name: "PrivEdge", type: "bar", itemStyle: { color: "#10b981" }, data: keys.map(k => scoreValue(pe, k)) },
    ], grid: { left: 42, right: 20, top: 44, bottom: 36 },
  };
  const metricText = (score: typeof base, key: typeof keys[number], baseline: boolean) => key === "attack_success"
    ? (baseline ? baseRatio : peRatio).text : decimalText(scoreValue(score, key));
  const missingAttack = base?.attack_success == null || pe?.attack_success == null;
  const poisoning = POISONING_ATTACKS.has(r.attack);
  return <>
    <DefenceResults result={r} />
    {poisoning ? <Card title="本次效果对比（离线评价）">
      <Chart option={compare} height={300} title="本次攻击比较" description="攻击目标入榜比例（AS）越低越好；Recall@10、NDCG@10 越高越好。数值范围为 0–1。" dataTable={
        <div className="table-scroll" tabIndex={0} role="region" aria-label="攻击比较数据"><table className="table"><thead><tr><th>指标</th><th className="numeric">无防御基线</th><th className="numeric">PrivEdge</th></tr></thead>
          <tbody>{keys.map((key, i) => <tr key={key}><th scope="row">{labels[i]}</th><td className="numeric">{metricText(base, key, true)}</td><td className="numeric">{metricText(pe, key, false)}</td></tr>)}</tbody>
        </table></div>
      } />
      <details className="help-details"><summary>AS 指标说明</summary><p className="muted small">AS 的分母为本次指定的 {baseRatio.total} 个不同目标类别；分子为实际返回榜单中的目标类别数。它不是多次攻击成功的概率，百分比保留接口原值。空输出与部分候选均按实际返回内容列示。</p></details>
      {(baseRatio.mismatch || peRatio.mismatch) && <p role="alert" className="warn-text">指标与榜单需核查：{baseRatio.mismatch && `基线榜单 ${baseRatio.hits}/${baseRatio.total}、接口 AS=${base?.attack_success}；`}{peRatio.mismatch && `PrivEdge 榜单 ${peRatio.hits}/${peRatio.total}、接口 AS=${pe?.attack_success}。`}未改写原始指标。</p>}
      {missingAttack && <p className="empty-state">攻击成功率：基线 {attackSuccessText(base?.attack_success, r)}；PrivEdge {attackSuccessText(pe?.attack_success, r)}。{r.attack_targets.length ? "已定义攻击目标；空输出或缺失返回值时不补零，也不标为协议类不适用。" : "本次未定义注入目标指标。"}</p>}
      <p className="muted small">攻击目标：{r.attack_targets.map(t => t.name).join("、") || "本次没有注入目标；协议场景请查看拒收原因，目标入榜指标不适用"}。</p>
    </Card> : PROTOCOL_ATTACKS.has(r.attack) ? <ProtocolComparison result={r} /> : <LedgerComparison result={r} />}
    <div className="grid-2 attack-rankings">
      <Card title="无防御基线榜单"><TopList items={r.baseline.top_k_named} showSupport={false} /></Card>
      <Card title={<>PrivEdge 榜单 <StateBadge state={r.decision.state} /></>}>
        <TopList items={r.decision.top_k_named} state={r.decision.state} />
        <div className="attack-reasons"><h3>检查原因</h3>{r.decision.reasons.length ? <Reasons reasons={r.decision.reasons} /> : <p className="muted">本次未返回降级或拒答原因。</p>}
          {!!r.decision.alerts?.length && <><h3>附加告警</h3><Reasons reasons={[]} alerts={r.decision.alerts} /></>}
        </div>
      </Card>
    </div>
  </>;
}

export function DefenceResults({result: r}: {result: RunResult}) {
  const counts = executionCounts(r.events ?? [], r.sources.map(source => source.source));
  const rejects = (r.events ?? []).filter(event => event.type === "reject");
  const removed = r.sources.reduce((sum, source) => sum + (Number.isFinite(source.removed_reports) ? source.removed_reports : 0), 0);
  return <Card title="三层处理结果">
    <ol className="defence-results">
      <li><h3>发布端：报告筛查</h3><p>{r.sources.length ? `过滤剔除 ${removed} 条报告。` : "未提供来源明细。"}剔除数不等于已确认的伪造报告数；模拟注入量见来源记录。</p></li>
      <li><h3>网关：协议准入</h3><p>已知来源接受 {counts.accepted} 个、拒收 {counts.rejected} 个；共记录 {rejects.length} 条拒收事件。事件可能重复或来自未知主体，不能等同于不同来源数。</p><InterceptionRecords result={r} /></li>
      <li><h3>融合：整次请求结论</h3><StateBadge state={r.decision.state} /><span> · 实际返回 {r.decision.top_k_named.length} 个类别</span><StateExplanation state={r.decision.state} count={r.decision.top_k_named.length} /><Reasons reasons={r.decision.reasons} alerts={r.decision.alerts} /></li>
    </ol>
    <details className="help-details"><summary>三层防线的区别</summary><p className="muted small">合法签名的数值投毒主要看鲁棒融合的影响；未重签篡改主要看签名拒收。单份摘要拒收、发布端过滤和整次拒答是不同事件，均不能单独证明预测准确。</p></details>
  </Card>;
}

function sweepFamily(attack: string) {
  return POISONING_ATTACKS.has(attack) ? "投毒" : PROTOCOL_ATTACKS.has(attack) ? "协议" : attack === "budget_burn" ? "账本" : "其他";
}

function sweepComparison(row: RunResult) {
  const base = row.evaluation?.baseline, pe = row.evaluation?.privedge;
  if (POISONING_ATTACKS.has(row.attack)) {
    const b = attackFraction(base?.attack_success, row, row.baseline.top_k_named).text;
    const p = attackFraction(pe?.attack_success, row, row.decision.top_k_named).text;
    return `AS ${b} → ${p}；NDCG ${decimalText(scoreValue(base, "ndcg"))} → ${decimalText(scoreValue(pe, "ndcg"))}`;
  }
  const events = row.events ?? [];
  const detail = String(events.find(event => event.type === "attack")?.detail ?? "");
  if (row.attack === "budget_burn") {
    return /被账本拒绝/.test(detail) ? "非法登记 0/1 → 1/1 被拒" : `未触发：${detail || "无事件"}`;
  }
  if (/还没有旧窗口|预算不足/.test(detail)) return `未触发：${detail}`;
  const rejects = events.filter(event => event.type === "reject").length;
  return `拦截 0/1 → ${rejects > 0 ? 1 : 0}/1`;
}

export function SweepResults({ rows, snapshot, datasetTitle, total, running, activeName, error, retry }: {
  rows: RunResult[]; snapshot: RunRequest | null; datasetTitle: string; total: number; running: boolean; activeName: string; error: string; retry: () => void;
}) {
  return <Card title="完整攻击巡检" extra={<span className="muted" role="status">{running ? `正在执行：${activeName || "准备首项"}` : error || rows.length < total ? "巡检未完成" : "巡检完成"} · {rows.length}/{total}</span>}>
    {snapshot && <p className="muted small">{datasetTitle}（{snapshot.dataset}） / 目标 {snapshot.target}；ε={snapshot.epsilon}，Top-m={snapshot.top_m}，每源采样上限 {countText(snapshot.users)} 人；请求攻击来源数 {snapshot.attackers}，MGA β={pct(snapshot.beta)}，种子 {snapshot.seed}。</p>}
    <details className="help-details"><summary>现场结果的解释范围</summary><p className="muted small">{SCENE_NOTE}</p></details>
    {error && <p className="error" role="alert">{error} <button disabled={running} onClick={retry}>重新巡检</button></p>}
    {!rows.length && !error && <p className="empty-state">{running ? "正在等待首项结果；每项执行完成后追加一行。" : "暂无已完成结果；开始巡检后逐项追加。"}</p>}
    <div className="table-scroll sweep-table" tabIndex={0} role="region" aria-label="完整攻击巡检表">
      <table className="table"><thead><tr><th>攻击与运行</th><th>类型</th><th>拦截记录</th><th>检查结论与原因</th><th>前后对比</th><th>对应防线</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.run_id}>
          <td>{row.attack_name}<small className="sweep-meta">{row.window}<br /><code>{row.run_id}</code></small></td>
          <td>{sweepFamily(row.attack)}</td>
          <td><InterceptionRecords result={row} /></td>
          <td><StateBadge state={row.decision.state} /><details className="sweep-reasons"><summary>查看检查原因</summary><Reasons reasons={row.decision.reasons} alerts={row.decision.alerts} /></details></td>
          <td>{sweepComparison(row)}</td>
          <td>{DEFENCES[row.attack]?.brief ?? "未提供"}<details><summary>查看依据</summary><p>{DEFENCES[row.attack]?.detail}</p></details></td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="muted small">投毒类看 AS/NDCG；协议类看被改写、重放或冒充的摘要是否被拦下；账本类看非法登记是否被拒。每行一次运行，不是多次统计。</p>
  </Card>;
}

export function InterceptionRecords({ result }: { result: RunResult }) {
  const groups = rejectionGroups(result.events);
  const messages = attackEvents(result.events);
  const attackMessages = messages.filter(e => e.type === "attack");
  return <>
    {groups.length ? groups.map(g => <p className="intercept" key={`${g.code}:${g.reason}`}>{g.reason}<code>{g.code}{g.count > 1 ? ` × ${g.count}` : ""}</code></p>) : <span className="muted">无网关拒收记录；数值防线与输出影响见本次结果，不能据此判断攻击未执行。</span>}
    {["budget_burn", "replay", "equivocation"].includes(result.attack) && attackMessages.map((e, i) => <p className="intercept" key={i}>{String(e.detail ?? "未提供事件说明")}</p>)}
    {!!messages.length && <details><summary>查看完整攻击与拒收事件（{messages.length}）</summary><ol className="sweep-event-list">{messages.map((e, i) => <li key={i}>{e.t_ms.toFixed(0)} ms · {String(e.source ?? e.source_id ?? "")}<br />{String(e.detail ?? e.reason ?? "未提供")} {e.code && <code>{e.code}</code>}</li>)}</ol></details>}
  </>;
}
