import pypdf

from core import sds_parser


def test_extract_fields_from_text_colon_style():
    text = (
        "SAFETY DATA SHEET\n"
        "Product Name: Acetone\n"
        "Manufacturer: ACME Chemical Co.\n"
        "CAS Number: 67-64-1\n"
        "Revision Date: 2024-01-15\n"
        "Signal Word: Danger\n"
    )
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["product_name"] == "Acetone"
    assert fields["manufacturer"] == "ACME Chemical Co."
    assert fields["cas_number"] == "67-64-1"
    assert fields["revision_date"] == "2024-01-15"
    assert fields["signal_word"] == "Danger"


def test_extract_fields_from_text_next_line_style():
    text = (
        "Product identifier\n"
        "Acetone, ACS Grade\n"
        "\n"
        "Supplier\n"
        "ACME Chemical Co.\n"
        "123 Main St\n"
    )
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["product_name"] == "Acetone, ACS Grade"
    assert fields["manufacturer"] == "ACME Chemical Co."


def test_extract_fields_from_text_us_date_format():
    text = "Revision Date: 01/15/2024\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["revision_date"] == "2024-01-15"


def test_extract_fields_from_text_month_name_date_format():
    text = "Date of issue: January 15, 2024\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["revision_date"] == "2024-01-15"


def test_extract_fields_from_text_dedupes_multiple_cas_numbers():
    text = (
        "Water 7732-18-5\n"
        "Acetone 67-64-1\n"
        "Acetone 67-64-1\n"
    )
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["cas_number"] == "7732-18-5, 67-64-1"


def test_extract_fields_from_text_signal_word_fallback_without_label():
    text = "SECTION 2: HAZARDS IDENTIFICATION\nDANGER\nFlammable liquid.\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["signal_word"] == "Danger"


def test_extract_fields_from_text_missing_fields_are_none():
    fields = sds_parser.extract_fields_from_text("Just some unrelated text.\n")
    assert fields["product_name"] is None
    assert fields["manufacturer"] is None
    assert fields["cas_number"] is None
    assert fields["revision_date"] is None
    assert fields["signal_word"] is None


def test_extract_fields_returns_empty_dict_for_non_pdf_file(tmp_path):
    fake = tmp_path / "not_a_pdf.pdf"
    fake.write_text("this is not a real pdf")
    assert sds_parser.extract_fields(fake) == {}


def test_extract_fields_returns_empty_dict_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.pdf"
    assert sds_parser.extract_fields(missing) == {}


def test_extract_fields_handles_valid_but_textless_pdf(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    fields = sds_parser.extract_fields(pdf_path)
    assert fields == {
        "product_name": None,
        "manufacturer": None,
        "cas_number": None,
        "revision_date": None,
        "signal_word": None,
    }
