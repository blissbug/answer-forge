import csv
import io
from types import SimpleNamespace

from app.models import QuestionWorkflowStatus
from app.services.export import export_csv


def test_export_contains_only_approved_questions_with_answers():
    approved = SimpleNamespace(workflow_status=QuestionWorkflowStatus.APPROVED, original_row=2, question_text="How is data encrypted?", current_answer_version=SimpleNamespace(answer_text='"With AES-256."'))
    rejected = SimpleNamespace(workflow_status=QuestionWorkflowStatus.REJECTED, original_row=3, question_text="Rejected question", current_answer_version=SimpleNamespace(answer_text="Do not export"))
    pending = SimpleNamespace(workflow_status=QuestionWorkflowStatus.READY_FOR_REVIEW, original_row=4, question_text="Pending question", current_answer_version=None)
    output = export_csv(SimpleNamespace(question_column="Question", answer_column="Answer", questions=[pending, rejected, approved]))
    rows = list(csv.DictReader(io.StringIO(output)))
    assert rows == [{"Question": "How is data encrypted?", "Answer": "With AES-256."}]
