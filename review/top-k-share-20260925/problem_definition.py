"""Formal information boundary for target-distribution transfer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisibilityContract:
    """Information available to the new server during inference."""

    published_top2k: bool = True
    published_frequencies: bool = True
    published_variances: bool = True
    public_target_context: bool = True
    source_raw_users: bool = False
    target_raw_users: bool = False
    target_distribution: bool = False
    true_source_target_similarity: bool = False
    additional_target_reports: bool = False

    def validate(self) -> None:
        if not self.published_top2k:
            raise ValueError("top-2k releases are required by the problem definition")
        forbidden = {
            "source_raw_users": self.source_raw_users,
            "target_raw_users": self.target_raw_users,
            "target_distribution": self.target_distribution,
            "true_source_target_similarity": self.true_source_target_similarity,
            "additional_target_reports": self.additional_target_reports,
        }
        enabled = [name for name, value in forbidden.items() if value]
        if enabled:
            raise ValueError(
                "deployable inference cannot use forbidden information: "
                + ", ".join(enabled)
            )


DEFAULT_VISIBILITY = VisibilityContract()
