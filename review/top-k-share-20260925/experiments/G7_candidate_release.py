"""G7: candidate coverage, public-context expansion, and communication cost."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig


def run() -> None:
    cases = [
        ExperimentCase(
            name=f"report_ratio_{str(ratio).replace('.', '_')}",
            description=(
                f"Server-only candidate baseline: each source publishes top-{ratio}k."
            ),
            config=ExperimentConfig(
                context_quality=0.25,
                report_ratio=ratio,
                context_candidate_ratio=0.0,
                rounds=3,
                mechanisms=("OLH", "MIXED"),
            ),
        )
        for ratio in (1.0, 1.5, 2.0, 3.0)
    ]
    cases.extend(
        ExperimentCase(
            name=f"context_expand_{str(context_ratio).replace('.', '_')}",
            description=(
                f"Top-2k server release plus top-{context_ratio}k public-context candidates."
            ),
            config=ExperimentConfig(
                context_quality=0.25,
                report_ratio=2.0,
                context_candidate_ratio=context_ratio,
                rounds=3,
                mechanisms=("OLH", "MIXED"),
            ),
        )
        for context_ratio in (1.0, 2.0, 5.0)
    )
    for condition in ("noisy", "misleading"):
        cases.append(
            ExperimentCase(
                name=f"{condition}_context_expand_2_0",
                description=(
                    f"Top-2k server release plus top-2k {condition} public-context candidates."
                ),
                config=ExperimentConfig(
                    context_quality=0.25,
                    context_condition=condition,
                    report_ratio=2.0,
                    context_candidate_ratio=2.0,
                    rounds=3,
                    mechanisms=("OLH", "MIXED"),
                ),
            )
        )
    run_group("G7_candidate_release", cases)


if __name__ == "__main__":
    run()
