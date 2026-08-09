import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, UniqueConstraint, Index
from .database import Base


def gen_task_id() -> str:
    return "tsk_" + uuid.uuid4().hex[:10]


def now_iso():
    return datetime.now(timezone.utc)


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(String, primary_key=True, default=gen_task_id)
    candidate_id = Column(String, nullable=False, index=True)
    source_email_id = Column(String, nullable=False)
    thread_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    assignee_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    due_date = Column(String, nullable=True)  # YYYY-MM-DD
    deal_value_inr = Column(Integer, nullable=True)
    company_name = Column(String, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)

    created_at = Column(DateTime(timezone=True), default=now_iso)
    updated_at = Column(DateTime(timezone=True), default=now_iso, onupdate=now_iso)

    __table_args__ = (
        Index("ix_tasks_candidate_thread", "candidate_id", "thread_id"),
    )

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "candidate_id": self.candidate_id,
            "source_email_id": self.source_email_id,
            "thread_id": self.thread_id,
            "title": self.title,
            "description": self.description,
            "assignee_id": self.assignee_id,
            "category": self.category,
            "priority": self.priority,
            "due_date": self.due_date,
            "deal_value_inr": self.deal_value_inr,
            "company_name": self.company_name,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EmailLog(Base):
    """
    Tracks every email a candidate has ever ingested — including ones that never
    became a task (skipped: spam / newsletter / auto-reply) — so the chat interface
    can answer questions about the whole batch without re-calling Gemini for facts
    we already computed, and so re-ingesting the same email_id is a no-op (idempotency).
    """
    __tablename__ = "email_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String, nullable=False, index=True)
    email_id = Column(String, nullable=False)
    thread_id = Column(String, nullable=False, index=True)
    run_label = Column(String, nullable=True)

    decision = Column(String, nullable=False)  # created | updated | skipped | error
    task_id = Column(String, nullable=True)

    category = Column(String, nullable=True)
    assignee_id = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    is_spurious_risk = Column(String, nullable=True)  # "marketing_lookalike_spam" etc, else null

    reasoning = Column(Text, nullable=True)
    subject = Column(String, nullable=True)
    from_email = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=now_iso)

    __table_args__ = (
        UniqueConstraint("candidate_id", "email_id", name="uq_candidate_email"),
    )

    def to_dict(self):
        return {
            "email_id": self.email_id,
            "thread_id": self.thread_id,
            "decision": self.decision,
            "task_id": self.task_id,
            "category": self.category,
            "assignee_id": self.assignee_id,
            "priority": self.priority,
            "confidence": self.confidence,
            "is_spurious_risk": self.is_spurious_risk,
            "reasoning": self.reasoning,
            "subject": self.subject,
            "from_email": self.from_email,
            "run_label": self.run_label,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
