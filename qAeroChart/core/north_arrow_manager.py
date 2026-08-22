# -*- coding: utf-8 -*-
"""
NorthArrowManager — creates and manages the "North Arrows" map layer
(Issue #108).

One memory LineString layer accumulates every placed north-arrow figure
(same accumulation pattern as ``MsaLayerManager`` / ``HoldingLayerManager``).
Each placement adds two line features sharing one origin: the true-north
line and the magnetic-north line (rotated by the declination), the latter
carrying an ICAO-style ``VAR x°E/W`` label rendered via layer labeling.

The last-used dialog configuration is persisted in QGIS project variables
(``qAeroChart`` section) so the dock restores it on reopen — same mechanism
as ``HorizontalScaleManager``.
"""
from __future__ import annotations

import json

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsLineSymbol,
)

from ..utils.logger import log
from ..utils.qt_compat import QColor, QVariant
from .north_arrow import NorthArrowGeometry, format_var_label


class NorthArrowManager:
    """Creates/styles the north-arrow memory layer and appends arrow figures."""

    GROUP_NAME = "North Arrow"
    LAYER_NAME = "North Arrows"

    _SECTION = "qAeroChart"
    _CFG_KEY = "qaerochart_narrow_cfg"

    _FIELDS = [
        QgsField("Arrow_Type", QVariant.String),
        QgsField("Label", QVariant.String),
        QgsField("Declination", QVariant.Double),
    ]

    # ------------------------------------------------------------------
    # Layer lifecycle
    # ------------------------------------------------------------------

    def get_or_create_layer(self, iface) -> QgsVectorLayer:
        """Return the shared 'North Arrows' layer, creating it if needed."""
        project = QgsProject.instance()
        existing = project.mapLayersByName(self.LAYER_NAME)
        if existing:
            if self._schema_matches(existing[0]):
                return existing[0]
            legacy_name = f"{self.LAYER_NAME} (legacy schema)"
            existing[0].setName(legacy_name)
            log(
                f"NorthArrowManager: renamed stale-schema '{self.LAYER_NAME}' to "
                f"'{legacy_name}'",
                "WARNING",
            )

        crs = iface.mapCanvas().mapSettings().destinationCrs()
        uri = f"LineString?crs={crs.authid()}"
        layer = QgsVectorLayer(uri, self.LAYER_NAME, "memory")

        pr = layer.dataProvider()
        pr.addAttributes(self._FIELDS)
        layer.updateFields()

        project.addMapLayer(layer, False)
        self._add_to_group(project, layer)
        self._apply_style(layer)

        log(f"NorthArrowManager: created '{self.LAYER_NAME}'")
        return layer

    def clear_arrows(self, layer: QgsVectorLayer) -> None:
        """Remove every north-arrow figure from *layer*."""
        layer.dataProvider().truncate()
        layer.updateExtents()
        layer.triggerRepaint()
        log(f"NorthArrowManager: cleared all arrows from '{layer.name()}'")

    # ------------------------------------------------------------------
    # Figure creation
    # ------------------------------------------------------------------

    def add_arrow(
        self,
        layer: QgsVectorLayer,
        geom: NorthArrowGeometry,
        declination_signed: float,
    ) -> None:
        """Append one two-line north-arrow figure to *layer*."""
        label = format_var_label(declination_signed)
        origin = QgsPointXY(geom.origin_x, geom.origin_y)
        true_tip = QgsPointXY(geom.true_tip_x, geom.true_tip_y)
        mag_tip = QgsPointXY(geom.mag_tip_x, geom.mag_tip_y)

        true_feat = QgsFeature(layer.fields())
        true_feat.setGeometry(QgsGeometry.fromPolylineXY([origin, true_tip]))
        true_feat.setAttributes(["True North", "", declination_signed])

        mag_feat = QgsFeature(layer.fields())
        mag_feat.setGeometry(QgsGeometry.fromPolylineXY([origin, mag_tip]))
        mag_feat.setAttributes(["Magnetic North", label, declination_signed])

        pr = layer.dataProvider()
        pr.addFeatures([true_feat, mag_feat])
        layer.updateExtents()
        layer.triggerRepaint()
        log(f"NorthArrowManager: added arrow at ({geom.origin_x}, {geom.origin_y}) [{label}]")

    # ------------------------------------------------------------------
    # Last-config persistence (project variables)
    # ------------------------------------------------------------------

    def save_config(self, config: dict) -> None:
        """Persist the last-used settings as JSON in a project variable."""
        QgsProject.instance().writeEntry(self._SECTION, self._CFG_KEY, json.dumps(config))

    def load_config(self) -> dict | None:
        """Return the persisted settings dict, or None when absent/corrupt."""
        raw, _found = QgsProject.instance().readEntry(self._SECTION, self._CFG_KEY, "")
        if not raw:
            return None
        try:
            cfg = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            log("NorthArrowManager: corrupt stored config ignored", "WARNING")
            return None
        return cfg if isinstance(cfg, dict) else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schema_matches(self, layer: QgsVectorLayer) -> bool:
        """True if *layer*'s fields match ``_FIELDS`` in name and order.

        ``add_arrow`` writes attributes positionally, so a stale-schema layer
        must not be silently reused.
        """
        existing_names = [f.name() for f in layer.fields()]
        expected_names = [f.name() for f in self._FIELDS]
        return existing_names == expected_names

    def _add_to_group(self, project: QgsProject, layer: QgsVectorLayer) -> None:
        root = project.layerTreeRoot()
        group = root.findGroup(self.GROUP_NAME)
        if group is None:
            group = root.insertGroup(0, self.GROUP_NAME)
        group.addLayer(layer)

    def _apply_style(self, layer: QgsVectorLayer) -> None:
        try:
            symbol = QgsLineSymbol.createSimple({
                "color": "#000000",
                "width": "0.8",
                "width_unit": "MM",
            })
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            self._apply_labeling(layer)
        except Exception as exc:
            log(f"NorthArrowManager: style failed: {exc}", "WARNING")

    def _apply_labeling(self, layer: QgsVectorLayer) -> None:
        text_format = QgsTextFormat()
        text_format.setColor(QColor("#000000"))
        text_format.setSize(8)

        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = "Label"
        label_settings.isExpression = False
        label_settings.enabled = True
        label_settings.setFormat(text_format)

        try:
            from qgis.core import Qgis
            label_settings.placement = Qgis.LabelPlacement.Line
        except AttributeError:
            try:
                label_settings.placement = QgsPalLayerSettings.Line
            except AttributeError:
                pass  # nosec B110 - keep QGIS default placement if both enum paths fail

        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        layer.setLabelsEnabled(True)
