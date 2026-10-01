"""G6: robustness to unrelated, stale, malicious, or missing sources."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig


def run() -> None:
    cases = [
        ExperimentCase(
            name=f"{condition}_sources",
            description=f"Weak-context transfer with {condition} source servers.",
            config=ExperimentConfig(
                context_quality=0.25,
                source_condition=condition,
                affected_source_fraction=0.0 if condition == "clean" else 0.34,
                rounds=3,
                mechanisms=("MIXED",),
            ),
        )
        for condition in ("clean", "unrelated", "stale", "adversarial", "missing")
    ]
    cases.extend(
        ExperimentCase(
            name=f"adversarial_fraction_{str(fraction).replace('.', '_')}",
            description=f"Summary poisoning affecting {fraction:.0%} of source servers.",
            config=ExperimentConfig(
                context_quality=0.25,
                source_condition="adversarial",
                affected_source_fraction=fraction,
                rounds=3,
                mechanisms=("MIXED",),
            ),
        )
        for fraction in (0.17, 0.5)
    )
    run_group("G6_source_robustness", cases)


if __name__ == "__main__":
    run()
