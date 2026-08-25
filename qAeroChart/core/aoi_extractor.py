# -*- coding: utf-8 -*-
"""
AOI feature extractor (Issue #111).

Copies the features that fall inside the current canvas extent from every
vector layer of the project into either temporary memory layers or one
GeoPackage, grouped under a "Charting Representation" tree group — a
throwaway cartographic copy that never touches the source data.

Pure helpers are unit-testable without QGIS; the extraction flow keeps its
QGIS-touching steps behind module-level functions so tests can substitute
them (same approach as other core modules).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from ..utils.logger import log

GROUP_NAME = "Charting Representation"

# ---------------------------------------------------------------------------
# Enum compat — resolve once (msa_dock.py idiom)
# ---------------------------------------------------------------------------

try:
    _GEOM_TO_WKB = {
        Qgis.GeometryType.Point: "Point",
        Qgis.GeometryType.Line: "LineString",
        Qgis.GeometryType.Polygon: "Polygon",
    }
except AttributeError:
    _GEOM_TO_WKB = {
        QgsWkbTypes.PointGeometry: "Point",  # type: ignore[attr-defined]
        QgsWkbTypes.LineGeometry: "LineString",  # type: ignore[attr-defined]
        QgsWkbTypes.PolygonGeometry: "Polygon",  # type: ignore[attr-defined]
    }

try:
    _WRITER_NO_ERROR = QgsVectorFileWriter.WriterError.NoError
except AttributeError:
    _WRITER_NO_ERROR = QgsVectorFileWriter.NoError  # type: ignore[attr-defined]

try:
    _CREATE_OR_OVERWRITE_LAYER = (
        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    )
except AttributeError:
    _CREATE_OR_OVERWRITE_LAYER = (  # type: ignore[attr-defined]
        QgsVectorFileWriter.CreateOrOverwriteLayer
    )


@dataclass
class ExtractResult:
    """Outcome counters for one extraction run."""

    extracted: int = 0
    no_features: int = 0
    skipped_editable: int = 0
    skipped_non_vector: int = 0
    skipped_geometry: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{self.extracted} layer(s) extracted"]
        if self.no_features:
            parts.append(f"{self.no_features} without features in AOI")
        if self.skipped_editable:
            parts.append(f"{self.skipped_editable} skipped (editable)")
        if self.skipped_non_vector:
            parts.append(f"{self.skipped_non_vector} non-vector")
        if self.skipped_geometry:
            parts.append(f"{self.skipped_geometry} unsupported geometry")
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def collect_ordered_layers(root) -> list:
    """Return every layer in *root*, top-to-bottom panel order.

    Nodes exposing a callable ``layer()`` attribute are layer nodes;
    anything else is treated as a group and recursed.
    """
    ordered: list = []
    for child in root.children():
        _collect_node(child, ordered)
    return ordered


def _collect_node(node, ordered: list) -> None:
    layer_getter = getattr(node, "layer", None)
    if callable(layer_getter):
        layer = layer_getter()
        if layer is not None:
            ordered.append(layer)
        return
    for child in node.children():
        _collect_node(child, ordered)


def is_vector_like(layer) -> bool:
    """True for layers exposing the vector API surface used here."""
    return callable(getattr(layer, "getFeatures", None)) and callable(
        getattr(layer, "geometryType", None)
    )


def wkb_string_for_geometry(geom) -> str | None:
    """Map a geometry-type enum value to its memory-layer URI token."""
    return _GEOM_TO_WKB.get(geom)


def build_extracted_name(name: str) -> str:
    return f"{name}_extracted"


# ---------------------------------------------------------------------------
# QGIS-touching steps (monkeypatch targets for unit tests)
# ---------------------------------------------------------------------------


def _prepare_group(project):
    """Return the (emptied) 'Charting Representation' tree group."""
    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME)
    if group is None:
        group = root.addGroup(GROUP_NAME)
    else:
        group.removeAllChildren()
    return group


def _add_layer_to_group(project, group, new_layer) -> None:
    project.addMapLayer(new_layer, False)
    group.addLayer(new_layer)


def _clone_style(source_layer, new_layer) -> None:
    renderer = source_layer.renderer()
    if renderer:
        new_layer.setRenderer(renderer.clone())
    labeling = source_layer.labeling()
    if labeling:
        new_layer.setLabeling(labeling.clone())
        new_layer.setLabelsEnabled(True)


def _transform_extent(extent, canvas_crs, target_crs, project):
    transform = QgsCoordinateTransform(canvas_crs, target_crs, project)
    return transform.transformBoundingBox(extent)


def _features_in_extent(layer, layer_extent) -> list:
    request = QgsFeatureRequest()
    request.setFilterRect(layer_extent)
    return list(layer.getFeatures(request))


def _write_gpkg_layer(
    layer, gpkg_path: str, layer_name: str, layer_extent, project
) -> bool:
    """Append *layer* (clipped to *layer_extent*) as a GPKG layer. True on success."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.filterExtent = layer_extent
    if os.path.exists(gpkg_path):
        options.actionOnExistingFile = _CREATE_OR_OVERWRITE_LAYER

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, gpkg_path, project.transformContext(), options
    )
    error = result[0] if isinstance(result, tuple) else result
    return error == _WRITER_NO_ERROR


def _reload_gpkg_layer(gpkg_path: str, layer_name: str):
    new_layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
    return new_layer


def _make_memory_layer(layer, geom_token: str, features: list):
    new_layer = QgsVectorLayer(
        f"{geom_token}?crs={layer.crs().authid()}",
        build_extracted_name(layer.name()),
        "memory",
    )
    provider = new_layer.dataProvider()
    provider.addAttributes(layer.fields())
    new_layer.updateFields()
    provider.addFeatures(features)
    return new_layer


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def extract_aoi(
    canvas_extent,
    canvas_crs,
    *,
    dest: str = "memory",
    gpkg_path: str | None = None,
    project=None,
    progress_cb=None,
) -> ExtractResult:
    """Extract AOI features from all project layers into *dest* ('memory'|'gpkg').

    ``progress_cb(done, total, layer_name)`` fires before each layer so
    callers can drive a progress widget. Per-layer failures are recorded in
    ``ExtractResult.errors`` and never abort the run.
    """
    result = ExtractResult()

    if dest == "gpkg" and not gpkg_path:
        result.errors.append("GeoPackage destination selected but no path given")
        return result

    project = project or QgsProject.instance()
    group = _prepare_group(project)
    layers = collect_ordered_layers(project.layerTreeRoot())
    total = len(layers)

    for index, layer in enumerate(layers):
        name = layer.name() if hasattr(layer, "name") else "<unnamed>"
        if progress_cb is not None:
            progress_cb(index, total, name)

        if not is_vector_like(layer):
            result.skipped_non_vector += 1
            continue
        if callable(getattr(layer, "isEditable", None)) and layer.isEditable():
            log(f"AoiExtractor: skipping editable layer '{name}'")
            result.skipped_editable += 1
            continue

        try:
            _process_one_layer(
                layer, dest, gpkg_path, canvas_extent, canvas_crs, project, group, result
            )
        except Exception as exc:
            msg = f"Layer '{name}': {exc}"
            result.errors.append(msg)
            log(f"AoiExtractor: {msg}", "ERROR")

    if progress_cb is not None:
        progress_cb(total, total, "")
    return result


def _process_one_layer(
    layer, dest: str, gpkg_path, canvas_extent, canvas_crs, project, group, result
) -> None:
    name = layer.name()
    target_crs = layer.crs()
    layer_extent = (
        _transform_extent(canvas_extent, canvas_crs, target_crs, project)
        if target_crs is not None
        else canvas_extent
    )

    features = _features_in_extent(layer, layer_extent)
    if not features:
        log(f"AoiExtractor: no features inside AOI for '{name}'")
        result.no_features += 1
        return

    geom_token = wkb_string_for_geometry(layer.geometryType())
    if geom_token is None:
        log(f"AoiExtractor: unsupported geometry on '{name}', skipped")
        result.skipped_geometry += 1
        return

    layer_name = build_extracted_name(name)
    if dest == "gpkg":
        ok = _write_gpkg_layer(layer, gpkg_path, layer_name, layer_extent, project)
        if not ok:
            raise RuntimeError("GeoPackage write failed")
        new_layer = _reload_gpkg_layer(gpkg_path, layer_name)
    else:
        new_layer = _make_memory_layer(layer, geom_token, features)

    _clone_style(layer, new_layer)
    _add_layer_to_group(project, group, new_layer)
    result.extracted += 1
    log(f"AoiExtractor: extracted '{name}' -> '{layer_name}' ({dest})")
