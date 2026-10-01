"""Command-line entry point (defaults preserve the laptop experiment)."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiment import (
    ALLOWED_MECHANISMS,
    SOURCE_CONDITIONS,
    ExperimentConfig,
    run,
    summarize,
    write_results,
)
from problem_definition import VisibilityContract
from simulation import CONTEXT_CONDITIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate a new server's target top-k from existing LDP releases."
    )
    parser.add_argument("--domain", type=int, default=128)
    parser.add_argument("--users-per-server", type=int, default=1500)
    parser.add_argument("--servers", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--epsilon", type=float, default=2.0)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument(
        "--context-quality", "--anchor-quality", dest="context_quality", type=float, default=0.7,
        help="quality of the public target context (legacy alias: --anchor-quality)",
    )
    parser.add_argument("--server-budget", type=int, default=3)
    parser.add_argument("--report-ratio", type=float, default=2.0)
    parser.add_argument(
        "--context-candidate-ratio",
        type=float,
        default=0.0,
        help="add top-r*k items from public target context to the local candidate set",
    )
    parser.add_argument(
        "--context-condition", choices=CONTEXT_CONDITIONS, default="clean"
    )
    parser.add_argument(
        "--source-condition", choices=SOURCE_CONDITIONS, default="clean"
    )
    parser.add_argument("--affected-source-fraction", type=float, default=0.34)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument(
        "--mechanisms",
        nargs="+",
        choices=ALLOWED_MECHANISMS,
        default=list(ALLOWED_MECHANISMS),
    )
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--visibility-anchor",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="whether the new server has public target context (legacy flag name)",
    )
    parser.add_argument(
        "--no-public-context",
        action="store_true",
        help="explicitly run the no-context identifiability baseline",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ExperimentConfig(
        domain=args.domain,
        users_per_server=args.users_per_server,
        server_count=args.servers,
        top_k=args.top_k,
        epsilon=args.epsilon,
        rounds=args.rounds,
        context_quality=args.context_quality,
        adaptive_server_budget=args.server_budget,
        report_ratio=args.report_ratio,
        context_candidate_ratio=args.context_candidate_ratio,
        context_condition=args.context_condition,
        source_condition=args.source_condition,
        affected_source_fraction=args.affected_source_fraction,
        seed=args.seed,
        mechanisms=tuple(args.mechanisms),
        visibility=VisibilityContract(
            public_target_context=args.visibility_anchor and not args.no_public_context
        ),
    )
    rows = run(config)
    write_results(rows, args.output)
    print("scenario method                 recall  ndcg  coverage candidates")
    for row in summarize(rows):
        print(
            f"{row['scenario']:<8} {row['method']:<22} "
            f"{row['recall']:.3f}   {row['ndcg']:.3f}  "
            f"{row['coverage']:.3f}    {row['candidate_size']:.1f}"
        )
    print(f"\nDetailed results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
