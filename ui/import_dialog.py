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
    QMessageBox,
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
        # Connect only after initial population so populating rows doesn't
        # itself trigger a recompute pass.
        self.table.itemChanged.connect(self._on_cell_changed)

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

            flag_item = QTableWidgetItem("")
            flag_item.setFlags(flag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, COL_FLAG, flag_item)

        self._recompute_all_flags()

    def _on_cell_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in (COL_PRODUCT, COL_MANUFACTURER, COL_CAS):
            self._recompute_all_flags()

    def _recompute_all_flags(self) -> None:
        # Editing one row can also affect whether other rows match it (a
        # batch-internal duplicate), so recompute every row's flag rather
        # than just the one that changed. Block signals to avoid re-entering
        # _on_cell_changed while we update the (non-editable) flag cells.
        self.table.blockSignals(True)
        try:
            for row_index in range(self.table.rowCount()):
                self._update_flag(row_index)
        finally:
            self.table.blockSignals(False)

    def _update_flag(self, row_index: int) -> None:
        product_name = self.table.item(row_index, COL_PRODUCT).text().strip()
        manufacturer = self.table.item(row_index, COL_MANUFACTURER).text().strip()
        cas_number = self.table.item(row_index, COL_CAS).text().strip()

        is_duplicate = bool(
            db.find_possible_duplicates(
                self.conn,
                product_name=product_name,
                manufacturer=manufacturer,
                cas_number=cas_number,
            )
        ) or self._matches_another_row_in_batch(row_index, product_name, cas_number)

        self.table.item(row_index, COL_FLAG).setText(
            "⚠ possible duplicate" if is_duplicate else ""
        )

    def _matches_another_row_in_batch(
        self, row_index: int, product_name: str, cas_number: str
    ) -> bool:
        name_norm = product_name.strip().lower()
        cas_set = {c.strip() for c in cas_number.split(",") if c.strip()}
        for other_index in range(self.table.rowCount()):
            if other_index == row_index:
                continue
            other_name = self.table.item(other_index, COL_PRODUCT).text().strip().lower()
            if name_norm and other_name == name_norm:
                return True
            other_cas = {
                c.strip() for c in self.table.item(other_index, COL_CAS).text().split(",") if c.strip()
            }
            if cas_set and other_cas and cas_set & other_cas:
                return True
        return False

    def accept(self) -> None:
        self._recompute_all_flags()  # catch any edit that hasn't re-triggered a recompute yet

        flagged_names = []
        for row_index in range(self.table.rowCount()):
            include_item = self.table.item(row_index, COL_INCLUDE)
            if include_item.checkState() != Qt.CheckState.Checked:
                continue
            if self.table.item(row_index, COL_FLAG).text():
                flagged_names.append(self.table.item(row_index, COL_FILENAME).text())

        if flagged_names:
            shown = ", ".join(flagged_names[:5])
            more = f", and {len(flagged_names) - 5} more" if len(flagged_names) > 5 else ""
            confirm = QMessageBox.question(
                self,
                "Possible duplicates",
                f"{len(flagged_names)} file(s) look like possible duplicates: "
                f"{shown}{more}.\n\nImport anyway?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        super().accept()

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
