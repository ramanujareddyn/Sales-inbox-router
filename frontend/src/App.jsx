import React, { useState, useEffect, useCallback } from "react";
import { api, BASE_URL } from "./api";
import EmailInput from "./components/EmailInput";
import EmailTable from "./components/EmailTable";
import TaskResults from "./components/TaskResults";
import ChatPanel from "./components/ChatPanel";

const DEFAULT_CANDIDATE = import.meta.env.VITE_CANDIDATE_ID || "priya.sharma@gmail.com";

export default function App() {
  const [candidateId, setCandidateId] = useState(DEFAULT_CANDIDATE);
  const [batch, setBatch] = useState([]);
  const [ingesting, setIngesting] = useState(false);
  const [tasks, setTasks] = useState(null);
  const [skipped, setSkipped] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async (cid) => {
    try {
      const [t, s] = await Promise.all([api.tasks(cid), api.stats(cid)]);
      setTasks(t.tasks);
      setSkipped(t.skipped_emails);
      setSummary(s);
    } catch (e) {
      // backend may not have any data yet for this candidate — not an error state
    }
  }, []);

  useEffect(() => { refresh(candidateId); }, [candidateId, refresh]);

  const handleIngest = async () => {
    if (!batch.length) return;
    setIngesting(true);
    setError("");
    try {
      const chunks = [];
      for (let i = 0; i < batch.length; i += 100) chunks.push(batch.slice(i, i + 100));
      let agg = { processed: 0, tasks_created: 0, tasks_updated: 0, skipped: 0 };
      for (const chunk of chunks) {
        const r = await api.ingest(candidateId, chunk, `ui-${Date.now()}`);
        agg.processed += r.processed;
        agg.tasks_created += r.tasks_created;
        agg.tasks_updated += r.tasks_updated;
        agg.skipped += r.skipped;
      }
      await refresh(candidateId);
    } catch (e) {
      setError("Ingest failed: " + e.message);
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="app">
      <div className="header">
        <div className="brand">
          <span className="mark">ROUTER</span>
          <h1>Sales Inbox → Task Router</h1>
        </div>
        <div className="candidate-row">
          candidate_id
          <input value={candidateId} onChange={(e) => setCandidateId(e.target.value.trim())} />
        </div>
      </div>
      <p className="subhead">
        Backend: <span className="mono">{BASE_URL}</span> · paste an inbox batch, watch it route itself, ask questions about what happened.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {summary && (
        <div className="stat-strip">
          <span className="stat-chip"><span className="dot" style={{ background: "var(--teal)" }} /> {summary.tasks_created} created</span>
          <span className="stat-chip"><span className="dot" style={{ background: "var(--blue)" }} /> {summary.tasks_updated} updated</span>
          <span className="stat-chip"><span className="dot" style={{ background: "var(--muted)" }} /> {summary.skipped} skipped</span>
          <span className="stat-chip"><span className="dot" style={{ background: "var(--red)" }} /> {summary.spurious_flagged} spurious-flagged</span>
        </div>
      )}

      <EmailInput onBatchReady={setBatch} onIngest={handleIngest} ingesting={ingesting} />
      <EmailTable emails={batch} />
      <TaskResults tasks={tasks} skipped={skipped} summary={summary} />
      <ChatPanel candidateId={candidateId} />
    </div>
  );
}
