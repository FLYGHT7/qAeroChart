# -*- coding: utf-8 -*-
"""Unit tests for bearing_utils.py — pure math, no QGIS required (Issue #137)."""

from qAeroChart.core.bearing_utils import resolve_true_bearing


class TestResolveTrueBearing:
    def test_true_outbound_passthrough(self):
        brg = resolve_true_bearing(90.0, is_magnetic=False, mag_var_signed=0.0, is_inbound=False)
        assert brg == 90.0

    def test_magnetic_east_variation_adds(self):
        brg = resolve_true_bearing(90.0, is_magnetic=True, mag_var_signed=5.0, is_inbound=False)
        assert abs(brg - 95.0) < 1e-9

    def test_magnetic_west_variation_subtracts(self):
        brg = resolve_true_bearing(90.0, is_magnetic=True, mag_var_signed=-5.0, is_inbound=False)
        assert abs(brg - 85.0) < 1e-9

    def test_inbound_reverses_180(self):
        brg = resolve_true_bearing(0.0, is_magnetic=False, mag_var_signed=0.0, is_inbound=True)
        assert abs(brg - 180.0) < 1e-9

    def test_wraps_to_0_360(self):
        brg = resolve_true_bearing(350.0, is_magnetic=True, mag_var_signed=20.0, is_inbound=False)
        assert abs(brg - 10.0) < 1e-9
        assert 0.0 <= brg < 360.0
