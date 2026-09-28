"""Command-line interface for the Soroban H1/H2 audit harness."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .provider_config import add_provider_arguments, configuration_from_args
from .runner import DEFAULT_KNOWLEDGE, HARNESS_MODES, scan_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="soroban-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="Run H1, H2, or both against a repository")
    scan.add_argument("repository", type=Path)
    scan.add_argument("--ref", help="Git branch, tag, or commit to analyze (default: HEAD)")
    scan.add_argument("--harness", choices=HARNESS_MODES, default="both")
    scan.add_argument("--output-root", type=Path, default=Path("soroban-audit-runs"))
    scan.add_argument(
        "--knowledge-dir",
        type=Path,
        action="append",
        default=[],
        help="Additional generalized H2 packet directory containing catalog.json",
    )
    scan.add_argument(
        "--codex",
        default=shutil.which("codex") or "/Applications/Codex.app/Contents/Resources/codex",
    )
    scan.add_argument("--stage-retries", type=int, default=2)
    scan.add_argument("--timeout-seconds", type=int, default=1800)
    scan.add_argument("--rate-limit-retries", type=int, default=0)
    scan.add_argument("--rate-limit-cooldown-seconds", type=int, default=600)
    scan.add_argument("--print-configuration", action="store_true")
    add_provider_arguments(scan)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stage_retries < 0 or args.rate_limit_retries < 0:
        parser.error("retry counts must be nonnegative")
    if args.timeout_seconds <= 0 or args.rate_limit_cooldown_seconds < 0:
        parser.error("timeout must be positive and cooldown must be nonnegative")
    try:
        config = configuration_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.print_configuration:
        repository = args.repository.expanduser().resolve()
        payload = {
            **config.identity(),
            "repository": str(repository),
            "reference": args.ref or "HEAD",
            "harness": args.harness,
            "outputRoot": str(args.output_root.expanduser().resolve()),
            "defaultKnowledge": str(DEFAULT_KNOWLEDGE),
            "additionalKnowledge": [str(path.expanduser().resolve()) for path in args.knowledge_dir],
        }
        print(json.dumps(payload, indent=2))
        return

    try:
        config.validate_environment()
        run_dir = scan_repository(
            repository=args.repository,
            reference=args.ref,
            harness=args.harness,
            output_root=args.output_root,
            codex=args.codex,
            config=config,
            additional_knowledge_dirs=args.knowledge_dir,
            retries=args.stage_retries,
            timeout_seconds=args.timeout_seconds,
            rate_limit_retries=args.rate_limit_retries,
            rate_limit_cooldown_seconds=args.rate_limit_cooldown_seconds,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"scan complete: {run_dir}")


if __name__ == "__main__":
    main()
