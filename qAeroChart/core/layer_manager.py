# -*- coding: utf-8 -*-
"""
LayerManager - Manages memory layers for aeronautical profile charts

This module handles the creation, configuration, and management of memory layers
used for ICAO aeronautical profile charts. It creates 5 specialized layers following
ICAO Annex 14 and Doc 8697 standards.

v2.0: Integrated with ProfileChartGeometry for cartesian calculations.
"""
from __future__ import annotations

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
)

from .profile_chart_geometry import ProfileChartGeometry
from ..utils.logger import log, push_message
from ..utils.qt_compat import Qt, QVariant, QgsUnitTypes, FontBold


class LayerManager:
    """
    Manager for creating and handling aeronautical profile chart layers.

    Creates and manages 5 memory layers:
    1. profile_point_symbol - Point symbols for profile points (MAPt, FAF, IF, etc.)
    2. profile_carto_label - Cartographic labels for profile points
    3. profile_line - Profile line connecting points
    4. profile_dist - Distance markers and annotations
    5. profile_MOCA - Minimum Obstacle Clearance Altitude indicators

    All layers are organized under a "MAP 03 - Profile" group in the layer tree.
    """

    # Layer names constants
    LAYER_POINT_SYMBOL = "profile_point_symbol"
    LAYER_CARTO_LABEL = "profile_carto_label"
    LAYER_LINE = "profile_line"
    LAYER_MOCA = "profile_MOCA"
    LAYER_BASELINE = "profile_baseline"  # legacy; merged into profile_line (Issue #24)
    LAYER_VERTICAL_SCALE = "profile_vertical_scale"  # altitude scale bar (Issue #57)

    # Group name
    GROUP_NAME = "MAP 03 - Profile"

    def __init__(self, iface: object, crs: QgsCoordinateReferenceSystem | None = None) -> None:
        """
        Initialize the LayerManager.

        Args:
            iface (QgisInterface): The QGIS interface object
            crs (QgsCoordinateReferenceSystem): CRS for layers (default: project CRS)
        """
        self.iface = iface
        self.project = QgsProject.instance()

        # Store a fallback CRS if provided, but always prefer live project CRS at use time.
        # This prevents being stuck on a stale CRS after project changes.
        try:
            self.crs = crs if isinstance(crs, QgsCoordinateReferenceSystem) else None
        except Exception:
            self.crs = None

        # Debug flag (can be overridden by config in create_all_layers)
        self.debug = True

        # Dictionary to store created layers
        self.layers = {}

        # Group reference
        self.layer_group = None

        try:
            init_auth = (
                self.project.crs().authid()
                if self.project and self.project.crs().isValid()
                else (self.crs.authid() if self.crs else '')
            )
            log(f"LayerManager initialized with CRS: {init_auth}")
        except Exception:
            log("LayerManager initialized (CRS unknown)")

    def _dbg(self, msg: str):
        """
        Lightweight debug logger. Prints message when `self.debug` is True.

        Args:
            msg (str): Message to log.
        """
        try:
            if getattr(self, 'debug', False):
                log(msg, "DEBUG")
        except Exception:
            # Avoid any logging-related crashes
            pass

    def _crs_is_valid(self) -> bool:
        """Return True when the current project CRS is set and valid."""
        try:
            proj = self.project.crs() if self.project else None
            return bool(proj and proj.isValid())
        except Exception:
            return False

    def _crs_map_units(self) -> str:
        """Return the map-unit label: 'meters', 'feet', 'degrees', or 'unknown'."""
        try:
            proj = self.project.crs() if self.project else None
            if not (proj and proj.isValid()):
                return "unknown"
            raw = getattr(proj, 'mapUnits', lambda: None)()
            return {
                QgsUnitTypes.DistanceMeters: "meters",
                QgsUnitTypes.DistanceFeet: "feet",
                QgsUnitTypes.DistanceDegrees: "degrees",
                QgsUnitTypes.DistanceUnknownUnit: "unknown",
            }.get(raw, "unknown")
        except Exception:
            return "unknown"

    def _crs_is_geographic(self) -> bool:
        """Return True when the project CRS uses angular (degree) units."""
        try:
            proj = self.project.crs() if self.project else None
            if not (proj and proj.isValid()):
                return False
            # isGeographic() is the definitive check — available in all QGIS versions
            # and correctly distinguishes e.g. "WGS 84 / UTM zone 16N" (projected, False)
            # from "WGS 84" / EPSG:4326 (geographic, True).
            if hasattr(proj, 'isGeographic'):
                return bool(proj.isGeographic())
            # Fallback: unit-based check
            units = self._crs_map_units()
            if units == "degrees":
                return True
            if units in ("meters", "feet"):
                return False
            # Last resort: only flag the canonical geographic CRS
            auth = proj.authid() or ""
            return auth == "EPSG:4326"
        except Exception:
            return False

    def _crs_guard(self, enforce_block: bool = True, show_message: bool = True) -> bool:
        """
        Ensure the project CRS is projected (not geographic) before drawing.

        Args:
            enforce_block (bool): When True, return False to block operations on invalid CRS.
            show_message (bool): When True, show a message in QGIS message bar if available.

        Returns:
            bool: True when CRS is acceptable or checking not enforced; False when blocked.
        """
        try:
            valid = self._crs_is_valid()
            geographic = self._crs_is_geographic() if valid else False
            ok = valid and not geographic

            proj = self.project.crs() if (self.project and valid) else None
            auth = proj.authid() if proj else ""
            desc = proj.description() if proj else ""
            units = self._crs_map_units()
            self._dbg(
                f"CRS guard -> valid={valid} geographic={geographic} ok={ok}"
                f" authid={auth} units={units} desc='{desc}'"
            )

            if not ok and show_message:
                try:
                    if self.iface:
                        self.iface.messageBar().pushWarning(
                            "qAeroChart",
                            f"Projected CRS required. Current: {auth} ({desc})."
                            " Switch to a projected CRS (meters/feet)."
                        )
                except Exception:
                    pass

            return ok if enforce_block else True
        except Exception as e:
            self._dbg(f"CRS guard failed: {e}")
            return not enforce_block

    def _log(self, msg: str, level: str = "INFO"):
        """
        General logger with level. Uses QGIS message bar when available.

        Args:
            msg (str): Message text.
            level (str): One of "INFO", "WARN", "ERROR".
        """
        try:
            level_upper = (level or "INFO").upper()
            if self.iface:
                if level_upper == "ERROR":
                    self.iface.messageBar().pushCritical("qAeroChart", msg)
                elif level_upper == "WARN":
                    self.iface.messageBar().pushWarning("qAeroChart", msg)
                else:
                    push_message(self.iface, "qAeroChart", msg, duration=4)
            log(msg, level_upper)
        except Exception:
            try:
                log(msg, level)
            except Exception:
                pass

    def _assign_feature_id(self, feature, layer_key, id_tracker):
        """
        Helper to assign sequential IDs to features per layer.

        Args:
            feature (QgsFeature): Feature to update.
            layer_key (str): Layer identifier constant.
            id_tracker (dict): Mutable map storing the next id per layer.
        """
        try:
            if not feature or not feature.fields():
                return
            if feature.fields().indexOf("id") < 0:
                return
            next_value = id_tracker.get(layer_key, 1)
            feature.setAttribute("id", next_value)
            id_tracker[layer_key] = next_value + 1
        except Exception as e:
            self._dbg(f"Could not assign id for layer {layer_key}: {e}")

    def _assign_layer_feature_id(self, layer, feature):
        """
        Assign a sequential integer id for single-feature additions outside batch mode.
        Uses the current maximum 'id' value in the target layer to avoid duplicates.
        """
        try:
            if not layer or not feature:
                return
            idx = layer.fields().indexOf("id")
            if idx < 0:
                return
            provider = layer.dataProvider()
            max_val = provider.maximumValue(idx) if provider else None
            next_val = 1
            if max_val not in (None, ''):
                try:
                    next_val = int(max_val) + 1
                except (TypeError, ValueError):
                    next_val = int(float(max_val)) + 1
            feature.setAttribute("id", next_val)
        except Exception as e:
            self._dbg(f"Could not assign single feature id: {e}")

    def _create_memory_layer(self, geom_type: str, name: str, *, id_type=QVariant.Int) -> QgsVectorLayer:
        """Create a memory layer with the given geometry type and standard 'id' field.

        Args:
            geom_type (str): One of 'Point', 'LineString', 'Polygon'.
            name (str): Layer name to assign.
            id_type: QVariant type for 'id' field (default Int; String for some layers).

        Returns:
            QgsVectorLayer: Newly created memory layer with project CRS applied.
        """
        try:
            # Build URI like 'Point?crs=EPSG:XXXX'
            geom = geom_type.strip()
            if geom not in {"Point", "LineString", "Polygon"}:
                geom = "Point"
            # Prefer live project CRS
            proj_crs = self.project.crs() if self.project else QgsCoordinateReferenceSystem()
            crs_auth = proj_crs.authid() if proj_crs and proj_crs.isValid() else "EPSG:4326"
            uri = f"{geom}?crs={crs_auth}"
            print(f"[qAeroChart] Creating memory layer '{name}' uri='{uri}' id_type={id_type!r}")
            layer = QgsVectorLayer(uri, name, "memory")
            # Add standard 'id' field
            provider = layer.dataProvider()
            provider.addAttributes([QgsField("id", id_type)])
            layer.updateFields()
            # Ensure CRS is applied
            self._ensure_layer_crs(layer)
            print(f"[qAeroChart] Memory layer '{name}' created OK, valid={layer.isValid()}")
            return layer
        except Exception as e:
            print(f"[qAeroChart] ERROR in _create_memory_layer '{name}': {e}")
            self._log(f"Failed to create memory layer '{name}': {e}", level="ERROR")
            # Return a minimal valid point layer as fallback
            try:
                layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
                provider = layer.dataProvider()
                provider.addAttributes([QgsField("id", id_type)])
                layer.updateFields()
                print(f"[qAeroChart] Fallback layer '{name}' created OK")
                return layer
            except Exception as e2:
                print(f"[qAeroChart] Fallback layer '{name}' ALSO failed: {e2}")
                return None

    def _ensure_layer_crs(self, layer: QgsVectorLayer):
        """Apply the current project CRS to a layer if possible."""
        try:
            if not layer:
                return
            proj_crs = self.project.crs() if self.project else None
            if proj_crs and proj_crs.isValid():
                layer.setCrs(proj_crs)
        except Exception as e:
            self._dbg(f"Could not set layer CRS: {e}")

    def create_all_layers(self, config=None):
        """
        Create all 5 profile chart layers and organize them in a group.

        Args:
            config (dict): Optional configuration with style parameters

        Returns:
            dict: Dictionary with layer names as keys and QgsVectorLayer objects as values
        """
        # Configure debug mode
        try:
            if config and isinstance(config, dict):
                self.debug = bool(config.get('debug', True))
        except Exception:
            pass

        self._dbg("Starting create_all_layers()")
        print("[qAeroChart] create_all_layers() called")
        log("Creating all profile layers...")
        # Enforce projected CRS; allow override via style.allow_geographic
        allow_geo = False
        try:
            allow_geo = (
                bool(config.get('style', {}).get('allow_geographic', False))
                if isinstance(config, dict) else False
            )
        except Exception:
            allow_geo = False
        self._dbg(f"create_all_layers: allow_geographic={allow_geo}")
        # Diagnostic: print CRS details before guard
        try:
            proj_crs = self.project.crs() if self.project else None
            print(
                f"[qAeroChart][DIAG] CRS before guard:"
                f" authid={proj_crs.authid() if proj_crs else 'N/A'},"
                f" isValid={proj_crs.isValid() if proj_crs else 'N/A'},"
                f" isGeographic={proj_crs.isGeographic() if proj_crs else 'N/A'}"
            )
            raw_units = getattr(proj_crs, 'mapUnits', lambda: None)() if proj_crs else None
            print(
                f"[qAeroChart][DIAG] mapUnits raw={raw_units!r},"
                f" type={type(raw_units).__name__ if raw_units is not None else 'N/A'}"
            )
        except Exception as diag_e:
            print(f"[qAeroChart][DIAG] CRS diagnostic failed: {diag_e}")
        guard_result = self._crs_guard(enforce_block=(not allow_geo), show_message=True)
        print(f"[qAeroChart][DIAG] _crs_guard returned: {guard_result}")
        if not guard_result:
            self._log("Aborting layer creation due to geographic/invalid CRS", level="WARN")
            print("[qAeroChart][DIAG] ABORTING create_all_layers due to CRS guard failure!")
            return {}

        # Create group first
        self._create_layer_group()

        # Create each layer (baseline merged into profile_line per Issue #24)
        for _layer_key, _layer_factory in [
            (self.LAYER_POINT_SYMBOL, self._create_point_symbol_layer),
            (self.LAYER_CARTO_LABEL, self._create_carto_label_layer),
            (self.LAYER_LINE, self._create_line_layer),
            (self.LAYER_MOCA, self._create_moca_layer),
            (self.LAYER_VERTICAL_SCALE, self._create_vertical_scale_layer),
        ]:
            try:
                self.layers[_layer_key] = _layer_factory()
            except Exception as _e:
                print(f"[qAeroChart] Layer '{_layer_key}' creation FAILED: {_e}")
                self._log(f"Failed to create layer '{_layer_key}': {_e}", level="ERROR")
                log(f"qAeroChart layer creation error for '{_layer_key}': {_e}", "ERROR")

        # Emit validity and field diagnostics
        for k, lyr in self.layers.items():
            try:
                self._dbg(
                    f"Layer '{k}': valid={lyr.isValid()}"
                    f" CRS={lyr.crs().authid()} fields={[f.name() for f in lyr.fields()]}"
                )
            except Exception as e:
                self._log(f"Diag failed for layer '{k}': {e}", level="WARN")

        print(f"[qAeroChart] Layers in self.layers after creation: {list(self.layers.keys())}")
        # Add layers to group and apply styles
        self._add_layers_to_group(config)

        log(f"Created {len(self.layers)} layers in group '{self.GROUP_NAME}'")
        print(f"[qAeroChart] create_all_layers() done — {len(self.layers)} layers added to group")
        self._dbg("Finished create_all_layers()")

        return self.layers

    def _find_group(self):
        """Return a *fresh* reference to this manager's layer-tree group.

        In QGIS 4 / SIP6 the Python wrapper returned by ``addGroup()`` can
        become stale (``not wrapper`` evaluates True) even though the C++
        object is alive.  Always re-finding by name avoids that trap.
        """
        try:
            root = self.project.layerTreeRoot()
            return root.findGroup(self.GROUP_NAME) if root else None
        except Exception:
            return None

    def _create_layer_group(self):
        """Create or get the layer group for profile charts."""
        root = self.project.layerTreeRoot()
        print(f"[qAeroChart][GROUP] _create_layer_group: root={root!r}, GROUP_NAME='{self.GROUP_NAME}'")

        # Check if group already exists
        existing_group = root.findGroup(self.GROUP_NAME)
        print(
            f"[qAeroChart][GROUP] findGroup returned: {existing_group!r},"
            f" bool={bool(existing_group) if existing_group is not None else 'is-None'}"
        )

        # SIP6 FIX: QgsLayerTreeGroup.__bool__() returns False for valid
        # objects in QGIS 4.  Always use 'is not None' instead of truthiness.
        if existing_group is not None:
            self.layer_group = existing_group
            log(f"Using existing group '{self.GROUP_NAME}'")
            print("[qAeroChart][GROUP] Reusing existing group")
        else:
            new_group = root.addGroup(self.GROUP_NAME)
            print(f"[qAeroChart][GROUP] addGroup returned: {new_group!r}")
            # Re-find immediately: the pointer returned by addGroup() can
            # become a dead SIP6 wrapper before we next use it.
            self.layer_group = root.findGroup(self.GROUP_NAME)
            print(f"[qAeroChart][GROUP] Re-find after addGroup: {self.layer_group!r}")
            log(f"Created new group '{self.GROUP_NAME}'")
        try:
            self._dbg(f"Group '{self.GROUP_NAME}' child count: {len(self.layer_group.children())}")
        except Exception:
            pass

        # Respect user layer tree order (Issue #11): do not auto-reorder/move group

    def _create_point_symbol_layer(self):
        """
        Create the profile_point_symbol layer for point symbols.

        Fields:
        - point_name: Name/identifier (MAPt, FAF, IF, etc.)
        - point_type: Type of point (fix, navaid, threshold, etc.)
        - distance: Distance from reference point (NM)
        - elevation: Elevation above MSL (ft)
        - notes: Additional notes

        Returns:
            QgsVectorLayer: The created layer
        """
        # Create memory layer
        layer = self._create_memory_layer('Point', self.LAYER_POINT_SYMBOL)

        # Add fields
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("point_name", QVariant.String, len=50),
            QgsField("point_type", QVariant.String, len=30),
            QgsField("distance", QVariant.Double),
            QgsField("elevation", QVariant.Double),
            QgsField("notes", QVariant.String, len=255)
        ])
        layer.updateFields()

        log(f"Created layer '{self.LAYER_POINT_SYMBOL}' with {layer.fields().count()} fields")

        return layer

    def _create_carto_label_layer(self):
        """
        Create the profile_carto_label layer for cartographic labels.

        Fields (Issue #25 unified schema):
        - id (string)
        - txt_label (string)      [prev: label_text]
        - txt_type (string)       [prev: label_type]
        - bold (bool)
        - html (bool)
        - font_size (int)
        - txt_rotation (double)   [prev: rotation]
        - txt_justified (string)
        - mask (bool)

        Returns:
            QgsVectorLayer: The created layer
        """
        layer = self._create_memory_layer('Point', self.LAYER_CARTO_LABEL, id_type=QVariant.String)

        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("txt_label", QVariant.String, len=100),
            QgsField("txt_type", QVariant.String, len=30),
            QgsField("bold", QVariant.Bool),
            QgsField("html", QVariant.Bool),
            QgsField("font_size", QVariant.Int),
            QgsField("txt_rotation", QVariant.Double),
            QgsField("txt_justified", QVariant.String, len=20),
            QgsField("mask", QVariant.Bool)
        ])
        layer.updateFields()

        log(f"Created layer '{self.LAYER_CARTO_LABEL}' with {layer.fields().count()} fields")

        return layer

    def _create_line_layer(self):
        """
        Create the profile_line layer for the main profile line.

        Fields:
        - line_type: Type of line (profile, approach, etc.)
        - segment_name: Name of the segment
        - gradient: Gradient/slope of the segment

        Returns:
            QgsVectorLayer: The created layer
        """
        # Unified schema for merged line layer (#40): id (string), symbol, txt_label, remarks
        layer = self._create_memory_layer('LineString', self.LAYER_LINE, id_type=QVariant.String)

        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("symbol", QVariant.String, len=30),
            QgsField("txt_label", QVariant.String, len=80),
            QgsField("remarks", QVariant.String, len=80)
        ])
        layer.updateFields()

        log(f"Created layer '{self.LAYER_LINE}' with {layer.fields().count()} fields")

        return layer

    # Removed separate key verticals/dist layers per #40 merge

    # _create_dist_layer removed per #40 (distance markers merged into profile_line)

    def _create_vertical_scale_layer(self) -> QgsVectorLayer:
        """Create the profile_vertical_scale layer for the altitude scale bar (Issue #57)."""
        layer = self._create_memory_layer('LineString', self.LAYER_VERTICAL_SCALE)
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("symbol", QVariant.String, len=25),
        ])
        layer.updateFields()
        log(f"Created layer '{self.LAYER_VERTICAL_SCALE}' with {layer.fields().count()} fields")
        return layer

    def _create_moca_layer(self):
        """
        Create the profile_MOCA layer for Minimum Obstacle Clearance Altitude.

        Uses Polygon geometry to display MOCA areas with diagonal hatching.

        Fields:
        - moca: MOCA value (ft)
        - segment_name: Associated segment
        - clearance: Clearance above obstacles (ft)

        Returns:
            QgsVectorLayer: The created layer
        """
        layer = self._create_memory_layer('Polygon', self.LAYER_MOCA)

        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("moca", QVariant.Double),
            QgsField("segment_name", QVariant.String, len=50),
            QgsField("clearance", QVariant.Double)
        ])
        layer.updateFields()

        log(f"Created layer '{self.LAYER_MOCA}' with {layer.fields().count()} fields")

        return layer

    def _add_layers_to_group(self, config=None):
        """
        Add all created layers to the layer group and apply styles.

        Args:
            config (dict): Optional configuration with style parameters
        """
        # In QGIS 4/SIP6 the stored wrapper can go stale; always re-find.
        print(f"[qAeroChart][GROUP] _add_layers_to_group ENTER, self.layer_group={self.layer_group!r}")
        group = self._find_group()
        print(f"[qAeroChart][GROUP] _find_group() returned: {group!r}")
        # SIP6 FIX: use 'is not None' — bool(QgsLayerTreeGroup) returns False
        if group is not None:
            self.layer_group = group
        if self.layer_group is None:
            # Group genuinely not found — re-create.
            print("[qAeroChart][GROUP] WARNING: group is None! Attempting re-creation...")
            log("Layer group not found, re-creating", "WARNING")
            try:
                self._create_layer_group()
                group = self._find_group()
                if group is not None:
                    self.layer_group = group
                    print(f"[qAeroChart][GROUP] Re-created group: {self.layer_group!r}")
            except Exception as _gc_err:
                print(f"[qAeroChart][GROUP] Re-creation failed: {_gc_err}")
        if self.layer_group is None:
            print("[qAeroChart][GROUP] FATAL: Cannot find or create layer group — aborting")
            log("Layer group not found after re-creation attempt", "ERROR")
            return

        # Add layers to project and group in specific order
        # Order layers so the profile line is above MOCA for visibility
        layer_order = [
            self.LAYER_CARTO_LABEL,
            self.LAYER_POINT_SYMBOL,
            self.LAYER_LINE,
            self.LAYER_MOCA,
            self.LAYER_VERTICAL_SCALE,
        ]

        print(
            f"[qAeroChart][DIAG] _add_layers_to_group:"
            f" layer_group={self.layer_group!r}, layers_keys={list(self.layers.keys())}"
        )
        for layer_name in layer_order:
            if layer_name in self.layers:
                layer = self.layers[layer_name]
                print(
                    f"[qAeroChart][DIAG] Processing '{layer_name}':"
                    f" type={type(layer).__name__}, valid={layer.isValid()}, id={layer.id()}"
                )
                # Add to project
                # Ensure CRS before adding (belt-and-suspenders)
                self._ensure_layer_crs(layer)
                # Use the returned reference: in QGIS 4 / PyQt6, the original
                # Python wrapper may become stale after C++ takes ownership.
                registered = self.project.addMapLayer(layer, False)
                print(
                    f"[qAeroChart][DIAG] addMapLayer('{layer_name}') returned:"
                    f" {type(registered).__name__ if registered else None},"
                    f" same_obj={registered is layer}"
                )
                if registered is None:
                    print(f"[qAeroChart][DIAG] WARNING: addMapLayer returned None for '{layer_name}'")
                    continue
                # Update internal dict so downstream code uses the live reference
                self.layers[layer_name] = registered
                # Re-find group each iteration: SIP6 wrappers can go stale
                # after addMapLayer / addLayer operations.
                group = self._find_group()
                if group is not None:
                    self.layer_group = group
                # Add to group using the registered reference
                tree_layer = self.layer_group.addLayer(registered)
                print(f"[qAeroChart][DIAG] addLayer('{layer_name}') returned tree_layer={tree_layer!r}")
                log(f"Added '{layer_name}' to group")
                try:
                    ext = registered.extent()
                    bbox = [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()]
                    self._dbg(
                        f"  -> layer '{layer_name}' valid={registered.isValid()}"
                        f" count={registered.featureCount()} extent={bbox}"
                    )
                except Exception:
                    pass
            else:
                print(f"[qAeroChart][DIAG] '{layer_name}' NOT in self.layers, skipping")

        # Final group check (re-find for fresh reference)
        group = self._find_group()
        if group is not None:
            self.layer_group = group
        print(
            "[qAeroChart][DIAG] After adding all layers: group children count="
            f"{len(self.layer_group.children()) if self.layer_group is not None else 'N/A'}"
        )
        try:
            for child in (self.layer_group.children() if self.layer_group is not None else []):
                print(f"[qAeroChart][DIAG]   child: {child.name()}, type={type(child).__name__}")
        except Exception:
            pass
        # Check project registry
        all_map_layers = self.project.mapLayers()
        print(f"[qAeroChart][DIAG] Project mapLayers count={len(all_map_layers)}")
        for lid, lyr in all_map_layers.items():
            if 'profile' in lyr.name().lower():
                print(f"[qAeroChart][DIAG]   registry: id={lid}, name={lyr.name()}, valid={lyr.isValid()}")

        # Apply basic styles to make features visible
        print("[qAeroChart][DIAG] About to call _apply_basic_styles()...")
        try:
            self._apply_basic_styles(config)
            print("[qAeroChart][DIAG] _apply_basic_styles() returned without error")
        except Exception as _style_err:
            import traceback
            print(f"[qAeroChart][DIAG] _apply_basic_styles() RAISED: {_style_err}")
            traceback.print_exc()

        # Move group to the top again (after new nodes were inserted)
        try:
            self._create_layer_group()  # will reuse existing and perform the move-to-top safety
        except Exception:
            pass

        # WYSIWYG request (Issue #11): Disable any custom render ordering so the layer panel order controls drawing.
        try:
            root = self.project.layerTreeRoot()
            if hasattr(root, 'hasCustomLayerOrder') and root.hasCustomLayerOrder():
                root.setHasCustomLayerOrder(False)
                self._dbg("Disabled custom layer order (WYSIWYG rendering order)")
        except Exception as e:
            self._log(f"Could not disable custom layer order: {e}", level="WARN")

    def _apply_basic_styles(self, config=None):
        """
        Apply basic symbology to layers to make them visible.

        Each styling section is wrapped in try/except so that a failure in one
        layer (e.g. due to Qt6 strict-enum changes) does not prevent the
        remaining layers from being styled and does not abort the caller
        (create_all_layers -> populate_layers_from_config chain).

        Args:
            config (dict): Optional configuration with style parameters
        """
        from qgis.core import (
            QgsSymbol,
            QgsSimpleLineSymbolLayer,
            QgsTextFormat,
            QgsPalLayerSettings,
            QgsVectorLayerSimpleLabeling,
            QgsLineSymbol,
            QgsSingleSymbolRenderer,
            QgsNullSymbolRenderer,
            QgsProperty,
            Qgis,
        )
        from qgis.PyQt.QtGui import QColor, QFont
        import traceback as _tb

        print("[qAeroChart][STYLES] _apply_basic_styles() ENTER")

        # Minimal, fixed styling (Issue #9)
        moca_border_width = 1.0
        point_size = 5.0
        line_color = '#000000'
        moca_hatch = '#000000'

        # ---- PROFILE_LINE ----
        line_layer = self.layers.get(self.LAYER_LINE)
        if line_layer:
            try:
                print(
                    f"[qAeroChart][STYLES] Styling PROFILE_LINE:"
                    f" valid={line_layer.isValid()}, renderer={line_layer.renderer()!r}"
                )
                simple = QgsSimpleLineSymbolLayer()
                simple.setColor(QColor(line_color))
                try:
                    simple.setCapStyle(Qt.FlatCap)
                    simple.setJoinStyle(Qt.MiterJoin)
                except Exception as cap_e:
                    print(f"[qAeroChart][STYLES]   setCapStyle/setJoinStyle skipped: {cap_e}")
                simple.setWidth(0.5)
                simple.setWidthUnit(QgsUnitTypes.RenderMillimeters)
                # FIX: changeSymbolLayer(0) replaces the default sub-layer
                # instead of appendSymbolLayer which created TWO sub-layers.
                sym = QgsLineSymbol()
                print(f"[qAeroChart][STYLES]   QgsLineSymbol default sub-layers: {sym.symbolLayerCount()}")
                sym.changeSymbolLayer(0, simple)
                print(f"[qAeroChart][STYLES]   After changeSymbolLayer(0): {sym.symbolLayerCount()} sub-layers")
                line_layer.setRenderer(QgsSingleSymbolRenderer(sym))
                line_layer.triggerRepaint()
                print("[qAeroChart][STYLES]   PROFILE_LINE styled OK")
                log("Applied single-symbol style to profile_line (0.5mm)")
            except Exception as e:
                print(f"[qAeroChart][STYLES] ERROR styling PROFILE_LINE: {e}")
                _tb.print_exc()
                log(f"PROFILE_LINE styling failed: {e}", "ERROR")

        # ---- PROFILE_POINT_SYMBOL ----
        point_layer = self.layers.get(self.LAYER_POINT_SYMBOL)
        if point_layer:
            try:
                print(
                    f"[qAeroChart][STYLES] Styling PROFILE_POINT_SYMBOL:"
                    f" valid={point_layer.isValid()}, geomType={point_layer.geometryType()!r}"
                )
                symbol = QgsSymbol.defaultSymbol(point_layer.geometryType())
                print(f"[qAeroChart][STYLES]   defaultSymbol: {symbol!r}")
                symbol.setColor(QColor(255, 0, 0))  # Red
                symbol.setSize(point_size)
                symbol.setSizeUnit(QgsUnitTypes.RenderMillimeters)
                # FIX: null-check renderer before calling setSymbol
                renderer = point_layer.renderer()
                print(f"[qAeroChart][STYLES]   point_layer.renderer() = {renderer!r}")
                if renderer is not None:
                    renderer.setSymbol(symbol)
                else:
                    print("[qAeroChart][STYLES]   WARNING: renderer is None - creating new renderer")
                    point_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                point_layer.triggerRepaint()
                print("[qAeroChart][STYLES]   PROFILE_POINT_SYMBOL styled OK")
                log("Applied style to profile_point_symbol (visible=True)")
            except Exception as e:
                print(f"[qAeroChart][STYLES] ERROR styling PROFILE_POINT_SYMBOL: {e}")
                _tb.print_exc()
                log(f"PROFILE_POINT_SYMBOL styling failed: {e}", "ERROR")

        # PROFILE_DIST merged into PROFILE_LINE per #40

        # ---- PROFILE_MOCA ----
        moca_layer = self.layers.get(self.LAYER_MOCA)
        if moca_layer:
            try:
                from qgis.core import QgsFillSymbol, QgsLinePatternFillSymbolLayer
                print(
                    f"[qAeroChart][STYLES] Styling PROFILE_MOCA:"
                    f" valid={moca_layer.isValid()}, renderer={moca_layer.renderer()!r}"
                )

                color_str = '0,0,0,0'
                symbol = QgsFillSymbol.createSimple({
                    'color': color_str,
                    'outline_color': moca_hatch,
                    'outline_width': str(moca_border_width),
                    'outline_width_unit': 'MM',
                    'outline_style': 'solid'
                })
                print(f"[qAeroChart][STYLES]   MOCA fill created with {symbol.symbolLayerCount()} sub-layers")

                line_pattern = QgsLinePatternFillSymbolLayer()
                line_pattern.setDistance(1.6)
                line_pattern.setDistanceUnit(QgsUnitTypes.RenderMillimeters)
                line_pattern.setLineAngle(45)

                line_symbol = line_pattern.subSymbol()
                if line_symbol:
                    line_symbol.setColor(QColor(moca_hatch))
                    line_symbol.setWidth(0.4)
                    line_symbol.setWidthUnit(QgsUnitTypes.RenderMillimeters)

                # FIX: replace the default sub-layer instead of appending a second one
                if symbol.symbolLayerCount() > 0:
                    symbol.changeSymbolLayer(0, line_pattern)
                    print("[qAeroChart][STYLES]   MOCA: replaced default sub-layer with line_pattern")
                else:
                    symbol.appendSymbolLayer(line_pattern)
                    print("[qAeroChart][STYLES]   MOCA: appended line_pattern (no default)")

                # FIX: null-check renderer
                renderer = moca_layer.renderer()
                print(f"[qAeroChart][STYLES]   moca_layer.renderer() = {renderer!r}")
                if renderer is not None:
                    renderer.setSymbol(symbol)
                else:
                    print("[qAeroChart][STYLES]   WARNING: moca renderer is None - creating new renderer")
                    moca_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                moca_layer.triggerRepaint()
                print("[qAeroChart][STYLES]   PROFILE_MOCA styled OK")
                log(f"Applied style to profile_MOCA (border: {moca_border_width}mm)")
            except Exception as e:
                print(f"[qAeroChart][STYLES] ERROR styling PROFILE_MOCA: {e}")
                _tb.print_exc()
                log(f"PROFILE_MOCA styling failed: {e}", "ERROR")
                # Fallback: simple solid fill so layer is at least visible
                try:
                    from qgis.core import QgsFillSymbol
                    fb_sym = QgsFillSymbol.createSimple({
                        'color': '100,100,255,150',
                        'outline_color': 'black',
                        'outline_width': str(moca_border_width),
                        'outline_width_unit': 'MM'
                    })
                    renderer = moca_layer.renderer()
                    if renderer is not None:
                        renderer.setSymbol(fb_sym)
                    else:
                        moca_layer.setRenderer(QgsSingleSymbolRenderer(fb_sym))
                    moca_layer.triggerRepaint()
                    print("[qAeroChart][STYLES]   PROFILE_MOCA fallback applied")
                except Exception as fb_e:
                    print(f"[qAeroChart][STYLES]   PROFILE_MOCA fallback also failed: {fb_e}")

        # ---- CARTO_LABEL ----
        label_layer = self.layers.get(self.LAYER_CARTO_LABEL)
        if label_layer:
            try:
                print(f"[qAeroChart][STYLES] Styling CARTO_LABEL: valid={label_layer.isValid()}")
                try:
                    label_layer.setRenderer(QgsNullSymbolRenderer())
                    print("[qAeroChart][STYLES]   QgsNullSymbolRenderer set")
                except Exception as nr_e:
                    print(f"[qAeroChart][STYLES]   QgsNullSymbolRenderer failed: {nr_e}, using transparent fallback")
                    symbol = QgsSymbol.defaultSymbol(label_layer.geometryType())
                    symbol.setColor(QColor(0, 0, 0, 0))
                    symbol.setSize(0.01)
                    renderer = label_layer.renderer()
                    if renderer is not None:
                        renderer.setSymbol(symbol)
                    else:
                        label_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

                text_format = QgsTextFormat()
                text_format.setFont(QFont("Arial", 10, FontBold))
                text_format.setSize(10)
                text_format.setColor(QColor(0, 0, 0))

                from qgis.core import QgsTextBufferSettings
                buffer = QgsTextBufferSettings()
                buffer.setEnabled(True)
                buffer.setSize(1.0)
                buffer.setColor(QColor(255, 255, 255))
                text_format.setBuffer(buffer)

                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = 'txt_label'
                label_settings.enabled = True
                label_settings.setFormat(text_format)

                try:
                    label_settings.placement = Qgis.LabelPlacement.OverPoint
                except AttributeError:
                    try:
                        label_settings.placement = QgsPalLayerSettings.OverPoint
                    except AttributeError:
                        pass
                label_settings.yOffset = 0.0

                try:
                    _rot = getattr(QgsPalLayerSettings, 'Rotation', None)
                    if _rot is None:
                        _prop_enum = getattr(QgsPalLayerSettings, 'Property', None)
                        if _prop_enum is not None:
                            _rot = getattr(_prop_enum, 'LabelRotation', None)
                    if _rot is not None:
                        label_settings.setDataDefinedProperty(
                            _rot, QgsProperty.fromField('txt_rotation')
                        )
                        print(f"[qAeroChart][STYLES]   Label rotation property: {_rot!r}")
                except Exception as rot_e:
                    print(f"[qAeroChart][STYLES]   Label rotation skipped: {rot_e}")

                labeling = QgsVectorLayerSimpleLabeling(label_settings)
                label_layer.setLabeling(labeling)
                label_layer.setLabelsEnabled(True)
                print("[qAeroChart][STYLES]   CARTO_LABEL styled OK")
                log("Applied labeling to profile_carto_label (black text with white buffer)")
            except Exception as e:
                print(f"[qAeroChart][STYLES] ERROR styling CARTO_LABEL: {e}")
                _tb.print_exc()
                log(f"CARTO_LABEL styling failed: {e}", "ERROR")

        print("[qAeroChart][STYLES] _apply_basic_styles() EXIT")
        # KEY VERTICALS merged into PROFILE_LINE per #40

    def add_point_feature(self, point, point_name, point_type="fix",
                          distance=0.0, elevation=0.0, notes=""):
        """
        Add a point feature to the profile_point_symbol layer.

        Args:
            point (QgsPointXY): Point coordinates
            point_name (str): Name/identifier of the point
            point_type (str): Type of point (fix, navaid, threshold, etc.)
            distance (float): Distance from reference (NM)
            elevation (float): Elevation above MSL (ft)
            notes (str): Additional notes

        Returns:
            bool: True if feature was added successfully
        """
        layer = self.layers.get(self.LAYER_POINT_SYMBOL)
        if not layer:
            log("Point symbol layer not found", "ERROR")
            return False

        feature = QgsFeature()
        feature.setFields(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        # Set attributes by name to avoid index/order issues (preferred on issue-23)
        self._assign_layer_feature_id(layer, feature)
        feature.setAttribute("point_name", point_name)
        feature.setAttribute("point_type", point_type)
        feature.setAttribute("distance", float(distance))
        feature.setAttribute("elevation", float(elevation))
        feature.setAttribute("notes", notes)

        layer.startEditing()
        success = layer.addFeature(feature)
        layer.commitChanges()

        if success:
            layer.triggerRepaint()  # Force visual refresh
            log(f"Added point '{point_name}' at ({point.x():.2f}, {point.y():.2f})")

        return success

    def add_label_feature(self, point, label_text, label_type="point_name",
                          rotation=0.0, font_size=10, *, bold=False, html=False, txt_justified="", mask=False):
        """
        Add a label feature to the profile_carto_label layer.

        Args:
            point (QgsPointXY): Label position
            label_text (str): Text to display
            label_type (str): Type of label
            rotation (float): Text rotation angle
            font_size (int): Font size

        Returns:
            bool: True if feature was added successfully
        """
        layer = self.layers.get(self.LAYER_CARTO_LABEL)
        if not layer:
            log("Carto label layer not found", "ERROR")
            return False

        feature = QgsFeature()
        feature.setFields(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        # Set attributes by name to avoid index/order issues
        self._assign_layer_feature_id(layer, feature)
        # Unified carto label schema (Issue #25)
        feature.setAttribute("txt_label", label_text)
        feature.setAttribute("txt_type", label_type)
        feature.setAttribute("txt_rotation", float(rotation))
        feature.setAttribute("font_size", int(font_size))
        feature.setAttribute("bold", bool(bold))
        feature.setAttribute("html", bool(html))
        feature.setAttribute("txt_justified", txt_justified)
        feature.setAttribute("mask", bool(mask))

        layer.startEditing()
        success = layer.addFeature(feature)
        layer.commitChanges()

        if success:
            layer.triggerRepaint()  # Force visual refresh
            log(f"Added label '{label_text}' at ({point.x():.2f}, {point.y():.2f})")

        return success

    def add_line_feature(self, points, line_type="profile", segment_name="", gradient=0.0):
        """
        Add a line feature to the profile_line layer.

        Args:
            points (list): List of QgsPointXY defining the line
            line_type (str): Type of line
            segment_name (str): Name of the segment
            gradient (float): Gradient/slope

        Returns:
            bool: True if feature was added successfully
        """
        layer = self.layers.get(self.LAYER_LINE)
        if not layer:
            log("Line layer not found", "ERROR")
            return False

        feature = QgsFeature()
        feature.setFields(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        # Set attributes by name to avoid index/order issues
        self._assign_layer_feature_id(layer, feature)
        # Map legacy params to unified schema (merged layer #40)
        feature.setAttribute("symbol", str(line_type))
        feature.setAttribute("txt_label", str(segment_name))
        feature.setAttribute("remarks", "")

        layer.startEditing()
        success = layer.addFeature(feature)
        layer.commitChanges()

        if success:
            layer.triggerRepaint()  # Force visual refresh
            log(f"Added line segment '{segment_name}' with {len(points)} points")

        return success

    def clear_all_layers(self):
        """Clear all features from all managed layers."""
        for layer_name, layer in self.layers.items():
            if layer:
                layer.startEditing()
                layer.deleteFeatures(layer.allFeatureIds())
                layer.commitChanges()
                log(f"Cleared layer '{layer_name}'")

    def remove_all_layers(self):
        """Remove all managed layers from the project."""
        for layer_name, layer in self.layers.items():
            if layer:
                self.project.removeMapLayer(layer.id())
                log(f"Removed layer '{layer_name}'")

        # Remove group if empty — re-find to avoid stale SIP6 wrapper
        group = self._find_group()
        if group is not None:
            root = self.project.layerTreeRoot()
            if len(group.children()) == 0:
                root.removeChildNode(group)
                log(f"Removed empty group '{self.GROUP_NAME}'")

        self.layers.clear()
        self.layer_group = None

    def get_layer(self, layer_name):
        """
        Get a specific layer by name.

        Args:
            layer_name (str): Name of the layer

        Returns:
            QgsVectorLayer: The layer or None if not found
        """
        return self.layers.get(layer_name)

    def layer_exists(self, layer_name):
        """
        Check if a layer exists.

        Args:
            layer_name (str): Name of the layer

        Returns:
            bool: True if layer exists
        """
        return layer_name in self.layers and self.layers[layer_name] is not None

    # ------------------------------------------------------------------
    # Standalone vertical scale (Issue #57 full implementation)
    # ------------------------------------------------------------------

    def create_vertical_scale_run(
        self,
        name: str,
        basepoint_x: float,
        basepoint_y: float,
        angle: float,
        scale_denominator: float = 10000.0,
        offset: float = -50.0,
        tick_len: float = 15.0,
        m_max: int = 100,
        m_step: int = 25,
        ft_max: int = 300,
        ft_step: int = 50,
    ) -> tuple[object, object] | None:
        """Create a self-contained vertical scale on the map (branch-style).

        Each call creates a new layer group ``{name}`` containing:
        - ``{name} - Lines`` : LineString layer with all tick/rail geometry
        - ``{name} - Labels``: Point layer with QGIS text labels

        Returns ``(lines_layer, labels_layer)`` on success, or ``None`` on
        failure (missing QGIS environment).

        Parameters
        ----------
        name:            Display name for the scale and its layer group.
        basepoint_x/y:   Map-CRS coordinates of the scale origin.
        angle:           Azimuth (degrees) along which the scale axis runs.
        scale_denominator:
            1:n denominator.  VE = denominator / 1000 (10 000 → VE 10).
        offset:          Perpendicular offset from basepoint to rails (map m).
        tick_len:        Full tick length in map metres.
        m_max, m_step:   Metre range and step.
        ft_max, ft_step: Feet range and step.
        """
        try:
            from qgis.core import (
                QgsPoint,
                QgsPointXY,
                QgsGeometry,
                QgsFeature,
                QgsVectorLayer,
                QgsField,
                QgsProject as _QgsProject,
                QgsPalLayerSettings,
                QgsTextFormat,
                QgsTextBufferSettings,
                QgsVectorLayerSimpleLabeling,
                QgsNullSymbolRenderer,
                Qgis,
            )
        except ImportError:
            log("create_vertical_scale_run: QGIS not available", "ERROR")
            return None

        from .vertical_scale import vertical_scale_tick_offsets
        from ..utils.qt_compat import QFont, QColor, QVariant

        offsets = vertical_scale_tick_offsets(
            tick_length_m=tick_len,
            scale_denominator=scale_denominator,
            metre_max=m_max,
            metre_step=m_step,
            feet_max=ft_max,
            feet_step=ft_step,
        )

        half_sp = offsets["half_spacing"]
        small_len = tick_len * 0.45
        srid = self._get_srid()

        # ---- helper: resolve QgsPoint in map space ----
        origin = QgsPoint(basepoint_x, basepoint_y)
        # perpendicular offset → baseline
        base_centre = origin.project(abs(offset), angle + (90.0 if offset >= 0 else -90.0))
        base_right = base_centre.project(half_sp, angle + 90.0)   # metres side
        base_left = base_centre.project(half_sp, angle - 90.0)   # feet side

        # ---- create Lines layer ----
        lines_layer = QgsVectorLayer(
            f"LineString?crs={srid}", f"{name} - Lines", "memory"
        )
        lines_prov = lines_layer.dataProvider()
        lines_prov.addAttributes([QgsField("symbol", QVariant.String, len=30)])
        lines_layer.updateFields()

        feats: list[QgsFeature] = []
        _fid = [1]

        def add_line(pts: list, sym: str) -> None:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPolyline(pts))
            f.setAttributes([_fid[0], sym])
            _fid[0] += 1
            feats.append(f)

        # Main metre ticks (right rail)
        for along, _ in offsets["metre_bases"]:
            base_pt = base_right.project(along, angle)
            tip_pt = base_pt.project(tick_len, angle + 90.0)
            add_line([base_pt, tip_pt], "metre_tick")

        # Main feet ticks (left rail)
        for along, _ in offsets["feet_bases"]:
            base_pt = base_left.project(along, angle)
            tip_pt = base_pt.project(tick_len, angle - 90.0)
            add_line([base_pt, tip_pt], "feet_tick")

        # Mid-step metre ticks
        for along, _ in offsets["metre_small_ticks"]:
            base_pt = base_right.project(along, angle)
            tip_pt = base_pt.project(small_len, angle + 90.0)
            add_line([base_pt, tip_pt], "m_tick_small")

        # Mid-step feet ticks
        for along, _ in offsets["feet_small_ticks"]:
            base_pt = base_left.project(along, angle)
            tip_pt = base_pt.project(small_len, angle - 90.0)
            add_line([base_pt, tip_pt], "ft_tick_small")

        # Metre spine (right rail)
        m_pts = [base_right.project(a, angle) for a, _ in offsets["metre_bases"]]
        for i in range(len(m_pts) - 1):
            add_line([m_pts[i], m_pts[i + 1]], "scale_line_right")

        # Feet spine (left rail)
        f_pts = [base_left.project(a, angle) for a, _ in offsets["feet_bases"]]
        for i in range(len(f_pts) - 1):
            add_line([f_pts[i], f_pts[i + 1]], "scale_line_left")

        # Secondary rails
        if offsets["metre_small_ticks"]:
            sm_pts = [base_right.project(a, angle) for a, _ in offsets["metre_small_ticks"]]
            sm_tips = [p.project(small_len, angle + 90.0) for p in sm_pts]
            for i in range(len(sm_tips) - 1):
                add_line([sm_tips[i], sm_tips[i + 1]], "scale_line_right_secondary")
            sf_pts = [base_left.project(a, angle) for a, _ in offsets["feet_small_ticks"]]
            sf_tips = [p.project(small_len, angle - 90.0) for p in sf_pts]
            for i in range(len(sf_tips) - 1):
                add_line([sf_tips[i], sf_tips[i + 1]], "scale_line_left_secondary")

        # Bottom connector (feet base → metre base)
        add_line([base_left.project(0.0, angle), base_right.project(0.0, angle)], "bottom_connect")

        lines_prov.addFeatures(feats)
        lines_layer.updateExtents()

        # ---- force black symbology on lines layer (prevent random QGIS colour) ----
        try:
            from qgis.core import (
                QgsSimpleLineSymbolLayer as _SLL,
                QgsLineSymbol as _LS,
                QgsSingleSymbolRenderer as _SSR,
            )
            _sl = _SLL()
            _sl.setColor(QColor("black"))
            _sl.setWidth(0.25)
            _sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            _sym = _LS()
            _sym.changeSymbolLayer(0, _sl)
            lines_layer.setRenderer(_SSR(_sym))
        except Exception as _e:
            log(f"Could not set lines_layer symbology: {_e}", "WARNING")

        # ---- create Labels layer ----
        labels_layer = QgsVectorLayer(
            f"Point?crs={srid}", f"{name} - Labels", "memory"
        )
        lbl_prov = labels_layer.dataProvider()
        lbl_prov.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("txt_label", QVariant.String, len=50),
        ])
        labels_layer.updateFields()

        lbl_feats: list[QgsFeature] = []
        _lid = [1]

        def add_label(pt: QgsPoint, text: str) -> None:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
            f.setAttributes([_lid[0], text])
            _lid[0] += 1
            lbl_feats.append(f)

        _FT_TO_M = 0.3048
        _ve = scale_denominator / 1000.0

        # Metre value labels
        for v in range(0, m_max + 1, m_step):
            along = v * _ve
            base_pt = base_right.project(along, angle)
            tip_pt = base_pt.project(tick_len * 1.15, angle + 90.0)
            add_label(tip_pt, str(v))
        # "METERS" unit label
        last_m = base_right.project(m_max * _ve, angle)
        add_label(last_m.project(tick_len * 1.5, angle + 90.0), "METERS")

        # Feet value labels
        for v in range(0, ft_max + 1, ft_step):
            along = v * _FT_TO_M * _ve
            base_pt = base_left.project(along, angle)
            tip_pt = base_pt.project(tick_len * 1.15, angle - 90.0)
            add_label(tip_pt, str(v))
        # "FEET" unit label
        last_f = base_left.project(ft_max * _FT_TO_M * _ve, angle)
        add_label(last_f.project(tick_len * 1.5, angle - 90.0), "FEET")

        # Title labels (at bottom of scale)
        denom_str = f"1:{int(scale_denominator):,}".replace(",", " ")
        for i, txt in enumerate(["VERTICAL", "SCALE", denom_str]):
            pt = origin.project(i * tick_len * 0.6, angle - 90.0)
            add_label(pt, txt)

        lbl_prov.addFeatures(lbl_feats)
        labels_layer.updateExtents()

        # ---- configure labeling on labels_layer ----
        try:
            pal = QgsPalLayerSettings()
            pal.fieldName = "txt_label"
            try:
                pal.placement = Qgis.LabelPlacement.OverPoint
            except AttributeError:
                pal.placement = QgsPalLayerSettings.OverPoint
            fmt = QgsTextFormat()
            fmt.setFont(QFont("Segoe UI", 8))
            fmt.setSize(8.0)
            fmt.setColor(QColor("black"))
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.6)
            buf.setColor(QColor("white"))
            fmt.setBuffer(buf)
            pal.setFormat(fmt)
            labels_layer.setLabelsEnabled(True)
            labels_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            labels_layer.setRenderer(QgsNullSymbolRenderer())
        except Exception as e:
            log(f"Could not configure labeling for vertical scale: {e}", "WARNING")

        # ---- add both layers to a named group ----
        try:
            project = _QgsProject.instance()
            root = project.layerTreeRoot()
            group = root.findGroup(name)
            if group is None:
                root.insertGroup(0, name)  # insert at top (#88)
                group = root.findGroup(name)
            project.addMapLayer(lines_layer, False)
            project.addMapLayer(labels_layer, False)
            group.addLayer(lines_layer)
            group.addLayer(labels_layer)
            log(f"Vertical scale '{name}' created: "
                f"{len(feats)} line features, {len(lbl_feats)} labels")
        except Exception as e:
            log(f"Could not add vertical scale layers to project: {e}", "ERROR")
            return None

        return lines_layer, labels_layer

    # ------------------------------------------------------------------
    # Standalone horizontal scale (Issue #69)
    # ------------------------------------------------------------------

    def create_horizontal_scale_run(
        self,
        name: str,
        basepoint_x: float,
        basepoint_y: float,
        angle: float,
        offset: float = -50.0,
        tick_len: float = 15.0,
        metre_right: int = 2500,
        metre_left: int = 400,
        metre_right_step: int = 500,
        metre_left_step: int = 100,
        ft_right: int = 8000,
        ft_left: int = 1000,
        ft_right_step: int = 1000,
        ft_left_step: int = 100,
    ) -> "tuple[object, object] | None":
        """Create a self-contained horizontal scale bar on the map.

        Produces two layers in a named group:
          - ``{name} - Lines``: LineString with all tick/rail geometry
          - ``{name} - Labels``: Point layer with QGIS text labels

        The scale bar runs along *angle* from *basepoint*.  Positive values
        extend in the forward direction; negative values extend backward.
        The metre rail is above the axis (angle-90 perpendicular) and the
        feet rail is below (angle+90 perpendicular).

        Returns ``(lines_layer, labels_layer)`` on success, ``None`` on failure.
        """
        try:
            from qgis.core import (
                QgsPoint,
                QgsPointXY,
                QgsGeometry,
                QgsFeature,
                QgsVectorLayer,
                QgsField,
                QgsProject as _QgsProject,
                QgsPalLayerSettings,
                QgsTextFormat,
                QgsTextBufferSettings,
                QgsVectorLayerSimpleLabeling,
                QgsNullSymbolRenderer,
                Qgis,
            )
        except ImportError:
            log("create_horizontal_scale_run: QGIS not available", "ERROR")
            return None

        from .horizontal_scale import horizontal_scale_tick_offsets
        from ..utils.qt_compat import QFont, QColor, QVariant

        offsets = horizontal_scale_tick_offsets(
            metre_right=metre_right,
            metre_left=metre_left,
            metre_right_step=metre_right_step,
            metre_left_step=metre_left_step,
            ft_right=ft_right,
            ft_left=ft_left,
            ft_right_step=ft_right_step,
            ft_left_step=ft_left_step,
            tick_length_m=tick_len,
        )

        half_sp = offsets["half_spacing"]
        small_len = tick_len * 0.45
        srid = self._get_srid()

        origin = QgsPoint(basepoint_x, basepoint_y)
        # Perpendicular offset: move origin so the bar sits away from the feature
        base_centre = origin.project(abs(offset), angle + (90.0 if offset >= 0 else -90.0))
        # Two rails: metres above (angle-90 = "up"), feet below (angle+90 = "down")
        base_m = base_centre.project(half_sp, angle - 90.0)   # metres rail
        base_f = base_centre.project(half_sp, angle + 90.0)   # feet rail

        # ---- Lines layer ----
        lines_layer = QgsVectorLayer(
            f"LineString?crs={srid}", f"{name} - Lines", "memory"
        )
        lines_prov = lines_layer.dataProvider()
        lines_prov.addAttributes([QgsField("symbol", QVariant.String, len=30)])
        lines_layer.updateFields()

        feats: list[QgsFeature] = []
        _fid = [1]

        def add_line(pts: list, sym: str) -> None:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPolyline(pts))
            f.setAttributes([_fid[0], sym])
            _fid[0] += 1
            feats.append(f)

        # Helper: project a point along positive or negative direction
        def fwd(base: QgsPoint, dist: float) -> QgsPoint:
            return base.project(dist, angle)

        def bwd(base: QgsPoint, dist: float) -> QgsPoint:
            return base.project(dist, angle + 180.0)

        # ---- Metre rail (upper): ticks extend further upward (angle-90) ----
        m_pos_pts: list[QgsPoint] = []
        for along in offsets["m_pos_ticks"]:
            pt = fwd(base_m, along)
            tip = pt.project(tick_len, angle - 90.0)
            add_line([pt, tip], "m_tick_pos")
            m_pos_pts.append(pt)

        m_neg_pts: list[QgsPoint] = []
        for along in offsets["m_neg_ticks"]:
            pt = bwd(base_m, along)
            tip = pt.project(tick_len, angle - 90.0)
            add_line([pt, tip], "m_tick_neg")
            m_neg_pts.append(pt)

        # Metre minor ticks (positive side)
        for along in offsets["m_pos_minor"]:
            pt = fwd(base_m, along)
            tip = pt.project(small_len, angle - 90.0)
            add_line([pt, tip], "m_tick_pos_minor")

        # Metre minor ticks (negative side)
        for along in offsets["m_neg_minor"]:
            pt = bwd(base_m, along)
            tip = pt.project(small_len, angle - 90.0)
            add_line([pt, tip], "m_tick_neg_minor")

        # ---- Feet rail (lower): ticks extend downward (angle+90) ----
        ft_pos_pts: list[QgsPoint] = []
        for along in offsets["ft_pos_ticks"]:
            pt = fwd(base_f, along)
            tip = pt.project(tick_len, angle + 90.0)
            add_line([pt, tip], "ft_tick_pos")
            ft_pos_pts.append(pt)

        ft_neg_pts: list[QgsPoint] = []
        for along in offsets["ft_neg_ticks"]:
            pt = bwd(base_f, along)
            tip = pt.project(tick_len, angle + 90.0)
            add_line([pt, tip], "ft_tick_neg")
            ft_neg_pts.append(pt)

        # Feet minor ticks (positive side)
        for along in offsets["ft_pos_minor"]:
            pt = fwd(base_f, along)
            tip = pt.project(small_len, angle + 90.0)
            add_line([pt, tip], "ft_tick_pos_minor")

        # Feet minor ticks (negative side)
        for along in offsets["ft_neg_minor"]:
            pt = bwd(base_f, along)
            tip = pt.project(small_len, angle + 90.0)
            add_line([pt, tip], "ft_tick_neg_minor")

        # ---- Main rails (spine lines connecting tick bases) ----
        # Metre positive spine
        if len(m_pos_pts) >= 2:
            add_line(m_pos_pts, "m_spine_pos")
        # Metre negative spine (zero + neg points)
        if m_neg_pts:
            add_line([m_pos_pts[0]] + m_neg_pts, "m_spine_neg")
        # Feet positive spine
        if len(ft_pos_pts) >= 2:
            add_line(ft_pos_pts, "ft_spine_pos")
        # Feet negative spine
        if ft_neg_pts:
            add_line([ft_pos_pts[0]] + ft_neg_pts, "ft_spine_neg")

        # ---- Secondary inner rail between the two spines at zero ----
        zero_m = fwd(base_m, 0.0)
        zero_f = fwd(base_f, 0.0)
        add_line([zero_m, zero_f], "centre_connector")

        lines_prov.addFeatures(feats)
        lines_layer.updateExtents()

        # ---- Force black line symbology ----
        try:
            from qgis.core import (
                QgsSimpleLineSymbolLayer as _SLL,
                QgsLineSymbol as _LS,
                QgsSingleSymbolRenderer as _SSR,
            )
            _sl = _SLL()
            _sl.setColor(QColor("black"))
            _sl.setWidth(0.25)
            _sl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            _sym = _LS()
            _sym.changeSymbolLayer(0, _sl)
            lines_layer.setRenderer(_SSR(_sym))
        except Exception as _e:
            log(f"Could not set horizontal scale lines symbology: {_e}", "WARNING")

        # ---- Labels layer ----
        labels_layer = QgsVectorLayer(
            f"Point?crs={srid}", f"{name} - Labels", "memory"
        )
        lbl_prov = labels_layer.dataProvider()
        lbl_prov.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("txt_label", QVariant.String, len=50),
        ])
        labels_layer.updateFields()

        lbl_feats: list[QgsFeature] = []
        _lid = [1]

        def add_label(pt: QgsPoint, text: str) -> None:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
            f.setAttributes([_lid[0], text])
            _lid[0] += 1
            lbl_feats.append(f)

        _FT_TO_M = 0.3048
        lbl_offset = tick_len * 1.3

        # Metre value labels (above ticks → angle-90)
        for v in [0] + list(range(metre_right_step, metre_right + 1, metre_right_step)):
            pt = fwd(base_m, float(v))
            add_label(pt.project(lbl_offset, angle - 90.0), str(v))
        for v in range(metre_left_step, metre_left + 1, metre_left_step):
            pt = bwd(base_m, float(v))
            add_label(pt.project(lbl_offset, angle - 90.0), str(v))

        # "METRES" unit header — centred above the bar
        centre_along = metre_right / 2.0
        add_label(
            fwd(base_m, centre_along).project(lbl_offset * 1.8, angle - 90.0),
            "METRES",
        )

        # Feet value labels (below ticks → angle+90)
        ft_right_steps = [0] + list(range(ft_right_step, ft_right + 1, ft_right_step))
        for v in ft_right_steps:
            pt = fwd(base_f, v * _FT_TO_M)
            add_label(pt.project(lbl_offset, angle + 90.0), str(v))
        for v in range(ft_left_step, ft_left + 1, ft_left_step):
            pt = bwd(base_f, v * _FT_TO_M)
            add_label(pt.project(lbl_offset, angle + 90.0), str(v))

        # "FEET" unit footer
        add_label(
            fwd(base_f, (ft_right * _FT_TO_M) / 2.0).project(lbl_offset * 1.8, angle + 90.0),
            "FEET",
        )

        lbl_prov.addFeatures(lbl_feats)
        labels_layer.updateExtents()

        # ---- Configure labeling ----
        try:
            pal = QgsPalLayerSettings()
            pal.fieldName = "txt_label"
            try:
                pal.placement = Qgis.LabelPlacement.OverPoint
            except AttributeError:
                pal.placement = QgsPalLayerSettings.OverPoint
            fmt = QgsTextFormat()
            fmt.setFont(QFont("Segoe UI", 8))
            fmt.setSize(8.0)
            fmt.setColor(QColor("black"))
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            buf.setSize(0.6)
            buf.setColor(QColor("white"))
            fmt.setBuffer(buf)
            pal.setFormat(fmt)
            labels_layer.setLabelsEnabled(True)
            labels_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            labels_layer.setRenderer(QgsNullSymbolRenderer())
        except Exception as e:
            log(f"Could not configure labeling for horizontal scale: {e}", "WARNING")

        # ---- Add layers to project under named group ----
        try:
            project = _QgsProject.instance()
            root = project.layerTreeRoot()
            group = root.findGroup(name)
            if group is None:
                root.insertGroup(0, name)  # insert at top (#88)
                group = root.findGroup(name)
            project.addMapLayer(lines_layer, False)
            project.addMapLayer(labels_layer, False)
            group.addLayer(lines_layer)
            group.addLayer(labels_layer)
            log(f"Horizontal scale '{name}' created: "
                f"{len(feats)} line features, {len(lbl_feats)} labels")
        except Exception as e:
            log(f"Could not add horizontal scale layers to project: {e}", "ERROR")
            return None

        return lines_layer, labels_layer

    def _get_srid(self) -> str:
        """Return the project CRS auth-id or a safe fallback."""
        try:
            crs = self.project.crs() if self.project else None
            if crs and crs.isValid():
                return crs.authid()
        except Exception:
            pass
        return "EPSG:4326"

    def draw_vertical_scale(self, config):
        """Draw the double-sided altitude scale bar for the profile (Issue #57).

        Faithfully ports scripts/Vertical_Scale.py: places a scale bar at the
        start of the profile line, offset 50 m perpendicular, with metre ticks
        on one side and feet ticks on the other side.

        Uses QgsPoint (3-D) for .project() — same API as the original script.
        """
        from qgis.core import QgsPoint, QgsGeometry, QgsFeature  # local: only available in QGIS
        from .vertical_scale import vertical_scale_tick_offsets

        layer = self.layers.get(self.LAYER_VERTICAL_SCALE)
        if not layer:
            log("Vertical scale layer not found; skipping", "WARNING")
            return

        origin_data = config.get("origin_point") or config.get("reference_point", {})
        try:
            ox = float(origin_data["x"])
            oy = float(origin_data["y"])
        except (KeyError, TypeError, ValueError):
            log("Invalid origin point for vertical scale", "ERROR")
            return

        # Derive profile azimuth from the first and last computed profile points
        profile_points = config.get("profile_points", [])
        runway = config.get("runway", {})
        direction = runway.get("direction", "0")
        try:
            rwy_num = int("".join(ch for ch in direction if ch.isdigit())[:2] or 0)
        except ValueError:
            rwy_num = 0
        dir_sign = -1 if rwy_num and rwy_num <= 18 else 1

        if len(profile_points) >= 2:
            # Compute start/end in map coords to get actual line azimuth
            try:
                thr_ft = float(runway.get("thr_elevation", 0))
            except (ValueError, TypeError):
                thr_ft = 0.0
            geometry = ProfileChartGeometry(
                QgsPointXY(ox, oy),
                vertical_exaggeration=10.0,
                horizontal_direction=dir_sign,
            )
            first_p = profile_points[0]
            last_p = profile_points[-1]
            try:
                p_start = geometry.calculate_profile_point(
                    float(first_p.get("distance_nm", 0)),
                    float(first_p.get("elevation", thr_ft)) - thr_ft,
                )
                p_end = geometry.calculate_profile_point(
                    float(last_p.get("distance_nm", 0)),
                    float(last_p.get("elevation", thr_ft)) - thr_ft,
                )
                start_3d = QgsPoint(p_start.x(), p_start.y())
                end_3d = QgsPoint(p_end.x(), p_end.y())
                angle = start_3d.azimuth(end_3d)
            except (ValueError, TypeError, AttributeError):
                # Fallback: use runway heading
                angle = float(rwy_num * 10) if rwy_num else 90.0
        else:
            angle = float(rwy_num * 10) if rwy_num else 90.0

        offsets = vertical_scale_tick_offsets()
        start_3d = QgsPoint(ox, oy)
        # offset = -50 → project 50 m in the opposite perpendicular (same as original script)
        basepoint = start_3d.project(-50.0, angle - 90.0)

        dp = layer.dataProvider()
        features: list[QgsFeature] = []
        next_id = 1

        def _line(a: QgsPoint, b: QgsPoint, sym: str) -> QgsFeature:
            nonlocal next_id
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPolyline([a, b]))
            f.setAttributes([next_id, sym])
            next_id += 1
            return f

        # Metre baseline (connects all metre tick bases)
        m_base_pts = [
            basepoint.project(along, angle)
            for along, _ in offsets["metre_bases"]
        ]
        for i in range(len(m_base_pts) - 1):
            features.append(_line(m_base_pts[i], m_base_pts[i + 1], "metre_base"))

        # Metre ticks (right side: angle+90)
        for (along, _), base_pt in zip(offsets["metre_tips"], m_base_pts):
            tip = base_pt.project(offsets["metre_tips"][0][1], angle + 90.0)
            features.append(_line(base_pt, tip, "metre_tick"))

        # Feet ticks (left side: angle-90)
        for along, _ in offsets["feet_bases"]:
            f_base = basepoint.project(along, angle)
            f_tip = f_base.project(abs(offsets["feet_tips"][0][1]), angle - 90.0)
            features.append(_line(f_base, f_tip, "feet_tick"))

        # End connector between last metre tip and last feet tip
        last_m_base = m_base_pts[-1]
        last_m_tip = last_m_base.project(offsets["metre_tips"][-1][1], angle + 90.0)
        last_f_along, _ = offsets["feet_bases"][-1]
        last_f_base = basepoint.project(last_f_along, angle)
        last_f_tip = last_f_base.project(abs(offsets["feet_tips"][-1][1]), angle - 90.0)
        features.append(_line(last_m_tip, last_f_tip, "connector"))

        dp.addFeatures(features)
        layer.updateExtents()
        log(f"Vertical scale drawn ({len(features)} features, azimuth={angle:.1f}°)")

    def populate_layers_from_config(self, config):
        """
        Populate all layers with profile data from configuration.
        Uses ProfileChartGeometry for cartesian calculations.

        Args:
            config (dict): Configuration dictionary with origin_point, runway, and profile_points

        Returns:
            bool: True if successful
        """
        self._dbg("Starting populate_layers_from_config()")
        print(f"[qAeroChart][DIAG] populate_layers_from_config called, layers_keys={list(self.layers.keys())}")
        log("Populating layers from config v2.0...")
        self._dbg("PHASE: BEGIN population")
        log(f"Config keys: {list(config.keys())}")
        # Enforce projected CRS; block profile creation on geographic CRS (Issue #13). Show the message here only.
        # Respect same override inside population
        allow_geo = False
        try:
            allow_geo = (
                bool(config.get('style', {}).get('allow_geographic', False))
                if isinstance(config, dict) else False
            )
        except Exception:
            allow_geo = False
        self._dbg(f"populate_layers_from_config: allow_geographic={allow_geo}")
        if not self._crs_guard(enforce_block=(not allow_geo), show_message=True):
            log("Profile population blocked due to geographic/invalid CRS", "ERROR")
            return False

        # Extract origin point (v2.0 uses "origin_point", v1.0 uses "reference_point")
        origin_data = config.get('origin_point', config.get('reference_point', {}))
        if not origin_data or 'x' not in origin_data or 'y' not in origin_data:
            log("No origin point in configuration", "ERROR")
            log("origin_data = {origin_data}", "ERROR")
            return False

        origin_point = QgsPointXY(origin_data['x'], origin_data['y'])
        log(f"*** ORIGIN POINT SET TO: X={origin_point.x():.2f}, Y={origin_point.y():.2f} ***")

        # Extract profile points and runway parameters
        profile_points = config.get('profile_points', [])
        if not profile_points:
            log("No profile points in configuration", "WARNING")
            return False

        runway = config.get('runway', {})
        runway_length = float(runway.get('length', 0))
        tch = float(runway.get('tch_rdh', 0))
        # THR elevation in feet (used to convert absolute altitudes to THR-relative for drawing)
        try:
            thr_ft = float(runway.get('thr_elevation', 0))
        except Exception:
            thr_ft = 0.0
        self._dbg(f"Runway params -> length={runway_length}m, TCH={tch}m; profile_points={len(profile_points)}")

        # Initialize geometry calculator with vertical exaggeration (default 10x)
        ve = 10.0
        try:
            ve = float(config.get('style', {}).get('vertical_exaggeration', 10.0))
        except Exception:
            ve = 10.0
        # Determine horizontal drawing direction based on runway direction
        dir_text = str(runway.get('direction', '')).strip()
        try:
            # Extract numeric runway designator (first two digits)
            rwy_num = int(''.join(ch for ch in dir_text if ch.isdigit())[:2] or 0)
        except Exception:
            rwy_num = 0
        # If RWY direction <= 18 then draw rightâ†'left (dir_sign = -1), else leftâ†'right
        dir_sign = -1 if rwy_num and rwy_num <= 18 else 1
        self._dbg(
            f"Geometry setup -> origin=({origin_point.x():.3f},{origin_point.y():.3f})"
            f" VE={ve} dir_sign={dir_sign} (RWY='{dir_text}')"
        )
        geometry = ProfileChartGeometry(origin_point, vertical_exaggeration=ve, horizontal_direction=dir_sign)

        # BATCH OPERATIONS: Collect all features first, then add in bulk
        point_features = []
        label_features = []
        line_features = []
        moca_features = []

        # Per-layer ID counters (start at 1)
        next_id = {
            self.LAYER_POINT_SYMBOL: 1,
            self.LAYER_CARTO_LABEL: 1,
            self.LAYER_LINE: 1,
            self.LAYER_MOCA: 1,
        }

        # Get layer references
        layer_point = self.layers.get(self.LAYER_POINT_SYMBOL)
        layer_label = self.layers.get(self.LAYER_CARTO_LABEL)
        layer_line = self.layers.get(self.LAYER_LINE)
        layer_moca = self.layers.get(self.LAYER_MOCA)

        # Style cleanup (Issue #9): ORIGIN marker toggle removed; no origin feature added
        style = config.get('style', {}) if config else {}

        # 2. Prepare profile line
        self._dbg("PHASE: PROFILE LINE start")
        if len(profile_points) >= 2:
            log("=== CREATING PROFILE LINE ===")
            log(f"Number of profile points: {len(profile_points)}")

            # Use THR-relative elevation for drawing
            profile_points_rel = []
            for p in profile_points:
                try:
                    elev_ft = float(p.get('elevation_ft', 0))
                except Exception:
                    elev_ft = 0.0
                rel_elev = elev_ft - thr_ft
                q = dict(p)
                q['elevation_ft'] = rel_elev
                profile_points_rel.append(q)

            line_points = geometry.create_profile_line(profile_points_rel)

            log(f"Profile line returned {len(line_points) if line_points else 0} points")

            if line_points and layer_line:
                # Debug: Print all line points
                for i, pt in enumerate(line_points):
                    log(f"  Point {i}: X={pt.x():.2f}, Y={pt.y():.2f}")

                feat = QgsFeature()
                feat.setFields(layer_line.fields())
                geom = QgsGeometry.fromPolylineXY(line_points)

                # Validate geometry
                if geom.isGeosValid():
                    log("âœ… Profile line geometry is VALID")
                else:
                    log(f"âŒ Profile line geometry is INVALID: {geom.lastError()}")

                log(f"Geometry type: {geom.type()}, WKT length: {len(geom.asWkt())}")

                feat.setGeometry(geom)
                # Set attributes following unified profile_line schema (Issue #24/#40)
                feat.setAttribute("symbol", "profile")
                feat.setAttribute("txt_label", "Main Profile")
                feat.setAttribute("remarks", "")
                self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                line_features.append(feat)
                log("âœ… Profile line feature added to batch")
                # Slope labels per segment
                try:
                    sorted_pts = sorted(profile_points_rel, key=lambda p: float(p.get('distance_nm', 0)))
                    for i in range(len(sorted_pts)-1):
                        p1 = sorted_pts[i]
                        p2 = sorted_pts[i+1]
                        grad_percent = geometry.calculate_gradient(
                            (float(p1.get('distance_nm', 0)), float(p1.get('elevation_ft', 0))),
                            (float(p2.get('distance_nm', 0)), float(p2.get('elevation_ft', 0)))
                        )
                        import math
                        deg = math.degrees(math.atan(grad_percent/100.0))
                        text = f"{deg:.1f}Â° ({grad_percent:.1f}%)"
                        mid_nm = (float(p1.get('distance_nm', 0)) + float(p2.get('distance_nm', 0))) / 2.0
                        # Keep visual offset roughly constant despite VE
                        mid_ft_rel = (
                            (float(p1.get('elevation_ft', 0)) + float(p2.get('elevation_ft', 0))) / 2.0
                            + (80.0 / ve)
                        )
                        pos = geometry.calculate_profile_point(mid_nm, mid_ft_rel)
                        if layer_label:
                            lf = QgsFeature()
                            lf.setFields(layer_label.fields())
                            lf.setGeometry(QgsGeometry.fromPointXY(pos))
                            lf.setAttribute("txt_label", text)
                            lf.setAttribute("txt_type", "slope")
                            lf.setAttribute("txt_rotation", float(deg))
                            lf.setAttribute("font_size", 9)
                            self._assign_feature_id(lf, self.LAYER_CARTO_LABEL, next_id)
                            label_features.append(lf)
                except Exception as e:
                    log(f"Could not create slope labels: {e}", "WARNING")
            else:
                log(f"âŒ Profile line NOT created (line_points={bool(line_points)}, layer_line={bool(layer_line)})")
        else:
            log(f"âŒ Not enough points for profile line ({len(profile_points)} points)")
        self._dbg("PHASE: PROFILE LINE end")

        # 3. Prepare runway line
        self._dbg("PHASE: RUNWAY LINE start")
        if runway_length > 0:
            log("=== CREATING RUNWAY LINE ===")
            log(f"Runway length: {runway_length}m, TCH: {tch}m")

            runway_points = geometry.create_runway_line(runway_length, tch)

            if runway_points and layer_line:
                # Debug: Print runway points
                for i, pt in enumerate(runway_points):
                    log(f"  Runway point {i}: X={pt.x():.2f}, Y={pt.y():.2f}")

                feat = QgsFeature()
                feat.setFields(layer_line.fields())
                geom = QgsGeometry.fromPolylineXY(runway_points)

                # Validate geometry
                if geom.isGeosValid():
                    log("âœ… Runway geometry is VALID")
                else:
                    log(f"âŒ Runway geometry is INVALID: {geom.lastError()}")

                feat.setGeometry(geom)
                # Unified schema attributes
                feat.setAttribute("symbol", "runway")
                feat.setAttribute("txt_label", "Runway")
                feat.setAttribute("remarks", "")
                self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                line_features.append(feat)
                log("âœ… Runway line feature added to batch")
            else:
                log("âŒ Runway line NOT created")
        else:
            log("âš ï¸ Runway length is 0, skipping runway line")
        self._dbg("PHASE: RUNWAY LINE end")

        # 4. Prepare profile points with symbols and labels
        # Compute dynamic vertical height reference for key vertical lines (Issue #16)
        try:
            max_elevation_ft = max(float(p.get('elevation_ft', 0)) for p in profile_points)
        except Exception:
            max_elevation_ft = 0.0
        # Use THR-relative top for key vertical height
        max_elevation_ft_rel = max_elevation_ft - thr_ft
        vertical_extra_m = 1000.0  # required extra height above highest point (meters)
        vertical_top_ft = max_elevation_ft_rel + vertical_extra_m * ProfileChartGeometry.METERS_TO_FT
        self._dbg(
            f"Key verticals dynamic height -> max_elev_ft={max_elevation_ft:.2f} ft,"
            f" extra={vertical_extra_m} m, top_ft={vertical_top_ft:.2f} ft"
        )
        self._dbg("PHASE: POINTS & LABELS start")
        for point_data in profile_points:
            try:
                distance_nm = float(point_data.get('distance_nm', 0))
                elevation_ft = float(point_data.get('elevation_ft', 0))
                point_name = point_data.get('point_name', 'Unknown')
                moca_ft = point_data.get('moca_ft', '')
                notes = point_data.get('notes', '')

                # Calculate cartesian position
                # Draw using THR-relative elevation
                point_xy = geometry.calculate_profile_point(distance_nm, elevation_ft - thr_ft)

                # Prepare point symbol
                if layer_point:
                    feat = QgsFeature()
                    feat.setFields(layer_point.fields())
                    feat.setGeometry(QgsGeometry.fromPointXY(point_xy))
                    # Set attributes by name
                    self._assign_feature_id(feat, self.LAYER_POINT_SYMBOL, next_id)
                    feat.setAttribute("point_name", point_name)
                    feat.setAttribute("point_type", "fix")
                    feat.setAttribute("distance", float(distance_nm))
                    # Keep stored attribute as absolute MSL elevation
                    feat.setAttribute("elevation", float(elevation_ft))
                    feat.setAttribute("notes", notes)
                    point_features.append(feat)

                # Prepare label
                if layer_label:
                    feat = QgsFeature()
                    feat.setFields(layer_label.fields())
                    feat.setGeometry(QgsGeometry.fromPointXY(point_xy))
                    # Set attributes by name
                    self._assign_feature_id(feat, self.LAYER_CARTO_LABEL, next_id)
                    feat.setAttribute("txt_label", point_name)
                    feat.setAttribute("txt_type", "point_name")
                    feat.setAttribute("txt_rotation", 0.0)
                    feat.setAttribute("font_size", 10)
                    label_features.append(feat)

                # Add key verticals for all points (fix for #45):
                # Always draw a vertical from baseline to slightly above the max elevation,
                # so points are visually aligned and consistent across naming schemes.
                try:
                    bottom = geometry.calculate_profile_point(distance_nm, 0.0)
                    # Dynamic height: highest elevation (subject to VE) + 1000 m (not exaggerated)
                    top_at_max = geometry.calculate_profile_point(distance_nm, max_elevation_ft)
                    top = QgsPointXY(bottom.x(), top_at_max.y() + vertical_extra_m)
                    self._dbg(
                        f"Created key vertical for {point_name} at {distance_nm}NM:"
                        f" baseline_y={bottom.y():.2f}, top_y={top.y():.2f}"
                    )
                    if layer_line:
                        feat_v = QgsFeature()
                        feat_v.setFields(layer_line.fields())
                        feat_v.setGeometry(QgsGeometry.fromPolylineXY([bottom, top]))
                        feat_v.setAttribute("symbol", "key")
                        feat_v.setAttribute("txt_label", "")
                        feat_v.setAttribute("remarks", point_name)
                        self._assign_feature_id(feat_v, self.LAYER_LINE, next_id)
                        line_features.append(feat_v)
                except Exception as e:
                    log(f"could not create key vertical for {point_name}: {e}", "WARNING")

                log(f"Prepared point '{point_name}' at {distance_nm} NM / {elevation_ft} ft")

            except (ValueError, TypeError) as e:
                log(f"Could not process point {point_data.get('point_name', 'unknown')}: {e}", "WARNING")
                continue

        # 5. Prepare distance markers (tick line segments)
        self._dbg("PHASE: DISTANCE MARKERS start")
        if profile_points:
            # Axis length: prefer explicit axis_max_nm in style, else use max point distance
            max_distance_nm = max(float(p.get('distance_nm', 0)) for p in profile_points)
            try:
                axis_max = float(style.get('axis_max_nm', max_distance_nm))
                if axis_max > max_distance_nm:
                    max_distance_nm = axis_max
            except Exception:
                pass
            # Maintain visual sizes independent of VE by dividing base by VE
            # Allow tick visual height to be configurable in style; default 200 m visual
            try:
                tick_visual_height_m = float(style.get('tick_height_m', 200.0))
            except Exception:
                tick_visual_height_m = 200.0
            tick_height_m = tick_visual_height_m / ve
            markers = geometry.create_distance_markers(max_distance_nm, marker_height_m=tick_height_m)

            # Prepare baseline feature (horizontal at y=0 from 0..max distance)
            # Add baseline as a feature in profile_line (Issue #24)
            if layer_line:
                try:
                    p0 = geometry.calculate_profile_point(0.0, 0.0)
                    p1 = geometry.calculate_profile_point(max_distance_nm, 0.0)
                    feat = QgsFeature()
                    feat.setFields(layer_line.fields())
                    feat.setGeometry(QgsGeometry.fromPolylineXY([p0, p1]))
                    # Add baseline into profile_line with symbol-based styling
                    feat.setAttribute("symbol", "baseline")
                    feat.setAttribute("txt_label", "Baseline")
                    feat.setAttribute("remarks", "")
                    self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                    line_features.append(feat)
                except Exception as e:
                    log(f"Could not prepare baseline: {e}", "WARNING")

            # Merge distance markers into line layer per #40
            if layer_line:
                for marker in markers:
                    bottom, top = marker['geometry']
                    feat = QgsFeature()
                    feat.setFields(layer_line.fields())
                    feat.setGeometry(QgsGeometry.fromPolylineXY([bottom, top]))
                    feat.setAttribute("symbol", 'tick')
                    try:
                        feat.setAttribute("txt_label", str(marker.get('label', marker.get('distance'))))
                    except Exception:
                        feat.setAttribute("txt_label", str(marker.get('distance', '')))
                    feat.setAttribute("remarks", '')
                    self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                    line_features.append(feat)
                log(f"Prepared {len(markers)} distance markers (merged into profile_line)")

            # Axis labels under baseline at each NM
            if layer_label:
                try:
                    # Axis labels should be 50 m BELOW the end of the tick marks (Issue #15)
                    # We compute the label y from the same tick visual height used above,
                    # plus 50 m visual, then divide by VE
                    label_extra_offset_visual_m = 50.0
                    label_y_offset_m = -((tick_visual_height_m + label_extra_offset_visual_m) / ve)
                    # Convert real meters to feet because calculate_profile_point expects feet
                    label_y_offset_ft = label_y_offset_m * ProfileChartGeometry.METERS_TO_FT
                    for i in range(int(max_distance_nm) + 1):
                        pos = geometry.calculate_profile_point(i, label_y_offset_ft)
                        feat = QgsFeature()
                        feat.setFields(layer_label.fields())
                        feat.setGeometry(QgsGeometry.fromPointXY(pos))
                        label_txt = str(i)
                        feat.setAttribute("txt_label", label_txt)
                        feat.setAttribute("txt_type", "axis")
                        feat.setAttribute("txt_rotation", 0.0)
                        feat.setAttribute("font_size", 9)
                        self._assign_feature_id(feat, self.LAYER_CARTO_LABEL, next_id)
                        label_features.append(feat)
                    log(
                        f"Prepared {int(max_distance_nm)+1} axis labels at"
                        f" {label_y_offset_m:.2f} m below baseline (real),"
                        f" i.e., {label_y_offset_ft:.2f} ft"
                    )
                except Exception as e:
                    log(f"Could not create axis labels: {e}", "WARNING")
            # Grid layer removed (Issue #14): skipping creation of full-height vertical grid lines
        self._dbg("PHASE: DISTANCE MARKERS end")

    # 6. Prepare MOCA polygons
        log("=== CREATING MOCA HATCH AREAS ===")
        self._dbg("PHASE: MOCA/OCA start")
        # Client requirement (#36): OCA removal â†' ignore any OCA config; render MOCA only
        # Force OCA path off and prefer MOCA; keep variable defined to avoid NameError
        has_oca = False
        has_explicit_moca = False
        try:
            has_explicit_moca = bool(config.get('moca_segments'))
        except Exception:
            pass

        if has_oca:
            # Draw only OCA and skip all MOCA to avoid overlap
            try:
                oca_single = config.get('oca') if config else None
                if oca_single and self.layers.get(self.LAYER_MOCA):
                    d1 = float(oca_single.get('from_nm', 0))
                    d2 = float(oca_single.get('to_nm', 0))
                    hft = float(oca_single.get('oca_ft', oca_single.get('height_ft', 0)))
                    # Draw height relative to THR
                    poly = geometry.create_oca_box(d1, d2, hft - thr_ft)
                    feat = QgsFeature()
                    feat.setFields(layer_moca.fields())
                    feat.setGeometry(QgsGeometry.fromPolygonXY([poly]))
                    feat.setAttribute("moca", float(hft))
                    feat.setAttribute("segment_name", f"OCA {d1}-{d2}NM")
                    feat.setAttribute("clearance", 0.0)
                    self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                    moca_features.append(feat)
                    log(f"Added OCA polygon {d1}-{d2} NM @ {hft} ft")
            except Exception as e:
                log(f"OCA single processing failed: {e}", "WARNING")
            try:
                explicit_moca = config.get('moca_segments', [])
                if explicit_moca and layer_moca:
                    log(f"Processing explicit MOCA segments: {len(explicit_moca)}")
                    for seg in explicit_moca:
                        try:
                            d1 = float(seg.get('from_nm', seg.get('from', 0)))
                            d2 = float(seg.get('to_nm', seg.get('to', 0)))
                            hft = float(seg.get('oca_ft', seg.get('height_ft', 0)))
                            poly = geometry.create_oca_box(d1, d2, hft - thr_ft)
                            feat = QgsFeature()
                            feat.setFields(layer_moca.fields())
                            feat.setGeometry(QgsGeometry.fromPolygonXY([poly]))
                            feat.setAttribute("moca", float(hft))
                            feat.setAttribute("segment_name", f"{d1}-{d2}NM")
                            feat.setAttribute("clearance", 0.0)
                            self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                            moca_features.append(feat)
                        except Exception as e:
                            log(f"Skipping explicit MOCA segment {seg}: {e}", "WARNING")
            except Exception as e:
                log(f"explicit MOCA processing failed: {e}", "WARNING")
        else:
            # No OCA provided; choose between explicit MOCA (preferred) or per-point MOCA
            if has_explicit_moca:
                try:
                    explicit_moca = config.get('moca_segments', [])
                    if explicit_moca and layer_moca:
                        log(f"Processing explicit MOCA segments: {len(explicit_moca)}")
                        for seg in explicit_moca:
                            try:
                                d1 = float(seg.get('from_nm', seg.get('from', 0)))
                                d2 = float(seg.get('to_nm', seg.get('to', 0)))
                                hft = float(seg.get('moca_ft', seg.get('height_ft', 0)))
                                poly = geometry.create_oca_box(d1, d2, hft - thr_ft)
                                feat = QgsFeature()
                                feat.setFields(layer_moca.fields())
                                feat.setGeometry(QgsGeometry.fromPolygonXY([poly]))
                                # Set attributes by name and ensure id is assigned
                                feat.setAttribute("moca", float(hft))
                                feat.setAttribute("segment_name", f"{d1}-{d2}NM")
                                feat.setAttribute("clearance", 0.0)
                                self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                                moca_features.append(feat)
                            except Exception as e:
                                log(f"Skipping explicit MOCA segment {seg}: {e}", "WARNING")
                except Exception as e:
                    log(f"explicit MOCA processing failed: {e}", "WARNING")
            else:
                log(f"Processing {len(profile_points)-1} possible MOCA segments (per-point)")
                # fall back to per-point MOCA between consecutive points
                for i in range(len(profile_points) - 1):
                    point1 = profile_points[i]
                    point2 = profile_points[i + 1]
                    moca_ft = point1.get('moca_ft', '')
                    log(
                        f"Segment {i}: {point1.get('point_name', '')}"
                        f" → {point2.get('point_name', '')}, MOCA={moca_ft}"
                    )
                    if moca_ft and moca_ft.strip():
                        try:
                            moca_value = float(moca_ft)
                            dist1_nm = float(point1.get('distance_nm', 0))
                            dist2_nm = float(point2.get('distance_nm', 0))
                            log(f"  Creating MOCA: {dist1_nm}NM to {dist2_nm}NM at {moca_value}ft")
                            moca_polygon = geometry.create_oca_box(dist1_nm, dist2_nm, moca_value - thr_ft)
                            log(f"  MOCA polygon has {len(moca_polygon)} points")
                            if layer_moca:
                                feat = QgsFeature()
                                feat.setFields(layer_moca.fields())
                                geom = QgsGeometry.fromPolygonXY([moca_polygon])
                                feat.setGeometry(geom)
                                feat.setAttribute("moca", float(moca_value))
                                feat.setAttribute(
                                    "segment_name",
                                    f"{point1.get('point_name', '')} - {point2.get('point_name', '')}"
                                )
                                feat.setAttribute("clearance", 0.0)
                                self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                                moca_features.append(feat)
                                log("  âœ… MOCA feature added to batch")
                        except (ValueError, TypeError) as e:
                            log(f"âŒ Could not create MOCA for segment: {e}")
                            continue

        # Removed duplicate per-segment MOCA generation to avoid conflicts.

        # (Note) explicit MOCA handled above only when no OCA is present.
        self._dbg("PHASE: MOCA/OCA end")

        # BATCH ADD: Add all features in bulk (single edit cycle per layer)
        log("=== BATCH ADDING FEATURES ===")
        self._dbg("PHASE: BATCH ADD start")
        log(
            f"Features to add - Points: {len(point_features)}, Labels: {len(label_features)},"
            f" Lines: {len(line_features)}, MOCA: {len(moca_features)}"
        )
        print(
            f"[qAeroChart][POP] BATCH: points={len(point_features)}, labels={len(label_features)},"
            f" lines={len(line_features)}, moca={len(moca_features)}"
        )

        if point_features and layer_point:
            layer_point.startEditing()
            success = layer_point.addFeatures(point_features)
            commit_success = layer_point.commitChanges()
            layer_point.updateExtents()
            layer_point.triggerRepaint()
            if not commit_success:
                log(f"âŒ POINTS COMMIT FAILED! Errors: {layer_point.commitErrors()}")
                print(f"[qAeroChart][POP] POINTS COMMIT FAILED: {layer_point.commitErrors()}")
            log(f"âœ… Added {len(point_features)} point features (addFeatures={success}, commit={commit_success})")
            self._dbg(f"Point layer now has {layer_point.featureCount()} features")
            print(
                f"[qAeroChart][POP] Points: add={success}, commit={commit_success},"
                f" count={layer_point.featureCount()}"
            )

        if label_features and layer_label:
            layer_label.startEditing()
            success = layer_label.addFeatures(label_features)
            commit_success = layer_label.commitChanges()
            layer_label.updateExtents()
            layer_label.triggerRepaint()
            if not commit_success:
                log(f"âŒ LABELS COMMIT FAILED! Errors: {layer_label.commitErrors()}")
                print(f"[qAeroChart][POP] LABELS COMMIT FAILED: {layer_label.commitErrors()}")
            log(f"âœ… Added {len(label_features)} label features (addFeatures={success}, commit={commit_success})")
            self._dbg(f"Label layer now has {layer_label.featureCount()} features")
            print(
                f"[qAeroChart][POP] Labels: add={success}, commit={commit_success},"
                f" count={layer_label.featureCount()}"
            )

        # Distance markers and key verticals are merged into profile_line per #40; commit line features
        log("=== ADDING LINE FEATURES ===")
        log(f"Layer valid: {layer_line.isValid()}")
        log(f"Layer CRS: {layer_line.crs().authid()}")
        log(f"Features in batch: {len(line_features)}")

        for idx, feat in enumerate(line_features):
            geom = feat.geometry()
            log(
                f"  Line {idx}: Valid={geom.isGeosValid()}, Type={geom.type()},"
                f" Empty={geom.isEmpty()}, WKT={geom.asWkt()[:100]}..."
            )

        layer_line.startEditing()
        success = layer_line.addFeatures(line_features)
        commit_success = layer_line.commitChanges()

        if not commit_success:
            errors = layer_line.commitErrors()
            log(f"âŒ LINE COMMIT FAILED! Errors: {errors}")
            print(f"[qAeroChart][POP] LINE COMMIT FAILED: {errors}")

        layer_line.updateExtents()
        layer_line.triggerRepaint()

        # Debug: Print extent and feature count
        extent = layer_line.extent()
        feature_count = layer_line.featureCount()
        log(f"âœ… Added {len(line_features)} line features (addFeatures={success}, commit={commit_success})")
        log(
            f"Line layer extent: {extent.xMinimum():.2f}, {extent.yMinimum():.2f}"
            f" to {extent.xMaximum():.2f}, {extent.yMaximum():.2f}"
        )
        log(f"Line layer feature count: {feature_count}")
        print(
            f"[qAeroChart][POP] Lines extent:"
            f" {extent.xMinimum():.2f},{extent.yMinimum():.2f}"
            f" -> {extent.xMaximum():.2f},{extent.yMaximum():.2f}"
        )
        print(f"[qAeroChart][POP] Lines: add={success}, commit={commit_success}, count={feature_count}")

        # Fallback: if for any reason no line features present, attempt to rebuild once
        if feature_count == 0:
            try:
                # Use THR-relative elevations like the main pass
                profile_points_rel = []
                for p in profile_points:
                    try:
                        elev_ft = float(p.get('elevation_ft', 0))
                    except Exception:
                        elev_ft = 0.0
                    rel_elev = elev_ft - thr_ft
                    q = dict(p)
                    q['elevation_ft'] = rel_elev
                    profile_points_rel.append(q)
                rebuild_points = geometry.create_profile_line(profile_points_rel)
                if rebuild_points:
                    f = QgsFeature()
                    f.setFields(layer_line.fields())
                    f.setGeometry(QgsGeometry.fromPolylineXY(rebuild_points))
                    f.setAttribute("symbol", "profile")
                    f.setAttribute("txt_label", "Main Profile (rebuild)")
                    f.setAttribute("remarks", "")
                    self._assign_feature_id(f, self.LAYER_LINE, next_id)
                    layer_line.startEditing()
                    ok_add = layer_line.addFeature(f)
                    ok_commit = layer_line.commitChanges()
                    layer_line.updateExtents()
                    layer_line.triggerRepaint()
                    log(f"Fallback rebuild line -> add={ok_add}, commit={ok_commit}")
                    try:
                        if self.iface:
                            from ..utils.qt_compat import MsgLevel
                            push_message(
                                self.iface, "qAeroChart",
                                "Profile line rebuilt due to empty layer after first pass.",
                                level=MsgLevel.Info,
                                duration=4,
                            )
                    except Exception:
                        pass
            except Exception as e:
                log(f"Fallback rebuild failed: {e}", "WARNING")

        # Distance markers are merged into profile_line per #40 (no separate dist layer)

        # Key verticals merged into profile_line per #40

        if moca_features and layer_moca:
            log("=== ADDING MOCA FEATURES ===")
            log(f"Layer valid: {layer_moca.isValid()}")
            log(f"Layer CRS: {layer_moca.crs().authid()}")
            log(f"Features in batch: {len(moca_features)}")

            for idx, feat in enumerate(moca_features):
                geom = feat.geometry()
                log(
                    f"  MOCA {idx}: Valid={geom.isGeosValid()}, Type={geom.type()},"
                    f" Area={geom.area():.2f}, Empty={geom.isEmpty()}"
                )

            layer_moca.startEditing()
            success = layer_moca.addFeatures(moca_features)
            commit_success = layer_moca.commitChanges()

            if not commit_success:
                errors = layer_moca.commitErrors()
                log(f"âŒ MOCA COMMIT FAILED! Errors: {errors}")
                print(f"[qAeroChart][POP] MOCA COMMIT FAILED: {errors}")

            layer_moca.updateExtents()
            layer_moca.triggerRepaint()

            # Debug: Print extent and feature count
            extent = layer_moca.extent()
            feature_count = layer_moca.featureCount()
            log(f"âœ… Added {len(moca_features)} MOCA features (addFeatures={success}, commit={commit_success})")
            log(
                f"MOCA layer extent: {extent.xMinimum():.2f}, {extent.yMinimum():.2f}"
                f" to {extent.xMaximum():.2f}, {extent.yMaximum():.2f}"
            )
            log(f"MOCA layer feature count: {feature_count}")
            print(
                f"[qAeroChart][POP] MOCA extent:"
                f" {extent.xMinimum():.2f},{extent.yMinimum():.2f}"
                f" -> {extent.xMaximum():.2f},{extent.yMaximum():.2f}"
            )
            print(f"[qAeroChart][POP] MOCA: add={success}, commit={commit_success}, count={feature_count}")

        # Baseline is added into profile_line (Issue #24); no separate baseline layer

        self._dbg("PHASE: BATCH ADD end")

        # Force refresh of canvas
        if self.iface:
            self.iface.mapCanvas().refresh()
            log("âœ… Canvas refreshed")
            print("[qAeroChart][POP] Canvas refreshed")

        # Auto-zoom to profile extent
        if layer_line and layer_line.featureCount() > 0:
            extent = layer_line.extent()
            # Add 20% buffer around the profile
            extent.scale(1.2)
            print(
                f"[qAeroChart][POP] Auto-zoom extent:"
                f" {extent.xMinimum():.2f},{extent.yMinimum():.2f}"
                f" -> {extent.xMaximum():.2f},{extent.yMaximum():.2f}"
            )
            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()
            log("âœ… Auto-zoomed to profile extent")
            print("[qAeroChart][POP] Auto-zoomed to extent")
        else:
            print(
                f"[qAeroChart][POP] WARNING: No auto-zoom!"
                f" layer_line={layer_line!r},"
                f" featureCount={layer_line.featureCount() if layer_line else 'N/A'}"
            )

            # View scale enforcement removed (Issue #9)

        log("=== LAYER POPULATION COMPLETE ===")
        self._dbg("PHASE: END population")
        self._dbg("Finished populate_layers_from_config()")

        # Final summary for Python console
        print("[qAeroChart][POP] === POPULATION COMPLETE ===")
        for _lk, _lv in self.layers.items():
            try:
                print(
                    f"[qAeroChart][POP]   {_lk}: valid={_lv.isValid()},"
                    f" features={_lv.featureCount()},"
                    f" renderer={type(_lv.renderer()).__name__ if _lv.renderer() else 'None'}"
                )
            except Exception:
                print(f"[qAeroChart][POP]   {_lk}: <error reading layer>")

        return True
