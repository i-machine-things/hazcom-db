"""Main window: department sidebar, search, results table, and row actions."""

from __future__ import annotations

import sqlite3

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import db
from ui.sds_dialog import SdsDialog

ALL_DEPARTMENTS_LABEL = "All Departments"
COLUMNS = ["Product Name", "Manufacturer", "Departments", "Revision Date"]


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self._current_rows: list[sqlite3.Row] = []

        self.setWindowTitle("hazcom-db — SDS Manager")
        self.resize(1000, 600)

        self._build_ui()
        self._install_easter_egg()
        self.refresh_departments()
        self.refresh_results()

    # --- UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)

        splitter = QSplitter()
        root_layout.addWidget(splitter)

        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_results_panel())
        splitter.setStretchFactor(1, 1)

        self.setStatusBar(QStatusBar())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.addWidget(QLabel("Departments"))

        self.department_list = QListWidget()
        self.department_list.currentItemChanged.connect(lambda *_: self.refresh_results())
        self.department_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.department_list.customContextMenuRequested.connect(
            self._show_department_context_menu
        )
        layout.addWidget(self.department_list)

        add_dept_btn = QPushButton("+ Add Department")
        add_dept_btn.clicked.connect(self._add_department)
        layout.addWidget(add_dept_btn)

        return sidebar

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        top_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search by product, manufacturer, or CAS number..."
        )
        self.search_edit.textChanged.connect(lambda *_: self.refresh_results())
        top_bar.addWidget(self.search_edit)

        add_sds_btn = QPushButton("Add SDS")
        add_sds_btn.clicked.connect(self._add_sds)
        top_bar.addWidget(add_sds_btn)
        layout.addLayout(top_bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda *_: self._open_selected_file())
        layout.addWidget(self.table)

        row_buttons = QHBoxLayout()
        open_btn = QPushButton("Open File")
        open_btn.clicked.connect(self._open_selected_file)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_sds)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_selected_sds)
        row_buttons.addWidget(open_btn)
        row_buttons.addWidget(edit_btn)
        row_buttons.addWidget(delete_btn)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)

        return panel

    # --- Departments -----------------------------------------------------------

    def _current_department_id(self):
        item = self.department_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def refresh_departments(self) -> None:
        current_id = self._current_department_id()
        self.department_list.blockSignals(True)
        self.department_list.clear()

        all_item = QListWidgetItem(ALL_DEPARTMENTS_LABEL)
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.department_list.addItem(all_item)

        selected_item = all_item
        for row in db.list_departments(self.conn):
            item = QListWidgetItem(row["name"])
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.department_list.addItem(item)
            if row["id"] == current_id:
                selected_item = item

        self.department_list.setCurrentItem(selected_item)
        self.department_list.blockSignals(False)

    def _add_department(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Department", "Department name:")
        if ok and name.strip():
            try:
                db.add_department(self.conn, name)
            except ValueError as exc:
                QMessageBox.warning(self, "Could not add department", str(exc))
            self.refresh_departments()

    def _show_department_context_menu(self, pos) -> None:
        item = self.department_list.itemAt(pos)
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        department_id = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec(self.department_list.mapToGlobal(pos))

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "Rename Department", "New name:", text=item.text()
            )
            if ok and new_name.strip():
                try:
                    db.rename_department(self.conn, department_id, new_name)
                except ValueError as exc:
                    QMessageBox.warning(self, "Could not rename department", str(exc))
                self.refresh_departments()
                self.refresh_results()
        elif action == delete_action:
            confirm = QMessageBox.question(
                self,
                "Delete Department",
                f"Delete department '{item.text()}'? "
                "SDS sheets tagged with it will lose that tag.",
            )
            if confirm == QMessageBox.StandardButton.Yes:
                db.delete_department(self.conn, department_id)
                self.refresh_departments()
                self.refresh_results()

    # --- Results table -----------------------------------------------------------

    def refresh_results(self) -> None:
        department_id = self._current_department_id()
        query_text = self.search_edit.text().strip() or None
        rows = db.search_sds(self.conn, query_text=query_text, department_id=department_id)
        self._current_rows = rows

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(row["product_name"]))
            self.table.setItem(r, 1, QTableWidgetItem(row["manufacturer"] or ""))
            self.table.setItem(r, 2, QTableWidgetItem(row["departments"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem(row["revision_date"] or ""))

        self.statusBar().showMessage(f"{len(rows)} SDS sheet(s)")

    def _selected_row(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        return self._current_rows[selected[0].row()]

    def _open_selected_file(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        path = db.resolve_file_path(row)
        if not path.exists():
            QMessageBox.warning(self, "File not found", f"Could not find file:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _add_sds(self) -> None:
        departments = db.list_departments(self.conn)
        dialog = SdsDialog(self.conn, departments)
        if dialog.exec():
            self._commit_sds(dialog.get_data())
        self.refresh_departments()
        self.refresh_results()

    def _edit_selected_sds(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select an SDS sheet to edit.")
            return
        departments = db.list_departments(self.conn)
        department_ids = db.get_department_ids_for_sds(self.conn, row["id"])
        dialog = SdsDialog(
            self.conn,
            departments,
            existing=row,
            existing_department_ids=department_ids,
        )
        if dialog.exec():
            self._commit_sds(dialog.get_data(), existing_row=row)
        self.refresh_departments()
        self.refresh_results()

    def _commit_sds(self, data: dict, existing_row: sqlite3.Row | None = None) -> None:
        if data["source_file_path"] is not None:
            if existing_row is not None and existing_row["file_managed"]:
                (db.SDS_FILES_DIR / existing_row["file_path"]).unlink(missing_ok=True)
            if data["copy_into_storage"]:
                file_path = db.copy_into_storage(data["source_file_path"])
                file_managed = True
            else:
                file_path = data["source_file_path"]
                file_managed = False
        else:
            file_path = existing_row["file_path"]
            file_managed = bool(existing_row["file_managed"])

        try:
            if existing_row is None:
                db.add_sds_sheet(
                    self.conn,
                    product_name=data["product_name"],
                    manufacturer=data["manufacturer"],
                    cas_number=data["cas_number"],
                    revision_date=data["revision_date"],
                    signal_word=data["signal_word"],
                    notes=data["notes"],
                    file_path=file_path,
                    file_managed=file_managed,
                    department_ids=data["department_ids"],
                )
            else:
                db.update_sds_sheet(
                    self.conn,
                    existing_row["id"],
                    product_name=data["product_name"],
                    manufacturer=data["manufacturer"],
                    cas_number=data["cas_number"],
                    revision_date=data["revision_date"],
                    signal_word=data["signal_word"],
                    notes=data["notes"],
                    file_path=file_path,
                    file_managed=file_managed,
                    department_ids=data["department_ids"],
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))

    def _delete_selected_sds(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select an SDS sheet to delete.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete SDS Sheet",
            f"Delete '{row['product_name']}'? This cannot be undone.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            db.delete_sds_sheet(self.conn, row["id"])
            self.refresh_results()

    # --- Rule 7: hidden, unobtrusive, not in any menu/help text -----------------

    def _install_easter_egg(self) -> None:
        shortcut = QShortcut(QKeySequence("Ctrl+Alt+Shift+H"), self)
        shortcut.activated.connect(self._show_easter_egg)

    def _show_easter_egg(self) -> None:
        QMessageBox.information(
            self,
            "hazcom-db",
            "Remember: the most hazardous substance in this building is "
            "undocumented coffee.\n\n(You found the secret handshake. Carry on.)",
        )
