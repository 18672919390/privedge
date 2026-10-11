import { useEffect, useState } from "react";
import { getJSON } from "../api";
import { Card, Metric, pct } from "../components/common";
import type { Evidence } from "./Experiments";

const FLOW = [
  ["用户端", "本地 OLH 扰动，原始选择不出设备"],
  ["区域发布者", "聚合 + 伪造用户过滤，只发布 Top-m 摘要"],
  ["签名信封 + 账本", "Ed25519 签名覆盖窗口号；哈希链记账，预算按窗口累加"],
  ["目标网关", "验签 / 角色 / 窗口 / 账本 / 同源多摘要；截尾、多源支持 t=2、权重封顶"],
  ["三态结论", "检查通过 / 降级 / 拒答：只表示来源与一致性是否达标，不表示预测准确"],
];

export function Overview({ go }: { go: (tab: string) => void }) {
  const [ev, setEv] = useState<Evidence | null>(null);
  useEffect(() => { getJSON<Evidence>("/api/evidence").then(setEv); }, []);
  const trd = ev?.utility.meituan_trd.curve;
  const sec = ev?.security.meituan_trd.rows.filter((r) => r.epsilon === 1 && String(r.scenario).startsWith("mga") && r.scenario !== "mga_1src_b0.02");
  const d0 = sec ? Math.max(...sec.filter((r) => r.defense === "D0_none").map((r) => Number(r.attack_success))) : 0;
  const d3 = sec ? Math.max(...sec.filter((r) => r.defense === "D3_both").map((r) => Number(r.attack_success))) : 0;
  const hj = ev?.hijack.meituan_trd.rows.filter((r) => r.epsilon === 1 && r.scenario === "demote_1src");
  const hjD3 = hj?.find((r) => r.defense === "D3_both")?.ndcg as number | undefined;
  const hjD4 = hj?.find((r) => r.defense === "D4_capped")?.ndcg as number | undefined;
  const formalOk = ev ? ev.formal.main.filter((q) => q.query.startsWith("Q") && q.holds).length : 0;

  return (
    <div className="page">
      <section className="hero">
        <h1>PrivEdge：多区域隐私摘要驱动的新区域开站选品</h1>
        <p>
          新开的前置仓 / 配送站（含低空无人机配送站点）没有任何历史订单。PrivEdge 让已运营区域只发布本地差分隐私的
          Top-m 摘要，新区域据此在冷启动时预测自己的 Top-10 热门品类。面对伪造用户、被攻破的合法发布者、
          谎报方差、篡改与重放，网关逐层防御，并给出可审计的三态结论。
        </p>
        <div className="row">
          <button className="primary" onClick={() => go("coldstart")}>开始冷启动预测</button>
          <button onClick={() => go("attack")}>进入攻防实验室</button>
        </div>
      </section>
      <div className="flow">
        {FLOW.map(([title, text], i) => (
          <div key={title} className="flow-step"><div className="flow-no">{i + 1}</div><b>{title}</b><span>{text}</span></div>
        ))}
      </div>
      <Card title="核心指标（美团 TRD 主场景，读取自预注册运行）">
        {ev && trd ? (
          <div className="metrics">
            <Metric label="ε=2 时 Recall@10" value={pct(trd.privedge["2.0"].recall, 1)} hint={`非隐私参照 ${pct(trd.nonprivate_source_mean["2.0"].recall, 1)}`} />
            <Metric label="伪造用户 ≥5% 的攻击成功率" value={`${pct(d0, 0)} → ${pct(d3, 0)}`} hint="无防御 → 两层防御（ε=1）" />
            <Metric label="权重劫持 + 扣热门 NDCG" value={`${hjD3?.toFixed(2)} → ${hjD4?.toFixed(2)}`} hint="仅截尾 → 加权重封顶（新种子复验）" />
            <Metric label="形式化安全性质" value={`${formalOk} / 5 成立`} hint="4 个负对照均按预期被攻破" />
            <Metric label="摘要信封大小" value={`${(ev.overhead.rows[2].release_envelope_bytes / 1000).toFixed(1)} KB`} hint="10 万用户原始报告约 1.2 MB" />
          </div>
        ) : <p className="muted">加载中…</p>}
      </Card>
      <div className="grid-2">
        <Card title="可证明的保证">
          <ul className="bullets">
            <li><b>定理 1（支持规则）</b>：f 个被攻破发布者无论发布什么，输出中的每个品类都至少被 t−f 个诚实区域发布过；f &lt; t 时无法注入新品类，且这个界是紧的。</li>
            <li><b>定理 2（有界影响）</b>：诚实多数下，截尾 + 权重封顶 κ=2 + 下限 0 使任一被攻破源对任一品类分数的抬高和压低，都不超过其权重份额 α。</li>
            <li><b>ProVerif</b>：认证、窗口绑定、账本绑定、不可代扣预算、上下文角色隔离，在 Dolev-Yao 攻击者下成立。</li>
          </ul>
        </Card>
        <Card title="如实说明的局限">
          <ul className="bullets">
            <li>ε=1 时 Recall 比非隐私参照低约 0.11（Massive、TRD）；ε≥2 才接近。</li>
            <li>≥2 个发布者合谋（f ≥ t）时，定理 1 不提供保证，只能限制幅度。</li>
            <li>2% 的弱伪造用户攻击在 ε=1 时低于发布端的检测阈值。</li>
            <li>TRD 品类名已匿名；区域拓扑为示意图，不是地理位置。</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
