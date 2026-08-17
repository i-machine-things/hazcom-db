#!/usr/bin/env python
"""Dev tool: print core.sds_parser.extract_fields() output for one or more
SDS PDFs, for manual review while hardening the parser against real samples.

Usage:
    python tools/inspect_sds.py path/to/one.pdf [more.pdf ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import sds_parser  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    for path in argv:
        print(f"\n=== {path} ===")
        fields = sds_parser.extract_fields(path)
        if not fields:
            print("  (extract_fields returned {} — could not open as a PDF)")
            continue
        for key, value in fields.items():
            print(f"  {key}: {value!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
