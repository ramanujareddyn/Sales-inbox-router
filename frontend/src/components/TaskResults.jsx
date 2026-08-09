import React, { useState } from "react";

const CAT_COLOR = {
  enterprise_rfp: "#5b9bf0",
  smb_enquiry: "#34c9a8",
  marketing: "#f0a93f",
  alliances: "#c48cf2",
  finance: "#f0e14a",
  triage: "#8993a4",
};

const ASSIGNEE_NAME = {
  u_aarti: "Aarti Menon", u_rohit: "Rohit Sharma", u_meera: "Meera Iyer",
  u_karan: "Karan Doshi", u_divya: "Divya Rao", u_triage: "Triage Queue",
};

export default function TaskResults({ tasks, skipped, summary }) {
  const [tab, setTab] = useState("tasks");

  if (!tasks && !skipped) {
    return (
      <div className="panel">
        <h2>3 · Routed output</h2>
        <div className="empty">Route a batch to see tasks and skipped emails here.</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h2>3 · Routed output</h2>
      {summary && (
        <div className="row" style={{ marginTop: 0, marginBottom: 14 }}>
          <span className="stat-chip">processed <b>{summary.processed}</b></span>
          <span className="stat-chip">created <b style={{color: "var(--teal)"}}>{summary.tasks_created}</b></span>
          <span className="stat-chip">updated <b style={{color: "var(--blue)"}}>{summary.tasks_updated}</b></span>
          <span className="stat-chip">skipped <b style={{color: "var(--muted)"}}>{summary.skipped}</b></span>
        </div>
      )}
      <div className="row" style={{ marginTop: 0 }}>
        <button onClick={() => setTab("tasks")} style={{ borderColor: tab === "tasks" ? "var(--amber)" : undefined }}>
          Tasks ({tasks?.length || 0})
        </button>
        <button onClick={() => setTab("skipped")} style={{ borderColor: tab === "skipped" ? "var(--amber)" : undefined }}>
          Skipped ({skipped?.length || 0})
        </button>
      </div>

      {tab === "tasks" && (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>Task</th><th>Assignee</th><th>Category</th><th>Priority</th>
                <th>Due</th><th>Value (₹)</th><th>Company</th><th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {(tasks || []).map((t) => (
                <tr key={t.task_id}>
                  <td>
                    <span className="cat-bar" style={{ background: CAT_COLOR[t.category] }} />
                    <span className="truncate" style={{ display: "inline-block", maxWidth: 220 }}>{t.title}</span>
                  </td>
                  <td>{ASSIGNEE_NAME[t.assignee_id] || t.assignee_id}</td>
                  <td className="mono hint">{t.category}</td>
                  <td><span className={`badge ${t.priority}`}>{t.priority}</span></td>
                  <td className="mono hint">{t.due_date || "—"}</td>
                  <td className="mono">{t.deal_value_inr ? t.deal_value_inr.toLocaleString("en-IN") : "—"}</td>
                  <td>{t.company_name || "—"}</td>
                  <td className="mono hint">{t.confidence?.toFixed(2)}</td>
                </tr>
              ))}
              {(!tasks || tasks.length === 0) && (
                <tr><td colSpan={8} className="empty">No tasks yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "skipped" && (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table>
            <thead><tr><th>Subject</th><th>From</th><th>Reason</th></tr></thead>
            <tbody>
              {(skipped || []).map((s) => (
                <tr key={s.email_id}>
                  <td className="truncate">{s.subject || "(no subject)"}</td>
                  <td className="mono hint">{s.from_email}</td>
                  <td className="hint">{s.is_spurious_risk || s.reasoning || "—"}</td>
                </tr>
              ))}
              {(!skipped || skipped.length === 0) && (
                <tr><td colSpan={3} className="empty">Nothing skipped yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
