"""Unit tests for descriptor functions over abstract events."""

from __future__ import annotations

from jtx.evaluation import descriptors as D
from jtx.model.events import Hit, Note, Param, PolyAftertouch


def test_empty_iterables_return_zero() -> None:
    assert D.hit_count([]) == 0
    assert D.note_count([]) == 0
    assert D.onset_count([]) == 0
    assert D.velocity_mean([]) == 0.0
    assert D.velocity_variance([]) == 0.0
    assert D.sixteenth_grid_coverage([], 1920) == 0.0
    assert D.param_values([], "cutoff") == []
    assert D.param_trajectory_variance([], "cutoff") == 0.0
    assert D.param_trajectory_range([], "cutoff") == 0.0
    assert D.voice_active([]) is False


def test_hit_note_onset_counts() -> None:
    events = [
        Hit(instrument="kick", velocity=110, duration_ticks=60, tick=0),
        Hit(instrument="snare", velocity=95, duration_ticks=60, tick=480),
        Note(pitch=60, velocity=90, duration_ticks=120, tick=240),
        Param(name="cutoff", value=0.5, tick=0),
    ]
    assert D.hit_count(events) == 2
    assert D.note_count(events) == 1
    assert D.onset_count(events) == 3  # Hits + Notes only, Param excluded


def test_velocity_statistics() -> None:
    events = [
        Hit(instrument="kick", velocity=100, duration_ticks=60, tick=0),
        Note(pitch=60, velocity=80, duration_ticks=120, tick=240),
        Param(name="cutoff", value=0.5, tick=0),  # excluded
    ]
    assert D.velocity_mean(events) == 90.0
    # population variance of [100, 80] = ((100-90)^2 + (80-90)^2)/2 = 100
    assert D.velocity_variance(events) == 100.0


def test_sixteenth_grid_coverage_full_bar() -> None:
    # 4/4 bar at 480ppq = 1920 ticks. 16th slot = 120 ticks.
    ticks_per_bar = 1920
    events = [Note(pitch=60, velocity=100, duration_ticks=60, tick=i * 120) for i in range(16)]
    assert D.sixteenth_grid_coverage(events, ticks_per_bar) == 1.0


def test_sixteenth_grid_coverage_partial() -> None:
    ticks_per_bar = 1920
    # Four-on-floor: 4 hits on quarter notes (every 4th 16th-slot)
    events = [Hit(instrument="kick", velocity=110, duration_ticks=60, tick=i * 480) for i in range(4)]
    assert D.sixteenth_grid_coverage(events, ticks_per_bar) == 0.25


def test_sixteenth_grid_coverage_dedupes_same_slot() -> None:
    """Multiple onsets in the same 16th slot count as one slot."""
    ticks_per_bar = 1920
    events = [
        Hit(instrument="kick", velocity=110, duration_ticks=60, tick=0),
        Hit(instrument="snare", velocity=95, duration_ticks=60, tick=10),  # same 16th slot
    ]
    assert D.sixteenth_grid_coverage(events, ticks_per_bar) == 1 / 16


def test_param_values_time_ordered_and_filtered_by_name() -> None:
    events = [
        Param(name="cutoff", value=0.8, tick=240),
        Param(name="resonance", value=0.5, tick=0),
        Param(name="cutoff", value=0.2, tick=0),
    ]
    assert D.param_values(events, "cutoff") == [0.2, 0.8]
    assert D.param_values(events, "resonance") == [0.5]


def test_param_trajectory_variance_and_range() -> None:
    events = [
        Param(name="cutoff", value=0.0, tick=0),
        Param(name="cutoff", value=1.0, tick=120),
        Param(name="cutoff", value=0.5, tick=240),
    ]
    # range = 1.0 - 0.0 = 1.0
    assert D.param_trajectory_range(events, "cutoff") == 1.0
    # population variance of [0.0, 1.0, 0.5] mean=0.5 → ((.5)^2+(.5)^2+0)/3
    assert abs(D.param_trajectory_variance(events, "cutoff") - (0.25 + 0.25 + 0.0) / 3) < 1e-9


def test_voice_active_with_any_event_type() -> None:
    assert D.voice_active([Hit(instrument="kick", velocity=100, duration_ticks=60, tick=0)])
    assert D.voice_active([Note(pitch=60, velocity=80, duration_ticks=60, tick=0)])
    assert D.voice_active([Param(name="cutoff", value=0.5, tick=0)])
    assert D.voice_active([PolyAftertouch(pitch=60, pressure=0.5, tick=0)])
    assert not D.voice_active([])
