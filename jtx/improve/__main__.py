"""``jtx-improve`` CLI — runs the Tier-A closed-loop session or a leaderboard.

Examples::

    jtx-improve run --tier A --budget-iter 50 --budget-wall 4h \\
                    --branch auto/improve/$(date +%Y%m%dT%H%M%SZ)

    jtx-improve leaderboard

The ``run`` subcommand is the closed loop; ``leaderboard`` scans
``eval_runs/`` and prints a sorted table. Tier B / C live in later
phases; passing ``--tier`` anything but ``A`` errors out so an early
typo doesn't silently run Tier-A behavior.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from jtx.improve.corpus import Corpus, default_corpus, load_corpus
from jtx.improve.driver import SessionConfig, run_session
from jtx.improve.report import load_sessions
from jtx.improve.reward import RewardWeights

_DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[2] / "eval_runs"


def _parse_duration(text: str) -> float:
    """Convert ``4h`` / ``30m`` / ``120s`` / bare number → seconds."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", text)
    if m is None:
        raise argparse.ArgumentTypeError(
            f"invalid duration {text!r} (expected e.g. '4h', '30m', '120s')"
        )
    value = float(m.group(1))
    unit = m.group(2) or "s"
    return value * {"s": 1.0, "m": 60.0, "h": 3600.0}[unit]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jtx-improve",
        description="Tier-A closed-loop optimizer over tuning.toml.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run one Tier-A optimization session.")
    run_p.add_argument(
        "--tier", choices=["A"], default="A",
        help="Modify surface. Only 'A' (knob windows) ships in Phase 2b.",
    )
    run_p.add_argument(
        "--budget-iter", type=int, default=50,
        help="Maximum iterations per session (default: 50).",
    )
    run_p.add_argument(
        "--budget-wall", type=_parse_duration, default=4 * 3600.0,
        help="Wall-clock budget per session (e.g. 4h, 30m). Default 4h.",
    )
    run_p.add_argument(
        "--plateau", type=int, default=25,
        help="Halt after this many consecutive rejections (default: 25).",
    )
    run_p.add_argument(
        "--seed", type=int, default=0,
        help="Proposer RNG seed — pin for reproducible sessions.",
    )
    run_p.add_argument(
        "--params-per-step", type=int, default=3,
        help="How many scalars one proposal perturbs (default: 3).",
    )
    run_p.add_argument(
        "--temperature", type=float, default=1.0,
        help="Initial perturbation scale multiplier (default: 1.0).",
    )
    run_p.add_argument(
        "--cooling", type=float, default=0.97,
        help="Temperature decay per iteration (default: 0.97).",
    )
    run_p.add_argument(
        "--hard-floor", type=float, default=0.05,
        help="Reject any candidate that drops a single anchor by more "
             "than this much from running best (default: 0.05).",
    )
    run_p.add_argument(
        "--branch", default=None,
        help="If set, 'git checkout -b <branch>' before iterating; the "
             "loop's commits land on it.",
    )
    run_p.add_argument(
        "--no-commit", action="store_true",
        help="Skip git commits (dry-run mode). Implies no branch creation.",
    )
    run_p.add_argument(
        "--skip-pytest", action="store_true",
        help="Skip the per-iteration pytest gate. Use only when the "
             "session is short and you already know the suite is green.",
    )
    run_p.add_argument(
        "--pytest-args", default="-q,--no-header",
        help="Comma-separated args forwarded to pytest "
             "(default: '-q,--no-header').",
    )
    run_p.add_argument(
        "--corpus", type=Path, default=None,
        help="Path to an eval_corpus.toml. Default is the in-package corpus.",
    )
    run_p.add_argument(
        "--out-root", type=Path, default=_DEFAULT_OUT_ROOT,
        help="Where to write eval_runs/<ts>/ (default: <repo>/eval_runs).",
    )
    run_p.add_argument(
        "--w-anchor", type=float, default=1.0,
        help="Weight on anchor fidelity (default: 1.0).",
    )
    run_p.add_argument(
        "--w-dead", type=float, default=0.4,
        help="Weight on dead-knob fraction (default: 0.4).",
    )
    run_p.add_argument(
        "--w-collapse", type=float, default=0.6,
        help="Weight on discriminability collapse (default: 0.6).",
    )
    run_p.add_argument(
        "--w-struct", type=float, default=0.3,
        help="Weight on structural integrity failures (default: 0.3).",
    )

    lb_p = sub.add_parser("leaderboard", help="Scan eval_runs/ and print sessions.")
    lb_p.add_argument(
        "--out-root", type=Path, default=_DEFAULT_OUT_ROOT,
        help="Where to scan (default: <repo>/eval_runs).",
    )
    lb_p.add_argument(
        "--limit", type=int, default=20,
        help="Max rows to print (default: 20).",
    )

    return parser


def _load_corpus(arg: Path | None) -> Corpus:
    if arg is None:
        return default_corpus()
    return load_corpus(arg)


def _cmd_run(args: argparse.Namespace) -> int:
    corpus = _load_corpus(args.corpus)
    config = SessionConfig(
        budget_iter=args.budget_iter,
        budget_wall_s=args.budget_wall,
        plateau_rejections=args.plateau,
        seed=args.seed,
        params_per_step=args.params_per_step,
        temperature=args.temperature,
        cooling=args.cooling,
        hard_floor=args.hard_floor,
        pytest_args=tuple(s for s in args.pytest_args.split(",") if s),
        skip_pytest=args.skip_pytest,
        commit=not args.no_commit,
        branch=None if args.no_commit else args.branch,
        out_root=args.out_root,
    )
    weights = RewardWeights(
        anchor=args.w_anchor,
        dead=args.w_dead,
        collapse=args.w_collapse,
        struct=args.w_struct,
    )
    summary = run_session(corpus=corpus, config=config, weights=weights)
    print(
        f"session {summary.session_dir.name}: "
        f"iters={summary.iterations} accepted={summary.accepted} "
        f"rejected={summary.rejected} "
        f"R: {summary.initial_R:.4f} → {summary.best_R:.4f} "
        f"(Δ={summary.best_R - summary.initial_R:+.4f})"
    )
    return 0


def _cmd_leaderboard(args: argparse.Namespace) -> int:
    sessions = load_sessions(args.out_root)
    if not sessions:
        print(f"(no sessions under {args.out_root})")
        return 0
    header = (
        f"{'session':<24} {'iters':>6} {'acc':>5} {'rej':>5} "
        f"{'R_init':>10} {'R_best':>10} {'ΔR':>10}"
    )
    print(header)
    for s in sessions[: args.limit]:
        print(
            f"{s.session_dir.name:<24} "
            f"{s.iterations:>6} {s.accepted:>5} {s.rejected:>5} "
            f"{s.initial_R:>10.4f} {s.best_R:>10.4f} "
            f"{s.best_R - s.initial_R:>+10.4f}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "leaderboard":
        return _cmd_leaderboard(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
