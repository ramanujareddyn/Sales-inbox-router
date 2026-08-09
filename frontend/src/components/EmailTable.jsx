import React from "react";

function truncate(s, n = 90) {
  if (!s) return "";
  const clean = s.replace(/\s+/g, " ").trim();
  return clean.length > n ? clean.slice(0, n) + "…" : clean;
}

export default function EmailTable({ emails }) {
  if (!emails || emails.length === 0) {
    return (
      <div className="panel">
        <h2>2 · Raw batch preview</h2>
        <div className="empty">Paste or generate a batch above to see it rendered here — before any routing logic touches it.</div>
      </div>
    );
  }

  const shown = emails.slice(0, 40);

  return (
    <div className="panel">
      <h2>2 · Raw batch preview ({emails.length} emails{emails.length > 40 ? ", showing first 40" : ""})</h2>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>From</th>
              <th>Subject</th>
              <th>Received</th>
              <th>Thread</th>
              <th>Body preview</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.email_id}>
                <td>
                  <div>{e.from_name || "—"}</div>
                  <div className="hint mono">{e.from_email}</div>
                </td>
                <td className="truncate">{e.subject || "(no subject)"}</td>
                <td className="mono hint">{e.received_at ? e.received_at.slice(0, 16).replace("T", " ") : "—"}</td>
                <td className="mono hint">{e.thread_id}</td>
                <td className="hint">{truncate(e.body)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
