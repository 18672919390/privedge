"""Small, data-free end-to-end run; not a statistical performance experiment."""
import json
import numpy as np

from experiment import ExperimentConfig, _release, run
from fusion import candidate_set
from two_stage_transfer import (candidate_top_k, fit_target_mixture,
                                reconstruct_sources, zero_filled_sources)
from experiments.validation.two_stage_synthetic import problem


def main():
    config = ExperimentConfig(domain=128, users_per_server=200, server_count=6,
                              top_k=10, epsilon=2, mechanisms=('OLH',), rounds=1)
    rows = run(config)
    assert rows and all(np.isfinite(r['recall']) for r in rows)
    sources, targets, contexts, _ = problem(20260925)
    releases = [_release(i, source, 'OLH', config,
                         np.random.default_rng(np.random.SeedSequence([20260925, i])))
                for i, source in enumerate(sources)]
    direct = zero_filled_sources(releases, config.domain)
    rebuilt = reconstruct_sources(releases, config.domain, prior_strength=.1, shift_tolerance=0)
    candidates = candidate_set(releases)
    checks = []
    for matrix in [direct, np.asarray([result.probabilities for result in rebuilt])]:
        for context in contexts:
            fit = fit_target_mixture(matrix, context)
            prediction = candidate_top_k(fit.probabilities, releases, config.top_k)
            assert len(prediction) == config.top_k and set(prediction) <= candidates
            assert np.all(np.isfinite(fit.probabilities))
            assert np.isclose(fit.weights.sum(), 1)
            checks.append(len(prediction))
    print(json.dumps(dict(status='PASS', main_experiment_rows=len(rows),
                          two_stage_predictions=len(checks), external_data_required=False)))


if __name__ == '__main__':
    main()
