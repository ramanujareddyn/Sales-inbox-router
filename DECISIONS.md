# DECISIONS.md

## 1. Gemini rate limits and retries

`gemini_client.py` wraps every call in exponential backoff (up to 3 attempts, capped at 8s)
on 429s, 5xx, timeouts, and malformed-JSON responses. Classification is forced into
`response_mime_type: application/json` so we're not parsing free text out of markdown fences.
If all retries fail, `routing.classify_email` falls back to `rule_based_fallback`: regex-based
detection for the unambiguous skip cases (out-of-office, newsletter), and a conservative
`u_triage` route with `confidence: 0.2` for everything else. This was a deliberate call per
§8.5/§8.6: a dropped email is explicitly penalized more heavily than a slow or low-confidence
one, so degrading to "flag for a human" beats returning an error and losing the email entirely.
**Two more weeks:** add a request queue with per-key rate limiting and a circuit breaker so a
sustained outage doesn't retry-storm the batch; currently each email retries independently.

## 2. Idempotency

Every processed email — task-worthy or not — gets one row in `EmailLog`, unique on
`(candidate_id, email_id)`. Before classifying, `/ingest` checks this table; a repeat `email_id`
for the same candidate is a no-op. This is enforced at the application layer rather than a raw
DB unique constraint failure, so a duplicate POST returns a clean "already processed" outcome
instead of a 500. Combined with real persistence (Postgres/SQLite, not an in-process dict), this
is what makes Run 2 (§8.1) safe against re-posting the identical batch.
**Two more weeks:** move the check-then-insert into a single transaction with `SELECT ... FOR
UPDATE` (or a DB-level unique constraint with `ON CONFLICT DO NOTHING`) to close the race window
if the grader ever parallelizes requests — right now two concurrent identical requests could
both pass the "not yet logged" check before either commits.

## 3. Data model for instant, non-Gemini chat answers

`EmailLog` stores the *outcome* of every classification (decision, category, assignee, priority,
confidence, a spurious-risk flag, and the reasoning string) at ingest time — not just the emails
that became tasks. `query_engine.py` runs plain SQL aggregations (`COUNT`, `GROUP BY`, filters)
over `EmailLog` and `Task` directly. Gemini is used twice per chat question — once to *plan*
which structured query to run (never to answer), and once to *phrase* the answer strictly from
the numbers Python already computed — but the numbers themselves never come from a fresh model
call. This means asking the same question twice returns the same `supporting_data` every time,
and re-running `/api/stats` doesn't require touching Gemini at all.
**Two more weeks:** cache `/api/stats` aggregates (materialized view or a `stats` table updated
on write) instead of computing them fresh on every request — fine at 250 emails, won't scale to
10k/day without an index-backed rollup.

## 4. Keeping the chat interface from hallucinating

The failure mode the spec calls out (§7.3, §8.6) is a model inventing a plausible-sounding count.
The guardrail is architectural, not a prompt instruction alone: `query_engine.run_query` returns
a plain Python dict computed from SQL; that dict is serialized into the phrasing prompt verbatim
and the prompt explicitly says not to state any number absent from it; the same dict is returned
to the frontend as `supporting_data` so it's checkable against the prose. If Gemini is
unreachable for the phrasing step, `_template_answer` falls back to a hand-written string built
from the same dict — the *answer* can degrade, the *data* never gets improvised. A question about
a category that doesn't exist (e.g. "GST refunds") still resolves through `category_count`, which
returns `0` for anything outside the six known categories rather than raising or guessing.
**Honest gap:** the query planner itself is an LLM call (mapping NL question → query_type), so a
sufficiently weird phrasing could route to the wrong query_type — but even then it can only
return *some* real computed number for the *wrong* question, never a fabricated one.

## 5. What I knowingly shipped wrong

Thread reconciliation matches replies to a task purely by `(candidate_id, thread_id)`, taking the
most recently created task on that thread. The brief's Example 11 (two distinct asks in one
email, correctly triaged as one ambiguous task) means a thread can legitimately need two owners
across its life, and my model collapses every reply on a thread into updates on a single task —
if a second, genuinely unrelated ask arrives later in the same thread, it'll incorrectly patch
the existing task instead of spinning up a second one. Detecting "this reply is actually a new
ask" versus "this reply is new information about the same ask" needs a classification step of
its own that I didn't build; I flagged it here instead of quietly shipping it as correct.
