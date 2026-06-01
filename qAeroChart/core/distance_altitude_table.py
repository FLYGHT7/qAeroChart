# -*- coding: utf-8 -*-
"""
Pure-Python helpers for the distance/altitude table (Issue #58).

Ported from scripts/table_distance_altitude.py.
Zero QGIS imports — fully unit-testable without a running QGIS instance.
The QGIS layout integration lives in LayoutManager.
"""
from __future__ import annotations

__all__ = [
    "build_table_rows",
    "compute_column_widths",
    "extract_table_data",
]


def build_table_rows(
    thr: str,
    numeric_columns: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Return (headers, values) for the distance/altitude table.

    Parameters
    ----------
    thr:
        Runway number string, e.g. ``"07"`` or ``"27"``.
    numeric_columns:
        Ordered mapping of ``distance_nm`` → ``elevation`` value strings,
        exactly as they should appear in the table cells.

    Returns
    -------
    tuple[list[str], list[str]]
        ``(headers, values)`` — both lists have the same length.
        ``headers[0]`` == ``"NM TO RWY{thr}"``, ``values[0]`` == ``"ALTITUDE"``.
    """
    headers: list[str] = [f"NM TO RWY{thr}"] + list(numeric_columns.keys())
    values: list[str] = ["ALTITUDE"] + list(numeric_columns.values())
    return headers, values


def compute_column_widths(
    num_columns: int,
    total_width: float = 180.20,
    first_col_width: float = 36.20,
    stroke_width: float = 0.25,
    cell_margin: float = 1.0,
) -> list[float]:
    """Compute per-column widths in mm, faithful to the original script logic.

    Parameters
    ----------
    num_columns:
        Total number of columns (including the first fixed column).
    total_width:
        Overall table width in mm (default 180.20).
    first_col_width:
        Width of the first (fixed label) column in mm (default 36.20).
    stroke_width:
        Grid line stroke width in mm (default 0.25).
    cell_margin:
        Per-cell horizontal margin in mm (default 1.0).

    Returns
    -------
    list[float]
        ``[first_col_width, dynamic_w, dynamic_w, ...]``
        When ``num_columns == 1`` returns ``[total_width]``.
    """
    if num_columns <= 1:
        return [total_width]

    num_dynamic = num_columns - 1
    # Extra space consumed by inter-column lines and cell margins
    extra = (num_columns - 1) * stroke_width + 2 * cell_margin * num_columns
    remaining = total_width - first_col_width - extra
    dynamic_w = remaining / num_dynamic
    return [first_col_width] + [dynamic_w] * num_dynamic


def extract_table_data(config: dict) -> tuple[str, dict[str, str]]:
    """Derive ``(thr, numeric_columns)`` from a profile config dict.

    Parameters
    ----------
    config:
        Profile configuration as stored by ``ProfileManager``.
        Expected keys: ``"runway"`` → ``{"direction": str, ...}``
        and ``"profile_points"`` → list of
        ``{"distance_nm": str, "elevation_ft": str, ...}``.

    Returns
    -------
    tuple[str, dict[str, str]]
        ``thr`` is the two-digit runway number (e.g. ``"07"``).
        ``numeric_columns`` maps ``distance_nm`` strings to elevation strings
        (``elevation_ft`` preferred; ``elevation`` used as fallback).
        Points missing either value are silently skipped.
    """
    runway = config.get("runway", {})
    direction = runway.get("direction", "00")
    thr = "".join(ch for ch in direction if ch.isdigit())[:2] or "00"

    numeric_columns: dict[str, str] = {}
    for pt in config.get("profile_points", []):
        dist = str(pt.get("distance_nm", "")).strip()
        elev = str(pt.get("elevation_ft", pt.get("elevation", ""))).strip()
        if dist and elev:
            numeric_columns[dist] = elev

    return thr, numeric_columns
