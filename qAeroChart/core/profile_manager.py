# -*- coding: utf-8 -*-
"""
Profile Manager - Manages stored profile configurations in QGIS project
"""
from __future__ import annotations

from qgis.core import QgsProject
import json
import time
import uuid

from ..utils.logger import log


class ProfileManager:
    """
    Manages profile configurations stored in the QGIS project.

    Profiles are stored as custom project variables with the prefix 'qaerochart_profile_'
    Each profile contains:
    - name: Display name (e.g., "MROC 09")
    - config: Full configuration dict (origin_point, runway, profile_points)
    - created: Timestamp
    - layers_visible: Whether layers are currently visible
    """

    PROFILE_PREFIX = "qaerochart_profile_"
    PROFILE_LIST_KEY = "qaerochart_profiles"

    def __init__(self):
        """Initialize profile manager."""
        self.project = QgsProject.instance()

    def get_all_profiles(self) -> list[dict]:
        """
        Get list of all saved profiles.

        Returns:
            list: List of profile metadata dicts [{'id': '...', 'name': '...', 'point_count': ...}, ...]
        """
        profile_list_json = self.project.readEntry("qAeroChart", self.PROFILE_LIST_KEY, "[]")[0]
        try:
            return json.loads(profile_list_json)
        except (json.JSONDecodeError, ValueError):
            return []

    def save_profile(self, profile_name: str, config: dict) -> str:
        """
        Save a profile configuration to the project.

        Args:
            profile_name (str): Display name for the profile
            config (dict): Profile configuration

        Returns:
            str: Profile ID
        """
        # Generate unique profile ID (uuid4 guarantees no collisions)
        profile_id = f"profile_{uuid.uuid4().hex}"

        # Save full config
        config_json = json.dumps(config)
        self.project.writeEntry("qAeroChart", f"{self.PROFILE_PREFIX}{profile_id}", config_json)

        # Get current profile list
        profiles = self.get_all_profiles()

        # Add new profile metadata
        profile_points = config.get('profile_points', [])
        runway = config.get('runway', {})

        profiles.append({
            'id': profile_id,
            'name': profile_name,
            'runway_direction': runway.get('direction', 'N/A'),
            'point_count': len(profile_points),
            'created': time.time()
        })

        # Save updated list
        self.project.writeEntry("qAeroChart", self.PROFILE_LIST_KEY, json.dumps(profiles))

        log(f"Saved profile '{profile_name}' with ID {profile_id}")

        return profile_id

    def get_profile(self, profile_id: str) -> dict | None:
        """
        Get a profile configuration by ID.

        Args:
            profile_id (str): Profile ID

        Returns:
            dict: Profile configuration or None
        """
        config_json = self.project.readEntry("qAeroChart", f"{self.PROFILE_PREFIX}{profile_id}", "")[0]

        if not config_json:
            return None

        try:
            return json.loads(config_json)
        except (json.JSONDecodeError, ValueError):
            return None

    def update_profile(self, profile_id: str, profile_name: str, config: dict) -> bool:
        """
        Update an existing profile.

        Args:
            profile_id (str): Profile ID
            profile_name (str): New display name
            config (dict): Updated configuration

        Returns:
            bool: True if successful
        """
        # Update config
        config_json = json.dumps(config)
        self.project.writeEntry("qAeroChart", f"{self.PROFILE_PREFIX}{profile_id}", config_json)

        # Update metadata in list
        profiles = self.get_all_profiles()
        profile_points = config.get('profile_points', [])
        runway = config.get('runway', {})

        found = False
        for profile in profiles:
            if profile['id'] == profile_id:
                profile['name'] = profile_name
                profile['runway_direction'] = runway.get('direction', 'N/A')
                profile['point_count'] = len(profile_points)
                found = True
                break

        if not found:
            raise KeyError(f"Profile '{profile_id}' not found in stored list")

        self.project.writeEntry("qAeroChart", self.PROFILE_LIST_KEY, json.dumps(profiles))

        log(f"Updated profile '{profile_name}'")

        return True

    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a profile from the project.

        Args:
            profile_id (str): Profile ID

        Returns:
            bool: True if successful
        """
        # Remove config
        self.project.removeEntry("qAeroChart", f"{self.PROFILE_PREFIX}{profile_id}")

        # Remove from list
        profiles = self.get_all_profiles()
        profiles = [p for p in profiles if p['id'] != profile_id]
        self.project.writeEntry("qAeroChart", self.PROFILE_LIST_KEY, json.dumps(profiles))

        log(f"Deleted profile {profile_id}")

        return True

    def get_profile_display_name(self, profile_metadata: dict) -> str:
        """
        Generate a display name for the profile list.

        Args:
            profile_metadata (dict): Profile metadata

        Returns:
            str: Formatted display name
        """
        name = profile_metadata.get('name', 'Unnamed')
        runway = profile_metadata.get('runway_direction', 'N/A')
        points = profile_metadata.get('point_count', 0)

        return f"✈️ {name} ({runway}) - {points} points"
