# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QAeroChartDockWidget
                                 A QGIS plugin
 ICAO Aeronautical Chart Plugin
                             -------------------
        begin                : 2025-10-21
        git sha              : $Format:%H$
        copyright            : (C) 2025 by andures
        email                : your.email@example.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from __future__ import annotations

import os

from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QTableWidgetItem, QFileDialog, QShortcut, QInputDialog
from qgis.PyQt.QtGui import QKeySequence
from .utils.qt_compat import Qt, QMessageBox, QAbstractItemView, MsgLevel
from qgis.core import QgsPointXY
from .core.profile_chart_geometry import ProfileChartGeometry
from .utils.json_handler import JSONHandler
from .utils.logger import log, push_message

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'qaerochart_dockwidget_base.ui'))


class QAeroChartDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(
        self, iface: object | None = None,
        controller: object | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Constructor."""
        super(QAeroChartDockWidget, self).__init__(parent)
        self._iface = iface
        self._controller = controller
        self.setupUi(self)

        # Track current profile being edited (None for new profiles)
        self.current_profile_id = None

        # Initialize profile form components
        self._init_profile_form()

        # Initialize profile list
        self._init_profile_list()

        # Connect menu signals
        self.btnNewProfile.clicked.connect(self.new_profile)
        self.btnEditProfile.clicked.connect(self.edit_profile)
        self.btnDrawProfile.clicked.connect(self.draw_profile)
        self.btnDeleteProfile.clicked.connect(self.delete_profile)
        self.btnBackToMenu.clicked.connect(self.show_menu)

        # Issue #57: vertical scale bar button (optional — only if present in UI)
        if hasattr(self, "btnVerticalScale"):
            self.btnVerticalScale.clicked.connect(self._on_vertical_scale_clicked)

        # Issue #58: distance/altitude table button (optional — only if present in UI)
        if hasattr(self, "btnDistanceAltitudeTable"):
            self.btnDistanceAltitudeTable.clicked.connect(self._on_distance_altitude_table_clicked)

        # Connect list selection
        self.listWidgetProfiles.itemSelectionChanged.connect(self._on_profile_selection_changed)
        # Enable context menu to rename without recreating
        try:
            self.listWidgetProfiles.setContextMenuPolicy(Qt.CustomContextMenu)
            self.listWidgetProfiles.customContextMenuRequested.connect(self._on_profiles_context_menu)
        except AttributeError:
            pass
        # F2 to rename selected profile
        try:
            self._rename_shortcut = QShortcut(QKeySequence(Qt.Key_F2), self.listWidgetProfiles)
            self._rename_shortcut.activated.connect(self.rename_selected_profile)
        except AttributeError:
            pass

        # Wire controller signals
        if self._controller is not None:
            self._controller.message.connect(self._show_message)
            self._controller.profiles_changed.connect(self._refresh_profile_list)

        # Start on menu page
        self.stackedWidget.setCurrentIndex(0)

    def closeEvent(self, event):
        """Handle close event."""
        self.closingPlugin.emit()
        event.accept()

    def _show_message(self, title: str, text: str, level: int) -> None:
        """Slot for ProfileController.message signal — pushes to QGIS message bar."""
        if self._iface is not None:
            push_message(self._iface, title, text, level, duration=5)

    def _init_profile_form(self):
        """Initialize the profile creation form embedded in the dockwidget."""
        # Load the form widget (QWidget root since B19 fix)
        form_ui_path = os.path.join(os.path.dirname(__file__), 'ui', 'profile_creation_dialog_base.ui')
        self.profile_form_widget = uic.loadUi(form_ui_path)

        # Replace the placeholder in scroll area
        scroll_layout = self.scrollArea.widget().layout()
        scroll_layout.removeWidget(self.labelFormPlaceholder)
        self.labelFormPlaceholder.deleteLater()
        scroll_layout.addWidget(self.profile_form_widget)

        # Store reference point
        self.reference_point = None

        # Connect all buttons
        self._connect_form_buttons()

        # Initialize table with default rows
        self._initialize_profile_table()

        # Set default values for runway parameters
        self._set_default_runway_values()

    def _connect_form_buttons(self):
        """Connect all buttons in the embedded form and the dockwidget button bar."""
        # Primary action buttons live on the dockwidget (always visible, outside scroll)
        if hasattr(self, 'btnCreateProfile'):
            self.btnCreateProfile.clicked.connect(self.create_profile)
        if hasattr(self, 'btnCancelForm'):
            self.btnCancelForm.clicked.connect(self.cancel_profile)
        if hasattr(self, 'btnLoadConfig'):
            self.btnLoadConfig.clicked.connect(self._on_load_config)
        if hasattr(self, 'btnSaveConfig'):
            self.btnSaveConfig.clicked.connect(self._on_save_config)

        # Reference point selection lives in the embedded form
        if hasattr(self.profile_form_widget, 'btn_select_point'):
            self.profile_form_widget.btn_select_point.clicked.connect(self._on_select_point_clicked)

        # Table management buttons remain in the embedded form
        if hasattr(self.profile_form_widget, 'btn_add_point'):
            self.profile_form_widget.btn_add_point.clicked.connect(self._on_add_row)
        if hasattr(self.profile_form_widget, 'btn_remove_point'):
            self.profile_form_widget.btn_remove_point.clicked.connect(self._on_remove_row)
        if hasattr(self.profile_form_widget, 'btn_move_up'):
            self.profile_form_widget.btn_move_up.clicked.connect(self._on_move_row_up)
        if hasattr(self.profile_form_widget, 'btn_move_down'):
            self.profile_form_widget.btn_move_down.clicked.connect(self._on_move_row_down)

    def _initialize_profile_table(self):
        """Initialize the profile points table with default values."""
        table = self.profile_form_widget.tableWidget_points

        # Set column widths
        table.setColumnWidth(0, 120)  # Point Name
        table.setColumnWidth(1, 100)  # Distance (NM)
        table.setColumnWidth(2, 110)  # Elevation (ft)
        table.setColumnWidth(3, 100)  # MOCA (ft)
        table.setColumnWidth(4, 180)  # Notes

        # Add default rows with realistic ICAO profile data
        # Based on standard approach profile with multiple fix points
        self._add_table_row("MAPt", "0.0", "500", "1000", "Missed Approach Point")
        self._add_table_row("2 NM", "2.0", "710", "1200", "")
        self._add_table_row("3 NM", "3.0", "1030", "1500", "")
        self._add_table_row("4 NM", "4.0", "1360", "1800", "")
        self._add_table_row("5 NM", "5.0", "1680", "2100", "")
        self._add_table_row("FAF", "6.0", "2000", "2400", "Final Approach Fix")
        self._add_table_row("IF", "7.4", "2000", "2500", "Intermediate Fix")

        log("Profile table initialized with 7 default points (realistic ICAO profile)")

    def _set_default_runway_values(self):
        """Set default values for runway parameters to speed up testing."""
        # Default profile name if user doesn't enter one yet
        if hasattr(self.profile_form_widget, 'lineEdit_profile_name'):
            self.profile_form_widget.lineEdit_profile_name.setText("Profile 07")
        # Set default runway direction (matching typical instrument approach)
        if hasattr(self.profile_form_widget, 'lineEdit_direction'):
            self.profile_form_widget.lineEdit_direction.setText("07")

        # Set default runway length (realistic: ~3000m = 9843 ft)
        if hasattr(self.profile_form_widget, 'lineEdit_length'):
            self.profile_form_widget.lineEdit_length.setText("3000")

        # Set default THR elevation (13 ft as per ICAO example)
        if hasattr(self.profile_form_widget, 'lineEdit_thr_elev'):
            self.profile_form_widget.lineEdit_thr_elev.setText("13")

        # Set default TCH/RDH (50 ft standard)
        if hasattr(self.profile_form_widget, 'lineEdit_tch_rdh'):
            self.profile_form_widget.lineEdit_tch_rdh.setText("50")

        # Log exactly what we set above so it's clear
        log("Default runway values set (DIR 07, 3000 m length, 13 ft THR, 50 ft TCH)")

    def show_menu(self):
        """Show the main menu page."""
        self._refresh_profile_list()
        self.stackedWidget.setCurrentIndex(0)
        log("Showing menu page")

    def show_profile_form(self):
        """Show the profile creation form page."""
        self.stackedWidget.setCurrentIndex(1)
        log("Showing profile form page")

    # ========== Profile List Management ==========

    def _init_profile_list(self):
        """Initialize the profile list widget."""
        # Allow selecting multiple profiles at once
        try:
            self.listWidgetProfiles.setSelectionMode(QAbstractItemView.ExtendedSelection)
        except AttributeError:
            pass

        # Bind Delete key to bulk delete when list has focus
        try:
            # PyQt6: QKeySequence.StandardKey.Delete; PyQt5: QKeySequence.Delete
            _del_key = getattr(QKeySequence, 'Delete', None) or QKeySequence.StandardKey.Delete
            self._delete_shortcut = QShortcut(_del_key, self.listWidgetProfiles)
            self._delete_shortcut.activated.connect(self.delete_profile)
        except (AttributeError, TypeError):
            pass

        self._refresh_profile_list()
        log("Profile list initialized")

    def _on_profiles_context_menu(self, pos):
        """Show context menu for profiles list with Rename action."""
        try:
            menu = QtWidgets.QMenu(self.listWidgetProfiles)
            act_rename = menu.addAction("Rename… (F2)")
            act_delete = menu.addAction("Delete")
            act_draw = menu.addAction("Draw")
            action = (menu.exec_ if hasattr(menu, 'exec_') else menu.exec)(self.listWidgetProfiles.mapToGlobal(pos))
            if action == act_rename:
                self.rename_selected_profile()
            elif action == act_delete:
                self.delete_profile()
            elif action == act_draw:
                self.draw_profile()
        except Exception as e:
            log(f"Context menu failed: {e}", "WARNING")

    def _refresh_profile_list(self) -> None:
        """Refresh the profile list from saved profiles."""
        self.listWidgetProfiles.clear()

        profiles = self._controller.get_all_profiles() if self._controller else []

        if not profiles:
            item = QtWidgets.QListWidgetItem("No profiles created yet. Click 'New Profile' to start.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.listWidgetProfiles.addItem(item)
        else:
            for profile in profiles:
                display_name = self._controller.get_profile_display_name(profile)
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(Qt.UserRole, profile['id'])
                self.listWidgetProfiles.addItem(item)

        log(f"Profile list refreshed ({len(profiles)} profiles)")

    def _on_profile_selection_changed(self):
        """Handle profile selection change."""
        selected_items = self.listWidgetProfiles.selectedItems()
        # Enable actions if at least one real profile item is selected
        has_valid = any(item.data(Qt.UserRole) for item in selected_items)

        if has_valid:
            # Enable action buttons
            self.btnEditProfile.setEnabled(True)
            self.btnDrawProfile.setEnabled(True)
            self.btnDeleteProfile.setEnabled(True)
        else:
            # Disable action buttons
            self.btnEditProfile.setEnabled(False)
            self.btnDrawProfile.setEnabled(False)
            self.btnDeleteProfile.setEnabled(False)

    def new_profile(self):
        """Create a new profile - clear form and show it."""
        # Clear form
        self.reference_point = None
        if hasattr(self.profile_form_widget, 'lineEdit_reference'):
            self.profile_form_widget.lineEdit_reference.clear()
        if hasattr(self.profile_form_widget, 'lineEdit_profile_name'):
            self.profile_form_widget.lineEdit_profile_name.clear()

        # Clear table and add default rows
        if hasattr(self.profile_form_widget, 'tableWidget_points'):
            self.profile_form_widget.tableWidget_points.setRowCount(0)
            self._initialize_profile_table()

        # Set default runway values
        self._set_default_runway_values()

        # Store that we're creating a new profile (not editing)
        self.current_profile_id = None

        # Update primary action button label
        if hasattr(self, 'btnCreateProfile'):
            self.btnCreateProfile.setText("Create Profile")

        # Show form
        self.show_profile_form()

    def edit_profile(self) -> None:
        """Edit the selected profile."""
        selected_items = self.listWidgetProfiles.selectedItems()

        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Please select a profile to edit.",
                    level=MsgLevel.Warning, duration=3
                )
            return

        profile_id = selected_items[0].data(Qt.UserRole)
        config = self._controller.get_profile(profile_id) if self._controller else None

        if not config:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "Error", "Could not load profile configuration.",
                    level=MsgLevel.Critical, duration=3
                )
            return

        self._populate_form_from_config(config)
        # Load display name into form's name field
        try:
            profiles = self._controller.get_all_profiles()
            for p in profiles:
                if p.get('id') == profile_id:
                    if hasattr(self.profile_form_widget, 'lineEdit_profile_name'):
                        self.profile_form_widget.lineEdit_profile_name.setText(p.get('name', ''))
                    break
        except (AttributeError, KeyError):
            pass

        self.current_profile_id = profile_id

        if hasattr(self, 'btnCreateProfile'):
            self.btnCreateProfile.setText("Update Profile")

        self.show_profile_form()

    def draw_profile(self) -> None:
        """Draw the selected profile on the map."""
        selected_items = self.listWidgetProfiles.selectedItems()

        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Please select a profile to draw.",
                    level=MsgLevel.Warning, duration=3
                )
            return

        profile_id = selected_items[0].data(Qt.UserRole)
        if self._controller:
            self._controller.draw_profile(profile_id)

    def _on_vertical_scale_clicked(self) -> None:
        """Draw the vertical scale bar for the selected profile (Issue #57)."""
        selected_items = self.listWidgetProfiles.selectedItems()
        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Please select a profile first.",
                    level=MsgLevel.Warning, duration=3
                )
            return
        profile_id = selected_items[0].data(Qt.UserRole)
        if self._controller:
            self._controller.generate_vertical_scale(profile_id)

    def _on_distance_altitude_table_clicked(self) -> None:
        """Insert the distance/altitude table for the selected profile (Issue #58)."""
        selected_items = self.listWidgetProfiles.selectedItems()
        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Please select a profile first.",
                    level=MsgLevel.Warning, duration=3
                )
            return
        profile_id = selected_items[0].data(Qt.UserRole)
        if self._controller:
            self._controller.generate_distance_altitude_table(profile_id)

    def delete_profile(self) -> None:
        """Delete one or multiple selected profiles."""
        selected_items = [i for i in self.listWidgetProfiles.selectedItems() if i.data(Qt.UserRole)]

        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Please select at least one profile to delete.",
                    level=MsgLevel.Warning, duration=3
                )
            return

        count = len(selected_items)
        names_preview = "\n".join([i.text() for i in selected_items[:5]])
        more = "" if count <= 5 else f"\n…and {count - 5} more"

        title = "Delete Profiles" if count > 1 else "Delete Profile"
        body = f"Are you sure you want to delete {count} profile(s)?\n\n{names_preview}{more}"

        reply = QMessageBox.question(
            self, title, body, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:  # type: ignore[comparison-overlap]
            return

        if self._controller:
            profile_ids = [i.data(Qt.UserRole) for i in selected_items]
            self._controller.delete_profiles(profile_ids)

    # ========== End Profile List Management ==========

    def cancel_profile(self):
        """Cancel profile creation and return to menu."""
        # Deactivate tool if active
        if hasattr(self, 'tool_manager') and self.tool_manager:
            self.tool_manager.deactivate_tool()

        # Clear form
        self.reference_point = None
        if hasattr(self.profile_form_widget, 'lineEdit_reference'):
            self.profile_form_widget.lineEdit_reference.clear()

        # Return to menu
        self.show_menu()
        log("Profile creation cancelled")

    # ========== Table Management Methods ==========

    def _on_add_row(self):
        """Add a new row to the profile points table."""
        table = self.profile_form_widget.tableWidget_points
        row_count = table.rowCount()
        self._add_table_row(f"Point_{row_count + 1}", "", "", "")
        log(f"Added row {row_count + 1} to table")

    def _on_remove_row(self):
        """Remove the currently selected row from the table."""
        table = self.profile_form_widget.tableWidget_points
        current_row = table.currentRow()

        if current_row >= 0:
            table.removeRow(current_row)
            log(f"Removed row {current_row} from table")
        else:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection",
                    "Please select a row to remove.",
                    level=MsgLevel.Warning,
                    duration=3
                )

    def _add_table_row(self, point_name="", distance="", elevation="", moca="", notes=""):
        """
        Add a row to the table with specified values.

        Args:
            point_name (str): Name/identifier of the profile point
            distance (str): Distance from origin (NM)
            elevation (str): Elevation/Altitude (ft)
            moca (str): Minimum Obstacle Clearance Altitude (ft)
            notes (str): Additional notes
        """
        table = self.profile_form_widget.tableWidget_points
        row_position = table.rowCount()
        table.insertRow(row_position)

        # Set items (5 columns)
        table.setItem(row_position, 0, QTableWidgetItem(point_name))
        table.setItem(row_position, 1, QTableWidgetItem(distance))
        table.setItem(row_position, 2, QTableWidgetItem(elevation))
        table.setItem(row_position, 3, QTableWidgetItem(moca))
        table.setItem(row_position, 4, QTableWidgetItem(notes))

    def _swap_rows(self, table, row_a, row_b):
        """Swap content between two rows in the points table."""
        if row_a < 0 or row_b < 0:
            return
        if row_a == row_b:
            return
        col_count = table.columnCount()
        # Capture items
        row_a_items = []
        row_b_items = []
        for c in range(col_count):
            row_a_items.append(table.takeItem(row_a, c))
            row_b_items.append(table.takeItem(row_b, c))
        # Put back swapped
        for c in range(col_count):
            table.setItem(row_a, c, row_b_items[c])
            table.setItem(row_b, c, row_a_items[c])

    def _on_move_row_up(self):
        """Move selected row(s) up, preserving order."""
        table = self.profile_form_widget.tableWidget_points
        selected = sorted({idx.row() for idx in table.selectedIndexes()})
        if not selected:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection",
                    "Select one or more rows to move.",
                    level=MsgLevel.Warning,
                    duration=3
                )
            return
        # Move each selected row up; start from smallest to avoid double-swapping
        for r in selected:
            if r > 0:
                self._swap_rows(table, r, r - 1)
        # Reselect moved rows at new positions
        table.clearSelection()
        for r in selected:
            new_r = max(0, r - 1)
            try:
                table.selectRow(new_r)
            except RuntimeError:
                pass
            table.setCurrentCell(new_r, 0)

    def _on_move_row_down(self):
        """Move selected row(s) down, preserving order."""
        table = self.profile_form_widget.tableWidget_points
        row_count = table.rowCount()
        selected = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        if not selected:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection",
                    "Select one or more rows to move.",
                    level=MsgLevel.Warning,
                    duration=3
                )
            return
        # Move each selected row down; start from largest to avoid double-swapping
        for r in selected:
            if r < row_count - 1:
                self._swap_rows(table, r, r + 1)
        # Reselect moved rows at new positions
        table.clearSelection()
        for r in selected:
            new_r = min(row_count - 1, r + 1)
            try:
                table.selectRow(new_r)
            except RuntimeError:
                pass
            table.setCurrentCell(new_r, 0)

    # ========== Configuration Save/Load Methods ==========

    def _on_save_config(self):
        """Save current configuration to JSON file."""
        try:
            # Build configuration from current form state
            config = self._build_config_from_form()

            if not config:
                self._iface.messageBar().pushMessage(
                    "Cannot Save",
                    "Please fill in required fields before saving.",
                    level=MsgLevel.Warning,
                    duration=5
                )
                return

            # Get default filename
            runway_dir = self.profile_form_widget.lineEdit_direction.text().strip() or "profile"
            default_filename = JSONHandler.get_default_filename(runway_dir)

            # Show file dialog
            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "Save Profile Configuration",
                default_filename,
                "JSON Files (*.json);;All Files (*)"
            )

            if not filepath:
                log("Save cancelled by user")
                return

            # Ensure .json extension
            if not filepath.lower().endswith('.json'):
                filepath += '.json'

            # Save configuration
            JSONHandler.save_config(config, filepath)

            # Show success message
            self._iface.messageBar().pushMessage(
                "Configuration Saved",
                f"Saved to: {os.path.basename(filepath)}",
                level=MsgLevel.Success,
                duration=5
            )

            log(f"Configuration saved to {filepath}")

        except Exception as e:
            self._iface.messageBar().pushMessage(
                "Save Error",
                f"Failed to save configuration: {str(e)}",
                level=MsgLevel.Critical,
                duration=5
            )
            log(f"Save failed: {str(e)}", "ERROR")

    def _on_load_config(self):
        """Load configuration from JSON file."""
        try:
            # Show file dialog
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Load Profile Configuration",
                "",
                "JSON Files (*.json);;All Files (*)"
            )

            if not filepath:
                log("Load cancelled by user")
                return

            # Load configuration
            config = JSONHandler.load_config(filepath)

            if config:
                # Populate form with loaded configuration
                self._populate_form_from_config(config)

                # Show success message
                self._iface.messageBar().pushMessage(
                    "Configuration Loaded",
                    f"Loaded from: {os.path.basename(filepath)}",
                    level=MsgLevel.Success,
                    duration=5
                )

                log(f"Configuration loaded from {filepath}")

        except FileNotFoundError as e:
            self._iface.messageBar().pushMessage(
                "File Not Found",
                str(e),
                level=MsgLevel.Warning,
                duration=5
            )
            log(f"{str(e)}", "WARNING")

        except ValueError as e:
            self._iface.messageBar().pushMessage(
                "Invalid Configuration",
                str(e),
                level=MsgLevel.Warning,
                duration=5
            )
            log(f"{str(e)}", "WARNING")

        except Exception as e:
            self._iface.messageBar().pushMessage(
                "Load Error",
                f"Failed to load configuration: {str(e)}",
                level=MsgLevel.Critical,
                duration=5
            )
            log(f"Load failed: {str(e)}", "ERROR")

    def _populate_form_from_config(self, config):
        """
        Populate form fields from loaded configuration.
        Supports both v1.0 (reference_point) and v2.0 (origin_point) formats.

        Args:
            config (dict): Loaded configuration
        """
        # Clear existing table data
        table = self.profile_form_widget.tableWidget_points
        table.setRowCount(0)

        # Load origin/reference point (v2.0 uses "origin_point", v1.0 uses "reference_point")
        origin_point = config.get("origin_point", config.get("reference_point", {}))
        if origin_point and 'x' in origin_point and 'y' in origin_point:
            self.reference_point = QgsPointXY(origin_point['x'], origin_point['y'])
            coord_text = f"Origin: X={origin_point['x']:.2f}, Y={origin_point['y']:.2f}"
            self.profile_form_widget.lineEdit_reference.setText(coord_text)

        # Load runway parameters
        runway = config.get("runway", {})
        self.profile_form_widget.lineEdit_direction.setText(runway.get("direction", ""))
        self.profile_form_widget.lineEdit_length.setText(runway.get("length", ""))
        self.profile_form_widget.lineEdit_thr_elev.setText(runway.get("thr_elevation", ""))
        self.profile_form_widget.lineEdit_tch_rdh.setText(runway.get("tch_rdh", ""))

        # Load only the axis max (Issue #9: Style Parameters cleanup)
        style = config.get("style", {})
        form = self.profile_form_widget
        if hasattr(form, 'spinBox_axis_max_nm'):
            try:
                form.spinBox_axis_max_nm.setValue(float(style.get('axis_max_nm', 12)))
            except Exception:
                form.spinBox_axis_max_nm.setValue(12.0)

        # Load OCA single if present
        try:
            oca = config.get('oca', None)
            has_oca = (hasattr(form, 'checkBox_enable_oca')
                       and hasattr(form, 'doubleSpinBox_oca_from_nm')
                       and hasattr(form, 'doubleSpinBox_oca_to_nm')
                       and hasattr(form, 'doubleSpinBox_oca_ft'))
            if has_oca:
                if oca:
                    form.checkBox_enable_oca.setChecked(True)
                    try:
                        form.doubleSpinBox_oca_from_nm.setValue(float(oca.get('from_nm', oca.get('from', 0.0))))
                        form.doubleSpinBox_oca_to_nm.setValue(float(oca.get('to_nm', oca.get('to', 0.0))))
                        form.doubleSpinBox_oca_ft.setValue(float(oca.get('oca_ft', oca.get('height_ft', 0.0))))
                    except (ValueError, TypeError):
                        pass
                else:
                    form.checkBox_enable_oca.setChecked(False)
        except Exception as e:
            log(f"Could not populate OCA UI: {e}", "WARNING")

        # Load profile points
        profile_points = config.get("profile_points", [])
        for point in profile_points:
            self._add_table_row(
                point_name=point.get("point_name", ""),
                distance=point.get("distance_nm", point.get("distance", "")),  # Backward compatibility
                elevation=point.get("elevation_ft", point.get("elevation", "")),  # Backward compatibility
                moca=point.get("moca_ft", point.get("moca", "")),  # Backward compatibility
                notes=point.get("notes", "")
            )

        config_version = config.get("version", "1.0")
        log(f"Loaded {len(profile_points)} profile points from config v{config_version}")

    def rename_selected_profile(self) -> None:
        """Trigger rename for the currently selected profile (F2)."""
        # Defensive import in case plugin loader strips or misses the module import
        try:
            from qgis.PyQt.QtWidgets import QInputDialog as _QID
        except Exception:
            _QID = None
        selected_items = self.listWidgetProfiles.selectedItems()
        if not selected_items:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "No Selection", "Select a single profile to rename.",
                    level=MsgLevel.Warning, duration=3
                )
            return

        item = selected_items[0]
        profile_id = item.data(Qt.UserRole)
        if not profile_id:
            return

        current_name = None
        try:
            profiles = self._controller.get_all_profiles() if self._controller else []
            for p in profiles:
                if p.get('id') == profile_id:
                    current_name = p.get('name', '')
                    break
        except (AttributeError, ValueError):
            current_name = item.text()

        # Ask user for new name
        dlg = _QID or QInputDialog
        try:
            new_name, ok = dlg.getText(self, "Rename Profile", "New name:", text=current_name or "")
        except Exception:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "Error",
                    "Unable to open rename dialog (QInputDialog not available).",
                    level=MsgLevel.Critical,
                    duration=4
                )
            return
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            if self._iface:
                self._iface.messageBar().pushMessage(
                    "Invalid Name", "Profile name cannot be empty.",
                    level=MsgLevel.Warning, duration=3
                )
            return

        if self._controller:
            self._controller.rename_profile(profile_id, new_name)

    def create_profile(self) -> None:
        """Create or update profile from the embedded form data."""
        log("Creating profile from embedded form...")
        print(f"[qAeroChart][DIAG] create_profile called, _controller={self._controller!r}")

        config = self._build_config_from_form()
        if not config:
            print(f"[qAeroChart][DIAG] _build_config_from_form returned falsy: {config!r}")
            return
        print(f"[qAeroChart][DIAG] config keys: {list(config.keys())}")

        profile_name = None
        if hasattr(self.profile_form_widget, 'lineEdit_profile_name'):
            profile_name = self.profile_form_widget.lineEdit_profile_name.text().strip()
        if not profile_name:
            runway = config.get('runway', {})
            profile_name = f"Profile {runway.get('direction', 'N/A')}"

        if self._controller:
            print(f"[qAeroChart][DIAG] Calling save_or_update_profile"
                  f"('{profile_name}', profile_id={self.current_profile_id!r})")
            saved = self._controller.save_or_update_profile(
                profile_name, config, self.current_profile_id
            )
            print(f"[qAeroChart][DIAG] save_or_update_profile returned: {saved}")
            if saved:
                self.current_profile_id = None
                try:
                    if hasattr(self.profile_form_widget, 'lineEdit_profile_name'):
                        self.profile_form_widget.lineEdit_profile_name.setText("")
                except (AttributeError, RuntimeError):
                    pass
                log("Profile saved. Form remains open for new profiles.")

    def _on_select_point_clicked(self):
        """Handle 'Select from Map' button click in embedded form."""
        log("Origin point selection requested (embedded form)")
        log(">>> CLICK ON THE MAP TO SELECT ORIGIN POINT <<<")

        # Update button text
        if hasattr(self.profile_form_widget, 'btn_select_point'):
            self.profile_form_widget.btn_select_point.setText(">>> Click on map now >>>")
            self.profile_form_widget.btn_select_point.setEnabled(False)

        # Activate map tool
        if hasattr(self, 'tool_manager') and self.tool_manager:
            tool = self.tool_manager.get_tool()
            if tool is None:
                tool = self.tool_manager.create_tool()

            # Provide a preview generator so the tool can draw a live preview while moving
            if hasattr(tool, 'set_preview_generator'):
                tool.set_preview_generator(self._generate_profile_preview)

            # Connect tool signal to our handler
            tool.originSelected.connect(self._on_origin_selected)

            # Activate the tool
            self.tool_manager.activate_tool()

    def _on_origin_selected(self, point):
        """Handle origin point selection from map."""
        self.reference_point = point

        # Update UI
        if hasattr(self.profile_form_widget, 'lineEdit_reference'):
            coord_text = f"Origin: X={point.x():.2f}, Y={point.y():.2f}"
            self.profile_form_widget.lineEdit_reference.setText(coord_text)

        # Reset button
        if hasattr(self.profile_form_widget, 'btn_select_point'):
            self.profile_form_widget.btn_select_point.setText("Select from Map")
            self.profile_form_widget.btn_select_point.setEnabled(True)

        log(f"Origin point set to X={point.x():.2f}, Y={point.y():.2f}")

        # Deactivate map tool to finish selection and clear preview
        if hasattr(self, 'tool_manager') and self.tool_manager:
            self.tool_manager.deactivate_tool()

    def _generate_profile_preview(self, origin_point):
        """Generate preview polylines (profile and ticks) for a candidate origin.
        Returns a dict with 'profile_line', 'baseline', 'grid_segments', 'tick_segments', and optional 'tick_labels'.
        """
        try:
            # Build a lightweight config from current form (no origin requirement)
            form = self.profile_form_widget
            # Collect profile points from table
            profile_points = []
            table = form.tableWidget_points
            for row in range(table.rowCount()):
                name = table.item(row, 0).text() if table.item(row, 0) else ""
                dist = table.item(row, 1).text() if table.item(row, 1) else "0"
                elev = table.item(row, 2).text() if table.item(row, 2) else "0"
                if name or dist or elev:
                    try:
                        profile_points.append({
                            'point_name': name,
                            'distance_nm': float(dist or 0),
                            'elevation_ft': float(elev or 0)
                        })
                    except (ValueError, TypeError):
                        continue
            # Runway params (optional for preview)
            try:
                runway_len = float(form.lineEdit_length.text().strip() or 0)
                tch_ft = float(form.lineEdit_tch_rdh.text().strip() or 0)
                tch_m = tch_ft * 0.3048
            except (ValueError, AttributeError):
                runway_len, tch_m = 0.0, 0.0

            dir_text = form.lineEdit_direction.text().strip() if hasattr(form, 'lineEdit_direction') else ""
            try:
                rwy_num = int(''.join(ch for ch in dir_text if ch.isdigit())[:2] or 0)
            except ValueError:
                rwy_num = 0
            dir_sign = -1 if rwy_num and rwy_num <= 18 else 1
            geometry = ProfileChartGeometry(origin_point, vertical_exaggeration=10.0, horizontal_direction=dir_sign)

            # Profile polyline
            profile_line = geometry.create_profile_line(profile_points)

            # Baseline, grid and ticks based on max distance
            tick_segments = []
            grid_segments = []
            tick_labels = []
            baseline = []
            if profile_points:
                max_nm = max(p.get('distance_nm', 0) for p in profile_points)
                # Respect axis_max_nm from UI if greater
                try:
                    if hasattr(form, 'spinBox_axis_max_nm'):
                        ui_max = float(form.spinBox_axis_max_nm.value())
                        if ui_max > max_nm:
                            max_nm = ui_max
                except Exception:
                    pass
                # ticks (short) â€“ keep visual height ~200 m after VE
                markers = geometry.create_distance_markers(max_nm, marker_height_m=(200.0/10.0))
                for m in markers:
                    seg = m['geometry']  # [bottom, top]
                    if len(seg) >= 2:
                        tick_segments.append(seg)
                        # Label at the top of the tick
                        top_pt = seg[1]
                        tick_labels.append({'pos': top_pt, 'text': str(m.get('label', m.get('distance', '')))})
                # grid (full-height) â€“ keep visual height ~1500 m after VE (shorter to reduce clutter)
                grid = geometry.create_distance_markers(max_nm, marker_height_m=(1500.0/10.0))
                for g in grid:
                    seg = g['geometry']
                    if len(seg) >= 2:
                        grid_segments.append(seg)
                # baseline from 0..max at y=0
                p0 = geometry.calculate_profile_point(0.0, 0.0)
                p1 = geometry.calculate_profile_point(max_nm, 0.0)
                baseline = [p0, p1]

            # Optional: add runway line preview on TCH level for context
            if runway_len > 0 and tch_m >= 0:
                runway_pts = geometry.create_runway_line(runway_len, tch_m)
                # merge with profile line end-to-end as simple overlay (optional)
                # For preview, we could append runway separately, but RubberBand uses single geometry.
                # We'll prepend runway to improve context if profile_line empty
                if not profile_line:
                    profile_line = runway_pts

            return {
                'profile_line': profile_line or [],
                'baseline': baseline or [],
                'grid_segments': grid_segments or [],
                'tick_segments': tick_segments or [],
                'tick_labels': tick_labels or []
            }
        except Exception as e:
            log(f"preview generation failed: {e}", "WARNING")
            return {'profile_line': [], 'tick_segments': [], 'tick_labels': []}

    def _build_config_from_form(self):
        """Build configuration dict from embedded form data."""
        # Validate origin point - allow fallback to last hovered preview point if user forgot to click
        if not self.reference_point:
            fallback_point = None
            try:
                if hasattr(self, 'tool_manager') and self.tool_manager:
                    tool = self.tool_manager.get_tool()
                    if tool and hasattr(tool, 'get_last_hover_point'):
                        fallback_point = tool.get_last_hover_point()
            except Exception:
                fallback_point = None

            if fallback_point:
                # Use the last hovered point as origin and inform the user
                self.reference_point = fallback_point
                self._iface.messageBar().pushMessage(
                    "Using Preview Point",
                    "No origin was clicked â€” using last preview position as origin.",
                    level=MsgLevel.Info,
                    duration=4
                )
            else:
                self._iface.messageBar().pushMessage(
                    "Missing Origin Point",
                    "Please select an origin point from the map.",
                    level=MsgLevel.Warning,
                    duration=5
                )
                return None

        # Get runway parameters
        runway = {
            'direction': self.profile_form_widget.lineEdit_direction.text().strip(),
            'length': self.profile_form_widget.lineEdit_length.text().strip(),
            'thr_elevation': self.profile_form_widget.lineEdit_thr_elev.text().strip(),
            'tch_rdh': self.profile_form_widget.lineEdit_tch_rdh.text().strip()
        }

        # Validate runway parameters
        if not all([runway['direction'], runway['length'], runway['thr_elevation'], runway['tch_rdh']]):
            self._iface.messageBar().pushMessage(
                "Missing Runway Parameters",
                "Please fill in all runway parameters.",
                level=MsgLevel.Warning,
                duration=5
            )
            return None

        # Get profile points from table
        profile_points = []
        table = self.profile_form_widget.tableWidget_points
        for row in range(table.rowCount()):
            point_name = table.item(row, 0).text() if table.item(row, 0) else ""
            distance_nm = table.item(row, 1).text() if table.item(row, 1) else ""
            elevation_ft = table.item(row, 2).text() if table.item(row, 2) else ""
            moca_ft = table.item(row, 3).text() if table.item(row, 3) else ""
            notes = table.item(row, 4).text() if table.item(row, 4) else ""

            if point_name or distance_nm or elevation_ft:
                profile_points.append({
                    'point_name': point_name,
                    'distance_nm': distance_nm,
                    'elevation_ft': elevation_ft,
                    'moca_ft': moca_ft,
                    'notes': notes
                })

        if not profile_points:
            self._iface.messageBar().pushMessage(
                "No Profile Points",
                "Please add at least one profile point.",
                level=MsgLevel.Warning,
                duration=5
            )
            return None

        # Build minimal style config (Issue #9)
        form = self.profile_form_widget
        vertical_exaggeration = 10.0  # fixed; no UI control yet
        axis_max_nm = 12.0
        if hasattr(form, 'spinBox_axis_max_nm'):
            try:
                axis_max_nm = float(form.spinBox_axis_max_nm.value())
            except Exception:
                axis_max_nm = 12.0

        # Derive explicit MOCA segments from table (use point i MOCA for segment iâ†’i+1)
        moca_segments = []
        try:
            for i in range(len(profile_points) - 1):
                p1 = profile_points[i]
                p2 = profile_points[i + 1]
                mft = (p1.get('moca_ft') or "").strip()
                if mft:
                    try:
                        moca_segments.append({
                            'from_nm': float(p1.get('distance_nm') or 0),
                            'to_nm': float(p2.get('distance_nm') or 0),
                            'moca_ft': float(mft)
                        })
                    except Exception:
                        continue
        except Exception:
            moca_segments = []

        # Optional OCA from UI
        oca_value = None
        try:
            if hasattr(form, 'checkBox_enable_oca') and form.checkBox_enable_oca.isChecked():
                if (hasattr(form, 'doubleSpinBox_oca_from_nm')
                        and hasattr(form, 'doubleSpinBox_oca_to_nm')
                        and hasattr(form, 'doubleSpinBox_oca_ft')):
                    oca_value = {
                        'from_nm': float(form.doubleSpinBox_oca_from_nm.value()),
                        'to_nm': float(form.doubleSpinBox_oca_to_nm.value()),
                        'oca_ft': float(form.doubleSpinBox_oca_ft.value())
                    }
        except Exception as e:
            log(f"Could not read OCA UI: {e}", "WARNING")

        # Build config
        config = {
            'version': '2.0',
            'origin_point': {
                'x': self.reference_point.x(),
                'y': self.reference_point.y()
            },
            'runway': runway,
            'profile_points': profile_points,
            'style': {
                'vertical_exaggeration': vertical_exaggeration,
                # Extend axis to explicit max even if series ends earlier
                'axis_max_nm': axis_max_nm
            },
            # Provide explicit MOCA segments by default so the hatched area matches the example exactly
            'moca_segments': moca_segments,
            # OCA rectangle from UI (optional)
            'oca': oca_value,
            'oca_segments': []
        }

        return config
