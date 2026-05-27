"""Engine — scheduler, clock sources, sinks, event types, algorithm ABC.

This package is the part of jtx that turns a Song description into a
stream of MIDI events. It is pure Python and Qt-free; the GUI imports
from here, never the reverse.
"""

from jtx.engine.algorithm import Algorithm
from jtx.engine.clock_source import ClockSource, InternalClock
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend
from jtx.engine.meter import parse_meter, ticks_per_bar, ticks_per_beat
from jtx.engine.scheduler import BarGenerator, Scheduler
from jtx.engine.sink import MemorySink, Sink

__all__ = [
    "Algorithm",
    "BarContext",
    "BarGenerator",
    "ClockSource",
    "ControlChange",
    "Event",
    "InternalClock",
    "MemorySink",
    "NoteOff",
    "NoteOn",
    "PitchBend",
    "Scheduler",
    "Sink",
    "parse_meter",
    "ticks_per_bar",
    "ticks_per_beat",
]
