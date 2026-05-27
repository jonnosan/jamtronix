"""Entry point — ``python -m jtx_gui`` or the ``jtx-gui`` console script.

Bootstraps QApplication, applies the theme, shows the splash dialog,
and either launches the main window with an opened song or exits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jtx_gui import theme
from jtx_gui.main_window import SETTINGS_APP, SETTINGS_ORG, MainWindow
from jtx_gui.state import AppState
from jtx_gui.views.splash import SplashDialog


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jtx-gui")
    parser.add_argument(
        "song",
        nargs="?",
        type=Path,
        help="Optional .jtx song to open immediately (skips the splash dialog).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(SETTINGS_APP)
    app.setOrganizationName(SETTINGS_ORG)
    theme.apply(app)

    state = AppState()
    window = MainWindow(state)

    if args.song is not None:
        if not window.open_song(args.song):
            return 1
        window.show()
        return app.exec()

    # Splash flow.
    splash = SplashDialog(parent=window)
    if splash.exec() != SplashDialog.DialogCode.Accepted:
        return 0

    choice = splash.picked()
    if choice == SplashDialog.RESULT_OPEN:
        if not window.open_song_dialog():
            # User cancelled the file dialog — show the window with
            # an empty workspace; they can still open from the menu.
            pass
    # RESULT_NEW path: button is disabled in #17, so we never get here
    # from the splash itself. (When #20 lands this becomes a wizard.)

    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
