import unittest

import numpy as np

from experiment import ExperimentConfig, run, summarize
from fusion import (
    ServerRelease,
    context_augmented_candidate_set,
    fuse_censor_aware_item_context,
    fuse_item_level_anchor,
    public_context_relevance,
)
from metrics import candidate_recall_upper_bound, migration_error
from ldp_protocols import estimate_frequency
from pem import pem
from problem_definition import VisibilityContract
from simulation import make_problem
from experiments.G8_parameter_sensitivity import build_cases
from experiments.validation.calibrate_variances import run_calibration
from experiments.validation.validate_independent_seeds import (
    METHODS as VALIDATION_METHODS,
    VALIDATION_SEEDS,
    analyze as analyze_independent_seeds,
    build_config as build_validation_config,
)


class ProtocolTests(unittest.TestCase):
    def test_frequency_oracles_return_finite_unbiased_estimates(self):
        distribution = np.array([0.55, 0.25, 0.12, 0.08])
        for offset, mechanism in enumerate(("GRR", "OUE", "OLH")):
            rng = np.random.default_rng(100 + offset)
            data = rng.choice(4, size=4000, p=distribution)
            result = estimate_frequency(mechanism, data, 4, 3.0, rng)
            self.assertEqual(result.counts.shape, (4,))
            self.assertTrue(np.all(np.isfinite(result.counts)))
            self.assertEqual(int(np.argmax(result.counts)), 0)

    def test_pem_returns_bounded_candidates(self):
        rng = np.random.default_rng(9)
        data = rng.choice(32, size=1200, p=np.arange(32, 0, -1) / 528)
        result = pem(data, domain=32, top_k=8, epsilon=3.0, rng=rng)
        self.assertLessEqual(len(result.items), 8)
        self.assertTrue(np.all((0 <= result.items) & (result.items < 32)))
        self.assertEqual(len(set(result.items.tolist())), len(result.items))


class ExperimentTests(unittest.TestCase):
    def test_variance_calibration_covers_all_protocols(self):
        rows = run_calibration(
            repetitions=3,
            user_counts=(50,),
            epsilons=(2.0,),
            mechanisms=("GRR", "OUE", "OLH", "PEM"),
        )
        self.assertEqual(len(rows), 12)
        self.assertEqual({row["protocol"] for row in rows}, {"GRR", "OUE", "OLH", "PEM"})
        for row in rows:
            self.assertGreaterEqual(row["nominal_95_coverage"], 0.0)
            self.assertLessEqual(row["nominal_95_coverage"], 1.0)
        pem_rows = [row for row in rows if row["protocol"] == "PEM"]
        self.assertTrue(all(row["calibration_scope"] == "released-item conditional" for row in pem_rows))

    def test_context_candidate_expansion_is_postprocessing_only(self):
        releases = [
            ServerRelease(
                0,
                "OLH",
                (0, 1),
                {0: 0.5, 1: 0.2},
                {0: 0.01, 1: 0.01},
            )
        ]
        context = np.array([0.1, 0.2, 0.7, 0.0])
        self.assertEqual(
            context_augmented_candidate_set(releases, context, 1), {0, 1, 2}
        )
        self.assertEqual(
            context_augmented_candidate_set(releases, context, 0), {0, 1}
        )

    def test_context_candidate_ratio_is_validated(self):
        with self.assertRaises(ValueError):
            ExperimentConfig(
                domain=32, top_k=4, context_candidate_ratio=9.0
            ).validate()

    def test_independent_seed_validation_design_is_frozen(self):
        self.assertEqual(len(VALIDATION_SEEDS), 10)
        self.assertEqual(len(set(VALIDATION_SEEDS)), 10)
        self.assertNotIn(20260909, VALIDATION_SEEDS)
        for seed in VALIDATION_SEEDS:
            config = build_validation_config(seed)
            self.assertEqual(config.rounds, 3)
            self.assertEqual(config.mechanisms, ("OLH", "MIXED"))
            self.assertEqual(config.context_quality, 0.25)
            self.assertEqual(config.censor_prior_strength, 0.10)
            self.assertEqual(config.censor_transfer_scale, 1.0)

    def test_independent_seed_analysis_pairs_before_bootstrap(self):
        raw_rows = []
        for seed, advantage in ((11, 0.10), (22, 0.20), (33, 0.30)):
            for scenario in ("OLH", "MIXED"):
                for round_id in (1, 2, 3):
                    for method in VALIDATION_METHODS:
                        increment = advantage if method == "censor_aware_item_context" else 0.0
                        raw_rows.append(
                            {
                                "seed": seed,
                                "round": round_id,
                                "scenario": scenario,
                                "method": method,
                                "recall": 0.4 + increment,
                                "ndcg": 0.6 + increment,
                                "coverage": 0.9,
                            }
                        )
        _, comparisons, _ = analyze_independent_seeds(raw_rows)
        result = next(
            row
            for row in comparisons
            if row["scenario"] == "ALL"
            and row["method"] == "censor_aware_item_context"
            and row["baseline"] == "average"
            and row["metric"] == "recall"
        )
        self.assertEqual(result["independent_seed_pairs"], 3)
        self.assertAlmostEqual(result["mean_delta"], 0.2)
        self.assertEqual((result["wins"], result["ties"], result["losses"]), (3, 0, 0))

    def test_g8_is_a_controlled_three_round_sensitivity_grid(self):
        cases = build_cases()
        self.assertEqual(len(cases), 21)
        self.assertTrue(all(case.config.rounds == 3 for case in cases))
        self.assertEqual(len({case.config.seed for case in cases}), 1)
        self.assertEqual(
            {case.config.mechanisms for case in cases}, {("OLH", "MIXED")}
        )

    def test_positive_round_count_is_required(self):
        ExperimentConfig(rounds=30).validate()
        with self.assertRaises(ValueError):
            ExperimentConfig(rounds=0).validate()

    def test_small_end_to_end_run(self):
        config = ExperimentConfig(
            domain=32,
            users_per_server=200,
            server_count=3,
            top_k=4,
            rounds=1,
            mechanisms=("MIXED",),
        )
        rows = run(config)
        self.assertEqual(len(rows), 15)
        self.assertTrue({"context_mixture", "trimmed_frequency", "rank_frequency"} <= {r["method"] for r in rows})
        for row in rows:
            self.assertTrue(0.0 <= row["recall"] <= 1.0)
            self.assertTrue(0.0 <= row["ndcg"] <= 1.0 + 1e-12)
            if row["method"] != "global_true_average":
                self.assertLessEqual(
                    row["recall"], row["candidate_recall_upper_bound"] + 1e-12
                )

    def test_visibility_forbids_target_oracle(self):
        with self.assertRaises(ValueError):
            VisibilityContract(target_distribution=True).validate()
        config = ExperimentConfig(visibility=VisibilityContract(public_target_context=False))
        config.validate()

    def test_no_context_does_not_inject_context_ranking(self):
        config = ExperimentConfig(
            domain=32,
            users_per_server=100,
            server_count=3,
            top_k=4,
            rounds=1,
            mechanisms=("OLH",),
            visibility=VisibilityContract(public_target_context=False),
        )
        rows = run(config)
        average = next(row for row in rows if row["method"] == "average")
        for method in (
            "adaptive_context",
            "censor_aware_item_context",
            "adaptive_censor_aware_item_context",
        ):
            context = next(row for row in rows if row["method"] == method)
            self.assertEqual(average["recall"], context["recall"])
            self.assertEqual(average["ndcg"], context["ndcg"])

    def test_context_quality_does_not_change_hidden_target_draw(self):
        first = make_problem(32, 3, 0.25, np.random.default_rng(77))
        second = make_problem(32, 3, 0.90, np.random.default_rng(77))
        np.testing.assert_array_equal(first.target, second.target)
        for first_source, second_source in zip(first.servers, second.servers):
            np.testing.assert_array_equal(first_source, second_source)
        self.assertFalse(np.array_equal(first.public_target_context, second.public_target_context))

    def test_distribution_shape_parameters_are_controlled_and_defaults_regress(self):
        first = make_problem(32, 3, 0.25, np.random.default_rng(44))
        second = make_problem(32, 3, 0.25, np.random.default_rng(44), target_concentration=96.0)
        np.testing.assert_array_equal(first.servers, make_problem(32, 3, 0.25, np.random.default_rng(44)).servers)
        self.assertFalse(np.array_equal(first.target, second.target))
        with self.assertRaises(ValueError):
            make_problem(32, 3, .25, np.random.default_rng(1), source_mix_min=.9, source_mix_max=.2)

    def test_candidate_report_ratio_controls_publication_cost(self):
        config = ExperimentConfig(
            domain=32,
            users_per_server=100,
            server_count=3,
            top_k=4,
            report_ratio=1.5,
            rounds=1,
            mechanisms=("OLH",),
        )
        rows = run(config)
        self.assertEqual(rows[0]["reported_item_count"], 18)
        self.assertEqual(rows[0]["estimated_payload_bytes"], 18 * 24)

    def test_adversarial_and_missing_source_runs(self):
        for condition in ("adversarial", "missing"):
            rows = run(
                ExperimentConfig(
                    domain=32,
                    users_per_server=100,
                    server_count=3,
                    top_k=4,
                    rounds=1,
                    mechanisms=("MIXED",),
                    source_condition=condition,
                )
            )
            self.assertTrue(any(row["method"] == "robust_adaptive_context" for row in rows))
            self.assertEqual(rows[0]["affected_source_count"], 1)
            self.assertAlmostEqual(rows[0]["effective_affected_source_fraction"], 1 / 3)

    def test_coverage_and_migration_diagnostics(self):
        target = np.array([0.7, 0.2, 0.1])
        sources = [np.array([0.6, 0.3, 0.1]), np.array([0.2, 0.3, 0.5])]
        self.assertEqual(candidate_recall_upper_bound([0, 1], {0, 2}), 0.5)
        diagnostics = migration_error(target, sources)
        self.assertGreater(diagnostics["source_target_tv_mean"], 0.0)

    def test_item_level_fusion(self):
        releases = [
            ServerRelease(0, "OLH", (0, 1), {0: 0.8, 1: 0.1}, {0: 0.01, 1: 0.01}),
            ServerRelease(1, "GRR", (1, 2), {1: 0.7, 2: 0.2}, {1: 0.01, 2: 0.01}),
        ]
        self.assertEqual(fuse_item_level_anchor(releases, np.array([0.9, 0.1, 0.0]), 1), [0])

    def test_sparse_context_does_not_rank_unpublished_zero_mass_items(self):
        release = ServerRelease(
            0,
            "OLH",
            (3, 0),
            {3: 0.8, 0: 0.1},
            {3: 0.01, 0: 0.01},
        )
        sparse_context = np.array([0.0, 0.0, 0.0, 1.0])
        relevance = public_context_relevance(release, sparse_context, report_k=4)
        one_item_relevance = public_context_relevance(
            release, sparse_context, report_k=1
        )
        self.assertAlmostEqual(relevance, one_item_relevance)

    def test_censor_aware_fusion_penalizes_a_single_source_outlier(self):
        releases = [
            ServerRelease(
                0,
                "OLH",
                (0, 1),
                {0: 0.30, 1: 0.25},
                {0: 0.0025, 1: 0.0025},
            ),
            ServerRelease(
                1,
                "OLH",
                (0, 2),
                {0: 0.28, 2: 0.24},
                {0: 0.0025, 2: 0.0025},
            ),
            ServerRelease(
                2,
                "OLH",
                (3, 4),
                {3: 0.60, 4: 0.55},
                {3: 0.0025, 4: 0.0025},
            ),
        ]
        context = np.array([0.35, 0.15, 0.15, 0.20, 0.15])
        old_prediction = fuse_item_level_anchor(releases, context, 1)
        new_prediction = fuse_censor_aware_item_context(
            releases, context, report_k=2, k=1
        )
        self.assertEqual(old_prediction, [3])
        self.assertEqual(new_prediction, [0])

    def test_summary_reports_round_variability(self):
        rows = run(
            ExperimentConfig(
                domain=32,
                users_per_server=100,
                server_count=3,
                top_k=4,
                rounds=2,
                mechanisms=("OLH",),
            )
        )
        records = summarize(rows)
        self.assertTrue(records)
        self.assertEqual(records[0]["rounds"], 2)
        self.assertIn("recall_std", records[0])
        self.assertGreaterEqual(records[0]["recall_std"], 0.0)


if __name__ == "__main__":
    unittest.main()
