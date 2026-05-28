"""Abstract event types — what algorithms emit.

Algorithms produce abstract events that name musical concepts
(instruments, parameter functions, pitches) without encoding MIDI
plumbing (channel numbers, CC numbers, voice routing). The voicing
stage in :mod:`jtx.engine.voicing` translates these to the concrete
MIDI events in :mod:`jtx.engine.events` using each voice's
:class:`~jtx.model.setup.VoiceSlot` configuration.

The separation lets cross-cutting features (sidechain, parameter
mapping, LFO targeting) operate on instrument/function names rather
than channel/note tuples — see ``Hit.instrument`` and ``Param.name``.

The four kinds:

* :class:`Hit` — a drum-piece hit, identified by instrument name.
* :class:`Note` — a pitched note (pitch is a MIDI note number used as
  a universal integer pitch encoding — not MIDI plumbing).
* :class:`Param` — a parameter set, identified by function name
  (``"cutoff"``, ``"resonance"``, ``"glide"``, ``"bend"``).
* :class:`PolyAftertouch` — per-note expressive pressure on poly /
  MPE voices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    """A drum-piece hit.

    The voicing stage resolves ``instrument`` to a MIDI ``(channel,
    note)`` pair. For a ``drum_kit`` slot, the instrument name keys
    into ``slot.kit_map``. For a single-piece ``drum`` slot, the
    instrument name is either ``None`` (use ``slot.note`` /
    ``slot.midi_channel``) or the voice's name (same effect).
    """

    instrument: str | None
    velocity: int  # 1..127
    duration_ticks: int  # short, MIDI-protocol housekeeping for drums
    tick: int


@dataclass(frozen=True)
class Note:
    """A pitched note.

    ``pitch`` is a MIDI note number (0..127) used as a universal
    integer pitch encoding — that is *not* MIDI plumbing. The voicing
    stage adds ``channel`` from the voice slot and (for MPE voices)
    allocates a per-note channel from the MPE block.
    """

    pitch: int  # MIDI note number, 0..127
    velocity: int  # 1..127
    duration_ticks: int
    tick: int


@dataclass(frozen=True)
class Param:
    """A parameter set on an abstract function name.

    ``name`` is a function-vocabulary string (``"cutoff"``,
    ``"resonance"``, ``"glide"``, ``"bend"``, …). The voicing stage
    resolves the name via the voice slot's ``parameter_map`` (or the
    algorithm's ``DEFAULT_PARAM_MAP``) to a concrete CC / OSC / MPE
    target.

    ``value`` is normalised: ``[0, 1]`` for CC-style functions
    (cutoff, resonance) and ``[-1, 1]`` for bend-style functions. The
    voicing stage rescales to the target's native range at emission
    time.
    """

    name: str
    value: float
    tick: int


@dataclass(frozen=True)
class PolyAftertouch:
    """Per-note expressive pressure for poly / MPE voices.

    The voicing stage resolves to MPE polyphonic pressure (the
    ``ChannelPressure`` on the note's allocated MPE channel) or, for
    non-MPE voices, channel pressure on the voice's main channel.
    """

    pitch: int  # MIDI note number of the note this applies to
    pressure: float  # 0..1
    tick: int


AbstractEvent = Hit | Note | Param | PolyAftertouch
"""Discriminated union of the abstract event types algorithms emit."""
