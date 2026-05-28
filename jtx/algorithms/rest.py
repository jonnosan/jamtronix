"""``rest`` — explicit-silence algorithm.

Returns an empty event list every bar. Used by the Composer when a voice
in the fixed palette has nothing useful to contribute to a given song
(e.g. ``sub`` in a happy/dreamy mood, ``arp`` in a sting format) so the
voice still exists in the song model — keeping the palette uniform
across all songs — but doesn't produce any sound.

Compatible with every :class:`VoiceType`; any voice slot can declare
``algorithm="rest"`` in its :class:`VoiceConfig` to opt out.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent
from jtx.model.parameter_target import ParameterTarget


class Rest(Algorithm):
    """Voice-level no-op."""

    name: ClassVar[str] = "rest"
    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {}

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        return []
