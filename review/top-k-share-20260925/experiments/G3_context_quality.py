"""G3: public target-context availability and quality."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import ExperimentCase, run_group
from experiment import ExperimentConfig
from problem_definition import VisibilityContract


def run() -> None:
    cases = [
        ExperimentCase(
            name="no_context",
            description="No target-side information; context methods fall back to average.",
            config=ExperimentConfig(
                visibility=VisibilityContract(public_target_context=False),
                context_quality=0.5,
                rounds=3,
                mechanisms=("OLH", "MIXED"),
            ),
        )
    ]
    cases.extend(
        ExperimentCase(
            name=f"context_quality_{str(quality).replace('.', '_')}",
            description=f"Visible clean public target context with quality={quality}.",
            config=ExperimentConfig(
                context_quality=quality,
                rounds=3,
                mechanisms=("OLH", "MIXED"),
            ),
        )
        for quality in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    run_group("G2_context_quality", cases)


if __name__ == "__main__":
    run()
