import type { RunRequest, RunResult } from "./types";

/** Client request lifetime only; cancellation does not stop server computation. */
export class SweepSession {
  private generation = 0;
  private controller?: AbortController;

  cancel() {
    this.generation += 1;
    this.controller?.abort();
    this.controller = undefined;
  }

  async run(snapshot: RunRequest, attacks: string[], execute: (request: RunRequest, signal: AbortSignal) => Promise<RunResult>, callbacks: {
    active: (attack: string) => void;
    row: (result: RunResult) => void;
    error: (attack: string, completed: number, reason: unknown) => void;
    finish: () => void;
  }) {
    this.cancel();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const current = () => generation === this.generation && !controller.signal.aborted;
    let completed = 0;
    let active = "";
    try {
      for (const attack of attacks) {
        if (!current()) return;
        active = attack;
        callbacks.active(attack);
        const result = await execute({ ...snapshot, attack }, controller.signal);
        if (!current()) return;
        callbacks.row(result);
        completed += 1;
      }
    } catch (reason) {
      if (current()) callbacks.error(active, completed, reason);
    } finally {
      if (current()) callbacks.finish();
    }
  }
}
