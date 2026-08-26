"""Dialog for creating a CDFA Distance/Altitude Calculator table (Issue #99).

Same style and layout conventions as GsRodTableDialog.
"""
from __future__ import annotations

try:
    from qgis.PyQt import QtWidgets
except ImportError:
    try:
        from PyQt6 import QtWidgets  # type: ignore
    except ImportError:
        from PyQt5 import QtWidgets  # type: ignore

from ..utils.qt_compat import Qt, QAbstractItemView
from ..core.dist_alt_calculator import DistAltConfig, compute_summary, compute_table

try:
    from qgis.gui import QgsCollapsibleGroupBox
except ImportError:
    QgsCollapsibleGroupBox = QtWidgets.QGroupBox  # fallback fuera de QGIS


class DistAltCalculatorDialog(QtWidgets.QDialog):
    """Interactive builder for CDFA Distance/Altitude Calculator tables with live preview."""

    _ROUND_STEP_MAP = {"None": 0, "5": 5, "10": 10}
    _ROUND_MODE_MAP = {"Nearest": "nearest", "Up": "up"}

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Distance/Altitude Calculator")
        self.setWindowModality(Qt.NonModal)
        self.resize(820, 560)
        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title_lbl = QtWidgets.QLabel("CDFA Distance/Altitude Calculator")
        title_lbl.setAlignment(Qt.AlignHCenter)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11pt;")
        root.addWidget(title_lbl)

        # ── Table parameters ─────────────────────────────────────────────
        params_grp = QtWidgets.QGroupBox("CDFA parameters")
        params_grid = QtWidgets.QGridLayout(params_grp)
        params_grid.setHorizontalSpacing(8)
        params_grid.setVerticalSpacing(6)

        self.spin_faf_altitude = QtWidgets.QDoubleSpinBox()
        self.spin_faf_altitude.setRange(0.0, 60000.0)
        self.spin_faf_altitude.setDecimals(0)
        self.spin_faf_altitude.setValue(6000)
        self.spin_faf_altitude.setSuffix(" ft")

        self.spin_thr_elevation = QtWidgets.QDoubleSpinBox()
        self.spin_thr_elevation.setRange(-1500.0, 20000.0)
        self.spin_thr_elevation.setDecimals(0)
        self.spin_thr_elevation.setValue(1922)
        self.spin_thr_elevation.setSuffix(" ft")

        self.spin_distance = QtWidgets.QDoubleSpinBox()
        self.spin_distance.setRange(0.1, 999.9)
        self.spin_distance.setDecimals(1)
        self.spin_distance.setValue(12.2)
        self.spin_distance.setSuffix(" NM")

        self.spin_tch_rdh = QtWidgets.QDoubleSpinBox()
        self.spin_tch_rdh.setRange(0.0, 200.0)
        self.spin_tch_rdh.setDecimals(0)
        self.spin_tch_rdh.setValue(49)
        self.spin_tch_rdh.setSuffix(" ft")

        self.spin_oca = QtWidgets.QDoubleSpinBox()
        self.spin_oca.setRange(-1500.0, 20000.0)
        self.spin_oca.setDecimals(0)
        self.spin_oca.setValue(2450)
        self.spin_oca.setSuffix(" ft")

        self.check_offset = QtWidgets.QCheckBox("Offset MAPt")
        self.spin_offset = QtWidgets.QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 99.9)
        self.spin_offset.setDecimals(1)
        self.spin_offset.setValue(0.0)
        self.spin_offset.setSuffix(" NM")
        self.spin_offset.setEnabled(False)
        self.check_offset.toggled.connect(self.spin_offset.setEnabled)
        self.check_offset.toggled.connect(self._refresh_preview)

        self.combo_round_step = QtWidgets.QComboBox()
        self.combo_round_step.addItems(["None", "5", "10"])

        self.combo_round_mode = QtWidgets.QComboBox()
        self.combo_round_mode.addItems(["Nearest", "Up"])
        self.combo_round_mode.setEnabled(False)

        self.line_title = QtWidgets.QLineEdit("CDFA Distance/Altitude Table")
        self.line_title.setPlaceholderText("Leave blank to omit title row")

        params_grid.addWidget(QtWidgets.QLabel("FAF Altitude"), 0, 0)
        params_grid.addWidget(self.spin_faf_altitude, 0, 1)
        params_grid.addWidget(QtWidgets.QLabel("THR Elevation"), 0, 2)
        params_grid.addWidget(self.spin_thr_elevation, 0, 3)

        params_grid.addWidget(QtWidgets.QLabel("FAF-THR Distance"), 1, 0)
        params_grid.addWidget(self.spin_distance, 1, 1)
        params_grid.addWidget(QtWidgets.QLabel("TCH/RDH"), 1, 2)
        params_grid.addWidget(self.spin_tch_rdh, 1, 3)

        params_grid.addWidget(QtWidgets.QLabel("OCA"), 2, 0)
        params_grid.addWidget(self.spin_oca, 2, 1)
        params_grid.addWidget(self.check_offset, 2, 2)
        params_grid.addWidget(self.spin_offset, 2, 3)

        params_grid.addWidget(QtWidgets.QLabel("Round Calculated Altitude to"), 3, 0)
        params_grid.addWidget(self.combo_round_step, 3, 1)
        params_grid.addWidget(QtWidgets.QLabel("Round mode"), 3, 2)
        params_grid.addWidget(self.combo_round_mode, 3, 3)

        params_grid.addWidget(QtWidgets.QLabel("Title row"), 4, 0)
        params_grid.addWidget(self.line_title, 4, 1, 1, 3)

        root.addWidget(params_grp)

        # ── Preview table ────────────────────────────────────────────────
        preview_lbl = QtWidgets.QLabel("Preview")
        preview_lbl.setStyleSheet("font-weight: bold;")
        root.addWidget(preview_lbl)

        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, stretch=1)

        self.label_summary = QtWidgets.QLabel("")
        root.addWidget(self.label_summary)

        # ── Layout placement ─────────────────────────────────────────────
        placement_grp = QgsCollapsibleGroupBox("Layout placement")
        placement_grp.setCollapsed(True)
        placement_grp.setSaveCollapsedState(False)
        pl = QtWidgets.QGridLayout(placement_grp)
        pl.setHorizontalSpacing(8)
        pl.setVerticalSpacing(6)

        self.combo_layouts = QtWidgets.QComboBox()
        self._reload_layouts()
        btn_refresh = QtWidgets.QPushButton("Refresh")
        btn_refresh.setFixedWidth(70)
        btn_refresh.clicked.connect(self._reload_layouts)

        self.spin_total_width = QtWidgets.QDoubleSpinBox()
        self.spin_total_width.setRange(10.0, 5000.0)
        self.spin_total_width.setDecimals(2)
        self.spin_total_width.setValue(180.20)

        self.spin_first_col = QtWidgets.QDoubleSpinBox()
        self.spin_first_col.setRange(5.0, 500.0)
        self.spin_first_col.setDecimals(2)
        self.spin_first_col.setValue(36.20)

        self.spin_height = QtWidgets.QDoubleSpinBox()
        self.spin_height.setRange(5.0, 500.0)
        self.spin_height.setDecimals(2)
        self.spin_height.setValue(60.0)

        self.spin_stroke = QtWidgets.QDoubleSpinBox()
        self.spin_stroke.setRange(0.0, 5.0)
        self.spin_stroke.setDecimals(2)
        self.spin_stroke.setValue(0.25)

        self.spin_margin = QtWidgets.QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 10.0)
        self.spin_margin.setDecimals(2)
        self.spin_margin.setValue(2.0)

        self.spin_font_size = QtWidgets.QDoubleSpinBox()
        self.spin_font_size.setRange(4.0, 30.0)
        self.spin_font_size.setDecimals(1)
        self.spin_font_size.setValue(8.0)

        self.line_font_family = QtWidgets.QLineEdit("Arial")

        self.spin_x = QtWidgets.QDoubleSpinBox()
        self.spin_x.setRange(0.0, 5000.0)
        self.spin_x.setDecimals(3)
        self.spin_x.setValue(0.0)

        self.spin_y = QtWidgets.QDoubleSpinBox()
        self.spin_y.setRange(0.0, 5000.0)
        self.spin_y.setDecimals(3)
        self.spin_y.setValue(0.0)

        layout_row = QtWidgets.QHBoxLayout()
        layout_row.setSpacing(4)
        layout_row.addWidget(self.combo_layouts)
        layout_row.addWidget(btn_refresh)

        pl.addWidget(QtWidgets.QLabel("Layout"), 0, 0)
        pl.addLayout(layout_row, 0, 1, 1, 3)

        pl.addWidget(QtWidgets.QLabel("Total width (mm)"), 1, 0)
        pl.addWidget(self.spin_total_width, 1, 1)
        pl.addWidget(QtWidgets.QLabel("First col (mm)"), 1, 2)
        pl.addWidget(self.spin_first_col, 1, 3)

        pl.addWidget(QtWidgets.QLabel("Height (mm)"), 2, 0)
        pl.addWidget(self.spin_height, 2, 1)
        pl.addWidget(QtWidgets.QLabel("Stroke (mm)"), 2, 2)
        pl.addWidget(self.spin_stroke, 2, 3)

        pl.addWidget(QtWidgets.QLabel("Cell margin (mm)"), 3, 0)
        pl.addWidget(self.spin_margin, 3, 1)
        pl.addWidget(QtWidgets.QLabel("Font size"), 3, 2)
        pl.addWidget(self.spin_font_size, 3, 3)

        pl.addWidget(QtWidgets.QLabel("Font family"), 4, 0)
        pl.addWidget(self.line_font_family, 4, 1, 1, 3)

        pl.addWidget(QtWidgets.QLabel("X (mm)"), 5, 0)
        pl.addWidget(self.spin_x, 5, 1)
        pl.addWidget(QtWidgets.QLabel("Y (mm)"), 5, 2)
        pl.addWidget(self.spin_y, 5, 3)

        root.addWidget(placement_grp)

        # ── Action buttons ───────────────────────────────────────────────
        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(8)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        self.btn_insert = QtWidgets.QPushButton("Add to layout")
        self.btn_insert.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
        )
        self.btn_insert.clicked.connect(self.accept)
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_insert)
        root.addLayout(btns)

        # ── Signals ──────────────────────────────────────────────────────
        for widget in (
            self.spin_faf_altitude,
            self.spin_thr_elevation,
            self.spin_distance,
            self.spin_tch_rdh,
            self.spin_oca,
            self.spin_offset,
        ):
            widget.valueChanged.connect(self._refresh_preview)
        self.line_title.textChanged.connect(self._refresh_preview)
        self.combo_round_step.currentTextChanged.connect(self._on_round_step_changed)
        self.combo_round_mode.currentTextChanged.connect(self._refresh_preview)

    def _on_round_step_changed(self, text: str) -> None:
        self.combo_round_mode.setEnabled(text != "None")
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Preview logic
    # ------------------------------------------------------------------

    def _build_calc_config(self) -> DistAltConfig:
        return DistAltConfig(
            faf_altitude_ft=self.spin_faf_altitude.value(),
            thr_elevation_ft=self.spin_thr_elevation.value(),
            faf_thr_distance_nm=self.spin_distance.value(),
            tch_rdh_ft=self.spin_tch_rdh.value(),
            oca_ft=self.spin_oca.value(),
            offset_enabled=self.check_offset.isChecked(),
            offset_distance_nm=self.spin_offset.value(),
            round_step=self._ROUND_STEP_MAP.get(self.combo_round_step.currentText(), 0),
            round_mode=self._ROUND_MODE_MAP.get(self.combo_round_mode.currentText(), "nearest"),
        )

    def _refresh_preview(self) -> None:
        try:
            cfg = self._build_calc_config()
            rows = compute_table(cfg, title=self.line_title.text().strip())
            summary = compute_summary(cfg)
        except Exception as exc:
            self.label_summary.setText(str(exc))
            self.table.setRowCount(0)
            return
        self.label_summary.setText(
            f"Gradient {summary['gradient_pct']:.2f}%  |  "
            f"VPA {summary['vpa_deg']:.2f}°  |  "
            f"Height loss {summary['height_loss_per_mile_ft']} ft/NM"
        )
        if not rows:
            self.table.setRowCount(0)
            return
        n_rows = len(rows)
        n_cols = len(rows[0])
        self.table.clearSpans()
        self.table.setRowCount(n_rows)
        self.table.setColumnCount(n_cols)
        self.table.horizontalHeader().setVisible(False)
        title_rows = 1 if self.line_title.text().strip() else 0
        header_row_idx = title_rows
        for r, row in enumerate(rows):
            is_title = r < title_rows
            is_header = r == header_row_idx
            for c, val in enumerate(row):
                item = QtWidgets.QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if is_title or is_header:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if is_title or c >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
            if is_title:
                self.table.setSpan(r, 0, 1, n_cols)
        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _reload_layouts(self) -> None:
        self.combo_layouts.clear()
        try:
            from qgis.core import QgsProject

            layouts = QgsProject.instance().layoutManager().layouts()
            for lyt in layouts:
                self.combo_layouts.addItem(lyt.name())
            if not layouts:
                self.combo_layouts.addItem("(no layouts found)")
        except Exception:
            self.combo_layouts.addItem("(no layouts found)")

    def select_layout(self, name: str) -> None:
        if not name:
            return
        idx = self.combo_layouts.findText(name)
        if idx >= 0:
            self.combo_layouts.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def table_data(self) -> list[list[str]]:
        try:
            return compute_table(self._build_calc_config(), title=self.line_title.text().strip())
        except Exception:
            return []

    def config(self) -> dict:
        return {
            "layout_name": self.combo_layouts.currentText(),
            "total_width": self.spin_total_width.value(),
            "first_col_width": self.spin_first_col.value(),
            "height": self.spin_height.value(),
            "x": self.spin_x.value(),
            "y": self.spin_y.value(),
            "stroke": self.spin_stroke.value(),
            "cell_margin": self.spin_margin.value(),
            "font_family": self.line_font_family.text() or "Arial",
            "font_size": self.spin_font_size.value(),
        }

    def selected_layout_name(self) -> str:
        return self.combo_layouts.currentText()

    def accept(self) -> None:
        try:
            compute_summary(self._build_calc_config())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Distance/Altitude Calculator", str(exc))
            return
        super().accept()
