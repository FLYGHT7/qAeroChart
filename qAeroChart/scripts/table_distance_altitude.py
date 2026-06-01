"""Interactive distance/altitude table builder with layout insertion.

Usage inside QGIS Python console:
    from qAeroChart.scripts import table_distance_altitude
    table_distance_altitude.run(iface)

This opens a dialog to build or load a table (e.g., from JSON) and then
inserts it into the selected print layout using QgsLayoutItemManualTable.
"""

try:
    from qgis.PyQt import QtWidgets
    from qgis.PyQt.QtGui import QColor, QFont
except ImportError:
    try:
        from PyQt6 import QtWidgets  # type: ignore
        from PyQt6.QtGui import QColor, QFont  # type: ignore
    except ImportError:
        from PyQt5 import QtWidgets  # type: ignore
        from PyQt5.QtGui import QColor, QFont  # type: ignore
from qgis.core import (
    QgsProject,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLayoutItemManualTable,
    QgsTableCell,
    QgsTextFormat,
    QgsLayoutFrame,
    QgsPrintLayout,
)
from qAeroChart.utils.qt_compat import QgsUnitTypes

from qAeroChart.ui.distance_altitude_table_dialog import DistanceAltitudeTableDialog

TABLE_NAME = "distance_altitude_table"
TABLE_ID_PREFIX = "distance_table_"


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


def _calc_column_widths(total_width, first_col_width, num_columns, stroke_width, cell_margin):
    """Mirror width math from original script to keep visual parity."""

    if num_columns < 1:
        return []
    if num_columns == 1:
        return [total_width]

    dynamic_cols = num_columns - 1
    extra_width = (num_columns - 1) * stroke_width + 2 * cell_margin * num_columns
    remaining_width = total_width - first_col_width - extra_width
    if remaining_width <= 0:
        # Fall back to evenly distributing the width
        return [total_width / num_columns] * num_columns
    dynamic_col_width = remaining_width / dynamic_cols
    return [first_col_width] + [dynamic_col_width] * dynamic_cols


def _get_or_create_layout(name, project):
    manager = project.layoutManager()
    for layout in manager.layouts():
        if layout.name() == name:
            return layout
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name or "AutoLayout")
    manager.addLayout(layout)
    return layout


def _remove_existing_table(layout):
    for mf in list(layout.multiFrames()):
        if hasattr(mf, "customProperty") and mf.customProperty("name") == TABLE_NAME:
            layout.removeMultiFrame(mf)


def _build_table(table_rows, cfg, layout):
    t = QgsLayoutItemManualTable.create(layout)
    t.setTableContents([[QgsTableCell(cell) for cell in row] for row in table_rows])
    t.setGridStrokeWidth(cfg["stroke"])
    try:
        t.setCellMargin(cfg["cell_margin"])
    except Exception:
        # Older QGIS versions may not expose cell margin; ignore gracefully
        pass
    t.setCustomProperty("name", TABLE_NAME)

    text_format = QgsTextFormat()
    text_format.setFont(QFont(cfg["font_family"]))
    text_format.setSize(cfg["font_size"])
    t.setContentTextFormat(text_format)
    t.setGridColor(QColor(0, 0, 0, 255))

    layout.addMultiFrame(t)

    col_widths = _calc_column_widths(
        cfg["total_width"],
        cfg["first_col_width"],
        len(table_rows[0]) if table_rows else 0,
        cfg["stroke"],
        cfg["cell_margin"],
    )
    if col_widths:
        t.setColumnWidths(col_widths)

    # Compute a sensible frame height so both header and first data row are visible
    computed_height = cfg["height"]
    try:
        rows = len(table_rows)
        if rows > 0:
            per_row = max(cfg.get("font_size", 8.0) * 2.2, 8.0)  # scale with font size
            computed_height = max(cfg["height"], rows * per_row + 2 * cfg["cell_margin"] + cfg["stroke"])
    except Exception:
        pass

    # If x/y look like legacy defaults (very large y), center horizontally and move near top
    x_pos = cfg["x"]
    y_pos = cfg["y"]
    try:
        pages = layout.pageCollection().pages()
        if pages:
            page_size = pages[0].pageSize()
            if cfg["x"] is None or cfg["x"] <= 0:
                x_pos = (page_size.width() - cfg["total_width"]) / 2.0
            if cfg["y"] is None or cfg["y"] <= 0 or cfg["y"] >= page_size.height() * 0.6:
                y_pos = (page_size.height() - computed_height) / 2.0
    except Exception:
        pass

    frame = QgsLayoutFrame(layout, t)
    frame.attemptResize(
        QgsLayoutSize(cfg["total_width"], computed_height, QgsUnitTypes.LayoutMillimeters)
    )
    frame.attemptMove(QgsLayoutPoint(x_pos, y_pos, QgsUnitTypes.LayoutMillimeters))

    item_id = _next_table_id(layout, TABLE_ID_PREFIX)
    frame.setId(item_id)
    try:
        frame.setDisplayName(item_id)
    except Exception:
        pass

    t.addFrame(frame)

    return t


def build_dialog(iface=None, parent=None, default_layout_name=None):
    """Create and configure the dialog without showing it (non-blocking flow)."""
    dlg = DistanceAltitudeTableDialog(iface=iface, parent=parent)
    if default_layout_name:
        dlg.select_layout(default_layout_name)
        try:
            project = QgsProject.instance()
            layout = _get_or_create_layout(default_layout_name, project)
            dlg.set_layout(layout)
        except Exception:
            pass
    return dlg


def insert_from_dialog(dlg, iface=None):
    """Read data from an accepted dialog and insert the table into the chosen layout."""
    table_rows = dlg.table_data()
    cfg = dlg.config()
    layout_name = cfg["layout_name"]
    if not layout_name or layout_name.startswith("("):
        layout_name = "AutoLayout"
        cfg = {**cfg, "layout_name": layout_name}
    project = QgsProject.instance()
    layout = _get_or_create_layout(layout_name, project)
    _remove_existing_table(layout)
    _build_table(table_rows, cfg, layout)
    layout.refresh()
    if iface:
        iface.messageBar().pushInfo(
            "Distance/Altitude",
            f"Table added to layout '{layout.name()}' with {len(table_rows[0]) if table_rows else 0} columns.",
        )
    else:
        print(
            f"Table added to layout '{layout.name()}' with {len(table_rows[0]) if table_rows else 0} columns."
        )


def run(iface=None, default_layout_name=None, parent_window=None, **_):
    """Open the dialog, then add the table to the chosen layout.

    Blocking version kept for backward-compat (e.g. Python console usage).
    For the plugin toolbar action, _open_distance_table_builder() uses the
    non-blocking build_dialog() / insert_from_dialog() path instead.
    """
    dlg = build_dialog(iface=iface, parent=parent_window, default_layout_name=default_layout_name)

    # PyQt6 removed exec_() — use exec() instead; Accepted=1 so truthiness check works for both
    result = (dlg.exec_ if hasattr(dlg, 'exec_') else dlg.exec)()
    if not result:
        return

    insert_from_dialog(dlg, iface)
