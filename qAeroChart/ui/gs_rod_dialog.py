"""Dialog for creating and configuring a GS / Rate-of-Descent table (Issue #73).

Same style and layout conventions as DistanceAltitudeTableDialog.
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
from ..core.gs_rod_calculator import GsRodConfig, compute_table, DEFAULT_GS_VALUES


class GsRodTableDialog(QtWidgets.QDialog):
    """Interactive builder for GS / Rate-of-Descent tables with live preview."""

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("GS / Rate of Descent Table")
        self.setWindowModality(Qt.NonModal)
        self.resize(760, 540)
        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title_lbl = QtWidgets.QLabel("GS / Rate of Descent Table Builder")
        title_lbl.setAlignment(Qt.AlignHCenter)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11pt;")
        root.addWidget(title_lbl)

        # ── Table parameters ─────────────────────────────────────────────
        params_grp = QtWidgets.QGroupBox("Table parameters")
        params_grid = QtWidgets.QGridLayout(params_grp)
        params_grid.setHorizontalSpacing(8)
        params_grid.setVerticalSpacing(6)

        self.spin_distance = QtWidgets.QDoubleSpinBox()
        self.spin_distance.setRange(0.1, 999.9)
        self.spin_distance.setDecimals(1)
        self.spin_distance.setValue(5.2)
        self.spin_distance.setSuffix(" NM")

        self.spin_gradient = QtWidgets.QDoubleSpinBox()
        self.spin_gradient.setRange(0.1, 30.0)
        self.spin_gradient.setDecimals(1)
        self.spin_gradient.setValue(5.3)
        self.spin_gradient.setSuffix(" %")

        self.line_title = QtWidgets.QLineEdit("Rate of Descent")
        self.line_title.setPlaceholderText("Leave blank to omit title row")

        self.line_footer = QtWidgets.QLineEdit()
        self.line_footer.setPlaceholderText("Leave blank to omit footer row")

        self.line_label_timing = QtWidgets.QLineEdit()
        self.line_label_timing.setPlaceholderText("Auto: FAF-MAPt {dist}NM")

        self.line_label_rod = QtWidgets.QLineEdit()
        self.line_label_rod.setPlaceholderText("Auto: Rate of Descent {grad}%")

        self.line_unit_gs = QtWidgets.QLineEdit("KT")
        self.line_unit_gs.setFixedWidth(60)

        self.line_unit_timing = QtWidgets.QLineEdit("min:s")
        self.line_unit_timing.setFixedWidth(60)

        self.line_gs_values = QtWidgets.QLineEdit(
            ", ".join(str(v) for v in DEFAULT_GS_VALUES)
        )
        self.line_gs_values.setPlaceholderText("Comma-separated integers, e.g. 70, 90, 100, 120, 140, 160")

        params_grid.addWidget(QtWidgets.QLabel("Distance (NM)"), 0, 0)
        params_grid.addWidget(self.spin_distance, 0, 1)
        params_grid.addWidget(QtWidgets.QLabel("Gradient (%)"), 0, 2)
        params_grid.addWidget(self.spin_gradient, 0, 3)

        params_grid.addWidget(QtWidgets.QLabel("Title row"), 1, 0)
        params_grid.addWidget(self.line_title, 1, 1, 1, 3)

        params_grid.addWidget(QtWidgets.QLabel("Footer row"), 2, 0)
        params_grid.addWidget(self.line_footer, 2, 1, 1, 3)

        params_grid.addWidget(QtWidgets.QLabel("Timing label"), 3, 0)
        params_grid.addWidget(self.line_label_timing, 3, 1)
        params_grid.addWidget(QtWidgets.QLabel("ROD label"), 3, 2)
        params_grid.addWidget(self.line_label_rod, 3, 3)

        params_grid.addWidget(QtWidgets.QLabel("GS unit"), 4, 0)
        params_grid.addWidget(self.line_unit_gs, 4, 1)
        params_grid.addWidget(QtWidgets.QLabel("Timing unit"), 4, 2)
        params_grid.addWidget(self.line_unit_timing, 4, 3)

        params_grid.addWidget(QtWidgets.QLabel("GS values"), 5, 0)
        params_grid.addWidget(self.line_gs_values, 5, 1, 1, 3)

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

        # ── Layout placement ─────────────────────────────────────────────
        placement_grp = QtWidgets.QGroupBox("Layout placement")
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
        self.spin_first_col.setValue(45.00)

        self.spin_height = QtWidgets.QDoubleSpinBox()
        self.spin_height.setRange(5.0, 500.0)
        self.spin_height.setDecimals(2)
        self.spin_height.setValue(20.0)

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
            self.spin_distance,
            self.spin_gradient,
        ):
            widget.valueChanged.connect(self._refresh_preview)
        for widget in (
            self.line_title,
            self.line_footer,
            self.line_label_timing,
            self.line_label_rod,
            self.line_unit_gs,
            self.line_unit_timing,
            self.line_gs_values,
        ):
            widget.textChanged.connect(self._refresh_preview)

    # ------------------------------------------------------------------
    # Preview logic
    # ------------------------------------------------------------------

    def _parse_gs_values(self) -> tuple[int, ...]:
        raw = self.line_gs_values.text()
        result: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                result.append(int(part))
        return tuple(result) if result else DEFAULT_GS_VALUES

    def _build_config(self) -> GsRodConfig:
        return GsRodConfig(
            distance_nm=self.spin_distance.value(),
            gradient_pct=self.spin_gradient.value(),
            gs_values=self._parse_gs_values(),
            title=self.line_title.text().strip(),
            label_timing=self.line_label_timing.text().strip(),
            label_rod=self.line_label_rod.text().strip(),
            unit_gs=self.line_unit_gs.text().strip() or "KT",
            unit_timing=self.line_unit_timing.text().strip() or "min:s",
            footer=self.line_footer.text().strip(),
        )

    def _refresh_preview(self) -> None:
        try:
            cfg = self._build_config()
            rows = compute_table(cfg)
        except Exception:
            return
        if not rows:
            return
        n_rows = len(rows)
        n_cols = len(rows[0])
        self.table.clearSpans()
        self.table.setRowCount(n_rows)
        self.table.setColumnCount(n_cols)
        self.table.horizontalHeader().setVisible(False)
        title_rows = 1 if cfg.title else 0
        header_row_idx = title_rows
        footer_row_idx = n_rows - 1 if cfg.footer else None
        for r, row in enumerate(rows):
            is_title = r < title_rows
            is_footer = r == footer_row_idx and footer_row_idx is not None
            is_header = r == header_row_idx
            for c, val in enumerate(row):
                item = QtWidgets.QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if is_title or is_footer or (is_header and c >= 2):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if is_title or is_footer or c >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
            if is_title or is_footer:
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
            return compute_table(self._build_config())
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
        if not self._parse_gs_values():
            QtWidgets.QMessageBox.warning(
                self, "GS/ROD Table", "Please enter at least one ground speed value."
            )
            return
        super().accept()
