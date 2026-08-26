"""CDFA Distance/Altitude stepdown table computation engine (Issue #99).

Ported from pansops-calculator's html/js/dist_alt_calculator.js (issue #136).
No Qt or QGIS dependencies — fully unit-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "DistAltConfig",
    "DistAltStep",
    "FT_PER_NM",
    "compute_summary",
    "compute_steps",
    "compute_table",
    "round_altitude",
    "steps_to_numeric_columns",
]

# 1852 m/NM / 0.3048 m/ft
FT_PER_NM: float = 1852.0 / 0.3048


@dataclass(frozen=True)
class DistAltConfig:
    """All user-facing parameters for a CDFA distance/altitude table."""

    faf_altitude_ft: float
    thr_elevation_ft: float
    faf_thr_distance_nm: float
    tch_rdh_ft: float
    oca_ft: float
    offset_enabled: bool = False
    offset_distance_nm: float = 0.0
    round_step: int = 0
    round_mode: str = "nearest"


@dataclass(frozen=True)
class DistAltStep:
    """A single computed row of the stepdown table."""

    distance_label: str
    calculated_altitude_ft: float
    publication_altitude_ft: int
    calculated_height_ft: int
    advisory_altitude: str


def _validate(cfg: DistAltConfig) -> None:
    if cfg.faf_thr_distance_nm <= 0:
        raise ValueError("FAF-THR distance must be greater than 0")
    if cfg.offset_enabled and cfg.offset_distance_nm < 0:
        raise ValueError("Offset MAPt distance cannot be negative")


def _format_distance_label(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def round_altitude(value: float, round_step: int = 0, round_mode: str = "nearest") -> float:
    """Round an altitude value to the nearest multiple of ``round_step``.

    ``round_step`` of 0 (default) disables rounding — returns ``value``
    unchanged. ``round_mode`` is "nearest" (exact ties round up) or "up"
    (ceiling to the next multiple); ignored when ``round_step <= 0``.
    """
    if round_step <= 0:
        return value
    quotient = value / round_step
    if round_mode == "up":
        rounded_quotient = math.ceil(quotient)
    else:  # "nearest" — exact ties round up
        rounded_quotient = math.floor(quotient + 0.5)
    return float(rounded_quotient * round_step)


def compute_summary(cfg: DistAltConfig) -> dict:
    """Return gradient, gradient_pct, vpa_deg and height_loss_per_mile_ft."""
    _validate(cfg)
    net_loss = cfg.faf_altitude_ft - cfg.thr_elevation_ft - cfg.tch_rdh_ft
    gradient = net_loss / (cfg.faf_thr_distance_nm * FT_PER_NM)
    vpa_deg = math.atan(gradient) * 180.0 / math.pi
    height_loss_per_mile_ft = round(net_loss / cfg.faf_thr_distance_nm)
    return {
        "gradient": gradient,
        "gradient_pct": gradient * 100.0,
        "vpa_deg": vpa_deg,
        "height_loss_per_mile_ft": height_loss_per_mile_ft,
    }


def compute_steps(cfg: DistAltConfig) -> list[DistAltStep]:
    """Return one DistAltStep per integer NM from FAF-THR distance down to 0.

    Rows whose offset-adjusted display distance is <= 0 are dropped entirely
    (not just hidden) when ``cfg.offset_enabled`` is True.
    """
    _validate(cfg)
    summary = compute_summary(cfg)
    gradient = summary["gradient"]

    steps: list[DistAltStep] = []
    start = math.floor(cfg.faf_thr_distance_nm)
    for d in range(start, -1, -1):
        display_distance = d - cfg.offset_distance_nm if cfg.offset_enabled else float(d)
        if cfg.offset_enabled and display_distance <= 0:
            continue

        calculated_altitude_ft = cfg.faf_altitude_ft - gradient * (cfg.faf_thr_distance_nm - d) * FT_PER_NM
        calculated_altitude_ft = round_altitude(calculated_altitude_ft, cfg.round_step, cfg.round_mode)
        publication_altitude_ft = int(math.ceil(calculated_altitude_ft / 10.0) * 10)
        calculated_height_ft = round(publication_altitude_ft - cfg.thr_elevation_ft)

        label = _format_distance_label(display_distance)
        if publication_altitude_ft > cfg.oca_ft:
            advisory = f"{label} NM - {publication_altitude_ft} ({calculated_height_ft})"
        else:
            advisory = "below OCA"

        steps.append(
            DistAltStep(
                distance_label=label,
                calculated_altitude_ft=calculated_altitude_ft,
                publication_altitude_ft=publication_altitude_ft,
                calculated_height_ft=calculated_height_ft,
                advisory_altitude=advisory,
            )
        )
    return steps


def steps_to_numeric_columns(steps: list[DistAltStep]) -> dict[str, str]:
    """Map distance label -> publication altitude string, ordered as given.

    Feeds directly into ``core.distance_altitude_table.build_table_rows``.
    """
    return {step.distance_label: str(step.publication_altitude_ft) for step in steps}


def compute_table(cfg: DistAltConfig, title: str = "") -> list[list[str]]:
    """Build the 5-column CDFA table as a list of string rows.

    Row structure
    -------------
    - Row 0 (optional): title row — ``title`` in col 0, empty in remaining cols
    - Row 1 (always):   header row
    - Row N (always):   one data row per computed step
    """
    header = [
        "Distance from MAPt (NM)",
        "Calculated Altitude (ft)",
        "Publication Altitude (ft)",
        "Calculated Height (ft)",
        "Advisory Altitude",
    ]
    rows: list[list[str]] = []
    if title:
        rows.append([title, "", "", "", ""])
    rows.append(header)
    for step in compute_steps(cfg):
        rows.append(
            [
                step.distance_label,
                f"{step.calculated_altitude_ft:.2f}",
                str(step.publication_altitude_ft),
                str(step.calculated_height_ft),
                step.advisory_altitude,
            ]
        )
    return rows
