# Coding Best Practices & Reminders

> **Style rule:** Notes must be clear and concise — 300 characters or less each. Group by topic, not by date. Whenever a PR review (CodeRabbit or human) catches a mistake, add or amend a note here right away so it isn't repeated.

## File & Storage Safety (hazcom-db)

- **Create-then-persist-then-delete when replacing a managed file.** Never delete the old file before the new copy exists and the DB write succeeds — otherwise a failed copy or a failed save leaves the row pointing at a deleted file. Clean up an orphaned new copy if the DB write fails.
- **Resolve and containment-check before deleting a "managed" file.** `_resolve_managed_path()` in `core/db.py` rejects an absolute path or `../` traversal so a malformed/imported record can't delete a file outside `SDS_FILES_DIR`. Always delete managed files through `db.remove_managed_file()`, not a raw `unlink`.
- **Disable a storage-mode toggle (copy vs. reference) when it wouldn't apply.** In the SDS edit dialog, "copy into storage" only matters when a new file is chosen — it's disabled until then so it can't be toggled and silently ignored.

## Easter Eggs

- **Ctrl+Alt+Shift+H** in the main window (`ui/main_window.py:_show_easter_egg`) pops a one-off joke message box. Not listed anywhere in the UI/docs; doesn't affect normal operation. Don't duplicate or break it.
