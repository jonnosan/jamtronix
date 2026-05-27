"""Sink ABC.

A sink is the egress point for events: realtime MIDI, MIDI file writer,
or in-memory capture for tests. The scheduler dispatches events here
one-at-a-time after waiting for their absolute tick.

Realtime + file sink implementations live in :mod:`jtx.sinks`
(issue #5). This ABC sits in the engine so the scheduler stays
unaware of which concrete sink it's writing to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jtx.engine.events import Event


class Sink(ABC):
    """Event egress."""

    @abstractmethod
    def emit(self, event: Event) -> None:
        """Send one event downstream. Called from the scheduler thread."""

    def start(self) -> None:  # noqa: B027 — intentional default no-op
        """Optional setup hook (open ports, reset file writer, ...)."""

    def stop(self) -> None:  # noqa: B027 — intentional default no-op
        """Optional teardown hook (close ports, flush file, ...)."""


class MemorySink(Sink):
    """Test sink: appends each emitted event to :attr:`events`."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)
