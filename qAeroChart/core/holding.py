# -*- coding: utf-8 -*-
"""
Nominal holding pattern geometry calculator.

Pure Python — no QGIS imports. Ported from qpansopy holding.py and wind_spiral.py.
All distances in nautical miles, angles in degrees (magnetic), coordinates in map CRS units.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple


class _Pt(NamedTuple):
    x: float
    y: float


@dataclass
class HoldingParameters:
    fix_x: float
    fix_y: float
    inbound_track: float   # bearing the aircraft flies TO the fix, degrees 0–360
    turn: str              # 'L' or 'R'
    ias_kt: float = 195.0
    altitude_ft: float = 10000.0
    isa_var: float = 0.0   # ISA temperature deviation, °C
    bank_deg: float = 25.0
    leg_min: float = 1.0


@dataclass
class HoldingResult:
    tas_kt: float
    rate_deg_s: float
    radius_nm: float
    leg_nm: float
    # Each segment: ('line'|'arc', [_Pt, ...])
    # 'line' → 2 points (straight leg), 'arc' → 3 points (circular arc: start, mid-ctrl, end)
    segments: list = field(default_factory=list)
    fix: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))
    outbound_pt: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))
    nominal0: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))
    nominal1: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))
    nominal2: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))
    nominal3: _Pt = field(default_factory=lambda: _Pt(0.0, 0.0))


def _offset(ox: float, oy: float, angle_deg: float, dist_nm: float) -> _Pt:
    """Offset a point by dist_nm nautical miles at angle_deg (math convention: 0°=+X, CCW)."""
    rad = math.radians(angle_deg)
    return _Pt(ox + dist_nm * 1852.0 * math.cos(rad),
               oy + dist_nm * 1852.0 * math.sin(rad))


def _tas_calc(ias: float, altitude_ft: float, isa_var: float, bank_deg: float):
    """Return (tas_kt, rate_deg_s, radius_nm) — original qpansopy / ICAO formula."""
    k = (171233.0
         * ((288.0 + isa_var - 0.00198 * altitude_ft) ** 0.5)
         / ((288.0 - 0.00198 * altitude_ft) ** 2.628))
    tas = k * ias
    rate = (3431.0 * math.tan(math.radians(bank_deg))) / (math.pi * tas)
    radius = tas / (20.0 * math.pi * rate)
    return tas, rate, radius


def build_holding(params: HoldingParameters) -> HoldingResult:
    """
    Compute the nominal holding racetrack geometry from HoldingParameters.

    Returns a HoldingResult whose `segments` list contains 4 entries that together
    trace the complete racetrack circuit:
      0 – inbound leg  (line:  outbound_pt → fix)
      1 – turn 1       (arc:   fix → nominal0)
      2 – outbound leg (line:  nominal0 → nominal2)
      3 – turn 2       (arc:   nominal2 → outbound_pt)
    """
    tas, rate, radius = _tas_calc(params.ias_kt, params.altitude_ft,
                                  params.isa_var, params.bank_deg)
    leg_nm = (tas / 3600.0) * (params.leg_min * 60.0)

    azimuth = float(params.inbound_track)
    # side: +90 → left turn (aircraft turns left off fix), −90 → right turn
    side = 90.0 if params.turn.upper() == 'L' else -90.0

    # Math-convention angles (0° = +X axis, CCW positive)
    angle_outbound = 90.0 - azimuth - 180.0
    angle_side = 90.0 - azimuth - side
    angle_mid_start = 90.0 - azimuth
    angle_mid_outbound = 90.0 - azimuth + 180.0

    fix = _Pt(params.fix_x, params.fix_y)

    outbound_pt = _offset(fix.x, fix.y, angle_outbound, leg_nm)

    nominal0 = _offset(fix.x, fix.y, angle_side, leg_nm)
    mid_top = _offset(fix.x, fix.y, angle_side, leg_nm / 2.0)
    nominal1 = _offset(mid_top.x, mid_top.y, angle_mid_start, leg_nm / 2.0)

    nominal2 = _offset(outbound_pt.x, outbound_pt.y, angle_side, leg_nm)
    mid_bot = _offset(outbound_pt.x, outbound_pt.y, angle_side, leg_nm / 2.0)
    nominal3 = _offset(mid_bot.x, mid_bot.y, angle_mid_outbound, leg_nm / 2.0)

    segments = [
        ('line', [outbound_pt, fix]),               # inbound leg
        ('arc',  [fix, nominal1, nominal0]),         # turn 1  (departure arc)
        ('line', [nominal0, nominal2]),              # outbound leg
        ('arc',  [nominal2, nominal3, outbound_pt]), # turn 2  (return arc)
    ]

    return HoldingResult(
        tas_kt=tas,
        rate_deg_s=rate,
        radius_nm=radius,
        leg_nm=leg_nm,
        segments=segments,
        fix=fix,
        outbound_pt=outbound_pt,
        nominal0=nominal0,
        nominal1=nominal1,
        nominal2=nominal2,
        nominal3=nominal3,
    )
