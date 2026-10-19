import { useState } from "react";
import { downloadEvidence, publicRun } from "../evidenceExport";
import { requestMatches, resolvedRequest, type CompletedRun } from "../demoSession";
import type { ProgramIdentity, RunRequest } from "../types";

export function EvidenceDownload({kind, id, payload, identity, label = "下载本次记录 JSON", disabled = false}: {
  kind: string; id: string; payload: () => unknown; identity: ProgramIdentity | null; label?: string; disabled?: boolean;
}) {
  const [error, setError] = useState("");
  return <span className="evidence-download"><button disabled={disabled} onClick={() => {try {
    downloadEvidence(kind, id, payload(), identity); setError("");
  } catch {setError("下载未完成，请重试。");}}}>{label}</button>{error && <span role="alert" className="error">{error}</span>}</span>;
}
export function RunActions({completed, draft, busy, replay, clear}: {
  completed: CompletedRun; draft: RunRequest; busy: boolean; replay: (request: RunRequest) => void; clear: () => void;
}) {
  const request = resolvedRequest(completed.result);
  return <section className="saved-result-note" aria-label="已完成结果与操作">
    <p><strong>上一次已完成结果</strong> · <code>{completed.result.run_id}</code> · {completed.savedAt}
      {!requestMatches(draft, completed.result) && <span className="warn-text"> · 当前参数尚未运行，以下仍是上次结果。</span>}
      {busy && <span className="warn-text"> · 新请求执行中，以下旧结果不代表新请求。</span>}</p>
    <div className="row"><button disabled={busy || !request} onClick={() => request && replay(request)}>使用这次参数和种子再运行</button>
      <EvidenceDownload kind="single" id={completed.result.run_id} payload={() => publicRun(completed.result)} identity={completed.identity} />
      <button disabled={busy} onClick={clear}>清空本页结果</button></div>
    <p className="muted small">页面内存保留已完成结果；刷新网页会清空页面记录。清空本页不清账本。重放会生成新窗口、编号和审计哈希。
      {completed.identity ? ` 程序 ${completed.identity.release_id} / ${completed.identity.application_version}，指纹随记录导出。` : " 未获得本次程序版本。"}</p>
  </section>;
}
