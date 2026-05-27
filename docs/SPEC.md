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
    GM drums (channel 10).

Songs reference a setup by id; multiple songs can share a setup.

Two bundled starter setups: `IAC Bus 1` (acid/deep-techno default) and `Ableton`
(same routing but with an Ableton `.als` template path empty by default so the
user can fill it in).

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

Five types. The type constrains which roles and which algorithms are valid.

| Type | Roles | What it emits |
|------|-------|---------------|
| `drum` | `drum` | Note-on/off on the kit channel using kit map names |
| `mono` | `bass`, `lead` | One note at a time + optional CC modulation |
| `poly` | `pad`, `stab`, `chord` | Multiple simultaneous notes |
| `modulator` | `modulator` | CCs and PitchBend only — no notes |
| `follower` | `follower` | Notes derived from another voice's output |

**Critical rule** (clarified during scoping): pattern knobs are
**per-algorithm**, not per-role. Only *defaults* vary by role. This means a bass
voice and a lead voice running the same algorithm with the same knob values
produce identical music up to MIDI channel — a useful property for
double-tracking and for `follower` voices' source-of-truth checks.

### Algorithm Library (~10–12 classes)

Consolidated from slackbeatz's 57 generators. Each algorithm declares its
**pattern knob schema** (knob name → type, range, default). Defaults can be
overridden per role.

| Type | Algorithm | Notes / knobs in scope |
|------|-----------|-----------------------|
| drum | `drum_pattern` | Unified euclidean + four-on-floor + breakbeat via knobs (`style=euclid|four_floor|break`, per-piece pulses/offsets, ghost layer, polyrhythm + `polyrhythm_subdiv` for continuous triplet hat, `roll_pos`/`roll_subdiv`/`roll_depth` for triplet roll fills) |
| drum | `drum_one_shot` | Single hits at given steps; useful for claps, crashes, tom rolls (`roll_pos`/`roll_subdiv`/`roll_depth`) |
| mono | `acid_bass` | 303-style step sequencer (probabilistic note picks, octave jumps, slide, internal CC74/CC71 sweep, pitch-bend wobble, optional `triplet_prob` for breakdown rolls) — covers slackbeatz `acid_303` |
| mono | `sub_drone` | Sustained drone, root/fifth alternation, optional progression follow, optional kick-locked filter envelope — covers slackbeatz `subdrone` (deep techno staple) |
| mono | `melodic_line` | Step-sequenced riff with passing tones, configurable `subdivision` (incl. 8t/16t triplet grids) and per-beat `triplet_prob` rolls — covers `rolling`, `gallop`, `mellow_pick`, `rhodes_phrase`, `acid_lead`, `psy_lead` |
| mono | `arp` | Up/down/random/walk arpeggio with `subdivision` (16/8/4/8t/16t/…), octaves, gate, hold — covers `sh101_arp`, `arp_walk` |
| poly | `sustained_chord` | Long-gated chord voicing following the progression — covers `triad_sustain`, `pad_drift`, `sustained_dyad`, `atmos_pad` |
| poly | `chord_stab` | Short-gated voicings on configurable steps — covers `offbeat_stab`, `acid_stab`, `wurli_chop` |
| modulator | `cc_lfo` | Single CC with shape (sine/tri/saw/square/random), rate (bars/beats), depth, phase — direct replacement for `candy` family |
| modulator | `cc_envelope` | Triggered envelope on CC, with attack/decay/sustain/release driven by bar/beat events — for kick-synced filter sweeps |
| follower | `voice_follower` | Single algorithm, fixed pipeline (see Followers below) |

That's 10. Two slots reserved for additions discovered during implementation
(e.g. a dedicated `noise_riser` or a `vocal_chop` that doesn't fit `melodic_line`).

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

### Pattern vs Feel Knobs

- **Pattern knobs**: algorithm-specific. They control *what notes are emitted*.
  Schema declared by the algorithm class. Examples: `acid_bass.slide_prob`,
  `drum_pattern.kick_pulses`, `arp.rate`.
- **Feel knobs**: universal across every voice type. They control *how* notes
  are emitted — micro-timing, dynamics, drop-outs. Applied at the scheduler
  level as a post-emit pass, so every algorithm gets identical feel handling.
  v1 set, mirroring slackbeatz `feel.py`:
  - `humanize` (±N ticks per event, default varies by role),
  - `vel_jitter` (±N velocity per note-on),
  - `gate_jitter` (±fraction of note duration),
  - `swing` (delay every other 16th — 0=straight, 1.0=full 16th-triplet feel),
  - `accent` (velocity boost on configurable beats),
  - `mute_prob` (per-bar drop chance),
  - `evolution` (linear velocity ramp across part),
  - `octave_jump` (per-event ±12 chance),
  - `passing_tones` (chromatic neighbour swap chance).

Same set on every voice; role determines defaults. (Drum role gets higher
`accent` defaults; bass role gets higher `swing` default; etc.)

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
- `period` (bars or beats),
- `phase` (0–1),
- `depth` (0–1).

LFOs are *applied* by binding them to a target in a part. Target scopes:

- `pattern:<voice>:<knob>` — modulates a pattern knob,
- `feel:<voice>:<knob>` — modulates a feel knob,
- `midi:ch<N>:cc<M>` — direct CC output,
- `root:<voice>` — modulates the root note (in semitones or scale degrees).

Applications are part-scoped (you can apply `slow_sweep` in `build` but not in
`drop`). This is strictly more powerful than the modulator voice type
(`cc_lfo`/`cc_envelope`) but coexists with it: modulator voices are the
convenient case (a CC on a channel); LFOs are the general case (modulate any
knob).

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

Shape (sketch):

```json
{
  "schema_version": 1,
  "title": "Phuture",
  "seed_override": null,
  "setup_ref": "iac-default",
  "key": { "tonic": "A", "scale": "minor" },
  "meter": "4/4",
  "tempo": 122,
  "chord_progression": { "degrees": ["i","VI","III","VII"], "bars_per_chord": 4 },
  "voices": {
    "kick":    { "algorithm": "drum_pattern", "pattern": {...}, "feel": {...} },
    "acid":    { "algorithm": "acid_bass",    "pattern": {...}, "feel": {...} },
    "organ":   { "algorithm": "chord_stab",   "pattern": {...}, "feel": {...} }
  },
  "parts": {
    "intro": { "bars": 16, "voice_overrides": { "acid": { "pattern": { "drop_prob": 0.5 } } } },
    "drop":  { "bars": 32, "voice_overrides": {} }
  },
  "arrangement": ["intro", "build", "drop", "build", "drop", "outro"],
  "lfos": [
    { "name": "slow_sweep", "shape": "sine", "period_bars": 8, "depth": 0.6,
      "applications": [ { "part": "build", "target": "midi:ch2:cc74" } ] }
  ]
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
