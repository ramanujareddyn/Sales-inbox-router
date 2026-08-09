import React, { useState, useRef, useEffect } from "react";
import { api } from "../api";

const SUGGESTIONS = [
  "How many emails were proposal or RFP related?",
  "How many were marketing versus actual spam we correctly ignored?",
  "Show me everything sitting in triage and why.",
  "What's our spurious rate so far?",
  "Which tasks are high priority but low confidence?",
];

export default function ChatPanel({ candidateId }) {
  const [messages, setMessages] = useState([
    { role: "bot", text: "Ask me about the emails you've routed — counts, triage items, spurious rate, whatever you need. I only answer from data actually processed, so I'll say \"zero\" or \"I don't have that\" rather than guess." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(candidateId, q);
      setMessages((m) => [...m, { role: "bot", text: res.answer, data: res.supporting_data }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "bot", text: "Couldn't reach the backend: " + e.message }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h2>4 · Ask about this batch</h2>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <span className="suggestion" key={s} onClick={() => send(s)}>{s}</span>
        ))}
      </div>
      <div className="chat-log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.data && Object.keys(m.data).length > 0 && (
              <div className="meta">{JSON.stringify(m.data)}</div>
            )}
          </div>
        ))}
        {busy && <div className="msg bot hint">thinking…</div>}
      </div>
      <div className="chat-input-row">
        <input
          placeholder="Ask a question about the processed emails…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="primary" onClick={() => send()} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
