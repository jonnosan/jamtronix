"""``jtx-improve`` — Phase 2b closed-loop optimizer over ``tuning.toml``.

Public surface:

* :func:`jtx.improve.driver.run_session` — the main loop.
* :class:`jtx.improve.corpus.Corpus` + :func:`default_corpus` /
  :func:`load_corpus` — the declarative test corpus.
* :func:`jtx.improve.reward.compute_reward` — the four-term R(tuning).
* :class:`jtx.improve.proposer.RandomWalkProposer` — Tier-A
  perturbation strategy.
* The safety / determinism / reporting helpers are imported where
  needed; the top-level package re-exports the most commonly used names.

CLI: ``python -m jtx.improve run …`` (also installed as
``jtx-improve`` per :mod:`pyproject.toml`'s ``[project.scripts]``).
"""

from __future__ import annotations

from jtx.improve.corpus import Corpus, CorpusCase, default_corpus, load_corpus
from jtx.improve.determinism import NonDeterministicReward, assert_deterministic
from jtx.improve.driver import SessionConfig, run_session
from jtx.improve.proposer import (
    ParamSpec,
    Proposal,
    RandomWalkProposer,
    default_param_specs,
    feel_param_specs,
    get_param,
    pattern_param_specs,
    set_param,
    tempo_param_specs,
    tuning_to_toml,
    write_tuning_toml,
)
from jtx.improve.report import (
    IterationLog,
    IterationRecord,
    SessionSummary,
    build_iteration_record,
    load_sessions,
    new_session_dir,
    write_summary,
)
from jtx.improve.reward import (
    RewardBreakdown,
    RewardWeights,
    compute_reward,
    hard_floor_violation,
)
from jtx.improve.safety import (
    ALLOWED_WRITABLE_PATHS,
    FORBIDDEN_PATHS,
    STOP_FILE,
    AllowListViolation,
    assert_git_args_safe,
    assert_proposal_paths_clean,
    assert_schema_unchanged,
    is_forbidden,
    is_writable,
    run_pytest,
    stop_requested,
)

__all__ = [
    "ALLOWED_WRITABLE_PATHS",
    "AllowListViolation",
    "Corpus",
    "CorpusCase",
    "FORBIDDEN_PATHS",
    "IterationLog",
    "IterationRecord",
    "NonDeterministicReward",
    "ParamSpec",
    "Proposal",
    "RandomWalkProposer",
    "RewardBreakdown",
    "RewardWeights",
    "STOP_FILE",
    "SessionConfig",
    "SessionSummary",
    "assert_deterministic",
    "assert_git_args_safe",
    "assert_proposal_paths_clean",
    "assert_schema_unchanged",
    "build_iteration_record",
    "compute_reward",
    "default_corpus",
    "default_param_specs",
    "feel_param_specs",
    "get_param",
    "hard_floor_violation",
    "is_forbidden",
    "is_writable",
    "load_corpus",
    "load_sessions",
    "new_session_dir",
    "pattern_param_specs",
    "run_pytest",
    "run_session",
    "set_param",
    "stop_requested",
    "tempo_param_specs",
    "tuning_to_toml",
    "write_summary",
    "write_tuning_toml",
]
