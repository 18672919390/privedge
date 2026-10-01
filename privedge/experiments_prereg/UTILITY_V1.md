# 预注册：隐私—效用与参数敏感性 v1（无攻击）

- 冻结时间：2026-09-29，在任何该实验结果产生之前
- 代码：`privedge/experiments/utility_v1.py`
- 输出：`runs/utility_v1_<dataset>/<run_id>/`
- 数据：Massive-STEPS、Olist、美团 TRD。

## 设置
- 每源 5,000 用户；种子 {101, 211, 307, 401, 503}；抽样与扰动种子布局与 SECURITY_V1 相同（ε 索引取自 [0.5, 1, 2, 4]）。
- 主网格：ε ∈ {0.5, 1, 2, 4} × 发布 Top-m ∈ {10, 20, 40}，使用全部源。
- 源数量敏感性：ε ∈ {1, 2}、m=20，源数 r ∈ {3, 5, 全部}；子集由种子 `SeedSequence([seed, target_index, 777])` 的排列取前 r 个。
- 评价 Top-10；目标真值只用于离线评价。

## 方法
- 非隐私参照：各源真实分布的平均，取 Top-10（不经 LDP；给出上界参照）。
- `average`、`variance_weighted`（团队原始融合，基于 LDP 摘要）。
- PrivEdge：发布端过滤开启 + `decide()` 默认策略（无上下文），记录输出状态；REFUSED 时 Top-10 记为空（Recall=NDCG=0），同时单独报告"仅非拒答请求"的指标与拒答率。

## 指标
Recall@10、NDCG@10、候选覆盖上界、三态分布；统计单元为目标服务器（种子取平均），目标级 bootstrap 95% 区间（2000 次，seed 0）。

## 预先声明的判定
- U1：ε ≥ 1、m=20、全部源时，PrivEdge 相对非隐私参照的 Recall@10 差，其目标级区间下界 ≥ −0.10（"接近非隐私源平均"）。
- U2：同条件下 PrivEdge 相对 `variance_weighted` 的 NDCG@10 差的区间下界 ≥ −0.02（防御无显著代价）。
- 其余格子只描述，不判定；不满足如实报告。
