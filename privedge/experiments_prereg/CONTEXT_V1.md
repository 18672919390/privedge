# 预注册：上下文攻击与三态决策实验 v1

- 冻结时间：2026-09-29，在任何该实验结果产生之前
- 代码：`privedge/experiments/context_v1.py`
- 输出：`runs/context_v1_<dataset>/<run_id>/`
- 数据：Massive-STEPS（7 目标）与 Olist（6 目标，Gate A 有条件），两者同一脚本、同一参数各运行一次。

## 目的
两个数据集的 Gate D 都表明公开上下文带来的目标特异增益很弱甚至为负，而 Massive 上错配上下文会使 `robust_context` NDCG 下降 0.116。本实验检验：PrivEdge 的上下文验证（签名、区域绑定、类别域、因果时间、账本）加上三态决策，能否把"上下文是攻击面"的风险关掉，并量化剩余风险。

## 设置
- 抽样、扰动种子与 SECURITY_V1 相同；ε ∈ {1, 2}；种子 {101, 211, 307, 401, 503}；每源 5,000 用户；Top-20 发布，Top-10 评价。
- 每个（目标, 种子, ε）新建一个账本；每个源用真实 Ed25519 身份签名发布 D1 摘要（发布端过滤开启），每个区域用各自的上下文身份签名发布上下文。全部经 `ColdStartService.predict` 走真实网关。
- 目标窗口开始时刻：Massive 2013 窗 `2012-04-03T00:00:00Z`、2018 窗 `2017-10-03T00:00:00Z`（与已冻结的 OSM 快照时刻相同，快照严格早于首条签到）；Olist W2017 `2017-01-01`、W2018 `2018-01-01`。网关规则：快照不得晚于窗口开始时刻。
- 攻击目标类别：与 SECURITY_V1 同一抽取规则与种子（源平均排名 31–80 中抽 3 个）。

## 上下文场景
- C0 correct：目标区域自己的合法上下文。
- C1 swapped：另一区域合法签名的上下文（数据集预先冻结的错排表）被当作目标上下文提交。
- C2 forged_unsigned：在目标合法上下文上篡改数值，把 3 个攻击目标的值设为 1.5 × 该向量最大值后归一化，不重新签名。
- C3 forged_signed：同 C2 的数值，但由被攻破的目标上下文密钥合法签名并入账本（密钥泄露，残余风险）。
- C4 none：不提供上下文。
- R2 / R3 可用性：只有 2 / 3 个源的摘要通过网关（其余源提交上一窗口的旧摘要，被 STALE_WINDOW 拒绝），上下文为 C0。

## 对比系统
- naive：直接使用提交的上下文数值与全部源摘要，分别用团队原始 `censor_aware` 与 `robust_context`（server_budget=min(3, 源数)）。
- PrivEdge：网关 + `decide()`（DecisionPolicy 默认值：min_sources=3、t=2、clip_z=3、min_agreement=0.2）。

## 指标
- 网关对上下文的判定码分布；三态分布（NORMAL / DEGRADED / REFUSED）及原因码。
- Recall@10、NDCG@10；攻击成功率 AS（仅 C2/C3）。
- 统计单元为目标服务器（种子取平均），目标级 bootstrap 95% 区间（2000 次，seed 0）。

## 预先声明的判定
- J1 安全性（确定性）：C0 上下文 100% 通过；C1 100% 被拒且原因码为 CONTEXT_REGION_MISMATCH；C2 100% 被拒且为 SIGNATURE_INVALID。
- J2 状态正确性：C1/C2/C4 输出 DEGRADED 且含 CONTEXT_UNVERIFIED；R2 输出 REFUSED；C0 与 R3 若出现 DEGRADED，报告其原因码与比例（LOW_AGREEMENT 阈值 0.2 在此前固定，不因结果调整）。
- J3 错配损失消除：Massive 上 C1 条件下 PrivEdge 相对 naive-robust_context 的 NDCG 差，目标级区间下界 > 0。Olist 上下文本身无信息，只报告不判定。
- J4 伪造上下文：C2 下 PrivEdge 的 AS 不高于其 C0 的 AS；C3 下报告 naive 与 PrivEdge 的 AS 及区间，不预设通过标准（残余风险）。
- 任一条件不满足如实报告；修改须新建 v2 并在新种子或新数据上验证。
