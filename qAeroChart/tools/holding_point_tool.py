# -*- coding: utf-8 -*-
"""
HoldingFixTool — map tool for selecting the holding fix point.

Single-click picks the fix and emits fixSelected(QgsPointXY).
The tool stays active until the user picks a point or explicitly cancels.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsPointXY
from qgis.gui import QgsMapTool, QgsRubberBand

from ..utils.logger import log
from ..utils.qt_compat import Qt

# ---------------------------------------------------------------------------
# QGIS 3 / 4 geometry-type enum compat
# ---------------------------------------------------------------------------
try:
    from qgis.core import Qgis as _Qgis
    _GEOM_POINT = _Qgis.GeometryType.Point
except AttributeError:
    from qgis.core import QgsWkbTypes as _QWT  # type: ignore[attr-defined]
    _GEOM_POINT = _QWT.PointGeometry

# ---------------------------------------------------------------------------
# QGIS 3 / 4 rubber-band icon enum compat
# ---------------------------------------------------------------------------
_ICON_CIRCLE = getattr(QgsRubberBand, "ICON_CIRCLE", None)
if _ICON_CIRCLE is None:
    try:
        _ICON_CIRCLE = QgsRubberBand.IconType.ICON_CIRCLE
    except AttributeError:
        _ICON_CIRCLE = 4  # numeric fallback


class HoldingFixTool(QgsMapTool):
    """Single-pick map tool for the holding fix point."""

    fixSelected = pyqtSignal(QgsPointXY)
    deactivated = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._rb: QgsRubberBand | None = None
        self._init_rubber_band()

    def _init_rubber_band(self) -> None:
        self._rb = QgsRubberBand(self._canvas, _GEOM_POINT)
        self._rb.setColor(QColor(255, 0, 255, 220))
        self._rb.setWidth(3)
        self._rb.setIcon(_ICON_CIRCLE)
        self._rb.setIconSize(12)
        self._rb.hide()

    # ------------------------------------------------------------------
    # Canvas events
    # ------------------------------------------------------------------

    def canvasReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pt = self.toMapCoordinates(event.pos())
        if self._rb:
            self._rb.reset(_GEOM_POINT)
            self._rb.addPoint(pt)
            self._rb.show()
        log(f"HoldingFixTool: fix selected at ({pt.x():.2f}, {pt.y():.2f})")
        self.fixSelected.emit(pt)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> None:
        super().activate()
        self._canvas.setCursor(Qt.CrossCursor)

    def deactivate(self) -> None:
        self.clear()
        super().deactivate()
        self.deactivated.emit()

    def clear(self) -> None:
        if self._rb:
            self._rb.reset(_GEOM_POINT)
            self._rb.hide()

    # ------------------------------------------------------------------
    # Required overrides
    # ------------------------------------------------------------------

    def isZoomTool(self) -> bool:
        return False

    def isTransient(self) -> bool:
        return False

    def isEditTool(self) -> bool:
        return False
