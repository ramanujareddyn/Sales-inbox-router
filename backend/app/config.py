import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
CANDIDATE_ID_DEFAULT = os.getenv("CANDIDATE_ID", "").strip().lower()

ASSIGNEE_IDS = ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"]
CATEGORIES = ["enterprise_rfp", "smb_enquiry", "marketing", "alliances", "finance", "triage"]
PRIORITIES = ["high", "medium", "low"]

_DEFAULT_TEAM_ROSTER = [
    {"user_id": "u_aarti", "name": "Aarti Menon", "department": "Sales — Enterprise",
     "scope": "RFPs, RFIs, tenders, and inbound deals above ₹10,00,000"},
    {"user_id": "u_rohit", "name": "Rohit Sharma", "department": "Sales — SMB",
     "scope": "Product enquiries, demo requests, deals at or below ₹10,00,000"},
    {"user_id": "u_meera", "name": "Meera Iyer", "department": "Marketing",
     "scope": "Webinars, event and conference sponsorships, content collaborations, PR and media"},
    {"user_id": "u_karan", "name": "Karan Doshi", "department": "Alliances",
     "scope": "Reseller, channel partner, and technology integration proposals"},
    {"user_id": "u_divya", "name": "Divya Rao", "department": "Finance",
     "scope": "Invoices, purchase orders, payment reminders, GST and vendor billing"},
    {"user_id": "u_triage", "name": "Triage Queue", "department": "Operations",
     "scope": "Ambiguous items requiring human review"},
]

_ROSTER_PATH = Path(__file__).resolve().parents[2] / "data" / "team_roster.json"
try:
    _roster_payload = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    TEAM_ROSTER = _roster_payload["team"]
except (OSError, ValueError, KeyError, TypeError):
    TEAM_ROSTER = _DEFAULT_TEAM_ROSTER


def normalize_candidate_id(email: str) -> str:
    return (email or "").strip().lower()
