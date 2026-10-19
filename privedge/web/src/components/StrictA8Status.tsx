import { useJSONResource } from "../useJSONResource";
import { Card } from "./common";

interface Registration {
  status: string; reason?: string; run_id?: string; evidence_id?: string;
  methods?: { name: string; status: string; reason?: string }[];
}
interface Response { status: string; reason?: string; datasets: Record<string, Registration> }
const labels: Record<string, string> = {
  NOT_RUN: "尚无严格登记运行", REGISTERED: "已登记", READY: "登记齐备",
  PARTIAL: "部分登记", INVALID: "登记核验失败",
};

export function StrictA8Status({ datasetName }: { datasetName: string }) {
  const resource = useJSONResource<Response>("/api/evidence/a8");
  const selected = resource.data?.datasets[datasetName];
  return <Card title="严格预注册绑定核验（A8）" className="strict-a8" extra={<button disabled={resource.loading} onClick={resource.retry}>重新读取并核对文件</button>}>
    <p className="muted small">此按钮只读取严格登记状态，不会运行实验或补登记。</p>
    {resource.loading ? <p role="status">正在核对严格登记…</p>
      : resource.error ? <p className="error" role="alert">严格登记读取失败：{resource.error}。<button onClick={resource.retry}>重试严格登记</button></p>
      : <><p><strong>{labels[selected?.status ?? ""] ?? "未提供"}</strong> <code>{selected?.status}</code>；当前数据集 {datasetName}；总体状态 {resource.data?.status}。</p>
          <p className="muted">严格入口：{selected?.reason ?? resource.data?.reason ?? "请结合登记运行及方法适用范围核对。"}</p>
          {Boolean(selected?.run_id || selected?.methods?.length) && <details><summary>查看严格登记详情</summary>
            <p className="small">运行：<code>{selected?.run_id ?? "未提供"}</code>；证据：{selected?.evidence_id ?? "未提供"}</p>
            {selected?.methods?.map(m => <p key={m.name}>{m.name}：{m.status === "NOT_APPLICABLE" ? "不适用" : labels[m.status] ?? m.status} <code>{m.status}</code>，{m.reason ?? "原因未提供"}</p>)}
          </details>}
        </>}
    <details className="help-details"><summary>严格登记状态说明</summary><p className="muted small">NOT_RUN 仅表示严格入口尚无相应登记，不代表没有上方四方法描述性结果。登记与哈希核验不独立证明预注册时间或算法优势。</p></details>
  </Card>;
}
