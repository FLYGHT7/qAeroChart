"""Tests for MSA layer creation and cartographic-label layer naming."""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qgis.PyQt.QtCore import QVariant

from qAeroChart.core.msa_layer_manager import MsaLayerManager


def test_bundled_qml_matches_issue_attachment():
    path = Path(__file__).resolve().parents[1] / "qAeroChart" / "styles" / "MSA_Sectors_style.qml"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "a99557113d4a1f19e171594b78b6ad7292dbefd328dea12dc441d6b9fbcc6f1f"
    )


def test_aeronautical_style_registered_without_changing_current_style():
    layer = MagicMock()
    layer.crs().authid.return_value = "EPSG:4326"
    layer.fields.return_value = ["field"]
    with (
        patch("qAeroChart.core.msa_layer_manager.QgsVectorLayer") as vector_layer,
        patch("qAeroChart.core.msa_layer_manager.QgsMapLayerStyle") as style,
    ):
        temporary = vector_layer.return_value
        temporary.loadNamedStyle.return_value = ("", True)
        MsaLayerManager()._add_aeronautical_style(layer)

    vector_layer.assert_called_once_with("Polygon?crs=EPSG:4326", "MSA style", "memory")
    temporary.dataProvider().addAttributes.assert_called_once_with(["field"])
    temporary.updateFields.assert_called_once_with()
    path = temporary.loadNamedStyle.call_args.args[0]
    assert path.endswith("/styles/MSA_Sectors_style.qml")
    style.return_value.readFromLayer.assert_called_once_with(temporary)
    layer.styleManager().addStyle.assert_called_once_with("aeronautical_charts", style.return_value)
    layer.styleManager().setCurrentStyle.assert_not_called()
    layer.setRenderer.assert_not_called()
    layer.setLabelsEnabled.assert_not_called()


@pytest.mark.parametrize("failure", ["missing", "load", "registration"])
def test_aeronautical_style_failure_keeps_default(failure):
    layer = MagicMock()
    with (
        patch("qAeroChart.core.msa_layer_manager.Path.is_file", return_value=failure != "missing"),
        patch("qAeroChart.core.msa_layer_manager.QgsVectorLayer") as vector_layer,
        patch("qAeroChart.core.msa_layer_manager.log") as logger,
    ):
        temporary = vector_layer.return_value
        temporary.loadNamedStyle.return_value = ("invalid QML", failure != "load")
        layer.styleManager().addStyle.return_value = False
        MsaLayerManager()._add_aeronautical_style(layer)

    logger.assert_called_once()
    assert logger.call_args.args[1] == "WARNING"
    layer.styleManager().setCurrentStyle.assert_not_called()
    layer.setRenderer.assert_not_called()
    if failure != "registration":
        layer.styleManager().addStyle.assert_not_called()


@pytest.mark.parametrize("preview", [False, True])
def test_only_new_committed_layers_get_aeronautical_style(preview):
    manager = MsaLayerManager()
    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as project,
        patch.object(manager, "_apply_style") as apply_style,
        patch.object(manager, "_add_aeronautical_style") as add_style,
    ):
        project.instance().mapLayersByName.return_value = []
        layer = manager._get_or_create(_make_iface(), "test", is_preview=preview, add_to_group=not preview)
    apply_style.assert_called_once_with(layer, is_preview=preview)
    if preview:
        add_style.assert_not_called()
    else:
        add_style.assert_called_once_with(layer)


def test_existing_layer_styles_are_preserved():
    manager = MsaLayerManager()
    existing = MagicMock()
    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as project,
        patch.object(manager, "_schema_matches", return_value=True),
        patch.object(manager, "_apply_style") as apply_style,
        patch.object(manager, "_add_aeronautical_style") as add_style,
    ):
        project.instance().mapLayersByName.return_value = [existing]
        assert manager.get_or_create_layer(_make_iface()) is existing
    apply_style.assert_not_called()
    add_style.assert_not_called()


def _make_iface():
    iface = MagicMock()
    iface.mapCanvas().mapSettings().destinationCrs().authid.return_value = "EPSG:4326"
    return iface


def _project_with_names(names):
    project = MagicMock()
    layers = {}
    for index, layer_name in enumerate(names):
        layer = MagicMock()
        layer.name.return_value = layer_name
        layers[str(index)] = layer
    project.mapLayers.return_value = layers
    return project


def test_carto_label_names_use_base_then_next_suffix():
    manager = MsaLayerManager()

    assert manager._next_carto_label_name(_project_with_names([])) == "carto_label_MSA"
    assert manager._next_carto_label_name(
        _project_with_names(["carto_label_MSA"])
    ) == "carto_label_MSA_1"
    assert manager._next_carto_label_name(
        _project_with_names(["carto_label_MSA", "carto_label_MSA_1", "carto_label_MSA_3"])
    ) == "carto_label_MSA_4"


def test_carto_label_name_ignores_unrelated_layers():
    project = _project_with_names([
        "carto_label_MSA_extra",
        "carto_label_MSA_old",
        "carto_label_MSA_1x",
        "other_layer",
    ])

    assert MsaLayerManager._next_carto_label_name(project) == "carto_label_MSA"


def test_create_carto_label_layer_uses_exact_schema_and_group_order():
    project = MagicMock()
    project.mapLayers.return_value = {}
    root = project.layerTreeRoot.return_value
    group = root.findGroup.return_value = MagicMock()
    layer = MagicMock()
    provider = layer.dataProvider.return_value
    manager = MsaLayerManager()

    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as qgs_project,
        patch("qAeroChart.core.msa_layer_manager.QgsVectorLayer", return_value=layer) as qgs_layer,
        patch("qAeroChart.core.msa_layer_manager.QgsField") as qgs_field,
    ):
        qgs_project.instance.return_value = project
        result = manager.create_carto_label_layer(_make_iface())

    assert result is layer
    qgs_layer.assert_called_once_with("Point?crs=EPSG:4326", "carto_label_MSA", "memory")
    expected_fields = [
        (('id', QVariant.String), {"len": 255, "prec": 0}),
        (('txt_label', QVariant.String), {"len": 255, "prec": 0}),
        (('bold', QVariant.Bool), {"len": 0, "prec": 0}),
        (('html', QVariant.Bool), {"len": 0, "prec": 0}),
        (('font_size', QVariant.Double), {"len": 10, "prec": 2}),
        (('bold_text', QVariant.String), {"len": 25, "prec": 0}),
        (('text-rotation', QVariant.Double), {"len": 10, "prec": 3}),
    ]
    assert [(call.args, call.kwargs) for call in qgs_field.call_args_list] == expected_fields
    provider.addAttributes.assert_called_once_with([qgs_field.return_value] * 7)
    layer.updateFields.assert_called_once_with()
    project.addMapLayer.assert_called_once_with(layer, False)
    group.insertLayer.assert_called_once_with(0, layer)
    provider.addFeatures.assert_not_called()


def test_carto_line_names_use_independent_family():
    project = _project_with_names([
        "carto_label_MSA_9", "carto_line_MSA", "carto_line_MSA_3",
    ])

    assert MsaLayerManager._next_carto_name(project, "carto_line_MSA") == "carto_line_MSA_4"


def test_create_carto_line_layer_uses_exact_schema_and_group_order():
    project = MagicMock()
    project.mapLayers.return_value = {}
    root = project.layerTreeRoot.return_value
    group = root.findGroup.return_value = MagicMock()
    layer = MagicMock()
    provider = layer.dataProvider.return_value
    manager = MsaLayerManager()

    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as qgs_project,
        patch("qAeroChart.core.msa_layer_manager.QgsVectorLayer", return_value=layer) as qgs_layer,
        patch("qAeroChart.core.msa_layer_manager.QgsField") as qgs_field,
    ):
        qgs_project.instance.return_value = project
        result = manager.create_carto_line_layer(_make_iface())

    assert result is layer
    qgs_layer.assert_called_once_with("LineString?crs=EPSG:4326", "carto_line_MSA", "memory")
    expected_fields = [
        (('id', QVariant.String), {"len": 255, "prec": 0}),
        (('txt_label', QVariant.String), {"len": 255, "prec": 0}),
    ]
    assert [(call.args, call.kwargs) for call in qgs_field.call_args_list] == expected_fields
    provider.addAttributes.assert_called_once_with([qgs_field.return_value] * 2)
    layer.updateFields.assert_called_once_with()
    project.addMapLayer.assert_called_once_with(layer, False)
    group.insertLayer.assert_called_once_with(0, layer)
    provider.addFeatures.assert_not_called()
