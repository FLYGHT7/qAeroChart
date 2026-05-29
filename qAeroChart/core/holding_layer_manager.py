# -*- coding: utf-8 -*-
"""
HoldingLayerManager — creates and manages the 'Holding Nominal' QGIS memory layer.

The layer lives in a 'Holdings' group at the top of the layer tree and accumulates
all holdings created in the current QGIS session.  Geometry is a mix of
QgsCircularString (turns) and plain polylines (legs), stored in a Linestring layer
— the same approach used by qpansopy.
"""
from __future__ import annotations

import uuid

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsCircularString,
)

from ..utils.logger import log
from ..utils.qt_compat import QVariant
from .holding import HoldingParameters, HoldingResult


class HoldingLayerManager:
    GROUP_NAME = "Holdings"
    LAYER_NAME = "Holding Nominal"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_layer(self, iface) -> QgsVectorLayer:
        """Return the shared 'Holding Nominal' layer, creating it if needed."""
        project = QgsProject.instance()
        existing = project.mapLayersByName(self.LAYER_NAME)
        if existing:
            return existing[0]

        crs = iface.mapCanvas().mapSettings().destinationCrs()
        uri = f"Linestring?crs={crs.authid()}"
        layer = QgsVectorLayer(uri, self.LAYER_NAME, "memory")

        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("holding_id",    QVariant.String),
            QgsField("inbound_track", QVariant.Double),
            QgsField("turn",          QVariant.String),
            QgsField("ias_kt",        QVariant.Double),
            QgsField("alt_ft",        QVariant.Double),
            QgsField("isa_var",       QVariant.Double),
            QgsField("bank_deg",      QVariant.Double),
            QgsField("leg_min",       QVariant.Double),
            QgsField("tas_kt",        QVariant.Double),
            QgsField("radius_nm",     QVariant.Double),
            QgsField("leg_nm",        QVariant.Double),
        ])
        layer.updateFields()

        project.addMapLayer(layer, False)
        self._add_to_group(project, layer)
        self._apply_style(layer)

        log(f"HoldingLayerManager: created '{self.LAYER_NAME}'")
        return layer

    def add_holding(self, layer: QgsVectorLayer,
                    params: HoldingParameters, result: HoldingResult) -> None:
        """Append the 4 racetrack segments of one holding to *layer*."""
        holding_id = uuid.uuid4().hex[:8]
        attrs = [
            holding_id,
            params.inbound_track,
            params.turn,
            params.ias_kt,
            params.altitude_ft,
            params.isa_var,
            params.bank_deg,
            params.leg_min,
            result.tas_kt,
            result.radius_nm,
            result.leg_nm,
        ]

        pr = layer.dataProvider()
        features = []
        for seg_type, pts in result.segments:
            qpts = [QgsPoint(p.x, p.y) for p in pts]
            feat = QgsFeature(layer.fields())
            feat.setAttributes(attrs)
            if seg_type == 'arc':
                cs = QgsCircularString()
                cs.setPoints(qpts)
                feat.setGeometry(QgsGeometry(cs))
            else:
                feat.setGeometry(QgsGeometry.fromPolyline(qpts))
            features.append(feat)

        pr.addFeatures(features)
        layer.updateExtents()
        layer.triggerRepaint()
        log(f"HoldingLayerManager: added holding {holding_id} to '{self.LAYER_NAME}'")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add_to_group(self, project: QgsProject, layer: QgsVectorLayer) -> None:
        root = project.layerTreeRoot()
        group = root.findGroup(self.GROUP_NAME)
        if group is None:
            group = root.insertGroup(0, self.GROUP_NAME)
        group.addLayer(layer)

    def _apply_style(self, layer: QgsVectorLayer) -> None:
        try:
            from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer
            sym = QgsLineSymbol.createSimple({
                "color": "#FF00FF",
                "width": "0.7",
                "width_unit": "MM",
                "capstyle": "round",
                "joinstyle": "round",
            })
            layer.setRenderer(QgsSingleSymbolRenderer(sym))
        except Exception as exc:
            log(f"HoldingLayerManager: style failed: {exc}", "WARNING")
