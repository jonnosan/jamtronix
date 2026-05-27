"""LFO definitions + per-part applications.

LFOs are declared at the song level and bound to targets per part. The
data model here is pure description; per-bar sampling and target dispatch
live in the engine (later milestone).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jtx.model.types import LFOShape


@dataclass
class LFOApplication:
    """Binds a song-level LFO to a target inside one part.

    Target strings follow the schema documented in ``docs/SPEC.md`` §LFOs:

    * ``pattern:<voice>:<knob>`` — modulate a pattern knob
    * ``feel:<voice>:<knob>``    — modulate a feel knob
    * ``midi:ch<N>:cc<M>``       — emit raw CC
    * ``root:<voice>``           — modulate the root note
    """

    part: str
    target: str


@dataclass
class LFO:
    name: str
    shape: LFOShape
    period_bars: float
    """Cycle length in bars. Fractional values land sub-bar (e.g. 0.25 = beat)."""
    phase: float = 0.0
    """Starting phase in [0, 1)."""
    depth: float = 1.0
    """Output scale in [0, 1]."""
    applications: list[LFOApplication] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.period_bars <= 0:
            errors.append(f"lfo {self.name!r}: period_bars must be > 0")
        if not (0.0 <= self.phase < 1.0):
            errors.append(f"lfo {self.name!r}: phase {self.phase} not in [0, 1)")
        if not (0.0 <= self.depth <= 1.0):
            errors.append(f"lfo {self.name!r}: depth {self.depth} not in [0, 1]")
        return errors
