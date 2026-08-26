"""Unit tests for gs_rod_calculator — Issue #73."""
import pytest
from qAeroChart.core.gs_rod_calculator import (
    GsRodConfig,
    compute_timing,
    compute_rod,
    compute_table,
    DEFAULT_GS_VALUES,
)


# ── Timing formula ─────────────────────────────────────────────────────────────

class TestTimingFormula:
    """Verify compute_timing against Image 1 expected values (5.2 NM)."""

    DISTANCE = 5.2

    @pytest.mark.parametrize("gs, expected", [
        (70,  "04:27"),
        (90,  "03:28"),
        (100, "03:07"),
        (120, "02:36"),
        (140, "02:14"),
        (160, "01:57"),
    ])
    def test_image1_values(self, gs, expected):
        assert compute_timing(self.DISTANCE, gs) == expected


class TestTimingFormulaImage2:
    """Verify compute_timing against Image 2 expected values (4.8 NM)."""

    DISTANCE = 4.8

    @pytest.mark.parametrize("gs, expected", [
        (90,  "03:12"),
        (100, "02:53"),
        (120, "02:24"),
        (140, "02:03"),
        (160, "01:48"),
    ])
    def test_image2_values(self, gs, expected):
        assert compute_timing(self.DISTANCE, gs) == expected


# ── ROD formula ────────────────────────────────────────────────────────────────

class TestRodFormula:
    """Verify compute_rod against Image 1 expected values (5.3 %)."""

    GRADIENT = 5.3

    @pytest.mark.parametrize("gs, expected", [
        (70,  375),
        (90,  482),
        (100, 536),
        (120, 643),
        (140, 750),
        (160, 857),
    ])
    def test_image1_values(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT) == expected


class TestRodFormulaMonotonicity:
    """ROD increases with both GS and gradient."""

    def test_increases_with_gs(self):
        gradient = 5.3
        values = [compute_rod(gs, gradient) for gs in DEFAULT_GS_VALUES]
        assert values == sorted(values)

    def test_increases_with_gradient(self):
        gs = 100
        assert compute_rod(gs, 3.0) < compute_rod(gs, 5.0) < compute_rod(gs, 7.0)


class TestRodFormulaNoRoundingDefault:
    """round_step=0 (the default) must reproduce today's exact behaviour."""

    GRADIENT = 5.3

    @pytest.mark.parametrize("gs, expected", [
        (70, 375), (90, 482), (100, 536),
        (120, 643), (140, 750), (160, 857),
    ])
    def test_default_round_step_matches_unrounded(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT) == expected
        assert compute_rod(gs, self.GRADIENT, round_step=0) == expected
        assert compute_rod(gs, self.GRADIENT, round_step=0, round_mode="up") == expected


class TestRodFormulaRounding:
    """Rounding to 5 or 10, in 'nearest' and 'up' modes.

    Base (unrounded) values for gradient=5.3:
    gs=70->375, gs=90->482, gs=100->536, gs=120->643, gs=140->750, gs=160->857
    """

    GRADIENT = 5.3

    @pytest.mark.parametrize("gs, expected", [
        (70, 375), (90, 480), (100, 535),
        (120, 645), (140, 750), (160, 855),
    ])
    def test_round_step_5_nearest(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT, round_step=5, round_mode="nearest") == expected

    @pytest.mark.parametrize("gs, expected", [
        (70, 375), (90, 485), (100, 540),
        (120, 645), (140, 750), (160, 860),
    ])
    def test_round_step_5_up(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT, round_step=5, round_mode="up") == expected

    @pytest.mark.parametrize("gs, expected", [
        (70, 380), (90, 480), (100, 540),
        (120, 640), (140, 750), (160, 860),
    ])
    def test_round_step_10_nearest(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT, round_step=10, round_mode="nearest") == expected

    @pytest.mark.parametrize("gs, expected", [
        (70, 380), (90, 490), (100, 540),
        (120, 650), (140, 750), (160, 860),
    ])
    def test_round_step_10_up(self, gs, expected):
        assert compute_rod(gs, self.GRADIENT, round_step=10, round_mode="up") == expected

    def test_step_10_nearest_tie_rounds_up(self):
        # gs=70 -> 375, remainder=5 vs step=10 -> exact tie, must round up to 380
        assert compute_rod(70, self.GRADIENT, round_step=10, round_mode="nearest") == 380


# ── compute_table structure ────────────────────────────────────────────────────

class TestComputeTableWithTitle:
    """Table with title row, no footer."""

    @pytest.fixture
    def cfg(self):
        return GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="")

    def test_row_count(self, cfg):
        rows = compute_table(cfg)
        # title + header + timing + rod = 4
        assert len(rows) == 4

    def test_title_in_first_col(self, cfg):
        rows = compute_table(cfg)
        assert rows[0][0] == "Rate of Descent"

    def test_title_row_rest_empty(self, cfg):
        rows = compute_table(cfg)
        assert all(v == "" for v in rows[0][1:])

    def test_header_row_structure(self, cfg):
        rows = compute_table(cfg)
        header = rows[1]
        assert header[0] == "Ground Speed"
        assert header[1] == "KT"
        assert header[2] == "70"

    def test_timing_row_label(self, cfg):
        rows = compute_table(cfg)
        assert "5.2" in rows[2][0]

    def test_rod_row_label(self, cfg):
        rows = compute_table(cfg)
        assert "5.3" in rows[3][0]

    def test_timing_values_correct(self, cfg):
        rows = compute_table(cfg)
        timing_row = rows[2]
        assert timing_row[2] == "04:27"  # 70 kt
        assert timing_row[7] == "01:57"  # 160 kt

    def test_rod_values_correct(self, cfg):
        rows = compute_table(cfg)
        rod_row = rows[3]
        assert rod_row[2] == "375"  # 70 kt
        assert rod_row[7] == "857"  # 160 kt


class TestComputeTableWithFooter:
    """Table with title row AND footer row."""

    @pytest.fixture
    def cfg(self):
        return GsRodConfig(
            distance_nm=4.8, gradient_pct=5.0,
            title="Rate of Descent",
            footer="Timing not authorized for defining the MAPt",
        )

    def test_row_count(self, cfg):
        rows = compute_table(cfg)
        # title + header + timing + rod + footer = 5
        assert len(rows) == 5

    def test_footer_in_last_row(self, cfg):
        rows = compute_table(cfg)
        assert "Timing not authorized" in rows[-1][0]

    def test_footer_rest_empty(self, cfg):
        rows = compute_table(cfg)
        assert all(v == "" for v in rows[-1][1:])


class TestComputeTableNoTitleNoFooter:
    """Minimal table: no title, no footer."""

    @pytest.fixture
    def cfg(self):
        return GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="", footer="")

    def test_row_count(self, cfg):
        rows = compute_table(cfg)
        # header + timing + rod = 3
        assert len(rows) == 3

    def test_first_row_is_header(self, cfg):
        rows = compute_table(cfg)
        assert rows[0][0] == "Ground Speed"

    def test_column_count(self, cfg):
        rows = compute_table(cfg)
        expected_cols = len(DEFAULT_GS_VALUES) + 2  # label + unit + gs columns
        for row in rows:
            assert len(row) == expected_cols


class TestCustomGsValues:
    """Table with different GS column list (Image 2 style)."""

    @pytest.fixture
    def cfg(self):
        return GsRodConfig(
            distance_nm=4.8, gradient_pct=5.0,
            gs_values=(90, 100, 120, 140, 160),
            title="",
            footer="",
        )

    def test_column_count(self, cfg):
        rows = compute_table(cfg)
        assert len(rows[0]) == 7  # label + unit + 5 GS values

    def test_first_gs_header(self, cfg):
        rows = compute_table(cfg)
        assert rows[0][2] == "90"


class TestCustomLabels:
    """Explicit label_timing and label_rod are used as-is."""

    def test_explicit_labels(self):
        cfg = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3,
            label_timing="FAF-MAPt 5.2NM",
            label_rod="Rate of Descent 5.3%",
            title="",
            footer="",
        )
        rows = compute_table(cfg)
        assert rows[1][0] == "FAF-MAPt 5.2NM"
        assert rows[2][0] == "Rate of Descent 5.3%"


class TestDefaultGsValues:
    def test_default_gs_values(self):
        assert DEFAULT_GS_VALUES == (70, 90, 100, 120, 140, 160)


# ── Row order (Issue #120) ──────────────────────────────────────────────────

class TestComputeTableRowOrder:
    """rod_first controls whether the timing or ROD row renders first."""

    def test_default_order_timing_first(self):
        cfg = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent")
        rows = compute_table(cfg)
        assert "FAF-MAPt" in rows[2][0]
        assert "Rate of Descent" in rows[3][0]

    def test_rod_first_swaps_order_with_title(self):
        cfg = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", rod_first=True,
        )
        rows = compute_table(cfg)
        assert "Rate of Descent" in rows[2][0]
        assert "FAF-MAPt" in rows[3][0]

    def test_rod_first_swaps_order_no_title(self):
        cfg = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="", rod_first=True)
        rows = compute_table(cfg)
        assert "Rate of Descent" in rows[1][0]
        assert "FAF-MAPt" in rows[2][0]

    def test_rod_first_preserves_row_values(self):
        """Swapping order must not change the computed values, only their position."""
        cfg_default = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="")
        cfg_rod_first = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="", rod_first=True)
        rows_default = compute_table(cfg_default)
        rows_rod_first = compute_table(cfg_rod_first)
        assert rows_default[1] == rows_rod_first[2]  # timing row unchanged
        assert rows_default[2] == rows_rod_first[1]  # rod row unchanged

    def test_row_count_unaffected(self):
        cfg_default = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="note",
        )
        cfg_rod_first = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="note",
            rod_first=True,
        )
        assert len(compute_table(cfg_default)) == len(compute_table(cfg_rod_first))


# ── ROD rounding propagation (Issue #116) ───────────────────────────────────────

class TestComputeTableRoundingPropagation:
    """round_step/round_mode must affect only the ROD row, not timing or structure."""

    def test_rod_row_rounded_timing_row_untouched(self):
        cfg_plain = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="")
        cfg_rounded = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="",
            round_step=10, round_mode="up",
        )
        rows_plain = compute_table(cfg_plain)
        rows_rounded = compute_table(cfg_rounded)

        # Row 0 = header, row 1 = timing, row 2 = rod (title="" so no title row)
        assert rows_plain[1] == rows_rounded[1]  # timing row unaffected by rounding
        assert rows_plain[2] != rows_rounded[2]  # rod row values changed

        rod_row = rows_rounded[2]
        assert rod_row[2:] == ["380", "490", "540", "650", "750", "860"]

    def test_round_step_zero_preserves_row_values(self):
        cfg_default = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="")
        cfg_explicit_zero = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="", round_step=0, round_mode="up",
        )
        assert compute_table(cfg_default) == compute_table(cfg_explicit_zero)

    def test_row_count_and_structure_unaffected_by_rounding(self):
        cfg_plain = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="note",
        )
        cfg_rounded = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="note",
            round_step=5, round_mode="nearest",
        )
        rows_plain = compute_table(cfg_plain)
        rows_rounded = compute_table(cfg_rounded)
        assert len(rows_plain) == len(rows_rounded)
        assert len(rows_plain[0]) == len(rows_rounded[0])
        assert rows_plain[0] == rows_rounded[0]   # title row unaffected
        assert rows_plain[1] == rows_rounded[1]   # header row unaffected
        assert rows_plain[2] == rows_rounded[2]   # timing row unaffected
        assert rows_plain[-1] == rows_rounded[-1]  # footer row unaffected


# ── show_timing toggle (Issue #117) ──────────────────────────────────────────

class TestComputeTableShowTiming:
    """show_timing controls whether the FAF-MAPt row renders at all (Issue #117)."""

    def test_default_show_timing_is_true(self):
        assert GsRodConfig(distance_nm=5.2, gradient_pct=5.3).show_timing is True

    def test_show_timing_true_includes_timing_row(self):
        cfg = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="")
        rows = compute_table(cfg)
        assert len(rows) == 3  # header + timing + rod
        assert "FAF-MAPt" in rows[1][0]
        assert "Rate of Descent" in rows[2][0]

    def test_show_timing_false_omits_timing_row(self):
        cfg = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="", show_timing=False)
        rows = compute_table(cfg)
        assert len(rows) == 2  # header + rod only
        assert rows[0][0] == "Ground Speed"
        assert "Rate of Descent" in rows[1][0]

    def test_show_timing_false_rod_row_values_unaffected(self):
        cfg_with = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="")
        cfg_without = GsRodConfig(distance_nm=5.2, gradient_pct=5.3, title="", show_timing=False)
        rows_with = compute_table(cfg_with)
        rows_without = compute_table(cfg_without)
        assert rows_with[2] == rows_without[1]  # same ROD row content, different position

    def test_show_timing_false_with_title_and_footer(self):
        cfg = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="Rate of Descent", footer="note",
            show_timing=False,
        )
        rows = compute_table(cfg)
        assert len(rows) == 4  # title + header + rod + footer
        assert rows[0][0] == "Rate of Descent"
        assert rows[-1][0] == "note"

    def test_show_timing_false_rod_first_has_no_effect(self):
        cfg_a = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="", show_timing=False, rod_first=False,
        )
        cfg_b = GsRodConfig(
            distance_nm=5.2, gradient_pct=5.3, title="", show_timing=False, rod_first=True,
        )
        assert compute_table(cfg_a) == compute_table(cfg_b)
