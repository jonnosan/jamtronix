# Psytrance template — step-by-step Ableton recipe

Build an Ableton Live set for jtx's psytrance workflow. End state:
open the `.als`, load a song against `setups/psytrance.jtx-setup`,
hit play → relentless kick, 16th-note rolling bass, twisted MPE lead
with per-note bends, occasional pluck stab, riser building into
each section.

**Read first**:
[`../ABLETON_SETUP.md`](../ABLETON_SETUP.md) — cross-style
fundamentals. MPE specifics in this recipe — make sure you've got
that doc in mind first.

## Style snapshot

- **Tempo**: 142 BPM canonical. 140 for groovier psy, 145 for
  harder.
- **Key**: `Fm`, `Em`, `Gm` typical. The bundled `psytrance-starter`
  uses `Fm` with a `i VI III VII` progression.
- **Energy**: relentless drive. 16th-note bass under every beat;
  lead snakes across with bends; risers + drops every 8 bars.

## jtx setup → Ableton tracks

Matching setup: **`setups/psytrance.jtx-setup`**.

| jtx voice | Ableton track | MIDI-In channel | Track type |
|---|---|---|---|
| `lead` (**MPE**) | **MPE Lead** | ch 2–7 (block) | MIDI — **MPE-In enabled** |
| `filter` | **Filter Mod** | ch 8 | MIDI (CC source) |
| `kick` | **Kick** | ch 9 | MIDI (drum rack) |
| `snare` / `chh` / `ohh` | **Drums (core)** | ch 10 | MIDI (drum rack) |
| `shaker` / `tom` | **Drums (perc)** | ch 11 | MIDI (drum rack) |
| `bass` | **Bass** | ch 12 | MIDI |
| `pluck` | **Pluck** | ch 13 | MIDI |
| `riser` | **Riser** | ch 14 | MIDI |
| `chord_ref` | **Chord Ref** | ch 15 | MIDI (utility) |
| `root_ref` | **Root Ref** | ch 16 | MIDI (utility) |

**Channel 1 is reserved** as the MPE master — leave it empty. Don't
add a track on ch 1.

## Build steps

### 1. Project setup

1. New Live set, tempo **142 BPM**.
2. Preferences → MIDI: enable Track on `IAC Driver Bus 1`.

### 2. The MPE Lead track — the key wiring

This is where psytrance differs from acid + deep-techno: the lead
voice uses MPE so per-note pitch bends land on the right note.

1. Add a MIDI track, rename **MPE Lead**.
2. **MIDI From**: `IAC Driver Bus 1` — but instead of picking a
   single channel, set it to **"All Ch"** (the dropdown shows
   numbered channels + an "All" option at the bottom). Live's MIDI
   input then accepts all 16 channels and respects per-channel
   data.
3. Click the **MPE** toggle in the track's MIDI input area (it
   appears next to the channel dropdown when "All Ch" is selected).
4. **Monitor**: In.
5. Drop an **MPE-aware instrument**:
   - **Wavetable** (best general-purpose MPE lead — open the
     instrument, ensure the "MPE" badge is lit in the title bar).
   - **Drift** is also MPE-aware and great for screaming psy
     leads.
   - **Sampler** if you want sample-based.
   - **Meld** (modern wavetable, MPE-native).
6. **Drag `JtxCCRack` from your User Library** onto this track. The
   rack's eight Macros come up pre-wired to CCs 74, 71, 5, 65, 1,
   102, 103, 104.
7. Drag your chosen instrument inside the rack.
8. **Macro mappings** (Live's Map mode):
   - Macro 1 (Cutoff) → instrument's filter cutoff. **Heads up** —
     `setups/psytrance.jtx-setup` maps `cutoff` to `MPETimbreTarget`,
     so per-note CC 74 arrives over MIDI directly on each note's
     MPE channel. The rack's Macro 1 ends up receiving track-level
     CC 74 only if the channel routing sends it there too; usually
     for an MPE lead you'd map Macro 1 to a *global* filter cutoff
     fallback (or leave unmapped) and rely on MPE's per-note timbre
     for the active modulation.
   - Macro 2 (Resonance) → filter resonance.
   - Macro 3-4 → optional.

### 3. Other tracks

Standard pattern: drag `JtxCCRack` onto each instrument track,
drag instrument inside, Map Macros to instrument params. See
[`acid.md`](./acid.md#2-per-track-wiring) for the full per-track
wiring procedure.

#### `bass` voice — psy bass

- **Instrument**: **Drift** mono.
- **Patch starting point**:
  - Saw + sub. Heavy.
  - Filter: 24 dB lowpass, cutoff around 400 Hz, light resonance.
  - Amp envelope: ultra-fast attack, snappy decay, almost no
    release (16th-note bass needs short notes to leave gaps for
    the kick).
  - Glide off for clean transitions.
- **Macro mappings** (Live's Map mode):
  - Macro 1 (Cutoff) → Drift filter cutoff (heavy LFO from jtx side
    drives this — the psy filter wobble).
  - Macro 2 (Resonance) → Drift filter resonance.
  - Macro 3 (Glide) → Drift glide (rarely used in psy bass but
    available).

#### `pluck` voice

- **Instrument**: **Operator** (FM synth — psy plucks love
  algorithm-5 carriers with a fast-decay modulator).
- **Patch starting point**:
  - Algorithm 5 (one carrier + one modulator).
  - Modulator decay short (~100ms).
  - Amp envelope short.
- **Macro mappings**:
  - Macro 1 → Operator's global filter cutoff (added via the
    filter section at the bottom).
  - Macro 2 → Operator's filter resonance.

#### `riser` voice

- **Instrument**: **Wavetable** with a noise + filter sweep patch.
- **Patch starting point**:
  - One oscillator on a noise wavetable.
  - Filter: 24 dB lowpass, cutoff modulated automatically by
    jtx's `noise_riser` algorithm via CC74 + pitch-bend ramp.
  - Amp envelope: slow attack (the riser swells across multiple
    bars).
- **Macro mappings**:
  - Macro 1 (Cutoff) → Wavetable filter cutoff (jtx's CC74 ramp
    sweeps this via the rack).
  - Pitch wheel passes through directly to the instrument — no
    Macro needed for bend (the riser's pitch ramp lands on the
    track's MIDI input as native pitch wheel messages).

#### `filter` voice (modulator)

- No instrument; routes raw CC. Use to drive global filter
  modulation across multiple tracks (e.g. side-by-side filter
  sweeps on bass + pluck).

#### Drums

- **Kick**: dedicated psy kick — long sustained click + sub.
  Search the bundled Live drum racks for "Kick 808" or "Hard Kick".
  MIDI note 36.
- **Drums (core)**: snare (38), closed hat (42), open hat (46).
  Use a tight 909-style hi-hat sample — psy hats are short + dry.
- **Drums (perc)**: shaker (82) — runs 16ths or 32nds for forward
  motion. Tom (45) for the occasional rolling fill.

## Mix + sends

- **Return A**: Reverb — short room (decay 0.8s) for snare + pluck.
- **Return B**: Long plate reverb (decay 4s) for lead bursts.
  *Mostly* unused on psy (which prefers dryness) but useful for
  breakdowns.
- **Sidechain compressor** on **Bass** triggered by **Kick**.
  Threshold deep, ratio 6:1, fast attack, release ~140ms (16th at
  142 BPM). This is what makes the 16th-note bass + kick combo
  punch instead of mud.
- **Master**: Limiter (Live's Limiter device, ceiling -0.3 dB,
  attack 5ms).

## Save

`File → Save Live Set As… → daw_templates/psytrance.als`.

## Verify

1. Load `examples/psytrance-starter.jtx` against this template /
   `setups/psytrance.jtx-setup`.
2. Play. You should hear:
   - Kick on every beat.
   - 16th-note bass rolling under (psy bass shape).
   - Lead occasionally entering with audible **per-note** pitch
     bends (this is the MPE proof — if bends only affect the most
     recent note, MPE-In isn't enabled on the track).
   - Riser swelling toward each section's drop.
3. If the lead's per-note bends sound monophonic / smear into one
   note:
   - Confirm the **MPE** badge is lit on the track's MIDI input.
   - Confirm the instrument is MPE-aware (Wavetable / Drift / Meld
     / Sampler all are).
   - Confirm `setups/psytrance.jtx-setup`'s lead voice has
     `mpe_mode: true` (yes by default).
