"use client";

import { useMemo, useState } from "react";

type Document = { id: string; filename: string; status: string; is_deleted: boolean; metadata: Record<string, unknown> };
type Result = { chunk_id: string; document_id: string; filename: string; content: string; metadata: Record<string, unknown> };
type AskCitation = { document_id: string; document_title: string; page_number: number | null; section_title: string | null; quoted_text: string };
type AskResponse = { question: string; answer: string; evidence_status: "STRONG" | "PARTIAL" | "CONFLICTING" | "MISSING"; citations: AskCitation[] };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, options);
  if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(data?.detail ?? "Something went wrong."); }
  return response.json();
}

export function KnowledgeWorkspace({ workspaceId, documents, onSelectDocument }: { workspaceId: string; documents: Document[]; onSelectDocument: (document: Document) => void }) {
  const activeDocuments = useMemo(() => documents.filter((document) => !document.is_deleted && document.status === "READY"), [documents]);
  const [mode, setMode] = useState<"ask" | "search">("ask");
  const [scope, setScope] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const pages = activeDocuments.reduce((sum, document) => sum + Number(document.metadata.page_count ?? 0), 0);
  const passages = activeDocuments.reduce((sum, document) => sum + Number(document.metadata.chunk_count ?? 0), 0);
  const scopeLabel = scope ? activeDocuments.find((document) => document.id === scope)?.filename : "All knowledge";

  const submit = async () => {
    if (!query.trim()) return;
    setLoading(true); setError(""); setResults([]); setAnswer(null);
    try {
      if (mode === "search") setResults(await request<Result[]>(`/workspaces/${workspaceId}/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: query.trim(), top_k: 5, document_id: scope || null }) }));
      else setAnswer(await request<AskResponse>(`/workspaces/${workspaceId}/knowledge/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: query.trim(), document_id: scope || null }) }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Knowledge request failed."); }
    finally { setLoading(false); }
  };

  const coverage = answer?.evidence_status === "STRONG" ? "bg-emerald-50 text-emerald-700" : answer?.evidence_status === "PARTIAL" ? "bg-amber-50 text-amber-700" : answer?.evidence_status === "CONFLICTING" ? "bg-rose-50 text-rose-700" : "bg-amber-100 text-amber-800";
  return <div className="knowledge-workspace">
    <div className="knowledge-heading"><div><p className="eyebrow">Company knowledge</p><h1>Ask your company, not the internet.</h1><p>{activeDocuments.length} active document{activeDocuments.length === 1 ? "" : "s"} · {pages} pages · {passages} indexed passages</p></div><div className="mode-switch"><button className={mode === "ask" ? "active" : ""} onClick={() => { setMode("ask"); setResults([]); setAnswer(null); }}>Ask</button><button className={mode === "search" ? "active" : ""} onClick={() => { setMode("search"); setResults([]); setAnswer(null); }}>Search</button></div></div>
    <div className="query-card"><div className="query-glow" aria-hidden="true" /><label>Search scope<select value={scope} onChange={(event) => setScope(event.target.value)}><option value="">All knowledge</option>{activeDocuments.map((document) => <option key={document.id} value={document.id}>{document.filename}</option>)}</select></label><form onSubmit={(event) => { event.preventDefault(); void submit(); }}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={mode === "ask" ? "Ask anything grounded in your knowledge…" : "Find an exact policy, claim, or passage…"} /><button disabled={loading || !activeDocuments.length || !query.trim()}>{loading ? "Working…" : mode === "ask" ? "Ask" : "Search"}<span aria-hidden="true">→</span></button></form><p>{scopeLabel} · Answers stay grounded in the sources you choose.</p></div>
    {error && <div className="workspace-alert" role="alert">{error}</div>}
    {!activeDocuments.length && <div className="workspace-empty">Add company documents before searching or asking questions.</div>}
    {mode === "search" && results.length === 0 && !loading && query && !error && <div className="workspace-empty">No relevant company knowledge found.</div>}
    {mode === "search" && results.length > 0 && <section className="knowledge-results"><div className="section-heading"><span>Search results</span><h2>Relevant passages</h2></div>{results.map((result) => <article key={result.chunk_id}><div><strong>{result.filename}</strong><span>Page {String(result.metadata.page_number ?? "—")}</span><button onClick={() => window.location.assign(`/?document=${result.document_id}&tab=content`)}>View source ↗</button></div><p>{result.content}</p></article>)}</section>}
    {answer && <section className="knowledge-answer"><div><h2>Answer</h2><span className={`coverage ${coverage}`}>Evidence coverage: {answer.evidence_status}</span></div><p>{answer.answer}</p><h3>Sources</h3>{answer.citations.length ? answer.citations.map((citation) => <article key={`${citation.document_id}-${citation.page_number}-${citation.quoted_text.slice(0, 20)}`}><div><strong>{citation.document_title}</strong><span>{citation.page_number ? `Page ${citation.page_number}` : ""}</span><button onClick={() => window.location.assign(`/?document=${citation.document_id}&tab=content`)}>View source ↗</button></div><p>“{citation.quoted_text}”</p></article>) : <div className="workspace-empty">Available company knowledge does not provide sufficient information to answer this question.</div>}</section>}
    <section className="recent-documents"><div className="section-heading"><span>Your library</span><h2>Recent documents</h2></div><div>{activeDocuments.slice(0, 6).map((document) => <button key={document.id} onClick={() => onSelectDocument(document)}><i aria-hidden="true">{document.filename.split(".").pop()?.slice(0, 3).toUpperCase()}</i><strong>{document.filename}</strong><span>{String(document.metadata.page_count ?? 0)} pages · {String(document.metadata.chunk_count ?? 0)} passages</span><b aria-hidden="true">↗</b></button>)}</div></section>
  </div>;
}
