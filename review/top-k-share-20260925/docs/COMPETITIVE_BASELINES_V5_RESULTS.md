# 竞争性基线正式对比结果

2026-09-15 已将 `context_mixture`、`trimmed_frequency` 和 `rank_frequency` 接入
`experiment.py`。使用4个场景（弱/强/无/误导上下文）、OLH/MIXED、20个新种子，
共80个任务；所有方法共享每个任务的同一批发布。固定参数为 alpha=.5、trim=1、
gamma=1。37项测试全部通过。完整输出在 `outputs/formal_baseline_comparison`。

## Recall 均值

| 场景 | 协议 | average | context mixture | trimmed frequency | censor-aware |
|---|---|---:|---:|---:|---:|
| 弱上下文 | OLH | .695 | .655 | **.800** | .815 |
| 弱上下文 | MIXED | .450 | .510 | .650 | **.670** |
| 强上下文 | OLH | .695 | .640 | .800 | **.810** |
| 强上下文 | MIXED | .450 | .550 | .650 | .675 |
| 误导上下文 | OLH | .695 | .565 | **.800** | .605 |
| 误导上下文 | MIXED | .450 | .425 | .650 | .535 |
| 无上下文 | OLH | .695 | .695 | **.800** | .695 |
| 无上下文 | MIXED | .450 | .450 | **.650** | .450 |

截尾频率基线在本配置下非常强，说明此前只与 average 比较会高估 censor-aware 的
独立贡献。弱上下文下 OLH 的 censor-aware 比截尾频率高 .015，MIXED 高 .020；
bootstrap 区间分别包含 0，不能宣称显著超过该基线。误导上下文和无上下文中，
截尾频率明显更稳健。

## 解释和后续

- context_mixture 的 alpha=.5 未重归一化源平均候选向量；它是一个固定收缩参照，
  不是概率模型最优值。正式论文前需在独立开发集比较归一化与 alpha 网格。
- trimmed_frequency 将未发布视为零并去掉一端极值，虽然没有建模删失，仍然有效地
  限制了单个异常源。它必须保留为主要强基线。
- 在无上下文条件下，context_mixture、censor-aware 按设计回退 average；trimmed
  和 rank_frequency 仍可用，因为它们不需要 q。这是信息边界一致的差异。
- 现有 censor-aware 主要优势是 MIXED/弱上下文相对 average；相对 trimmed 的优势
  很小且不稳定。论文主张应改成“在特定截断和异构噪声条件下，与稳健基线相当或略优”，
  不能写成全面优越。

本轮是固定参数的测试集式对照，不是开发集调参后的最终确认。下一步应使用独立开发
种子冻结 alpha、gamma、trim，并在第四步的稀疏度、迁移强度和 Top-k gap 因素中重复；
若 censor-aware 不能稳定超过截尾频率，应把贡献转向删失估计的校准误差界或通信/计算
成本，而不是继续堆叠更多启发式权重。
