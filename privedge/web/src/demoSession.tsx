import { createContext, useContext } from "react";
import type { DatasetInfo, ProgramIdentity, RunRequest, RunResult } from "./types";
import type { Drill, OriginalCheck } from "./ledgerDisplay";

export interface CompletedRun { result: RunResult; identity: ProgramIdentity | null; savedAt: string }
export interface SavedSweep {
  snapshot: RunRequest; rows: RunResult[]; total: number; complete: boolean;
  error?: string; identity: ProgramIdentity | null;
}
export interface PageSession {
  draft?: RunRequest; seedText?: string; completed?: CompletedRun;
  sweep?: SavedSweep; mode?: "single" | "sweep";
  drill?: { value: Drill; original: OriginalCheck | null; seq: number; identity: ProgramIdentity | null };
}
export type SessionPage = "coldstart" | "attack" | "ledger";
export interface DemoSessionValue {
  sessions: Record<string, PageSession>;
  patch: (dataset: string, page: SessionPage, patch: Partial<PageSession>) => void;
  identity: ProgramIdentity | null;
  captureIdentity: () => Promise<ProgramIdentity | null>;
}
export const DemoSessionContext = createContext<DemoSessionValue>({
  sessions: {}, patch: () => {}, identity: null, captureIdentity: async () => null,
});
export const sessionKey = (dataset: string, page: SessionPage) => `${dataset}:${page}`;
export const useDemoSession = () => useContext(DemoSessionContext);
export function defaultRequest(dataset: DatasetInfo, attack = "none"): RunRequest {
  return {dataset: dataset.name, target: dataset.servers[Math.min(3, dataset.servers.length - 1)].id,
    epsilon: attack === "none" ? 2 : 1, top_m: attack === "none" ? 40 : 20,
    users: 5000, attack, attackers: 1, beta: .1, seed: null};
}
export function parseSeed(text: string): { value: number | null; error: string } {
  const trimmed = text.trim();
  if (!trimmed) return {value: null, error: ""};
  if (!/^\d+$/.test(trimmed) || !Number.isSafeInteger(Number(trimmed))) {
    return {value: null, error: "种子须为非负整数，且不超过 9007199254740991；留空则随机。"};
  }
  return {value: Number(trimmed), error: ""};
}
export function resolvedRequest(result: RunResult): RunRequest | null {
  if (!result.request_snapshot) return null;
  return {...result.request_snapshot, dataset: result.dataset, target: result.target,
    epsilon: result.epsilon, top_m: result.top_m, users: result.users ?? result.request_snapshot.users, seed: result.seed};
}
export function requestMatches(request: RunRequest, result: RunResult): boolean {
  const actual = resolvedRequest(result);
  if (!actual) return false;
  return (["dataset", "target", "epsilon", "top_m", "users", "attack", "attackers", "beta"] as const)
    .every(key => request[key] === actual[key]) && (request.seed == null || request.seed === actual.seed);
}
export function transferNormal(result: RunResult, draft: RunRequest): RunRequest | null {
  const source = resolvedRequest(result);
  if (!source || source.attack !== "none" || source.dataset !== draft.dataset) return null;
  return {...draft, target: source.target, epsilon: source.epsilon, top_m: source.top_m, users: source.users, seed: source.seed};
}
