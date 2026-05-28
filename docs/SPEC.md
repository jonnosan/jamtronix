# Jamtronix (jtx) — Functional Spec, v1

## Context

Jamtronix is a new macOS GUI app loosely modelled on the existing `slackbeatz`
Python project at `/Users/jonno/src/slackbeatz`. Slackbeatz works as a CLI
DSL → MIDI generator targeting eight styles, with ~57 generators, deep
composition support (scales, chord progressions, polymeter), and a deterministic
seed mechanism. It is intended for either DAW jamming or headless rendering.

Jamtronix takes the *ideas* that worked in slackbeatz — DSL-defined arrangements,
arranger model, deterministic PRNG, pattern/feel knob split, per-part overrides
— and rebuilds them as a focused **GUI-only, macOS-only, MIDI-out-only** jam tool
optimised for **acid** and **deep techno** workflows (with psytrance as a third
starter template). The CLI surface, multiple-style emphasis, audio backends
(FluidSynth, Surge), and broad generator library are dropped. New concepts:
**modulator** voices for CC-only output, **follower** voices for derived parts,
bar-by-bar live regeneration so external inputs (planned for later) can steer
the music in real time, and Ableton-template launching.

Outcome: a single Mac app that you launch, pick or create a song from a title,
fiddle with knobs while it streams MIDI into Ableton (or any DAW), and tweak per
part vs across all parts. The same song with the same seed always plays the same
way.

---

## Goals (v1)

- Mac-only GUI app for live-jamming with a DAW (Ableton primary, others fine).
- MIDI-out only, with optional offline render of the arrangement to a `.mid`
  file.
- Acid + deep techno coverage out of the box; psytrance template included.
- Deterministic playback from a (song, seed) pair.
- Bar-by-bar regeneration so per-bar knob changes (and future external MIDI-in)
  can steer playback.
- All three sync modes: internal master (default), MIDI Clock slave, Ableton
  Link.
- Engine factored as a standalone Python module so a headless playback CLI can
  be added later with no refactor.

## Non-Goals (v1)

- No CLI surface, no headless mode.
- No audio rendering. jtx never makes sound directly — it only emits MIDI.
- No `surge-xt`, `fluidsynth`, or any synth-backend integration. Ableton/DAW
  template launch is a `open <file>` shell call only.
- No external MIDI-in. Architecture supports it (see "External-input hooks"
  below) but no input is wired in v1.
- No user-authored algorithms. All ~10–12 algorithm classes ship in jtx.
- No backwards compatibility with `.sb` slackbeatz files.

---

## Stack

- **Language**: Python 3.12+ (matches slackbeatz; PySide6 wheels available).
- **GUI**: PySide6 (Qt 6).
- **MIDI**: `mido` + `python-rtmidi` (proven in slackbeatz; works on Mac IAC bus
  and CoreMIDI devices).
- **Clock**:
  - Internal master: `time.perf_counter()` driven scheduler (slackbeatz
    `InternalClock` pattern).
  - MIDI Clock slave: reads 0xF8 ticks from a MIDI-in port, accumulates into PPQ
    480.
  - Ableton Link: `python-link` bindings (or `ctypes` to libabletonlink). Per-app
    setting picks one of the three.
- **Persistence**: JSON `.jtx` files. TOML considered but JSON serialises Python
  dicts cleanly and round-trips without quoting headaches.
- **Packaging**: `briefcase` or `py2app` to produce a `.app` bundle. Decided at
  implementation time.

Project layout (separation matters for the future headless CLI):

```
jtx/
  jtx/                       # engine library (no Qt imports)
    model/                   # Song, Part, Voice, Setup, Algorithm dataclasses
    algorithms/              # all generator classes
    engine/                  # scheduler, clock_source (internal/slave/link)
    sinks/                   # RealtimeMidiSink, MidiFileSink
    persist/                 # JSON load/save
    seed.py                  # SHA-256 deterministic seeding
  jtx_gui/                   # PySide6 app; imports jtx, never the reverse
  templates/                 # hardcoded acid / deep_techno / psytrance song templates
  setups/                    # bundled starter setups (IAC + Ableton)
  examples/                  # one starter .jtx per template
  tests/                     # smoke + golden-fixture tests
```

`jtx_gui` is allowed to import from `jtx`; the reverse is forbidden — that's how
we preserve the option for a headless `jtx play song.jtx` CLI.

---

## Core Concepts

### Setup

A **setup** describes the rig the song talks to. Stored as a `.jtx-setup` JSON
file (or embedded inside a song if the user prefers). Contents:

- **Name** (string).
- **Default MIDI output port** (used for any voice that doesn't override it).
- **Optional DAW template path** (`.als` for Ableton, or any file). A button in
  the GUI opens this via macOS `open`. No further DAW integration; jtx doesn't
  talk OSC, doesn't push program changes, doesn't arm tracks.
- **Voice slots**: a named list of voice configurations. Each slot has:
  - `name` (string, unique within setup),
  - `type` (`drum` / `mono` / `poly` / `modulator` / `follower`),
  - `default_role` (constrained by type — see Voice Types below),
  - `midi_port` (defaults to setup's default port),
  - `midi_channel` (1–16),
  - For `drum`: `kit_map` (`{kick: 36, snare: 38, hat: 42, …}`), defaulting to
    GM drums (channel 10),
  - `parameter_map` (function name → `ParameterTarget`; see Parameter Mapping
    below),
  - `mpe_mode` (bool, default `false`) + `mpe_channel_count` (default `8`) —
    when on, the voice owns the contiguous MPE channel block
    `[midi_channel, midi_channel + mpe_channel_count - 1]` and NoteOns
    round-robin through it for per-note expression.

Songs reference a setup by id; multiple songs can share a setup.

Two bundled starter setups: `IAC Bus 1` (acid/deep-techno default) and `Ableton`
(same routing but with an Ableton `.als` template path empty by default so the
user can fill it in). A third setup, `Ableton MPE`, demonstrates the MPE
channel-block layout for an MPE-aware lead voice.

### Parameter Mapping

Algorithms emit function-tagged events (`ControlChange` / `PitchBend` /
`ChannelPressure` carrying a `function="cutoff"` / `"resonance"` / `"glide"` /
`"bend"` / … tag). A sink-side router consults each voice's `parameter_map` to
rewrite the event for the DAW target. Lookup precedence: voice-slot override →
algorithm `DEFAULT_PARAM_MAP` → unchanged passthrough.

**Function vocabulary** (v1):

| voice type | functions |
|---|---|
| `drum` | (none — drums emit only notes) |
| `mono` | `cutoff`, `resonance`, `glide`, `bend` |
| `poly` | `cutoff`, `resonance`, `bend` |
| `modulator` | (none — emits CC directly) |
| `follower` | (none — passes source events through unchanged) |

**`ParameterTarget` sum type**:

```
CCTarget(cc: int)        # MIDI CC on the voice's channel (default; CC# remap)
MPEPitchBendTarget()     # per-note pitch bend on the MPE-allocated channel
MPEPressureTarget()      # channel pressure on the MPE-allocated channel
MPETimbreTarget()        # CC 74 on the MPE-allocated channel (MPE timbre slot)
OscTarget(address: str)  # send as OSC float to setup.osc_host:osc_port
```

The on-disk shape is dict-discriminated (`{"kind": "cc", "cc": 74}` etc.) so
new variants can be added without bumping the schema.

**OSC parameter routing** (when a function's target is `OscTarget`):

The router calls the configured OSC client out-of-band and produces
no MIDI event for the source. Address scheme:

```
/jtx/<voice_name>/<function>  <float>
```

…where `<voice_name>` is the JTX `VoiceSlot.name` and `<function>` is
the v1 vocabulary name (`cutoff` / `resonance` / `glide` / `bend`).
The float arg is normalised: CC-style sources (`cutoff`/`resonance`/
`glide`) land in `[0, 1]`; bend-style sources land in `[-1, 1]`.

One OSC destination per setup (`Setup.osc_host` / `Setup.osc_port`,
default `127.0.0.1:11000`). The bundled `JtxParameterRouter.amxd` Max
for Live device listens on that port and dispatches by matching the
device's per-instance "voice name" parameter against the message's
voice segment, then driving one of eight Live-mappable parameter
sliders (Cutoff / Resonance / Glide / Bend / Spare 1..4). See
`docs/ABLETON_SETUP.md` for the device + per-track setup.

**MPE channel allocation** (when `mpe_mode == true`):

- Channel 1 is reserved as the **MPE master**. JTX never emits on ch 1 for
  MPE voices; setup validation rejects `mpe_mode=true` with `midi_channel=1`.
- A voice with `midi_channel=2`, `mpe_channel_count=8` owns channels 2..9.
  Each NoteOn claims the next channel in the block round-robin from the
  most-recently-allocated index.
- **Steal-oldest** when the block is full: the displaced note's channel is
  reused, with a synthetic `NoteOff` emitted on it before the new `NoteOn`.
- Tagged events bind to the most-recently-allocated note via a three-tier
  rule that handles `acid_bass`'s leading + trailing pitch-bend wrap:
  1. **Leading**: a NoteOn whose tick is within the next 2 ticks wins
     (catches `tick=NoteOn.tick - 1` pre-bend).
  2. **Trailing**: a note whose NoteOff is exactly at the current tick wins
     (catches the zero-bend reset at `tick=NoteOff.tick`).
  3. **In-lifetime**: any currently-sounding note; most recent wins.
  4. Else: most-recently-allocated channel.
- Notes that span bars survive in the allocator across `events_for_bar` calls
  — the router is per-voice and stateful for the lifetime of a `SongPlayer`.

### Song

A song is a top-level container with:

- **Title** (string). Default seed is `int(sha256(title)) & ((1<<63)-1)`.
- **Seed override** (optional integer). If set, replaces the title-derived seed.
- **Setup reference** (id).
- **Song-level musical defaults**:
  - `key` (root + scale, e.g. `Am`, `Cm dorian`, `F# phrygian`),
  - `meter` (e.g. `4/4`),
  - `tempo` (BPM),
  - `chord_progression` (Roman-numeral degrees + bars-per-chord, e.g.
    `i VI III VII × 4 bars` — see Macro Chord Progression below).
- **Voice configurations**: one per voice in the setup the song uses, each
  carrying:
  - Selected algorithm (drawn from algorithms valid for that voice's type/role),
  - Pattern knob values (full schema for the algorithm),
  - Feel knob values (universal set, see Feel Knobs below).
- **Parts**: ordered list of named parts.
- **Arrangement**: a sequence of part references with bar counts — the playlist.
- **LFOs**: zero or more named LFO definitions (see LFOs below).

Songs are written to `~/jtx/songs/<title-slug>.jtx` by default; user can save
anywhere.

### Voice Types and Roles

Six types. The type constrains which roles and which algorithms are valid.

| Type | Roles | What it emits |
|------|-------|---------------|
| `drum` | `drum` | Single MIDI note on the slot's channel (slot.note) |
| `drum_kit` | `drum_kit` | Multi-piece kit: each piece carries its own `(channel, note)` via `kit_map` |
| `mono` | `bass`, `lead` | One note at a time + optional CC modulation |
| `poly` | `pad`, `stab`, `chord` | Multiple simultaneous notes |
| `modulator` | `modulator` | CCs and PitchBend only — no notes |
| `follower` | `follower` | Notes derived from another voice's output |

**Critical rule** (clarified during scoping): pattern knobs are
**per-algorithm**, not per-role. Only *defaults* vary by role. This means a bass
voice and a lead voice running the same algorithm with the same knob values
produce identical music up to MIDI channel — a useful property for
double-tracking and for `follower` voices' source-of-truth checks.

#### `drum` vs `drum_kit`

* A `drum` voice represents one piece (kick or snare or hat). Its
  emissions land on `slot.midi_channel` at `slot.note`. The legacy
  single-entry `kit_map` field is gone in schema v3.
* A `drum_kit` voice represents an entire kit. `slot.kit_map` is a
  dict of `piece_name → KitPiece(note, channel)` — each piece can sit
  on its own MIDI channel (kick on ch9, hats on ch10, perc on ch11).
  Algorithms emit abstract `Hit(instrument=name)` events; the voicing
  stage looks the name up in the slot's `kit_map`.

### Abstract Events

Algorithms know about *musical concepts* (instruments, parameter
functions, pitches) and **not** about MIDI plumbing (channels, CC
numbers, voice routing). They emit abstract events; a **voicing
stage** at the end of the pipeline translates abstract → MIDI using
the voice's slot.

Event types (`jtx/model/events.py`):

* `Hit(instrument: str | None, velocity, duration_ticks, tick)` — a
  drum hit. On a `drum_kit` slot, `instrument` keys into `kit_map`
  for `(channel, note)`. On any other slot, `instrument=None` (or
  the voice's own name) lands on `(slot.midi_channel, slot.note)`.
* `Note(pitch, velocity, duration_ticks, tick)` — a pitched note.
  `pitch` is a MIDI note number used as a *universal integer pitch
  encoding* (not MIDI plumbing). The voicing stage adds the channel.
* `Param(name, value, tick)` — a parameter set on a function name
  (`cutoff`, `resonance`, `glide`, `bend`). The voicing stage routes
  via `slot.parameter_map` / algorithm `DEFAULT_PARAM_MAP`. `value`
  is normalised (`[0,1]` for CC-style, `[-1,1]` for bend).
* `PolyAftertouch(pitch, pressure, tick)` — per-note expression on
  poly / MPE voices.

Why this matters: cross-cutting features (sidechain, parameter
mapping, LFO targeting) operate on instrument / function *names*
rather than channel/note tuples. Pump's
`sidechain_from=["kick"]` works uniformly whether the kick is a
standalone `drum` voice or a piece inside a `drum_kit`.

### Algorithm Library (~10–12 classes)

Consolidated from slackbeatz's 57 generators. Each algorithm declares its
**pattern knob schema** (knob name → type, range, default). Defaults can be
overridden per role.

| Type | Algorithm | Notes / knobs in scope |
|------|-----------|-----------------------|
| drum_kit | `drum_kit` | Headline drum algorithm. Coordinates kick/snare/hats/perc across the voice's `kit_map` based on `style` (acid/techno/psy), `kit_focus` (full/minimal/kick_only/no_kick/percussion/build/wind_down), `density`, `variation`, `perc_complexity`, and `ctx.part_intensity` / `ctx.part_progress`. MIDI-naive: emits `Hit(instrument=name)`; voicing stage maps each piece to its `(channel, note)`. |
| drum | `drum_pattern` | Unified euclidean + four-on-floor + breakbeat via knobs (`style=euclid|four_floor|break`, per-piece pulses/offsets, ghost layer, polyrhythm + `polyrhythm_subdiv` for continuous triplet hat, `roll_pos`/`roll_subdiv`/`roll_depth` for triplet roll fills) |
| drum | `drum_one_shot` | Single hits at given steps; useful for claps, crashes, tom rolls (`roll_pos`/`roll_subdiv`/`roll_depth`) |
| mono | `acid_bass` | 303-style step sequencer (probabilistic note picks, octave jumps, slide, internal CC74/CC71 sweep, pitch-bend wobble, optional `triplet_prob` for breakdown rolls) — covers slackbeatz `acid_303` |
| mono | `sub_drone` | Sustained drone, root/fifth alternation, optional progression follow, optional kick-locked filter envelope — covers slackbeatz `subdrone` (deep techno staple) |
| mono | `melodic_line` | Step-sequenced riff with passing tones, configurable `subdivision` (incl. 8t/16t triplet grids) and per-beat `triplet_prob` rolls — covers `rolling`, `gallop`, `mellow_pick`, `rhodes_phrase`, `acid_lead`, `psy_lead` |
| mono | `motif_phrase` | Structured A-A'-A-B lead: rhythm-template + pitch-contour cell tiled across a phrase, with slot-label transforms (transpose/octave/density/displacement/retrograde) and scale-step progression. Uses `ctx.rng_hold` to keep base motif content stable across the phrase. Built for psy / acid leads where the line *develops* rather than walking randomly. |
| mono | `arp` | Up/down/random/walk arpeggio with `subdivision` (16/8/4/8t/16t/…), octaves, gate, hold — covers `sh101_arp`, `arp_walk` |
| poly | `sustained_chord` | Long-gated chord voicing following the progression — covers `triad_sustain`, `pad_drift`, `sustained_dyad`, `atmos_pad` |
| poly | `chord_stab` | Short-gated voicings on configurable steps — covers `offbeat_stab`, `acid_stab`, `wurli_chop` |
| mono | `reese_bass` | Held bass with rhythmic CC74 wobble + slow detune LFO — modern dub-techno / half-time wobble bass not covered by `acid_bass` or `sub_drone` |
| mono | `noise_riser` | Multi-bar crescendo voice: retriggered NoteOn + CC74 + pitch-bend ramp. Build-up into the drop |
| modulator | `cc_lfo` | Single CC with shape (sine/tri/saw/square/random), rate (bars/beats), depth, phase — direct replacement for `candy` family |
| modulator | `cc_envelope` | Triggered envelope on CC, with attack/decay/sustain/release driven by bar/beat events — for kick-synced filter sweeps |
| modulator | `step_cc` | Step-sequenced CC modulator — knob-driven value curves on a configurable subdivision (rhythmic, not periodic) |
| follower | `voice_follower` | Single algorithm, fixed pipeline (see Followers below) |

14 algorithms. Future additions get added per-PR.

### Followers

A follower voice listens to one **source voice** by name. Its single algorithm
(`voice_follower`) implements a **fixed pipeline** in this order:

```
source → latch → pattern_transform → transpose → chord → quantize_to_scale → ratchet → output
```

- **Latch**: gate which incoming events pass through. Modes: `all`, `first_per_bar`,
  `every_nth=N`, `accent_only` (velocity ≥ threshold).
- **Pattern transform**: `invert` (mirror around axis pitch), `retrograde`
  (reverse the bar), `thin=p` (drop fraction p of events), `none`.
- **Transpose**: combined semitones (`±N`) and octaves (`±N`).
- **Chord**: emit one note per **semitone offset** in a list, relative to the
  incoming note. Default `[0]` (i.e. one-to-one, no chord). Setting
  `[0, 4, 7]` builds a major triad off every input note; `[0, 3, 7]` a minor
  triad; `[0, 5]` a power chord; etc. With one offset this is a
  fixed-interval shift; with several it's a chorder. Semitones (not scale
  degrees) keep the chorder simple and predictable — diatonic fitting is the
  next step's job.
- **Quantize to scale**: snap each output note to the nearest pitch in a
  scale. Defaults to the current song/part scale. Options: `off`, `nearest`,
  `up`, `down`, plus an explicit scale override (so you can build a chromatic
  chord and quantize to a different scale than the source voice is using).
  With `off`, the chord step's literal semitones pass through unchanged.
- **Ratchet**: turn each output note into N evenly-spaced repeats inside its
  duration. Knob: `ratchet` (1 = off; `ratchet=3` is the triplet-fill
  primitive). `ratchet_curve` (`flat` / `ramp_up` / `last_beat` / `pulse`)
  varies the count per note across the bar so triplet bursts can be
  positioned without per-step lists.

Follower voices can chain: a follower can be the source of another follower, so
any required reordering of the pipeline is built up by chaining. Cycles are
forbidden and detected at song-load time.

### Pattern vs Mix vs Global Feel Knobs

Schema v3 introduces three distinct knob surfaces:

- **Pattern knobs** (per voice): algorithm-specific. They control
  *what notes are emitted*. Schema declared by the algorithm class.
  Examples: `acid_bass.slide_prob`, `drum_kit.kit_focus`, `arp.rate`.

- **Mix knobs** (per voice, `VoiceConfig.mix`): mix-pass shaping —
  *how velocities + envelope behave for this voice*. Run after the
  algorithm emits, before the post-emit feel pass:
  - `sidechain_from` (list of **instrument names** — e.g. `["kick"]`),
    `sidechain_floor`, `sidechain_release_beats`.
  - `fade_in_at_bar`, `fade_in_beats`, `fade_out_at_bar`,
    `fade_out_beats`, `fade_sustain_level`, `fade_shape`,
    `fade_min_velocity`.
  - `evolution_start`, `evolution_end` (linear velocity ramp across
    the part).

- **Global feel knobs** (song-wide, `Song.feel`): five knobs that
  span every voice and compose across mix-pass + feel-pass +
  algorithm-side reads:
  - **Pump** (0..1) — compiles to synthetic `sidechain_from=["kick"]`
    on every non-kit voice via `jtx.engine.global_feel`. The depth
    scales the sidechain floor (`127 - pump*80`). Explicit user
    `sidechain_from` wins on key collision.
  - **Groove** (0..1) — feel-pass: swing on hat instruments
    (`chh`/`hh`/`ohh`/`hat`) and on lead/stab/chord NoteOns; humanize
    ≈ `groove*8` ticks; accent +`groove*14` velocity on beats 2 & 4.
  - **Drive** (0..1) — feel-pass: +`drive*15` velocity on every Hit
    + Note, and a "cutoff push" that adds `drive*0.2` to every
    `Param(name="cutoff").value` (clamped at 1.0). Pairs the louder
    + brighter shifts so the mix audibly gets harder as you turn it
    up. drum_kit additionally reads `ctx.song_feel["drive"]` for
    ghost-note + roll-fill probability boosts.
  - **Tension** (0..1) — applied directly in `SongPlayer`:
    `intensity_eff = clamp(0.5 + (intensity - 0.5) * (0.5 + tension*1.5))`.
    At 0 the per-part intensity envelope collapses to 0.5; at 1 it
    exaggerates 1.5×.
  - **Wander** (0..1) — feel-pass: per-bar mute probability
    ≤ `wander*0.1`; per-NoteOn octave-jump probability
    ≤ `wander*0.15` (melodic voices only).

The deleted v1/v2 per-voice feel grab-bag (humanize / swing / accent /
mute_prob / octave_jump / passing_tones / gate_jitter / vel_jitter)
is gone. The functionality it represented is now expressed via
Groove / Drive / Wander — and (for the cases that legitimately want
*per-voice* behaviour like a build-up reese-bass fade-in) via the
surviving Mix knobs.

### Knob Scope (Override Model)

Resolution order, most-specific first (mirrors slackbeatz):

```
part-level override → song-level voice value → algorithm default for role → algorithm default
```

GUI UX:
- The song view shows the song-level value for every knob; edits there change
  the value for *all* parts.
- Entering a part view shows the same knobs, each with an "override here"
  checkbox. Toggling it scopes that knob to the current part; unchecking removes
  the override.
- Knob widgets visibly distinguish "inherited from song" vs "overridden in this
  part" (e.g. tint + tooltip showing the inherited value).

### LFOs

Named, song-level LFOs as in slackbeatz Phase #65. Each LFO has:

- `name`,
- `shape` (sine / tri / saw / ramp / square / random / s&h),
- `period_bars` (cycle length in bars; fractional values land sub-bar),
- `phase` (0–1),
- `depth` (0–1),
- `samples_per_bar` (default 1) — how many times the LFO is sampled
  per bar for **event-emitting** targets (`midi:` / `voice:`).
  Higher = smoother sweep at the cost of more events. Knob-writing
  targets (`pattern:` / `mix:` / `global_feel:` / `root:`) always
  sample once at tick 0 regardless — they back read-once knob dicts.

LFOs are *applied* by binding them to a target in a part. Target scopes:

- `pattern:<voice>:<knob>` — modulates a pattern knob,
- `mix:<voice>:<knob>` — modulates a per-voice mix knob
  (sidechain / fade / evolution),
- `global_feel:<knob>` — modulates a song-wide feel knob
  (`pump`/`groove`/`drive`/`tension`/`wander`),
- `voice:<voice>:<function>` — drives a voice parameter by logical
  name (`cutoff` / `resonance` / `bend` / …). The LFO emits
  `Param(name=function, value=...)` events into the named voice's
  stream; the **parameter router** resolves `function` via
  `slot.parameter_map` (or the algorithm's `DEFAULT_PARAM_MAP`) to a
  concrete CC / MPE / OSC target. Lets a single LFO config drive the
  right wire format regardless of how the voice happens to be routed
  on a given setup. Combined with `samples_per_bar` this replaces
  the retired `cc_lfo` voice algorithm.
- `midi:ch<N>:cc<M>` — direct CC output,
- `root:<voice>` — modulates the root note (in semitones or scale degrees).

The legacy `feel:<voice>:<knob>` target was removed in schema v3 —
`mix:` covers per-voice surface, `global_feel:` covers song-wide.

**Phantom voices.** A `voice:<v>:<fn>` target may name a setup slot
that has no `Song.voices` entry (e.g. a `filter` modulator slot
driven entirely by an LFO). The SongPlayer builds a parameter_router
per such phantom slot so LFO emissions still route through
`slot.parameter_map`.

Applications are part-scoped (you can apply `slow_sweep` in `build` but not in
`drop`). This is strictly more powerful than the modulator voice type
(`cc_envelope` / `step_cc`) but coexists with it: modulator algorithms
are the convenient case for *envelope*-shaped or *step-sequenced*
modulation that doesn't fit a single sine/saw LFO.

### Macro Chord Progression

Stored as Roman-numeral degrees plus bars-per-chord. Example:

```json
{ "degrees": ["i", "VI", "III", "VII"], "bars_per_chord": 4 }
```

Degrees combine with the song's scale + tonic to produce concrete chords. Each
algorithm receives, per bar:
- the song-level key root,
- the *current* macro-chord degree and its resolved root note.

What each algorithm does with that input is its choice (sub_drone follows it,
acid_bass may or may not, drum ignores it). This means an algorithm doesn't need
to know the progression; it just gets the current chord root every bar.

This sets up the planned external-input hooks: when MIDI-in is wired later,
incoming root notes simply replace the current chord-degree-resolved root for
upcoming bars. The same scaffolding works for both internal progressions and
external steering.

### Per-Voice Overrides Inside a Part

Within a part, a voice can override:
- `key` (scale + tonic — for modal mixture moments),
- `meter` (for polymeter — e.g. drums 4/4, bass 3/4),
- algorithm (swap which algorithm this voice runs in this part),
- any pattern or feel knob.

Tempo is **part-level only** (not per-voice) so the scheduler has a single PPQ
clock per part.

### Seed Model

- Default song seed: `int(sha256(title)) & ((1<<63)-1)`.
- User can override with an explicit integer in the song header (a "Reroll"
  button regenerates this to a random int).
- Per-(part, voice) seed: `sha256(song_seed || part_name || voice_name)` → first
  8 bytes → 63-bit int. Same scheme as slackbeatz, no Python hash randomisation.
- Per-bar seed (for LFOs and bar-by-bar regen): combines the above with
  `bar_index`.

Cyclic PRNG streams (`derive_loop_seed` / `derive_hold_seed`) layer on top of the
per-(part, voice) seed so any algorithm can ask for *repeating* randomness
without breaking the bar-stateless contract. `BarContext.rng_loop(period)` returns
an RNG that loops on an N-bar period (`bar_index % period` — bars at the same
slot share the seed, so a 4-bar phrase repeats forever). `BarContext.rng_hold(period)`
returns an RNG that holds for N bars before changing (`bar_index // period` — used
by `motif_phrase` to keep base motif content stable across a phrase). Both accept
`period=0` (off-sentinel — returns the bar-fresh `ctx.rng`), `period=1`
(loop-only — every bar identical), and `period="part"` (constant across the
part). A `salt` argument keeps multiple cyclic streams in the same algorithm
distinct.

Guarantees:
- Same (title, seed, song state) always plays the same notes.
- Repeated parts in the arrangement (`drop drop`) play identically by default.
- A single part with `seed-variant per instance` enabled cycles through deterministic
  variants based on arrangement position.

---

## Arrangement and Playback

### Arrangement

The arrangement is a timed playlist (sequence of part references), each with a
bar count. Example: `intro 16 → build 16 → drop 32 → build 16 → drop 32 → outro 8`.

### Live Override

During playback, the user can click any part to queue it. When the next bar
boundary arrives, jtx switches to that part. If the queued part finishes (its
configured bar count elapses), jtx returns to the playlist *at the position
after the part that was running when the override was triggered* (so live
overrides feel like an Ableton-style scene fire, not a permanent edit).

### Bar-by-Bar Regeneration (Architectural Commitment)

Generators in jtx must yield events **one bar at a time**, taking the current
context (key root, current chord, knob values, LFO outputs) as input. The
scheduler pulls one bar ahead at all times. This means:

- Per-bar regen is the *only* mode. There is no "render the whole part up
  front" path.
- Knob tweaks during playback land within ~1 bar.
- Future external-input wiring can shove a new root note into the upcoming bar
  with no refactor.
- Determinism is preserved by per-bar seeding (see Seed Model).

Algorithms expose `def generate_bar(self, ctx: BarContext) -> list[Event]`. The
`BarContext` carries the bar's seeded RNG, current chord, current key, knob
values resolved at *that bar's* scope, and absolute tick offset.

### Clock Modes

A single setting at the app level chooses one of:

1. **Internal master** (default). jtx's perf-counter scheduler drives playback.
   Can emit MIDI Clock (0xF8) on a configurable port so external gear chases.
2. **MIDI Clock slave**. jtx listens on a configurable MIDI-in port for Start /
   Stop / Continue / Clock, accumulates ticks, and uses that as its time source.
3. **Ableton Link**. Joins a Link session; tempo and downbeat phase come from
   Link. jtx contributes its tempo when changed in the UI.

Switching modes is allowed only while stopped.

---

## Persistence Format

`.jtx` files are JSON. One file per song. Setups are stored as `.jtx-setup` JSON
files. Schema version field at the top so we can migrate later. No round-tripping
to a text DSL in v1.

Shape (schema v3 sketch):

```json
{
  "schema_version": 3,
  "title": "Phuture",
  "seed_override": null,
  "setup_ref": "ableton",
  "key": { "tonic": "A", "scale": "minor" },
  "meter": "4/4",
  "tempo": 122,
  "chord_progression": { "degrees": ["i","VI","III","VII"], "bars_per_chord": 4 },
  "feel": { "pump": 0.5, "groove": 0.2, "drive": 0.5, "tension": 0.5, "wander": 0.1 },
  "voices": {
    "kit":   { "algorithm": "drum_kit",   "pattern": {"style":"acid","kit_focus":"full"}, "mix": {} },
    "acid":  { "algorithm": "acid_bass",  "pattern": {...}, "mix": {} },
    "organ": { "algorithm": "chord_stab", "pattern": {...}, "mix": {"fade_in_at_bar":4, "fade_in_beats":8} }
  },
  "parts": {
    "intro": {
      "bars": 8,
      "intensity_start": 0.2, "intensity_end": 0.35,
      "voice_overrides": { "kit": { "pattern": { "kit_focus": "minimal" } } }
    },
    "build": {
      "bars": 8,
      "intensity_start": 0.35, "intensity_end": 0.95,
      "voice_overrides": { "kit": { "pattern": { "kit_focus": "build" } } }
    },
    "drop":  { "bars": 32, "intensity_start": 0.9, "intensity_end": 0.85 }
  },
  "arrangement": ["intro", "build", "drop", "build", "drop", "outro"],
  "lfos": [
    { "name": "slow_pump", "shape": "sine", "period_bars": 32, "depth": 0.6,
      "applications": [ { "part": "drop", "target": "global_feel:pump" } ] }
  ]
}
```

Setup file (`.jtx-setup`) shape for a drum_kit voice:

```json
{
  "name": "kit",
  "type": "drum_kit",
  "default_role": "drum_kit",
  "midi_channel": 9,
  "kit_map": {
    "kick":  {"note": 36, "channel": 9},
    "snare": {"note": 38, "channel": 10},
    "chh":   {"note": 42, "channel": 10}
  }
}
```

…and for a single-piece drum voice:

```json
{
  "name": "kick",
  "type": "drum",
  "default_role": "drum",
  "midi_channel": 10,
  "note": 36
}
```

---

## New-Song Wizard

Three steps:

1. **Title** — text input.
2. **Style template** — pick one of: `acid`, `deep techno`, `psytrance`. This
   chooses a hardcoded template (Python module under `templates/`) that
   specifies starting tempo, scale, parts, voices (drum + bass + chord + lead +
   one modulator typically), algorithms, and per-role default knobs. Style is
   used *only* at song-creation time; it is **not** stored on the resulting
   song.
3. **Setup** — pick from bundled setups or create a new one.

After creation the song is just a song: all voices, algorithms, and knobs are
fully editable. There is no "switch style" button later; if you want a different
starter, create a new song.

---

## GUI Structure (PySide6)

Single-window app with three main views, accessible via a left sidebar:

1. **Song view**: header (title, seed, setup, key, meter, tempo, chord
   progression), voice list with per-voice algorithm + collapsible pattern/feel
   knob panels, LFO definitions list.
2. **Parts view**: list of parts; clicking a part opens its detail view with the
   same voice/knob panels but every knob has the "override here" toggle.
   Arrangement editor (drag/reorder + bar counts) along the bottom.
3. **Live view** (primary jam surface): big play/stop transport, current part
   highlight, queueable part buttons, all knobs from the active part exposed as
   knob widgets, a bar/beat indicator. This is the surface used during a jam.

Top toolbar: clock mode selector, MIDI out port selector (override of setup),
"Launch DAW template" button (if setup has a template path), "Render to MIDI
file" button (offline export).

### Knob Widgets

Pattern knobs: standard rotary knob widget with numeric edit. Modulator
indicators: small dot on the corner of the knob shows whether an LFO is bound
to it (click to inspect). Feel knobs: same widget, in a distinct visual group.

---

## Offline MIDI File Export

A button on the live view renders the entire arrangement deterministically (no
live overrides — pure playlist) to a `.mid` file at a path the user picks. Same
scheduler, but a `MidiFileSink` instead of `RealtimeMidiSink`. No audio bounce.

---

## External-Input Hooks (Built, Not Wired)

The architecture must accommodate future external MIDI-in steering of the root
note. To make this cheap to enable later:

- `BarContext.chord_root` is sourced from a `RootProvider` interface. The
  default `ProgressionRootProvider` reads the song's chord progression. A
  future `ExternalMidiRootProvider` will read the last note received on a
  configured MIDI-in channel.
- Switching providers is a single line in the engine bootstrap; no algorithm
  changes required.
- No GUI exposure of this in v1. The interface exists, no concrete external
  provider is built, no settings UI for inbound channel.

---

## Bootstrap (Before Any Code)

Order of operations once this plan is approved:

1. **Create the GitHub repo** `jonnosan/jamtronix` using the `jonnosan` gh
   account (same account as slackbeatz; see `reference_github_issues_workflow`).
   - Visibility: assume **public** to match `jonnosan/slackbeatz`. Confirm
     before creating; this is not a Callendina fleet repo, so the
     `feedback_fleet_repos_private` default doesn't apply.
   - Default branch: `main`.
   - Add MIT license (matches slackbeatz) and a minimal README pointing at
     `docs/SPEC.md`.
2. **Land this design doc** at `docs/SPEC.md` in the new repo, in the initial
   commit alongside the README + LICENSE. The plan file at
   `~/.claude/plans/i-want-you-to-lovely-boole.md` is moved into the repo
   verbatim (with minor formatting/path fixes — e.g. drop the prefatory plan
   metadata).
3. **Create GitHub issues** to track the build. Proposed initial set, in
   rough implementation order:

   1. `repo bootstrap` — pyproject, ruff/mypy config, `.venv` setup notes,
      package skeleton (`jtx/`, `jtx_gui/`, `templates/`, `setups/`,
      `examples/`, `tests/`).
   2. `engine: data model` — Song/Part/Voice/Setup/Algorithm dataclasses +
      JSON load/save with `schema_version` field.
   3. `engine: seed derivation` — `derive_seed`, title→seed, per-(part,voice)
      and per-bar seeding. Unit tests for determinism.
   4. `engine: scheduler skeleton + InternalClock` — perf-counter master clock,
      `BarContext`, bar-by-bar generator interface, sort+dispatch loop.
   5. `engine: RealtimeMidiSink + MidiFileSink` — `mido` + `python-rtmidi`,
      offline export path.
   6. `engine: clock modes — MIDI Clock slave + Ableton Link` — both added
      behind a `ClockSource` ABC.
   7. `algorithms: drum_pattern + drum_one_shot` — euclidean + four-floor +
      breakbeat unified, ghost layer, polyrhythm.
   8. `algorithms: acid_bass` — covers `acid_303` knobs (slide, cycle,
      resonance, bend) and `intensity`/`octave`.
   9. `algorithms: sub_drone` — root/fifth, progression follow, kick_env.
   10. `algorithms: melodic_line + arp` — covers riff/lead/arp generators.
   11. `algorithms: sustained_chord + chord_stab` — pad and stab voicings.
   12. `algorithms: cc_lfo + cc_envelope (modulator type)` — convenient case.
   13. `algorithms: voice_follower` — fixed pipeline (latch → transform →
       transpose → chord → ratchet), cycle detection.
   14. `engine: LFO system` — named LFOs, target scopes (pattern / feel /
       midi / root), per-bar evaluation.
   15. `engine: feel post-emit pass` — universal feel knobs applied at the
       scheduler level (humanize/swing/jitter/etc.).
   16. `engine: external input hook stub` — `RootProvider` interface +
       default `ProgressionRootProvider`, no MIDI-in concrete impl.
   17. `gui: Qt skeleton + Song view` — sidebar nav, title/seed/setup/key/
       meter/tempo widgets, voice list with algorithm picker, pattern + feel
       knob panels.
   18. `gui: Parts view + override toggles` — part list, per-part voice
       overrides, arrangement editor.
   19. `gui: Live view (jam surface)` — transport, current-part highlight,
       queueable parts, knob widgets bound to active part.
   20. `gui: new-song wizard` — title + style picker (acid / deep_techno /
       psytrance) + setup picker; hardcoded templates under `templates/`.
   21. `gui: clock mode selector + DAW template launcher` — toolbar items.
   22. `bundle: starter setups (IAC + Ableton) and one example song per style`.
   23. `packaging: macOS .app bundle` — briefcase or py2app, decided after
       17 works.

   Each issue gets a `v1` milestone. Labels follow
   `reference_github_issues_workflow`: `engine`, `gui`, `algorithm`, `infra`,
   `docs`.

## Verification

This is a personal-use jam app following the same testing posture as slackbeatz
(see `feedback_no_formal_tests`): minimal pytest + golden fixtures, primary
verification via the GUI itself.

End-to-end check before declaring v1 done:

1. Launch jtx, create a new "acid" song titled `Phuture Test`. Confirm seed is
   the title hash.
2. Acid template populates with kick + acid bass + chord stab + cc_lfo + arp
   melody. Confirm it plays through IAC Bus 1 into Ableton and lands on the
   right tracks.
3. Tweak the acid bass `slide_prob` mid-playback — verify next bar reflects it.
4. Mark `slide_prob` as a part-level override in `drop`; verify other parts keep
   the song-level value.
5. Add a follower voice listening to the acid bass, transpose +12, latch
   `first_per_bar`. Verify output.
6. Repeat the same song with same title + no seed override on a second machine;
   verify identical MIDI output (byte-for-byte after sort).
7. Render to `.mid`. Import to Ableton. Verify it sounds identical to the live
   stream.
8. Switch clock to Ableton Link with Ableton running. Verify jtx follows
   Ableton's tempo and downbeat.
9. Click an `.als` template launch button; confirm Ableton opens that project.

If items 1–9 pass, v1 ships.

---

## Open Items (Decide During Implementation)

These don't block writing the spec but will need decisions soon:

- **Drum kit naming convention**: agreed kit map vocabulary across all `drum_*`
  algorithms — confirm at first algorithm implementation.
- **Packaging**: `briefcase` vs `py2app`. Decide once a working dev loop exists.
- **Ableton Link binding**: confirm `python-link` is current and works on the
  user's Python build; if not, fall back to a `ctypes`-wrapped `libabletonlink`.
- **Live-override return behaviour**: spec'd as "return to playlist after override
  part finishes". Confirm with first jam that this feels right; alternative is
  "stay on override part until next override fired".
- **LFO output rate**: continuous-CC LFOs need a tick rate (e.g. every 4 ticks
  ≈ 90 Hz at 480 PPQ). Pick during scheduler implementation.

---

## Critical Files (When Implementation Starts)

These slackbeatz files are the closest reference for each jtx subsystem:

| jtx subsystem | slackbeatz reference |
|---------------|---------------------|
| Deterministic seeding | `/Users/jonno/src/slackbeatz/slackbeatz/engine/scheduler.py` (`derive_seed`) |
| Scheduler / clock | `/Users/jonno/src/slackbeatz/slackbeatz/engine/clock_source.py` |
| Realtime MIDI sink | `/Users/jonno/src/slackbeatz/slackbeatz/sinks/realtime.py` |
| Feel knob registry | `/Users/jonno/src/slackbeatz/slackbeatz/generators/feel.py` |
| Acid bass algorithm | `/Users/jonno/src/slackbeatz/slackbeatz/generators/bass/acid_303.py` |
| Sub-drone algorithm | `/Users/jonno/src/slackbeatz/slackbeatz/generators/bass/subdrone.py` |
| Scale / progression theory | `/Users/jonno/src/slackbeatz/slackbeatz/theory/scales.py`, `_shared.py` |
| Per-part / per-gen override resolution | `/Users/jonno/src/slackbeatz/slackbeatz/model/song.py`, `/model/context.py` |
| LFO application | `/Users/jonno/src/slackbeatz/slackbeatz/engine/lfo_apply.py` |

Direction of borrowing: read these, port the *ideas*, write fresh code. Don't
mechanically port — the data model is different (JSON not DSL, bar-by-bar
not whole-part, voice types not generator types) and a clean implementation
will be shorter than a port.
