import type { PipelineEvent } from "./types";

export function executionCounts(events: PipelineEvent[], sources: string[]) {
  const known = new Set(sources);
  const collected = new Set<string>(), released = new Set<string>(), ledger = new Set<string>();
  const admission = new Map<string, "admit" | "reject">();
  for (const e of events) {
    const id = String(e.source ?? e.source_id ?? "");
    if (!known.has(id)) continue;
    if (e.type === "collect") collected.add(id);
    if (e.type === "release") released.add(id);
    if (e.type === "ledger") ledger.add(id);
    if (e.type === "reject" || e.type === "admit") {
      if (admission.get(id) !== "reject") admission.set(id, e.type);
    }
  }
  return { collected: collected.size, released: released.size, ledger: ledger.size,
    accepted: [...admission.values()].filter(x => x === "admit").length,
    rejected: [...admission.values()].filter(x => x === "reject").length,
    decision: events.some(e => e.type === "decision") };
}
export function decimalText(value: number | null | undefined, digits = 3): string {
  return value == null || !Number.isFinite(value) ? "未提供" : value.toFixed(digits);
}
export function resultSentence(state: string, count: number): string {
  if (state === "REFUSED") return "本次检查结论为拒答；具体原因见下方检查结论。";
  if (state === "DEGRADED") return count ? `本次降级输出 ${count} 个类别，需结合原因阅读。` : "本次降级，未返回可展示的类别。";
  return count ? `本次输出 ${count} 个类别，准确度另见离线评价。` : "本次未返回可展示的类别。";
}
