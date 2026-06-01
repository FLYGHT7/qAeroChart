# -*- coding: utf-8 -*-
"""
vertical_scale — Pure-geometry helpers for the vertical scale bar.

All arithmetic only; nothing from qgis.core here so this module is fully
testable without a QGIS environment.

The QGIS geometry (QgsPoint.project calls) lives in
LayerManager.populate_vertical_scale_layer(), which uses the offsets
computed here to build the actual map features.

Ported from scripts/Vertical_Scale.py (Issue #57).
"""
from __future__ import annotations

_FT_TO_M: float = 0.3048


def vertical_scale_tick_offsets(
    vertical_exaggeration: float = 10.0,
    metre_max: int = 100,
    metre_step: int = 25,
    feet_max: int = 300,
    feet_step: int = 50,
    tick_length_m: float = 15.0,
    scale_denominator: float | None = None,
) -> dict[str, list[tuple[float, float]] | tuple[float, float] | float]:
    """
    Compute tick-mark offsets for a double-sided vertical scale bar.

    The scale bar is drawn parallel to the profile line. One side shows
    metre-altitude graduations and the other shows feet-altitude graduations,
    with both scaled by the vertical exaggeration factor so they visually
    match the profile chart's altitude axis.

    All returned values are in map-CRS metres; the caller (LayerManager)
    projects them along/perpendicular to the actual profile azimuth using
    QgsPoint.project().

    Returns a dict with:
      ``metre_bases``       list[(along, 0.0)]          — base of each main metre tick
      ``metre_tips``        list[(along, +tick_length)]  — tip of each main metre tick
      ``feet_bases``        list[(along, 0.0)]           — base of each main foot tick
      ``feet_tips``         list[(along, -tick_length)]  — tip of each main foot tick
      ``connector``         (metre_end_along, feet_end_along) — horizontal end-cap
      ``metre_small_ticks`` list[(along, 0.0)]           — mid-step metre positions
      ``feet_small_ticks``  list[(along, 0.0)]           — mid-step feet positions
      ``half_spacing``      float  — rail offset (tick_length_m * 0.5)
      ``sec_offset``        float  — secondary rail offset (tick_length_m * 0.8)

    Parameters
    ----------
    vertical_exaggeration:
        Same VE used by ProfileChartGeometry (default 10.0).  Converts
        altitude metres/feet to map metres along the scale axis.
        Ignored when ``scale_denominator`` is provided.
    metre_max, metre_step:
        Defines metre graduation range: range(0, metre_max+1, metre_step).
    feet_max, feet_step:
        Defines feet graduation range: range(0, feet_max+1, feet_step).
    tick_length_m:
        Half-width of each tick in map metres (perpendicular to the scale axis).
    scale_denominator:
        When provided, overrides ``vertical_exaggeration`` using the formula
        ``VE = scale_denominator / 1000.0`` (e.g. 10 000 → VE 10).
    """
    _ve: float = (
        float(scale_denominator) / 1000.0
        if scale_denominator is not None
        else vertical_exaggeration
    )

    metre_steps = list(range(0, metre_max + 1, metre_step))
    feet_steps = list(range(0, feet_max + 1, feet_step))

    metre_bases: list[tuple[float, float]] = [
        (v * _ve, 0.0) for v in metre_steps
    ]
    metre_tips: list[tuple[float, float]] = [
        (v * _ve, tick_length_m) for v in metre_steps
    ]
    feet_bases: list[tuple[float, float]] = [
        (v * _FT_TO_M * _ve, 0.0) for v in feet_steps
    ]
    feet_tips: list[tuple[float, float]] = [
        (v * _FT_TO_M * _ve, -tick_length_m) for v in feet_steps
    ]

    connector: tuple[float, float] = (metre_bases[-1][0], feet_bases[-1][0])

    # --- dual-rail additions (Task 2b) ---
    half_spacing: float = tick_length_m * 0.5
    sec_offset: float = tick_length_m * 0.8

    metre_small_steps = list(range(metre_step // 2, metre_max, metre_step))
    feet_small_steps = list(range(feet_step // 2, feet_max, feet_step))

    metre_small_ticks: list[tuple[float, float]] = [
        (v * _ve, 0.0) for v in metre_small_steps
    ]
    feet_small_ticks: list[tuple[float, float]] = [
        (v * _FT_TO_M * _ve, 0.0) for v in feet_small_steps
    ]

    return {
        "metre_bases": metre_bases,
        "metre_tips": metre_tips,
        "feet_bases": feet_bases,
        "feet_tips": feet_tips,
        "connector": connector,
        "metre_small_ticks": metre_small_ticks,
        "feet_small_ticks": feet_small_ticks,
        "half_spacing": half_spacing,
        "sec_offset": sec_offset,
    }
    """
    Compute tick-mark offsets for a double-sided vertical scale bar.

    The scale bar is drawn parallel to the profile line. One side shows
    metre-altitude graduations and the other shows feet-altitude graduations,
    with both scaled by the vertical exaggeration factor so they visually
    match the profile chart's altitude axis.

    All returned values are in map-CRS metres; the caller (LayerManager)
    projects them along/perpendicular to the actual profile azimuth using
    QgsPoint.project().

    Returns a dict with:
      ``metre_bases``   list[(along, 0.0)]          — base of each metre tick
      ``metre_tips``    list[(along, +tick_length)]  — tip of each metre tick
      ``feet_bases``    list[(along, 0.0)]           — base of each foot tick
      ``feet_tips``     list[(along, -tick_length)]  — tip of each foot tick
      ``connector``     (metre_end_along, feet_end_along) — horizontal end-cap

    Parameters
    ----------
    vertical_exaggeration:
        Same VE used by ProfileChartGeometry (default 10.0).  Converts
        altitude metres/feet to map metres along the scale axis.
    metre_max, metre_step:
        Defines metre graduation range: range(0, metre_max+1, metre_step).
    feet_max, feet_step:
        Defines feet graduation range: range(0, feet_max+1, feet_step).
    tick_length_m:
        Half-width of each tick in map metres (perpendicular to the scale axis).
    """
    metre_steps = list(range(0, metre_max + 1, metre_step))
    feet_steps = list(range(0, feet_max + 1, feet_step))

    metre_bases: list[tuple[float, float]] = [
        (v * vertical_exaggeration, 0.0) for v in metre_steps
    ]
    metre_tips: list[tuple[float, float]] = [
        (v * vertical_exaggeration, tick_length_m) for v in metre_steps
    ]
    feet_bases: list[tuple[float, float]] = [
        (v * _FT_TO_M * vertical_exaggeration, 0.0) for v in feet_steps
    ]
    feet_tips: list[tuple[float, float]] = [
        (v * _FT_TO_M * vertical_exaggeration, -tick_length_m) for v in feet_steps
    ]

    connector: tuple[float, float] = (metre_bases[-1][0], feet_bases[-1][0])

    return {
        "metre_bases": metre_bases,
        "metre_tips": metre_tips,
        "feet_bases": feet_bases,
        "feet_tips": feet_tips,
        "connector": connector,
    }
