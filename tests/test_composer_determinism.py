"""Same (title, mood, format, chaos) → byte-identical Song JSON."""

from __future__ import annotations

import dataclasses
import json

from jtx.composer import MOOD_ANCHORS, compose


def _song_to_json(song) -> str:
    return json.dumps(dataclasses.asdict(song), sort_keys=True)


def test_compose_is_deterministic() -> None:
    a = compose("Hello", "iac", MOOD_ANCHORS["euphoric"], "song", chaos=0.4)
    b = compose("Hello", "iac", MOOD_ANCHORS["euphoric"], "song", chaos=0.4)
    assert _song_to_json(a) == _song_to_json(b)


def test_different_titles_produce_different_songs() -> None:
    a = compose("Alpha", "iac", MOOD_ANCHORS["euphoric"], "song", chaos=0.0)
    b = compose("Beta", "iac", MOOD_ANCHORS["euphoric"], "song", chaos=0.0)
    assert _song_to_json(a) != _song_to_json(b)


def test_different_chaos_changes_song() -> None:
    a = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    b = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.6)
    assert _song_to_json(a) != _song_to_json(b)


def test_different_format_changes_song() -> None:
    a = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    b = compose("Same", "iac", MOOD_ANCHORS["happy"], "ramp", chaos=0.0)
    assert _song_to_json(a) != _song_to_json(b)


def test_different_mood_changes_song() -> None:
    a = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    b = compose("Same", "iac", MOOD_ANCHORS["brooding"], "song", chaos=0.0)
    assert _song_to_json(a) != _song_to_json(b)


def test_different_texture_changes_song() -> None:
    a = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0, texture=0.2)
    b = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0, texture=0.8)
    assert _song_to_json(a) != _song_to_json(b)


def test_different_motion_changes_song() -> None:
    a = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0, motion=0.1)
    b = compose("Same", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0, motion=0.9)
    assert _song_to_json(a) != _song_to_json(b)
