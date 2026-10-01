import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiment import ExperimentConfig
from experiments.validation.desktop_validation import analyze, execute, independent_seeds, run_seed, sign_flip


class DesktopValidationTests(unittest.TestCase):
    def test_paired_analysis_and_holm(self):
        rows = []
        for seed in range(6):
            for method, value in (("average", 0.2), ("censor_aware_item_context", 0.4)):
                rows.append(dict(case="test", scenario="OLH", method=method, seed=seed,
                                 recall=value, ndcg=value, coverage=0.8, candidate_miss_mass=0.1))
        _, comparisons = analyze(rows)
        self.assertAlmostEqual(comparisons[0]["mean_delta"], 0.2)
        self.assertEqual(comparisons[0]["seed_pairs"], 6)
        self.assertEqual(comparisons[0]["wins"], 6)
        self.assertGreaterEqual(comparisons[0]["pvalue_holm"], comparisons[0]["pvalue"])
        with self.assertRaises(ValueError):
            analyze(rows + [rows[0]])

    def test_large_sign_flip_is_bounded_and_reproducible(self):
        values = np.ones(30)
        result = sign_flip(values, np.random.default_rng(1))
        self.assertGreater(result, 0)
        self.assertLess(result, 0.001)
        self.assertEqual(result, sign_flip(values, np.random.default_rng(1)))

    def test_seed_prefix_and_context_only(self):
        self.assertEqual(independent_seeds(3), independent_seeds(5)[:3])
        config = ExperimentConfig(domain=32, top_k=4, users_per_server=50,
                                  server_count=2, rounds=1, mechanisms=("OUE",))
        result = run_seed("test", config, 12)
        baseline = next(r for r in result["rows"] if r["method"] == "context_only")
        self.assertEqual(baseline["recall"], baseline["coverage"])
        self.assertEqual(result, {**run_seed("test", config, 12), "seconds": result["seconds"]})

    def test_process_execution_resume_and_manifest_guard(self):
        config = ExperimentConfig(domain=32, top_k=4, users_per_server=30,
                                  server_count=2, rounds=1, mechanisms=("OUE",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execute(root, {"test": config}, [1, 2], 1)
            before = (root / "round_results.csv").read_bytes()
            execute(root, {"test": config}, [1, 2], 2)
            self.assertEqual(before, (root / "round_results.csv").read_bytes())
            with self.assertRaises(ValueError):
                execute(root, {"test": config}, [1, 2, 3], 1)


if __name__ == "__main__":
    unittest.main()
