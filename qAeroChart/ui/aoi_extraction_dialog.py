# -*- coding: utf-8 -*-
"""
AOI extraction dialog (Issue #111).

Asks the user where the extracted AOI features should go — temporary
memory layers or a GeoPackage — before the extraction runs. Mirrors the
contributor script's storage-choice step as a proper dialog.
"""
from __future__ import annotations

import os

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsProject
from qgis.utils import iface

from ..core.aoi_extractor import GROUP_NAME


class AoiExtractionDialog(QtWidgets.QDialog):
    """Storage-choice dialog for the AOI extraction flow."""

    DEST_MEMORY = "memory"
    DEST_GPKG = "gpkg"

    def __init__(self, parent=None):
        _fallback = iface.mainWindow() if iface else None
        super().__init__(parent or _fallback)
        self.setWindowTitle("Extract AOI Features")
        self.setObjectName("AoiExtractionDialog")
        self.setMinimumWidth(420)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QLabel(
            f"Copies every feature inside the current map extent into "
            f"'{GROUP_NAME}' layers, leaving source data untouched."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        dest_group = QGroupBox("Destination")
        dest_layout = QVBoxLayout(dest_group)

        self.radio_memory = QRadioButton(
            "Temporary memory layers (lost when project closes)"
        )
        self.radio_gpkg = QRadioButton("GeoPackage (.gpkg)")
        self.radio_memory.setChecked(True)
        dest_layout.addWidget(self.radio_memory)
        dest_layout.addWidget(self.radio_gpkg)
        layout.addWidget(dest_group)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("GeoPackage:"))
        self.edit_gpkg_path = QLineEdit()
        self.edit_gpkg_path.setPlaceholderText("Choose destination .gpkg file…")
        self.btn_browse = QPushButton("Browse…")
        path_row.addWidget(self.edit_gpkg_path)
        path_row.addWidget(self.btn_browse)
        layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_extract = QPushButton("Extract")
        self.btn_extract.setStyleSheet(
            "font-weight: bold; background-color: #00557f; color: white; padding: 6px;"
        )
        self.btn_cancel = QPushButton("Cancel")
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_extract)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.setLayout(layout)

        self._connect_signals()
        self._sync_path_enabled()

    def _connect_signals(self):
        self.radio_memory.toggled.connect(self._sync_path_enabled)
        self.btn_browse.clicked.connect(self._browse_gpkg)
        self.btn_extract.clicked.connect(self._on_accept)
        self.btn_cancel.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------

    def _sync_path_enabled(self) -> None:
        is_gpkg = self.radio_gpkg.isChecked()
        self.edit_gpkg_path.setEnabled(is_gpkg)
        self.btn_browse.setEnabled(is_gpkg)

    def _suggested_gpkg_name(self) -> str:
        project_file = QgsProject.instance().fileName()
        project_name = (
            os.path.splitext(os.path.basename(project_file))[0]
            if project_file else "Untitled_Project"
        )
        return f"{project_name}_extracted_qa.gpkg"

    def _browse_gpkg(self) -> None:
        start_dir = os.path.join(os.path.expanduser("~"), self._suggested_gpkg_name())
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Destination GeoPackage", start_dir, "GeoPackage (*.gpkg)"
        )
        if path:
            if not path.lower().endswith(".gpkg"):
                path += ".gpkg"
            self.edit_gpkg_path.setText(path)

    def _on_accept(self) -> None:
        if self.get_dest() == self.DEST_GPKG and not self.get_gpkg_path():
            self.edit_gpkg_path.setFocus()
            return
        self.accept()

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def get_dest(self) -> str:
        return self.DEST_GPKG if self.radio_gpkg.isChecked() else self.DEST_MEMORY

    def get_gpkg_path(self) -> str:
        return self.edit_gpkg_path.text().strip()
