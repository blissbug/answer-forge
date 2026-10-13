from openpyxl import Workbook

from app.services.questionnaire_import import read_rows


def test_csv_rows_preserve_headers_and_original_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "questions.csv"
    source.write_text("section,question,response\nSecurity,Supports SAML?,\n,,\n", encoding="utf-8")
    columns, rows = read_rows(source)
    assert columns == ["section", "question", "response"]
    assert rows[0] == (2, {"section": "Security", "question": "Supports SAML?", "response": ""})
    assert rows[1][0] == 3


def test_xlsx_rows_preserve_headers_and_original_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "questions.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["question", "response"])
    sheet.append(["What is the SLA?", ""])
    workbook.save(source)
    columns, rows = read_rows(source)
    assert columns == ["question", "response"]
    assert rows == [(2, {"question": "What is the SLA?", "response": ""})]
