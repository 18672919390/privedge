import type { PipelineEvent, ProgramIdentity, RunRequest, RunResult } from "./types";
import type { Drill, OriginalCheck, LedgerView } from "./ledgerDisplay";

type Row = Record<string, unknown>;
/** Explicit projections prevent future API fields (including secrets) from entering exports. */
function pick(value: object | undefined | null, fields: readonly string[]): Row {
  const source = (value ?? {}) as Row;
  return Object.fromEntries(fields.filter(key => source[key] !== undefined).map(key => [key, source[key]]));
}
const namedFields = ["category", "name", "support", "injected", "in_truth"];
const reasons = (rows?: {code: string; reason: string}[]) => (rows ?? []).map(row => pick(row, ["code", "reason"]));
const score = (row: object | undefined) => pick(row, ["recall", "ndcg", "attack_success"]);
export function publicIdentity(identity: ProgramIdentity | null) {
  if (!identity) return {status: "UNAVAILABLE", reason: "未获得版本，无法绑定本次程序指纹"};
  return {...pick(identity, ["release_id", "application_version", "source_fingerprint_sha256", "fingerprint_file_count", "fingerprint_scope"]),
    data_sha256: Object.fromEntries(Object.entries(identity.data_sha256 ?? {}).filter(([path, hash]) =>
      /^[a-z0-9_]+\/(domain\.json|private_events\.csv\.gz|public_context\.csv)$/.test(path) && /^[a-f0-9]{64}$/i.test(hash)))};
}
export const publicRequest = (request?: RunRequest | null) => pick(request, ["dataset", "target", "epsilon", "top_m", "users", "attack", "attackers", "beta", "seed"]);
export function publicEvent(event: PipelineEvent) {
  return pick(event, ["type", "t_ms", "source", "source_id", "code", "reason", "detail", "target", "window", "epsilon", "top_m", "users",
    "fake_users", "attackers", "release_id", "items", "removed_reports", "seq", "entry_hash", "spent", "state"]);
}
export function publicRun(result: RunResult) {
  return {...pick(result, ["run_id", "dataset", "target", "window", "seed", "epsilon", "top_m", "users", "attack", "attack_name", "attackers", "elapsed_ms"]),
    request_snapshot: publicRequest(result.request_snapshot),
    attack_targets: (result.attack_targets ?? []).map(row => pick(row, namedFields)),
    decision: {...pick(result.decision, ["state", "method", "agreement"]), reasons: reasons(result.decision.reasons), alerts: reasons(result.decision.alerts),
      top_k_named: result.decision.top_k_named.map(row => pick(row, namedFields))},
    baseline: {method: result.baseline?.method, top_k_named: (result.baseline?.top_k_named ?? []).map(row => pick(row, namedFields))},
    evaluation: {note: result.evaluation?.note, baseline: score(result.evaluation?.baseline), privedge: score(result.evaluation?.privedge),
      truth_top10: (result.evaluation?.truth_top10 ?? []).map(row => pick(row, namedFields))},
    sources: (result.sources ?? []).map(row => pick(row, ["source", "users", "fake_users", "removed_reports", "bad", "anomaly_score", "flagged", "rejected"])),
    audit: pick(result.audit, ["request_id", "record_hash", "ledger_head", "ledger_chain_ok"]),
    events: (result.events ?? []).map(publicEvent)};
}
function publicLedger(view?: LedgerView) {
  return view ? {...pick(view, ["total", "chain_ok", "first_bad", "head", "latest_window"]),
    latest_budget: view.latest_budget.map(row => pick(row, ["source_id", "window_id", "spent", "limit"]))} : null;
}
export function publicDrill(dataset: string, drill: Drill, original: OriginalCheck | null) {
  return {dataset, drill: pick(drill, ["edited_seq", "field", "from", "to", "chain_ok", "first_bad", "decision_state", "decision_reason", "error"]),
    original: original ? {pending: original.pending, error: original.error, before: publicLedger(original.before), after: publicLedger(original.after)} : null,
    scope: "副本演练及原链前后摘要；不含密钥注册表，不代表导出并校验完整账本。"};
}
export function publicA8(selected: {cells: object[]; methods: object[]; provenance?: Record<string, unknown>; [key: string]: unknown}, dataset: string, epsilon: number, scenario: string) {
  return {selection: {dataset, epsilon, scenario}, ...pick(selected, ["status", "reason", "evidence_id", "source_run_id", "target_count", "source_count", "users_per_source", "top_k", "limitations"]),
    methods: selected.methods.map(row => pick(row, ["id", "name", "definition"])),
    cells: selected.cells.filter(row => (row as Row).epsilon === epsilon && (row as Row).scenario === scenario)
      .map(row => pick(row, ["method", "epsilon", "scenario", "top_m", "sample_count", "ndcg", "recall", "attack_success", "ndcg_ci95", "recall_ci95", "attack_success_ci95", "refusal_rate", "seeds"])),
    provenance: pick(selected.provenance, ["source_manifest_sha256", "source_results_sha256", "summary_sha256", "audit_sha256", "review_id", "historical_preregistration_bound", "started_at", "finished_at", "code_combined"]),
    scope: "只读导出历史描述性结果，不重跑实验；严格登记状态请单独查看，不能由本导出推定 READY。"};
}
export function evidenceEnvelope(kind: string, payload: unknown, identity: ProgramIdentity | null, now = new Date().toISOString()) {
  return {schema_version: 1, kind, exported_at: now, program_identity: publicIdentity(identity),
    scope_note: "本文件为页面已获取证据的只读快照；指纹供程序文件比对，不是包签名、第三方认证或新的统计登记。", payload};
}
export function downloadEvidence(kind: string, id: string, payload: unknown, identity: ProgramIdentity | null) {
  const documentData = evidenceEnvelope(kind, payload, identity);
  const filename = `PrivEdge_${kind}_${id}_${documentData.exported_at}`.replace(/[^a-zA-Z0-9_\-.]/g, "_") + ".json";
  const url = URL.createObjectURL(new Blob([JSON.stringify(documentData, null, 2)], {type: "application/json;charset=utf-8"}));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
