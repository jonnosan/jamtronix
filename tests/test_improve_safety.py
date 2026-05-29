"""Tests for the Phase 2b safety rails.

Allow-list + forbidden-path enforcement, STOP file, git arg fences,
schema lock. These are the rules that make running the loop
unattended safe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.improve.safety import (
    STOP_FILE,
    AllowListViolation,
    assert_git_args_safe,
    assert_proposal_paths_clean,
    assert_schema_unchanged,
    is_forbidden,
    is_writable,
    stop_requested,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tuning_toml_is_writable() -> None:
    """The override file is the one path Tier-A can write to."""
    assert is_writable(REPO_ROOT / "tuning.toml")


def test_song_py_is_forbidden() -> None:
    assert is_forbidden(REPO_ROOT / "jtx" / "model" / "song.py")


def test_sinks_subtree_is_forbidden() -> None:
    """Touching anything under jtx/sinks/ aborts immediately."""
    assert is_forbidden(REPO_ROOT / "jtx" / "sinks" / "midi_sink.py")


def test_tests_dir_is_forbidden() -> None:
    """The loop must not edit its own tests."""
    assert is_forbidden(REPO_ROOT / "tests" / "test_some_new_thing.py")


def test_examples_dir_is_forbidden() -> None:
    assert is_forbidden(REPO_ROOT / "examples" / "any.jtx")


def test_setups_dir_is_forbidden() -> None:
    assert is_forbidden(REPO_ROOT / "setups" / "iac.jtx-setup")


def test_assert_proposal_paths_allows_only_tuning_toml() -> None:
    assert_proposal_paths_clean([REPO_ROOT / "tuning.toml"])


def test_assert_proposal_paths_rejects_random_path(tmp_path: Path) -> None:
    """A path outside the allow-list — even in tmp — aborts."""
    with pytest.raises(AllowListViolation):
        assert_proposal_paths_clean([tmp_path / "stuff.toml"])


def test_assert_proposal_paths_rejects_schema_edit_attempt() -> None:
    """The forbidden-path guard catches a Tier-C-style attempt to edit song.py."""
    with pytest.raises(AllowListViolation, match="forbidden"):
        assert_proposal_paths_clean([REPO_ROOT / "jtx" / "model" / "song.py"])


# ---------- STOP file --------------------------------------------------


def test_stop_file_path_is_in_repo_root() -> None:
    assert STOP_FILE.parent == REPO_ROOT


def test_stop_requested_reads_filesystem() -> None:
    """The check must hit the actual filesystem; no caching."""
    # No STOP file in repo currently.
    assert stop_requested() is False


# ---------- git arg fences --------------------------------------------


def test_git_no_verify_blocked() -> None:
    with pytest.raises(PermissionError, match="--no-verify"):
        assert_git_args_safe(["commit", "-m", "x", "--no-verify"])


def test_git_reset_hard_blocked() -> None:
    with pytest.raises(PermissionError, match="reset --hard"):
        assert_git_args_safe(["reset", "--hard", "HEAD"])


def test_git_push_force_blocked() -> None:
    with pytest.raises(PermissionError, match="force"):
        assert_git_args_safe(["push", "--force"])


def test_git_push_blocked_unconditionally() -> None:
    """The loop must never publish; bare push refused."""
    with pytest.raises(PermissionError, match="push"):
        assert_git_args_safe(["push"])


def test_git_safe_args_pass() -> None:
    # No exception → call succeeds.
    assert_git_args_safe(["status"])
    assert_git_args_safe(["add", "tuning.toml"])
    assert_git_args_safe(["commit", "-m", "x"])
    assert_git_args_safe(["checkout", "-b", "feature/x"])


# ---------- Schema lock -----------------------------------------------


def test_schema_lock_passes_on_clean_repo() -> None:
    """At repo HEAD, the schema lock must succeed."""
    assert_schema_unchanged()  # no exception
