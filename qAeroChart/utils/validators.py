# -*- coding: utf-8 -*-
"""
Validators - Data validation utilities for aeronautical profile charts

This module provides validation functions for user input, ensuring data
complies with ICAO standards and format requirements.
"""

from __future__ import annotations

import re


class Validators:
    """
    Collection of validation functions for profile chart data.
    """

    @staticmethod
    def validate_coordinate(value: str | float, coord_type: str = "x") -> tuple[bool, str, float | None]:
        """
        Validate that a coordinate value is a valid number.

        The plugin operates on projected CRS (meters), so no geographic
        range check is applied here. Callers dealing with WGS-84 inputs
        must add their own range validation.

        Args:
            value (str or float): Coordinate value
            coord_type (str): Type of coordinate ('x' or 'y'), used in error message only

        Returns:
            tuple: (is_valid, error_message, parsed_value)
        """
        try:
            parsed = float(value)
            return (True, "", parsed)
        except (ValueError, TypeError):
            return (False, f"Invalid {coord_type} coordinate format", None)

    @staticmethod
    def validate_distance(value: str | float) -> tuple[bool, str, float | None]:
        """
        Validate distance value (Nautical Miles).

        Args:
            value (str or float): Distance value

        Returns:
            tuple: (is_valid, error_message, parsed_value)
        """
        try:
            parsed = float(value)

            if parsed < 0:
                return (False, "Distance cannot be negative", None)

            # Reasonable range check (0-999 NM for approach profiles)
            if parsed > 999:
                return (False, "Distance exceeds reasonable range (max 999 NM)", None)

            return (True, "", parsed)

        except (ValueError, TypeError):
            return (False, "Invalid distance format", None)

    @staticmethod
    def validate_elevation(value: str | float) -> tuple[bool, str, float | None]:
        """
        Validate elevation value (feet).

        Args:
            value (str or float): Elevation value

        Returns:
            tuple: (is_valid, error_message, parsed_value)
        """
        try:
            parsed = float(value)

            # Reasonable range check (-1500 to 60000 ft)
            # -1500 for Dead Sea level, 60000 for high mountain approaches
            if parsed < -1500 or parsed > 60000:
                return (False, "Elevation must be between -1500 and 60000 ft", None)

            return (True, "", parsed)

        except (ValueError, TypeError):
            return (False, "Invalid elevation format", None)

    @staticmethod
    def validate_runway_direction(value: str) -> tuple[bool, str]:
        """
        Validate runway direction format (e.g., "09/27", "18/36").

        Args:
            value (str): Runway direction

        Returns:
            tuple: (is_valid, error_message)
        """
        if not value or not isinstance(value, str):
            return (False, "Runway direction is required")

        # Pattern: NN/NN where NN is 01-36
        pattern = r'^(0[1-9]|[12][0-9]|3[0-6])/(0[1-9]|[12][0-9]|3[0-6])$'

        if not re.match(pattern, value):
            return (False, "Invalid runway direction format (use NN/NN, e.g., 09/27)")

        # Check if directions are reciprocal (differ by 18)
        parts = value.split('/')
        dir1 = int(parts[0])
        dir2 = int(parts[1])

        reciprocal = (dir1 + 18) % 36
        if reciprocal == 0:
            reciprocal = 36

        if dir2 != reciprocal:
            return (False, "Runway directions must be reciprocal (differ by 18)")

        return (True, "")

    @staticmethod
    def validate_runway_length(value: str | float) -> tuple[bool, str, float | None]:
        """
        Validate runway length (meters).

        Args:
            value (str or float): Runway length

        Returns:
            tuple: (is_valid, error_message, parsed_value)
        """
        try:
            parsed = float(value)

            # Reasonable range: 100m to 6000m
            if parsed < 100 or parsed > 6000:
                return (False, "Runway length must be between 100 and 6000 meters", None)

            return (True, "", parsed)

        except (ValueError, TypeError):
            return (False, "Invalid runway length format", None)

    @staticmethod
    def validate_point_name(value: str) -> tuple[bool, str]:
        """
        Validate point name (alphanumeric, max 50 chars).

        Args:
            value (str): Point name

        Returns:
            tuple: (is_valid, error_message)
        """
        if not value or not isinstance(value, str):
            return (False, "Point name is required")

        value = value.strip()

        if len(value) == 0:
            return (False, "Point name cannot be empty")

        if len(value) > 50:
            return (False, "Point name too long (max 50 characters)")

        # Allow alphanumeric, spaces, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9\s\-_]+$', value):
            return (False, "Point name contains invalid characters")

        return (True, "")

    @staticmethod
    def validate_moca(value):
        """
        Validate MOCA (Minimum Obstacle Clearance Altitude) value (feet).

        Args:
            value (str or float): MOCA value

        Returns:
            tuple: (is_valid, error_message, parsed_value)
        """
        if not value or str(value).strip() == "":
            # MOCA is optional
            return (True, "", None)

        try:
            parsed = float(value)

            # MOCA range: 0 to 60000 ft
            if parsed < 0 or parsed > 60000:
                return (False, "MOCA must be between 0 and 60000 ft", None)

            return (True, "", parsed)

        except (ValueError, TypeError):
            return (False, "Invalid MOCA format", None)

    @staticmethod
    def validate_all_runway_params(direction, length, thr_elevation, tch_rdh):
        """
        Validate all runway parameters at once.

        Args:
            direction (str): Runway direction
            length (str): Runway length
            thr_elevation (str): Threshold elevation
            tch_rdh (str): TCH/RDH value

        Returns:
            tuple: (is_valid, error_messages_dict)
        """
        errors = {}

        # Validate direction
        is_valid, msg = Validators.validate_runway_direction(direction)
        if not is_valid:
            errors['direction'] = msg

        # Validate length
        is_valid, msg, _ = Validators.validate_runway_length(length)
        if not is_valid:
            errors['length'] = msg

        # Validate threshold elevation
        is_valid, msg, _ = Validators.validate_elevation(thr_elevation)
        if not is_valid:
            errors['thr_elevation'] = msg

        # Validate TCH/RDH
        is_valid, msg, _ = Validators.validate_elevation(tch_rdh)
        if not is_valid:
            errors['tch_rdh'] = msg

        return (len(errors) == 0, errors)

    @staticmethod
    def validate_profile_point(point_data):
        """
        Validate all fields of a profile point.

        Args:
            point_data (dict): Profile point data

        Returns:
            tuple: (is_valid, error_messages_dict)
        """
        errors = {}

        # Validate point name
        point_name = point_data.get('point_name', '')
        is_valid, msg = Validators.validate_point_name(point_name)
        if not is_valid:
            errors['point_name'] = msg

        # Validate distance (optional)
        distance = point_data.get('distance', '')
        if distance and str(distance).strip():
            is_valid, msg, _ = Validators.validate_distance(distance)
            if not is_valid:
                errors['distance'] = msg

        # Validate elevation (optional)
        elevation = point_data.get('elevation', '')
        if elevation and str(elevation).strip():
            is_valid, msg, _ = Validators.validate_elevation(elevation)
            if not is_valid:
                errors['elevation'] = msg

        # Validate coordinates (optional but if one is present, both must be)
        x_coord = point_data.get('x_coord', '')
        y_coord = point_data.get('y_coord', '')

        if x_coord or y_coord:
            if not x_coord or not y_coord:
                errors['coordinates'] = "Both X and Y coordinates are required"
            else:
                is_valid, msg, _ = Validators.validate_coordinate(x_coord, 'x')
                if not is_valid:
                    errors['x_coord'] = msg

                is_valid, msg, _ = Validators.validate_coordinate(y_coord, 'y')
                if not is_valid:
                    errors['y_coord'] = msg

        # Validate MOCA (optional)
        moca = point_data.get('moca', '')
        if moca and str(moca).strip():
            is_valid, msg, _ = Validators.validate_moca(moca)
            if not is_valid:
                errors['moca'] = msg

        return (len(errors) == 0, errors)
