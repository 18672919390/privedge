import type { Reason } from "./types";

export interface BudgetRow { source_id: string; window_id: string; spent: number | null; limit: number | null }
export interface LedgerEntry { seq: number; kind: string; record_id: string; principal: string; window_id: string; epsilon: number; envelope_digest: string; prev_hash: string; entry_hash: string; created_at: string }
export interface LedgerView {
  entries: LedgerEntry[]; total: number; chain_ok: boolean; first_bad: number | null; head: string;
  latest_window: string | null; latest_budget: BudgetRow[];
  registry: { key_id: string; principal: string; role: string; public_key: string; revoked: boolean }[];
}
export interface Drill { edited_seq: number; field: string; from: number; to: number; chain_ok: boolean; first_bad: number | null; decision_state?: string; decision_reason?: string | null; error?: string; entry_principal?: string | null; entry_window?: string | null; entry_kind?: string | null; total?: number }
export interface AuditRecord {
  request_id: string; at: string; target_region: string; record_hash: string; ledger_head: string; kind?: string; ledger_scope?: string;
  ledger_chain_ok?: boolean; ledger_first_bad?: number | null; inputs?: string[];
  admission: { accepted: string[]; rejected: { source_id: string; code: string; reason?: string }[] };
  decision: { state: string; reasons?: Reason[]; alerts?: Reason[] };
}
export interface OriginalCheck { before: LedgerView; after?: LedgerView; pending: boolean; error?: string }
export const numberText = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "未提供" : value.toLocaleString("zh-CN");
export function chainText(view: Pick<LedgerView, "total" | "chain_ok" | "first_bad">) {
  return view.total === 0 ? "暂无业务记录" : view.chain_ok ? "完整" : view.first_bad == null ? "校验失败，断点未提供" : `第 ${view.first_bad} 条断裂`;
}
export function canDrill(view: LedgerView | null | undefined, seq: number, loading: boolean, error: string, busy: boolean) {
  return !!view && view.total > 0 && Number.isInteger(seq) && seq >= 0 && seq < view.total && !loading && !error && !busy;
}
export const budgetEmptyText = (window: string | null | undefined) => window ? "该窗口未提供预算数据。" : "尚无发布窗口；运行后显示逐来源预算。";
export function verificationText(before: LedgerView, after: LedgerView) {
  if (!after.chain_ok) return "原账本复核异常：完整性校验未通过，请核查断点。";
  if (before.total === after.total && before.head === after.head) return "原账本复核通过：条目数与链头均未改变，完整性校验通过。";
  return "原账本完整，但条目数或链头发生变化；可能存在并行业务，不能确认前后快照一致。";
}
export function rejectionSummary(rows: AuditRecord["admission"]["rejected"]) {
  const groups = new Map<string, { code: string; reason: string; count: number }>();
  for (const row of rows) {
    const reason = row.reason || "接口未提供中文解释";
    const key = `${row.code}\u0000${reason}`, group = groups.get(key);
    if (group) group.count++; else groups.set(key, { code: row.code, reason, count: 1 });
  }
  return [...groups.values()];
}
export function budgetOption(rows: BudgetRow[]) {
  const finite = (value: number | null) => value != null && Number.isFinite(value) ? value : null;
  return {
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
    legend: { top: 0, textStyle: { color: "#a8b7d2", fontSize: 13 } },
    xAxis: { type: "value" as const, name: "ε", max: Math.max(1, ...rows.flatMap(row => [finite(row.spent) ?? 0, finite(row.limit) ?? 0])) * 1.15 },
    yAxis: { type: "category" as const, inverse: true, data: rows.map(row => row.source_id), axisLabel: { interval: 0, fontSize: 13, lineHeight: 17, formatter: (value: string) => value.replace(/@/g, "@\n").split("\n").map(line => line.match(/.{1,18}/gu)?.join("\n") ?? line).join("\n") } },
    series: [
      { type: "bar" as const, name: "已用预算", data: rows.map(row => finite(row.spent)), barMaxWidth: 12, itemStyle: { color: "#6366f1" } },
      { type: "bar" as const, name: "该来源窗口上限", data: rows.map(row => finite(row.limit)), barMaxWidth: 12, itemStyle: { color: "#f59e0b" } },
    ],
    grid: { left: 10, right: 30, top: 45, bottom: 20, containLabel: true },
  };
}
