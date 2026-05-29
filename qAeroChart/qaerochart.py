# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QAeroChart
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
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolBar

# Initialize Qt resources from file resources.py
# from .resources import *

# Import the code for the DockWidget
from .qaerochart_dockwidget import QAeroChartDockWidget
from .vertical_scale_dialog import VerticalScaleDockWidget
from .horizontal_scale_dialog import HorizontalScaleDockWidget
from .holding_dock import HoldingDockWidget
from .utils.logger import log
from .utils.qt_compat import Qt
import os.path


class QAeroChart:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = (QSettings().value('locale/userLocale') or '')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'QAeroChart_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&qAeroChart')
        # TODO: We are going to let the user set this up in a future iteration
        # self.toolbar = self.iface.addToolBar(u'QAeroChart')
        # self.toolbar.setObjectName(u'QAeroChart')

        # print("** INITIALIZING qAeroChart")

        self.pluginIsActive = False
        self.dockwidget = None
        
        # Map tool manager (will be initialized in initGui)
        self.tool_manager = None

        # Layer manager (will be initialized in initGui)
        self.layer_manager = None
        # Layout toolbar actions
        self.distance_table_action = None
        self.oca_h_table_action = None
        self._oca_h_dialog = None
        self._layout_toolbar_hooked = False
        self._layout_toolbars: list = []        # per-designer QToolBar instances (#87)
        self._layout_toolbar_windows: set = set()  # ids of windows already attached

        # Profile controller (will be initialized in initGui)
        self._profile_manager = None
        self._controller = None

        # Dedicated toolbar for qAeroChart tools
        self.tools_toolbar = None
        self.generate_profile_action = None
        self.vertical_scale_action = None
        self.vertical_scale_dock = None
        # Top-level menu
        self.top_menu = None
        # Vertical scale dock (Issue #57 standalone)
        self.vertical_scale_dock = None
        self.vertical_scale_action = None
        # Horizontal scale dock (Issue #69)
        self.horizontal_scale_dock = None
        self.horizontal_scale_action = None
        # Distance/Altitude Table dialog (Issue #68: non-blocking, kept alive)
        self._distance_dialog = None
        # GS/ROD Table dialog (Issue #73: non-blocking, kept alive)
        self._gs_rod_dialog = None
        self.gs_rod_action = None
        # Nominal Holding dock (Issue #94)
        self._holding_dock = None
        self.holding_action = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('QAeroChart', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, 'icons', 'icon.png')

        # Do not add to default Vector/Plugins menu; we'll create our own top menu
        self.add_action(
            icon_path,
            text=self.tr(u'qAeroChart - ICAO Aeronautical Charts'),
            callback=self.run,
            add_to_menu=False,
            add_to_toolbar=False,
            parent=self.iface.mainWindow())

        # Create dedicated toolbar and "Generate Profile" button (issue #4)
        self.tools_toolbar = self.iface.addToolBar('qAeroChart tools')
        self.tools_toolbar.setObjectName('qAeroChartTools')

        self.generate_profile_action = QAction(QIcon(icon_path), self.tr('Generate Profile'), self.iface.mainWindow())
        self.generate_profile_action.setObjectName('qAeroChartGenerateProfileAction')
        self.generate_profile_action.setStatusTip(self.tr('Open qAeroChart and generate a profile'))
        # For now, reuse existing entry point; opens the dock where user can generate/draw
        self.generate_profile_action.triggered.connect(self.run)
        self.tools_toolbar.addAction(self.generate_profile_action)

        # Vertical Scale action (Issue #57)
        vs_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_vertical_scale.svg')
        self.vertical_scale_action = QAction(QIcon(vs_icon_path), self.tr('Vertical Scale'), self.iface.mainWindow())
        self.vertical_scale_action.setObjectName('qAeroChartVerticalScaleAction')
        self.vertical_scale_action.setStatusTip(self.tr('Create vertical scale (meters/feet)'))
        self.vertical_scale_action.triggered.connect(self.open_vertical_scale_dock)
        self.tools_toolbar.addAction(self.vertical_scale_action)

        # Horizontal Scale action (Issue #69)
        hs_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_horizontal_scale.svg')
        if not os.path.exists(hs_icon_path):
            hs_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon.png')
        self.horizontal_scale_action = QAction(QIcon(hs_icon_path), self.tr('Horizontal Scale'), self.iface.mainWindow())
        self.horizontal_scale_action.setObjectName('qAeroChartHorizontalScaleAction')
        self.horizontal_scale_action.setStatusTip(self.tr('Create horizontal scale (meters/feet)'))
        self.horizontal_scale_action.triggered.connect(self.open_horizontal_scale_dock)
        self.tools_toolbar.addAction(self.horizontal_scale_action)

        # Nominal Holding action (Issue #94)
        holding_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_holding.svg')
        if not os.path.exists(holding_icon_path):
            holding_icon_path = icon_path
        self.holding_action = QAction(
            QIcon(holding_icon_path),
            self.tr('Nominal Holding'),
            self.iface.mainWindow(),
        )
        self.holding_action.setObjectName('qAeroChartHoldingAction')
        self.holding_action.setStatusTip(self.tr('Draw a nominal holding pattern on the map'))
        self.holding_action.triggered.connect(self.open_holding_dialog)
        self.tools_toolbar.addAction(self.holding_action)

        # Create top-level menu "qAeroChart" and insert it to the right of qPANSOPY if present (issue #3)
        try:
            menu_bar = self.iface.mainWindow().menuBar()
            self.top_menu = QMenu(self.tr('qAeroChart'), self.iface.mainWindow())
            self.top_menu.setObjectName('qAeroChartMenu')
            # Add our primary action
            self.top_menu.addAction(self.generate_profile_action)
            self.top_menu.addAction(self.vertical_scale_action)
            self.top_menu.addAction(self.horizontal_scale_action)
            self.top_menu.addAction(self.holding_action)

            # Try to position it right after qPANSOPY
            inserted = False
            actions = menu_bar.actions()
            for i, act in enumerate(actions):
                try:
                    title = act.text().replace('&', '').strip()
                except Exception:
                    title = ''
                if title.lower() == 'qpansopy':
                    if i + 1 < len(actions):
                        menu_bar.insertMenu(actions[i + 1], self.top_menu)
                    else:
                        menu_bar.addMenu(self.top_menu)
                    inserted = True
                    break
            if not inserted:
                # Fallback: append at end
                menu_bar.addMenu(self.top_menu)
        except Exception as e:
            print(f"PLUGIN qAeroChart WARNING: Could not create top-level menu: {e}")

        # GS/ROD Table action (Issue #73)
        gs_rod_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_gs_rod_table.svg')
        if not os.path.exists(gs_rod_icon_path):
            gs_rod_icon_path = icon_path
        self.gs_rod_action = QAction(QIcon(gs_rod_icon_path), self.tr('GS / Rate of Descent Table'), self.iface.mainWindow())
        self.gs_rod_action.setObjectName('qAeroChartGsRodTableAction')
        self.gs_rod_action.setStatusTip(self.tr('Create a Ground Speed / Rate of Descent table'))
        self.gs_rod_action.triggered.connect(self._open_gs_rod_table_builder)
        # gs_rod_action is available via the top menu and the Layout Designer toolbar;
        # it is intentionally NOT added to the map canvas toolbar (#91)

        # Layout toolbar action: add distance/altitude table into print layout
        dat_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_distance_table.svg')
        if not os.path.exists(dat_icon_path):
            dat_icon_path = icon_path
        self.distance_table_action = QAction(QIcon(dat_icon_path), self.tr('Add Distance/Altitude Table'), self.iface.mainWindow())
        self.distance_table_action.setObjectName('qAeroChartDistanceTableAction')
        self.distance_table_action.setStatusTip(self.tr('Insert a distance/altitude table into the active layout'))
        self.distance_table_action.triggered.connect(self._open_distance_table_builder)
        # distance_table_action is available via the top menu and the Layout Designer toolbar;
        # it is intentionally NOT added to the map canvas toolbar (#91)
        # Also hook into layout-designer openings to force-add the action to their toolbars
        try:
            self.iface.layoutDesignerOpened.connect(self._on_layout_designer_opened)
            self._layout_toolbar_hooked = True
        except Exception as e:
            print(f"PLUGIN qAeroChart WARNING: Could not hook layoutDesignerOpened: {e}")
        try:
            if self.top_menu:
                self.top_menu.addAction(self.distance_table_action)
                self.top_menu.addAction(self.gs_rod_action)
        except Exception:
            pass

        # OCA/H table toolbar action
        oca_icon_path = os.path.join(self.plugin_dir, 'icons', 'icon_oca_h_table.svg')
        self.oca_h_table_action = QAction(
            QIcon(oca_icon_path),
            self.tr('Add OCA/H Table'),
            self.iface.mainWindow(),
        )
        self.oca_h_table_action.setObjectName('qAeroChartOcaHTableAction')
        self.oca_h_table_action.setStatusTip(self.tr('Insert an OCA/H table into the active layout'))
        self.oca_h_table_action.triggered.connect(self._open_oca_h_table_builder)
        # oca_h_table_action is available via the top menu and the Layout Designer toolbar;
        # it is intentionally NOT added to the map canvas toolbar (#91)
        try:
            if self.top_menu:
                self.top_menu.addAction(self.oca_h_table_action)
        except Exception:
            pass
        
        # Initialize map tool manager — wrapped in try/except so a failure here
        # does NOT prevent layer_manager / controller from initialising (the
        # critical path for creating layers).
        try:
            from .tools import ProfilePointToolManager
            self.tool_manager = ProfilePointToolManager(
                self.iface.mapCanvas(),
                self.iface
            )
            log("Tool manager initialized")
        except Exception as e:
            print(f"[qAeroChart] WARNING: tool_manager init failed: {e}")
            log(f"Tool manager init failed: {e}", "WARNING")
            self.tool_manager = None

        # Initialize layer manager and profile controller
        from .core import LayerManager, ProfileManager, ProfileController
        self.layer_manager = LayerManager(self.iface)
        self._profile_manager = ProfileManager()
        self._controller = ProfileController(self._profile_manager, self.layer_manager)
        log("Layer manager and profile controller initialized")

    # --------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        log("Cleaning up...")

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        log("Unloading...")

        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&qAeroChart'),
                action)
            self.iface.removeToolBarIcon(action)
        # Remove custom toolbar and its action
        if self.tools_toolbar:
            if self.generate_profile_action:
                try:
                    self.tools_toolbar.removeAction(self.generate_profile_action)
                except Exception:
                    pass
            try:
                # QGIS will handle deletion of toolbar instance
                self.iface.mainWindow().removeToolBar(self.tools_toolbar)
            except Exception:
                pass
            self.tools_toolbar = None
            self.generate_profile_action = None
        # Remove top-level menu
        if self.top_menu:
            try:
                self.iface.mainWindow().menuBar().removeAction(self.top_menu.menuAction())
            except Exception:
                pass
            self.top_menu = None

        # Close vertical scale dock
        if self.vertical_scale_dock:
            try:
                self.iface.removeDockWidget(self.vertical_scale_dock)
                self.vertical_scale_dock.deleteLater()
            except Exception:
                pass
            self.vertical_scale_dock = None
            self.vertical_scale_action = None

        # Close horizontal scale dock
        if self.horizontal_scale_dock:
            try:
                self.iface.removeDockWidget(self.horizontal_scale_dock)
                self.horizontal_scale_dock.deleteLater()
            except Exception:
                pass
            self.horizontal_scale_dock = None
            self.horizontal_scale_action = None

        # Clean up tool manager
        if self.tool_manager:
            self.tool_manager.cleanup()
            self.tool_manager = None
        
        # Clean up controller and managers
        self._controller = None
        self._profile_manager = None

        # Clean up layer manager (optional - layers remain in project)
        if self.layer_manager:
            # Uncomment to remove layers on plugin unload:
            # self.layer_manager.remove_all_layers()
            self.layer_manager = None

        # Remove per-designer qAeroChart toolbars (issue #87)
        for toolbar in self._layout_toolbars:
            try:
                toolbar.hide()
                toolbar.deleteLater()
            except Exception:
                pass
        self._layout_toolbars.clear()
        self._layout_toolbar_windows.clear()

        # Remove layout toolbar actions
        if self.distance_table_action:
            try:
                self.iface.removeLayoutDesignerToolBarIcon(self.distance_table_action)
            except Exception:
                pass
            self.distance_table_action = None
        if self.oca_h_table_action:
            try:
                self.iface.removeLayoutDesignerToolBarIcon(self.oca_h_table_action)
            except Exception:
                pass
            self.oca_h_table_action = None
        self._oca_h_dialog = None
        if self._layout_toolbar_hooked:
            try:
                self.iface.layoutDesignerOpened.disconnect(self._on_layout_designer_opened)
            except Exception:
                pass
            self._layout_toolbar_hooked = False

        # Clean up GS/ROD dialog reference
        self._gs_rod_dialog = None
        if self.gs_rod_action:
            self.gs_rod_action = None

        # Clean up Nominal Holding dock
        if self._holding_dock:
            try:
                self.iface.removeDockWidget(self._holding_dock)
                self._holding_dock.deleteLater()
            except Exception:
                pass
            self._holding_dock = None
        if self.holding_action:
            self.holding_action = None

    # --------------------------------------------------------------------------

    def _active_layout_name(self):
        """Best-effort retrieval of the active layout name in the layout designer."""

        try:
            designer = self.iface.activeLayoutDesignerInterface()
            if designer is not None and hasattr(designer, "layout") and designer.layout() is not None:
                return designer.layout().name()
        except Exception:
            pass
        try:
            designer = self.iface.activeLayoutDesigner()
            if designer is not None and hasattr(designer, "layout") and designer.layout() is not None:
                return designer.layout().name()
        except Exception:
            pass
        return None

    def _safe_insert(self, insert_fn, dlg) -> None:
        """Call *insert_fn* and catch errors so a failed insert never crashes the plugin."""
        try:
            insert_fn(dlg, self.iface)
        except Exception as exc:
            try:
                self.iface.messageBar().pushCritical(
                    "qAeroChart", f"Table insert failed: {exc}",
                )
            except Exception:
                print(f"PLUGIN qAeroChart ERROR: Table insert failed: {exc}")

    def _open_oca_h_table_builder(self):
        """Launch the OCA/H table builder dialog (issue #74: non-blocking)."""
        try:
            from .scripts import table_oca_h
        except Exception as exc:
            print(f"PLUGIN qAeroChart ERROR: Cannot import OCA/H table builder: {exc}")
            return

        if self._oca_h_dialog is not None and self._oca_h_dialog.isVisible():
            self._oca_h_dialog.raise_()
            self._oca_h_dialog.activateWindow()
            return

        default_layout = self._active_layout_name()
        parent_window = None
        try:
            designer = self.iface.activeLayoutDesignerInterface()
            if designer is not None:
                parent_window = designer.window()
        except Exception:
            parent_window = None

        dlg = table_oca_h.build_dialog(
            iface=self.iface,
            parent=parent_window,
            default_layout_name=default_layout,
        )
        dlg.accepted.connect(lambda: self._safe_insert(table_oca_h.insert_from_dialog, dlg))
        dlg.finished.connect(lambda _: setattr(self, '_oca_h_dialog', None))
        self._oca_h_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_distance_table_builder(self):
        """Launch the distance/altitude table builder dialog (issue #68: non-blocking)."""

        try:
            from .scripts import table_distance_altitude
        except Exception as exc:
            print(f"PLUGIN qAeroChart ERROR: Cannot import table builder: {exc}")
            return

        # If dialog already open, just bring it to front
        if self._distance_dialog is not None and self._distance_dialog.isVisible():
            self._distance_dialog.raise_()
            self._distance_dialog.activateWindow()
            return

        default_layout = self._active_layout_name()
        parent_window = None
        try:
            designer = self.iface.activeLayoutDesignerInterface()
            if designer is not None:
                parent_window = designer.window()
                self._attach_action_to_designer(designer)
        except Exception:
            parent_window = None
        if parent_window is None:
            try:
                designer = self.iface.activeLayoutDesigner()
                if designer is not None:
                    parent_window = designer
                    self._attach_action_to_designer(designer)
            except Exception:
                parent_window = None
        # parent_window stays None when no layout designer is open so the
        # dialog floats independently (centered on screen, not over the map).

        dlg = table_distance_altitude.build_dialog(
            iface=self.iface,
            parent=parent_window,
            default_layout_name=default_layout,
        )
        dlg.accepted.connect(lambda: self._safe_insert(table_distance_altitude.insert_from_dialog, dlg))
        dlg.finished.connect(lambda _: setattr(self, '_distance_dialog', None))
        self._distance_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_gs_rod_table_builder(self) -> None:
        """Launch the GS/Rate-of-Descent table builder dialog (issue #73)."""
        try:
            from .scripts import table_gs_rod
        except Exception as exc:
            print(f"PLUGIN qAeroChart ERROR: Cannot import GS/ROD table builder: {exc}")
            return

        # If dialog already open, just bring it to front
        if self._gs_rod_dialog is not None and self._gs_rod_dialog.isVisible():
            self._gs_rod_dialog.raise_()
            self._gs_rod_dialog.activateWindow()
            return

        default_layout = self._active_layout_name()
        parent_window = None
        try:
            designer = self.iface.activeLayoutDesignerInterface()
            if designer is not None:
                parent_window = designer.window()
        except Exception:
            parent_window = None

        dlg = table_gs_rod.build_dialog(
            iface=self.iface,
            parent=parent_window,
            default_layout_name=default_layout,
        )
        dlg.accepted.connect(lambda: self._safe_insert(table_gs_rod.insert_from_dialog, dlg))
        dlg.finished.connect(lambda _: setattr(self, '_gs_rod_dialog', None))
        self._gs_rod_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_layout_designer_opened(self, designer_iface):
        """Ensure our action appears in the layout designer toolbar when a composition opens."""

        try:
            self._attach_action_to_designer(designer_iface)
        except Exception as exc:
            print(f"PLUGIN qAeroChart WARNING: Could not attach action to layout designer: {exc}")

    def _attach_action_to_designer(self, designer_iface) -> None:
        """Create a dedicated 'qAeroChart tools' toolbar in the Layout Designer
        window (issues #85, #86, #87).  Called once per designer instance.
        """
        if designer_iface is None:
            return

        window = getattr(designer_iface, 'window', None)
        if callable(window):
            window = window()
        if not window:
            return

        # Guard: avoid creating a second toolbar if already attached to this window
        win_id = id(window)
        if win_id in self._layout_toolbar_windows:
            return

        toolbar = QToolBar(self.tr('qAeroChart tools'), window)
        toolbar.setObjectName('qAeroChartLayoutToolbar')

        for action in (self.distance_table_action, self.gs_rod_action, self.oca_h_table_action):
            if action is not None:
                toolbar.addAction(action)

        window.addToolBar(toolbar)
        self._layout_toolbars.append(toolbar)
        self._layout_toolbar_windows.add(win_id)

    # --------------------------------------------------------------------------

    def run(self):
        """Toggle the Generate Profile dock (issue #67: clicking icon closes if already open)."""

        # First-time creation
        if self.dockwidget is None:
            log("Starting...")
            self.pluginIsActive = True
            self.dockwidget = QAeroChartDockWidget(
                iface=self.iface, controller=self._controller
            )
            self.dockwidget.tool_manager = self.tool_manager
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
            return

        # Toggle: hide if visible, show if hidden
        if self.dockwidget.isVisible():
            self.dockwidget.hide()
            self.pluginIsActive = False
        else:
            self.pluginIsActive = True
            self.dockwidget.show()
            self.dockwidget.raise_()

    def open_vertical_scale_dock(self) -> None:
        """Toggle the Vertical Scale dock (issue #67: clicking icon closes if already open)."""
        try:
            if self.vertical_scale_dock is None:
                self.vertical_scale_dock = VerticalScaleDockWidget(self.iface.mainWindow())
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.vertical_scale_dock)
                self.vertical_scale_dock.show()
                return

            # Toggle: hide if visible, show if hidden
            if self.vertical_scale_dock.isVisible():
                self.vertical_scale_dock.hide()
            else:
                self.vertical_scale_dock.show_menu()
                self.vertical_scale_dock.show()
                self.vertical_scale_dock.raise_()
        except Exception as e:
            log(f"Could not toggle Vertical Scale dock: {e}", "ERROR")

    def open_holding_dialog(self) -> None:
        """Toggle the Nominal Holding dock (issue #94)."""
        try:
            if self._holding_dock is None:
                self._holding_dock = HoldingDockWidget(self.iface.mainWindow())
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self._holding_dock)
                self._holding_dock.show()
                return

            if self._holding_dock.isVisible():
                self._holding_dock.hide()
            else:
                self._holding_dock.show()
                self._holding_dock.raise_()
        except Exception as exc:
            log(f"Could not toggle Holding dock: {exc}", "ERROR")

    def open_horizontal_scale_dock(self) -> None:
        """Toggle the Horizontal Scale dock (issue #69)."""
        try:
            if self.horizontal_scale_dock is None:
                self.horizontal_scale_dock = HorizontalScaleDockWidget(self.iface.mainWindow())
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.horizontal_scale_dock)
                self.horizontal_scale_dock.show()
                return

            # Toggle: hide if visible, show if hidden
            if self.horizontal_scale_dock.isVisible():
                self.horizontal_scale_dock.hide()
            else:
                self.horizontal_scale_dock.show()
                self.horizontal_scale_dock.raise_()
        except Exception as e:
            log(f"Could not toggle Horizontal Scale dock: {e}", "ERROR")
