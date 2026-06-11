# -*- coding: utf-8 -*-
"""Horizontal Scale dock widget — mirrors VerticalScaleDockWidget (Issue #69)."""

from qgis.PyQt import QtWidgets
from .utils.qt_compat import Qt
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
    QSpacerItem,
    QSizePolicy,
    QInputDialog,
    QShortcut,
)
from qgis.PyQt.QtGui import QKeySequence
from qgis.core import QgsPointXY, QgsPoint
from .utils.qt_compat import MsgLevel
from qgis.utils import iface
from .core.horizontal_scale_manager import HorizontalScaleManager


class HorizontalScaleDockWidget(QtWidgets.QDockWidget):
    """Dock widget for creating and managing horizontal scale bars (Issue #69)."""

    def __init__(self, parent=None):
        _fallback = iface.mainWindow() if iface else None
        super().__init__(parent or _fallback)
        self.setWindowTitle("Horizontal Scale")
        self.setObjectName("HorizontalScaleDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._map_tool = None
        self._prev_tool = None
        self.tool_manager = None
        self.origin_point = None
        self.last_params = None
        self.run_history: list[dict] = []
        self._current_mode = "new"
        self.current_scale_id = None
        self.scale_manager = HorizontalScaleManager()
        self._rename_shortcut = None

        self._build_ui()
        self._load_persisted_scales()
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

        menu_label = QLabel("Horizontal Scales")
        menu_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        menu_layout.addWidget(menu_label)

        self.list_scales = QtWidgets.QListWidget()
        self.list_scales.setStyleSheet(
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #e0e0e0; }\n"
            "QListWidget::item:selected { background-color: #e3f2fd; color: black; }\n"
            "QListWidget::item:hover { background-color: #f5f5f5; }"
        )
        try:
            self.list_scales.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list_scales.customContextMenuRequested.connect(self._on_list_context_menu)
            self._rename_shortcut = QShortcut(QKeySequence(Qt.Key_F2), self.list_scales)
            self._rename_shortcut.activated.connect(self._rename_selected)
        except Exception:
            pass
        self.list_scales.setMinimumHeight(220)
        self.list_scales.setMaximumHeight(260)
        self.list_scales.itemSelectionChanged.connect(self._on_history_selection_changed)
        self.list_scales.itemDoubleClicked.connect(self._on_edit_clicked)

        grp_list = QGroupBox("Saved scales")
        grp_list_layout = QVBoxLayout(grp_list)
        grp_list_layout.setContentsMargins(8, 8, 8, 8)
        grp_list_layout.setSpacing(6)
        grp_list_layout.addWidget(self.list_scales)

        menu_buttons = QHBoxLayout()
        menu_buttons.setSpacing(6)
        self.btn_new = QPushButton("+ New Scale")
        self.btn_new.setMinimumHeight(35)
        self.btn_new.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_run_selected = QPushButton("Run Selected")
        self.btn_run_selected.setMinimumHeight(35)
        self.btn_edit = QPushButton("Edit Selected")
        self.btn_edit.setMinimumHeight(35)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setMinimumHeight(35)
        self.btn_delete.setStyleSheet("background-color: #f44336; color: white;")
        self.btn_edit.setEnabled(False)
        self.btn_run_selected.setEnabled(False)
        self.btn_delete.setEnabled(False)

        self.btn_new.clicked.connect(self._on_new_clicked)
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        self.btn_run_selected.clicked.connect(self._on_run_selected)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        menu_buttons.addWidget(self.btn_new)
        menu_buttons.addWidget(self.btn_run_selected)
        menu_buttons.addWidget(self.btn_edit)
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
        btn_run = QPushButton("Run")
        btn_close = QPushButton("Close")
        btn_run.clicked.connect(self._on_run)
        btn_close.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(btn_run)
        buttons.addWidget(btn_close)
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

        title = QLabel("Horizontal Scale")
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(title)

        # Origin & Orientation
        grp_origin = QGroupBox("Origin & Orientation")
        form_origin = QFormLayout(grp_origin)
        form_origin.setHorizontalSpacing(6)
        form_origin.setVerticalSpacing(4)
        form_origin.setContentsMargins(6, 6, 6, 6)

        self.line_origin = QLineEdit()
        self.line_origin.setReadOnly(True)
        origin_btn = QPushButton("Select on map")
        origin_btn.clicked.connect(self._pick_origin)
        origin_row = QHBoxLayout()
        origin_row.addWidget(self.line_origin)
        origin_row.addWidget(origin_btn)
        origin_container = QWidget()
        origin_container.setLayout(origin_row)
        form_origin.addRow("Origin point (0)", origin_container)

        form_origin.addRow(
            "Azimuth (deg)",
            self._spin_field("azimuth", QSpinBox, 0, 359, 90, 5),
        )
        layout.addWidget(grp_origin)

        # Style
        grp_style = QGroupBox("Style")
        form_style = QFormLayout(grp_style)
        form_style.setHorizontalSpacing(6)
        form_style.setVerticalSpacing(4)
        form_style.setContentsMargins(6, 6, 6, 6)
        form_style.addRow("Name", self._line_field("name", "Horizontal Scale"))
        form_style.addRow(
            "Offset from guide line",
            self._spin_field("offset", QDoubleSpinBox, -5000.0, 5000.0, -50.0, 5.0, decimals=2),
        )
        form_style.addRow(
            "Tick length (map units)",
            self._spin_field("tick", QDoubleSpinBox, 1.0, 500.0, 15.0, 1.0, decimals=2),
        )
        layout.addWidget(grp_style)

        # Metre ranges
        grp_metres = QGroupBox("Metres")
        form_metres = QFormLayout(grp_metres)
        form_metres.setHorizontalSpacing(6)
        form_metres.setVerticalSpacing(4)
        form_metres.setContentsMargins(6, 6, 6, 6)
        form_metres.addRow("Right (forward, m)", self._spin_field("m_right", QSpinBox, 100, 100000, 2500, 100))
        form_metres.addRow("Left (backward, m)", self._spin_field("m_left", QSpinBox, 0, 10000, 400, 50))
        form_metres.addRow("Step right (m)", self._spin_field("m_right_step", QSpinBox, 10, 5000, 500, 50))
        form_metres.addRow("Step left (m)", self._spin_field("m_left_step", QSpinBox, 10, 1000, 100, 10))
        layout.addWidget(grp_metres)

        # Feet ranges
        grp_feet = QGroupBox("Feet")
        form_feet = QFormLayout(grp_feet)
        form_feet.setHorizontalSpacing(6)
        form_feet.setVerticalSpacing(4)
        form_feet.setContentsMargins(6, 6, 6, 6)
        form_feet.addRow("Right (forward, ft)", self._spin_field("ft_right", QSpinBox, 100, 300000, 8000, 500))
        form_feet.addRow("Left (backward, ft)", self._spin_field("ft_left", QSpinBox, 0, 30000, 1000, 100))
        form_feet.addRow("Step right (ft)", self._spin_field("ft_right_step", QSpinBox, 10, 10000, 1000, 100))
        form_feet.addRow("Step left (ft)", self._spin_field("ft_left_step", QSpinBox, 10, 2000, 100, 10))
        layout.addWidget(grp_feet)

        _sp_min = getattr(QSizePolicy, 'Minimum', None) or QSizePolicy.Policy.Minimum
        _sp_fixed = getattr(QSizePolicy, 'Fixed', None) or QSizePolicy.Policy.Fixed
        layout.addSpacerItem(QSpacerItem(20, 10, _sp_min, _sp_fixed))
        return layout

    # ------------------------------------------------------------------
    # Helpers for labeled inputs
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
        setattr(self, f"{'dspin' if isinstance(box, QDoubleSpinBox) else 'spin'}_{attr}", box)
        return box

    def _line_field(self, attr, default):
        line = QLineEdit()
        line.setText(default)
        setattr(self, f"line_{attr}", line)
        return line

    # ------------------------------------------------------------------
    # Menu / Form navigation
    # ------------------------------------------------------------------

    def show_menu(self):
        self._restore_previous_map_tool()
        self.stack.setCurrentWidget(self.page_menu)
        self._update_buttons()

    def show_form(self):
        self.stack.setCurrentWidget(self.page_form)

    def _on_new_clicked(self):
        self._current_mode = "new"
        self.current_scale_id = None
        self._reset_form_defaults()
        self.show_form()

    def _on_edit_clicked(self):
        params = self._selected_history_params() or self.last_params
        if not params:
            return
        self._current_mode = "edit"
        self.current_scale_id = params.get("id")
        self._apply_params(params)
        self.show_form()

    def _reset_form_defaults(self):
        self.line_name.setText("Horizontal Scale")
        self.dspin_offset.setValue(-50.0)
        self.dspin_tick.setValue(15.0)
        self.spin_m_right.setValue(2500)
        self.spin_m_left.setValue(400)
        self.spin_m_right_step.setValue(500)
        self.spin_m_left_step.setValue(100)
        self.spin_ft_right.setValue(8000)
        self.spin_ft_left.setValue(1000)
        self.spin_ft_right_step.setValue(1000)
        self.spin_ft_left_step.setValue(100)
        self.spin_azimuth.setValue(90)
        self.origin_point = None
        self.line_origin.clear()
        self.current_scale_id = None

    def _apply_params(self, params: dict) -> None:
        self.line_name.setText(params.get("name", "Horizontal Scale"))
        self.dspin_offset.setValue(float(params.get("offset", -50.0)))
        self.dspin_tick.setValue(float(params.get("tick_len", 15.0)))
        self.spin_m_right.setValue(int(params.get("metre_right", 2500)))
        self.spin_m_left.setValue(int(params.get("metre_left", 400)))
        self.spin_m_right_step.setValue(int(params.get("metre_right_step", 500)))
        self.spin_m_left_step.setValue(int(params.get("metre_left_step", 100)))
        self.spin_ft_right.setValue(int(params.get("ft_right", 8000)))
        self.spin_ft_left.setValue(int(params.get("ft_left", 1000)))
        self.spin_ft_right_step.setValue(int(params.get("ft_right_step", 1000)))
        self.spin_ft_left_step.setValue(int(params.get("ft_left_step", 100)))
        self.spin_azimuth.setValue(int(params.get("angle", 90)))
        bp = params.get("basepoint")
        self.origin_point = bp
        if bp:
            try:
                self.line_origin.setText(f"{bp.x():.3f}, {bp.y():.3f}")
            except Exception:
                self.line_origin.setText(str(bp))
        else:
            self.line_origin.clear()
        self.current_scale_id = params.get("id")

    def _update_buttons(self) -> None:
        try:
            has = bool(self.run_history)
            self.btn_edit.setEnabled(has)
            self.btn_run_selected.setEnabled(has)
            self.btn_delete.setEnabled(has)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_persisted_scales(self) -> None:
        try:
            stored = self.scale_manager.load_all_configs()
            self.run_history = [self._from_storable(p) for p in stored]
            self.last_params = self.run_history[-1] if self.run_history else None
            self._refresh_history()
            self._update_buttons()
        except Exception:
            pass

    def _to_storable(self, params: dict) -> dict:
        data = dict(params)
        bp = data.get("basepoint")
        try:
            if bp is not None:
                data["basepoint"] = {"x": float(bp.x()), "y": float(bp.y())}
        except Exception:
            data["basepoint"] = None
        return data

    def _from_storable(self, params: dict) -> dict:
        data = dict(params)
        bp = data.get("basepoint")
        try:
            if isinstance(bp, dict) and "x" in bp and "y" in bp:
                data["basepoint"] = QgsPoint(float(bp["x"]), float(bp["y"]))
        except Exception:
            data["basepoint"] = None
        return data

    def _replace_history(self, params: dict) -> None:
        sid = params.get("id")
        if not sid:
            self.run_history.append(params)
            return
        for idx, entry in enumerate(self.run_history):
            if entry.get("id") == sid:
                self.run_history[idx] = params
                return
        self.run_history.append(params)

    # ------------------------------------------------------------------
    # List actions
    # ------------------------------------------------------------------

    def _on_run_selected(self) -> None:
        params = self._selected_history_params()
        if not params:
            return
        sid = params.get("id")
        if sid:
            cfg = self.scale_manager.get_config(sid)
            if cfg:
                params = self._from_storable(cfg)
        try:
            self._run_params(params)
            self.last_params = params
        except Exception as e:
            try:
                iface.messageBar().pushCritical("Horizontal Scale", f"Error: {e}")
            except Exception:
                print(f"Horizontal Scale ERROR: {e}")

    def _on_delete_selected(self) -> None:
        params = self._selected_history_params()
        if not params:
            return
        sid = params.get("id")
        if sid:
            self.scale_manager.delete(sid)
        self.run_history = [p for p in self.run_history if p.get("id") != sid]
        self.current_scale_id = None
        self._refresh_history()
        self._update_buttons()

    def _on_list_context_menu(self, pos) -> None:
        if not self.run_history:
            return
        menu = QtWidgets.QMenu(self.list_scales)
        act_rename = menu.addAction("Rename... (F2)")
        act_delete = menu.addAction("Delete")
        action = (menu.exec_ if hasattr(menu, 'exec_') else menu.exec)(
            self.list_scales.mapToGlobal(pos)
        )
        if action == act_rename:
            self._rename_selected()
        elif action == act_delete:
            self._on_delete_selected()

    def _rename_selected(self) -> None:
        params = self._selected_history_params()
        if not params:
            iface.messageBar().pushMessage(
                "No Selection", "Select a scale to rename.",
                level=MsgLevel.Warning, duration=3,
            )
            return
        current_name = params.get("name", "Horizontal Scale")
        new_name, ok = QInputDialog.getText(self, "Rename Scale", "New name:", text=current_name)
        if not ok:
            return
        new_name = (new_name or "").strip()
        if not new_name:
            iface.messageBar().pushMessage(
                "Invalid Name", "Name cannot be empty.",
                level=MsgLevel.Warning, duration=3,
            )
            return
        params["name"] = new_name
        sid = params.get("id")
        if sid:
            self.scale_manager.rename(sid, new_name)
        self._replace_history(params)
        self._refresh_history()

    def _refresh_history(self) -> None:
        self.list_scales.clear()
        if not self.run_history:
            item = QtWidgets.QListWidgetItem(
                "No horizontal scales created yet. Click '+ New Scale' to start."
            )
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list_scales.addItem(item)
            self.current_scale_id = None
            self._update_buttons()
            return
        for idx, params in enumerate(self.run_history):
            name = params.get("name", "Horizontal Scale")
            az = params.get("angle")
            display = f"{name} (az {int(az) if az is not None else '-'} deg)"
            item = QtWidgets.QListWidgetItem(display)
            item.setData(Qt.UserRole, params.get("id", idx))
            self.list_scales.addItem(item)

    def _on_history_selection_changed(self) -> None:
        sel = self._selected_history_params()
        self.current_scale_id = sel.get("id") if sel else None
        self._update_buttons()

    def _selected_history_params(self) -> dict | None:
        selected = self.list_scales.selectedItems()
        if not selected:
            return None
        sid = selected[0].data(Qt.UserRole)
        if sid is None:
            return None
        for entry in self.run_history:
            if entry.get("id") == sid:
                return entry
        return None

    # ------------------------------------------------------------------
    # Map picker
    # ------------------------------------------------------------------

    def _pick_origin(self) -> None:
        try:
            from .tools.profile_point_tool import ProfilePointToolManager
        except ImportError:
            return
        canvas = iface.mapCanvas()
        self._restore_previous_map_tool()
        if not self.tool_manager:
            self.tool_manager = ProfilePointToolManager(canvas, iface)
        tool = self.tool_manager.create_tool()
        if hasattr(tool, 'set_preview_generator'):
            tool.set_preview_generator(self._generate_scale_preview)
        try:
            tool.originSelected.disconnect(self._on_origin_selected)
        except Exception:
            pass
        tool.originSelected.connect(self._on_origin_selected)
        self.tool_manager.activate_tool()

    def _on_origin_selected(self, point: QgsPointXY, _btn=None) -> None:
        self.origin_point = point
        self.line_origin.setText(f"{point.x():.3f}, {point.y():.3f}")
        self._restore_previous_map_tool()

    def _restore_previous_map_tool(self) -> None:
        if self.tool_manager:
            try:
                self.tool_manager.deactivate_tool()
            except Exception:
                pass
        if self._map_tool:
            try:
                self._map_tool.canvasClicked.disconnect(self._on_origin_selected)
            except Exception:
                pass
        try:
            if self._prev_tool:
                iface.mapCanvas().setMapTool(self._prev_tool)
        except Exception:
            pass
        self._map_tool = None
        self._prev_tool = None

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _collect_params(self) -> dict:
        return {
            "name": self.line_name.text().strip() or "Horizontal Scale",
            "offset": float(self.dspin_offset.value()),
            "tick_len": float(self.dspin_tick.value()),
            "metre_right": int(self.spin_m_right.value()),
            "metre_left": int(self.spin_m_left.value()),
            "metre_right_step": int(self.spin_m_right_step.value()),
            "metre_left_step": int(self.spin_m_left_step.value()),
            "ft_right": int(self.spin_ft_right.value()),
            "ft_left": int(self.spin_ft_left.value()),
            "ft_right_step": int(self.spin_ft_right_step.value()),
            "ft_left_step": int(self.spin_ft_left_step.value()),
            "basepoint": self.origin_point,
            "angle": float(self.spin_azimuth.value()),
        }

    def _run_params(self, params: dict) -> None:
        """Execute the scale generation using the standalone script."""
        from .scripts.Horizontal_Scale import run_horizontal_scale
        run_horizontal_scale(**params)

    def _on_run(self) -> None:
        self._restore_previous_map_tool()
        params = self._collect_params()
        if self.current_scale_id:
            params["id"] = self.current_scale_id
        try:
            self._run_params(params)
            storable = self._to_storable(params)
            if params.get("id"):
                self.scale_manager.update(params["id"], storable)
                self._replace_history(params)
            else:
                sid = self.scale_manager.save_new(storable)
                params["id"] = sid
                self.run_history.append(params)
            self.last_params = params
            self._refresh_history()
            self._update_buttons()
            self.show_menu()
        except Exception as e:
            try:
                iface.messageBar().pushCritical("Horizontal Scale", f"Error: {e}")
            except Exception:
                print(f"Horizontal Scale ERROR: {e}")

    # ------------------------------------------------------------------
    # Live map preview
    # ------------------------------------------------------------------

    def _generate_scale_preview(self, origin_point):
        """Generate tick segments and labels for live canvas preview while picking origin."""
        _FT_TO_M = 0.3048
        try:
            angle = float(self.spin_azimuth.value())
            offset = float(self.dspin_offset.value())
            tick_len = float(self.dspin_tick.value())
            m_right = int(self.spin_m_right.value())
            m_left = int(self.spin_m_left.value())
            m_right_step = int(self.spin_m_right_step.value())
            m_left_step = int(self.spin_m_left_step.value())
            ft_right = int(self.spin_ft_right.value())
            ft_left = int(self.spin_ft_left.value())
            ft_right_step = int(self.spin_ft_right_step.value())
            ft_left_step = int(self.spin_ft_left_step.value())

            half_sp = tick_len * 0.5
            lbl_off = tick_len * 1.3
            small_len = tick_len * 0.45

            bar_centre = QgsPoint(origin_point).project(
                abs(offset), angle + (90.0 if offset >= 0 else -90.0)
            )
            base_m = bar_centre.project(half_sp, angle - 90.0)
            base_f = bar_centre.project(half_sp, angle + 90.0)

            tick_segments = []
            tick_labels = []

            def fwd(base, dist):
                return base.project(dist, angle)

            def bwd(base, dist):
                return base.project(dist, angle + 180.0)

            # ---- Metre rail (upper) ----
            m_pos_pts, m_neg_pts = [], []
            for v in range(0, m_right + 1, m_right_step):
                pt = fwd(base_m, float(v))
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(tick_len, angle - 90.0))])
                m_pos_pts.append(QgsPointXY(pt))
                tick_labels.append({"pos": QgsPointXY(pt.project(lbl_off, angle - 90.0)), "text": str(v)})

            for v in range(m_left_step, m_left + 1, m_left_step):
                pt = bwd(base_m, float(v))
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(tick_len, angle - 90.0))])
                m_neg_pts.append(QgsPointXY(pt))
                tick_labels.append({"pos": QgsPointXY(pt.project(lbl_off, angle - 90.0)), "text": str(v)})

            # Minor ticks — metre rail
            for v in range(m_right_step // 2, m_right, m_right_step):
                pt = fwd(base_m, float(v))
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(small_len, angle - 90.0))])
            for v in range(m_left_step // 2, m_left, m_left_step):
                pt = bwd(base_m, float(v))
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(small_len, angle - 90.0))])

            # "METRES" header
            ctr_m = fwd(base_m, m_right / 2.0)
            tick_labels.append({"pos": QgsPointXY(ctr_m.project(lbl_off * 1.8, angle - 90.0)), "text": "METRES"})

            # ---- Feet rail (lower) ----
            ft_pos_pts, ft_neg_pts = [], []
            for v in range(0, ft_right + 1, ft_right_step):
                pt = fwd(base_f, v * _FT_TO_M)
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(tick_len, angle + 90.0))])
                ft_pos_pts.append(QgsPointXY(pt))
                tick_labels.append({"pos": QgsPointXY(pt.project(lbl_off, angle + 90.0)), "text": str(v)})

            for v in range(ft_left_step, ft_left + 1, ft_left_step):
                pt = bwd(base_f, v * _FT_TO_M)
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(tick_len, angle + 90.0))])
                ft_neg_pts.append(QgsPointXY(pt))
                tick_labels.append({"pos": QgsPointXY(pt.project(lbl_off, angle + 90.0)), "text": str(v)})

            # Minor ticks — feet rail
            for v in range(ft_right_step // 2, ft_right, ft_right_step):
                pt = fwd(base_f, v * _FT_TO_M)
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(small_len, angle + 90.0))])
            for v in range(ft_left_step // 2, ft_left, ft_left_step):
                pt = bwd(base_f, v * _FT_TO_M)
                tick_segments.append([QgsPointXY(pt), QgsPointXY(pt.project(small_len, angle + 90.0))])

            # "FEET" header
            ctr_f = fwd(base_f, ft_right * _FT_TO_M / 2.0)
            tick_labels.append({"pos": QgsPointXY(ctr_f.project(lbl_off * 1.8, angle + 90.0)), "text": "FEET"})

            # Spine extents
            m_left_end = bwd(base_m, float(m_left)) if m_left > 0 else fwd(base_m, 0.0)
            m_right_end = fwd(base_m, float(m_right))
            f_left_end = bwd(base_f, ft_left * _FT_TO_M) if ft_left > 0 else fwd(base_f, 0.0)
            f_right_end = fwd(base_f, ft_right * _FT_TO_M)

            profile_line = [QgsPointXY(m_left_end), QgsPointXY(m_right_end)]
            feet_line = [QgsPointXY(f_left_end), QgsPointXY(f_right_end)]

            return {
                "profile_line": profile_line,
                "baseline": [profile_line, feet_line],
                "tick_segments": tick_segments,
                "grid_segments": [],
                "tick_labels": tick_labels,
            }
        except Exception:
            return {"profile_line": [], "tick_segments": [], "tick_labels": []}

    def closeEvent(self, event):
        self._restore_previous_map_tool()
        super().closeEvent(event)
