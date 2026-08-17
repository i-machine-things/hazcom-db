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


def test_extract_fields_from_text_strips_embedded_label_from_fallback_line():
    # Real-world case (Goo Gone SDS): "Product identifier" has no same-line
    # value, and the fallback next-line grab landed on a line that itself
    # starts with a different field's label ("Trade name:").
    text = "Product identifier\nTrade name: Goo Gone Goo & Adhesive Remover\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["product_name"] == "Goo Gone Goo & Adhesive Remover"


def test_extract_fields_from_text_manufacturer_not_matched_mid_sentence():
    # Real-world case: "manufacturer" appearing inside an unrelated sentence
    # (boilerplate/disclaimer text) must not be treated as the field label.
    text = "For questions not covered here, please contact the manufacturer directly.\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["manufacturer"] is None


def test_extract_fields_from_text_manufacturer_skips_phone_number_fallback_line():
    # Real-world case: a phone/fax line sitting between the "Manufacturer"
    # label and the actual company name must be skipped, not captured.
    text = "Manufacturer\nTel : +1-888-555-0100\nACME Corp\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["manufacturer"] == "ACME Corp"


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


def test_extract_fields_from_text_explicit_none_label_is_authoritative():
    # A labeled "Signal word: None" must not be overridden by an unrelated
    # standalone DANGER elsewhere in the document (e.g. in another section).
    text = (
        "Signal word None.\n"
        "16. Other information\n"
        "DANGER: keep out of reach of children.\n"
    )
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["signal_word"] is None


def test_extract_fields_from_text_rejects_impossible_calendar_date():
    text = "Revision Date: 2024-13-40\n"
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["revision_date"] is None


def test_extract_fields_from_text_missing_fields_are_none():
    fields = sds_parser.extract_fields_from_text("Just some unrelated text.\n")
    assert fields["product_name"] is None
    assert fields["manufacturer"] is None
    assert fields["cas_number"] is None
    assert fields["revision_date"] is None
    assert fields["signal_word"] is None


def test_extract_fields_from_text_real_world_sample():
    # Excerpted (pages 1-2) from a real Oemeta NOVAMET 875 SDS. Regression
    # coverage for two bugs a real sample surfaced: "Manufacturer/Supplier"
    # (compound label on one line) and "Revision date: X Issue date: Y"
    # (two label:value pairs sharing one line, dash-separated MM-DD-YYYY).
    text = (
        "SAFETY DATA SHEET\n"
        "1. Identification\n"
        "Product identifier NOVAMET 875\n"
        "Other means of identification\n"
        "Article-No. 40870330\n"
        "Recommended use Water-miscible metal working fluid. Industrial use.\n"
        "Recommended restrictions None known.\n"
        "Manufacturer/Supplier\n"
        "Oemeta, Inc.\n"
        "2339 South Decker Lake Blvd\n"
        "West Valley City, UT 84119\n"
        "Phone: (+1) 801 953-0381\n"
        "Fax: (+1) 801 953-0446\n"
        "2. Hazard(s) identification\n"
        "Physical hazards Not classified.\n"
        "Health hazards Not classified.\n"
        "Label elements\n"
        "Hazard symbol None.\n"
        "Signal word None.\n"
        "3. Composition/information on ingredients\n"
        "Mixtures\n"
        "1 / 8\n"
        "Material name: NOVAMET 875\n"
        "40870330 Version #: 1.0 Revision date: 08-03-2017 Issue date: 08-03-2017\n"
        "SDS US\n"
        "Chemical name Common name and synonyms CAS number %\n"
        "Distillates, petroleum, hydrotreated 64742-53-6\n"
        "light naphthenic\n"
        "50 - < 60\n"
        "Alcohols, C16-18 and C18-unsatd., 68920-66-1\n"
        "ethoxylated\n"
        "1 - < 5\n"
        "Boric acid 10043-35-3 1 - < 3\n"
        "Ethanol, 2-(2-butoxyethoxy)- 112-34-5 1 - < 5\n"
        "Other components below reportable levels 30 - < 40\n"
        "Ethanol, 2,2'-(methylimino)bis- 105-59-9 1 - < 5\n"
    )
    fields = sds_parser.extract_fields_from_text(text)
    assert fields["product_name"] == "NOVAMET 875"
    assert fields["manufacturer"] == "Oemeta, Inc."
    assert fields["cas_number"] == "64742-53-6, 68920-66-1, 10043-35-3, 112-34-5, 105-59-9"
    assert fields["revision_date"] == "2017-08-03"
    assert fields["signal_word"] is None  # SDS explicitly states "Signal word None."


def test_extract_fields_returns_empty_dict_for_encrypted_pdf(tmp_path):
    # PdfReader() can construct successfully for an encrypted PDF, but page
    # access (len(reader.pages)) raises FileNotDecryptedError — must not
    # escape extract_fields uncaught.
    pdf_path = tmp_path / "encrypted.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("secret")
    with open(pdf_path, "wb") as f:
        writer.write(f)

    assert sds_parser.extract_fields(pdf_path) == {}


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
