# compare_v1 review handoff: massive_steps

Source run: `compare_v1_massive_steps-20261014T122937Z-50c077`. Result hashes: `True`; data hashes: `True`; full registered grid: `true`; original summary independently recomputed: `True`; confirmatory use: `True`.

Preregistration path in source manifest: `experiments_prereg/COMPARE_V1.md`; review-time SHA-256: `8b8ee34baee147e8e12d60c84b6c65fcd4f4890e9ff1dce84f950ff363bf7522`. The source manifest recorded the path but no preregistration digest; the snapshot is included with this handoff.

`method_summary.csv` reports target-weighted means and target-cluster bootstrap intervals. `target_method_summary.csv` contains target-level, seed-averaged values and per-target refusal/answered-only statistics. `paired_target_differences.csv` contains the target-level paired contrasts for every method and metric. `independent_summary.json` reproduces the run summary and adds answered-only fields. The SVG plots epsilon=2 NDCG and attack success with target-cluster 95% intervals.

Answered-only Recall/NDCG first average non-REFUSED seeds within each target, then average those targets equally. These values condition on PrivEdge answering and are descriptive only; they are excluded from confirmatory decisions. The registered headline utility still scores refusals as zero.

## Preregistered decisions

| Contrast | Mean difference | 95% CI | Decision |
|---|---:|---:|---|
| clean_utility_noninferiority | 0.019991876609764012 | [0.003643045277167093, 0.048924130427934746] | supported |
| mga_1src_b0.10_attack_reduction | -0.9142857142857143 | [-0.9714285714285714, -0.8666666666666665] | supported |
| weight_hijack_1src_attack_reduction | -0.780952380952381 | [-0.8380952380952379, -0.7142857142857143] | supported |
| weight_hijack_2src_attack_reduction | -0.15238095238095248 | [-0.2095238095238096, -0.09523809523809533] | supported |

All decisions use unrounded target-level differences, 2,000 bootstrap replicates, seed 0. The full machine-readable checks and decisions are in `validation.json` and `confirmatory_decisions.json`.
