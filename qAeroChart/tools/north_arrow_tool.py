# -*- coding: utf-8 -*-
"""
NorthArrowTool — map tool for placing a north-arrow figure by clicking.

Single-click emits ``arrowPlaced(QgsPointXY)`` with the clicked map point.
The tool stays active so several arrows can be placed in a row; the dock
deactivates it explicitly or the user switches tools.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import QgsPointXY
from qgis.gui import QgsMapToolEmitPoint

from ..utils.logger import log
from ..utils.qt_compat import Qt


class NorthArrowTool(QgsMapToolEmitPoint):
    """Click-to-place map tool for north arrows (Issue #108)."""

    arrowPlaced = pyqtSignal(QgsPointXY)
    deactivated = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas

    # ------------------------------------------------------------------
    # Canvas events
    # ------------------------------------------------------------------

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

    def deactivate(self) -> None:
        super().deactivate()
        self.deactivated.emit()

    # ------------------------------------------------------------------
    # Required overrides
    # ------------------------------------------------------------------

    def isZoomTool(self) -> bool:
        return False

    def isTransient(self) -> bool:
        return False

    def isEditTool(self) -> bool:
        return False
