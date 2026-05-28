"""``drum_kit`` — multi-piece coordinated drum generator.

Unlike ``drum_pattern`` (one voice = one piece), a single ``drum_kit``
voice generates patterns across multiple kit pieces — kick, snare,
hats, claps, percussion — using a small set of knobs that shape the
whole kit's behaviour together. The drum_kit voice owns a
``kit_map: dict[str, KitPiece]`` in its :class:`VoiceSlot`; each piece
can live on its own MIDI channel + note.

The algorithm emits :class:`Hit` events (abstract — keyed by
instrument name). The voicing stage downstream resolves each Hit to a
MIDI ``(channel, note)`` using ``slot.kit_map``. Algorithms never
encode MIDI plumbing.

Headline knobs:

* ``punch`` (0..1, default 0.5) — ghost-noteish ↔ punchy. High punch
  raises kick + snare velocities and suppresses ghost-note layers.
* ``mech`` (0..1, default 0.5) — organic ↔ mechanical. High mech raises
  snare-grid ceilings (machine-gun fills), tightens the triplet-hat
  polyrhythm trigger, and steepens the build snare ramp.
* ``kit_focus`` — which pieces play. ``"full"`` is the default.
  Override per-part to make e.g. a "kick_only" drop or a "build" with
  ramping snare density culminating in a fill on the part's last bar.
* ``density`` (0..1, default 0.5) — overall density multiplier; biases
  every per-piece grid up or down.
* ``variation`` (0..1, default 0.3) — pseudo-random per-bar drift.
* ``perc_complexity`` (0..1, default 0.4) — busy-ness of optional
  percussion pieces (perc / tom / clave / cowbell).
* ``snare_subdiv`` — ``"auto"`` (default — ramps with intensity) /
  ``"16"`` / ``"32"`` / ``"8t"`` to force a snare grid.
* ``kick_pattern`` — ``"auto"`` / ``"four_floor"`` / ``"half_time"`` /
  ``"break"``. Auto picks four_floor at intensity > 0.4, half_time
  below.
* ``hat_pulses`` (-1..16, default -1=auto) — closed-hat pulses across
  16 steps; -1 means derive from intensity.
* ``clap_on`` — ``"never"`` / ``"2_and_4"`` / ``"intensity_gate"``
  (default — claps only above intensity 0.7).

The algorithm reads :attr:`BarContext.part_intensity`,
:attr:`BarContext.part_progress`, and :attr:`BarContext.song_feel`
(``drive`` boosts ghost-note probability on snare/perc; ``wander``
triggers a polyrhythm chance on perc).

The mix-pass / feel-pass / parameter-router stages run downstream of
voicing — drum_kit's job is just to emit the right Hits.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import ClassVar

from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import Hit
from jtx.model.setup import KitPiece
from jtx.model.song import KnobDict

# Drum samples ignore note-off; this is MIDI-protocol housekeeping.
_NOTE_OFF_OFFSET_TICKS = 30

_KIT_FOCUS = (
    "full",
    "minimal",
    "kick_only",
    "no_kick",
    "percussion",
    "build",
    "wind_down",
)


@dataclass(frozen=True)
class _StyleProfile:
    """Derived tuning shape applied on top of the headline pattern.

    Built per-bar by :func:`_derive_profile` from the ``punch`` + ``mech``
    knobs. Lives as a dataclass (not a free dict) so the field set is
    explicit and the downstream generators don't accidentally read a
    missing key.
    """

    # Whether to add a triplet-hat polyrhythm layer when intensity is high.
    triplet_hat_above: float
    # Default base velocity for the kick.
    kick_vel: int
    snare_vel: int
    hat_vel: int
    # Probability adjustment for the ghost-note pass (multiplied onto the
    # base ghost probability derived from drive).
    ghost_bias: float
    # Ceiling for the build-mode snare ramp (in pulses across a 32-slot
    # grid). High mech → machine-gun ramp; low mech → tense, restrained.
    build_snare_max: int
    # Curve exponent for the build snare ramp; >1 back-loads the rise.
    build_snare_curve: float
    # Ceiling for the **auto** snare-pulse ramp at eff=1.0 in non-build
    # modes (i.e. the main "drop" groove).
    default_snare_max: int
    # Increment for the build-mode closed-hat ramp across part_progress.
    # Hat pulses = round(8 + build_hat_ramp_delta * progress). Replaces
    # the old hard-coded acid-vs-techno branch.
    build_hat_ramp_delta: int


def _derive_profile(punch: float, mech: float) -> _StyleProfile:
    """Map (punch, mech) ∈ [0, 1]² to a continuous :class:`_StyleProfile`.

    Both inputs are clamped. The derivation is intentionally simple and
    monotonic so the mood→profile pipeline in the Composer remains
    interpretable. Tuning corners (informational, not exact):

    * ``(punch≈0.55, mech≈0.4)`` lands near today's "acid" character —
      lower snare ceilings, restrained build ramp, no triplet-hat layer.
    * ``(punch≈0.4, mech≈0.7)`` near today's "techno" — driving snare,
      machine-gun build, triplet-hat polyrhythm at high intensity.
    * ``(punch≈0.85, mech≈0.85)`` near today's "psy" — full ceilings,
      hard kick, strong ghost-note bias.
    """
    p = max(0.0, min(1.0, punch))
    m = max(0.0, min(1.0, mech))
    return _StyleProfile(
        triplet_hat_above=1.1 - m * 0.4,
        kick_vel=int(round(118 + (p - 0.5) * 12)),
        snare_vel=int(round(100 + (p - 0.5) * 8)),
        hat_vel=int(round(80 + (m - 0.5) * 4)),
        ghost_bias=1.2 - p * 0.4 + (1.0 - m) * 0.2,
        build_snare_max=int(round(16 + m * 16)),
        build_snare_curve=1.3 + m * 0.3,
        # Non-linear so the acid corner (mech≈0.4) lands near 8-10 in the
        # drop while techno (mech≈0.7) reaches ~18 and psy (mech≈0.85) ~23.
        default_snare_max=int(round(4 + (m**1.5) * 24)),
        build_hat_ramp_delta=int(round(4 + m * 6)),
    )


# Canonical instrument-name aliases — the algorithm checks these first
# when looking for a piece. Keys are categories; values are alias lists.
_INSTRUMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "kick": ("kick", "bd"),
    "snare": ("snare", "sd"),
    "chh": ("chh", "hh", "hat", "hats"),
    "ohh": ("ohh", "ohat", "open_hat"),
    "clap": ("clap",),
    "perc": ("perc", "tom", "clave", "cowbell", "rim", "wood", "shaker", "tamb"),
}


class DrumKit(Algorithm):
    """Multi-piece coordinated drum generator."""

    name: ClassVar[str] = "drum_kit"

    def __init__(self, *, kit_map: dict[str, KitPiece]) -> None:
        # The algorithm is MIDI-naive: it stores only the *names* of the
        # pieces this voice can play. The voicing stage handles the
        # (channel, note) lookup at emission time.
        self.available: frozenset[str] = frozenset(kit_map)

    def generate_bar(self, ctx: BarContext) -> list[Hit]:  # type: ignore[override]
        knobs = ctx.pattern_knobs
        punch = float(knobs.get("punch", 0.5))
        mech = float(knobs.get("mech", 0.5))
        style = _derive_profile(punch, mech)

        kit_focus = str(knobs.get("kit_focus", "full"))
        if kit_focus not in _KIT_FOCUS:
            raise ValueError(
                f"drum_kit: unknown kit_focus {kit_focus!r} (expected one of {list(_KIT_FOCUS)})"
            )

        intensity = max(0.0, min(1.0, float(ctx.part_intensity)))
        progress = max(0.0, min(1.0, float(ctx.part_progress)))
        density = max(0.0, min(1.0, float(knobs.get("density", 0.5))))
        variation = max(0.0, min(1.0, float(knobs.get("variation", 0.3))))
        perc_complexity = max(0.0, min(1.0, float(knobs.get("perc_complexity", 0.4))))
        # Combined intensity dial — density biases the effective intensity
        # so a "loud-but-sparse" pattern is still expressible.
        eff = max(0.0, min(1.0, intensity * (0.5 + density)))

        drive = float(ctx.song_feel.get("drive", 0.0))
        wander = float(ctx.song_feel.get("wander", 0.0))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)

        hits: list[Hit] = []
        if kit_focus == "minimal":
            hits.extend(self._gen_kick(ctx, style, knobs, kit_focus, eff, progress, total_steps, s))
            return hits
        if kit_focus == "kick_only":
            hits.extend(self._gen_kick(ctx, style, knobs, kit_focus, eff, progress, total_steps, s))
            return hits

        if kit_focus != "no_kick":
            hits.extend(self._gen_kick(ctx, style, knobs, kit_focus, eff, progress, total_steps, s))

        if kit_focus != "percussion":
            hits.extend(
                self._gen_snare(ctx, style, knobs, kit_focus, eff, progress, total_steps, s, drive)
            )
        hits.extend(
            self._gen_hats(ctx, style, knobs, kit_focus, eff, progress, total_steps, s, wander)
        )
        if kit_focus != "percussion":
            hits.extend(self._gen_clap(ctx, style, knobs, kit_focus, eff, total_steps, s))
        hits.extend(
            self._gen_perc(
                ctx,
                style,
                knobs,
                kit_focus,
                eff,
                progress,
                total_steps,
                s,
                perc_complexity,
                drive,
                wander,
                variation,
            )
        )
        return hits

    # ----------------------------------------------------------- pieces

    def _gen_kick(
        self,
        ctx: BarContext,
        style: _StyleProfile,
        knobs: KnobDict,
        kit_focus: str,
        eff: float,
        progress: float,
        total_steps: int,
        s: int,
    ) -> list[Hit]:
        target = self._find("kick")
        if target is None:
            return []
        kick_pattern = str(knobs.get("kick_pattern", "auto"))
        if kit_focus == "wind_down":
            # Half-time tail end as the part winds down.
            pattern_choice = "half_time" if progress > 0.5 else "four_floor"
        elif kick_pattern == "auto":
            pattern_choice = "four_floor" if eff >= 0.4 else "half_time"
        else:
            pattern_choice = kick_pattern
        pattern = self._kick_steps(pattern_choice, total_steps)
        vel = self._intensity_velocity(style.kick_vel, eff)
        return [self._hit(target, step * s, vel) for step in pattern]

    def _gen_snare(
        self,
        ctx: BarContext,
        style: _StyleProfile,
        knobs: KnobDict,
        kit_focus: str,
        eff: float,
        progress: float,
        total_steps: int,
        s: int,
        drive: float,
    ) -> list[Hit]:
        target = self._find("snare")
        if target is None:
            return []
        snare_subdiv = str(knobs.get("snare_subdiv", "auto"))
        # Determine grid pulses across the 16-step bar.
        if kit_focus == "build":
            # Snare grid ramps with part_progress — the canonical
            # buildup move. Per-style ceiling: techno + psy hit 32nds
            # at the drop (machine gun); acid caps at 16ths so the
            # build feels tense rather than frantic.
            ramp = progress**style.build_snare_curve
            ceiling = style.build_snare_max
            pulses = int(round(2 + (ceiling - 2) * ramp))
        elif snare_subdiv == "auto":
            # Two-zone ramp with per-style ceiling. Low-ceiling styles
            # (acid) cap their snare density well before the techno /
            # psy ramp would; high-ceiling styles keep the familiar
            # 12 → 24 driving snare in the drop.
            max_pulses = style.default_snare_max
            mid_max = min(12, max_pulses)
            if eff < 0.4:
                pulses = 2  # 2 & 4
            elif eff < 0.7:
                pulses = int(round(4 + (mid_max - 4) * (eff - 0.4) / 0.3))
            elif max_pulses <= 12:
                # Low-ceiling style — already at the cap.
                pulses = max_pulses
            else:
                pulses = int(round(12 + (max_pulses - 12) * (eff - 0.7) / 0.3))
        elif snare_subdiv == "16":
            pulses = 16
        elif snare_subdiv == "32":
            pulses = 32
        elif snare_subdiv == "8t":
            pulses = 12  # 8th-triplets across the bar
        else:
            raise ValueError(f"drum_kit: unknown snare_subdiv {snare_subdiv!r}")

        # When pulses exceed total_steps we shift to a finer grid.
        if pulses <= 2:
            steps = [4, 12]
            base_pattern = [i in steps for i in range(total_steps)]
            base_tick = lambda step: step * s
            hits = [
                self._hit(target, base_tick(step), self._intensity_velocity(style.snare_vel, eff))
                for step, hit in enumerate(base_pattern)
                if hit
            ]
        else:
            # Use a 32-slot grid for >16 pulses so 32nd notes fit.
            grid = max(total_steps, pulses)
            tick_per_slot = max(1, ctx.ticks_per_bar // grid)
            pattern = euclid(pulses, grid)
            hits = []
            for idx, hit in enumerate(pattern):
                if not hit:
                    continue
                tick = idx * tick_per_slot
                # Velocity ramps lower for high-density rolls so it
                # doesn't blast.
                vel_scale = 1.0 - 0.35 * (pulses - 16) / 16 if pulses > 16 else 1.0
                vel = int(round(self._intensity_velocity(style.snare_vel, eff) * vel_scale))
                hits.append(self._hit(target, tick, vel))

        # Drive adds ghost-note layer on off-steps.
        ghost_prob = drive * 0.25 * style.ghost_bias
        if ghost_prob > 0:
            ghost_vel = max(1, int(style.snare_vel * 0.35))
            for step in range(total_steps):
                if step % 2 == 0:
                    continue
                if ctx.rng.random() < ghost_prob:
                    hits.append(self._hit(target, step * s, ghost_vel))
        return hits

    def _gen_hats(
        self,
        ctx: BarContext,
        style: _StyleProfile,
        knobs: KnobDict,
        kit_focus: str,
        eff: float,
        progress: float,
        total_steps: int,
        s: int,
        wander: float,
    ) -> list[Hit]:
        hits: list[Hit] = []
        chh = self._find("chh")
        ohh = self._find("ohh")
        hat_pulses_raw = int(knobs.get("hat_pulses", -1))
        if kit_focus == "wind_down":
            # Hats drop out after the half-way mark.
            if progress > 0.5:
                return hits
        if chh is not None:
            if kit_focus == "build":
                # Hats ramp across the build, increment driven by mech.
                # Low-mech (e.g. acid) stays in the 8–12 range; high-mech
                # (techno/psy) doubles to 16th-density at full progress.
                pulses = int(round(8 + style.build_hat_ramp_delta * progress))
            elif hat_pulses_raw >= 0:
                pulses = hat_pulses_raw
            else:
                pulses = int(round(6 + 10 * eff))  # 6..16
            pattern = euclid(pulses, total_steps)
            vel = self._intensity_velocity(style.hat_vel, eff)
            for step, hit in enumerate(pattern):
                if not hit:
                    continue
                hits.append(self._hit(chh, step * s, vel))
            # Optional triplet-hat polyrhythm layer when intensity is
            # high (techno signature; psy has it sometimes; acid rarely).
            if eff >= style.triplet_hat_above:
                tri_slots = 12
                tick_per_slot = ctx.ticks_per_bar // tri_slots
                for i in range(tri_slots):
                    if i % 3 == 0:
                        continue  # skip the main-beat slot to avoid double-hit
                    hits.append(self._hit(chh, i * tick_per_slot, max(1, int(vel * 0.6))))

        if ohh is not None and eff >= 0.5 and kit_focus not in ("percussion",):
            # Open hat on the "and" of each beat (steps 2, 6, 10, 14).
            for step in (2, 6, 10, 14):
                if step < total_steps:
                    hits.append(self._hit(ohh, step * s, max(1, int(style.hat_vel * 0.9))))

        # Wander seeds a polyrhythmic chh accent overlay.
        if wander > 0 and chh is not None:
            poly_pulses = max(0, int(round(wander * 6)))
            if poly_pulses > 0:
                tri_slots = 12
                tick_per_slot = ctx.ticks_per_bar // tri_slots
                poly = euclid(poly_pulses, tri_slots)
                for i, hit in enumerate(poly):
                    if not hit:
                        continue
                    hits.append(self._hit(chh, i * tick_per_slot, max(1, int(style.hat_vel * 0.5))))
        return hits

    def _gen_clap(
        self,
        ctx: BarContext,
        style: _StyleProfile,
        knobs: KnobDict,
        kit_focus: str,
        eff: float,
        total_steps: int,
        s: int,
    ) -> list[Hit]:
        target = self._find("clap")
        if target is None:
            return []
        clap_on = str(knobs.get("clap_on", "intensity_gate"))
        if clap_on == "never":
            return []
        if clap_on == "intensity_gate" and eff < 0.7:
            return []
        # 2-and-4 in either gate mode.
        return [
            self._hit(target, step * s, max(1, int(style.snare_vel * 0.85)))
            for step in (4, 12)
            if step < total_steps
        ]

    def _gen_perc(
        self,
        ctx: BarContext,
        style: _StyleProfile,
        knobs: KnobDict,
        kit_focus: str,
        eff: float,
        progress: float,
        total_steps: int,
        s: int,
        perc_complexity: float,
        drive: float,
        wander: float,
        variation: float,
    ) -> list[Hit]:
        target = self._find("perc")
        if target is None:
            return []
        if kit_focus == "minimal":
            return []
        pulses = max(0, int(round(perc_complexity * eff * 16)))
        if pulses <= 0:
            return []
        # Perc adopts a clave-ish offset so it doesn't double the kick.
        # Variation seeds the offset choice.
        offset_rng = random.Random((ctx.bar_index * 31 + 7) ^ ctx.part_voice_seed)
        offset = offset_rng.choice((0, 2, 3, 6))
        if variation > 0:
            offset = (offset + offset_rng.randint(0, int(variation * 4))) % max(1, total_steps)
        pattern = euclid(pulses, total_steps, offset)
        base_vel = max(1, int(style.hat_vel * (0.7 + 0.4 * perc_complexity)))
        hits = [self._hit(target, step * s, base_vel) for step, hit in enumerate(pattern) if hit]

        # Build-section roll fill on the part's last bar's last beat.
        if kit_focus == "build" and progress > 0.875:
            # Triplet roll fill across the last beat.
            beats_per_bar = total_steps // 4
            roll_start_step = (beats_per_bar - 1) * 4
            tri_grid = 12
            tick_per_slot = ctx.ticks_per_bar // tri_grid
            roll_start_tick = roll_start_step * s
            for slot in range(tri_grid):
                tick = slot * tick_per_slot
                if tick < roll_start_tick:
                    continue
                window_progress = (tick - roll_start_tick) / max(
                    1, ctx.ticks_per_bar - roll_start_tick
                )
                vel = max(1, min(127, int(base_vel * (0.7 + 0.6 * window_progress))))
                hits.append(self._hit(target, tick, vel))

        return hits

    # ------------------------------------------------------------ utils

    @staticmethod
    def _kick_steps(pattern: str, total_steps: int) -> list[int]:
        if pattern == "four_floor":
            return [step for step in range(0, total_steps, 4)]
        if pattern == "half_time":
            # Beats 1 and 3 only.
            return [step for step in (0, 8) if step < total_steps]
        if pattern == "break":
            # Amen-style breakbeat — kick on 0, 7, 10.
            return [step for step in (0, 7, 10) if step < total_steps]
        raise ValueError(f"drum_kit: unknown kick pattern {pattern!r}")

    @staticmethod
    def _intensity_velocity(base: int, intensity: float) -> int:
        # ±15 around the style's base velocity, scaled by intensity.
        return max(1, min(127, int(base + (intensity - 0.5) * 30)))

    def _find(self, category: str) -> str | None:
        """Return the available instrument name in *category*, or None."""
        for alias in _INSTRUMENT_ALIASES.get(category, ()):
            if alias in self.available:
                return alias
        return None

    @staticmethod
    def _hit(instrument: str, tick: int, velocity: int) -> Hit:
        return Hit(
            instrument=instrument,
            velocity=max(1, min(127, int(velocity))),
            duration_ticks=_NOTE_OFF_OFFSET_TICKS,
            tick=tick,
        )
