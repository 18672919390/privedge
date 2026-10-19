import { useEffect, useId, useRef, type ReactNode } from "react";
import * as echarts from "echarts";
import { chartRows } from "../chartData";

export function Chart({ option, title, description, height = 320, dataTable, missingText, canvasWidth, showDescription = true }: {
  option: echarts.EChartsCoreOption; title: string; description: string; height?: number;
  dataTable?: ReactNode; missingText?: (category: string) => string; canvasWidth?: number; showDescription?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts>();
  const id = useId();
  const table = chartRows(option);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, "dark", { renderer: "canvas" });
    const observer = new ResizeObserver(() => chart.current?.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    // Evidence and audit charts must show their final values immediately, including after a refresh.
    chart.current?.setOption({ backgroundColor: "transparent", animation: false, ...option }, true);
  }, [option]);

  return <div className="chart-block">
    <div className={canvasWidth ? "topology-scroll" : undefined} tabIndex={canvasWidth ? 0 : undefined} role={canvasWidth ? "region" : "img"} aria-label={title} aria-describedby={showDescription ? id : undefined}>
      <div ref={ref} aria-hidden="true" style={{ width: canvasWidth ?? "100%", height, marginInline: canvasWidth ? "auto" : undefined }} />
    </div>
    {showDescription && <details className="help-details"><summary>图表说明</summary><p id={id} className="muted small chart-description">{description}</p></details>}
    <details className="chart-data"><summary>{title}：查看数据表</summary>
      {dataTable ?? (table && <div className="table-scroll" tabIndex={0} role="region" aria-label={`${title}数据`}>
        <table className="table"><caption className="sr-only">{title}，{description}</caption>
          <thead><tr>{table.headers.map((h, i) => <th key={i} scope="col" className={i ? "numeric" : undefined}>{h}</th>)}</tr></thead>
          <tbody>{table.rows.map((row, i) => <tr key={i}>{row.map((v, j) => j === 0
            ? <th key={j} scope="row">{v}</th>
            : <td key={j} className="numeric">{v ?? missingText?.(String(row[0])) ?? "未提供"}</td>)}</tr>)}</tbody>
        </table>
      </div>)}
    </details>
  </div>;
}
