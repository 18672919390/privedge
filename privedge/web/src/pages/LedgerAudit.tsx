import { useCallback, useEffect, useState } from "react";
import { getJSON, postJSON } from "../api";
import { Chart } from "../components/Chart";
import { Card, short } from "../components/common";
import type { DatasetInfo } from "../types";

interface LedgerEntry {
  seq: number;
  kind: string;
  record_id: string;
  principal: string;
  window_id: string;
  epsilon: number;
  envelope_digest: string;
  prev_hash: string;
  entry_hash: string;
  created_at: string;
}
interface LedgerView {
  entries: LedgerEntry[];
  total: number;
  chain_ok: boolean;
  first_bad: number | null;
  head: string;
  budget: { source_id: string; window_id: string; spent: number; limit: number }[];
  registry: { key_id: string; principal: string; role: string; public_key: string; revoked: boolean }[];
}
interface Drill { edited_seq: number; field: string; from: number; to: number; chain_ok: boolean; first_bad: number | null; error?: string }
interface AuditRecord { request_id: string; at: string; target_region: string; record_hash: string; ledger_head: string;
  admission: { accepted: string[]; rejected: { code: string; source_id: string }[] }; decision: { state: string } }

export function LedgerAudit({ dataset }: { dataset: DatasetInfo }) {
  const [view, setView] = useState<LedgerView | null>(null);
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [drill, setDrill] = useState<Drill | null>(null);
  const [seq, setSeq] = useState(0);

  const refresh = useCallback(async () => {
    setView(await getJSON<LedgerView>(`/api/ledger/${dataset.name}`));
    setAudit(await getJSON<AuditRecord[]>(`/api/audit/${dataset.name}`));
  }, [dataset.name]);
  useEffect(() => { refresh(); }, [refresh]);

  const lastWindow = view?.budget.length ? view.budget[view.budget.length - 1].window_id : "";
  const budget = view?.budget.filter((b) => b.window_id === lastWindow) ?? [];
  const budgetOption = {
    tooltip: {},
    xAxis: { type: "category", data: budget.map((b) => b.source_id), axisLabel: { rotate: 30 } },
    yAxis: { type: "value", max: 4, name: "ε" },
    series: [
      { type: "bar", data: budget.map((b) => b.spent), itemStyle: { color: "#6366f1" }, name: "已用",
        markLine: { data: [{ yAxis: 4, name: "上限" }], lineStyle: { color: "#ef4444" }, label: { formatter: "单窗口上限 ε=4", position: "insideEndTop", color: "#fca5a5" } } },
    ],
    grid: { left: 40, right: 20, top: 30, bottom: 60 },
  };

  return (
    <div className="page">
      <Card title="隐私预算账本（哈希链）" extra={<button onClick={refresh}>刷新</button>}>
        {view && (
          <div className="metrics">
            <div className="metric"><div className="metric-value">{view.total}</div><div className="metric-label">账本条目</div></div>
            <div className="metric"><div className={`metric-value ${view.chain_ok ? "ok" : "danger-text"}`}>{view.chain_ok ? "完整" : `第 ${view.first_bad} 条断裂`}</div><div className="metric-label">哈希链校验</div></div>
            <div className="metric"><div className="metric-value mono">{short(view.head, 16)}</div><div className="metric-label">链头哈希</div></div>
            <div className="metric"><div className="metric-value">{view.registry.length}</div><div className="metric-label">注册密钥</div></div>
          </div>
        )}
        {!view && <p className="muted">加载中…</p>}
        {view && !view.total && <p className="muted">账本为空：先在“冷启动预测”或“攻防实验室”运行一次。</p>}
      </Card>
      <div className="grid-2">
        <Card title={`最新窗口 ${lastWindow || "—"} 的预算消耗`}>
          <Chart option={budgetOption} height={280} />
          <p className="muted small">同一窗口内的多次发布按顺序组合累加；账本在登记前验签，第三方无法以他人名义扣预算。</p>
        </Card>
        <Card title="篡改演练（在账本副本上修改一条记录）">
          <div className="row">
            <span className="inline-label">修改第
              <input type="number" min={0} max={Math.max(0, (view?.total ?? 1) - 1)} value={seq} onChange={(e) => setSeq(Number(e.target.value))} style={{ width: 90 }} />
              条记录的 ε
            </span>
            <button className="primary" onClick={async () => setDrill(await postJSON<Drill>(`/api/ledger/${dataset.name}/tamper-drill?seq=${seq}`))}>执行演练</button>
          </div>
          {drill && (drill.error ? <p className="error">{drill.error}</p> : (
            <p className={drill.chain_ok ? "ok" : "danger-text"}>
              把第 {drill.edited_seq} 条的 {drill.field} 从 {drill.from} 改为 {drill.to} 后，哈希链校验
              {drill.chain_ok ? "仍通过（不应发生）" : `失败，并精确定位到第 ${drill.first_bad} 条`}。真实账本未被修改。
            </p>
          ))}
        </Card>
      </div>
      <Card title="账本条目（最近 300 条）">
        <div className="scroll">
          <table className="table mono small">
            <thead><tr><th>序号</th><th>类型</th><th>主体</th><th>窗口</th><th>ε</th><th>信封摘要</th><th>前一哈希</th><th>本条哈希</th></tr></thead>
            <tbody>
              {view?.entries.slice().reverse().map((e) => (
                <tr key={e.seq}><td>{e.seq}</td><td>{e.kind}</td><td>{e.principal}</td><td>{e.window_id}</td><td>{e.epsilon}</td>
                  <td>{short(e.envelope_digest)}</td><td>{short(e.prev_hash)}</td><td>{short(e.entry_hash)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid-2">
        <Card title="网关审计记录">
          <div className="scroll">
            <table className="table small">
              <thead><tr><th>请求</th><th>目标</th><th>接受</th><th>拒收</th><th>结论</th><th>记录哈希</th></tr></thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.request_id}><td>{a.request_id}</td><td>{a.target_region}</td><td>{a.admission.accepted.length}</td>
                    <td>{a.admission.rejected.map((r) => r.code).join("、") || "—"}</td><td>{a.decision.state}</td><td className="mono">{short(a.record_hash)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="密钥注册表（数据源 / 角色绑定）">
          <div className="scroll">
            <table className="table small">
              <thead><tr><th>密钥</th><th>主体</th><th>角色</th><th>公钥</th></tr></thead>
              <tbody>
                {view?.registry.map((k) => (
                  <tr key={k.key_id}><td>{k.key_id}</td><td>{k.principal}</td><td>{k.role}</td><td className="mono">{short(k.public_key, 16)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
