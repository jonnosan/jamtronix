"""Engine — scheduler, clock sources, sinks, event types, algorithm ABC.

This package is the part of jtx that turns a Song description into a
stream of MIDI events. It is pure Python and Qt-free; the GUI imports
from here, never the reverse.
"""

from jtx.engine.algorithm import Algorithm
from jtx.engine.clock_source import (
    AbletonLinkClock,
    ClockSource,
    InternalClock,
    MidiClockSlaveClock,
)
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend
from jtx.engine.feel import apply_feel
from jtx.engine.lfo import (
    ParsedTarget,
    applications_for_part,
    apply_lfos_to_bar,
    parse_target,
    sample_lfo,
)
from jtx.engine.meter import parse_meter, ticks_per_bar, ticks_per_beat
from jtx.engine.root_provider import (
    ProgressionRootProvider,
    RootProvider,
    degree_to_semitones,
)
from jtx.engine.scheduler import BarGenerator, Scheduler
from jtx.engine.sink import MemorySink, Sink

__all__ = [
    "AbletonLinkClock",
    "Algorithm",
    "BarContext",
    "BarGenerator",
    "ClockSource",
    "ControlChange",
    "Event",
    "InternalClock",
    "MemorySink",
    "MidiClockSlaveClock",
    "NoteOff",
    "NoteOn",
    "ParsedTarget",
    "PitchBend",
    "ProgressionRootProvider",
    "RootProvider",
    "Scheduler",
    "Sink",
    "applications_for_part",
    "apply_feel",
    "apply_lfos_to_bar",
    "degree_to_semitones",
    "parse_meter",
    "parse_target",
    "sample_lfo",
    "ticks_per_bar",
    "ticks_per_beat",
]
