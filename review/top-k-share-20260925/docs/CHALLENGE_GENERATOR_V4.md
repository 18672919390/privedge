# 第四步：更有挑战性、较少单一假设的生成机制

2026-09-15核对补充：以下网格含研究计划，不能等同于已执行范围。当前G14入口实际
运行5类因素、16配置、3种子和2协议，共96场景；记录gap/entropy/Top-k mass。
gap分箱、上下文TV、Gini、完整12/20种子与协议平衡尚未实现。前三个形状参数和
迁移参数仍属于同一个混合生成族。统一导航见[实验目录](EXPERIMENT_GUIDE.md)。

第四步的目标是识别方法何时有效、何时必然失效，而不是只提高平均 Recall。
生成器现已参数化，默认值与旧实验完全相同：

```text
target_concentration=24, latent_exponent=0.9,
source_exponent=1.08, source_mix_max=0.9, source_mix_min=0.15
```

这些参数已加入 `ExperimentConfig` 并由 `make_problem` 传入；旧 G1-G8 不改结果。

## 要检验的六个维度

| 维度 | 操作值 | 只改变什么 | 必须报告 |
|---|---|---|---|
| 目标稀疏度 | concentration=4, 24, 96 | Dirichlet 总浓度 | 熵、非零质量、gap、Recall/NDCG |
| 头部/长尾 | latent exponent=0.4, 0.9, 1.6 | 潜在 Zipf 形状 | Gini、Top-k mass、gap |
| 源长尾 | source exponent=0.7,1.08,1.6 | 无关源形状 | 源 TV、候选覆盖、Recall |
| 源迁移强度 | mix range [.9,.9], [.9,.5], [.9,.15], [.5,0] | p_s 与目标关系 | 每源 TV、最差/最好源、方法差 |
| Top-k 边界 | 每轮记录 gap=p_(k)-p_(k+1)，按五分位分析 | 不改生成器 | gap 分箱 Recall，不能用测试 gap 调参 |
| 上下文失配 | clean、noisy、misleading、outdated | q 的可靠性 | q 与 p_T 的 TV、上下文收益/损失 |

上下文质量仍单独控制 q 的 Dirichlet 浓度；不要把 quality 当作 TV 距离。
对每个因素先固定 domain=128、users=1500、servers=6、k=10、epsilon=2、report=2、
协议=OLH/MIXED、同一12个独立种子。每个水平都复用同一组种子，形成配对差异。
完成单因素后再做预先指定的二因素交互：迁移×上下文失配、稀疏度×epsilon。

## 必须增加的对照

每个场景至少运行 average、variance_weighted、旧 censor-aware、全源软融合和新方法。
另外计算：

- `candidate_recall_upper_bound`：区分候选发现失败与融合排序失败；
- `candidate_miss_mass`：候选集合外的目标概率质量；
- `target_gap`：真实目标第 k 与第 k+1 项差距；
- `source_target_tv_*`：仅评估使用的迁移诊断；
- `context_target_tv`：仅评估使用的 q 失配诊断；
- 源列表 Jaccard、有效独立源数和候选重合度：检验源冗余；
- 全源与选源候选两种模式：分离丢候选和丢统计证据。

若 Recall 下降但 coverage 不变，问题在融合；若 coverage 同步下降，问题在发布/候选。
若只有小 gap 分箱失败，这是符合 Top-k 排序理论的边界现象；若大 gap 也失败，应
检查 LDP 估计偏差或迁移模型。若 context_target_tv 大时复杂方法劣于 average，
这应作为鲁棒性结果报告，不应删掉该条件。

## 控制和随机性

每轮使用五个独立随机流：潜在画像、目标、上下文、源采样、污染。改变生成参数时
保持同一轮的种子和流划分，确保 quality/形状消融不会偷偷重抽目标或源。
协议比较需固定机制顺序或每协议使用独立且预先生成的报告随机种子；不能让 MIXED
中服务器编号同时决定协议和源相似度后，把编号效应误报为协议效应。

目标浓度变化会同时影响目标熵和边界 gap；因此浓度实验只能称为“稀疏度族”实验，
必须按真实 gap 分箱。Zipf 指数也可能改变源候选覆盖，不能只报告最终 Recall。
源 mix 参数只是本合成模型的迁移族，不代表现实普遍分布规律。

## 运行顺序和样本量

第一轮探索：六个维度各3水平、12种子、两协议，每个配置一轮，共432个场景。
先用每维3种子 smoke 检查时间和指标范围，再运行固定12种子；不得看最终测试结果后
增加或删除水平。第二轮只保留第一轮中有明确交互的2个因素，每格20种子。
开发集用于选择固定超参数；最终测试集必须使用新的目标随机种子和新的源随机流。

主结果按种子汇总，bootstrap/置换以种子为独立单位。报告均值、跨种子标准差、95% CI，
多因素比较采用预先定义的 Holm/FDR 方案。不要将同一目标下的多轮当作独立用户群。

## 当前实现状态

`simulation.py` 和 `ExperimentConfig` 已支持前三个形状/迁移参数；默认行为回归不变。
第4步的完整 sweep 入口和 gap/entropy/TV 记录尚未接入 `write_results`，避免直接运行
尚未冻结的因素网格。下一步应实现 `experiments/validation/challenge_generator.py`，先运行
3种子 smoke，再冻结配置生成正式输出。这个文档是实验协议，不能用来事后挑有利维度。
