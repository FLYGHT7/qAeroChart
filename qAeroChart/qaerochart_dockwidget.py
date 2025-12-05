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

import os

from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtWidgets import QTableWidgetItem, QFileDialog, QMessageBox
from qgis.core import Qgis, QgsPointXY
from qgis.utils import iface

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'qaerochart_dockwidget_base.ui'))



class QAeroChartDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(QAeroChartDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        
        # Initialize profile manager
        from .core import ProfileManager
        self.profile_manager = ProfileManager()
        
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
        
        # Connect list selection
        self.listWidgetProfiles.itemSelectionChanged.connect(self._on_profile_selection_changed)
        
        # Start on menu page
        self.stackedWidget.setCurrentIndex(0)

    def closeEvent(self, event):
        """Handle close event."""
        self.closingPlugin.emit()
        event.accept()
    
    def _init_profile_form(self):
        """Initialize the profile creation form embedded in the dockwidget."""
        from .ui.profile_creation_dialog import ProfileCreationDialog
        
        # Load the dialog form as a widget (not as a dialog)
        form_ui_path = os.path.join(os.path.dirname(__file__), 'ui', 'profile_creation_dialog_base.ui')
        self.profile_form_widget = uic.loadUi(form_ui_path)
        
        # Replace the placeholder in scroll area
        scroll_layout = self.scrollArea.widget().layout()
        scroll_layout.removeWidget(self.labelFormPlaceholder)
        self.labelFormPlaceholder.deleteLater()
        scroll_layout.addWidget(self.profile_form_widget)
        
        # Store reference point
        self.reference_point = None
        
        # Connect table management buttons
        self._connect_form_buttons()

    # Style parameters UI has been simplified; no map-unit toggle wiring needed
        
        # Initialize table with default rows
        self._initialize_profile_table()
        
        # Set default values for runway parameters
        self._set_default_runway_values()
        
        print("PLUGIN qAeroChart: Profile form initialized in dockwidget")

    # Removed legacy map-units wiring (Issue #9: Style Parameters cleanup)
    
    def _connect_form_buttons(self):
        """Connect all buttons in the embedded form."""
        # Create/Cancel buttons from the embedded form
        if hasattr(self.profile_form_widget, 'btn_create'):
            self.profile_form_widget.btn_create.clicked.connect(self.create_profile)
        
        if hasattr(self.profile_form_widget, 'btn_cancel'):
            self.profile_form_widget.btn_cancel.clicked.connect(self.cancel_profile)
        
        # Reference point selection
        if hasattr(self.profile_form_widget, 'btn_select_point'):
            self.profile_form_widget.btn_select_point.clicked.connect(self._on_select_point_clicked)
        
        # Table management
        if hasattr(self.profile_form_widget, 'btn_add_point'):
            self.profile_form_widget.btn_add_point.clicked.connect(self._on_add_row)
        
        if hasattr(self.profile_form_widget, 'btn_remove_point'):
            self.profile_form_widget.btn_remove_point.clicked.connect(self._on_remove_row)
        
        # Configuration save/load
        if hasattr(self.profile_form_widget, 'btn_save_config'):
            self.profile_form_widget.btn_save_config.clicked.connect(self._on_save_config)
        
        if hasattr(self.profile_form_widget, 'btn_load_config'):
            self.profile_form_widget.btn_load_config.clicked.connect(self._on_load_config)
        
        print("PLUGIN qAeroChart: Form buttons connected")
    
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
        
        print("PLUGIN qAeroChart: Profile table initialized with 7 default points (realistic ICAO profile)")
    
    def _set_default_runway_values(self):
        """Set default values for runway parameters to speed up testing."""
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
        print("PLUGIN qAeroChart: Default runway values set (DIR 07, 3000 m length, 13 ft THR, 50 ft TCH)")
    
    def show_menu(self):
        """Show the main menu page."""
        self._refresh_profile_list()
        self.stackedWidget.setCurrentIndex(0)
        print("PLUGIN qAeroChart: Showing menu page")
    
    def show_profile_form(self):
        """Show the profile creation form page."""
        self.stackedWidget.setCurrentIndex(1)
        print("PLUGIN qAeroChart: Showing profile form page")
    
    # ========== Profile List Management ==========
    
    def _init_profile_list(self):
        """Initialize the profile list widget."""
        self._refresh_profile_list()
        print("PLUGIN qAeroChart: Profile list initialized")
    
    def _refresh_profile_list(self):
        """Refresh the profile list from saved profiles."""
        self.listWidgetProfiles.clear()
        
        profiles = self.profile_manager.get_all_profiles()
        
        if not profiles:
            # Show empty state
            item = QtWidgets.QListWidgetItem("No profiles created yet. Click 'New Profile' to start.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.listWidgetProfiles.addItem(item)
        else:
            for profile in profiles:
                display_name = self.profile_manager.get_profile_display_name(profile)
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(Qt.UserRole, profile['id'])  # Store profile ID
                self.listWidgetProfiles.addItem(item)
        
        print(f"PLUGIN qAeroChart: Profile list refreshed ({len(profiles)} profiles)")
    
    def _on_profile_selection_changed(self):
        """Handle profile selection change."""
        selected_items = self.listWidgetProfiles.selectedItems()
        
        if selected_items and selected_items[0].data(Qt.UserRole):
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
        
        # Clear table and add default rows
        if hasattr(self.profile_form_widget, 'tableWidget_points'):
            self.profile_form_widget.tableWidget_points.setRowCount(0)
            self._initialize_profile_table()
        
        # Set default runway values
        self._set_default_runway_values()
        
        # Store that we're creating a new profile (not editing)
        self.current_profile_id = None
        
        # Show form
        self.show_profile_form()
        print("PLUGIN qAeroChart: New profile creation started")
    
    def edit_profile(self):
        """Edit the selected profile."""
        selected_items = self.listWidgetProfiles.selectedItems()
        
        if not selected_items:
            iface.messageBar().pushMessage(
                "No Selection",
                "Please select a profile to edit.",
                level=Qgis.Warning,
                duration=3
            )
            return
        
        profile_id = selected_items[0].data(Qt.UserRole)
        config = self.profile_manager.get_profile(profile_id)
        
        if not config:
            iface.messageBar().pushMessage(
                "Error",
                "Could not load profile configuration.",
                level=Qgis.Critical,
                duration=3
            )
            return
        
        # Load configuration into form
        self._populate_form_from_config(config)
        
        # Store profile ID for updating
        self.current_profile_id = profile_id
        
        # Show form
        self.show_profile_form()
        print(f"PLUGIN qAeroChart: Editing profile {profile_id}")
    
    def draw_profile(self):
        """Draw the selected profile on the map."""
        selected_items = self.listWidgetProfiles.selectedItems()
        
        if not selected_items:
            iface.messageBar().pushMessage(
                "No Selection",
                "Please select a profile to draw.",
                level=Qgis.Warning,
                duration=3
            )
            return
        
        profile_id = selected_items[0].data(Qt.UserRole)
        config = self.profile_manager.get_profile(profile_id)
        
        if not config:
            iface.messageBar().pushMessage(
                "Error",
                "Could not load profile configuration.",
                level=Qgis.Critical,
                duration=3
            )
            return
        
        # Create/update layers
        if hasattr(self, 'layer_manager') and self.layer_manager:
            self._create_profile_layers(config)
            iface.messageBar().pushMessage(
                "Profile Drawn",
                "Profile has been drawn on the map.",
                level=Qgis.Success,
                duration=3
            )
        
        print(f"PLUGIN qAeroChart: Drew profile {profile_id}")
    
    def delete_profile(self):
        """Delete the selected profile."""
        selected_items = self.listWidgetProfiles.selectedItems()
        
        if not selected_items:
            iface.messageBar().pushMessage(
                "No Selection",
                "Please select a profile to delete.",
                level=Qgis.Warning,
                duration=3
            )
            return
        
        profile_id = selected_items[0].data(Qt.UserRole)
        profile_name = selected_items[0].text()
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to delete this profile?\n\n{profile_name}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.profile_manager.delete_profile(profile_id)
            self._refresh_profile_list()
            iface.messageBar().pushMessage(
                "Profile Deleted",
                "Profile has been removed.",
                level=Qgis.Info,
                duration=3
            )
            print(f"PLUGIN qAeroChart: Deleted profile {profile_id}")
    
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
        print("PLUGIN qAeroChart: Profile creation cancelled")
    
    # ========== Table Management Methods ==========
    
    def _on_add_row(self):
        """Add a new row to the profile points table."""
        table = self.profile_form_widget.tableWidget_points
        row_count = table.rowCount()
        self._add_table_row(f"Point_{row_count + 1}", "", "", "")
        print(f"PLUGIN qAeroChart: Added row {row_count + 1} to table")
    
    def _on_remove_row(self):
        """Remove the currently selected row from the table."""
        table = self.profile_form_widget.tableWidget_points
        current_row = table.currentRow()
        
        if current_row >= 0:
            table.removeRow(current_row)
            print(f"PLUGIN qAeroChart: Removed row {current_row} from table")
        else:
            iface.messageBar().pushMessage(
                "No Selection",
                "Please select a row to remove.",
                level=Qgis.Warning,
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
    
    # ========== Configuration Save/Load Methods ==========
    
    def _on_save_config(self):
        """Save current configuration to JSON file."""
        try:
            # Build configuration from current form state
            config = self._build_config_from_form()
            
            if not config:
                iface.messageBar().pushMessage(
                    "Cannot Save",
                    "Please fill in required fields before saving.",
                    level=Qgis.Warning,
                    duration=5
                )
                return
            
            # Get default filename
            runway_dir = self.profile_form_widget.lineEdit_direction.text().strip() or "profile"
            from .utils import JSONHandler
            default_filename = JSONHandler.get_default_filename(runway_dir)
            
            # Show file dialog
            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "Save Profile Configuration",
                default_filename,
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not filepath:
                print("PLUGIN qAeroChart: Save cancelled by user")
                return
            
            # Ensure .json extension
            if not filepath.lower().endswith('.json'):
                filepath += '.json'
            
            # Save configuration
            JSONHandler.save_config(config, filepath)
            
            # Show success message
            iface.messageBar().pushMessage(
                "Configuration Saved",
                f"Saved to: {os.path.basename(filepath)}",
                level=Qgis.Success,
                duration=5
            )
            
            print(f"PLUGIN qAeroChart: Configuration saved to {filepath}")
            
        except Exception as e:
            iface.messageBar().pushMessage(
                "Save Error",
                f"Failed to save configuration: {str(e)}",
                level=Qgis.Critical,
                duration=5
            )
            print(f"PLUGIN qAeroChart ERROR: Save failed: {str(e)}")
    
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
                print("PLUGIN qAeroChart: Load cancelled by user")
                return
            
            # Load configuration
            from .utils import JSONHandler
            config = JSONHandler.load_config(filepath)
            
            if config:
                # Populate form with loaded configuration
                self._populate_form_from_config(config)
                
                # Show success message
                iface.messageBar().pushMessage(
                    "Configuration Loaded",
                    f"Loaded from: {os.path.basename(filepath)}",
                    level=Qgis.Success,
                    duration=5
                )
                
                print(f"PLUGIN qAeroChart: Configuration loaded from {filepath}")
            
        except FileNotFoundError as e:
            iface.messageBar().pushMessage(
                "File Not Found",
                str(e),
                level=Qgis.Warning,
                duration=5
            )
            print(f"PLUGIN qAeroChart WARNING: {str(e)}")
            
        except ValueError as e:
            iface.messageBar().pushMessage(
                "Invalid Configuration",
                str(e),
                level=Qgis.Warning,
                duration=5
            )
            print(f"PLUGIN qAeroChart WARNING: {str(e)}")
            
        except Exception as e:
            iface.messageBar().pushMessage(
                "Load Error",
                f"Failed to load configuration: {str(e)}",
                level=Qgis.Critical,
                duration=5
            )
            print(f"PLUGIN qAeroChart ERROR: Load failed: {str(e)}")
    
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
            if hasattr(form, 'checkBox_enable_oca') and hasattr(form, 'doubleSpinBox_oca_from_nm') and hasattr(form, 'doubleSpinBox_oca_to_nm') and hasattr(form, 'doubleSpinBox_oca_ft'):
                if oca:
                    form.checkBox_enable_oca.setChecked(True)
                    try:
                        form.doubleSpinBox_oca_from_nm.setValue(float(oca.get('from_nm', oca.get('from', 0.0))))
                        form.doubleSpinBox_oca_to_nm.setValue(float(oca.get('to_nm', oca.get('to', 0.0))))
                        form.doubleSpinBox_oca_ft.setValue(float(oca.get('oca_ft', oca.get('height_ft', 0.0))))
                    except Exception:
                        pass
                else:
                    form.checkBox_enable_oca.setChecked(False)
        except Exception as e:
            print(f"PLUGIN qAeroChart WARNING: Could not populate OCA UI: {e}")

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
        print(f"PLUGIN qAeroChart: Loaded {len(profile_points)} profile points from config v{config_version}")
    
    def create_profile(self):
        """Create profile from the form data."""
        print("PLUGIN qAeroChart: Creating profile from embedded form...")
        
        # Validate and collect data
        config = self._build_config_from_form()
        
        if config:
            # Generate profile name from runway direction
            runway = config.get('runway', {})
            profile_name = f"Profile {runway.get('direction', 'N/A')}"
            
            # If editing existing profile, update it; otherwise create new
            if hasattr(self, 'current_profile_id') and self.current_profile_id:
                self.profile_manager.update_profile(self.current_profile_id, profile_name, config)
                message = "Profile has been updated successfully."
            else:
                self.profile_manager.save_profile(profile_name, config)
                message = "Profile has been created and saved successfully."
            
            # Create/update layers
            if hasattr(self, 'layer_manager') and self.layer_manager:
                self._create_profile_layers(config)
                
                # Show success message
                iface.messageBar().pushMessage(
                    "Profile Saved",
                    message,
                    level=Qgis.Success,
                    duration=5
                )
                
                # Reset current profile ID
                self.current_profile_id = None
                
                # KEEP FORM OPEN - Don't go back to menu
                # User can click "Back to Menu" if they want, or create another profile
                print("PLUGIN qAeroChart: Profile created successfully. Form remains open for new profiles.")
            else:
                print("PLUGIN qAeroChart WARNING: Layer manager not available")
    
    def _on_select_point_clicked(self):
        """Handle 'Select from Map' button click in embedded form."""
        print("PLUGIN qAeroChart: Origin point selection requested (embedded form)")
        print("PLUGIN qAeroChart: >>> CLICK ON THE MAP TO SELECT ORIGIN POINT <<<")
        
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
        
        print(f"PLUGIN qAeroChart: Origin point set to X={point.x():.2f}, Y={point.y():.2f}")
        
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
                    except:
                        continue
            # Runway params (optional for preview)
            try:
                runway_len = float(form.lineEdit_length.text().strip() or 0)
                tch_ft = float(form.lineEdit_tch_rdh.text().strip() or 0)
                tch_m = tch_ft * 0.3048
            except:
                runway_len, tch_m = 0.0, 0.0
            
            from .core.profile_chart_geometry import ProfileChartGeometry
            # Use the same default VE as runtime population (10x) for preview
            # Determine direction sign from current runway direction
            dir_text = form.lineEdit_direction.text().strip() if hasattr(form, 'lineEdit_direction') else ""
            try:
                rwy_num = int(''.join(ch for ch in dir_text if ch.isdigit())[:2] or 0)
            except Exception:
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
                # ticks (short) – keep visual height ~200 m after VE
                markers = geometry.create_distance_markers(max_nm, marker_height_m=(200.0/10.0))
                for m in markers:
                    seg = m['geometry']  # [bottom, top]
                    if len(seg) >= 2:
                        tick_segments.append(seg)
                        # Label at the top of the tick
                        top_pt = seg[1]
                        tick_labels.append({'pos': top_pt, 'text': str(m.get('label', m.get('distance', '')))} )
                # grid (full-height) – keep visual height ~1500 m after VE (shorter to reduce clutter)
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
            print(f"PLUGIN qAeroChart WARNING: preview generation failed: {e}")
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
                iface.messageBar().pushMessage(
                    "Using Preview Point",
                    "No origin was clicked — using last preview position as origin.",
                    level=Qgis.Info,
                    duration=4
                )
            else:
                iface.messageBar().pushMessage(
                    "Missing Origin Point",
                    "Please select an origin point from the map.",
                    level=Qgis.Warning,
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
            iface.messageBar().pushMessage(
                "Missing Runway Parameters",
                "Please fill in all runway parameters.",
                level=Qgis.Warning,
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
            iface.messageBar().pushMessage(
                "No Profile Points",
                "Please add at least one profile point.",
                level=Qgis.Warning,
                duration=5
            )
            return None
        
        # Build minimal style config (Issue #9)
        form = self.profile_form_widget
        vertical_exaggeration = 10.0
        axis_max_nm = 12.0
        # Vertical exaggeration is fixed to 10x (no UI control)
        try:
            vertical_exaggeration = 10.0
        except Exception:
            vertical_exaggeration = 10.0
        if hasattr(form, 'spinBox_axis_max_nm'):
            try:
                axis_max_nm = float(form.spinBox_axis_max_nm.value())
            except Exception:
                axis_max_nm = 12.0
        
        # Derive explicit MOCA segments from table (use point i MOCA for segment i→i+1)
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
                if hasattr(form, 'doubleSpinBox_oca_from_nm') and hasattr(form, 'doubleSpinBox_oca_to_nm') and hasattr(form, 'doubleSpinBox_oca_ft'):
                    oca_value = {
                        'from_nm': float(form.doubleSpinBox_oca_from_nm.value()),
                        'to_nm': float(form.doubleSpinBox_oca_to_nm.value()),
                        'oca_ft': float(form.doubleSpinBox_oca_ft.value())
                    }
        except Exception as e:
            print(f"PLUGIN qAeroChart WARNING: Could not read OCA UI: {e}")

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
    
    # Old dialog methods removed - now using embedded form
    
    def _create_profile_layers(self, config):
        """
        Create profile layers based on configuration v2.0.
        Uses ProfileChartGeometry for cartesian calculations.
        
        Args:
            config (dict): Profile configuration from dialog (v2.0 format)
        """
        try:
            print("PLUGIN qAeroChart: Creating profile layers v2.0...")
            
            # Create all layers with style config
            layers = self.layer_manager.create_all_layers(config)
            
            # Populate layers using config (LayerManager handles all geometry calculations)
            success = self.layer_manager.populate_layers_from_config(config)
            
            if success:
                # Get counts for message
                profile_points = config.get('profile_points', [])
                runway_params = config.get('runway', {})
                
                # Show success message
                iface.messageBar().pushMessage(
                    "qAeroChart",
                    f"Profile chart created: {runway_params.get('direction', 'N/A')} with {len(profile_points)} points",
                    level=Qgis.Success,
                    duration=5
                )
                
                print(f"PLUGIN qAeroChart: Profile created successfully with {len(profile_points)} points")
            else:
                raise Exception("Failed to populate layers from configuration")
            
        except Exception as e:
            print(f"PLUGIN qAeroChart ERROR: Failed to create profile layers: {str(e)}")
            iface.messageBar().pushMessage(
                "Error",
                f"Failed to create profile layers: {str(e)}",
                level=Qgis.Critical,
                duration=5
            )
