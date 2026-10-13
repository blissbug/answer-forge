import csv
import io

from app.models import QuestionWorkflowStatus, Questionnaire


def export_csv(questionnaire: Questionnaire) -> str:
    questions = sorted((item for item in questionnaire.questions if item.workflow_status == QuestionWorkflowStatus.APPROVED and item.current_answer_version), key=lambda item: item.original_row)
    columns = [questionnaire.question_column, questionnaire.answer_column]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for question in questions:
        answer = question.current_answer_version.answer_text.strip()
        if len(answer) >= 2 and answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1].strip()
        writer.writerow({questionnaire.question_column: question.question_text, questionnaire.answer_column: answer})
    return output.getvalue()
