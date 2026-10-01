import type { ReactNode } from "react";
import type { NamedItem, Reason } from "../types";

export const STATE_TEXT = { NORMAL: "正常输出", DEGRADED: "降级输出", REFUSED: "拒绝输出" } as const;

export function StateBadge({ state }: { state: keyof typeof STATE_TEXT }) {
  return <span className={`badge state-${state}`}>{state} · {STATE_TEXT[state]}</span>;
}

export function Card({ title, extra, children }: { title: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <header className="card-head">
        <h3>{title}</h3>
        {extra}
      </header>
      {children}
    </section>
  );
}

export function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="metric">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

export function Reasons({ reasons, alerts }: { reasons: Reason[]; alerts?: Reason[] }) {
  if (!reasons.length && !alerts?.length) return <p className="muted">无降级原因</p>;
  return (
    <ul className="reasons">
      {reasons.map((r) => (
        <li key={r.code} className="reason"><code>{r.code}</code>{r.reason}</li>
      ))}
      {alerts?.map((r) => (
        <li key={`a-${r.code}`} className="alert"><code>{r.code}</code>{r.reason}</li>
      ))}
    </ul>
  );
}

export function TopList({ items, showSupport = true }: { items: NamedItem[]; showSupport?: boolean }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>#</th>
          <th>品类</th>
          {showSupport && <th>支持源数</th>}
          <th>离线核对</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={item.category} className={item.injected ? "row-injected" : ""}>
            <td>{index + 1}</td>
            <td>{item.name}{item.injected && <span className="tag danger">攻击目标</span>}</td>
            {showSupport && <td>{item.support ?? "-"}</td>}
            <td>{item.in_truth ? <span className="ok">✓ 真实 Top-10</span> : <span className="muted">—</span>}</td>
          </tr>
        ))}
        {!items.length && (
          <tr><td colSpan={4} className="muted">无输出</td></tr>
        )}
      </tbody>
    </table>
  );
}

export const pct = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;

export const short = (hash: string, n = 12) => (hash ? `${hash.slice(0, n)}…` : "");
