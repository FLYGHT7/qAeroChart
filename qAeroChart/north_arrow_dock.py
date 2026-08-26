# -*- coding: utf-8 -*-
"""North Arrow dock widget — place a true/magnetic north arrow by clicking
the map (Issue #108).

Mirrors the MSA / Holding dock architecture: geometry math lives in
``core/north_arrow.py`` (pure Python, unit tested), layer creation/styling/
labeling plus config persistence in ``core/north_arrow_manager.py``, and
this class only handles UI + signal wiring.
"""
from __future__ import annotations

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsPointXY, QgsProject
from qgis.utils import iface

from .core.north_arrow import compute_arrow_geometry, format_var_label
from .core.north_arrow_manager import NorthArrowManager
from .tools.north_arrow_tool import NorthArrowTool
from .utils.logger import log
from .utils.qt_compat import MsgLevel, Qt


class NorthArrowDockWidget(QtWidgets.QDockWidget):
    """Dock widget for placing north arrows with magnetic declination."""

    _DEFAULT_STATUS_TEXT = (
        "Select location on map, then click the chart to place the arrow. "
        "Once placed, use Update Arrow to apply changes without clicking again."
    )

    def __init__(self, parent=None):
        _fallback = iface.mainWindow() if iface else None
        super().__init__(parent or _fallback)
        self.setWindowTitle("North Arrow")
        self.setObjectName("NorthArrowDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._layer_manager = NorthArrowManager()
        self._map_tool: NorthArrowTool | None = None
        self._prev_tool = None
        self._last_origin: QgsPointXY | None = None

        self._build_ui()
        self._restore_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        dims_group = QGroupBox("Line Lengths (km)")
        dims_form = QFormLayout(dims_group)
        dims_form.setHorizontalSpacing(6)
        dims_form.setVerticalSpacing(4)
        dims_form.setContentsMargins(6, 6, 6, 6)

        self.spin_true_len = QDoubleSpinBox()
        self.spin_true_len.setRange(0.1, 1000.0)
        self.spin_true_len.setDecimals(1)
        self.spin_true_len.setValue(10.0)
        dims_form.addRow("True North:", self.spin_true_len)

        self.spin_mag_len = QDoubleSpinBox()
        self.spin_mag_len.setRange(0.1, 1000.0)
        self.spin_mag_len.setDecimals(1)
        self.spin_mag_len.setValue(7.0)
        dims_form.addRow("Magnetic North:", self.spin_mag_len)

        layout.addWidget(dims_group)

        decl_group = QGroupBox("Magnetic Declination")
        decl_layout = QVBoxLayout(decl_group)

        decl_form = QFormLayout()
        decl_form.setHorizontalSpacing(6)
        decl_form.setVerticalSpacing(4)
        self.spin_declination = QDoubleSpinBox()
        self.spin_declination.setRange(0.0, 90.0)
        self.spin_declination.setDecimals(2)
        self.spin_declination.setValue(0.0)
        decl_form.addRow("Declination Angle (°):", self.spin_declination)
        decl_layout.addLayout(decl_form)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Direction:"))
        self.radio_east = QRadioButton("East")
        self.radio_west = QRadioButton("West")
        self.radio_east.setChecked(True)
        self._ew_group = QButtonGroup(self)
        self._ew_group.addButton(self.radio_east)
        self._ew_group.addButton(self.radio_west)
        dir_row.addWidget(self.radio_west)
        dir_row.addWidget(self.radio_east)
        dir_row.addStretch()
        decl_layout.addLayout(dir_row)

        layout.addWidget(decl_group)

        self.chk_replace = QCheckBox("Replace existing north arrows")
        self.chk_replace.setChecked(False)
        layout.addWidget(self.chk_replace)

        self.btn_place = QPushButton("Select location on map")
        self.btn_place.setCheckable(True)
        layout.addWidget(self.btn_place)

        self.btn_update = QPushButton("Update Arrow")
        self.btn_update.setEnabled(False)
        self.btn_update.setStyleSheet(
            "font-weight: bold; background-color: #00557f; color: white; padding: 8px;"
        )
        layout.addWidget(self.btn_update)

        self.btn_clear = QPushButton("Remove All Arrows")
        self.btn_clear.setStyleSheet("background-color: #f44336; color: white;")
        layout.addWidget(self.btn_clear)

        self.lbl_status = QLabel(self._DEFAULT_STATUS_TEXT)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        self.setWidget(container)
        self._connect_ui_signals()

    def _connect_ui_signals(self):
        self.btn_place.toggled.connect(self._on_place_toggled)
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.btn_clear.clicked.connect(self._clear_all_arrows)

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def _declination_signed(self) -> float:
        value = self.spin_declination.value()
        return -value if self.radio_west.isChecked() else value

    def _current_config(self) -> dict:
        cfg = {
            "true_len_km": self.spin_true_len.value(),
            "mag_len_km": self.spin_mag_len.value(),
            "declination": self.spin_declination.value(),
            "is_west": self.radio_west.isChecked(),
        }
        if self._last_origin is not None:
            cfg["last_origin_x"] = self._last_origin.x()
            cfg["last_origin_y"] = self._last_origin.y()
        return cfg

    def _restore_config(self) -> None:
        cfg = self._layer_manager.load_config()
        if not cfg:
            return
        try:
            self.spin_true_len.setValue(float(cfg.get("true_len_km", 10.0)))
            self.spin_mag_len.setValue(float(cfg.get("mag_len_km", 7.0)))
            self.spin_declination.setValue(float(cfg.get("declination", 0.0)))
            self.radio_west.setChecked(bool(cfg.get("is_west", False)))
            if "last_origin_x" in cfg and "last_origin_y" in cfg:
                self._last_origin = QgsPointXY(
                    float(cfg["last_origin_x"]), float(cfg["last_origin_y"])
                )
                self.btn_update.setEnabled(True)
        except (TypeError, ValueError) as exc:
            log(f"NorthArrowDock: could not restore stored config: {exc}", "WARNING")

    def _save_config(self) -> None:
        try:
            self._layer_manager.save_config(self._current_config())
        except Exception as exc:
            log(f"NorthArrowDock: could not persist config: {exc}", "WARNING")

    # ------------------------------------------------------------------
    # Map-tool placement mode
    # ------------------------------------------------------------------

    def _on_place_toggled(self, checked: bool) -> None:
        if checked:
            self._start_placement()
        else:
            self._stop_placement()

    def _start_placement(self) -> None:
        canvas = iface.mapCanvas() if iface else None
        if canvas is None:
            self.lbl_status.setText("Map canvas not available.")
            self.btn_place.setChecked(False)
            return

        if self._map_tool is None:
            self._map_tool = NorthArrowTool(canvas)
            self._map_tool.arrowPlaced.connect(self._on_arrow_placed)
            self._map_tool.deactivated.connect(self._on_tool_deactivated)

        self._prev_tool = canvas.mapTool()
        canvas.setMapTool(self._map_tool)
        self.lbl_status.setText("Click on the chart to place the north arrow.")
        log("NorthArrowDock: placement mode active")

    def _stop_placement(self) -> None:
        canvas = iface.mapCanvas() if iface else None
        if canvas is not None and self._map_tool is not None:
            try:
                canvas.unsetMapTool(self._map_tool)
            except RuntimeError:  # nosec B110 - tool already torn down during QGIS shutdown
                pass
        self.btn_place.setChecked(False)
        self.lbl_status.setText(self._DEFAULT_STATUS_TEXT)

    def _on_tool_deactivated(self) -> None:
        # Fires when another tool takes over (e.g. user picks pan/zoom) —
        # sync the toggle button without recursing into _stop_placement.
        self.btn_place.blockSignals(True)
        self.btn_place.setChecked(False)
        self.btn_place.blockSignals(False)
        self.lbl_status.setText(self._DEFAULT_STATUS_TEXT)

    # ------------------------------------------------------------------
    # Drawing / clearing
    # ------------------------------------------------------------------

    def _on_arrow_placed(self, point) -> None:
        self._last_origin = QgsPointXY(point.x(), point.y())
        self.btn_update.setEnabled(True)
        self._draw_arrow_at(self._last_origin, message="North arrow placed")

    def _on_update_clicked(self) -> None:
        if self._last_origin is None:
            return
        self._draw_arrow_at(self._last_origin, message="North arrow updated")

    def _draw_arrow_at(self, point, message: str) -> None:
        layer = self._layer_manager.get_or_create_layer(iface)
        if self.chk_replace.isChecked():
            self._layer_manager.clear_arrows(layer)

        geom = compute_arrow_geometry(
            point.x(),
            point.y(),
            self.spin_true_len.value() * 1000.0,
            self.spin_mag_len.value() * 1000.0,
            self._declination_signed(),
        )
        self._layer_manager.add_arrow(layer, geom, self._declination_signed())
        self._save_config()

        canvas = iface.mapCanvas() if iface else None
        if canvas is not None:
            canvas.refresh()
        if iface is not None:
            iface.messageBar().pushMessage(
                "qAeroChart",
                f"{message} ({format_var_label(self._declination_signed())}).",
                level=MsgLevel.Success,
                duration=4,
            )

    def _clear_all_arrows(self) -> None:
        project = QgsProject.instance()
        existing = project.mapLayersByName(NorthArrowManager.LAYER_NAME)
        if not existing:
            if iface is not None:
                iface.messageBar().pushMessage(
                    "qAeroChart",
                    "No north-arrow layer on the map.",
                    level=MsgLevel.Info,
                    duration=3,
                )
            return
        self._layer_manager.clear_arrows(existing[0])
        canvas = iface.mapCanvas() if iface else None
        if canvas is not None:
            canvas.refresh()

    # ------------------------------------------------------------------
    # Dock lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._stop_placement()
        self._save_config()
        super().closeEvent(event)
