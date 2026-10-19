"""Property checks for the proved domain of the robust-fusion influence bound."""

import numpy as np

from privedge.algorithms import ServerRelease
from privedge.robust import capped_weights, winsorize_releases


ITEMS = (0, 1, 2, 3)


def _release(index, weight, frequencies):
    variance = 1.0 / weight**2
    return ServerRelease(
        index,
        "OLH",
        ITEMS,
        dict(zip(ITEMS, frequencies)),
        {item: variance for item in ITEMS},
    )


def test_stronger_peer_majority_bounds_weight_share_and_item_influence():
    rng = np.random.default_rng(20261014)
    for n in range(4, 10):
        max_f = int(np.ceil((n - 1) / 2)) - 1
        for _ in range(25):
            f = int(rng.integers(1, max_f + 1))
            honest_weights = rng.uniform(0.7, 1.4, size=n - f)
            malicious_weights = 10.0 ** rng.uniform(-5, 5, size=f)
            raw_weights = np.r_[malicious_weights, honest_weights]
            honest_values = rng.uniform(0.0, 1.0, size=(n - f, len(ITEMS)))
            malicious_values = rng.uniform(-20.0, 100.0, size=(f, len(ITEMS)))
            values = np.vstack([malicious_values, honest_values])
            releases = [
                _release(s, raw_weights[s], values[s]) for s in range(n)
            ]
            kappa = float(rng.uniform(1.0, 3.0))
            clip_z = float(rng.uniform(0.0, 4.0))
            rel_floor = float(rng.uniform(0.0, 0.5))

            clipped, _ = winsorize_releases(
                releases, clip_z=clip_z, rel_floor=rel_floor, floor=0.0
            )
            capped = capped_weights(releases, kappa)
            actual_alpha = float(capped[:f].sum() / capped.sum())
            w, W = float(honest_weights.min()), float(honest_weights.max())
            alpha_bound = f * kappa * W / ((n - f) * w + f * kappa * W)
            assert actual_alpha <= alpha_bound + 1e-12

            for item_index, item in enumerate(ITEMS):
                honest_var = np.array(
                    [releases[s].variances[item] for s in range(f, n)]
                )
                raw_honest_x = values[f:, item_index]
                honest_x = np.array(
                    [clipped[s].frequencies[item] for s in range(f, n)]
                )
                M = float(raw_honest_x.max())
                R = float(raw_honest_x.max() - raw_honest_x.min())
                V = float(honest_var.max())
                U = M + clip_z * np.sqrt(
                    V + (1.4826 * R) ** 2 + (rel_floor * M) ** 2 + 1e-10
                )
                assert all(clipped[s].frequencies[item] <= U + 1e-10 for s in range(f))

                honest_score = float(
                    np.dot(capped[f:], honest_x) / capped[f:].sum()
                )
                all_score = float(
                    np.dot(capped, [clipped[s].frequencies[item] for s in range(n)])
                    / capped.sum()
                )
                assert (1.0 - actual_alpha) * honest_score - 1e-10 <= all_score
                assert all_score <= (
                    (1.0 - alpha_bound) * honest_score + alpha_bound * U + 1e-10
                )


def test_old_majority_condition_does_not_imply_honest_weight_floor():
    # n=4, f=2 satisfies f < (n+1)/2, but honest peers have median weight 1e-12.
    raw = np.array([1e-12, 1e-12, 1.0, 1.0])
    kappa = 2.0
    releases = [_release(s, raw[s], [0.5] * len(ITEMS)) for s in range(len(raw))]
    capped = capped_weights(releases, kappa)
    assert np.all(capped[2:] < raw[2:].min())

    # This witnesses a gap in the old proof step only; it does not violate its
    # stated adversarial-share formula.
    actual_alpha = float(capped[:2].sum() / capped.sum())
    alpha_bound = 2 * kappa * 1.0 / (2 * 1.0 + 2 * kappa * 1.0)
    assert actual_alpha <= alpha_bound
