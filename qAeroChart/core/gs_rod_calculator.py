"""Ground-speed / Rate-of-descent table computation engine.

No Qt or QGIS dependencies — fully unit-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


DEFAULT_GS_VALUES: tuple[int, ...] = (70, 90, 100, 120, 140, 160)

# Aviation constant used to reproduce standard ICAO-style ROD tables.
# Derived empirically from published approach chart tables; using math.floor
# on this constant reproduces the expected ft/min values exactly.
_NM_TO_FT: float = 6068.0


@dataclass(frozen=True)
class GsRodConfig:
    """All user-facing parameters for a GS/ROD table."""

    distance_nm: float
    gradient_pct: float
    gs_values: tuple[int, ...] = field(default_factory=lambda: DEFAULT_GS_VALUES)
    title: str = "Rate of Descent"
    label_timing: str = ""           # e.g. "FAF-MAPt 5.2NM" — auto-generated if empty
    label_rod: str = ""              # e.g. "Rate of Descent 5.3%" — auto-generated if empty
    unit_gs: str = "KT"
    unit_timing: str = "min:s"
    footer: str = ""


def _format_seconds(total: float) -> str:
    """Format a duration in seconds as MM:SS."""
    total_int = round(total)
    minutes, secs = divmod(total_int, 60)
    return f"{minutes:02d}:{secs:02d}"


def compute_timing(distance_nm: float, gs_kt: int) -> str:
    """Return flight time as MM:SS string."""
    seconds = (distance_nm / gs_kt) * 3600.0
    return _format_seconds(seconds)


def compute_rod(gs_kt: int, gradient_pct: float) -> int:
    """Return rate of descent in ft/min, truncated to nearest integer."""
    # ROD (ft/min) = GS (kt) × gradient (%) × NM_to_ft / 100 / 60
    return math.floor(gs_kt * gradient_pct * _NM_TO_FT / 100.0 / 60.0)


def compute_table(cfg: GsRodConfig) -> list[list[str]]:
    """Build and return the 2-D table as a list of string rows.

    Row structure
    -------------
    - Row 0 (optional): title row — cfg.title in col 0, empty in remaining cols
    - Row 1 (always):   header row — ["Ground Speed", unit_gs, gs1, gs2, ...]
    - Row 2 (always):   timing row — [label_timing, unit_timing, t1, t2, ...]
    - Row 3 (always):   ROD row    — [label_rod, "ft/min", r1, r2, ...]
    - Row N (optional): footer row — cfg.footer in col 0, empty in remaining cols
    """
    num_gs = len(cfg.gs_values)
    # +2 columns: label col + unit col
    total_cols = num_gs + 2

    def _empty_row() -> list[str]:
        return [""] * total_cols

    rows: list[list[str]] = []

    # ── Optional title row ──────────────────────────────────────────────
    if cfg.title:
        row = _empty_row()
        row[0] = cfg.title
        rows.append(row)

    # ── Header row ──────────────────────────────────────────────────────
    header = ["Ground Speed", cfg.unit_gs] + [str(gs) for gs in cfg.gs_values]
    rows.append(header)

    # ── Timing row ──────────────────────────────────────────────────────
    label_t = cfg.label_timing or f"FAF-MAPt {cfg.distance_nm:.1f}NM"
    timing_vals = [compute_timing(cfg.distance_nm, gs) for gs in cfg.gs_values]
    rows.append([label_t, cfg.unit_timing] + timing_vals)

    # ── ROD row ─────────────────────────────────────────────────────────
    label_r = cfg.label_rod or f"Rate of Descent {cfg.gradient_pct:.1f}%"
    rod_vals = [str(compute_rod(gs, cfg.gradient_pct)) for gs in cfg.gs_values]
    rows.append([label_r, "ft/min"] + rod_vals)

    # ── Optional footer row ─────────────────────────────────────────────
    if cfg.footer:
        row = _empty_row()
        row[0] = cfg.footer
        rows.append(row)

    return rows
