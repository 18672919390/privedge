# 预注册：自适应"权重劫持"攻击与权重封顶防御（SECURITY_V3）

- 冻结时间：2026-09-29，在任何 v3 结果产生之前。冒烟运行只检查退出码，不查看结果。
- 代码：`privedge/experiments/security_v3.py`；攻击 `attacks.weight_hijack_items`；防御 `robust.capped_weights` + `DecisionPolicy.weight_cap`
- 输出：`runs/security_v3_<dataset>/<run_id>/`
- 数据：Massive-STEPS（7 目标）、Olist（6 目标）、美团 TRD（11 目标），各运行一次。

## 动机（设计审查发现，非实验结果）
主线融合按发布者自报方差加权（权重 = 1/√平均方差）。自报方差受发布者控制：被攻破的合法发布者只需把方差缩小为 1/10⁴，权重就会放大约 100 倍。v2 的截尾只限制频率，不限制权重，因此这是 v2 未覆盖的自适应攻击。

## 攻击场景（与 v2 相同的抽样、扰动、种子、目标抽取与被攻破源选择规则）
- `clean`
- `compromised_1src`、`compromised_2src`：v2 原样（对照）
- `hijack_1src`、`hijack_2src`：注入 3 个目标（取该源最高频率），并把全部自报方差 ×10⁻⁴
- `demote_1src`：在 hijack 的基础上，再扣下自己排名最高的 7 个诚实类别（可用性攻击：把真实热门挤出结果）
- `mga_1src_b0.10`：检查新防御不破坏 v2 的结论

ε ∈ {1, 2}；每源 5,000 用户；Top-20 发布；Top-10 评价。

## 防御臂
- D0：`variance_weighted`（无防御）
- D3：v2 主线（发布端过滤 + 截尾 + t=2）
- D4：D3 + 权重封顶，即每个源的权重不超过其余源权重中位数的 κ 倍，**κ=2 预先固定，不调参**

## 判定（逐数据集）
- H1 有效：在 D3 攻击成功率 ≥ 0.1 的 hijack 单元（hijack_1src、hijack_2src、demote_1src × ε）中，D4−D3 攻击成功率差的目标级 95% 区间上界 < 0。
- H2 可用性：demote_1src 场景下，D4 的 NDCG@10 高于 D3（D4−D3 区间下界 > 0），或两者与 clean D3 的差都 ≥ −0.02。
- H3 代价：clean 场景 D4−D3 的 NDCG@10 均值 ≥ −0.02，且区间下界 ≥ −0.04。
- H4 不回退：compromised 与 MGA 场景下，D4 的攻击成功率均值不高于 D3 + 0.02。

## 采用规则
H1、H3 均满足（三套数据）时，D4 成为 v4.1 主线默认配置（`DecisionPolicy.weight_cap=2.0`）。否则保留 D3，把权重劫持写为已知局限。不满足的结果如实报告，不在同一批数据上调整 κ 后重跑。
