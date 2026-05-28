# Acid template — step-by-step Ableton recipe

Build an Ableton Live set that pairs with jtx's acid-house workflow.
End state: open the `.als`, hit play in jtx with
`setups/ableton.jtx-setup` selected → punchy 808/909 drums, a
303-style acid bass with filter sweeps, a clavy stab, and a clean
lead. Modulation rides Ableton through `JtxCCRack` (the bundled
Instrument Rack preset with all eight Macros pre-wired to CCs).

**Read first**: [`../ABLETON_SETUP.md`](../ABLETON_SETUP.md) — covers
the cross-style fundamentals (how the rack works, how to drop it on
each track, how to wire Macros to instrument params). This doc is
the per-style instrument picks + Macro-to-param mappings.

## Style snapshot

- **Tempo**: 125 BPM (acid-house). Slide up to 130 for harder acid.
- **Key**: `Am` is the canonical starter; works across the bundled
  acid song templates.
- **Energy**: bass-led; acid line carries the song. Drums are tight
  + minimal. Lead + stab punctuate.

## jtx setup → Ableton tracks

Matching setup: **`setups/ableton.jtx-setup`** (the bundled generic
Ableton starter — already laid out for acid).

| jtx voice | Ableton track | MIDI-In channel | Track type |
|---|---|---|---|
| `acid` | **Acid Bass** | ch 2 | MIDI |
| `stab` | **Stab** | ch 3 | MIDI |
| `lead` | **Lead** | ch 4 | MIDI |
| `filter` | **Filter Mod** | ch 5 | MIDI (CC source) |
| `kick` | **Kick** | ch 9 | MIDI (drum rack) |
| `snare` / `chh` / `ohh` | **Drums (core)** | ch 10 | MIDI (drum rack) |
| `tom` / `clave` / `shaker` | **Drums (perc)** | ch 11 | MIDI (drum rack) |
| `chord_ref` | **Chord Ref** | ch 15 | MIDI (utility) |
| `root_ref` | **Root Ref** | ch 16 | MIDI (utility) |

The two utility channels output the current chord + root as held
MIDI notes — wire them to external arpeggiators / chord-followers
(or just route them to a simple polysynth to hear the song's
underlying chord progression).

## Build steps

### 1. Project setup

1. Create a new Live set. Set tempo to **125 BPM**.
2. Top-right corner → **Link** toggle on if you want jtx to lock to
   Live's transport (set jtx clock mode to Ableton Link as well).
3. **Preferences → Link / Tempo / MIDI → MIDI Ports**: enable
   "Track" on the **IAC Driver Bus 1** input. (macOS — for other
   platforms, route jtx's output to a virtual MIDI bus and accept
   that here.)
4. **Install the rack preset** (one-time, if you haven't already):
   copy `daw_templates/JtxCCRack.adg` to
   `~/Music/Ableton/User Library/Presets/Instruments/Instrument Rack/`.
   Restart Live or refresh its browser; the rack should appear
   under **User Library → Presets → Instruments → Instrument Rack**.

### 2. Per-track wiring

For **each instrument** MIDI track in the table above (acid, stab,
lead — NOT drum tracks):

1. Add a MIDI track. Rename it (e.g. "Acid Bass").
2. **MIDI From**: set to `IAC Driver Bus 1`. Set the channel to the
   number from the table.
3. **Monitor**: `In`.
4. **MIDI To**: `No Output`.
5. **Drag `JtxCCRack` from your User Library onto the track**. The
   rack lands with all eight Macros pre-wired to incoming CCs (74,
   71, 5, 65, 1, 102, 103, 104) — no MIDI Learn needed.
6. Drag the instrument (see "Instruments" below) inside the rack
   (Live's Rack UI shows a "Drop an Instrument here" slot — drop it
   there).
7. Click Live's **Map** button (top-right). Click each rack Macro
   knob, then click the corresponding instrument param. Click **Map**
   again to exit.

Drum + modulator + utility tracks skip the rack (they're either
drum racks playing notes, or CC sources passing through).

### 3. Instruments + per-voice Macro-to-param mappings

#### `acid` voice (TB-303 territory)

- **Instrument**: **Drift** (built-in monosynth).
- **Patch starting point**:
  - Oscillator: saw, single voice.
  - Filter: 24 dB ladder lowpass, resonance ~75%.
  - Filter envelope: snappy decay, full env modulation amount.
  - Amp envelope: fast attack, short decay, no sustain or release
    (303 is a percussive sound).
  - Pitch: -1 octave (jtx acid_bass plays in the low register
    already; if it sounds boomy, raise back to 0).
- **Macro mappings** (Live's Map mode):
  - Macro 1 (Cutoff) → Drift's Filter Cutoff.
  - Macro 2 (Resonance) → Drift's Filter Resonance.
  - Macro 3 (Glide) → Drift's Glide (the "glide time" knob in the
    Voice section).
  - Macro 4 (Port) → Drift's Glide On/Off (toggle, mapped from CC65).
  - Other Macros stay unmapped unless you have a use for them.

#### `stab` voice

- **Instrument**: **Wavetable**.
- **Patch starting point**:
  - Oscillator 1: a brassy / vocal wavetable, polyphonic.
  - Amp envelope: fast attack, ~100ms decay, no sustain (it's a
    stab, not a held chord).
  - Reverb send to a Return track with a small Hall.
- **Macro mappings**:
  - Macro 1 (Cutoff) → Wavetable's filter cutoff.
  - Macro 2 (Resonance) → Wavetable's filter resonance.
  - Other Macros optional.

#### `lead` voice

- **Instrument**: **Drift** (monosynth — leads are mono in acid
  song templates).
- **Patch starting point**:
  - Saw oscillator, glide enabled.
  - Filter: 12 dB lowpass, moderate resonance.
  - Amp envelope: medium attack, long release.
  - Pitch -1 octave to land in the mid-register.
- **Macro mappings**:
  - Macro 1 → Drift's Filter Cutoff.
  - Macro 2 → Drift's Filter Resonance.
  - Macro 3 → Drift's Glide time.

#### `filter` voice (modulator)

- This is a **CC-only voice** — no instrument plays on this track.
  jtx algorithms can emit raw CC LFOs / envelopes from a modulator
  voice; the easiest use is to route this track's MIDI output to
  another track's filter via "MIDI To".
- **Quick wiring**: set this track's **MIDI To** to the **Acid
  Bass** track (track-style routing), or leave it disconnected if
  you're not using LFO modulators in your songs.
- No rack needed (raw CC passes straight through to the target).

#### Drums

- **Kick** track: Drum Rack with one cell at MIDI note 36 → an
  808-style kick sample (the bundled 808 Cabasa rack works fine as
  a starting point, or any built-in kick pack).
- **Drums (core)** track: Drum Rack with cells at notes 38 (snare),
  42 (closed hat), 46 (open hat). Use 909-style samples for the
  classic acid sound.
- **Drums (perc)** track: Drum Rack with cells at notes 45 (tom),
  75 (clave), 82 (shaker). Quieter than the core drums — these are
  garnish.

#### Utility tracks (chord_ref / root_ref)

These are optional but useful for sanity-checking. Drop a simple
polysynth (Wavetable's "Init" patch) on the **Chord Ref** track and
a sub-bass patch on **Root Ref**. They'll play the current chord +
root note as jtx moves through the progression — handy reference
when writing, mute on final mixdown.

## Mix + sends

- **Return A**: small Hall reverb (decay ~1.5s). Send small amounts
  from Stab + Lead.
- **Return B**: 1/4-note delay. Send from Lead (the acid line stays
  dry — delay smears its rhythmic precision).
- **Master**: Live's Glue Compressor, ratio 2:1, attack ~30ms,
  release auto. Gentle.

## Save

`File → Save Live Set As… → daw_templates/acid.als` (or wherever
you keep templates locally).

## Verify

1. Open the bundled acid-demo song in jtx:
   `File → Open → examples/acid-demo.jtx`. (You may need to point
   it at `setups/ableton.jtx-setup`.)
2. Hit Play in jtx. You should hear:
   - Kick on every beat (4-on-the-floor).
   - Acid line snaking through ch 2.
   - Stab punctuating on the off-beats.
   - The acid track's filter cutoff sliding smoothly (driven by jtx's
     CC74 LFO landing on Macro 1 of the rack, then Macro 1 → Drift's
     filter cutoff).
3. If the filter doesn't move: confirm the Acid Bass track is
   receiving MIDI (track's input meter blinks on each note). Then
   check the rack — its Macro 1 should be visibly moving. If Macro 1
   moves but the instrument doesn't respond, the Macro → instrument
   mapping is missing or wrong; redo Map mode.
