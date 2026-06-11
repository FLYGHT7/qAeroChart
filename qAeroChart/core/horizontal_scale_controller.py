# -*- coding: utf-8 -*-
"""
HorizontalScaleController — MVC mediator between HorizontalScaleDockWidget
and HorizontalScaleManager / LayerManager.

Mirrors VerticalScaleController exactly, using horizontal-scale methods.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QObject, pyqtSignal

from .horizontal_scale_manager import HorizontalScaleManager
from .layer_manager import LayerManager
from ..utils.logger import log
from ..utils.qt_compat import MsgLevel


class HorizontalScaleController(QObject):
    """Mediator between HorizontalScaleDockWidget, HorizontalScaleManager, and LayerManager."""

    # (title, text, Qgis.MessageLevel int)
    message: pyqtSignal = pyqtSignal(str, str, int)
    # Emitted after any change to the persisted scale list
    scales_changed: pyqtSignal = pyqtSignal()

    def __init__(
        self,
        scale_manager: HorizontalScaleManager,
        layer_manager: LayerManager | None = None,
    ) -> None:
        super().__init__()
        self._scale_manager = scale_manager
        self._layer_manager = layer_manager

    def _emit_msg(self, title: str, text: str, level) -> None:
        """Emit ``message`` signal with int-casted level (PyQt6 strict enum safety)."""
        self.message.emit(title, text, int(level))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_all_scales(self) -> list[dict]:
        """Return lightweight metadata list from the manager."""
        return self._scale_manager.get_all()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def run_scale(self, params: dict) -> bool:
        """Draw a horizontal scale on the map and persist the configuration."""
        if self._layer_manager is None:
            log("HorizontalScaleController.run_scale: no layer manager", "WARNING")
            return False

        try:
            bp = params.get("basepoint", {})
            self._layer_manager.create_horizontal_scale_run(
                name=params.get("name", "Horizontal Scale"),
                basepoint_x=float(bp.get("x", 0.0)),
                basepoint_y=float(bp.get("y", 0.0)),
                angle=float(params.get("angle", 90.0)),
                offset=float(params.get("offset", -50.0)),
                tick_len=float(params.get("tick_len", 15.0)),
                metre_right=int(params.get("metre_right", 2500)),
                metre_left=int(params.get("metre_left", 400)),
                metre_right_step=int(params.get("metre_right_step", 500)),
                metre_left_step=int(params.get("metre_left_step", 100)),
                ft_right=int(params.get("ft_right", 8000)),
                ft_left=int(params.get("ft_left", 1000)),
                ft_right_step=int(params.get("ft_right_step", 1000)),
                ft_left_step=int(params.get("ft_left_step", 100)),
            )
            self._scale_manager.save_new(params)
            self.scales_changed.emit()
            self._emit_msg(
                "Horizontal Scale",
                f"Scale '{params.get('name', 'Horizontal Scale')}' generated successfully.",
                MsgLevel.Success,
            )
            return True

        except Exception as e:
            log(f"HorizontalScaleController.run_scale failed: {e}", "ERROR")
            self._emit_msg("Horizontal Scale Error", str(e), MsgLevel.Critical)
            return False

    def rename_scale(self, scale_id: str, new_name: str) -> bool:
        """Rename a persisted scale. Returns True on success."""
        try:
            result = self._scale_manager.rename(scale_id, new_name)
            if result:
                self.scales_changed.emit()
                self._emit_msg(
                    "Horizontal Scale",
                    f"Renamed to '{new_name}'.",
                    MsgLevel.Info,
                )
            return result
        except Exception as e:
            log(f"HorizontalScaleController.rename_scale failed: {e}", "ERROR")
            self._emit_msg("Horizontal Scale Error", str(e), MsgLevel.Critical)
            return False

    def delete_scale(self, scale_id: str) -> bool:
        """Delete a persisted scale. Returns True when the id was found."""
        try:
            result = self._scale_manager.delete(scale_id)
            if result:
                self.scales_changed.emit()
                self._emit_msg("Horizontal Scale", "Scale deleted.", MsgLevel.Info)
            return result
        except Exception as e:
            log(f"HorizontalScaleController.delete_scale failed: {e}", "ERROR")
            self._emit_msg("Horizontal Scale Error", str(e), MsgLevel.Critical)
            return False
