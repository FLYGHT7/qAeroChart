# -*- coding: utf-8 -*-
"""
horizontal_scale — Pure-geometry helpers for the horizontal scale bar.

All arithmetic only; no qgis.core imports so this module is fully testable
without a QGIS environment.

The QGIS geometry (QgsPoint.project calls) lives in
LayerManager.create_horizontal_scale_run(), which uses the offsets
computed here to build the actual map features.

The scale bar matches the standard aeronautical chart layout (see Issue #69):
  - Upper rail: metres (positive right, negative left)
  - Lower rail: feet  (positive right, negative left)
  - Major ticks at each step; minor (half-step) ticks inward
  - Labels above metre rail and below feet rail
"""
from __future__ import annotations

_FT_TO_M: float = 0.3048


def horizontal_scale_tick_offsets(
    metre_right: int = 2500,
    metre_left: int = 400,
    metre_right_step: int = 500,
    metre_left_step: int = 100,
    ft_right: int = 8000,
    ft_left: int = 1000,
    ft_right_step: int = 1000,
    ft_left_step: int = 100,
    tick_length_m: float = 15.0,
) -> dict[str, object]:
    """Compute tick-mark offsets for a double-sided horizontal scale bar.

    The scale bar is drawn along a chosen azimuth on the map.  The origin
    (``along=0``) corresponds to the aeronautical reference point (e.g., runway
    threshold).  Positive ``along`` values extend in the forward direction
    (right in the image); negative values extend backward (left).

    All returned values are in **real map-CRS metres**; the caller
    (LayerManager) projects them using ``QgsPoint.project(abs(along), angle)``
    for positive and ``QgsPoint.project(abs(along), angle + 180)`` for negative.

    Returns a dict with:
      ``m_pos_ticks``        list[float]  — along-axis positions (≥ 0) for metre ticks
      ``m_neg_ticks``        list[float]  — abs values (> 0) for negative metre ticks
      ``m_pos_minor``        list[float]  — along-axis positions for minor metre ticks (right)
      ``m_neg_minor``        list[float]  — abs values for minor metre ticks (left)
      ``ft_pos_ticks``       list[float]  — along-axis positions for foot ticks (≥ 0)
      ``ft_neg_ticks``       list[float]  — abs values for negative foot ticks
      ``ft_pos_minor``       list[float]  — along-axis positions for minor foot ticks (right)
      ``ft_neg_minor``       list[float]  — abs values for minor foot ticks (left)
      ``half_spacing``       float        — half of tick_length_m (rail offset)
      ``tick_length_m``      float        — full tick length
      ``metre_right``        int          — maximum positive metre value
      ``metre_left``         int          — maximum negative metre value (magnitude)
      ``ft_right``           int          — maximum positive feet value
      ``ft_left``            int          — maximum negative feet value (magnitude)

    Parameters
    ----------
    metre_right, metre_left:
        Positive and negative extents of the metre scale (real metres).
    metre_right_step, metre_left_step:
        Major tick spacing on positive and negative sides.
    ft_right, ft_left:
        Positive and negative extents of the feet scale.
    ft_right_step, ft_left_step:
        Major tick spacing on positive and negative sides.
    tick_length_m:
        Full tick length in map metres (perpendicular to scale axis).
    """
    half_sp: float = tick_length_m * 0.5

    # ---- metre ticks ----
    m_pos_ticks: list[float] = list(
        float(v) for v in range(0, metre_right + 1, metre_right_step)
    )
    m_neg_ticks: list[float] = list(
        float(v) for v in range(metre_left_step, metre_left + 1, metre_left_step)
    )
    m_pos_minor: list[float] = list(
        float(v) for v in range(
            metre_right_step // 2,
            metre_right,
            metre_right_step,
        )
    )
    m_neg_minor: list[float] = list(
        float(v) for v in range(
            metre_left_step // 2,
            metre_left,
            metre_left_step,
        )
    )

    # ---- feet ticks (converted to metres for map projection) ----
    ft_pos_ticks: list[float] = list(
        float(v) * _FT_TO_M for v in range(0, ft_right + 1, ft_right_step)
    )
    ft_neg_ticks: list[float] = list(
        float(v) * _FT_TO_M for v in range(ft_left_step, ft_left + 1, ft_left_step)
    )
    ft_pos_minor: list[float] = list(
        float(v) * _FT_TO_M for v in range(
            ft_right_step // 2,
            ft_right,
            ft_right_step,
        )
    )
    ft_neg_minor: list[float] = list(
        float(v) * _FT_TO_M for v in range(
            ft_left_step // 2,
            ft_left,
            ft_left_step,
        )
    )

    return {
        "m_pos_ticks": m_pos_ticks,
        "m_neg_ticks": m_neg_ticks,
        "m_pos_minor": m_pos_minor,
        "m_neg_minor": m_neg_minor,
        "ft_pos_ticks": ft_pos_ticks,
        "ft_neg_ticks": ft_neg_ticks,
        "ft_pos_minor": ft_pos_minor,
        "ft_neg_minor": ft_neg_minor,
        "half_spacing": half_sp,
        "tick_length_m": tick_length_m,
        "metre_right": metre_right,
        "metre_left": metre_left,
        "ft_right": ft_right,
        "ft_left": ft_left,
    }
