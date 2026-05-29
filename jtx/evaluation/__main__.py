"""CLI entry — knob-sensitivity sweep emitter.

Usage::

    python -m jtx.evaluation sweep --axis motion --steps 11 [--seed N] [--out FILE.csv]

Writes a CSV with columns ``axis_value, <feature_1>, <feature_2>, …``
followed by two trailing summary rows: ``#slope`` and ``#r2`` per
feature. Default output is stdout; ``--out`` writes to a file.

The other two Phase 1c modes (discriminability, structure) are
pytest-only — they aren't useful as CLIs because their output is a
matrix, not a per-row CSV.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from jtx.evaluation.sensitivity import SensitivityFixed, SensitivityResult, sweep
from jtx.persist.json_io import load_setup

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETUP = _REPO_ROOT / "setups" / "iac.jtx-setup"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jtx.evaluation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sweep_p = sub.add_parser(
        "sweep",
        help="Sweep one composer axis across N steps; emit a per-step CSV.",
    )
    sweep_p.add_argument(
        "--axis",
        choices=["texture", "motion", "valence", "energy"],
        required=True,
    )
    sweep_p.add_argument("--steps", type=int, default=11)
    sweep_p.add_argument("--seed", type=int, default=0)
    sweep_p.add_argument("--out", type=Path, default=None)
    sweep_p.add_argument(
        "--setup",
        type=Path,
        default=_DEFAULT_SETUP,
        help="Path to a .jtx-setup file (default: setups/iac.jtx-setup).",
    )
    sweep_p.add_argument(
        "--fmt",
        default="song",
        choices=["sting", "jingle", "loop", "ramp", "song", "anthem"],
        help="Song.format the swept songs use (default: song).",
    )
    sweep_p.add_argument(
        "--parts",
        default="drop",
        help="Comma-separated part names to render (default: drop).",
    )
    sweep_p.add_argument("--bars", type=int, default=4)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd != "sweep":
        # argparse already enforces required=True, but guard anyway.
        return 2

    setup = load_setup(args.setup)
    fixed = SensitivityFixed(fmt=args.fmt)
    parts = tuple(p.strip() for p in args.parts.split(",") if p.strip())
    result = sweep(
        axis=args.axis,
        setup=setup,
        steps=args.steps,
        fixed=fixed,
        seed=args.seed,
        parts=parts,
        bars=args.bars,
    )

    feature_keys = list(result.feature_keys)
    if args.out is None:
        _write_csv(sys.stdout, feature_keys, result)
    else:
        with args.out.open("w", newline="") as fh:
            _write_csv(fh, feature_keys, result)
    return 0


def _write_csv(stream: TextIO, feature_keys: list[str], result: SensitivityResult) -> None:
    writer = csv.writer(stream)
    writer.writerow(["axis_value", *feature_keys])
    for point in result.points:
        writer.writerow(
            [f"{point.axis_value:.6f}", *[f"{point.features[k]:.6f}" for k in feature_keys]]
        )
    writer.writerow([])
    writer.writerow(["#slope", *[f"{result.slope[k]:.6f}" for k in feature_keys]])
    writer.writerow(["#r2", *[f"{result.r2[k]:.6f}" for k in feature_keys]])


if __name__ == "__main__":
    raise SystemExit(main())
