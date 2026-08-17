# SDS sample PDFs (local only)

Drop real SDS PDF files in this directory to test `core/sds_parser.py`
against them locally. This directory is gitignored except for this file —
real vendor SDS PDFs are not ours to redistribute, so they never get
committed.

## Using them

- `pytest tests/test_sds_parser_samples.py -v` runs a smoke check (auto-fill
  must not raise) against every PDF found here. It's skipped automatically
  when the directory is empty, including in CI.
- `python tools/inspect_sds.py path/to/one.pdf [more.pdf ...]` prints the
  extracted fields for manual review — the fastest way to see what
  `extract_fields()` actually got right or wrong for a given file.

## Adding a regression test from a bad sample

When a sample surfaces a new failure pattern:

1. Don't commit the PDF itself.
2. Copy just the relevant lines of its extracted text (`extract_fields`
   works from a text blob — `core/sds_parser.extract_fields_from_text` is
   the pure-text entry point used by `tests/test_sds_parser.py`) into a new
   test case there, trimmed down to whatever reproduces the bug.
3. Fix the bug, confirm the new test passes, and log the pattern under
   "PDF Field Extraction" in `.claude/CODING_NOTES.md`.
