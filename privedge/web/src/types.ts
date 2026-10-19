export interface DatasetInfo {
  name: string;
  title: string;
  role: string;
  domain: number;
  servers: { id: string; users: number }[];
  attacks: Record<string, string>;
}

export interface NamedItem {
  category: number;
  name: string;
  support?: number | null;
  injected?: boolean;
  in_truth?: boolean;
}

export interface PipelineEvent {
  type: "start" | "collect" | "attack" | "release" | "ledger" | "reject" | "admit" | "decision";
  t_ms: number;
  source?: string;
  source_id?: string;
  code?: string;
  reason?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface Score {
  recall: number;
  ndcg: number;
  attack_success: number | null;
}

export interface Reason {
  code: string;
  reason: string;
}

export interface SourceRow {
  source: string;
  users: number;
  fake_users: number;
  removed_reports: number;
  bad: boolean;
  anomaly_score?: number;
  flagged?: boolean;
  rejected?: string;
}

export interface RunResult {
  /** Client-side snapshot of the completed request; not a backend API field. */
  request_snapshot?: RunRequest;
  run_id: string;
  dataset: string;
  target: string;
  window: string;
  seed: number;
  epsilon: number;
  top_m: number;
  users?: number;
  attack: string;
  attack_name: string;
  attackers: string[];
  attack_targets: NamedItem[];
  decision: {
    state: "NORMAL" | "DEGRADED" | "REFUSED";
    method: string;
    reasons: Reason[];
    alerts: Reason[];
    agreement: number;
    top_k_named: NamedItem[];
  };
  baseline: { method: string; top_k_named: NamedItem[] };
  evaluation: { note: string; privedge: Score; baseline: Score; truth_top10: NamedItem[] };
  sources: SourceRow[];
  audit: { request_id: string; record_hash: string; ledger_head: string; ledger_chain_ok: boolean };
  elapsed_ms: number;
  events: PipelineEvent[];
}

export interface RunRequest {
  dataset: string;
  target: string;
  epsilon: number;
  top_m: number;
  users: number;
  attack: string;
  attackers: number;
  beta: number;
  seed?: number | null;
}

export interface ProgramIdentity {
  release_id: string;
  application_version: string;
  source_fingerprint_sha256: string;
  fingerprint_file_count: number;
  fingerprint_scope: string;
  data_sha256: Record<string, string>;
}
