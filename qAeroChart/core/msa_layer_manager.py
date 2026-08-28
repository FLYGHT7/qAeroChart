# -*- coding: utf-8 -*-
"""
MsaLayerManager — creates and manages the MSA sector map layers.

Two memory Polygon layers are managed: the persistent "MSA Sectors" layer
(accumulates every committed MSA figure in the current QGIS session, tagged
by ``Msa_Id``, the same accumulation pattern as ``HoldingLayerManager``) and a
"MSA_Preview" layer that is truncated and refilled on every live-preview
update instead of being removed/recreated.
"""
from __future__ import annotations

import uuid

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

from ..utils.logger import log
from ..utils.qt_compat import MsgLevel, QColor, QVariant
from .msa import MSASectorGeometry


class MsaLayerManager:
    GROUP_NAME = "MSA"
    LAYER_NAME = "MSA Sectors"
    PREVIEW_LAYER_NAME = "MSA_Preview"

    _FIELDS = [
        QgsField("Msa_Id", QVariant.String),
        QgsField("Sector", QVariant.Int),
        QgsField("Start_Brg", QVariant.Double),
        QgsField("End_Brg", QVariant.Double),
        QgsField("Brg_Type", QVariant.String),
        QgsField("Ref_North", QVariant.String),
        QgsField("Mag_Var", QVariant.Double),
        QgsField("Inner_NM", QVariant.Double),
        QgsField("Outer_NM", QVariant.Double),
        QgsField("Altitude", QVariant.Double),
        QgsField("Label", QVariant.String),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_layer(self, iface) -> QgsVectorLayer:
        """Return the shared 'MSA Sectors' layer, creating it if needed."""
        return self._get_or_create(iface, self.LAYER_NAME, is_preview=False, add_to_group=True)

    def get_or_create_preview_layer(self, iface) -> QgsVectorLayer:
        """Return the 'MSA_Preview' layer, creating it if needed."""
        return self._get_or_create(iface, self.PREVIEW_LAYER_NAME, is_preview=True, add_to_group=False)

    def add_sectors(
        self,
        layer: QgsVectorLayer,
        sector_geometries: list[MSASectorGeometry],
        *,
        brg_type_str: str,
        ref_north_str: str,
        mag_var_signed: float,
        msa_id: str | None = None,
    ) -> str:
        """Append every sector in *sector_geometries* to *layer* as one MSA figure."""
        msa_id = msa_id or uuid.uuid4().hex[:8]
        pr = layer.dataProvider()
        features = []
        for idx, sec_geom in enumerate(sector_geometries):
            sector = sec_geom.sector
            label = f"MSA {sector.altitude_ft:,.0f}"
            qpts = [QgsPointXY(x, y) for x, y in sec_geom.ring]
            geom = QgsGeometry.fromPolygonXY([qpts])
            if not geom.isGeosValid():
                fixed = geom.makeValid()
                if fixed.isEmpty():
                    log(
                        f"MsaLayerManager: sector {idx + 1} geometry invalid "
                        f"and makeValid() produced an empty result "
                        f"({geom.lastError()}); keeping original geometry",
                        "WARNING",
                    )
                else:
                    log(
                        f"MsaLayerManager: sector {idx + 1} geometry was "
                        f"invalid ({geom.lastError()}); fixed before commit",
                        "WARNING",
                    )
                    geom = fixed
            feat = QgsFeature(layer.fields())
            feat.setGeometry(geom)
            feat.setAttributes([
                msa_id,
                idx + 1,
                sector.start_brg,
                sector.end_brg,
                brg_type_str,
                ref_north_str,
                mag_var_signed,
                sector.inner_r_nm,
                sector.outer_r_nm,
                sector.altitude_ft,
                label,
            ])
            features.append(feat)

        pr.addFeatures(features)
        layer.updateExtents()
        layer.triggerRepaint()
        log(f"MsaLayerManager: added {len(features)} sector(s) (msa_id={msa_id}) to '{layer.name()}'")
        return msa_id

    def remove_sectors(self, layer: QgsVectorLayer, msa_id: str) -> None:
        """Delete all features tagged with *msa_id* from *layer* (mirrors
        ``HoldingLayerManager.remove_holding`` — lets a caller replace a
        previously committed MSA figure instead of piling up a duplicate)."""
        ids = [f.id() for f in layer.getFeatures() if f["Msa_Id"] == msa_id]
        if not ids:
            return
        layer.dataProvider().deleteFeatures(ids)
        layer.updateExtents()
        layer.triggerRepaint()
        log(f"MsaLayerManager: removed MSA figure {msa_id} from '{layer.name()}'")

    def replace_preview(
        self,
        layer: QgsVectorLayer,
        sector_geometries: list[MSASectorGeometry],
        *,
        brg_type_str: str,
        ref_north_str: str,
        mag_var_signed: float,
    ) -> None:
        """Clear and refill the preview layer in one step."""
        layer.dataProvider().truncate()
        if sector_geometries:
            self.add_sectors(
                layer, sector_geometries,
                brg_type_str=brg_type_str, ref_north_str=ref_north_str,
                mag_var_signed=mag_var_signed, msa_id="preview",
            )
        layer.updateExtents()
        layer.triggerRepaint()

    def clear_preview(self, layer: QgsVectorLayer) -> None:
        layer.dataProvider().truncate()
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schema_matches(self, layer: QgsVectorLayer) -> bool:
        """True if *layer*'s fields match ``_FIELDS`` in name and order.

        ``add_sectors`` writes attributes positionally, so a layer left over
        from an older schema (e.g. the original standalone script's 9-field
        preview layer, or an earlier plugin version) must not be silently
        reused — that produces attribute count/type mismatches at write time.
        """
        existing_names = [f.name() for f in layer.fields()]
        expected_names = [f.name() for f in self._FIELDS]
        return existing_names == expected_names

    def _get_or_create(
        self, iface, layer_name: str, *, is_preview: bool, add_to_group: bool
    ) -> QgsVectorLayer:
        project = QgsProject.instance()
        existing = project.mapLayersByName(layer_name)
        if existing:
            if self._schema_matches(existing[0]):
                return existing[0]
            if is_preview:
                # Preview layers are ephemeral scratch data — safe to discard
                # and recreate with the current schema.
                project.removeMapLayer(existing[0].id())
                log(f"MsaLayerManager: discarded stale-schema '{layer_name}'", "WARNING")
            else:
                # Never silently delete a user's committed MSA data — rename
                # the stale layer aside and create a fresh one instead.
                legacy_name = f"{layer_name} (legacy schema)"
                existing[0].setName(legacy_name)
                log(
                    f"MsaLayerManager: renamed stale-schema '{layer_name}' to "
                    f"'{legacy_name}'", "WARNING",
                )
                if iface is not None:
                    iface.messageBar().pushMessage(
                        "qAeroChart",
                        f"Existing '{layer_name}' layer had an outdated field "
                        f"layout and was renamed to '{legacy_name}'; a new "
                        f"'{layer_name}' layer was created.",
                        level=MsgLevel.Warning,
                        duration=6,
                    )

        crs = iface.mapCanvas().mapSettings().destinationCrs()
        uri = f"Polygon?crs={crs.authid()}"
        layer = QgsVectorLayer(uri, layer_name, "memory")

        pr = layer.dataProvider()
        pr.addAttributes(self._FIELDS)
        layer.updateFields()

        project.addMapLayer(layer, False)
        if add_to_group:
            self._add_to_group(project, layer)
        else:
            project.layerTreeRoot().addLayer(layer)
        self._apply_style(layer, is_preview=is_preview)

        log(f"MsaLayerManager: created '{layer_name}'")
        return layer

    def _add_to_group(self, project: QgsProject, layer: QgsVectorLayer) -> None:
        root = project.layerTreeRoot()
        group = root.findGroup(self.GROUP_NAME)
        if group is None:
            group = root.insertGroup(0, self.GROUP_NAME)
        group.addLayer(layer)

    def _apply_style(self, layer: QgsVectorLayer, *, is_preview: bool) -> None:
        try:
            if is_preview:
                symbol = QgsFillSymbol.createSimple({
                    "color": "255,0,127,30",
                    "outline_color": "#FF007F",
                    "outline_width": "0.5",
                    "outline_width_unit": "MM",
                    "outline_style": "dash",
                })
                label_color = QColor("#FF007F")
            else:
                symbol = QgsFillSymbol.createSimple({
                    "color": "0,0,0,0",
                    "outline_color": "#FF6600",
                    "outline_width": "0.6",
                    "outline_width_unit": "MM",
                    "outline_style": "solid",
                })
                label_color = QColor("#FF6600")
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            self._apply_labeling(layer, label_color)
        except Exception as exc:
            log(f"MsaLayerManager: style failed: {exc}", "WARNING")

    def _apply_labeling(self, layer: QgsVectorLayer, color: QColor) -> None:
        text_format = QgsTextFormat()
        text_format.setColor(color)
        text_format.setSize(9)

        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = "Label"
        label_settings.isExpression = False
        label_settings.enabled = True
        label_settings.setFormat(text_format)

        try:
            from qgis.core import Qgis
            label_settings.placement = Qgis.LabelPlacement.OverPoint
        except AttributeError:
            try:
                label_settings.placement = QgsPalLayerSettings.OverPoint
            except AttributeError:
                pass

        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        layer.setLabelsEnabled(True)
