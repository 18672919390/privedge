import type { PipelineEvent, RunResult, Score } from "./types";

export const DEFENCES: Record<string, { brief: string; detail: string; bounded?: boolean }> = {
  none: { brief: "无攻击对照", detail: "不注入攻击，系统仍执行发布筛查、网关核验与鲁棒融合。" },
  mga: { brief: "发布端 · 联合支持过滤", detail: "利用 OLH 已知噪声结构检测联合支持异常的报告簇，剔除伪造用户报告。历史依据：SECURITY_V2。" },
  compromised: { brief: "网关 · 多源支持与留一共识截尾", detail: "候选品类需要至少 t=2 个来源支持；少于 t 个被攻破源无法注入任何诚实源均未发布的品类。依据：定理 1。" },
  hijack: { brief: "网关 · 权重封顶", detail: "κ=2，每个源的权重不超过其余源权重中位数的 2 倍。依据：定理 2；SECURITY_V4 为历史确认性证据。", bounded: true },
  demote: { brief: "网关 · 权重封顶与非负截尾", detail: "权重封顶 κ=2，截尾下限为 0，压低热门品类的影响受攻击者权重份额限制。依据：定理 2。", bounded: true },
  negative: { brief: "网关 · 非负截尾", detail: "将负频率截到 0，保证当前计算的单源贡献非负；不据此比较改变发布集合、留一统计量或权重后的反事实排序。依据：定理 2 引理 C。", bounded: true },
  tamper: { brief: "网关 · Ed25519 签名校验", detail: "核验签名，检测未重新签名的摘要篡改。历史形式化依据：ProVerif Q1。" },
  replay: { brief: "网关 · 签名窗口绑定", detail: "签名覆盖窗口号，拒收旧窗口摘要。历史形式化依据：ProVerif Q1、负对照 nc1。" },
  equivocation: { brief: "网关 · 同源多摘要检查", detail: "同一数据源在一次请求中提交多份摘要时全部拒收，避免重复计入支持来源。依据：定理 1 的前提。" },
  impostor: { brief: "网关 · 注册密钥与角色核验", detail: "密钥注册表绑定数据源主体与角色，拒收未注册密钥冒充的摘要。历史形式化依据：ProVerif Q1。" },
  budget_burn: { brief: "账本 · 登记前验签", detail: "账本登记前核验主体签名，第三方不能以他人名义扣除预算。历史形式化依据：ProVerif Q5、负对照 nc4。" },
};

export const SCENE_NOTE = "本页为当前参数下的现场运行；登记统计结果请在实验中心查看。检查通过、降级、拒答表示来源与一致性检查结论，不表示预测准确度等级。";

export function attackSuccessText(value: number | null | undefined, result: Pick<RunResult, "attack_targets">) {
  if (typeof value === "number" && Number.isFinite(value)) return `${(value * 100).toFixed(0)}%`;
  return result.attack_targets.length ? "未提供" : "不适用";
}

export function attackFraction(value: number | null | undefined, result: Pick<RunResult, "attack_targets">, items: RunResult["decision"]["top_k_named"]) {
  const targets = new Set(result.attack_targets.map(item => item.category));
  const hits = new Set(items.filter(item => targets.has(item.category)).map(item => item.category)).size;
  const available = typeof value === "number" && Number.isFinite(value);
  return {hits, total: targets.size, available,
    // The API rounds AS to four decimal places; retain its original value and
    // allow half a unit at that precision before flagging a different ratio.
    mismatch: available && targets.size > 0 && Math.abs(value - hits / targets.size) > .00005 + Number.EPSILON * 4,
    text: !targets.size ? "不适用" : !available ? "未提供" : `${hits}/${targets.size}（${(value * 100).toFixed(1)}%）`};
}

export function scoreValue(score: Score | undefined, key: keyof Score): number | null {
  const value = score?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function attackEvents(events: PipelineEvent[]) {
  return events.filter(event => event.type === "attack" || event.type === "reject");
}

/** Preserve each real message, grouping equal reason codes without losing multiplicity. */
export function rejectionGroups(events: PipelineEvent[]) {
  const groups = new Map<string, { code: string; reason: string; count: number }>();
  for (const event of events) {
    if (event.type !== "reject") continue;
    const code = String(event.code ?? "未提供原因码");
    const reason = String(event.reason ?? "未提供原因说明");
    const key = `${code}\0${reason}`;
    const group = groups.get(key);
    if (group) group.count += 1;
    else groups.set(key, { code, reason, count: 1 });
  }
  return [...groups.values()];
}
