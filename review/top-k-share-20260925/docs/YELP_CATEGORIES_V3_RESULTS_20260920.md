# Yelp 类别域目标迁移实验（修正版）

## 结论

本轮适合继续保留 Yelp，但结果支持的是“类别域可迁移、目录上下文有弱信号、主方法优势依赖样本量”，还不能声称稳定优于 average。
商户 ID 版本没有被纳入本轮：跨城市商户不重叠，那个任务构造会让源候选无法迁移。
本轮只使用类别事件。商户类别按固定 SHA-256 选一个；用户在全部城市、全部年份中只保留一个固定哈希的评分 4–5 事件。
目标真值是全局去重后目标城市的完整事件分布，仅用于离线评价。目录上下文只来自商户元数据，不使用目标评论数量、评分或文本。
均匀上下文下，context-aware 方法显式回退到 average；否则会把均匀向量误当成目标信号而产生任意源排序。
正确目录和交换目录使用完全相同的源发布；交换对照检验上下文是否真的带有目标信息。

## 配置

- 城市：Philadelphia | PA, Tucson | AZ, Tampa | FL, Indianapolis | IN, Nashville | TN, New Orleans | LA；每个城市轮流作为目标，其余五城为源。
- 用户数：[2000, 10000]；epsilon=2.0；k=10；发布 m=20；五个种子。
- OLH 是可部署发布；ORACLE 使用抽样源的真实频率，只用于分解 LDP/候选损失。
- 目标上下文：uniform、correct_catalog、swapped_catalog。

## OLH 结果（均值 ± 五种子/六目标的样本标准差）

| 源用户数 | 上下文 | average | context-weighted | censor-aware | robust | 候选覆盖上限 |
|---:|---|---:|---:|---:|---:|---:|
| 2000 | uniform | 0.417 ± 0.070 | 0.417 ± 0.070 | 0.417 ± 0.070 | 0.417 ± 0.070 | 0.600 |
| 2000 | correct_catalog | 0.417 ± 0.070 | 0.430 ± 0.075 | 0.457 ± 0.068 | 0.403 ± 0.081 | 0.600 |
| 2000 | swapped_catalog | 0.417 ± 0.070 | 0.437 ± 0.067 | 0.447 ± 0.063 | 0.400 ± 0.079 | 0.600 |
| 10000 | uniform | 0.663 ± 0.116 | 0.663 ± 0.116 | 0.663 ± 0.116 | 0.663 ± 0.116 | 0.890 |
| 10000 | correct_catalog | 0.663 ± 0.116 | 0.657 ± 0.114 | 0.673 ± 0.105 | 0.637 ± 0.122 | 0.890 |
| 10000 | swapped_catalog | 0.663 ± 0.116 | 0.663 ± 0.107 | 0.663 ± 0.113 | 0.647 ± 0.104 | 0.890 |

## 目录排序基线与无噪声诊断

| 源用户数 | 发布 | correct_catalog context-only（候选内） | average | censor-aware | robust | 候选覆盖 |
|---:|---|---:|---:|---:|---:|---:|
| 2000 | OLH | 0.567 ± 0.092 | 0.417 ± 0.070 | 0.457 ± 0.068 | 0.403 ± 0.081 | 0.600 |
| 2000 | ORACLE | 0.467 ± 0.092 | 0.740 ± 0.089 | 0.747 ± 0.094 | 0.760 ± 0.086 | 0.973 |
| 10000 | OLH | 0.553 ± 0.082 | 0.663 ± 0.116 | 0.673 ± 0.105 | 0.637 ± 0.122 | 0.890 |
| 10000 | ORACLE | 0.477 ± 0.110 | 0.753 ± 0.097 | 0.767 ± 0.099 | 0.783 ± 0.087 | 0.977 |

## 上下文配对差值

correct_catalog 与 swapped_catalog 使用同一源发布；差值按目标城市和种子配对后汇总。

| 用户数 | 发布 | 方法 | Recall correct−swapped | Recall correct−uniform |
|---:|---|---|---:|---:|
| 2000 | OLH | context_weighted | -0.007 | +0.013 |
| 2000 | OLH | censor_aware | +0.010 | +0.040 |
| 2000 | OLH | robust_context | +0.003 | -0.013 |
| 2000 | OLH | context_only | +0.020 | +0.350 |
| 2000 | ORACLE | context_weighted | -0.007 | +0.003 |
| 2000 | ORACLE | censor_aware | -0.010 | +0.007 |
| 2000 | ORACLE | robust_context | +0.003 | +0.020 |
| 2000 | ORACLE | context_only | +0.047 | +0.047 |
| 10000 | OLH | context_weighted | -0.007 | -0.007 |
| 10000 | OLH | censor_aware | +0.010 | +0.010 |
| 10000 | OLH | robust_context | -0.010 | -0.027 |
| 10000 | OLH | context_only | +0.040 | +0.273 |
| 10000 | ORACLE | context_weighted | +0.000 | -0.003 |
| 10000 | ORACLE | censor_aware | -0.010 | +0.013 |
| 10000 | ORACLE | robust_context | +0.003 | +0.030 |
| 10000 | ORACLE | context_only | +0.060 | +0.043 |

## 如何解释

- 2,000 用户、OLH：average Recall=0.417，correct_catalog censor-aware=0.457（+4.0 个百分点）；context-weighted=0.430（+1.3 个百分点）。
- 10,000 用户、OLH：average=0.663，correct_catalog censor-aware=0.673（+1.0 个百分点）；context-weighted=0.657（−0.7 个百分点）。
- 2,000 用户的候选覆盖上限为 0.600；10,000 用户为 0.890。低样本时不能把融合排序误判为主要瓶颈。
- 无噪声 ORACLE 的候选覆盖约 0.973–0.977，correct_catalog censor-aware/robust 约 0.747/0.760（2,000）和 0.767/0.783（10,000）。因此 LDP 候选发现确实造成损失，但上下文方法也仍只带来小幅改善。
- correct−swapped 对 OLH censor-aware 为 +0.010（两档均值），context-weighted 为 −0.007；目录的目标特异性信号弱，不能声称强目标识别。context-only 候选内基线更高，说明目录本身在这个协议中是强基线。
- Yelp 类别实验适合继续做真实验证；它不支持“当前 censor-aware 稳定优于 average”的强结论。主方法若要形成贡献，需要解释低样本候选缺失、目录供给与用户行为偏差，并在未开发城市上确认。
- `context_full_domain` 是允许公开上下文扩展候选的诊断，不是候选并集内的可比方法；表格没有把它当作主结果。
- 目录是当前元数据快照，历史上是否已公开未证实；用户事件是“留下正向评论的用户事件”，不能称为城市居民消费偏好。

## 复现与输出

```powershell
.runtime/python/python.exe experiments/validation/audit_available_data.py
.runtime/python/python.exe experiments/validation/yelp_categories_v3.py --output-dir outputs/yelp_categories_v3_six --cities "Philadelphia | PA" "Tucson | AZ" "Tampa | FL" "Indianapolis | IN" "Nashville | TN" "New Orleans | LA"
.runtime/python/python.exe experiments/validation/report_yelp_categories_v3.py
```

原始逐目标结果、manifest、摘要及上下文配对结果位于 outputs/yelp_categories_v3_six。
