"""Tests for Layout Designer toolbar attachment (issues #85, #86, #87).

Verifies that _attach_action_to_designer creates a dedicated 'qAeroChart tools'
toolbar on each Layout Designer window and handles edge cases gracefully.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest
import tests.mocks.qgis_mock  # noqa: F401

# Patch heavy QGIS-dependent imports before they are loaded, so we can import
# qaerochart.py without a real QGIS / Qt installation.
for _mod in (
    'qAeroChart.qaerochart_dockwidget',
    'qAeroChart.qaerochart_dockwidget_base',
    'qAeroChart.vertical_scale_dialog',
    'qAeroChart.vertical_scale_manager',
    'qAeroChart.core.layer_manager',
    'qAeroChart.core.profile_controller',
    'qAeroChart.core.profile_manager',
    'qAeroChart.core.layout_manager',
    'qAeroChart.tools',
    'qAeroChart.tools.profile_point_tool',
    'qAeroChart.tools.north_arrow_tool',
    'qAeroChart.north_arrow_dock',
):
    sys.modules.setdefault(_mod, MagicMock())

# Make QToolBar() return a NEW MagicMock on every call so tests don't
# share the same mock instance and accumulate call counts.
from qgis.PyQt.QtWidgets import QToolBar as _QToolBarMock  # noqa: E402
_QToolBarMock.side_effect = lambda *a, **kw: MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeDesigner:
    """Minimal designer-interface stub whose window() returns a fixed mock."""

    def __init__(self, window: MagicMock | None = None) -> None:
        self._window = window if window is not None else MagicMock()
        # Ensure menuBar().actions() returns an empty list so the Settings
        # lookup loop in _attach_action_to_designer completes gracefully.
        self._window.menuBar().actions.return_value = []

    def window(self) -> MagicMock | None:
        return self._window


def _make_plugin() -> types.SimpleNamespace:
    """Return a bare-minimum plugin namespace with only layout-toolbar state."""
    p = types.SimpleNamespace()
    # State attributes
    p._layout_toolbars = []
    p._layout_toolbar_windows = set()
    p._layout_menus = []
    # Actions
    p.distance_table_action = MagicMock(name="distance_table_action")
    p.gs_rod_action = MagicMock(name="gs_rod_action")
    p.oca_h_table_action = MagicMock(name="oca_h_table_action")
    p.dist_alt_calculator_action = MagicMock(name="dist_alt_calculator_action")
    # tr() just returns its argument
    p.tr = lambda s: s
    # Bind the real method from qaerochart.py without constructing the full plugin
    from qAeroChart.qaerochart import QAeroChart
    p._attach_action_to_designer = QAeroChart._attach_action_to_designer.__get__(p, type(p))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAttachActionToDesigner:
    def test_toolbar_created_on_first_attach(self):
        """After one attach call, _layout_toolbars should have one entry."""
        plugin = _make_plugin()
        designer = FakeDesigner()
        plugin._attach_action_to_designer(designer)
        assert len(plugin._layout_toolbars) == 1

    def test_idempotent_same_window(self):
        """Calling attach twice with the same window must not create a duplicate toolbar."""
        plugin = _make_plugin()
        designer = FakeDesigner()
        plugin._attach_action_to_designer(designer)
        plugin._attach_action_to_designer(designer)
        assert len(plugin._layout_toolbars) == 1

    def test_second_window_gets_own_toolbar(self):
        """Two different designer windows must each get their own toolbar."""
        plugin = _make_plugin()
        plugin._attach_action_to_designer(FakeDesigner())
        plugin._attach_action_to_designer(FakeDesigner())
        assert len(plugin._layout_toolbars) == 2

    def test_toolbar_has_four_actions(self):
        """The created toolbar must receive addAction calls for all four actions."""
        plugin = _make_plugin()
        designer = FakeDesigner()
        plugin._attach_action_to_designer(designer)
        toolbar = plugin._layout_toolbars[0]
        # addAction was called four times: distance, gs_rod, oca_h, dist_alt_calculator
        assert toolbar.addAction.call_count == 4
        toolbar.addAction.assert_any_call(plugin.distance_table_action)
        toolbar.addAction.assert_any_call(plugin.gs_rod_action)
        toolbar.addAction.assert_any_call(plugin.oca_h_table_action)
        toolbar.addAction.assert_any_call(plugin.dist_alt_calculator_action)

    def test_toolbar_added_to_window(self):
        """The designer window must have addToolBar called with the new toolbar."""
        plugin = _make_plugin()
        window = MagicMock()
        designer = FakeDesigner(window=window)
        plugin._attach_action_to_designer(designer)
        toolbar = plugin._layout_toolbars[0]
        window.addToolBar.assert_called_once_with(toolbar)

    def test_toolbar_object_name(self):
        """The toolbar is given the expected object name."""
        plugin = _make_plugin()
        designer = FakeDesigner()
        plugin._attach_action_to_designer(designer)
        toolbar = plugin._layout_toolbars[0]
        toolbar.setObjectName.assert_called_once_with('qAeroChartLayoutToolbar')

    def test_no_op_when_designer_is_none(self):
        """Passing None must not raise and must leave _layout_toolbars unchanged."""
        plugin = _make_plugin()
        plugin._attach_action_to_designer(None)
        assert len(plugin._layout_toolbars) == 0

    def test_no_op_when_window_is_none(self):
        """A designer whose window() returns None must not raise."""
        plugin = _make_plugin()
        designer = FakeDesigner()
        designer.window = lambda: None
        plugin._attach_action_to_designer(designer)
        assert len(plugin._layout_toolbars) == 0

    def test_skips_none_actions(self):
        """If an action is None it is not passed to addAction."""
        plugin = _make_plugin()
        plugin.gs_rod_action = None
        designer = FakeDesigner()
        plugin._attach_action_to_designer(designer)
        toolbar = plugin._layout_toolbars[0]
        assert toolbar.addAction.call_count == 3
        toolbar.addAction.assert_any_call(plugin.distance_table_action)
        toolbar.addAction.assert_any_call(plugin.oca_h_table_action)
        toolbar.addAction.assert_any_call(plugin.dist_alt_calculator_action)

    def test_window_id_tracked(self):
        """After attaching, the window id must appear in _layout_toolbar_windows."""
        plugin = _make_plugin()
        window = MagicMock()
        designer = FakeDesigner(window=window)
        plugin._attach_action_to_designer(designer)
        assert id(window) in plugin._layout_toolbar_windows

    def test_unload_clears_state(self):
        """Simulating the unload cleanup clears both list and set."""
        plugin = _make_plugin()
        plugin._attach_action_to_designer(FakeDesigner())
        plugin._attach_action_to_designer(FakeDesigner())
        assert len(plugin._layout_toolbars) == 2
        assert len(plugin._layout_toolbar_windows) == 2
        assert len(plugin._layout_menus) == 2

        # Simulate unload clean-up
        for toolbar in plugin._layout_toolbars:
            try:
                toolbar.hide()
                toolbar.deleteLater()
            except Exception:
                pass
        plugin._layout_toolbars.clear()
        plugin._layout_toolbar_windows.clear()

        for menu in plugin._layout_menus:
            try:
                menu.parent().removeAction(menu.menuAction())
            except Exception:
                pass
        plugin._layout_menus.clear()

        assert len(plugin._layout_toolbars) == 0
        assert len(plugin._layout_toolbar_windows) == 0
        assert len(plugin._layout_menus) == 0
