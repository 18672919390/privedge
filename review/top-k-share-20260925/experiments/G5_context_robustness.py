"""G5: robustness to incomplete, noisy, stale, or misleading context."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig


def run() -> None:
    run_group(
        "G5_context_robustness",
        [
            ExperimentCase(
                name=f"{condition}_context",
                description=f"Weak public context under the {condition} condition.",
                config=ExperimentConfig(
                    context_quality=0.25,
                    context_condition=condition,
                    rounds=3,
                    mechanisms=("OLH", "MIXED"),
                ),
            )
            for condition in (
                "clean",
                "partial",
                "noisy",
                "misleading",
                "outdated",
                "adversarial",
            )
        ],
    )


if __name__ == "__main__":
    run()
