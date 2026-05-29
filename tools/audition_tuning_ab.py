#!/usr/bin/env python3
"""Render A/B .jtx files for the four sonics anchors under two tunings.

Compares ``default_tuning()`` against the repo's ``tuning.toml`` (the
optimizer's accepted Tier-A snapshot). Writes 8 files into the output
directory::

    acid_default.jtx        acid_tuned.jtx
    deep_techno_default.jtx deep_techno_tuned.jtx
    psytrance_default.jtx   psytrance_tuned.jtx
    dub_techno_default.jtx  dub_techno_tuned.jtx

Each pair shares a title (so identical RNG seed) — the only thing that
differs is the Tuning. Play side-by-side with::

    .venv/bin/python tools/jtx_player.py --loop \\
        /Users/jonno/jtx/audition-r0808/acid_default.jtx
    .venv/bin/python tools/jtx_player.py --loop \\
        /Users/jonno/jtx/audition-r0808/acid_tuned.jtx
"""

from __future__ import annotations

import argparse
from pathlib import Path

from jtx.composer import compose
from jtx.composer.mood import MoodSpec
from jtx.composer.sonics import SONICS_REGIONS
from jtx.composer.tuning import default_tuning, load_tuning
from jtx.persist.json_io import save_song

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same coords the Phase 1b/1c fixtures use — keeps the audition aligned
# with what the optimizer was actually scoring.
SONICS_MOOD: dict[str, MoodSpec] = {
    "acid":        MoodSpec(valence=-0.15, energy=0.55),
    "deep_techno": MoodSpec(valence=-0.35, energy=0.40),
    "psytrance":   MoodSpec(valence=-0.25, energy=0.90),
    "dub_techno":  MoodSpec(valence=0.00,  energy=0.20),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "jtx" / "audition-r0808",
        help="Output directory for .jtx files.",
    )
    ap.add_argument(
        "--tuning",
        type=Path,
        default=REPO_ROOT / "tuning.toml",
        help="Tier-A override to compare against the default.",
    )
    ap.add_argument(
        "--fmt",
        default="loop",
        help="Song format (default: loop — best for A/B; live's looper friendly).",
    )
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    tuned = load_tuning(args.tuning)
    base = default_tuning()
    if tuned == base:
        print(f"warning: {args.tuning} is byte-identical to default_tuning() — "
              f"nothing to A/B.")
        return 1

    for name, (texture, motion) in SONICS_REGIONS.items():
        mood = SONICS_MOOD[name]
        for label, t in (("default", base), ("tuned", tuned)):
            # Stable title → identical RNG seed across the two tunings;
            # any audible difference therefore traces to the override.
            song = compose(
                f"audition-{name}",
                "iac",
                mood,
                args.fmt,
                chaos=0.0,
                texture=texture,
                motion=motion,
                tuning=t,
            )
            path = args.out / f"{name}_{label}.jtx"
            save_song(song, path)
            print(f"  {path.name}: {song.tempo} bpm "
                  f"key={song.key.tonic} {song.key.scale} "
                  f"voices_active={sum(1 for v in song.voices.values() if v.algorithm != 'rest')}")

    print(f"\nWrote 8 files to {args.out}")
    print("Play with:")
    print(f"  .venv/bin/python tools/jtx_player.py --loop {args.out}/<name>_<default|tuned>.jtx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
