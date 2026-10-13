import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentRun, AgentRunStatus, AnswerOrigin, AnswerVersion, EvidenceStatus, Question, QuestionnaireStatus, QuestionWorkflowStatus


def create_version(db: Session, question: Question, text: str, evidence: EvidenceStatus, origin: AnswerOrigin, user_id: uuid.UUID) -> AnswerVersion:
    number = (db.scalar(select(func.max(AnswerVersion.version_number)).where(AnswerVersion.question_id == question.id)) or 0) + 1
    version = AnswerVersion(question_id=question.id, version_number=number, answer_text=text.strip(), evidence_status=evidence, origin=origin, created_by_id=user_id)
    db.add(version); db.flush()
    question.current_answer_version_id = version.id
    question.workflow_status = QuestionWorkflowStatus.READY_FOR_REVIEW
    question.not_applicable_reason = None
    question.questionnaire.status = QuestionnaireStatus.IN_REVIEW
    question.questionnaire.completed_at = None
    return version


def cancel_active_agent_runs(db: Session, question: Question) -> None:
    """Human edits win over pending/running automated output for a question."""
    now = datetime.now(timezone.utc)
    for run in question.agent_runs:
        if run.status in {AgentRunStatus.QUEUED, AgentRunStatus.RUNNING}:
            run.status = AgentRunStatus.CANCELLED
            run.completed_at = now
            run.error_message = "Superseded by a human edit."


def cancel_queued_agent_runs(question: Question) -> set[uuid.UUID]:
    """Supersede only work that has not been claimed by an agent worker."""
    now = datetime.now(timezone.utc)
    run_ids: set[uuid.UUID] = set()
    for run in question.agent_runs:
        if run.status == AgentRunStatus.QUEUED:
            run.status = AgentRunStatus.CANCELLED
            run.completed_at = now
            run.progress_message = "Superseded by retry."
            run.error_message = "Superseded by retry before processing started."
            run_ids.add(run.id)
    return run_ids


def approve(db: Session, question: Question) -> None:
    if not question.current_answer_version_id:
        raise HTTPException(status_code=422, detail="A question must have an answer before approval.")
    question.workflow_status = QuestionWorkflowStatus.APPROVED
    refresh_completion(question)


def reject(question: Question) -> None:
    if not question.current_answer_version_id:
        raise HTTPException(status_code=422, detail="There is no answer to reject.")
    question.workflow_status = QuestionWorkflowStatus.REJECTED
    question.questionnaire.status = QuestionnaireStatus.IN_REVIEW


def not_applicable(question: Question, reason: str | None) -> None:
    question.workflow_status = QuestionWorkflowStatus.NOT_APPLICABLE
    question.not_applicable_reason = reason.strip() if reason else None
    refresh_completion(question)


def refresh_completion(question: Question) -> None:
    questionnaire = question.questionnaire
    states = [item.workflow_status for item in questionnaire.questions]
    if states and all(state in {QuestionWorkflowStatus.APPROVED, QuestionWorkflowStatus.NOT_APPLICABLE} for state in states):
        questionnaire.status = QuestionnaireStatus.COMPLETED
        questionnaire.completed_at = datetime.now(timezone.utc)
    else:
        questionnaire.status = QuestionnaireStatus.IN_REVIEW
        questionnaire.completed_at = None
