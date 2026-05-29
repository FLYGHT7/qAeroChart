# -*- coding: utf-8 -*-
"""Unit tests for holding.py — pure math, no QGIS required."""
import math
import pytest

from qAeroChart.core.holding import (
    HoldingParameters,
    _offset,
    _tas_calc,
    build_holding,
)


# ---------------------------------------------------------------------------
# _tas_calc
# ---------------------------------------------------------------------------

class TestTasCalc:
    def test_reference_values(self):
        """Regression against qpansopy reference: IAS=195, alt=10000, isa=0, bank=25."""
        tas, rate, radius = _tas_calc(195.0, 10000.0, 0.0, 25.0)
        # TAS should be around 233–235 kt for these conditions
        assert 220.0 < tas < 250.0, f"TAS out of expected range: {tas}"
        assert rate > 0
        assert radius > 0

    def test_higher_altitude_increases_tas(self):
        _, _, _ = _tas_calc(195.0, 10000.0, 0.0, 25.0)
        tas_low, _, _ = _tas_calc(195.0, 5000.0, 0.0, 25.0)
        tas_high, _, _ = _tas_calc(195.0, 20000.0, 0.0, 25.0)
        assert tas_high > tas_low

    def test_bank_angle_does_not_affect_tas(self):
        tas1, rate1, radius1 = _tas_calc(195.0, 10000.0, 0.0, 15.0)
        tas2, rate2, radius2 = _tas_calc(195.0, 10000.0, 0.0, 30.0)
        assert abs(tas1 - tas2) < 0.001, "TAS should be independent of bank angle"
        assert rate2 > rate1, "Higher bank → higher rate of turn"
        assert radius1 > radius2, "Higher bank → tighter radius"

    def test_isa_positive_deviation_increases_tas(self):
        tas0, _, _ = _tas_calc(195.0, 10000.0, 0.0, 25.0)
        tas_hot, _, _ = _tas_calc(195.0, 10000.0, 15.0, 25.0)
        assert tas_hot > tas0


# ---------------------------------------------------------------------------
# _offset
# ---------------------------------------------------------------------------

class TestOffset:
    def test_east_offset(self):
        """angle=0° (east) with 1 NM should move +1852 m in X."""
        pt = _offset(0.0, 0.0, 0.0, 1.0)
        assert abs(pt.x - 1852.0) < 0.01
        assert abs(pt.y) < 0.01

    def test_north_offset(self):
        """angle=90° (north) with 1 NM should move +1852 m in Y."""
        pt = _offset(0.0, 0.0, 90.0, 1.0)
        assert abs(pt.x) < 0.01
        assert abs(pt.y - 1852.0) < 0.01

    def test_distance_scaling(self):
        pt1 = _offset(0.0, 0.0, 45.0, 1.0)
        pt2 = _offset(0.0, 0.0, 45.0, 2.0)
        assert abs(math.hypot(pt2.x, pt2.y) - 2 * math.hypot(pt1.x, pt1.y)) < 0.01


# ---------------------------------------------------------------------------
# build_holding
# ---------------------------------------------------------------------------

class TestBuildHolding:
    def _default_right(self, **kw) -> HoldingParameters:
        defaults = dict(
            fix_x=0.0, fix_y=0.0,
            inbound_track=180.0, turn='R',
            ias_kt=195.0, altitude_ft=10000.0,
            isa_var=0.0, bank_deg=25.0, leg_min=1.0,
        )
        defaults.update(kw)
        return HoldingParameters(**defaults)

    def test_returns_four_segments(self):
        r = build_holding(self._default_right())
        assert len(r.segments) == 4

    def test_segment_types(self):
        r = build_holding(self._default_right())
        types = [s[0] for s in r.segments]
        assert types == ['line', 'arc', 'line', 'arc']

    def test_segment_point_counts(self):
        r = build_holding(self._default_right())
        assert len(r.segments[0][1]) == 2  # inbound leg: 2 pts
        assert len(r.segments[1][1]) == 3  # turn 1: start, ctrl, end
        assert len(r.segments[2][1]) == 2  # outbound leg: 2 pts
        assert len(r.segments[3][1]) == 3  # turn 2: start, ctrl, end

    def test_inbound_leg_ends_at_fix(self):
        """The inbound leg (segment 0) should end at the fix point."""
        p = self._default_right(fix_x=100.0, fix_y=200.0)
        r = build_holding(p)
        inbound_end = r.segments[0][1][-1]
        assert abs(inbound_end.x - 100.0) < 0.01
        assert abs(inbound_end.y - 200.0) < 0.01

    def test_arc1_starts_at_fix(self):
        p = self._default_right(fix_x=100.0, fix_y=200.0)
        r = build_holding(p)
        arc1_start = r.segments[1][1][0]
        assert abs(arc1_start.x - 100.0) < 0.01
        assert abs(arc1_start.y - 200.0) < 0.01

    def test_circuit_is_closed(self):
        """The last segment (turn 2) should end back at outbound_pt (= start of inbound leg)."""
        r = build_holding(self._default_right())
        outbound_pt_from_seg0 = r.segments[0][1][0]
        arc2_end = r.segments[3][1][-1]
        assert abs(arc2_end.x - outbound_pt_from_seg0.x) < 0.01
        assert abs(arc2_end.y - outbound_pt_from_seg0.y) < 0.01

    def test_right_and_left_are_mirrored(self):
        """Left and right holdings should be symmetric around the inbound-track axis."""
        right = build_holding(self._default_right(inbound_track=0.0))
        left = build_holding(self._default_right(inbound_track=0.0, turn='L'))
        # The outbound leg points should be mirrored in X relative to the fix (x=0)
        assert abs(right.nominal0.x + left.nominal0.x) < 0.01

    def test_longer_leg_time_gives_longer_leg_nm(self):
        r1 = build_holding(self._default_right(leg_min=1.0))
        r2 = build_holding(self._default_right(leg_min=2.0))
        assert r2.leg_nm > r1.leg_nm

    def test_leg_nm_consistency(self):
        """Leg distance should match the straight-segment length."""
        r = build_holding(self._default_right())
        seg_pts = r.segments[2][1]
        dx = seg_pts[1].x - seg_pts[0].x
        dy = seg_pts[1].y - seg_pts[0].y
        seg_len_nm = math.hypot(dx, dy) / 1852.0
        assert abs(seg_len_nm - r.leg_nm) < 0.01

    def test_positive_results(self):
        r = build_holding(self._default_right())
        assert r.tas_kt > 0
        assert r.radius_nm > 0
        assert r.leg_nm > 0
        assert r.rate_deg_s > 0
