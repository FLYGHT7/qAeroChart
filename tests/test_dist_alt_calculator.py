"""Unit tests for dist_alt_calculator — Issue #99, Issue #119."""
from dataclasses import replace

import pytest

from qAeroChart.core.dist_alt_calculator import (
    DistAltConfig,
    compute_steps,
    compute_summary,
    compute_table,
    round_altitude,
    steps_to_numeric_columns,
)

# Reference example from pansops-calculator docs/plan-136-dist-alt-calculator.md:
# FAF 6000 ft, THR/MAPt 1922 ft, distance 12.2 NM, TCH 49 ft, OCA 2450 ft.
REFERENCE_CFG = DistAltConfig(
    faf_altitude_ft=6000,
    thr_elevation_ft=1922,
    faf_thr_distance_nm=12.2,
    tch_rdh_ft=49,
    oca_ft=2450,
)


class TestSummary:
    def test_reference_example(self):
        summary = compute_summary(REFERENCE_CFG)
        assert summary["gradient_pct"] == pytest.approx(5.44, abs=0.01)
        assert summary["vpa_deg"] == pytest.approx(3.11, abs=0.01)
        assert summary["height_loss_per_mile_ft"] == 330


class TestSteps:
    def test_row_d12(self):
        steps = compute_steps(REFERENCE_CFG)
        row = next(s for s in steps if s.distance_label == "12")
        assert row.calculated_altitude_ft == pytest.approx(5933.95, abs=0.01)
        assert row.publication_altitude_ft == 5940
        assert row.calculated_height_ft == 4018

    def test_row_d0_equals_threshold_plus_tch(self):
        steps = compute_steps(REFERENCE_CFG)
        row = next(s for s in steps if s.distance_label == "0")
        assert row.calculated_altitude_ft == pytest.approx(
            REFERENCE_CFG.thr_elevation_ft + REFERENCE_CFG.tch_rdh_ft, abs=0.01
        )

    def test_row_count_matches_floor_distance_plus_one(self):
        steps = compute_steps(REFERENCE_CFG)
        assert len(steps) == 13  # floor(12.2) + 1 == 12 + 1

    def test_below_oca_advisory(self):
        cfg = DistAltConfig(
            faf_altitude_ft=3000,
            thr_elevation_ft=1922,
            faf_thr_distance_nm=10,
            tch_rdh_ft=49,
            oca_ft=2900,
        )
        steps = compute_steps(cfg)
        assert any(s.advisory_altitude == "below OCA" for s in steps)
        assert any(s.advisory_altitude != "below OCA" for s in steps)

    def test_offset_filters_non_positive_display_distance(self):
        cfg = DistAltConfig(
            faf_altitude_ft=6000,
            thr_elevation_ft=1922,
            faf_thr_distance_nm=12.2,
            tch_rdh_ft=49,
            oca_ft=2450,
            offset_enabled=True,
            offset_distance_nm=2.0,
        )
        steps = compute_steps(cfg)
        # d=0,1,2 dropped (display distance <= 0); d=2 -> 0.0 also dropped
        assert all(float(s.distance_label) > 0 for s in steps)
        assert len(steps) == 10  # d=3..12 survive


class TestStepsToNumericColumns:
    def test_maps_distance_label_to_publication_altitude(self):
        steps = compute_steps(REFERENCE_CFG)
        numeric = steps_to_numeric_columns(steps)
        assert numeric["12"] == "5940"
        assert numeric["0"] == str(next(s.publication_altitude_ft for s in steps if s.distance_label == "0"))


class TestComputeTable:
    def test_header_and_row_count(self):
        rows = compute_table(REFERENCE_CFG)
        assert rows[0][0] == "Distance from MAPt (NM)"
        assert len(rows) == 1 + 13  # header + 13 data rows

    def test_title_row_optional(self):
        rows = compute_table(REFERENCE_CFG, title="CDFA Table")
        assert rows[0] == ["CDFA Table", "", "", "", ""]
        assert rows[1][0] == "Distance from MAPt (NM)"


class TestValidation:
    def test_zero_distance_raises(self):
        cfg = DistAltConfig(
            faf_altitude_ft=6000,
            thr_elevation_ft=1922,
            faf_thr_distance_nm=0,
            tch_rdh_ft=49,
            oca_ft=2450,
        )
        with pytest.raises(ValueError):
            compute_summary(cfg)

    def test_negative_offset_raises(self):
        cfg = DistAltConfig(
            faf_altitude_ft=6000,
            thr_elevation_ft=1922,
            faf_thr_distance_nm=12.2,
            tch_rdh_ft=49,
            oca_ft=2450,
            offset_enabled=True,
            offset_distance_nm=-1,
        )
        with pytest.raises(ValueError):
            compute_steps(cfg)


class TestRoundAltitudeNoRoundingDefault:
    def test_zero_step_returns_value_unchanged(self):
        assert round_altitude(5933.95, round_step=0) == 5933.95

    def test_default_args_no_rounding(self):
        assert round_altitude(5933.95) == 5933.95

    def test_round_mode_ignored_when_step_zero(self):
        assert round_altitude(5933.95, round_step=0, round_mode="up") == 5933.95

    def test_reference_row_d12_unaffected_by_default_config(self):
        steps = compute_steps(REFERENCE_CFG)
        row = next(s for s in steps if s.distance_label == "12")
        assert row.calculated_altitude_ft == pytest.approx(5933.95, abs=0.01)
        assert row.publication_altitude_ft == 5940


class TestRoundAltitudeRounding:
    @pytest.mark.parametrize(
        "round_step, round_mode, expected",
        [
            (5, "nearest", 5935.0),
            (5, "up", 5935.0),
            (10, "nearest", 5930.0),
            (10, "up", 5940.0),
        ],
    )
    def test_rounding_cases(self, round_step, round_mode, expected):
        assert round_altitude(5933.95, round_step, round_mode) == pytest.approx(expected, abs=0.01)

    def test_exact_tie_rounds_up(self):
        assert round_altitude(1005.0, round_step=10, round_mode="nearest") == 1010.0
        assert round_altitude(1002.5, round_step=5, round_mode="nearest") == 1005.0


class TestComputeStepsRoundingPropagation:
    def test_publication_altitude_derived_from_rounded_value(self):
        cfg_rounded = replace(REFERENCE_CFG, round_step=10, round_mode="nearest")
        steps_plain = compute_steps(REFERENCE_CFG)
        steps_rounded = compute_steps(cfg_rounded)
        assert len(steps_plain) == len(steps_rounded)

        row_plain = next(s for s in steps_plain if s.distance_label == "12")
        row_rounded = next(s for s in steps_rounded if s.distance_label == "12")

        assert row_plain.publication_altitude_ft == 5940
        assert row_rounded.calculated_altitude_ft == pytest.approx(5930.0, abs=0.01)
        assert row_rounded.publication_altitude_ft == 5930

    def test_up_mode_matches_ceiling_publication_altitude(self):
        cfg_rounded = replace(REFERENCE_CFG, round_step=10, round_mode="up")
        row = next(s for s in compute_steps(cfg_rounded) if s.distance_label == "12")
        assert row.calculated_altitude_ft == pytest.approx(5940.0, abs=0.01)
        assert row.publication_altitude_ft == 5940


class TestAdvisoryAltitudeRoundingSideEffect:
    def test_rounding_flips_advisory_across_oca(self):
        cfg_plain = replace(REFERENCE_CFG, oca_ft=5935)
        cfg_rounded = replace(REFERENCE_CFG, oca_ft=5935, round_step=10, round_mode="nearest")

        row_plain = next(s for s in compute_steps(cfg_plain) if s.distance_label == "12")
        row_rounded = next(s for s in compute_steps(cfg_rounded) if s.distance_label == "12")

        assert row_plain.publication_altitude_ft == 5940
        assert row_plain.advisory_altitude != "below OCA"

        assert row_rounded.publication_altitude_ft == 5930
        assert row_rounded.advisory_altitude == "below OCA"


class TestComputeTableRoundingFormatting:
    def test_rounded_whole_number_still_formatted_with_two_decimals(self):
        cfg_rounded = replace(REFERENCE_CFG, round_step=10, round_mode="up")
        rows = compute_table(cfg_rounded)
        row_12 = next(r for r in rows if r[0] == "12")
        assert row_12[1] == "5940.00"

    def test_row_and_column_count_unaffected_by_rounding(self):
        cfg_rounded = replace(REFERENCE_CFG, round_step=10, round_mode="nearest")
        rows_plain = compute_table(REFERENCE_CFG)
        rows_rounded = compute_table(cfg_rounded)
        assert len(rows_plain) == len(rows_rounded)
        assert len(rows_plain[0]) == len(rows_rounded[0])
