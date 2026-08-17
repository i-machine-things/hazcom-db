# hazcom-db

A local desktop app for managing Safety Data Sheets (SDS): store them, tag each one with the
department(s) that use it, and search/filter by department or product.

Built with PyQt6 and SQLite. Runs entirely on one machine — no server, no accounts, no network
access required.

## Features

- Add SDS sheets with product name, manufacturer, CAS number(s), revision date, signal word, and
  notes.
- Attach the SDS file either by **copying it into the app's own storage** (default — keeps the
  app self-contained and portable) or by **referencing the file at its current location**.
- Tag each SDS sheet with one or more departments; manage the department list directly in the app
  (add, rename, delete — no seed list required).
- Filter by department from the sidebar, and search live by product name, manufacturer, or CAS
  number.
- Open the attached PDF straight from the app (double-click a row, or the "Open File" button) in
  your system's default viewer.

## Requirements

- Python 3.10+
- PyQt6

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

App data (the SQLite database and any app-managed SDS file copies) is stored in `./data/`, which
is gitignored — it's runtime state, not source.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
flake8 --max-line-length=120 --select=E,F .
bandit -r . --severity-level medium -q
```

`core/db.py` holds the SQLite schema and all data access and has no PyQt import, so it's fully
unit-testable without a Qt platform plugin. UI code lives in `ui/`.

## Project layout

```
main.py             # entry point
core/db.py           # schema, connection, CRUD, search/filter, managed file storage
ui/main_window.py     # main window: department sidebar, search, results table
ui/sds_dialog.py       # Add/Edit SDS dialog
tests/test_db.py        # data-layer test coverage
```

## Status

Packaging/distribution (installers, etc.) is intentionally out of scope for now — this is a
single-machine tool run via `python main.py`. CI covers lint, security scan, and tests.
