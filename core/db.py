"""SQLite schema and data access for hazcom-db.

Deliberately has no PyQt import so it can be unit tested without a Qt
platform plugin (see tests/test_db.py and the CI test job).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "hazcom.db"
SDS_FILES_DIR = DATA_DIR / "sds_files"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS sds_sheets (
    id            INTEGER PRIMARY KEY,
    product_name  TEXT NOT NULL,
    manufacturer  TEXT,
    cas_number    TEXT,
    revision_date TEXT,
    signal_word   TEXT,
    notes         TEXT,
    file_path     TEXT NOT NULL,
    file_managed  INTEGER NOT NULL DEFAULT 1,
    date_added    TEXT NOT NULL DEFAULT (datetime('now')),
    date_updated  TEXT
);

CREATE TABLE IF NOT EXISTS sds_departments (
    sds_id        INTEGER NOT NULL REFERENCES sds_sheets(id) ON DELETE CASCADE,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    PRIMARY KEY (sds_id, department_id)
);
"""


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SDS_FILES_DIR.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def connect_and_init(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Convenience entry point for app startup: ensure dirs exist, connect, init schema."""
    ensure_data_dirs()
    conn = get_connection(db_path)
    init_db(conn)
    return conn


def _escape_like(value: str) -> str:
    """Escape SQLite LIKE wildcards so user text is matched literally."""
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


# --- Departments ------------------------------------------------------------

def list_departments(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, name FROM departments ORDER BY name COLLATE NOCASE"
    ).fetchall()


def add_department(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Department name cannot be empty.")
    try:
        cur = conn.execute("INSERT INTO departments (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Department '{name}' already exists.") from exc
    return cur.lastrowid


def rename_department(conn: sqlite3.Connection, department_id: int, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Department name cannot be empty.")
    try:
        conn.execute(
            "UPDATE departments SET name = ? WHERE id = ?", (new_name, department_id)
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Department '{new_name}' already exists.") from exc


def delete_department(conn: sqlite3.Connection, department_id: int) -> None:
    conn.execute("DELETE FROM departments WHERE id = ?", (department_id,))
    conn.commit()


# --- SDS sheets ---------------------------------------------------------------

def add_sds_sheet(
    conn: sqlite3.Connection,
    *,
    product_name: str,
    file_path: str,
    file_managed: bool = True,
    manufacturer: str | None = None,
    cas_number: str | None = None,
    revision_date: str | None = None,
    signal_word: str | None = None,
    notes: str | None = None,
    department_ids: list[int] | None = None,
) -> int:
    product_name = product_name.strip()
    if not product_name:
        raise ValueError("Product name cannot be empty.")
    if not file_path:
        raise ValueError("A file must be selected.")

    cur = conn.execute(
        """
        INSERT INTO sds_sheets
            (product_name, manufacturer, cas_number, revision_date,
             signal_word, notes, file_path, file_managed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_name,
            manufacturer,
            cas_number,
            revision_date,
            signal_word,
            notes,
            file_path,
            1 if file_managed else 0,
        ),
    )
    sds_id = cur.lastrowid
    set_sds_departments(conn, sds_id, department_ids or [])
    conn.commit()
    return sds_id


def update_sds_sheet(
    conn: sqlite3.Connection,
    sds_id: int,
    *,
    product_name: str,
    file_path: str,
    file_managed: bool,
    manufacturer: str | None = None,
    cas_number: str | None = None,
    revision_date: str | None = None,
    signal_word: str | None = None,
    notes: str | None = None,
    department_ids: list[int] | None = None,
) -> None:
    product_name = product_name.strip()
    if not product_name:
        raise ValueError("Product name cannot be empty.")
    if not file_path:
        raise ValueError("A file must be selected.")

    conn.execute(
        """
        UPDATE sds_sheets
        SET product_name = ?, manufacturer = ?, cas_number = ?, revision_date = ?,
            signal_word = ?, notes = ?, file_path = ?, file_managed = ?,
            date_updated = datetime('now')
        WHERE id = ?
        """,
        (
            product_name,
            manufacturer,
            cas_number,
            revision_date,
            signal_word,
            notes,
            file_path,
            1 if file_managed else 0,
            sds_id,
        ),
    )
    set_sds_departments(conn, sds_id, department_ids or [])
    conn.commit()


def set_sds_departments(conn: sqlite3.Connection, sds_id: int, department_ids: list[int]) -> None:
    conn.execute("DELETE FROM sds_departments WHERE sds_id = ?", (sds_id,))
    conn.executemany(
        "INSERT INTO sds_departments (sds_id, department_id) VALUES (?, ?)",
        [(sds_id, dept_id) for dept_id in department_ids],
    )


def get_sds_sheet(conn: sqlite3.Connection, sds_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sds_sheets WHERE id = ?", (sds_id,)).fetchone()


def get_department_ids_for_sds(conn: sqlite3.Connection, sds_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT department_id FROM sds_departments WHERE sds_id = ?", (sds_id,)
    ).fetchall()
    return [row["department_id"] for row in rows]


def delete_sds_sheet(conn: sqlite3.Connection, sds_id: int) -> None:
    row = conn.execute(
        "SELECT file_path, file_managed FROM sds_sheets WHERE id = ?", (sds_id,)
    ).fetchone()
    if row is None:
        return
    conn.execute("DELETE FROM sds_sheets WHERE id = ?", (sds_id,))
    conn.commit()
    if row["file_managed"]:
        (SDS_FILES_DIR / row["file_path"]).unlink(missing_ok=True)


def search_sds(
    conn: sqlite3.Connection,
    query_text: str | None = None,
    department_id: int | None = None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT s.*, GROUP_CONCAT(d.name, ', ') AS departments
        FROM sds_sheets s
        LEFT JOIN sds_departments sd ON sd.sds_id = s.id
        LEFT JOIN departments d ON d.id = sd.department_id
        WHERE (:department_id IS NULL OR s.id IN (
            SELECT sds_id FROM sds_departments WHERE department_id = :department_id
        ))
        AND (:like IS NULL OR
             s.product_name LIKE :like ESCAPE '!' OR
             s.manufacturer LIKE :like ESCAPE '!' OR
             s.cas_number LIKE :like ESCAPE '!')
        GROUP BY s.id
        ORDER BY s.product_name COLLATE NOCASE
    """
    like_pattern = f"%{_escape_like(query_text)}%" if query_text else None
    return conn.execute(
        sql, {"department_id": department_id, "like": like_pattern}
    ).fetchall()


# --- File storage -------------------------------------------------------------

def copy_into_storage(source_path: Path | str) -> str:
    """Copy a file into the managed SDS storage dir; return the path to store (relative to SDS_FILES_DIR)."""
    ensure_data_dirs()
    source = Path(source_path)
    dest = SDS_FILES_DIR / source.name
    counter = 1
    while dest.exists():
        dest = SDS_FILES_DIR / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    shutil.copy2(source, dest)
    return dest.name


def resolve_file_path(row: sqlite3.Row) -> Path:
    if row["file_managed"]:
        return SDS_FILES_DIR / row["file_path"]
    return Path(row["file_path"])
