"""OverrideField — wraps an editor with an 'override here' checkbox.

Used by the Parts view: every knob, picker, or text field that can be
overridden in a part appears with a checkbox above it. When the box is
clear, the field is disabled and shows the inherited (song-level or
default) value in a dimmed style. When checked, the field is enabled
and edits write into the part's override dict.

The widget owns the override semantics; callers just provide:
- a knob/algorithm/key spec,
- the inherited value (resolved from the song-level config + algorithm
  default),
- a callback for "override on/off" and "override value changed".

This keeps the Parts view free of per-knob plumbing.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from jtx_gui import theme
from jtx_gui.algorithm_meta import KnobSpec
from jtx_gui.widgets.knob import KnobWidget

# A semi-transparent overlay used to dim inherited fields. We can't
# easily disable a child QLineEdit's stylesheet without it looking
# broken, so we tint via opacity instead.
_INHERITED_OPACITY = 0.55
_OVERRIDDEN_OPACITY = 1.0


class OverrideField(QFrame):
    """One knob/picker plus its 'OVERRIDE HERE' checkbox.

    The class is shape-agnostic: float / int / choice / list / string
    knob kinds all flow through here. Editing happens in two callbacks:

    * ``on_override_toggle(enabled: bool, inherited_value)`` — flip the
      override state. The caller decides whether to add or remove the
      key from the override dict, and what seed value to use when
      enabling.
    * ``on_value_change(value)`` — fired when the user edits the field
      while the override is enabled.
    """

    def __init__(
        self,
        *,
        spec: KnobSpec,
        inherited_value: object,
        override_value: object | None,
        on_override_toggle: Callable[[bool, object], None],
        on_value_change: Callable[[object], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OverrideField")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._spec = spec
        self._inherited = inherited_value
        self._on_override_toggle = on_override_toggle
        self._on_value_change = on_value_change

        is_overridden = override_value is not None
        current = override_value if is_overridden else inherited_value

        self._checkbox = QCheckBox("OVERRIDE")
        self._checkbox.setChecked(is_overridden)
        self._checkbox.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; "
            "font-size: 8pt; letter-spacing: 1px; }}"
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._checkbox.toggled.connect(self._on_check_toggled)

        self._editor = self._build_editor(current)
        self._editor.setEnabled(is_overridden)
        self._apply_inherited_style(is_overridden)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._checkbox, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._editor, 0, Qt.AlignmentFlag.AlignHCenter)

    # ----- editor construction --------------------------------------------

    def _build_editor(self, current: object) -> QWidget:
        spec = self._spec
        if spec.kind in {"float", "int"}:
            knob = KnobWidget(
                label=spec.name,
                minimum=float(spec.minimum),
                maximum=float(spec.maximum),
                value=float(current if isinstance(current, int | float) else spec.default),  # type: ignore[arg-type]
                step=max(1.0, float(spec.step)) if spec.kind == "int" else float(spec.step),
                decimals=spec.decimals,
                integer=spec.kind == "int",
            )

            def emit_float(v: float) -> None:
                self._on_value_change(int(v) if spec.kind == "int" else float(v))

            knob.value_changed.connect(emit_float)
            return knob

        if spec.kind == "choice":
            combo = QComboBox()
            combo.addItems(list(spec.choices))
            current_str = str(current)
            if current_str not in spec.choices:
                combo.addItem(current_str)
            combo.setCurrentText(current_str)
            combo.currentTextChanged.connect(self._on_value_change)
            wrap = _label_below(combo, spec.name)
            wrap.setMinimumWidth(110)
            return wrap

        # list_int / list_str / string fallback.
        edit = QLineEdit()
        edit.setText(_format_text_value(current))
        edit.editingFinished.connect(lambda: self._on_value_change(self._parse_text(edit.text())))
        if spec.kind == "list_int":
            edit.setPlaceholderText("comma-separated ints")
        wrap = _label_below(edit, spec.name)
        wrap.setMinimumWidth(140)
        return wrap

    # ----- toggle handling -------------------------------------------------

    def _on_check_toggled(self, checked: bool) -> None:
        self._editor.setEnabled(checked)
        self._apply_inherited_style(checked)
        self._on_override_toggle(checked, self._inherited)

    def _apply_inherited_style(self, overridden: bool) -> None:
        opacity = _OVERRIDDEN_OPACITY if overridden else _INHERITED_OPACITY
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(self._editor)
        effect.setOpacity(opacity)
        self._editor.setGraphicsEffect(effect)
        tip = (
            f"{self._spec.name}: overriding"
            if overridden
            else f"{self._spec.name}: inheriting {_format_text_value(self._inherited)!s}"
        )
        self._editor.setToolTip(tip)
        self._checkbox.setToolTip(tip)

    # ----- value parsing for text fields ----------------------------------

    def _parse_text(self, raw: str) -> object:
        if self._spec.kind == "list_int":
            stripped = raw.strip()
            if not stripped:
                return []
            try:
                return [int(p.strip()) for p in stripped.split(",") if p.strip()]
            except ValueError:
                return self._inherited
        if self._spec.kind == "list_str":
            return [p.strip() for p in raw.split(",") if p.strip()]
        return raw.strip()


def _label_below(widget: QWidget, label: str) -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(widget)
    lbl = QLabel(label.upper())
    lbl.setObjectName("FieldLabel")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl)
    return holder


def _format_text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value)


class OverrideRow(QFrame):
    """Convenience: a horizontal flow row of OverrideField widgets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def add(self, field: QWidget) -> None:
        self._layout.addWidget(field)

    def fill(self) -> None:
        self._layout.addStretch(1)
