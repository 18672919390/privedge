import { useEffect, useState } from "react";
import { getJSON } from "./api";
import { AttackLab } from "./pages/AttackLab";
import { ColdStart } from "./pages/ColdStart";
import { Experiments } from "./pages/Experiments";
import { LedgerAudit } from "./pages/LedgerAudit";
import { Overview } from "./pages/Overview";
import type { DatasetInfo } from "./types";

const TABS = [
  ["overview", "总览"],
  ["coldstart", "冷启动预测"],
  ["attack", "攻防实验室"],
  ["ledger", "账本审计"],
  ["experiments", "实验中心"],
] as const;
type Tab = (typeof TABS)[number][0];

export function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [current, setCurrent] = useState("meituan_trd");
  const [error, setError] = useState("");
  useEffect(() => { getJSON<DatasetInfo[]>("/api/datasets").then(setDatasets).catch((e) => setError(String(e))); }, []);
  const dataset = datasets.find((d) => d.name === current);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo">◆</span> PrivEdge <small>隐私保护的新区域开站选品</small></div>
        <nav>
          {TABS.map(([key, label]) => (
            <button key={key} className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>{label}</button>
          ))}
        </nav>
        <select className="dataset" value={current} onChange={(e) => setCurrent(e.target.value)}>
          {datasets.map((d) => <option key={d.name} value={d.name}>{d.title} · {d.role}</option>)}
        </select>
      </header>
      <main>
        {error && <p className="error">后端未连接：{error}</p>}
        {tab === "overview" && <Overview go={(t) => setTab(t as Tab)} />}
        {tab === "coldstart" && dataset && <ColdStart dataset={dataset} />}
        {tab === "attack" && dataset && <AttackLab dataset={dataset} />}
        {tab === "ledger" && dataset && <LedgerAudit dataset={dataset} />}
        {tab === "experiments" && <Experiments />}
      </main>
      <footer>PrivEdge · 本队自有原始代码 · 数据：美团 TRD（CC BY 4.0）、Olist、Massive-STEPS · 所有实验数字均可追溯到运行目录</footer>
    </div>
  );
}
