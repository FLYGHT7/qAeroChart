# -*- coding: utf-8 -*-
"""Vertical Scale dock widget with menu + form flow."""

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
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
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.core import QgsPointXY, QgsPoint, Qgis
from qgis.utils import iface
from .scripts.Vertical_Scale import run_vertical_scale, _scale_factor
from .tools.profile_point_tool import ProfilePointToolManager
from qgis.PyQt.QtGui import QShortcut, QKeySequence
from .vertical_scale_manager import VerticalScaleManager


class VerticalScaleDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.setWindowTitle("Vertical Scale")
        self.setObjectName("VerticalScaleDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._map_tool = None
        self._prev_tool = None
        self.tool_manager = None
        self.origin_point = None
        self.last_params = None
        self.run_history = []
        self._current_mode = "new"
        self.current_scale_id = None
        self.scale_manager = VerticalScaleManager()

        # Shortcut for rename (F2)
        try:
            self._rename_shortcut = None
        except Exception:
            pass

        self._build_ui()
        self._load_persisted_scales()
        self.show_menu()

    def showEvent(self, event):
        # Always land on the menu page when shown (aligns with profile UX)
        self.show_menu()
        super().showEvent(event)

    # ---------- UI construction ----------
    def _build_ui(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        container.setStyleSheet("font-family: 'Segoe UI'; font-size: 9pt;")

        self.stack = QStackedWidget(container)

        # Menu page: mirrors profile flow (start here, then open form)
        self.page_menu = QWidget()
        menu_layout = QVBoxLayout(self.page_menu)
        menu_layout.setAlignment(Qt.AlignTop)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(8)

        menu_label = QLabel("Vertical Scales")
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
        self.btn_new = QPushButton("➕ New Scale")
        self.btn_new.setMinimumHeight(35)
        self.btn_new.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        self.btn_run_selected = QPushButton("▶️ Run Selected")
        self.btn_run_selected.setMinimumHeight(35)

        self.btn_edit = QPushButton("✏️ Edit Selected")
        self.btn_edit.setMinimumHeight(35)

        self.btn_delete = QPushButton("🗑️ Delete")
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

        # Form page: parameters + map origin picker
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

        # default to menu page; show_menu will also enforce this
        self.stack.setCurrentWidget(self.page_menu)

        layout.addWidget(self.stack)
        layout.setAlignment(self.stack, Qt.AlignTop)
        container.setLayout(layout)
        self.setWidget(container)

    def _build_form_fields(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Title
        title = QLabel("Vertical Scale")
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
        form_origin.addRow("Origin point", origin_container)

        form_origin.addRow("Azimuth (deg)", self._spin_field("azimuth", QSpinBox, 0, 359, 90, 5))
        layout.addWidget(grp_origin)

        # Scale & Style
        grp_scale = QGroupBox("Scale")
        form_scale = QFormLayout(grp_scale)
        form_scale.setHorizontalSpacing(6)
        form_scale.setVerticalSpacing(4)
        form_scale.setContentsMargins(6, 6, 6, 6)

        form_scale.addRow("Name", self._line_field("name", "Vertical Scale"))
        form_scale.addRow("Scale denominator (1:n)", self._spin_field("scale", QSpinBox, 1000, 100000, 10000, 500))
        form_scale.addRow("Offset from guide line", self._spin_field("offset", QDoubleSpinBox, -5000.0, 5000.0, -50.0, 5.0, decimals=2))
        form_scale.addRow("Tick length", self._spin_field("tick", QDoubleSpinBox, 1.0, 200.0, 15.0, 1.0, decimals=2))
        layout.addWidget(grp_scale)

        # Ranges
        grp_ranges = QGroupBox("Ranges")
        form_ranges = QFormLayout(grp_ranges)
        form_ranges.setHorizontalSpacing(6)
        form_ranges.setVerticalSpacing(4)
        form_ranges.setContentsMargins(6, 6, 6, 6)

        form_ranges.addRow("Meters max", self._spin_field("m_max", QSpinBox, 10, 10000, 100, 5))
        form_ranges.addRow("Meters step", self._spin_field("m_step", QSpinBox, 1, 1000, 25, 1))
        form_ranges.addRow("Feet max", self._spin_field("ft_max", QSpinBox, 10, 50000, 300, 10))
        form_ranges.addRow("Feet step", self._spin_field("ft_step", QSpinBox, 1, 5000, 50, 5))
        layout.addWidget(grp_ranges)

        # Spacer to push buttons down if room
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Fixed))

        return layout

    # ---------- Helpers for labeled inputs ----------
    def _labeled_spin(self, text, attr, minv, maxv, default, step=1):
        box = QSpinBox()
        box.setRange(minv, maxv)
        box.setSingleStep(step)
        box.setValue(default)
        setattr(self, f"spin_{attr}", box)
        row = QHBoxLayout()
        row.addWidget(QLabel(text))
        row.addStretch(1)
        row.addWidget(box)
        return row

    def _labeled_dspin(self, text, attr, minv, maxv, default, step=1.0):
        box = QDoubleSpinBox()
        box.setRange(minv, maxv)
        box.setDecimals(2)
        box.setSingleStep(step)
        box.setValue(default)
        setattr(self, f"dspin_{attr}", box)
        row = QHBoxLayout()
        row.addWidget(QLabel(text))
        row.addStretch(1)
        row.addWidget(box)
        return row

    def _labeled_line(self, text, attr, default):
        line = QLineEdit()
        line.setText(default)
        setattr(self, f"line_{attr}", line)
        row = QHBoxLayout()
        row.addWidget(QLabel(text))
        row.addStretch(1)
        row.addWidget(line)
        return row

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

    # ---------- Menu/Form navigation ----------
    def show_menu(self):
        self._restore_previous_map_tool()
        self.stack.setCurrentWidget(self.page_menu)
        self._update_edit_button()

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
        self.line_name.setText("Vertical Scale")
        self.spin_scale.setValue(10000)
        self.dspin_offset.setValue(-50.0)
        self.dspin_tick.setValue(15.0)
        self.spin_m_max.setValue(100)
        self.spin_m_step.setValue(25)
        self.spin_ft_max.setValue(300)
        self.spin_ft_step.setValue(50)
        self.spin_azimuth.setValue(90)
        self.origin_point = None
        self.line_origin.clear()
        self.current_scale_id = None

    def _apply_params(self, params):
        self.line_name.setText(params.get("name", "Vertical Scale"))
        self.spin_scale.setValue(int(params.get("scale_denominator", 10000)))
        self.dspin_offset.setValue(float(params.get("offset", -50.0)))
        self.dspin_tick.setValue(float(params.get("tick_len", 15.0)))
        self.spin_m_max.setValue(int(params.get("m_max", 100)))
        self.spin_m_step.setValue(int(params.get("m_step", 25)))
        self.spin_ft_max.setValue(int(params.get("ft_max", 300)))
        self.spin_ft_step.setValue(int(params.get("ft_step", 50)))
        self.spin_azimuth.setValue(int(params.get("angle", 90)))
        bp = params.get("basepoint")
        self.current_scale_id = params.get("id")
        self.origin_point = bp
        if bp:
            self.line_origin.setText(f"{bp.x():.3f}, {bp.y():.3f}")
        else:
            self.line_origin.clear()

    def _update_edit_button(self):
        try:
            has_items = bool(self.run_history)
            self.btn_edit.setEnabled(has_items)
            self.btn_run_selected.setEnabled(has_items)
            self.btn_delete.setEnabled(has_items)
        except Exception:
            pass

    def _load_persisted_scales(self):
        try:
            stored = self.scale_manager.load_all_configs()
            self.run_history = [self._from_storable(p) for p in stored]
            self.last_params = self.run_history[-1] if self.run_history else None
            self._refresh_history()
            self._update_edit_button()
        except Exception:
            pass

    def _to_storable(self, params):
        data = dict(params)
        bp = data.get("basepoint")
        try:
            if bp is not None:
                data["basepoint"] = {"x": float(bp.x()), "y": float(bp.y())}
        except Exception:
            data["basepoint"] = None
        return data

    def _from_storable(self, params):
        data = dict(params)
        bp = data.get("basepoint")
        try:
            if isinstance(bp, dict) and "x" in bp and "y" in bp:
                data["basepoint"] = QgsPoint(float(bp.get("x", 0.0)), float(bp.get("y", 0.0)))
        except Exception:
            data["basepoint"] = None
        return data

    def _replace_history(self, params):
        sid = params.get("id")
        if not sid:
            self.run_history.append(params)
            return
        for idx, entry in enumerate(self.run_history):
            if entry.get("id") == sid:
                self.run_history[idx] = params
                return
        self.run_history.append(params)

    def _on_run_selected(self):
        params = self._selected_history_params()
        if not params:
            return
        sid = params.get("id")
        if sid:
            cfg = self.scale_manager.get_config(sid)
            if cfg:
                params = self._from_storable(cfg)
        try:
            run_vertical_scale(**params)
            self.current_scale_id = params.get("id")
            self.last_params = params
        except Exception as e:
            try:
                iface.messageBar().pushCritical("Vertical Scale", f"Error creating scale: {e}")
            except Exception:
                print(f"Vertical Scale ERROR: {e}")

    def _on_delete_selected(self):
        params = self._selected_history_params()
        if not params:
            return
        sid = params.get("id")
        if sid:
            self.scale_manager.delete(sid)
        self.run_history = [p for p in self.run_history if p.get("id") != sid]
        self.current_scale_id = None
        self._refresh_history()
        self._update_edit_button()

    def _on_list_context_menu(self, pos):
        if not self.run_history:
            return
        menu = QtWidgets.QMenu(self.list_scales)
        act_rename = menu.addAction("Rename… (F2)")
        act_delete = menu.addAction("Delete")
        action = menu.exec_(self.list_scales.mapToGlobal(pos))
        if action == act_rename:
            self._rename_selected()
        elif action == act_delete:
            self._on_delete_selected()

    def _rename_selected(self):
        params = self._selected_history_params()
        if not params:
            iface.messageBar().pushMessage(
                "No Selection",
                "Select a scale to rename.",
                level=Qgis.Warning,
                duration=3,
            )
            return
        current_name = params.get("name", "Vertical Scale")
        new_name, ok = QInputDialog.getText(self, "Rename Scale", "New name:", text=current_name)
        if not ok:
            return
        new_name = (new_name or "").strip()
        if not new_name:
            iface.messageBar().pushMessage(
                "Invalid Name",
                "Name cannot be empty.",
                level=Qgis.Warning,
                duration=3,
            )
            return
        params["name"] = new_name
        sid = params.get("id")
        if sid:
            self.scale_manager.rename(sid, new_name)
        self._replace_history(params)
        self._refresh_history()

    def _refresh_history(self):
        self.list_scales.clear()
        if not self.run_history:
            item = QtWidgets.QListWidgetItem("No vertical scales created yet. Click 'New Vertical Scale' to start.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list_scales.addItem(item)
            self.current_scale_id = None
            self._update_edit_button()
            return
        for idx, params in enumerate(self.run_history):
            name = params.get("name", "Vertical Scale")
            az = params.get("angle")
            display = f"{name} (az {int(az) if az is not None else '-'} deg)"
            item = QtWidgets.QListWidgetItem(display)
            item.setData(Qt.UserRole, params.get("id", idx))
            self.list_scales.addItem(item)

    def _on_history_selection_changed(self):
        sel = self._selected_history_params()
        self.current_scale_id = sel.get("id") if sel else None
        self._update_edit_button()

    def _selected_history_params(self):
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

    # ---------- Map picker ----------
    def _pick_origin(self):
        canvas = iface.mapCanvas()
        self._restore_previous_map_tool()

        # Use the profile point tool for live preview while hovering
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

    def _on_origin_selected(self, point: QgsPointXY, _btn=None):
        self.origin_point = point
        self.line_origin.setText(f"{point.x():.3f}, {point.y():.3f}")
        self._restore_previous_map_tool()

    def _restore_previous_map_tool(self):
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

    # ---------- Run generator ----------
    def _on_run(self):
        # Leave canvas in a sane state even if selection was cancelled
        self._restore_previous_map_tool()
        params = {
            "name": self.line_name.text().strip() or "Vertical Scale",
            "scale_denominator": float(self.spin_scale.value()),
            "offset": float(self.dspin_offset.value()),
            "tick_len": float(self.dspin_tick.value()),
            "m_max": int(self.spin_m_max.value()),
            "m_step": int(self.spin_m_step.value()),
            "ft_max": int(self.spin_ft_max.value()),
            "ft_step": int(self.spin_ft_step.value()),
            "basepoint": self.origin_point,
            "angle": float(self.spin_azimuth.value()),
        }
        if self.current_scale_id:
            params["id"] = self.current_scale_id
        try:
            run_vertical_scale(**params)
            # Persist
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
            self._update_edit_button()
            self.show_menu()
        except Exception as e:
            try:
                iface.messageBar().pushCritical("Vertical Scale", f"Error creating scale: {e}")
            except Exception:
                print(f"Vertical Scale ERROR: {e}")

    def _generate_scale_preview(self, origin_point):
        """Live preview of the vertical scale while hovering over the map."""
        try:
            angle = float(self.spin_azimuth.value())
            scale_den = float(self.spin_scale.value())
            offset = float(self.dspin_offset.value())
            tick_len = float(self.dspin_tick.value())
            m_max = int(self.spin_m_max.value())
            m_step = int(self.spin_m_step.value())
            ft_max = int(self.spin_ft_max.value())
            ft_step = int(self.spin_ft_step.value())

            factor = _scale_factor(scale_den)
            base = QgsPoint(origin_point).project(offset, angle - 90)

            tick_segments = []
            tick_labels = []
            profile_line = []

            meter_ticks = []
            for val_m in range(0, m_max + 1, m_step):
                dist = val_m * factor
                p0 = base.project(dist, angle)
                p1 = p0.project(tick_len, angle + 90)
                meter_ticks.append(QgsPointXY(p0))
                tick_segments.append([QgsPointXY(p0), QgsPointXY(p1)])
                if val_m < m_max:
                    lbl = p1.project(tick_len * 0.75, angle + 90)
                    tick_labels.append({"pos": QgsPointXY(lbl), "text": str(val_m)})

            feet_ticks = []
            for val_ft in range(0, ft_max + 1, ft_step):
                meters = val_ft * 0.3048
                dist = meters * factor
                p0 = base.project(dist, angle)
                p1 = p0.project(tick_len, angle - 90)
                feet_ticks.append(QgsPointXY(p0))
                tick_segments.append([QgsPointXY(p0), QgsPointXY(p1)])
                if val_ft < ft_max:
                    lbl = p1.project(tick_len * 0.75, angle - 90)
                    tick_labels.append({"pos": QgsPointXY(lbl), "text": str(val_ft)})

            # Main baseline preview (left feet start → right meters end)
            if feet_ticks and meter_ticks:
                profile_line = [feet_ticks[0], meter_ticks[-1]]
            elif meter_ticks:
                profile_line = meter_ticks
            elif feet_ticks:
                profile_line = feet_ticks

            # Unit ticks and labels
            unit_offset = tick_len * 0.6
            label_offset = tick_len * 0.75
            unit_label_along = tick_len * 1.0
            unit_label_up = tick_len * 0.3
            if meter_ticks:
                m_top = meter_ticks[-1]
                m_top_pt = QgsPoint(m_top)
                m_top_tick = m_top_pt.project(tick_len, angle + 90)
                max_lbl = m_top_tick.project(label_offset, angle + 90)
                tick_labels.append({"pos": QgsPointXY(max_lbl), "text": str(m_max)})
                lbl = m_top_pt.project(unit_label_along, angle)
                lbl = lbl.project(unit_label_up, angle + 90)
                tick_labels.append({"pos": QgsPointXY(lbl), "text": "METERS"})
            if feet_ticks:
                f_top = feet_ticks[-1]
                f_top_pt = QgsPoint(f_top)
                f_top_tick = f_top_pt.project(tick_len, angle - 90)
                max_lbl = f_top_tick.project(label_offset, angle - 90)
                tick_labels.append({"pos": QgsPointXY(max_lbl), "text": str(ft_max)})
                lbl = f_top_pt.project(unit_label_along, angle + 180)
                lbl = lbl.project(unit_label_up, angle - 90)
                tick_labels.append({"pos": QgsPointXY(lbl), "text": "FEET"})

            return {
                "profile_line": profile_line,
                "baseline": profile_line,
                "tick_segments": tick_segments,
                "grid_segments": [],
                "tick_labels": tick_labels,
            }
        except Exception:
            return {"profile_line": [], "tick_segments": [], "tick_labels": []}

    def closeEvent(self, event):
        self._restore_previous_map_tool()
        super().closeEvent(event)
