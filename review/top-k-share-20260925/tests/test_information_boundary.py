"""Regression checks for the public-input contract; not a privacy proof."""

import unittest
from unittest.mock import patch

import numpy as np

from experiment import ExperimentConfig, _predictions, _release
from fusion import ServerRelease
from ldp_protocols import FrequencyEstimate
from simulation import SyntheticProblem


class InformationBoundaryTests(unittest.TestCase):
    def test_hidden_world_does_not_change_deployable_predictions(self):
        domain = 16
        releases = [
            ServerRelease(0, "OUE", (0, 1, 2, 3),
                          {0: .6, 1: .3, 2: .2, 3: .1}, dict.fromkeys(range(4), .01)),
            ServerRelease(1, "OLH", (4, 5, 6, 7),
                          {4: .6, 5: .3, 6: .2, 7: .1}, dict.fromkeys(range(4, 8), .01)),
        ]
        first = np.zeros(domain)
        first[:2] = [.8, .2]
        second = np.zeros(domain)
        second[4:6] = [.8, .2]
        a = SyntheticProblem(first, [first, first], np.array([1., 0.]), first)
        b = SyntheticProblem(second, [second, second], np.array([0., 1.]), second)
        config = ExperimentConfig(domain=domain, top_k=2, server_count=2,
                                  adaptive_server_budget=1, context_candidate_ratio=2.)
        public_context = np.arange(domain, 0, -1, dtype=float)
        public_context /= public_context.sum()
        diagnostics = {"oracle_weighted", "global_true_average"}
        for observed in (public_context, None):
            with self.subTest(context_visible=observed is not None):
                left = _predictions(releases, a, config, observed)
                right = _predictions(releases, b, config, observed)
                for name in left.keys() - diagnostics:
                    self.assertEqual(left[name], right[name], name)
                self.assertNotEqual(left["oracle_weighted"], right["oracle_weighted"])
                self.assertNotEqual(left["global_true_average"], right["global_true_average"])
                if observed is None:
                    self.assertEqual(left["censor_aware_item_context"], left["average"])

    def test_fixed_perturbed_estimate_gives_same_release_for_different_raw_populations(self):
        # At the publisher boundary, hold the FO output fixed. Changing raw
        # sampled users must not add a second channel through frequency/variance.
        config = ExperimentConfig(domain=16, top_k=2, users_per_server=50)
        estimate = FrequencyEstimate(np.arange(16, dtype=float),
                                     np.arange(16, dtype=float) + 1, "OUE")
        first = np.eye(16)[0]
        second = np.eye(16)[15]
        with patch("experiment.estimate_frequency", return_value=estimate):
            a = _release(0, first, "OUE", config, np.random.default_rng(1))
            b = _release(0, second, "OUE", config, np.random.default_rng(2))
        self.assertEqual(a, b)
        self.assertEqual(a.variances[15], 16 / 50**2)


if __name__ == "__main__":
    unittest.main()
