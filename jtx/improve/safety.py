"""Safety rails for the ``jtx-improve`` closed loop.

Phase 2b's writable-file allow-list, forbidden-path guard, schema
lock, pytest gate, and STOP-file kill switch. These are the rules
that make the loop trustworthy enough to leave running unattended.

The driver consults this module on every iteration; nothing else
references these helpers directly.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Repo root resolution mirrors :mod:`jtx.composer.tuning` so a single
# constant defines "where the project lives" for both layers.
_REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------
# Allow-list + forbidden paths.
# ----------------------------------------------------------------------


# Files the loop is allowed to write. Tier A — Phase 2b — narrows to
# the override file only. Tier B / C will extend this list when they
# land.
ALLOWED_WRITABLE_PATHS: tuple[Path, ...] = (
    _REPO_ROOT / "tuning.toml",
)

# Path prefixes the loop must never touch. Touching one auto-rejects
# the iteration without scoring. Lifted verbatim from the Phase 2b
# brief; keep this list in sync with the plan when new untouchable
# surfaces are introduced.
FORBIDDEN_PATHS: tuple[Path, ...] = (
    _REPO_ROOT / "jtx" / "model" / "song.py",
    _REPO_ROOT / "jtx" / "sinks",
    _REPO_ROOT / "jtx" / "engine" / "voicing.py",
    _REPO_ROOT / "jtx" / "engine" / "parameter_router.py",
    _REPO_ROOT / "tests",
    _REPO_ROOT / "examples",
    _REPO_ROOT / "setups",
)


class AllowListViolation(Exception):
    """Raised when a proposal would touch a non-allow-listed path."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def is_writable(path: Path) -> bool:
    """True iff *path* is in :data:`ALLOWED_WRITABLE_PATHS`."""
    resolved = path.resolve()
    return any(resolved == p.resolve() for p in ALLOWED_WRITABLE_PATHS)


def is_forbidden(path: Path) -> bool:
    """True iff *path* sits under any :data:`FORBIDDEN_PATHS` prefix."""
    resolved = path.resolve()
    for forbidden in FORBIDDEN_PATHS:
        try:
            resolved.relative_to(forbidden.resolve())
            return True
        except ValueError:
            continue
    return False


def assert_proposal_paths_clean(paths: Sequence[Path]) -> None:
    """Raise :class:`AllowListViolation` if *paths* leaves the allow-list.

    Phase 2b: the only allowed path is ``tuning.toml``. Anything else
    is an immediate abort — no scoring, no commit, no working-tree
    pollution.
    """
    for p in paths:
        if is_forbidden(p):
            raise AllowListViolation(path=p, reason="forbidden (Tier D)")
        if not is_writable(p):
            raise AllowListViolation(
                path=p, reason="not on the Tier-A writable allow-list"
            )


# ----------------------------------------------------------------------
# STOP file kill switch.
# ----------------------------------------------------------------------


STOP_FILE = _REPO_ROOT / "STOP"


def stop_requested() -> bool:
    """``touch STOP`` in the working tree halts the loop between iterations."""
    return STOP_FILE.exists()


# ----------------------------------------------------------------------
# Schema lock.
# ----------------------------------------------------------------------


def assert_schema_unchanged(*, repo_root: Path = _REPO_ROOT) -> None:
    """Raise if :data:`jtx.model.types.SCHEMA_VERSION` has shifted.

    The loop never edits ``song.py`` directly (forbidden path), but
    this guard catches concurrent edits to the schema while the loop
    runs — accepting an iteration whose Song instances don't match the
    repo's current schema would silently corrupt every saved .jtx.
    """
    from jtx.model.types import SCHEMA_VERSION  # imported lazily for testability

    # Read the file directly so we catch a checked-out edit that hasn't
    # yet caused the loaded module to refresh.
    types_path = repo_root / "jtx" / "model" / "types.py"
    if not types_path.exists():
        raise RuntimeError(f"schema lock: missing {types_path}")
    source = types_path.read_text()
    needle = f"SCHEMA_VERSION = {SCHEMA_VERSION}"
    if needle not in source:
        raise RuntimeError(
            f"schema lock: jtx.model.types.SCHEMA_VERSION drifted from "
            f"{SCHEMA_VERSION} in loaded module"
        )


# ----------------------------------------------------------------------
# pytest gate.
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PytestResult:
    """Outcome of a pytest invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_pytest(
    args: Sequence[str] = ("-q", "--no-header"),
    *,
    repo_root: Path = _REPO_ROOT,
    timeout: float = 600.0,
) -> PytestResult:
    """Run ``pytest`` with *args* in *repo_root* and capture the outcome.

    The loop calls this before scoring each iteration; a non-zero
    return code aborts the iteration. ``timeout`` defaults to 10
    minutes so a hung test process doesn't strand the loop.
    """
    proc = subprocess.run(
        ["pytest", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return PytestResult(
        returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
    )


# ----------------------------------------------------------------------
# Git fences.
# ----------------------------------------------------------------------


_FORBIDDEN_GIT_FLAGS: tuple[str, ...] = (
    "--no-verify",
    "--no-gpg-sign",
)


def assert_git_args_safe(args: Sequence[str]) -> None:
    """Refuse git invocations that smuggle in destructive / hook-skipping flags.

    The loop's git helper goes through this gate; tests assert the
    rules hold even if a future refactor changes the call sites.
    """
    if not args:
        raise ValueError("git: empty argv")
    for flag in _FORBIDDEN_GIT_FLAGS:
        if flag in args:
            raise PermissionError(f"git: forbidden flag {flag!r}")
    if "reset" in args and "--hard" in args:
        raise PermissionError("git: refuses 'reset --hard'")
    if "push" in args and "--force" in args:
        raise PermissionError("git: refuses 'push --force'")
    if args[0] == "push":
        raise PermissionError("git: refuses 'push' (loop never publishes)")


__all__ = [
    "ALLOWED_WRITABLE_PATHS",
    "AllowListViolation",
    "FORBIDDEN_PATHS",
    "PytestResult",
    "STOP_FILE",
    "assert_git_args_safe",
    "assert_proposal_paths_clean",
    "assert_schema_unchanged",
    "is_forbidden",
    "is_writable",
    "run_pytest",
    "stop_requested",
]
