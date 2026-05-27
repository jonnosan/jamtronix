# jamtronix (jtx)

A macOS-only, GUI-only MIDI jam tool for acid and deep techno (with a psytrance
starter template). Loosely modelled on [`slackbeatz`](https://github.com/jonnosan/slackbeatz),
rebuilt around a focused workflow: launch the app, pick or create a song from a
title, fiddle with knobs while it streams MIDI into Ableton (or any DAW).

The same (song, seed) pair always plays the same way.

## Status

Pre-release. See [`docs/SPEC.md`](docs/SPEC.md) for the v1 functional spec and
[the v1 milestone issues](https://github.com/jonnosan/jamtronix/milestones) for
build progress.

## Design highlights

- **MIDI-out only** — jtx never makes sound. It talks to a DAW or hardware via
  CoreMIDI / IAC Bus. Optional offline MIDI file export.
- **PySide6 GUI**, no CLI in v1. Engine factored as a separate library so a
  headless playback CLI can land later with no refactor.
- **Five voice types**: `drum`, `mono`, `poly`, `modulator` (CC-only),
  `follower` (derives from another voice).
- **~10–12 algorithms**, consolidated from slackbeatz's 57 generators.
- **Deterministic PRNG** seeded from song title (SHA-256), with per-(part,
  voice, bar) derivation so every bar is reproducible.
- **Bar-by-bar regeneration**: knob changes (and future external MIDI-in) land
  within ~1 bar.
- **Clock**: internal master, MIDI Clock slave, or Ableton Link.
- **Setup includes a DAW template path** — one button opens the matching
  `.als` (or any) file via macOS `open`.

## Development setup

Requires Python 3.12+ on macOS.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Lint + type-check (both gate pre-push):

```sh
ruff check .
ruff format --check .
mypy jtx
```

Run tests (none yet; the testing posture is minimal pytest + manual
verification via the GUI):

```sh
pytest
```

## Layout

- `jtx/` — engine library. **No Qt imports.** Will hold the data model,
  algorithms, scheduler, sinks, and persistence.
- `jtx_gui/` — PySide6 front end. May import from `jtx`; the reverse is
  forbidden so a future headless CLI can sit on the same engine.
- `templates/` — hardcoded style templates (acid / deep_techno / psytrance)
  used by the new-song wizard.
- `setups/` — bundled starter setups (IAC, Ableton).
- `examples/` — one starter `.jtx` per template.
- `tests/` — smoke + golden-fixture tests.

## Links

- Spec: [`docs/SPEC.md`](docs/SPEC.md)
- Predecessor / reference: [`jonnosan/slackbeatz`](https://github.com/jonnosan/slackbeatz)
