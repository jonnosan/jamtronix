"""OSC client wrapper used by the sink-side parameter router.

A voice with an :class:`OscTarget` in its ``parameter_map`` produces no
MIDI for that function — the
:class:`jtx.engine.parameter_router.ParameterRouter` calls
:meth:`OscClient.send` instead, addressing the configured destination.

Two implementations:

* :class:`OscClient` — wraps ``pythonosc.udp_client.SimpleUDPClient``
  and emits real UDP packets. Construction is cheap (one socket); the
  same instance is reused across the whole song.
* :class:`MemoryOscClient` — test double that just records each
  ``(address, value)`` tuple in :attr:`MemoryOscClient.sent`.

Both implement the :class:`OscClientProtocol` informal interface
(``send`` + ``close``).
"""

from __future__ import annotations

from typing import Any, Protocol


class OscClientProtocol(Protocol):
    """Informal interface for OSC client implementations."""

    def send(self, address: str, value: float) -> None: ...

    def close(self) -> None: ...


class OscClient:
    """Real OSC client backed by ``python-osc`` UDP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11000) -> None:
        # Import locally so projects that don't use OSC don't pay the
        # python-osc import cost at engine startup.
        from pythonosc.udp_client import SimpleUDPClient

        self.host = host
        self.port = int(port)
        self._client: Any = SimpleUDPClient(self.host, self.port)

    def send(self, address: str, value: float) -> None:
        self._client.send_message(address, float(value))

    def close(self) -> None:
        # SimpleUDPClient holds a UDP socket internally; ``python-osc``
        # exposes no explicit close, but the socket is released when
        # the client is garbage-collected. We drop the reference here
        # so subsequent calls fail loudly rather than silently
        # bouncing off a stale socket.
        self._client = None


class MemoryOscClient:
    """Test double — appends sent messages to :attr:`sent`."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, float]] = []
        self._closed = False

    def send(self, address: str, value: float) -> None:
        if self._closed:
            raise RuntimeError("MemoryOscClient already closed")
        self.sent.append((address, float(value)))

    def close(self) -> None:
        self._closed = True
