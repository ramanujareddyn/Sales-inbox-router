import json
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from ..database import get_db
from ..models import Task, EmailLog
from ..schemas import ChatRequest
from ..config import normalize_candidate_id, CATEGORIES
from ..gemini_client import call_gemini_json, call_gemini_text, GeminiError
from ..query_engine import plan_query, run_query

router = APIRouter()


@router.get("/api/tasks")
def api_tasks(candidate_id: str = Query(...), db: Session = Depends(get_db)):
    cid = normalize_candidate_id(candidate_id)
    tasks = db.query(Task).filter(Task.candidate_id == cid).order_by(Task.created_at.desc()).all()
    skipped = (
        db.query(EmailLog)
        .filter(EmailLog.candidate_id == cid, EmailLog.decision == "skipped")
        .order_by(EmailLog.created_at.desc())
        .all()
    )
    return {
        "tasks": [t.to_dict() for t in tasks],
        "skipped_emails": [s.to_dict() for s in skipped],
    }


@router.get("/api/stats")
def api_stats(candidate_id: str = Query(...), db: Session = Depends(get_db)):
    cid = normalize_candidate_id(candidate_id)
    processed = db.query(func.count(EmailLog.id)).filter(EmailLog.candidate_id == cid).scalar() or 0
    created = db.query(func.count(EmailLog.id)).filter(
        EmailLog.candidate_id == cid, EmailLog.decision == "created"
    ).scalar() or 0
    updated = db.query(func.count(EmailLog.id)).filter(
        EmailLog.candidate_id == cid, EmailLog.decision == "updated"
    ).scalar() or 0
    skipped = db.query(func.count(EmailLog.id)).filter(
        EmailLog.candidate_id == cid, EmailLog.decision == "skipped"
    ).scalar() or 0
    by_category = dict(
        db.query(Task.category, func.count(Task.task_id))
        .filter(Task.candidate_id == cid).group_by(Task.category).all()
    )
    spurious_flagged = db.query(func.count(EmailLog.id)).filter(
        EmailLog.candidate_id == cid, EmailLog.decision == "created", EmailLog.is_spurious_risk.isnot(None)
    ).scalar() or 0

    return {
        "processed": processed,
        "tasks_created": created,
        "tasks_updated": updated,
        "skipped": skipped,
        "spurious_flagged": spurious_flagged,
        "by_category": by_category,
    }


@router.post("/api/chat")
def api_chat(req: ChatRequest, db: Session = Depends(get_db)):
    cid = normalize_candidate_id(req.candidate_id)

    plan = plan_query(req.query, call_gemini_json)
    query_type = plan.get("query_type", "general_summary")
    params = plan.get("params", {})

    if query_type == "out_of_scope":
        return {
            "answer": "I can only answer questions about the emails already processed in this "
                      "batch — I can't take actions like sending emails or messaging someone. "
                      "Try asking me something like \"what's in triage\" or \"how many RFPs came in\".",
            "supporting_data": {},
        }

    data = run_query(db, cid, query_type, params)

    phrasing_prompt = f"""You are answering an ops executive's question using ONLY the data below.
Do not state any number, count, or fact that is not present in this data. If the data shows a
zero or an empty list, say so plainly — do not soften it into something vague. Keep the answer
to 1-3 sentences, plain language, no markdown.

Question: {req.query}

Data (ground truth, computed by the backend — not to be second-guessed or supplemented):
{json.dumps(data, default=str)}
"""
    try:
        answer = call_gemini_text(phrasing_prompt).strip()
    except GeminiError:
        answer = _template_answer(query_type, data)

    return {"answer": answer, "supporting_data": data}


def _template_answer(query_type: str, data: dict) -> str:
    """Fallback phrasing if Gemini is unreachable — still fully grounded in `data`."""
    if not data:
        return "No data available."
    if "triage_count" in data:
        return f"{data['triage_count']} email(s) are sitting in triage."
    if "spurious_rate" in data:
        return f"Spurious rate is {data['spurious_rate']*100:.1f}% ({data['spurious_count']} of {data['processed']} processed)."
    if "total_deal_value_inr" in data:
        return f"Total stated deal value is ₹{data['total_deal_value_inr']:,} across tasks with a value; {data['rfps_with_no_stated_value']} had none stated."
    if query_type == "category_count":
        category, count = next(iter(data.items()))
        return f"{count} email(s) were classified as {category}."
    if query_type == "marketing_vs_spam":
        return f"There were {data.get('marketing', 0)} marketing task(s) and {data.get('skipped_marketing_lookalike_spam', 0)} marketing-like spam email(s) correctly skipped."
    if query_type == "high_priority_low_confidence":
        return f"There are {len(data.get('matches', []))} high-priority task(s) with low confidence."
    if query_type == "thread_multi_update":
        return f"{len(data.get('threads_updated_multiple_times', []))} thread(s) were updated more than once."
    if "processed" in data:
        categories = ", ".join(f"{k}: {v}" for k, v in data.get("by_category", {}).items()) or "no routed categories"
        return f"So far, {data['processed']} emails were processed, {data.get('tasks_created', 0)} tasks were created, and {data.get('skipped', 0)} were skipped. Categories: {categories}."
    return json.dumps(data)


# ---- Sample email generation (used by the frontend "generate sample emails" button) ----

FIRST_NAMES = ["Suresh", "Ankit", "Nandita", "Priya", "Rohan", "Farhan", "Meenal", "Vikram", "Sana", "Arjun"]
LAST_NAMES = ["Kulkarni", "Bose", "Reddy", "Sharma", "Iyer", "Qureshi", "Patil", "Nair", "Menon", "Rao"]
COMPANIES = ["Meridian Steel", "Railyard Logistics", "India SaaS Summit", "Vantage Cloud Services",
             "Zenith Cloud Partners", "Halcyon Retail", "BHEL", "Northbridge Consulting", "Orbit Analytics"]

TEMPLATES = [
    ("rfp", "RFP - {company} Document Management", "Please find attached our RFP for a document management system. Indicative budget is Rs. {value} lakhs. Proposals must reach us by {date}.", False),
    ("smb", "Quick demo request", "Hi, we're a {size}-person team at {company}. Can we get a demo sometime next week? Nothing urgent.", False),
    ("marketing", "Sponsorship confirmation needed", "We're finalising sponsors for a conference. Gold tier is Rs. {value} lakhs. We need confirmation by tomorrow EOD.", False),
    ("finance", "Invoice INV-{num}", "Please find attached invoice INV-{num} for Rs. {value2} against PO-{num2}. Kindly process payment.", False),
    ("alliances", "Partnership opportunity", "We're an implementation partner with 40+ enterprise clients. We'd like to explore reselling your platform.", False),
    ("spam", "Boost your SEO rankings today", "Hi, I noticed your website isn't ranking well. We've helped 200+ companies triple their traffic. Free audit attached, interested in a quick call?", False),
    ("newsletter", "The B2B Growth Weekly — Issue {num}", "In this edition: why PLG is stalling, 5 pricing experiments that worked. Unsubscribe here.", False),
    ("ooo", "Out of Office", "I am out of office until next week with limited access to email. For urgent matters contact my colleague.", False),
    ("psu", "Tender Notice - {company}", "Tender Notice No. {num}. {company} invites bids for supply of software licences. Estimated value: Rs. {value2}. Last date for bid submission: {date}.", False),
    ("triage", "Two quick things", "We'd like to evaluate your platform for our org, budget TBD. Also our CMO wants to co-host a webinar in September. Can you loop in the right people?", False),
]


@router.get("/api/sample-emails")
def sample_emails(count: int = Query(250, le=250)):
    random.seed()
    emails = []
    base_time = datetime.now(timezone.utc)
    for i in range(count):
        kind, subj_t, body_t, is_reply = random.choice(TEMPLATES)
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        company = random.choice(COMPANIES)
        value = random.choice([3, 8, 12, 25, 40, 65])
        value2 = value * 10000
        num = random.randint(1000, 9999)
        num2 = random.randint(10000, 99999)
        size = random.choice([15, 30, 80, 200])
        days_out = random.choice([1, 2, 5, 10, 20])
        received = base_time - timedelta(hours=random.randint(0, 240))
        due = received + timedelta(days=days_out)

        subject = subj_t.format(company=company, num=num)
        body = body_t.format(
            company=company, value=value, value2=f"{value2:,}", date=due.strftime("%d %b %Y"),
            size=size, num=num, num2=num2,
        )
        thread_id = f"th_{1000+i}"
        emails.append({
            "email_id": f"em_{10000+i}",
            "thread_id": thread_id,
            "message_index": 0,
            "from_name": f"{fname} {lname}",
            "from_email": f"{fname.lower()}.{lname.lower()}@{company.lower().replace(' ', '')}.com",
            "to": "sales@company.com",
            "cc": [],
            "subject": subject,
            "body": body,
            "received_at": received.isoformat(),
            "attachments": [],
            "is_reply": False,
        })
    return {"emails": emails}
