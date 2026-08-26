# -*- coding: utf-8 -*-
"""
Shared bearing/track conversion helpers.

Pure Python — no QGIS imports. Used by any feature that needs to convert a
user-entered magnetic bearing/track to true (or pass a true value through
unchanged), given a signed magnetic variation.
"""
from __future__ import annotations

__all__ = ["resolve_true_bearing"]


def resolve_true_bearing(
    input_brg: float, *, is_magnetic: bool, mag_var_signed: float, is_inbound: bool
) -> float:
    """Convert a user-entered bearing to a true bearing in degrees 0-360.

    ``is_inbound`` reverses the bearing 180° first (bearings TO the station are
    stored as the reciprocal outbound-FROM bearing before the sector is drawn).
    ``mag_var_signed`` is already signed (positive = East, negative = West) —
    callers own the E/W → sign conversion.
    """
    brg = (input_brg + 180.0) % 360.0 if is_inbound else input_brg
    if is_magnetic:
        brg = (brg + mag_var_signed) % 360.0
    return brg % 360.0
