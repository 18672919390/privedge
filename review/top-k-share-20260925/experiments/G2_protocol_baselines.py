"""G2: classical protocol and basic fusion baselines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig


def run() -> None:
    run_group(
        "G1_protocol_baselines",
        [
            ExperimentCase(
                name=f"epsilon_{str(epsilon).replace('.', '_')}",
                description=f"Classical LDP protocols at epsilon={epsilon}.",
                config=ExperimentConfig(
                    epsilon=epsilon,
                    rounds=3,
                    mechanisms=("PEM", "GRR", "OUE", "OLH"),
                ),
            )
            for epsilon in (1.0, 2.0, 4.0)
        ],
    )


if __name__ == "__main__":
    run()
