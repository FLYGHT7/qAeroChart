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
    rod_first: bool = False  # Issue #120: swap the timing/ROD row order when True
    show_timing: bool = True  # Issue #117: omit the timing row entirely when False
    round_step: int = 0          # Issue #116: 0 = no rounding, else 5 or 10
    round_mode: str = "nearest"  # "nearest" | "up" — ignored when round_step == 0


def _format_seconds(total: float) -> str:
    """Format a duration in seconds as MM:SS."""
    total_int = round(total)
    minutes, secs = divmod(total_int, 60)
    return f"{minutes:02d}:{secs:02d}"


def compute_timing(distance_nm: float, gs_kt: int) -> str:
    """Return flight time as MM:SS string."""
    seconds = (distance_nm / gs_kt) * 3600.0
    return _format_seconds(seconds)


def compute_rod(
    gs_kt: int,
    gradient_pct: float,
    round_step: int = 0,
    round_mode: str = "nearest",
) -> int:
    """Return rate of descent in ft/min, truncated to nearest integer.

    round_step: 0 (default) disables rounding — preserves the exact
        truncated value. Pass 5 or 10 to round to that multiple.
    round_mode: "nearest" (ties round up) or "up" (ceiling to next
        multiple). Ignored when round_step <= 0.
    """
    # ROD (ft/min) = GS (kt) × gradient (%) × NM_to_ft / 100 / 60
    value = math.floor(gs_kt * gradient_pct * _NM_TO_FT / 100.0 / 60.0)
    if round_step <= 0:
        return value
    remainder = value % round_step
    if remainder == 0:
        return value
    if round_mode == "up":
        return value - remainder + round_step
    # "nearest" (default) — exact ties (remainder == round_step / 2) round up
    if remainder < round_step / 2:
        return value - remainder
    return value - remainder + round_step


def compute_table(cfg: GsRodConfig) -> list[list[str]]:
    """Build and return the 2-D table as a list of string rows.

    Row structure
    -------------
    - Row 0 (optional): title row — cfg.title in col 0, empty in remaining cols
    - Row 1 (always):   header row — ["Ground Speed", unit_gs, gs1, gs2, ...]
    - Row 2/3 (always): timing row and ROD row, in the order controlled by
      cfg.rod_first (timing first when False, the default; ROD first when True)
      — [label_timing, unit_timing, t1, t2, ...] / [label_rod, "ft/min", r1, r2, ...]
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

    # ── Timing row (optional; Issue #117) ─────────────────────────────────
    if cfg.show_timing:
        label_t = cfg.label_timing or f"FAF-MAPt {cfg.distance_nm:.1f}NM"
        timing_vals = [compute_timing(cfg.distance_nm, gs) for gs in cfg.gs_values]
        timing_row = [label_t, cfg.unit_timing] + timing_vals

    # ── ROD row ─────────────────────────────────────────────────────────
    label_r = cfg.label_rod or f"Rate of Descent {cfg.gradient_pct:.1f}%"
    rod_vals = [
        str(compute_rod(gs, cfg.gradient_pct, cfg.round_step, cfg.round_mode))
        for gs in cfg.gs_values
    ]
    rod_row = [label_r, "ft/min"] + rod_vals

    if cfg.show_timing:
        rows.extend([rod_row, timing_row] if cfg.rod_first else [timing_row, rod_row])
    else:
        rows.append(rod_row)

    # ── Optional footer row ─────────────────────────────────────────────
    if cfg.footer:
        row = _empty_row()
        row[0] = cfg.footer
        rows.append(row)

    return rows
