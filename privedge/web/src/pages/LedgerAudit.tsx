import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { getJSON, postJSON } from "../api";
import { useJSONResource } from "../useJSONResource";
import { Chart } from "../components/Chart";
import { Card, HashValue, Reasons, StateBadge } from "../components/common";
import { budgetEmptyText, budgetOption, canDrill, chainText, numberText, rejectionSummary, verificationText } from "../ledgerDisplay";
import type { AuditRecord, Drill, LedgerView, OriginalCheck } from "../ledgerDisplay";
import type { DatasetInfo } from "../types";
import { sessionKey, useDemoSession } from "../demoSession";
import { EvidenceDownload } from "../components/RunActions";
import { publicDrill } from "../evidenceExport";

export function LedgerAudit({ dataset, goToPrediction }: { dataset: DatasetInfo; goToPrediction: () => void }) {
  const store = useDemoSession(), saved = store.sessions[sessionKey(dataset.name, "ledger")]?.drill;
  const url = `/api/ledger/${dataset.name}`;
  const ledger = useJSONResource<LedgerView>(url);
  const auditRecords = useJSONResource<AuditRecord[]>(`/api/audit/${dataset.name}`);
  const [drill, setDrill] = useState<Drill | null>(saved?.value ?? null);
  const [original, setOriginal] = useState<OriginalCheck | null>(saved?.original ?? null);
  const [seq, setSeq] = useState(saved?.seq ?? 0);
  const drillIdentity = useRef(saved?.identity ?? null);
  const [drilling, setDrilling] = useState(false);
  const [drillError, setDrillError] = useState("");
  const controllerRef = useRef<AbortController>();
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; controllerRef.current?.abort(); }, []);
  const view = ledger.data;
  const busy = drilling || !!original?.pending;
  const enabled = canDrill(view, seq, ledger.loading, ledger.error, busy);
  const budget = view?.latest_budget ?? [];
  const option = useMemo(() => budgetOption(view?.latest_budget ?? []), [view]);
  const clearDrill = (clearResult = false) => {
    generation.current++; controllerRef.current?.abort();
    if (clearResult) {setDrill(null); setOriginal(null); store.patch(dataset.name, "ledger", {drill: undefined});}
    setDrillError(""); setDrilling(false);
  };
  const refreshLedger = () => { clearDrill(); ledger.retry(); };
  const refresh = () => { refreshLedger(); auditRecords.retry(); };
  const readOriginal = async (before: LedgerView, controller: AbortController, token: number, completedDrill = drill) => {
    setOriginal({ before, pending: true });
    try {
      const after = await getJSON<LedgerView>(url, controller.signal);
      if (!controller.signal.aborted && generation.current === token) {
        const check = {before, after, pending: false}; setOriginal(check);
        if (completedDrill) store.patch(dataset.name, "ledger", {drill: {value: completedDrill, original: check, seq: completedDrill.edited_seq, identity: drillIdentity.current}});
        ledger.retry(); auditRecords.retry();
      }
    } catch (reason) {
      if (!controller.signal.aborted && generation.current === token) {
        const check = {before, pending: false, error: String(reason)}; setOriginal(check);
        if (completedDrill) store.patch(dataset.name, "ledger", {drill: {value: completedDrill, original: check, seq: completedDrill.edited_seq, identity: drillIdentity.current}});
      }
    }
  };
  const runDrill = async () => {
    if (!enabled || !view) return;
    const before = view;
    clearDrill();
    const token = generation.current, controller = new AbortController();
    controllerRef.current = controller; setDrilling(true);
    try {
      const identity = await store.captureIdentity();
      if (controller.signal.aborted || generation.current !== token) return;
      drillIdentity.current = identity;
      const result = await postJSON<Drill>(`${url}/tamper-drill?seq=${seq}`, undefined, controller.signal);
      if (controller.signal.aborted || generation.current !== token) return;
      if (result.error) { setDrillError(result.error); return; }
      setDrill(result);
      store.patch(dataset.name, "ledger", {drill: {value: result, original: {before, pending: false, error: "尚未完成原账本复核"}, seq: result.edited_seq, identity}});
      await readOriginal(before, controller, token, result);
    } catch (reason) {
      if (!controller.signal.aborted && generation.current === token) setDrillError(String(reason));
    } finally {
      if (!controller.signal.aborted && generation.current === token) setDrilling(false);
    }
  };
  const retryOriginal = () => {
    if (!original || busy) return;
    controllerRef.current?.abort();
    const controller = new AbortController(); controllerRef.current = controller;
    void readOriginal(original.before, controller, ++generation.current);
  };
  return <div className="page ledger-page">
    <Card title="隐私预算账本" headingLevel={1} extra={<button disabled={ledger.loading || auditRecords.loading || busy} onClick={refresh}>刷新</button>}>
      <p className="muted small">当前账本：{dataset.title}（{dataset.name}）</p>
      <details className="help-details"><summary>账本保存与刷新说明</summary><p className="muted small">账本由当前服务保存在内存中。刷新这里只重新读取；刷新网页清空页面记录，重启服务才清空内存账本。下方保留的副本演练是当时快照，不替代最新账本。</p></details>
      {ledger.loading && <p role="status">正在加载账本完整性与预算…</p>}
      {ledger.error && <p className="error" role="alert">账本加载失败：{ledger.error}。<button onClick={refreshLedger}>重试账本</button></p>}
      {view && <div className="ledger-summary">
        <div className="ledger-integrity"><span className="muted">完整性检查</span><strong className={!view.total ? "muted" : view.chain_ok ? "ok" : "danger-text"}>{chainText(view)}</strong></div>
        <dl className="ledger-facts"><div><dt>账本条目</dt><dd>{numberText(view.total)}</dd></div><div><dt>注册密钥</dt><dd>{numberText(view.registry.length)}</dd></div><div><dt>链头哈希</dt><dd><HashValue value={view.head} /></dd></div></dl>
      </div>}
      {view && view.total > 0 && <p className="muted small">审计结论：{view.chain_ok ? `链校验通过 ${view.total} / ${view.total} 条` : chainText(view)}；链头 <HashValue value={view.head} />。</p>}
      {view && !view.total && !ledger.loading && !ledger.error && <div className="empty-state"><p>当前尚无业务记录；空链校验完整不代表已有交易通过审计。</p><button className="primary" onClick={goToPrediction}>前往冷启动预测</button></div>}
    </Card>
    <Card title="账本条目（最近 300 条）">
      {ledger.loading && <p role="status">正在加载账本条目…</p>}
      {ledger.error && <p className="error">账本条目读取失败，请重试账本。</p>}
      {view && !view.entries.length && <p className="empty-state">暂无账本条目。</p>}
      {!!view?.entries.length && <div className="scroll ledger-entries" tabIndex={0} role="region" aria-label="账本条目"><table className="table small"><thead><tr><th className="numeric">序号</th><th>类型</th><th>主体</th><th>窗口</th><th className="numeric">ε</th><th>信封摘要</th><th>前一哈希</th><th>本条哈希</th></tr></thead><tbody>{view.entries.slice().reverse().map(e => <tr key={e.seq}><td className="numeric">{e.seq}</td><td>{e.kind}</td><td>{e.principal}</td><td>{e.window_id}</td><td className="numeric">{numberText(e.epsilon)}</td><td><HashValue value={e.envelope_digest} /></td><td><HashValue value={e.prev_hash} /></td><td><HashValue value={e.entry_hash} /></td></tr>)}</tbody></table></div>}
    </Card>
    <Card title={view?.latest_window ? `最新窗口 ${view.latest_window} 的预算消耗` : "最新窗口预算"} className="ledger-budget">
      {ledger.loading ? <p role="status">正在加载最新窗口预算…</p>
        : ledger.error ? <p className="error">预算读取失败，请重试账本。</p>
        : !budget.length ? <p className="empty-state">{budgetEmptyText(view?.latest_window)}</p>
        : <Chart option={option} height={Math.max(300, budget.length * 44 + 70)} title="最新窗口逐来源预算" description="逐来源已用预算与各自窗口上限" showDescription={false} dataTable={<div className="table-scroll" tabIndex={0} role="region" aria-label="逐来源预算数据"><table className="table"><thead><tr><th>来源</th><th>窗口</th><th className="numeric">已用 ε</th><th className="numeric">上限 ε</th></tr></thead><tbody>{budget.map(b => <tr key={`${b.source_id}-${b.window_id}`}><td>{b.source_id}</td><td>{b.window_id}</td><td className="numeric">{numberText(b.spent)}</td><td className="numeric">{numberText(b.limit)}</td></tr>)}</tbody></table></div>} />}
      <details className="help-details"><summary>预算计算与窗口说明</summary>
      <p className="muted small">同一窗口内的多次发布按顺序组合累加；账本在登记前验签，第三方无法以他人名义扣预算。</p>
      <p className="muted small">本演示每次运行创建新窗口；图中仅为最新窗口，不是跨窗口的总隐私消耗。跨窗口用户是否重叠依赖部署假设，本演示不核验。</p>
      </details>
    </Card>
    <Card title="网关审计记录" extra={<button disabled={auditRecords.loading} onClick={auditRecords.retry}>刷新审计</button>}>
      {auditRecords.loading && <p role="status">正在加载审计记录…</p>}
      {auditRecords.error && <p className="error" role="alert">审计记录加载失败：{auditRecords.error}。<button onClick={auditRecords.retry}>重试审计</button></p>}
      {!auditRecords.loading && !auditRecords.error && !auditRecords.data?.length && <p className="empty-state">暂无请求审计记录。</p>}
      {!!auditRecords.data?.length && <AuditTable records={auditRecords.data} />}
    </Card>
    <Card title="副本篡改演练" className="ledger-drill">
      <div className="row ledger-drill-controls"><label className="inline-label">记录序号<input aria-label="篡改演练记录序号" type="number" min={0} max={Math.max(0, (view?.total ?? 1) - 1)} value={Number.isFinite(seq) ? seq : ""} disabled={busy || ledger.loading || !!ledger.error || !view?.total} onChange={event => { clearDrill(); setSeq(event.target.value === "" ? NaN : Number(event.target.value)); }} /></label>
        <button className="primary" disabled={!enabled} onClick={runDrill}>{busy ? "演练与复核中…" : "执行演练"}</button></div>
      <p className="muted small">仅修改账本副本中的 ε；记录序号从 0 开始。完成后重新读取原账本，核对条目数、链头与完整性。</p>
      <p className="muted small">本演练只校验账本副本，不涉及来源准入，因此没有接受/拒收数。</p>
      {ledger.loading ? <p className="muted">正在读取账本，读取完成后可执行演练。</p> : ledger.error ? <p className="error">账本读取失败，暂不能演练。请先重试账本。</p> : !view?.total ? <p className="empty-state">暂无可演练记录。</p> : (!Number.isInteger(seq) || seq < 0 || seq >= view.total) ? <p className="error">请输入 0 至 {view.total - 1} 的整数序号。</p> : null}
      {drillError && <p className="error" role="alert">演练失败：{drillError}。<button disabled={!enabled} onClick={runDrill}>重试演练</button></p>}
      {!drill && !drillError && !!view?.total && <p className="ledger-drill-placeholder muted">选择一条记录，查看修改内容、链上断点与副本请求结论。</p>}
      {drill && <><p className="muted small">以下为上次已完成的副本演练；修改序号不会改写这份结果。</p><DrillResult drill={drill} />
        <div className="row"><EvidenceDownload kind="ledger_drill" id={`${dataset.name}_${drill.edited_seq}`} identity={drillIdentity.current} disabled={busy} payload={() => publicDrill(dataset.name, drill, original)} />
          <button disabled={busy} onClick={() => clearDrill(true)}>清空演练记录</button></div></>}
      {original && <section className="original-check" aria-live="polite"><h3>原账本复核</h3>
        {original.pending ? <p role="status">正在重新读取原账本…</p> : original.error ? <p className="error" role="alert">原账本复核未完成：{original.error}。<button onClick={retryOriginal}>重试复核</button></p> : original.after && <>
          <p className={original.after.chain_ok ? "muted" : "error"}>{verificationText(original.before, original.after)}</p>
          <dl className="ledger-check-values"><div><dt>条目数（前 / 后）</dt><dd>{numberText(original.before.total)} / {numberText(original.after.total)}</dd></div><div><dt>复核完整性</dt><dd>{chainText(original.after)}</dd></div><div><dt>演练前链头</dt><dd><HashValue value={original.before.head} /></dd></div><div><dt>演练后链头</dt><dd><HashValue value={original.after.head} /></dd></div></dl>
        </>}
      </section>}
    </Card>    <details className="card ledger-registry"><summary>密钥注册表<span className="muted small">主体与角色绑定</span></summary>
      {ledger.loading ? <p role="status">正在加载密钥注册表…</p> : ledger.error ? <p className="error">密钥注册表读取失败，请重试账本。</p> : !view?.registry.length ? <p className="empty-state">暂无注册密钥。</p> : <div className="scroll" tabIndex={0} role="region" aria-label="密钥注册表"><table className="table small"><thead><tr><th>密钥</th><th>主体</th><th>角色</th><th>状态</th><th>公钥</th></tr></thead><tbody>{view.registry.map(k => <tr key={k.key_id}><td>{k.key_id}</td><td>{k.principal}</td><td>{k.role}</td><td>{k.revoked ? "已吊销" : "有效"}</td><td><HashValue value={k.public_key} /></td></tr>)}</tbody></table></div>}
    </details>
  </div>;
}

export function DrillResult({ drill }: { drill: Drill }) {
  return <>
  <ol className="ledger-drill-steps">
    <li><h3>修改内容</h3><p>第 {drill.edited_seq} 条{drill.entry_principal ? ` · 主体 ${drill.entry_principal}` : ""}{drill.entry_window ? ` · 窗口 ${drill.entry_window}` : ""} · {drill.field === "epsilon" ? "隐私预算 ε" : drill.field}</p><p className="ledger-edit-value">{numberText(drill.from)} <span className="muted">→</span> {numberText(drill.to)}</p></li>
    <li><h3>完整性检查</h3><p className={drill.chain_ok ? "warn-text" : "danger-text"}>{drill.chain_ok ? "副本仍通过校验（非预期，请核查）" : drill.first_bad == null ? "副本校验失败，断点未提供" : `副本校验失败，首个断点位于第 ${drill.first_bad} 条`}</p></li>
    <li><h3>副本请求结论</h3><StateBadge state={drill.decision_state ?? "未提供"} /><p>{drill.decision_reason === "LEDGER_CORRUPTED" ? "账本完整性校验失败，拒绝使用该副本输出推荐。" : "原因说明未提供。"}{drill.decision_reason && <code>{drill.decision_reason}</code>}</p>{drill.decision_state !== "REFUSED" && <p className="warn-text">非预期结果，请核查。</p>}</li>
  </ol>
  <p className="muted small">副本共 {numberText(drill.total)} 条；本演练不涉及来源准入，接受/拒收不适用。</p>
  </>;
}

export function AuditTable({ records }: { records: AuditRecord[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setExpanded(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  return <div className="scroll ledger-audits" tabIndex={0} role="region" aria-label="网关审计记录"><table className="table"><thead><tr><th>请求编号</th><th>类型</th><th>目标</th><th className="numeric">接受</th><th className="numeric">拒收</th><th>检查结论</th><th>核对依据</th></tr></thead><tbody>{records.map(a => <Fragment key={a.request_id}><tr><td className="mono">{a.request_id}</td><td>{a.kind === "ledger_drill" ? "演练" : "预测"}</td><td>{a.target_region}</td><td className="numeric">{numberText(a.admission.accepted.length)}</td><td className="numeric">{numberText(a.admission.rejected.length)}</td><td><StateBadge state={a.decision.state} /></td><td><button aria-expanded={expanded.has(a.request_id)} onClick={() => toggle(a.request_id)}>{expanded.has(a.request_id) ? "收起详情" : "查看详情"}</button></td></tr>
    {expanded.has(a.request_id) && <tr><td colSpan={7}><AuditDetail record={a} /></td></tr>}
  </Fragment>)}</tbody></table></div>;
}
export function AuditDetail({ record: a }: { record: AuditRecord }) {
  return <div className="audit-detail">{a.kind === "ledger_drill" && <p className="muted small">本次为副本演练：拒答针对账本副本，原账本未改动；演练不涉及来源准入。</p>}<section><h3>准入与结论</h3><p>接受来源：{a.admission.accepted.join("、") || "无"}</p>
    {a.admission.rejected.length ? <><ul className="ledger-rejections">{rejectionSummary(a.admission.rejected).map(r => <li key={`${r.code}-${r.reason}`}>{r.reason}<code>{r.code}</code><span>共 {r.count} 次</span></li>)}</ul><details><summary>逐来源拒收记录</summary><ul>{a.admission.rejected.map((r, i) => <li key={i}>{r.source_id}：{r.reason || "接口未提供中文解释"}<code>{r.code}</code></li>)}</ul></details></> : <p className="muted">未返回摘要拒收记录。</p>}
    <Reasons reasons={a.decision.reasons ?? []} alerts={a.decision.alerts} /></section>
    <section><h3>追溯依据</h3><dl className="ledger-check-values"><div><dt>记录时间</dt><dd>{a.at || "未提供"}</dd></div><div><dt>请求时账本校验</dt><dd>{a.ledger_chain_ok == null ? "未提供" : a.ledger_chain_ok ? "完整" : a.ledger_first_bad == null ? "失败，断点未提供" : `第 ${a.ledger_first_bad} 条断裂`}</dd></div><div><dt>账本链头</dt><dd><HashValue value={a.ledger_head} /></dd></div><div><dt>审计记录哈希</dt><dd><HashValue value={a.record_hash} /></dd></div></dl><details><summary>输入摘要（{numberText(a.inputs?.length)}）</summary>{a.inputs?.length ? <ul>{a.inputs.map((hash, i) => <li key={`${hash}-${i}`}><HashValue value={hash} /></li>)}</ul> : <p className="muted">未提供输入摘要。</p>}</details></section>
  </div>;
}
