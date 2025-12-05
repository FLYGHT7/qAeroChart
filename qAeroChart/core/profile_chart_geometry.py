# -*- coding: utf-8 -*-
"""
ProfileChartGeometry - Geographic geometry calculations for profile charts

This module handles all geometric calculations for creating profile charts
drawn on the map following the runway heading.
"""

from qgis.core import QgsPointXY
import math


class ProfileChartGeometry:
    """
    Handles cartesian geometry calculations for aeronautical profile charts.
    
    The profile chart is drawn as a 2D graph where:
    - X-axis = horizontal distance from origin (in meters)
    - Y-axis = altitude/elevation (in meters, scaled for visualization)
    - Origin = (0, 0) positioned at the selected map point
    
    This creates the standard ICAO profile chart layout automatically.
    """
    
    # Conversion constants
    NM_TO_METERS = 1852.0  # 1 Nautical Mile = 1852 meters
    FT_TO_METERS = 0.3048  # 1 Foot = 0.3048 meters
    METERS_TO_FT = 3.28084  # 1 Meter = 3.28084 feet
    
    # ICAO Standard: 320 ft/NM (slope ratio for profile visualization)
    # This is NOT a scale factor - it's the standard aspect ratio
    # Horizontal: Use REAL distances in meters (no scaling)
    # Vertical: Use REAL altitudes in meters (no scaling)
    # The "320 ft/NM" is achieved by the natural proportions, not artificial scaling
    
    def __init__(self, origin_point, vertical_exaggeration: float = 10.0, horizontal_direction: int = 1):
        """
        Initialize the geometry calculator with cartesian coordinate system.
        
        Args:
            origin_point (QgsPointXY): Origin point where chart will be drawn
            vertical_exaggeration (float): Factor to exaggerate vertical distances
        """
        self.origin = origin_point
        # Scales (horizontal kept at 1:1; vertical exaggerated per requirement)
        self.horizontal_scale = 1.0
        self.vertical_exaggeration = max(1.0, float(vertical_exaggeration or 10.0))
        # Direction: +1 means left→right (increasing X to the right), -1 means right→left
        self.dir_sign = 1 if int(horizontal_direction or 1) >= 0 else -1
        
        print(f"PLUGIN qAeroChart: ProfileChartGeometry initialized at origin "
              f"X={origin_point.x():.2f}, Y={origin_point.y():.2f} (Cartesian mode, VE={self.vertical_exaggeration}x)")
    
    def nm_to_meters(self, nautical_miles):
        """
        Convert nautical miles to meters.
        
        Args:
            nautical_miles (float): Distance in NM
        
        Returns:
            float: Distance in meters
        """
        return nautical_miles * self.NM_TO_METERS
    
    def calculate_profile_point(self, distance_nm, elevation_ft):
        """
        Calculate cartesian coordinates for a profile point.
        
        Args:
            distance_nm (float): Distance from origin in Nautical Miles (X-axis)
            elevation_ft (float): Elevation/Altitude in feet (Y-axis, scaled)
        
        Returns:
            QgsPointXY: Point in cartesian coordinates (X=distance*h_scale, Y=altitude*v_scale)
        """
        distance_m = self.nm_to_meters(distance_nm)
        elevation_m = elevation_ft * self.FT_TO_METERS
        
        # Apply both horizontal and vertical scaling
        scaled_distance_m = distance_m * self.horizontal_scale
        scaled_elevation_m = elevation_m * self.vertical_exaggeration
        
        result_point = QgsPointXY(
            self.origin.x() + (self.dir_sign * scaled_distance_m),
            self.origin.y() + scaled_elevation_m
        )
        
        print(f"PLUGIN qAeroChart: Point calc - Distance: {distance_nm:.2f}NM ({distance_m:.2f}m→{scaled_distance_m:.2f}m), "
              f"Elevation: {elevation_ft:.2f}ft ({elevation_m:.2f}m→{scaled_elevation_m:.2f}m) "
              f"→ ({result_point.x():.2f}, {result_point.y():.2f})")
        
        return result_point
    
    def create_runway_line(self, length_m, _tch_m_unused=0.0):
        """
        Create the runway line geometry in cartesian coordinates.

        Specification (Issue #6):
        - The origin (0 NM) is the THR (start of runway) for the profile chart.
        - The runway distance must be drawn on the opposite side of the profile
          axis (i.e., negative direction from the origin), so that distances
          0→N NM extend AWAY from the runway.
        - The runway lies on the baseline (Y = 0), not at TCH.

        Args:
            length_m (float): Runway length in meters
            _tch_m_unused (float): Deprecated. Kept for signature compatibility.

        Returns:
            list[QgsPointXY]: Two points defining the runway line
        """
        # Apply horizontal scale. Vertical is baseline (0)
        scaled_length = length_m * self.horizontal_scale

        # Draw from (origin - length) → origin at Y = baseline
        y = self.origin.y()  # baseline (0 elevation)
        start = QgsPointXY(self.origin.x() - scaled_length, y)
        end = QgsPointXY(self.origin.x(), y)

        print(
            f"PLUGIN qAeroChart: Runway line created (left of origin) - Length: {length_m}m→{scaled_length:.2f}m, Y=baseline"
        )

        return [start, end]
    
    def create_profile_line(self, profile_points):
        """
        Create the main profile line connecting profile points.
        
        Args:
            profile_points (list): List of dicts with 'distance_nm' and 'elevation_ft'
        
        Returns:
            list[QgsPointXY]: Ordered points defining the profile line
        """
        points = []
        
        # Sort by distance to ensure correct order
        sorted_points = sorted(profile_points, key=lambda p: float(p.get('distance_nm', 0)))
        
        for point_data in sorted_points:
            try:
                distance_nm = float(point_data.get('distance_nm', 0))
                elevation_ft = float(point_data.get('elevation_ft', 0))
                
                pt = self.calculate_profile_point(distance_nm, elevation_ft)
                points.append(pt)
                
            except (ValueError, TypeError) as e:
                print(f"PLUGIN qAeroChart WARNING: Could not process point "
                      f"{point_data.get('point_name', 'unknown')}: {e}")
                continue
        
        print(f"PLUGIN qAeroChart: Profile line created with {len(points)} points")
        
        return points
    
    def create_distance_markers(self, max_distance_nm, marker_height_m=200):
        """
        Create distance marker points in cartesian coordinates.
        
        Markers are placed at each nautical mile along the X-axis.
        
        Args:
            max_distance_nm (float): Maximum distance in NM
            marker_height_m (float): Height of markers (default: 200m, will be scaled)
        
        Returns:
            list[dict]: List of markers with 'distance', 'label', and 'geometry'
        """
        markers = []
        
        scaled_marker_height = marker_height_m * self.vertical_exaggeration
        
    # Create marker for each nautical mile
        for i in range(int(max_distance_nm) + 1):
            distance_m = self.nm_to_meters(i)
            scaled_distance = distance_m * self.horizontal_scale
            x_position = self.origin.x() + (self.dir_sign * scaled_distance)
            
            # Marker line drawn DOWNWARD from baseline (to match eAIP style)
            bottom = QgsPointXY(x_position, self.origin.y())  # baseline
            top = QgsPointXY(x_position, self.origin.y() - scaled_marker_height)
            
            markers.append({
                'distance': i,
                'label': str(i),
                'geometry': [bottom, top]
            })
        
        print(f"PLUGIN qAeroChart: Created {len(markers)} distance markers "
              f"(height: {marker_height_m}m→{scaled_marker_height:.2f}m)")
        
        return markers
    
    def create_vertical_reference_line(self, distance_nm, height_m):
        """
        Create a vertical reference line at a specific distance.
        
        Args:
            distance_nm (float): Distance from origin in NM
            height_m (float): Height of the line in meters
        
        Returns:
            list[QgsPointXY]: Two points defining the vertical line
        """
        # Apply horizontal scale for distance and vertical exaggeration for height
        x_position = self.origin.x() + (self.dir_sign * (self.nm_to_meters(distance_nm) * self.horizontal_scale))
        
        bottom = QgsPointXY(x_position, self.origin.y())
        top = QgsPointXY(x_position, self.origin.y() + (height_m * self.vertical_exaggeration))
        
        return [bottom, top]
    
    def create_oca_box(self, start_distance_nm, end_distance_nm, height_ft):
        """
        Create OCA/H (Obstacle Clearance Altitude/Height) box as a polygon.
        
        This creates a hatched rectangular area representing the MOCA clearance zone.
        
        Args:
            start_distance_nm (float): Starting distance in NM
            end_distance_nm (float): Ending distance in NM
            height_ft (float): Height of MOCA in feet
        
        Returns:
            list[QgsPointXY]: Five points defining the polygon (closed)
        """
        # Convert to meters and scale
        start_m = self.nm_to_meters(start_distance_nm)
        end_m = self.nm_to_meters(end_distance_nm)
        height_m = height_ft * self.FT_TO_METERS
        
        # Apply both scales
        scaled_start = start_m * self.horizontal_scale
        scaled_end = end_m * self.horizontal_scale
        scaled_height = height_m * self.vertical_exaggeration
        
        # Create polygon vertices (clockwise)
        bottom_left = QgsPointXY(self.origin.x() + (self.dir_sign * scaled_start), self.origin.y())
        bottom_right = QgsPointXY(self.origin.x() + (self.dir_sign * scaled_end), self.origin.y())
        top_right = QgsPointXY(self.origin.x() + (self.dir_sign * scaled_end), self.origin.y() + scaled_height)
        top_left = QgsPointXY(self.origin.x() + (self.dir_sign * scaled_start), self.origin.y() + scaled_height)
        
        # Close the polygon by repeating first point
        polygon = [bottom_left, bottom_right, top_right, top_left, bottom_left]
        
        print(f"PLUGIN qAeroChart: OCA polygon created - "
              f"Distance: {start_distance_nm}-{end_distance_nm} NM ({scaled_start:.2f}-{scaled_end:.2f}m), "
              f"Height: {height_ft} ft ({scaled_height:.2f}m)")
        
        return polygon
    
    def calculate_gradient(self, point1_nm_ft, point2_nm_ft):
        """
        Calculate gradient between two points.
        
        Args:
            point1_nm_ft (tuple): (distance_nm, elevation_ft) for first point
            point2_nm_ft (tuple): (distance_nm, elevation_ft) for second point
        
        Returns:
            float: Gradient as percentage
        """
        dist1_nm, elev1_ft = point1_nm_ft
        dist2_nm, elev2_ft = point2_nm_ft
        
        # Convert to meters
        dist1_m = self.nm_to_meters(dist1_nm)
        dist2_m = self.nm_to_meters(dist2_nm)
        elev1_m = elev1_ft * self.FT_TO_METERS
        elev2_m = elev2_ft * self.FT_TO_METERS
        
        # Calculate gradient
        horizontal_distance = dist2_m - dist1_m
        vertical_distance = elev2_m - elev1_m
        
        if horizontal_distance == 0:
            return 0.0
        
        gradient = (vertical_distance / horizontal_distance) * 100
        
        return gradient
    
    def extend_line_with_gradient(self, start_point_nm_ft, gradient_percent, extend_distance_nm):
        """
        Extend a line with a specific gradient.
        
        Args:
            start_point_nm_ft (tuple): (distance_nm, elevation_ft) for starting point
            gradient_percent (float): Gradient as percentage
            extend_distance_nm (float): Distance to extend in NM
        
        Returns:
            QgsPointXY: End point of extended line
        """
        start_dist_nm, start_elev_ft = start_point_nm_ft
        
        # Calculate elevation change
        extend_distance_m = self.nm_to_meters(extend_distance_nm)
        elevation_change_m = (gradient_percent / 100) * extend_distance_m
        elevation_change_ft = elevation_change_m * self.METERS_TO_FT
        
        # Calculate end point
        end_dist_nm = start_dist_nm + extend_distance_nm
        end_elev_ft = start_elev_ft + elevation_change_ft
        
        return self.calculate_profile_point(end_dist_nm, end_elev_ft)
