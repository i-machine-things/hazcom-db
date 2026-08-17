"""Bulk import review dialog.

Runs auto-fill + duplicate detection across a batch of SDS PDFs (picked via a
file dialog or dropped onto the main window) and lets the user correct each
row before anything is written to the database.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import db, sds_parser

SIGNAL_WORDS = ["", "Danger", "Warning"]

COL_INCLUDE = 0
COL_FILENAME = 1
COL_PRODUCT = 2
COL_MANUFACTURER = 3
COL_CAS = 4
COL_REVISION = 5
COL_SIGNAL = 6
COL_FLAG = 7
COLUMN_LABELS = [
    "Import", "File", "Product Name", "Manufacturer", "CAS Number(s)",
    "Revision Date", "Signal Word", "Flag",
]


class ImportDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        departments: list[sqlite3.Row],
        file_paths: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self.conn = conn
        self._file_paths = file_paths
        self.setWindowTitle(f"Import {len(file_paths)} SDS File(s)")
        self.resize(900, 500)

        self._build_ui(departments)
        self._populate_rows()

    def _build_ui(self, departments: list[sqlite3.Row]) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Review the auto-filled fields below before importing "
                "(some fields may be blank or wrong — SDS PDFs vary). "
                "Uncheck any file you don't want to import."
            )
        )

        self.table = QTableWidget(len(self._file_paths), len(COLUMN_LABELS))
        self.table.setHorizontalHeaderLabels(COLUMN_LABELS)
        self.table.horizontalHeader().setSectionResizeMode(
            COL_PRODUCT, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        layout.addWidget(QLabel("Tag all imported sheets with:"))
        self.department_list = QListWidget()
        for row in departments:
            item = QListWidgetItem(row["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.department_list.addItem(item)
        self.department_list.setMaximumHeight(100)
        layout.addWidget(self.department_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_rows(self) -> None:
        for row_index, path_str in enumerate(self._file_paths):
            path = Path(path_str)
            fields = sds_parser.extract_fields(path)
            product_name = fields.get("product_name") or path.stem

            include_item = QTableWidgetItem()
            include_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            include_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row_index, COL_INCLUDE, include_item)

            filename_item = QTableWidgetItem(path.name)
            filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, COL_FILENAME, filename_item)

            self.table.setItem(row_index, COL_PRODUCT, QTableWidgetItem(product_name))
            self.table.setItem(
                row_index, COL_MANUFACTURER, QTableWidgetItem(fields.get("manufacturer") or "")
            )
            self.table.setItem(
                row_index, COL_CAS, QTableWidgetItem(fields.get("cas_number") or "")
            )
            self.table.setItem(
                row_index, COL_REVISION, QTableWidgetItem(fields.get("revision_date") or "")
            )
            self.table.setItem(
                row_index, COL_SIGNAL, QTableWidgetItem(fields.get("signal_word") or "")
            )

            duplicates = db.find_possible_duplicates(
                self.conn,
                product_name=product_name,
                manufacturer=fields.get("manufacturer"),
                cas_number=fields.get("cas_number"),
            )
            flag_item = QTableWidgetItem("⚠ possible duplicate" if duplicates else "")
            flag_item.setFlags(flag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, COL_FLAG, flag_item)

    def _selected_department_ids(self) -> list[int]:
        ids = []
        for i in range(self.department_list.count()):
            item = self.department_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def get_selected_entries(self) -> list[dict]:
        department_ids = self._selected_department_ids()
        entries = []
        for row_index, path_str in enumerate(self._file_paths):
            include_item = self.table.item(row_index, COL_INCLUDE)
            if include_item.checkState() != Qt.CheckState.Checked:
                continue

            product_name = self.table.item(row_index, COL_PRODUCT).text().strip()
            if not product_name:
                continue

            revision_date_text = self.table.item(row_index, COL_REVISION).text().strip()
            revision_date = revision_date_text if _is_valid_iso_date(revision_date_text) else None

            signal_word = self.table.item(row_index, COL_SIGNAL).text().strip()
            if signal_word not in SIGNAL_WORDS:
                signal_word = ""

            entries.append(
                {
                    "product_name": product_name,
                    "manufacturer": self.table.item(row_index, COL_MANUFACTURER).text().strip()
                    or None,
                    "cas_number": self.table.item(row_index, COL_CAS).text().strip() or None,
                    "revision_date": revision_date,
                    "signal_word": signal_word or None,
                    "notes": None,
                    "source_file_path": path_str,
                    "copy_into_storage": True,
                    "department_ids": department_ids,
                }
            )
        return entries


def _is_valid_iso_date(text: str) -> bool:
    if not text:
        return False
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False
