# -*- coding: utf-8 -*-
"""
TableStyleManager — persists named table style configs in QgsProject settings.

A *table style* defines the visual / placement parameters for a Distance/Altitude
Table so users can switch between named presets (e.g. 'ICAO', 'Honduras') instead
of re-entering all values manually.

Each config stores:
  name            Display name for the preset
  top_left_text   Default cell (0, 0) — e.g. "NM TO RWY00"
  first_col_text  Default cell (1, 0) — e.g. "ALTITUDE"
  total_width     Total table width (mm)
  first_col_width First-column width (mm)
  height          Row height (mm)
  stroke          Grid stroke width (mm)
  cell_margin     Cell margin (mm)
  font_family     Font family string
  font_size       Font size (pt)

Built-in styles ("Default", "ICAO") are always available and cannot be
deleted.  Project-specific styles are stored in QgsProject settings under the
``qAeroChart`` section (same as the other managers in this package).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from qgis.core import QgsProject

from ..utils.logger import log


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Built-in presets — always available, cannot be deleted
# ---------------------------------------------------------------------------

BUILTIN_STYLES: dict[str, dict[str, Any]] = {
    "Default": {
        "name": "Default",
        "top_left_text": "NM TO RWY00",
        "first_col_text": "ALTITUDE",
        "total_width": 180.20,
        "first_col_width": 36.20,
        "height": 14.0,
        "stroke": 0.25,
        "cell_margin": 2.0,
        "font_family": "Arial",
        "font_size": 8.0,
    },
    "ICAO": {
        "name": "ICAO",
        "top_left_text": "NM TO THR",
        "first_col_text": "ALTITUDE",
        "total_width": 180.20,
        "first_col_width": 30.00,
        "height": 14.0,
        "stroke": 0.25,
        "cell_margin": 2.0,
        "font_family": "Arial",
        "font_size": 8.0,
    },
}


class TableStyleManager:
    """Persist named table style configs in QgsProject settings (Issue #71)."""

    _SECTION = "qAeroChart"
    _LIST_KEY = "qaerochart_table_styles"
    _CFG_PREFIX = "qaerochart_tstyle_"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _project(self) -> QgsProject:
        return QgsProject.instance()

    def _read(self, key: str, default: str = "") -> str:
        val, _ = self._project().readEntry(self._SECTION, key, default)
        return val or default

    def _write(self, key: str, value: str) -> None:
        self._project().writeEntry(self._SECTION, key, value)

    def _remove(self, key: str) -> None:
        self._project().removeEntry(self._SECTION, key)

    def _get_list(self) -> list[dict]:
        raw = self._read(self._LIST_KEY, "[]")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def _set_list(self, items: list[dict]) -> None:
        self._write(self._LIST_KEY, json.dumps(items))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        """Return lightweight metadata list including built-ins.

        Returns [{name, builtin}, ...], built-ins first then project styles.
        """
        builtins = [{"name": n, "builtin": True} for n in BUILTIN_STYLES]
        project_items = [
            {"name": item["name"], "builtin": False}
            for item in self._get_list()
        ]
        return builtins + project_items

    def get_config(self, name: str) -> dict | None:
        """Return full config for *name*, checking built-ins first."""
        if name in BUILTIN_STYLES:
            return dict(BUILTIN_STYLES[name])
        for item in self._get_list():
            if item.get("name") == name:
                sid = item.get("id", "")
                raw = self._read(f"{self._CFG_PREFIX}{sid}", "{}")
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    return None
        return None

    def save_new(self, params: dict) -> str:
        """Persist a new style config. Returns the new style id."""
        sid = f"tstyle_{uuid.uuid4().hex[:8]}"
        name = params.get("name", "Style")
        items = self._get_list()
        items.append({"id": sid, "name": name, "created": _now()})
        self._set_list(items)
        self._write(f"{self._CFG_PREFIX}{sid}", json.dumps(params))
        log(f"TableStyleManager: saved '{name}' as {sid}")
        return sid

    def update(self, name: str, params: dict) -> bool:
        """Update an existing project style by name. Returns True if found."""
        if name in BUILTIN_STYLES:
            return False
        for item in self._get_list():
            if item.get("name") == name:
                sid = item["id"]
                self._write(f"{self._CFG_PREFIX}{sid}", json.dumps(params))
                log(f"TableStyleManager: updated '{name}'")
                return True
        return False

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a project style. Returns True on success."""
        if old_name in BUILTIN_STYLES:
            return False
        items = self._get_list()
        for item in items:
            if item.get("name") == old_name:
                sid = item["id"]
                item["name"] = new_name
                self._set_list(items)
                # Update the name inside the stored config too
                raw = self._read(f"{self._CFG_PREFIX}{sid}", "{}")
                try:
                    cfg = json.loads(raw)
                    cfg["name"] = new_name
                    self._write(f"{self._CFG_PREFIX}{sid}", json.dumps(cfg))
                except (json.JSONDecodeError, ValueError):
                    pass
                log(f"TableStyleManager: renamed '{old_name}' → '{new_name}'")
                return True
        return False

    def delete(self, name: str) -> bool:
        """Delete a project style by name. Built-ins cannot be deleted."""
        if name in BUILTIN_STYLES:
            return False
        items = self._get_list()
        for item in items:
            if item.get("name") == name:
                sid = item["id"]
                self._remove(f"{self._CFG_PREFIX}{sid}")
                self._set_list([i for i in items if i.get("name") != name])
                log(f"TableStyleManager: deleted '{name}'")
                return True
        return False

    def load_all_configs(self) -> list[dict]:
        """Return all full configs (built-ins + project) for persistence round-trip."""
        result = list(BUILTIN_STYLES.values())
        for item in self._get_list():
            sid = item.get("id", "")
            raw = self._read(f"{self._CFG_PREFIX}{sid}", "{}")
            try:
                cfg = json.loads(raw)
                result.append(cfg)
            except (json.JSONDecodeError, ValueError):
                pass
        return result
