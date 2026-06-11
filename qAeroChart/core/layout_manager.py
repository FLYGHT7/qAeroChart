# -*- coding: utf-8 -*-
"""
LayoutManager — manages QGIS print layouts for the qAeroChart plugin.

Currently handles:
- Distance/Altitude table (Issue #58), ported from
  scripts/table_distance_altitude.py
"""
from __future__ import annotations

from qgis.core import (
    QgsProject,
    QgsPrintLayout,
    QgsLayoutItemManualTable,
    QgsTableCell,
    QgsTextFormat,
    QgsLayoutFrame,
    QgsLayoutSize,
    QgsLayoutPoint,
)

from ..utils.logger import log
from ..utils.qt_compat import QColor, QFont, QgsUnitTypes
from .distance_altitude_table import build_table_rows, compute_column_widths, extract_table_data

# Layout-item custom property that identifies the table so it can be replaced
_TABLE_PROPERTY = "distance_altitude_table"
_TABLE_ID_PREFIX = "distance_table_"

# Frame geometry (mm) — taken directly from the original script
_TOTAL_WIDTH_MM = 180.20
_FIRST_COL_WIDTH_MM = 36.20
_FRAME_HEIGHT_MM = 9.8
_FRAME_X_MM = 19.79
_FRAME_Y_MM = 190.439
_GRID_STROKE_MM = 0.25
_CELL_MARGIN_MM = 1.0
_FONT_NAME = "Arial"
_FONT_SIZE = 8


class LayoutManager:
    """Manages QGIS print layouts for the qAeroChart plugin.

    Wraps QGIS layout API. Instantiated once per plugin session and
    handed to ``ProfileController``.
    """

    # Name used when a new layout must be created
    LAYOUT_NAME = "AeroChart"

    @staticmethod
    def _next_table_id(layout, prefix: str) -> str:
        """Return the next sequential item ID for *prefix* in *layout*."""
        max_n = 0
        for item in layout.items():
            try:
                item_id = item.id()
                if item_id.startswith(prefix):
                    n = int(item_id[len(prefix):])
                    if n > max_n:
                        max_n = n
            except (AttributeError, ValueError):
                pass
        return f"{prefix}{max_n + 1:03d}"

    def get_or_create_layout(self) -> QgsPrintLayout:
        """Return the first existing print layout or create one called ``AeroChart``.

        Mirrors the original script:
        "if layouts: use layouts[0], else create AutoLayout"
        We use our own canonical name instead of "AutoLayout".
        """
        project = QgsProject.instance()
        manager = project.layoutManager()
        layouts = manager.layouts()
        if layouts:
            layout = layouts[0]
            log(f"LayoutManager: reusing layout '{layout.name()}'")
        else:
            layout = QgsPrintLayout(project)
            layout.initializeDefaults()
            layout.setName(self.LAYOUT_NAME)
            manager.addLayout(layout)
            log(f"LayoutManager: created layout '{self.LAYOUT_NAME}'")
        return layout  # type: ignore[return-value]

    def populate_distance_altitude_table(self, config: dict) -> None:
        """Insert (or replace) the distance/altitude table in the print layout.

        Faithfully ports ``scripts/table_distance_altitude.py``:
        - Derives runway number and point data from the profile config.
        - Removes any existing item with the ``distance_altitude_table``
          custom property before adding a fresh one.
        - Column widths are computed by ``compute_column_widths()``.

        Parameters
        ----------
        config:
            Profile configuration as stored by ``ProfileManager``.
        """
        thr, numeric_columns = extract_table_data(config)
        headers, values = build_table_rows(thr, numeric_columns)

        tbl_rows = [
            [QgsTableCell(h) for h in headers],
            [QgsTableCell(v) for v in values],
        ]

        layout = self.get_or_create_layout()

        # Remove existing table (if any) so re-running is idempotent
        for mf in list(layout.multiFrames()):
            if (
                hasattr(mf, "customProperty")
                and mf.customProperty("name") == _TABLE_PROPERTY
            ):
                layout.removeMultiFrame(mf)
                log("LayoutManager: removed existing distance_altitude_table")

        # Build the manual table
        t = QgsLayoutItemManualTable.create(layout)
        t.setTableContents(tbl_rows)
        t.setGridStrokeWidth(_GRID_STROKE_MM)
        t.setCustomProperty("name", _TABLE_PROPERTY)

        # Text format
        text_format = QgsTextFormat()
        text_format.setFont(QFont(_FONT_NAME))
        text_format.setSize(_FONT_SIZE)
        t.setContentTextFormat(text_format)
        t.setGridColor(QColor(0, 0, 0, 255))

        layout.addMultiFrame(t)

        # Column widths
        col_widths = compute_column_widths(
            num_columns=len(headers),
            total_width=_TOTAL_WIDTH_MM,
            first_col_width=_FIRST_COL_WIDTH_MM,
            stroke_width=_GRID_STROKE_MM,
            cell_margin=_CELL_MARGIN_MM,
        )
        t.setColumnWidths(col_widths)

        # Frame
        try:
            layout_unit = QgsUnitTypes.LayoutMillimeters
        except AttributeError:
            # QGIS ≥ 3.38 moved the enum
            from qgis.core import Qgis  # type: ignore[attr-defined]
            layout_unit = Qgis.LayoutUnit.Millimeters  # type: ignore[attr-defined]

        frame = QgsLayoutFrame(layout, t)
        frame.attemptResize(
            QgsLayoutSize(_TOTAL_WIDTH_MM, _FRAME_HEIGHT_MM, layout_unit)
        )
        frame.attemptMove(
            QgsLayoutPoint(_FRAME_X_MM, _FRAME_Y_MM, layout_unit)
        )

        item_id = self._next_table_id(layout, _TABLE_ID_PREFIX)
        frame.setId(item_id)
        try:
            frame.setDisplayName(item_id)
        except Exception:
            pass

        t.addFrame(frame)

        layout.refresh()

        log(
            f"LayoutManager: table added ({len(numeric_columns)} numeric columns, "
            f"thr={thr})"
        )
