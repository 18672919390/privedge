# compare_v1 review handoff: meituan_trd

Source run: `compare_v1_meituan_trd-20261014T122937Z-6621cf`. Result hashes: `True`; data hashes: `True`; full registered grid: `true`; original summary independently recomputed: `True`; confirmatory use: `True`.

Preregistration path in source manifest: `experiments_prereg/COMPARE_V1.md`; review-time SHA-256: `8b8ee34baee147e8e12d60c84b6c65fcd4f4890e9ff1dce84f950ff363bf7522`. The source manifest recorded the path but no preregistration digest; the snapshot is included with this handoff.

`method_summary.csv` reports target-weighted means and target-cluster bootstrap intervals. `target_method_summary.csv` contains target-level, seed-averaged values and per-target refusal/answered-only statistics. `paired_target_differences.csv` contains the target-level paired contrasts for every method and metric. `independent_summary.json` reproduces the run summary and adds answered-only fields. The SVG plots epsilon=2 NDCG and attack success with target-cluster 95% intervals.

Answered-only Recall/NDCG first average non-REFUSED seeds within each target, then average those targets equally. These values condition on PrivEdge answering and are descriptive only; they are excluded from confirmatory decisions. The registered headline utility still scores refusals as zero.

## Preregistered decisions

| Contrast | Mean difference | 95% CI | Decision |
|---|---:|---:|---|
| clean_utility_noninferiority | -0.0005309182565860215 | [-0.0020737155239937384, 0.0008199286225501314] | supported |
| mga_1src_b0.10_attack_reduction | -0.36363636363636365 | [-0.42424242424242425, -0.309090909090909] | supported |
| weight_hijack_1src_attack_reduction | -1.0 | [-1.0, -1.0] | supported |
| weight_hijack_2src_attack_reduction | -0.9393939393939394 | [-0.9696969696969698, -0.9030303030303032] | supported |

All decisions use unrounded target-level differences, 2,000 bootstrap replicates, seed 0. The full machine-readable checks and decisions are in `validation.json` and `confirmatory_decisions.json`.
