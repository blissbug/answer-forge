import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AgentRun, AgentRunPhase, AgentRunStatus, AnswerOrigin, Citation, EvidenceStatus, Question, QuestionWorkflowStatus
from app.schemas import SearchResult
from app.services.llm import DraftAnswer, EvidenceAssessment, LLMProvider, RevisedAnswer, VerificationResult
from app.services.review import create_version
from app.services.retrieval import RetrievalService
from app.telemetry import span


MISSING_ANSWER = "Available company knowledge does not provide sufficient information to answer this question."
logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self, retrieval: RetrievalService, llm: LLMProvider, max_rounds: int, top_k: int) -> None:
        self.retrieval, self.llm, self.max_rounds, self.top_k = retrieval, llm, max_rounds, top_k

    def research(self, db: Session, workspace_id: uuid.UUID, question_text: str, run_id: uuid.UUID) -> tuple[list[SearchResult], bool, list[dict]]:
        """Perform only the bounded retrieval/assessment phase; no writes occur."""
        query = question_text
        passages: list[SearchResult] = []
        trace_rounds: list[dict] = []
        sufficient = False
        for round_number in range(self.max_rounds):
            with span("retrieval.search", {"agent_run.id": str(run_id), "retrieval.top_k": self.top_k}):
                results = self.retrieval.search(db, workspace_id, query, self.top_k)
            seen = {item.chunk_id for item in passages}
            passages.extend(result for result in results if result.chunk_id not in seen)
            trace_rounds.append({"query": query, "result_ids": [str(item.chunk_id) for item in results], "result_count": len(results)})
            logger.info("agent_retrieval_round", extra={"agent_run_id": str(run_id), "round": round_number + 1, "result_count": len(results)})
            if not passages:
                break
            run = db.get(AgentRun, run_id) if db is not None else None
            if run is not None:
                self._set_phase(db, run, AgentRunPhase.ASSESSING, "Assessing evidence")
            with span("agent.assess", {"agent_run.id": str(run_id), "retrieval.result_count": len(passages)}):
                assessment = self.llm.generate_structured(f"Assess whether these company passages sufficiently answer the question. Return JSON only. Question: {question_text}\nPassages: {[(str(p.chunk_id), p.content) for p in passages]}", EvidenceAssessment)
            sufficient = assessment.sufficient
            if sufficient or not assessment.suggested_search_query:
                break
            query = assessment.suggested_search_query
        return passages, sufficient, trace_rounds

    def process_run(self, db: Session, run_id: uuid.UUID, user_id: uuid.UUID) -> AgentRun | None:
        run = db.get(AgentRun, run_id)
        if not run or run.status != AgentRunStatus.QUEUED:
            return run
        claimed = db.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == AgentRunStatus.QUEUED).values(status=AgentRunStatus.RUNNING, phase=AgentRunPhase.RETRIEVING, progress_message="Retrieving evidence", started_at=datetime.now(timezone.utc)))
        db.commit()
        if not claimed.rowcount:
            return db.get(AgentRun, run_id)
        db.refresh(run)
        question = db.get(Question, run.question_id)
        assert question is not None
        question.workflow_status = QuestionWorkflowStatus.PROCESSING
        db.commit()
        logger.info("agent_run_started", extra={"agent_run_id": str(run_id), "question_id": str(question.id)})
        started = time.monotonic()
        try:
            with span("agent.retrieve", {"agent_run.id": str(run_id)}):
                passages, sufficient, trace_rounds = self.research(db, question.questionnaire.workspace_id, question.question_text, run_id)
            if not passages or not sufficient:
                return self._persist(db, run, question, MISSING_ANSWER, EvidenceStatus.MISSING, [], user_id, trace_rounds, started)
            self._set_phase(db, run, AgentRunPhase.DRAFTING, "Drafting answer")
            with span("agent.draft", {"agent_run.id": str(run_id)}):
                draft = self.llm.generate_structured(f"Answer only from these company passages. Do not invent facts. Question: {question.question_text}\nPassages: {[(str(p.chunk_id), p.content) for p in passages]}", DraftAnswer)
            selected = [item for item in passages if str(item.chunk_id) in set(draft.citation_chunk_ids)]
            self._set_phase(db, run, AgentRunPhase.VERIFYING, "Verifying supported claims")
            with span("agent.verify", {"agent_run.id": str(run_id)}):
                verification = self.llm.generate_structured(f"Verify every material claim in this answer against supplied passages. Answer: {draft.answer}\nPassages: {[(str(p.chunk_id), p.content) for p in selected]}", VerificationResult)
            if not verification.supported:
                self._set_phase(db, run, AgentRunPhase.REVISING, "Revising unsupported claims")
                with span("agent.revise", {"agent_run.id": str(run_id)}):
                    revised = self.llm.generate_structured(f"Revise this answer once, removing every unsupported claim. Use only these passages and return citations. Unsupported claims: {verification.unsupported_claims}\nAnswer: {draft.answer}\nPassages: {[(str(p.chunk_id), p.content) for p in selected]}", RevisedAnswer)
                selected = [item for item in passages if str(item.chunk_id) in set(revised.citation_chunk_ids)]
                self._set_phase(db, run, AgentRunPhase.VERIFYING, "Verifying revised answer")
                with span("agent.verify", {"agent_run.id": str(run_id)}):
                    verification = self.llm.generate_structured(f"Verify every material claim in this answer against supplied passages. Answer: {revised.answer}\nPassages: {[(str(p.chunk_id), p.content) for p in selected]}", VerificationResult)
                if not verification.supported:
                    return self._persist(db, run, question, MISSING_ANSWER, EvidenceStatus.MISSING, [], user_id, trace_rounds, started)
                draft = DraftAnswer(answer=revised.answer, evidence_status=revised.evidence_status, citation_chunk_ids=revised.citation_chunk_ids)
            usable = [item for item in selected if str(item.chunk_id) in set(verification.usable_citation_ids)]
            return self._persist(db, run, question, draft.answer, verification.evidence_status, usable, user_id, trace_rounds, started)
        except Exception as error:
            db.rollback()
            with db.begin():
                run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
                if run is None:
                    return None
                question = db.scalar(select(Question).where(Question.id == run.question_id).with_for_update())
                if question is None:
                    return run
                run.status = AgentRunStatus.FAILED
                run.phase = AgentRunPhase.FAILED
                run.progress_message = "Generation failed"
                run.error_type = type(error).__name__
                run.error_message = str(error)[:1000]
                run.completed_at = datetime.now(timezone.utc)
                question.workflow_status = QuestionWorkflowStatus.READY_FOR_REVIEW if question.current_answer_version_id else QuestionWorkflowStatus.FAILED
            logger.exception("agent_run_failed", extra={"agent_run_id": str(run_id), "error_type": type(error).__name__})
            return run

    def _persist(self, db: Session, run: AgentRun, question: Question, answer: str, evidence: EvidenceStatus, passages: list[SearchResult], user_id: uuid.UUID, trace_rounds: list[dict], started: float) -> AgentRun:
        db.rollback()
        with db.begin():
            locked_run = db.scalar(select(AgentRun).where(AgentRun.id == run.id).with_for_update())
            locked_question = db.scalar(select(Question).where(Question.id == question.id).with_for_update())
            if locked_run is None or locked_question is None:
                raise RuntimeError("Agent run or question disappeared before result persistence.")
            if locked_run.status != AgentRunStatus.RUNNING:
                return locked_run
            locked_run.phase = AgentRunPhase.PERSISTING
            locked_run.progress_message = "Saving answer"
            version = create_version(db, locked_question, answer, evidence, AnswerOrigin.AGENT, user_id)
            for passage in passages:
                db.add(Citation(answer_version_id=version.id, document_id=passage.document_id, document_chunk_id=passage.chunk_id, quoted_text=passage.content, page_number=passage.metadata.get("page_number"), section_title=passage.metadata.get("section_title"), relevance_score=passage.similarity_score))
            locked_run.answer_version_id = version.id
            locked_run.status = AgentRunStatus.SUCCEEDED
            locked_run.phase = AgentRunPhase.READY_FOR_REVIEW
            locked_run.progress_message = "Ready for review"
            locked_run.retrieval_rounds = len(trace_rounds)
            locked_run.completed_at = datetime.now(timezone.utc)
            locked_run.latency_ms = int((time.monotonic() - started) * 1000)
            locked_run.trace_data = {"retrieval_rounds": trace_rounds, "outcome": evidence.value}
        db.refresh(locked_run)
        logger.info("agent_run_succeeded", extra={"agent_run_id": str(locked_run.id), "answer_version_id": str(locked_run.answer_version_id), "outcome": evidence.value})
        return locked_run

    @staticmethod
    def _set_phase(db: Session, run: AgentRun, phase: AgentRunPhase, message: str) -> None:
        run.phase = phase
        run.progress_message = message
        db.commit()
