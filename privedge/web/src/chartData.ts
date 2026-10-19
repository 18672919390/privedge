// Only the category/number series used by this console are supported here.
// Read the same option as the canvas, preserving zero and missing values.
export function chartRows(option: unknown): { headers: string[]; rows: (string | number | null)[][] } | null {
  const o = option as { xAxis?: { data?: unknown[]; name?: string }; series?: { name?: string; type?: string; data?: unknown[] }[] };
  if (!Array.isArray(o.xAxis?.data) || !Array.isArray(o.series) ||
      !o.series.every(s => s.type === "line" || s.type === "bar")) return null;
  return {
    headers: [o.xAxis.name || "类别", ...o.series.map(s => s.name || "数值")],
    rows: o.xAxis.data.map((category, i) => [String(category), ...o.series!.map(s => {
      const value = s.data?.[i];
      return typeof value === "number" && Number.isFinite(value) ? value : null;
    })]),
  };
}
