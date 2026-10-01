import { useEffect, useState } from "react";
import { postJSON } from "../api";
import { Chart } from "../components/Chart";
import { Card, Reasons, StateBadge, TopList, pct } from "../components/common";
import { Topology } from "../components/Topology";
import type { DatasetInfo, RunRequest, RunResult } from "../types";
import { EventLog, RunControls, useRunner } from "./ColdStart";

const DEFENCE: Record<string, string> = {
  none: "—",
  mga: "发布端：利用 OLH 已知噪声结构做联合支持项集检测，剔除伪造用户报告",
  compromised: "网关：多源支持规则 t=2（定理 1：少于 t 个被攻破源无法注入诚实源未发布的品类）+ 留一共识截尾",
  hijack: "网关：权重封顶 κ=2，每个源的权重不超过其余源中位数的 2 倍（定理 2，SECURITY_V4 确认）",
  demote: "网关：权重封顶 κ=2 + 截尾下限 0，扣下热门的影响不超过其权重份额（定理 2）",
  negative: "网关：截尾下限 0，负频率的作用等同于不发布（定理 2 引理 C）",
  tamper: "网关：Ed25519 签名校验（ProVerif Q1）",
  replay: "网关：签名覆盖窗口号，旧窗口摘要一律拒收（ProVerif Q1，负对照 nc1）",
  equivocation: "网关：同一数据源一次请求提交多份摘要时全部拒收（定理 1 的前提）",
  impostor: "网关：密钥注册表绑定 (数据源, 角色)（ProVerif Q1）",
  budget_burn: "账本：登记前验签，第三方无法以他人名义扣预算（ProVerif Q5，负对照 nc4）",
};

interface SweepRow {
  attack: string;
  name: string;
  rejected: string[];
  state: string;
  base: RunResult["evaluation"]["baseline"];
  pe: RunResult["evaluation"]["privedge"];
}

export function AttackLab({ dataset }: { dataset: DatasetInfo }) {
  const [request, setRequest] = useState<RunRequest>({
    dataset: dataset.name, target: dataset.servers[Math.min(3, dataset.servers.length - 1)].id,
    epsilon: 1, top_m: 20, users: 5000, attack: "hijack", attackers: 1, beta: 0.1,
  });
  useEffect(() => setRequest((r) => ({ ...r, dataset: dataset.name, target: dataset.servers[Math.min(3, dataset.servers.length - 1)].id })), [dataset]);
  const { events, status, result, error, running, bad, start } = useRunner({});
  const [sweep, setSweep] = useState<SweepRow[]>([]);
  const [sweeping, setSweeping] = useState(false);
  const sources = dataset.servers.map((s) => s.id).filter((s) => s !== request.target);

  const runSweep = async () => {
    setSweeping(true);
    setSweep([]);
    for (const attack of Object.keys(dataset.attacks).filter((a) => a !== "none")) {
      const r = await postJSON<RunResult>("/api/run", { ...request, attack, seed: 20260929 });
      setSweep((rows) => [...rows, {
        attack, name: r.attack_name, state: r.decision.state,
        rejected: r.events.filter((e) => e.type === "reject").map((e) => String(e.code)),
        base: r.evaluation.baseline, pe: r.evaluation.privedge,
      }]);
    }
    setSweeping(false);
  };

  const compare = result && {
    legend: { data: ["无防御基线", "PrivEdge"], textStyle: { color: "#cbd5e1" } },
    tooltip: {},
    xAxis: { type: "category", data: ["攻击成功率", "Recall@10", "NDCG@10"] },
    yAxis: { type: "value", min: 0, max: 1 },
    series: [
      { name: "无防御基线", type: "bar", itemStyle: { color: "#ef4444" },
        data: [result.evaluation.baseline.attack_success ?? 0, result.evaluation.baseline.recall, result.evaluation.baseline.ndcg] },
      { name: "PrivEdge", type: "bar", itemStyle: { color: "#10b981" },
        data: [result.evaluation.privedge.attack_success ?? 0, result.evaluation.privedge.recall, result.evaluation.privedge.ndcg] },
    ],
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
  };

  return (
    <div className="page">
      <Card title="攻防实验室：在真实流水上发起攻击" extra={
        <div className="row">
          <button className="primary" disabled={running} onClick={() => start(request)}>{running ? "执行中…" : "发起攻击"}</button>
          <button disabled={sweeping} onClick={runSweep}>{sweeping ? `巡检中 ${sweep.length}/10…` : "一键全攻击巡检"}</button>
        </div>
      }>
        <RunControls dataset={dataset} request={request} setRequest={setRequest} extra={<>
          <label>攻击类型
            <select value={request.attack} onChange={(e) => setRequest({ ...request, attack: e.target.value })}>
              {Object.entries(dataset.attacks).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>被攻破区域数
            <select value={request.attackers} onChange={(e) => setRequest({ ...request, attackers: Number(e.target.value) })}>
              {[1, 2, 3].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          {request.attack === "mga" && (
            <label>伪造用户比例 β
              <select value={request.beta} onChange={(e) => setRequest({ ...request, beta: Number(e.target.value) })}>
                {[0.02, 0.05, 0.1, 0.2].map((v) => <option key={v} value={v}>{v * 100}%</option>)}
              </select>
            </label>
          )}
        </>} />
        <p className="defence"><b>对应防线：</b>{DEFENCE[request.attack]}</p>
        {request.attackers >= 2 && ["compromised", "hijack", "demote"].includes(request.attack) && (
          <p className="warn-text">注意：被攻破区域数 ≥ t=2 时，定理 1 不再提供注入保证，只能依靠截尾与权重封顶限制幅度（如实展示）。</p>
        )}
        {error && <p className="error">{error}</p>}
      </Card>

      <div className="grid-2">
        <Card title="攻击流水">
          <Topology target={request.target} sources={sources} status={status} bad={bad} state={result?.decision.state} />
        </Card>
        <Card title="执行日志"><EventLog events={events} /></Card>
      </div>

      {result && (
        <>
          <div className="grid-3">
            <Card title="无防御基线（不验签、不过滤、不截尾）">
              <TopList items={result.baseline.top_k_named} showSupport={false} />
            </Card>
            <Card title={<>PrivEdge <StateBadge state={result.decision.state} /></>}>
              <Reasons reasons={result.decision.reasons} alerts={result.decision.alerts} />
              <TopList items={result.decision.top_k_named} />
            </Card>
            <Card title="效果对比（离线评估）">
              {compare && <Chart option={compare} height={260} />}
              <p className="muted small">攻击目标：{result.attack_targets.map((t) => t.name).join("、") || "（本攻击不注入品类）"}；攻击者：{result.attackers.join("、")}</p>
            </Card>
          </div>
        </>
      )}

      {sweep.length > 0 && (
        <Card title="全攻击巡检（同一目标、同一种子）">
          <table className="table">
            <thead><tr><th>攻击</th><th>网关拒收</th><th>结论</th><th>基线 攻击成功率</th><th>PrivEdge 攻击成功率</th><th>基线 NDCG</th><th>PrivEdge NDCG</th><th>防线</th></tr></thead>
            <tbody>
              {sweep.map((row) => (
                <tr key={row.attack}>
                  <td>{row.name}</td>
                  <td>{row.rejected.length ? row.rejected.join("、") : "—"}</td>
                  <td>{row.state}</td>
                  <td>{pct(row.base.attack_success, 0)}</td>
                  <td>{pct(row.pe.attack_success, 0)}</td>
                  <td className={row.base.ndcg < row.pe.ndcg - 0.02 ? "danger-text" : ""}>{row.base.ndcg.toFixed(3)}</td>
                  <td>{row.pe.ndcg.toFixed(3)}</td>
                  <td className="small">{DEFENCE[row.attack]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
