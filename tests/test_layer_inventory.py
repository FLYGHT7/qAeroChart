# -*- coding: utf-8 -*-
"""Unit tests for qAeroChart.core.layer_inventory (Issue #110)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import tests.mocks.qgis_mock  # noqa: F401

from qAeroChart.core import layer_inventory as li


# ---------------------------------------------------------------------------
# Fakes — plain objects, no QGIS classes needed thanks to duck-typing
# ---------------------------------------------------------------------------

P, L, PG = "point", "line", "polygon"  # geometry sentinels
RASTER_T, VECTOR_T, OTHER_T = "raster-type", "vector-type", "mesh-type"


class FakeCrs:
    def __init__(self, authid: str) -> None:
        self._authid = authid

    def authid(self) -> str:
        return self._authid


class FakeProvider:
    def __init__(self, name: str, uri: str = "uri://x") -> None:
        self._name = name
        self._uri = uri

    def name(self) -> str:
        return self._name

    def dataSourceUri(self) -> str:
        return self._uri


class FakeLayer:
    def __init__(
        self,
        name: str,
        *,
        layer_type: str = VECTOR_T,
        geom: str | None = P,
        provider: str = "ogr",
        source: str = "/data/x.shp",
        crs: str | None = "EPSG:4326",
        valid: bool = True,
        with_provider: bool = True,
    ) -> None:
        self._name = name
        self._type = layer_type
        self._geom = geom
        self._provider = FakeProvider(provider) if with_provider else None
        self._source = source
        self._crs = FakeCrs(crs) if crs else None
        self._valid = valid

    def name(self) -> str:
        return self._name

    def type(self):
        return self._type

    def isValid(self) -> bool:
        return self._valid

    def geometryType(self):
        return self._geom

    def dataProvider(self):
        return self._provider

    def crs(self):
        return self._crs

    def source(self) -> str:
        return self._source


class FakeLayerNode:
    def __init__(self, layer) -> None:
        self._layer = layer

    def layer(self):
        return self._layer


class FakeGroupNode:
    def __init__(self, name: str, children=()) -> None:
        self._name = name
        self._children = list(children)

    def name(self) -> str:
        return self._name

    def children(self):
        return self._children


@pytest.fixture(autouse=True)
def sentinel_enums(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module's resolved enum constants with test sentinels.

    Under the shared qgis_mock the real resolution yields MagicMock values,
    which cannot be compared against the fakes' plain strings.
    """
    monkeypatch.setattr(li, "_GEOM_TO_NAME", {P: "Point", L: "Line", PG: "Polygon"})
    monkeypatch.setattr(li, "_TYPE_VECTOR", VECTOR_T)
    monkeypatch.setattr(li, "_TYPE_RASTER", RASTER_T)


# ---------------------------------------------------------------------------
# layer_type_name
# ---------------------------------------------------------------------------


class TestLayerTypeName:
    def test_point(self):
        assert li.layer_type_name(FakeLayer("a", geom=P)) == "Point"

    def test_line(self):
        assert li.layer_type_name(FakeLayer("a", geom=L)) == "Line"

    def test_polygon(self):
        assert li.layer_type_name(FakeLayer("a", geom=PG)) == "Polygon"

    def test_raster(self):
        assert li.layer_type_name(FakeLayer("a", layer_type=RASTER_T)) == "Raster"

    def test_unknown_layer_kind(self):
        assert li.layer_type_name(FakeLayer("a", layer_type=OTHER_T)) == "Unknown"

    def test_unknown_geometry(self):
        assert li.layer_type_name(FakeLayer("a", geom="weird")) == "Unknown"


# ---------------------------------------------------------------------------
# Traversal / row building
# ---------------------------------------------------------------------------


class TestCollectLayerRows:
    def test_flat_tree_in_order(self):
        root = FakeGroupNode("", [
            FakeLayerNode(FakeLayer("A")),
            FakeLayerNode(FakeLayer("B")),
        ])
        rows = li.collect_layer_rows(root)
        assert [r[0] for r in rows] == ["A", "B"]

    def test_nested_group_paths(self):
        # Real usage: collect_layer_rows receives the invisible tree root,
        # so named groups appear as its children.
        inner = FakeGroupNode("Inner", [FakeLayerNode(FakeLayer("C"))])
        outer = FakeGroupNode("Outer", [
            FakeLayerNode(FakeLayer("A")),
            inner,
        ])
        rows = li.collect_layer_rows(FakeGroupNode("", [outer]))
        assert [(r[0], r[5]) for r in rows] == [("A", "Outer"), ("C", "Outer/Inner")]

    def test_row_content_full(self):
        layer = FakeLayer(
            "Airports",
            geom=PG,
            provider="memory",
            source="/shp/airports.shp",
            crs="EPSG:3857",
        )
        rows = li.collect_layer_rows(FakeGroupNode("", [FakeLayerNode(layer)]))
        assert rows == [["Airports", "Polygon", "memory", "EPSG:3857", "/shp/airports.shp", ""]]

    def test_invalid_layer_skipped(self):
        layer = FakeLayer("Broken", valid=False)
        rows = li.collect_layer_rows(FakeGroupNode("", [FakeLayerNode(layer)]))
        assert rows == []

    def test_none_layer_skipped(self):
        rows = li.collect_layer_rows(FakeGroupNode("", [FakeLayerNode(None)]))
        assert rows == []

    def test_layer_without_provider_skipped(self):
        layer = FakeLayer("NoProv", with_provider=False)
        rows = li.collect_layer_rows(FakeGroupNode("", [FakeLayerNode(layer)]))
        assert rows == []

    def test_empty_tree(self):
        assert li.collect_layer_rows(FakeGroupNode("")) == []
