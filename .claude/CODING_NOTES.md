# Coding Best Practices & Reminders

> **Style rule:** Notes must be clear and concise — 300 characters or less each. Group by topic, not by date. Whenever a PR review (CodeRabbit or human) catches a mistake, add or amend a note here right away so it isn't repeated.

## File & Storage Safety (hazcom-db)

- **Create-then-persist-then-delete when replacing a managed file.** Never delete the old file before the new copy exists and the DB write succeeds — otherwise a failed copy or a failed save leaves the row pointing at a deleted file. Clean up an orphaned new copy if the DB write fails.
- **Resolve and containment-check before deleting a "managed" file.** `_resolve_managed_path()` in `core/db.py` rejects an absolute path or `../` traversal so a malformed/imported record can't delete a file outside `SDS_FILES_DIR`. Always delete managed files through `db.remove_managed_file()`, not a raw `unlink`.
- **Disable a storage-mode toggle (copy vs. reference) when it wouldn't apply.** In the SDS edit dialog, "copy into storage" only matters when a new file is chosen — it's disabled until then so it can't be toggled and silently ignored.

## PDF Field Extraction (hazcom-db)

- **A regex label match can consume part of a compound header.** "Manufacturer/Supplier" matched by `manufacturer` leaves `/Supplier` as the same-line "value" — reject same-line text when it starts with a non-separator char and fall through to the next line instead.
- **Multiple "Label: value" pairs can share one PDF text line.** SDS footers commonly read "Revision date: X Issue date: Y" as one line — truncate a same-line capture at the next embedded `Label:` pattern so the next field's value isn't swallowed too.
- **US SDS footers commonly use dash-separated dates (`MM-DD-YYYY`), not just slashes.** Test date parsing against real SDS text, not just synthetic `Month DD, YYYY` / `MM/DD/YYYY` examples — a real sample immediately surfaced both this and the label-parsing bug above.

## UI Layout (hazcom-db)

- **An empty/near-empty `QListWidget` with no height cap will expand to dominate a dialog.** The department checklist in `SdsDialog` had no `setMaximumHeight`, unlike the equivalent list in `ImportDialog` — confirmed via a real `.grab()` screenshot, not just code review. Cap list/tree widget heights in dialogs explicitly.
- **`QTableWidget` columns default to a fixed ~100px unless given a resize mode or explicit width.** Only column 0 had `Stretch`; the rest were left at the ~100px default, which wrapped header text like "Revision Date" onto two lines. Set explicit widths for non-stretched columns.

## Easter Eggs

- **Ctrl+Alt+Shift+H** in the main window (`ui/main_window.py:_show_easter_egg`) pops a one-off joke message box. Not listed anywhere in the UI/docs; doesn't affect normal operation. Don't duplicate or break it.
