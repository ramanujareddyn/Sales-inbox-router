from typing import Optional, List
from pydantic import BaseModel, field_validator
from .config import ASSIGNEE_IDS, CATEGORIES, PRIORITIES, normalize_candidate_id


class EnumFieldError(Exception):
    """Raised to produce the exact 400 error shape required by the spec (§5.1)."""
    def __init__(self, field: str, received, allowed: list):
        self.field = field
        self.received = received
        self.allowed = allowed
        super().__init__(f"invalid_enum_value: {field}")


class TaskCreate(BaseModel):
    candidate_id: str
    source_email_id: str
    thread_id: str
    title: str
    description: Optional[str] = None
    assignee_id: str
    category: str
    priority: str
    due_date: Optional[str] = None
    deal_value_inr: Optional[int] = None
    company_name: Optional[str] = None
    confidence: float = 0.5

    @field_validator("candidate_id")
    @classmethod
    def _norm_candidate(cls, v):
        return normalize_candidate_id(v)

    @field_validator("assignee_id")
    @classmethod
    def _check_assignee(cls, v):
        if v not in ASSIGNEE_IDS:
            raise ValueError(f"invalid assignee_id: {v}")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"invalid category: {v}")
        return v

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v):
        if v not in PRIORITIES:
            raise ValueError(f"invalid priority: {v}")
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    deal_value_inr: Optional[int] = None
    company_name: Optional[str] = None
    confidence: Optional[float] = None

    @field_validator("assignee_id")
    @classmethod
    def _check_assignee(cls, v):
        if v is not None and v not in ASSIGNEE_IDS:
            raise ValueError(f"invalid assignee_id: {v}")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"invalid category: {v}")
        return v

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v):
        if v is not None and v not in PRIORITIES:
            raise ValueError(f"invalid priority: {v}")
        return v


class EmailIn(BaseModel):
    email_id: str
    thread_id: str
    message_index: Optional[int] = 0
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    to: Optional[str] = None
    cc: Optional[List[str]] = []
    subject: Optional[str] = ""
    body: Optional[str] = ""
    received_at: Optional[str] = None
    attachments: Optional[List[str]] = []
    is_reply: Optional[bool] = False


class IngestRequest(BaseModel):
    candidate_id: str
    emails: List[EmailIn]
    run_label: Optional[str] = None

    @field_validator("candidate_id")
    @classmethod
    def _norm(cls, v):
        return normalize_candidate_id(v)


class ChatRequest(BaseModel):
    candidate_id: str
    query: str

    @field_validator("candidate_id")
    @classmethod
    def _norm(cls, v):
        return normalize_candidate_id(v)
