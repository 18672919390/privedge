import { useMemo, useState, type ReactNode } from "react";
import "../experiments.css";
import { useJSONResource } from "../useJSONResource";
import { Chart } from "../components/Chart";
import { Card } from "../components/common";
import { finiteValue, hasChartValues } from "../experimentDisplay";
import { A8Comparison } from "../components/A8Comparison";

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
  Q1: "认证、完整性、窗口绑定", Q2: "账本绑定", Q5: "不可代扣他人预算",
  Q3: "上下文真实性与角色隔离", Q4: "模型内符号保密性", S1: "可达性：接受摘要", S2: "可达性：接受上下文",
};

const Source = ({ id }: { id?: string }) => <details className="help-details"><summary>查看数据来源</summary><p className="muted small">{id ? <>数据来源：<code>runs/…/{id}</code></> : "暂无对应运行记录"}</p></details>;

export function Experiments({ datasetName: ds, selectDataset }: { datasetName: string; selectDataset: (name: string) => void }) {
  const { data: ev, error, loading, retry } = useJSONResource<Evidence>("/api/evidence");
  const [eps, setEps] = useState(1);
  const documents = useJSONResource<{ name: string; text: string }[]>("/api/prereg");
  const docs = Array.isArray(documents.data) ? documents.data : [];
  const [doc, setDoc] = useState("");

  const charts = useMemo(() => {
    const u = ev?.utility?.[ds];
    const epsilons = ["0.5", "1.0", "2.0", "4.0"];
    const utility = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1", fontSize: 13 } },
      xAxis: { type: "category", name: "ε", data: epsilons },
      yAxis: { type: "value", name: "Recall@10", min: 0, max: 1 },
      series: (["nonprivate_source_mean", "variance_weighted", "privedge"] as const).map((m) => ({
        name: METHOD[m], type: "line", symbolSize: 8,
        lineStyle: m === "nonprivate_source_mean" ? { type: "dashed" } : undefined,
        data: epsilons.map((e) => u?.curve?.[m]?.[e]?.recall ?? null),
      })),
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const topm = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1", fontSize: 13 } },
      xAxis: { type: "category", name: "ε", data: epsilons },
      yAxis: { type: "value", name: "Recall@10（拒答记 0）", nameTextStyle: { align: "left" }, min: 0 },
      series: ["10", "20", "40"].map((m) => ({ name: `Top-${m}`, type: "line", data: epsilons.map((e) => u?.top_m?.[m]?.[e] ?? null) })),
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const sec = ev?.security?.[ds]?.rows?.filter((r) => r.epsilon === eps && r.scenario !== "clean") ?? [];
    const scen = [...new Set(sec.map((r) => String(r.scenario)))];
    const security = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1", fontSize: 13 } },
      xAxis: { type: "category", data: scen.map((s) => SCEN[s] ?? s), axisLabel: { interval: 0, fontSize: 13, formatter: (v: string) => v.replace("源被", "源\n被").replace("伪造 ", "伪造\n").replace("2 源", "2源\n") } },
      yAxis: { type: "value", name: "攻击成功率", min: 0, max: 1 },
      series: [["D0_none", "无防御", "#ef4444"], ["D3_both", "两层防御", "#10b981"]].map(([d, name, color]) => ({
        name, type: "bar", itemStyle: { color },
        data: scen.map((s) => sec.find((r) => r.scenario === s && r.defense === d)?.attack_success ?? null),
      })),
      grid: { left: 50, right: 20, top: 50, bottom: 60 },
    };
    const hj = ev?.hijack?.[ds]?.rows?.filter((r) => r.epsilon === eps) ?? [];
    const hs = ["hijack_1src", "demote_1src", "hijack_2src"];
    const clean = hj.find((r) => r.scenario === "clean" && r.defense === "D3_both")?.ndcg as number;
    const hijack = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1", fontSize: 13 } },
      xAxis: { type: "category", data: hs.map((s) => SCEN[s]), axisLabel: { fontSize: 13, interval: 0, formatter: (v: string) => v.replace("+", "+\n").replace("2 源", "2源\n") } },
      yAxis: { type: "value", name: "NDCG@10", min: 0, max: 1 },
      series: [
        ...[["D0_none", "无防御", "#ef4444"], ["D3_both", "截尾 + t=2", "#f59e0b"], ["D4_capped", "+ 权重封顶（主线）", "#10b981"]].map(([d, name, color]) => ({
          name, type: "bar", itemStyle: { color }, data: hs.map((s) => hj.find((r) => r.scenario === s && r.defense === d)?.ndcg ?? null),
        })),
        { name: "无攻击水平", type: "line", data: hs.map(() => finiteValue(clean)), lineStyle: { type: "dashed", color: "#94a3b8" }, symbol: "none" },
      ],
      grid: { left: 50, right: 20, top: 50, bottom: 40 },
    };
    const users = [5000, 20000, 100000];
    const overhead = {
      tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: "#cbd5e1", fontSize: 13 } },
      xAxis: { type: "category", name: "用户数", data: users.map((x) => x.toLocaleString()) },
      yAxis: [{ type: "log", name: "字节" }],
      series: [
        { name: "原始 LDP 报告", type: "bar", data: users.map((n) => ev?.overhead?.rows?.find((r) => r.users === n && r.domain === 156)?.raw_reports_bytes ?? null) },
        { name: "签名摘要信封", type: "bar", data: users.map((n) => ev?.overhead?.rows?.find((r) => r.users === n && r.domain === 156)?.release_envelope_bytes ?? null) },
      ],
      grid: { left: 20, right: 64, top: 50, bottom: 40, containLabel: true },
    };
    const result = { utility, topm, security, hijack, overhead };
    for (const option of Object.values(result)) {
      Object.assign(option.grid, {top: 70});
      for (const series of option.series) series.data = series.data.map(finiteValue);
    }
    return result;
  }, [ev, ds, eps]);

  const overhead = ev?.overhead?.rows?.find((row) => row.domain === 156 && row.users === 5000);
  const slot = (available: boolean, children: ReactNode) => <EvidenceSlot loading={loading} error={error} available={available} retry={retry}>{children}</EvidenceSlot>;
  return (
    <div className="page experiments-page">
      <section className="history-scope card"><h2>历史证据库 <span className="tag">只读</span></h2><p className="muted small">读取已登记的历史结果，不启动新实验；现场单次运行不并入这些统计。</p></section>
      <A8Comparison datasetName={ds} selectDataset={selectDataset} />
      <header className="experiment-section-head"><h2>效用与发布参数</h2><p className="muted">当前数据集：{ev?.utility?.[ds]?.title ?? ds}；曲线展示完整 ε 范围。</p><p className="muted small">干净数据上目标是与基线持平；优势见下方攻防实验与三态判断。</p></header>
      <div className="experiment-pair">
        <Card title="隐私与效用关系">
          {slot(hasChartValues(charts.utility), <div className="experiment-chart" tabIndex={0} role="region" aria-label="隐私与效用图表区域"><Chart title="隐私与效用" description="" showDescription={false} option={charts.utility} /></div>)}
          <Source id={ev?.utility?.[ds]?.run_id} />
        </Card>
        <Card title="发布长度 Top-m 的影响">{slot(hasChartValues(charts.topm), <div className="experiment-chart" tabIndex={0} role="region" aria-label="发布长度的影响图表区域"><Chart title="发布长度的影响" description="" showDescription={false} option={charts.topm} /></div>)}<Source id={ev?.utility?.[ds]?.run_id} /></Card>
      </div>
      <header className="experiment-section-head"><div><h2>攻防实验</h2></div>
        <label>攻防图隐私预算<select aria-label="既有攻防图隐私预算" value={eps} onChange={e => setEps(Number(e.target.value))}><option value={1}>ε=1</option><option value={2}>ε=2</option></select></label>
      </header>
      <div className="experiment-pair">
        <Card title="投毒防御效果">{slot(hasChartValues(charts.security), <div className="experiment-chart" tabIndex={0} role="region" aria-label="投毒防御图表区域"><Chart title="投毒防御" description="" showDescription={false} option={charts.security} /></div>)}<Source id={ev?.security?.[ds]?.run_id} /></Card>
        <Card title="自适应权重劫持防御效果">{slot(hasChartValues(charts.hijack), <div className="experiment-chart" tabIndex={0} role="region" aria-label="自适应权重劫持图表区域"><Chart title="自适应权重劫持" description="" showDescription={false} option={charts.hijack} /></div>)}<Source id={ev?.hijack?.[ds]?.run_id} /></Card>
      </div>
        <Card title="协议形式化验证">
          {slot(Boolean(ev?.formal?.main?.length || Object.keys(ev?.formal?.controls ?? {}).length), <div className="experiment-pair formal-tables">
          <div className="table-scroll" tabIndex={0} role="region" aria-label="主性质验证"><table className="table small">
            <thead><tr><th>性质</th><th>含义</th><th>结果</th></tr></thead>
            <tbody>
              {(ev?.formal?.main ?? []).map((q) => {
                const reach = q.query.startsWith("S");
                const good = reach ? !q.holds : q.holds;
                return <tr key={q.query}><td>{q.query}</td><td>{QUERY[q.query]}</td><td className={good ? "ok" : "danger-text"}>{reach ? (good ? "可达" : "不可达") : (good ? "成立" : "不成立")}</td></tr>;
              })}
            </tbody>
          </table></div>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="负对照验证"><table className="table small">
            <thead><tr><th>负对照</th><th>去掉的检查</th><th>被破坏的性质</th></tr></thead>
            <tbody>
              {Object.entries(ev?.formal?.controls ?? {}).map(([k, c]) => (
                <tr key={k}><td>{k}</td><td>{c.dropped_check.replace(/[（(]修复前的 ledger\.append[）)]/g, "")}</td><td className={c.as_expected ? "warn-text" : "danger-text"}>{c.broken.join("、")}{c.as_expected ? "（符合预期）" : ""}</td></tr>
              ))}
            </tbody>
          </table></div>
          </div>)}
          <Source id={ev?.formal?.run_id} />
        </Card>
        <Card title="通信开销">
          {slot(hasChartValues(charts.overhead), <div className="experiment-overhead"><div className="experiment-chart" tabIndex={0} role="region" aria-label="通信开销图表区域"><Chart title="通信开销" description="" showDescription={false} option={charts.overhead} height={280} /></div>
          <div><h3>实验条件与历史耗时</h3><p className="muted">156 类 · Top-m=20 · ε=1</p><p className="muted small">{overhead ? `登记环境下，5000 用户、6 个源一次网关预测约 ${overhead.gateway_predict_6_sources_ms} ms，验签约 ${overhead.verify_signature_ms} ms。` : "暂无对应开销结果。"}</p></div></div>)}
          <Source id={ev?.overhead?.run_id} />
        </Card>
      <Card title="预注册与结果文档" extra={
        <select aria-label="预注册与结果文档" value={docs.some(d => d.name === doc) ? doc : ""} onChange={(e) => setDoc(e.target.value)}>
          <option value="">选择文档…</option>
          {docs.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </select>
      }>
        {documents.loading ? <p className="muted">加载预注册文档…</p> : documents.error ? <p className="error" role="alert">预注册文档加载失败：{documents.error}。<button onClick={documents.retry}>重试文档</button></p> : docs.some(d => d.name === doc) ? <pre className="doc">{docs.find((d) => d.name === doc)?.text}</pre> : <p className="muted">{docs.length ? `共 ${docs.length} 份文档。` : "暂无预注册文档。"}</p>}
      </Card>
    </div>
  );
}

export function EvidenceSlot({loading, error, available, retry, children}: {loading: boolean; error: string; available: boolean; retry: () => void; children: ReactNode}) {
  if (loading) return <p role="status">正在读取实验数据…</p>;
  if (error) return <p role="alert" className="error">实验数据加载失败：{error} <button onClick={retry}>重试实验数据</button></p>;
  if (!available) return <p className="muted">当前条件未提供对应实验结果。<button onClick={retry}>重新读取实验数据</button></p>;
  return <>{children}</>;
}
