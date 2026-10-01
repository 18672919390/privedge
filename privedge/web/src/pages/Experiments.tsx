import { useEffect, useMemo, useState } from "react";
import { getJSON } from "../api";
import { Chart } from "../components/Chart";
import { Card } from "../components/common";

type Cell = Record<string, number | string | number[] | null>;
export interface Evidence {
  utility: Record<string, { title: string; run_id: string; curve: Record<string, Record<string, { recall: number; ndcg: number }>>;
    top_m: Record<string, Record<string, number>>; sources: Record<string, Record<string, number>>; refusal: Record<string, number> }>;
  security: Record<string, { title: string; run_id: string; rows: Cell[] }>;
  hijack: Record<string, { title: string; run_id: string; rows: Cell[] }>;
  formal: { run_id: string; main: { query: string; result: string; holds: boolean }[];
    controls: Record<string, { dropped_check: string; broken: string[]; as_expected: boolean }> };
  overhead: { run_id: string; rows: Record<string, number>[] };
}

const METHOD = { nonprivate_source_mean: "非隐私参照（源平均）", variance_weighted: "团队原始方差加权", privedge: "PrivEdge（含全部防御）", average: "简单平均" } as const;
const SCEN: Record<string, string> = {
  "mga_1src_b0.02": "伪造用户 2%", "mga_1src_b0.05": "伪造用户 5%", "mga_1src_b0.10": "伪造用户 10%",
  "mga_2src_b0.05": "2 源伪造 5%", compromised_1src: "1 源被攻破", compromised_2src: "2 源被攻破",
  hijack_1src: "权重劫持", demote_1src: "劫持+扣热门", hijack_2src: "2 源权重劫持", clean: "无攻击",
};
const QUERY: Record<string, string> = {
  Q1: "认证、完整性、窗口绑定", Q2: "账本绑定（对被攻破源也成立）", Q5: "不可代扣他人预算",
  Q3: "上下文真实性与角色隔离", Q4: "原始数据不外泄", S1: "可达性：接受摘要", S2: "可达性：接受上下文",
};

const Source = ({ id }: { id: string }) => <p className="muted small">数据来源：<code>runs/…/{id}</code></p>;

export function Experiments() {
  const [ev, setEv] = useState<Evidence | null>(null);
  const [ds, setDs] = useState("meituan_trd");
  const [eps, setEps] = useState(1);
  const [docs, setDocs] = useState<{ name: string; text: string }[]>([]);
  const [doc, setDoc] = useState("");
  useEffect(() => { getJSON<Evidence>("/api/evidence").then(setEv); getJSON<typeof docs>("/api/prereg").then(setDocs); }, []);

  const charts = useMemo(() => {
    if (!ev) return null;
    const u = ev.utility[ds];
    const epsilons = ["0.5", "1.0", "2.0", "4.0"];
    const utility = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1" } },
      xAxis: { type: "category", name: "ε", data: epsilons },
      yAxis: { type: "value", name: "Recall@10", min: 0.3, max: 1 },
      series: (["nonprivate_source_mean", "variance_weighted", "privedge"] as const).map((m) => ({
        name: METHOD[m], type: "line", smooth: true, symbolSize: 8,
        lineStyle: m === "nonprivate_source_mean" ? { type: "dashed" } : undefined,
        data: epsilons.map((e) => u.curve[m]?.[e]?.recall ?? null),
      })),
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const topm = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1" } },
      xAxis: { type: "category", name: "ε", data: epsilons },
      yAxis: { type: "value", name: "Recall@10（拒答记 0）", min: 0 },
      series: ["10", "20", "40"].map((m) => ({ name: `Top-${m}`, type: "line", data: epsilons.map((e) => u.top_m[m]?.[e] ?? null) })),
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const sec = ev.security[ds].rows.filter((r) => r.epsilon === eps && r.scenario !== "clean");
    const scen = [...new Set(sec.map((r) => String(r.scenario)))];
    const security = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1" } },
      xAxis: { type: "category", data: scen.map((s) => SCEN[s] ?? s), axisLabel: { rotate: 20 } },
      yAxis: { type: "value", name: "攻击成功率", min: 0, max: 1 },
      series: [["D0_none", "无防御", "#ef4444"], ["D3_both", "两层防御", "#10b981"]].map(([d, name, color]) => ({
        name, type: "bar", itemStyle: { color },
        data: scen.map((s) => sec.find((r) => r.scenario === s && r.defense === d)?.attack_success ?? null),
      })),
      grid: { left: 50, right: 20, top: 50, bottom: 60 },
    };
    const hj = ev.hijack[ds].rows.filter((r) => r.epsilon === eps);
    const hs = ["hijack_1src", "demote_1src", "hijack_2src"];
    const clean = hj.find((r) => r.scenario === "clean" && r.defense === "D3_both")?.ndcg as number;
    const hijack = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1" } },
      xAxis: { type: "category", data: hs.map((s) => SCEN[s]) },
      yAxis: { type: "value", name: "NDCG@10", min: 0, max: 1 },
      series: [
        ...[["D0_none", "无防御", "#ef4444"], ["D3_both", "截尾 + t=2", "#f59e0b"], ["D4_capped", "+ 权重封顶（主线）", "#10b981"]].map(([d, name, color]) => ({
          name, type: "bar", itemStyle: { color }, data: hs.map((s) => hj.find((r) => r.scenario === s && r.defense === d)?.ndcg ?? null),
        })),
        { name: "无攻击水平", type: "line", data: hs.map(() => clean), lineStyle: { type: "dashed", color: "#94a3b8" }, symbol: "none" },
      ],
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const users = [5000, 20000, 100000];
    const overhead = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1" } },
      xAxis: { type: "category", name: "用户数", data: users.map((x) => x.toLocaleString()) },
      yAxis: [{ type: "log", name: "字节" }],
      series: [
        { name: "原始 LDP 报告", type: "bar", data: users.map((n) => ev.overhead.rows.find((r) => r.users === n && r.domain === 156)?.raw_reports_bytes) },
        { name: "签名摘要信封", type: "bar", data: users.map((n) => ev.overhead.rows.find((r) => r.users === n && r.domain === 156)?.release_envelope_bytes) },
      ],
      grid: { left: 60, right: 20, top: 50, bottom: 40 },
    };
    return { utility, topm, security, hijack, overhead };
  }, [ev, ds, eps]);

  if (!ev || !charts) return <div className="page"><p className="muted">加载实验登记数据…</p></div>;
  return (
    <div className="page">
      <Card title="实验中心：全部数字读取自已登记的预注册运行目录" extra={
        <div className="row">
          {Object.entries(ev.utility).map(([k, v]) => (
            <button key={k} className={k === ds ? "primary" : ""} onClick={() => setDs(k)}>{v.title}</button>
          ))}
          <select value={eps} onChange={(e) => setEps(Number(e.target.value))}>
            <option value={1}>攻防图 ε=1</option><option value={2}>攻防图 ε=2</option>
          </select>
        </div>
      }>
        <p className="muted">预注册：先冻结方案再运行，不在同一批数据上调参重跑，未满足的判定同样报告。详见下方预注册文档。</p>
      </Card>
      <div className="grid-2">
        <Card title="隐私—效用：Recall@10 随 ε 变化（m=20，全部源）">
          <Chart option={charts.utility} />
          <p className="muted small">无攻击时 PrivEdge 与团队原始方差加权曲线几乎重合：签名、截尾、支持规则、权重封顶在干净数据上几乎不损失效用。</p>
          <Source id={ev.utility[ds].run_id} />
        </Card>
        <Card title="发布长度 Top-m 的影响（PrivEdge）"><Chart option={charts.topm} /><Source id={ev.utility[ds].run_id} /></Card>
        <Card title={`投毒攻防（SECURITY_V2，ε=${eps}）`}><Chart option={charts.security} /><Source id={ev.security[ds].run_id} /></Card>
        <Card title={`自适应权重劫持（SECURITY_V4 新种子，ε=${eps}）`}><Chart option={charts.hijack} /><Source id={ev.hijack[ds].run_id} /></Card>
      </div>
      <div className="grid-2">
        <Card title="发布协议形式化验证（ProVerif 2.05，Dolev-Yao 攻击者）">
          <table className="table small">
            <thead><tr><th>性质</th><th>含义</th><th>结果</th></tr></thead>
            <tbody>
              {ev.formal.main.map((q) => {
                const reach = q.query.startsWith("S");
                const good = reach ? !q.holds : q.holds;
                return <tr key={q.query}><td>{q.query}</td><td>{QUERY[q.query]}</td><td className={good ? "ok" : "danger-text"}>{reach ? (good ? "可达" : "不可达") : (good ? "成立" : "不成立")}</td></tr>;
              })}
            </tbody>
          </table>
          <table className="table small">
            <thead><tr><th>负对照</th><th>去掉的检查</th><th>被破坏的性质</th></tr></thead>
            <tbody>
              {Object.entries(ev.formal.controls).map(([k, c]) => (
                <tr key={k}><td>{k}</td><td>{c.dropped_check}</td><td className={c.as_expected ? "warn-text" : "danger-text"}>{c.broken.join("、")}{c.as_expected ? "（符合预期）" : ""}</td></tr>
              ))}
            </tbody>
          </table>
          <Source id={ev.formal.run_id} />
        </Card>
        <Card title="通信开销：摘要大小与用户数无关（156 类）">
          <Chart option={charts.overhead} height={280} />
          <p className="muted small">网关处理 6 个源一次预测约 {ev.overhead.rows[0].gateway_predict_6_sources_ms} ms，验签约 {ev.overhead.rows[0].verify_signature_ms} ms。</p>
          <Source id={ev.overhead.run_id} />
        </Card>
      </div>
      <Card title="预注册与结果文档" extra={
        <select value={doc} onChange={(e) => setDoc(e.target.value)}>
          <option value="">选择文档…</option>
          {docs.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </select>
      }>
        {doc ? <pre className="doc">{docs.find((d) => d.name === doc)?.text}</pre> : <p className="muted">共 {docs.length} 份文档。</p>}
      </Card>
    </div>
  );
}
