import { useMemo } from "react";
import { Chart } from "./Chart";
import { STATE_TEXT } from "./common";
import { topologyLayout } from "../topologyLayout";

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
export function Topology({ target, sources, status, bad, state, showNotes = true }: {
  target: string;
  sources: string[];
  status: Record<string, NodeStatus>;
  bad: string[];
  state?: string;
  showNotes?: boolean;
}) {
  const layout = useMemo(() => {
    const ctx = document.createElement("canvas").getContext("2d");
    if (ctx) ctx.font = '13px "Microsoft YaHei", "PingFang SC", sans-serif';
    return topologyLayout(target, sources, ctx ? text => ctx.measureText(text).width : undefined);
  }, [target, sources]);
  const option = useMemo(() => {
    const nodes = layout.nodes.map(({ id: source, x, y, lines, position }) => {
      const s = status[source] ?? "idle";
      return {
        name: source,
        value: [x, y],
        symbolSize: 46,
        itemStyle: { color: COLORS[s], borderColor: bad.includes(source) ? "#f59e0b" : "#0b1220", borderWidth: bad.includes(source) ? 4 : 2 },
        label: { show: true, position, distance: 8, formatter: `${lines.join("\n")}\n${LABELS[s]}`, color: "#e5ecff", backgroundColor: "#111a2e", padding: [3, 6], borderRadius: 4, fontSize: 13, lineHeight: 18, fontFamily: '"Microsoft YaHei", "PingFang SC", sans-serif' },
      };
    });
    const stateColor = state === "NORMAL" ? "#10b981" : state === "DEGRADED" ? "#f59e0b" : state === "REFUSED" ? "#ef4444" : "#6366f1";
    nodes.push({
      name: target,
      value: [0, 0],
      symbolSize: 78,
      itemStyle: { color: stateColor, borderColor: "#c7d2fe", borderWidth: 3 },
      label: { show: true, position: "bottom", distance: 8, formatter: `${layout.targetLines.join("\n")}\n${STATE_TEXT[state as keyof typeof STATE_TEXT] ?? state ?? "等待运行"}`, color: "#e5ecff", backgroundColor: "#111a2e", padding: [3, 6], borderRadius: 4, fontSize: 13, lineHeight: 18, fontFamily: '"Microsoft YaHei", "PingFang SC", sans-serif' },
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
        // Transform positions only; keep circular symbols in screen pixels.
        coordinateSystem: "cartesian2d",
        symbol: "circle",
        roam: false,
        data: nodes,
        links,
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
        animationDurationUpdate: 0,
      }],
      xAxis: { type: "value", show: false, min: -layout.extent, max: layout.extent },
      yAxis: { type: "value", show: false, min: -layout.extent, max: layout.extent, inverse: true },
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
    };
  }, [target, sources, status, bad, state, layout]);

  return (
    <div>
      <Chart showDescription={showNotes} option={option} height={layout.size} canvasWidth={layout.size} title="来源交换拓扑" description={`目标区域 ${target}，共 ${sources.length} 个来源。图示不代表地理位置；窄窗口可横向滚动，下方数据表可核对完整状态。三态表示检查结论，不代表准确度。`} dataTable={
        <div className="table-scroll" tabIndex={0} role="region" aria-label="拓扑状态明细"><table className="table">
          <thead><tr><th scope="col">区域</th><th scope="col">角色</th><th scope="col">状态</th><th scope="col">攻击标记</th></tr></thead>
          <tbody><tr><th scope="row">{target}</th><td>目标网关</td><td>{STATE_TEXT[state as keyof typeof STATE_TEXT] ?? state ?? "等待运行"}</td><td>—</td></tr>
          {sources.map(source => <tr key={source}><th scope="row">{source}</th><td>来源</td><td>{LABELS[status[source] ?? "idle"]}</td><td>{bad.includes(source) ? "被攻破" : "未标记"}</td></tr>)}</tbody>
        </table></div>
      } />
      <div className="legend">
        {(Object.keys(COLORS) as NodeStatus[]).map((k) => (
          <span key={k}><i style={{ background: COLORS[k] }} />{LABELS[k]}</span>
        ))}
        {showNotes && <span className="muted">示意拓扑：数据集只有匿名区域编号，没有坐标</span>}
      </div>
    </div>
  );
}
