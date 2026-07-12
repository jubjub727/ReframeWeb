from __future__ import annotations


def add_benchmark_parsers(subparsers) -> None:
    task_choice = _benchmark_parser(
        subparsers,
        "task-choice",
        "Measure task-choice correctness and latency across direct model providers.",
    )
    task_choice.add_argument(
        "--session-id",
        help="Active session id used for conversation and session memory context.",
    )

    _benchmark_parser(
        subparsers,
        "conversation-evaluation",
        "Record conversation-evaluation memory-search hints across models.",
    )

    control_flow = _benchmark_parser(
        subparsers,
        "control-flow",
        "Snapshot upstream memory context, then benchmark search-depth models.",
    )
    control_flow.add_argument(
        "--search-depth-model-id",
        default=None,
        help="OpenCode Go model id for search-depth benchmarking. Defaults to glm-5.1.",
    )

    _benchmark_parser(
        subparsers,
        "memory-relevance",
        "Benchmark memory relevance over one reusable candidate snapshot per case.",
    )

    task_prompt = _benchmark_parser(
        subparsers,
        "task-prompt",
        "Benchmark task-prompt generation over one selected-memory snapshot per case.",
    )
    task_prompt.add_argument(
        "--refresh-snapshots",
        action="store_true",
        help="Rebuild real memory snapshots instead of reusing cached ones.",
    )

    _analysis_parser(
        subparsers,
        "task-choice",
        "Summarize failures from a saved task-choice benchmark JSON file.",
    )
    _analysis_parser(
        subparsers,
        "conversation-evaluation",
        "Show conversation-evaluation replies ordered by latency.",
        british_alias=True,
    )
    _analysis_parser(
        subparsers,
        "control-flow",
        "Show control-flow latency and search-depth age summaries.",
        british_alias=True,
    )


def _benchmark_parser(subparsers, name: str, help_text: str):
    parser = subparsers.add_parser(f"benchmark-{name}", help=help_text)
    parser.add_argument(
        "--provider-id",
        action="append",
        dest="provider_ids",
        help="Direct model provider id to test. Repeat to test a subset.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Benchmark case id to run. Repeat to test a subset.",
    )
    _add_reasoning_effort_args(parser)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmup-runs", type=int, default=0)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--provider-cooldown-seconds", type=float, default=8.0)
    parser.add_argument(
        "--output",
        help=(
            "Path to write benchmark JSON. Defaults to "
            f"benchmark-results/{name}-<timestamp>.json."
        ),
    )
    return parser


def _add_reasoning_effort_args(parser) -> None:
    parser.add_argument(
        "--reasoning-effort",
        action="append",
        dest="reasoning_efforts",
        help="Reasoning effort to run. Repeat to bypass capability discovery.",
    )
    parser.add_argument(
        "--reasoning-effort-candidate",
        action="append",
        dest="reasoning_effort_candidates",
        help="Reasoning effort to probe. Repeat to replace the default candidates.",
    )


def _analysis_parser(
    subparsers,
    name: str,
    help_text: str,
    *,
    british_alias: bool = False,
) -> None:
    command = f"analyze-{name}-benchmark"
    aliases = [f"analyse-{name}-benchmark"] if british_alias else []
    parser = subparsers.add_parser(command, aliases=aliases, help=help_text)
    parser.add_argument("path")
