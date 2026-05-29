# -*- coding: utf-8 -*-
"""Nominal Holding dock widget — mirrors VerticalScaleDockWidget / HorizontalScaleDockWidget (Issue #94)."""

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import (
    QLabel,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QStackedWidget,
    QWidget,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QSpacerItem,
    QRadioButton,
    QButtonGroup,
    QShortcut,
    QInputDialog,
    QMenu,
    QAction,
)
from qgis.PyQt.QtGui import QKeySequence
from qgis.core import QgsPointXY, QgsPoint
from qgis.utils import iface

from .utils.qt_compat import Qt, MsgLevel
from .core.holding import HoldingParameters, build_holding
from .core.holding_layer_manager import HoldingLayerManager


class HoldingDockWidget(QtWidgets.QDockWidget):
    """Dock widget for creating nominal holding patterns (Issue #94)."""

    def __init__(self, parent=None):
        _fallback = iface.mainWindow() if iface else None
        super().__init__(parent or _fallback)
        self.setWindowTitle("Nominal Holding")
        self.setObjectName("HoldingDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._map_tool = None
        self._prev_tool = None
        self.tool_manager = None
        self.origin_point = None
        self.last_params = None
        self.run_history: list[dict] = []
        self._layer_manager = HoldingLayerManager()

        self._build_ui()
        self.show_menu()

    def showEvent(self, event):
        self.show_menu()
        super().showEvent(event)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        container.setStyleSheet("font-family: 'Segoe UI'; font-size: 9pt;")

        self.stack = QStackedWidget(container)

        # ---- Menu page ----
        self.page_menu = QWidget()
        menu_layout = QVBoxLayout(self.page_menu)
        menu_layout.setAlignment(Qt.AlignTop)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(8)

        menu_label = QLabel("Nominal Holdings")
        menu_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        menu_layout.addWidget(menu_label)

        self.list_holdings = QtWidgets.QListWidget()
        self.list_holdings.setStyleSheet(
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #e0e0e0; }\n"
            "QListWidget::item:selected { background-color: #fce4ec; color: black; }\n"
            "QListWidget::item:hover { background-color: #f5f5f5; }"
        )
        self.list_holdings.setMinimumHeight(200)
        self.list_holdings.setMaximumHeight(260)
        self.list_holdings.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_holdings.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_holdings.customContextMenuRequested.connect(self._on_list_context_menu)
        self._rename_shortcut = QShortcut(QKeySequence(Qt.Key_F2), self.list_holdings)
        self._rename_shortcut.activated.connect(self._rename_selected)

        grp_list = QGroupBox("Created in this session")
        grp_list_layout = QVBoxLayout(grp_list)
        grp_list_layout.setContentsMargins(8, 8, 8, 8)
        grp_list_layout.setSpacing(6)
        grp_list_layout.addWidget(self.list_holdings)

        menu_buttons = QHBoxLayout()
        menu_buttons.setSpacing(6)
        self.btn_new = QPushButton("+ New Holding")
        self.btn_new.setMinimumHeight(35)
        self.btn_new.setStyleSheet("background-color: #CC00CC; color: white; font-weight: bold;")
        self.btn_run_selected = QPushButton("Re-run")
        self.btn_run_selected.setMinimumHeight(35)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setMinimumHeight(35)
        self.btn_delete.setStyleSheet("background-color: #f44336; color: white;")
        self.btn_run_selected.setEnabled(False)
        self.btn_delete.setEnabled(False)

        self.btn_new.clicked.connect(self._on_new_clicked)
        self.btn_run_selected.clicked.connect(self._on_run_selected)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        menu_buttons.addWidget(self.btn_new)
        menu_buttons.addWidget(self.btn_run_selected)
        menu_buttons.addWidget(self.btn_delete)
        grp_list_layout.addLayout(menu_buttons)

        menu_layout.addWidget(grp_list)
        self._refresh_history()
        self.stack.addWidget(self.page_menu)

        # ---- Form page ----
        self.page_form = QWidget()
        form_layout = QVBoxLayout(self.page_form)
        form_layout.setAlignment(Qt.AlignTop)
        form_layout.addLayout(self._build_form_fields())

        buttons = QHBoxLayout()
        self.btn_run = QPushButton("Create Holding")
        self.btn_run.setMinimumHeight(32)
        self.btn_run.setStyleSheet("background-color: #CC00CC; color: white; font-weight: bold;")
        btn_back = QPushButton("← Back")
        btn_back.setMinimumHeight(32)
        self.btn_run.clicked.connect(self._on_run)
        btn_back.clicked.connect(self.show_menu)
        buttons.addStretch(1)
        buttons.addWidget(btn_back)
        buttons.addWidget(self.btn_run)
        form_layout.addLayout(buttons)
        self.stack.addWidget(self.page_form)

        self.stack.setCurrentWidget(self.page_menu)
        layout.addWidget(self.stack)
        layout.setAlignment(self.stack, Qt.AlignTop)
        container.setLayout(layout)
        self.setWidget(container)

    def _build_form_fields(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)

        title = QLabel("Nominal Holding")
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(title)

        # ── Fix point ────────────────────────────────────────────────
        grp_fix = QGroupBox("Fix point")
        form_fix = QFormLayout(grp_fix)
        form_fix.setHorizontalSpacing(6)
        form_fix.setVerticalSpacing(4)
        form_fix.setContentsMargins(6, 6, 6, 6)

        self.line_fix = QLineEdit()
        self.line_fix.setReadOnly(True)
        self.line_fix.setPlaceholderText("Click 'Select on map'…")
        fix_btn = QPushButton("Select on map")
        fix_btn.clicked.connect(self._pick_fix)
        fix_row = QHBoxLayout()
        fix_row.addWidget(self.line_fix)
        fix_row.addWidget(fix_btn)
        fix_container = QWidget()
        fix_container.setLayout(fix_row)
        form_fix.addRow("Fix", fix_container)
        layout.addWidget(grp_fix)

        # ── Flight parameters ─────────────────────────────────────────
        grp_params = QGroupBox("Parameters")
        form_params = QFormLayout(grp_params)
        form_params.setHorizontalSpacing(6)
        form_params.setVerticalSpacing(4)
        form_params.setContentsMargins(6, 6, 6, 6)

        self.line_name = QLineEdit()
        self.line_name.setPlaceholderText("e.g. Holding 01")
        form_params.addRow("Name", self.line_name)

        form_params.addRow(
            "Inbound track (°)",
            self._spin_field("track", QDoubleSpinBox, 0.0, 360.0, 180.0, 1.0, decimals=1),
        )

        turn_w = QWidget()
        turn_lay = QHBoxLayout(turn_w)
        turn_lay.setContentsMargins(0, 0, 0, 0)
        self.radio_r = QRadioButton("Right (R)")
        self.radio_l = QRadioButton("Left (L)")
        self.radio_r.setChecked(True)
        self._turn_group = QButtonGroup(self)
        self._turn_group.addButton(self.radio_r)
        self._turn_group.addButton(self.radio_l)
        turn_lay.addWidget(self.radio_r)
        turn_lay.addWidget(self.radio_l)
        form_params.addRow("Turn direction", turn_w)

        form_params.addRow(
            "IAS (kt)",
            self._spin_field("ias", QDoubleSpinBox, 50.0, 600.0, 195.0, 5.0),
        )
        form_params.addRow(
            "Altitude (ft)",
            self._spin_field("alt", QDoubleSpinBox, 0.0, 50000.0, 10000.0, 500.0),
        )
        form_params.addRow(
            "ISA var (°C)",
            self._spin_field("isa", QDoubleSpinBox, -50.0, 50.0, 0.0, 1.0),
        )
        form_params.addRow(
            "Bank angle (°)",
            self._spin_field("bank", QDoubleSpinBox, 5.0, 45.0, 25.0, 1.0),
        )
        form_params.addRow(
            "Leg time (min)",
            self._spin_field("leg", QDoubleSpinBox, 0.5, 4.0, 1.0, 0.5, decimals=1),
        )
        layout.addWidget(grp_params)

        # ── Computed values (live preview) ───────────────────────────
        grp_computed = QGroupBox("Computed values")
        form_comp = QFormLayout(grp_computed)
        form_comp.setHorizontalSpacing(6)
        form_comp.setVerticalSpacing(4)
        form_comp.setContentsMargins(6, 6, 6, 6)

        self.lbl_tas = QLabel("—")
        self.lbl_radius = QLabel("—")
        self.lbl_leg_nm = QLabel("—")
        form_comp.addRow("TAS", self.lbl_tas)
        form_comp.addRow("Radius", self.lbl_radius)
        form_comp.addRow("Leg distance", self.lbl_leg_nm)
        layout.addWidget(grp_computed)

        # Connect live preview updates
        self.radio_r.toggled.connect(self._update_computed)
        for attr in ("track", "ias", "alt", "isa", "bank", "leg"):
            w = getattr(self, f"dspin_{attr}", None)
            if w:
                w.valueChanged.connect(self._update_computed)

        self._update_computed()

        _sp_min = getattr(QSizePolicy, "Minimum", None) or QSizePolicy.Policy.Minimum
        _sp_fixed = getattr(QSizePolicy, "Fixed", None) or QSizePolicy.Policy.Fixed
        layout.addSpacerItem(QSpacerItem(20, 10, _sp_min, _sp_fixed))
        return layout

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------

    def _spin_field(self, attr, cls, minv, maxv, default, step, decimals=None):
        if cls is QDoubleSpinBox:
            box = QDoubleSpinBox()
            if decimals is not None:
                box.setDecimals(decimals)
        else:
            box = QSpinBox()
        box.setRange(minv, maxv)
        box.setSingleStep(step)
        box.setValue(default)
        setattr(self, f"dspin_{attr}", box)
        return box

    # ------------------------------------------------------------------
    # Menu / form navigation
    # ------------------------------------------------------------------

    def show_menu(self):
        self._restore_map_tool()
        self.stack.setCurrentWidget(self.page_menu)
        self._update_buttons()

    def show_form(self):
        self.stack.setCurrentWidget(self.page_form)

    def _on_new_clicked(self):
        self._reset_form()
        self.show_form()

    def _reset_form(self):
        next_idx = len(self.run_history) + 1
        self.line_name.setText(f"Holding {next_idx:02d}")
        self.dspin_track.setValue(180.0)
        self.dspin_ias.setValue(195.0)
        self.dspin_alt.setValue(10000.0)
        self.dspin_isa.setValue(0.0)
        self.dspin_bank.setValue(25.0)
        self.dspin_leg.setValue(1.0)
        self.radio_r.setChecked(True)
        self.origin_point = None
        self.line_fix.clear()
        self._update_computed()

    def _update_buttons(self):
        has = bool(self.run_history)
        self.btn_run_selected.setEnabled(has)
        self.btn_delete.setEnabled(has)

    # ------------------------------------------------------------------
    # History list
    # ------------------------------------------------------------------

    def _refresh_history(self):
        self.list_holdings.clear()
        if not self.run_history:
            item = QtWidgets.QListWidgetItem(
                "No holdings created yet. Click '+ New Holding' to start."
            )
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list_holdings.addItem(item)
            self._update_buttons()
            return
        for idx, params in enumerate(self.run_history):
            name = params.get("name") or f"Holding {idx + 1:02d}"
            turn = params.get("turn", "R")
            track = params.get("inbound_track", 0)
            ias = params.get("ias_kt", 195)
            alt = params.get("altitude_ft", 10000)
            display = f"{name}  —  Track {int(track)}° / Turn {turn} / {int(ias)} kt / {int(alt)} ft"
            item = QtWidgets.QListWidgetItem(display)
            item.setData(Qt.UserRole, idx)
            self.list_holdings.addItem(item)

    def _on_selection_changed(self):
        self._update_buttons()

    def _selected_params(self) -> dict | None:
        items = self.list_holdings.selectedItems()
        if not items:
            return None
        idx = items[0].data(Qt.UserRole)
        if idx is None:
            return None
        try:
            return self.run_history[idx]
        except IndexError:
            return None

    def _on_run_selected(self):
        params = self._selected_params()
        if not params:
            return
        try:
            self._run_params(params)
        except Exception as e:
            try:
                iface.messageBar().pushCritical("qAeroChart", f"Holding error: {e}")
            except Exception:
                print(f"Holding ERROR: {e}")

    def _on_delete_selected(self):
        items = self.list_holdings.selectedItems()
        if not items:
            return
        idx = items[0].data(Qt.UserRole)
        if idx is not None:
            try:
                self.run_history.pop(idx)
            except IndexError:
                pass
        self._refresh_history()
        self._update_buttons()

    def _rename_selected(self):
        params = self._selected_params()
        if not params:
            iface.messageBar().pushMessage(
                "qAeroChart", "Select a holding to rename.",
                level=MsgLevel.Warning, duration=3,
            )
            return
        current_name = params.get("name") or "Holding"
        new_name, ok = QInputDialog.getText(
            self, "Rename Holding", "New name:", text=current_name
        )
        if not ok:
            return
        new_name = (new_name or "").strip()
        if not new_name:
            iface.messageBar().pushMessage(
                "qAeroChart", "Name cannot be empty.",
                level=MsgLevel.Warning, duration=3,
            )
            return
        params["name"] = new_name
        self._refresh_history()

    def _on_list_context_menu(self, pos):
        params = self._selected_params()
        if not params:
            return
        menu = QMenu(self)
        act_rename = QAction("Rename… (F2)", self)
        act_rename.triggered.connect(self._rename_selected)
        act_delete = QAction("Delete", self)
        act_delete.triggered.connect(self._on_delete_selected)
        menu.addAction(act_rename)
        menu.addSeparator()
        menu.addAction(act_delete)
        (menu.exec_ if hasattr(menu, 'exec_') else menu.exec)(self.list_holdings.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Live computed-values preview (in the form)
    # ------------------------------------------------------------------

    def _update_computed(self):
        try:
            r = build_holding(self._collect_params(fix_x=0.0, fix_y=0.0))
            self.lbl_tas.setText(f"{r.tas_kt:.1f} kt")
            self.lbl_radius.setText(f"{r.radius_nm:.3f} NM")
            self.lbl_leg_nm.setText(f"{r.leg_nm:.2f} NM")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Map picker with canvas rubber-band preview
    # ------------------------------------------------------------------

    def _pick_fix(self):
        from .tools.profile_point_tool import ProfilePointToolManager
        canvas = iface.mapCanvas()
        self._restore_map_tool()
        if not self.tool_manager:
            self.tool_manager = ProfilePointToolManager(canvas, iface)
        tool = self.tool_manager.create_tool()
        if hasattr(tool, "set_preview_generator"):
            tool.set_preview_generator(self._generate_holding_preview)
        try:
            tool.originSelected.disconnect(self._on_fix_selected)
        except Exception:
            pass
        tool.originSelected.connect(self._on_fix_selected)
        self.tool_manager.activate_tool()

    def _on_fix_selected(self, point: QgsPointXY, _btn=None):
        self.origin_point = point
        self.line_fix.setText(f"{point.x():.3f}, {point.y():.3f}")
        self._restore_map_tool()

    def _restore_map_tool(self):
        if self.tool_manager:
            try:
                self.tool_manager.deactivate_tool()
            except Exception:
                pass
        self._map_tool = None
        self._prev_tool = None

    def _generate_holding_preview(self, hover_point: QgsPointXY) -> dict:
        """Return the racetrack polyline for the rubber-band canvas preview."""
        try:
            from qgis.core import QgsCircularString, QgsPoint as _QgsPoint

            params = self._collect_params(fix_x=hover_point.x(), fix_y=hover_point.y())
            result = build_holding(params)

            all_pts: list[QgsPointXY] = []
            for seg_type, pts in result.segments:
                qpts = [_QgsPoint(p.x, p.y) for p in pts]
                if seg_type == "arc":
                    cs = QgsCircularString()
                    cs.setPoints(qpts)
                    line = cs.curveToLine()
                    for i in range(line.numPoints()):
                        pt = line.pointN(i)
                        all_pts.append(QgsPointXY(pt.x(), pt.y()))
                else:
                    for p in pts:
                        all_pts.append(QgsPointXY(p.x, p.y))

            # Close the racetrack loop for a clean polygon-like preview
            if all_pts and (all_pts[0].x() != all_pts[-1].x()
                            or all_pts[0].y() != all_pts[-1].y()):
                all_pts.append(all_pts[0])

            return {
                "profile_line": all_pts,
                "baseline": [],
                "tick_segments": [],
                "grid_segments": [],
                "tick_labels": [],
            }
        except Exception:
            return {"profile_line": [], "tick_segments": [], "tick_labels": []}

    # ------------------------------------------------------------------
    # Collect params / run
    # ------------------------------------------------------------------

    def _collect_params(self, fix_x: float = 0.0, fix_y: float = 0.0) -> HoldingParameters:
        return HoldingParameters(
            fix_x=fix_x,
            fix_y=fix_y,
            inbound_track=self.dspin_track.value(),
            turn="L" if self.radio_l.isChecked() else "R",
            ias_kt=self.dspin_ias.value(),
            altitude_ft=self.dspin_alt.value(),
            isa_var=self.dspin_isa.value(),
            bank_deg=self.dspin_bank.value(),
            leg_min=self.dspin_leg.value(),
        )

    def _run_params(self, params: dict):
        fix = params.get("_fix")
        if fix is None:
            iface.messageBar().pushMessage(
                "qAeroChart", "No fix point stored for this holding.",
                level=MsgLevel.Warning, duration=4,
            )
            return
        hp = HoldingParameters(
            fix_x=fix["x"], fix_y=fix["y"],
            inbound_track=params["inbound_track"],
            turn=params["turn"],
            ias_kt=params["ias_kt"],
            altitude_ft=params["altitude_ft"],
            isa_var=params["isa_var"],
            bank_deg=params["bank_deg"],
            leg_min=params["leg_min"],
        )
        result = build_holding(hp)
        layer = self._layer_manager.get_or_create_layer(iface)
        self._layer_manager.add_holding(layer, hp, result)
        try:
            _ml = getattr(__import__("qgis.core", fromlist=["Qgis"]).Qgis,
                          "MessageLevel", None)
            _success = getattr(_ml, "Success", 3) if _ml else 3
            iface.messageBar().pushMessage(
                "qAeroChart",
                f"Holding drawn — TAS {result.tas_kt:.1f} kt | "
                f"Radius {result.radius_nm:.3f} NM | Leg {result.leg_nm:.2f} NM",
                level=_success, duration=5,
            )
        except Exception:
            pass

    def _on_run(self):
        self._restore_map_tool()
        if self.origin_point is None:
            iface.messageBar().pushMessage(
                "qAeroChart", "Select a fix point on the map first.",
                level=MsgLevel.Warning, duration=4,
            )
            return

        hp = self._collect_params(
            fix_x=self.origin_point.x(),
            fix_y=self.origin_point.y(),
        )
        try:
            result = build_holding(hp)
            layer = self._layer_manager.get_or_create_layer(iface)
            self._layer_manager.add_holding(layer, hp, result)

            # Store in session history
            name = self.line_name.text().strip() or f"Holding {len(self.run_history) + 1:02d}"
            entry = {
                "name": name,
                "inbound_track": hp.inbound_track,
                "turn": hp.turn,
                "ias_kt": hp.ias_kt,
                "altitude_ft": hp.altitude_ft,
                "isa_var": hp.isa_var,
                "bank_deg": hp.bank_deg,
                "leg_min": hp.leg_min,
                "_fix": {"x": self.origin_point.x(), "y": self.origin_point.y()},
            }
            self.run_history.append(entry)
            self.last_params = entry

            try:
                _Qgis = __import__("qgis.core", fromlist=["Qgis"]).Qgis
                _ml = getattr(_Qgis, "MessageLevel", None)
                _success = getattr(_ml, "Success", 3) if _ml else 3
                iface.messageBar().pushMessage(
                    "qAeroChart",
                    f"Holding drawn — TAS {result.tas_kt:.1f} kt | "
                    f"Radius {result.radius_nm:.3f} NM | Leg {result.leg_nm:.2f} NM",
                    level=_success, duration=5,
                )
            except Exception:
                pass

            self._refresh_history()
            self._update_buttons()
            self.show_menu()

        except Exception as e:
            try:
                iface.messageBar().pushCritical("qAeroChart", f"Holding error: {e}")
            except Exception:
                print(f"Holding ERROR: {e}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._restore_map_tool()
        super().closeEvent(event)
