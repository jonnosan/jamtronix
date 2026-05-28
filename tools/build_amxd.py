"""Bundle ``JtxParameterRouter.maxpat`` into a ``JtxParameterRouter.amxd``.

The ``.amxd`` format is a chunked binary container:

* 4-byte magic ``ampf``
* 4-byte big-endian length of the rest of the file (excluding the
  magic + this length field)
* One or more chunks, each ``[4-byte FourCC][4-byte BE size][content]``

For a minimum-viable Max for Live device we need two chunks:

* ``meta`` — device-level metadata. The bare minimum is the device
  type (``amxd``) followed by the audio routing category (``audio_effect``
  / ``midi_effect`` / ``instrument``). JTX's router doesn't process
  audio or notes — it just receives OSC and drives Live params — so
  ``midi_effect`` is the closest match (lets Live drop the device on
  any track that accepts MIDI effects, which is every MIDI track).
* ``ptch`` — the patcher JSON itself, optionally gzipped.

This wrap is **best-effort**. The format is reverse-engineered from
inspection of M4L-saved devices; without running it through Max for
Live we can't guarantee Live will accept the result. The fallback is
always: open the ``.maxpat`` in Max for Live → File → Save Device → it
writes a guaranteed-valid ``.amxd``.

Run from repo root:

    python tools/build_amxd.py
"""

from __future__ import annotations

import struct
from pathlib import Path


def _pack_chunk(fourcc: bytes, payload: bytes) -> bytes:
    """Wrap *payload* in a ``[FourCC][BE size][payload]`` chunk."""
    assert len(fourcc) == 4
    return fourcc + struct.pack(">I", len(payload)) + payload


def build_amxd(maxpat_path: Path, out_path: Path) -> None:
    maxpat_bytes = maxpat_path.read_bytes()

    # ``meta`` chunk: null-terminated key=value lines.
    # The exact key set matters less than the device-type / category
    # appearing; experimentally Max for Live tolerates extra entries.
    meta_lines = [
        b"amxd 1",
        b"device_type midi_effect",
        b"device_name JtxParameterRouter",
        b"author Jamtronix",
    ]
    meta_payload = b"\n".join(meta_lines) + b"\n"

    ptch_payload = maxpat_bytes

    body = _pack_chunk(b"meta", meta_payload) + _pack_chunk(b"ptch", ptch_payload)
    body_len = len(body)

    file_bytes = b"ampf" + struct.pack(">I", body_len) + body
    out_path.write_bytes(file_bytes)
    print(f"wrote {out_path} ({len(file_bytes)} bytes; payload {len(maxpat_bytes)} bytes)")


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    maxpat = here / "daw_templates" / "JtxParameterRouter.maxpat"
    amxd = here / "daw_templates" / "JtxParameterRouter.amxd"
    if not maxpat.exists():
        raise SystemExit(f"missing {maxpat}")
    build_amxd(maxpat, amxd)


if __name__ == "__main__":
    main()
