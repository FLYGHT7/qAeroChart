# -*- coding: utf-8 -*-
"""Unit tests for qAeroChart.core.aoi_extractor (Issue #111)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

import tests.mocks.qgis_mock  # noqa: F401

from qAeroChart.core import aoi_extractor as ae


P, L, PG, WEIRD = "point", "line", "polygon", "unknown-geom"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLayer:
    def __init__(
        self,
        name: str,
        *,
        geom=PG,
        features=(),
        editable: bool = False,
        vector: bool = True,
        crs_authid: str = "EPSG:4326",
    ) -> None:
        self._name = name
        self._geom = geom
        self._features = list(features)
        self._editable = editable
        self._vector = vector
        self._crs_authid = crs_authid
        if not vector:
            # Duck-typing check relies on these being absent/non-callable.
            self.getFeatures = None
            self.geometryType = None

    def name(self) -> str:
        return self._name

    def geometryType(self):
        return self._geom

    def isEditable(self) -> bool:
        return self._editable

    def crs(self):
        crs = MagicMock()
        crs.authid.return_value = self._crs_authid
        return crs

    def getFeatures(self, request=None):
        if not self._vector:
            raise AssertionError("non-vector should not be queried")
        return iter(self._features)

    def fields(self):
        return ["f1"]

    def renderer(self):
        return None

    def labeling(self):
        return None


@dataclass
class FakeGroup:
    name: str = ""
    removed: int = 0
    added: list = field(default_factory=list)

    def removeAllChildren(self) -> None:
        self.removed += 1

    def addLayer(self, layer) -> None:
        self.added.append(layer)


@dataclass
class FakeTree:
    children_nodes: list = field(default_factory=list)
    existing_group: FakeGroup | None = None
    created_group: FakeGroup | None = None

    def children(self):
        return self.children_nodes

    def findGroup(self, name):
        return self.existing_group

    def addGroup(self, name):
        self.created_group = FakeGroup(name=name)
        return self.created_group


@dataclass
class FakeProject:
    tree: FakeTree = field(default_factory=FakeTree)

    def layerTreeRoot(self):
        return self.tree

    def transformContext(self):
        return MagicMock()

    def addMapLayer(self, layer, register=True):
        pass


class FakeLayerNode:
    def __init__(self, layer) -> None:
        self._layer = layer

    def layer(self):
        return self._layer


class FakeGroupNode:
    def __init__(self, children=()) -> None:
        self._children = list(children)

    def children(self):
        return self._children


@pytest.fixture(autouse=True)
def sentinel_enums(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ae, "_GEOM_TO_WKB", {P: "Point", L: "LineString", PG: "Polygon"}
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestCollectOrderedLayers:
    def test_top_to_bottom_order(self):
        a, b = FakeLayer("A"), FakeLayer("B")
        root = FakeGroupNode([FakeLayerNode(a), FakeLayerNode(b)])
        assert ae.collect_ordered_layers(root) == [a, b]

    def test_nested_groups_flattened_in_order(self):
        a, b, c = FakeLayer("A"), FakeLayer("B"), FakeLayer("C")
        root = FakeGroupNode([
            FakeLayerNode(a),
            FakeGroupNode([FakeLayerNode(b)]),
            FakeLayerNode(c),
        ])
        assert ae.collect_ordered_layers(root) == [a, b, c]

    def test_none_layer_node_ignored(self):
        root = FakeGroupNode([FakeLayerNode(None), FakeLayerNode(FakeLayer("X"))])
        assert len(ae.collect_ordered_layers(root)) == 1


class TestHelpers:
    def test_wkb_mapping_point_line_polygon(self):
        assert ae.wkb_string_for_geometry(P) == "Point"
        assert ae.wkb_string_for_geometry(L) == "LineString"
        assert ae.wkb_string_for_geometry(PG) == "Polygon"

    def test_wkb_unknown_returns_none(self):
        assert ae.wkb_string_for_geometry(WEIRD) is None

    def test_build_extracted_name(self):
        assert ae.build_extracted_name("Airports") == "Airports_extracted"

    def test_is_vector_like(self):
        assert ae.is_vector_like(FakeLayer("v")) is True
        assert ae.is_vector_like(object()) is False

    def test_summary_counts_all_buckets(self):
        res = ae.ExtractResult(
            extracted=2,
            no_features=1,
            skipped_editable=3,
            skipped_non_vector=4,
            skipped_geometry=5,
            errors=["boom"],
        )
        text = res.summary()
        for fragment in ("2 layer(s)", "without features", "(editable)", "non-vector",
                        "unsupported geometry", "1 error"):
            assert fragment in text


# ---------------------------------------------------------------------------
# extract_aoi flow — counters with substituted internals
# ---------------------------------------------------------------------------


@pytest.fixture()
def flow_env(monkeypatch: pytest.MonkeyPatch):
    """Stub the QGIS-touching internals so the flow logic can be tested."""
    env = MagicMock()
    env.group = FakeGroup(name=ae.GROUP_NAME)
    monkeypatch.setattr(ae, "_prepare_group", lambda project: env.group)
    monkeypatch.setattr(
        ae, "_transform_extent", lambda extent, c, t, p: extent
    )
    yield env


def _run(project, layers, dest="memory", **kwargs):
    project.tree.children_nodes = [FakeLayerNode(lay) for lay in layers]
    return ae.extract_aoi(
        "EXTENT", "EPSG:3857",
        dest=dest,
        gpkg_path="/tmp/x.gpkg" if dest == "gpkg" else None,
        project=project, **kwargs,
    )


class TestExtractFlowCounters:
    def test_memory_extraction_success(self, flow_env, monkeypatch):
        feats = [MagicMock(), MagicMock()]
        layer = FakeLayer("Airports", geom=PG, features=feats)
        captured = {}

        def fake_make(src, token, f):
            captured["token"], captured["features"] = token, list(f)
            return MagicMock()

        monkeypatch.setattr(ae, "_make_memory_layer", fake_make)
        result = _run(FakeProject(), [layer])
        assert result.extracted == 1
        assert captured["token"] == "Polygon"
        assert len(captured["features"]) == 2
        assert flow_env.group.added and len(flow_env.group.added) == 1

    def test_no_features_bucket(self, flow_env):
        result = _run(FakeProject(), [FakeLayer("Empty", features=[])])
        assert result.extracted == 0
        assert result.no_features == 1

    def test_editable_layer_skipped(self, flow_env):
        result = _run(FakeProject(), [FakeLayer("Editing", editable=True)])
        assert result.skipped_editable == 1
        assert result.extracted == 0

    def test_non_vector_skipped_without_query(self, flow_env):
        layer = FakeLayer("Raster", vector=False)
        result = _run(FakeProject(), [layer])
        assert result.skipped_non_vector == 1
        assert result.no_features == 0

    def test_unsupported_geometry_counted(self, flow_env):
        result = _run(FakeProject(), [FakeLayer("Meshy", geom=WEIRD, features=[MagicMock()])])
        assert result.skipped_geometry == 1

    def test_gpkg_success_and_failure_paths(self, flow_env, monkeypatch):
        ok_layer = FakeLayer("OK", features=[MagicMock()])
        bad_layer = FakeLayer("BAD", features=[MagicMock()])
        monkeypatch.setattr(ae, "_write_gpkg_layer", lambda *a: True)
        monkeypatch.setattr(ae, "_reload_gpkg_layer", lambda p, n: MagicMock())
        result = _run(FakeProject(), [ok_layer], dest="gpkg")
        assert result.extracted == 1

        monkeypatch.setattr(ae, "_write_gpkg_layer", lambda *a: False)
        result = _run(FakeProject(), [bad_layer], dest="gpkg")
        assert result.extracted == 0
        assert any("GeoPackage write failed" in e for e in result.errors)
        assert any("BAD" in e for e in result.errors)

    def test_per_layer_error_does_not_abort_run(self, flow_env, monkeypatch):
        boom = FakeLayer("Boom", features=[MagicMock()])
        good = FakeLayer("Good", features=[MagicMock()])

        def flaky_make(src, token, feats):
            if src.name() == "Boom":
                raise RuntimeError("x")
            return MagicMock()

        monkeypatch.setattr(ae, "_make_memory_layer", flaky_make)
        result = _run(FakeProject(), [boom, good])
        assert len(result.errors) == 1
        assert "Boom" in result.errors[0]
        assert result.extracted == 1

    def test_progress_cb_fires_per_layer_and_final(self, flow_env):
        layers = [FakeLayer(f"L{i}") for i in range(3)]
        events = []
        result = _run(
            FakeProject(), layers,
            progress_cb=lambda done, total, name: events.append((done, total)),
        )
        assert events == [(0, 3), (1, 3), (2, 3), (3, 3)]
        assert result.extracted == 0  # no features injected anywhere

    def test_gpkg_requires_path(self, flow_env):
        project = FakeProject()
        project.tree.children_nodes = []
        result = ae.extract_aoi(
            "EXTENT", "EPSG:3857", dest="gpkg", gpkg_path=None, project=project
        )
        assert result.errors == ["GeoPackage destination selected but no path given"]


class TestPrepareGroup:
    def test_existing_group_is_emptied(self):
        group = FakeGroup(name="Charting Representation")
        project = FakeProject(tree=FakeTree(existing_group=group))
        ae._prepare_group(project)
        assert group.removed == 1

    def test_missing_group_created_with_expected_name(self):
        project = FakeProject(tree=FakeTree())
        group = ae._prepare_group(project)
        assert group.name == "Charting Representation"
