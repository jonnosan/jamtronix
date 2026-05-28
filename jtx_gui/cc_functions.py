"""Function vocabulary surfaced in the setup editor.

The setup editor's parameter-map section renders one row per function
listed in :data:`FUNCTIONS_BY_VOICE_TYPE` for the selected voice's type.
``DEFAULT_TARGETS`` supplies the "what would the router pick if this
slot has nothing set?" answer (a :class:`CCTarget` with the algorithm's
historical stock CC number). The actual lookup the router performs at
runtime is per-algorithm (each ``Algorithm`` subclass declares
``DEFAULT_PARAM_MAP``); this table is purely a UI affordance.

``detune`` and ``glide_on`` are intentionally NOT in
``FUNCTIONS_BY_VOICE_TYPE`` — they're algorithm-specific
(``reese_bass`` and ``acid_bass`` respectively), not portable
mono/poly knobs. They still have a ``DEFAULT_TARGETS`` entry so the
router has a fallback if a song's parameter_map references them
explicitly.
"""

from __future__ import annotations

from jtx.model.parameter_target import CCTarget, ParameterTarget
from jtx.model.types import VoiceType

FUNCTIONS_BY_VOICE_TYPE: dict[VoiceType, tuple[str, ...]] = {
    "drum": (),
    "mono": ("cutoff", "resonance", "glide", "bend"),
    "poly": ("cutoff", "resonance", "bend"),
    "modulator": (),
    "follower": (),
}

DEFAULT_TARGETS: dict[str, ParameterTarget] = {
    "cutoff": CCTarget(74),
    "resonance": CCTarget(71),
    "glide": CCTarget(5),
    # ``bend`` has no CC anchor; the placeholder CC keeps the UI
    # picker workable for the legacy CC row even though the natural
    # use is MPEPitchBendTarget.
    "bend": CCTarget(0),
    "detune": CCTarget(1),
    "glide_on": CCTarget(65),
}


def functions_for_type(voice_type: VoiceType) -> tuple[str, ...]:
    """Return the v1 function vocabulary for *voice_type* (empty if none)."""
    return FUNCTIONS_BY_VOICE_TYPE.get(voice_type, ())


def default_target(function: str) -> ParameterTarget:
    """Return the documented default target for *function*.

    Falls back to ``CCTarget(0)`` for unknown functions so the UI
    doesn't crash when rendering an exotic parameter_map entry.
    """
    return DEFAULT_TARGETS.get(function, CCTarget(0))
