# EVALS.md

> **Status: reproducible evaluation harness; metrics pending the real labeled inbox.** The
> repository contains the challenge schema and sample generator, but no independently
> hand-labelled 50-email gold set. The challenge explicitly penalizes fabricated metrics, so
> this file does not claim accuracy numbers that were not measured. Run the harness below after
> creating `labels.csv` from the deployed/sample inbox, then paste its output into the tables.

## Methodology

1. Hand-label ≥50 emails sampled from the real `inbox.json`, covering every category
   (`enterprise_rfp`, `smb_enquiry`, `marketing`, `alliances`, `finance`, `triage`) and every
   skip type (out-of-office, newsletter, spam), not just the easy cases — deliberately include
   the trap patterns called out in §6 (PSU tender below threshold, marketing-lookalike spam,
   reseller pitch, two-ask ambiguity, Hinglish/shorthand values, thread replies).
2. Save labels to `backend/labels.csv`:
   ```csv
   email_id,expected_action,expected_assignee_id
   em_00142,task,u_aarti
   em_00187,skip,
   ```
3. Run the harness:
   ```bash
   cd backend
   python eval_harness.py --inbox path/to/inbox.json --labels labels.csv \
       --backend http://localhost:8000 --candidate priya.sharma@gmail.com
   ```
4. Paste its output into the tables below.

## Results (fill in after running the harness)

### §8.2 buckets

| Bucket | Count | Notes |
|---|---|---|
| ✅ Correct | — | |
| ⚠️ Misrouted | — | |
| ❌ Missed | — | |
| 🚨 Spurious | — | weighted most heavily per spec — should be as close to 0 as possible |

### Precision / Recall per assignee

| assignee_id | Precision | Recall | F1 | n (expected) |
|---|---|---|---|---|
| u_aarti | — | — | — | — |
| u_rohit | — | — | — | — |
| u_meera | — | — | — | — |
| u_karan | — | — | — | — |
| u_divya | — | — | — | — |
| u_triage | — | — | — | — |

## Failure Cases I Did Not Fix

These are the categories of error I expect the harness to surface, based on where the routing
logic is weakest by construction — listed honestly rather than glossed over:

1. **Thread replies that introduce a genuinely new, unrelated ask.** Reconciliation is keyed
   purely on `(candidate_id, thread_id)` (see DECISIONS.md #5) — a second distinct request
   arriving later in the same thread gets merged into the existing task instead of spawning a
   second one. I did not build a "is this reply actually a new ask" classifier.
2. **Deal-value inference from ambiguous shorthand outside the patterns I tested** (e.g. "10L
   p.a." recurring revenue vs. one-time deal value, or values split across a quoted reply chain
   and the new message) — the prompt instructs the model to ignore quoted text, but a value
   restated *differently* across quoted and new text (not just repeated) isn't explicitly
   handled and could be double-counted or dropped depending on phrasing.
3. **Company name extraction when the signature and the `from_email` domain disagree** (e.g. a
   personal Gmail address emailing on behalf of a named company mentioned only in the signature)
   — the prompt says not to infer from domain, but doesn't give explicit priority ordering
   between "name in body," "name in signature block," and "name in `cc` domain," so results may
   be inconsistent across similar emails.

Add real, harness-surfaced failures here once run against the actual dataset — the three above
are anticipated risk areas, not observed failures, and should be replaced/supplemented with
concrete `email_id`s once the eval is run for real.
