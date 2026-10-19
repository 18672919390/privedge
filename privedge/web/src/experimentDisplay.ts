export function finiteValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
export function meanText(value: unknown): string {
  const n = finiteValue(value);
  return n === null ? "未提供" : n.toFixed(4);
}
export function intervalText(value: unknown): string {
  return Array.isArray(value) && value.length === 2 && value.every(v => finiteValue(v) !== null) && value[0] <= value[1]
    ? `[${value.map(v => v.toFixed(4)).join(", ")}]` : "区间未提供";
}
export function hasChartValues(option: {series: {data: unknown[]}[]}): boolean {
  return option.series.some(series => series.data.some(v => finiteValue(v) !== null));
}
export function selectedCells<T extends {epsilon: number; scenario: string}>(cells: T[] | undefined, epsilon: number, scenario: string): T[] {
  return (cells ?? []).filter(cell => cell.epsilon === epsilon && cell.scenario === scenario);
}
