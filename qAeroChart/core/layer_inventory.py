# -*- coding: utf-8 -*-
"""
Layer inventory builder (Issue #110).

Walks the QGIS layer tree and produces one row per layer with the fields
needed to audit/document where the project's data lives:

    Layer Name | Type | Provider | CRS | Source | Panel Group

Pure traversal logic — nodes are duck-typed (a node exposing a callable
``layer()`` attribute is a layer node, anything else is treated as a group),
so it runs unchanged under the unit-test mocks without importing
QgsLayerTree classes.

Geometry/layer-type enums are resolved once at import time using the
try-scoped / fallback idiom used across the plugin: QGIS 4 exposes
``Qgis.GeometryType.*`` and ``QgsMapLayer.LayerType.*``, while QGIS 3 uses
the flat ``QgsWkbTypes.PointGeometry`` / ``QgsMapLayer.Vector`` constants.
"""
from __future__ import annotations

from qgis.core import Qgis, QgsMapLayer, QgsProject, QgsWkbTypes

HEADERS = ["Layer Name", "Layer Type", "Provider", "CRS", "Source", "Panel Group"]

# ---------------------------------------------------------------------------
# Enum compat — resolve once (msa_dock.py _GEOM_POINT idiom)
# ---------------------------------------------------------------------------

try:
    _GEOM_TO_NAME = {
        Qgis.GeometryType.Point: "Point",
        Qgis.GeometryType.Line: "Line",
        Qgis.GeometryType.Polygon: "Polygon",
    }
except AttributeError:
    _GEOM_TO_NAME = {
        QgsWkbTypes.PointGeometry: "Point",  # type: ignore[attr-defined]
        QgsWkbTypes.LineGeometry: "Line",  # type: ignore[attr-defined]
        QgsWkbTypes.PolygonGeometry: "Polygon",  # type: ignore[attr-defined]
    }

try:
    _TYPE_VECTOR = QgsMapLayer.LayerType.Vector
    _TYPE_RASTER = QgsMapLayer.LayerType.Raster
except AttributeError:
    _TYPE_VECTOR = QgsMapLayer.Vector  # type: ignore[attr-defined]
    _TYPE_RASTER = QgsMapLayer.Raster  # type: ignore[attr-defined]


def layer_type_name(layer) -> str:
    """Return a display type for *layer*: Point/Line/Polygon/Raster/Unknown."""
    try:
        layer_type = layer.type()
    except AttributeError:
        return "Unknown"

    if layer_type == _TYPE_VECTOR:
        try:
            return _GEOM_TO_NAME.get(layer.geometryType(), "Unknown")
        except AttributeError:
            return "Unknown"
    if layer_type == _TYPE_RASTER:
        return "Raster"
    return "Unknown"


def collect_layer_rows(root) -> list[list[str]]:
    """Walk the layer tree rooted at *root* and return inventory rows.

    Rows follow tree order; ``Panel Group`` holds the ``/``-joined group
    names. Layers that are invalid or expose no data provider are skipped,
    matching the contributor's original scripts.
    """
    rows: list[list[str]] = []
    for child in root.children():
        _process_node(child, group_path="", rows=rows)
    return rows


def build_inventory(project=None) -> list[list[str]]:
    """Convenience wrapper: inventory rows for *project* (default singleton)."""
    project = project or QgsProject.instance()
    return collect_layer_rows(project.layerTreeRoot())


def _process_node(node, *, group_path: str, rows: list[list[str]]) -> None:
    layer_getter = getattr(node, "layer", None)
    if callable(layer_getter):
        row = _layer_row(layer_getter(), group_path)
        if row is not None:
            rows.append(row)
        return

    name = getattr(node, "name", lambda: "")()
    path = f"{group_path}/{name}" if group_path else name
    for child in node.children():
        _process_node(child, group_path=path, rows=rows)


def _layer_row(layer, group_path: str) -> list[str] | None:
    if layer is None or not layer.isValid():
        return None
    provider = getattr(layer, "dataProvider", None)
    if provider is None or not callable(provider):
        return None

    crs_authid = ""
    crs_getter = getattr(layer, "crs", None)
    if callable(crs_getter):
        crs = crs_getter()
        if crs is not None:
            crs_authid = crs.authid()

    dp = provider()
    if dp is None:
        return None
    source_getter = getattr(layer, "source", None)
    source = source_getter() if callable(source_getter) else dp.dataSourceUri()

    return [
        layer.name(),
        layer_type_name(layer),
        dp.name(),
        crs_authid,
        source,
        group_path,
    ]
