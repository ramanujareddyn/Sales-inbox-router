const BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

async function req(path, opts = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

export const api = {
  sampleEmails: (count = 250) => req(`/api/sample-emails?count=${count}`),
  ingest: (candidate_id, emails, run_label) =>
    req(`/ingest`, { method: "POST", body: JSON.stringify({ candidate_id, emails, run_label }) }),
  tasks: (candidate_id) => req(`/api/tasks?candidate_id=${encodeURIComponent(candidate_id)}`),
  stats: (candidate_id) => req(`/api/stats?candidate_id=${encodeURIComponent(candidate_id)}`),
  chat: (candidate_id, query) =>
    req(`/api/chat`, { method: "POST", body: JSON.stringify({ candidate_id, query }) }),
  users: () => req(`/users`),
};

export { BASE_URL };
