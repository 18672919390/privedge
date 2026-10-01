import unittest
import numpy as np

from censor_estimator import build_design, project_simplex, solve, value_gradient
from fusion import ServerRelease


class CensorEstimatorTests(unittest.TestCase):
    def release(self, items=(0, 1), values=(.6, .3)):
        return ServerRelease(0, "OUE", items, dict(zip(items, values)), dict.fromkeys(items, .01))

    def test_projection_and_full_release_analytic_solution(self):
        np.testing.assert_allclose(project_simplex(np.array([2., 1., -4.])), [1, 0, 0])
        release = self.release((0, 1, 2), (.6, .3, .1))
        q = np.array([.1, .2, .7])
        result = solve(build_design([release], q, shift_tolerance=0, prior_strength=2))
        np.testing.assert_allclose(result.probabilities, (np.array([.6, .3, .1]) + 2*q)/3, atol=1e-7)
        self.assertTrue(result.converged)

    def test_gradient_convexity_and_certificate(self):
        design = build_design([self.release()], np.array([.1, .2, .3, .4]), shift_tolerance=.02)
        x = np.array([.2, .1, .3, .4])
        value, gradient = value_gradient(x, design)
        for i in range(4):
            direction = np.eye(4)[i] * 1e-6
            numeric = (value_gradient(x + direction, design)[0] - value_gradient(x - direction, design)[0])/2e-6
            self.assertAlmostEqual(numeric, gradient[i], places=7)
        optimum = solve(design, tolerance=1e-14)
        early = solve(design, tolerance=1e-14, max_iterations=1)
        self.assertLessEqual(early.objective - optimum.objective, early.dual_gap + 1e-12)
        self.assertLessEqual(np.linalg.norm(early.probabilities - optimum.probabilities), early.optimization_l2_bound + 1e-6)
        self.assertAlmostEqual(optimum.probabilities.sum(), 1)
        self.assertTrue(np.all(optimum.probabilities >= 0))
        self.assertLessEqual(value_gradient((x+optimum.probabilities)/2, design)[0], (value+optimum.objective)/2 + 1e-12)

    def test_missing_high_prior_is_penalized_and_pem_rejected(self):
        q = np.array([.1, .1, .8])
        release = self.release()
        censored = solve(build_design([release], q))
        ignored = solve(build_design([release], q, use_censoring=False))
        self.assertLess(censored.probabilities[2], ignored.probabilities[2])
        self.assertEqual(censored.top_k(1, {0, 1}), [0])
        with self.assertRaises(ValueError):
            build_design([ServerRelease(0, "PEM", release.top_items, release.frequencies, release.variances)], q)

    def test_invalid_public_inputs_and_nonconvergence_flag(self):
        with self.assertRaises(ValueError):
            build_design([self.release()], np.array([.5, np.nan]))
        with self.assertRaises(ValueError):
            build_design([self.release()], np.array([.5,.5]), prior_strength=0)
        result = solve(build_design([self.release()], np.array([.1,.2,.7])), max_iterations=1, tolerance=1e-30)
        self.assertFalse(result.converged)


if __name__ == "__main__":
    unittest.main()
