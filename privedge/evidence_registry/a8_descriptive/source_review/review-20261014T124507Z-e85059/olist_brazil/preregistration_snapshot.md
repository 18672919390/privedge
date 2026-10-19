# 预注册：PrivEdge 四方法与投毒对照 v1

- 冻结日期：2026-10-14；代码入口：`privedge/experiments/compare_v1.py`。
- 输出：`privedge/runs/compare_v1_<dataset>/<run_id>/`；每次执行创建新的唯一运行目录，不覆盖历史运行。
- 目标：在同一批 OLH 发布和攻击输入上比较简单平均、无防御方差加权、已有截尾均值鲁棒聚合与完整 PrivEdge 流程。

## 数据与参数

- 数据集：美团 TRD（主场景）、Olist Brazil（跨域对照）、Massive-STEPS（异质压力场景）；每次 CLI 调用运行其中一个数据集。
- 目标：依次将每个 server 作为目标，其余所有 server 为源；不抽取源子集。
- 每源用户数：5,000；发布列表 Top-m：20；输出 Top-k：10；攻击目标数：3。
- 隐私预算：`epsilon ∈ {1, 2}`。
- 独立种子：`{101, 211, 307, 401, 503}`。用户抽样、OLH 扰动、攻击目标与攻击报告按代码中固定的 `SeedSequence` 布局生成；所有方法对同一目标、种子、ε、场景共用底层干净样本和对应攻击输入。
- 随机种子表、数据文件哈希、代码指纹、参数和输出文件哈希由每次运行的 `manifest.json` 记录。

## 四种方法

1. `simple_average`：对各源已发布频率求简单算术平均；未发布项按 0 计。
2. `variance_weighted`：对已发布频率按现有逆不确定度权重融合，不启用发布端筛查、截尾或权重封顶。
3. `trimmed_frequency`：复用 `research_core/competitive_baselines.py` 的逐项截尾均值，固定 `trim=1`；候选并集取自各源 Top-20，缺失项按 0。完整主实验至少有 5 个源；若源数少于 3，该基线在定义上不适用，不回退到平均值。
4. `privedge`：发布端伪造报告筛查开启；网关固定使用 v4.1 默认策略（多源支持数至少 2、留一共识截尾 `clip_z=3`、权重封顶 `κ=2`、截尾下限 0）；缺上下文时按无上下文路径运行，并保留 `NORMAL/DEGRADED/REFUSED` 状态。拒答的 Recall、NDCG 和攻击成功率均记 0，同时另报非拒答条件下的效用和拒答率。

后三种基线中的前三个不执行 PrivEdge 防御步骤，以便清楚区分鲁棒融合与完整端到端方案。四方法比较衡量的是完整方案与基线的总效果，不能解读为仅聚合公式的消融实验。

## 威胁场景

- `clean`：没有攻击。
- MGA 发布端伪造用户：单源注入比例 `β ∈ {0.02, 0.05, 0.10}`，以及双源各注入 `β=0.05`。攻击者按已有 `mga_fake_reports` 机制构造 OLH 报告；PrivEdge 启用发布端筛查，其他三方法使用未筛查发布。
- 已攻陷发布端：1 个或 2 个源在生成 Top-20 后将 3 个攻击目标伪造成源内高频类别。
- 权重劫持：1 个或 2 个源伪造相同的 Top-20 目标类别，并把所报告方差缩小 `10^-4` 倍，以增加逆方差权重。
- 攻击类别按每个目标的源端真实平均分布排序后取第 31–80 名，再由预注册种子抽 3 类。这只用于构造攻击负载；推理方法只接收其输入发布摘要，目标真值、真实源分布和攻击生成参数均不传给融合函数。

## 指标与统计

- Recall@10、NDCG@10、候选覆盖上界、攻击成功率（3 个攻击类别进入 Top-10 的比例）、PrivEdge 状态分布及拒答率。
- 配对单元：相同数据集、目标、种子、ε 和场景下的四方法输出。先在每个目标内对 5 个种子取均值，再以目标为独立统计单位计算方法差。
- 报告目标级配对均值差及 2,000 次目标簇 bootstrap 百分位 95% 区间（bootstrap seed=0）。种子和同一目标下的多个场景不当作独立目标样本。
- `smoke-test` 子集仅用于检查程序，不用于预注册判定或正式报告。

## 预先判定

- 清洁效用主判定：ε=2、`clean` 场景，PrivEdge 相对 `trimmed_frequency` 的 NDCG@10 配对差 95% 区间下界不低于 −0.02，判为在该设置下满足预设非劣界；否则报告未满足或不确定。
- 防投毒主判定分别针对 ε=2 下 `mga_1src_b0.10`、`weight_hijack_1src` 和 `weight_hijack_2src`。只有当 PrivEdge 相对 `variance_weighted` 的攻击成功率配对差 95% 区间上界严格小于 0，才记为该场景有支持证据；其余记为未满足或不确定。场景分开报告，不跨攻击类型汇总成普遍鲁棒性结论。
- 所有其他 ε、场景和指标均作为描述性结果报告；若结果不支持预期，保留并解释，不更改阈值或场景定义。

## 运行

在 `privedge/` 目录执行：

```powershell
python -m privedge.experiments.compare_v1 --dataset meituan_trd
python -m privedge.experiments.compare_v1 --dataset olist_brazil
python -m privedge.experiments.compare_v1 --dataset massive_steps
```

可用 `--max-targets` 或 `--max-seeds` 做烟测；带有这两个参数的运行会在 manifest 中标为 `smoke_test=true`。
