import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

// Exercise the actual TypeScript transport with deterministic socket and playback timing.
// Browser end-to-end tests separately exercise the real server and React state.
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const require = createRequire(path.join(root, "privedge/web/package.json"));
const ts = require("typescript");
const sourcePath = path.join(root, "privedge/web/src/api.ts");
const source = ts.transpileModule(fs.readFileSync(sourcePath, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function harness() {
  let socket;
  let serial = 0;
  const timers = new Map();
  const calls = { events: [], results: [], errors: [] };
  class Socket {
    constructor(url) { this.url = url; this.sent = []; socket = this; }
    send(text) { this.sent.push(JSON.parse(text)); }
    close() { this.onclose?.({ code: 1000 }); }
    open() { this.onopen?.(); }
    receive(data) { this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) }); }
    disconnect(code = 1011) { this.onclose?.({ code }); }
    fail() { this.onerror?.(); }
  }
  const exports = {};
  vm.runInNewContext(source, {
    exports,
    location: { protocol: "http:", host: "127.0.0.1:8765" },
    WebSocket: Socket,
    window: {
      setTimeout(task) { const id = ++serial; timers.set(id, task); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
  });
  const request = { dataset: "olist_brazil", target: "SP", epsilon: 1, top_m: 20, users: 2000, attack: "none", attackers: 1, beta: 0.1 };
  const cancel = exports.runStream(request, (v) => calls.events.push(v), (v) => calls.results.push(v), (v) => calls.errors.push(v));
  const flush = () => {
    for (let n = 0; timers.size; n += 1) {
      assert.ok(n < 100, "playback must terminate");
      const [id, task] = timers.entries().next().value;
      timers.delete(id);
      task();
    }
  };
  return { socket, calls, cancel, flush, request };
}

const checks = [];
function check(name, run) {
  try { run(); checks.push({ name, passed: true }); }
  catch (error) { checks.push({ name, passed: false, error: String(error) }); }
}

check("early 1011 close reports interruption once", () => {
  const h = harness(); h.socket.open(); h.socket.disconnect(); h.flush();
  assert.equal(h.calls.errors.length, 1);
  assert.match(h.calls.errors[0], /1011.*未收到最终结果/);
  assert.equal(h.calls.results.length, 0);
});
check("error followed by close does not report twice", () => {
  const h = harness(); h.socket.fail(); h.socket.disconnect(); h.flush();
  assert.equal(h.calls.errors.length, 1);
});
check("normal close waits for queued result and event playback", () => {
  const h = harness(); h.socket.open();
  assert.equal(h.socket.sent[0].dataset, h.request.dataset);
  assert.equal(h.socket.sent[0].target, h.request.target);
  h.socket.receive({ kind: "event", event: { type: "start" } });
  h.socket.receive({ kind: "event", event: { type: "decision" } });
  h.socket.receive({ kind: "result", result: { run_id: "completed" } });
  h.socket.disconnect(1000); h.flush();
  assert.equal(h.calls.events.length, 2);
  assert.equal(h.calls.results.length, 1);
  assert.equal(h.calls.results[0].run_id, "completed");
  assert.equal(h.calls.errors.length, 0);
});
check("unmount cancellation suppresses queued and late callbacks", () => {
  const h = harness(); h.socket.open();
  h.socket.receive({ kind: "event", event: { type: "start" } });
  h.socket.receive({ kind: "event", event: { type: "decision" } });
  h.socket.receive({ kind: "result", result: { run_id: "old" } });
  h.cancel(); h.socket.receive({ kind: "event", event: { type: "late" } }); h.flush();
  assert.equal(h.calls.events.length, 1);
  assert.equal(h.calls.results.length, 0);
  assert.equal(h.calls.errors.length, 0);
});
check("cancel before connection does not send a request", () => {
  const h = harness(); h.cancel(); h.socket.open(); h.flush();
  assert.equal(h.socket.sent.length, 0);
  assert.equal(h.calls.errors.length, 0);
});
check("malformed JSON recovers with a readable error", () => {
  const h = harness(); h.socket.receive("{invalid"); h.flush();
  assert.equal(h.calls.errors.length, 1);
  assert.match(h.calls.errors[0], /解析失败/);
});
check("unknown message kind recovers with a readable error", () => {
  const h = harness(); h.socket.receive({ kind: "unknown" }); h.flush();
  assert.equal(h.calls.errors.length, 1);
  assert.match(h.calls.errors[0], /无法识别/);
});
check("server validation error survives close while queued", () => {
  const h = harness(); h.socket.receive({ kind: "event", event: { type: "start" } });
  h.socket.receive({ kind: "error", error: "invalid target" });
  h.socket.disconnect(1000); h.flush();
  assert.equal(h.calls.errors.length, 1);
  assert.equal(h.calls.errors[0], "invalid target");
});
check("duplicate terminal messages cannot overwrite a result", () => {
  const h = harness(); h.socket.receive({ kind: "result", result: { run_id: "first" } });
  h.socket.receive({ kind: "result", result: { run_id: "second" } }); h.flush();
  assert.equal(h.calls.results.length, 1);
  assert.equal(h.calls.results[0].run_id, "first");
  assert.equal(h.calls.errors.length, 0);
});
const result = { test: "actual runStream transport with deterministic WebSocket lifecycle", passed: checks.filter((v) => v.passed).length, total: checks.length, checks };
fs.writeFileSync(process.env.PRIVEDGE_RUNSTREAM_OUTPUT || path.join(here, "runstream_results.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
if (result.passed !== result.total) process.exitCode = 1;
