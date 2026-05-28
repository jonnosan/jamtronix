# Ableton + JTX — setup guide

How to connect jtx to Ableton Live so the **parameter-mapping**
abstraction (cutoff / resonance / glide / bend per voice) survives
swapping instrument patches without re-doing MIDI Learn every time.

This is the **cross-style fundamentals** doc. For per-style recipes
(acid / deep techno / psytrance — which instrument to pick, which
patch to load, what to map each slider to) see the per-style docs
under `docs/templates/` once they land (#105).

## The pieces

* `jtx/` — generates MIDI + OSC to Ableton over IAC bus + UDP.
* `setups/ableton-osc.jtx-setup` — bundled setup that demonstrates
  OSC parameter routing alongside MPE and standard MIDI.
* `daw_templates/JtxParameterRouter.maxpat` — the Max for Live device
  source. Receives `/jtx/<voice>/<function>` OSC messages on port
  11000 and routes them to eight Live-mappable parameter sliders.
* `daw_templates/JtxParameterRouter.amxd` — best-effort wrap of the
  `.maxpat`. **If Ableton refuses to load it**, regenerate from the
  `.maxpat` (one click — see "Building the device" below).
* `daw_templates/JtxParameterRouter.js` — the JS routing scriptlet
  the `.maxpat` references. Must live next to the `.maxpat` (or be
  bundled into the `.amxd` by Max).

## How parameter mapping works in practice

Each jtx voice's `parameter_map` decides what each abstract function
becomes on the wire:

* `CCTarget(74)` → MIDI CC 74 on the voice's channel (the legacy
  path).
* `MPEPitchBendTarget()` → MIDI pitch-bend on the per-note MPE
  channel (poly bend works).
* `MPETimbreTarget()` → MIDI CC 74 on the per-note MPE channel.
* `MPEPressureTarget()` → MIDI channel pressure on the per-note MPE
  channel.
* `OscTarget("/jtx/<voice>/<function>")` → UDP OSC float to the
  setup's `osc_host:osc_port`, ignoring MIDI entirely.

The key win for OSC: the address `/jtx/lead/cutoff` is stable
forever. Swap Wavetable for Drift on the lead track — the
`JtxParameterRouter` device on that track still receives
`/jtx/lead/cutoff`, still drives its `Cutoff` slider. The user only
has to re-do Live's "Map" gesture from the slider to the new
instrument's filter-frequency param. jtx's config doesn't change.

## Building the device

The bundled `.amxd` is a best-effort binary wrap of the `.maxpat`.
If Live loads it cleanly: skip ahead. If Live refuses
("Could not open device" or similar):

1. Open Max for Live (Live → top menu → Help → "Open Max").
2. File → Open → pick `daw_templates/JtxParameterRouter.maxpat`.
3. The patcher opens. Confirm there are no red boxes (red = error).
4. File → Save As Device → save back over
   `daw_templates/JtxParameterRouter.amxd` (or to your User Library's
   Max for Live folder for personal use).

The `.maxpat` is the canonical source — `tools/build_amxd.py` is the
script that produces the bundled `.amxd`. Future edits go through
the `.maxpat`; re-run the script (or re-save from Max) to regenerate
the binary.

## Wiring a track to the device

Drop the device on any track jtx controls (one device per track):

1. Drag `JtxParameterRouter.amxd` from Finder onto an Ableton track.
   (Or place it in your User Library and drag from there.)
2. Set the device's **Voice name** parameter (text field at the top
   of the device) to match the jtx voice's name. E.g. for the
   `lead` voice in `setups/ableton-osc.jtx-setup`, type `lead`.
3. The device has eight Live-mappable parameters: **Cutoff**,
   **Resonance**, **Glide**, **Bend**, **Spare 1..4**.
4. Click Live's **Map** mode (top-right corner of Live's screen).
5. Click the device's **Cutoff** slider, then click the destination
   on the track's instrument (e.g. Wavetable's "Filter Freq"). Live
   shows the mapping; click Map again to exit Map mode.
6. Repeat for Resonance / Glide / Bend.
7. The spare sliders are for forward-compat — the v1 jtx vocabulary
   doesn't drive them. Leave unmapped unless an algorithm grows a
   new function.

## OSC config

Default: jtx sends to `127.0.0.1:11000`. The device listens on the
same port. To change:

* In jtx: Setup editor → General tab → "OSC host : port" row.
* In the device: open the `.maxpat`, change the `udpreceive 11000`
  object's argument to your new port, save.

Most users want to leave it at `127.0.0.1:11000`.

## MPE alongside OSC

OSC and MPE compose. A typical lead voice has:

* `cutoff`, `resonance`, `glide` → `OscTarget` (smooth modulation
  via the M4L device, no MIDI Learn needed).
* `bend` → `MPEPitchBendTarget()` (per-note pitch bend over MIDI to
  the MPE-aware instrument).

This is what `setups/ableton-osc.jtx-setup` demonstrates. The
device only handles OSC — MPE pitch-bend flows over MIDI directly to
the instrument, which must be MPE-aware (Sampler / Wavetable / Drift
/ Meld + the track's MIDI-In set to MPE).

## Ableton Link

jtx also supports Ableton Link as a clock source: Setup editor →
General tab → Clock mode → "Ableton Link". Requires the optional
`LinkPython-extern` dependency:

```
pip install 'jamtronix[link]'
```

When Link is active, jtx tempo follows the Link session; start/stop
participates in the shared transport. No further setup — Link auto-
peers on the local network.
