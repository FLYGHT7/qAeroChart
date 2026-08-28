# -*- coding: utf-8 -*-
"""
NorthArrowTool — map tool for placing a north-arrow figure by clicking.

Provides a live rubber-band preview of the two north lines (true + magnetic)
that follow the cursor.  Single-click emits ``arrowPlaced(QgsPointXY)`` with
the clicked map point.  The tool stays active so several arrows can be placed
in a row; the dock deactivates it explicitly or the user switches tools.

Preview is driven by a generator callable supplied by the dock via
``set_preview_generator`` — the same pattern used by ``ProfilePointTool``
(issues #85, #108, #151).
"""
from __future__ import annotations

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsMapTool, QgsRubberBand

from ..utils.logger import log
from ..utils.qt_compat import Qt

# ---------------------------------------------------------------------------
# QGIS 3 / 4 compatibility for geometry type enums
# ---------------------------------------------------------------------------
try:
    from qgis.core import Qgis as _Qgis
    _GEOM_LINE = _Qgis.GeometryType.Line
except AttributeError:
    from qgis.core import QgsWkbTypes as _QgsWkbTypes
    _GEOM_LINE = _QgsWkbTypes.LineGeometry


class NorthArrowTool(QgsMapTool):
    """Click-to-place map tool for north arrows with live preview (Issue #151)."""

    arrowPlaced = pyqtSignal(QgsPointXY)
    deactivated = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._preview_generator = None  # callable: QgsPointXY → dict

        # Rubberbands for live preview
        self._true_band = QgsRubberBand(self._canvas, _GEOM_LINE)
        self._true_band.setColor(QColor(0, 0, 0, 200))  # black, semi-transparent
        self._true_band.setWidth(2)
        self._true_band.hide()

        self._mag_band = QgsRubberBand(self._canvas, _GEOM_LINE)
        self._mag_band.setColor(QColor(0, 100, 200, 200))  # blue, semi-transparent
        self._mag_band.setWidth(2)
        self._mag_band.setLineStyle(Qt.DashLine)
        self._mag_band.hide()

    # ------------------------------------------------------------------
    # Preview API
    # ------------------------------------------------------------------

    def set_preview_generator(self, generator_callable):
        """Provide a callable that produces preview geometry.

        The callable should accept a ``QgsPointXY`` (cursor position) and
        return a dict with:

        - ``'true_line'``: ``list[QgsPointXY]`` — origin → true-north tip
        - ``'mag_line'``: ``list[QgsPointXY]`` — origin → magnetic-north tip
        """
        self._preview_generator = generator_callable

    # ------------------------------------------------------------------
    # Canvas events
    # ------------------------------------------------------------------

    def canvasMoveEvent(self, event):
        """Live preview: update rubberbands at cursor position."""
        if not self._preview_generator:
            return
        try:
            pt = self.toMapCoordinates(event.pos())
            preview = self._preview_generator(pt)

            # True-north line (solid)
            true_pts = preview.get('true_line', [])
            self._true_band.reset(_GEOM_LINE)
            if true_pts:
                geom = QgsGeometry.fromPolylineXY(true_pts)
                self._true_band.setToGeometry(geom, None)
                self._true_band.show()
            else:
                self._true_band.hide()

            # Magnetic-north line (dashed)
            mag_pts = preview.get('mag_line', [])
            self._mag_band.reset(_GEOM_LINE)
            if mag_pts:
                geom = QgsGeometry.fromPolylineXY(mag_pts)
                self._mag_band.setToGeometry(geom, None)
                self._mag_band.show()
            else:
                self._mag_band.hide()
        except Exception as exc:
            log(f"NorthArrowTool preview failed: {exc}", "WARNING")

    def canvasReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pt = self.toMapCoordinates(event.pos())
        log(f"NorthArrowTool: arrow placed at ({pt.x():.2f}, {pt.y():.2f})")
        self.arrowPlaced.emit(pt)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> None:
        super().activate()
        self._canvas.setCursor(Qt.CrossCursor)
        self.clear_feedback()

    def deactivate(self) -> None:
        super().deactivate()
        self.clear_feedback()
        self.deactivated.emit()

    def clear_feedback(self):
        """Reset and hide all preview rubberbands."""
        self._true_band.reset(_GEOM_LINE)
        self._true_band.hide()
        self._mag_band.reset(_GEOM_LINE)
        self._mag_band.hide()

    # ------------------------------------------------------------------
    # Required overrides
    # ------------------------------------------------------------------

    def isZoomTool(self) -> bool:
        return False

    def isTransient(self) -> bool:
        return False

    def isEditTool(self) -> bool:
        return False
