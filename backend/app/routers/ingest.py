from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Task, EmailLog
from ..schemas import IngestRequest
from ..routing import classify_email, rule_based_fallback
from ..config import normalize_candidate_id

router = APIRouter()

MAX_BATCH = 100


def _merge_patch(task: Task, result: dict) -> dict:
    """Thread-reply reconciliation: update only the fields the new message actually
    changed, per Example 10 in the spec (priority/due_date/deal_value can change on
    a reply; we don't blindly overwrite title/company_name with a possibly-worse guess).
    """
    changes = {}
    if result.get("due_date"):
        changes["due_date"] = result["due_date"]
    if result.get("deal_value_inr") is not None:
        changes["deal_value_inr"] = result["deal_value_inr"]
    if result.get("company_name") and not task.company_name:
        changes["company_name"] = result["company_name"]
    # priority: only escalate or explicitly change based on new signal (e.g. new deadline)
    new_priority = result.get("priority")
    if new_priority and new_priority != task.priority:
        order = {"low": 0, "medium": 1, "high": 2}
        if order.get(new_priority, 1) >= order.get(task.priority, 1):
            changes["priority"] = new_priority
    if result.get("confidence") is not None:
        changes["confidence"] = result["confidence"]
    if result.get("description"):
        note = f"\n\n[Update on reply]: {result['description']}"
        changes["description"] = (task.description or "") + note

    for k, v in changes.items():
        setattr(task, k, v)
    return changes


@router.post("/ingest")
def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    if len(req.emails) > MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"batch exceeds max of {MAX_BATCH} emails")

    candidate_id = normalize_candidate_id(req.candidate_id)
    processed = 0
    tasks_created = 0
    tasks_updated = 0
    skipped = 0
    errors = []

    for email in req.emails:
        email_dict = email.model_dump()
        email_id = email_dict["email_id"]
        thread_id = email_dict["thread_id"]
        processed += 1

        # --- Idempotency: same (candidate, email_id) already processed -> no-op ---
        existing_log = (
            db.query(EmailLog)
            .filter(EmailLog.candidate_id == candidate_id, EmailLog.email_id == email_id)
            .first()
        )
        if existing_log:
            if existing_log.decision in ("created", "updated"):
                tasks_updated += 0  # already accounted for; no state change
            else:
                skipped += 1
            continue

        try:
            result = classify_email(email_dict)
        except Exception as e:
            result = rule_based_fallback(email_dict)
            result["reasoning"] = f"classification error, used fallback: {e}"

        if not result.get("is_task"):
            log = EmailLog(
                candidate_id=candidate_id, email_id=email_id, thread_id=thread_id,
                run_label=req.run_label, decision="skipped", task_id=None,
                category=None, assignee_id=None, priority=None,
                confidence=result.get("confidence"),
                is_spurious_risk=(
                    "marketing_lookalike_spam" if result.get("is_marketing_lookalike_spam") else result.get("skip_reason")
                ),
                reasoning=result.get("reasoning"),
                subject=email_dict.get("subject"), from_email=email_dict.get("from_email"),
            )
            db.add(log)
            skipped += 1
            db.commit()
            continue

        # --- Thread reconciliation: does this candidate already have a task on this thread? ---
        existing_task = (
            db.query(Task)
            .filter(Task.candidate_id == candidate_id, Task.thread_id == thread_id)
            .order_by(Task.created_at.desc())
            .first()
        )

        if existing_task is not None:
            _merge_patch(existing_task, result)
            db.commit()
            db.refresh(existing_task)
            tasks_updated += 1
            log = EmailLog(
                candidate_id=candidate_id, email_id=email_id, thread_id=thread_id,
                run_label=req.run_label, decision="updated", task_id=existing_task.task_id,
                category=existing_task.category, assignee_id=existing_task.assignee_id,
                priority=existing_task.priority, confidence=result.get("confidence"),
                is_spurious_risk=None, reasoning=result.get("reasoning"),
                subject=email_dict.get("subject"), from_email=email_dict.get("from_email"),
            )
            db.add(log)
            db.commit()
        else:
            task = Task(
                candidate_id=candidate_id,
                source_email_id=email_id,
                thread_id=thread_id,
                title=result.get("title") or email_dict.get("subject") or "Untitled",
                description=result.get("description"),
                assignee_id=result.get("assignee_id") or "u_triage",
                category=result.get("category") or "triage",
                priority=result.get("priority") or "medium",
                due_date=result.get("due_date"),
                deal_value_inr=result.get("deal_value_inr"),
                company_name=result.get("company_name"),
                confidence=result.get("confidence") if result.get("confidence") is not None else 0.5,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            tasks_created += 1
            log = EmailLog(
                candidate_id=candidate_id, email_id=email_id, thread_id=thread_id,
                run_label=req.run_label, decision="created", task_id=task.task_id,
                category=task.category, assignee_id=task.assignee_id, priority=task.priority,
                confidence=task.confidence, is_spurious_risk=None,
                reasoning=result.get("reasoning"),
                subject=email_dict.get("subject"), from_email=email_dict.get("from_email"),
            )
            db.add(log)
            db.commit()

    return {
        "processed": processed,
        "tasks_created": tasks_created,
        "tasks_updated": tasks_updated,
        "skipped": skipped,
        "errors": errors,
    }
