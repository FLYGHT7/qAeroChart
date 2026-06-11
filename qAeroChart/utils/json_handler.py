# -*- coding: utf-8 -*-
"""
JSONHandler - Handles saving and loading profile configurations

This module provides functionality to save and load profile chart configurations
to/from JSON files, allowing users to reuse profile setups.
"""

import json
import os
from datetime import datetime

from .logger import log


class JSONHandler:
    """
    Handles JSON serialization and deserialization of profile configurations.

    Configuration structure:
    {
        "metadata": {
            "version": "1.0",
            "created": "2025-10-22T10:30:00",
            "modified": "2025-10-22T10:30:00",
            "plugin_version": "0.1.0"
        },
        "reference_point": {
            "x": 123.456789,
            "y": 45.678901
        },
        "runway": {
            "direction": "09/27",
            "length": "3000",
            "thr_elevation": "500",
            "tch_rdh": "50"
        },
        "profile_points": [
            {
                "point_name": "MAPt",
                "distance": "0.0",
                "elevation": "500",
                "x_coord": "123.456",
                "y_coord": "45.678",
                "moca": "1000",
                "notes": "Missed approach point"
            }
        ]
    }
    """

    # Current configuration format version
    CONFIG_VERSION = "2.0"
    PLUGIN_VERSION = "0.1.0"

    @staticmethod
    def save_config(config, filepath):
        """
        Save profile configuration to JSON file.

        Args:
            config (dict): Configuration dictionary from ProfileCreationDialog
            filepath (str): Path to save the JSON file

        Returns:
            bool: True if saved successfully, False otherwise

        Raises:
            IOError: If file cannot be written
            ValueError: If config is invalid
        """
        try:
            # Validate config structure (accept v1 or v2 shapes)
            if not JSONHandler._validate_config(config):
                raise ValueError("Invalid configuration structure")

            # Add metadata
            # Determine point key (origin_point preferred in v2.0)
            origin_point = config.get("origin_point") or config.get("reference_point") or {}
            # Compose metadata (preserve incoming version if provided)
            target_version = config.get("version", JSONHandler.CONFIG_VERSION)
            full_config = {
                "metadata": {
                    "version": target_version,
                    "created": config.get("metadata", {}).get(
                        "created", datetime.now().isoformat()),
                    "modified": datetime.now().isoformat(),
                    "plugin_version": JSONHandler.PLUGIN_VERSION
                },
                # Store both keys for backward compatibility
                "origin_point": origin_point,
                "reference_point": origin_point,
                "runway": config.get("runway", {}),
                "profile_points": config.get("profile_points", []),
                # Persist style and MOCA segments if present (v2.0+)
                "style": config.get("style", {}),
                "moca_segments": config.get("moca_segments", []),
                # Persist OCA parameters if present
                "oca": config.get("oca", None),
                "oca_segments": config.get("oca_segments", [])
            }

            # Write to file with pretty formatting
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)

            log(f"Configuration saved to {filepath}")
            return True

        except (OSError, TypeError, ValueError) as e:
            log(f"Failed to save config: {e}", "ERROR")
            raise

    @staticmethod
    def load_config(filepath):
        """
        Load profile configuration from JSON file.

        Args:
            filepath (str): Path to the JSON file

        Returns:
            dict: Configuration dictionary or None if failed

        Raises:
            IOError: If file cannot be read
            ValueError: If JSON is invalid
        """
        try:
            # Check if file exists
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Configuration file not found: {filepath}")

            # Read and parse JSON
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Validate structure
            if not JSONHandler._validate_loaded_config(config):
                raise ValueError("Invalid configuration file structure")

            # Check version compatibility
            config_version = config.get("metadata", {}).get("version", "unknown")
            if config_version != JSONHandler.CONFIG_VERSION:
                log(
                    f"Config version mismatch (file: {config_version}, "
                    f"expected: {JSONHandler.CONFIG_VERSION})",
                    "WARNING",
                )

            log(f"Configuration loaded from {filepath}")
            return config

        except (OSError, json.JSONDecodeError, ValueError) as e:
            log(f"Failed to load config: {e}", "ERROR")
            raise

    @staticmethod
    def _validate_config(config):
        """
        Validate configuration structure before saving.

        Args:
            config (dict): Configuration to validate

        Returns:
            bool: True if valid
        """
        # Check required keys (accept origin_point or reference_point)
        if "runway" not in config or "profile_points" not in config:
            log("Missing runway or profile_points in configuration", "ERROR")
            return False

        ref_point = config.get("origin_point") or config.get("reference_point")
        if not isinstance(ref_point, dict) or 'x' not in ref_point or 'y' not in ref_point:
            log("Invalid origin/reference point structure", "ERROR")
            return False

        # Validate runway
        runway = config.get("runway", {})
        runway_keys = ["direction", "length", "thr_elevation", "tch_rdh"]
        if not all(key in runway for key in runway_keys):
            log("Missing runway parameters", "ERROR")
            return False

        # Validate profile_points
        profile_points = config.get("profile_points", [])
        if not isinstance(profile_points, list):
            log("profile_points must be a list", "ERROR")
            return False

        return True

    @staticmethod
    def _validate_loaded_config(config):
        """
        Validate loaded configuration structure.

        Args:
            config (dict): Loaded configuration

        Returns:
            bool: True if valid
        """
        # Check metadata
        if "metadata" not in config:
            log("Config missing metadata", "WARNING")

        # Check required sections (accept origin_point or reference_point)
        if "runway" not in config or "profile_points" not in config:
            log("Config missing required sections", "ERROR")
            return False
        if ("origin_point" not in config) and ("reference_point" not in config):
            log("Config missing origin/reference point", "ERROR")
            return False

        return True

    @staticmethod
    def create_empty_config():
        """
        Create an empty configuration template.

        Returns:
            dict: Empty configuration structure
        """
        return {
            "metadata": {
                "version": JSONHandler.CONFIG_VERSION,
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "plugin_version": JSONHandler.PLUGIN_VERSION
            },
            "reference_point": {
                "x": 0.0,
                "y": 0.0
            },
            "runway": {
                "direction": "",
                "length": "",
                "thr_elevation": "",
                "tch_rdh": ""
            },
            "profile_points": []
        }

    @staticmethod
    def get_default_filename(runway_direction="profile"):
        """
        Generate a default filename for configuration.

        Args:
            runway_direction (str): Runway direction for naming

        Returns:
            str: Suggested filename
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_direction = runway_direction.replace("/", "-")
        return f"profile_{safe_direction}_{timestamp}.json"
