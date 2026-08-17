# hazcom-db

A local desktop app for managing Safety Data Sheets (SDS): store them, tag each one with the
department(s) that use it, and search/filter by department or product.

Status: scaffolding in progress.

## Requirements

- Python 3.12+
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

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
flake8 --max-line-length=120 --select=E,F .
bandit -r . --severity-level medium -q
```
