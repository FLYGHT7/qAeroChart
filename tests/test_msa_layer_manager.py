"""Tests for MSA layer creation and cartographic-label layer naming."""
from unittest.mock import MagicMock, patch

from qgis.PyQt.QtCore import QVariant

from qAeroChart.core.msa_layer_manager import MsaLayerManager


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
