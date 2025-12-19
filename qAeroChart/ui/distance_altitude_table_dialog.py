from PyQt5 import QtCore, QtWidgets


class DistanceAltitudeTableDialog(QtWidgets.QDialog):
    """Interactive builder for distance/altitude tables with live preview."""

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Distance/Altitude Table")
        # Non-modal so the layout window does not minimize
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setModal(False)
        self.resize(720, 520)
        self._build_ui()
        self._init_table()
        self._layout = None
        self._existing_tables = []

    # ---------- UI ----------
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("Table Builder")
        title.setAlignment(QtCore.Qt.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(title)

        # Top controls
        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(6)

        self.line_top_left = QtWidgets.QLineEdit("NM TO RWY00")
        self.line_row1_label = QtWidgets.QLineEdit("ALTITUDE")
        self.spin_rows = QtWidgets.QSpinBox()
        self.spin_rows.setRange(1, 50)
        self.spin_rows.setValue(2)
        self.spin_cols = QtWidgets.QSpinBox()
        self.spin_cols.setRange(1, 50)
        self.spin_cols.setValue(6)

        controls.addWidget(QtWidgets.QLabel("Top-left text"), 0, 0)
        controls.addWidget(self.line_top_left, 0, 1)
        controls.addWidget(QtWidgets.QLabel("First column text"), 0, 2)
        controls.addWidget(self.line_row1_label, 0, 3)
        controls.addWidget(QtWidgets.QLabel("Rows"), 1, 0)
        controls.addWidget(self.spin_rows, 1, 1)
        controls.addWidget(QtWidgets.QLabel("Columns"), 1, 2)
        controls.addWidget(self.spin_cols, 1, 3)

        btn_load_json = QtWidgets.QPushButton("Load JSON")
        btn_load_json.clicked.connect(self._load_json)
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_table)
        btn_resize = QtWidgets.QPushButton("Resize Table")
        btn_resize.clicked.connect(self._resize_table)

        row_btns = QtWidgets.QHBoxLayout()
        row_btns.setSpacing(6)
        row_btns.addWidget(btn_load_json)
        row_btns.addWidget(btn_resize)
        row_btns.addWidget(btn_clear)
        row_btns.addStretch(1)
        controls.addLayout(row_btns, 2, 0, 1, 4)

        # Existing tables loader (from layout)
        self.combo_existing = QtWidgets.QComboBox()
        self.combo_existing.setMinimumWidth(200)
        self.btn_load_existing = QtWidgets.QPushButton("Load from layout")
        self.btn_load_existing.clicked.connect(self._load_from_existing)
        existing_layout = QtWidgets.QHBoxLayout()
        existing_layout.setSpacing(6)
        existing_layout.addWidget(QtWidgets.QLabel("Existing tables"))
        existing_layout.addWidget(self.combo_existing)
        existing_layout.addWidget(self.btn_load_existing)
        existing_layout.addStretch(1)

        layout.addLayout(controls)
        layout.addLayout(existing_layout)

        # Preview table
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        # Layout/placement options
        options_grp = QtWidgets.QGroupBox("Layout placement")
        options_layout = QtWidgets.QGridLayout(options_grp)
        options_layout.setHorizontalSpacing(8)
        options_layout.setVerticalSpacing(6)

        self.combo_layouts = QtWidgets.QComboBox()
        self._reload_layouts()
        btn_refresh_layouts = QtWidgets.QPushButton("Refresh")
        btn_refresh_layouts.setFixedWidth(70)
        btn_refresh_layouts.clicked.connect(self._reload_layouts)

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
        self.spin_height.setValue(14.0)
        self.spin_x = QtWidgets.QDoubleSpinBox()
        self.spin_x.setRange(0.0, 5000.0)
        self.spin_x.setDecimals(3)
        self.spin_x.setValue(0.0)
        self.spin_y = QtWidgets.QDoubleSpinBox()
        self.spin_y.setRange(0.0, 5000.0)
        self.spin_y.setDecimals(3)
        self.spin_y.setValue(0.0)
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

        options_layout.addWidget(QtWidgets.QLabel("Layout"), 0, 0)
        layout_picker = QtWidgets.QHBoxLayout()
        layout_picker.setSpacing(4)
        layout_picker.addWidget(self.combo_layouts)
        layout_picker.addWidget(btn_refresh_layouts)
        options_layout.addLayout(layout_picker, 0, 1, 1, 3)

        options_layout.addWidget(QtWidgets.QLabel("Total width (mm)"), 1, 0)
        options_layout.addWidget(self.spin_total_width, 1, 1)
        options_layout.addWidget(QtWidgets.QLabel("First col (mm)"), 1, 2)
        options_layout.addWidget(self.spin_first_col, 1, 3)

        options_layout.addWidget(QtWidgets.QLabel("Height (mm)"), 2, 0)
        options_layout.addWidget(self.spin_height, 2, 1)
        options_layout.addWidget(QtWidgets.QLabel("Stroke (mm)"), 2, 2)
        options_layout.addWidget(self.spin_stroke, 2, 3)

        options_layout.addWidget(QtWidgets.QLabel("Cell margin (mm)"), 3, 0)
        options_layout.addWidget(self.spin_margin, 3, 1)
        options_layout.addWidget(QtWidgets.QLabel("Font family"), 3, 2)
        options_layout.addWidget(self.line_font_family, 3, 3)

        options_layout.addWidget(QtWidgets.QLabel("Font size"), 4, 0)
        options_layout.addWidget(self.spin_font_size, 4, 1)
        options_layout.addWidget(QtWidgets.QLabel("X (mm)"), 4, 2)
        options_layout.addWidget(self.spin_x, 4, 3)

        options_layout.addWidget(QtWidgets.QLabel("Y (mm)"), 5, 0)
        options_layout.addWidget(self.spin_y, 5, 1)

        layout.addWidget(options_grp)

        # Action buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        self.btn_insert = QtWidgets.QPushButton("Add to layout")
        self.btn_insert.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_insert.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(self.btn_insert)
        layout.addLayout(buttons)

        # Signals
        self.spin_rows.valueChanged.connect(self._resize_table)
        self.spin_cols.valueChanged.connect(self._resize_table)

    def select_layout(self, name):
        """Select a layout in the combo if it exists (no-op otherwise)."""

        if not name:
            return
        idx = self.combo_layouts.findText(name)
        if idx >= 0:
            self.combo_layouts.setCurrentIndex(idx)

    def set_layout(self, layout):
        """Attach to a layout (for loading existing tables)."""

        self._layout = layout
        self._refresh_existing_tables()

    def _init_table(self):
        self._resize_table()
        # Seed defaults
        self.table.setItem(0, 0, QtWidgets.QTableWidgetItem(self.line_top_left.text()))
        for col in range(1, self.table.columnCount()):
            self.table.setItem(0, col, QtWidgets.QTableWidgetItem(str(col)))
        if self.table.rowCount() > 1:
            self.table.setItem(1, 0, QtWidgets.QTableWidgetItem(self.line_row1_label.text()))

    # ---------- Data helpers ----------
    def _resize_table(self):
        rows = self.spin_rows.value()
        cols = self.spin_cols.value()
        current_data = self.table_data()
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        for r in range(rows):
            for c in range(cols):
                if r < len(current_data) and c < len(current_data[r]):
                    self.table.setItem(r, c, QtWidgets.QTableWidgetItem(current_data[r][c]))
                else:
                    self.table.setItem(r, c, QtWidgets.QTableWidgetItem(""))

    def _clear_table(self):
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(""))

    def _refresh_existing_tables(self):
        self._existing_tables = []
        self.combo_existing.clear()
        if not self._layout:
            self.combo_existing.addItem("(no layout attached)")
            return
        try:
            from qgis.core import QgsLayoutItemManualTable, QgsLayoutFrame

            items = self._layout.items()
            tables = [it for it in items if isinstance(it, QgsLayoutItemManualTable)]
            if not tables:
                self.combo_existing.addItem("(no tables in layout)")
                return
            for idx, tbl in enumerate(tables):
                label = tbl.customProperty("name") or f"Table {idx+1}"
                info = self._extract_table(tbl)
                if info:
                    self._existing_tables.append(info)
                    self.combo_existing.addItem(f"{label} ({len(info['rows'][0]) if info['rows'] else 0} cols)")
        except Exception:
            self.combo_existing.addItem("(cannot read tables)")

    def _extract_table(self, tbl):
        try:
            contents = tbl.tableContents()
        except Exception:
            contents = []
        rows = []
        try:
            for row in contents:
                row_vals = []
                for cell in row:
                    try:
                        row_vals.append(cell.text())
                    except Exception:
                        row_vals.append("")
                rows.append(row_vals)
        except Exception:
            rows = []

        cfg = {
            "stroke": getattr(tbl, "gridStrokeWidth", lambda: 0.25)(),
            "cell_margin": getattr(tbl, "cellMargin", lambda: 0.0)(),
            "column_widths": getattr(tbl, "columnWidths", lambda: [])(),
            "font_family": "Arial",
            "font_size": 8.0,
            "total_width": None,
            "height": None,
            "x": None,
            "y": None,
        }

        try:
            fmt = tbl.contentTextFormat()
            fnt = fmt.font()
            cfg["font_family"] = fnt.family()
            cfg["font_size"] = fmt.size()
        except Exception:
            pass

        # Derive size/pos from first frame associated
        try:
            frames = [it for it in self._layout.items() if isinstance(it, QgsLayoutFrame) and it.multiFrame() == tbl]
            if frames:
                frame = frames[0]
                size = frame.sizeWithUnits()
                pos = frame.positionWithUnits()
                cfg["total_width"] = size.width()
                cfg["height"] = size.height()
                cfg["x"] = pos.x()
                cfg["y"] = pos.y()
        except Exception:
            pass

        return {"rows": rows, "config": cfg}

    def _load_from_existing(self):
        if not self._existing_tables:
            return
        idx = self.combo_existing.currentIndex()
        if idx < 0 or idx >= len(self._existing_tables):
            return
        data = self._existing_tables[idx]
        rows = data.get("rows", [])
        if not rows:
            return
        # Resize to match
        self.spin_rows.setValue(len(rows))
        self.spin_cols.setValue(len(rows[0]))
        self._resize_table()
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        cfg = data.get("config", {})
        if cfg.get("column_widths"):
            # Set first column width when available
            self.spin_first_col.setValue(cfg["column_widths"][0])
        if cfg.get("total_width"):
            self.spin_total_width.setValue(cfg["total_width"])
        if cfg.get("height"):
            self.spin_height.setValue(cfg["height"])
        if cfg.get("x") is not None:
            self.spin_x.setValue(cfg["x"])
        if cfg.get("y") is not None:
            self.spin_y.setValue(cfg["y"])
        if cfg.get("stroke") is not None:
            self.spin_stroke.setValue(cfg["stroke"])
        if cfg.get("cell_margin") is not None:
            self.spin_margin.setValue(cfg["cell_margin"])
        if cfg.get("font_family"):
            self.line_font_family.setText(cfg["font_family"])
        if cfg.get("font_size"):
            try:
                self.spin_font_size.setValue(float(cfg["font_size"]))
            except Exception:
                pass

    def _reload_layouts(self):
        self.combo_layouts.clear()
        try:
            from qgis.core import QgsProject

            manager = QgsProject.instance().layoutManager()
            layouts = manager.layouts()
            for lyt in layouts:
                self.combo_layouts.addItem(lyt.name())
            if not layouts:
                self.combo_layouts.addItem("(no layouts found)")
        except Exception:
            self.combo_layouts.addItem("(no layouts found)")

    def _load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Table JSON", "", "JSON Files (*.json)")
        if not path:
            return
        import json

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as exc:  # keep error simple
            QtWidgets.QMessageBox.warning(self, "Invalid JSON", f"Could not read file: {exc}")
            return
        thr = data.get("thr", "00")
        numeric = data.get("numeric_columns", {})
        if not numeric:
            QtWidgets.QMessageBox.warning(self, "Invalid JSON", "numeric_columns is missing or empty")
            return
        keys = list(numeric.keys())
        # Preserve order but ensure strings
        values = [numeric[k] for k in keys]
        cols = len(keys) + 1
        self.spin_rows.setValue(2)
        self.spin_cols.setValue(cols)
        self._resize_table()
        self.line_top_left.setText(f"NM TO RWY{thr}")
        self.table.setItem(0, 0, QtWidgets.QTableWidgetItem(self.line_top_left.text()))
        for idx, key in enumerate(keys, start=1):
            self.table.setItem(0, idx, QtWidgets.QTableWidgetItem(str(key)))
        self.line_row1_label.setText("ALTITUDE")
        self.table.setItem(1, 0, QtWidgets.QTableWidgetItem(self.line_row1_label.text()))
        for idx, val in enumerate(values, start=1):
            self.table.setItem(1, idx, QtWidgets.QTableWidgetItem(str(val)))

    # Public accessors
    def table_data(self):
        rows = []
        for r in range(self.table.rowCount()):
            row = []
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                row.append(item.text().strip() if item else "")
            rows.append(row)
        return rows

    def config(self):
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

    def selected_layout_name(self):
        return self.combo_layouts.currentText()

    def accept(self):  # Validate before closing
        if self.table.columnCount() < 1 or self.table.rowCount() < 1:
            QtWidgets.QMessageBox.warning(self, "Table", "Please set at least 1 row and 1 column")
            return
        super().accept()

