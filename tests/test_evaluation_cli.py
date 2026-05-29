"""Smoke tests for ``python -m jtx.evaluation sweep`` CSV output.

Keeps the CLI surface contract — column order, summary rows — pinned
so dashboards / spreadsheets can rely on parseable shape.
"""

from __future__ import annotations

import csv
import io

import pytest

from jtx.evaluation.__main__ import main


def _run_capture(monkeypatch, *argv: str) -> str:
    """Run main() with stdout redirected; return captured stdout."""
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = main(list(argv))
    assert rc == 0
    return buf.getvalue()


def test_sweep_cli_emits_header_and_summary(monkeypatch) -> None:
    out = _run_capture(monkeypatch, "sweep", "--axis", "motion", "--steps", "3")
    rows = list(csv.reader(io.StringIO(out)))
    # Header + 3 step rows + blank + #slope + #r2.
    assert len(rows) == 7
    header = rows[0]
    assert header[0] == "axis_value"
    assert "filter.cutoff_var" in header
    for r in rows[1:4]:
        assert len(r) == len(header)
        float(r[0])  # axis_value parseable
    assert rows[4] == []
    assert rows[5][0] == "#slope"
    assert rows[6][0] == "#r2"


def test_sweep_cli_to_file(tmp_path, monkeypatch) -> None:
    out = tmp_path / "sweep.csv"
    rc = main(["sweep", "--axis", "texture", "--steps", "3", "--out", str(out)])
    assert rc == 0
    rows = list(csv.reader(out.open()))
    assert len(rows) == 7
    assert rows[0][0] == "axis_value"


def test_sweep_cli_rejects_bad_axis() -> None:
    with pytest.raises(SystemExit):
        main(["sweep", "--axis", "color", "--steps", "3"])
