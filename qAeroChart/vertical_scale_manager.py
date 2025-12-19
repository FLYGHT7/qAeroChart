# -*- coding: utf-8 -*-
"""
VerticalScaleManager - Persist vertical scale configurations in QGIS project.

Stores configs as project entries so they survive plugin reloads, similar to ProfileManager.
Each scale entry keeps:
- id: unique string
- name: display name
- params: full dict for run_vertical_scale
- created: timestamp
"""
from qgis.core import QgsProject
import json
import time


class VerticalScaleManager:
    PREFIX = "qaerochart_vscale_"
    LIST_KEY = "qaerochart_vscales"

    def __init__(self):
        self.project = QgsProject.instance()

    def _write(self, key: str, value: str):
        self.project.writeEntry("qAeroChart", key, value)

    def _read(self, key: str, default=""):
        return self.project.readEntry("qAeroChart", key, default)[0]

    def get_all(self):
        """Return list of metadata dicts with id/name/created."""
        raw = self._read(self.LIST_KEY, "[]")
        try:
            return json.loads(raw)
        except Exception:
            return []

    def _save_list(self, items):
        try:
            self._write(self.LIST_KEY, json.dumps(items))
        except Exception:
            pass

    def save_new(self, params: dict):
        """Save a new scale config; returns new id."""
        sid = f"vscale_{int(time.time() * 1000)}"
        self.save_config(sid, params)
        items = self.get_all()
        items.append({
            "id": sid,
            "name": params.get("name", "Vertical Scale"),
            "created": time.time(),
        })
        self._save_list(items)
        return sid

    def save_config(self, sid: str, params: dict):
        try:
            self._write(f"{self.PREFIX}{sid}", json.dumps(params))
        except Exception:
            pass

    def get_config(self, sid: str):
        raw = self._read(f"{self.PREFIX}{sid}", "")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def update(self, sid: str, params: dict):
        if not sid:
            return sid
        self.save_config(sid, params)
        # Update list metadata name
        items = self.get_all()
        changed = False
        for it in items:
            if it.get("id") == sid:
                it["name"] = params.get("name", it.get("name", "Vertical Scale"))
                changed = True
                break
        if changed:
            self._save_list(items)
        return sid

    def rename(self, sid: str, new_name: str):
        if not sid or not new_name:
            return False
        items = self.get_all()
        found = False
        for it in items:
            if it.get("id") == sid:
                it["name"] = new_name
                found = True
                break
        if found:
            self._save_list(items)
        cfg = self.get_config(sid)
        if cfg:
            cfg["name"] = new_name
            self.save_config(sid, cfg)
        return found

    def delete(self, sid: str):
        if not sid:
            return False
        try:
            self.project.removeEntry("qAeroChart", f"{self.PREFIX}{sid}")
        except Exception:
            pass
        items = [it for it in self.get_all() if it.get("id") != sid]
        self._save_list(items)
        return True

    def load_all_configs(self):
        """Return list of full configs including id and name merged."""
        result = []
        for meta in self.get_all():
            sid = meta.get("id")
            cfg = self.get_config(sid) or {}
            cfg["id"] = sid
            if "name" not in cfg:
                cfg["name"] = meta.get("name", "Vertical Scale")
            result.append(cfg)
        return result
