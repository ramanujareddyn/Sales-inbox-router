"""
Eval harness for EVALS.md.

Usage:
  1. Hand-label >=50 emails from the real inbox.json into labels.csv with columns:
     email_id,expected_action (task|skip),expected_assignee_id (blank if skip)
  2. Run:
     python eval_harness.py --inbox inbox.json --labels labels.csv \
     --backend http://localhost:8000 --candidate priya.sharma@gmail.com
  3. It posts the labeled emails to /ingest, reads back /tasks, and prints
     precision/recall/F1 per assignee_id plus the four §8.2 buckets
     (correct / misrouted / missed / spurious).

This does NOT invent a dataset — it requires a real labels.csv from manual review of
inbox.json, per the "no fabricated metrics" requirement in the challenge brief.
"""
import argparse
import csv
import json
import sys
import httpx


def load_inbox(path):
    with open(path) as f:
        data = json.load(f)
    return {e["email_id"]: e for e in (data if isinstance(data, list) else data["emails"])}


def load_labels(path):
    rows = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rows[row["email_id"]] = row
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--candidate", required=True)
    args = ap.parse_args()

    inbox = load_inbox(args.inbox)
    labels = load_labels(args.labels)
    emails = [inbox[eid] for eid in labels if eid in inbox]
    if len(emails) < len(labels):
        missing = set(labels) - set(inbox)
        print(f"WARNING: {len(missing)} labeled email_ids not found in inbox.json: {list(missing)[:5]}...")

    with httpx.Client(timeout=120) as client:
        r = client.post(f"{args.backend}/ingest", json={
            "candidate_id": args.candidate, "emails": emails, "run_label": "eval_harness",
        })
        r.raise_for_status()
        print("ingest response:", r.json())

        r = client.get(f"{args.backend}/tasks", params={"candidate_id": args.candidate})
        r.raise_for_status()
        tasks_by_email = {t["source_email_id"]: t for t in r.json()}

    buckets = {"correct": 0, "misrouted": 0, "missed": 0, "spurious": 0}
    per_assignee = {}

    for eid, label in labels.items():
        expected_action = label["expected_action"].strip().lower()
        expected_assignee = label.get("expected_assignee_id", "").strip()
        task = tasks_by_email.get(eid)

        if expected_action == "skip":
            if task:
                buckets["spurious"] += 1
            continue

        if not task:
            buckets["missed"] += 1
            continue

        actual = task["assignee_id"]
        per_assignee.setdefault(expected_assignee, {"tp": 0, "fp": 0, "fn": 0})
        per_assignee.setdefault(actual, {"tp": 0, "fp": 0, "fn": 0})

        if actual == expected_assignee:
            buckets["correct"] += 1
            per_assignee[expected_assignee]["tp"] += 1
        else:
            buckets["misrouted"] += 1
            per_assignee[expected_assignee]["fn"] += 1
            per_assignee[actual]["fp"] += 1

    print("\n--- Buckets (§8.2) ---")
    print(json.dumps(buckets, indent=2))

    print("\n--- Per-assignee precision/recall ---")
    for assignee, c in per_assignee.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        print(f"{assignee}: precision={precision}, recall={recall}, f1={f1} (tp={tp} fp={fp} fn={fn})")


if __name__ == "__main__":
    sys.exit(main())
