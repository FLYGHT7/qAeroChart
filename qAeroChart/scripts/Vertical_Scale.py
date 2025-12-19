"""
Create a vertical scale (lines + labels) for Type A charts.

Defaults follow the provided spec:
- Vertical scale: 1:10 000 (configurable)
- Meters: 0..100 every 25 m on the right
- Feet: 0..300 every 50 ft on the left
- Layer group: "Vertical Scale" with two child layers:
  - Lines: "Vertical Scale"
  - Labels: "carto-vertical-scale-label"

Usage: select a guide line (baseline) to orient the scale, then run this script.
"""

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
    QgsNullSymbolRenderer,
    QgsTextBufferSettings,
    Qgis,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.utils import iface

# Editable parameters
SCALE_DENOMINATOR = 10000  # default vertical scale 1:10 000
OFFSET = -50.0             # shift from the selected guide line (map units)
TICK_LEN = 15.0            # tick length (map units)
M_MAX = 100                # meters max
M_STEP = 25                # meters step
FT_MAX = 300               # feet max
FT_STEP = 50               # feet step


def _scale_factor(denominator: float) -> float:
    """Convert real meters to map units based on vertical scale denominator.

    For a denominator of 10 000, 100 m → 100 * (10 000 / 1000) = 1000 map units.
    """
    try:
        return float(denominator) / 1000.0
    except Exception:
        return 10.0


def _create_layer(name: str, geom: str, crs_authid: str, fields):
    layer = QgsVectorLayer(f"{geom}?crs={crs_authid}", name, "memory")
    layer.dataProvider().addAttributes(fields)
    layer.updateFields()
    return layer


def run_vertical_scale(
    scale_denominator: float = SCALE_DENOMINATOR,
    offset: float = OFFSET,
    tick_len: float = TICK_LEN,
    m_max: int = M_MAX,
    m_step: int = M_STEP,
    ft_max: int = FT_MAX,
    ft_step: int = FT_STEP,
    *,
    basepoint: QgsPoint = None,
    angle: float = None,
    name: str = "Vertical Scale",
):
    map_srid = iface.mapCanvas().mapSettings().destinationCrs().authid()

    # If no basepoint/angle provided, fall back to selected guide line
    if basepoint is None or angle is None:
        layer = iface.activeLayer()
        if not layer or not layer.selectedFeatureCount():
            iface.messageBar().pushMessage(
                "Vertical Scale",
                "Select a guide line feature or set an origin/azimuth in the dock.",
                level=Qgis.Warning,
                duration=4,
            )
            return
        selection = layer.selectedFeatures()
        geom = selection[0].geometry().asPolyline()
        if not geom:
            iface.messageBar().pushMessage(
                "Vertical Scale",
                "Selected feature is not a line.",
                level=Qgis.Critical,
                duration=4,
            )
            return

        start_point = QgsPoint(geom[0])
        end_point = QgsPoint(geom[-1])
        angle = start_point.azimuth(end_point)
        basepoint = start_point

    factor = _scale_factor(scale_denominator)
    basepoint = basepoint if isinstance(basepoint, QgsPoint) else QgsPoint(basepoint)
    basepoint = basepoint.project(offset, angle - 90)

    # Split the spine into two rails (feet left, meters right) separated by half the tick length
    half_spacing = tick_len * 0.5
    base_left = basepoint.project(half_spacing, angle - 90)
    base_right = basepoint.project(half_spacing, angle + 90)

    # Prepare layers
    line_fields = [QgsField('id', QVariant.String, len=255), QgsField('symbol', QVariant.String, len=25)]
    label_fields = [QgsField('id', QVariant.String, len=255), QgsField('txt_label', QVariant.String, len=50)]

    line_layer = _create_layer(f"{name} - Lines", "Linestring", map_srid, line_fields)
    label_layer = _create_layer(f"{name} - Labels", "Point", map_srid, label_fields)

    def add_line(points, symbol_val):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolyline(points))
        f.setAttributes([symbol_val, symbol_val])
        line_layer.dataProvider().addFeature(f)

    def add_label(point, text, label_id):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point)))
        f.setAttributes([label_id, text])
        label_layer.dataProvider().addFeature(f)

    # Meter side (right)
    meter_ticks = []
    for val_m in range(0, m_max + 1, m_step):
        dist = val_m * factor
        p0 = base_right.project(dist, angle)
        p1 = p0.project(tick_len, angle + 90)
        meter_ticks.append(p0)
        add_line([p0, p1], "m_tick")
        # label slightly beyond tick (skip max; we handle it separately to avoid duplicate)
        if val_m < m_max:
            p_label = p1.project(tick_len * 0.75, angle + 90)
            add_label(p_label, str(val_m), f"m_{val_m}")

    # Feet side (left)
    feet_ticks = []
    for val_ft in range(0, ft_max + 1, ft_step):
        meters = val_ft * 0.3048
        dist = meters * factor
        p0 = base_left.project(dist, angle)
        p1 = p0.project(tick_len, angle - 90)
        feet_ticks.append(p0)
        add_line([p0, p1], "ft_tick")
        if val_ft < ft_max:
            p_label = p1.project(tick_len * 0.75, angle - 90)
            add_label(p_label, str(val_ft), f"ft_{val_ft}")

    # Mid-step ticks for finer reading (half of each step) and secondary rails through their tips
    small_tick_len = tick_len * 0.45
    sec_offset = tick_len * 0.8  # extra offset to ensure secondary rail is visible (both sides)
    meter_small_tips = []
    feet_small_tips = []
    for val_m in range(m_step // 2, m_max + 1, m_step):
        dist = val_m * factor
        p0 = base_right.project(dist, angle)
        p1 = p0.project(small_tick_len, angle + 90)
        add_line([p0, p1], "m_tick_small")
        meter_small_tips.append(p1)
    for val_ft in range(ft_step // 2, ft_max + 1, ft_step):
        meters = val_ft * 0.3048
        dist = meters * factor
        p0 = base_left.project(dist, angle)
        p1 = p0.project(small_tick_len, angle - 90)
        add_line([p0, p1], "ft_tick_small")
        feet_small_tips.append(p1)

    # Main rails per side
    if meter_ticks:
        add_line(meter_ticks, "scale_line_right")
    if feet_ticks:
        add_line(feet_ticks, "scale_line_left")

    # Secondary rail for meters (right)
    start_tip_m = base_right.project(sec_offset, angle + 90)
    end_tip_m = base_right.project(m_max * factor, angle).project(sec_offset, angle + 90)
    add_line([start_tip_m, end_tip_m], "scale_line_right_secondary")

    # Secondary rail for feet (left)
    start_tip_f = base_left.project(sec_offset, angle - 90)
    end_tip_f = base_left.project(ft_max * 0.3048 * factor, angle).project(sec_offset, angle - 90)
    add_line([start_tip_f, end_tip_f], "scale_line_left_secondary")

    # Connect rails at base (bottom) only; no top connector
    if meter_ticks and feet_ticks:
        add_line([feet_ticks[0], meter_ticks[0]], "bottom_connect")

    # Add static labels: numeric max on last tick; units on extra tick beyond
    try:
        unit_offset = tick_len * 0.6
        label_offset = tick_len * 0.75
        unit_label_along = tick_len * 1.0
        unit_label_up = tick_len * 0.3

        # Meters: number at last tick; unit on an extra tick beyond
        meters_top_val = meter_ticks[-1]
        meters_top_tick = meters_top_val.project(tick_len, angle + 90)
        add_label(meters_top_tick.project(label_offset, angle + 90), str(m_max), "lbl_m_max")
        meters_unit_label = meters_top_val.project(unit_label_along, angle)
        meters_unit_label = meters_unit_label.project(unit_label_up, angle + 90)
        add_label(meters_unit_label, "METERS", "lbl_meters")

        # Feet: number at last tick; unit on an extra tick beyond
        feet_top_val = feet_ticks[-1]
        feet_top_tick = feet_top_val.project(tick_len, angle - 90)
        add_label(feet_top_tick.project(label_offset, angle - 90), str(ft_max), "lbl_ft_max")
        feet_unit_label = feet_top_val.project(unit_label_along, angle + 180)
        feet_unit_label = feet_unit_label.project(unit_label_up, angle - 90)
        add_label(feet_unit_label, "FEET", "lbl_feet")
        # Bottom title
        bottom = basepoint.project(-tick_len * 3.0, angle)
        add_label(bottom, "VERTICAL", "lbl_vertical")
        add_label(bottom.project(tick_len * 1.5, angle), "SCALE", "lbl_scale")
        add_label(bottom.project(tick_len * 3.0, angle), f"1:{int(scale_denominator):,}".replace(',', ' '), "lbl_ratio")
    except Exception:
        pass

    # Basic styling: black thin lines
    try:
        line_renderer = line_layer.renderer()
        sym = line_renderer.symbol()
        sym.setColor(QColor("black"))
        sym.setWidth(0.25)
        line_layer.triggerRepaint()
    except Exception:
        pass

    # Make point layer invisible (only labels visible)
    try:
        label_layer.setRenderer(QgsNullSymbolRenderer())
    except Exception:
        try:
            pt_sym = QgsMarkerSymbol.createSimple({"color": "transparent", "size": "0"})
            label_layer.setRenderer(QgsSingleSymbolRenderer(pt_sym))
        except Exception:
            pass

    # Enable labeling for txt_label field so numbers/headers render
    try:
        pal = QgsPalLayerSettings()
        pal.fieldName = "txt_label"
        pal.isExpression = False
        try:
            pal.placement = Qgis.LabelPlacement.OverPoint
        except Exception:
            pal.placement = QgsPalLayerSettings.OverPoint
        pal.enabled = True
        fmt = QgsTextFormat()
        fmt.setFont(QFont("Segoe UI", 8))
        fmt.setSize(8)
        fmt.setColor(QColor("black"))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.6)
        buf.setColor(QColor("white"))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)
        label_layer.setLabelsEnabled(True)
        label_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        label_layer.triggerRepaint()
    except Exception:
        pass

    # Add to project under a group
    root = QgsProject.instance().layerTreeRoot()
    group_name = name if name else "Vertical Scale"
    group = root.findGroup(group_name) or root.addGroup(group_name)
    QgsProject.instance().addMapLayer(line_layer, False)
    QgsProject.instance().addMapLayer(label_layer, False)
    group.addLayer(line_layer)
    group.addLayer(label_layer)

    iface.messageBar().pushMessage(
        "Vertical Scale",
        "Created scale lines and labels (meters/feet).",
        level=Qgis.Success,
        duration=4,
    )


if __name__ == "__main__":
    run_vertical_scale()