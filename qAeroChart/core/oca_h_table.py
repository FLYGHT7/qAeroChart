"""OCA/H table data model and table builder (Issue #74).

No Qt or QGIS dependencies — fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_CATEGORY_HEADERS: tuple[str, ...] = ("A", "B", "C", "D")


@dataclass(frozen=True)
class OcaHRow:
    """One procedure row in the OCA/H table."""

    procedure: str
    values: tuple[str, ...]  # one value per category column


@dataclass(frozen=True)
class OcaHConfig:
    """All user-facing parameters for an OCA/H table."""

    rows: tuple[OcaHRow, ...] = field(default_factory=tuple)
    header_col0: str = "OCA (H)"
    category_headers: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_CATEGORY_HEADERS
    )
    title: str = ""
    footer: str = ""


def compute_table(cfg: OcaHConfig) -> list[list[str]]:
    """Build and return the 2-D table as a list of string rows.

    Row structure
    -------------
    - Row 0 (optional): title row — cfg.title in col 0, rest empty
    - Row 1 (always):   header row — [header_col0, cat1, cat2, ...]
    - Row N (per row):  data row   — [procedure, val1, val2, ...]
    - Row M (optional): footer row — cfg.footer in col 0, rest empty
    """
    num_cats = len(cfg.category_headers)
    total_cols = num_cats + 1  # label col + one per category

    def _empty_row() -> list[str]:
        return [""] * total_cols

    result: list[list[str]] = []

    # ── Optional title row ───────────────────────────────────────────
    if cfg.title:
        row = _empty_row()
        row[0] = cfg.title
        result.append(row)

    # ── Header row ───────────────────────────────────────────────────
    result.append([cfg.header_col0] + list(cfg.category_headers))

    # ── Data rows ────────────────────────────────────────────────────
    for oca_row in cfg.rows:
        vals = list(oca_row.values)
        # Pad or truncate values to match category count
        if len(vals) < num_cats:
            vals += [""] * (num_cats - len(vals))
        else:
            vals = vals[:num_cats]
        result.append([oca_row.procedure] + vals)

    # ── Optional footer row ──────────────────────────────────────────
    if cfg.footer:
        row = _empty_row()
        row[0] = cfg.footer
        result.append(row)

    return result
