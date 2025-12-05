# -*- coding: utf-8 -*-
"""
LayerManager - Manages memory layers for aeronautical profile charts

This module handles the creation, configuration, and management of memory layers
used for ICAO aeronautical profile charts. It creates 5 specialized layers following
ICAO Annex 14 and Doc 8697 standards.

v2.0: Integrated with ProfileChartGeometry for cartesian calculations.
"""

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsProject,
    QgsLayerTreeGroup,
    QgsWkbTypes,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    Qgis
)

from .profile_chart_geometry import ProfileChartGeometry


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
    LAYER_DIST = "profile_dist"
    LAYER_MOCA = "profile_MOCA"
    LAYER_BASELINE = "profile_baseline"  # legacy; merged into profile_line (Issue #24)
    LAYER_KEY_VLINES = "profile_key_verticals"
    
    # Group name
    GROUP_NAME = "MAP 03 - Profile"
    
    def __init__(self, iface, crs=None):
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
            init_auth = (self.project.crs().authid() if self.project and self.project.crs().isValid() else (self.crs.authid() if self.crs else ''))
            print(f"PLUGIN qAeroChart: LayerManager initialized with CRS: {init_auth}")
        except Exception:
            print("PLUGIN qAeroChart: LayerManager initialized (CRS unknown)")

    # ------------- Internal helpers -------------
    def _log(self, message, level="INFO"):
        try:
            print(f"[qAeroChart][{level}] {message}")
        except Exception:
            # best-effort logging to avoid breaking flows
            pass

    def _dbg(self, message):
        if self.debug:
            self._log(message, level="DEBUG")

    def _crs_guard(self, *, enforce_block=False, show_message=True):
        """
        Check CRS suitability.
        - If geographic CRS (degrees), optionally block further actions per Issue #13.
        - Always inform user via message bar.
        
        Args:
            enforce_block (bool): When True, show a red error and signal caller to abort.
        
        Returns:
            bool: True if CRS is acceptable (projected), False if geographic and enforce_block requested.
        """
        try:
            current_crs = self.project.crs() if self.project else self.crs
            if current_crs is None or not current_crs.isValid():
                msg = "Project CRS is not set or invalid. Set a projected CRS (meters) before creating a profile."
                self._log(msg, level="WARN")
                try:
                    if show_message and self.iface:
                        self.iface.messageBar().pushMessage("qAeroChart", msg, level=Qgis.Critical, duration=8)
                except Exception:
                    pass
                return False if enforce_block else True

            if current_crs.isGeographic():
                msg = (
                    f"Project CRS {current_crs.authid()} is geographic (degrees). "
                    "Set a projected CRS (meters) and retry. Profile creation is blocked."
                )
                self._log(msg, level="WARN")
                try:
                    if show_message and self.iface:
                        # Red bar
                        self.iface.messageBar().pushMessage("qAeroChart", msg, level=Qgis.Critical, duration=8)
                except Exception:
                    pass
                return False if enforce_block else True
            return True
        except Exception as e:
            self._log(f"CRS guard check failed: {e}", level="WARN")
            return True

    def _current_project_crs(self):
        """Return the current project CRS if valid, else fallback to self.crs."""
        try:
            if self.project and self.project.crs() and self.project.crs().isValid():
                return self.project.crs()
        except Exception:
            pass
        return self.crs

    def _crs_param_for_uri(self, crs_obj):
        """Build a robust CRS parameter for memory layer URI.
        Prefer EPSG code if available; fallback to authid; else return None.
        """
        try:
            if not crs_obj:
                return None
            epsg = crs_obj.postgisSrid()
            if isinstance(epsg, int) and epsg > 0:
                return f"EPSG:{epsg}"
            auth = crs_obj.authid()
            if auth:
                return auth
        except Exception:
            pass
        return None

    def _ensure_layer_crs(self, layer):
        """Force-assign current project CRS to a layer if missing or different.
        This double-check mitigates cases where provider URI is ignored.
        """
        try:
            proj_crs = self._current_project_crs()
            if not proj_crs or not isinstance(layer, QgsVectorLayer):
                return
            # If layer has no CRS or a different one, set it explicitly
            if not layer.crs().isValid() or layer.crs() != proj_crs:
                layer.setCrs(proj_crs)
        except Exception as e:
            self._log(f"Could not ensure CRS on layer '{getattr(layer, 'name', lambda: '')()}': {e}", level="WARN")
    
    def _create_memory_layer(self, geom_type: str, name: str, *, id_type: QVariant = QVariant.Int) -> QgsVectorLayer:
        """Create a memory layer with the live project CRS and an 'id' field.
        geom_type: 'Point' | 'LineString' | 'Polygon'
        id_type: QVariant.Int (default) or QVariant.String, depending on layer schema
        """
        proj_crs = self._current_project_crs()
        crs_param = self._crs_param_for_uri(proj_crs)
        uri = f"{geom_type}?crs={crs_param}" if crs_param else geom_type
        layer = QgsVectorLayer(uri, name, "memory")
        try:
            if proj_crs:
                layer.setCrs(proj_crs)
        except Exception:
            pass
        # Ensure ID field exists first
        try:
            provider = layer.dataProvider()
            # Only add if not present
            if provider and layer.fields().indexOf("id") < 0:
                provider.addAttributes([QgsField("id", id_type)])
                layer.updateFields()
        except Exception:
            pass
        return layer

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
        print("PLUGIN qAeroChart: Creating all profile layers...")
        # Enforce projected CRS; block if geographic (Issue #13). Show a message here, too, for clarity.
        if not self._crs_guard(enforce_block=True, show_message=True):
            self._log("Aborting layer creation due to geographic/invalid CRS", level="WARN")
            return {}
        
        # Create group first
        self._create_layer_group()
        
        # Create each layer (baseline merged into profile_line per Issue #24)
        self.layers[self.LAYER_POINT_SYMBOL] = self._create_point_symbol_layer()
        self.layers[self.LAYER_CARTO_LABEL] = self._create_carto_label_layer()
        self.layers[self.LAYER_LINE] = self._create_line_layer()
        self.layers[self.LAYER_KEY_VLINES] = self._create_named_line_layer(self.LAYER_KEY_VLINES)
        self.layers[self.LAYER_DIST] = self._create_dist_layer()
        self.layers[self.LAYER_MOCA] = self._create_moca_layer()

        # Emit validity and field diagnostics
        for k, lyr in self.layers.items():
            try:
                self._dbg(f"Layer '{k}': valid={lyr.isValid()} CRS={lyr.crs().authid()} fields={[f.name() for f in lyr.fields()]}")
            except Exception as e:
                self._log(f"Diag failed for layer '{k}': {e}", level="WARN")
        
        # Add layers to group and apply styles
        self._add_layers_to_group(config)
        
        print(f"PLUGIN qAeroChart: Created {len(self.layers)} layers in group '{self.GROUP_NAME}'")
        self._dbg("Finished create_all_layers()")
        
        return self.layers
    
    def _create_layer_group(self):
        """Create or get the layer group for profile charts."""
        root = self.project.layerTreeRoot()
        
        # Check if group already exists
        existing_group = root.findGroup(self.GROUP_NAME)
        
        if existing_group:
            self.layer_group = existing_group
            print(f"PLUGIN qAeroChart: Using existing group '{self.GROUP_NAME}'")
        else:
            self.layer_group = root.addGroup(self.GROUP_NAME)
            print(f"PLUGIN qAeroChart: Created new group '{self.GROUP_NAME}'")
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
        
        print(f"PLUGIN qAeroChart: Created layer '{self.LAYER_POINT_SYMBOL}' with {layer.fields().count()} fields")
        
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
        
        print(f"PLUGIN qAeroChart: Created layer '{self.LAYER_CARTO_LABEL}' with {layer.fields().count()} fields")
        
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
        # Unified schema for profile_line (Issue #24): id (string), symbol, txt_label, trim, offset_marker
        layer = self._create_memory_layer('LineString', self.LAYER_LINE, id_type=QVariant.String)
        
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("symbol", QVariant.String, len=30),
            QgsField("txt_label", QVariant.String, len=80),
            QgsField("trim", QVariant.String, len=20),
            QgsField("offset_marker", QVariant.String, len=20)
        ])
        layer.updateFields()
        
        print(f"PLUGIN qAeroChart: Created layer '{self.LAYER_LINE}' with {layer.fields().count()} fields")
        
        return layer

    def _create_named_line_layer(self, name):
        """Create a generic line layer with standard fields using the given name."""
        layer = self._create_memory_layer('LineString', name)
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("line_type", QVariant.String, len=30),
            QgsField("segment_name", QVariant.String, len=50),
            QgsField("gradient", QVariant.Double)
        ])
        layer.updateFields()
        return layer
    
    def _create_dist_layer(self):
        """
        Create the profile_dist layer for distance markers (tick lines).
        
        Notes:
        - Use LineString geometry so each marker is a small vertical segment (tick)
        - This makes the scale visually clear as en el gráfico 2D (distancia vs altitud)
        
        Fields:
        - distance: Distance value (NM)
        - from_point: Origin point name
        - marker_type: Type of marker (tick, label, etc.)
        
        Returns:
            QgsVectorLayer: The created layer
        """
        layer = self._create_memory_layer('LineString', self.LAYER_DIST)
        
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("distance", QVariant.Double),
            QgsField("from_point", QVariant.String, len=50),
            QgsField("marker_type", QVariant.String, len=30)
        ])
        layer.updateFields()
        
        print(f"PLUGIN qAeroChart: Created layer '{self.LAYER_DIST}' with {layer.fields().count()} fields (LineString)")
        
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
        
        print(f"PLUGIN qAeroChart: Created layer '{self.LAYER_MOCA}' with {layer.fields().count()} fields")
        
        return layer
    
    def _add_layers_to_group(self, config=None):
        """
        Add all created layers to the layer group and apply styles.
        
        Args:
            config (dict): Optional configuration with style parameters
        """
        if not self.layer_group:
            print("PLUGIN qAeroChart ERROR: Layer group not found")
            return
        
        # Add layers to project and group in specific order
        # Order layers so the profile line is above MOCA for visibility
        layer_order = [
            self.LAYER_CARTO_LABEL,
            self.LAYER_POINT_SYMBOL,
            self.LAYER_KEY_VLINES,
            self.LAYER_DIST,
            self.LAYER_LINE,
            self.LAYER_MOCA
        ]
        
        for layer_name in layer_order:
            if layer_name in self.layers:
                layer = self.layers[layer_name]
                # Add to project
                # Ensure CRS before adding (belt-and-suspenders)
                self._ensure_layer_crs(layer)
                self.project.addMapLayer(layer, False)
                # Add to group
                self.layer_group.addLayer(layer)
                print(f"PLUGIN qAeroChart: Added '{layer_name}' to group")
                try:
                    self._dbg(f"  -> layer '{layer_name}' valid={layer.isValid()} count={layer.featureCount()} extent={[layer.extent().xMinimum(), layer.extent().yMinimum(), layer.extent().xMaximum(), layer.extent().yMaximum()]}")
                except Exception:
                    pass
        
        # Apply basic styles to make features visible
        self._apply_basic_styles(config)

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
        
        Args:
            config (dict): Optional configuration with style parameters
        """
        from qgis.core import (
            QgsSymbol,
            QgsSimpleLineSymbolLayer,
            QgsSimpleMarkerSymbolLayer,
            QgsTextFormat,
            QgsPalLayerSettings,
            QgsVectorLayerSimpleLabeling,
            QgsUnitTypes,
            QgsLineSymbol,
            QgsSingleSymbolRenderer,
            QgsProperty,
            Qgis,
            QgsRuleBasedRenderer,
        )
        from qgis.PyQt.QtGui import QColor, QFont
        from qgis.PyQt.QtCore import Qt
        
        # Minimal, fixed styling (Issue #9: remove style parameters; rely on predefined styles later)
        style = config.get('style', {}) if config else {}
        line_width = 2.0
        moca_border_width = 1.0
        point_size = 5.0
        line_color = '#000000'
        moca_fill = '#6464FF64'
        moca_hatch = '#000000'
        
        # Style for PROFILE_LINE - Rule-based: baseline vs others (profile/runway)
        line_layer = self.layers.get(self.LAYER_LINE)
        if line_layer:
            # Default symbol for profile/runway
            core = QgsSimpleLineSymbolLayer(); core.setColor(QColor(line_color))
            casing = QgsSimpleLineSymbolLayer(); casing.setColor(QColor(255,255,255))
            try:
                core.setCapStyle(Qt.FlatCap); core.setJoinStyle(Qt.MiterJoin)
                casing.setCapStyle(Qt.FlatCap); casing.setJoinStyle(Qt.MiterJoin)
            except Exception:
                pass
            core.setWidth(line_width); core.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            casing.setWidth(line_width*1.8); casing.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            sym_default = QgsLineSymbol(); sym_default.appendSymbolLayer(casing); sym_default.appendSymbolLayer(core)

            # Baseline symbol: dashed dark line
            bl = QgsSimpleLineSymbolLayer(); bl.setColor(QColor(0,0,0))
            try:
                bl.setCapStyle(Qt.FlatCap); bl.setJoinStyle(Qt.MiterJoin)
                bl.setUseCustomDashPattern(True); bl.setCustomDashVector([6.0, 0.8]); bl.setCustomDashPatternUnit(QgsUnitTypes.RenderMillimeters)
            except Exception:
                pass
            bl.setWidth(max(line_width, 2.5)); bl.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            sym_base = QgsLineSymbol(); sym_base.appendSymbolLayer(bl)

            root = QgsRuleBasedRenderer.Rule(None)
            rule_baseline = QgsRuleBasedRenderer.Rule(sym_base)
            rule_baseline.setFilterExpression("\"symbol\" = 'baseline'")
            rule_default = QgsRuleBasedRenderer.Rule(sym_default)
            rule_default.setFilterExpression("\"symbol\" IN ('profile','runway')")
            root.appendChild(rule_baseline)
            root.appendChild(rule_default)
            renderer = QgsRuleBasedRenderer(root)
            line_layer.setRenderer(renderer)
            line_layer.triggerRepaint()
            print("PLUGIN qAeroChart: Applied rule-based style to profile_line (baseline vs others)")
        
        # Style for PROFILE_POINT_SYMBOL - Red circles, configurable size (or hidden)
        point_layer = self.layers.get(self.LAYER_POINT_SYMBOL)
        if point_layer:
            symbol = QgsSymbol.defaultSymbol(point_layer.geometryType())
            # Always show point symbols (Issue #9)
            symbol.setColor(QColor(255, 0, 0))  # Red
            symbol.setSize(point_size)
            symbol.setSizeUnit(QgsUnitTypes.RenderMillimeters)
            point_layer.renderer().setSymbol(symbol)
            point_layer.triggerRepaint()
            print(f"PLUGIN qAeroChart: Applied style to profile_point_symbol (visible=True)")
        
        # Style for PROFILE_DIST - Gray tick lines, 0.3 mm
        dist_layer = self.layers.get(self.LAYER_DIST)
        if dist_layer:
            symbol = QgsSymbol.defaultSymbol(dist_layer.geometryType())
            symbol.setColor(QColor(128, 128, 128))  # Gray
            # For line symbols, configure width in millimeters
            try:
                symbol.setWidth(0.3)
                from qgis.core import QgsUnitTypes
                symbol.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            except Exception:
                pass
            dist_layer.renderer().setSymbol(symbol)
            dist_layer.triggerRepaint()
            print(f"PLUGIN qAeroChart: Applied style to profile_dist (gray tick lines, 0.3mm)")
            # eAIP style: no 'N NM' labels on vertical ticks; axis labels below baseline are used instead.
            try:
                dist_layer.setLabelsEnabled(False)
            except Exception:
                pass
        
        # Style for PROFILE_MOCA - Configurable hatching pattern
        moca_layer = self.layers.get(self.LAYER_MOCA)
        if moca_layer:
            from qgis.core import QgsFillSymbol, QgsLinePatternFillSymbolLayer, QgsSimpleFillSymbolLayer
            
            try:
                # Parse colors from hex
                # Use transparent fill to mimic eAIP hatch-only look
                color_str = '0,0,0,0'
                
                # Create fill symbol with configurable parameters
                symbol = QgsFillSymbol.createSimple({
                    'color': color_str,
                    'outline_color': moca_hatch,
                    'outline_width': str(moca_border_width),
                    'outline_width_unit': 'MM',
                    'outline_style': 'solid'
                })
                
                # Try to add diagonal line pattern
                line_pattern = QgsLinePatternFillSymbolLayer()
                line_pattern.setDistance(1.6)  # slightly tighter spacing
                line_pattern.setDistanceUnit(QgsUnitTypes.RenderMillimeters)
                line_pattern.setLineAngle(45)  # 45 degree diagonal
                
                # Configure line style
                line_symbol = line_pattern.subSymbol()
                if line_symbol:
                    line_symbol.setColor(QColor(moca_hatch))
                    line_symbol.setWidth(0.4)  # finer lines
                    line_symbol.setWidthUnit(QgsUnitTypes.RenderMillimeters)
                
                symbol.appendSymbolLayer(line_pattern)
                
            except Exception as e:
                # Fallback to simple fill if pattern fails
                print(f"PLUGIN qAeroChart WARNING: Could not create hatching pattern: {e}")
                symbol = QgsFillSymbol.createSimple({
                    'color': '100,100,255,150',
                    'outline_color': 'black',
                    'outline_width': str(moca_border_width),
                    'outline_width_unit': 'MM'
                })
            
            moca_layer.renderer().setSymbol(symbol)
            moca_layer.triggerRepaint()
            print(f"PLUGIN qAeroChart: Applied style to profile_MOCA (border: {moca_border_width}mm)")

        # Baseline layer styling removed; baseline is rendered in profile_line via rule-based styling

        
        
        # Style for CARTO_LABEL - Configure text labels
        label_layer = self.layers.get(self.LAYER_CARTO_LABEL)
        if label_layer:
            # Make point symbols invisible (we only want text labels)
            symbol = QgsSymbol.defaultSymbol(label_layer.geometryType())
            symbol.setColor(QColor(0, 0, 0, 0))  # Transparent
            symbol.setSize(0.5)  # Very small
            label_layer.renderer().setSymbol(symbol)
            
            # Configure text format for labels
            text_format = QgsTextFormat()
            text_format.setFont(QFont("Arial", 10, QFont.Bold))
            text_format.setSize(10)
            text_format.setColor(QColor(0, 0, 0))  # Black text
            
            # Optional: Add text buffer (white outline) for better visibility
            from qgis.core import QgsTextBufferSettings
            buffer = QgsTextBufferSettings()
            buffer.setEnabled(True)
            buffer.setSize(1.0)
            buffer.setColor(QColor(255, 255, 255))  # White buffer
            text_format.setBuffer(buffer)
            
            # Create label settings
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = 'txt_label'  # Field containing the text to display
            label_settings.enabled = True
            label_settings.setFormat(text_format)
            
            # Position labels slightly above the point (QGIS 3.40+ uses Qgis.LabelPlacement enum)
            label_settings.placement = Qgis.LabelPlacement.OverPoint
            label_settings.yOffset = 0.0

            # Data-defined rotation from attribute 'rotation' when provided (e.g., slope labels)
            try:
                label_settings.setDataDefinedProperty(QgsPalLayerSettings.Rotation, QgsProperty.fromField('txt_rotation'))
            except Exception:
                pass
            
            # Apply labeling to layer
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            label_layer.setLabeling(labeling)
            label_layer.setLabelsEnabled(True)
            
            print("PLUGIN qAeroChart: Applied labeling to profile_carto_label (black text with white buffer)")

        # Style for KEY VERTICALS - darker dashed lines
        key_v_layer = self.layers.get(self.LAYER_KEY_VLINES)
        if key_v_layer:
            kv = QgsSimpleLineSymbolLayer()
            kv.setColor(QColor(60, 60, 60))
            try:
                kv.setCapStyle(Qt.FlatCap)
                kv.setJoinStyle(Qt.MiterJoin)
            except Exception:
                pass
            kv.setWidth(0.6)
            kv.setWidthUnit(QgsUnitTypes.RenderMillimeters)
            try:
                from qgis.PyQt.QtCore import Qt as QtCoreQt
                kv.setPenStyle(QtCoreQt.DashLine)
            except Exception:
                pass
            key_symbol = QgsLineSymbol()
            key_symbol.appendSymbolLayer(kv)
            key_v_layer.setRenderer(QgsSingleSymbolRenderer(key_symbol))
            key_v_layer.triggerRepaint()
            print("PLUGIN qAeroChart: Applied style to profile_key_verticals (dashed dark)")
    
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
            print("PLUGIN qAeroChart ERROR: Point symbol layer not found")
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
            print(f"PLUGIN qAeroChart: Added point '{point_name}' at ({point.x():.2f}, {point.y():.2f})")
        
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
            print("PLUGIN qAeroChart ERROR: Carto label layer not found")
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
            print(f"PLUGIN qAeroChart: Added label '{label_text}' at ({point.x():.2f}, {point.y():.2f})")
        
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
            print("PLUGIN qAeroChart ERROR: Line layer not found")
            return False
        
        feature = QgsFeature()
        feature.setFields(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        # Set attributes by name to avoid index/order issues
        self._assign_layer_feature_id(layer, feature)
        # Map legacy params to unified schema
        feature.setAttribute("symbol", str(line_type))
        feature.setAttribute("txt_label", str(segment_name))
        feature.setAttribute("trim", "")
        feature.setAttribute("offset_marker", "")
        
        layer.startEditing()
        success = layer.addFeature(feature)
        layer.commitChanges()
        
        if success:
            layer.triggerRepaint()  # Force visual refresh
            print(f"PLUGIN qAeroChart: Added line segment '{segment_name}' with {len(points)} points")
        
        return success
    
    def clear_all_layers(self):
        """Clear all features from all managed layers."""
        for layer_name, layer in self.layers.items():
            if layer:
                layer.startEditing()
                layer.deleteFeatures(layer.allFeatureIds())
                layer.commitChanges()
                print(f"PLUGIN qAeroChart: Cleared layer '{layer_name}'")
    
    def remove_all_layers(self):
        """Remove all managed layers from the project."""
        for layer_name, layer in self.layers.items():
            if layer:
                self.project.removeMapLayer(layer.id())
                print(f"PLUGIN qAeroChart: Removed layer '{layer_name}'")
        
        # Remove group if empty
        if self.layer_group:
            root = self.project.layerTreeRoot()
            if len(self.layer_group.children()) == 0:
                root.removeChildNode(self.layer_group)
                print(f"PLUGIN qAeroChart: Removed empty group '{self.GROUP_NAME}'")
        
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
        print("PLUGIN qAeroChart: Populating layers from config v2.0...")
        print(f"PLUGIN qAeroChart: Config keys: {list(config.keys())}")
        # Enforce projected CRS; block profile creation on geographic CRS (Issue #13). Show the message here only.
        if not self._crs_guard(enforce_block=True, show_message=True):
            print("PLUGIN qAeroChart ERROR: Profile population blocked due to geographic/invalid CRS")
            return False
        
        # Extract origin point (v2.0 uses "origin_point", v1.0 uses "reference_point")
        origin_data = config.get('origin_point', config.get('reference_point', {}))
        if not origin_data or 'x' not in origin_data or 'y' not in origin_data:
            print("PLUGIN qAeroChart ERROR: No origin point in configuration")
            print(f"PLUGIN qAeroChart ERROR: origin_data = {origin_data}")
            return False
        
        origin_point = QgsPointXY(origin_data['x'], origin_data['y'])
        print(f"PLUGIN qAeroChart: *** ORIGIN POINT SET TO: X={origin_point.x():.2f}, Y={origin_point.y():.2f} ***")
        
        # Extract profile points and runway parameters
        profile_points = config.get('profile_points', [])
        if not profile_points:
            print("PLUGIN qAeroChart WARNING: No profile points in configuration")
            return False
        
        runway = config.get('runway', {})
        runway_length = float(runway.get('length', 0))
        tch = float(runway.get('tch_rdh', 0))
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
        # If RWY direction <= 18 then draw right→left (dir_sign = -1), else left→right
        dir_sign = -1 if rwy_num and rwy_num <= 18 else 1
        geometry = ProfileChartGeometry(origin_point, vertical_exaggeration=ve, horizontal_direction=dir_sign)
        
        # BATCH OPERATIONS: Collect all features first, then add in bulk
        point_features = []
        label_features = []
        line_features = []
        dist_features = []
        moca_features = []
        baseline_features = []  # legacy list; baseline will be added to profile_line
        key_vertical_features = []

        # Per-layer ID counters (start at 1)
        next_id = {
            self.LAYER_POINT_SYMBOL: 1,
            self.LAYER_CARTO_LABEL: 1,
            self.LAYER_LINE: 1,
            self.LAYER_DIST: 1,
            self.LAYER_MOCA: 1,
            # baseline merged into profile_line
            self.LAYER_KEY_VLINES: 1,
        }
        
        # Get layer references
        layer_point = self.layers.get(self.LAYER_POINT_SYMBOL)
        layer_label = self.layers.get(self.LAYER_CARTO_LABEL)
        layer_line = self.layers.get(self.LAYER_LINE)
        layer_dist = self.layers.get(self.LAYER_DIST)
        layer_moca = self.layers.get(self.LAYER_MOCA)
        
        # Style cleanup (Issue #9): ORIGIN marker toggle removed; no origin feature added
        style = config.get('style', {}) if config else {}
        
        # 2. Prepare profile line
        if len(profile_points) >= 2:
            print(f"PLUGIN qAeroChart: === CREATING PROFILE LINE ===")
            print(f"PLUGIN qAeroChart: Number of profile points: {len(profile_points)}")
            
            line_points = geometry.create_profile_line(profile_points)
            
            print(f"PLUGIN qAeroChart: Profile line returned {len(line_points) if line_points else 0} points")
            
            if line_points and layer_line:
                # Debug: Print all line points
                for i, pt in enumerate(line_points):
                    print(f"PLUGIN qAeroChart:   Point {i}: X={pt.x():.2f}, Y={pt.y():.2f}")
                
                feat = QgsFeature()
                feat.setFields(layer_line.fields())
                geom = QgsGeometry.fromPolylineXY(line_points)
                
                # Validate geometry
                if geom.isGeosValid():
                    print(f"PLUGIN qAeroChart: ✅ Profile line geometry is VALID")
                else:
                    print(f"PLUGIN qAeroChart: ❌ Profile line geometry is INVALID: {geom.lastError()}")
                
                print(f"PLUGIN qAeroChart: Geometry type: {geom.type()}, WKT length: {len(geom.asWkt())}")
                
                feat.setGeometry(geom)
                # Set attributes following unified profile_line schema (Issue #24)
                feat.setAttribute("symbol", "profile")
                feat.setAttribute("txt_label", "Main Profile")
                feat.setAttribute("trim", "")
                feat.setAttribute("offset_marker", "")
                self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                line_features.append(feat)
                print(f"PLUGIN qAeroChart: ✅ Profile line feature added to batch")
                # Slope labels per segment
                try:
                    sorted_pts = sorted(profile_points, key=lambda p: float(p.get('distance_nm', 0)))
                    for i in range(len(sorted_pts)-1):
                        p1 = sorted_pts[i]
                        p2 = sorted_pts[i+1]
                        grad_percent = geometry.calculate_gradient((float(p1.get('distance_nm',0)), float(p1.get('elevation_ft',0))),
                                                                   (float(p2.get('distance_nm',0)), float(p2.get('elevation_ft',0))))
                        import math
                        deg = math.degrees(math.atan(grad_percent/100.0))
                        text = f"{deg:.1f}° ({grad_percent:.1f}%)"
                        mid_nm = (float(p1.get('distance_nm',0)) + float(p2.get('distance_nm',0)))/2.0
                        # Keep visual offset roughly constant despite VE
                        mid_ft = (float(p1.get('elevation_ft',0)) + float(p2.get('elevation_ft',0)))/2.0 + (80.0/ve)
                        pos = geometry.calculate_profile_point(mid_nm, mid_ft)
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
                    print(f"PLUGIN qAeroChart WARNING: Could not create slope labels: {e}")
            else:
                print(f"PLUGIN qAeroChart: ❌ Profile line NOT created (line_points={bool(line_points)}, layer_line={bool(layer_line)})")
        else:
            print(f"PLUGIN qAeroChart: ❌ Not enough points for profile line ({len(profile_points)} points)")
        
        # 3. Prepare runway line
        if runway_length > 0:
            print(f"PLUGIN qAeroChart: === CREATING RUNWAY LINE ===")
            print(f"PLUGIN qAeroChart: Runway length: {runway_length}m, TCH: {tch}m")
            
            runway_points = geometry.create_runway_line(runway_length, tch)
            
            if runway_points and layer_line:
                # Debug: Print runway points
                for i, pt in enumerate(runway_points):
                    print(f"PLUGIN qAeroChart:   Runway point {i}: X={pt.x():.2f}, Y={pt.y():.2f}")
                
                feat = QgsFeature()
                feat.setFields(layer_line.fields())
                geom = QgsGeometry.fromPolylineXY(runway_points)
                
                # Validate geometry
                if geom.isGeosValid():
                    print(f"PLUGIN qAeroChart: ✅ Runway geometry is VALID")
                else:
                    print(f"PLUGIN qAeroChart: ❌ Runway geometry is INVALID: {geom.lastError()}")
                
                feat.setGeometry(geom)
                # Unified schema attributes
                feat.setAttribute("symbol", "runway")
                feat.setAttribute("txt_label", "Runway")
                feat.setAttribute("trim", "")
                feat.setAttribute("offset_marker", "")
                self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                line_features.append(feat)
                print(f"PLUGIN qAeroChart: ✅ Runway line feature added to batch")
            else:
                print(f"PLUGIN qAeroChart: ❌ Runway line NOT created")
        else:
            print(f"PLUGIN qAeroChart: ⚠️ Runway length is 0, skipping runway line")
        
        # 4. Prepare profile points with symbols and labels
        # Compute dynamic vertical height reference for key vertical lines (Issue #16)
        try:
            max_elevation_ft = max(float(p.get('elevation_ft', 0)) for p in profile_points)
        except Exception:
            max_elevation_ft = 0.0
        vertical_extra_m = 1000.0  # required extra height above highest point (meters)
        vertical_top_ft = max_elevation_ft + vertical_extra_m * ProfileChartGeometry.METERS_TO_FT
        self._dbg(f"Key verticals dynamic height -> max_elev_ft={max_elevation_ft:.2f} ft, extra={vertical_extra_m} m, top_ft={vertical_top_ft:.2f} ft")
        for point_data in profile_points:
            try:
                distance_nm = float(point_data.get('distance_nm', 0))
                elevation_ft = float(point_data.get('elevation_ft', 0))
                point_name = point_data.get('point_name', 'Unknown')
                moca_ft = point_data.get('moca_ft', '')
                notes = point_data.get('notes', '')
                
                # Calculate cartesian position
                point_xy = geometry.calculate_profile_point(distance_nm, elevation_ft)
                
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

                # Add key verticals for known names (FAF/IF/MAPT)
                if point_name.strip().upper() in {"FAF", "IF", "MAPT", "MAP"}:
                    try:
                        bottom = geometry.calculate_profile_point(distance_nm, 0.0)
                        # Dynamic height: highest elevation (subject to VE) + 1000 m NOT exaggerated (Issue #16 last comment)
                        top_at_max = geometry.calculate_profile_point(distance_nm, max_elevation_ft)
                        top = QgsPointXY(bottom.x(), top_at_max.y() + vertical_extra_m)
                        self._dbg(f"Created key vertical for {point_name} at {distance_nm}NM: baseline_y={bottom.y():.2f}, top_y={top.y():.2f}")
                        if self.layers.get(self.LAYER_KEY_VLINES):
                            lyr = self.layers[self.LAYER_KEY_VLINES]
                            feat_v = QgsFeature()
                            feat_v.setFields(lyr.fields())
                            feat_v.setGeometry(QgsGeometry.fromPolylineXY([bottom, top]))
                            if len(lyr.fields())>=3:
                                feat_v.setAttribute("line_type", "key")
                                feat_v.setAttribute("segment_name", point_name)
                                feat_v.setAttribute("gradient", 0.0)
                            self._assign_feature_id(feat_v, self.LAYER_KEY_VLINES, next_id)
                            key_vertical_features.append(feat_v)
                    except Exception as e:
                        print(f"PLUGIN qAeroChart WARNING: could not create key vertical for {point_name}: {e}")
                
                print(f"PLUGIN qAeroChart: Prepared point '{point_name}' at {distance_nm} NM / {elevation_ft} ft")
                
            except (ValueError, TypeError) as e:
                print(f"PLUGIN qAeroChart WARNING: Could not process point {point_data.get('point_name', 'unknown')}: {e}")
                continue
        
        # 5. Prepare distance markers (tick line segments)
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
                    feat.setAttribute("trim", "")
                    feat.setAttribute("offset_marker", "")
                    self._assign_feature_id(feat, self.LAYER_LINE, next_id)
                    line_features.append(feat)
                except Exception as e:
                    print(f"PLUGIN qAeroChart WARNING: Could not prepare baseline: {e}")
            
            if layer_dist:
                for marker in markers:
                    # marker['geometry'] contains [bottom, top] points
                    bottom, top = marker['geometry']
                    feat = QgsFeature()
                    feat.setFields(layer_dist.fields())
                    feat.setGeometry(QgsGeometry.fromPolylineXY([bottom, top]))
                    feat.setAttribute("distance", float(marker['distance']))
                    feat.setAttribute("from_point", 'Origin')
                    feat.setAttribute("marker_type", 'tick')
                    self._assign_feature_id(feat, self.LAYER_DIST, next_id)
                    dist_features.append(feat)
                
                print(f"PLUGIN qAeroChart: Prepared {len(markers)} distance markers")

            # Axis labels under baseline at each NM
            if layer_label:
                try:
                    # Axis labels should be 50 m BELOW the end of the tick marks (Issue #15)
                    # We compute the label y from the same tick visual height used above, plus 50 m visual, then divide by VE
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
                    print(f"PLUGIN qAeroChart: Prepared {int(max_distance_nm)+1} axis labels at {label_y_offset_m:.2f} m below baseline (real), i.e., {label_y_offset_ft:.2f} ft")
                except Exception as e:
                    print(f"PLUGIN qAeroChart WARNING: Could not create axis labels: {e}")
            # Grid layer removed (Issue #14): skipping creation of full-height vertical grid lines
        
    # 6. Prepare MOCA polygons
        print(f"PLUGIN qAeroChart: === CREATING MOCA/OCA HATCH AREAS ===")
        # Decide precedence: OCA > explicit MOCA > per-point MOCA
        has_oca = False
        has_explicit_moca = False
        try:
            has_oca = bool(config.get('oca')) or bool(config.get('oca_segments'))
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
                    poly = geometry.create_oca_box(d1, d2, hft)
                    feat = QgsFeature()
                    feat.setFields(layer_moca.fields())
                    feat.setGeometry(QgsGeometry.fromPolygonXY([poly]))
                    feat.setAttribute("moca", float(hft))
                    feat.setAttribute("segment_name", f"OCA {d1}-{d2}NM")
                    feat.setAttribute("clearance", 0.0)
                    self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                    moca_features.append(feat)
                    print(f"PLUGIN qAeroChart: Added OCA polygon {d1}-{d2} NM @ {hft} ft")
            except Exception as e:
                print(f"PLUGIN qAeroChart WARNING: OCA single processing failed: {e}")
            try:
                oca_segments = config.get('oca_segments', []) if config else []
                if oca_segments and self.layers.get(self.LAYER_MOCA):
                    print(f"PLUGIN qAeroChart: Processing OCA segments: {len(oca_segments)}")
                    for seg in oca_segments:
                        try:
                            d1 = float(seg.get('from_nm', seg.get('from', 0)))
                            d2 = float(seg.get('to_nm', seg.get('to', 0)))
                            hft = float(seg.get('oca_ft', seg.get('height_ft', 0)))
                            poly = geometry.create_oca_box(d1, d2, hft)
                            feat = QgsFeature()
                            feat.setFields(layer_moca.fields())
                            feat.setGeometry(QgsGeometry.fromPolygonXY([poly]))
                            feat.setAttribute("moca", float(hft))
                            feat.setAttribute("segment_name", f"OCA {d1}-{d2}NM")
                            feat.setAttribute("clearance", 0.0)
                            self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                            moca_features.append(feat)
                        except Exception as e:
                            print(f"PLUGIN qAeroChart WARNING: Skipping OCA segment {seg}: {e}")
            except Exception as e:
                print(f"PLUGIN qAeroChart WARNING: OCA segments processing failed: {e}")
            print("PLUGIN qAeroChart: OCA present → skipping all MOCA (explicit and per-point)")
        else:
            # No OCA provided; choose between explicit MOCA (preferred) or per-point MOCA
            if has_explicit_moca:
                try:
                    explicit_moca = config.get('moca_segments', [])
                    if explicit_moca and layer_moca:
                        print(f"PLUGIN qAeroChart: Processing explicit MOCA segments: {len(explicit_moca)}")
                        for seg in explicit_moca:
                            try:
                                d1 = float(seg.get('from_nm', seg.get('from', 0)))
                                d2 = float(seg.get('to_nm', seg.get('to', 0)))
                                hft = float(seg.get('moca_ft', seg.get('height_ft', 0)))
                                poly = geometry.create_oca_box(d1, d2, hft)
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
                                print(f"PLUGIN qAeroChart WARNING: Skipping explicit MOCA segment {seg}: {e}")
                except Exception as e:
                    print(f"PLUGIN qAeroChart WARNING: explicit MOCA processing failed: {e}")
            else:
                print(f"PLUGIN qAeroChart: Processing {len(profile_points)-1} possible MOCA segments (per-point)")
                # fall back to per-point MOCA between consecutive points
                for i in range(len(profile_points) - 1):
                    point1 = profile_points[i]
                    point2 = profile_points[i + 1]
                    moca_ft = point1.get('moca_ft', '')
                    print(f"PLUGIN qAeroChart: Segment {i}: {point1.get('point_name','')} → {point2.get('point_name','')}, MOCA={moca_ft}")
                    if moca_ft and moca_ft.strip():
                        try:
                            moca_value = float(moca_ft)
                            dist1_nm = float(point1.get('distance_nm', 0))
                            dist2_nm = float(point2.get('distance_nm', 0))
                            print(f"PLUGIN qAeroChart:   Creating MOCA: {dist1_nm}NM to {dist2_nm}NM at {moca_value}ft")
                            moca_polygon = geometry.create_oca_box(dist1_nm, dist2_nm, moca_value)
                            print(f"PLUGIN qAeroChart:   MOCA polygon has {len(moca_polygon)} points")
                            if layer_moca:
                                feat = QgsFeature()
                                feat.setFields(layer_moca.fields())
                                geom = QgsGeometry.fromPolygonXY([moca_polygon])
                                feat.setGeometry(geom)
                                feat.setAttribute("moca", float(moca_value))
                                feat.setAttribute("segment_name", f"{point1.get('point_name', '')} - {point2.get('point_name', '')}")
                                feat.setAttribute("clearance", 0.0)
                                self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                                moca_features.append(feat)
                                print(f"PLUGIN qAeroChart:   ✅ MOCA feature added to batch")
                        except (ValueError, TypeError) as e:
                            print(f"PLUGIN qAeroChart: ❌ Could not create MOCA for segment: {e}")
                            continue
        
        for i in range(len(profile_points) - 1):
            if has_explicit_moca:
                break
            point1 = profile_points[i]
            point2 = profile_points[i + 1]
            
            moca_ft = point1.get('moca_ft', '')
            print(f"PLUGIN qAeroChart: Segment {i}: {point1.get('point_name','')} → {point2.get('point_name','')}, MOCA={moca_ft}")
            
            if moca_ft and moca_ft.strip():
                try:
                    moca_value = float(moca_ft)
                    dist1_nm = float(point1.get('distance_nm', 0))
                    dist2_nm = float(point2.get('distance_nm', 0))
                    
                    print(f"PLUGIN qAeroChart:   Creating MOCA: {dist1_nm}NM to {dist2_nm}NM at {moca_value}ft")
                    
                    # create_oca_box returns 5 points (closed polygon) for hatched area
                    moca_polygon = geometry.create_oca_box(dist1_nm, dist2_nm, moca_value)
                    
                    print(f"PLUGIN qAeroChart:   MOCA polygon has {len(moca_polygon)} points")
                    
                    # Debug: Print polygon vertices
                    for j, pt in enumerate(moca_polygon):
                        print(f"PLUGIN qAeroChart:     Vertex {j}: X={pt.x():.2f}, Y={pt.y():.2f}")
                    
                    if layer_moca:
                        feat = QgsFeature()
                        feat.setFields(layer_moca.fields())
                        # Create polygon geometry
                        geom = QgsGeometry.fromPolygonXY([moca_polygon])
                        
                        # Validate geometry
                        if geom.isGeosValid():
                            print(f"PLUGIN qAeroChart:   ✅ MOCA polygon geometry is VALID")
                        else:
                            print(f"PLUGIN qAeroChart:   ❌ MOCA polygon geometry is INVALID: {geom.lastError()}")
                        
                        print(f"PLUGIN qAeroChart:   Geometry type: {geom.type()}, Area: {geom.area():.2f}")
                        
                        feat.setGeometry(geom)
                        try:
                            feat.setAttribute("id", next_id[self.LAYER_MOCA]); next_id[self.LAYER_MOCA] += 1
                        except Exception:
                            pass
                        feat.setAttribute("moca", float(moca_value))
                        feat.setAttribute("segment_name", f"{point1.get('point_name', '')} - {point2.get('point_name', '')}")
                        feat.setAttribute("clearance", 0.0)
                        self._assign_feature_id(feat, self.LAYER_MOCA, next_id)
                        moca_features.append(feat)
                        print(f"PLUGIN qAeroChart:   ✅ MOCA feature added to batch")
                    else:
                        print(f"PLUGIN qAeroChart:   ❌ layer_moca is None!")
                        
                except (ValueError, TypeError) as e:
                    print(f"PLUGIN qAeroChart: ❌ Could not create MOCA for segment: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            else:
                print(f"PLUGIN qAeroChart:   ⚠️ No MOCA value for this segment")

        # (Note) explicit MOCA handled above only when no OCA is present.
        
        # BATCH ADD: Add all features in bulk (single edit cycle per layer)
        print(f"PLUGIN qAeroChart: === BATCH ADDING FEATURES ===")
        print(f"PLUGIN qAeroChart: Features to add - Points: {len(point_features)}, Labels: {len(label_features)}, Lines: {len(line_features)}, Dist: {len(dist_features)}, MOCA: {len(moca_features)}")
        
        if point_features and layer_point:
            layer_point.startEditing()
            success = layer_point.addFeatures(point_features)
            layer_point.commitChanges()
            layer_point.updateExtents()
            layer_point.triggerRepaint()
            print(f"PLUGIN qAeroChart: ✅ Added {len(point_features)} point features (success={success})")
            self._dbg(f"Point layer now has {layer_point.featureCount()} features")
        
        if label_features and layer_label:
            layer_label.startEditing()
            success = layer_label.addFeatures(label_features)
            layer_label.commitChanges()
            layer_label.updateExtents()
            layer_label.triggerRepaint()
            print(f"PLUGIN qAeroChart: ✅ Added {len(label_features)} label features (success={success})")
            self._dbg(f"Label layer now has {layer_label.featureCount()} features")

        if line_features and layer_line:
            print(f"PLUGIN qAeroChart: === ADDING LINE FEATURES ===")
            print(f"PLUGIN qAeroChart: Layer valid: {layer_line.isValid()}")
            print(f"PLUGIN qAeroChart: Layer CRS: {layer_line.crs().authid()}")
            print(f"PLUGIN qAeroChart: Features in batch: {len(line_features)}")

            for idx, feat in enumerate(line_features):
                geom = feat.geometry()
                print(f"PLUGIN qAeroChart:   Line {idx}: Valid={geom.isGeosValid()}, Type={geom.type()}, Empty={geom.isEmpty()}, WKT={geom.asWkt()[:100]}...")

            layer_line.startEditing()
            success = layer_line.addFeatures(line_features)
            commit_success = layer_line.commitChanges()

            if not commit_success:
                errors = layer_line.commitErrors()
                print(f"PLUGIN qAeroChart: ❌ LINE COMMIT FAILED! Errors: {errors}")

            layer_line.updateExtents()
            layer_line.triggerRepaint()

            # Debug: Print extent and feature count
            extent = layer_line.extent()
            feature_count = layer_line.featureCount()
            print(f"PLUGIN qAeroChart: ✅ Added {len(line_features)} line features (addFeatures={success}, commit={commit_success})")
            print(f"PLUGIN qAeroChart: Line layer extent: {extent.xMinimum():.2f}, {extent.yMinimum():.2f} to {extent.xMaximum():.2f}, {extent.yMaximum():.2f}")
            print(f"PLUGIN qAeroChart: Line layer feature count: {feature_count}")

            # Fallback: if for any reason no line features present, attempt to rebuild once
            if feature_count == 0:
                try:
                    rebuild_points = geometry.create_profile_line(profile_points)
                    if rebuild_points:
                        f = QgsFeature()
                        f.setFields(layer_line.fields())
                        f.setGeometry(QgsGeometry.fromPolylineXY(rebuild_points))
                        f.setAttribute("symbol", "profile")
                        f.setAttribute("txt_label", "Main Profile (rebuild)")
                        f.setAttribute("trim", "")
                        f.setAttribute("offset_marker", "")
                        self._assign_feature_id(f, self.LAYER_LINE, next_id)
                        layer_line.startEditing()
                        ok_add = layer_line.addFeature(f)
                        ok_commit = layer_line.commitChanges()
                        layer_line.updateExtents()
                        layer_line.triggerRepaint()
                        print(f"PLUGIN qAeroChart: Fallback rebuild line -> add={ok_add}, commit={ok_commit}")
                        try:
                            if self.iface:
                                self.iface.messageBar().pushMessage(
                                    "qAeroChart",
                                    "Profile line rebuilt due to empty layer after first pass.",
                                    level=Qgis.Info,
                                    duration=4
                                )
                        except Exception:
                            pass
                except Exception as e:
                    print(f"PLUGIN qAeroChart WARNING: Fallback rebuild failed: {e}")

        if dist_features and layer_dist:
            layer_dist.startEditing()
            success = layer_dist.addFeatures(dist_features)
            layer_dist.commitChanges()
            layer_dist.updateExtents()
            layer_dist.triggerRepaint()
            print(f"PLUGIN qAeroChart: ✅ Added {len(dist_features)} distance markers (success={success})")
            self._dbg(f"Dist layer now has {layer_dist.featureCount()} features")



        # Add KEY VERTICALS features
        key_v_layer = self.layers.get(self.LAYER_KEY_VLINES)
        if key_vertical_features and key_v_layer:
            key_v_layer.startEditing()
            success = key_v_layer.addFeatures(key_vertical_features)
            key_v_layer.commitChanges()
            key_v_layer.updateExtents()
            key_v_layer.triggerRepaint()
            print(f"PLUGIN qAeroChart: ✅ Added {len(key_vertical_features)} key verticals")

        if moca_features and layer_moca:
            print(f"PLUGIN qAeroChart: === ADDING MOCA FEATURES ===")
            print(f"PLUGIN qAeroChart: Layer valid: {layer_moca.isValid()}")
            print(f"PLUGIN qAeroChart: Layer CRS: {layer_moca.crs().authid()}")
            print(f"PLUGIN qAeroChart: Features in batch: {len(moca_features)}")

            for idx, feat in enumerate(moca_features):
                geom = feat.geometry()
                print(f"PLUGIN qAeroChart:   MOCA {idx}: Valid={geom.isGeosValid()}, Type={geom.type()}, Area={geom.area():.2f}, Empty={geom.isEmpty()}")

            layer_moca.startEditing()
            success = layer_moca.addFeatures(moca_features)
            commit_success = layer_moca.commitChanges()

            if not commit_success:
                errors = layer_moca.commitErrors()
                print(f"PLUGIN qAeroChart: ❌ MOCA COMMIT FAILED! Errors: {errors}")

            layer_moca.updateExtents()
            layer_moca.triggerRepaint()

            # Debug: Print extent and feature count
            extent = layer_moca.extent()
            feature_count = layer_moca.featureCount()
            print(f"PLUGIN qAeroChart: ✅ Added {len(moca_features)} MOCA features (addFeatures={success}, commit={commit_success})")
            print(f"PLUGIN qAeroChart: MOCA layer extent: {extent.xMinimum():.2f}, {extent.yMinimum():.2f} to {extent.xMaximum():.2f}, {extent.yMaximum():.2f}")
            print(f"PLUGIN qAeroChart: MOCA layer feature count: {feature_count}")

        # Baseline is added into profile_line (Issue #24); no separate baseline layer

        # Force refresh of canvas
        if self.iface:
            self.iface.mapCanvas().refresh()
            print(f"PLUGIN qAeroChart: ✅ Canvas refreshed")

        # Auto-zoom to profile extent
        if layer_line and layer_line.featureCount() > 0:
            extent = layer_line.extent()
            # Add 20% buffer around the profile
            extent.scale(1.2)
            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()
            print(f"PLUGIN qAeroChart: ✅ Auto-zoomed to profile extent")

            # View scale enforcement removed (Issue #9)

        print("PLUGIN qAeroChart: === LAYER POPULATION COMPLETE ===")
        self._dbg("Finished populate_layers_from_config()")

        return True
