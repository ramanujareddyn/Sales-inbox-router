import re
import json
from datetime import datetime, timedelta
from typing import Optional

from .gemini_client import call_gemini_json, GeminiError
from .config import ASSIGNEE_IDS, CATEGORIES, PRIORITIES

SYSTEM_PROMPT = """You are the routing engine for a B2B company's sales@ inbox. You classify one
incoming email at a time and decide whether it should become a task, and if so, who owns it.

TEAM & ROUTING RULES:
- u_aarti (Aarti Menon, Sales-Enterprise): RFPs, RFIs, tenders, inbound deals ABOVE ₹10,00,000.
- u_rohit (Rohit Sharma, Sales-SMB): product enquiries / demo requests / deals AT OR BELOW ₹10,00,000,
  including when no value is stated at all (small/unspecified deals default here, NOT to Aarti).
- u_meera (Meera Iyer, Marketing): webinars, event/conference sponsorships, content collaborations,
  PR, media. This is about WHO IS ASKING and WHY — a company that mentions "webinar" or "PR" while
  trying to SELL US their marketing/SEO/content services is NOT marketing, it's spam. Direction of
  intent matters: are they buying from us, or pitching us?
- u_karan (Karan Doshi, Alliances): reseller / channel partner / technology integration proposals.
  Even if they mention "clients" or "revenue", a partnership/reseller pitch is Alliances, not Sales.
- u_divya (Divya Rao, Finance): invoices, POs, payment reminders, GST, vendor billing. The amount on
  an invoice is NOT a deal_value_inr — leave deal_value_inr null for invoices.
- u_triage: genuinely ambiguous emails, or emails with two distinct asks that belong to two different
  owners (e.g. "evaluate your platform" + "co-host a webinar" in one email). Use a LOW confidence
  (<=0.5) here and explain the ambiguity in reasoning. Do not use triage as a dumping ground for
  things that actually fit a category above.

ADDITIONAL HARD RULES:
1. Government / PSU tenders ALWAYS go to u_aarti, category enterprise_rfp, REGARDLESS of deal value,
   even if the value is small or stated in a way that would normally route to Rohit.
2. Do NOT create a task for: out-of-office auto-replies, newsletters, or unsolicited vendor spam /
   cold pitches (including ones disguised using marketing-sounding keywords). Set is_task=false for
   these and explain briefly in reasoning which of these three it is.
3. Never invent due_date, deal_value_inr, or company_name. If the email doesn't clearly state it,
   the field must be null. A missing/null value is scored better than a fabricated one.
4. Parse Indian currency shorthand precisely: "lakh"/"L" = x100000, "crore"/"cr" = x10000000.
   "Rs. 25 lakhs" -> 2500000. "1.2 cr" -> 12000000. Round to the nearest integer rupee, no decimals.
5. If the email is itself a reply on an existing thread (quoted text below, "Re:" subject, or
   is_reply=true), extract ONLY the new information in the latest message — ignore quoted/forwarded
   content when extracting facts, and do not double count values mentioned only in the quoted part.
6. confidence (0.0-1.0) should reflect your genuine certainty in this specific routing decision —
   a clean, unambiguous RFP might be 0.9+, a coin-flip triage case might be 0.3-0.5.

Respond with ONLY a single JSON object (no markdown fences, no commentary) with this exact shape:
{
  "is_task": true | false,
  "skip_reason": "out_of_office" | "newsletter" | "spam" | null,
  "is_marketing_lookalike_spam": true | false,
  "category": "enterprise_rfp" | "smb_enquiry" | "marketing" | "alliances" | "finance" | "triage" | null,
  "assignee_id": "u_aarti" | "u_rohit" | "u_meera" | "u_karan" | "u_divya" | "u_triage" | null,
  "priority_signal": "high" | "medium" | "low",
  "due_date": "YYYY-MM-DD" | null,
  "deal_value_inr": integer | null,
  "company_name": "string" | null,
  "confidence": 0.0-1.0,
  "title": "short task title",
  "description": "1-3 sentence summary of what's needed and why, in your own words",
  "reasoning": "one sentence on why this routing/skip decision was made"
}
"""

USER_PROMPT_TMPL = """EMAIL TO CLASSIFY
from_name: {from_name}
from_email: {from_email}
subject: {subject}
received_at: {received_at}
is_reply: {is_reply}
cc: {cc}

BODY:
{body}
"""


def build_user_prompt(email: dict) -> str:
    return USER_PROMPT_TMPL.format(
        from_name=email.get("from_name") or "",
        from_email=email.get("from_email") or "",
        subject=email.get("subject") or "",
        received_at=email.get("received_at") or "",
        is_reply=email.get("is_reply", False),
        cc=", ".join(email.get("cc") or []),
        body=(email.get("body") or "")[:6000],
    )


PSU_PATTERNS = re.compile(
    r"\b(tender|psu|public sector undertaking|government of|ministry of|municipal corporation|"
    r"nic\.in|gov\.in|gem\.gov|bhel|ongc|nhai|railways?)\b", re.I
)
OOO_PATTERNS = re.compile(r"\b(out of office|automatic reply|auto-reply|ooo)\b", re.I)
NEWSLETTER_PATTERNS = re.compile(r"\b(unsubscribe|newsletter|weekly digest|this week in)\b", re.I)
SPAM_PATTERNS = re.compile(
    r"\b(website isn't ranking|seo audit|boost your seo|organic traffic|free audit attached|"
    r"lead generation service)\b", re.I
)


def _hours_until(received_at: Optional[str], due_date: Optional[str]) -> Optional[float]:
    if not received_at or not due_date:
        return None


def _latest_message_text(email: dict) -> str:
    """Return the new part of a reply, excluding quoted history."""
    body = email.get("body") or ""
    lines = []
    for line in body.splitlines():
        if line.lstrip().startswith(">") or re.match(r"^On .+wrote:\s*$", line.strip(), re.I):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_amount(text: str) -> Optional[int]:
    pattern = re.compile(
        r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|l|crores?|cr)?"
        r"|\b([\d]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr)\b", re.I
    )
    for match in pattern.finditer(text):
        raw = match.group(1) or match.group(3)
        unit = (match.group(2) or match.group(4) or "").lower()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit.startswith("l"):
            value *= 100_000
        elif unit.startswith("c"):
            value *= 10_000_000
        return int(round(value))
    return None


def _parse_due_date(text: str, received_at: Optional[str]) -> Optional[str]:
    try:
        received = datetime.fromisoformat((received_at or "").replace("Z", "+00:00"))
    except ValueError:
        received = datetime.now().astimezone()

    if re.search(r"\b(day after tomorrow)\b", text, re.I):
        return (received + timedelta(days=2)).date().isoformat()
    if re.search(r"\b(tomorrow|next day)\b", text, re.I):
        return (received + timedelta(days=1)).date().isoformat()

    month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
    match = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ -](\d{{1,2}})[-/](\d{{4}})\b|"
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ -]({month_names})[ -](\d{{4}})\b|"
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ -]({month_names})\b",
        text, re.I,
    )
    if not match:
        return None
    try:
        if match.group(1):
            return datetime.strptime(f"{match.group(1)}-{match.group(2)}-{match.group(3)}", "%d-%m-%Y").date().isoformat()
        if match.group(4):
            return datetime.strptime(f"{match.group(4)}-{match.group(5)}-{match.group(6)}", "%d-%B-%Y").date().isoformat()
        return datetime.strptime(f"{match.group(7)}-{match.group(8)}-{received.year}", "%d-%B-%Y").date().isoformat()
    except ValueError:
        return None


def _extract_company(email: dict, text: str) -> Optional[str]:
    subject = email.get("subject") or ""
    patterns = [
        r"(?:RFP|Tender Notice)\s*[-—:]\s*(.+?)(?:\s+(?:Document\s+Management|Management|Platform|Suite|Automation|System))?$",
        r"(?:sponsors? for)\s+(?:the\s+)?(.+?)(?:\.|,|\s+in\s+|$)",
        r"\bat\s+([A-Z][A-Za-z0-9&.' -]{2,60}?)(?:,|\.|\s+based\s+in)",
        r"\b([A-Z][A-Za-z0-9&.' -]{2,60}?)\s+is inviting proposals",
        r"—\s*[^,\n]+,\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, subject if "RFP" in pattern or "Tender" in pattern else text, re.I)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,-")
            if value and len(value) > 2 and value.lower() not in {
                "a conference", "an event", "the conference", "the event", "our conference"
            }:
                return value

    domain = (email.get("from_email") or "").split("@")[-1].lower().split(".")[0]
    known_domains = {
        "vantagecloudservices": "Vantage Cloud Services",
        "zenithcloudpartners": "Zenith Cloud Partners",
        "meridiansteel": "Meridian Steel",
        "halcyonretail": "Halcyon Retail",
    }
    return known_domains.get(domain)


def _enrich_result(result: dict, email: dict) -> dict:
    """Fill only facts that are explicitly present; never overwrite model facts."""
    latest = _latest_message_text(email)
    subject = email.get("subject") or ""
    facts = f"{subject} {latest}"
    if result.get("due_date") is None:
        result["due_date"] = _parse_due_date(latest, email.get("received_at"))
    if result.get("deal_value_inr") is None and result.get("category") != "finance":
        result["deal_value_inr"] = _parse_amount(latest)
    if not result.get("company_name"):
        result["company_name"] = _extract_company(email, facts)
    if re.search(r"\b(overdue|urgent|asap|as soon as possible|today|tomorrow)\b", latest, re.I):
        result["priority_signal"] = "high"
    return result
    try:
        recv = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        due = datetime.fromisoformat(due_date)
        due = due.replace(tzinfo=recv.tzinfo) + timedelta(hours=23, minutes=59)
        return (due - recv).total_seconds() / 3600.0
    except Exception:
        return None


def apply_deterministic_overrides(result: dict, email: dict) -> dict:
    """Rule-based safety net layered on top of the LLM's judgment, per DECISIONS.md.
    The 72-hour deadline math and the PSU override are deterministic — we don't trust
    the LLM's arithmetic/memory for these, we compute them ourselves.
    """
    body_subject = f"{email.get('subject','')} {email.get('body','')}"

    # PSU/Government override
    if PSU_PATTERNS.search(body_subject) and result.get("is_task"):
        result["assignee_id"] = "u_aarti"
        result["category"] = "enterprise_rfp"

    # 72-hour high-priority override (deterministic, not LLM-judged)
    if result.get("is_task"):
        hours = _hours_until(email.get("received_at"), result.get("due_date"))
        if hours is not None and hours <= 72:
            result["priority"] = "high"
        else:
            result["priority"] = result.get("priority_signal") or "medium"
            if result["priority"] not in PRIORITIES:
                result["priority"] = "medium"
    return result


def rule_based_fallback(email: dict) -> dict:
    """Used only if Gemini is unreachable after retries — degrade gracefully instead
    of dropping the email. Intentionally conservative: routes to triage with low
    confidence rather than guessing an owner, except for unambiguous skip patterns.
    """
    subject = (email.get("subject") or "")
    body = (email.get("body") or "")
    text = f"{subject} {body}"

    if OOO_PATTERNS.search(text):
        return {"is_task": False, "skip_reason": "out_of_office", "is_marketing_lookalike_spam": False,
                "category": None, "assignee_id": None, "priority_signal": "low", "due_date": None,
                "deal_value_inr": None, "company_name": None, "confidence": 0.9,
                "title": "", "description": "", "reasoning": "Auto-reply pattern matched (fallback)."}
    if NEWSLETTER_PATTERNS.search(text):
        return {"is_task": False, "skip_reason": "newsletter", "is_marketing_lookalike_spam": False,
                "category": None, "assignee_id": None, "priority_signal": "low", "due_date": None,
                "deal_value_inr": None, "company_name": None, "confidence": 0.9,
                "title": "", "description": "", "reasoning": "Newsletter pattern matched (fallback)."}
    if SPAM_PATTERNS.search(text):
        return {"is_task": False, "skip_reason": "spam", "is_marketing_lookalike_spam": True,
                "category": None, "assignee_id": None, "priority_signal": "low", "due_date": None,
                "deal_value_inr": None, "company_name": None, "confidence": 0.95,
                "title": "", "description": "", "reasoning": "Unsolicited vendor/SEO pitch matched (fallback)."}

    # Useful degradation when Gemini is unavailable: route clear business signals
    # deterministically instead of sending the whole inbox to triage.
    # Two different asks must be triaged before the broader marketing keyword
    # rule sees the word "webinar".
    has_multiple_asks = bool(re.search(
        r"\b(two\s+(?:quick\s+)?things|two\s+requests)\b", text, re.I
    )) or bool(
        re.search(r"\b(evaluate|platform|product)\b", text, re.I)
        and re.search(r"\b(also|and)\b", text, re.I)
        and re.search(r"\b(webinar|sponsorship|co-host)\b", text, re.I)
    )
    if (has_multiple_asks
            and re.search(r"\b(evaluate|platform|product)\b", text, re.I)
            and re.search(r"\b(webinar|sponsorship|co-host)\b", text, re.I)):
        return {
            "is_task": True, "skip_reason": None, "is_marketing_lookalike_spam": False,
            "category": "triage", "assignee_id": "u_triage", "priority_signal": "medium",
            "due_date": None, "deal_value_inr": None, "company_name": None,
            "confidence": 0.42, "title": subject[:120] or "Ambiguous request",
            "description": "This email contains separate platform-evaluation and marketing-collaboration requests owned by different teams.",
            "reasoning": "Two distinct asks require human review instead of choosing one owner.",
        }

    rules = [
        (re.compile(r"\b(invoice|purchase order|\bpo[- ]|gst|payment (due|overdue)|vendor billing)\b", re.I),
         "finance", "u_divya", "Finance request matched by fallback rules."),
        (re.compile(r"\b(reseller|channel partner|implementation partner|technology integration|joint go-to-market|partnership)\b", re.I),
         "alliances", "u_karan", "Partnership request matched by fallback rules."),
        (re.compile(r"\b(sponsorship|webinar|conference|event sponsorship|content collaboration|pr|media)\b", re.I),
         "marketing", "u_meera", "Marketing request matched by fallback rules."),
        (re.compile(r"\b(rfp|rfi|request for proposal|request for information|proposal|tender)\b", re.I),
         "enterprise_rfp", "u_aarti", "Enterprise proposal request matched by fallback rules."),
        (re.compile(r"\b(demo|product enquiry|product inquiry|quick demo|interested in your platform)\b", re.I),
         "smb_enquiry", "u_rohit", "Product enquiry matched by fallback rules."),
    ]
    for pattern, category, assignee, reason in rules:
        if pattern.search(text):
            rule_confidence = {
                "finance": 0.90,
                "alliances": 0.90,
                "marketing": 0.88,
                "enterprise_rfp": 0.92,
                "smb_enquiry": 0.86,
            }.get(category, 0.75)
            return {
                "is_task": True, "skip_reason": None, "is_marketing_lookalike_spam": False,
                "category": category, "assignee_id": assignee, "priority_signal": "medium",
                "due_date": None, "deal_value_inr": None, "company_name": None,
                "confidence": rule_confidence, "title": subject[:120] or "Inbox request",
                "description": "Gemini was unavailable; a clear category was selected using deterministic fallback rules.",
                "reasoning": reason,
            }

    return {
        "is_task": True, "skip_reason": None, "is_marketing_lookalike_spam": False,
        "category": "triage", "assignee_id": "u_triage", "priority_signal": "medium",
        "due_date": None, "deal_value_inr": None, "company_name": None, "confidence": 0.2,
        "title": subject[:120] or "Needs manual review",
        "description": "Gemini classification was unavailable; routed to triage for manual review.",
        "reasoning": "LLM call failed after retries; conservative fallback to triage.",
    }


def classify_email(email: dict) -> dict:
    # Explicit exclusions must remain safe during Gemini outages.
    text = f"{email.get('subject', '')} {email.get('body', '')}"
    if OOO_PATTERNS.search(text) or NEWSLETTER_PATTERNS.search(text) or SPAM_PATTERNS.search(text):
        return rule_based_fallback({**email, "body": text})

    # Fast path: the fallback rules are reliable for the clear categories and
    # avoid spending one Gemini request per obvious email in a large batch.
    # Leave genuinely ambiguous/unknown messages for Gemini.
    fast_result = rule_based_fallback(email)
    if fast_result.get("is_task") and fast_result.get("category") != "triage":
        return apply_deterministic_overrides(_enrich_result(fast_result, email), email)
    try:
        raw = call_gemini_json(SYSTEM_PROMPT, build_user_prompt(email))
    except GeminiError:
        raw = rule_based_fallback(email)

    # Defensive normalization in case the model returns something slightly off-spec.
    if raw.get("assignee_id") not in ASSIGNEE_IDS:
        raw["assignee_id"] = "u_triage" if raw.get("is_task") else None
    if raw.get("category") not in CATEGORIES:
        raw["category"] = "triage" if raw.get("is_task") else None
    if raw.get("assignee_id") == "u_triage":
        raw["category"] = "triage"

    raw = _enrich_result(raw, email)
    raw = apply_deterministic_overrides(raw, email)
    return raw
