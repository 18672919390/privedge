import { useEffect, useRef, useState } from "react";
import { runStream } from "../api";
import { Card, Metric, Reasons, StateBadge, TopList, pct, short } from "../components/common";
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
  decision: (e) => `决策：${e.state}`,
};

export function useRunner(defaults: Partial<RunRequest>) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState<Record<string, NodeStatus>>({});
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [bad, setBad] = useState<string[]>([]);
  const stop = useRef<() => void>();

  useEffect(() => () => stop.current?.(), []);

  const start = (request: RunRequest, pace = 60) => {
    stop.current?.();
    setEvents([]);
    setStatus({});
    setResult(null);
    setError("");
    setBad([]);
    setRunning(true);
    stop.current = runStream(
      { ...defaults, ...request },
      (event) => {
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
      (r) => { setResult(r); setRunning(false); },
      (message) => { setError(message); setRunning(false); },
      pace,
    );
  };
  return { events, status, result, error, running, bad, start };
}

export function EventLog({ events }: { events: PipelineEvent[] }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }); }, [events]);
  return (
    <div className="eventlog" ref={box}>
      {events.map((e, i) => (
        <div key={i} className={`ev ev-${e.type}`}>
          <span className="ev-t">{e.t_ms.toFixed(0)} ms</span>
          <span>{(EVENT_TEXT[e.type] ?? ((x) => x.type))(e)}</span>
        </div>
      ))}
      {!events.length && <p className="muted">运行后，这里逐条显示后端真实执行的每一步。</p>}
    </div>
  );
}

export function RunControls({ dataset, request, setRequest, extra }: {
  dataset: DatasetInfo;
  request: RunRequest;
  setRequest: (r: RunRequest) => void;
  extra?: React.ReactNode;
}) {
  const set = (patch: Partial<RunRequest>) => setRequest({ ...request, ...patch });
  return (
    <div className="controls">
      <label>新开站区域（目标）
        <select value={request.target} onChange={(e) => set({ target: e.target.value })}>
          {dataset.servers.map((s) => <option key={s.id} value={s.id}>{s.id}（{s.users.toLocaleString()} 人）</option>)}
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
      <label>每区域参与用户
        <select value={request.users} onChange={(e) => set({ users: Number(e.target.value) })}>
          {[2000, 5000, 10000].map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      {extra}
    </div>
  );
}

export function ColdStart({ dataset }: { dataset: DatasetInfo }) {
  const [request, setRequest] = useState<RunRequest>({
    dataset: dataset.name, target: dataset.servers[Math.min(3, dataset.servers.length - 1)].id,
    epsilon: 2, top_m: 40, users: 5000, attack: "none", attackers: 1, beta: 0.1,
  });
  useEffect(() => setRequest((r) => ({ ...r, dataset: dataset.name, target: dataset.servers[Math.min(3, dataset.servers.length - 1)].id })), [dataset]);
  const { events, status, result, error, running, bad, start } = useRunner({});
  const sources = dataset.servers.map((s) => s.id).filter((s) => s !== request.target);

  return (
    <div className="page">
      <Card title="冷启动预测：新开站区域的 Top-10 热门品类" extra={
        <button className="primary" disabled={running} onClick={() => start(request)}>{running ? "执行中…" : "开始预测"}</button>
      }>
        <p className="muted">
          其余区域只在本地做 LDP 扰动，并发布签名的 Top-m 摘要；目标区域没有任何历史数据。
          网关逐条验证后融合，给出 Top-10 与三态结论。目标区域的真实分布只用于右下角的离线打分。
        </p>
        <RunControls dataset={dataset} request={request} setRequest={setRequest} />
        {error && <p className="error">{error}</p>}
      </Card>
      <div className="grid-2">
        <Card title="区域拓扑与发布流水">
          <Topology target={request.target} sources={sources} status={status} bad={bad} state={result?.decision.state} />
        </Card>
        <Card title="实时执行日志" extra={<span className="muted">真实执行步骤（按 60 ms 节奏回放）</span>}>
          <EventLog events={events} />
        </Card>
      </div>
      {result && <ResultPanel result={result} />}
    </div>
  );
}

export function ResultPanel({ result }: { result: RunResult }) {
  const d = result.decision;
  return (
    <div className="grid-2">
      <Card title={<>网关结论 <StateBadge state={d.state} /></>} extra={<span className="muted">融合：{d.method}，源间一致度 {d.agreement.toFixed(3)}</span>}>
        <Reasons reasons={d.reasons} alerts={d.alerts} />
        <p className="muted small">检查通过只说明来源数量和集合一致性达标，不表示预测准确。准确度见右侧离线评估。</p>
        <TopList items={d.top_k_named} />
      </Card>
      <div className="stack">
        <Card title="离线评估（仅用于展示，不参与预测）">
          <div className="metrics">
            <Metric label="Recall@10" value={pct(result.evaluation.privedge.recall, 0)} />
            <Metric label="NDCG@10" value={result.evaluation.privedge.ndcg.toFixed(3)} />
            <Metric label="端到端耗时" value={`${result.elapsed_ms.toFixed(0)} ms`} hint="10 个区域的扰动、发布、登记与预测" />
          </div>
          <p className="muted small">{result.evaluation.note}</p>
        </Card>
        <Card title="数据源明细">
          <table className="table">
            <thead><tr><th>区域</th><th>用户</th><th>伪造用户</th><th>过滤剔除</th><th>偏离分数</th><th>网关</th></tr></thead>
            <tbody>
              {result.sources.map((s) => (
                <tr key={s.source} className={s.bad ? "row-bad" : ""}>
                  <td>{s.source}{s.bad && <span className="tag warn">攻击者</span>}</td>
                  <td>{s.users}</td>
                  <td>{s.fake_users || "—"}</td>
                  <td>{s.removed_reports || "—"}</td>
                  <td>{s.anomaly_score ?? "—"}{s.flagged && <span className="tag warn">告警</span>}</td>
                  <td>{s.rejected ? <span className="danger-text">拒收 {s.rejected}</span> : <span className="ok">接受</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="审计记录">
          <dl className="kv">
            <dt>请求编号</dt><dd>{result.audit.request_id}</dd>
            <dt>审计记录哈希</dt><dd><code>{short(result.audit.record_hash, 24)}</code></dd>
            <dt>账本链头</dt><dd><code>{short(result.audit.ledger_head, 24)}</code></dd>
            <dt>哈希链校验</dt><dd>{result.audit.ledger_chain_ok ? <span className="ok">完整</span> : <span className="danger-text">断裂</span>}</dd>
            <dt>随机种子</dt><dd>{result.seed}（可复现）</dd>
          </dl>
        </Card>
      </div>
    </div>
  );
}
