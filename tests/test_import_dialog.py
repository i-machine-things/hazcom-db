import os
import sqlite3
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from core import db  # noqa: E402
from ui.import_dialog import COL_CAS, COL_FLAG, COL_PRODUCT, ImportDialog  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    db.init_db(connection)
    yield connection
    connection.close()


def _make_pdf(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4 fake")
    return str(path)


def test_flag_recomputes_when_edited_to_match_existing_record(qapp, conn, tmp_path):
    db.add_sds_sheet(conn, product_name="Acetone", manufacturer="ACME", file_path="a.pdf")

    dialog = ImportDialog(conn, db.list_departments(conn), [_make_pdf(tmp_path, "solvent.pdf")])
    assert dialog.table.item(0, COL_FLAG).text() == ""

    dialog.table.item(0, COL_PRODUCT).setText("Acetone")
    assert dialog.table.item(0, COL_FLAG).text() != ""


def test_flag_clears_when_edited_away_from_a_match(qapp, conn, tmp_path):
    db.add_sds_sheet(conn, product_name="Acetone", file_path="a.pdf")

    dialog = ImportDialog(conn, db.list_departments(conn), [_make_pdf(tmp_path, "acetone.pdf")])
    dialog.table.item(0, COL_PRODUCT).setText("Acetone")
    assert dialog.table.item(0, COL_FLAG).text() != ""

    dialog.table.item(0, COL_PRODUCT).setText("Something Else Entirely")
    assert dialog.table.item(0, COL_FLAG).text() == ""


def test_flags_duplicate_within_same_batch(qapp, conn, tmp_path):
    paths = [_make_pdf(tmp_path, "a.pdf"), _make_pdf(tmp_path, "b.pdf")]
    dialog = ImportDialog(conn, db.list_departments(conn), paths)
    assert dialog.table.item(0, COL_FLAG).text() == ""
    assert dialog.table.item(1, COL_FLAG).text() == ""

    dialog.table.item(1, COL_PRODUCT).setText(dialog.table.item(0, COL_PRODUCT).text())

    assert dialog.table.item(0, COL_FLAG).text() != ""
    assert dialog.table.item(1, COL_FLAG).text() != ""


def test_flags_duplicate_within_same_batch_by_cas_number(qapp, conn, tmp_path):
    paths = [_make_pdf(tmp_path, "a.pdf"), _make_pdf(tmp_path, "b.pdf")]
    dialog = ImportDialog(conn, db.list_departments(conn), paths)

    dialog.table.item(0, COL_CAS).setText("67-64-1")
    dialog.table.item(1, COL_CAS).setText("67-64-1")

    assert dialog.table.item(0, COL_FLAG).text() != ""
    assert dialog.table.item(1, COL_FLAG).text() != ""


def test_accept_confirms_before_importing_a_flagged_row(qapp, conn, tmp_path, monkeypatch):
    db.add_sds_sheet(conn, product_name="Acetone", file_path="a.pdf")

    dialog = ImportDialog(conn, db.list_departments(conn), [_make_pdf(tmp_path, "solvent.pdf")])
    dialog.table.item(0, COL_PRODUCT).setText("Acetone")

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_accept_does_not_prompt_when_nothing_is_flagged(qapp, conn, tmp_path, monkeypatch):
    dialog = ImportDialog(conn, db.list_departments(conn), [_make_pdf(tmp_path, "solvent.pdf")])

    def _fail_if_called(*a, **k):
        raise AssertionError("QMessageBox.question should not be called")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_fail_if_called))
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
