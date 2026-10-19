/** Display semantics only; never change evidence or algorithm outputs. */
export function countText(value: number | null | undefined): string {
  return value == null ? "未提供" : value.toLocaleString("zh-CN");
}

export function metricValue(value: number | null | undefined): number | null {
  return value == null ? null : value;
}

export function refusalText(method: string, cell?: { refusal_rate: number | null }): string {
  if (!cell) return "未提供";
  if (cell.refusal_rate != null) return `${(cell.refusal_rate * 100).toFixed(1)}%`;
  return ["average", "variance_weighted", "robust_baseline"].includes(method)
    ? "不适用（基线无三态）" : "未提供";
}

export function emptyResultText(state?: string): string {
  if (state === "REFUSED") return "本次检查结论为拒答，不输出榜单。具体原因见上方说明。";
  if (state === "DEGRADED") return "本次为降级结论，未返回可展示的类别。具体原因见上方说明。";
  return "本次未返回可展示的类别。";
}

export function followsLog(scrollHeight: number, scrollTop: number, clientHeight: number): boolean {
  return scrollHeight - scrollTop - clientHeight <= 48;
}

export function budgetScale(rows: { spent: number; limit: number }[]): number {
  return Math.max(1, ...rows.flatMap((row) => [row.spent, row.limit])) * 1.15;
}
