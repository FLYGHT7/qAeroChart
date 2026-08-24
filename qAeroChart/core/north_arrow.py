# -*- coding: utf-8 -*-
"""
North arrow geometry calculator (Issue #108).

Pure Python — no QGIS imports. Computes the tip coordinates of a simple
two-line north arrow (true north + magnetic north) drawn at an origin point,
given lengths in meters and a signed magnetic declination in degrees.

Sign convention matches ``core/msa.py``: declination is already signed
(positive = East, negative = West) — callers own the E/W → sign conversion.

Coordinates are in map CRS units (meters for projected CRS).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class NorthArrowGeometry:
    """Tip coordinates of one north arrow figure, relative to map CRS."""

    origin_x: float
    origin_y: float
    true_tip_x: float
    true_tip_y: float
    mag_tip_x: float
    mag_tip_y: float


def compute_arrow_geometry(
    origin_x: float,
    origin_y: float,
    true_length_m: float,
    mag_length_m: float,
    declination_signed: float,
) -> NorthArrowGeometry:
    """Compute true-north and magnetic-north tip coordinates.

    The true-north line points straight up (+Y). The magnetic-north line is
    rotated clockwise by the declination (positive = East = toward +X),
    matching the contributor's reference script.
    """
    rad = math.radians(declination_signed)
    return NorthArrowGeometry(
        origin_x=origin_x,
        origin_y=origin_y,
        true_tip_x=origin_x,
        true_tip_y=origin_y + true_length_m,
        mag_tip_x=origin_x + mag_length_m * math.sin(rad),
        mag_tip_y=origin_y + mag_length_m * math.cos(rad),
    )


def format_var_label(declination_signed: float) -> str:
    """Format an ICAO-style variation label, e.g. ``VAR 5.5°E`` / ``VAR 3°W``."""
    suffix = "E" if declination_signed >= 0 else "W"
    return f"VAR {abs(declination_signed):g}\N{DEGREE SIGN}{suffix}"
