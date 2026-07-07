"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function QAPage() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello! I am your portfolio advisory assistant. Ask me questions about your current holdings, diversification, or sector concentrations.",
      citations: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [serviceDown, setServiceDown] = useState(false);
  const [interrupted, setInterrupted] = useState(false);

  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (e, retryInput = null) => {
    if (e) e.preventDefault();
    const query = retryInput || input;
    if (!query.trim()) return;

    if (!retryInput) {
      setInput("");
    }

    setLoading(true);
    setError(null);
    setRateLimited(false);
    setServiceDown(false);
    setInterrupted(false);

    // Add user message and a placeholder assistant message
    const userMsg = { role: "user", content: query };
    const assistantPlaceholder = { role: "assistant", content: "", streaming: true, citations: [] };

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);

    try {
      const response = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: query,
          conversationHistory: messages
            .filter((m) => !m.streaming)
            .map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (response.status === 429) {
        setRateLimited(true);
        throw new Error("Too many requests. Please wait.");
      }
      if (response.status === 503) {
        setServiceDown(true);
        throw new Error("AI service temporarily unavailable. Using rule-based analysis.");
      }
      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || "Failed to submit question");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let completeReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (!completeReceived) {
            setInterrupted(true);
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const rawMessage = buffer.slice(0, boundary + 2);
          buffer = buffer.slice(boundary + 2);

          const lines = rawMessage.split("\n");
          let eventName = "";
          let dataStr = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventName = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              dataStr = line.slice(6).trim();
            }
          }

          if (eventName === "chunk" && dataStr) {
            try {
              const chunkData = JSON.parse(dataStr);
              if (chunkData.text) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === "assistant") {
                    last.content += chunkData.text;
                  }
                  return updated;
                });
              }
            } catch (_) {}
          } else if (eventName === "complete" && dataStr) {
            completeReceived = true;
            try {
              const completeData = JSON.parse(dataStr);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") {
                  last.streaming = false;
                  last.citations = completeData.citations || [];
                }
                return updated;
              });
            } catch (_) {}
          } else if (eventName === "error" && dataStr) {
            try {
              const errData = JSON.parse(dataStr);
              throw new Error(errData.error || "Generation error");
            } catch (e) {
              setError(e.message);
            }
          }

          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      setError(err.message);
      // Clean up the placeholder if we didn't receive any chunks
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && !last.content) {
          return updated.slice(0, -1);
        }
        if (last && last.role === "assistant") {
          last.streaming = false;
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = () => {
    // Find the last user question to retry
    const userMessages = messages.filter((m) => m.role === "user");
    if (userMessages.length > 0) {
      const lastQuestion = userMessages[userMessages.length - 1].content;
      // Remove last user message and following assistant message
      setMessages((prev) => {
        let lastUserIdx = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].role === "user") {
            lastUserIdx = i;
            break;
          }
        }
        if (lastUserIdx !== -1) {
          return prev.slice(0, lastUserIdx);
        }
        return prev;
      });
      handleSend(null, lastQuestion);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Q&A Assistant</h1>
        <p className="text-sm text-slate-400">
          Query regulatory guidelines and get advisory help on your portfolio.
        </p>
      </div>

      {/* Banners for Errors */}
      {serviceDown && (
        <div className="rounded-lg border border-amber-900 bg-amber-950/20 p-3 text-sm text-amber-400">
          ⚠️ AI service temporarily unavailable. Using rule-based analysis.
        </div>
      )}
      {rateLimited && (
        <div className="rounded-lg border border-red-900 bg-red-950/20 p-3 text-sm text-red-400">
          ⚠️ Too many requests. Please wait.
        </div>
      )}

      {/* Chat Container */}
      <Card className="flex flex-col border-slate-800 bg-slate-900/30 h-[600px]">
        {/* Messages Log */}
        <CardContent className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex flex-col ${
                msg.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`rounded-2xl px-4 py-2.5 max-w-[85%] text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-sky-600 text-slate-50 rounded-br-none"
                    : "bg-slate-800/80 text-slate-100 rounded-bl-none border border-slate-700/50"
                }`}
              >
                {msg.role === "user" ? (
                  <p>{msg.content}</p>
                ) : (
                  <div className="prose prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: ({node, ...props}) => <p className="mb-2 last:mb-0" {...props} />,
                        ul: ({node, ...props}) => <ul className="list-disc pl-4 mb-2 space-y-0.5" {...props} />,
                        li: ({node, ...props}) => <li className="text-slate-300" {...props} />,
                      }}
                    >
                      {msg.content || (msg.streaming ? "Thinking..." : "")}
                    </ReactMarkdown>
                  </div>
                )}
              </div>

              {/* Citations / Evidence cards */}
              {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 w-full max-w-[85%] space-y-1.5 pl-2">
                  <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Citations ({msg.citations.length})</p>
                  {msg.citations.map((cite, i) => (
                    <CitationCard key={i} citation={cite} />
                  ))}
                </div>
              )}
            </div>
          ))}

          {/* Interrupted message state */}
          {interrupted && !loading && (
            <div className="flex flex-col items-center justify-center p-4 border border-dashed border-slate-800 rounded-xl bg-slate-900/10 gap-2">
              <p className="text-xs text-slate-400">Stream interrupted before completion.</p>
              <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={handleRetry}>
                Retry Generation
              </Button>
            </div>
          )}

          {error && !serviceDown && !rateLimited && !interrupted && (
            <div className="flex flex-col items-center justify-center p-4 border border-dashed border-red-950 rounded-xl bg-red-950/10 gap-2">
              <p className="text-xs text-red-400">Error: {error}</p>
              <Button size="sm" variant="outline" className="border-red-900/40 text-red-400 hover:bg-red-950/50" onClick={handleRetry}>
                Retry Question
              </Button>
            </div>
          )}

          <div ref={messagesEndRef} />
        </CardContent>

        {/* Input Form Footer */}
        <CardFooter className="border-t border-slate-800/80 bg-slate-950/20 p-4">
          <form onSubmit={handleSend} className="flex w-full items-center gap-2">
            <input
              type="text"
              placeholder="Ask about sector concentration or SEBI guidelines..."
              className="flex-1 rounded-lg border border-slate-800 bg-slate-950 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <Button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-sky-600 hover:bg-sky-500 text-slate-50"
            >
              {loading ? "Sending..." : "Send"}
            </Button>
          </form>
        </CardFooter>
      </Card>
    </div>
  );
}

// Collapsible Citation Card Component
function CitationCard({ citation }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded border border-slate-800 bg-slate-950/50 text-[11px] overflow-hidden transition-all">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-1.5 text-left text-slate-400 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <span className="font-semibold text-slate-300">
          [{citation.source}] {citation.docTitle || "Document"}
        </span>
        <span className="text-[10px] text-slate-500">
          {open ? "Hide excerpt ▲" : "Show excerpt ▼"}
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-900 bg-slate-950 p-2.5 space-y-1">
          <div className="flex justify-between text-[10px] text-slate-500">
            <span>Section: {citation.section || "N/A"}</span>
            <span>Date: {citation.date || "N/A"}</span>
          </div>
          <p className="italic text-slate-300 leading-normal border-l-2 border-sky-500/50 pl-2 mt-1">
            "{citation.relevantText}"
          </p>
        </div>
      )}
    </div>
  );
}
