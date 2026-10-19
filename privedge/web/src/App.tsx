import { useCallback, useEffect, useState } from "react";
import { getJSON } from "./api";
import { DemoSessionContext, defaultRequest, sessionKey, transferNormal, type PageSession, type SessionPage } from "./demoSession";
import { useJSONResource } from "./useJSONResource";
import { AttackLab } from "./pages/AttackLab";
import { ColdStart } from "./pages/ColdStart";
import { Experiments } from "./pages/Experiments";
import { LedgerAudit } from "./pages/LedgerAudit";
import { Overview } from "./pages/Overview";
import type { DatasetInfo, ProgramIdentity, RunRequest } from "./types";

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
  const datasetResource = useJSONResource<DatasetInfo[]>("/api/datasets");
  const datasets = datasetResource.data ?? [];
  const [current, setCurrent] = useState("meituan_trd");
  const dataset = datasets.find((d) => d.name === current);
  const [sessions, setSessions] = useState<Record<string, PageSession>>({});
  const [identity, setIdentity] = useState<ProgramIdentity | null>(null);
  const patch = useCallback((name: string, page: SessionPage, values: Partial<PageSession>) => {
    setSessions(old => ({...old, [sessionKey(name, page)]: {...old[sessionKey(name, page)], ...values}}));
  }, []);
  const captureIdentity = useCallback(async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const value = await getJSON<ProgramIdentity>("/api/version", controller.signal);
      if (!value.release_id || !/^[a-f0-9]{64}$/i.test(value.source_fingerprint_sha256)) throw Error("版本未提供");
      setIdentity(value); return value;
    } catch { setIdentity(null); return null; }
    finally { clearTimeout(timer); }
  }, []);
  useEffect(() => { void captureIdentity(); }, [captureIdentity]);
  const go = (destination: string) => {
    if (destination.startsWith("demo-") && dataset) {
      const normal = destination === "demo-normal", page = normal ? "coldstart" : "attack";
      const attack = normal ? "none" : destination === "demo-tamper" ? "tamper" : "hijack";
      // The normal shortcut uses the fixed, package-verified pass example.
      // It is a reproducible operating demonstration, not a performance claim.
      let request: RunRequest = normal
        ? {...defaultRequest(dataset, attack), target: dataset.servers[dataset.servers.length - 1].id,
          epsilon: 2, top_m: 40, users: 1000, seed: 1}
        : {...defaultRequest(dataset, attack), epsilon: 1, top_m: 20, seed: 20260929};
      const previous = sessions[sessionKey(current, "coldstart")]?.completed;
      if (!normal && previous) request = transferNormal(previous.result, request) ?? request;
      patch(current, page, {draft: request, seedText: String(request.seed), mode: "single"});
      setTab(page); return;
    }
    if (TABS.some(([key]) => key === destination)) setTab(destination as Tab);
  };

  return (
    <DemoSessionContext.Provider value={{sessions, patch, identity, captureIdentity}}><div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo">◆</span> PrivEdge <small>多源 LDP 摘要的抗投毒可信交换</small></div>
        <nav aria-label="主导航">
          {TABS.map(([key, label]) => (
            <button key={key} aria-current={tab === key ? "page" : undefined} className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>{label}</button>
          ))}
        </nav>
        <select aria-label="当前数据集" title={dataset ? `${dataset.title} / ${dataset.role}` : "选择数据集"} className="dataset" value={current} disabled={datasetResource.loading || !datasets.length} onChange={(e) => setCurrent(e.target.value)}>
          {datasets.map((d) => <option key={d.name} value={d.name}>{d.title} · {d.role}</option>)}
        </select>
      </header>
      <main id="main-content">
        {dataset && tab !== "overview" && <p className="dataset-context">当前数据集：<strong>{dataset.title}</strong><span>{dataset.role}</span></p>}
        {datasetResource.loading && <p className="muted" role="status">正在加载数据集…</p>}
        {datasetResource.error && <p className="error" role="alert">后端未连接：{datasetResource.error}。<button onClick={datasetResource.retry}>重试连接</button></p>}
        {tab === "overview" && <Overview go={go} />}
        {tab === "coldstart" && dataset && <ColdStart key={dataset.name} dataset={dataset} />}
        {tab === "attack" && dataset && <AttackLab key={dataset.name} dataset={dataset} />}
        {tab === "ledger" && dataset && <LedgerAudit key={dataset.name} dataset={dataset} goToPrediction={() => setTab("coldstart")} />}
        {tab === "experiments" && <Experiments datasetName={current} selectDataset={setCurrent} />}
      </main>
      <footer className="program-version"><details><summary>{identity ? `程序 ${identity.release_id} / ${identity.application_version}` : "未获得程序版本"} · 查看可核对标识</summary>
        {identity && <><p>{identity.fingerprint_scope}</p><code>{identity.source_fingerprint_sha256}</code><p>共 {identity.fingerprint_file_count} 个程序文件；不是程序包签名或第三方认证。</p></>}
        <button onClick={() => void captureIdentity()}>重新读取程序标识</button></details></footer>
    </div></DemoSessionContext.Provider>
  );
}
