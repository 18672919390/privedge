# compare_v1 review handoff: olist_brazil

Source run: `compare_v1_olist_brazil-20261014T122937Z-6efd0f`. Result hashes: `True`; data hashes: `True`; full registered grid: `true`; original summary independently recomputed: `True`; confirmatory use: `True`.

Preregistration path in source manifest: `experiments_prereg/COMPARE_V1.md`; review-time SHA-256: `8b8ee34baee147e8e12d60c84b6c65fcd4f4890e9ff1dce84f950ff363bf7522`. The source manifest recorded the path but no preregistration digest; the snapshot is included with this handoff.

`method_summary.csv` reports target-weighted means and target-cluster bootstrap intervals. `target_method_summary.csv` contains target-level, seed-averaged values and per-target refusal/answered-only statistics. `paired_target_differences.csv` contains the target-level paired contrasts for every method and metric. `independent_summary.json` reproduces the run summary and adds answered-only fields. The SVG plots epsilon=2 NDCG and attack success with target-cluster 95% intervals.

Answered-only Recall/NDCG first average non-REFUSED seeds within each target, then average those targets equally. These values condition on PrivEdge answering and are descriptive only; they are excluded from confirmatory decisions. The registered headline utility still scores refusals as zero.

## Preregistered decisions

| Contrast | Mean difference | 95% CI | Decision |
|---|---:|---:|---|
| clean_utility_noninferiority | 0.0030125782143820188 | [-0.0005213439789712091, 0.006824956076466134] | supported |
| mga_1src_b0.10_attack_reduction | -0.6555555555555554 | [-0.7558333333333332, -0.5333333333333333] | supported |
| weight_hijack_1src_attack_reduction | -1.0 | [-1.0, -1.0] | supported |
| weight_hijack_2src_attack_reduction | -0.8111111111111112 | [-0.8555555555555557, -0.7444444444444445] | supported |

All decisions use unrounded target-level differences, 2,000 bootstrap replicates, seed 0. The full machine-readable checks and decisions are in `validation.json` and `confirmatory_decisions.json`.
