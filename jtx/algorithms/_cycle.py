"""Shared knob helpers for cyclic-PRNG cycle-period choices.

Algorithms expose ``<decision>_cycle_bars`` choice knobs whose string
values map onto the period argument of
:meth:`jtx.engine.context.BarContext.rng_loop` /
:meth:`~jtx.engine.context.BarContext.rng_hold`. This module owns the
choice list and the string→factory-arg parser so every algorithm uses
the same vocabulary.
"""

from __future__ import annotations

CYCLE_BARS_CHOICES: tuple[str, ...] = ("off", "1", "2", "4", "8", "16", "part")
"""Standard choice list for ``<decision>_cycle_bars`` knobs."""


def parse_cycle_bars(value: object) -> int | str:
    """Parse a ``cycle_bars`` knob value into the factory argument.

    Accepts the literal choice strings (``"off"`` / ``"1"`` / … /
    ``"part"``) or already-typed ``int`` / ``"part"``. Returns 0 for the
    off-sentinel (caller passes to ``rng_loop`` / ``rng_hold`` to get
    ``ctx.rng`` fall-through), ``"part"`` for the part-constant option,
    or a positive ``int`` for the period.
    """
    if value is None or value == "off" or value == 0 or value == "0":
        return 0
    if value == "part":
        return "part"
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"parse_cycle_bars: unsupported value {value!r}")
