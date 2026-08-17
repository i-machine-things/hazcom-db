"""Local-only smoke test against real SDS samples.

Not a correctness check — there's no ground truth for arbitrary dropped-in
files (see tests/fixtures/sds_samples/README.md for the workflow to turn a
real failure into an actual regression test). This just confirms extraction
never raises and returns the expected shape, across whatever real samples
happen to be sitting in fixtures/sds_samples/ locally. Skipped automatically
when that directory is empty, which it always will be in CI.
"""
from pathlib import Path

import pytest

from core import sds_parser

SAMPLES_DIR = Path(__file__).resolve().parent / "fixtures" / "sds_samples"
EXPECTED_KEYS = {"product_name", "manufacturer", "cas_number", "revision_date", "signal_word"}


def _sample_pdfs() -> list[Path]:
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(SAMPLES_DIR.glob("*.pdf"))


@pytest.mark.skipif(not _sample_pdfs(), reason="no local SDS samples in tests/fixtures/sds_samples/")
@pytest.mark.parametrize("pdf_path", _sample_pdfs(), ids=lambda p: p.name)
def test_extract_fields_does_not_crash_on_real_sample(pdf_path):
    fields = sds_parser.extract_fields(pdf_path)
    # {} is a legitimate outcome for a file extract_fields couldn't open at
    # all (e.g. still-encrypted) — the real regression signal is a broken
    # key set on a file that *did* open.
    assert fields == {} or set(fields.keys()) == EXPECTED_KEYS
