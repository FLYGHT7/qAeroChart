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
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

# Initialize Qt resources from file resources.py
# from .resources import *

# Import the code for the DockWidget
from .qaerochart_dockwidget import QAeroChartDockWidget
from .vertical_scale_dialog import VerticalScaleDockWidget
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
        locale = QSettings().value('locale/userLocale')[0:2]
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

        # Dedicated toolbar for qAeroChart tools
        self.tools_toolbar = None
        self.generate_profile_action = None
        self.vertical_scale_action = None
        self.vertical_scale_dock = None
        # Top-level menu
        self.top_menu = None

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

        # Create top-level menu "qAeroChart" and insert it to the right of qPANSOPY if present (issue #3)
        try:
            menu_bar = self.iface.mainWindow().menuBar()
            self.top_menu = QMenu(self.tr('qAeroChart'), self.iface.mainWindow())
            self.top_menu.setObjectName('qAeroChartMenu')
            # Add our primary action
            self.top_menu.addAction(self.generate_profile_action)
            self.top_menu.addAction(self.vertical_scale_action)

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
        
        # Initialize map tool manager
        from .tools import ProfilePointToolManager
        self.tool_manager = ProfilePointToolManager(
            self.iface.mapCanvas(),
            self.iface
        )
        print("PLUGIN qAeroChart: Tool manager initialized")
        
        # Initialize layer manager
        from .core import LayerManager
        self.layer_manager = LayerManager(self.iface)
        print("PLUGIN qAeroChart: Layer manager initialized")

    def open_vertical_scale_dock(self):
        try:
            if not self.vertical_scale_dock:
                self.vertical_scale_dock = VerticalScaleDockWidget(self.iface.mainWindow())
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.vertical_scale_dock)
            else:
                # Always start from the menu page to mimic profile flow
                try:
                    self.vertical_scale_dock.show_menu()
                except Exception:
                    pass
            self.vertical_scale_dock.show()
            self.vertical_scale_dock.raise_()
        except Exception as e:
            try:
                self.iface.messageBar().pushCritical('qAeroChart', f'Could not open Vertical Scale dock: {e}')
            except Exception:
                print(f"PLUGIN qAeroChart ERROR: Could not open Vertical Scale dock: {e}")

    # --------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print("PLUGIN qAeroChart: Cleaning up...")

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

        print("PLUGIN qAeroChart: Unloading...")

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
        
        # Clean up tool manager
        if self.tool_manager:
            self.tool_manager.cleanup()
            self.tool_manager = None
        
        # Clean up layer manager (optional - layers remain in project)
        if self.layer_manager:
            # Uncomment to remove layers on plugin unload:
            # self.layer_manager.remove_all_layers()
            self.layer_manager = None

    # --------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            print("PLUGIN qAeroChart: Starting...")

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget is None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = QAeroChartDockWidget()

            # Pass managers to dockwidget
            self.dockwidget.tool_manager = self.tool_manager
            self.dockwidget.layer_manager = self.layer_manager

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
