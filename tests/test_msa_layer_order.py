"""Layer-tree ordering tests for the MSA preview layer (issue #162)."""
from unittest.mock import MagicMock, patch

from qAeroChart.core.msa_layer_manager import MsaLayerManager


def _make_iface():
    iface = MagicMock()
    iface.mapCanvas().mapSettings().destinationCrs().authid.return_value = "EPSG:4326"
    return iface


def test_new_preview_layer_is_inserted_at_top_of_layer_tree():
    root = MagicMock()
    project = MagicMock()
    project.mapLayersByName.return_value = []
    project.layerTreeRoot.return_value = root
    preview_layer = MagicMock()

    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as qgs_project,
        patch(
            "qAeroChart.core.msa_layer_manager.QgsVectorLayer",
            return_value=preview_layer,
        ),
        patch.object(MsaLayerManager, "_apply_style"),
    ):
        qgs_project.instance.return_value = project
        result = MsaLayerManager().get_or_create_preview_layer(_make_iface())

    assert result is preview_layer
    project.addMapLayer.assert_called_once_with(preview_layer, False)
    root.insertLayer.assert_called_once_with(0, preview_layer)
    root.addLayer.assert_not_called()


def test_existing_preview_layer_keeps_its_current_position():
    root = MagicMock()
    project = MagicMock()
    project.layerTreeRoot.return_value = root
    existing_preview = MagicMock()
    project.mapLayersByName.return_value = [existing_preview]
    manager = MsaLayerManager()

    with (
        patch("qAeroChart.core.msa_layer_manager.QgsProject") as qgs_project,
        patch.object(manager, "_schema_matches", return_value=True),
    ):
        qgs_project.instance.return_value = project
        result = manager.get_or_create_preview_layer(_make_iface())

    assert result is existing_preview
    root.insertLayer.assert_not_called()
    root.addLayer.assert_not_called()
