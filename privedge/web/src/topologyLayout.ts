export interface Box { x: number; y: number; width: number; height: number }
export interface RegionPosition { id: string; x: number; y: number; lines: string[]; label: Box; position: "left" | "right" | "top" | "bottom" }
const GAP = 8;
export function boxesOverlap(a: Box, b: Box, gap = GAP): boolean {
  return a.x < b.x + b.width + gap - .01 && a.x + a.width + gap > b.x + .01 && a.y < b.y + b.height + gap - .01 && a.y + a.height + gap > b.y + .01;
}
export function wrapRegion(name: string, measure: (text: string) => number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const token of name.match(/[^\s@]+[@\s]?/g) ?? [name]) {
    if (line && measure(line + token) > 132) { lines.push(line); line = ""; }
    for (const ch of token) {
      if (line && measure(line + ch) > 132) { lines.push(line); line = ""; }
      line += ch;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [name];
}
/** Pixel geometry. Labels reserve the longest status, so replay never shifts nodes. */
export function topologyLayout(target: string, sources: string[], measure = (s: string) => [...s].reduce((n,c) => n + (/[^\x00-\xff]/.test(c) ? 13 : 8), 0)) {
  const names = sources.map(id => ({ id, lines: wrapRegion(id, measure) }));
  const targetLines = wrapRegion(`目标区域 ${target}`, measure);
  const targetLabel: Box = { x: -Math.max(132, ...targetLines.map(measure)) / 2 - 6, y: 47, width: Math.max(132, ...targetLines.map(measure)) + 12, height: (targetLines.length + 1) * 18 + 6 };
  let radius = 160;
  let nodes: RegionPosition[] = [];
  for (;;) {
    nodes = names.map(({ id, lines }, i) => {
      const angle = 2 * Math.PI * i / Math.max(names.length, 1) - Math.PI / 2;
      const cos = Math.cos(angle), sin = Math.sin(angle), x = radius * cos, y = radius * sin;
      const width = Math.max(measure("已签名发布"), ...lines.map(measure)) + 12;
      const height = (lines.length + 1) * 18 + 6;
      const position = Math.abs(cos) < .45 ? (sin < 0 ? "top" : "bottom") : (cos < 0 ? "left" : "right");
      const label = { x: position === "left" ? x - 31 - width : position === "right" ? x + 31 : x - width / 2,
        y: position === "top" ? y - 31 - height : position === "bottom" ? y + 31 : y - height / 2, width, height };
      return { id, x, y, lines, label, position };
    });
    const labels = [...nodes.map(n => n.label), targetLabel];
    const circles = [...nodes.map(n => ({ x:n.x-23,y:n.y-23,width:46,height:46 })), {x:-39,y:-39,width:78,height:78}];
    const overlap = labels.some((a,i) => labels.some((b,j) => j > i && boxesOverlap(a,b))) || labels.some(a => circles.some(b => boxesOverlap(a,b))) || circles.some((a,i) => circles.some((b,j) => j > i && boxesOverlap(a,b)));
    if (!overlap) break;
    radius += 16;
  }
  const bounds = [...nodes.map(n => n.label), targetLabel];
  const extent = Math.max(320, radius + 40, ...bounds.flatMap(b => [Math.abs(b.x)+16,Math.abs(b.y)+16,Math.abs(b.x+b.width)+16,Math.abs(b.y+b.height)+16]));
  return { nodes, targetLines, targetLabel, radius, size: Math.ceil(extent * 2), extent };
}
