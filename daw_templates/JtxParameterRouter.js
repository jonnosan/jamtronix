// JtxParameterRouter.js — OSC dispatch for the JTX M4L parameter router.
//
// Loaded by the ``js`` object inside ``JtxParameterRouter.maxpat``. Receives
// OSC messages forwarded by ``udpreceive 11000`` and routes them to one of
// eight parameter outlets based on a JTX function name, scoped to a
// per-instance voice name set by the user via the device's "Voice name"
// parameter.
//
// Outlet layout (set in maxpat with ``outlets = 9``; outlet 0 reserved
// for debug/status messages):
//
//   0  status  — last-received address + value (for the device's banner)
//   1  cutoff
//   2  resonance
//   3  glide
//   4  bend
//   5  spare1
//   6  spare2
//   7  spare3
//   8  spare4

inlets = 1;
outlets = 9;

// Function-name → outlet index. Anything else is dropped (but the
// status message is still emitted so the user sees raw traffic).
var FUNCTION_OUTLETS = {
    "cutoff": 1,
    "resonance": 2,
    "glide": 3,
    "bend": 4,
    "spare1": 5,
    "spare2": 6,
    "spare3": 7,
    "spare4": 8
};

// Per-instance voice binding, settable via the "voice" message:
//   ["voice", "lead"]
//
// The local Max patcher wires the ``voice_name`` live.text param's
// output through a ``prepend voice`` so any edit propagates here.
var voice_name = "lead";

function voice(name) {
    voice_name = String(name);
}

// OSC messages arrive as a list. ``udpreceive`` outputs them as
// `[<address>, <value>]`. We accept the address as the message
// selector (Max routes ``/jtx/...`` style addresses by treating the
// leading slash + first segment as the selector). Wire-up uses an
// ``OSC-route /jtx`` upstream so by the time we see the message the
// `/jtx` prefix has been stripped.
function anything() {
    var address = messagename;
    var args = arrayfromargs(arguments);
    var value = args.length > 0 ? args[0] : 0.0;

    // Status outlet always fires so the user can see traffic.
    outlet(0, address, value);

    // Address shape after /jtx-route is "/<voice>/<function>" — strip
    // the leading slash and split on "/".
    var parts = address.replace(/^\//, "").split("/");
    if (parts.length < 2) return;

    var msg_voice = parts[0];
    var msg_func = parts[1];

    if (msg_voice !== voice_name) return;
    if (!Object.prototype.hasOwnProperty.call(FUNCTION_OUTLETS, msg_func)) return;

    outlet(FUNCTION_OUTLETS[msg_func], value);
}
