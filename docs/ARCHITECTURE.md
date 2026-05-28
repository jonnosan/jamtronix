# Jamtronix Architecture

This doc is the **how-it-works overview** — the picture you'd want
before diving into any module. For the **what-it-stores** spec (knob
meanings, persisted JSON shapes, voice types, schema versions), see
[`SPEC.md`](SPEC.md).

## What jamtronix is

A macOS GUI MIDI jam tool for acid + deep techno (and similar
electronic styles). One `.jtx` file is a **song** — a recipe for
generating MIDI bar-by-bar. The user lets a song play and tweaks knobs
in real time; jamtronix produces the next bar inside the current bar's
playback window. Stop the transport and the recipe stays — no recorded
audio, no frozen sequence.

The bet: instead of a giant fixed MIDI sequence, store the **algorithms
+ knobs + LFOs** that *would* produce the music, and run them as
needed. This makes "tweak the bass cutoff" and "swap the chord
progression" lightweight operations rather than re-recordings.

## The bar pipeline

A song's voices each run an **algorithm** every bar. The algorithms
emit **abstract events**; a chain of passes shapes them; the final
voicing + routing stages translate to MIDI on the wire. Per-bar
pipeline:

```
algorithm        →   abstract events (Hit / Note / Param / PolyAftertouch)
  │
  ▼
mix pass         →   per-voice velocity shaping (sidechain, fade, evolution)
  │                  matches Hit.instrument; never touches MIDI plumbing
  ▼
feel pass        →   global feel knobs (Groove, Drive, Wander) shape ticks
  │                  + velocities; Pump + Tension are handled elsewhere
  ▼
voicing stage    →   abstract events → MIDI (NoteOn/NoteOff, CC, PitchBend)
  │                  using the voice slot's kit_map / note / midi_channel
  ▼
parameter router →   function-tagged events get final routing via
  │                  slot.parameter_map (MPE channel allocation, OSC
  │                  dispatch, CC number override)
  ▼
sink             →   MIDI out (CoreMIDI / file / memory for tests)
```

This is the **most architecturally load-bearing diagram in the repo**.
A few invariants follow from it:

* **Algorithms are MIDI-naive.** No `NoteOn(channel=…, note=…)` or
  `ControlChange(cc=…)` construction anywhere in `jtx/algorithms/`.
  Drum-style hits emit `Hit(instrument="kick", …)`; pitched notes
  emit `Note(pitch=…, …)`; CCs and pitch bends emit
  `Param(name="cutoff", value=…, …)` with a semantic function name.
  See [`feedback_algorithms_midi_naive`](../../.claude/memory/) for
  the rationale.

* **Mix and feel work on the same shape algorithms emit.** Both
  operate on abstract events — they don't need to round-trip through
  MIDI to know whether a particular Hit is a kick.

* **The voicing stage is the only place that knows about MIDI
  channels + notes.** That's where `slot.kit_map` is consulted, where
  `slot.midi_channel` gets attached, where `slot.note` resolves a
  single-piece drum hit.

* **The parameter router is the only place that knows about CC
  numbers and OSC addresses.** Function names like `"cutoff"` get
  resolved via `slot.parameter_map["cutoff"]` (or the algorithm's
  `DEFAULT_PARAM_MAP["cutoff"]` fallback) to a `CCTarget(74)` /
  `MPEPitchBendTarget()` / `OscTarget("/jtx/lead/cutoff")` / etc.

## Abstract events

Defined in [`jtx/model/events.py`](../jtx/model/events.py). Four
kinds:

| Event | What it represents | Carries |
|---|---|---|
| `Hit` | A drum-piece hit | `instrument`, `velocity`, `duration_ticks`, `tick` |
| `Note` | A pitched note | `pitch`, `velocity`, `duration_ticks`, `tick` |
| `Param` | A parameter set (CC-style or pitch-bend-style) | `name`, `value` (normalised), `tick` |
| `PolyAftertouch` | Per-note expressive pressure (MPE) | `pitch`, `pressure`, `tick` |

`Hit.instrument` is the routing key for both **voicing** (which
piece's `(channel, note)` does this hit land on?) and **mix-pass
sidechain** (does this hit trigger ducking on a voice whose
`sidechain_from` includes this instrument name?).

`Param.name` is the routing key for **parameter routing**. The
[Parameter Mapping](#parameter-mapping) abstraction (issue #99)
underpins this — algorithms emit by semantic name, slots map names to
concrete targets. **Never bake the CC number into the function name**
(see [`feedback_modulator_function_names`](../../.claude/memory/)).

## Voicing stage

[`jtx/engine/voicing.py`](../jtx/engine/voicing.py).

For each voice's abstract event stream:

* **Hit** on a `drum_kit` slot → lookup `slot.kit_map[instrument]` to
  get a `KitPiece(note, channel)`; emit NoteOn + NoteOff at that
  `(channel, note)`.
* **Hit** on a `drum` slot (or any other non-kit slot) → emit at
  `(slot.midi_channel, slot.note)`. The Hit's `instrument` is
  typically the voice's own name (threaded through by
  `SongPlayer.instantiate_algorithm`), so it matches the slot's name.
* **Note** → emit NoteOn + NoteOff at `slot.midi_channel`, using
  `Note.pitch` directly.
* **Param** → emit `ControlChange(function=name)` with placeholder
  `cc=0`, or `PitchBend(function="bend")` for bend-style params. The
  parameter router downstream fills in the actual CC number / target.
* **PolyAftertouch** → emit `ChannelPressure(function="aftertouch")`.
  The router rebinds onto the MPE per-note channel for MPE voices.

## Parameter Mapping

[`jtx/engine/parameter_router.py`](../jtx/engine/parameter_router.py).

Per voice, the router routes function-tagged events through:

1. `voice_slot.parameter_map[function]` — per-voice explicit override.
2. `algorithm.DEFAULT_PARAM_MAP[function]` — algorithm-level fallback.
3. None → event passes through unchanged.

The four target kinds are `CCTarget(cc)`, `MPEPitchBendTarget()`,
`MPEPressureTarget()`, `MPETimbreTarget()`, `OscTarget(address)`.

For MPE voices, the router also handles per-note channel allocation
from the MPE block + steal-oldest when full + lead-window binding (so
`acid_bass`'s pre-bend at `NoteOn.tick - 1` lands on the right
channel). See `LEAD_WINDOW_TICKS` and `_route_tagged` for the details.

## Mix pass

[`jtx/engine/mix.py`](../jtx/engine/mix.py).

Operates on abstract events. Three knob families:

* **Sidechain** (`sidechain_from`, `sidechain_floor`,
  `sidechain_release_beats`). Triggers come from any voice's Hit
  events whose `.instrument` is in the configured sources. Velocity
  scales between raw and floor based on `(this_event.tick -
  trigger.tick) / release_ticks`. Negative-tick anchoring handles
  triggers from the previous bar.

* **Fade envelope** (`fade_in_at_bar`, `fade_in_beats`, `fade_shape`,
  `fade_sustain_level`, `fade_out_at_bar`, `fade_out_beats`,
  `fade_min_velocity`). Velocity gets scaled by a ramp; events below
  `fade_min_velocity` are dropped entirely.

* **Evolution** (`evolution_start`, `evolution_end`). Linear velocity
  multiplier ramped across the part's bars.

All three scale `Hit.velocity` and `Note.velocity` uniformly. Param +
PolyAftertouch pass through.

## Feel pass

[`jtx/engine/feel.py`](../jtx/engine/feel.py).

Translates four song-wide feel knobs into per-event shaping:

| Knob | Effect | Gating |
|---|---|---|
| **Groove** | Swing (delay odd 16ths), humanize (±ticks jitter), accent (vel boost on beats 2 & 4) | Swing only fires on Hit events whose `instrument` is a hat name (chh/hh/ohh/hat/…) or on Note events from `lead`/`stab`/`chord` role voices |
| **Drive** | Velocity boost on every Hit + Note **and** +`drive*0.2` cutoff push on every `Param(name="cutoff")` | All voices |
| **Wander** | Per-bar mute probability + per-Note octave-jump probability (Hits never octave-jump) | Octave jump only on melodic-role voices (`bass`/`lead`/`pad`/`stab`/`chord`) |

**Pump** (sidechain compilation) lives in
[`jtx/engine/global_feel.py`](../jtx/engine/global_feel.py), running
between LFOs and the mix pass — it synthesises
`sidechain_from=["kick"]` on every non-kit voice when `Song.feel.pump > 0`.

**Tension** is applied directly in `SongPlayer.events_for_bar` — it
reshapes the part-intensity envelope before passing into
`BarContext.part_intensity`.

## LFOs

[`jtx/engine/lfo.py`](../jtx/engine/lfo.py) +
[`jtx/model/lfo.py`](../jtx/model/lfo.py).

Song-level LFOs are named time-varying sources bound to a **target**
inside a **part**. Target grammar:

| Target | Effect |
|---|---|
| `pattern:<voice>:<knob>` | Overwrite a pattern knob in that voice's `BarContext.pattern_knobs` |
| `mix:<voice>:<knob>` | Overwrite a per-voice mix knob |
| `global_feel:<knob>` | Overwrite a song-wide feel knob (broadcast to all voices) |
| `voice:<voice>:<function>` | Emit `Param(name=function, …)` into the named voice's stream — routed via that slot's `parameter_map` |
| `midi:ch<N>:cc<M>` | Emit a raw CC event |
| `root:<voice>` | Move the voice's `chord_root_semitones` |

**Sub-bar sampling.** Event-emitting targets (`midi:` and `voice:`)
sample `lfo.samples_per_bar` times across the bar for smooth sweeps.
Knob-writing targets (`pattern:` / `mix:` / `global_feel:` / `root:`)
always sample once at tick 0 — they back read-once knob dicts.

**Phantom voices.** Setup slots that exist but have no song-level
`VoiceConfig` (e.g. a "filter" modulator slot driven entirely by an
LFO) act as routing destinations. SongPlayer builds a
`ParameterRouter` per phantom slot; LFO `voice:` emissions targeting
phantom slots route through their `parameter_map`.

## Module map

```
jtx/                          engine code (no UI)
├── algorithms/               one algorithm per file — emit abstract events
│   ├── drum_kit.py           headline multi-piece drum algorithm
│   ├── drum_pattern.py       single-piece drum (euclid / four-on-floor / break)
│   ├── drum_one_shot.py      one-shot drum hits
│   ├── acid_bass.py          303-style step sequencer
│   ├── sub_drone.py          held sub-bass
│   ├── reese_bass.py         detuned modulating bass
│   ├── melodic_line.py       scale-walk lead/bass
│   ├── motif_phrase.py       A-A'-A-B structured lead
│   ├── arp.py                chord-tone arpeggiator
│   ├── chord_stab.py         (in sustained_chord.py) short-gated chord
│   ├── sustained_chord.py    long-gated chord voicing
│   ├── noise_riser.py        crescendo voice
│   ├── cc_envelope.py        triggered envelope modulator
│   ├── step_cc.py            step-sequenced parameter modulator
│   ├── voice_follower.py     derives from another voice (latch/transpose/chord/quantize)
│   ├── reference.py          root_pulse — chord-root reference click
│   ├── _euclid.py            shared euclid distribution helper
│   ├── _theory.py            scale + tonic → MIDI pitch utilities
│   └── _palettes.py …        algorithm-internal helpers
│
├── engine/                   the pipeline + supporting layers
│   ├── algorithm.py          base Algorithm class + DEFAULT_PARAM_MAP convention
│   ├── context.py            BarContext — what each algorithm sees
│   ├── voicing.py            abstract events → MIDI
│   ├── mix.py                sidechain / fade / evolution (abstract events)
│   ├── feel.py               Groove / Drive / Wander (abstract events)
│   ├── global_feel.py        compile Song.feel.pump → sidechain knobs
│   ├── lfo.py                sampler + target parser + applier
│   ├── parameter_router.py   per-voice function-tagged event routing + MPE allocation
│   ├── meter.py              tick math
│   ├── scheduler.py          tick → wall-clock dispatch (with bar look-ahead)
│   ├── sink.py               MIDI output (CoreMIDI / file / memory)
│   ├── clock_source.py       internal / MIDI-clock-slave / Ableton-Link
│   ├── root_provider.py      chord progression → per-bar chord root
│   └── osc_client.py         python-osc wrapper for OscTarget routing
│
├── model/                    pure data classes (no engine logic)
│   ├── events.py             Hit / Note / Param / PolyAftertouch (abstract)
│   ├── song.py               Song / Part / VoiceConfig / Key / ChordProgression
│   ├── setup.py              Setup / VoiceSlot / KitPiece
│   ├── lfo.py                LFO / LFOApplication
│   ├── parameter_target.py   ParameterTarget sum type (CC / MPE / OSC)
│   ├── types.py              VoiceType / Role / SCHEMA_VERSION literals
│   └── validate.py           cross-reference validation (follower cycles, etc.)
│
├── persist/                  on-disk JSON round-trip
│   └── json_io.py            load_song / save_song / load_setup / save_setup
│
├── player.py                 SongPlayer — orchestrates the bar pipeline
└── seed.py                   deterministic seed derivation

jtx_gui/                      PySide6 GUI (separate package)
├── widgets/                  knob / collapsible / etc. — reusable controls
├── views/                    song_view / parts_view / setup_editor — top-level panes
├── algorithm_meta.py         knob schemas for the UI to render
├── state.py                  AppState — song / setup loading + dirty tracking
└── bundles.py                discover bundled setups

templates/                    Python modules that BUILD a Song from scratch
├── acid.py / deep_techno.py / psytrance.py — curated style templates
├── wildcard.py — chaotic randomised template
└── blank.py — minimum-viable starting point

setups/                       bundled .jtx-setup files (ableton, iac, etc.)
examples/                     bundled .jtx + .jtx-setup pairs (acid-starter, etc.)
docs/                         this directory
tools/                        CLI utilities (jtx_player, build_amxd, iac_smoke)
daw_templates/                Max-for-Live device (JtxParameterRouter)
tests/                        pytest suite (~470 tests)
```

## Determinism + reproducibility

Every musical decision flows through a deterministic seed chain rooted
at the song's title (or `Song.seed_override`).

```
song_seed   = derive_from_title(title)
              ├── derive_part_voice_seed(song_seed, part, voice)
              │     └── derive_bar_seed(part_voice_seed, bar_index)
              │           └── ctx.rng  (per-(song, part, voice, bar))
              ├── derive_bar_seed(song_seed, bar_index)
              │     └── LFO RNG  (per-(song, bar))
              └── …
```

Every algorithm uses `ctx.rng` (and optionally `ctx.rng_loop` /
`ctx.rng_hold` for cycling RNG streams). Same song + same bar = same
MIDI output across runs. Tests rely on this hard.

## Bar-by-bar regeneration (the architectural commitment)

The scheduler always pulls one bar ahead. Knob tweaks during playback
land within ~1 bar. There is no "render the whole part up front" path;
no MIDI sequence is ever frozen. This is what makes the song format a
*recipe* rather than a *recording*.

Consequence: every algorithm must implement
`generate_bar(ctx: BarContext) -> list[AbstractEvent]` and be
stateless across bars (except for the optional `ctx.rng_hold` /
`ctx.source_events` for follower voices). No bar can reach back into
the previous bar's output — the SongPlayer caches that explicitly via
`prev_voice_events` for cross-bar sidechain lookback and follower
shift-by-1-bar.

## Architectural rules (what to defend)

1. **Algorithms must be MIDI-naive** — see
   [`feedback_algorithms_midi_naive`](../../.claude/memory/).
2. **Modulators emit Param by semantic function name** — never bake
   CC numbers into the name; see
   [`feedback_modulator_function_names`](../../.claude/memory/).
3. **Cross-voice references use instrument / function names** —
   sidechain by `Hit.instrument`, LFOs by `voice:<v>:<function>`,
   never by `(channel, note)`.
4. **Voicing + parameter routing are the only MIDI-aware layers**.
   If you find yourself reaching for `slot.midi_channel` outside
   those two modules, reconsider.
5. **Bar-by-bar regeneration is the only mode**. Don't add APIs that
   require rendering a whole part / song up front.

## Where to look next

* **Knob meanings, JSON shapes, voice types**: [`SPEC.md`](SPEC.md)
* **Ableton-side setup recipes**: [`ABLETON_SETUP.md`](ABLETON_SETUP.md)
* **How to wire MPE / OSC**: `SPEC.md` §Parameter Mapping +
  `daw_templates/JtxParameterRouter.amxd`
* **A new algorithm**: copy `jtx/algorithms/melodic_line.py` (a good
  reference for the `generate_bar` shape + Note/Param emission).
* **Adding an LFO target kind**: `jtx/engine/lfo.py` —
  `parse_target` + `apply_lfos_to_bar`.
