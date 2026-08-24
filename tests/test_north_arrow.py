# -*- coding: utf-8 -*-
"""Unit tests for qAeroChart.core.north_arrow (Issue #108)."""
import math

import pytest

from qAeroChart.core.north_arrow import (
    NorthArrowGeometry,
    compute_arrow_geometry,
    format_var_label,
)


class TestComputeArrowGeometry:
    def test_returns_geometry_dataclass(self):
        geom = compute_arrow_geometry(0.0, 0.0, 1000.0, 700.0, 5.0)
        assert isinstance(geom, NorthArrowGeometry)

    def test_true_north_points_straight_up(self):
        geom = compute_arrow_geometry(100.0, 200.0, 1000.0, 700.0, 5.0)
        assert geom.true_tip_x == pytest.approx(100.0)
        assert geom.true_tip_y == pytest.approx(1200.0)

    def test_zero_declination_lines_are_collinear(self):
        geom = compute_arrow_geometry(50.0, 50.0, 800.0, 800.0, 0.0)
        assert geom.mag_tip_x == pytest.approx(geom.true_tip_x)
        assert geom.mag_tip_y == pytest.approx(geom.true_tip_y)

    def test_east_declination_rotates_toward_plus_x(self):
        geom = compute_arrow_geometry(0.0, 0.0, 1000.0, 1000.0, 30.0)
        expected_x = 1000.0 * math.sin(math.radians(30.0))
        expected_y = 1000.0 * math.cos(math.radians(30.0))
        assert geom.mag_tip_x == pytest.approx(expected_x)
        assert geom.mag_tip_y == pytest.approx(expected_y)
        assert geom.mag_tip_x > 0.0

    def test_west_declination_mirrors_east(self):
        east = compute_arrow_geometry(0.0, 0.0, 1000.0, 1000.0, 25.0)
        west = compute_arrow_geometry(0.0, 0.0, 1000.0, 1000.0, -25.0)
        assert west.mag_tip_x == pytest.approx(-east.mag_tip_x)
        assert west.mag_tip_y == pytest.approx(east.mag_tip_y)

    def test_lengths_are_independent(self):
        geom = compute_arrow_geometry(0.0, 0.0, 2000.0, 500.0, 0.0)
        assert geom.true_tip_y == pytest.approx(2000.0)
        assert geom.mag_tip_y == pytest.approx(500.0)

    def test_origin_is_preserved_for_offset_point(self):
        geom = compute_arrow_geometry(-12345.0, 987.5, 100.0, 100.0, 10.0)
        assert geom.origin_x == pytest.approx(-12345.0)
        assert geom.origin_y == pytest.approx(987.5)


class TestFormatVarLabel:
    def test_east_variation(self):
        assert format_var_label(5.5) == "VAR 5.5\N{DEGREE SIGN}E"

    def test_west_variation_uses_absolute_value(self):
        assert format_var_label(-3.0) == "VAR 3\N{DEGREE SIGN}W"

    def test_zero_is_east_by_convention(self):
        assert format_var_label(0.0).endswith("E")

    def test_trailing_zeros_trimmed(self):
        assert format_var_label(7.0) == "VAR 7\N{DEGREE SIGN}E"

    def test_two_decimals_kept_when_present(self):
        assert format_var_label(-2.25) == "VAR 2.25\N{DEGREE SIGN}W"
