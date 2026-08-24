# -*- coding: utf-8 -*-
"""Unit tests for qAeroChart.core.north_arrow_manager (Issue #108)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import tests.mocks.qgis_mock  # noqa: F401

from qAeroChart.core.north_arrow import compute_arrow_geometry
from qAeroChart.core.north_arrow_manager import NorthArrowManager


# ---------------------------------------------------------------------------
# Fake QgsProject (same pattern as horizontal/vertical scale manager tests)
# ---------------------------------------------------------------------------


class _FakeProject:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def writeEntry(self, section: str, key: str, value: str) -> None:
        self._store[f"{section}/{key}"] = value

    def readEntry(self, section: str, key: str, default: str = "") -> tuple[str, bool]:
        full_key = f"{section}/{key}"
        found = full_key in self._store
        return self._store.get(full_key, default), found

    def removeEntry(self, section: str, key: str) -> None:
        self._store.pop(f"{section}/{key}", None)


@pytest.fixture()
def fake_project() -> _FakeProject:
    return _FakeProject()


@pytest.fixture()
def mgr(fake_project: _FakeProject) -> NorthArrowManager:
    with patch(
        "qAeroChart.core.north_arrow_manager.QgsProject",
        **{"instance.return_value": fake_project},
    ):
        yield NorthArrowManager()


def _fake_layer() -> MagicMock:
    layer = MagicMock()
    layer.fields.return_value = []
    layer.name.return_value = NorthArrowManager.LAYER_NAME
    return layer


def _reset_shared_feature_mock() -> None:
    """Clear call history on the module-level shared QgsFeature mock.

    qgis_mock exposes ``QgsFeature`` as a bare MagicMock whose return_value
    persists across tests — without resetting, earlier tests' setAttributes
    records leak into later assertions.
    """
    from qgis.core import QgsFeature

    QgsFeature.reset_mock()


# ---------------------------------------------------------------------------
# add_arrow
# ---------------------------------------------------------------------------


class TestAddArrow:
    def test_adds_two_features(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        geom = compute_arrow_geometry(0.0, 0.0, 1000.0, 700.0, 5.0)
        mgr.add_arrow(layer, geom, 5.0)
        layer.dataProvider().addFeatures.assert_called_once()
        features = layer.dataProvider().addFeatures.call_args[0][0]
        assert len(features) == 2

    def test_feature_attributes_in_order(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        geom = compute_arrow_geometry(10.0, 20.0, 1000.0, 700.0, 5.5)
        _reset_shared_feature_mock()
        mgr.add_arrow(layer, geom, 5.5)
        features = layer.dataProvider().addFeatures.call_args[0][0]

        # Mock semantics: every QgsFeature(...) call returns the *same* mock,
        # so both setAttributes calls land on one object — read them in order.
        feat = features[0]
        attr_calls = [c.args[0] for c in feat.mock_calls if c[0] == "setAttributes"]

        assert len(attr_calls) == 2

        true_attrs = attr_calls[0]
        mag_attrs = attr_calls[1]

        assert true_attrs[0] == "True North"
        assert true_attrs[1] == ""
        assert true_attrs[2] == pytest.approx(5.5)

        assert mag_attrs[0] == "Magnetic North"
        assert mag_attrs[1] == "VAR 5.5\N{DEGREE SIGN}E"
        assert mag_attrs[2] == pytest.approx(5.5)

    def test_west_label_written_to_magnetic_feature(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        geom = compute_arrow_geometry(0.0, 0.0, 1000.0, 700.0, -4.0)
        _reset_shared_feature_mock()
        mgr.add_arrow(layer, geom, -4.0)
        features = layer.dataProvider().addFeatures.call_args[0][0]
        mag_attrs = features[1].setAttributes.call_args[0][0]
        assert mag_attrs[1] == "VAR 4\N{DEGREE SIGN}W"

    def test_layer_refreshed_after_add(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        geom = compute_arrow_geometry(0.0, 0.0, 1000.0, 700.0, 0.0)
        mgr.add_arrow(layer, geom, 0.0)
        layer.updateExtents.assert_called_once()
        layer.triggerRepaint.assert_called_once()


# ---------------------------------------------------------------------------
# clear_arrows
# ---------------------------------------------------------------------------


class TestClearArrows:
    def test_clear_truncates_provider(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        mgr.clear_arrows(layer)
        layer.dataProvider().truncate.assert_called_once()

    def test_clear_repaints(self, mgr: NorthArrowManager) -> None:
        layer = _fake_layer()
        mgr.clear_arrows(layer)
        layer.triggerRepaint.assert_called_once()


# ---------------------------------------------------------------------------
# Config persistence round-trip
# ---------------------------------------------------------------------------


class TestConfigPersistence:
    def test_round_trip(self, mgr: NorthArrowManager) -> None:
        cfg = {
            "origin_x": 1.5,
            "origin_y": -2.0,
            "true_len_m": 10000.0,
            "mag_len_m": 7000.0,
            "declination": -3.25,
        }
        mgr.save_config(cfg)
        loaded = mgr.load_config()
        assert loaded == cfg

    def test_load_missing_returns_none(self, fake_project: _FakeProject) -> None:
        with patch(
            "qAeroChart.core.north_arrow_manager.QgsProject",
            **{"instance.return_value": fake_project},
        ):
            assert NorthArrowManager().load_config() is None

    def test_load_corrupt_returns_none(self) -> None:
        from qAeroChart.core import north_arrow_manager as mod

        bad_project = MagicMock()
        bad_project.readEntry.return_value = ("{not valid json", True)
        with patch.object(mod.QgsProject, "instance", return_value=bad_project):
            assert NorthArrowManager().load_config() is None

    def test_saved_value_is_valid_json(
        self, mgr: NorthArrowManager, fake_project: _FakeProject
    ) -> None:
        mgr.save_config({"a": 1})
        raw, found = fake_project.readEntry("qAeroChart", "qaerochart_narrow_cfg", "")
        assert found is True
        assert isinstance(json.loads(raw), dict)


# ---------------------------------------------------------------------------
# Schema guard
# ---------------------------------------------------------------------------


class _StubField:
    """Lightweight QgsField stand-in exposing only ``name()``."""

    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class TestSchemaMatches:
    def test_matching_field_names_pass(
        self, mgr: NorthArrowManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            NorthArrowManager,
            "_FIELDS",
            [_StubField(n) for n in ["Arrow_Type", "Label", "Declination"]],
        )
        layer = MagicMock()
        layer.fields.return_value = [
            _StubField("Arrow_Type"),
            _StubField("Label"),
            _StubField("Declination"),
        ]
        assert mgr._schema_matches(layer) is True

    def test_wrong_field_order_fails(
        self, mgr: NorthArrowManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            NorthArrowManager,
            "_FIELDS",
            [_StubField(n) for n in ["Arrow_Type", "Label", "Declination"]],
        )
        layer = MagicMock()
        layer.fields.return_value = [
            _StubField("Declination"),
            _StubField("Label"),
            _StubField("Arrow_Type"),
        ]
        assert mgr._schema_matches(layer) is False

    def test_missing_field_fails(
        self, mgr: NorthArrowManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            NorthArrowManager,
            "_FIELDS",
            [_StubField(n) for n in ["Arrow_Type", "Label", "Declination"]],
        )
        layer = MagicMock()
        layer.fields.return_value = [_StubField("Arrow_Type"), _StubField("Label")]
        assert mgr._schema_matches(layer) is False
