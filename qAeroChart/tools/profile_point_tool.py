# -*- coding: utf-8 -*-
"""
ProfilePointTool - Map tool for selecting origin points on the map

This tool allows users to click on the map canvas to select an origin point
(the location WHERE the profile chart will be drawn). It provides visual
feedback using a rubber band and emits signals to communicate with the
ProfileCreationDialog.
"""

from qgis.PyQt.QtCore import pyqtSignal, QRectF
from qgis.PyQt.QtGui import QColor, QFont, QPen, QBrush
from ..utils.logger import log
from ..utils.qt_compat import Qt
from qgis.core import QgsPointXY, QgsGeometry
from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapCanvasItem

# ---------------------------------------------------------------------------
# QGIS 3 / 4 compatibility for geometry type enums
# ---------------------------------------------------------------------------
try:
    from qgis.core import Qgis as _Qgis
    _GEOM_POINT = _Qgis.GeometryType.Point
    _GEOM_LINE = _Qgis.GeometryType.Line
except AttributeError:
    from qgis.core import QgsWkbTypes as _QgsWkbTypes
    _GEOM_POINT = _QgsWkbTypes.PointGeometry
    _GEOM_LINE = _QgsWkbTypes.LineGeometry

# ---------------------------------------------------------------------------
# QGIS 3 / 4 compatibility for QgsRubberBand icon enum
# ---------------------------------------------------------------------------
_ICON_CIRCLE = getattr(QgsRubberBand, 'ICON_CIRCLE', None)
if _ICON_CIRCLE is None:
    try:
        _ICON_CIRCLE = QgsRubberBand.IconType.ICON_CIRCLE
    except AttributeError:
        _ICON_CIRCLE = 4  # numeric fallback


class _PreviewLabelCanvasItem(QgsMapCanvasItem):
    """Lightweight canvas overlay that paints text labels at map positions.

    Works on both QGIS 3 and QGIS 4 since QgsMapCanvasItem is available in
    all versions.  Replaces the old QgsTextAnnotation / QgsMapCanvasAnnotationItem
    approach that was removed in QGIS 4.
    """

    def __init__(self, canvas, labels: list):
        """
        Args:
            canvas: QgsMapCanvas instance.
            labels: list of dicts with 'pos' (QgsPointXY) and 'text' (str).
        """
        super().__init__(canvas)
        self._canvas_ref = canvas
        self._labels = labels
        self._font = QFont("Arial", 8)
        self._pen = QPen(QColor(0, 0, 0))
        self._bg = QBrush(QColor(255, 255, 255, 200))
        self.updateCanvas()

    def paint(self, painter, option, widget):
        if not painter:
            return
        painter.setFont(self._font)
        fm = painter.fontMetrics()
        for entry in self._labels:
            pos = entry.get('pos')
            text = str(entry.get('text', ''))
            if not isinstance(pos, QgsPointXY) or not text:
                continue
            pt = self.toCanvasCoordinates(pos)
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            # Draw background rect then text (offset below the axis)
            x = int(pt.x()) - tw // 2
            y = int(pt.y()) + 4
            painter.setBrush(self._bg)
            painter.setPen(QPen(QColor(0, 0, 0, 60)))
            painter.drawRect(x - 2, y, tw + 4, th + 2)
            painter.setPen(self._pen)
            painter.drawText(x, y + th - 1, text)

    def boundingRect(self):
        return QRectF(self._canvas_ref.rect())


class ProfilePointTool(QgsMapTool):
    """
    Map tool for selecting profile origin points.

    This tool allows users to click on the map to select an origin point
    (WHERE to draw the profile chart). It provides visual feedback with a
    temporary marker and emits the selected point coordinates when clicked.

    Signals:
        originSelected(QgsPointXY): Emitted when user clicks on the map with the origin point coordinates
        deactivated(): Emitted when the tool is deactivated
    """

    # Signals
    originSelected = pyqtSignal(QgsPointXY)  # Renamed from pointSelected
    deactivated = pyqtSignal()

    def __init__(self, canvas):
        """
        Initialize the ProfilePointTool.

        Args:
            canvas (QgsMapCanvas): The QGIS map canvas
        """
        super(ProfilePointTool, self).__init__(canvas)
        self.canvas = canvas
        self.rubber_band = None
        self.preview_band = None
        self.preview_ticks_band = None
        self.preview_baseline_band = None
        self.preview_grid_band = None
        self._preview_generator = None  # Callable taking QgsPointXY -> dict with polylines
        self.preview_label_items = []
        self._last_hover_point = None

        # Initialize rubber band for visual feedback
        self._init_rubber_band()

        log("ProfilePointTool initialized")

    def _init_rubber_band(self):
        """Initialize the rubber band for visual feedback."""
        # Create rubber band for point visualization
        self.rubber_band = QgsRubberBand(self.canvas, _GEOM_POINT)

        # Set appearance
        self.rubber_band.setColor(QColor(255, 0, 0, 180))  # Red with transparency
        self.rubber_band.setWidth(3)
        self.rubber_band.setIcon(_ICON_CIRCLE)
        self.rubber_band.setIconSize(15)

        # Create rubber band for profile preview (line)
        self.preview_band = QgsRubberBand(self.canvas, _GEOM_LINE)
        self.preview_band.setColor(QColor(0, 120, 215, 180))  # Blue-ish
        self.preview_band.setWidth(2)
        self.preview_band.hide()

        # Create rubber band for tick preview (line)
        self.preview_ticks_band = QgsRubberBand(self.canvas, _GEOM_LINE)
        self.preview_ticks_band.setColor(QColor(128, 128, 128, 160))  # Gray
        self.preview_ticks_band.setWidth(1)
        self.preview_ticks_band.hide()

        # Baseline (horizontal axis) preview
        self.preview_baseline_band = QgsRubberBand(self.canvas, _GEOM_LINE)
        self.preview_baseline_band.setColor(QColor(0, 0, 0, 220))  # Black
        self.preview_baseline_band.setWidth(3)
        self.preview_baseline_band.hide()

        # Grid (full verticals) preview
        self.preview_grid_band = QgsRubberBand(self.canvas, _GEOM_LINE)
        self.preview_grid_band.setColor(QColor(170, 170, 170, 140))
        self.preview_grid_band.setWidth(1)
        self.preview_grid_band.hide()

        # Hide initially
        self.rubber_band.hide()

    def canvasPressEvent(self, event):
        """
        Handle mouse press event on canvas.

        Args:
            event (QgsMapMouseEvent): The mouse event
        """
        # We'll handle the click on release, but we can use press for other interactions
        pass

    def canvasReleaseEvent(self, event):
        """
        Handle mouse release event on canvas.
        This is where we capture the point selection.

        Args:
            event (QgsMapMouseEvent): The mouse event
        """
        # Only respond to left-click
        if event.button() != Qt.LeftButton:
            return

        # Get the clicked point in map coordinates
        point = self.toMapCoordinates(event.pos())

        log(f"Origin point selected at X={point.x():.2f}, Y={point.y():.2f}")

        # Show visual feedback
        self._show_point_feedback(point)

        # Emit signal with the selected origin point
        self.originSelected.emit(point)

    def canvasMoveEvent(self, event):
        """
        Handle mouse move event on canvas.
        Can be used for hover effects or preview.

        Args:
            event (QgsMapMouseEvent): The mouse event
        """
        # Live preview of profile at the hovered origin point
        try:
            if not self._preview_generator:
                return
            point = self.toMapCoordinates(event.pos())
            # Track last hovered map point for potential fallback if user doesn't click
            try:
                self._last_hover_point = QgsPointXY(point.x(), point.y())
            except Exception:
                self._last_hover_point = point
            preview = self._preview_generator(point)

            # Expecting preview dict with optional keys 'profile_line' (list[QgsPointXY])
            # and 'tick_segments' (list[list[QgsPointXY]] with two points each)
            # Update main profile preview
            self.preview_band.reset(_GEOM_LINE)
            profile_pts = preview.get('profile_line', [])
            if profile_pts:
                geom = QgsGeometry.fromPolylineXY(profile_pts)
                self.preview_band.setToGeometry(geom, None)
                self.preview_band.show()
            else:
                self.preview_band.hide()

            # Update baseline
            self.preview_baseline_band.reset(_GEOM_LINE)
            baseline_pts = preview.get('baseline', [])
            if baseline_pts:
                geom = QgsGeometry.fromPolylineXY(baseline_pts)
                self.preview_baseline_band.setToGeometry(geom, None)
                self.preview_baseline_band.show()
            else:
                self.preview_baseline_band.hide()

            # Update ticks preview (as multi-segment)
            self.preview_ticks_band.reset(_GEOM_LINE)
            tick_segments = preview.get('tick_segments', [])
            if tick_segments:
                # Aggregate as multiLineString
                # Build one big geometry by adding each small segment
                for seg in tick_segments:
                    if len(seg) >= 2:
                        geom = QgsGeometry.fromPolylineXY(seg)
                        # RubberBand can't append multiple geometries at once; draw sequentially
                        self.preview_ticks_band.addGeometry(geom, None)
                self.preview_ticks_band.show()
            else:
                self.preview_ticks_band.hide()

            # Update grid preview
            self.preview_grid_band.reset(_GEOM_LINE)
            grid_segments = preview.get('grid_segments', [])
            if grid_segments:
                for seg in grid_segments:
                    if len(seg) >= 2:
                        geom = QgsGeometry.fromPolylineXY(seg)
                        self.preview_grid_band.addGeometry(geom, None)
                self.preview_grid_band.show()
            else:
                self.preview_grid_band.hide()

            # Update tick labels (canvas-painted labels — works on QGIS 3 and 4)
            self._clear_preview_labels()
            tick_labels = preview.get('tick_labels', [])
            if tick_labels:
                label_item = _PreviewLabelCanvasItem(self.canvas, tick_labels)
                label_item.show()
                self.preview_label_items.append(label_item)
        except Exception as e:
            log(f"preview failed: {e}", "WARNING")

    def get_last_hover_point(self):
        """Return the last hovered map point (QgsPointXY) or None."""
        return self._last_hover_point

    def _show_point_feedback(self, point):
        """
        Show visual feedback at the selected point location.

        Args:
            point (QgsPointXY): The point to highlight
        """
        if self.rubber_band:
            # Clear previous rubber band
            self.rubber_band.reset(_GEOM_POINT)

            # Add the point
            self.rubber_band.addPoint(point)

            # Show the rubber band
            self.rubber_band.show()

            log("Visual feedback displayed at point")

    def clear_feedback(self):
        """Clear the visual feedback rubber band."""
        if self.rubber_band:
            self.rubber_band.reset(_GEOM_POINT)
            self.rubber_band.hide()
            log("Visual feedback cleared")
        if self.preview_band:
            self.preview_band.reset(_GEOM_LINE)
            self.preview_band.hide()
        if self.preview_ticks_band:
            self.preview_ticks_band.reset(_GEOM_LINE)
            self.preview_ticks_band.hide()
        if self.preview_baseline_band:
            self.preview_baseline_band.reset(_GEOM_LINE)
            self.preview_baseline_band.hide()
        if self.preview_grid_band:
            self.preview_grid_band.reset(_GEOM_LINE)
            self.preview_grid_band.hide()
        self._clear_preview_labels()

    def activate(self):
        """
        Called when the tool is activated.
        Sets up the tool for use.
        """
        super(ProfilePointTool, self).activate()

        # Set cursor
        self.canvas.setCursor(Qt.CrossCursor)

        # Clear any previous feedback
        self.clear_feedback()

        log("ProfilePointTool activated")

    def deactivate(self):
        """
        Called when the tool is deactivated.
        Cleans up visual elements.
        """
        super(ProfilePointTool, self).deactivate()

        # Clear rubber band
        self.clear_feedback()

        self.deactivated.emit()

        log("ProfilePointTool deactivated")

    def isZoomTool(self):
        """
        Indicates this is not a zoom tool.

        Returns:
            bool: False
        """
        return False

    def isTransient(self):
        """
        Indicates this tool is transient (temporary).

        Returns:
            bool: True - tool should be deactivated after use
        """
        return False  # Set to False so tool stays active until manually deactivated

    def isEditTool(self):
        """
        Indicates this is not an edit tool.

        Returns:
            bool: False
        """
        return False

    def flags(self):
        """
        Return flags for the map tool.

        Returns:
            QgsMapTool.Flags: Tool flags
        """
        return QgsMapTool.Flags()

    # ================= Preview API =================
    def set_preview_generator(self, generator_callable):
        """Provide a callable that produces preview geometry for a candidate origin.
        The callable should accept QgsPointXY and return a dict with keys:
          - 'profile_line': list[QgsPointXY]
          - 'tick_segments': list[list[QgsPointXY]]
          - 'tick_labels': list[{'pos': QgsPointXY, 'text': str}]
        """
        self._preview_generator = generator_callable

    def _clear_preview_labels(self):
        """Remove and clear all preview label items from canvas."""
        if not self.preview_label_items:
            return
        for item in self.preview_label_items:
            try:
                item.hide()
                # QgsMapCanvasItem subclasses need to be removed from the scene
                scene = self.canvas.scene()
                if scene and item.scene():
                    scene.removeItem(item)
            except Exception:
                pass
        self.preview_label_items = []


class ProfilePointToolManager:
    """
    Manager class to handle ProfilePointTool lifecycle and integration.

    This class simplifies the management of the map tool, including activation,
    deactivation, and cleanup. It's designed to be used by the main plugin class.
    """

    def __init__(self, canvas, iface):
        """
        Initialize the tool manager.

        Args:
            canvas (QgsMapCanvas): The QGIS map canvas
            iface (QgisInterface): The QGIS interface object
        """
        self.canvas = canvas
        self.iface = iface
        self.tool = None
        self.previous_tool = None

        log("ProfilePointToolManager initialized")

    def create_tool(self):
        """
        Create a new instance of ProfilePointTool.

        Returns:
            ProfilePointTool: The created tool instance
        """
        if self.tool is None:
            self.tool = ProfilePointTool(self.canvas)
            log("ProfilePointTool instance created")

        return self.tool

    def activate_tool(self):
        """
        Activate the ProfilePointTool.
        Saves the current tool to restore later.
        """
        # Save current tool
        self.previous_tool = self.canvas.mapTool()

        # Create tool if it doesn't exist
        if self.tool is None:
            self.create_tool()

        # Set as active tool
        self.canvas.setMapTool(self.tool)

        log("ProfilePointTool activated via manager")

    def deactivate_tool(self):
        """
        Deactivate the ProfilePointTool and restore previous tool.
        """
        if self.tool:
            # Clear feedback
            self.tool.clear_feedback()

        # Restore previous tool
        if self.previous_tool:
            self.canvas.setMapTool(self.previous_tool)
            log("Previous tool restored")
        else:
            self.canvas.unsetMapTool(self.tool)
            log("Map tool unset")

        self.previous_tool = None

    def cleanup(self):
        """
        Clean up the tool and manager.
        Call this when the plugin is unloaded.
        """
        if self.tool:
            self.deactivate_tool()
            self.tool = None

        log("ProfilePointToolManager cleaned up")

    def get_tool(self):
        """
        Get the current tool instance.

        Returns:
            ProfilePointTool: The tool instance or None
        """
        return self.tool
