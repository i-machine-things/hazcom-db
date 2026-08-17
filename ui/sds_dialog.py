"""Add/Edit dialog for a single SDS sheet."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PyQt6.QtCore import QDate, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core import db, sds_parser

SIGNAL_WORDS = ["", "Danger", "Warning"]


class SdsDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        departments: list[sqlite3.Row],
        existing: sqlite3.Row | None = None,
        existing_department_ids: list[int] | None = None,
        initial_file_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Edit SDS Sheet" if existing else "Add SDS Sheet")
        self.setMinimumWidth(480)
        self.setAcceptDrops(True)

        self._selected_file_path: str | None = None
        self._existing = existing
        self._existing_department_ids = set(existing_department_ids or [])
        self._has_duplicate_warning = False

        self._build_ui(departments)
        if existing is not None:
            self._populate_from_existing(existing)
        elif initial_file_path is not None:
            self._set_selected_file(initial_file_path)
        self._check_duplicates()

    def _build_ui(self, departments: list[sqlite3.Row]) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.product_name_edit = QLineEdit()
        self.product_name_edit.textChanged.connect(self._check_duplicates)
        form.addRow("Product Name*", self.product_name_edit)

        self.manufacturer_edit = QLineEdit()
        self.manufacturer_edit.textChanged.connect(self._check_duplicates)
        form.addRow("Manufacturer", self.manufacturer_edit)

        self.cas_number_edit = QLineEdit()
        self.cas_number_edit.textChanged.connect(self._check_duplicates)
        form.addRow("CAS Number(s)", self.cas_number_edit)

        date_row = QHBoxLayout()
        self.has_revision_date_checkbox = QCheckBox("Has revision date")
        self.revision_date_edit = QDateEdit(QDate.currentDate())
        self.revision_date_edit.setCalendarPopup(True)
        self.revision_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.revision_date_edit.setEnabled(False)
        self.has_revision_date_checkbox.toggled.connect(self.revision_date_edit.setEnabled)
        date_row.addWidget(self.has_revision_date_checkbox)
        date_row.addWidget(self.revision_date_edit)
        form.addRow("Revision Date", date_row)

        self.signal_word_combo = QComboBox()
        self.signal_word_combo.addItems(SIGNAL_WORDS)
        form.addRow("Signal Word", self.signal_word_combo)

        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(60)
        form.addRow("Notes", self.notes_edit)

        file_row = QHBoxLayout()
        self.file_path_label = QLabel("No file selected (or drag & drop a PDF onto this window)")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_path_label, stretch=1)
        file_row.addWidget(browse_btn)
        form.addRow("SDS File*", file_row)

        self.copy_into_storage_checkbox = QCheckBox("Copy file into app storage")
        self.copy_into_storage_checkbox.setChecked(True)
        form.addRow("", self.copy_into_storage_checkbox)

        self.autofill_status_label = QLabel("")
        self.autofill_status_label.setStyleSheet("color: gray; font-style: italic;")
        self.autofill_status_label.hide()
        layout.addWidget(self.autofill_status_label)

        self.duplicate_warning_label = QLabel("")
        self.duplicate_warning_label.setStyleSheet("color: #b45309; font-weight: bold;")
        self.duplicate_warning_label.setWordWrap(True)
        self.duplicate_warning_label.hide()
        layout.addWidget(self.duplicate_warning_label)

        layout.addWidget(QLabel("Departments"))
        self.department_list = QListWidget()
        self.department_list.setMaximumHeight(120)
        self._reload_department_list(departments)
        layout.addWidget(self.department_list)

        new_dept_row = QHBoxLayout()
        self.new_department_edit = QLineEdit()
        self.new_department_edit.setPlaceholderText("New department name...")
        add_dept_btn = QPushButton("Add")
        add_dept_btn.clicked.connect(self._add_department_inline)
        new_dept_row.addWidget(self.new_department_edit)
        new_dept_row.addWidget(add_dept_btn)
        layout.addLayout(new_dept_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_department_list(self, departments: list[sqlite3.Row]) -> None:
        self.department_list.clear()
        for row in departments:
            item = QListWidgetItem(row["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            checked = row["id"] in self._existing_department_ids
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.department_list.addItem(item)

    def _populate_from_existing(self, existing: sqlite3.Row) -> None:
        self.product_name_edit.setText(existing["product_name"] or "")
        self.manufacturer_edit.setText(existing["manufacturer"] or "")
        self.cas_number_edit.setText(existing["cas_number"] or "")

        if existing["revision_date"]:
            self.has_revision_date_checkbox.setChecked(True)
            date = QDate.fromString(existing["revision_date"], "yyyy-MM-dd")
            if date.isValid():
                self.revision_date_edit.setDate(date)

        if existing["signal_word"] in SIGNAL_WORDS:
            self.signal_word_combo.setCurrentText(existing["signal_word"])

        self.notes_edit.setPlainText(existing["notes"] or "")

        display_name = Path(existing["file_path"]).name
        self.file_path_label.setText(f"Current file: {display_name}")
        self.copy_into_storage_checkbox.setChecked(bool(existing["file_managed"]))
        # Storage mode only applies to a newly-selected file — disabled until
        # one is chosen, so it can't silently be ignored (see CODING_NOTES).
        self.copy_into_storage_checkbox.setEnabled(False)
        self.copy_into_storage_checkbox.setToolTip(
            "Choose a replacement file to change how it's stored."
        )

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SDS File", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self._set_selected_file(path)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls or not urls[0].isLocalFile():
            return
        local_str = urls[0].toLocalFile()
        if local_str:
            self._set_selected_file(local_str)

    def _set_selected_file(self, path: str) -> None:
        file_path = Path(path)
        if not file_path.is_file() or file_path.suffix.lower() != ".pdf":
            QMessageBox.warning(self, "Invalid file", "Please choose a PDF file.")
            return
        self._selected_file_path = path
        self.file_path_label.setText(file_path.name)
        self.copy_into_storage_checkbox.setEnabled(True)
        self.copy_into_storage_checkbox.setToolTip("")
        # Open in the system default viewer so the auto-filled fields can be
        # compared against the actual document. The dialog is non-modal (see
        # MainWindow._track_open_dialog) so this doesn't get blocked.
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))
        self._autofill_from_pdf(path)

    def _autofill_from_pdf(self, path: str) -> None:
        fields = sds_parser.extract_fields(path)
        filled_any = False

        if fields.get("product_name") and not self.product_name_edit.text().strip():
            self.product_name_edit.setText(fields["product_name"])
            filled_any = True
        if fields.get("manufacturer") and not self.manufacturer_edit.text().strip():
            self.manufacturer_edit.setText(fields["manufacturer"])
            filled_any = True
        if fields.get("cas_number") and not self.cas_number_edit.text().strip():
            self.cas_number_edit.setText(fields["cas_number"])
            filled_any = True
        if fields.get("revision_date") and not self.has_revision_date_checkbox.isChecked():
            date = QDate.fromString(fields["revision_date"], "yyyy-MM-dd")
            if date.isValid():
                self.has_revision_date_checkbox.setChecked(True)
                self.revision_date_edit.setDate(date)
                filled_any = True
        if fields.get("signal_word") and not self.signal_word_combo.currentText():
            self.signal_word_combo.setCurrentText(fields["signal_word"])
            filled_any = True

        if filled_any:
            self.autofill_status_label.setText(
                "Auto-filled from the PDF — accuracy varies by document format. "
                "Compare each field against the PDF (opened alongside this window) "
                "before saving."
            )
            self.autofill_status_label.show()

    def _check_duplicates(self, *_args) -> None:
        product_name = self.product_name_edit.text().strip()
        cas_number = self.cas_number_edit.text().strip()
        if not product_name and not cas_number:
            self.duplicate_warning_label.hide()
            self._has_duplicate_warning = False
            return

        exclude_id = self._existing["id"] if self._existing is not None else None
        matches = db.find_possible_duplicates(
            self.conn,
            product_name=product_name,
            manufacturer=self.manufacturer_edit.text().strip(),
            cas_number=cas_number,
            exclude_sds_id=exclude_id,
        )
        self._has_duplicate_warning = bool(matches)
        if matches:
            names = ", ".join(
                f"{m['product_name']} ({m['manufacturer'] or 'unknown manufacturer'})"
                for m in matches[:3]
            )
            more = f", and {len(matches) - 3} more" if len(matches) > 3 else ""
            self.duplicate_warning_label.setText(
                f"⚠ Possible duplicate of: {names}{more}. Review before saving."
            )
            self.duplicate_warning_label.show()
        else:
            self.duplicate_warning_label.hide()

    def _add_department_inline(self) -> None:
        name = self.new_department_edit.text().strip()
        if not name:
            return
        try:
            new_id = db.add_department(self.conn, name)
        except ValueError as exc:
            QMessageBox.warning(self, "Could not add department", str(exc))
            return
        self._existing_department_ids.add(new_id)
        self._reload_department_list(db.list_departments(self.conn))
        self.new_department_edit.clear()

    def accept(self) -> None:
        if not self.product_name_edit.text().strip():
            QMessageBox.warning(self, "Missing product name", "Enter a product name.")
            return
        if self._selected_file_path is None and self._existing is None:
            QMessageBox.warning(self, "Missing file", "Choose a file for this SDS sheet.")
            return
        if self._has_duplicate_warning:
            confirm = QMessageBox.question(
                self,
                "Possible duplicate",
                "This looks like it might duplicate an existing SDS sheet. Save anyway?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        super().accept()

    def get_data(self) -> dict:
        revision_date = None
        if self.has_revision_date_checkbox.isChecked():
            revision_date = self.revision_date_edit.date().toString("yyyy-MM-dd")

        selected_ids = []
        for i in range(self.department_list.count()):
            item = self.department_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_ids.append(item.data(Qt.ItemDataRole.UserRole))

        return {
            "product_name": self.product_name_edit.text().strip(),
            "manufacturer": self.manufacturer_edit.text().strip() or None,
            "cas_number": self.cas_number_edit.text().strip() or None,
            "revision_date": revision_date,
            "signal_word": self.signal_word_combo.currentText() or None,
            "notes": self.notes_edit.toPlainText().strip() or None,
            "source_file_path": self._selected_file_path,
            "copy_into_storage": self.copy_into_storage_checkbox.isChecked(),
            "department_ids": selected_ids,
        }
