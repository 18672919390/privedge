import type { ReactNode } from "react";
import { emptyResultText } from "../presentation";
import type { NamedItem, Reason } from "../types";

export const STATE_TEXT = { NORMAL: "检查通过", DEGRADED: "降级", REFUSED: "拒答" } as const;

export function StateBadge({ state }: { state: string }) {
  return <span className={`badge state-${state}`}>{STATE_TEXT[state as keyof typeof STATE_TEXT] ?? state}<small>{state}</small></span>;
}

export function StateExplanation({ state, count }: {state: string; count: number}) {
  const text = state === "REFUSED" ? `无法提供符合要求的完整结果；${count ? `接口保留 ${count} 个部分候选，需结合拒答原因阅读。` : "本次未返回候选，具体原因见下方。"}`
    : state === "DEGRADED" ? "本次仍提供输出，并有下列降级原因。" : "本次通过当前来源与一致性检查，不保证预测准确或完全免疫投毒。";
  return <p className="state-explanation muted small">{text} 三态表示检查结论，不是准确度等级。</p>;
}

export function Card({ title, extra, children, headingLevel = 2, className = "" }: { title: ReactNode; extra?: ReactNode; children: ReactNode; headingLevel?: 1 | 2 | 3; className?: string }) {
  const Heading = headingLevel === 1 ? "h1" : headingLevel === 3 ? "h3" : "h2";
  return (
    <section className={`card ${className}`}>
      <header className="card-head">
        <Heading>{title}</Heading>
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
  if (!reasons.length && !alerts?.length) return <p className="muted">本次未返回降级、拒答原因或附加告警。</p>;
  return (
    <ul className="reasons">
      {reasons.map((r) => (
        <li key={r.code} className="reason">{r.reason}<code>{r.code}</code></li>
      ))}
      {alerts?.map((r) => (
        <li key={`a-${r.code}`} className="alert">{r.reason}<code>{r.code}</code></li>
      ))}
    </ul>
  );
}

export function TopList({ items, showSupport = true, state }: { items: NamedItem[]; showSupport?: boolean; state?: string }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="类别榜单"><table className="table">
      <thead>
        <tr>
          <th className="numeric">#</th>
          <th>品类</th>
          {showSupport && <th className="numeric">支持源数</th>}
          <th>离线核对</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={item.category} className={item.injected ? "row-injected" : ""}>
            <td className="numeric">{index + 1}</td>
            <td className="category-name">{item.name}{item.injected && <span className="tag danger">攻击目标</span>}</td>
            {showSupport && <td className="numeric">{item.support ?? "未提供"}</td>}
            <td>{item.in_truth ? <span className="ok">✓ 真实 Top-10</span> : <span className="muted">—</span>}</td>
          </tr>
        ))}
        {!items.length && (
          <tr><td colSpan={showSupport ? 4 : 3} className="empty-state">{emptyResultText(state)}</td></tr>
        )}
      </tbody>
    </table></div>
  );
}

export const pct = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined ? "未提供" : `${(value * 100).toFixed(digits)}%`;

export const short = (hash: string, n = 12) => (hash ? `${hash.slice(0, n)}…` : "");

export function HashValue({ value, length = 16 }: { value?: string; length?: number }) {
  if (!value) return <span className="muted">未提供</span>;
  return <details className="hash-value"><summary title="展开完整值"><code>{short(value, length)}</code></summary><code className="full-hash">{value}</code></details>;
}
