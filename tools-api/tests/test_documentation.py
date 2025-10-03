import textwrap

from app.runtime.documentation import render_documentation


def test_render_documentation_includes_service_catalog():
    output = render_documentation()

    normalized = textwrap.dedent(output)

    assert "Rich Text Parser" in normalized
    assert "POST /parse/html" in normalized
    assert "Google Docs JSON Parser" in normalized
    assert "Docx Toolkit" in normalized
    assert "Interactive documentation: http://localhost:8000/docs" in normalized
