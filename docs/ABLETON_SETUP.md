# Ableton + JTX — setup guide

How to connect jtx to Ableton Live so per-voice modulation (cutoff /
resonance / glide / bend) survives swapping instrument patches
without re-doing MIDI Learn every time.

This is the **cross-style fundamentals** doc. For per-style recipes
(which instrument to pick per track, what to map each Macro to)
see:

* [`templates/acid.md`](./templates/acid.md) — acid house
* [`templates/deep_techno.md`](./templates/deep_techno.md) — deep techno
* [`templates/psytrance.md`](./templates/psytrance.md) — psytrance + MPE lead

Pick a style after you've worked through the fundamentals below.

## The pieces

* `jtx/` — generates MIDI to Ableton over IAC bus.
* `setups/ableton.jtx-setup` — bundled generic Ableton starter setup
  (channel layout for acid house). `setups/deep_techno.jtx-setup`
  and `setups/psytrance.jtx-setup` are per-style variants.
* `daw_templates/JtxCCRack.adg` — **the** Ableton Instrument Rack
  preset that does the heavy lifting. Eight Macro knobs are
  pre-wired to the MIDI CCs jtx emits. Drop the rack on a track,
  drop your chosen instrument inside, click Live's Map mode to wire
  each Macro to the instrument's matching param. Swap the
  instrument later → re-Map the Macros once; jtx side stays
  unchanged.

## How parameter mapping works in practice

jtx algorithms emit function-tagged events (e.g. `function="cutoff"`)
which the engine routes to MIDI CCs per each voice's
`parameter_map`. The defaults match the Rack's wiring:

| jtx function | MIDI CC | Rack Macro |
|---|---|---|
| `cutoff` | 74 | Macro 1 — Cutoff |
| `resonance` | 71 | Macro 2 — Resonance |
| `glide` | 5 | Macro 3 — Glide |
| `glide_on` | 65 | Macro 4 — Port |
| `detune` | 1 | Macro 5 — Mod |
| (user-routable) | 102 | Macro 6 — Aux 1 |
| (user-routable) | 103 | Macro 7 — Aux 2 |
| (user-routable) | 104 | Macro 8 — Aux 3 |

CC 102–104 are in MIDI's "undefined" range, used here as jtx-Live
agreed-upon channels for arbitrary user routing — LFO targets, FX
sends, anything you point a `cc_lfo` or `step_cc` modulator voice at.

## One-time setup

### Install the Rack preset

The repo ships `daw_templates/JtxCCRack.adg`. Copy it into your
Ableton User Library so Live shows it in the browser:

```
~/Music/Ableton/User Library/Presets/Instruments/Instrument Rack/
```

Drag the file there in Finder, then restart Live (or refresh the
browser) — `JtxCCRack` should appear under **User Library → Presets
→ Instruments → Instrument Rack** in Live's left panel.

### Configure Live's MIDI input

`Live → Preferences → Link / Tempo / MIDI`:

1. Set the IAC Driver Bus 1 input's **Track** column to **On** so
   tracks can listen on it. (MPE and Remote can stay off unless a
   specific track needs them.)
2. (Optional, for MPE leads) enable **MPE** on the same row.

## Per-track wiring

For each Ableton track jtx will control:

1. Add a **MIDI track**, rename it after the matching jtx voice.
2. **MIDI From**: `IAC Driver Bus 1`. **Channel**: the channel from
   the matching `setups/*.jtx-setup` (or `All Ch` for MPE leads).
3. **Monitor**: `In`.
4. **MIDI To**: `No Output`.
5. Drag **`JtxCCRack`** from your User Library onto the track. The
   eight Macros come up already wired to the agreed CCs.
6. Drag your chosen instrument inside the Rack. Drop it next to or
   between the Macros — Live's Rack UI shows a "Drop an Instrument
   here" area; that's where it goes.
7. Click Live's **Map** button (top-right corner). The interface
   tints. Click each Macro, then click the instrument param it
   should drive (e.g. Macro 1 → instrument's filter cutoff). Click
   **Map** again when done.

That's the per-track setup. The CC → Macro plumbing is baked into
the Rack; you only ever map Macro → instrument param.

## Swap workflow (the whole point)

When you decide a different instrument fits better:

1. Inside the Rack, drag in the new instrument; drag the old one
   out.
2. Click **Map**.
3. Click each Macro in turn → click the new instrument's matching
   param.
4. Click **Map** again.

Done. jtx side untouched, no MIDI Learn, no audition. The CC → Macro
mappings inside the Rack persist across all such swaps.

## MPE

For per-note pitch bend on an MPE lead voice (e.g. psytrance):

1. Set the track's **MIDI From** input row's **Channel** dropdown to
   `All Ch`.
2. Enable the **MPE** toggle that appears next to the channel
   dropdown.
3. Pick an MPE-aware instrument inside the Rack — Wavetable, Drift,
   Sampler, Meld all support MPE.

JTX's MPE-mode voices emit per-note pitch bend on each note's
allocated channel directly (no Rack involvement). The Rack still
handles cutoff / resonance / etc. via its CCs.

## Ableton Link

jtx also supports Ableton Link as a clock source: Setup editor →
General tab → Clock mode → "Ableton Link". Requires the optional
`LinkPython-extern` dependency:

```
pip install 'jamtronix[link]'
```

When Link is active, jtx tempo follows the Link session; start/stop
participates in the shared transport. No further setup — Link
auto-peers on the local network.
