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
- **`PdfReader()` can construct successfully for an encrypted PDF; page access is what raises.** `len(reader.pages)` / `reader.pages[i]` can raise `FileNotDecryptedError` (a `PdfReadError` subclass) even though the reader itself opened fine — wrap page access in the same try/except as construction, not just the constructor call.
- **Validate regex-assembled dates against the calendar before returning them.** `MM-DD-YYYY`-shaped text like "2024-13-40" isn't automatically a valid date — round-trip through `datetime.date.fromisoformat()` and reject on `ValueError`.
- **A labeled field's value is authoritative, even when it doesn't match what you're looking for.** `_find_signal_word` fell through to a full-text `DANGER`/`WARNING` scan whenever a `Signal word:` label's value wasn't literally "Danger"/"Warning" — so an explicit "Signal word: None" got overridden by an unrelated standalone DANGER elsewhere in the document. Once a label is found, its value (or lack of one) should end the search.
- **Only accept files with a validated extension, even when the OS file picker allows "All Files".** Both browse (`QFileDialog` with an "All Files" filter option) and drag-and-drop can hand back a non-PDF; validate `Path(path).suffix.lower() == ".pdf"` before treating it as the SDS attachment.
- **Check `QUrl.isLocalFile()` before calling `toLocalFile()`.** For a non-local URL (e.g. dropped from a browser), `toLocalFile()` returns `""`, and `Path("")` is the current working directory — `.is_dir()` on that is `True`, silently triggering a recursive scan/import of the app's CWD.
- **Anchor label matching to the start of the line, except where labels legitimately share a line.** Unanchored `manufacturer`/`supplier` search matched those words buried mid-sentence in disclaimer boilerplate (e.g. "...contact the manufacturer directly"), producing garbage. Anchoring fixed it, but revision-date labels *do* legitimately appear mid-line in combined footers ("Version #: 1.0 Revision date: X Issue date: Y") — `_find_label_value` takes an `anchored` flag; only revision-date search stays unanchored.
- **A next-line fallback candidate can itself start with a different field's label.** "Product identifier" with no same-line value, followed by "Trade name: X" as the next line, produced "Trade name: X" as the product name — the fallback grabbed the raw line without checking whether it had its own embedded label. `_strip_leading_label()` now strips a generic `"Label: "` prefix from any fallback candidate.
- **Skip phone/fax lines when scanning fallback candidates for a name.** A "Tel:"/"Fax:" line (or a line that's mostly digits) sitting between a label and the real value it's for got captured as the value; `_looks_like_boilerplate()` skips these and keeps scanning subsequent lines.
- **Real SDS diversity across vendors is the real test, not one sample.** The Oemeta sample alone passed but a 6-file batch across different vendors (WD-40, Blaster, Lucas, Phillips 66, ACE) surfaced several more failure modes above. Label-search heuristics need testing against several real, differently-formatted SDS before being trusted — revision-date extraction in particular is still missing on a number of real documents and needs more real samples to diagnose further.

## UI Layout (hazcom-db)

- **An empty/near-empty `QListWidget` with no height cap will expand to dominate a dialog.** The department checklist in `SdsDialog` had no `setMaximumHeight`, unlike the equivalent list in `ImportDialog` — confirmed via a real `.grab()` screenshot, not just code review. Cap list/tree widget heights in dialogs explicitly.
- **`QTableWidget` columns default to a fixed ~100px unless given a resize mode or explicit width.** Only column 0 had `Stretch`; the rest were left at the ~100px default, which wrapped header text like "Revision Date" onto two lines. Set explicit widths for non-stretched columns.
- **`QDialog.exec()` blocks the rest of the system, not just the app, in practice.** The user reported being unable to alt-tab to *any other program* while the Add/Import dialog was open. Add/Edit and Import dialogs are now opened non-modally (`.show()` + `finished` signal instead of blocking on `.exec()`'s return value) so the system-default PDF viewer opened for comparison (see below) is actually reachable. `MainWindow._open_dialogs` keeps a strong reference to each open dialog — a non-modal `QDialog` with no other reference gets garbage-collected out from under the user.
- **Opening a file for comparison only helps if you can actually switch to it.** `SdsDialog._set_selected_file` opens the chosen PDF in the system default viewer (`QDesktopServices.openUrl`) so the user can compare it against the auto-filled fields — this only works because the dialog is non-modal (previous note).

## Data Integrity & Batch Review (hazcom-db)

- **A "flag possible duplicates" check computed once at row-population time goes stale the moment cells become editable.** `ImportDialog`'s duplicate flag only reflected the initially auto-filled values; editing a cell afterward didn't recheck it, and two matching rows *within the same batch* were never compared against each other (only against the DB). Recompute on `itemChanged` for the relevant columns, compare against both the DB and sibling rows, and re-validate once more in `accept()` before anything is written.
- **PyQt UI logic can be pytest-covered like anything else** — `tests/test_import_dialog.py` sets `QT_QPA_PLATFORM=offscreen` and drives real `QTableWidgetItem.setText()` edits against a real `QApplication`. CI's test job already installs the Qt system libs and sets this env var, so this isn't new infrastructure, just the first module to use it.

## Easter Eggs

- **Ctrl+Alt+Shift+H** in the main window (`ui/main_window.py:_show_easter_egg`) pops a one-off joke message box. Not listed anywhere in the UI/docs; doesn't affect normal operation. Don't duplicate or break it.
