"""G4: heterogeneous mechanisms, epsilon, and server population sizes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig


def run() -> None:
    homogeneous_eps = (2.0,) * 6
    heterogeneous_eps = (0.8, 1.2, 1.6, 2.0, 2.4, 3.0)
    homogeneous_users = (1500,) * 6
    heterogeneous_users = (600, 900, 1200, 1500, 1800, 2400)
    run_group(
        "G4_heterogeneous",
        [
            ExperimentCase(
                name="homogeneous_olh",
                description="Homogeneous OLH, epsilon, and source population baseline.",
                config=ExperimentConfig(rounds=3, mechanisms=("OLH",)),
            ),
            ExperimentCase(
                name="heterogeneous_mechanisms",
                description="Mixed PEM/GRR/OUE/OLH with homogeneous epsilon and population.",
                config=ExperimentConfig(rounds=3, mechanisms=("MIXED",)),
            ),
            ExperimentCase(
                name="heterogeneous_epsilon",
                description="OLH sources with heterogeneous privacy budgets.",
                config=ExperimentConfig(
                    rounds=3,
                    mechanisms=("OLH",),
                    server_epsilons=heterogeneous_eps,
                ),
            ),
            ExperimentCase(
                name="heterogeneous_population",
                description="OLH sources with heterogeneous user populations.",
                config=ExperimentConfig(
                    rounds=3,
                    mechanisms=("OLH",),
                    server_user_counts=heterogeneous_users,
                ),
            ),
            ExperimentCase(
                name="fully_heterogeneous",
                description="Mixed mechanisms, epsilon values, and source populations.",
                config=ExperimentConfig(
                    rounds=3,
                    mechanisms=("MIXED",),
                    server_epsilons=heterogeneous_eps,
                    server_user_counts=heterogeneous_users,
                ),
            ),
        ],
    )


if __name__ == "__main__":
    run()
