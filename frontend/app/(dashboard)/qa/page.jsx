"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const prompts = ["What is my portfolio worth?", "How concentrated is my portfolio?", "How does realized P&L differ from unrealized P&L?"];
const fieldLabels = {
  ticker: "Ticker", quantity: "Units", avg_buy_price: "Average purchase price", current_price: "Price",
  invested_cost: "Invested cost", market_value: "Market value", total_invested: "Invested cost",
  total_current: "Market value", realized_pnl: "Realized P&L", unrealized_pnl: "Unrealized P&L",
  price: "Price", symbol: "Ticker", currency: "Currency", published_at: "As of",
  price_source: "Price source", priced_holdings: "Priced positions",
};
const control = "rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50";

async function readAnswer(response, onProgress) {
  if (response.status === 401) throw new Error("Your session expired. Sign in again to continue.");
  if (response.status === 429) throw new Error("Too many questions in a short time. Wait a moment, then retry.");
  if (!response.ok || !response.body) throw new Error("Q&A is temporarily unavailable.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split(/\r?\n\r?\n/);
      pending = events.pop();
      for (const event of events) {
        const lines = event.split(/\r?\n/);
        const kind = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
        const data = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) continue;
        const payload = JSON.parse(data);
        if (kind === "status") onProgress(payload.message);
        if (kind === "complete" && typeof payload.fullText === "string") return payload;
        if (kind === "error") throw new Error("Q&A could not complete this request. Please retry.");
      }
    }
    throw new Error("The connection ended before the answer arrived. Please retry.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export default function QAPage() {
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState("");
  const request = useRef(null);
  const input = useRef(null);
  const busy = turns.some((turn) => turn.status === "pending");

  useEffect(() => () => request.current?.abort(), []);

  async function send(question, retryIndex = turns.length) {
    question = question.trim();
    if (!question || request.current) return;
    const controller = new AbortController();
    request.current = controller;

    const conversationHistory = turns.slice(0, retryIndex)
      .filter((turn) => turn.status === "complete")
      .flatMap((turn) => [{ role: "user", content: turn.question }, { role: "assistant", content: turn.answer }])
      .slice(-8);
    const replaceTurn = (values) => setTurns((previous) => previous.map((turn, index) =>
      index === retryIndex ? { ...turn, ...values } : turn
    ));

    const pending = { question, status: "pending", progress: "Reading your question" };
    setTurns((previous) => retryIndex === previous.length
      ? [...previous, pending]
      : previous.map((turn, index) => index === retryIndex ? pending : turn));
    if (retryIndex === turns.length) setDraft("");

    try {
      const response = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ question, conversationHistory }),
      });
      const answer = await readAnswer(response, (progress) => replaceTurn({ progress }));
      replaceTurn({ status: "complete", answer: answer.fullText, citations: answer.citations });
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof TypeError || error instanceof SyntaxError
          ? "Q&A lost its connection. Please retry."
          : error.message;
        replaceTurn({ status: "failed", error: message });
      }
    } finally {
      request.current = null;
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="border-b border-slate-800 pb-5">
        <h1 className="text-3xl font-semibold tracking-tight">Portfolio Q&A</h1>
        <p className="mt-1 text-sm text-slate-400">Ask about your holdings, Indian equities, or a finance concept.</p>
      </header>

      {turns.length === 0 && (
        <ul aria-label="Suggested questions" className="flex flex-wrap gap-2 py-6">
          {prompts.map((prompt) => <li key={prompt}>
            <button type="button" className={control} onClick={() => { setDraft(prompt); input.current?.focus(); }}>{prompt}</button>
          </li>)}
        </ul>
      )}

      <div className="divide-y divide-slate-800">
        {turns.map((turn, index) => (
          <article key={index} className="space-y-4 py-5">
            <h2 className="break-words text-lg font-medium text-slate-100">{turn.question}</h2>
            {turn.status === "pending" && <p role="status" className="text-sm text-slate-400">{turn.progress}…</p>}
            {turn.status === "failed" && (
              <div className="flex flex-wrap items-center gap-3">
                <p role="alert" className="text-sm text-amber-300">{turn.error}</p>
                {index === turns.length - 1 && <button type="button" onClick={() => send(turn.question, index)} disabled={busy} className={control}>Retry</button>}
              </div>
            )}
            {turn.status === "complete" && (
              <>
                <div className="break-words text-sm leading-relaxed text-slate-200 [&_a]:text-sky-300 [&_a]:underline [&_li]:my-1 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mb-3 [&_table]:my-3 [&_table]:block [&_table]:overflow-x-auto [&_td]:border [&_td]:border-slate-700 [&_td]:p-2 [&_th]:border [&_th]:border-slate-700 [&_th]:p-2 [&_ul]:list-disc [&_ul]:pl-6">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer}</ReactMarkdown>
                </div>
                {turn.citations?.length > 0 && <Sources citations={turn.citations} />}
              </>
            )}
          </article>
        ))}
      </div>

      <form className="space-y-2 border-t border-slate-800 bg-slate-950 pt-4" onSubmit={(event) => { event.preventDefault(); send(draft); }}>
        <label htmlFor="question" className="block text-sm font-medium">Your question</label>
        <textarea id="question" ref={input} rows={2} maxLength={3000} value={draft} onChange={(event) => setDraft(event.target.value)}
          className="w-full resize-y rounded-md border border-slate-700 bg-slate-900/40 px-3 py-2 text-sm text-slate-100"
          placeholder="Ask a question or follow up" />
        <div className="flex justify-end">
          <button type="submit" disabled={busy || !draft.trim()} className="rounded-md bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-white disabled:opacity-50">{busy ? "Waiting for answer" : "Send question"}</button>
        </div>
      </form>
    </div>
  );
}

function Sources({ citations }) {
  return (
    <details className="rounded-md border border-slate-800 px-3 py-2 text-sm">
      <summary className="cursor-pointer text-slate-300">Sources ({citations.length})</summary>
      <ul className="mt-2 divide-y divide-slate-800">
        {citations.map((citation, index) => (
          <li key={citation.section || index} className="py-3">
            <p className="font-medium text-slate-200">{citation.docTitle || citation.source}</p>
            <p className="mt-1 text-xs text-slate-400">{[citation.docTitle && citation.source, citation.date].filter(Boolean).join(" · ")}</p>
            <SourceEvidence content={citation.relevantText} />
          </li>
        ))}
      </ul>
    </details>
  );
}

function SourceEvidence({ content }) {
  if (!content) return null;
  let facts;
  try {
    const record = JSON.parse(content);
    facts = Object.entries(record || {}).filter(([key, value]) =>
      Object.hasOwn(fieldLabels, key) && (value === null || typeof value === "number" || typeof value === "string"));
  } catch {
    return <p className="mt-2 break-words text-slate-400">{content}</p>;
  }
  if (!facts.length) return null;
  return (
    <dl className="mt-2 space-y-1 text-slate-400">
      {facts.map(([key, value]) => <div key={key} className="flex flex-wrap justify-between gap-x-4">
        <dt>{fieldLabels[key]}</dt>
        <dd className="tabular-nums">{value ?? "Unavailable"}</dd>
      </div>)}
    </dl>
  );
}
