import { useMemo } from "react";
import { Chart } from "./Chart";

export type NodeStatus = "idle" | "collect" | "release" | "admit" | "reject" | "attack";

const COLORS: Record<NodeStatus, string> = {
  idle: "#3a4660",
  collect: "#3b82f6",
  release: "#22c55e",
  admit: "#10b981",
  reject: "#ef4444",
  attack: "#f59e0b",
};
const LABELS: Record<NodeStatus, string> = {
  idle: "待命",
  collect: "本地扰动",
  release: "已签名发布",
  admit: "网关接受",
  reject: "网关拒收",
  attack: "被攻破",
};

/** Schematic region topology: the datasets carry no coordinates, so positions are not geographic. */
export function Topology({ target, sources, status, bad, state }: {
  target: string;
  sources: string[];
  status: Record<string, NodeStatus>;
  bad: string[];
  state?: string;
}) {
  const option = useMemo(() => {
    const radius = 38;
    const nodes = sources.map((source, index) => {
      const angle = (2 * Math.PI * index) / Math.max(sources.length, 1) - Math.PI / 2;
      const s = status[source] ?? "idle";
      return {
        name: source,
        x: 50 + radius * Math.cos(angle),
        y: 50 + radius * Math.sin(angle),
        symbolSize: 46,
        itemStyle: { color: COLORS[s], borderColor: bad.includes(source) ? "#f59e0b" : "#0b1220", borderWidth: bad.includes(source) ? 4 : 2 },
        label: { show: true, formatter: `{b}\n${LABELS[s]}`, color: "#e5ecff", fontSize: 11 },
      };
    });
    const stateColor = state === "NORMAL" ? "#10b981" : state === "DEGRADED" ? "#f59e0b" : state === "REFUSED" ? "#ef4444" : "#6366f1";
    nodes.push({
      name: target,
      x: 50,
      y: 50,
      symbolSize: 78,
      itemStyle: { color: stateColor, borderColor: "#c7d2fe", borderWidth: 3 },
      label: { show: true, formatter: `新开站区域\n{b}\n${state ?? "网关"}`, color: "#fff", fontSize: 12 },
    });
    const links = sources.map((source) => {
      const s = status[source] ?? "idle";
      return {
        source,
        target,
        lineStyle: {
          color: COLORS[s],
          width: s === "admit" ? 3 : 1.5,
          type: s === "reject" ? "dashed" : "solid",
          opacity: s === "idle" ? 0.3 : 0.9,
        },
      };
    });
    return {
      tooltip: { formatter: (p: { name?: string }) => p.name ?? "" },
      series: [{
        type: "graph",
        layout: "none",
        roam: false,
        data: nodes,
        links,
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
        animationDurationUpdate: 200,
      }],
      xAxis: { show: false, min: 0, max: 100 },
      yAxis: { show: false, min: 0, max: 100, inverse: true },
      grid: { left: 10, right: 10, top: 10, bottom: 10 },
    };
  }, [target, sources, status, bad, state]);

  return (
    <div>
      <Chart option={option} height={420} />
      <div className="legend">
        {(Object.keys(COLORS) as NodeStatus[]).map((k) => (
          <span key={k}><i style={{ background: COLORS[k] }} />{LABELS[k]}</span>
        ))}
        <span className="muted">示意拓扑：数据集只有匿名区域编号，没有坐标</span>
      </div>
    </div>
  );
}
