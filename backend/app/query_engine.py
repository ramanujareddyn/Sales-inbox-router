from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import Task, EmailLog
from .config import CATEGORIES

QUERY_TYPES = [
    "category_count", "marketing_vs_spam", "triage_list", "spurious_rate",
    "high_priority_low_confidence", "alliances_breakdown", "deal_value_sum",
    "thread_multi_update", "general_summary", "out_of_scope",
]

PLANNER_SYSTEM_PROMPT = f"""You translate an ops executive's question about a processed email
batch into ONE structured query for a fixed set of backend functions. You never answer the
question yourself and you never invent data — you only pick the right query_type and params.

Available query_types:
- "category_count": params {{ "category": "<one of {CATEGORIES} or any other word the user used>" }}
  Use for questions asking how many emails/tasks fall in a category (RFP, marketing, finance,
  alliances, smb, triage, or anything else the user names — even nonsense categories, so we can
  correctly report zero).
- "marketing_vs_spam": no params. Use for "marketing vs spam" style comparisons.
- "triage_list": no params. Use for "what's in triage / show me triage".
- "spurious_rate": no params. Use for "spurious rate / how many wrongly flagged".
- "high_priority_low_confidence": params {{ "confidence_threshold": float, default 0.5 }}.
  Use for "high priority but low confidence / unassigned-feeling" questions.
- "alliances_breakdown": no params. Use for reseller-vs-integration-partner style sub-breakdowns.
- "deal_value_sum": params {{ "category": "enterprise_rfp" | null }}. Use for total deal value questions.
- "thread_multi_update": no params. Use for "did any thread get updated more than once".
- "general_summary": no params. Use as a fallback for broad "how's it going / summarize" questions.
- "out_of_scope": no params. Use when the user asks the system to TAKE AN ACTION (send an email,
  create a task manually, delete something, message someone) rather than answer a question about
  already-processed data.

Respond with ONLY JSON: {{ "query_type": "...", "params": {{...}} }}
"""


def plan_query(question: str, gemini_json_fn) -> dict:
    try:
        planned = gemini_json_fn(PLANNER_SYSTEM_PROMPT, f"Question: {question}")
        if planned.get("query_type") in QUERY_TYPES:
            return planned
    except Exception:
        pass
    return _deterministic_plan(question)


def _deterministic_plan(question: str) -> dict:
    """Keep chat useful and grounded during an LLM outage."""
    q = (question or "").lower()
    if any(word in q for word in ("send ", "email ", "message ", "delete ", "create a task")):
        return {"query_type": "out_of_scope", "params": {}}
    if "spurious" in q:
        return {"query_type": "spurious_rate", "params": {}}
    if "high" in q and ("low confidence" in q or "unassigned" in q):
        return {"query_type": "high_priority_low_confidence", "params": {"confidence_threshold": 0.5}}
    if "triage" in q:
        return {"query_type": "triage_list", "params": {}}
    if "marketing" in q and ("spam" in q or "ignored" in q):
        return {"query_type": "marketing_vs_spam", "params": {}}
    if "reseller" in q or "integration partner" in q or "alliances" in q:
        return {"query_type": "alliances_breakdown", "params": {}}
    if "deal value" in q or "total value" in q:
        return {"query_type": "deal_value_sum", "params": {"category": "enterprise_rfp" if "rfp" in q else None}}
    if "updated more than once" in q or "update" in q and "thread" in q:
        return {"query_type": "thread_multi_update", "params": {}}
    for phrase, category in (
        ("rfp", "enterprise_rfp"), ("proposal", "enterprise_rfp"), ("marketing", "marketing"),
        ("finance", "finance"), ("invoice", "finance"), ("alliance", "alliances"),
        ("triage", "triage"), ("demo", "smb_enquiry"), ("gst refund", "gst_refund"),
    ):
        if phrase in q:
            return {"query_type": "category_count", "params": {"category": category}}
    return {"query_type": "general_summary", "params": {}}


def run_query(db: Session, candidate_id: str, query_type: str, params: dict) -> dict:
    if query_type == "out_of_scope":
        return {"out_of_scope": True}

    if query_type == "category_count":
        category = (params or {}).get("category", "")
        norm = _normalize_category_guess(category)
        if norm not in CATEGORIES:
            return {f"{_safe_key(category)}_count": 0, "note": f"'{category}' is not a tracked category; reporting zero."}
        count = db.query(func.count(Task.task_id)).filter(
            Task.candidate_id == candidate_id, Task.category == norm
        ).scalar() or 0
        return {norm: count}

    if query_type == "marketing_vs_spam":
        marketing = db.query(func.count(Task.task_id)).filter(
            Task.candidate_id == candidate_id, Task.category == "marketing"
        ).scalar() or 0
        spam = db.query(func.count(EmailLog.id)).filter(
            EmailLog.candidate_id == candidate_id,
            EmailLog.decision == "skipped",
            EmailLog.is_spurious_risk == "marketing_lookalike_spam",
        ).scalar() or 0
        return {"marketing": marketing, "skipped_marketing_lookalike_spam": spam}

    if query_type == "triage_list":
        rows = db.query(Task).filter(
            Task.candidate_id == candidate_id, Task.category == "triage"
        ).all()
        return {
            "triage_count": len(rows),
            "triage_task_ids": [r.task_id for r in rows],
            "triage_items": [{"task_id": r.task_id, "title": r.title, "reason": r.description} for r in rows],
        }

    if query_type == "spurious_rate":
        processed = db.query(func.count(EmailLog.id)).filter(EmailLog.candidate_id == candidate_id).scalar() or 0
        spurious = db.query(func.count(EmailLog.id)).filter(
            EmailLog.candidate_id == candidate_id,
            EmailLog.decision == "created",
            EmailLog.is_spurious_risk.isnot(None),
        ).scalar() or 0
        rate = round(spurious / processed, 4) if processed else 0.0
        return {"spurious_count": spurious, "processed": processed, "spurious_rate": rate}

    if query_type == "high_priority_low_confidence":
        threshold = (params or {}).get("confidence_threshold", 0.5)
        rows = db.query(Task).filter(
            Task.candidate_id == candidate_id, Task.priority == "high", Task.confidence < threshold
        ).all()
        return {"matches": [{"task_id": r.task_id, "title": r.title, "confidence": r.confidence} for r in rows]}

    if query_type == "alliances_breakdown":
        count = db.query(func.count(Task.task_id)).filter(
            Task.candidate_id == candidate_id, Task.category == "alliances"
        ).scalar() or 0
        return {"alliances": count, "note": "Reseller vs. tech-integration sub-type isn't separately stored; only the combined alliances count is available."}

    if query_type == "deal_value_sum":
        category = (params or {}).get("category") or "enterprise_rfp"
        with_value = db.query(Task).filter(
            Task.candidate_id == candidate_id, Task.category == category, Task.deal_value_inr.isnot(None)
        ).all()
        without_value = db.query(func.count(Task.task_id)).filter(
            Task.candidate_id == candidate_id, Task.category == category, Task.deal_value_inr.is_(None)
        ).scalar() or 0
        total = sum(t.deal_value_inr for t in with_value)
        return {"total_deal_value_inr": total, "rfps_with_no_stated_value": without_value}

    if query_type == "thread_multi_update":
        rows = (
            db.query(EmailLog.thread_id, func.count(EmailLog.id).label("n"))
            .filter(EmailLog.candidate_id == candidate_id, EmailLog.decision == "updated")
            .group_by(EmailLog.thread_id)
            .having(func.count(EmailLog.id) > 1)
            .all()
        )
        return {"threads_updated_multiple_times": [r[0] for r in rows]}

    # general_summary fallback
    total_processed = db.query(func.count(EmailLog.id)).filter(EmailLog.candidate_id == candidate_id).scalar() or 0
    created = db.query(func.count(Task.task_id)).filter(Task.candidate_id == candidate_id).scalar() or 0
    skipped = db.query(func.count(EmailLog.id)).filter(
        EmailLog.candidate_id == candidate_id, EmailLog.decision == "skipped"
    ).scalar() or 0
    by_category = dict(
        db.query(Task.category, func.count(Task.task_id))
        .filter(Task.candidate_id == candidate_id)
        .group_by(Task.category).all()
    )
    return {"processed": total_processed, "tasks_created": created, "skipped": skipped, "by_category": by_category}


def _normalize_category_guess(raw: str) -> str:
    r = (raw or "").strip().lower()
    mapping = {
        "rfp": "enterprise_rfp", "proposal": "enterprise_rfp", "proposals": "enterprise_rfp",
        "enterprise": "enterprise_rfp", "enterprise_rfp": "enterprise_rfp",
        "smb": "smb_enquiry", "demo": "smb_enquiry", "smb_enquiry": "smb_enquiry",
        "marketing": "marketing", "sponsorship": "marketing", "webinar": "marketing",
        "alliances": "alliances", "reseller": "alliances", "partner": "alliances", "partnership": "alliances",
        "finance": "finance", "invoice": "finance", "invoices": "finance", "billing": "finance",
        "triage": "triage",
    }
    return mapping.get(r, r)


def _safe_key(raw: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (raw or "unknown").lower()).strip("_") or "unknown"
