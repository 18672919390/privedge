import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { refusalText } from "../presentation";
import { Card } from "./common";
import { meanText, intervalText, selectedCells } from "../experimentDisplay";
import { EvidenceDownload } from "./RunActions";
import { publicA8 } from "../evidenceExport";
import { useDemoSession } from "../demoSession";

interface Cell {
  method: string; epsilon: number; scenario: string; top_m: number; sample_count: number;
  ndcg: number | null; recall: number | null; attack_success: number | null;
  ndcg_ci95: number[] | null; recall_ci95: number[] | null; attack_success_ci95: number[] | null;
  refusal_rate: number | null; seeds?: number[];
}
interface Dataset {
  status: string; reason?: string; evidence_id?: string; source_run_id?: string; target_count?: number;
  source_count?: number; users_per_source?: number; top_k?: number; limitations?: string[];
  provenance?: Record<string, string | boolean | null>;
  methods: { id: string; name: string; definition: string }[]; cells: Cell[];
}
interface Response { status: string; datasets: Record<string, Dataset> }
const NAMES: Record<string, string> = { meituan_trd: "美团 TRD", olist_brazil: "Olist", massive_steps: "Massive-STEPS" };
const SCENARIOS: Record<string, string> = {
  clean: "无攻击", "mga_1src_b0.02": "1源注入 β=2%", "mga_1src_b0.05": "1源注入 β=5%", "mga_1src_b0.10": "1源注入 β=10%",
  "mga_2src_b0.05": "2源注入 β=5%", compromised_1src: "1源被攻破", compromised_2src: "2源被攻破",
  weight_hijack_1src: "1源权重劫持", weight_hijack_2src: "2源权重劫持",
};
export function Score({value, interval}: {value?: number | null; interval?: number[] | null}) {
  return <><strong className="score-mean">{meanText(value)}</strong><span className="score-interval">{intervalText(interval)}</span></>;
}

export function A8Comparison({ datasetName: dataset, selectDataset }: { datasetName: string; selectDataset: (name: string) => void }) {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [epsilon, setEpsilon] = useState(2);
  const [scenario, setScenario] = useState("clean");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setData(null); setError("");
    getJSON<Response>("/api/evidence/a8/descriptive", controller.signal)
      .then((value) => { if (active) setData(value); })
      .catch(() => { if (active) setError("四方法结果加载失败，请重试。"); });
    return () => { active = false; controller.abort(); };
  }, [attempt]);
  const selected = data?.datasets[dataset];
  return <Card title="四方法对照 · 描述性结果" headingLevel={1} className="a8-comparison" extra={<div className="experiment-filters">
    <label>数据集<select aria-label="四方法数据集" value={dataset} onChange={(e) => selectDataset(e.target.value)}>
      {Object.entries(NAMES).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
    </select></label>
    <label>A8 隐私预算<select aria-label="四方法隐私预算" value={epsilon} onChange={(e) => setEpsilon(Number(e.target.value))}>
      <option value={1}>ε=1</option><option value={2}>ε=2</option>
    </select></label>
    <label>场景<select aria-label="四方法场景" value={scenario} onChange={(e) => setScenario(e.target.value)}>
      {Object.entries(SCENARIOS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
    </select></label>
  </div>}>
    <p className="filter-scope">当前 ε={epsilon} · {SCENARIOS[scenario]} · 筛选仅作用于本区</p>
    {error ? <p role="alert">{error} <button onClick={() => setAttempt((v) => v + 1)}>重试加载</button></p>
      : !data ? <p className="muted">加载四方法结果…</p>
      : selected?.status !== "DESCRIPTIVE" ? <p role="alert">{selected?.status === "INVALID" ? "描述性证据核验失败" : selected?.status === "NOT_REGISTERED" ? "尚未登记描述性结果" : "描述性结果未提供"} <code>{selected?.status ?? data.status}</code>：{selected?.reason ?? "该数据集没有可用结果"} <button onClick={() => setAttempt((v) => v + 1)}>重新核对描述性结果</button></p>
      : <A8Results selected={selected} epsilon={epsilon} scenario={scenario} datasetName={dataset} />}
  </Card>;
}

export function A8Results({selected, epsilon, scenario, datasetName = "未提供"}: {selected: Dataset; epsilon: number; scenario: string; datasetName?: string}) {
  const {identity} = useDemoSession();
  const cells = selectedCells(selected.cells, epsilon, scenario);
  const topms = [...new Set(cells.map(c => c.top_m))];
  const seeds = [...new Set(cells.flatMap(c => c.seeds ?? []))];
  return <>
        <div className="row"><EvidenceDownload kind="historical_a8" id={`${selected.evidence_id ?? "descriptive"}_${epsilon}_${scenario}`} identity={identity}
          payload={() => publicA8({...selected}, datasetName, epsilon, scenario)} label="下载当前条件历史数据 JSON" disabled={!cells.length} /></div>
        <details className="help-details"><summary>实验样本与参数</summary><p className="muted small">{selected.target_count ?? "未提供"}个留一目标，每次{selected.source_count ?? "未提供"}个来源；每源{selected.users_per_source ?? "未提供"}条诚实报告，Top-m={topms.join(" / ") || "未提供"}、Top-k={selected.top_k ?? "未提供"}、{seeds.length || "未提供"}种子。区间按目标区域重采样，拒答计0。</p></details>
        {!cells.length && <p role="status">当前 ε 与场景未提供四方法结果。</p>}
        <div className="table-scroll" tabIndex={0} role="region" aria-label="四方法均值与区间"><table className="table a8-table">
          <thead><tr><th>方法</th><th className="numeric">NDCG@10 [95%区间]</th><th className="numeric">Recall@10 [95%区间]</th><th className="numeric">{scenario === "clean" ? "目标入榜率（无攻击参照）" : "攻击成功率"} [95%区间]</th><th className="numeric">拒答率</th></tr></thead>
          <tbody>{selected.methods.map((method) => {
            const c = cells.find((v) => v.method === method.id);
            return <tr key={method.id}><td title={method.definition}>{method.name}</td>
              <td className="numeric"><Score value={c?.ndcg} interval={c?.ndcg_ci95} /></td><td className="numeric"><Score value={c?.recall} interval={c?.recall_ci95} /></td>
              <td className="numeric"><Score value={c?.attack_success} interval={c?.attack_success_ci95} /></td>
              <td className="numeric">{refusalText(method.id, c)}</td></tr>;
          })}</tbody>
        </table></div>
        <details><summary>方法定义与解释范围</summary>
        <p className="muted small">原始运行：<code>{selected.source_run_id}</code>。β为伪造报告数/诚实报告数。三种基线使用未筛查摘要，PrivEdge包含发布端筛查；该比较不覆盖实际签名、网关准入或账本。</p>
        <p className="muted small">AS 为攻击目标类别入榜比例；上表是多目标、多种子历史均值与区间，不是现场单次成功概率，不能由均值反推整数分子。导出只保存当前条件，不重算结果。</p>

          {selected.methods.map((m) => <p key={m.id}><strong>{m.name}：</strong>{m.definition}</p>)}
          {selected.limitations?.map((line) => <p key={line} className="muted small">{line}</p>)}
        </details>
        <details className="experiment-provenance"><summary>完整来源与文件指纹</summary>
          <dl><dt>原始运行</dt><dd><code>{selected.source_run_id ?? "未提供"}</code></dd><dt>证据编号</dt><dd>{selected.evidence_id ?? "未提供"}</dd>
          <dt>本条件种子</dt><dd><code>{seeds.join("、") || "未提供"}</code></dd>
          <dt>各方法样本量</dt><dd>{selected.methods.map(m => `${m.name}：${cells.find(c => c.method === m.id)?.sample_count ?? "未提供"}`).join("；")}</dd>
          {Object.entries(selected.provenance ?? {}).map(([key,value]) => <div key={key}><dt>{({source_manifest_sha256:"原始清单 SHA256",source_results_sha256:"原始结果 SHA256",summary_sha256:"描述性摘要 SHA256",audit_sha256:"核验记录 SHA256",review_id:"核验编号",historical_preregistration_bound:"历史预注册绑定",started_at:"开始时间",finished_at:"结束时间",code_combined:"历史代码指纹"} as Record<string,string>)[key] ?? key}</dt><dd><code>{value === false ? "未绑定" : String(value ?? "未提供")}</code></dd></div>)}
          </dl>
        </details>
      </>;
}
