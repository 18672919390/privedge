import { useCallback, useEffect, useRef, useState } from "react";
import { countText, followsLog } from "../presentation";
import { runStream } from "../api";
import { Card, Metric, Reasons, StateBadge, StateExplanation, TopList, pct, HashValue, STATE_TEXT } from "../components/common";
import { RunActions } from "../components/RunActions";
import { defaultRequest, parseSeed, requestMatches, sessionKey, useDemoSession, type CompletedRun } from "../demoSession";
import { executionCounts, decimalText, resultSentence } from "../predictionDisplay";
import { Topology, type NodeStatus } from "../components/Topology";
import type { DatasetInfo, PipelineEvent, RunRequest, RunResult } from "../types";

const EVENT_TEXT: Record<string, (e: PipelineEvent) => string> = {
  start: (e) => `开始：目标 ${e.target}，窗口 ${e.window}，ε=${e.epsilon}，Top-${e.top_m}，每源 ${e.users} 用户`,
  collect: (e) => `${e.source} 在本地完成 OLH 扰动（${e.users} 名用户${Number(e.fake_users) ? `，混入 ${e.fake_users} 个伪造用户` : ""}）`,
  attack: (e) => `⚠ ${e.source}：${e.detail}`,
  release: (e) => `${e.source} 签名发布摘要 ${e.release_id}（${e.items} 项）${Number(e.removed_reports) ? `，发布端过滤剔除 ${e.removed_reports} 条异常报告` : ""}`,
  ledger: (e) => `账本登记 #${e.seq}，链头 ${e.entry_hash}，${e.source} 本窗口已用 ε=${e.spent}`,
  reject: (e) => `✗ 网关拒收 ${e.source_id}：${e.code}（${e.reason}）`,
  admit: (e) => `✓ 网关接受 ${e.source}`,
  decision: (e) => `检查结论：${STATE_TEXT[e.state as keyof typeof STATE_TEXT] ?? e.state}（${e.state}），不表示准确度等级`,
};

export function useRunner(defaults: Partial<RunRequest>, completed?: (value: CompletedRun) => void) {
  const { captureIdentity } = useDemoSession();
  const completion = useRef(completed); completion.current = completed;
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState<Record<string, NodeStatus>>({});
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [bad, setBad] = useState<string[]>([]);
  const stop = useRef<() => void>();
  const generation = useRef(0);

  const reset = useCallback(() => {
    generation.current += 1;
    stop.current?.();
    stop.current = undefined;
    setEvents([]);
    setStatus({});
    setResult(null);
    setError("");
    setBad([]);
    setRunning(false);
  }, []);
  useEffect(() => () => { generation.current += 1; stop.current?.(); }, []);

  const start = async (request: RunRequest, pace = 60) => {
    reset();
    const runGeneration = generation.current;
    setRunning(true);
    const identity = await captureIdentity();
    if (generation.current !== runGeneration) return;
    stop.current = runStream(
      { ...defaults, ...request },
      (event) => {
        if (generation.current !== runGeneration) return;
        setEvents((list) => [...list, event]);
        if (event.type === "start") setBad((event.attackers as string[]) ?? []);
        const source = (event.source ?? event.source_id) as string | undefined;
        if (!source) return;
        const next: Partial<Record<string, NodeStatus>> = {
          collect: "collect", release: "release", admit: "admit", reject: "reject", attack: "attack",
        };
        const s = next[event.type];
        if (s) setStatus((m) => ({ ...m, [source]: m[source] === "reject" ? "reject" : s }));
      },
      (r) => { if (generation.current === runGeneration) {
        const response = { ...r, request_snapshot: { ...defaults, ...request, seed: r.seed } };
        setResult(response); setRunning(false);
        completion.current?.({result: response, identity, savedAt: new Date().toISOString()});
      } },
      (message) => { if (generation.current === runGeneration) { setError(message); setRunning(false); } },
      pace,
    );
  };
  return { events, status, result, error, running, bad, start, reset };
}

export function EventLog({ events, conciseDecision = false }: { events: PipelineEvent[]; conciseDecision?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (!events.length) follow.current = true;
    if (follow.current) box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [events]);
  return (
    <div className={`eventlog ${events.length ? "" : "is-empty"}`} ref={box} tabIndex={0} role="region" aria-label="执行日志，可滚动查看" onScroll={() => { const el = box.current; if (el) follow.current = followsLog(el.scrollHeight, el.scrollTop, el.clientHeight); }}>
      {events.map((e, i) => (
        <div key={i} className={`ev ev-${e.type}`}>
          <span className="ev-t">{e.t_ms.toFixed(0)} ms</span>
          <span>{conciseDecision && e.type === "decision" ? `检查结论：${STATE_TEXT[e.state as keyof typeof STATE_TEXT] ?? e.state}（${e.state}）` : (EVENT_TEXT[e.type] ?? ((x) => x.type))(e)}</span>
        </div>
      ))}
      {!events.length && <p className="muted">运行后，这里逐条显示后端真实执行的每一步。</p>}
    </div>
  );
}

export function RunControls({ dataset, request, setRequest, extra, disabled = false, prediction = false, seedText, setSeedText, seedError = "" }: {
  dataset: DatasetInfo;
  request: RunRequest;
  setRequest: (r: RunRequest) => void;
  extra?: React.ReactNode;
  disabled?: boolean;
  prediction?: boolean;
  seedText?: string; setSeedText?: (text: string) => void; seedError?: string;
}) {
  const set = (patch: Partial<RunRequest>) => setRequest({ ...request, ...patch });
  return (
    <fieldset className="controls" disabled={disabled} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <label>{prediction ? "目标区域" : "新开站区域（目标）"}
        <select value={request.target} onChange={(e) => set({ target: e.target.value })}>
          {dataset.servers.map((s) => <option key={s.id} value={s.id}>{s.id}（{prediction ? "离线样本 " : ""}{s.users.toLocaleString()} 人）</option>)}
        </select>
      </label>
      <label>隐私预算 ε
        <select value={request.epsilon} onChange={(e) => set({ epsilon: Number(e.target.value) })}>
          {[0.5, 1, 2, 4].map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      <label>每区域发布 Top-m
        <select value={request.top_m} onChange={(e) => set({ top_m: Number(e.target.value) })}>
          {[10, 20, 40].map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      <label>{prediction ? "每源采样用户数（上限）" : "每区域参与用户"}
        <select value={request.users} onChange={(e) => set({ users: Number(e.target.value) })}>
          {[1000, 2000, 5000, 10000].map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      <label>随机种子（留空随机）<input aria-label="随机种子" inputMode="numeric" type="text" value={seedText ?? String(request.seed ?? "")} aria-invalid={!!seedError}
        onChange={event => setSeedText ? setSeedText(event.target.value) : set({seed: parseSeed(event.target.value).value})} /></label>
      {extra}
      {seedError && <p className="error controls-note" role="alert">{seedError}</p>}
      <details className="controls-note parameter-help"><summary>这些参数决定什么？</summary>
        <dl><dt>目标区域</dt><dd>需要输出榜单的一侧；目标真值只用于离线打分，不进入融合。</dd>
          <dt>隐私预算 ε</dt><dd>本次发布的本地隐私预算；越小隐私约束越强，不保证准确率单调变化。</dd>
          <dt>Top-m</dt><dd>每个来源发布的摘要长度；目标输出为 Top-10，两者不同。</dd>
          <dt>每源采样上限</dt><dd>向每个来源请求的最多用户数；实际数量见来源明细。</dd>
          <dt>随机种子</dt><dd>控制模拟采样与随机过程。留空由后端生成；结果中的实际种子可用于同条件重放。</dd></dl>
      </details>
    </fieldset>
  );
}

export function ColdStart({ dataset }: { dataset: DatasetInfo }) {
  const session = useDemoSession(), saved = session.sessions[sessionKey(dataset.name, "coldstart")];
  const [request, setRequest] = useState<RunRequest>(() => saved?.draft ?? defaultRequest(dataset));
  const [seedText, setSeedText] = useState(saved?.seedText ?? String(saved?.draft?.seed ?? ""));
  const [completed, setCompleted] = useState<CompletedRun | undefined>(saved?.completed);
  const { events, status, error, running, bad, start, reset } = useRunner({}, value => {
    setCompleted(value); session.patch(dataset.name, "coldstart", {completed: value});
  });
  const seed = parseSeed(seedText);
  const updateRequest = (next: RunRequest) => { reset(); setRequest(next); session.patch(dataset.name, "coldstart", {draft: next}); };
  const updateSeed = (text: string) => {setSeedText(text); updateRequest({...request, seed: parseSeed(text).value}); session.patch(dataset.name, "coldstart", {seedText: text});};
  const run = (next = request) => { if (!seed.error) void start({...next, seed: seed.value}); };
  const replay = (next: RunRequest) => {updateRequest(next); setSeedText(String(next.seed)); session.patch(dataset.name, "coldstart", {seedText: String(next.seed)}); void start(next);};
  const clear = () => {reset(); setCompleted(undefined); session.patch(dataset.name, "coldstart", {completed: undefined});};
  const result = completed?.result;
  const matching = result && requestMatches(request, result) && !seed.error;
  const displayedEvents = events.length || running ? events : matching ? result.events ?? [] : [];
  const sources = dataset.servers.map((s) => s.id).filter((s) => s !== request.target);

  return (
    <div className="page prediction-page">
      <Card title="预测配置" headingLevel={1} extra={
        <button className="primary" disabled={running || !!seed.error} onClick={() => run()}>{running ? "执行中…" : "开始预测"}</button>
      }>
        <p className="muted">
          选择参数，点击“开始预测”，查看摘要交换过程与榜单。
        </p>
        <details className="help-details"><summary>运行与结果保留说明</summary><p className="muted small">正常摘要交换演示。每次执行建立新窗口；切页会停止接收当前请求，已开始的后端计算可能继续，已完成结果按数据集保留。</p></details>
        <RunControls dataset={dataset} request={request} setRequest={updateRequest} disabled={running} prediction seedText={seedText} setSeedText={updateSeed} seedError={seed.error} />
        {error && <p className="error" role="alert">运行未完成：{error} <button disabled={!!seed.error} onClick={() => run()}>重试预测</button></p>}
      </Card>
      {completed && <RunActions completed={completed} draft={request} busy={running} replay={replay} clear={clear} />}
      {result && <RunSummary result={result} compact datasetTitle={dataset.title} />}
      <div className="grid-2 process-grid">
        <Card title="区域拓扑与发布流水">
          <Topology showNotes={false} target={request.target} sources={sources} status={status} bad={bad} state={matching && !running ? result?.decision.state : undefined} />
        </Card>
        <Card className="prediction-log" title="实时执行日志" extra={<details className="help-details"><summary>日志说明</summary><p>真实执行步骤按 60 ms 节奏回放，不代表实际网络延时。</p></details>}>
          <ExecutionStages events={displayedEvents} sources={sources} complete={!!matching && !running && !error} running={running} error={error} />
          <EventLog events={displayedEvents} conciseDecision />
        </Card>
      </div>
      {result && <ResultPanel result={result} />}
    </div>
  );
}

export function ExecutionStages({ events, sources, complete, running, error }: { events: PipelineEvent[]; sources: string[]; complete: boolean; running: boolean; error: string }) {
  const c = executionCounts(events, sources);
  const rows = [
    ["本地扰动", `${c.collected} / ${sources.length} 个来源`],
    ["签名发布", `${c.released} / ${sources.length} 个来源`],
    ["账本登记", `${c.ledger} / ${sources.length} 个来源`],
    ["网关准入", `接受 ${c.accepted} · 拒收 ${c.rejected}`],
    ["融合与结果", complete ? "结果已返回" : c.decision ? "已形成结论" : running ? "等待结论" : error ? "未完成" : "等待运行"],
  ];
  return <div className="execution-stages" aria-label="执行阶段">
    <ol>{rows.map(([name, value]) => <li key={name}><strong>{name}</strong><span>{value}</span></li>)}</ol>
    <p className="muted small">“接受”指该摘要通过签名、身份、窗口、格式和账本核验并进入融合；不表示该来源数值真实或榜单准确。</p>
    {error && <p className="muted small">执行未完成，已接收记录保留。</p>}
  </div>;
}

export function ResultPanel({ result }: { result: RunResult }) {
  const d = result.decision;
  const lowAgreement = d.reasons.some((reason) => reason.code === "LOW_AGREEMENT");
  const consistency = lowAgreement
    ? "未通过（低于阈值，已触发 LOW_AGREEMENT 降级）"
    : d.state === "REFUSED" ? null : "通过（高于阈值）";
  return (
    <div className="prediction-results">
      <Card className="prediction-ranking" title={<>检查结论与榜单 <StateBadge state={d.state} /></>}>
        <StateExplanation state={d.state} count={d.top_k_named.length} />
        <details className="help-details"><summary>融合方法与一致性检查</summary><p className="muted small">本次融合方法：{d.method}{consistency ? `；来源一致性检查：${consistency}` : ""}。</p></details>
        <div className="reason-groups">
          <section aria-label="降级或拒答原因"><h3>降级／拒答原因</h3>{d.reasons.length ? <Reasons reasons={d.reasons} /> : <p className="muted">本次未返回降级或拒答原因。</p>}</section>
          {!!d.alerts?.length && <section aria-label="附加告警"><h3>附加告警</h3><Reasons reasons={[]} alerts={d.alerts} /></section>}
        </div>
        <TopList items={d.top_k_named} state={d.state} />
      </Card>
        <Card className="prediction-evaluation" title="离线评价">
          <div className="metrics">
            <Metric label="Recall@10" value={pct(result.evaluation?.privedge?.recall, 0)} hint="真实 Top-10 品类中被榜单找回的比例。" />
            <Metric label="NDCG@10" value={decimalText(result.evaluation?.privedge?.ndcg)} hint="衡量榜单排序与目标真值的匹配程度。" />
          </div>
          <details className="help-details"><summary>评价指标说明</summary><p className="muted">目标区域真值仅用于离线打分，不进入发布、准入或融合。数值越高表示本次离线匹配越好。</p></details>
          {d.state === "REFUSED" && !d.top_k_named.length && <p className="empty-state">本次拒答且无榜单；接口若返回零分，该数值是空输出的离线评分，不是三态等级。</p>}
          <div className="runtime-info"><strong>运行信息</strong><p>端到端耗时：{result.elapsed_ms == null ? "未提供" : `${decimalText(result.elapsed_ms, 0)} ms`}；共 {result.sources.length} 个来源。</p></div>
        </Card>
        <Card className="prediction-audit" title="审计记录">
          <dl className="kv">
            <dt>请求编号</dt><dd>{result.audit.request_id}</dd>
            <dt>审计记录哈希</dt><dd><HashValue value={result.audit.record_hash} length={24} /></dd>
            <dt>账本链头</dt><dd><HashValue value={result.audit.ledger_head} length={24} /></dd>
            <dt>哈希链校验</dt><dd>{result.audit.ledger_chain_ok ? <span className="ok">完整</span> : <span className="danger-text">断裂</span>}</dd>
            <dt>随机种子</dt><dd>{result.seed}</dd>
          </dl>
        </Card>
        <Card className="prediction-sources" title="来源明细">
          <div className="table-scroll" tabIndex={0} role="region" aria-label="数据源明细">
          <table className="table">
            <thead><tr><th>区域</th><th className="numeric">用户</th><th className="numeric">伪造用户</th><th className="numeric">过滤剔除</th><th className="numeric">偏离分数</th><th>网关</th></tr></thead>
            <tbody>
              {result.sources.map((s) => (
                <tr key={s.source} className={s.bad ? "row-bad" : ""}>
                  <td>{s.source}{s.bad && <span className="tag warn">攻击者</span>}</td>
                  <td className="numeric">{s.users}</td>
                  <td className="numeric">{countText(s.fake_users)}</td>
                  <td className="numeric">{countText(s.removed_reports)}</td>
                  <td className="numeric">{s.anomaly_score ?? "未提供"}{s.flagged && <span className="tag warn">告警</span>}</td>
                  <td>{s.rejected ? <span className="danger-text">拒收 {s.rejected}</span> : <span className="ok">接受</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
    </div>
  );
}

export function RunSummary({ result, compact = false, datasetTitle }: { result: RunResult; compact?: boolean; datasetTitle?: string }) {
  return <section className="run-summary" aria-label="本次运行结论" role="status">
    <div className="row"><strong>本次现场示例</strong><StateBadge state={result.decision.state} /><span>{result.decision.top_k_named.length} 个输出类别</span></div>
    <p>数据集 {datasetTitle ? `${datasetTitle}（${result.dataset}）` : result.dataset} / 目标 {result.target}；ε={result.epsilon}，Top-m={result.top_m}，种子 {result.seed}；运行 <code>{result.run_id}</code></p>
    {result.request_snapshot && <p className="small">本次请求：每源 {countText(result.request_snapshot.users)} {compact ? "名用户上限" : "名参与用户"}；攻击 {result.attack_name}{result.attack !== "none" && <>；请求攻击来源数 {result.request_snapshot.attackers}；伪造报告比例 β={result.request_snapshot.beta}（仅伪造用户攻击适用）</>}。窗口 {result.window}。</p>}
    {compact ? <p>{resultSentence(result.decision.state, result.decision.top_k_named.length)}</p> : <Reasons reasons={result.decision.reasons} alerts={result.decision.alerts} />}
    {!compact && <p className="muted small">三态表示来源与一致性检查结论，不表示准确度等级；现场示例不替代登记实验。</p>}
  </section>;
}
