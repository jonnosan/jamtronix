"""Entry point — ``python -m jtx_gui`` or the ``jtx-gui`` console script.

Bootstraps QApplication, applies the theme, and either opens the song
passed on the CLI or auto-generates a random one using the last-used
setup + clock mode (persisted via QSettings).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jtx_gui import theme
from jtx_gui.main_window import SETTINGS_APP, SETTINGS_ORG, MainWindow
from jtx_gui.state import AppState


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jtx-gui")
    parser.add_argument(
        "song",
        nargs="?",
        type=Path,
        help="Optional .jtx song to open immediately (otherwise a random song is generated).",
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
    else:
        window.bootstrap_random_song()

    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
