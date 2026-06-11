# -*- coding: utf-8 -*-
"""
logger.py - Central logging utility for qAeroChart.

Routes messages to QgsMessageLog when running inside QGIS, and falls back to
print() when the QGIS runtime is unavailable (e.g., unit tests).
"""
from __future__ import annotations

_TAG = "qAeroChart"


def _normalize_msg_level(level):
    """Convert level to Qgis.MessageLevel enum for QGIS 3 and 4 compatibility.

    QGIS 3 (PyQt5): Qgis.Warning = 1 (plain int).
    QGIS 4 (PyQt6): pushMessage requires Qgis.MessageLevel enum, not plain int.
    """
    try:
        from qgis.core import Qgis
        MessageLevel = getattr(Qgis, 'MessageLevel', None)
        if MessageLevel is not None and isinstance(level, MessageLevel):
            return level          # already the correct enum type
        _names = {0: 'Info', 1: 'Warning', 2: 'Critical', 3: 'Success'}
        try:
            int_val = int(level)
        except (TypeError, ValueError):
            int_val = 0
        name = _names.get(int_val, 'Info')
        if MessageLevel is not None:
            return getattr(MessageLevel, name, MessageLevel.Info)
        return getattr(Qgis, name, 0)
    except Exception:
        return level


def log(msg: str, level: str = "INFO") -> None:
    """
    Log a message to QgsMessageLog with a fallback to print().

    Args:
        msg: The message text.
        level: Severity — "INFO", "WARNING", or "CRITICAL".
    """
    try:
        from qgis.core import QgsMessageLog, Qgis
        _name_map = {"INFO": "Info", "WARNING": "Warning", "CRITICAL": "Critical"}
        name = _name_map.get(level.upper(), "Info")
        qgis_level = _normalize_msg_level(
            getattr(getattr(Qgis, 'MessageLevel', None), name, None)
            or getattr(Qgis, name, 0)
        )
        QgsMessageLog.logMessage(msg, _TAG, qgis_level)
    except Exception:
        print(f"[{_TAG}] {level.upper()}: {msg}")


def push_message(iface, title: str, text: str, level=None, duration: int = 5) -> None:
    """Push a message to the QGIS message bar, compatible with QGIS 3 and 4.

    Normalises integer level values to Qgis.MessageLevel enums required
    by QGIS 4 / PyQt6.  Falls back to print() outside QGIS.

    Args:
        iface: QGIS interface object.
        title: Short title shown in the bar.
        text: Detail text.
        level: Qgis.MessageLevel value or plain int (0–3).  Defaults to Info.
        duration: Seconds before the message auto-dismisses.
    """
    try:
        from qgis.core import Qgis
        if level is None:
            # Resolve Info safely — Qgis.Info in QGIS 3, Qgis.MessageLevel.Info in QGIS 4
            _ML = getattr(Qgis, "MessageLevel", None)
            level = getattr(_ML, "Info", None) if _ML else None
            if level is None:
                level = getattr(Qgis, "Info", 0)
        normalized = _normalize_msg_level(level)
        iface.messageBar().pushMessage(title, text, level=normalized, duration=duration)
    except Exception:
        print(f"[{_TAG}] {title}: {text}")
