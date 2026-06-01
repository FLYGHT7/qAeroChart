# -*- coding: utf-8 -*-
"""
ProfileController - MVC controller mediating between ProfileManager/LayerManager
and the DockWidget view.

Emits signals for all user-visible feedback so the view never reaches into
business-logic paths directly.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QObject, pyqtSignal

from .profile_manager import ProfileManager
from .layer_manager import LayerManager
from .layout_manager import LayoutManager
from ..utils.logger import log
from ..utils.qt_compat import MsgLevel


class ProfileController(QObject):
    """Mediator between ProfileManager/LayerManager and the DockWidget view.

    The view must:
    - Call controller methods to trigger any write operation.
    - Connect to ``message`` and ``profiles_changed`` signals for UI updates.
    - Never call ProfileManager or LayerManager directly.
    """

    # (title, text, Qgis.MessageLevel int) â€” emitted after every user-visible event
    message: pyqtSignal = pyqtSignal(str, str, int)
    # Emitted whenever the profile list has changed (add / delete / rename)
    profiles_changed: pyqtSignal = pyqtSignal()

    def __init__(
        self,
        profile_manager: ProfileManager,
        layer_manager: LayerManager | None = None,
        layout_manager: LayoutManager | None = None,
    ) -> None:
        super().__init__()
        self._profile_manager = profile_manager
        self._layer_manager = layer_manager
        self._layout_manager = layout_manager

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_msg(self, title: str, text: str, level) -> None:
        """Emit ``message`` signal with int-casted level (PyQt6 strict enum safety)."""
        self.message.emit(title, text, int(level))

    # ------------------------------------------------------------------
    # Read-only queries (thin delegation to ProfileManager)
    # ------------------------------------------------------------------

    def get_all_profiles(self) -> list[dict]:
        return self._profile_manager.get_all_profiles()

    def get_profile(self, profile_id: str) -> dict | None:
        return self._profile_manager.get_profile(profile_id)

    def get_profile_display_name(self, profile: dict) -> str:
        return self._profile_manager.get_profile_display_name(profile)

    # ------------------------------------------------------------------
    # Write operations â€” emit signals instead of touching the UI
    # ------------------------------------------------------------------

    def save_or_update_profile(
        self,
        name: str,
        config: dict,
        profile_id: str | None = None,
    ) -> bool:
        """Create or update a profile and optionally draw it.

        Returns True on success.
        """
        try:
            print(f"[qAeroChart][DIAG] save_or_update_profile called, profile_id={profile_id!r}")
            if profile_id:
                self._profile_manager.update_profile(profile_id, name, config)
                success_msg = "Profile has been updated successfully."
            else:
                self._profile_manager.save_profile(name, config)
                success_msg = "Profile has been created and saved successfully."

            print(f"[qAeroChart][DIAG] _layer_manager={self._layer_manager!r}")
            if self._layer_manager:
                print("[qAeroChart][DIAG] Calling create_all_layers...")
                result = self._layer_manager.create_all_layers(config)
                keys = list(result.keys()) if isinstance(result, dict) else result
                print(f"[qAeroChart][DIAG] create_all_layers returned: {keys!r}")
                print("[qAeroChart][DIAG] Calling populate_layers_from_config...")
                pop_result = self._layer_manager.populate_layers_from_config(config)
                print(f"[qAeroChart][DIAG] populate_layers_from_config returned: {pop_result!r}")
                profile_points = config.get("profile_points", [])
                runway_dir = config.get("runway", {}).get("direction", "N/A")
                log(f"Profile saved: dir={runway_dir}, {len(profile_points)} points")
            else:
                print("[qAeroChart][DIAG] WARNING: _layer_manager is None!")
                log("Layer manager not available; profile saved without drawing", "WARNING")

            self._emit_msg("Profile Saved", success_msg, MsgLevel.Success)
            self.profiles_changed.emit()
            return True

        except Exception as e:
            import traceback
            print(f"[qAeroChart][DIAG] save_or_update_profile EXCEPTION: {e}")
            traceback.print_exc()
            log(f"save_or_update_profile failed: {e}", "ERROR")
            self._emit_msg("Profile Error", str(e), MsgLevel.Critical)
            return False

    def delete_profiles(self, profile_ids: list[str]) -> int:
        """Delete profiles by ID list.

        Returns number of successfully deleted profiles.
        """
        deleted = 0
        for pid in profile_ids:
            try:
                self._profile_manager.delete_profile(pid)
                deleted += 1
            except Exception as e:
                log(f"Could not delete profile {pid}: {e}", "ERROR")

        if deleted:
            msg = f"{deleted} profile(s) removed." if deleted > 1 else "Profile has been removed."
            self._emit_msg("Profile Deleted", msg, MsgLevel.Info)
            self.profiles_changed.emit()
            log(f"Deleted {deleted} profile(s)")

        return deleted

    def rename_profile(self, profile_id: str, new_name: str) -> bool:
        """Rename a profile in-place.

        Returns True on success.
        """
        config = self._profile_manager.get_profile(profile_id)
        if not config:
            self._emit_msg(
                "Error",
                "Could not load profile configuration to rename.",
                MsgLevel.Critical,
            )
            return False

        try:
            self._profile_manager.update_profile(profile_id, new_name, config)
            self._emit_msg("Profile Renamed", f"Renamed to '{new_name}'.", MsgLevel.Info)
            self.profiles_changed.emit()
            return True
        except (KeyError, ValueError) as e:
            log(f"rename_profile failed: {e}", "ERROR")
            self._emit_msg("Rename Error", str(e), MsgLevel.Critical)
            return False

    def draw_profile(self, profile_id: str) -> bool:
        """Re-draw an existing profile on the map.

        Returns True on success.
        """
        config = self._profile_manager.get_profile(profile_id)
        if not config:
            self._emit_msg(
                "Error", "Could not load profile configuration.", MsgLevel.Critical
            )
            return False

        if not self._layer_manager:
            log("Layer manager not available", "WARNING")
            return False

        try:
            self._layer_manager.create_all_layers(config)
            self._layer_manager.populate_layers_from_config(config)
            self._emit_msg(
                "Profile Drawn", "Profile has been drawn on the map.", MsgLevel.Success
            )
            log(f"Drew profile {profile_id}")
            return True
        except Exception as e:
            log(f"draw_profile failed: {e}", "ERROR")
            self._emit_msg("Draw Error", str(e), MsgLevel.Critical)
            return False

    def generate_vertical_scale(self, profile_id: str) -> bool:
        """Draw the vertical scale bar for an existing profile (Issue #57).

        Returns True on success.
        """
        config = self._profile_manager.get_profile(profile_id)
        if not config:
            self._emit_msg("Error", "Profile not found.", MsgLevel.Critical)
            return False

        if not self._layer_manager:
            log("Layer manager not available", "WARNING")
            return False

        try:
            self._layer_manager.populate_vertical_scale_layer(config)
            self._emit_msg(
                "Vertical Scale", "Scale bar drawn on the map.", MsgLevel.Success
            )
            log(f"Generated vertical scale for profile {profile_id}")
            return True
        except (ValueError, AttributeError) as e:
            log(f"generate_vertical_scale failed: {e}", "ERROR")
            self._emit_msg("Vertical Scale Error", str(e), MsgLevel.Critical)
            return False

    def generate_distance_altitude_table(self, profile_id: str) -> bool:
        """Insert the distance/altitude table into the print layout (Issue #58).

        Returns True on success.
        """
        config = self._profile_manager.get_profile(profile_id)
        if not config:
            self._emit_msg("Error", "Profile not found.", MsgLevel.Critical)
            return False

        if not self._layout_manager:
            log("Layout manager not available", "WARNING")
            return False

        try:
            self._layout_manager.populate_distance_altitude_table(config)
            self._emit_msg(
                "Distance/Altitude Table",
                "Table added to the print layout.",
                MsgLevel.Success,
            )
            log(f"Generated distance/altitude table for profile {profile_id}")
            return True
        except (ValueError, AttributeError) as e:
            log(f"generate_distance_altitude_table failed: {e}", "ERROR")
            self._emit_msg("Table Error", str(e), MsgLevel.Critical)
            return False
