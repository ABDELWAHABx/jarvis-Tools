import io
from app.services.docx_service import create_docx_from_text, parse_docx_to_text


def test_create_and_parse_docx_roundtrip():
    text = "Hello World\n\nThis is a second paragraph.\nWith a line break."
    b = create_docx_from_text(text)
    assert isinstance(b, (bytes, bytearray))
    # parse back
    parsed = parse_docx_to_text(b)
    assert "Hello World" in parsed
    assert "This is a second paragraph" in parsed
