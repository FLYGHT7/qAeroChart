"""
Compatibility shim that normalises PyQt5 / PyQt6 API differences.

QGIS ships PyQt5 via ``qgis.PyQt``.  When running outside QGIS (dev/test)
PyQt6 may be available.  This module re-exports Qt enum values under a
unified API so plugin code never needs ``if PyQt5 / elif PyQt6`` guards.

Usage::

    from qAeroChart.utils.qt_compat import Qt, QMessageBox, QAbstractItemView, QVariant
"""
from __future__ import annotations

try:
    # QGIS runtime — uses its own PyQt wrapper (PyQt5 in QGIS 3, PyQt6 in QGIS 4)
    from qgis.PyQt.QtCore import Qt as _Qt
    from qgis.PyQt.QtCore import QVariant as _QVariant_raw
    from qgis.PyQt.QtGui import QColor as _QColor
    from qgis.PyQt.QtGui import QFont as _QFont
    from qgis.PyQt.QtWidgets import QMessageBox as _QMessageBox
    from qgis.PyQt.QtWidgets import QAbstractItemView as _QAbstractItemView

    # In QGIS 4 / PyQt6, QVariant may import but lack .Int/.String/.Double/.Bool
    # (PyQt6 removed these type constants from the Python QVariant binding).
    # CRITICAL: PyQt6 uses strict enum checking — QgsField() requires actual
    # QMetaType.Type enum values, NOT plain integers. Passing int where
    # QMetaType.Type is expected raises TypeError in PyQt6.
    if hasattr(_QVariant_raw, 'Int') and hasattr(_QVariant_raw, 'String'):
        _QVariant = _QVariant_raw
    else:
        # QGIS 4 / PyQt6: obtain real QMetaType.Type enum members so QgsField works.
        try:
            from qgis.PyQt.QtCore import QMetaType as _QMetaType

            class _QVariant:  # type: ignore[no-redef]
                Int = _QMetaType.Type.Int
                Double = _QMetaType.Type.Double
                String = _QMetaType.Type.QString   # C++ name is QString, not String
                Bool = _QMetaType.Type.Bool
        except (ImportError, AttributeError):
            # Last-resort integer fallback (values match QMetaType::Type numerically)
            class _QVariant:  # type: ignore[no-redef]
                Int = 2
                Double = 6
                String = 10
                Bool = 1
except ImportError:
    try:
        from PyQt6.QtCore import Qt as _Qt  # type: ignore[no-redef]
        from PyQt6.QtGui import QColor as _QColor  # type: ignore[no-redef]
        from PyQt6.QtGui import QFont as _QFont  # type: ignore[no-redef]
        from PyQt6.QtWidgets import QMessageBox as _QMessageBox  # type: ignore[no-redef]
        from PyQt6.QtWidgets import QAbstractItemView as _QAbstractItemView  # type: ignore[no-redef]

        # PyQt6: QVariant not exposed. Use QMetaType.Type enum values (strict checking).
        try:
            from PyQt6.QtCore import QMetaType as _QMetaType6  # type: ignore[no-redef]

            class _QVariant:  # type: ignore[no-redef]
                Int = _QMetaType6.Type.Int
                Double = _QMetaType6.Type.Double
                String = _QMetaType6.Type.QString
                Bool = _QMetaType6.Type.Bool
        except (ImportError, AttributeError):
            class _QVariant:  # type: ignore[no-redef]
                Int = 2
                Double = 6
                String = 10
                Bool = 1
    except ImportError:
        from PyQt5.QtCore import Qt as _Qt  # type: ignore[no-redef]
        from PyQt5.QtCore import QVariant as _QVariant  # type: ignore[no-redef]
        from PyQt5.QtGui import QColor as _QColor  # type: ignore[no-redef]
        from PyQt5.QtGui import QFont as _QFont  # type: ignore[no-redef]
        from PyQt5.QtWidgets import QMessageBox as _QMessageBox  # type: ignore[no-redef]
        from PyQt5.QtWidgets import QAbstractItemView as _QAbstractItemView  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Qt namespace
# ---------------------------------------------------------------------------

class _QtCompat:
    """Normalised Qt namespace.

    In PyQt6 many constants moved into sub-enums (e.g. ``Qt.AlignmentFlag.AlignLeft``).
    This class exposes them under the PyQt5-compatible short names so the rest
    of the plugin code never needs to branch on the binding version.
    """

    # Item roles ---------------------------------------------------------------
    UserRole = getattr(_Qt, "UserRole", None) or _Qt.ItemDataRole.UserRole

    # Item flags ---------------------------------------------------------------
    ItemIsSelectable = (
        getattr(_Qt, "ItemIsSelectable", None)
        or _Qt.ItemFlag.ItemIsSelectable
    )

    ItemIsEditable = (
        getattr(_Qt, "ItemIsEditable", None)
        or _Qt.ItemFlag.ItemIsEditable
    )

    # Context menu policy -------------------------------------------------------
    CustomContextMenu = (
        getattr(_Qt, "CustomContextMenu", None)
        or _Qt.ContextMenuPolicy.CustomContextMenu
    )

    # Keyboard keys ------------------------------------------------------------
    Key_F2 = getattr(_Qt, "Key_F2", None) or _Qt.Key.Key_F2
    Key_Delete = getattr(_Qt, "Key_Delete", None) or _Qt.Key.Key_Delete

    # Mouse buttons ------------------------------------------------------------
    LeftButton = getattr(_Qt, "LeftButton", None) or _Qt.MouseButton.LeftButton

    # Cursor shapes ------------------------------------------------------------
    CrossCursor = getattr(_Qt, "CrossCursor", None) or _Qt.CursorShape.CrossCursor

    # Pen cap and join styles --------------------------------------------------
    FlatCap = getattr(_Qt, "FlatCap", None) or _Qt.PenCapStyle.FlatCap
    MiterJoin = getattr(_Qt, "MiterJoin", None) or _Qt.PenJoinStyle.MiterJoin

    # Dock widget areas --------------------------------------------------------
    RightDockWidgetArea = (
        getattr(_Qt, "RightDockWidgetArea", None)
        or _Qt.DockWidgetArea.RightDockWidgetArea
    )
    LeftDockWidgetArea = (
        getattr(_Qt, "LeftDockWidgetArea", None)
        or _Qt.DockWidgetArea.LeftDockWidgetArea
    )

    # Alignment flags ----------------------------------------------------------
    AlignLeft = getattr(_Qt, "AlignLeft", None) or _Qt.AlignmentFlag.AlignLeft
    AlignRight = getattr(_Qt, "AlignRight", None) or _Qt.AlignmentFlag.AlignRight
    AlignTop = getattr(_Qt, "AlignTop", None) or _Qt.AlignmentFlag.AlignTop
    AlignBottom = getattr(_Qt, "AlignBottom", None) or _Qt.AlignmentFlag.AlignBottom
    AlignHCenter = getattr(_Qt, "AlignHCenter", None) or _Qt.AlignmentFlag.AlignHCenter
    AlignVCenter = getattr(_Qt, "AlignVCenter", None) or _Qt.AlignmentFlag.AlignVCenter
    AlignCenter = getattr(_Qt, "AlignCenter", None) or _Qt.AlignmentFlag.AlignCenter

    # Window modality ----------------------------------------------------------
    NonModal = getattr(_Qt, "NonModal", None) or _Qt.WindowModality.NonModal


Qt = _QtCompat


# ---------------------------------------------------------------------------
# QMessageBox button constants + passthrough for the question() dialog
# ---------------------------------------------------------------------------

class _QMessageBoxCompat:
    """Normalised QMessageBox enum values.

    Also proxies ``question()`` so callers can use a single import for both
    the dialog call and the button-flag comparisons.
    """

    Yes = getattr(_QMessageBox, "Yes", None) or _QMessageBox.StandardButton.Yes
    No = getattr(_QMessageBox, "No", None) or _QMessageBox.StandardButton.No

    @staticmethod
    def question(parent, title: str, text: str, buttons=None, default=None):
        """Delegate to the real QMessageBox.question() static method."""
        return _QMessageBox.question(parent, title, text, buttons, default)


QMessageBox = _QMessageBoxCompat


# ---------------------------------------------------------------------------
# QAbstractItemView selection mode constants
# ---------------------------------------------------------------------------

class _QAbstractItemViewCompat:
    """Normalised QAbstractItemView enum values."""

    ExtendedSelection = (
        getattr(_QAbstractItemView, "ExtendedSelection", None)
        or _QAbstractItemView.SelectionMode.ExtendedSelection
    )

    AllEditTriggers = (
        getattr(_QAbstractItemView, "AllEditTriggers", None)
        or _QAbstractItemView.EditTrigger.AllEditTriggers
    )

    NoEditTriggers = (
        getattr(_QAbstractItemView, "NoEditTriggers", None)
        or _QAbstractItemView.EditTrigger.NoEditTriggers
    )


QAbstractItemView = _QAbstractItemViewCompat


# ---------------------------------------------------------------------------
# QVariant type codes
# ---------------------------------------------------------------------------

# In QGIS / PyQt5 this is the real QVariant class; in PyQt6 dev environments
# it is the integer-stub class defined above.  Either way the numeric values
# (Int=2, Double=6, String=10, Bool=1) are identical to what QgsField expects.

QVariant = _QVariant


# ---------------------------------------------------------------------------
# QgsUnitTypes compatibility (removed in QGIS 4 / Qt6)
# ---------------------------------------------------------------------------
# In QGIS 3 (Qt5): QgsUnitTypes.RenderMillimeters, QgsUnitTypes.DistanceMeters, etc.
# In QGIS 4 (Qt6): Qgis.RenderUnit.Millimeters, Qgis.DistanceUnit.Meters, etc.
# This shim resolves at import time so all callers can use a single name.

def _resolve_unit(qgis4_dotted: str, qgsunit_attr: str, fallback):
    """Resolve a unit constant for QGIS 3 and QGIS 4.

    qgis4_dotted: dotted path under ``Qgis``, e.g. ``'RenderUnit.Millimeters'``
    qgsunit_attr: attribute name on ``QgsUnitTypes``, e.g. ``'RenderMillimeters'``
    fallback:     raw int value used when neither import path works.
    """
    try:
        from qgis.core import Qgis as _Qgis
        parts = qgis4_dotted.split(".")
        obj = _Qgis
        for part in parts:
            obj = getattr(obj, part)
        return obj
    except Exception:
        pass
    try:
        from qgis.core import QgsUnitTypes as _QUT
        return getattr(_QUT, qgsunit_attr)
    except Exception:
        return fallback


class _QgsUnitTypesCompat:
    """Shim exposing QgsUnitTypes constants for both QGIS 3 and QGIS 4."""

    # Render units
    RenderMillimeters = _resolve_unit("RenderUnit.Millimeters", "RenderMillimeters", 3)
    RenderPixels = _resolve_unit("RenderUnit.Pixels", "RenderPixels", 2)
    RenderMapUnits = _resolve_unit("RenderUnit.MapUnits", "RenderMapUnits", 1)
    RenderPoints = _resolve_unit("RenderUnit.Points", "RenderPoints", 4)
    RenderInches = _resolve_unit("RenderUnit.Inches", "RenderInches", 5)
    RenderPercentage = _resolve_unit("RenderUnit.Percentage", "RenderPercentage", 7)

    # Distance units
    DistanceMeters = _resolve_unit("DistanceUnit.Meters", "DistanceMeters", 0)
    DistanceKilometers = _resolve_unit("DistanceUnit.Kilometers", "DistanceKilometers", 1)
    DistanceFeet = _resolve_unit("DistanceUnit.Feet", "DistanceFeet", 3)
    DistanceDegrees = _resolve_unit("DistanceUnit.Degrees", "DistanceDegrees", 4)
    DistanceUnknownUnit = _resolve_unit("DistanceUnit.Unknown", "DistanceUnknownUnit", 8)

    # Layout units
    LayoutMillimeters = _resolve_unit("LayoutUnit.Millimeters", "LayoutMillimeters", 0)
    LayoutCentimeters = _resolve_unit("LayoutUnit.Centimeters", "LayoutCentimeters", 1)
    LayoutMeters = _resolve_unit("LayoutUnit.Meters", "LayoutMeters", 2)
    LayoutInches = _resolve_unit("LayoutUnit.Inches", "LayoutInches", 3)
    LayoutPoints = _resolve_unit("LayoutUnit.Points", "LayoutPoints", 5)
    LayoutPixels = _resolve_unit("LayoutUnit.Pixels", "LayoutPixels", 6)


QgsUnitTypes = _QgsUnitTypesCompat


# ---------------------------------------------------------------------------
# QFont.Bold compatibility (moved to QFont.Weight.Bold in PyQt6)
# ---------------------------------------------------------------------------

def _font_bold_weight():
    """Return the bold weight constant compatible with PyQt5 and PyQt6."""
    try:
        return _QFont.Weight.Bold  # PyQt6
    except AttributeError:
        return _QFont.Bold  # PyQt5 — plain int 75


FontBold = _font_bold_weight()


# ---------------------------------------------------------------------------
# QColor / QFont — passthrough; same API in PyQt5 and PyQt6
# ---------------------------------------------------------------------------

QColor = _QColor
QFont = _QFont


# ---------------------------------------------------------------------------
# Qgis.MessageLevel compatibility (Qgis.Warning → Qgis.MessageLevel.Warning in QGIS 4)
# ---------------------------------------------------------------------------

def _resolve_msg_level(name: str, fallback_int: int):
    """Return the Qgis message-level enum value for *name*, QGIS 3 or 4."""
    try:
        from qgis.core import Qgis as _Qgis
        # QGIS 4: Qgis.MessageLevel.Warning etc.
        _ML = getattr(_Qgis, "MessageLevel", None)
        if _ML is not None:
            val = getattr(_ML, name, None)
            if val is not None:
                return val
        # QGIS 3: Qgis.Warning etc.
        val = getattr(_Qgis, name, None)
        if val is not None:
            return val
    except Exception:
        pass
    return fallback_int


class _MsgLevel:
    """Cross-version Qgis.MessageLevel constants.

    Safe to reference at module level — never raises AttributeError.
    Use ``MsgLevel.Success`` instead of ``Qgis.Success`` everywhere.
    """
    Info = _resolve_msg_level("Info", 0)
    Warning = _resolve_msg_level("Warning", 1)
    Critical = _resolve_msg_level("Critical", 2)
    Success = _resolve_msg_level("Success", 3)


MsgLevel = _MsgLevel
