"""G8: sensitivity of the censor-aware method to its two new parameters."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment import ExperimentConfig
from experiments.common import ExperimentCase, run_group


PRIOR_VALUES = (0.0, 0.01, 0.03, 0.10, 0.30, 1.0)
TRANSFER_VALUES = (0.0, 0.25, 0.50, 1.0, 2.0, 4.0)
JOINT_PRIOR_VALUES = (0.03, 0.10, 0.30)
JOINT_TRANSFER_VALUES = (0.50, 1.0, 2.0)
DEFAULT_PRIOR = 0.10
DEFAULT_TRANSFER = 1.0
SENSITIVITY_SEED = 20260909


def _label(value: float) -> str:
    return str(value).replace(".", "_")


def _config(prior: float, transfer: float) -> ExperimentConfig:
    return ExperimentConfig(
        context_quality=0.25,
        censor_prior_strength=prior,
        censor_transfer_scale=transfer,
        rounds=3,
        seed=SENSITIVITY_SEED,
        mechanisms=("OLH", "MIXED"),
    )


def build_cases() -> list[ExperimentCase]:
    cases = [
        ExperimentCase(
            name=f"prior_{_label(prior)}",
            description=(
                f"Prior-strength sweep: prior={prior}, "
                f"transfer={DEFAULT_TRANSFER}."
            ),
            config=_config(prior, DEFAULT_TRANSFER),
        )
        for prior in PRIOR_VALUES
    ]
    cases.extend(
        ExperimentCase(
            name=f"transfer_{_label(transfer)}",
            description=(
                f"Transfer-scale sweep: prior={DEFAULT_PRIOR}, "
                f"transfer={transfer}."
            ),
            config=_config(DEFAULT_PRIOR, transfer),
        )
        for transfer in TRANSFER_VALUES
    )
    cases.extend(
        ExperimentCase(
            name=f"joint_p_{_label(prior)}_t_{_label(transfer)}",
            description=f"Joint sensitivity grid: prior={prior}, transfer={transfer}.",
            config=_config(prior, transfer),
        )
        for prior in JOINT_PRIOR_VALUES
        for transfer in JOINT_TRANSFER_VALUES
    )
    return cases


def run() -> None:
    run_group("G8_parameter_sensitivity", build_cases())


if __name__ == "__main__":
    run()
