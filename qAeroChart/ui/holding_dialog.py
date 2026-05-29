# -*- coding: utf-8 -*-
"""
HoldingDialog — non-blocking dialog for creating nominal holding patterns (issue #94).

Workflow:
  1. User clicks "Pick on map"  → HoldingFixTool activates; dialog stays visible.
  2. User clicks the fix point  → coordinates appear in the dialog.
  3. User fills in parameters   → live preview shows TAS / radius / leg.
  4. User clicks "Create"       → holding is added to the 'Holding Nominal' layer.
  The dialog stays open so multiple holdings can be created.
"""
from __future__ import annotations

try:
    from qgis.PyQt import QtWidgets
except ImportError:
    try:
        from PyQt6 import QtWidgets  # type: ignore
    except ImportError:
        from PyQt5 import QtWidgets  # type: ignore

from ..utils.logger import log
from ..utils.qt_compat import Qt, QMessageBox
from ..core.holding import HoldingParameters, build_holding
from ..core.holding_layer_manager import HoldingLayerManager


class HoldingDialog(QtWidgets.QDialog):
    """Non-modal dialog for nominal holding pattern creation."""

    def __init__(self, iface=None, parent=None) -> None:
        super().__init__(parent)
        self.iface = iface
        self._fix_x: float | None = None
        self._fix_y: float | None = None
        self._tool = None
        self._layer_manager = HoldingLayerManager()

        self.setWindowTitle("Nominal Holding")
        self.setWindowModality(Qt.NonModal)
        self.resize(440, 360)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QtWidgets.QLabel("Nominal Holding Pattern")
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        root.addWidget(title)

        # ── Fix point ────────────────────────────────────────────────
        fix_grp = QtWidgets.QGroupBox("Fix point")
        fix_lay = QtWidgets.QHBoxLayout(fix_grp)
        self.btn_pick = QtWidgets.QPushButton("Pick on map")
        self.btn_pick.setCheckable(True)
        self.btn_pick.setToolTip("Click to activate the map-pick tool, then click the fix on the canvas")
        self.lbl_x = QtWidgets.QLabel("X: —")
        self.lbl_y = QtWidgets.QLabel("Y: —")
        fix_lay.addWidget(self.btn_pick)
        fix_lay.addSpacing(12)
        fix_lay.addWidget(self.lbl_x)
        fix_lay.addWidget(self.lbl_y)
        fix_lay.addStretch()
        root.addWidget(fix_grp)

        # ── Parameters ───────────────────────────────────────────────
        params_grp = QtWidgets.QGroupBox("Parameters")
        grid = QtWidgets.QGridLayout(params_grp)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # Row 0: inbound track + turn direction
        grid.addWidget(QtWidgets.QLabel("Inbound track"), 0, 0)
        self.spin_track = QtWidgets.QDoubleSpinBox()
        self.spin_track.setRange(0.0, 360.0)
        self.spin_track.setValue(180.0)
        self.spin_track.setSuffix(" °")
        self.spin_track.setDecimals(1)
        grid.addWidget(self.spin_track, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Turn"), 0, 2)
        turn_w = QtWidgets.QWidget()
        turn_lay = QtWidgets.QHBoxLayout(turn_w)
        turn_lay.setContentsMargins(0, 0, 0, 0)
        self.radio_r = QtWidgets.QRadioButton("R")
        self.radio_l = QtWidgets.QRadioButton("L")
        self.radio_r.setChecked(True)
        turn_lay.addWidget(self.radio_r)
        turn_lay.addWidget(self.radio_l)
        grid.addWidget(turn_w, 0, 3)

        # Row 1: IAS + altitude
        grid.addWidget(QtWidgets.QLabel("IAS"), 1, 0)
        self.spin_ias = QtWidgets.QDoubleSpinBox()
        self.spin_ias.setRange(50.0, 600.0)
        self.spin_ias.setValue(195.0)
        self.spin_ias.setSuffix(" kt")
        grid.addWidget(self.spin_ias, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Altitude"), 1, 2)
        self.spin_alt = QtWidgets.QDoubleSpinBox()
        self.spin_alt.setRange(0.0, 50000.0)
        self.spin_alt.setValue(10000.0)
        self.spin_alt.setSuffix(" ft")
        self.spin_alt.setSingleStep(500.0)
        grid.addWidget(self.spin_alt, 1, 3)

        # Row 2: ISA var + bank
        grid.addWidget(QtWidgets.QLabel("ISA var"), 2, 0)
        self.spin_isa = QtWidgets.QDoubleSpinBox()
        self.spin_isa.setRange(-50.0, 50.0)
        self.spin_isa.setValue(0.0)
        self.spin_isa.setSuffix(" °C")
        grid.addWidget(self.spin_isa, 2, 1)

        grid.addWidget(QtWidgets.QLabel("Bank"), 2, 2)
        self.spin_bank = QtWidgets.QDoubleSpinBox()
        self.spin_bank.setRange(5.0, 45.0)
        self.spin_bank.setValue(25.0)
        self.spin_bank.setSuffix(" °")
        grid.addWidget(self.spin_bank, 2, 3)

        # Row 3: leg time
        grid.addWidget(QtWidgets.QLabel("Leg time"), 3, 0)
        self.spin_leg = QtWidgets.QDoubleSpinBox()
        self.spin_leg.setRange(0.5, 4.0)
        self.spin_leg.setSingleStep(0.5)
        self.spin_leg.setValue(1.0)
        self.spin_leg.setSuffix(" min")
        self.spin_leg.setDecimals(1)
        grid.addWidget(self.spin_leg, 3, 1)

        root.addWidget(params_grp)

        # ── Computed values preview ───────────────────────────────────
        prev_grp = QtWidgets.QGroupBox("Computed values")
        prev_lay = QtWidgets.QHBoxLayout(prev_grp)
        self.lbl_tas = QtWidgets.QLabel("TAS: —")
        self.lbl_radius = QtWidgets.QLabel("Radius: —")
        self.lbl_leg_nm = QtWidgets.QLabel("Leg: —")
        for lbl in (self.lbl_tas, self.lbl_radius, self.lbl_leg_nm):
            prev_lay.addWidget(lbl)
        root.addWidget(prev_grp)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.close)
        self.btn_create = QtWidgets.QPushButton("Create Holding")
        self.btn_create.setStyleSheet(
            "background-color: #CC00CC; color: white; font-weight: bold; padding: 4px 12px;"
        )
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addWidget(self.btn_create)
        root.addLayout(btn_row)

        # ── Signal connections ────────────────────────────────────────
        self.btn_pick.clicked.connect(self._toggle_pick_tool)
        self.btn_create.clicked.connect(self._create_holding)
        self.radio_r.toggled.connect(self._update_preview)
        for w in (self.spin_track, self.spin_ias, self.spin_alt,
                  self.spin_isa, self.spin_bank, self.spin_leg):
            w.valueChanged.connect(self._update_preview)

        self._update_preview()

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        try:
            r = build_holding(self._make_params(fix_x=0.0, fix_y=0.0))
            self.lbl_tas.setText(f"TAS: {r.tas_kt:.1f} kt")
            self.lbl_radius.setText(f"Radius: {r.radius_nm:.3f} NM")
            self.lbl_leg_nm.setText(f"Leg: {r.leg_nm:.2f} NM")
        except Exception as exc:
            log(f"Holding preview failed: {exc}", "WARNING")

    # ------------------------------------------------------------------
    # Map-tool interaction
    # ------------------------------------------------------------------

    def _toggle_pick_tool(self, checked: bool) -> None:
        if not self.iface:
            return
        if checked:
            from ..tools.holding_point_tool import HoldingFixTool
            canvas = self.iface.mapCanvas()
            self._tool = HoldingFixTool(canvas)
            self._tool.fixSelected.connect(self._on_fix_selected)
            self._tool.deactivated.connect(self._on_tool_deactivated)
            canvas.setMapTool(self._tool)
            self.btn_pick.setText("Cancel pick")
        else:
            self._cancel_pick()

    def _cancel_pick(self) -> None:
        if self._tool and self.iface:
            try:
                self.iface.mapCanvas().unsetMapTool(self._tool)
            except Exception:
                pass
            try:
                self._tool.clear()
            except Exception:
                pass
        self._tool = None
        self.btn_pick.setText("Pick on map")
        self.btn_pick.setChecked(False)

    def _on_fix_selected(self, pt) -> None:
        self._fix_x = pt.x()
        self._fix_y = pt.y()
        self.lbl_x.setText(f"X: {pt.x():.2f}")
        self.lbl_y.setText(f"Y: {pt.y():.2f}")
        self._cancel_pick()
        self.raise_()
        self.activateWindow()

    def _on_tool_deactivated(self) -> None:
        self.btn_pick.setText("Pick on map")
        self.btn_pick.setChecked(False)
        self._tool = None

    # ------------------------------------------------------------------
    # Create holding
    # ------------------------------------------------------------------

    def _make_params(self, fix_x: float, fix_y: float) -> HoldingParameters:
        return HoldingParameters(
            fix_x=fix_x,
            fix_y=fix_y,
            inbound_track=self.spin_track.value(),
            turn='L' if self.radio_l.isChecked() else 'R',
            ias_kt=self.spin_ias.value(),
            altitude_ft=self.spin_alt.value(),
            isa_var=self.spin_isa.value(),
            bank_deg=self.spin_bank.value(),
            leg_min=self.spin_leg.value(),
        )

    def _create_holding(self) -> None:
        if self._fix_x is None or self._fix_y is None:
            QtWidgets.QMessageBox.warning(
                self, "No fix point", "Pick a fix point on the map first."
            )
            return

        params = self._make_params(self._fix_x, self._fix_y)
        try:
            result = build_holding(params)
            layer = self._layer_manager.get_or_create_layer(self.iface)
            self._layer_manager.add_holding(layer, params, result)
            msg = (f"Holding created — TAS {result.tas_kt:.1f} kt | "
                   f"Radius {result.radius_nm:.3f} NM | Leg {result.leg_nm:.2f} NM")
            if self.iface:
                try:
                    from qgis.core import Qgis
                    _ml = getattr(Qgis, "MessageLevel", None)
                    _success = getattr(_ml, "Success", None) if _ml else getattr(Qgis, "Success", 3)
                    self.iface.messageBar().pushMessage("qAeroChart", msg, level=_success, duration=5)
                except Exception:
                    pass
            log(f"Holding created at ({self._fix_x:.2f}, {self._fix_y:.2f}), "
                f"track {params.inbound_track}°, turn {params.turn}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create holding: {exc}")
            log(f"Holding creation failed: {exc}", "ERROR")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._cancel_pick()
        super().closeEvent(event)
