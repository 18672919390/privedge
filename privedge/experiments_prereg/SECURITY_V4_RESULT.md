# SECURITY_V4（权重封顶确认性复验，新种子）：结果与预注册判定

- 预注册：`SECURITY_V4.md`；新种子 601、709、811、907、1009（此前从未使用）
- 运行：
  - Massive：`runs/security_v4_massive_steps/security_v4_massive_steps-20260929T145354Z-705ea4/`
  - Olist：`runs/security_v4_olist_brazil/security_v4_olist_brazil-20260929T145354Z-3c22fd/`
  - TRD：`runs/security_v4_meituan_trd/security_v4_meituan_trd-20260929T145355Z-8514ad/`

## 判定

| 判定 | Massive | Olist | TRD |
|---|---|---|---|
| C1 不回退（14 个场景 × ε 单元） | 满足 14/14 | 满足 14/14 | 满足 14/14 |
| C2 单源劫持 / 降级下 D4 NDCG 显著高于 D3（4 个单元） | 满足 4/4 | 满足 4/4 | 满足 4/4 |

**采用：D4（`weight_cap=2.0`）成为 v4.1 主线默认。**

## 描述性结果（新种子）

- 单源劫持 / 降级下，D4 相对 D3 的 NDCG 提升 +0.03 ~ +0.65。D4 与无攻击的差距在 0.09 以内；D3 的差距为 0.03–0.68。
- 单源劫持下，攻击成功率从 D3 到 D4 的变化：Massive 0.40→0.39（ε=1）、0.31→0.17（ε=2）；Olist 0.48→0.31、0.09→0；TRD 0.62→0.28、0.40→0。
- 2 源劫持（f=t）下，ε=1 时注入仍几乎总成功（0.93–1.00）；ε=2 时 D4 降到 0.06–0.85。这符合定理 1：f ≥ t 时支持规则不提供保证。

## 补充核对（不参与判定）

- 权重封顶对效用网格没有影响：`utility_v1_capped_*`（ε 4 档 × m 3 档 + 源数量网格）中，PrivEdge 的 1,920 行与 UTILITY_V1 逐行相同。运行目录：
  - `runs/utility_v1_capped_massive_steps/utility_v1_capped_massive_steps-20260929T145611Z-001563/`
  - `runs/utility_v1_capped_olist_brazil/utility_v1_capped_olist_brazil-20260929T145611Z-fbb9b5/`
  - `runs/utility_v1_capped_meituan_trd/utility_v1_capped_meituan_trd-20260929T145612Z-981d68/`
- 截尾下限 0（推导定理 2 时发现的加固：被攻破源可发布 −10⁶ 删除任意类别）：
  - 全部网格上 67,200 个诚实发布值中负值为 0 个，所以该下限不改变任何已记录结果。运行目录 `runs/negative_check/negative_check-20260929T145958Z-bb6c1b/`。
  - 攻击演示见 `tests/test_core.py::test_negative_frequencies_cannot_delete_items`。
