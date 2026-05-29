"""Iteration log + per-session summary + leaderboard scanner.

Every accepted-or-rejected iteration appends one JSON line to
``eval_runs/<ts>/log.jsonl``. When the loop exits cleanly the driver
also writes ``summary.md``. The :func:`load_sessions` scanner walks
``eval_runs/`` and produces a leaderboard sorted by best ``R``.

Schema is open — fields can be added without breaking older sessions.
The scanner is defensive: missing keys read as ``None`` and unknown
keys are ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jtx.improve.proposer import Proposal
from jtx.improve.reward import RewardBreakdown


@dataclass(frozen=True)
class IterationRecord:
    """One log line — proposal summary + score deltas + accept reason."""

    iteration: int
    accepted: bool
    reason: str
    R_before: float
    R_after: float
    A_after: float
    D_after: float
    C_after: float
    S_after: float
    anchor_scores: dict[str, float]
    anchor_deltas: dict[str, float]
    diff: dict[str, tuple[float, float]] = field(default_factory=dict)
    elapsed_s: float = 0.0


def _record_to_jsonable(record: IterationRecord) -> dict[str, Any]:
    return {
        "iteration": record.iteration,
        "accepted": record.accepted,
        "reason": record.reason,
        "R_before": record.R_before,
        "R_after": record.R_after,
        "A_after": record.A_after,
        "D_after": record.D_after,
        "C_after": record.C_after,
        "S_after": record.S_after,
        "anchor_scores": record.anchor_scores,
        "anchor_deltas": record.anchor_deltas,
        "diff": {k: list(v) for k, v in record.diff.items()},
        "elapsed_s": record.elapsed_s,
    }


def build_iteration_record(
    *,
    iteration: int,
    accepted: bool,
    reason: str,
    before: RewardBreakdown,
    after: RewardBreakdown,
    proposal: Proposal,
    elapsed_s: float,
) -> IterationRecord:
    """Construct the per-iteration record from the driver's state."""
    anchor_deltas = {
        name: after.anchor_total(name) - before.anchor_total(name)
        for name in before.anchor_scores
    }
    return IterationRecord(
        iteration=iteration,
        accepted=accepted,
        reason=reason,
        R_before=before.R,
        R_after=after.R,
        A_after=after.A,
        D_after=after.D,
        C_after=after.C,
        S_after=after.S,
        anchor_scores=dict(after.anchor_scores),
        anchor_deltas=anchor_deltas,
        diff=dict(proposal.diff),
        elapsed_s=elapsed_s,
    )


def new_session_dir(out_root: Path) -> Path:
    """Create + return ``out_root/<UTC-timestamp>/`` for a fresh session."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    session = out_root / ts
    session.mkdir(parents=True, exist_ok=False)
    return session


class IterationLog:
    """Append-only JSONL writer for one session.

    Opening the file once and keeping it open avoids a per-iteration
    fopen — sessions can run for hours and the syscall overhead adds
    up. ``flush()`` after every line means a crash leaves the log
    consistent rather than ending mid-line.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: IterationRecord) -> None:
        self._fh.write(json.dumps(_record_to_jsonable(record)))
        self._fh.write("\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> IterationLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def write_summary(
    session_dir: Path,
    *,
    started_at: datetime,
    ended_at: datetime,
    initial: RewardBreakdown,
    best: RewardBreakdown,
    accepted_iters: int,
    rejected_iters: int,
    floor_blocks: int,
    termination: str,
) -> Path:
    """Emit ``summary.md`` in *session_dir* and return the path.

    The summary highlights:

    * R before / after the session.
    * The three biggest descriptor improvements (per-anchor deltas).
    * Iterations blocked by the hard floor.
    * Termination reason (iter cap / wall-clock / STOP file / plateau).
    """
    deltas = sorted(
        (
            (name, best.anchor_total(name) - initial.anchor_total(name))
            for name in initial.anchor_scores
        ),
        key=lambda kv: -kv[1],
    )

    lines: list[str] = []
    lines.append(f"# jtx-improve session {session_dir.name}\n")
    lines.append(f"- Started: {started_at.isoformat()}")
    lines.append(f"- Ended:   {ended_at.isoformat()}")
    lines.append(f"- Termination: {termination}\n")

    lines.append("## Reward")
    lines.append(f"- R initial:  {initial.R:.6f}")
    lines.append(f"- R best:     {best.R:.6f}")
    lines.append(f"- ΔR:         {best.R - initial.R:+.6f}")
    lines.append("")
    lines.append("|term|initial|best|")
    lines.append("|--|--|--|")
    lines.append(f"|A|{initial.A:.4f}|{best.A:.4f}|")
    lines.append(f"|D|{initial.D:.4f}|{best.D:.4f}|")
    lines.append(f"|C|{initial.C:.4f}|{best.C:.4f}|")
    lines.append(f"|S|{initial.S:.4f}|{best.S:.4f}|")

    lines.append("\n## Iterations")
    lines.append(f"- Accepted: {accepted_iters}")
    lines.append(f"- Rejected: {rejected_iters}")
    lines.append(f"- Hard-floor blocks: {floor_blocks}")

    lines.append("\n## Top per-anchor deltas")
    for name, delta in deltas[:3]:
        lines.append(f"- {name}: {delta:+.4f}")

    if any(d < 0 for _, d in deltas):
        lines.append("\n## Regressions (within hard-floor)")
        for name, delta in deltas:
            if delta < 0:
                lines.append(f"- {name}: {delta:+.4f}")

    path = session_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n")
    return path


# ----------------------------------------------------------------------
# Leaderboard scanner.
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSummary:
    """One session's headline numbers — for the leaderboard."""

    session_dir: Path
    iterations: int
    accepted: int
    rejected: int
    best_R: float
    initial_R: float
    last_summary: str | None = None


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # A partial last line (crash mid-write) just gets skipped.
            continue
    return records


def load_session(session_dir: Path) -> SessionSummary | None:
    """Read one session directory into a :class:`SessionSummary`."""
    log_path = session_dir / "log.jsonl"
    records = _load_jsonl_records(log_path)
    if not records:
        return None
    initial_R = records[0].get("R_before", 0.0)
    best_R = max(r.get("R_after", float("-inf")) for r in records)
    accepted = sum(1 for r in records if r.get("accepted"))
    summary_path = session_dir / "summary.md"
    return SessionSummary(
        session_dir=session_dir,
        iterations=len(records),
        accepted=accepted,
        rejected=len(records) - accepted,
        best_R=best_R,
        initial_R=initial_R,
        last_summary=summary_path.read_text() if summary_path.exists() else None,
    )


def load_sessions(out_root: Path) -> list[SessionSummary]:
    """All sessions under *out_root*, sorted by best R descending."""
    if not out_root.exists():
        return []
    summaries: list[SessionSummary] = []
    for child in sorted(out_root.iterdir()):
        if not child.is_dir():
            continue
        summary = load_session(child)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(key=lambda s: -s.best_R)
    return summaries


__all__ = [
    "IterationLog",
    "IterationRecord",
    "SessionSummary",
    "build_iteration_record",
    "load_session",
    "load_sessions",
    "new_session_dir",
    "write_summary",
]
