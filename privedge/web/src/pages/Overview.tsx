import { useId, useLayoutEffect, useRef, useState } from "react";
import { TheoryScope } from "../components/TheoryScope";
import "../overview.css";

const INTRO = "PrivEdge面向多源 LDP 摘要的抗投毒可信交换，结合发布端筛查、网关鲁棒融合、签名验证与隐私预算账本，应对伪造报告、恶意发布与摘要篡改，并输出检查通过、降级或拒答及原因。新区域 Top-10 选品只是应用例子，统计代理任务上的结果不等于经营收益已验证。";
const ROLES = ["用户端", "区域发布者", "密钥注册表", "账本", "目标网关", "审计检查"];
const PROTOCOL = [
  { from: 0, to: 1, text: "提交 OLH 扰动报告", kind: "data" },
  { from: 1, to: 1, text: "筛查伪造报告，估计频率与方差，生成 Top-m 摘要", kind: "data" },
  { from: 1, to: 3, text: "签名摘要，申请登记", kind: "check" },
  { from: 3, to: 2, text: "查询主体与角色对应的公钥，并验签", kind: "check" },
  { from: 3, to: 3, text: "检查窗口预算，通过后追加哈希链", kind: "check" },
  { from: 1, to: 4, text: "登记成功后，发送签名摘要", kind: "data" },
  { from: 4, to: 2, text: "验证身份与角色，检查签名、窗口和域", kind: "check" },
  { from: 4, to: 3, text: "核对账本记录与摘要一致性", kind: "check" },
  { from: 4, to: 4, text: "检查同源多摘要及格式，不合格摘要拒收并记录原因", kind: "data" },
  { from: 4, to: 4, text: "鲁棒融合与排序，形成三态结果及原因", kind: "data" },
  { from: 5, to: 3, text: "汇集审计记录，检查哈希链完整性并定位断点", kind: "check" },
];


/** Connectors follow actual node bounds, including font wrapping and resizing. */
function Architecture() {
  const root = useRef<HTMLDivElement>(null);
  const marker = useId().replace(/:/g, "");
  const [paths, setPaths] = useState<string[]>([]);
  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    const update = () => {
      if (window.innerWidth < 1100) { setPaths([]); return; }
      const origin = element.getBoundingClientRect();
      const box = (name: string) => {
        const r = element.querySelector<HTMLElement>(`[data-flow="${name}"]`)!.getBoundingClientRect();
        return { left: r.left - origin.left, right: r.right - origin.left, y: r.top - origin.top + r.height / 2 };
      };
      const gate = box("gate");
      const sourcePaths = ["source-0", "source-1", "source-2"].map(name => {
        const source = box(name), join = source.right + (gate.left - source.right) * .52;
        return `M ${source.right} ${source.y} H ${join} V ${gate.y} H ${gate.left - 5}`;
      });
      const fusion = box("fusion"), output = box("result"), join = (fusion.right + output.left) / 2;
      setPaths([...sourcePaths, `M ${fusion.right} ${fusion.y} H ${join} V ${output.y} H ${output.left - 5}`]);
    };
    const observer = new ResizeObserver(update);
    observer.observe(element);
    element.querySelectorAll("[data-flow]").forEach(node => observer.observe(node));
    window.addEventListener("resize", update);
    update();
    return () => { observer.disconnect(); window.removeEventListener("resize", update); };
  }, []);
  return <div className="exchange-architecture" ref={root}>
    <svg className="exchange-connections" aria-hidden="true">
      <defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="currentColor" /></marker></defs>
      {paths.map((path, i) => <path key={i} d={path} fill="none" stroke="currentColor" strokeWidth="1.5" markerEnd={`url(#${marker})`} />)}
    </svg>
    <section className="exchange-sources" aria-labelledby="sources-heading">
      <div className="exchange-column-heading">
        <h3 id="sources-heading">源区域</h3>
        <p className="exchange-caption">各区域独立处理，原始品类留在本地</p>
      </div>
      <div className="source-branches">{["S₁", "S₂", "Sₙ"].map((name, i) => <div key={name}>
        {i === 2 && <div className="source-ellipsis" aria-label="其他源区域">⋮</div>}
        <article className="source-branch" data-flow={`source-${i}`}>
          <div className="source-user"><strong>{name}</strong><span>用户本地<br />OLH 扰动</span></div>
          <div className="source-transfer"><span>扰动<br />报告</span><span aria-hidden="true">→</span></div>
          <div className="source-publisher"><h4>区域发布者</h4><p>伪造报告筛查 · 频率与方差估计</p><span className="exchange-artifact">签名 Top-m 摘要</span></div>
        </article>
      </div>)}</div>
    </section>
    <div className="exchange-transfer" aria-label="发布者登记后向网关发送签名摘要"><span className="mobile-flow-arrow" aria-hidden="true">↓</span></div>
    <section className="exchange-target" aria-labelledby="target-heading">
      <div className="exchange-column-heading">
        <span className="exchange-input-label">签名摘要</span>
        <h3 id="target-heading">目标侧验证与融合</h3>
        <p className="exchange-caption">先核验来源，再限制恶意摘要的影响</p>
      </div>
      <article className="exchange-node" data-flow="gate"><h4>网关准入</h4>
        <p>签名与角色 · 窗口与域 · 格式<br />账本一致性 · 同源多摘要检查</p>
        <p className="exchange-defense"><b>协议检查</b>应对篡改、重放与冒充</p>
        <p className="exchange-rejection">不合格：拒收该摘要并记录原因</p>
      </article>
      <div className="exchange-down"><span aria-hidden="true">↓</span> 准入摘要</div>
      <article className="exchange-node" data-flow="fusion"><h4>鲁棒融合</h4>
        <p>留一共识截尾 · 多源支持<br />权重封顶 · 加权排序</p>
        <p className="exchange-defense"><b>网关防线</b>限制被攻破发布者的影响</p>
      </article>
    </section>
    <div className="exchange-transfer"><span className="mobile-flow-arrow" aria-hidden="true">↓</span></div>
    <section className="exchange-output" aria-labelledby="output-heading">
      <div className="exchange-column-heading">
        <span className="exchange-input-label">融合结果</span>
        <h3 id="output-heading">结果与审计</h3>
        <p className="exchange-caption">保留结论、原因与核对依据</p>
      </div>
      <article className="exchange-node" data-flow="result"><h4>三态结果</h4>
        <div className="exchange-states"><span className="state-NORMAL">检查通过</span><span className="state-DEGRADED">降级</span><span className="state-REFUSED">拒答</span></div>
        <p>三态表示检查结论，不代表准确度</p>
      </article>
      <div className="exchange-down"><span aria-hidden="true">↓</span> 记录结论及原因</div>
      <article className="exchange-node"><h4>审计记录</h4><p>摘要哈希 · 账本位置<br />准入记录 · 结论及原因</p></article>
    </section>
    <section className="exchange-trust" aria-labelledby="trust-heading">
      <h3 id="trust-heading">登记与核验依据</h3>
      <div className="exchange-trust-content">
        <div className="exchange-trust-card"><h4>密钥注册表</h4><p>保存主体与角色对应的公钥。<br />为发布登记和网关准入提供验签依据。</p></div>
        <div className="exchange-trust-card"><h4>预算账本</h4><p>登记前验签，按窗口累计隐私预算。<br />以哈希链记录摘要登记，供网关核验。</p></div>
      </div>
    </section>
  </div>;
}

function Protocol() {
  const marker = useId().replace(/:/g, "");
  return <details className="exchange-protocol">
    <summary>查看签名发布与准入过程</summary>
    <div className="protocol-roles" aria-hidden="true">{ROLES.map(role => <strong key={role}>{role}</strong>)}</div>
    <ol className="protocol-steps">{PROTOCOL.map((step, i) => {
      const start = step.from * 100 + 50, end = step.to * 100 + 50, self = start === end;
      const d = self ? `M${start},6 h26 v20 h-26` : `M${start},22 H${end}`;
      return <li key={i} className={`protocol-step protocol-${step.kind}`}>
        <div className="protocol-action"><span className="protocol-number">{i + 1}</span><span>{step.text}</span></div>
        <span className="protocol-participants">{ROLES[step.from]} {self ? "内部处理" : `→ ${ROLES[step.to]}`}</span>
        <svg viewBox="0 0 600 34" preserveAspectRatio="none" aria-hidden="true">
          <defs><marker id={`${marker}-${i}`} markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="currentColor" /></marker></defs>
          {ROLES.map((_, r) => <path key={r} d={`M${r * 100 + 50},0 V34`} className="protocol-lifeline" />)}
          <path d={d} className="protocol-message" markerEnd={`url(#${marker}-${i})`} />
        </svg>
      </li>;
    })}</ol>
  </details>;
}

export function Overview({ go }: { go: (tab: string) => void }) {
  return <div className="page overview-page">
    <section className="hero"><h1>PrivEdge：多源 LDP 摘要的抗投毒可信交换</h1><p>对多个来源的隐私摘要进行核验与融合，展示预测结果、攻击影响和审计记录。</p></section>
    <section className="card demo-guide" aria-labelledby="demo-heading">
      <header className="card-head"><h2 id="demo-heading">开始演示</h2></header>
      <div className="demo-shortcuts">
        <button onClick={() => go("demo-normal")}>正常交换</button>
        <button onClick={() => go("demo-hijack")}>投毒对比</button>
        <button onClick={() => go("demo-tamper")}>篡改检测</button>
        <button onClick={() => go("ledger")}>账本审计</button>
        <button onClick={() => go("experiments")}>实验结果</button>
      </div>
      <details className="help-details"><summary>演示操作说明</summary>
        <p>前三个入口只填参，不自动运行。进入后点击“开始预测”或“发起攻击”。也可以直接使用顶部导航。</p>
        <p>“正常交换”使用包内验证过的固定演示条件：当前数据集最后一个区域、ε=2、Top-m=40、每源1000、seed=1；它用于展示检查通过的完整流程，不代表总体预测效果。攻击入口优先带入当前数据集上一次正常运行的实际参数与种子。</p>
        <p>你操作目标网关。包内标准数据模拟多个发布者，不用上传个人数据。</p>
      </details>
    </section>
    <details className="exchange-section">
      <summary className="exchange-summary"><span>系统工作流程图</span><small>查看摘要如何核验、融合与审计</small></summary>
      <div className="exchange-content" aria-labelledby="exchange-heading">
        <div className="exchange-heading"><h2 id="exchange-heading">多源摘要可信交换架构</h2>
          <div className="exchange-key"><span><i /> 摘要传递</span><span><i className="dashed" /> 登记 / 核验</span></div>
        </div>
        <Architecture /><Protocol />
      </div>
    </details>
    <details className="card help-details" aria-labelledby="scope-heading">
      <summary id="scope-heading">技术说明与适用范围</summary>
      <p>{INTRO}</p>
      <p>OLH、Ed25519 等为已有基础组件；本作品将发布筛查、鲁棒融合、准入账本与可核对证据连接为防御流程。</p>
      <p>当前控制台在同进程中模拟多个来源及用户本地扰动；架构图展示角色与消息关系，不代表已部署独立设备上的分布式系统。真实身份与密钥管理、网络隔离和生产部署仍需单独设计与验证。</p>
      <p className="muted small">三态表示来源与一致性检查结论，不代表预测准确度；无攻击时不宣称比简单平均更准。理论条件与实验解释范围应一并核对。</p>
      <TheoryScope />
    </details>

  </div>;
}
