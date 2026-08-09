import React, { useState } from "react";
import { api } from "../api";

export default function EmailInput({ onBatchReady, onIngest, ingesting }) {
  const [raw, setRaw] = useState("");
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);

  const parseAndSet = (text) => {
    setError("");
    try {
      const parsed = JSON.parse(text);
      const emails = Array.isArray(parsed) ? parsed : parsed.emails;
      if (!Array.isArray(emails)) throw new Error("Expected a JSON array of emails, or {\"emails\": [...]}");
      onBatchReady(emails);
    } catch (e) {
      onBatchReady([]);
      setError(e.message);
    }
  };

  const handleChange = (e) => {
    setRaw(e.target.value);
    if (e.target.value.trim()) parseAndSet(e.target.value);
    else onBatchReady([]);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const { emails } = await api.sampleEmails(250);
      const text = JSON.stringify(emails, null, 2);
      setRaw(text);
      onBatchReady(emails);
    } catch (e) {
      setError("Could not reach backend to generate samples: " + e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setRaw(text);
    parseAndSet(text);
  };

  return (
    <div className="panel">
      <h2>1 · Paste or generate an email batch</h2>
      <textarea
        placeholder='Paste a JSON array of emails (same schema as inbox.json) here, or generate a sample batch below...'
        value={raw}
        onChange={handleChange}
      />
      {error && <div className="hint" style={{ color: "var(--red)", marginTop: 8 }}>{error}</div>}
      <div className="row">
        <button className="primary" disabled={generating} onClick={handleGenerate}>
          {generating ? "Generating…" : "Generate 250 sample emails"}
        </button>
        <label className="hint" style={{ cursor: "pointer" }}>
          <input type="file" accept=".json" style={{ display: "none" }} onChange={handleFile} />
          <span style={{ textDecoration: "underline" }}>or upload a .json file</span>
        </label>
        <span style={{ flex: 1 }} />
        <button className="primary" disabled={ingesting || !raw.trim()} onClick={onIngest}>
          {ingesting ? "Routing…" : "Route this batch →"}
        </button>
      </div>
    </div>
  );
}
