import unittest
import numpy as np

from fusion import ServerRelease
from two_stage_transfer import (candidate_tail_features, candidate_top_k, equal_mix,
                                fit_candidate_target_mixture, fit_target_mixture,
                                reconstruct_candidate_tail, reconstruct_sources,
                                zero_filled_sources)


class TwoStageTransferTests(unittest.TestCase):
    def setUp(self):
        self.releases = [
            ServerRelease(0, 'OLH', (0, 1), {0: .7, 1: .2}, {0: .01, 1: .01}),
            ServerRelease(1, 'OLH', (2, 3), {2: .6, 3: .3}, {2: .01, 3: .01}),
        ]

    def test_reconstruction_is_target_independent_probability(self):
        first = reconstruct_sources(self.releases, 4)
        second = reconstruct_sources(self.releases, 4)
        for a, b in zip(first, second):
            np.testing.assert_allclose(a.probabilities, b.probabilities)
            self.assertAlmostEqual(a.probabilities.sum(), 1)
            self.assertTrue(np.all(a.probabilities >= 0))

    def test_context_changes_weights_and_prediction(self):
        sources = np.array([[.8, .2, 0, 0], [0, 0, .7, .3]])
        a = fit_target_mixture(sources, np.array([.7, .2, .05, .05]), ridge=.01)
        b = fit_target_mixture(sources, np.array([.05, .05, .6, .3]), ridge=.01)
        self.assertGreater(a.weights[0], a.weights[1])
        self.assertGreater(b.weights[1], b.weights[0])
        self.assertNotEqual(candidate_top_k(a.probabilities, self.releases, 1),
                            candidate_top_k(b.probabilities, self.releases, 1))

    def test_zero_fill_equal_mix_matches_direct_average_order(self):
        mixed = equal_mix(zero_filled_sources(self.releases, 4))
        self.assertEqual(candidate_top_k(mixed, self.releases, 2), [0, 2])

    def test_candidate_tail_preserves_mass_and_aggregates_unidentified_items(self):
        releases = [ServerRelease(0, 'OLH', (0, 1), {0: .4, 1: .2},
                                  {0: .01, 1: .01})]
        result = reconstruct_candidate_tail(releases, 6)[0].probabilities
        self.assertAlmostEqual(result.sum(), 1)
        np.testing.assert_allclose(result[2:], np.full(4, result[2]))
        features = candidate_tail_features(result, releases)[0]
        np.testing.assert_allclose(features, [result[0], result[1], result[2:].sum()])

    def test_candidate_feature_mixture_ignores_tail_allocation(self):
        sources = np.array([[.6,.2,.05,.05,.05,.05], [.1,.1,.2,.2,.2,.2]])
        context = np.array([.5,.2,.075,.075,.075,.075])
        fitted = fit_candidate_target_mixture(sources, context, self.releases, ridge=.01)
        changed = sources.copy()
        changed[:, 4] += changed[:, 5]
        changed[:, 5] = 0
        altered = fit_candidate_target_mixture(changed, context, self.releases, ridge=.01)
        np.testing.assert_allclose(fitted.weights, altered.weights, atol=1e-12)
        self.assertAlmostEqual(fitted.weights.sum(), 1)
        self.assertAlmostEqual(fitted.probabilities.sum(), 1)


if __name__ == '__main__':
    unittest.main()
