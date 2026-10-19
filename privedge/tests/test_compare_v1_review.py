import json
import unittest
from pathlib import Path

from privedge.experiments import review_compare_v1 as review


def _row(target, seed, method, recall, ndcg, state="n/a"):
    return {
        "target_server": target,
        "seed": seed,
        "epsilon": 2.0,
        "scenario": "clean",
        "method": method,
        "attack_success": 0.0,
        "recall": recall,
        "ndcg": ndcg,
        "candidate_recall_upper_bound": 1.0,
        "state": state,
    }


class CompareV1ReviewTests(unittest.TestCase):
    def test_summary_uses_target_means_and_separates_answered_utility(self):
        rows = []
        for target, values in {
            "A": {"simple_average": [(0.5, 0.6), (0.5, 0.8)],
                  "variance_weighted": [(0.5, 0.6), (0.5, 0.8)],
                  "trimmed_frequency": [(0.5, 0.6), (0.5, 0.8)],
                  "privedge": [(0.0, 0.0, "REFUSED"), (0.8, 0.8, "NORMAL")]},
            "B": {"simple_average": [(0.8, 0.8), (0.8, 0.8)],
                  "variance_weighted": [(0.8, 0.8), (0.8, 0.8)],
                  "trimmed_frequency": [(0.8, 0.8), (0.8, 0.8)],
                  "privedge": [(0.6, 0.6, "NORMAL"), (0.8, 0.8, "NORMAL")]},
        }.items():
            for method, seeds in values.items():
                for seed, value in zip((101, 211), seeds):
                    recall, ndcg = value[:2]
                    state = value[2] if len(value) == 3 else "n/a"
                    rows.append(_row(target, seed, method, recall, ndcg, state))

        _, target_rows, summary_rows, paired = review.build_statistics(rows)
        privedge = next(r for r in summary_rows if r["method"] == "privedge")
        self.assertAlmostEqual(privedge["recall"], 0.55)
        self.assertAlmostEqual(privedge["answered_recall"], 0.75)
        self.assertAlmostEqual(privedge["refusal_rate"], 0.25)
        self.assertEqual(privedge["answered_targets"], 2)
        target_a = next(r for r in target_rows if r["method"] == "privedge" and r["target_server"] == "A")
        self.assertEqual(target_a["answered_seeds"], 1)
        self.assertAlmostEqual(target_a["answered_ndcg"], 0.8)
        self.assertTrue(any(r["metric"] == "ndcg" and r["target_server"] == "A" for r in paired))

    def test_grid_check_requires_every_registered_pair_and_exact_target_set(self):
        meta_path = review.PACKAGE_ROOT / "data" / "meituan_trd" / "domain.json"
        targets = [item["server_id"] for item in json.loads(meta_path.read_text(encoding="utf-8"))["servers"]]
        config = {
            "dataset": "meituan_trd", "methods": list(review.METHODS),
            "seeds": list(review.SEEDS), "epsilons": list(review.EPSILONS),
            "scenarios": list(review.SCENARIOS), "targets": targets, "smoke_test": False,
        }
        rows = []
        for target in targets:
            for seed in config["seeds"]:
                for epsilon in config["epsilons"]:
                    for scenario in config["scenarios"]:
                        for method in review.METHODS:
                            rows.append({
                                "target_server": target, "seed": seed, "epsilon": epsilon,
                                "scenario": scenario, "method": method,
                                "attack_success": 0.0, "recall": 0.0, "ndcg": 0.0,
                                "candidate_recall_upper_bound": 0.0,
                                "state": "NORMAL" if method == "privedge" else "n/a",
                            })
        manifest = {"config": config}
        checks = review.check_grid(manifest, rows, allow_smoke=False)
        self.assertTrue(checks["valid_for_confirmatory_decision"])
        self.assertTrue(checks["targets"]["match"])
        self.assertEqual(checks["grid_rows"]["expected"], len(rows))

        broken = rows[:-1]
        checks = review.check_grid(manifest, broken, allow_smoke=False)
        self.assertFalse(checks["grid_rows"]["match"])
        self.assertFalse(checks["paired_methods"]["match"])

        config["targets"] = [targets[0], targets[0]]
        checks = review.check_grid(manifest, rows, allow_smoke=False)
        self.assertFalse(checks["targets"]["match"])
        self.assertFalse(checks["formal_grid"]["match"])

    def test_bootstrap_interval_is_repeatable(self):
        values = [0.0, 0.25, 1.0, 0.5]
        self.assertEqual(review.bootstrap_ci(values), review.bootstrap_ci(values))


if __name__ == "__main__":
    unittest.main()
