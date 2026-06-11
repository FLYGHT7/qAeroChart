# -*- coding: utf-8 -*-
"""
VerticalScaleManager — persists vertical-scale configurations in the QGIS
project settings (QgsProject.writeEntry / readEntry).

Each configuration is stored as a JSON string under the key
``"qaerochart_vscale_{id}"``.  A separate list entry (``"qaerochart_vscales"``)
keeps lightweight metadata (id, name, created timestamp) so the UI can
enumerate scales without loading every full config.

Design mirrors ProfileManager but uses QGIS project entries instead of JSON
files so the scale data travels with the ``.qgz`` project.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from qgis.core import QgsProject

from ..utils.logger import log


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class VerticalScaleManager:
    """Persist vertical-scale configurations in QgsProject settings."""

    _SECTION = "qAeroChart"
    _LIST_KEY = "qaerochart_vscales"
    _CFG_PREFIX = "qaerochart_vscale_"

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
        """Return lightweight metadata list: [{id, name, created}, ...]."""
        return self._get_list()

    def save_new(self, params: dict) -> str:
        """Persist a new scale configuration. Returns the new scale id."""
        sid = f"vscale_{uuid.uuid4().hex[:8]}"
        items = self._get_list()
        items.append(
            {"id": sid, "name": params.get("name", "Scale"), "created": _now()}
        )
        self._set_list(items)
        self._write(f"{self._CFG_PREFIX}{sid}", json.dumps(params))
        log(f"VerticalScaleManager: saved '{params.get('name')}' as {sid}")
        return sid

    def get_config(self, sid: str) -> dict | None:
        """Return the full configuration dict for *sid*, or None if not found."""
        raw = self._read(f"{self._CFG_PREFIX}{sid}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            log(f"VerticalScaleManager: corrupt config for {sid}", "WARNING")
            return None

    def update(self, sid: str, params: dict) -> str:
        """Overwrite the configuration for *sid*. Returns *sid*."""
        self._write(f"{self._CFG_PREFIX}{sid}", json.dumps(params))
        items = self._get_list()
        for item in items:
            if item["id"] == sid:
                item["name"] = params.get("name", item["name"])
                break
        self._set_list(items)
        return sid

    def rename(self, sid: str, new_name: str) -> bool:
        """Rename a scale in the metadata list. Returns True on success."""
        items = self._get_list()
        for item in items:
            if item["id"] == sid:
                item["name"] = new_name
                self._set_list(items)
                return True
        return False

    def delete(self, sid: str) -> bool:
        """Remove a scale and its config. Returns True when the id was found."""
        items = self._get_list()
        new_items = [it for it in items if it["id"] != sid]
        if len(new_items) == len(items):
            return False
        self._set_list(new_items)
        self._remove(f"{self._CFG_PREFIX}{sid}")
        log(f"VerticalScaleManager: deleted {sid}")
        return True

    def load_all_configs(self) -> list[dict]:
        """Return full configs for all persisted scales."""
        result = []
        for item in self._get_list():
            cfg = self.get_config(item["id"])
            if cfg is not None:
                result.append(cfg)
        return result
