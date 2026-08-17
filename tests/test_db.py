import sqlite3

import pytest

from core import db


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    db.init_db(connection)
    yield connection
    connection.close()


def test_init_db_creates_expected_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"departments", "sds_sheets", "sds_departments"} <= tables


def test_add_and_list_departments(conn):
    db.add_department(conn, "Paint Shop")
    db.add_department(conn, "Machining")
    names = [row["name"] for row in db.list_departments(conn)]
    assert names == ["Machining", "Paint Shop"]  # alphabetical


def test_add_department_duplicate_raises(conn):
    db.add_department(conn, "Paint Shop")
    with pytest.raises(ValueError):
        db.add_department(conn, "Paint Shop")


def test_add_department_empty_name_raises(conn):
    with pytest.raises(ValueError):
        db.add_department(conn, "   ")


def test_rename_department(conn):
    dept_id = db.add_department(conn, "Paint Shop")
    db.rename_department(conn, dept_id, "Finishing")
    names = [row["name"] for row in db.list_departments(conn)]
    assert names == ["Finishing"]


def test_delete_department_cascades_tag_but_not_sheet(conn):
    dept_id = db.add_department(conn, "Paint Shop")
    sds_id = db.add_sds_sheet(
        conn,
        product_name="Acetone",
        file_path="acetone.pdf",
        department_ids=[dept_id],
    )

    db.delete_department(conn, dept_id)

    assert db.get_department_ids_for_sds(conn, sds_id) == []
    assert db.get_sds_sheet(conn, sds_id) is not None


def test_add_and_get_sds_sheet(conn):
    dept_id = db.add_department(conn, "Paint Shop")
    sds_id = db.add_sds_sheet(
        conn,
        product_name="Acetone",
        manufacturer="ACME Chemical",
        cas_number="67-64-1",
        revision_date="2024-01-15",
        signal_word="Danger",
        notes="Flammable",
        file_path="acetone.pdf",
        department_ids=[dept_id],
    )

    row = db.get_sds_sheet(conn, sds_id)
    assert row["product_name"] == "Acetone"
    assert row["manufacturer"] == "ACME Chemical"
    assert db.get_department_ids_for_sds(conn, sds_id) == [dept_id]


def test_add_sds_sheet_requires_product_name(conn):
    with pytest.raises(ValueError):
        db.add_sds_sheet(conn, product_name="  ", file_path="x.pdf")


def test_add_sds_sheet_requires_file_path(conn):
    with pytest.raises(ValueError):
        db.add_sds_sheet(conn, product_name="Acetone", file_path="")


def test_update_sds_sheet_changes_departments(conn):
    paint = db.add_department(conn, "Paint Shop")
    machining = db.add_department(conn, "Machining")
    sds_id = db.add_sds_sheet(
        conn, product_name="Acetone", file_path="acetone.pdf", department_ids=[paint]
    )

    db.update_sds_sheet(
        conn,
        sds_id,
        product_name="Acetone",
        file_path="acetone.pdf",
        file_managed=True,
        department_ids=[machining],
    )

    assert db.get_department_ids_for_sds(conn, sds_id) == [machining]


def test_search_sds_by_text(conn):
    db.add_sds_sheet(conn, product_name="Acetone", file_path="a.pdf")
    db.add_sds_sheet(conn, product_name="Isopropyl Alcohol", file_path="b.pdf")

    results = db.search_sds(conn, query_text="acet")
    assert [row["product_name"] for row in results] == ["Acetone"]


def test_search_sds_by_department(conn):
    paint = db.add_department(conn, "Paint Shop")
    machining = db.add_department(conn, "Machining")
    db.add_sds_sheet(
        conn, product_name="Acetone", file_path="a.pdf", department_ids=[paint]
    )
    db.add_sds_sheet(
        conn, product_name="Cutting Oil", file_path="b.pdf", department_ids=[machining]
    )

    results = db.search_sds(conn, department_id=paint)
    assert [row["product_name"] for row in results] == ["Acetone"]


def test_search_sds_returns_joined_department_names(conn):
    paint = db.add_department(conn, "Paint Shop")
    machining = db.add_department(conn, "Machining")
    db.add_sds_sheet(
        conn,
        product_name="Multi-Use Solvent",
        file_path="a.pdf",
        department_ids=[paint, machining],
    )

    results = db.search_sds(conn)
    departments = results[0]["departments"]
    assert "Paint Shop" in departments
    assert "Machining" in departments


def test_search_escapes_like_wildcards(conn):
    db.add_sds_sheet(conn, product_name="100% Solvent", file_path="a.pdf")
    db.add_sds_sheet(conn, product_name="Acetone", file_path="b.pdf")

    results = db.search_sds(conn, query_text="100% Solvent")
    assert [row["product_name"] for row in results] == ["100% Solvent"]


def test_delete_sds_sheet_removes_row(conn):
    sds_id = db.add_sds_sheet(conn, product_name="Acetone", file_path="a.pdf")
    db.delete_sds_sheet(conn, sds_id)
    assert db.get_sds_sheet(conn, sds_id) is None


def test_delete_sds_sheet_removes_managed_file(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "SDS_FILES_DIR", tmp_path)
    stored_file = tmp_path / "acetone.pdf"
    stored_file.write_bytes(b"%PDF-1.4 fake")

    sds_id = db.add_sds_sheet(
        conn, product_name="Acetone", file_path="acetone.pdf", file_managed=True
    )
    db.delete_sds_sheet(conn, sds_id)

    assert not stored_file.exists()


def test_delete_sds_sheet_ignores_absolute_path_outside_storage(conn, tmp_path, monkeypatch):
    storage_dir = tmp_path / "sds_files"
    storage_dir.mkdir()
    monkeypatch.setattr(db, "SDS_FILES_DIR", storage_dir)

    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"%PDF-1.4 fake")

    sds_id = db.add_sds_sheet(
        conn, product_name="Acetone", file_path=str(outside_file), file_managed=True
    )
    db.delete_sds_sheet(conn, sds_id)

    assert outside_file.exists(), "a malformed absolute file_path must not be deleted"


def test_delete_sds_sheet_ignores_traversal_path_outside_storage(conn, tmp_path, monkeypatch):
    storage_dir = tmp_path / "sds_files"
    storage_dir.mkdir()
    monkeypatch.setattr(db, "SDS_FILES_DIR", storage_dir)

    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"%PDF-1.4 fake")

    sds_id = db.add_sds_sheet(
        conn,
        product_name="Acetone",
        file_path="../outside.pdf",
        file_managed=True,
    )
    db.delete_sds_sheet(conn, sds_id)

    assert outside_file.exists(), "a malformed ../ file_path must not be deleted"


def test_delete_sds_sheet_leaves_external_file(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "SDS_FILES_DIR", tmp_path)
    external_file = tmp_path / "external.pdf"
    external_file.write_bytes(b"%PDF-1.4 fake")

    sds_id = db.add_sds_sheet(
        conn,
        product_name="Acetone",
        file_path=str(external_file),
        file_managed=False,
    )
    db.delete_sds_sheet(conn, sds_id)

    assert external_file.exists()


def test_copy_into_storage_avoids_collisions(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "SDS_FILES_DIR", tmp_path / "sds_files")

    source = tmp_path / "acetone.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    first = db.copy_into_storage(source)
    second = db.copy_into_storage(source)

    assert first == "acetone.pdf"
    assert second == "acetone_1.pdf"
    assert (db.SDS_FILES_DIR / first).exists()
    assert (db.SDS_FILES_DIR / second).exists()
