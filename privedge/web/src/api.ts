import type { PipelineEvent, RunRequest, RunResult } from "./types";

export async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

export async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
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
  const pump = () => {
    const next = queue.shift();
    if (!next) {
      timer = undefined;
      return;
    }
    next();
    timer = window.setTimeout(pump, pace);
  };
  const schedule = (task: () => void) => {
    queue.push(task);
    if (timer === undefined) pump();
  };
  socket.onopen = () => socket.send(JSON.stringify(request));
  socket.onmessage = (message) => {
    const data = JSON.parse(message.data);
    if (data.kind === "event") schedule(() => onEvent(data.event));
    else if (data.kind === "result") schedule(() => { onResult(data.result); socket.close(); });
    else schedule(() => { onError(data.error); socket.close(); });
  };
  socket.onerror = () => onError("WebSocket 连接失败，请确认后端已在 8765 端口启动");
  return () => {
    window.clearTimeout(timer);
    socket.close();
  };
}
