"""Count negative published frequencies in honest summaries over the UTILITY_V1 grid.

If there are none, the clip_floor=0 hardening cannot change any honest-data result."""

from __future__ import annotations

import argparse

import numpy as np

from ..adapters.standard import load
from ..ldp import perturb
from ..pipeline import summarize_reports
from .runner import Run
from .security_v1 import EPSILON_GRID, SEEDS, USERS
from .utility_v1 import TOP_MS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", default="massive_steps,olist_brazil,meituan_trd")
    args = parser.parse_args()
    report = {}
    hashes = {}
    for name in args.datasets.split(","):
        data = load(name)
        hashes |= {f"{name}/{k}": v for k, v in data.file_sha256.items()}
        servers, domain = data.servers, data.domain
        published = negative = 0
        worst = 0.0
        for seed in SEEDS:
            for source in servers:
                srng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, 17]))
                sample = data.events[source][srng.permutation(len(data.events[source]))[:USERS]]
                for e_index, epsilon in enumerate(EPSILON_GRID):
                    prng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, e_index, 99]))
                    reports = perturb(sample, domain, epsilon, prng)
                    for top_m in TOP_MS:
                        for defense in (False, True):
                            items = summarize_reports(reports, domain, top_m, defense)[0]
                            values = [item.frequency for item in items]
                            published += len(values)
                            negative += sum(v < 0 for v in values)
                            worst = min(worst, min(values))
        report[name] = {"published_values": published, "negative_values": negative, "min_value": worst}
        print(name, report[name], flush=True)
    run = Run("negative_check", {"datasets": args.datasets.split(","), "seeds": SEEDS, "epsilons": EPSILON_GRID,
                                 "top_ms": TOP_MS, "users_per_source": USERS}, hashes)
    run.write_json("results.json", report)
    run.finish(["results.json"])
    print(run.dir)


if __name__ == "__main__":
    main()
