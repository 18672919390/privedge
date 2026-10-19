import type { PipelineEvent, RunRequest, RunResult } from "./types";

export async function getJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

export async function postJSON<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

/** Stream pipeline events over WebSocket; `pace` ms spaces out playback of the real, already-executed steps. */
export function runStream(
  request: RunRequest,
  onEvent: (event: PipelineEvent) => void,
  onResult: (result: RunResult) => void,
  onError: (message: string) => void,
  pace = 60,
): () => void {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/run`);
  const queue: (() => void)[] = [];
  let timer: number | undefined;
  let cancelled = false;
  let terminalReceived = false;
  let finished = false;
  const clear = () => {
    window.clearTimeout(timer);
    timer = undefined;
    queue.length = 0;
  };
  const fail = (message: string) => {
    if (cancelled || finished) return;
    finished = true;
    clear();
    onError(message);
    socket.close();
  };
  const pump = () => {
    if (cancelled || finished) return;
    const next = queue.shift();
    if (!next) {
      timer = undefined;
      return;
    }
    next();
    if (!cancelled && !finished) timer = window.setTimeout(pump, pace);
  };
  const schedule = (task: () => void) => {
    queue.push(task);
    if (timer === undefined) pump();
  };
  socket.onopen = () => { if (!cancelled) socket.send(JSON.stringify(request)); };
  socket.onmessage = (message) => {
    if (cancelled || finished || terminalReceived) return;
    try {
      const data = JSON.parse(message.data);
      if (data.kind === "event") schedule(() => onEvent(data.event));
      else if (data.kind === "result") {
        // The server may close before the paced event queue has reached the result.
        terminalReceived = true;
        schedule(() => { finished = true; onResult(data.result); socket.close(); });
      } else if (data.kind === "error") {
        terminalReceived = true;
        schedule(() => fail(String(data.error || "后端未能完成本次运行，请重试")));
      } else fail("收到无法识别的运行消息，请重试");
    } catch {
      fail("运行消息解析失败，请重试");
    }
  };
  socket.onerror = () => {
    if (!terminalReceived) fail("WebSocket 连接失败，请确认后端服务可用后重试");
  };
  socket.onclose = (event) => {
    if (!terminalReceived) fail(`运行连接已中断（关闭码 ${event.code}），未收到最终结果，请重试`);
  };
  return () => {
    cancelled = true;
    clear();
    socket.close();
  };
}
