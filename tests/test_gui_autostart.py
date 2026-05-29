"""Autostart + QSettings persistence for setup id + clock mode."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx_gui.bundles import bundled_setups  # noqa: E402
from jtx_gui.main_window import (  # noqa: E402
    SETTING_LAST_CLOCK_MODE,
    SETTING_LAST_SETUP_ID,
    SETTINGS_APP,
    SETTINGS_ORG,
    MainWindow,
)
from jtx_gui.state import AppState  # noqa: E402
from jtx_gui.transport import TransportService  # noqa: E402
from jtx_gui.views.composer_view import ComposerView  # noqa: E402
from jtx_gui.views.toolbar import TopToolbar  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    # bootstrap_random_song + toolbar/composer persistence read
    # QSettings under the app's org/application — make sure those
    # match production so the tests share the persistence namespace.
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName(SETTINGS_ORG)
    app.setApplicationName(SETTINGS_APP)
    return app


@pytest.fixture(autouse=True)
def _clean_settings(qapp: QApplication) -> Iterator[None]:
    """Wipe persisted Jamtronix QSettings around each test.

    QSettings persists per organization/application, so test ordering
    would otherwise leak setup/clock choices into each other.
    """
    QSettings(SETTINGS_ORG, SETTINGS_APP).clear()
    yield
    QSettings(SETTINGS_ORG, SETTINGS_APP).clear()


def _stem_of_first_bundled_setup() -> str:
    paths = bundled_setups()
    assert paths, "no bundled .jtx-setup files found"
    return paths[0].stem


def _other_setup_stem(exclude: str) -> str | None:
    for path in bundled_setups():
        if path.stem != exclude:
            return path.stem
    return None


def test_bootstrap_random_song_uses_persisted_setup_id(qapp: QApplication) -> None:
    """bootstrap_random_song honours the SETTING_LAST_SETUP_ID written previously."""
    target = _stem_of_first_bundled_setup()
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(SETTING_LAST_SETUP_ID, target)

    state = AppState()
    window = MainWindow(state)
    window.bootstrap_random_song()

    assert state.song is not None
    assert state.setup is not None
    assert state.setup.id == target
    # adopt() leaves no on-disk path and marks the song dirty.
    assert state.path is None
    assert state.dirty is True
    window.deleteLater()


def test_bootstrap_random_song_falls_back_to_default_when_persisted_setup_missing(
    qapp: QApplication,
) -> None:
    """Unknown persisted setup id falls back to the default rather than crashing."""
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(SETTING_LAST_SETUP_ID, "this-does-not-exist")

    state = AppState()
    window = MainWindow(state)
    window.bootstrap_random_song()

    assert state.song is not None
    assert state.setup is not None
    # Default fallback is "ableton" — present in the bundled setups.
    bundle_stems = {p.stem for p in bundled_setups()}
    assert state.setup.id in bundle_stems
    assert state.setup.id == "ableton"
    window.deleteLater()


def test_bootstrap_random_song_applies_persisted_clock_mode(qapp: QApplication) -> None:
    """The toolbar's clock mode reflects SETTING_LAST_CLOCK_MODE after bootstrap."""
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(SETTING_LAST_CLOCK_MODE, "ableton_link")

    state = AppState()
    window = MainWindow(state)
    window.bootstrap_random_song()

    assert window._toolbar.clock_mode == "ableton_link"  # type: ignore[attr-defined]
    window.deleteLater()


def test_bootstrap_random_song_defaults_clock_mode_when_unset(qapp: QApplication) -> None:
    """With no persisted clock mode, the toolbar settles on internal_master."""
    state = AppState()
    window = MainWindow(state)
    window.bootstrap_random_song()

    assert window._toolbar.clock_mode == "internal_master"  # type: ignore[attr-defined]
    window.deleteLater()


def test_toolbar_clock_mode_persists_across_instances(qapp: QApplication) -> None:
    """A clock-mode change on one toolbar is visible to a freshly-constructed one."""
    state = AppState()
    transport = TransportService()
    first = TopToolbar(state=state, transport=transport, port_factory=lambda: [])
    first.set_clock_mode("ableton_link")
    first.deleteLater()

    state2 = AppState()
    transport2 = TransportService()
    second = TopToolbar(state=state2, transport=transport2, port_factory=lambda: [])
    assert second.clock_mode == "ableton_link"
    second.deleteLater()


def test_setup_combo_persists_id_on_change(qapp: QApplication) -> None:
    """Switching setup_combo writes SETTING_LAST_SETUP_ID to QSettings."""
    bundles = bundled_setups()
    if len(bundles) < 2:
        pytest.skip("need at least two bundled setups to exercise a combo change")

    state = AppState()
    view = ComposerView(state)
    # Pick a stem different from whatever the combo lands on by default.
    current = view._setup_combo.currentText()  # type: ignore[attr-defined]
    alternate = _other_setup_stem(current)
    assert alternate is not None

    target_idx = view._setup_combo.findText(alternate)  # type: ignore[attr-defined]
    assert target_idx >= 0
    view._setup_combo.setCurrentIndex(target_idx)  # type: ignore[attr-defined]

    persisted = QSettings(SETTINGS_ORG, SETTINGS_APP).value(SETTING_LAST_SETUP_ID, "", type=str)
    assert persisted == alternate
    view.deleteLater()


def test_main_module_does_not_import_splash(qapp: QApplication) -> None:
    """The splash dialog flow is gone — the entry point shouldn't reference it."""
    main_module_src = Path(__file__).resolve().parent.parent / "jtx_gui" / "__main__.py"
    text = main_module_src.read_text(encoding="utf-8")
    assert "SplashDialog" not in text
    assert "splash" not in text.lower()
