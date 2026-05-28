# Per-style Ableton templates

Step-by-step recipes for building Ableton Live sets that pair with
jtx's three flagship styles. Each recipe walks through the track
layout, suggested instrument per voice, rack + Macro wiring, and the
mixing setup that pulls it all together.

| Style | Recipe | Matching jtx setup |
|---|---|---|
| Acid house | [`acid.md`](./acid.md) | `setups/ableton.jtx-setup` |
| Deep techno | [`deep_techno.md`](./deep_techno.md) | `setups/deep_techno.jtx-setup` |
| Psytrance | [`psytrance.md`](./psytrance.md) | `setups/psytrance.jtx-setup` |

## Start here

Read [`../ABLETON_SETUP.md`](../ABLETON_SETUP.md) first if you
haven't already — it covers the cross-style fundamentals:

- How `daw_templates/JtxCCRack.adg` works (the bundled Instrument
  Rack with eight Macros pre-wired to the CCs jtx emits).
- How to drop the rack on a track and wire its Macros to instrument
  params using Live's native Map mode.
- How MPE leads coexist with the rack (rack handles cutoff /
  resonance / etc.; pitch bend rides MIDI directly per-note).
- How to install the optional Ableton Link binding.

Then pick a style recipe above and follow it end-to-end. The result
is a `daw_templates/<style>.als` Live set you can re-open any time
you want to jam in that style.

## Why no committed `.als` files?

Ableton Live Set files are binary artifacts that need Ableton to
construct properly — they encode track UUIDs, device chain layouts,
and instrument-internal state. The canonical source of truth is
this set of recipes; the `.als` is the build output you produce
locally by following them once with Live open.

If you DO commit your finished `.als` back to the repo, drop them
in `daw_templates/`.
