"""OCA/H Table dialog — interactive builder (Issue #74)."""
from __future__ import annotations

try:
    from qgis.PyQt import QtWidgets
except ImportError:
    try:
        from PyQt6 import QtWidgets  # type: ignore
    except ImportError:
        from PyQt5 import QtWidgets  # type: ignore

from ..utils.qt_compat import Qt, QAbstractItemView
from ..core.oca_h_table import (
    DEFAULT_CATEGORY_HEADERS,
    OcaHConfig,
    OcaHRow,
    compute_table,
)

_DEFAULT_ROWS = [
    ("ILS CAT I", "324 (161)", "334 (171)", "346 (183)", "361 (198)"),
    ("LOC", "600 (440)", "600 (440)", "600 (440)", "600 (440)"),
    ("LOC WO SDF", "800 (640)", "800 (640)", "800 (640)", "800 (640)"),
]


class OcaHTableDialog(QtWidgets.QDialog):
    """Interactive builder for OCA/H tables with live preview."""

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("OCA/H Table")
        self.setWindowModality(Qt.NonModal)
        self.resize(800, 580)
        self._build_ui()
        self._populate_defaults()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title_lbl = QtWidgets.QLabel("OCA/H Table Builder")
        title_lbl.setAlignment(Qt.AlignHCenter)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11pt;")
        root.addWidget(title_lbl)

        # ── Table parameters ─────────────────────────────────────────
        params_grp = QtWidgets.QGroupBox("Table parameters")
        params_grid = QtWidgets.QGridLayout(params_grp)
        params_grid.setHorizontalSpacing(8)
        params_grid.setVerticalSpacing(6)

        self.line_title = QtWidgets.QLineEdit()
        self.line_title.setPlaceholderText("Optional title row")
        self.line_footer = QtWidgets.QLineEdit()
        self.line_footer.setPlaceholderText("Optional footer row")
        self.line_header_col0 = QtWidgets.QLineEdit("OCA (H)")
        self.line_category_headers = QtWidgets.QLineEdit(
            ", ".join(DEFAULT_CATEGORY_HEADERS)
        )
        self.line_category_headers.setToolTip(
            "Comma-separated aircraft category headers, e.g. A, B, C, D"
        )

        params_grid.addWidget(QtWidgets.QLabel("Title"), 0, 0)
        params_grid.addWidget(self.line_title, 0, 1, 1, 3)
        params_grid.addWidget(QtWidgets.QLabel("Footer"), 1, 0)
        params_grid.addWidget(self.line_footer, 1, 1, 1, 3)
        params_grid.addWidget(QtWidgets.QLabel("Col 0 header"), 2, 0)
        params_grid.addWidget(self.line_header_col0, 2, 1)
        params_grid.addWidget(QtWidgets.QLabel("Category headers"), 2, 2)
        params_grid.addWidget(self.line_category_headers, 2, 3)

        root.addWidget(params_grp)

        # ── Data entry table ─────────────────────────────────────────
        data_grp = QtWidgets.QGroupBox("Procedure rows")
        data_vlayout = QtWidgets.QVBoxLayout(data_grp)
        data_vlayout.setSpacing(4)

        self.data_table = QtWidgets.QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        data_vlayout.addWidget(self.data_table, stretch=1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)
        btn_add = QtWidgets.QPushButton("Add row")
        btn_add.clicked.connect(self._add_row)
        btn_remove = QtWidgets.QPushButton("Remove row")
        btn_remove.clicked.connect(self._remove_row)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch(1)
        data_vlayout.addLayout(btn_row)

        root.addWidget(data_grp, stretch=1)

        # ── Preview ──────────────────────────────────────────────────
        preview_lbl = QtWidgets.QLabel("Preview")
        preview_lbl.setStyleSheet("font-weight: bold;")
        root.addWidget(preview_lbl)

        self.preview = QtWidgets.QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.horizontalHeader().setStretchLastSection(True)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setAlternatingRowColors(True)
        root.addWidget(self.preview, stretch=1)

        # ── Layout placement ─────────────────────────────────────────
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

        # ── Action buttons ───────────────────────────────────────────
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

        # ── Signals ──────────────────────────────────────────────────
        for widget in (
            self.line_title,
            self.line_footer,
            self.line_header_col0,
            self.line_category_headers,
        ):
            widget.textChanged.connect(self._on_params_changed)

        self.data_table.cellChanged.connect(self._refresh_preview)
        self.line_category_headers.textChanged.connect(self._rebuild_data_columns)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _populate_defaults(self) -> None:
        """Populate data table with sample rows and trigger preview."""
        cats = self._parse_category_headers()
        n_cols = len(cats) + 1  # procedure col + one per category
        self.data_table.setColumnCount(n_cols)
        self._update_data_headers()
        self.data_table.setRowCount(0)
        for row_data in _DEFAULT_ROWS:
            self._insert_data_row(list(row_data))
        self._refresh_preview()

    def _update_data_headers(self) -> None:
        cats = self._parse_category_headers()
        self.data_table.setHorizontalHeaderLabels(
            [self.line_header_col0.text() or "OCA (H)"] + list(cats)
        )

    def _insert_data_row(self, values: list[str] | None = None) -> None:
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)
        n_cols = self.data_table.columnCount()
        for c in range(n_cols):
            val = values[c] if values and c < len(values) else ""
            self.data_table.setItem(row, c, QtWidgets.QTableWidgetItem(val))

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _add_row(self) -> None:
        self._insert_data_row()
        self._refresh_preview()

    def _remove_row(self) -> None:
        row = self.data_table.currentRow()
        if row >= 0:
            self.data_table.removeRow(row)
            self._refresh_preview()

    def _on_params_changed(self) -> None:
        self._update_data_headers()
        self._refresh_preview()

    def _rebuild_data_columns(self) -> None:
        """Adjust data_table column count when category headers change."""
        cats = self._parse_category_headers()
        new_n = len(cats) + 1
        old_n = self.data_table.columnCount()
        if new_n == old_n:
            self._update_data_headers()
            return
        self.data_table.blockSignals(True)
        self.data_table.setColumnCount(new_n)
        # Fill newly added cells with empty string
        for r in range(self.data_table.rowCount()):
            for c in range(old_n, new_n):
                self.data_table.setItem(r, c, QtWidgets.QTableWidgetItem(""))
        self.data_table.blockSignals(False)
        self._update_data_headers()
        self._refresh_preview()

    def _reload_layouts(self) -> None:
        self.combo_layouts.clear()
        try:
            from qgis.core import QgsProject

            layouts = QgsProject.instance().layoutManager().layouts()
            for lyt in layouts:
                self.combo_layouts.addItem(lyt.name())
        except Exception:
            self.combo_layouts.addItem("(no layouts)")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _parse_category_headers(self) -> tuple[str, ...]:
        raw = self.line_category_headers.text()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return tuple(parts) if parts else DEFAULT_CATEGORY_HEADERS

    def _build_config(self) -> OcaHConfig:
        cats = self._parse_category_headers()
        n_cols = self.data_table.columnCount()
        data_rows: list[OcaHRow] = []
        for r in range(self.data_table.rowCount()):
            proc = (self.data_table.item(r, 0) or QtWidgets.QTableWidgetItem("")).text()
            vals: list[str] = []
            for c in range(1, n_cols):
                item = self.data_table.item(r, c)
                vals.append(item.text() if item else "")
            data_rows.append(OcaHRow(procedure=proc, values=tuple(vals)))
        return OcaHConfig(
            rows=tuple(data_rows),
            header_col0=self.line_header_col0.text().strip() or "OCA (H)",
            category_headers=cats,
            title=self.line_title.text().strip(),
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
        title_rows = 1 if cfg.title else 0
        header_row_idx = title_rows
        footer_row_idx = n_rows - 1 if cfg.footer else None

        self.preview.clearSpans()
        self.preview.setRowCount(n_rows)
        self.preview.setColumnCount(n_cols)
        self.preview.horizontalHeader().setVisible(False)

        for r, row in enumerate(rows):
            is_title = r < title_rows
            is_footer = r == footer_row_idx and footer_row_idx is not None
            is_header = r == header_row_idx
            for c, val in enumerate(row):
                item = QtWidgets.QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if is_title or is_footer or is_header:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if is_title or is_footer or is_header or c >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.preview.setItem(r, c, item)
            if is_title or is_footer:
                self.preview.setSpan(r, 0, 1, n_cols)
        self.preview.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Public API
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

    def select_layout(self, name: str) -> None:
        idx = self.combo_layouts.findText(name)
        if idx >= 0:
            self.combo_layouts.setCurrentIndex(idx)
