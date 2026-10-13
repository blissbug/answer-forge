"use client";

import { useEffect, useState } from "react";

type Questionnaire = {
  id: string;
  workspace_id: string;
  title: string;
  status: string;
  total_questions: number;
  approved_questions: number;
  rejected_questions: number;
  not_applicable_questions: number;
  needs_review_questions: number;
};

type Question = {
  id: string;
  question_text: string;
  workflow_status: string;
  position: number;
  current_answer_version_id: string | null;
  current_answer_evidence_status: string | null;
};
type AnswerVersion = {
  id: string;
  answer_text: string;
  evidence_status: string;
  origin: string;
  version_number: number;
};
type Citation = {
  id: string;
  document_id: string;
  document_filename: string;
  source_removed: boolean;
  quoted_text: string;
  page_number: number | null;
  section_title: string | null;
  relevance_score: number | null;
};
type AgentRun = {
  id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  phase: string;
  progress_message: string | null;
  answer_version_id: string | null;
  retrieval_rounds: number;
  latency_ms: number | null;
  error_message: string | null;
  trace_data: { outcome?: string } | null;
  created_at: string;
  updated_at: string;
};
type SearchResult = { chunk_id: string; document_id: string; filename: string; content: string; metadata: Record<string, unknown>; similarity_score: number };
type DocumentSuggestion = { id: string; filename: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const activeRunStates = new Set(["QUEUED", "RUNNING"]);
const styles: Record<string, string> = {
  hero: "flex w-full items-start justify-between gap-6 overflow-hidden rounded-2xl border border-blue-100 bg-gradient-to-br from-white via-blue-50/60 to-amber-50/60 p-7 shadow-[0_16px_50px_rgba(30,64,175,.07)]",
  heroActions: "flex items-center gap-3", statusPill: "inline-flex h-9 items-center rounded-full border border-blue-200 bg-white/80 px-3 text-[10px] font-extrabold uppercase tracking-wider text-forge-500 shadow-sm",
  progressBlock: "my-7 w-full rounded-2xl border border-slate-200/80 bg-white/70 p-5 shadow-[0_8px_30px_rgba(30,64,175,.05)]", progressHeader: "mb-2 flex justify-between text-xs font-semibold text-slate-600", progressTrack: "h-2.5 overflow-hidden rounded-full bg-amber-100 [&>span]:block [&>span]:h-full [&>span]:rounded-full [&>span]:bg-gradient-to-r [&>span]:from-blue-600 [&>span]:to-amber-400 [&>span]:transition-[width] [&>span]:duration-700",
  stats: "mb-7 grid w-full auto-rows-fr grid-cols-2 gap-3 lg:grid-cols-4", approved: "grid min-h-[96px] grid-rows-[1fr_auto] rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4 shadow-sm [&>strong]:self-start [&>strong]:text-2xl [&>strong]:text-emerald-700 [&>span]:self-end [&>span]:text-xs [&>span]:text-emerald-700/70", needsReview: "grid min-h-[96px] grid-rows-[1fr_auto] rounded-2xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm [&>strong]:self-start [&>strong]:text-2xl [&>strong]:text-amber-700 [&>span]:self-end [&>span]:text-xs [&>span]:text-amber-700/70", rejected: "grid min-h-[96px] grid-rows-[1fr_auto] rounded-2xl border border-rose-100 bg-rose-50/70 p-4 shadow-sm [&>strong]:self-start [&>strong]:text-2xl [&>strong]:text-rose-700 [&>span]:self-end [&>span]:text-xs [&>span]:text-rose-700/70", notApplicable: "grid min-h-[96px] grid-rows-[1fr_auto] rounded-2xl border border-slate-200 bg-white/70 p-4 shadow-sm [&>strong]:self-start [&>strong]:text-2xl [&>strong]:text-slate-700 [&>span]:self-end [&>span]:text-xs [&>span]:text-slate-500",
  generateAllButton: "rounded-xl border border-forge-700 bg-gradient-to-br from-blue-600 to-forge-700 px-4 py-2 font-bold text-white shadow-[0_8px_20px_rgba(30,64,175,.18)] hover:-translate-y-px", continueButton: "rounded-xl border border-slate-200 bg-white/80 px-4 py-2 font-bold text-slate-700 shadow-sm hover:-translate-y-px hover:shadow-md", exportButton: "inline-flex items-center rounded-xl border border-slate-200 bg-white/80 px-4 py-2 font-bold text-slate-700 shadow-sm hover:-translate-y-px hover:shadow-md",
  questionTable: "[&>button]:hover:bg-slate-50", questionState: "flex items-center justify-end gap-2", statusLabel: "rounded-full px-2 py-1 text-[10px] font-bold", statusAPPROVED: "bg-emerald-50 text-emerald-700", statusREADYFORREVIEW: "bg-blue-50 text-forge-500", statusREJECTED: "bg-rose-50 text-rose-700", statusNOTAPPLICABLE: "bg-slate-100 text-slate-600", statusQUEUED: "bg-amber-50 text-amber-700", statusPROCESSING: "bg-amber-50 text-amber-700", statusFAILED: "bg-rose-50 text-rose-700", statusEXTRACTED: "bg-slate-50 text-slate-600", missingEvidenceIcon: "grid h-[17px] w-[17px] place-items-center rounded-full bg-amber-100 text-[11px] font-extrabold text-amber-800",
  reviewModal: "w-[min(1080px,94vw)]", reviewHeader: "relative flex-col !items-stretch bg-white/90", headerLine: "relative flex w-full items-center gap-4", position: "absolute right-9 top-7 whitespace-nowrap text-xs font-bold text-slate-500", headerProgress: "mt-3 h-[3px] w-full overflow-hidden rounded-full bg-amber-100 [&>span]:block [&>span]:h-full [&>span]:bg-gradient-to-r [&>span]:from-blue-600 [&>span]:to-amber-400 [&>span]:transition-[width] [&>span]:duration-500", reviewBody: "p-6 md:px-16 md:py-8", questionSection: "pt-0 [&>h2]:max-w-[850px] [&>h2]:text-2xl [&>h2]:tracking-tight", answerSection: "bg-white", answerMeta: "mb-4 text-xs text-slate-500", saveButton: "rounded-xl border border-forge-700 bg-forge-700 px-3 py-2 font-bold text-white",
  editButton: "mt-4 min-w-[116px] rounded-xl !border-blue-200 !bg-blue-50 px-4 py-2 !font-bold !text-blue-700 hover:!border-blue-300 hover:!bg-blue-100", regenerateButton: "mt-4 min-w-[116px] rounded-xl !border-amber-200 !bg-amber-50 px-4 py-2 !font-bold !text-amber-700 hover:!border-amber-300 hover:!bg-amber-100", generateAnswerButton: "rounded-xl border border-forge-700 bg-forge-700 px-3 py-2 font-bold text-white", evidenceSection: "rounded-2xl bg-blue-50/60 px-6 py-7 md:px-8", evidenceHeading: "mb-5 flex items-start justify-between gap-6", evidenceCount: "text-[11px] font-semibold normal-case tracking-normal text-slate-500", attachButton: "mr-2 min-w-[132px] rounded-xl !border-blue-700 !bg-blue-600 px-4 py-2 !font-bold !text-white shadow-sm hover:!border-blue-800 hover:!bg-blue-700", evidenceSearch: "mt-5 grid gap-4 rounded-xl border border-blue-200 bg-white p-6 shadow-sm", searchTitle: "text-sm font-bold text-forge-900", suggestions: "flex flex-wrap gap-2", suggestion: "rounded-full border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700", searchHint: "m-0 text-xs text-slate-500", resultPicker: "grid max-h-[220px] gap-2 overflow-y-auto", resultOption: "w-full rounded-xl border border-slate-200 bg-white p-3 text-left text-slate-700", selectedResult: "w-full rounded-xl border border-forge-500 bg-amber-50 p-3 text-left text-slate-700", searchActions: "flex justify-end gap-2", cancelEvidenceButton: "min-w-[88px] rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-600", addEvidenceButton: "min-w-[88px] rounded-xl border border-forge-700 bg-forge-700 px-3 py-2 text-white", citationTitle: "flex items-center justify-between gap-3", emptyEvidence: "rounded-xl border border-dashed border-amber-200 bg-white/60 p-5 text-slate-600", reviewNeutralButton: "rounded-xl border border-slate-300 bg-white px-4 py-2 font-bold text-slate-600", reviewRejectButton: "rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 font-bold text-rose-700", reviewApproveButton: "rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 font-bold text-emerald-700",
};

styles.evidenceSearch += " [&>label]:grid [&>label]:gap-2 [&>label]:text-xs [&>label]:font-bold [&>label]:text-slate-700 [&_input]:h-10 [&_input]:w-full [&_input]:rounded-md [&_input]:border [&_input]:border-slate-300 [&_input]:px-3 [&_input]:text-sm [&_.searchAction]:justify-self-end";
styles.searchAction = "rounded-md !border-blue-700 !bg-blue-600 px-4 py-2 text-sm font-bold !text-white shadow-sm hover:!border-blue-800 hover:!bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50";
styles.resultOption += " hover:border-blue-300 hover:bg-blue-50";
styles.hero += " max-md:flex-col";
styles.evidenceHeading += " max-md:flex-col";
styles.headerLine += " max-[480px]:pr-10";
styles.position = "absolute right-0 top-9 whitespace-nowrap text-right text-xs font-bold text-slate-500";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, options);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail ?? "Something went wrong.");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

function readable(value: string) {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function QuestionnairePanel({ questionnaire, onBack, onQuestionnaireUpdated, onDelete }: {
  questionnaire: Questionnaire;
  onBack: () => void;
  onQuestionnaireUpdated: () => Promise<void>;
  onDelete?: () => void;
}) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(null);
  const [queueMessage, setQueueMessage] = useState("");
  const [queueing, setQueueing] = useState(false);

  const refresh = async (): Promise<Question[]> => {
    const next = await request<Question[]>(`/questionnaires/${questionnaire.id}/questions`);
    setQuestions(next);
    await onQuestionnaireUpdated();
    return next;
  };

  useEffect(() => { void refresh(); }, [questionnaire.id]);
  useEffect(() => {
    const stream = new EventSource(`${apiUrl}/questionnaires/${questionnaire.id}/events`);
    const update = () => { void refresh(); };
    stream.addEventListener("run.phase", update);
    stream.addEventListener("run.completed", update);
    stream.addEventListener("run.failed", update);
    return () => stream.close();
  }, [questionnaire.id]);

  const queueAll = async () => {
    setQueueing(true);
    setQueueMessage("");
    try {
      const runs = await request<AgentRun[]>(`/questionnaires/${questionnaire.id}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setQueueMessage(`${runs.length} question${runs.length === 1 ? "" : "s"} queued. Processing continues in the background.`);
      await refresh();
    } catch (error) {
      setQueueMessage(error instanceof Error ? error.message : "Could not queue generation.");
    } finally {
      setQueueing(false);
    }
  };

  const counts = questions.reduce((current, question) => {
    if (question.workflow_status === "APPROVED") current.approved += 1;
    else if (question.workflow_status === "REJECTED") current.rejected += 1;
    else if (question.workflow_status === "NOT_APPLICABLE") current.notApplicable += 1;
    return current;
  }, { approved: 0, rejected: 0, notApplicable: 0 });
  const total = questions.length || questionnaire.total_questions;
  const completed = counts.approved + counts.notApplicable;
  const progress = total ? Math.round((completed / total) * 100) : 0;
  const selected = questions.find((question) => question.id === selectedQuestionId) ?? null;

  return <main className="questionnaire-overview">
    <button className="back-link" onClick={onBack}>← Knowledge Base</button>
    <section className={styles.hero}>
      <div><p className="eyebrow">Questionnaire</p><h1>{questionnaire.title}</h1><p className="muted">{total} questions · {readable(questionnaire.status)}</p></div>
      <div className={styles.heroActions}><span className={styles.statusPill}>{readable(questionnaire.status)}</span>{onDelete && <button className="questionnaire-delete" onClick={onDelete} title="Delete questionnaire" aria-label="Delete questionnaire"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v6m4-6v6" /></svg></button>}</div>
    </section>
    <div className={styles.progressBlock}><div className={styles.progressHeader}><span>Completion</span><strong>{progress}%</strong></div><div className={styles.progressTrack}><span style={{ width: `${progress}%` }} /></div><p>{completed} of {total} questions approved or not applicable</p></div>
    <div className={styles.stats}>
      <div className={styles.approved}><strong>{counts.approved}</strong><span>Approved</span></div>
      <div className={styles.needsReview}><strong>{Math.max(0, total - completed - counts.rejected)}</strong><span>Needs review</span></div>
      <div className={styles.rejected}><strong>{counts.rejected}</strong><span>Rejected</span></div>
      <div className={styles.notApplicable}><strong>{counts.notApplicable}</strong><span>Not applicable</span></div>
    </div>
    <div className="questionnaire-actions">
      <button className={styles.generateAllButton} onClick={() => void queueAll()} disabled={queueing}>{queueing ? "Queueing…" : "Generate Answers"}</button>
      <button className={styles.continueButton} onClick={() => setSelectedQuestionId(questions.find((item) => !["APPROVED", "REJECTED", "NOT_APPLICABLE"].includes(item.workflow_status))?.id ?? questions[0]?.id ?? null)} disabled={!questions.length}>Continue review</button>
      <a className={styles.exportButton} href={`${apiUrl}/questionnaires/${questionnaire.id}/export?format=csv`}>Export approved CSV</a>
    </div>
    {queueMessage && <p className="generation-message" role="status">{queueMessage}</p>}
    <div className="tabs"><button className="active">Questions</button></div>
    <div className={`question-table ${styles.questionTable}`}>
      {questions.map((question) => <button key={question.id} onClick={() => setSelectedQuestionId(question.id)}>
        <span>{question.position}</span><strong>{question.question_text}</strong><div className={styles.questionState}><em className={`${styles.statusLabel} ${styles[`status${question.workflow_status.replaceAll("_", "")}`] ?? ""}`}>{readable(question.workflow_status)}</em>{question.current_answer_evidence_status === "MISSING" && <span className={styles.missingEvidenceIcon} title="No supported evidence found" aria-label="No supported evidence found">!</span>}</div>
      </button>)}
    </div>
    {selected && <QuestionReview question={selected} workspaceId={questionnaire.workspace_id} questionnaireTitle={questionnaire.title} questionCount={questions.length} onClose={() => { setSelectedQuestionId(null); void refresh(); }} onChanged={refresh} onDecision={async (resolvedQuestionId) => {
      const nextQuestions = await refresh();
      const currentIndex = nextQuestions.findIndex((item) => item.id === resolvedQuestionId);
      const unresolved = (item: Question) => !["APPROVED", "REJECTED", "NOT_APPLICABLE"].includes(item.workflow_status);
      const next = nextQuestions.find((item, index) => index > currentIndex && unresolved(item)) ?? nextQuestions.find(unresolved);
      setSelectedQuestionId(next?.id ?? null);
    }} />}
  </main>;
}

function QuestionReview({ question, workspaceId, questionnaireTitle, questionCount, onClose, onChanged, onDecision }: {
  question: Question;
  workspaceId: string;
  questionnaireTitle: string;
  questionCount: number;
  onClose: () => void;
  onChanged: () => Promise<Question[]>;
  onDecision: (resolvedQuestionId: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState<AnswerVersion | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [evidenceResults, setEvidenceResults] = useState<SearchResult[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<SearchResult | null>(null);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(new Set());
  const [availableDocuments, setAvailableDocuments] = useState<DocumentSuggestion[]>([]);
  const [documentSuggestions, setDocumentSuggestions] = useState<DocumentSuggestion[]>([]);
  const [evidenceBusy, setEvidenceBusy] = useState(false);

  const refresh = async () => {
    const [nextRuns, nextAnswer] = await Promise.all([
      request<AgentRun[]>(`/questions/${question.id}/agent-runs`),
      question.current_answer_version_id ? request<AnswerVersion>(`/answer-versions/${question.current_answer_version_id}`) : Promise.resolve(null),
    ]);
    setRuns(nextRuns);
    setAnswer(nextAnswer);
    setDraft(nextAnswer?.answer_text ?? "");
    if (nextAnswer) setCitations(await request<Citation[]>(`/answer-versions/${nextAnswer.id}/citations`)); else setCitations([]);
  };

  useEffect(() => { void refresh(); }, [question.id, question.current_answer_version_id]);
  useEffect(() => { setMessage(""); setEditing(false); setEvidenceOpen(false); setEvidenceQuery(question.question_text); setEvidenceResults([]); setDocumentSuggestions([]); setSelectedEvidence(null); setExpandedCitations(new Set()); }, [question.id, question.question_text]);
  useEffect(() => {
    if (!evidenceOpen) return;
    void request<DocumentSuggestion[]>(`/workspaces/${workspaceId}/documents?visibility=active`).then(setAvailableDocuments).catch((error) => setMessage(error instanceof Error ? error.message : "Could not load company knowledge."));
  }, [evidenceOpen, workspaceId]);
  useEffect(() => {
    const needle = evidenceQuery.trim().toLowerCase();
    setDocumentSuggestions(needle.length < 2 ? [] : availableDocuments.filter((document) => document.filename.toLowerCase().includes(needle)).slice(0, 5));
  }, [availableDocuments, evidenceQuery]);
  const searchEvidence = async () => {
    if (evidenceQuery.trim().length < 2) return;
    setEvidenceBusy(true);
    setMessage("");
    try {
      setEvidenceResults(await request<SearchResult[]>(`/workspaces/${workspaceId}/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: evidenceQuery.trim(), top_k: 5 }) }));
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not search company knowledge."); }
    finally { setEvidenceBusy(false); }
  };
  const activeRun = runs.find((run) => activeRunStates.has(run.status));

  const save = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await request(`/questions/${question.id}/answers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer_text: draft, evidence_status: "MISSING" }) });
      setEditing(false);
      await onChanged();
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save the answer."); } finally { setBusy(false); }
  };

  const action = async (name: "approve" | "reject" | "not-applicable") => {
    setBusy(true);
    try {
      if (name === "approve" && !answer && draft.trim()) await save();
      await request(`/questions/${question.id}/${name}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: name === "not-applicable" ? JSON.stringify({}) : undefined });
      setEditing(false);
      await onDecision(question.id);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not update this question."); } finally { setBusy(false); }
  };

  const regenerate = async () => {
    setBusy(true);
    setMessage("");
    try {
      const run = await request<AgentRun>(`/questions/${question.id}/regenerate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
      setRuns((existing) => [run, ...existing.filter((item) => item.id !== run.id)]);
      setMessage("Regeneration queued. The current answer remains available until a new result is ready.");
      await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not queue regeneration."); } finally { setBusy(false); }
  };

  const retryQueued = async () => {
    setBusy(true);
    setMessage("");
    try {
      const run = await request<AgentRun>(`/questions/${question.id}/agent-runs/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
      setRuns((existing) => [run, ...existing.filter((item) => item.id !== run.id)]);
      setMessage("Queued attempt replaced. AnswerForge will process the new attempt.");
      await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not retry the queued answer."); } finally { setBusy(false); }
  };

  const attachEvidence = async (result: SearchResult) => {
    if (!answer) return;
    setEvidenceBusy(true);
    try {
      await request(`/answer-versions/${answer.id}/citations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ document_chunk_id: result.chunk_id }) });
      await refresh();
      setEvidenceOpen(false);
      setEvidenceResults([]);
      setSelectedEvidence(null);
      setMessage("Evidence citation attached. It is recorded as human-selected support and does not automatically change the evidence assessment.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not attach evidence."); } finally { setEvidenceBusy(false); }
  };

  return <div className="review-overlay"><section className={`review-modal ${styles.reviewModal}`}>
    <header className={styles.reviewHeader}><div className={styles.headerLine}><div><p className="eyebrow">Review questionnaire</p><strong>{questionnaireTitle}</strong></div><span className={styles.position}>{question.position} / {questionCount}</span><button className="absolute right-0 top-0 grid h-8 w-8 place-items-center rounded-md text-xl text-slate-500 hover:bg-slate-200" onClick={onClose} aria-label="Close review">×</button></div><div className={styles.headerProgress}><span style={{ width: `${Math.min(100, Math.round((question.position / Math.max(1, questionCount)) * 100))}%` }} /></div></header>
    <main className={styles.reviewBody}>
      <section className={styles.questionSection}><div className="review-label">Question</div><h2>{question.question_text}</h2></section>
      <section className={styles.answerSection}><div className="review-label">Answer</div>
        {activeRun && <p className="agent-state"><span className="status-dot status-dot-processing" /> {activeRun.phase === "QUEUED" ? "AnswerForge has queued this answer." : `AnswerForge is ${readable(activeRun.phase).toLowerCase()}.`}{activeRun.status === "QUEUED" && <button className={styles.regenerateButton} onClick={() => void retryQueued()} disabled={busy}>Retry queue</button>}</p>}
        {answer && <p className={styles.answerMeta}>{answer.origin === "AGENT" ? "Generated by AnswerForge" : answer.origin === "EDITED" ? "Edited by human" : answer.origin === "MANUAL" ? "Written by human" : "Imported answer"} · v{answer.version_number}</p>}
        {editing ? <><textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={8} /><button className={styles.saveButton} onClick={() => void save()} disabled={busy || !draft.trim()}>Save revision</button></> : answer ? <><p className="answer-copy">{answer.answer_text}</p><div className="inline-actions"><button className={styles.editButton} onClick={() => setEditing(true)}>Edit answer</button><button className={styles.regenerateButton} onClick={() => void regenerate()} disabled={busy || Boolean(activeRun)}>Regenerate</button></div></> : <div className="inline-actions"><button className={styles.generateAnswerButton} onClick={() => void regenerate()} disabled={busy || Boolean(activeRun)}>Generate answer</button><button className={styles.editButton} onClick={() => setEditing(true)}>Write answer</button></div>}
      </section>
      <section className={`evidence-panel ${styles.evidenceSection}`}><div className={styles.evidenceHeading}><div><div className="review-label">Evidence <span className={styles.evidenceCount}>· {answer?.evidence_status ?? "MISSING"} · {citations.length} source{citations.length === 1 ? "" : "s"}</span></div><p>Sources are stored as snapshots, so they remain readable even if knowledge is later removed.</p></div>{answer && <button className={styles.attachButton} onClick={() => setEvidenceOpen((open) => !open)}>{evidenceOpen ? "Close" : "+ Find evidence"}</button>}</div>
                {evidenceOpen && <div className={styles.evidenceSearch}><div className={styles.searchTitle}>Find supporting company evidence</div><label>Search company knowledge<input value={evidenceQuery} onChange={(event) => setEvidenceQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void searchEvidence(); }} placeholder="Start typing a document or topic…" /></label><button className={styles.searchAction} onClick={() => void searchEvidence()} disabled={evidenceBusy || evidenceQuery.trim().length < 2}>Search</button>{documentSuggestions.length > 0 && <div className={styles.suggestions}>{documentSuggestions.map((document) => <button key={document.id} className={styles.suggestion} onClick={() => setEvidenceQuery(document.filename)}><span>Document</span>{document.filename}</button>)}</div>}<p className={styles.searchHint}>{evidenceQuery.trim().length < 2 ? "Type at least two characters for document suggestions and search." : evidenceBusy ? "Searching knowledge…" : "Select a passage, then add it as evidence."}</p>{evidenceResults.length > 0 && <div className={styles.resultPicker}>{evidenceResults.map((result) => <button key={result.chunk_id} className={result.chunk_id === selectedEvidence?.chunk_id ? styles.selectedResult : styles.resultOption} onClick={() => setSelectedEvidence(result)}><span><strong>{result.filename}</strong> · Page {String(result.metadata.page_number ?? "—")}</span><p>{result.content}</p></button>)}</div>}<div className={styles.searchActions}><button className={styles.cancelEvidenceButton} onClick={() => { setEvidenceOpen(false); setSelectedEvidence(null); }}>Cancel</button>{selectedEvidence && <button className={styles.addEvidenceButton} onClick={() => void attachEvidence(selectedEvidence)} disabled={evidenceBusy}>Add evidence</button>}</div></div>}
        {citations.length ? <div className="citation-list">{citations.map((citation) => <article key={citation.id}><div className={styles.citationTitle}><strong>{citation.document_filename}{citation.page_number ? ` · Page ${citation.page_number}` : ""}</strong>{citation.source_removed ? <button className="text-action source-disabled" disabled title="Source removed from knowledge">View source ↗</button> : <button className="text-action" onClick={() => { window.location.assign(`/?document=${citation.document_id}&tab=content`); }}>View source ↗</button>}</div>{citation.source_removed && <p className="removed-source-copy">This source is no longer active. The quoted evidence snapshot is retained for historical context.</p>}<p>{expandedCitations.has(citation.id) ? citation.quoted_text.replaceAll("\\\\n", " ") : `${citation.quoted_text.replaceAll("\\\\n", " ").slice(0, 280)}${citation.quoted_text.replaceAll("\\\\n", " ").length > 280 ? "…" : ""}`}</p>{citation.quoted_text.replaceAll("\\\\n", " ").length > 280 && <button className="text-action" onClick={() => setExpandedCitations((current) => { const next = new Set(current); if (next.has(citation.id)) next.delete(citation.id); else next.add(citation.id); return next; })}>{expandedCitations.has(citation.id) ? "Show less" : "Show more"}</button>}</article>)}</div> : <div className={styles.emptyEvidence}><strong>{answer?.origin === "EDITED" || answer?.origin === "MANUAL" ? "No supported evidence found for this human edit" : activeRun ? "Evidence is being gathered" : "No evidence attached"}</strong><p>{answer?.origin === "EDITED" || answer?.origin === "MANUAL" ? "Attach company knowledge below to retain a human-selected citation. This does not automatically mark the answer as supported." : activeRun ? "Citations will appear only when the generated answer is ready." : "This answer does not currently have supporting company knowledge citations."}</p></div>}
      </section>
      {runs[0] && <section><div className="review-label">Generation details</div><p className="muted">Latest run: {readable(runs[0].status)} · {runs[0].retrieval_rounds} retrieval round{runs[0].retrieval_rounds === 1 ? "" : "s"}{runs[0].latency_ms ? ` · ${(runs[0].latency_ms / 1000).toFixed(1)}s` : ""}</p>{runs[0].error_message && <p className="agent-error">{runs[0].error_message}</p>}</section>}
      {message && <p className="agent-message" role="status">{message}</p>}
    </main>
    <footer><button className={styles.reviewNeutralButton} onClick={() => void action("not-applicable")} disabled={busy}>Not applicable</button><button className={styles.reviewRejectButton} onClick={() => void action("reject")} disabled={busy || !answer}>Reject</button><button className={styles.reviewApproveButton} onClick={() => void action("approve")} disabled={busy || (!answer && !draft.trim())}>Approve →</button></footer>
  </section></div>;
}
